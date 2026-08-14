"""Preflight y ejecución gobernada del benchmark ciego Claude–Codex.

Por defecto solo audita y escribe evidencia. ``--execute`` exige un tope USD explícito y
ambos productores legales cableados dentro de MIA; falla antes de abrir la base o llamar un
modelo si uno falta. No acepta menos de diez repeticiones ni casos reales.
"""
from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import os
import secrets
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path

import psycopg
from dotenv import load_dotenv

if sys.platform == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

ROOT = Path(__file__).resolve().parents[1]
load_dotenv(ROOT / ".env")
sys.path.insert(0, str(ROOT / "backend"))

from mia.agents.state import thread_id_for  # noqa: E402
from mia.db import pool  # noqa: E402
from mia.eval import harness, spend_guard  # noqa: E402
from mia.eval.provider_benchmark import (  # noqa: E402
    ARM_IDS,
    BenchmarkContractError,
    attach_call_telemetry,
    benchmark_cases,
    build_blind_review_packet,
    build_plan,
    certification_status,
    collect_call_telemetry,
    review_template,
)

PG = dict(host=os.getenv("PG_HOST", "127.0.0.1"), port=os.getenv("PG_PORT", "5432"),
          dbname=os.getenv("PG_DB", "mia"), user="postgres",
          password=os.getenv("PG_PASSWORD", ""))
EXIT_BLOCKED = 3
EXIT_INCOMPLETE = 2
RUN_STATE_SCHEMA = "mia-provider-benchmark-runner/v2"


def _revision() -> str:
    try:
        return subprocess.run(["git", "rev-parse", "HEAD"], cwd=ROOT, check=True,
                              capture_output=True, text=True).stdout.strip()
    except Exception:
        return "unknown"


def _write(path: Path, value: dict) -> None:
    """Escritura atómica y durable; nunca deja JSON truncado como checkpoint."""
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_suffix(path.suffix + ".tmp")
    with temp.open("w", encoding="utf-8", newline="\n") as stream:
        stream.write(json.dumps(value, ensure_ascii=False, indent=2) + "\n")
        stream.flush()
        os.fsync(stream.fileno())
    os.replace(temp, path)


def _read(path: Path) -> dict:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise BenchmarkContractError(f"Checkpoint ilegible: {path}: {exc}") from exc
    if not isinstance(value, dict):
        raise BenchmarkContractError(f"Checkpoint inválido (no es objeto JSON): {path}")
    return value


def _sha256(value: dict) -> str:
    raw = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"),
                     default=str).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()


def _validate_stored_plan(plan: dict, *, revision: str, repetitions: int) -> None:
    body = {key: value for key, value in plan.items() if key != "plan_sha256"}
    if plan.get("plan_sha256") != _sha256(body):
        raise BenchmarkContractError("El plan guardado fue modificado o está corrupto.")
    if plan.get("revision") != revision:
        raise BenchmarkContractError(
            f"La revisión no coincide: plan={plan.get('revision')!r}, actual={revision!r}.")
    planned = {int(row.get("repetitions", -1)) for row in plan.get("cases", [])}
    if planned != {int(repetitions)}:
        raise BenchmarkContractError(
            f"Las repeticiones solicitadas ({repetitions}) no coinciden con el plan {sorted(planned)}.")


def _mode(smoke: bool, arms: tuple[str, ...]) -> str:
    if not smoke:
        return "full-comparable"
    return ("smoke-single-arm-non-comparable" if len(arms) == 1
            else "smoke-1x2-non-comparable")


def _execution_config(plan: dict, *, smoke: bool, arms: tuple[str, ...],
                      session_id: str, max_usd: float,
                      max_wall_minutes: float) -> dict:
    value = {
        "plan_sha256": plan["plan_sha256"],
        "revision": plan["revision"],
        "mode": _mode(smoke, arms),
        "arms": list(arms),
        "session_id": session_id,
        "max_usd": float(max_usd),
        "max_wall_minutes": float(max_wall_minutes),
    }
    value["config_sha256"] = _sha256(value)
    return value


