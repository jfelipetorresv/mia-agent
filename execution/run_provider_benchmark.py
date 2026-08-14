"""Preflight y ejecución gobernada del benchmark ciego Claude–Codex.

Por defecto solo audita y escribe evidencia. ``--execute`` exige un tope USD explícito y
ambos productores legales cableados dentro de MIA; falla antes de abrir la base o llamar un
modelo si uno falta. No acepta menos de diez repeticiones ni casos reales.
"""
from __future__ import annotations

import argparse
import asyncio
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


def _revision() -> str:
    try:
        return subprocess.run(["git", "rev-parse", "HEAD"], cwd=ROOT, check=True,
                              capture_output=True, text=True).stdout.strip()
    except Exception:
        return "unknown"


def _write(path: Path, value: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_suffix(path.suffix + ".tmp")
    temp.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    temp.replace(path)


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
                   smoke: bool = False, max_wall_minutes: float = 120.0) -> dict:
    guard = spend_guard.EvalSpendGuard(run_limit_usd=max_usd, source="cli",
                                       session_id=session_id)
    reports: dict[str, dict] = {}
    original_full = os.environ.get("MIA_EVAL_PERSIST_FULL")
    os.environ["MIA_EVAL_PERSIST_FULL"] = "1"
    deadline = time.monotonic() + max_wall_minutes * 60
    await pool.open_pool()
    try:
        for arm_id in ARM_IDS:
            arm = plan["arms"][arm_id]
            policy = arm["producer_policy"]
            tenant_id = _make_tenant(arm_id, policy)
            matter_ids: list[str] = []
            case_runs: dict[str, dict] = {}
            try:
                selected_cases = benchmark_cases()[:1] if smoke else benchmark_cases()
                for _, case in selected_cases:
                    if time.monotonic() >= deadline:
                        guard.stop_reason = "tope_de_tiempo_del_benchmark"
                        break
                    repetitions = next(row["repetitions"] for row in plan["cases"]
                                       if row["case_id"] == case.id)
                    repetitions = 1 if smoke else repetitions
                    results = await harness.run_case_n(
                        tenant_id, case, repetitions, guard=guard,
                        eval_provider=arm.get("eval_provider"),
                    )
                    matter_ids.extend(str(r["matter_id"]) for r in results if r.get("matter_id"))
                    telemetry = await collect_call_telemetry(tenant_id, matter_ids, policy or "")
                    attach_call_telemetry(results, telemetry)
                    case_runs[case.id] = {"requested": repetitions, "results": results}
                    if len(results) != repetitions:
                        break
                reports[arm_id] = {"schema_version": plan["schema_version"],
                                   "plan_sha256": plan["plan_sha256"], "arm_id": arm_id,
                                   "policy": policy, "eval_provider": arm.get("eval_provider"),
                                   "mode": "smoke-1x2" if smoke else "full",
                                   "case_runs": case_runs,
                                   "spend": guard.snapshot()}
                _write(output / f"arm-{arm_id}.json", reports[arm_id])
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

    if not smoke and set(reports) == set(ARM_IDS):
        packet, key = build_blind_review_packet(reports, plan, seed=secrets.token_bytes(32))
        _write(output / "blind-review-packet.json", packet)
        _write(output / "blind-review-key.private.json", key)
        _write(output / "blind-review-template.json", review_template(packet))
    status = certification_status(reports, plan)
    status["spend"] = guard.snapshot()
    status["mode"] = "smoke-1x2" if smoke else "full"
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
    parser.add_argument("--session-id", default=None)
    parser.add_argument("--output-dir", default=None)
    args = parser.parse_args()

    run_id = f"provider-benchmark-{datetime.now():%Y%m%d-%H%M%S}"
    output = Path(args.output_dir) if args.output_dir else ROOT / "validation" / run_id
    try:
        plan = build_plan(repetitions=args.repeat, revision=_revision())
    except BenchmarkContractError as exc:
        parser.error(str(exc))
    _write(output / "benchmark-plan.json", plan)
    preflight = {"schema_version": plan["schema_version"], "plan_sha256": plan["plan_sha256"],
                 "execution_ready": plan["execution_ready"], "blockers": plan["blockers"],
                 "required_turns": plan["required_turns"],
                 "model_calls_executed": 0,
                 "codex_isolated_adapter":
                     plan["arms"]["codex"]["isolated_eval_preflight"],
                 "decision": "ready" if plan["execution_ready"] else "blocked"}
    _write(output / "preflight.json", preflight)

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
    session_id = args.session_id or spend_guard.default_session_id("provider-benchmark")
    status = asyncio.run(_execute(
        plan, output, max_usd=args.max_usd, session_id=session_id,
        smoke=args.smoke, max_wall_minutes=args.max_wall_minutes,
    ))
    if args.smoke:
        print("Smoke 1×2 terminado; no declara ganador ni certifica la matriz completa.")
        return 0 if set((status.get("validations") or {})) == set(ARM_IDS) else EXIT_INCOMPLETE
    print("Ejecución completa." if status["certifiable"] else "Ejecución incompleta; ver status.json.")
    return 0 if status["certifiable"] else EXIT_INCOMPLETE


if __name__ == "__main__":
    raise SystemExit(main())
