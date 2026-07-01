"""
Mia · test_curator.py — gate del Módulo 3b (Curator cron + persistencia de playbooks).

Ejercita la tabla `playbooks` (migración 005), el `PlaybookManager` DB-backed (decisión #18) y
el `Curator` contra la DB real, con el LLM y los embeddings MOCKEADOS (sin red).

Embeddings de los candidatos: se insertan con vectores CONTROLADOS (vía SQL directo) para fijar
la similitud coseno exacta (0.9 candidato, 0.84 NO candidato). El `call_llm(task="curator")` se
mockea para devolver un cuerpo fusionado conocido.

HALT: si este gate falla, NO se avanza (CLAUDE.md §G). Salida: exit 0 = PASS · exit 1 = FAIL.

    .venv\\Scripts\\python.exe execution\\test_curator.py
"""
from __future__ import annotations
import asyncio
import math
import os
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace

import psycopg
from dotenv import load_dotenv

if sys.platform == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

ROOT = Path(__file__).resolve().parents[1]
load_dotenv(ROOT / ".env")
sys.path.insert(0, str(ROOT / "backend"))
sys.path.insert(0, str(ROOT / "execution"))

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

import init_playbooks                               # noqa: E402  (runner migración 005)
from mia import embeddings                          # noqa: E402
from mia.agent import llm                           # noqa: E402
from mia.agent.llm import _TASK_FALLBACK_CHAINS     # noqa: E402  (H.5: task → cadena de fallback)
from mia.db import pool                             # noqa: E402
from mia.memory.playbook_manager import Playbook, PlaybookManager  # noqa: E402
from mia.memory.curator import Curator              # noqa: E402
from mia.cron import build_scheduler                # noqa: E402

_results: list[tuple[str, bool]] = []


def check(name: str, ok: bool) -> None:
    _results.append((name, bool(ok)))
    print(("  [OK]   " if ok else "  [FAIL] ") + name)


# ── mocks (sin red) ──────────────────────────────────────────────────────────
def _fake_embed(texts):
    # vector fijo (la similitud de los candidatos se controla con inserts directos).
    return [[0.5] + [0.0] * 1023 for _ in texts]


def _fake_call_llm(messages, *, task=None, model=None, **kw):
    return SimpleNamespace(
        choices=[SimpleNamespace(message=SimpleNamespace(content="CONTENIDO_FUSIONADO_MOCK"))],
        usage=SimpleNamespace(prompt_tokens=10, completion_tokens=20, total_tokens=30),
    )


embeddings.embed_texts = _fake_embed
llm.call_llm = _fake_call_llm

PG = dict(
    host=os.getenv("PG_HOST", "127.0.0.1"), port=os.getenv("PG_PORT", "5432"),
    dbname=os.getenv("PG_DB", "mia"), user="postgres", password=os.getenv("PG_PASSWORD", ""),
)


def make_tenant(label: str) -> str:
    with psycopg.connect(autocommit=True, **PG) as c:
        return str(c.execute(
            "INSERT INTO tenants(name) VALUES(%s) RETURNING id", (f"CURATOR_TEST {label}",)
        ).fetchone()[0])


def drop_test_tenants() -> None:
    with psycopg.connect(autocommit=True, **PG) as c:
        c.execute("DELETE FROM tenants WHERE name LIKE 'CURATOR_TEST%'")


# vectores 1024-dim con similitud coseno controlada respecto al eje 0.
def vec_axis(i: int) -> list[float]:
    v = [0.0] * 1024
    v[i] = 1.0
    return v


def vec_cos(c: float) -> list[float]:
    """Vector unitario con coseno exactamente `c` respecto a vec_axis(0)."""
    v = [0.0] * 1024
    v[0] = c
    v[1] = math.sqrt(max(0.0, 1.0 - c * c))
    return v


async def insert_pb(tenant: str, title: str, embedding, *, summary="s", applies="w",
                    content="cuerpo", status="active", last_used=None) -> str:
    async with pool.tenant_connection(tenant) as conn:
        row = await (await conn.execute(
            "INSERT INTO playbooks (tenant_id, title, summary, applies_when, content, "
            "embedding, status, last_used_at) "
            "VALUES (%s::uuid,%s,%s,%s,%s,%s,%s,%s) RETURNING id",
            (tenant, title, summary, applies, content, embedding, status, last_used),
        )).fetchone()
    return str(row[0])


async def count_active(tenant: str, title_like: str | None = None) -> int:
    sql = "SELECT count(*) FROM playbooks WHERE status='active'"
    args: tuple = ()
    if title_like is not None:
        sql += " AND title LIKE %s"
        args = (title_like,)
    async with pool.tenant_connection(tenant) as conn:
        return (await (await conn.execute(sql, args)).fetchone())[0]


async def status_of(tenant: str, pid: str) -> str | None:
    async with pool.tenant_connection(tenant) as conn:
        row = await (await conn.execute(
            "SELECT status FROM playbooks WHERE id=%s::uuid", (pid,))).fetchone()
    return row[0] if row else None