def _prepare_state(output: Path, config: dict, *, resume: bool) -> dict:
    path = output / "run-state.json"
    if path.exists():
        if not resume:
            raise BenchmarkContractError(
                "Ya existe una ejecución en este directorio; use --resume para continuarla.")
        state = _read(path)
        if state.get("schema_version") != RUN_STATE_SCHEMA:
            raise BenchmarkContractError("El checkpoint usa un esquema no reanudable.")
        if state.get("config") != config:
            raise BenchmarkContractError(
                "La sesión/configuración no coincide; se prohíbe mezclar ejecuciones.")
        return state
    if resume:
        raise BenchmarkContractError("--resume exige un run-state.json existente.")
    stale = list(output.glob("arm-*.json"))
    stale.extend(path for path in (
        output / "status.json", output / "blind-review-packet.json",
        output / "blind-review-key.private.json", output / "blind-review-template.json",
    ) if path.exists())
    if stale:
        raise BenchmarkContractError(
            "El destino contiene artefactos sin estado compatible; no se mezclan sesiones: "
            + ", ".join(path.name for path in stale))
    state = {
        "schema_version": RUN_STATE_SCHEMA,
        "config": config,
        "started_at": datetime.now().astimezone().isoformat(),
        "updated_at": datetime.now().astimezone().isoformat(),
        "completed_units": [],
        "inflight": None,
        "cumulative": {
            "wall_seconds": 0.0,
            "spent_usd": 0.0,
            "calls": 0,
            "total_tokens": 0,
            "llm_seconds": 0.0,
        },
        "complete": False,
        "comparable": config["mode"] == "full-comparable",
    }
    _write(path, state)
    return state


def _load_reports(output: Path, plan: dict, arms: tuple[str, ...], mode: str,
                  config: dict | None = None) -> dict[str, dict]:
    reports: dict[str, dict] = {}
    unexpected = [path for path in output.glob("arm-*.json")
                  if path.stem.removeprefix("arm-") not in arms]
    if unexpected:
        raise BenchmarkContractError(
            "Hay brazos ajenos a esta configuración: "
            + ", ".join(path.name for path in unexpected))
    for arm_id in arms:
        path = output / f"arm-{arm_id}.json"
        if not path.exists():
            continue
        report = _read(path)
        identity_ok = (
            report.get("plan_sha256") == plan["plan_sha256"]
            and report.get("revision") == plan["revision"]
            and report.get("arm_id") == arm_id
            and report.get("mode") == mode
        )
        if config is not None:
            identity_ok = (identity_ok
                           and report.get("session_id") == config["session_id"]
                           and report.get("config_sha256") == config["config_sha256"])
        if not identity_ok:
            raise BenchmarkContractError(
                f"El checkpoint del brazo {arm_id} pertenece a otro plan/configuración.")
        reports[arm_id] = report
    return reports


def _unit_key(arm_id: str, case_id: str, repetition: int) -> str:
    return f"{arm_id}/{case_id}/{repetition}"


def _accumulate(base: dict, snapshot: dict, elapsed_seconds: float) -> dict:
    """Combina invocaciones sin confundir el saldo persistente con gasto nuevo."""
    return {
        "wall_seconds": round(float(base.get("wall_seconds", 0.0))
                              + max(0.0, elapsed_seconds), 3),
        "spent_usd": round(float(base.get("spent_usd", 0.0))
                           + float(snapshot.get("run_spent_usd") or 0.0), 6),
        "calls": int(base.get("calls", 0)) + int(snapshot.get("calls") or 0),
        "total_tokens": int(base.get("total_tokens", 0))
                        + int(snapshot.get("total_tokens") or 0),
        "llm_seconds": round(float(base.get("llm_seconds", 0.0))
                             + float(snapshot.get("llm_seconds") or 0.0), 3),
    }


def _remaining_limits(cumulative: dict, *, max_usd: float,
                      max_wall_minutes: float) -> tuple[float, float]:
    return (
        max(0.0, float(max_usd) - float(cumulative.get("spent_usd", 0.0))),
        max(0.0, float(max_wall_minutes) * 60
            - float(cumulative.get("wall_seconds", 0.0))),
    )


def _govern_status(status: dict, *, mode: str, arms: tuple[str, ...],
                   complete: bool) -> dict:
    status["mode"] = mode
    status["execution_complete"] = bool(complete)
    status["comparable"] = mode == "full-comparable" and arms == ARM_IDS
    status["partial"] = not complete
    if not status["comparable"] or not complete:
        status["certifiable"] = False
        status["winner"] = None
        status["diagnostic_only"] = True
    return status


def _matrix_complete(reports: dict[str, dict], plan: dict,
                     arms: tuple[str, ...], *, smoke: bool) -> bool:
    cases = plan.get("cases", [])[:1] if smoke else plan.get("cases", [])
    for arm_id in arms:
        case_runs = (reports.get(arm_id) or {}).get("case_runs", {})
        for row in cases:
            wanted = 1 if smoke else int(row["repetitions"])
            if len((case_runs.get(row["case_id"]) or {}).get("results", [])) != wanted:
                return False
    return True


