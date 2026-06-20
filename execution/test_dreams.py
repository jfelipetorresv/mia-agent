"""
Mia · test_dreams.py — gate de Dreams semanal.
"""
from __future__ import annotations

import asyncio
import json
import os
import sys
import tempfile
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

import init_dreams  # noqa: E402
import init_feedback  # noqa: E402
import init_playbooks  # noqa: E402
from mia import config  # noqa: E402
from mia.agent import llm  # noqa: E402
from mia.cron import build_scheduler  # noqa: E402
from mia.db import pool  # noqa: E402
from mia.memory.dreams import Dreams  # noqa: E402
from mia.memory.gepa import GEPALoop  # noqa: E402
from mia.memory.trace_capture import TraceCapture  # noqa: E402
from mia.memory.wiki_manager import WikiManager  # noqa: E402

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
    if "JSON array" in content:
        out = '["Concepto Dream", "Concepto Conectado"]'
    elif "Devuelve JSON" in content:
        out = json.dumps({
            "title": "Procedimiento Dreams",
            "applies_when": "Cuando se repita una consulta aprobada.",
            "content": "Pasos procedurales aprendidos.",
        })
    else:
        out = (
            "## Definicion (segun la practica de este despacho)\nTexto aprendido.\n\n"
            "## Patrones identificados\n- Patron semanal.\n\n"
            "## Casos que lo soportan (referencias anonimas)\n- matter anonimo.\n\n"
            "## Conexiones con otros conceptos\n- Concepto Conectado.\n\n"
            "## Lo que NO funciona (aprendido de rechazos)\n- Pendiente.\n"
        )
    return SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content=out))])


def make_tenant() -> str:
    with psycopg.connect(autocommit=True, **PG) as c:
        return str(c.execute("INSERT INTO tenants(name) VALUES('Dreams Test') RETURNING id").fetchone()[0])


def cleanup(tenant_id: str) -> None:
    with psycopg.connect(autocommit=True, **PG) as c:
        c.execute("DELETE FROM tenants WHERE id=%s::uuid", (tenant_id,))


def insert_old_playbook(tenant_id: str) -> str:
    created = datetime.now(timezone.utc) - timedelta(days=90)
    with psycopg.connect(autocommit=True, **PG) as c:
        return str(c.execute(
            "INSERT INTO playbooks "
            "(tenant_id, title, summary, applies_when, content, status, created_at, updated_at) "
            "VALUES (%s::uuid, 'Dreams viejo', 'summary', 'applies', 'content', 'active', %s, %s) RETURNING id",
            (tenant_id, created, created),
        ).fetchone()[0])


def append_trace(tc: TraceCapture, tenant_id: str, **fields) -> None:
    rec = {
        "tenant_id": tenant_id,
        "matter_id": fields.pop("matter_id", "matter-dream"),
        "timestamp": fields.pop("timestamp", datetime.now(timezone.utc).isoformat()),
        "input": fields.pop("input", "consulta recurrente"),
        "output": fields.pop("output", "respuesta final"),
        "model": "test",
        "tokens": 1,
        "latency_ms": 1,
        **fields,
    }
    path = tc._path_for(tenant_id)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(rec, ensure_ascii=False) + "\n")


def weekly_reports(tenant_id: str) -> int:
    with psycopg.connect(autocommit=True, **PG) as c:
        return c.execute(
            "SELECT count(*) FROM feedback_proposals WHERE tenant_id=%s::uuid AND proposal_type='weekly_report'",
            (tenant_id,),
        ).fetchone()[0]


def tenant_metrics(tenant_id: str):
    with psycopg.connect(autocommit=True, **PG) as c:
        return c.execute(
            "SELECT config #> '{dreams,last_metrics}' FROM tenant_settings WHERE tenant_id=%s::uuid",
            (tenant_id,),
        ).fetchone()[0]


def playbook_status(playbook_id: str) -> str:
    with psycopg.connect(autocommit=True, **PG) as c:
        return c.execute("SELECT status FROM playbooks WHERE id=%s::uuid", (playbook_id,)).fetchone()[0]


