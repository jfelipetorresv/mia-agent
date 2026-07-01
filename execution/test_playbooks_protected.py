"""
Mia · test_playbooks_protected.py — gate de H.6 (playbooks protegidos / semilla).

Verifica contra la DB real que la bandera `protected` inmuniza los playbooks core frente al
mantenimiento automático:

  1. register_playbook(protected=True) fija la columna; get_playbook la devuelve.
  2. UPSERT sobre un protegido NO pisa content/summary/applies_when (salvo force=True).
  3. Curator.find_candidates excluye pares protegidos.
  4. Curator._prune_candidates excluye protegidos.
  5. Curator._execute_merge con origen protegido → 0 (no archiva las fuentes).
  6. Curator._execute_deletion NO archiva un protegido.
  7. SkillImprover.process_trace sobre un protegido → None (no propone mejora).
  8. GEPALoop.prune_unused_skills NO archiva protegidos.
  9. ux.apply_proposal (improve_playbook) con target protegido → HTTP 409.
 10. RLS A↔B.

HALT si falla (CLAUDE.md §G). Exit 0 = PASS · exit 1 = FAIL.
    .venv\\Scripts\\python.exe execution\\test_playbooks_protected.py
"""
from __future__ import annotations
import asyncio
import os
import sys
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

import init_playbooks                                   # noqa: E402  (migración 005)
import init_playbooks_protected                         # noqa: E402  (migración 014)
import init_feedback                                    # noqa: E402  (migración 006)
from fastapi import HTTPException                        # noqa: E402
from mia import embeddings                               # noqa: E402
from mia.agent import llm                                # noqa: E402
from mia.db import pool                                  # noqa: E402
from mia.memory.playbook_manager import Playbook, PlaybookManager  # noqa: E402
from mia.memory.curator import Curator                   # noqa: E402
from mia.memory.skill_improver import SkillImprover      # noqa: E402
from mia.memory.gepa import GEPALoop                      # noqa: E402
from mia.api.routes import ux                            # noqa: E402

_results: list[tuple[str, bool]] = []


def check(name: str, ok: bool) -> None:
    _results.append((name, bool(ok)))
    print(("  [OK]   " if ok else "  [FAIL] ") + name)


# ── mocks (sin red) ──────────────────────────────────────────────────────────
def _fake_embed(texts):
    return [[0.5] + [0.0] * 1023 for _ in texts]


def _fake_call_llm(messages, *, task=None, model=None, **kw):
    return SimpleNamespace(
        choices=[SimpleNamespace(message=SimpleNamespace(content="CONTENIDO_MOCK"))],
        usage=SimpleNamespace(prompt_tokens=1, completion_tokens=1, total_tokens=2))


embeddings.embed_texts = _fake_embed
llm.call_llm = _fake_call_llm

PG = dict(
    host=os.getenv("PG_HOST", "127.0.0.1"), port=os.getenv("PG_PORT", "5432"),
    dbname=os.getenv("PG_DB", "mia"), user="postgres", password=os.getenv("PG_PASSWORD", ""),
)


def make_tenant(label: str) -> str:
    with psycopg.connect(autocommit=True, **PG) as c:
        return str(c.execute(
            "INSERT INTO tenants(name) VALUES(%s) RETURNING id", (f"PROT_TEST {label}",)
        ).fetchone()[0])


def drop_test_tenants() -> None:
    with psycopg.connect(autocommit=True, **PG) as c:
        c.execute("DELETE FROM tenants WHERE name LIKE 'PROT_TEST%'")


def vec_axis(i: int) -> list[float]:
    v = [0.0] * 1024
    v[i] = 1.0
    return v


def vec_cos(c: float) -> list[float]:
    import math
    v = [0.0] * 1024
    v[0] = c
    v[1] = math.sqrt(max(0.0, 1.0 - c * c))
    return v


async def insert_pb(tenant: str, title: str, embedding, *, summary="s", applies="w",
                    content="cuerpo", status="active", last_used=None, protected=False,
                    created=None) -> str:
    created_sql = "now()" if created is None else "%(created)s"
    async with pool.tenant_connection(tenant) as conn:
        row = await (await conn.execute(
            "INSERT INTO playbooks (tenant_id, title, summary, applies_when, content, "
            f"embedding, status, last_used_at, protected, created_at) "
            f"VALUES (%(t)s::uuid,%(ti)s,%(su)s,%(ap)s,%(co)s,%(em)s,%(st)s,%(lu)s,%(pr)s,{created_sql}) "
            "RETURNING id",
            {"t": tenant, "ti": title, "su": summary, "ap": applies, "co": content,
             "em": embedding, "st": status, "lu": last_used, "pr": protected, "created": created},
        )).fetchone()
    return str(row[0])


