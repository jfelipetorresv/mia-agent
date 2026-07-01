"""
Mia · test_curator_hitl.py — gate de H.2 (Curator dry-run → HITL, cierra Riesgo #19).

Ejercita el flujo dry-run→propuesta→aprobar/rechazar contra la DB real, con LLM y embeddings
MOCKEADOS. Verifica: propose NO muta playbooks, la propuesta persiste, approve ejecuta + audita,
reject no muta, rollback automático en fallo, y coherencia del snapshot_hash sin cambios.

HALT si falla (CLAUDE.md §G). Exit 0 = PASS · exit 1 = FAIL.
    .venv\\Scripts\\python.exe execution\\test_curator_hitl.py
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

import init_playbooks                                  # noqa: E402  (migración 005)
import init_jurisdiction_foundation                    # noqa: E402  (migración 011 · audit_logs)
import init_curator_proposals                          # noqa: E402  (migración 012)
from mia import embeddings                             # noqa: E402
from mia.agent import llm                              # noqa: E402
from mia.db import pool                                # noqa: E402
from mia.memory.curator import Curator                 # noqa: E402

_results: list[tuple[str, bool]] = []


def check(name: str, ok: bool) -> None:
    _results.append((name, bool(ok)))
    print(("  [OK]   " if ok else "  [FAIL] ") + name)


# ── mocks (sin red) ──────────────────────────────────────────────────────────
def _fake_embed(texts):
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
            "INSERT INTO tenants(name) VALUES(%s) RETURNING id", (f"CURHITL_TEST {label}",)
        ).fetchone()[0])


def drop_test_tenants() -> None:
    with psycopg.connect(autocommit=True, **PG) as c:
        c.execute("DELETE FROM tenants WHERE name LIKE 'CURHITL_TEST%'")


def vec_axis(i: int) -> list[float]:
    v = [0.0] * 1024
    v[i] = 1.0
    return v


def vec_cos(c: float) -> list[float]:
    v = [0.0] * 1024
    v[0] = c
    v[1] = math.sqrt(max(0.0, 1.0 - c * c))
    return v


async def insert_pb(tenant: str, title: str, embedding, *, status="active", last_used=None,
                    content="cuerpo") -> str:
    async with pool.tenant_connection(tenant) as conn:
        row = await (await conn.execute(
            "INSERT INTO playbooks (tenant_id, title, summary, applies_when, content, "
            "embedding, status, last_used_at) "
            "VALUES (%s::uuid,%s,'s','w',%s,%s,%s,%s) RETURNING id",
            (tenant, title, content, embedding, status, last_used),
        )).fetchone()
    return str(row[0])


async def pb_by_title(tenant: str, title: str) -> dict | None:
    async with pool.tenant_connection(tenant) as conn:
        row = await (await conn.execute(
            "SELECT status, content FROM playbooks WHERE title=%s", (title,))).fetchone()
    return {"status": row[0], "content": row[1]} if row else None


async def proposal_status(tenant: str, pid: str) -> str | None:
    async with pool.tenant_connection(tenant) as conn:
        row = await (await conn.execute(
            "SELECT status FROM curator_proposals WHERE id=%s::uuid", (pid,))).fetchone()
    return row[0] if row else None


async def status_of(tenant: str, pid: str) -> str | None:
    async with pool.tenant_connection(tenant) as conn:
        row = await (await conn.execute(
            "SELECT status FROM playbooks WHERE id=%s::uuid", (pid,))).fetchone()
    return row[0] if row else None


async def count_active(tenant: str, title_like: str) -> int:
    async with pool.tenant_connection(tenant) as conn:
        return (await (await conn.execute(
            "SELECT count(*) FROM playbooks WHERE status='active' AND title LIKE %s",
            (title_like,))).fetchone())[0]


async def audit_count(tenant: str, action: str) -> int:
    async with pool.tenant_connection(tenant) as conn:
        return (await (await conn.execute(
            "SELECT count(*) FROM audit_logs WHERE action=%s", (action,))).fetchone())[0]


async def run_gate(t: dict) -> None:
    await pool.open_pool()
    try:
        cur = Curator()

        # ===================== 1 · propose (dry-run) NO muta =====================
        old = datetime.now(timezone.utc) - timedelta(days=91)
        c1 = await insert_pb(t["merge"], "C1", vec_axis(0))
        c2 = await insert_pb(t["merge"], "C2", vec_cos(0.9))          # cos 0.9 con C1 → merge
        stale = await insert_pb(t["merge"], "Stale", vec_axis(50), last_used=old)  # → deletion

        proposal = await cur.propose(t["merge"])
        check("propose devuelve 1 merge + 1 deletion",
              len(proposal.proposed_merges) == 1 and len(proposal.proposed_deletions) == 1)
        check("propose NO muta: C1/C2/Stale siguen activos",
              (await status_of(t["merge"], c1)) == "active"
              and (await status_of(t["merge"], c2)) == "active"
              and (await status_of(t["merge"], stale)) == "active")
        check("propose NO crea el consolidado", (await count_active(t["merge"], "Consolidado:%")) == 0)

        # ===================== 2 · la propuesta persiste =====================
        pend = await cur.list_proposals(t["merge"], status="pending")
        check("la propuesta persiste como pending", len(pend) == 1 and pend[0]["id"] == proposal.id)
        check("propose asignó snapshot_hash", bool(proposal.snapshot_hash))

        # ===================== 3 · RLS: B no ve las propuestas de A =====================
        check("RLS: tenant B no ve las propuestas de A",
              (await cur.list_proposals(t["b"], status="pending")) == [])

        # ===================== 4 · approve ejecuta + audita =====================
        res = await cur.apply_proposal(t["merge"], proposal.id, reviewed_by="abogado@x.co")
        check("approve devuelve status=approved con 1 merge + 1 deletion",
              res["status"] == "approved" and res["merges_done"] == 1 and res["deletions_done"] == 1)
        check("approve archiva los originales del merge",
              (await status_of(t["merge"], c1)) == "archived"
              and (await status_of(t["merge"], c2)) == "archived")
        check("approve crea el playbook consolidado", (await count_active(t["merge"], "Consolidado:%")) == 1)
        check("approve archiva el playbook obsoleto (deletion)",
              (await status_of(t["merge"], stale)) == "archived")
        check("approve deja registro en audit_logs",
              (await audit_count(t["merge"], "curator_proposal_approved")) == 1)
        # idempotencia: re-aprobar una propuesta ya approved no re-ejecuta
        res2 = await cur.apply_proposal(t["merge"], proposal.id)
        check("approve idempotente (no re-ejecuta una propuesta ya aprobada)",
              res2.get("status") == "approved" and res2.get("error"))

        # ===================== 5 · reject NO muta =====================
        r1 = await insert_pb(t["reject"], "R1", vec_axis(0))
        r2 = await insert_pb(t["reject"], "R2", vec_cos(0.9))
        prop_r = await cur.propose(t["reject"])
        rej = await cur.reject_proposal(t["reject"], prop_r.id, reviewed_by="abogado@x.co")
        check("reject devuelve status=rejected", rej["status"] == "rejected")
        check("reject NO muta playbooks (R1/R2 siguen activos)",
              (await status_of(t["reject"], r1)) == "active"
              and (await status_of(t["reject"], r2)) == "active")
        check("reject deja registro en audit_logs",
              (await audit_count(t["reject"], "curator_proposal_rejected")) == 1)

        # ===================== 6 · rollback automático en fallo =====================
        f1 = await insert_pb(t["fail"], "F1", vec_axis(0))
        f2 = await insert_pb(t["fail"], "F2", vec_cos(0.9))
        prop_f = await cur.propose(t["fail"])
        # forzar fallo DURANTE la ejecución (la fusión LLM revienta) → debe revertir TODO.
        _orig = llm.call_llm
        llm.call_llm = lambda *a, **k: (_ for _ in ()).throw(RuntimeError("LLM caído"))
        try:
            fail_res = await cur.apply_proposal(t["fail"], prop_f.id)
        finally:
            llm.call_llm = _orig
        check("apply con fallo devuelve status=failed", fail_res["status"] == "failed")
        check("rollback: F1/F2 siguen ACTIVOS tras el fallo (nada se archivó)",
              (await status_of(t["fail"], f1)) == "active"
              and (await status_of(t["fail"], f2)) == "active")
        check("rollback: no quedó consolidado a medias",
              (await count_active(t["fail"], "Consolidado:%")) == 0)
        check("fallo deja registro en audit_logs (curator_proposal_failed)",
              (await audit_count(t["fail"], "curator_proposal_failed")) == 1)

        # ===================== 7 · snapshot_hash coincide si no hay cambios =====================
        await insert_pb(t["noop"], "N1", vec_axis(0))
        await insert_pb(t["noop"], "N2", vec_axis(60))     # cos 0 → sin merge; recientes → sin poda
        prop_n = await cur.propose(t["noop"])
        check("propose en tenant estable → propuesta vacía", prop_n.is_empty())
        recomputed = Curator._snapshot_hash(await cur._snapshot_state(t["noop"]))
        check("snapshot_hash coincide antes/después si no hay cambios",
              prop_n.snapshot_hash == recomputed)

        # ===================== 8 · C.1: doble-approve concurrente → 1 gana, 1 rechazado ==========
        cc1 = await insert_pb(t["concurrent"], "CC1", vec_axis(0))
        cc2 = await insert_pb(t["concurrent"], "CC2", vec_cos(0.9))
        prop_c = await cur.propose(t["concurrent"])
        # dos aprobaciones EN PARALELO sobre la misma propuesta (FOR UPDATE serializa).
        r_a, r_b = await asyncio.gather(
            cur.apply_proposal(t["concurrent"], prop_c.id),
            cur.apply_proposal(t["concurrent"], prop_c.id),
        )
        approved = [r for r in (r_a, r_b) if r["status"] == "approved" and not r.get("error")]
        blocked = [r for r in (r_a, r_b) if r.get("error")]
        check("doble-approve concurrente: exactamente 1 aplica (approved)", len(approved) == 1)
        check("doble-approve concurrente: el 2º recibe 409 (no pendiente)",
              len(blocked) == 1 and "no está pendiente" in (blocked[0].get("error") or ""))
        check("doble-approve: los originales se archivaron UNA sola vez",
              (await status_of(t["concurrent"], cc1)) == "archived"
              and (await status_of(t["concurrent"], cc2)) == "archived"
              and (await count_active(t["concurrent"], "Consolidado:%")) == 1)

        # ===================== 9 · C.1: snapshot_hash mismatch → drift (409) =====================
        d1 = await insert_pb(t["drift"], "D1", vec_axis(0))
        d2 = await insert_pb(t["drift"], "D2", vec_cos(0.9))
        prop_d = await cur.propose(t["drift"])
        # el estado cambia DESPUÉS de proponer (se agrega un playbook activo) → hash distinto.
        await insert_pb(t["drift"], "D3 tardío", vec_axis(70))
        res_d = await cur.apply_proposal(t["drift"], prop_d.id)
        check("snapshot_hash mismatch → status=drift (409) con mensaje 'regenerar'",
              res_d["status"] == "drift" and "regenerar" in (res_d.get("error") or ""))
        check("drift: NO se ejecutó la fusión (D1/D2 siguen activos)",
              (await status_of(t["drift"], d1)) == "active"
              and (await status_of(t["drift"], d2)) == "active")
        check("drift: la propuesta vuelve a 'pending' (no quedó en 'applying')",
              (await proposal_status(t["drift"], prop_d.id)) == "pending")

        # ===================== 10 · C.1.3: ON CONFLICT DO UPDATE (no silenciar) ==================
        await insert_pb(t["conflict"], "X", vec_axis(0))
        await insert_pb(t["conflict"], "Y", vec_cos(0.9))
        prop_k = await cur.propose(t["conflict"])
        target_title = prop_k.proposed_merges[0]["target_title"]
        # el título consolidado YA existe (archivado, contenido viejo) → DO UPDATE debe reactivarlo.
        await insert_pb(t["conflict"], target_title, vec_axis(80), status="archived", content="VIEJO")
        res_k = await cur.apply_proposal(t["conflict"], prop_k.id)
        check("approve con título consolidado pre-existente → approved", res_k["status"] == "approved")
        row_k = await pb_by_title(t["conflict"], target_title)
        check("ON CONFLICT DO UPDATE reactiva+actualiza (no DO NOTHING)",
              row_k is not None and row_k["status"] == "active"
              and row_k["content"] == "CONTENIDO_FUSIONADO_MOCK")
    finally:
        await pool.close_pool()


def main() -> int:
    print("== Tarea H.2 · Curator dry-run → HITL (cierra Riesgo #19) ==")
    if not os.getenv("PG_PASSWORD"):
        print("  [FAIL] PG_PASSWORD vacío en .env")
        return 1

    init_playbooks.apply()
    init_jurisdiction_foundation.apply()   # audit_logs (011)
    init_curator_proposals.apply()         # curator_proposals (012)

    drop_test_tenants()
    t = {k: make_tenant(k) for k in
         ("a", "b", "merge", "reject", "fail", "noop", "concurrent", "drift", "conflict")}
    try:
        asyncio.run(run_gate(t))
    finally:
        drop_test_tenants()

    passed = sum(1 for _, ok in _results if ok)
    total = len(_results)
    print(f"\n{passed}/{total} checks PASS")
    if passed == total:
        print("Curator HITL OK — H.2 verificado (Riesgo #19 cerrado por dry-run→propuesta).")
        return 0
    print("Curator HITL FAIL — HALT: no avanzar (CLAUDE.md §G).")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