def _reconcile_state(state: dict, reports: dict[str, dict]) -> None:
    """Reconcilia solo evidencia ya escrita; una llamada ambigua nunca se repite."""
    observed: set[str] = set()
    for arm_id, report in reports.items():
        for case_id, run in (report.get("case_runs") or {}).items():
            for repetition, _ in enumerate(run.get("results") or []):
                observed.add(_unit_key(arm_id, case_id, repetition))
    declared = set(state.get("completed_units") or [])
    missing = declared - observed
    if missing:
        raise BenchmarkContractError(
            "El estado declara repeticiones sin evidencia; no se reanuda: "
            + ", ".join(sorted(missing)))
    inflight = state.get("inflight")
    if inflight and inflight not in observed:
        raise BenchmarkContractError(
            f"La llamada {inflight} quedó en vuelo sin resultado durable. "
            "No se repetirá automáticamente; requiere conciliación manual.")
    state["completed_units"] = sorted(observed)
    state["inflight"] = None


def _make_tenant(arm_id: str, policy: str | None) -> str:
    with psycopg.connect(autocommit=True, **PG) as conn:
        tenant_id = str(conn.execute(
            "INSERT INTO tenants(name) VALUES(%s) RETURNING id",
            (f"[eval] benchmark proveedor {arm_id}",)).fetchone()[0])
        if policy:
            conn.execute(
                "INSERT INTO tenant_settings(tenant_id, config) VALUES "
                "(%s::uuid, jsonb_build_object('model_policy', %s::text)) "
                "ON CONFLICT (tenant_id) DO UPDATE SET config = "
                "COALESCE(tenant_settings.config, '{}'::jsonb) || EXCLUDED.config",
                (tenant_id, policy))
        return tenant_id


def _drop_tenant(tenant_id: str, matter_ids: list[str]) -> None:
    with psycopg.connect(autocommit=True, **PG) as conn:
        for matter_id in matter_ids:
            thread_id = thread_id_for(tenant_id, matter_id)
            for table in ("checkpoint_writes", "checkpoint_blobs", "checkpoints"):
                try:
                    conn.execute(f"DELETE FROM {table} WHERE thread_id=%s", (thread_id,))
                except Exception:
                    pass
        conn.execute("DELETE FROM tenants WHERE id=%s::uuid", (tenant_id,))


