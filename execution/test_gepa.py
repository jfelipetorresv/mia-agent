"""
Mia · test_gepa.py — gate del GEPA Loop procedural.

Verifica detección de nuevos procedimientos, evolución bajo revisión humana,
grading, pruning y registro en scheduler.
"""
from __future__ import annotations

import asyncio
import json
import os
import sys
import tempfile
import time
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

import init_feedback  # noqa: E402
import init_playbooks  # noqa: E402
from mia.agent import llm  # noqa: E402
from mia.db import pool  # noqa: E402
from mia.memory.gepa import GEPALoop  # noqa: E402
from mia.memory.trace_capture import TraceCapture  # noqa: E402

PG = dict(
    host=os.getenv("PG_HOST", "127.0.0.1"),
    port=os.getenv("PG_PORT", "5432"),
    dbname=os.getenv("PG_DB", "mia"),
    user="postgres",
    password=os.getenv("PG_PASSWORD", ""),
)

_results: list[tuple[str, bool]] = []


def check(name: str, ok: bool) -> None:
    _results.append((name, bool(ok)))
    print(("  [OK]   " if ok else "  [FAIL] ") + name)


def fake_llm(messages, *, task=None, **kwargs):
    content = messages[-1]["content"]
    if "Devuelve JSON" in content:
        out = json.dumps({
            "title": "Procedimiento recurrente",
            "applies_when": "Cuando se repita una consulta similar aprobada.",
            "content": "Pasos observados desde trazas aprobadas.",
        })
    else:
        out = "Contenido mejorado propuesto desde correcciones del despacho."
    return SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content=out))])


def make_tenant(name: str) -> str:
    with psycopg.connect(autocommit=True, **PG) as c:
        return str(c.execute("INSERT INTO tenants(name) VALUES(%s) RETURNING id", (name,)).fetchone()[0])


def cleanup(*tenant_ids: str) -> None:
    with psycopg.connect(autocommit=True, **PG) as c:
        for tid in tenant_ids:
            c.execute("DELETE FROM tenants WHERE id=%s::uuid", (tid,))


def insert_playbook(tenant_id: str, title: str, *, status: str = "active", days_old: int = 0) -> str:
    created = datetime.now(timezone.utc) - timedelta(days=days_old)
    with psycopg.connect(autocommit=True, **PG) as c:
        return str(c.execute(
            "INSERT INTO playbooks "
            "(tenant_id, title, summary, applies_when, content, status, created_at, updated_at) "
            "VALUES (%s::uuid, %s, 'summary', 'applies', 'content', %s, %s, %s) RETURNING id",
            (tenant_id, title, status, created, created),
        ).fetchone()[0])


def proposal_count(tenant_id: str, proposal_type: str) -> int:
    with psycopg.connect(autocommit=True, **PG) as c:
        return c.execute(
            "SELECT count(*) FROM feedback_proposals WHERE tenant_id=%s::uuid AND proposal_type=%s",
            (tenant_id, proposal_type),
        ).fetchone()[0]


def playbook_status(playbook_id: str) -> str:
    with psycopg.connect(autocommit=True, **PG) as c:
        return c.execute("SELECT status FROM playbooks WHERE id=%s::uuid", (playbook_id,)).fetchone()[0]


def append_trace(tc: TraceCapture, tenant_id: str, **fields) -> None:
    rec = {
        "tenant_id": tenant_id,
        "matter_id": fields.pop("matter_id", f"m-{time.time_ns()}"),
        "timestamp": fields.pop("timestamp", datetime.now(timezone.utc).isoformat()),
        "input": fields.pop("input", "misma pregunta recurrente"),
        "output": fields.pop("output", "respuesta aprobada"),
        "model": "test",
        "tokens": 1,
        "latency_ms": 1,
        **fields,
    }
    path = tc._path_for(tenant_id)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(rec, ensure_ascii=False) + "\n")


