"""Gate offline del contrato Claude–Codex. Cero red, DB o gasto."""
from __future__ import annotations

import copy
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from mia.eval import provider_benchmark as pb  # noqa: E402
from mia.eval import codex_cli_adapter  # noqa: E402
from mia.eval.cases import RISK_CASES  # noqa: E402
from mia.eval.holdout import HOLDOUT_CASES  # noqa: E402
from mia.agent import llm  # noqa: E402

checks: list[tuple[str, bool]] = []


def check(label: str, condition: bool) -> None:
    checks.append((label, bool(condition)))
    print(("PASS" if condition else "FAIL") + " " + label)


def fake_report(plan: dict, arm_id: str) -> dict:
    case_runs = {}
    for case in plan["cases"]:
        results = []
        for repetition in range(case["repetitions"]):
            model = "cli-claude-opus" if arm_id == "claude" else "codex-producer"
            results.append({
                "matter_id": f"{arm_id}-{case['case_id']}-{repetition}",
                "draft_full": f"borrador {case['case_id']} {repetition}",
                "diagnosis_full": f"diagnóstico {case['case_id']} {repetition}",
                "elapsed_ms": 1000 + repetition,
                "usage": {"total_tokens": 100, "cost_usd": 0.01},
                "score": {"citas_sin_respaldo": 0},
                "jurisdiction_leak": {"leak": False},
                "model_fallbacks": [],
                "call_telemetry": [{"task": "legal_draft", "model": model,
                                    "effective_model": model, "effort": "high",
                                    "fallback_used": False}],
                "telemetry_complete": True,
            })
        case_runs[case["case_id"]] = {"requested": case["repetitions"], "results": results}
    return {"arm_id": arm_id, "case_runs": case_runs}


def main() -> int:
    try:
        pb.build_plan(repetitions=9, revision="test")
        check("rechaza menos de diez repeticiones", False)
    except pb.BenchmarkContractError:
        check("rechaza menos de diez repeticiones", True)

    plan = pb.build_plan(repetitions=10, revision="test")
    expected = {c.id for c in RISK_CASES} | {c.id for c in HOLDOUT_CASES}
    check("matriz incluye todos los riesgos y el holdout", {c["case_id"] for c in plan["cases"]} == expected)
    check("cada caso corre diez veces por brazo", plan["required_turns"] == len(expected) * 10 * 2)
    check("plan tiene hash estable de 64 hex", len(plan["plan_sha256"]) == 64)
    check("Claude tiene productor jurídico aislado", plan["arms"]["claude"]["graph_producer_ready"] is True)
    check("Codex eval no se confunde con productor del grafo",
          plan["arms"]["codex"]["graph_producer_ready"] is False
          and "sin_ruta_productor_juridico_en_mia"
          in plan["arms"]["codex"]["production_blockers"])
    check("ruta Codex eval habilita el mismo grafo sin política productiva",
          plan["arms"]["codex"]["benchmark_graph_ready"] is True
          and plan["arms"]["codex"]["eval_provider"] == "codex"
          and plan["execution_ready"] is True)
    normal_chain = llm.resolve_fallback_chain("legal_draft")
    with llm.eval_provider_override("codex"):
        forced = llm.resolve_fallback_chain("legal_draft", model="claude-sonnet")
        forced_compression = llm.resolve_fallback_chain("compression", model="mia-local")
    check("override eval fuerza Codex sin fallback incluso ante model explícito",
          forced == ["cli-codex-eval"] and forced_compression == ["cli-codex-eval"])
    check("override se restaura y no fuga a producción",
          llm.resolve_fallback_chain("legal_draft") == normal_chain)
    try:
        llm._invoke(None, "cli-codex-eval", {"messages": []})
        check("alias eval falla fuera del contexto", False)
    except RuntimeError:
        check("alias eval falla fuera del contexto", True)
    original_graph_call = codex_cli_adapter.call_graph_cli
    codex_cli_adapter.call_graph_cli = lambda *args, **kwargs: object()
    try:
        with llm.eval_provider_override("codex", max_calls=1):
            llm._invoke(None, "cli-codex-eval", {"messages": []})
            try:
                llm._invoke(None, "cli-codex-eval", {"messages": []})
                quota_stopped = False
            except RuntimeError as exc:
                quota_stopped = "tope_de_llamadas" in str(exc)
    finally:
        codex_cli_adapter.call_graph_cli = original_graph_call
    check("override Codex tiene tope duro de llamadas", quota_stopped)

    # Simulamos una futura ruta Codex solo para probar el resto del contrato puro.
    test_plan = copy.deepcopy(plan)
    test_plan["execution_ready"] = True
    test_plan["blockers"] = []
    test_plan["arms"]["codex"]["graph_producer_ready"] = True
    test_plan["arms"]["codex"]["producer_policy"] = "codex_test"
    reports = {arm: fake_report(test_plan, arm) for arm in pb.ARM_IDS}

    original_prefixes = pb.PROVIDER_PREFIXES["codex"]
    pb.PROVIDER_PREFIXES["codex"] = original_prefixes + ("codex-producer",)
    try:
        packet, key = pb.build_blind_review_packet(reports, test_plan, seed=b"fixed-seed")
    finally:
        pb.PROVIDER_PREFIXES["codex"] = original_prefixes
    serialized_packet = str(packet).lower()
    check("paquete ciego no contiene proveedor/modelo/costo",
          "claude" not in serialized_packet and "codex" not in serialized_packet
          and "effective_model" not in serialized_packet and "cost_usd" not in serialized_packet)
    check("llave privada separa el mapeo A/B", len(key["candidate_mapping"]) == plan["required_turns"])
    check("paquete contiene un par por caso y repetición",
          len(packet["pairs"]) == len(expected) * 10)

    template = pb.review_template(packet)
    invalid = pb.validate_human_review(packet, template)
    check("plantilla vacía no se presenta como revisión", invalid["complete"] is False)
    template["reviewer_id"] = "revisor-juridico-independiente"
    for row in template["reviews"]:
        row["preference"] = "tie"
        for side in ("A", "B"):
            row["scores"][side] = {dimension: 4 for dimension in pb.REVIEW_DIMENSIONS}
            row["gates"][side] = {gate: False for gate in packet["rubric"]["binary_gates"]}
    valid = pb.validate_human_review(packet, template)
    check("revisión completa y ciega valida", valid["complete"] is True)

    status = pb.certification_status(reports, test_plan, valid)
    check("estado no inventa ganador antes de desenmascarar", status["winner"] is None)
    check("métricas incluyen tokens, p50, costo y fallback",
          status["metrics"]["claude"]["tokens_total"] > 0
          and status["metrics"]["claude"]["latency_p50_ms"] is not None
          and status["metrics"]["claude"]["cost_total_usd"] > 0
          and status["metrics"]["claude"]["fallback_rate"] == 0.0)

    broken = copy.deepcopy(reports["claude"])
    first_case = next(iter(broken["case_runs"]))
    broken["case_runs"][first_case]["results"].pop()
    check("una sola repetición faltante invalida el brazo",
          pb.validate_arm_report(broken, test_plan, "claude")["complete"] is False)

    passed = sum(ok for _, ok in checks)
    print(f"\nRESULT: {passed}/{len(checks)} PASS")
    return 0 if passed == len(checks) else 1


if __name__ == "__main__":
    raise SystemExit(main())
