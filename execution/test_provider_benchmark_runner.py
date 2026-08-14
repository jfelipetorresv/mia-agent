"""Pruebas offline del runner reanudable; cero DB, red o llamadas de modelo."""
from __future__ import annotations

import copy
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from execution import run_provider_benchmark as runner  # noqa: E402
from mia.eval.provider_benchmark import BenchmarkContractError  # noqa: E402


checks: list[tuple[str, bool]] = []


def check(label: str, condition: bool) -> None:
    checks.append((label, bool(condition)))
    print(("PASS " if condition else "FAIL ") + label)


def rejects(fn) -> bool:
    try:
        fn()
    except BenchmarkContractError:
        return True
    return False


def fake_plan() -> dict:
    body = {
        "schema_version": "test/v1",
        "revision": "rev-a",
        "arms": {arm: {"producer_policy": arm, "eval_provider": None}
                 for arm in runner.ARM_IDS},
        "cases": [{"case_id": "case-a", "repetitions": 10}],
    }
    return {**body, "plan_sha256": runner._sha256(body)}


def fake_config(plan: dict, *, arms=runner.ARM_IDS, session="session-a") -> dict:
    return runner._execution_config(
        plan, smoke=False, arms=arms, session_id=session,
        max_usd=30.0, max_wall_minutes=180.0,
    )


def fake_report(plan: dict, arm: str, count: int, *, mode="full-comparable",
                config: dict | None = None) -> dict:
    report = {
        "plan_sha256": plan["plan_sha256"],
        "revision": plan["revision"],
        "arm_id": arm,
        "mode": mode,
        "case_runs": {
            "case-a": {"requested": 10, "results": [
                {"matter_id": f"{arm}-{index}"} for index in range(count)
            ]},
        },
    }
    if config:
        report["session_id"] = config["session_id"]
        report["config_sha256"] = config["config_sha256"]
    return report


