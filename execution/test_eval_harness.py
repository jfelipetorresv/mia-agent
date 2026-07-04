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
import tempfile
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
from mia.eval.cases import GoldenCase, GoldenCaseDoc      # noqa: E402

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
        # Borrador con una cita SIN marca → el verificador la anota (sin_respaldo=1).
        content = ("BORRADOR: contestación de la demanda. Con fundamento en la Ley 1437 de 2011 "
                   "y en reiterada jurisprudencia, se propone la excepción de caducidad. " * 6)
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
    with tempfile.TemporaryDirectory() as td:
        run_dir = harness.persist_report(report, base_dir=td)
        check("persist_report: escribe cases.jsonl + summary.json",
              (run_dir / "cases.jsonl").exists() and (run_dir / "summary.json").exists())


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
        check("e2e: el scorer detectó la cita sin respaldo del borrador",
              res["score"]["citas_sin_respaldo"] >= 1)
        check("e2e: el informe de verificación viaja en el resultado",
              isinstance(res["verification"], dict) and "citas" in res["verification"])
        check("e2e: el resultado trae puntaje con flags",
              "flags" in res["score"] and isinstance(res["score"]["flags"], list))
    finally:
        await pool.close_pool()
        _drop_tenant(tenant, matter_ids)


def main() -> int:
    embeddings.embed_texts = _fake_embed
    llm.call_llm = _fake_call_llm

    offline_checks()
    asyncio.run(db_checks())

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