async def _execute(plan: dict, output: Path, *, max_usd: float, session_id: str,
                   smoke: bool = False, max_wall_minutes: float = 120.0,
                   arms: tuple[str, ...] = ARM_IDS, resume: bool = False) -> dict:
    mode = _mode(smoke, arms)
    config = _execution_config(
        plan, smoke=smoke, arms=arms, session_id=session_id,
        max_usd=max_usd, max_wall_minutes=max_wall_minutes,
    )
    state = _prepare_state(output, config, resume=resume)
    reports = _load_reports(output, plan, arms, mode, config)
    _reconcile_state(state, reports)
    _write(output / "run-state.json", state)

    cumulative_base = dict(state["cumulative"])
    remaining_usd, remaining_wall_seconds = _remaining_limits(
        cumulative_base, max_usd=max_usd, max_wall_minutes=max_wall_minutes)
    guard = spend_guard.EvalSpendGuard(run_limit_usd=remaining_usd, source="cli",
                                       session_id=session_id)
    if remaining_usd <= 0:
        guard.stop_reason = "tope_de_gasto_acumulado_del_benchmark"
    original_full = os.environ.get("MIA_EVAL_PERSIST_FULL")
    os.environ["MIA_EVAL_PERSIST_FULL"] = "1"
    invocation_started = time.monotonic()
    deadline = time.monotonic() + remaining_wall_seconds
    if remaining_wall_seconds <= 0:
        guard.stop_reason = "tope_de_tiempo_acumulado_del_benchmark"

    def checkpoint(*, complete: bool = False) -> None:
        snap = guard.snapshot()
        state["updated_at"] = datetime.now().astimezone().isoformat()
        state["complete"] = bool(complete)
        state["cumulative"] = _accumulate(
            cumulative_base, snap, time.monotonic() - invocation_started)
        _write(output / "run-state.json", state)

    await pool.open_pool()
    try:
        selected_cases = benchmark_cases()[:1] if smoke else benchmark_cases()
        for arm_id in arms:
            if guard.stop_reason:
                break
            arm = plan["arms"][arm_id]
            policy = arm["producer_policy"]
            tenant_id = _make_tenant(arm_id, policy)
            matter_ids: list[str] = []
            report = reports.setdefault(arm_id, {
                "schema_version": plan["schema_version"],
                "plan_sha256": plan["plan_sha256"],
                "revision": plan["revision"],
                "arm_id": arm_id,
                "policy": policy,
                "eval_provider": arm.get("eval_provider"),
                "mode": mode,
                "session_id": session_id,
                "config_sha256": config["config_sha256"],
                "case_runs": {},
                "spend": {},
            })
            try:
                for _, case in selected_cases:
                    if time.monotonic() >= deadline:
                        guard.stop_reason = "tope_de_tiempo_del_benchmark"
                        break
                    repetitions = next(row["repetitions"] for row in plan["cases"]
                                       if row["case_id"] == case.id)
                    repetitions = 1 if smoke else repetitions
                    case_run = report["case_runs"].setdefault(
                        case.id, {"requested": repetitions, "results": []})
                    if int(case_run.get("requested", -1)) != repetitions:
                        raise BenchmarkContractError(
                            f"Checkpoint incompatible para {arm_id}/{case.id}.")
                    existing = case_run["results"]
                    if len(existing) > repetitions:
                        raise BenchmarkContractError(
                            f"Checkpoint tiene repeticiones extra para {arm_id}/{case.id}.")
                    for repetition in range(len(existing), repetitions):
                        if time.monotonic() >= deadline:
                            guard.stop_reason = "tope_de_tiempo_del_benchmark"
                            break
                        key = _unit_key(arm_id, case.id, repetition)
                        if key in state["completed_units"]:
                            raise BenchmarkContractError(
                                f"Estado inconsistente: {key} ya completo pero no está en el reporte.")
                        state["inflight"] = key
                        checkpoint()
                        results = await harness.run_case_n(
                            tenant_id, case, 1, guard=guard,
                            eval_provider=arm.get("eval_provider"),
                        )
                        if len(results) != 1:
                            # La llamada puede haber tenido efectos/costo inciertos. El
                            # marcador queda en vuelo y bloquea una repetición automática.
                            checkpoint()
                            break
                        result = results[0]
                        current_mids = ([str(result["matter_id"])]
                                        if result.get("matter_id") else [])
                        matter_ids.extend(current_mids)
                        telemetry = await collect_call_telemetry(
                            tenant_id, current_mids, policy or "")
                        attach_call_telemetry(results, telemetry)
                        existing.append(result)
                        report["spend"] = guard.snapshot()
                        _write(output / f"arm-{arm_id}.json", report)
                        state["completed_units"].append(key)
                        state["completed_units"] = sorted(set(state["completed_units"]))
                        state["inflight"] = None
                        checkpoint()
                    if len(existing) != repetitions:
                        break
                report["spend"] = guard.snapshot()
                _write(output / f"arm-{arm_id}.json", report)
            finally:
                _drop_tenant(tenant_id, matter_ids)
            if guard.stop_reason:
                break
    finally:
        await pool.close_pool()
        if original_full is None:
            os.environ.pop("MIA_EVAL_PERSIST_FULL", None)
        else:
            os.environ["MIA_EVAL_PERSIST_FULL"] = original_full
        checkpoint(complete=False)

    counts_complete = _matrix_complete(reports, plan, arms, smoke=smoke)
    status = certification_status(reports, plan)
    selected_validations = status.get("validations") or {}
    complete = counts_complete and (smoke or all(
        (selected_validations.get(arm_id) or {}).get("complete") for arm_id in arms))
    checkpoint(complete=complete)
    if not smoke and arms == ARM_IDS and complete:
        packet_path = output / "blind-review-packet.json"
        key_path = output / "blind-review-key.private.json"
        template_path = output / "blind-review-template.json"
        existing = [path.exists() for path in (packet_path, key_path, template_path)]
        if any(existing) and not all(existing):
            raise BenchmarkContractError(
                "Los artefactos ciegos están incompletos; no se sobrescriben ni mezclan.")
        if not any(existing):
            packet, key = build_blind_review_packet(
                reports, plan, seed=secrets.token_bytes(32))
            _write(packet_path, packet)
            _write(key_path, key)
            _write(template_path, review_template(packet))
    status["spend_current_invocation"] = guard.snapshot()
    status["cumulative"] = state["cumulative"]
    _govern_status(status, mode=mode, arms=arms, complete=complete)
    _write(output / "status.json", status)
    return status