def main() -> int:
    plan = fake_plan()
    runner._validate_stored_plan(plan, revision="rev-a", repetitions=10)
    check("plan íntegro acepta misma revisión y repeticiones", True)
    check("reanudación rechaza otra revisión", rejects(
        lambda: runner._validate_stored_plan(plan, revision="rev-b", repetitions=10)))
    check("reanudación rechaza otra cantidad de repeticiones", rejects(
        lambda: runner._validate_stored_plan(plan, revision="rev-a", repetitions=11)))
    tampered = copy.deepcopy(plan)
    tampered["cases"][0]["repetitions"] = 99
    check("reanudación rechaza plan alterado aunque conserve hash viejo", rejects(
        lambda: runner._validate_stored_plan(tampered, revision="rev-a", repetitions=99)))

    with tempfile.TemporaryDirectory() as tmp:
        output = Path(tmp)
        config = fake_config(plan)
        state = runner._prepare_state(output, config, resume=False)
        check("inicio guarda estado atómico y sin temporal residual",
              (output / "run-state.json").is_file()
              and not (output / "run-state.json.tmp").exists())
        resumed = runner._prepare_state(output, config, resume=True)
        check("misma configuración reanuda el mismo estado",
              resumed["started_at"] == state["started_at"])
        changed = fake_config(plan, session="session-b")
        check("sesión distinta no se mezcla", rejects(
            lambda: runner._prepare_state(output, changed, resume=True)))
        check("estado existente exige --resume explícito", rejects(
            lambda: runner._prepare_state(output, config, resume=False)))

    with tempfile.TemporaryDirectory() as tmp:
        output = Path(tmp)
        (output / "arm-claude.json").write_text("{}", encoding="utf-8")
        check("artefactos huérfanos no se adoptan como sesión nueva", rejects(
            lambda: runner._prepare_state(output, fake_config(plan), resume=False)))

    reports = {"claude": fake_report(plan, "claude", 1)}
    state = {
        "completed_units": [],
        "inflight": "claude/case-a/0",
    }
    runner._reconcile_state(state, reports)
    check("crash tras escribir resultado se reconcilia sin repetir llamada",
          state["inflight"] is None
          and state["completed_units"] == ["claude/case-a/0"])

    ambiguous = {"completed_units": [], "inflight": "claude/case-a/1"}
    check("llamada en vuelo sin resultado durable se bloquea, nunca se repite", rejects(
        lambda: runner._reconcile_state(ambiguous, reports)))
    missing = {"completed_units": ["claude/case-a/9"], "inflight": None}
    check("estado que afirma resultado inexistente se rechaza", rejects(
        lambda: runner._reconcile_state(missing, reports)))

    cumulative = runner._accumulate(
        {"wall_seconds": 100.0, "spent_usd": 2.0, "calls": 3,
         "total_tokens": 400, "llm_seconds": 20.0},
        {"run_spent_usd": 1.25, "calls": 2, "total_tokens": 300,
         "llm_seconds": 4.5},
        12.25,
    )
    check("gasto, tiempo, llamadas y tokens se acumulan entre procesos",
          cumulative == {"wall_seconds": 112.25, "spent_usd": 3.25,
                         "calls": 5, "total_tokens": 700, "llm_seconds": 24.5})
    remaining = runner._remaining_limits(
        cumulative, max_usd=4.0, max_wall_minutes=2.0)
    check("topes de gasto y reloj descuentan lo consumido antes del resume",
          remaining == (0.75, 7.75))
    exhausted = runner._remaining_limits(
        {"spent_usd": 4.5, "wall_seconds": 999},
        max_usd=4.0, max_wall_minutes=2.0)
    check("un tope acumulado agotado queda en cero, nunca se reinicia",
          exhausted == (0.0, 0.0))

    check("un brazo solo está rotulado diagnóstico no comparable",
          runner._mode(True, ("claude",)) == "smoke-single-arm-non-comparable")
    diagnostic = runner._govern_status(
        {"certifiable": True, "winner": "claude"},
        mode=runner._mode(True, ("claude",)), arms=("claude",), complete=True)
    check("un solo brazo nunca certifica ni conserva ganador",
          diagnostic["certifiable"] is False
          and diagnostic["winner"] is None
          and diagnostic["diagnostic_only"] is True)
    check("matriz completa exige ambos brazos y todas las repeticiones",
          not runner._matrix_complete(reports, plan, runner.ARM_IDS, smoke=False))
    partial_status = runner.certification_status(reports, plan)
    check("certification_status acepta evidencia parcial y nunca la certifica",
          partial_status["certifiable"] is False
          and partial_status["winner"] is None)
    full_reports = {arm: fake_report(plan, arm, 10) for arm in runner.ARM_IDS}
    check("solo la matriz exacta se considera ejecución completa",
          runner._matrix_complete(full_reports, plan, runner.ARM_IDS, smoke=False))

    with tempfile.TemporaryDirectory() as tmp:
        output = Path(tmp)
        config = fake_config(plan, arms=("claude",))
        runner._write(output / "arm-claude.json", fake_report(
            plan, "claude", 1, config=config))
        loaded = runner._load_reports(
            output, plan, ("claude",), "full-comparable", config)
        check("reanudación carga el brazo compatible", set(loaded) == {"claude"})
        runner._write(output / "arm-codex.json", fake_report(plan, "codex", 1))
        check("un brazo ajeno a la configuración diagnóstica se rechaza", rejects(
            lambda: runner._load_reports(
                output, plan, ("claude",), "full-comparable")))

    with tempfile.TemporaryDirectory() as tmp:
        output = Path(tmp)
        config = fake_config(plan, arms=("claude",))
        mixed = fake_report(plan, "claude", 1, config=config)
        mixed["session_id"] = "otra-session"
        runner._write(output / "arm-claude.json", mixed)
        check("reporte de otra sesión se rechaza aunque comparta plan", rejects(
            lambda: runner._load_reports(
                output, plan, ("claude",), "full-comparable", config)))

    passed = sum(ok for _, ok in checks)
    print(f"\nRESULT: {passed}/{len(checks)} PASS")
    return 0 if passed == len(checks) else 1


if __name__ == "__main__":
    raise SystemExit(main())