async def run_checks() -> None:
    original_llm = llm.call_llm
    original_home = config.MIA_HOME
    llm.call_llm = fake_llm
    tenant = make_tenant()
    try:
        with tempfile.TemporaryDirectory() as tmp:
            config.MIA_HOME = Path(tmp)
            tc = TraceCapture(Path(tmp) / "traces")
            wiki = WikiManager(home=tmp, trace_capture=tc)
            gepa = GEPALoop(trace_capture=tc)
            dreams = Dreams(trace_capture=tc, wiki_manager=wiki, gepa=gepa)
            old_skill = insert_old_playbook(tenant)

            append_trace(tc, tenant, matter_id="approved-1", hitl_outcome="approved", retrieved_doc_ids=[], output="borrador aprobado")
            append_trace(tc, tenant, matter_id="approved-1", hitl_outcome="approved", output="borrador aprobado 2")
            append_trace(tc, tenant, matter_id="rejected-1", hitl_outcome="rejected", output="rechazo de prueba")
            for i in range(3):
                append_trace(
                    tc,
                    tenant,
                    matter_id=f"edited-{i}",
                    hitl_outcome="edited",
                    input="misma correccion de estilo",
                    draft_original="texto original",
                    draft_final="texto final preferido",
                )

            await wiki.init_wiki(tenant)
            stale = wiki.concept_path(tenant, "Concepto antiguo")
            stale.write_text(
                "---\nconcept: Concepto antiguo\nconfidence: 0.8\nlast_updated: 2000-01-01\ncase_count: 3\n---\n# Concepto antiguo\n",
                encoding="utf-8",
            )

            jobs = {j["name"] for j in build_scheduler().list_jobs()}
            check("scheduler registra dreams_weekly", "dreams_weekly" in jobs)
            check("scheduler no registra GEPA separado", "gepa_weekly" not in jobs)

            result = await dreams.run(tenant)
            check("Dreams devuelve las 6 secciones", {"metrics", "wiki", "gepa", "cleanup", "nudges", "report"}.issubset(result.keys()))
            check("Replay calcula approval_rate", abs(result["metrics"]["approval_rate"] - (2 / 6)) < 0.01)
            check("Replay calcula edit_rate", abs(result["metrics"]["edit_rate"] - (3 / 6)) < 0.01)
            check("Replay registra gaps sin RAG", "approved-1" in result["metrics"]["gaps"])
            check("Métricas quedan en tenant_settings", tenant_metrics(tenant)["matters_worked"] >= 5)
            check("Wiki update compila conceptos aprobados", "Concepto Dream" in result["wiki"]["concepts_updated"])
            check("Rechazos quedan registrados en wiki", (await wiki.get_concept(tenant, "Patrones rechazados")) is not None)
            check("GEPA corre desde Dreams", {"new_skills_proposed", "skills_evolved", "skills_pruned", "top_skills"}.issubset(result["gepa"].keys()))
            check("Lint archiva concepto stale/orphan", (Path(tmp) / "wiki" / tenant / "concepts" / "archived" / "concepto_antiguo.md").exists())
            check("Pruning archiva skill viejo", playbook_status(old_skill) == "archived")
            soul = (Path(tmp) / f"soul_{tenant}.md").read_text(encoding="utf-8")
            check("Nudges actualiza SOUL", "Preferencias aprendidas por Mia" in soul)
            check("Weekly report queda como propuesta", weekly_reports(tenant) >= 1)
            check("Reporte semanal es legible", "Dreams Test" in result["report"] and "Tasa de aprobación" in result["report"])

            src = (ROOT / "backend" / "mia" / "memory" / "dreams.py").read_text(encoding="utf-8")
            forbidden = ("Colombia", "España", "México", "Argentina", "Perú", "Chile", "Civil", "Penal")
            check("Dreams no hardcodea jurisdicciones ni áreas", not any(word in src for word in forbidden))
    finally:
        llm.call_llm = original_llm
        config.MIA_HOME = original_home
        cleanup(tenant)


async def async_main() -> int:
    print("== Dreams semanal ==")
    if not os.getenv("PG_PASSWORD"):
        print("  [FAIL] PG_PASSWORD vacío en .env")
        return 1
    init_playbooks.apply()
    init_feedback.apply()
    init_dreams.apply()
    await pool.open_pool()
    try:
        await run_checks()
    finally:
        await pool.close_pool()
    passed = sum(1 for _, ok in _results if ok)
    total = len(_results)
    print(f"\nRESULT: {passed}/{total} checks PASS")
    if passed == total:
        print("Dreams OK — consolidación semanal verificada.")
        return 0
    print("Dreams FAIL — no avanzar con la siguiente tarea.")
    return 1


def main() -> int:
    return asyncio.run(async_main())


if __name__ == "__main__":
    raise SystemExit(main())
