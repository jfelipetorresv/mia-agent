"""
Mia · test_skill_improver.py — gate de H.4 (skills self-improving con HITL pending).

Verifica: extract_skill_candidate respeta los 3 requisitos (approved + activated_playbooks +
usado>1), propose_improvement persiste en feedback_proposals con status='pending' (NUNCA aprobado
solo), process_trace end-to-end, fire-and-forget seguro, y RLS A↔B.

HALT si falla (CLAUDE.md §G). Exit 0 = PASS · exit 1 = FAIL.
    .venv\\Scripts\\python.exe execution\\test_skill_improver.py
"""
from __future__ import annotations
import asyncio
import os
import sys
from pathlib import Path

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
import init_feedback                                   # noqa: E402  (migración 006 · feedback_proposals)
from mia.db import pool                                # noqa: E402
from mia.memory.skill_improver import (                # noqa: E402
    SkillCandidate,
    SkillImprover,
    extract_skill_candidate,
)

_results: list[tuple[str, bool]] = []


def check(name: str, ok: bool) -> None:
    _results.append((name, bool(ok)))
    print(("  [OK]   " if ok else "  [FAIL] ") + name)


PG = dict(
    host=os.getenv("PG_HOST", "127.0.0.1"), port=os.getenv("PG_PORT", "5432"),
    dbname=os.getenv("PG_DB", "mia"), user="postgres", password=os.getenv("PG_PASSWORD", ""),
)


def make_tenant(label: str) -> str:
    with psycopg.connect(autocommit=True, **PG) as c:
        return str(c.execute(
            "INSERT INTO tenants(name) VALUES(%s) RETURNING id", (f"SKILLIMP_TEST {label}",)
        ).fetchone()[0])


def drop_test_tenants() -> None:
    with psycopg.connect(autocommit=True, **PG) as c:
        c.execute("DELETE FROM tenants WHERE name LIKE 'SKILLIMP_TEST%'")


async def insert_pb(tenant: str, title: str, *, usage_count: int, content="cuerpo del playbook") -> str:
    async with pool.tenant_connection(tenant) as conn:
        row = await (await conn.execute(
            "INSERT INTO playbooks (tenant_id, title, summary, applies_when, content, usage_count) "
            "VALUES (%s::uuid,%s,'s','w',%s,%s) RETURNING id::text",
            (tenant, title, content, usage_count))).fetchone()
    return row[0]


async def proposal_row(tenant: str, pid: str) -> dict | None:
    async with pool.tenant_connection(tenant) as conn:
        row = await (await conn.execute(
            "SELECT proposal_type, status, target_playbook_id::text, trace_ids "
            "FROM feedback_proposals WHERE id=%s::uuid", (pid,))).fetchone()
    if not row:
        return None
    return {"type": row[0], "status": row[1], "target": row[2], "trace_ids": row[3]}


async def count_proposals(tenant: str) -> int:
    async with pool.tenant_connection(tenant) as conn:
        return (await (await conn.execute(
            "SELECT count(*) FROM feedback_proposals")).fetchone())[0]


def _trace(tenant, pid, *, outcome="approved", playbooks=None):
    return {
        "tenant_id": tenant, "matter_id": "m-1", "hitl_outcome": outcome,
        "activated_playbooks": playbooks if playbooks is not None else [pid],
        "input": "¿Cómo redacto una acción de tutela por derecho de petición?",
        "output": "Para la tutela: identifique el derecho fundamental, los hechos y la pretensión…",
        "timestamp": "2026-06-30T10:00:00+00:00",
    }