async def run_gate(t: dict) -> None:
    await pool.open_pool()
    try:
        cur = Curator()
        check("Curator() se instancia sin error", isinstance(cur, Curator))

        # === migración: columnas clave ===
        async with pool.connection() as conn:
            cols = {r[0] for r in await (await conn.execute(
                "SELECT column_name FROM information_schema.columns "
                "WHERE table_schema='public' AND table_name='playbooks'")).fetchall()}
        need = {"tenant_id", "title", "summary", "applies_when", "content", "status",
                "usage_count", "last_used_at", "embedding"}
        check("migración: playbooks existe con columnas clave (incl. embedding/last_used_at)",
              need.issubset(cols))

        # === RLS por tenant ===
        await insert_pb(t["a"], "PB RLS", vec_axis(3))
        async with pool.tenant_connection(t["b"]) as conn:
            nb = (await (await conn.execute(
                "SELECT count(*) FROM playbooks WHERE title='PB RLS'")).fetchone())[0]
        async with pool.tenant_connection(t["a"]) as conn:
            na = (await (await conn.execute(
                "SELECT count(*) FROM playbooks WHERE title='PB RLS'")).fetchone())[0]
        check("RLS playbooks: mia_app aislado por tenant (A ve, B no)", na == 1 and nb == 0)

        # === PlaybookManager DB-backed: register + upsert ===
        mgr = PlaybookManager(pool=pool, tenant_id=t["a"])
        pid = await mgr.register_playbook(
            Playbook(id="ignored", title="PB Registrado", summary="resumen",
                     applies_when="cuando aplica", content="cuerpo del playbook"))
        async with pool.tenant_connection(t["a"]) as conn:
            exists = (await (await conn.execute(
                "SELECT count(*) FROM playbooks WHERE title='PB Registrado'")).fetchone())[0]
        check("register_playbook persiste en DB (no solo memoria)", exists == 1 and pid)

        await mgr.register_playbook(
            Playbook(id="x", title="PB Upsert", summary="s1", applies_when="w1", content="c1"))
        await mgr.register_playbook(
            Playbook(id="x", title="PB Upsert", summary="s2", applies_when="w2", content="c2"))
        async with pool.tenant_connection(t["a"]) as conn:
            dup = (await (await conn.execute(
                "SELECT count(*) FROM playbooks WHERE title='PB Upsert'")).fetchone())[0]
        check("register_playbook hace upsert (mismo título no duplica)", dup == 1)

        # === get_index ===
        idx = await mgr.get_index()
        check("get_index devuelve los títulos activos del tenant",
              "PB Registrado" in idx and "PB Upsert" in idx)

        # === mark_used ===
        await mgr.mark_used(pid)
        async with pool.tenant_connection(t["a"]) as conn:
            row = await (await conn.execute(
                "SELECT usage_count, last_used_at FROM playbooks WHERE id=%s::uuid", (pid,))).fetchone()
        check("mark_used incrementa usage_count y fija last_used_at",
              row[0] == 1 and row[1] is not None)

        # === load_playbooks ===
        check("load_playbooks de tenant sin playbooks -> []",
              (await cur.load_playbooks(t["empty"])) == [])
        for i in range(3):
            await insert_pb(t["load"], f"PB load {i}", vec_axis(i + 10))
        loaded = await cur.load_playbooks(t["load"])
        check("load_playbooks con 3 playbooks -> los 3", len(loaded) == 3)

        # === find_candidates ===
        await insert_pb(t["sin"], "S1", vec_axis(0))
        await insert_pb(t["sin"], "S2", vec_axis(7))     # coseno 0 con S1
        check("find_candidates sin solapamiento -> []",
              (await cur.find_candidates(t["sin"])) == [])

        ca = await insert_pb(t["con"], "C1", vec_axis(0))
        cb = await insert_pb(t["con"], "C2", vec_cos(0.9))   # coseno 0.9 con C1
        cands = await cur.find_candidates(t["con"])
        pair = {ca, cb}
        check("find_candidates con solapamiento (cos>0.85) -> aparece el par",
              len(cands) == 1 and {cands[0][0], cands[0][1]} == pair and cands[0][2] > 0.85)

        await insert_pb(t["umb"], "U1", vec_axis(0))
        await insert_pb(t["umb"], "U2", vec_cos(0.84))   # coseno 0.84 < umbral
        check("find_candidates con score 0.84 -> NO candidato",
              (await cur.find_candidates(t["umb"])) == [])

        # === consolidate ===
        n = await cur.consolidate(t["con"], cands)
        new_active = await count_active(t["con"], "Consolidado:%")
        check("consolidate crea un playbook fusionado nuevo en DB (contenido del LLM)",
              n == 1 and new_active == 1)
        async with pool.tenant_connection(t["con"]) as conn:
            fused = await (await conn.execute(
                "SELECT content FROM playbooks WHERE title LIKE 'Consolidado:%'")).fetchone()
        check("el playbook fusionado tiene el contenido devuelto por el LLM",
              fused[0] == "CONTENIDO_FUSIONADO_MOCK")
        check("consolidate archiva los dos originales (status='archived')",
              (await status_of(t["con"], ca)) == "archived"
              and (await status_of(t["con"], cb)) == "archived")

        # idempotente: re-consolidar el mismo par no crea otro
        n2 = await cur.consolidate(t["con"], cands)
        check("consolidate idempotente (mismo par dos veces -> no duplica)",
              n2 == 0 and (await count_active(t["con"], "Consolidado:%")) == 1)

        # === prune ===
        old = datetime.now(timezone.utc) - timedelta(days=91)
        recent = datetime.now(timezone.utc) - timedelta(days=10)
        p_old = await insert_pb(t["prune"], "P viejo", vec_axis(0), last_used=old)
        p_new = await insert_pb(t["prune"], "P reciente", vec_axis(1), last_used=recent)
        pruned = await cur.prune(t["prune"])
        check("prune archiva los obsoletos (last_used_at > 90 días)",
              pruned == 1 and (await status_of(t["prune"], p_old)) == "archived")
        check("prune respeta los usados hace poco (10 días -> activo)",
              (await status_of(t["prune"], p_new)) == "active")

        # === run completo (tenant con 2 playbooks distintos: sin candidatos ni poda) ===
        # C.5: _run_legacy() muta sin HITL; solo se permite en tests con el env guard.
        os.environ["MIA_ALLOW_CURATOR_LEGACY_RUN"] = "1"
        try:
            await insert_pb(t["run"], "R1", vec_axis(0))
            await insert_pb(t["run"], "R2", vec_axis(50))
            stats = await cur._run_legacy(t["run"])
            check("_run_legacy(tenant) devuelve dict con analyzed/consolidated/pruned/errors",
                  set(stats.keys()) == {"analyzed", "consolidated", "pruned", "errors"}
                  and stats["errors"] == 0)

            # === aislamiento: el Curator de A no toca los playbooks de B ===
            pb_b = await insert_pb(t["b"], "B intacto", vec_axis(2))
            await cur._run_legacy(t["a"])
            check("aislamiento: curator de A no toca playbooks de B",
                  (await status_of(t["b"], pb_b)) == "active")

            # === _run_all_tenants_legacy (enumeración mockeada) ===
            cur._list_tenant_ids = lambda: [t["run"], t["empty"]]
            allstats = await cur._run_all_tenants_legacy()
            check("_run_all_tenants_legacy itera los tenants y devuelve stats por tenant",
                  set(allstats.keys()) == {t["run"], t["empty"]}
                  and all("analyzed" in v for v in allstats.values()))
        finally:
            os.environ.pop("MIA_ALLOW_CURATOR_LEGACY_RUN", None)

        # === C.5: _run_legacy sin el env guard → RuntimeError (no muta sin HITL) ===
        guard_ok = False
        try:
            await cur._run_legacy(t["run"])
        except RuntimeError:
            guard_ok = True
        check("_run_legacy sin MIA_ALLOW_CURATOR_LEGACY_RUN → RuntimeError (fail-closed)", guard_ok)
    finally:
        await pool.close_pool()


