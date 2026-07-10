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
from psycopg.types.json import Json

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

import init_dream_prescriptions  # noqa: E402
import init_dreams  # noqa: E402
import init_feedback  # noqa: E402
import init_playbooks  # noqa: E402
import init_turn_usage  # noqa: E402
from mia import config  # noqa: E402
from mia.agent import llm  # noqa: E402
from mia.cron import build_scheduler  # noqa: E402
from mia.db import pool  # noqa: E402
from mia.memory import prescriptions as rx  # noqa: E402
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


# ── Helpers CP-V2 · auto-diagnóstico prescriptivo ────────────────────────────
def set_value_rate(tenant_id: str, rate: float) -> None:
    with psycopg.connect(autocommit=True, **PG) as c:
        c.execute(
            "INSERT INTO tenant_settings (tenant_id, config) "
            "VALUES (%s::uuid, jsonb_build_object('value', %s::jsonb)) "
            "ON CONFLICT (tenant_id) DO UPDATE SET config = jsonb_set("
            "coalesce(tenant_settings.config, '{}'::jsonb), '{value}', %s::jsonb, true)",
            (tenant_id, Json({"hourly_rate_usd": rate}), Json({"hourly_rate_usd": rate})),
        )


def set_decision(tenant_id: str, prescription_id: str, status: str, days_ago: int) -> None:
    with psycopg.connect(autocommit=True, **PG) as c:
        c.execute(
            "UPDATE dream_prescriptions SET status=%s, "
            "decided_at = now() - (%s * interval '1 day') "
            "WHERE tenant_id=%s::uuid AND prescription_id=%s",
            (status, days_ago, tenant_id, prescription_id),
        )


def stored_prescription_ids(tenant_id: str, statuses: tuple[str, ...] = ("new", "recurring")) -> set[str]:
    with psycopg.connect(autocommit=True, **PG) as c:
        rows = c.execute(
            "SELECT prescription_id FROM dream_prescriptions "
            "WHERE tenant_id=%s::uuid AND status = ANY(%s)",
            (tenant_id, list(statuses)),
        ).fetchall()
    return {r[0] for r in rows}


def surfaced_ids(tenant_id: str) -> set[str]:
    with psycopg.connect(autocommit=True, **PG) as c:
        rows = c.execute(
            "SELECT prescription_id FROM dream_prescriptions "
            "WHERE tenant_id=%s::uuid AND status IN ('new', 'recurring') "
            "AND coalesce((payload->>'surfaced')::boolean, true)",
            (tenant_id,),
        ).fetchall()
    return {r[0] for r in rows}