def main() -> int:
    parser = argparse.ArgumentParser(description="Benchmark ciego Claude–Codex de MIA")
    parser.add_argument("--execute", action="store_true",
                        help="ejecuta ambos brazos; sin esta bandera solo hace preflight")
    parser.add_argument("--repeat", type=int, default=10)
    parser.add_argument("--max-usd", type=float, default=None,
                        help="tope explícito para toda la matriz; obligatorio con --execute")
    parser.add_argument("--max-wall-minutes", type=float, default=None,
                        help="tope de reloj; obligatorio con --execute")
    parser.add_argument("--smoke", action="store_true",
                        help="ejecuta solo 1 caso × 1 repetición × 2 brazos")
    parser.add_argument("--arm", choices=ARM_IDS, default=None,
                        help="diagnóstico de un brazo; solo válido junto con --smoke")
    parser.add_argument("--resume", action="store_true",
                        help="reanuda exactamente el plan/sesión/configuración guardados")
    parser.add_argument("--session-id", default=None)
    parser.add_argument("--output-dir", default=None)
    args = parser.parse_args()
    if args.arm and not args.smoke:
        parser.error("--arm solo se permite con --smoke; un brazo nunca es comparable")

    run_id = f"provider-benchmark-{datetime.now():%Y%m%d-%H%M%S}"
    output = Path(args.output_dir) if args.output_dir else ROOT / "validation" / run_id
    revision = _revision()
    plan_path = output / "benchmark-plan.json"
    try:
        if plan_path.exists():
            if not args.resume:
                raise BenchmarkContractError(
                    "El directorio ya contiene un plan; use --resume o elija otro destino.")
            plan = _read(plan_path)
            _validate_stored_plan(plan, revision=revision, repetitions=args.repeat)
        else:
            if args.resume:
                raise BenchmarkContractError("--resume exige benchmark-plan.json existente.")
            plan = build_plan(repetitions=args.repeat, revision=revision)
            _write(plan_path, plan)
    except BenchmarkContractError as exc:
        parser.error(str(exc))
    preflight = {"schema_version": plan["schema_version"], "plan_sha256": plan["plan_sha256"],
                 "execution_ready": plan["execution_ready"], "blockers": plan["blockers"],
                 "required_turns": plan["required_turns"],
                 "model_calls_executed": 0,
                 "codex_isolated_adapter":
                     plan["arms"]["codex"]["isolated_eval_preflight"],
                 "decision": "ready" if plan["execution_ready"] else "blocked"}
    preflight_path = output / "preflight.json"
    if args.resume:
        if not preflight_path.exists():
            parser.error("la ejecución reanudable perdió preflight.json; no se reconstruye")
        stored_preflight = _read(preflight_path)
        if stored_preflight.get("plan_sha256") != plan["plan_sha256"]:
            parser.error("preflight.json pertenece a otro plan; no se mezcla ni sobrescribe")
    else:
        _write(preflight_path, preflight)

    print(f"Plan: {output / 'benchmark-plan.json'}")
    print(f"Turnos requeridos: {plan['required_turns']} (datos sintéticos)")
    if not plan["execution_ready"]:
        print("BLOQUEADO antes de gastar: " + ", ".join(plan["blockers"]))
        return EXIT_BLOCKED
    if not args.execute:
        print("Preflight verde; no se llamó ningún modelo.")
        return 0
    if args.max_usd is None or args.max_usd <= 0:
        parser.error("--execute exige --max-usd con un valor mayor que cero")
    if args.max_wall_minutes is None or args.max_wall_minutes <= 0:
        parser.error("--execute exige --max-wall-minutes con un valor mayor que cero")
    arms = (args.arm,) if args.arm else ARM_IDS
    if args.resume:
        try:
            prior_state = _read(output / "run-state.json")
            prior_session = str(prior_state.get("config", {}).get("session_id") or "")
            if not prior_session:
                raise BenchmarkContractError("El checkpoint no identifica su sesión de gasto.")
            if args.session_id and args.session_id != prior_session:
                raise BenchmarkContractError(
                    "--session-id no coincide con la sesión guardada; no se mezclan saldos.")
            session_id = prior_session
        except BenchmarkContractError as exc:
            parser.error(str(exc))
    else:
        session_id = args.session_id or spend_guard.default_session_id("provider-benchmark")
    status = asyncio.run(_execute(
        plan, output, max_usd=args.max_usd, session_id=session_id,
        smoke=args.smoke, max_wall_minutes=args.max_wall_minutes,
        arms=arms, resume=args.resume,
    ))
    if args.smoke:
        label = "un solo brazo" if args.arm else "1×2"
        print(f"Smoke {label} terminado; es diagnóstico no comparable y nunca certifica.")
        return 0 if status.get("execution_complete") else EXIT_INCOMPLETE
    print("Ejecución completa." if status["certifiable"] else "Ejecución incompleta; ver status.json.")
    return 0 if status["certifiable"] else EXIT_INCOMPLETE


if __name__ == "__main__":
    raise SystemExit(main())
