"""
Mia · test_eval_harness.py — gate de CP-E4 (banco de pruebas de calidad · Ola 5).

Cubre:
  OFFLINE (puro, sin DB):
    · score_turn: disciplina de citas (cita sin marca → sin_respaldo + flag; cita con
      [VERIFICAR] → marcada, ok), cierre del diagnóstico, borrador vacío/minúsculo, flags;
    · compare_reports: detecta REGRESIÓN (suben citas sin respaldo, se pierde el cierre,
      deja de producir borrador, borrador encogido) y MEJORA (los inversos); veredicto
      agregado fail-safe (una regresión manda);
    · casos de oro: bien formados y TODOS sintéticos (candado);
    · build_report + persist_report (a un tempdir).

  DB (RLS · grafo real con LLM/embeddings stubbeados):
    · read_eval_policy: fail-closed (default False; True solo con el flag);
    · candado: un caso NO sintético sin autorización → EvalConsentError; con el flag → corre;
    · end-to-end: run_case siembra el asunto, corre el grafo completo headless hasta el HITL,
      puntúa el borrador real (con una cita sin marca → sin_respaldo>0) y devuelve el informe.

Salida: exit 0 = PASS · exit 1 = FAIL.

    .venv\\Scripts\\python.exe execution\\test_eval_harness.py
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

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

from mia import config, embeddings                        # noqa: E402
from mia.agent import llm                                 # noqa: E402
from mia.agent.prompt_builder import (                    # noqa: E402
    DIAGNOSIS_CLOSING_FOOTER,
    DIAGNOSIS_CLOSING_HEADER,
)
from mia.agents.state import thread_id_for                # noqa: E402
from mia.db import pool                                   # noqa: E402
from mia.eval import compare_reports, score_turn          # noqa: E402
from mia.eval import cases as cases_mod                   # noqa: E402
from mia.eval import harness                              # noqa: E402
from mia.eval import scoring                               # noqa: E402
from mia.eval.cases import GoldenCase, GoldenCaseDoc      # noqa: E402

# R3-MEDIO (Codex, ronda 3): temporales del harness por el helper común fail-before-create
# (nunca dentro del repo, limpieza garantizada). Antes: TemporaryDirectory()/mkdtemp sueltos.
sys.path.insert(0, str(ROOT / "execution"))
from _tmp_desechable import tmpdir_desechable              # noqa: E402

_results: list[tuple[str, bool]] = []


def check(name: str, ok: bool) -> None:
    _results.append((name, bool(ok)))
    print(("  [OK]   " if ok else "  [FAIL] ") + name)


PG = dict(
    host=os.getenv("PG_HOST", "127.0.0.1"), port=os.getenv("PG_PORT", "5432"),
    dbname=os.getenv("PG_DB", "mia"), user="postgres", password=os.getenv("PG_PASSWORD", ""),
)

_CLOSING = (f"{DIAGNOSIS_CLOSING_HEADER}\nProblema jurídico: la caducidad de la acción.\n"
            f"Normas y fuentes: Ley 1437 de 2011 [VERIFICAR]\n"
            f"Riesgo y recomendación: proponer la excepción.\n{DIAGNOSIS_CLOSING_FOOTER}")


# ── mocks (sin red) — el grafo real con LLM/embeddings stubbeados ─────────────
def _fake_embed(texts):
    return [[0.0] * config.EMBED_DIM for _ in texts]


def _fake_call_llm(messages, *, task=None, model=None, **kw):
    sysmsg = messages[0]["content"] if messages and isinstance(messages[0], dict) else ""
    if "BORRADOR" in sysmsg or "Redacta el borrador" in sysmsg:
        # Borrador con una cita SIN marca → el verificador la anota (sin_respaldo=1), y bajo
        # jurisdicción desconocida la OMITE. F2 · informe por oración: se añade además una
        # afirmación asertiva SIN cita (> piso de longitud, termina en '.') para ejercitar el
        # residuo `oraciones.sin_respaldo_afirmativa` end-to-end (fake desobediente, regla 46).
        content = (("BORRADOR: contestación de la demanda. Con fundamento en la Ley 1437 de 2011 "
                    "y en reiterada jurisprudencia, se propone la excepción de caducidad. " * 6)
                   + "El término de caducidad de la acción se cuenta a partir del día siguiente "
                     "a la ocurrencia del hecho dañoso, y la carga de la prueba corresponde "
                     "íntegramente a quien alega el derecho que reclama dentro del proceso.")
    elif "CRUCE" in sysmsg or "diagnóstico" in sysmsg.lower():
        content = "DIAGNÓSTICO: el eje es la caducidad.\n\n" + _CLOSING
    else:
        content = "Análisis del especialista para el turno de prueba."
    return SimpleNamespace(
        choices=[SimpleNamespace(message=SimpleNamespace(content=content))],
        usage=SimpleNamespace(prompt_tokens=12, completion_tokens=20, total_tokens=32),
    )


# ── OFFLINE ────────────────────────────────────────────────────────────────────
def offline_checks() -> None:
    print("\n-- offline: scorer, comparador, casos, persistencia --")

    # score_turn · disciplina de citas.
    draft_unmarked = "Con base en la Ley 1437 de 2011 se solicita rechazar la demanda por completo."
    s1 = score_turn(draft_unmarked, "DIAGNÓSTICO x\n" + _CLOSING, {"usage": {"total": 100}})
    check("score: cita sin marca → citas_sin_respaldo ≥ 1 y flag",
          s1["citas_sin_respaldo"] >= 1 and "citas_sin_respaldo" in s1["flags"])
    check("score: cierre del diagnóstico detectado", s1["has_diagnosis_closing"] is True)

    draft_marked = "Con base en la Ley 1437 de 2011 [VERIFICAR] se pide rechazar la demanda entera."
    s2 = score_turn(draft_marked, "d\n" + _CLOSING, {})
    check("score: cita con [VERIFICAR] → NO cuenta como sin respaldo",
          s2["citas_sin_respaldo"] == 0 and "citas_sin_respaldo" not in s2["flags"])

    s3 = score_turn("", "sin cierre", {})
    check("score: borrador vacío → flag sin_borrador y no ok",
          "sin_borrador" in s3["flags"] and s3["ok"] is False)
    s4 = score_turn("muy corto", "x", {})
    check("score: borrador minúsculo → flag",
          "borrador_minusculo" in s4["flags"])
    check("score: sin cierre del diagnóstico → flag",
          "sin_cierre_diagnostico" in s3["flags"])

    # compare_reports · regresión / mejora.
    def rep(cid, **sc):
        base = dict(citas_sin_respaldo=0, has_diagnosis_closing=True, reached_draft=True,
                    draft_chars=1000, total_tokens=100)
        base.update(sc)
        return {"cases": [{"case_id": cid, "score": base}]}

    reg = compare_reports(rep("c1"), rep("c1", citas_sin_respaldo=3))
    check("compare: suben citas sin respaldo → regresión",
          reg["overall"] == "regresion" and reg["n_regresiones"] == 1)
    reg2 = compare_reports(rep("c1"), rep("c1", has_diagnosis_closing=False))
    check("compare: se pierde el cierre → regresión", reg2["overall"] == "regresion")
    reg3 = compare_reports(rep("c1"), rep("c1", reached_draft=False, draft_chars=0))
    check("compare: deja de producir borrador → regresión", reg3["overall"] == "regresion")
    reg4 = compare_reports(rep("c1", draft_chars=1000), rep("c1", draft_chars=200))
    check("compare: borrador encogido a <mitad → regresión", reg4["overall"] == "regresion")
    imp = compare_reports(rep("c1", citas_sin_respaldo=3), rep("c1", citas_sin_respaldo=0))
    check("compare: bajan citas sin respaldo → mejora", imp["overall"] == "mejora")
    same = compare_reports(rep("c1"), rep("c1"))
    check("compare: idéntico → sin_cambio", same["overall"] == "sin_cambio")
    # fail-safe: una regresión manda aunque haya una mejora en otro caso.
    mix_b = {"cases": [rep("c1")["cases"][0], rep("c2", citas_sin_respaldo=3)["cases"][0]]}
    mix_a = {"cases": [rep("c1", citas_sin_respaldo=3)["cases"][0], rep("c2", citas_sin_respaldo=0)["cases"][0]]}
    mix = compare_reports(mix_b, mix_a)
    check("compare: regresión + mejora → veredicto REGRESIÓN (fail-safe)",
          mix["overall"] == "regresion")

    # casos de oro: bien formados y TODOS sintéticos.
    check("casos: el set canónico es no vacío y todos SINTÉTICOS",
          len(cases_mod.GOLDEN_CASES) >= 1
          and all(c.synthetic for c in cases_mod.GOLDEN_CASES))
    check("casos: cada uno trae id, mensaje y documentos",
          all(c.id and c.message and c.documents for c in cases_mod.GOLDEN_CASES))

    # build_report + persist_report a un tempdir.
    report = harness.build_report("eval_test", [
        {"case_id": "a", "title": "A", "matter_id": "m", "reached_draft": True,
         "score": score_turn("Ley 1437 de 2011 texto largo " * 10, "d\n" + _CLOSING, {})},
    ])
    check("build_report: resumen con conteos",
          report["summary"]["n_casos"] == 1 and report["summary"]["n_llegaron_a_borrador"] == 1)
    td = tmpdir_desechable("mia-harness-report-")
    run_dir = harness.persist_report(report, base_dir=str(td))
    check("persist_report: escribe cases.jsonl + summary.json",
          (run_dir / "cases.jsonl").exists() and (run_dir / "summary.json").exists())

    # Barrera de cableado (retrospectiva 2026-07-22-007): el camino `--case --repeat N`
    # de run_eval.py estuvo SIN persistir hasta ac5ce98 — 30 corridas del baseline
    # vivieron solo en un log que murió con el proceso. Este check impide que el
    # descableado vuelva en silencio: _run_repeat debe llamar a persist_report y el
    # main del repeat debe respetar --run-id.
    run_eval_src = (Path(__file__).resolve().parent / "run_eval.py").read_text(
        encoding="utf-8")
    repeat_body = run_eval_src.split("async def _run_repeat", 1)[1].split(
        "\nasync def ", 1)[0]
    check("run_eval._run_repeat PERSISTE los crudos (persist_report cableado)",
          "persist_report(" in repeat_body)
    check("run_eval: el camino --repeat respeta --run-id (no genera uno propio siempre)",
          "_run_repeat(run_id" in run_eval_src)


# ── Frente E: casos de RIESGO + señales nuevas (todo OFFLINE, sin DB) ──────────
def frente_e_offline_checks() -> None:
    print("\n-- offline: Frente E — fuga de jurisdicción, procedencia, tasa, agéntico --")

    # RISK_CASES: registrados, sintéticos, y CADA uno con el fixture que su riesgo exige.
    check("risk cases: el set de riesgo es no vacío y todos SINTÉTICOS",
          len(cases_mod.RISK_CASES) >= 3 and all(c.synthetic for c in cases_mod.RISK_CASES))
    check("risk cases: cada uno trae id y mensaje",
          all(c.id and c.message for c in cases_mod.RISK_CASES))
    check("risk cases: no se coló ninguno en el set canónico (load_golden_cases sigue en 3, "
          "sin romper a execution/test_gold_cases_influence_eval.py que asume n==4)",
          len(cases_mod.load_golden_cases()) == 3
          and not (set(c.id for c in cases_mod.RISK_CASES)
                   & set(c.id for c in cases_mod.load_golden_cases())))

    fuga = next(c for c in cases_mod.RISK_CASES if c.id == "fuga-jurisdiccion-contrato-sin-pais")
    check("risk cases: el caso de fuga de jurisdicción tiene expediente VACÍO a propósito",
          fuga.documents == ())
    procedencia = next(c for c in cases_mod.RISK_CASES if c.id == "procedencia-despacho-vacio")
    check("risk cases: el caso de procedencia tiene expediente VACÍO a propósito",
          procedencia.documents == ())
    citas_abrev = next(c for c in cases_mod.RISK_CASES
                       if c.id == "disciplina-citas-formas-abreviadas")
    check("risk cases: el caso de disciplina de citas sella una forma ABREVIADA ('arts.')",
          any("arts." in ch for d in citas_abrev.documents for ch in d.chunks))

    # jurisdiction_leak_signal: reusa el escáner del guardián (agents.verification), no
    # duplica vocabulario de país — MUTACIÓN: mismo texto, se le añade una cita concreta.
    razona_por_institucion = (
        "El régimen general de validez de un contrato exige capacidad de las partes, "
        "consentimiento libre de vicios, objeto y causa lícitos. Sin conocer bajo qué "
        "ordenamiento trabaja el despacho no es posible precisar más.")
    limpio = scoring.jurisdiction_leak_signal(razona_por_institucion)
    check("jurisdiction_leak: razona por institución sin citar articulado → SIN fuga",
          limpio["leak"] is False and limpio["citas_detectadas"] == 0)
    con_fuga = razona_por_institucion + " Con fundamento en el artículo 90 de la Ley 1437 de 2011."
    mutado = scoring.jurisdiction_leak_signal(con_fuga)
    check("jurisdiction_leak: MUTADO — se añade una cita concreta → SÍ detecta la fuga "
          "(mutación roja sobre el mismo texto limpio)",
          mutado["leak"] is True and mutado["citas_detectadas"] >= 1
          and "Ley 1437 de 2011" in mutado["detalle"][0])

    # jurisdiction_leak_rate: pura, agrega N resultados de `run_case`-shape. MUTACIÓN:
    # de 0/3 con fuga a 2/3 con fuga (la tasa, no un booleano, es el punto del gate).
    limpios = [{"matter_id": f"m{i}", "draft_preview": razona_por_institucion,
               "diagnosis_preview": ""} for i in range(3)]
    tasa0 = harness.jurisdiction_leak_rate(limpios)
    check("jurisdiction_leak_rate: 3 corridas limpias → tasa 0.0",
          tasa0["n"] == 3 and tasa0["n_con_fuga"] == 0 and tasa0["tasa"] == 0.0)
    mixtos = [{"matter_id": "m0", "draft_preview": con_fuga, "diagnosis_preview": ""},
             {"matter_id": "m1", "draft_preview": con_fuga, "diagnosis_preview": ""},
             {"matter_id": "m2", "draft_preview": razona_por_institucion, "diagnosis_preview": ""}]
    tasa1 = harness.jurisdiction_leak_rate(mixtos)
    check("jurisdiction_leak_rate: MUTADO — 2 de 3 corridas con fuga → tasa 0.6667 "
          "(reporta TASA, no un booleano de una pasada)",
          tasa1["n_con_fuga"] == 2 and abs(tasa1["tasa"] - round(2 / 3, 4)) < 1e-9
          and len(tasa1["detalle"]) == 3)
    # la fuga también puede venir por el DIAGNÓSTICO (no solo el borrador) — por eso
    # `run_case` ahora guarda `diagnosis_preview` y `jurisdiction_leak_rate` lo incluye.
    solo_diagnostico = [{"matter_id": "m0", "draft_preview": razona_por_institucion,
                         "diagnosis_preview": con_fuga}]
    tasa2 = harness.jurisdiction_leak_rate(solo_diagnostico)
    check("jurisdiction_leak_rate: una fuga que solo aparece en el DIAGNÓSTICO también cuenta",
          tasa2["n_con_fuga"] == 1)

    # provenance_signal: atribuir al despacho SIN material sellado es sospechoso; CON
    # material, la misma frase deja de serlo (MUTACIÓN sobre `documents_retrieved`).
    atribuye = "Conforme a la experiencia del despacho en casos similares, el contrato es válido."
    p_sin_material = scoring.provenance_signal(atribuye, "", 0)
    check("provenance: atribución al despacho SIN material sellado → indebida",
          p_sin_material["atribucion_indebida"] is True
          and p_sin_material["sin_material_sellado"] is True)
    p_con_material = scoring.provenance_signal(atribuye, "", 3)
    check("provenance: MUTADO — MISMA frase pero CON material sellado → ya NO es indebida",
          p_con_material["atribucion_indebida"] is False)
    sin_atribucion = "El contrato es válido conforme a lo que consta en [doc 1]."
    p_neutro = scoring.provenance_signal(sin_atribucion, "", 0)
    check("provenance: sin frases de procedencia → no marca nada aunque no haya material",
          p_neutro["atribucion_indebida"] is False and p_neutro["frases_detectadas"] == [])

    # compare_agentic_reports: pura, compara dos reportes por case_id. MUTACIÓN: quitar la
    # traza `agentic_reading` del caso "on" (motor sin herramientas) cambia el veredicto de
    # "corrió" a "no corrió", sin inventar un motivo de parada que no ocurrió.
    off_report = {"cases": [{"case_id": "c1", "score": {"total_tokens": 500}}]}
    on_report_corrio = {"cases": [{"case_id": "c1", "score": {"total_tokens": 300},
                                   "agentic_reading": {"stop": "suficiente", "expansions": 1}}]}
    cmp1 = harness.compare_agentic_reports(off_report, on_report_corrio)
    check("compare_agentic: el motivo de parada y el delta de tokens viajan por caso",
          cmp1["cases"][0]["corrio_agentic"] is True
          and cmp1["cases"][0]["motivo_parada"] == "suficiente"
          and cmp1["cases"][0]["delta_tokens"] == -200
          and cmp1["n_corrio_agentic"] == 1)
    on_report_no_corrio = {"cases": [{"case_id": "c1", "score": {"total_tokens": 500}}]}
    cmp2 = harness.compare_agentic_reports(off_report, on_report_no_corrio)
    check("compare_agentic: MUTADO — sin traza (motor sin herramientas) → corrio_agentic "
          "False y motivo_parada None, NO se inventa un motivo",
          cmp2["cases"][0]["corrio_agentic"] is False
          and cmp2["cases"][0]["motivo_parada"] is None
          and cmp2["n_corrio_agentic"] == 0)


# ── DB ──────────────────────────────────────────────────────────────────────────
def _make_tenant() -> str:
    with psycopg.connect(autocommit=True, **PG) as c:
        return str(c.execute(
            "INSERT INTO tenants(name) VALUES('[eval] test cpe4') RETURNING id").fetchone()[0])


def _set_eval_flag(tenant_id: str, value: bool) -> None:
    with psycopg.connect(autocommit=True, **PG) as c:
        c.execute(
            "INSERT INTO tenant_settings (tenant_id, config) "
            "VALUES (%s::uuid, jsonb_build_object('eval', jsonb_build_object('allow_eval_real_data', %s::bool))) "
            "ON CONFLICT (tenant_id) DO UPDATE SET config = "
            "  jsonb_set(COALESCE(tenant_settings.config,'{}'::jsonb), '{eval}', "
            "  jsonb_build_object('allow_eval_real_data', %s::bool), true)",
            (tenant_id, value, value))


def _drop_tenant(tenant_id: str, matter_ids: list[str]) -> None:
    with psycopg.connect(autocommit=True, **PG) as c:
        for mid in matter_ids:
            tid = thread_id_for(tenant_id, mid)
            for t in ("checkpoint_writes", "checkpoint_blobs", "checkpoints"):
                try:
                    c.execute(f"DELETE FROM {t} WHERE thread_id=%s", (tid,))
                except Exception:
                    pass
        c.execute("DELETE FROM tenants WHERE id=%s", (tenant_id,))


async def budget_eval_isolation_checks() -> None:
    """S2 — el gasto del BANCO no contamina el presupuesto MENSUAL del despacho.

    El defecto reproducido: en la ronda anterior se excluyó el scope de eval de la RESERVA
    (`agent/llm.py`), pero NO del CÁLCULO. Como el uso del banco SÍ se persiste en `turn_usage`
    con `source='eval'`, las dos sumas de `policy/budget.py` (el baseline de `_ensure_month` y
    el respaldo de `month_to_date_cost`) seguían contándolo: una tanda de pruebas podía agotar
    el sobre del mes y BLOQUEAR un turno real de un abogado.

    Se comprueban las dos direcciones, que es lo que hace válida la prueba:
      (a) una fila source='eval' NO cuenta al mes;
      (b) una fila de PRODUCCIÓN cuenta EXACTAMENTE igual que antes del cambio (mismo número,
          al céntimo), y sigue reservando y liquidando contra el sobre mensual.
    """
    print("\n-- db: S2 — el gasto del banco no contamina el sobre mensual del despacho --")
    from mia.policy import budget as policy_budget  # noqa: E402

    await pool.open_pool()
    tenant = _make_tenant()
    prod_usd, eval_usd = 0.1100, 7.7700
    try:
        with psycopg.connect(autocommit=True, **PG) as c:
            for source, cost in (("api", prod_usd), ("eval", eval_usd)):
                c.execute(
                    "INSERT INTO turn_usage (tenant_id, model, task, source, prompt_tokens, "
                    "completion_tokens, total_tokens, cost_usd) "
                    "VALUES (%s::uuid,'claude-sonnet','main',%s,10,10,20,%s)",
                    (tenant, source, cost))

        # (a) + (b) sobre el RESPALDO (`month_to_date_cost` sin fila en ai_budget_months).
        # MUTACIÓN: quitar `AND {_NOT_EVAL}` de esa consulta → sale 7.88 y cae este check.
        mtd = await policy_budget.month_to_date_cost(tenant)
        check(f"S2: el gasto del mes cuenta SOLO producción (USD {mtd:.4f} == "
              f"{prod_usd:.4f}) y NO la fila source='eval' (USD {eval_usd:.4f})",
              abs(mtd - prod_usd) < 1e-6)

        # Y sobre el BASELINE de `_ensure_month`, que es el camino real de producción: la
        # primera reserva del mes copia el gasto ya hecho a `ai_budget_months`.
        # MUTACIÓN: quitar `AND {_NOT_EVAL}` del INSERT de `_ensure_month` → el baseline nace
        # en 7.88 y cae este check.
        hold = policy_budget.reserve_call_sync(tenant, 0.02, model="claude-sonnet", task="main")
        check("S2 · producción INTACTA: un turno normal sigue reservando saldo mensual "
              "(reserve_call_sync devolvió un hold)", bool(hold))
        with psycopg.connect(autocommit=True, **PG) as c:
            base = float(c.execute(
                "SELECT baseline_usd FROM ai_budget_months WHERE tenant_id=%s::uuid",
                (tenant,)).fetchone()[0])
        check(f"S2: el baseline del mes también excluye el eval (USD {base:.4f} == "
              f"{prod_usd:.4f})", abs(base - prod_usd) < 1e-6)

        # Liquidación: el gasto de producción se suma al sobre EXACTAMENTE por su coste real.
        policy_budget.finish_call_sync(tenant, hold, 0.0300)
        st = await policy_budget.budget_status(tenant)
        check(f"S2 · producción INTACTA: tras liquidar, el mes suma producción + coste real "
              f"(USD {st['spent_this_month_usd']:.2f} == {prod_usd + 0.03:.2f}) y la reserva "
              "quedó devuelta",
              abs(st["spent_this_month_usd"] - round(prod_usd + 0.03, 2)) < 1e-6
              and st["reserved_usd"] == 0.0)
    finally:
        await pool.close_pool()
        _drop_tenant(tenant, [])


async def db_checks() -> None:
    print("\n-- db: política fail-closed, candado, end-to-end por el grafo --")
    await pool.open_pool()
    tenant = _make_tenant()
    matter_ids: list[str] = []
    try:
        # read_eval_policy fail-closed.
        pol0 = await harness.read_eval_policy(tenant)
        check("política: sin flag → allow_real_data False (fail-closed)",
              pol0["allow_real_data"] is False)
        _set_eval_flag(tenant, True)
        pol1 = await harness.read_eval_policy(tenant)
        check("política: con el flag → allow_real_data True", pol1["allow_real_data"] is True)
        _set_eval_flag(tenant, False)

        # Candado: caso NO sintético sin autorización → EvalConsentError.
        real_case = GoldenCase(id="real-x", title="Real", message="analiza",
                               documents=(GoldenCaseDoc("d.txt", ("hecho",)),), synthetic=False)
        blocked = False
        try:
            await harness.run_case(tenant, real_case, tenant_allow_real=False)
        except harness.EvalConsentError:
            blocked = True
        check("candado: caso NO sintético sin autorización → EvalConsentError", blocked)

        # End-to-end: caso sintético por el grafo real (LLM/embeddings stubbeados).
        syn_case = GoldenCase(
            id="e2e-caducidad", title="E2E caducidad",
            message="Analiza la caducidad y prepara la defensa con las normas aplicables.",
            documents=(GoldenCaseDoc("demanda.txt", (
                "El daño se consolidó el 3 de marzo de 2019 y la demanda se presentó el "
                "10 de septiembre de 2021.",)),),
            profile={"despacho": "Defensa de entidades."})
        res = await harness.run_case(tenant, syn_case, tenant_allow_real=False)
        matter_ids.append(res["matter_id"])
        check("e2e: el turno llegó a borrador", res["reached_draft"] is True)
        # M1 (hallazgo capa 2): intake DEBE recuperar el documento sembrado del caso —
        # los chunks se siembran con embedding, así que RAG los ve. 0 = corrida a ciegas.
        check("e2e: intake recuperó el expediente del caso (RAG, no a ciegas)",
              res["documents_retrieved"] >= 1)
        # F2 (endurecimiento): este tenant no configuró jurisdicción → la cita sin
        # respaldo del fake ya NO llega al borrador marcada — se OMITE antes de emitirse.
        # El check no queda ciego: exige que el informe REGISTRE la omisión (hubo cita
        # que omitir), no solo que el score salga limpio.
        check("e2e: la cita sin respaldo del fake fue OMITIDA del borrador (jurisdicción "
              "desconocida) y el informe lo registra",
              res["verification"].get("omitidas", 0) >= 1
              and res["score"]["citas_sin_respaldo"] == 0)
        # F2 · informe POR ORACIÓN e2e (rama genérica — este tenant no tiene jurisdicción): la
        # cita omitida cae en una oración `con_omision` y la afirmación asertiva sin cita del
        # fake cae en el residuo `sin_respaldo_afirmativa`. Señal POSITIVA no ciega (regla 46).
        o_e2e = res["verification"].get("oraciones") or {}
        check("e2e por oración (rama genérica): el informe trae 'oraciones' con con_omision≥1 "
              "y sin_respaldo_afirmativa≥1 (fake desobediente end-to-end)",
              o_e2e.get("con_omision", 0) >= 1 and o_e2e.get("sin_respaldo_afirmativa", 0) >= 1)
        # MUTACIÓN: el MISMO borrador del fake, sin el modo por oración, NO produce el bloque
        # 'oraciones' — es sentence_report lo que lo activa (si se descablea, este check cae).
        fake_draft = _fake_call_llm(
            [{"content": "Redacta el borrador"}]).choices[0].message.content
        _, rep_off = harness.verification.annotate_draft(fake_draft, omit_unbacked=True)
        _, rep_on = harness.verification.annotate_draft(
            fake_draft, omit_unbacked=True, sentence_report=True)
        check("e2e MUTADO: el mismo borrador sin el modo por oración NO trae 'oraciones'; con él sí",
              "oraciones" not in rep_off and "oraciones" in rep_on)
        check("e2e: el informe de verificación viaja en el resultado",
              isinstance(res["verification"], dict) and "citas" in res["verification"])
        check("e2e: el resultado trae puntaje con flags",
              "flags" in res["score"] and isinstance(res["score"]["flags"], list))

        # Frente E — end-to-end: run_case ahora expone diagnosis_preview y provenance
        # (antes se calculaban y se perdían); se verifican sobre el MISMO turno de arriba.
        check("e2e: el resultado trae diagnosis_preview (antes se perdía por completo)",
              bool(res.get("diagnosis_preview")))
        check("e2e: provenance viaja en el resultado y ve que SÍ hubo material sellado",
              isinstance(res.get("provenance"), dict)
              and res["provenance"]["sin_material_sellado"] is False)
        check("e2e agentic_reading: con la bandera apagada (default de esta suite, nunca se "
              "tocó), el resultado NO trae la traza — mismo turno de siempre, sin el bucle",
              "agentic_reading" not in res)

        # run_case_n + jurisdiction_leak_rate contra el GRAFO real (LLM/embeddings
        # stubbeados, el mismo doble que usa el resto de esta suite): demuestra que el
        # MECANISMO de repetición y de tasa funciona de punta a punta sobre un caso de
        # RIESGO real (expediente VACÍO). La intermitencia REAL solo se observa en vivo
        # contra un modelo de verdad (fuera de alcance aquí — ver notas_honestas).
        fuga_case = next(c for c in cases_mod.RISK_CASES
                         if c.id == "fuga-jurisdiccion-contrato-sin-pais")
        # A-MAY2: `run_case_n` reconstruye un guardián por DEFECTO si no se le pasa uno y no
        # encuentra uno activo — y ese default apunta al LIBRO DE SALDOS REAL (sesión
        # 'inapp-<fecha>'). Aunque aquí hay un guardián activo cuya propagación por ContextVar
        # bastaría, se pasa guard= EXPLÍCITO con un ledger DESECHABLE para cerrar la fuga EN
        # ORIGEN, sin depender de que el contexto viaje intacto a través de cada asyncio.run.
        from mia.eval import spend_guard as _sg  # noqa: E402
        guard_n = _sg.EvalSpendGuard(
            session_id="test-eval-harness-run_case_n",
            ledger_path=tmpdir_desechable("mia-harness-ledger-n-") / "ledger.json")
        n_results = await harness.run_case_n(tenant, fuga_case, 3, tenant_allow_real=False,
                                             guard=guard_n)
        matter_ids.extend(r["matter_id"] for r in n_results if r.get("matter_id"))
        check("e2e run_case_n: corre el caso 3 veces, con matter_id nuevo cada vez",
              len(n_results) == 3 and len({r["matter_id"] for r in n_results}) == 3)
        check("e2e run_case_n: el expediente VACÍO no recupera documentos en ninguna corrida",
              all(r["documents_retrieved"] == 0 for r in n_results))
        rate = harness.jurisdiction_leak_rate(n_results)
        # F2 (endurecimiento): el fake cita 'Ley 1437 de 2011' en el cierre del diagnóstico
        # SIEMPRE, pero bajo jurisdicción desconocida el diagnóstico pasa por el guardián y
        # la cita se OMITE antes de emitirse → la fuga EMITIDA debe ser 0 en las 3. El check
        # no queda ciego: exige además que cada corrida REGISTRE la omisión en el informe
        # del diagnóstico (la cita existió y fue interceptada — no es que el fake dejara de
        # citar). Sigue midiendo el MECANISMO, no la intermitencia en vivo.
        check("e2e jurisdiction_leak_rate: la fuga del fake fue interceptada en las 3 "
              "corridas (0 emitidas) y cada informe del diagnóstico registra la omisión",
              rate["n"] == 3 and rate["n_con_fuga"] == 0 and rate["tasa"] == 0.0
              and all((r.get("verification_diagnosis") or {}).get("omitidas", 0) >= 1
                      for r in n_results))

        # Procedencia con despacho vacío: confirma que `sin_material_sellado` refleja el
        # turno REAL (0 documentos recuperados). El fake LLM de esta suite no reproduce
        # frases de procedencia, así que `atribucion_indebida` no se ejercita aquí de punta
        # a punta — eso ya lo cubre `provenance_signal` en OFFLINE con su mutación.
        procedencia_case = next(c for c in cases_mod.RISK_CASES
                                if c.id == "procedencia-despacho-vacio")
        res_proc = await harness.run_case(tenant, procedencia_case, tenant_allow_real=False)
        matter_ids.append(res_proc["matter_id"])
        check("e2e procedencia: despacho vacío → 0 documentos recuperados",
              res_proc["documents_retrieved"] == 0)
        check("e2e procedencia: provenance ve que este turno no selló material",
              res_proc["provenance"]["sin_material_sellado"] is True)

        # ── S5: el juez sustantivo ARBITRARIO se rechaza (la marca era burlable) ──
        # La versión anterior aceptaba cualquier juez marcado con `governed_judge` y luego
        # exigía "evidencia": que el tope hubiera visto ≥1 llamada suya. Eso es burlable — un
        # juez puede hacer N peticiones HTTP pagadas y UNA llamada gobernada solo para aprobar
        # el chequeo, y el gasto real pasa sin control. Ahora se rechaza de entrada.
        from mia.eval import spend_guard  # noqa: E402

        juez_case = GoldenCase(
            id="juez-rubrica", title="Juez con rúbrica",
            message="Analiza la caducidad y prepara la defensa.",
            documents=(GoldenCaseDoc("demanda.txt", ("El daño se consolidó en 2019.",)),),
            rubric={"citas_clave": ["Ley 1437 de 2011"], "conclusiones_clave": []})

        corrio = {"n": 0}

        def juez_burlon(draft, diagnosis, rubric):
            """El juez BURLÓN del hallazgo S5: gastaría por su cuenta y luego haría UNA
            llamada gobernada para 'acreditarse'. Aquí no llega a ejecutarse ni una vez."""
            corrio["n"] += 1
            embeddings.embed_texts(["la llamada gobernada de coartada"])
            return {"veredicto": "solido", "explicacion_llana": "ok"}

        # MUTACIÓN: quitar el `raise UngovernedJudge` de `run_case` → cae este check (el juez
        # burlón corre, se acredita con su llamada de coartada y la corrida lo da por bueno).
        bloqueado = None
        try:
            await harness.run_case(tenant, juez_case, tenant_allow_real=False,
                                   substantive_judge=juez_burlon)
        except BaseException as exc:  # noqa: BLE001
            bloqueado = exc
        check("S5: un juez sustantivo arbitrario se RECHAZA antes de correr nada "
              "(UngovernedJudge) — ni siquiera el que traería una llamada de coartada",
              isinstance(bloqueado, spend_guard.UngovernedJudge) and corrio["n"] == 0)
        check("S5: la marca burlable `governed_judge` ya no existe (no se puede acreditar un "
              "juez poniéndole un atributo)",
              not hasattr(spend_guard, "governed_judge")
              and not hasattr(spend_guard, "is_governed_judge"))

        # S1: la parada del juez es un SpendGuardHalt, así que ningún `except Exception` del
        # camino puede tragársela y hacer pasar la corrida bloqueada por completa.
        # MUTACIÓN: hacer que `UngovernedJudge` herede de `Exception` → cae este check.
        tragada = False
        try:
            try:
                await harness.run_case(tenant, juez_case, tenant_allow_real=False,
                                       substantive_judge=juez_burlon)
            except Exception:  # noqa: BLE001 — el patrón de graph.py / run_suite
                tragada = True
        except spend_guard.SpendGuardHalt:
            pass
        check("S1: UngovernedJudge deriva de SpendGuardHalt(BaseException): un `except "
              "Exception` NO se la come", tragada is False)

        # Camino BUENO: con rúbrica y SIN juez, la calificación determinista sigue viva.
        res_rub = await harness.run_case(tenant, juez_case, tenant_allow_real=False)
        matter_ids.append(res_rub["matter_id"])
        check("S5: sin juez, la calificación sustantiva DETERMINISTA (cobertura de rúbrica) "
              "sigue funcionando igual",
              isinstance(res_rub.get("substantive"), dict)
              and "cobertura_citas" in res_rub["substantive"])
    finally:
        await pool.close_pool()
        _drop_tenant(tenant, matter_ids)


def main() -> int:
    embeddings.embed_texts = _fake_embed
    llm.call_llm = _fake_call_llm

    offline_checks()
    frente_e_offline_checks()
    # `harness.run_case` es FAIL-CLOSED (Frente A): sin tope de gasto activo NO corre, porque
    # llamarla de verdad gasta dinero (modelo + embeddings de Voyage). Esta suite la invoca
    # directo, así que abre su propio guardián con un fichero de saldo desechable. Aquí el LLM
    # y los embeddings están stubbeados, así que no se gasta un centavo: el guardián solo
    # satisface el contrato.
    from mia.eval import spend_guard  # noqa: E402
    guardia = spend_guard.EvalSpendGuard(
        session_id="test-eval-harness",
        ledger_path=tmpdir_desechable("mia-harness-ledger-") / "ledger.json")
    with spend_guard.install(), guardia.activate():
        asyncio.run(db_checks())
        asyncio.run(budget_eval_isolation_checks())

    passed = sum(1 for _, ok in _results if ok)
    total = len(_results)
    print(f"\n{passed}/{total} checks PASS")
    if passed == total:
        print("Banco de pruebas OK — CP-E4 verificado.")
        return 0
    print("Banco de pruebas FAIL — HALT: no avanzar (CLAUDE.md §G).")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