def rls_forced(table: str) -> bool:
    with psycopg.connect(autocommit=True, **PG) as c:
        row = c.execute(
            "SELECT relrowsecurity, relforcerowsecurity FROM pg_class WHERE relname=%s",
            (table,),
        ).fetchone()
    return bool(row and row[0] and row[1])


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

            # ── CP-V2 · auto-diagnóstico prescriptivo ────────────────────────
            print("\n== CP-V2 · diagnóstico prescriptivo ==")
            engine = rx.PrescriptionEngine(trace_capture=tc)

            # Dreams.run ya corrió con 6 turnos: todos los buckets de señal se
            # saltan (<5 eventos cada uno) salvo el aviso de tarifa de fábrica.
            diag0 = result.get("diagnostics") or {}
            check("Dreams.run trae la sección diagnostics",
                  isinstance(diag0.get("prescriptions"), list))
            check("Con pocos datos solo aparece el aviso de tarifa",
                  {p["id"] for p in diag0["prescriptions"]} == {"valor-sin-configurar"})
            check("El reporte menciona las recomendaciones",
                  "recomendaciones de mejora" in result["report"])

            # Guarda anti-invención: un despacho sin actividad no recibe nada.
            empty_tenant = make_tenant()
            try:
                empty = await rx.PrescriptionEngine(trace_capture=tc).run(empty_tenant)
                check("Guarda anti-invención: sin datos no hay recomendaciones",
                      empty["prescriptions"] == [] and empty["candidates_total"] == 0)
            finally:
                cleanup(empty_tenant)

            # Señal real: retrabajo (6 ediciones del mismo contexto) +
            # conocimiento (6 respuestas sin fuentes del despacho).
            for i in range(3):
                append_trace(tc, tenant, matter_id=f"edited-x{i}", hitl_outcome="edited",
                             input="misma correccion de estilo",
                             draft_original="texto original", draft_final="texto final")
            for i in range(5):
                append_trace(tc, tenant, matter_id=f"gap-{i}", hitl_outcome="approved",
                             retrieved_doc_ids=[], output="respuesta sin fuentes")

            diag1 = await engine.run(tenant)
            ids1 = {p["id"] for p in diag1["prescriptions"]}
            rework = next((p for p in diag1["prescriptions"] if p["category"] == "retrabajo"), None)
            check("Retrabajo detectado con evidencia real (conteos)",
                  rework is not None and any("6 respuestas corregidas" in e for e in rework["evidence"]))
            check("Conocimiento sin fuentes detectado", "conocimiento-sin-fuentes" in ids1)
            check("Ranking: gravedad × dólares × certeza ordena el panel",
                  diag1["prescriptions"][0]["id"] == rework["id"])
            check("El impacto usa la tarifa del despacho (fábrica: 100 USD/h)",
                  abs((rework["dollar_impact"] or 0) - 150.0) < 0.01)

            # IDs estables + memoria de recomendaciones.
            diag2 = await engine.run(tenant)
            ids2 = {p["id"] for p in diag2["prescriptions"]}
            check("IDs estables entre corridas",
                  rework["id"] in ids2 and "conocimiento-sin-fuentes" in ids2)
            rework2 = next(p for p in diag2["prescriptions"] if p["id"] == rework["id"])
            check("La segunda corrida marca el hallazgo como recurrente",
                  rework2["status"] == "recurring" and rework2["age_days"] >= 0)

            # La tarifa del despacho cambia el impacto y apaga el aviso de fábrica;
            # la tarjeta huérfana se PODA de la tabla (el panel queda coherente).
            set_value_rate(tenant, 200.0)
            diag3 = await engine.run(tenant)
            rework3 = next(p for p in diag3["prescriptions"] if p["id"] == rework["id"])
            check("El impacto en dólares sigue la tarifa fijada (200 USD/h)",
                  abs((rework3["dollar_impact"] or 0) - 300.0) < 0.01)
            check("Con tarifa fijada desaparece el aviso de tarifa",
                  "valor-sin-configurar" not in {p["id"] for p in diag3["prescriptions"]})
            check("La señal resuelta se poda de la tabla",
                  "valor-sin-configurar" not in stored_prescription_ids(tenant))

            # Decisión del abogado: lo descartado no se repite…
            set_decision(tenant, rework["id"], "dismissed", days_ago=1)
            diag4 = await engine.run(tenant)
            check("Lo descartado no se vuelve a mostrar",
                  rework["id"] not in {p["id"] for p in diag4["prescriptions"]}
                  and rework["id"] in diag4["suppressed"])
            check("La decisión sobrevive a la poda",
                  rework["id"] in stored_prescription_ids(tenant, ("dismissed",)))

            # …salvo que la señal siga viva pasados 30 días.
            set_decision(tenant, rework["id"], "dismissed", days_ago=31)
            diag5 = await engine.run(tenant)
            resurfaced = next((p for p in diag5["prescriptions"] if p["id"] == rework["id"]), None)
            check("Resurge tras 30 días como recurrente",
                  resurfaced is not None and resurfaced["status"] == "recurring")

            # Funciones puras: diversidad del top y bucket de costo.
            fake = [dict(id=f"a{i}", category="costo", headline="", prescription="",
                         evidence=[], severity=10, certainty=1.0,
                         dollar_impact=100.0 - i, time_impact_mins=None) for i in range(3)]
            fake.append(dict(id="b", category="guias", headline="", prescription="",
                             evidence=[], severity=1, certainty=0.5,
                             dollar_impact=None, time_impact_mins=None))
            top = rx.rank_and_diversify(fake)
            check("Diversidad: máximo 2 por categoría en el top",
                  sum(1 for p in top if p["category"] == "costo") == 2
                  and any(p["id"] == "b" for p in top))

            # Escenario REAL (capa 2, H3/H6): motor 'nube' pagado por token (task
            # main en claude-sonnet) + tareas de apoyo en el económico/suscripción
            # con costo 0 — como de verdad registra turn_usage.
            rows_cost = [
                {"task": "main", "model": "claude-sonnet", "prompt_tokens": 2_000_000,
                 "completion_tokens": 200_000, "cost_usd": 9.0, "calls": 10},
                {"task": "compression", "model": "cli-claude-haiku", "prompt_tokens": 500_000,
                 "completion_tokens": 50_000, "cost_usd": 0.0, "calls": 20},
            ]
            cost_out = rx.bucket_cost(rows_cost)
            check("Costo: reporta el gasto real pagado y apunta a Configuración",
                  len(cost_out) == 1 and abs((cost_out[0]["dollar_impact"] or 0) - 9.0) < 0.01
                  and any("Configuración" in e for e in cost_out[0]["evidence"]))
            check("Costo: suscripción/local (costo 0) no genera hallazgo",
                  rx.bucket_cost([rows_cost[1]]) == [])
            check("Costo: con menos de 5 llamadas pagadas se salta",
                  rx.bucket_cost([{**rows_cost[0], "calls": 3}]) == [])
            check("Retrabajo: con menos de 5 ediciones se salta",
                  rx.bucket_rework([{"hitl_outcome": "edited", "input": "x"}] * 4, 100.0) == [])

            # H1/R1 (capa 2): una decisión del abogado tomada DURANTE la corrida
            # del cron no se pisa — el upsert jamás resetea una fila decidida
            # (sin comparar relojes); solo el resurgimiento explícito lo hace.
            set_decision(tenant, "conocimiento-sin-fuentes", "dismissed", days_ago=0)
            cand = next(p for p in diag5["prescriptions"] if p["id"] == "conocimiento-sin-fuentes")
            await engine._persist(tenant, [dict(cand, surfaced=True)])
            check("Carrera cron×decisión: la decisión del abogado sobrevive al upsert",
                  "conocimiento-sin-fuentes" in stored_prescription_ids(tenant, ("dismissed",)))
            await engine._persist(tenant, [dict(cand, surfaced=True, _resurface=True)])
            check("El resurgimiento explícito sí reabre la tarjeta",
                  "conocimiento-sin-fuentes" in stored_prescription_ids(tenant, ("recurring",)))

            # H2 (capa 2): una tarjeta con señal viva que sale del top por
            # diversidad NO se borra (conserva su edad); el panel solo muestra
            # las surfaceadas.
            fakes = [dict(id=f"costo-fake-{i}", category="costo", headline="h",
                          prescription="p", evidence=["e"], severity=10, certainty=1.0,
                          dollar_impact=1000.0 - i, time_impact_mins=None) for i in range(3)]
            picked_ids = {p["id"] for p in rx.rank_and_diversify(fakes)}
            for p in fakes:
                p["surfaced"] = p["id"] in picked_ids
            await engine._persist(tenant, fakes)
            check("La poda respeta la señal viva fuera del top (edad conservada)",
                  {"costo-fake-0", "costo-fake-1", "costo-fake-2"}
                  <= stored_prescription_ids(tenant))
            check("El panel solo muestra las tarjetas del top (surfaced)",
                  surfaced_ids(tenant) == {"costo-fake-0", "costo-fake-1"})

            check("dream_prescriptions tiene RLS forzado", rls_forced("dream_prescriptions"))
            src_rx = (ROOT / "backend" / "mia" / "memory" / "prescriptions.py").read_text(encoding="utf-8")
            check("Prescriptions no hardcodea jurisdicciones ni áreas",
                  not any(word in src_rx for word in forbidden))
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
    init_turn_usage.apply()
    init_dream_prescriptions.apply()
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