async def run_checks() -> None:
    original = llm.call_llm
    llm.call_llm = fake_llm
    tenant = make_tenant("GEPA_TEST")
    other = make_tenant("GEPA_TEST_OTHER")
    try:
        with tempfile.TemporaryDirectory() as tmp:
            tc = TraceCapture(Path(tmp) / "traces")
            gepa = GEPALoop(trace_capture=tc)

            check("GEPA expone run_all_tenants", callable(getattr(gepa, "run_all_tenants", None)))

            append_trace(tc, tenant, hitl_outcome="approved", input="misma pregunta recurrente")
            check("detect_new_skill devuelve None con una sola señal",
                  await gepa.detect_new_skill(tenant) is None)

            append_trace(tc, tenant, hitl_outcome="approved", input="misma pregunta recurrente")
            draft = await gepa.detect_new_skill(tenant)
            check("detect_new_skill crea draft con 2 aprobaciones", draft is not None and draft["status"] == "draft")
            check("draft queda en playbooks status=draft", draft is not None and playbook_status(draft["skill_id"]) == "draft")
            check("detect_new_skill crea propuesta new_playbook", proposal_count(tenant, "new_playbook") >= 1)

            good = insert_playbook(tenant, "Skill bueno")
            bad = insert_playbook(tenant, "Skill malo")
            old = insert_playbook(tenant, "Skill viejo", days_old=90)
            fresh = insert_playbook(tenant, "Skill fresco")
            insert_playbook(other, "Skill otro tenant")

            append_trace(tc, tenant, hitl_outcome="approved", playbook_id=good)
            append_trace(tc, tenant, hitl_outcome="approved", playbook_id=good)
            append_trace(tc, tenant, hitl_outcome="rejected", playbook_id=bad)
            append_trace(tc, tenant, hitl_outcome="edited", playbook_id=bad, draft_original="A", draft_final="B")

            grades = await gepa.grade_all_skills(tenant)
            good_grade = next(g for g in grades if g["skill_id"] == good)
            bad_grade = next(g for g in grades if g["skill_id"] == bad)
            check("grade_all_skills calcula approval_rate", good_grade["approval_rate"] == 1.0)
            check("grade_all_skills calcula edit_rate", bad_grade["edit_rate"] == 0.5)

            # CP-C3 (Riesgo #31): las trazas REALES del grafo traen activated_playbooks
            # (LISTA de ids, no playbook_id singular) — el grading debe contarlas igual.
            duo_a = insert_playbook(tenant, "Skill dúo A")
            duo_b = insert_playbook(tenant, "Skill dúo B")
            append_trace(tc, tenant, hitl_outcome="approved", activated_playbooks=[duo_a, duo_b])
            append_trace(tc, tenant, hitl_outcome="rejected", activated_playbooks=[duo_b])
            grades2 = await gepa.grade_all_skills(tenant)
            ga = next(g for g in grades2 if g["skill_id"] == duo_a)
            gb = next(g for g in grades2 if g["skill_id"] == duo_b)
            check("CP-C3: activated_playbooks (lista) cuenta activaciones para CADA playbook",
                  ga["activations"] == 1 and gb["activations"] == 2)
            check("CP-C3: rates por playbook desde activated_playbooks (A 100%, B 50%)",
                  ga["approval_rate"] == 1.0 and gb["approval_rate"] == 0.5)

            no_change = await gepa.evolve_skill(tenant, good)
            check("evolve_skill no propone si desempeño alto", no_change["proposal_created"] is False)
            evolved = await gepa.evolve_skill(tenant, bad)
            check("evolve_skill propone si desempeño bajo", evolved["proposal_created"] is True)
            check("evolve_skill crea propuesta improve_playbook", proposal_count(tenant, "improve_playbook") >= 1)
            check("evolve_skill no aplica automáticamente", playbook_status(bad) == "active")

            pruned = await gepa.prune_unused_skills(tenant, days=60)
            check("prune_unused_skills archiva skills viejos", old in pruned and playbook_status(old) == "archived")
            check("prune_unused_skills no archiva frescos", playbook_status(fresh) == "active")

            cycle = await gepa.run_evolution_cycle(tenant)
            check("run_evolution_cycle devuelve resumen", {"new_skills_proposed", "skills_evolved", "skills_pruned", "top_skills"}.issubset(cycle.keys()))
            all_out = await gepa.run_all_tenants()
            check("run_all_tenants incluye tenants", tenant in all_out and other in all_out)

            src = (ROOT / "backend" / "mia" / "memory" / "gepa.py").read_text(encoding="utf-8")
            forbidden = ("Colombia", "España", "México", "Argentina", "Perú", "Chile", "Civil", "Penal")
            check("GEPA no hardcodea jurisdicciones ni áreas", not any(word in src for word in forbidden))
    finally:
        llm.call_llm = original
        cleanup(tenant, other)


async def async_main() -> int:
    print("== GEPA Loop procedural ==")
    if not os.getenv("PG_PASSWORD"):
        print("  [FAIL] PG_PASSWORD vacío en .env")
        return 1
    init_playbooks.apply()
    init_feedback.apply()
    await pool.open_pool()
    try:
        await run_checks()
    finally:
        await pool.close_pool()
    passed = sum(1 for _, ok in _results if ok)
    total = len(_results)
    print(f"\nRESULT: {passed}/{total} checks PASS")
    if passed == total:
        print("GEPA OK — aprendizaje procedural verificado.")
        return 0
    print("GEPA FAIL — no avanzar con la siguiente tarea.")
    return 1


def main() -> int:
    return asyncio.run(async_main())


if __name__ == "__main__":
    raise SystemExit(main())