async def field(tenant: str, pid: str, col: str):
    async with pool.tenant_connection(tenant) as conn:
        row = await (await conn.execute(
            f"SELECT {col} FROM playbooks WHERE id=%s::uuid", (pid,))).fetchone()
    return row[0] if row else None


DAYS_AGO_100 = "now() - interval '100 days'"


async def run_gate(t: dict) -> None:
    await pool.open_pool()
    try:
        A, B = t["a"], t["b"]
        mgr = PlaybookManager(pool=pool, tenant_id=A)

        # === 1 · register_playbook(protected=True) + get_playbook ===
        pid_prot = await mgr.register_playbook(
            Playbook(id="x", title="Semilla Core", summary="s", applies_when="w", content="v1-core"),
            protected=True)
        check("1a · register_playbook(protected=True) fija la columna",
              (await field(A, pid_prot, "protected")) is True)
        got = await mgr.get_playbook("Semilla Core")
        check("1b · get_playbook incluye 'protected'", got is not None and got.get("protected") is True)

        # === 2 · UPSERT sobre protegido NO pisa content (salvo force) ===
        await mgr.register_playbook(
            Playbook(id="x", title="Semilla Core", summary="s2", applies_when="w2", content="v2-auto"),
            protected=True)
        check("2a · upsert automático NO pisa el contenido de un protegido",
              (await field(A, pid_prot, "content")) == "v1-core")
        await mgr.register_playbook(
            Playbook(id="x", title="Semilla Core", summary="s3", applies_when="w3", content="v3-force"),
            protected=True, force=True)
        check("2b · upsert con force=True SÍ actualiza el protegido",
              (await field(A, pid_prot, "content")) == "v3-force")

        # un playbook normal (no protegido) SÍ se actualiza por upsert
        pid_norm = await mgr.register_playbook(
            Playbook(id="x", title="Normal", summary="s", applies_when="w", content="n1"))
        await mgr.register_playbook(
            Playbook(id="x", title="Normal", summary="s", applies_when="w", content="n2"))
        check("2c · upsert normal (no protegido) sí actualiza contenido",
              (await field(A, pid_norm, "content")) == "n2")

        cur = Curator()

        # === 3 · find_candidates excluye pares protegidos ===
        # dos protegidos muy similares (cos ~1.0) → NO deben aparecer como candidatos
        pa = await insert_pb(A, "ProtSim A", vec_cos(1.0), protected=True)
        pb = await insert_pb(A, "ProtSim B", vec_cos(0.999), protected=True)
        cands = await cur.find_candidates(A)
        pair_ids = {frozenset((x, y)) for x, y, _ in cands}
        check("3a · find_candidates excluye pares protegidos",
              frozenset((pa, pb)) not in pair_ids)
        # dos NO protegidos igual de similares → SÍ candidatos (control)
        na = await insert_pb(A, "NormSim A", vec_cos(0.99))
        nb = await insert_pb(A, "NormSim B", vec_cos(0.995))
        cands2 = await cur.find_candidates(A)
        pair_ids2 = {frozenset((x, y)) for x, y, _ in cands2}
        check("3b · find_candidates SÍ incluye el par no protegido (control)",
              frozenset((na, nb)) in pair_ids2)

        # === 4 · _prune_candidates excluye protegidos ===
        old_prot = await insert_pb(A, "Viejo Protegido", vec_axis(5), protected=True,
                                   last_used=None)
        # fijar last_used_at a 100 días atrás
        async with pool.tenant_connection(A) as conn:
            await conn.execute(f"UPDATE playbooks SET last_used_at={DAYS_AGO_100} WHERE id=%s::uuid",
                               (old_prot,))
            old_norm = (await (await conn.execute(
                "INSERT INTO playbooks (tenant_id,title,summary,applies_when,content,embedding,status,last_used_at) "
                f"VALUES (%s::uuid,'Viejo Normal','s','w','c',%s,'active',{DAYS_AGO_100}) RETURNING id",
                (A, vec_axis(6)))).fetchone())[0]
        prune_ids = {r["id"] for r in await cur._prune_candidates(A)}
        check("4a · _prune_candidates excluye el protegido viejo", old_prot not in prune_ids)
        check("4b · _prune_candidates SÍ incluye el normal viejo (control)",
              str(old_norm) in prune_ids)

        # === 5 · _execute_merge con origen protegido → 0, fuentes intactas ===
        async with pool.tenant_connection(A) as conn:
            merged = await cur._execute_merge(conn, A, {"source_ids": [pa, pb],
                                                        "target_title": "No debería crearse"})
        check("5a · _execute_merge con origen protegido devuelve 0", merged == 0)
        check("5b · las fuentes protegidas siguen activas",
              (await field(A, pa, "status")) == "active" and (await field(A, pb, "status")) == "active")

        # === 6 · _execute_deletion NO archiva un protegido ===
        async with pool.tenant_connection(A) as conn:
            deleted = await Curator._execute_deletion(conn, {"id": old_prot})
        check("6a · _execute_deletion devuelve 0 para un protegido", deleted == 0)
        check("6b · el protegido sigue activo tras _execute_deletion",
              (await field(A, old_prot, "status")) == "active")

        # === 7 · SkillImprover.process_trace sobre un protegido → None ===
        # el playbook debe estar usado > 1 vez para que, de NO ser protegido, propondría
        async with pool.tenant_connection(A) as conn:
            await conn.execute("UPDATE playbooks SET usage_count=5 WHERE id=%s::uuid", (pid_prot,))
        trace = {
            "tenant_id": A, "matter_id": "m-1", "hitl_outcome": "approved",
            "activated_playbooks": [pid_prot],
            "input": "consulta jurídica de prueba para el playbook protegido",
            "output": "respuesta jurídica de prueba suficientemente larga para el candidato",
            "timestamp": "2026-06-30T10:00:00+00:00",
        }
        res = await SkillImprover().process_trace(A, trace)
        check("7 · process_trace sobre playbook protegido → None (no propone mejora)", res is None)

        # === 8 · GEPALoop.prune_unused_skills NO archiva protegidos ===
        # protegido viejo y sin uso: sin la guarda, GEPA lo archivaría.
        old_prot2 = await insert_pb(A, "GEPA Protegido", vec_axis(7), protected=True,
                                    last_used=None, created="2020-01-01T00:00:00+00:00")
        pruned = await GEPALoop().prune_unused_skills(A, days=60)
        check("8a · prune_unused_skills NO archiva el protegido", old_prot2 not in pruned)
        check("8b · el protegido sigue activo tras GEPA",
              (await field(A, old_prot2, "status")) == "active")

        # === 9 · ux.apply_proposal con target protegido → 409 ===
        async with pool.tenant_connection(A) as conn:
            prop_id = (await (await conn.execute(
                "INSERT INTO feedback_proposals (tenant_id, proposal_type, target_playbook_id, "
                "suggested_content, rationale, status) "
                "VALUES (%s::uuid,'improve_playbook',%s::uuid,%s,%s,'pending') "
                "RETURNING id::text",
                (A, pid_prot, "contenido sugerido que NO debe aplicarse", "prueba H.6"))
            ).fetchone())[0]
        fake_req = SimpleNamespace(state=SimpleNamespace(tenant_id=A))
        status_code = None
        try:
            await ux.apply_proposal(prop_id, fake_req)
        except HTTPException as e:
            status_code = e.status_code
        check("9a · apply_proposal sobre playbook protegido → 409", status_code == 409)
        check("9b · el contenido protegido no cambió por la sugerencia",
              (await field(A, pid_prot, "content")) == "v3-force")

        # === 10 · RLS A↔B ===
        async with pool.tenant_connection(B) as conn:
            nb_cnt = (await (await conn.execute(
                "SELECT count(*) FROM playbooks WHERE title='Semilla Core'")).fetchone())[0]
        check("10 · RLS: B no ve el playbook protegido de A", nb_cnt == 0)
    finally:
        await pool.close_pool()


def main() -> int:
    print("== Tarea H.6 · playbooks protegidos (semilla/core inmune al mantenimiento) ==")
    if not os.getenv("PG_PASSWORD"):
        print("  [FAIL] PG_PASSWORD vacío en .env")
        return 1

    init_playbooks.apply()
    init_playbooks_protected.apply()
    init_feedback.apply()

    drop_test_tenants()
    t = {k: make_tenant(k) for k in ("a", "b")}
    try:
        asyncio.run(run_gate(t))
    finally:
        drop_test_tenants()

    passed = sum(1 for _, ok in _results if ok)
    total = len(_results)
    print(f"\n{passed}/{total} checks PASS")
    if passed == total:
        print("playbooks protected OK — H.6 verificado (semillas inmunes a Curator/GEPA/SkillImprover/UX).")
        return 0
    print("playbooks protected FAIL — HALT: no avanzar (CLAUDE.md §G).")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