async def run_gate(t: dict) -> None:
    await pool.open_pool()
    try:
        A, B = t["a"], t["b"]
        pid = await insert_pb(A, "Tutela", usage_count=3)
        imp = SkillImprover()

        # ===================== 1 · extract respeta los 3 requisitos =====================
        check("extract: outcome!=approved → None",
              extract_skill_candidate(_trace(A, pid, outcome="rejected"), relevance=5) is None)
        check("extract: activated_playbooks vacío → None",
              extract_skill_candidate(_trace(A, pid, playbooks=[]), relevance=5) is None)
        check("extract: relevancia < 2 (usado 1 vez) → None",
              extract_skill_candidate(_trace(A, pid), relevance=1) is None)
        cand = extract_skill_candidate(_trace(A, pid), relevance=3)
        check("extract: approved + playbooks + usado>1 → SkillCandidate",
              isinstance(cand, SkillCandidate) and cand.playbook_ids == [pid]
              and cand.signal_count == 3 and cand.trace_ids)

        # ===================== 2 · propose_improvement → pending (improve) =============
        existing = {"id": pid, "content": "cuerpo del playbook"}
        prop = await imp.propose_improvement(cand, existing)
        row = await proposal_row(A, prop["id"])
        check("propose_improvement persiste en feedback_proposals", row is not None)
        check("propuesta improve_playbook con target al playbook",
              row["type"] == "improve_playbook" and row["target"] == pid)
        check("propuesta queda PENDING (no aprobada automáticamente)", row["status"] == "pending")
        check("propuesta guarda procedencia (trace_ids)", bool(row["trace_ids"]))

        # ===================== 3 · propose_improvement sin existente → new_playbook ====
        prop2 = await imp.propose_improvement(cand, None)
        row2 = await proposal_row(A, prop2["id"])
        check("sin playbook existente → new_playbook, target NULL, pending",
              row2["type"] == "new_playbook" and row2["target"] is None and row2["status"] == "pending")

        # ===================== 4 · process_trace end-to-end ===========================
        before = await count_proposals(A)
        res = await imp.process_trace(A, _trace(A, pid))       # playbook usage_count=3 (>1)
        after = await count_proposals(A)
        check("process_trace con playbook usado>1 → propone (pending)",
              res is not None and res["status"] == "pending" and after == before + 1)

        # playbook usado 1 vez → NO propone
        pid_one = await insert_pb(A, "UsadoUnaVez", usage_count=1)
        res_none = await imp.process_trace(A, _trace(A, pid_one))
        check("process_trace con playbook usado 1 vez → None (sin propuesta)", res_none is None)

        # ===================== 5 · fire-and-forget seguro =============================
        imp_boom = SkillImprover()
        imp_boom.process_trace = lambda *a, **k: (_ for _ in ()).throw(RuntimeError("boom"))
        safe = await imp_boom.process_trace_safe(A, _trace(A, pid))
        check("process_trace_safe traga el error y devuelve None (no rompe el turno)", safe is None)

        # ===================== 6 · RLS A↔B =====================
        async with pool.tenant_connection(B) as conn:
            nb = (await (await conn.execute("SELECT count(*) FROM feedback_proposals")).fetchone())[0]
        check("RLS: B no ve las propuestas de A", nb == 0)

        # ===================== 7 · C.4: drain_bg_tasks espera las tareas en vuelo ==========
        from mia.agents import graph
        ran = {"done": False}

        async def _slow():
            await asyncio.sleep(0.05)
            ran["done"] = True

        task = asyncio.create_task(_slow())
        graph._BG_TASKS.add(task)
        task.add_done_callback(graph._BG_TASKS.discard)
        await graph.drain_bg_tasks()
        check("C.4: drain_bg_tasks espera las tareas fire-and-forget (no se pierden en shutdown)",
              ran["done"] is True and len(graph._BG_TASKS) == 0)
    finally:
        await pool.close_pool()


def main() -> int:
    print("== Tarea H.4 · Skills self-improving con HITL pending ==")
    if not os.getenv("PG_PASSWORD"):
        print("  [FAIL] PG_PASSWORD vacío en .env")
        return 1

    init_playbooks.apply()
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
        print("skill_improver OK — H.4 verificado (extracción + propuesta pending, HITL intacto).")
        return 0
    print("skill_improver FAIL — HALT: no avanzar (CLAUDE.md §G).")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