def main() -> int:
    print("== Módulo 3b · Curator cron + persistencia de playbooks ==")
    if not os.getenv("PG_PASSWORD"):
        print("  [FAIL] PG_PASSWORD vacío en .env")
        return 1

    init_playbooks.apply()   # idempotente: asegura la tabla (rol postgres)

    # checks que no tocan DB
    # H.5: "curator" tiene cadena de fallback; el proveedor preferido es claude-sonnet
    # (cae a mia-local). Verificamos el primer eslabón y que mia-local esté en la cadena.
    curator_chain = _TASK_FALLBACK_CHAINS.get("curator", [])
    check('"curator" con cadena de fallback (preferido claude-sonnet o mia-local)',
          bool(curator_chain) and curator_chain[0] in ("mia-local", "claude-sonnet")
          and "mia-local" in curator_chain)
    check('el job "curator_weekly" está registrado en el scheduler',
          any(j["name"] == "curator_weekly" for j in build_scheduler().list_jobs()))

    drop_test_tenants()
    t = {k: make_tenant(k) for k in ("a", "b", "empty", "load", "sin", "con", "umb", "prune", "run")}
    try:
        asyncio.run(run_gate(t))
    finally:
        drop_test_tenants()

    passed = sum(1 for _, ok in _results if ok)
    total = len(_results)
    print(f"\n{passed}/{total} checks PASS")
    if passed == total:
        print("Curator OK — Módulo 3b verificado.")
        return 0
    print("Curator FAIL — HALT: no avanzar (CLAUDE.md §G).")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
