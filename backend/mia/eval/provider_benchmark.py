"""Contrato del benchmark ciego y versionado Claude–Codex de MIA.

Reutiliza los casos, el holdout, las mutaciones y el arnés productivo existentes. Este módulo
no llama modelos por su cuenta: define una matriz justa, audita que cada proveedor pueda ser
el productor jurídico del grafo, captura telemetría y genera artefactos ciegos separados de
la llave. El ejecutor gobernado vive en ``execution/run_provider_benchmark.py``.

Reglas duras:
* diez o más repeticiones por caso y brazo;
* solo datos sintéticos;
* un brazo no está disponible porque exista su CLI: debe tener ruta del mismo grafo; Codex
  solo puede entrar por el override eval aislado y nunca por una política productiva;
* ningún ganador se declara sin ambos brazos completos, telemetría completa y revisión humana;
* el paquete del revisor nunca contiene proveedor, modelo, costo ni la llave A/B.
"""
from __future__ import annotations

import hashlib
import hmac
import json
import shutil
import statistics
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

from ..agent import llm
from .codex_cli_adapter import preflight as codex_cli_preflight
from .cases import RISK_CASES, GoldenCase
from .holdout import (
    HOLDOUT_PURPOSE_MEASURE,
    case_digest as holdout_case_digest,
    load_holdout_cases,
    verify_holdout_integrity,
)

SCHEMA_VERSION = "mia-provider-benchmark/v1"
MIN_REPETITIONS = 10
ARM_IDS = ("claude", "codex")
REVIEW_DIMENSIONS = ("fundamentacion", "calidad_juridica", "completitud", "precision")
PROVIDER_PREFIXES = {
    "claude": ("cli-claude", "claude-"),
    "codex": ("cli-codex", "codex", "openai", "gpt-"),
}


class BenchmarkContractError(ValueError):
    """El artefacto no satisface el contrato mínimo del benchmark."""


class IncompleteEvidence(BenchmarkContractError):
    """La evidencia no permite una conclusión honesta."""


@dataclass(frozen=True)
class ArmCapability:
    arm_id: str
    cli_installed: bool
    producer_policy: str | None
    graph_producer_ready: bool
    benchmark_graph_ready: bool
    eval_provider: str | None
    isolated_eval_ready: bool
    isolated_eval_preflight: dict[str, Any] | None
    legal_routes: dict[str, list[str]]
    blockers: tuple[str, ...]
    production_blockers: tuple[str, ...]


def _canonical(value: Any) -> bytes:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"),
                      default=str).encode("utf-8")


def sha256_json(value: Any) -> str:
    return hashlib.sha256(_canonical(value)).hexdigest()


def _case_digest(case: GoldenCase) -> str:
    payload = {
        "id": case.id,
        "title": case.title,
        "message": case.message,
        "documents": [asdict(doc) for doc in case.documents],
        "profile": case.profile,
        "rubric": case.rubric,
        "recall_markers": list(case.recall_markers),
        "synthetic": case.synthetic,
    }
    return sha256_json(payload)


def benchmark_cases() -> list[tuple[str, GoldenCase]]:
    """Casos medidos: riesgos visibles + holdout sellado, sin exponer su contenido."""
    integrity = verify_holdout_integrity()
    if not integrity.get("ok"):
        raise IncompleteEvidence("El holdout no coincide con su manifiesto; benchmark abortado.")
    holdout = load_holdout_cases(HOLDOUT_PURPOSE_MEASURE)
    cases = [("risk", case) for case in RISK_CASES]
    cases.extend(("holdout", case) for case in holdout)
    if any(not case.synthetic for _, case in cases):
        raise BenchmarkContractError("El benchmark Claude–Codex solo admite casos sintéticos.")
    return cases


def _belongs(alias: str, arm_id: str) -> bool:
    normalized = str(alias or "").strip().lower()
    return any(normalized.startswith(prefix) for prefix in PROVIDER_PREFIXES[arm_id])


def _isolated_policy_for(arm_id: str) -> tuple[str | None, dict[str, list[str]]]:
    """Busca una política cuyo productor y fallbacks LEGALES sean del mismo proveedor."""
    preferred = ["quality_adaptive"] if arm_id == "claude" else []
    policies = preferred + [p for p in llm.VALID_POLICIES if p not in preferred]
    for policy in policies:
        chains = llm._POLICY_CHAINS.get(policy, {})
        routes = {task: list(chains.get(task, ())) for task in llm.LEGAL_TASKS}
        if routes and all(route and all(_belongs(alias, arm_id) for alias in route)
                          for route in routes.values()):
            return policy, routes
    return None, {}


def capability_audit() -> dict[str, ArmCapability]:
    """Separa capacidad productiva de la ruta lateral del mismo grafo para el benchmark."""
    result: dict[str, ArmCapability] = {}
    cli_names = {"claude": "claude", "codex": "codex"}
    for arm_id in ARM_IDS:
        policy, routes = _isolated_policy_for(arm_id)
        installed = shutil.which(cli_names[arm_id]) is not None
        blockers: list[str] = []
        production_blockers: list[str] = []
        if not installed:
            blockers.append(f"cli_{arm_id}_no_instalado")
        if policy is None:
            production_blockers.append("sin_ruta_productor_juridico_en_mia")
        isolated_preflight = codex_cli_preflight() if arm_id == "codex" else None
        isolated_eval_ready = bool(isolated_preflight and isolated_preflight.get("ready"))
        if arm_id == "codex" and not isolated_eval_ready:
            blockers.extend(f"adaptador_codex:{item}"
                            for item in (isolated_preflight or {}).get("blockers", []))
        benchmark_graph_ready = (policy is not None if arm_id == "claude"
                                 else isolated_eval_ready)
        if arm_id == "claude" and policy is None:
            blockers.append("sin_ruta_claude_para_benchmark")
        result[arm_id] = ArmCapability(
            arm_id=arm_id,
            cli_installed=installed,
            producer_policy=policy,
            graph_producer_ready=policy is not None,
            benchmark_graph_ready=benchmark_graph_ready,
            eval_provider="codex" if arm_id == "codex" else None,
            isolated_eval_ready=isolated_eval_ready,
            isolated_eval_preflight=isolated_preflight,
            legal_routes=routes,
            blockers=tuple(blockers),
            production_blockers=tuple(production_blockers),
        )
    return result


def build_plan(*, repetitions: int = MIN_REPETITIONS, revision: str = "unknown") -> dict:
    """Matriz versionada. Bajar de diez es error, no una corrida 'rápida' comparable."""
    repetitions = int(repetitions)
    if repetitions < MIN_REPETITIONS:
        raise BenchmarkContractError(
            f"Se requieren al menos {MIN_REPETITIONS} repeticiones por caso y brazo.")
    capabilities = capability_audit()
    case_rows = []
    for group, case in benchmark_cases():
        digest = (holdout_case_digest(case) if group == "holdout" else _case_digest(case))
        case_rows.append({"case_id": case.id, "group": group, "sha256": digest,
                          "synthetic": True, "repetitions": repetitions})
    body = {
        "schema_version": SCHEMA_VERSION,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "revision": revision,
        "arms": {arm: asdict(capabilities[arm]) for arm in ARM_IDS},
        "cases": case_rows,
        "requirements": {
            "minimum_repetitions": MIN_REPETITIONS,
            "blind_human_review": True,
            "required_telemetry": ["tokens", "latency_ms", "cost_usd", "model",
                                   "effective_model", "effort", "fallbacks"],
            "quality_gates": ["zero_unsupported_claims", "zero_false_verified_citations",
                              "zero_jurisdiction_leaks", "no_material_false_block_increase"],
            "mutation_gate": "execution/test_eval_scoring_mutacion.py",
            "holdout_integrity": verify_holdout_integrity(),
        },
    }
    body["required_turns"] = len(case_rows) * repetitions * len(ARM_IDS)
    body["execution_ready"] = all(c.benchmark_graph_ready for c in capabilities.values())
    body["production_ready"] = all(c.graph_producer_ready for c in capabilities.values())
    body["blockers"] = [f"{arm}:{blocker}" for arm, c in capabilities.items()
                        for blocker in c.blockers]
    body["plan_sha256"] = sha256_json(body)
    return body


async def collect_call_telemetry(tenant_id: str, matter_ids: Iterable[str],
                                 policy: str) -> dict[str, list[dict]]:
    """Lee las llamadas exitosas antes de borrar el tenant y explicita si hubo fallback.

    Los fallos previos se obtienen de ``result.model_fallbacks`` (recolector del turno); esta
    consulta aporta el alias servido, modelo efectivo, esfuerzo, escalamiento, tokens y costo.
    """
    from ..db import pool

    mids = [str(mid) for mid in matter_ids if mid]
    if not mids:
        return {}
    async with pool.tenant_connection(tenant_id) as conn:
        rows = await (await conn.execute(
            "SELECT matter_id::text, task, model, effective_model, effort, "
            "quality_escalation, prompt_tokens, completion_tokens, total_tokens, "
            "cost_usd, node, stop_reason FROM turn_usage "
            "WHERE matter_id = ANY(%s::uuid[]) ORDER BY created_at, id",
            (mids,),
        )).fetchall()
    policy_routes = llm._POLICY_CHAINS.get(policy, {})
    by_matter: dict[str, list[dict]] = {}
    for row in rows:
        task = str(row[1] or "")
        expected = list(policy_routes.get(task, ()))
        alias = str(row[2] or "")
        item = {
            "task": task or None,
            "model": alias,
            "effective_model": str(row[3] or alias),
            "effort": row[4],
            "quality_escalation": row[5],
            "prompt_tokens": int(row[6] or 0),
            "completion_tokens": int(row[7] or 0),
            "total_tokens": int(row[8] or 0),
            "cost_usd": float(row[9] or 0.0),
            "node": row[10],
            "stop_reason": row[11],
            "expected_primary": expected[0] if expected else None,
            "fallback_used": bool(expected and alias != expected[0]),
        }
        by_matter.setdefault(str(row[0]), []).append(item)
    return by_matter


def attach_call_telemetry(results: list[dict], telemetry: dict[str, list[dict]]) -> None:
    """Adjunta en sitio la traza por matter; vacío queda explícito, nunca como cero falso."""
    for result in results:
        calls = telemetry.get(str(result.get("matter_id") or ""), [])
        result["call_telemetry"] = calls
        result["telemetry_complete"] = bool(calls) and all(
            call.get("effective_model") and call.get("model") for call in calls)


def validate_arm_report(report: dict, plan: dict, arm_id: str) -> dict:
    expected = {row["case_id"]: int(row["repetitions"]) for row in plan["cases"]}
    case_runs = report.get("case_runs") or {}
    missing: list[str] = []
    telemetry_missing = 0
    foreign_routes: list[str] = []
    for case_id, required in expected.items():
        results = list((case_runs.get(case_id) or {}).get("results") or [])
        if len(results) != required:
            missing.append(f"{case_id}:{len(results)}/{required}")
        for result in results:
            if not result.get("telemetry_complete"):
                telemetry_missing += 1
            for call in result.get("call_telemetry") or []:
                task = call.get("task")
                if task in llm.LEGAL_TASKS and not _belongs(call.get("model", ""), arm_id):
                    foreign_routes.append(f"{case_id}:{task}:{call.get('model')}")
    complete = not missing and telemetry_missing == 0 and not foreign_routes
    return {"complete": complete, "missing_runs": missing,
            "runs_without_complete_telemetry": telemetry_missing,
            "foreign_legal_routes": foreign_routes}


def _all_results(report: dict) -> list[tuple[str, int, dict]]:
    rows: list[tuple[str, int, dict]] = []
    for case_id, case_report in sorted((report.get("case_runs") or {}).items()):
        for index, result in enumerate(case_report.get("results") or [], 1):
            rows.append((case_id, index, result))
    return rows


def _blind_side(seed: bytes, pair_id: str, arm_id: str) -> str:
    digest = hmac.new(seed, f"{pair_id}:{arm_id}".encode(), hashlib.sha256).digest()
    return "A" if digest[0] % 2 == 0 else "B"


def build_blind_review_packet(arm_reports: dict[str, dict], plan: dict, *, seed: bytes) -> tuple[dict, dict]:
    """Devuelve (paquete_para_revisor, llave_privada). Requiere texto completo de ambos brazos."""
    if set(arm_reports) != set(ARM_IDS):
        raise IncompleteEvidence("Se requieren exactamente los brazos Claude y Codex.")
    validations = {arm: validate_arm_report(arm_reports[arm], plan, arm) for arm in ARM_IDS}
    if not all(v["complete"] for v in validations.values()):
        raise IncompleteEvidence(f"Brazos incompletos: {validations}")

    indexed = {arm: {(cid, idx): result for cid, idx, result in _all_results(report)}
               for arm, report in arm_reports.items()}
    keys = sorted(indexed["claude"])
    if keys != sorted(indexed["codex"]):
        raise IncompleteEvidence("Los brazos no contienen las mismas corridas.")
    pairs, mapping = [], {}
    for case_id, repetition in keys:
        pair_id = hashlib.sha256(
            f"{plan['plan_sha256']}:{case_id}:{repetition}".encode()).hexdigest()[:20]
        sides: dict[str, dict] = {}
        used: set[str] = set()
        for arm_id in ARM_IDS:
            result = indexed[arm_id][(case_id, repetition)]
            draft = result.get("draft_full")
            diagnosis = result.get("diagnosis_full")
            if not isinstance(draft, str) or not isinstance(diagnosis, str):
                raise IncompleteEvidence(
                    f"{case_id} repetición {repetition} no conserva texto completo.")
            side = _blind_side(seed, pair_id, arm_id)
            if side in used:  # HMAC puede asignar el mismo lado; el segundo toma el opuesto.
                side = "B" if side == "A" else "A"
            used.add(side)
            candidate_id = hashlib.sha256(
                f"{pair_id}:{side}:{sha256_json([diagnosis, draft])}".encode()).hexdigest()[:24]
            sides[side] = {"candidate_id": candidate_id, "diagnosis": diagnosis, "draft": draft}
            mapping[candidate_id] = {"arm_id": arm_id, "case_id": case_id,
                                     "repetition": repetition,
                                     "text_sha256": sha256_json([diagnosis, draft])}
        pairs.append({"pair_id": pair_id, "case_id": case_id, "repetition": repetition,
                      "candidates": {side: sides[side] for side in ("A", "B")}})
    packet = {
        "schema_version": SCHEMA_VERSION,
        "packet_type": "blind_human_review",
        "plan_sha256": plan["plan_sha256"],
        "rubric": {"score_range": [1, 5], "dimensions": list(REVIEW_DIMENSIONS),
                   "binary_gates": ["unsupported_claim", "false_verified_citation",
                                    "jurisdiction_leak", "false_block"]},
        "pairs": pairs,
    }
    packet["packet_sha256"] = sha256_json(packet)
    key = {"schema_version": SCHEMA_VERSION, "packet_sha256": packet["packet_sha256"],
           "candidate_mapping": mapping}
    key["key_sha256"] = sha256_json(key)
    return packet, key


def review_template(packet: dict) -> dict:
    return {
        "schema_version": SCHEMA_VERSION,
        "packet_sha256": packet["packet_sha256"],
        "reviewer_id": "",
        "independent_legal_reviewer": True,
        "reviews": [{
            "pair_id": pair["pair_id"],
            "scores": {side: {dimension: None for dimension in REVIEW_DIMENSIONS}
                       for side in ("A", "B")},
            "gates": {side: {gate: None for gate in packet["rubric"]["binary_gates"]}
                      for side in ("A", "B")},
            "preference": None,
            "comments": "",
        } for pair in packet.get("pairs", [])],
    }


def validate_human_review(packet: dict, review: dict) -> dict:
    reasons: list[str] = []
    if review.get("packet_sha256") != packet.get("packet_sha256"):
        reasons.append("packet_sha256_no_coincide")
    if not str(review.get("reviewer_id") or "").strip():
        reasons.append("reviewer_id_ausente")
    expected = {pair["pair_id"] for pair in packet.get("pairs", [])}
    rows = {row.get("pair_id"): row for row in review.get("reviews") or []}
    if set(rows) != expected:
        reasons.append("cobertura_de_pares_incompleta")
    for pair_id in expected & set(rows):
        row = rows[pair_id]
        if row.get("preference") not in ("A", "B", "tie"):
            reasons.append(f"{pair_id}:preferencia_invalida")
        for side in ("A", "B"):
            scores = (row.get("scores") or {}).get(side) or {}
            if any(not isinstance(scores.get(dim), int) or not 1 <= scores[dim] <= 5
                   for dim in REVIEW_DIMENSIONS):
                reasons.append(f"{pair_id}:{side}:scores_invalidos")
            gates = (row.get("gates") or {}).get(side) or {}
            if any(not isinstance(gates.get(gate), bool)
                   for gate in packet["rubric"]["binary_gates"]):
                reasons.append(f"{pair_id}:{side}:gates_invalidos")
    return {"complete": not reasons, "reasons": sorted(set(reasons)),
            "n_expected": len(expected), "n_reviewed": len(expected & set(rows))}


def arm_metrics(report: dict) -> dict:
    results = [result for _, _, result in _all_results(report)]
    latencies = [float(r.get("elapsed_ms")) for r in results if r.get("elapsed_ms") is not None]
    tokens = [int((r.get("usage") or {}).get("total_tokens", 0) or 0) for r in results]
    costs = [float((r.get("usage") or {}).get("cost_usd", 0.0) or 0.0) for r in results]
    fallbacks = [bool(r.get("model_fallbacks")) or any(
        call.get("fallback_used") for call in r.get("call_telemetry") or []) for r in results]
    leaks = [bool((r.get("jurisdiction_leak") or {}).get("leak")) for r in results]
    unsupported = [int((r.get("score") or {}).get("citas_sin_respaldo", 0) or 0)
                   for r in results]
    return {
        "n": len(results),
        "tokens_total": sum(tokens),
        "tokens_mean": round(statistics.fmean(tokens), 2) if tokens else None,
        "latency_p50_ms": round(statistics.median(latencies), 1) if latencies else None,
        "cost_total_usd": round(sum(costs), 6),
        "cost_mean_usd": round(statistics.fmean(costs), 6) if costs else None,
        "fallback_rate": round(sum(fallbacks) / len(fallbacks), 4) if fallbacks else None,
        "jurisdiction_leaks": sum(leaks),
        "unsupported_citations": sum(unsupported),
    }


def certification_status(arm_reports: dict[str, dict], plan: dict,
                         review_validation: dict | None = None) -> dict:
    validations = {arm: validate_arm_report(arm_reports.get(arm, {}), plan, arm)
                   for arm in ARM_IDS}
    blockers = []
    if not plan.get("execution_ready"):
        blockers.extend(plan.get("blockers") or [])
    blockers.extend(f"{arm}:evidencia_incompleta" for arm, value in validations.items()
                    if not value["complete"])
    if not review_validation or not review_validation.get("complete"):
        blockers.append("revision_juridica_humana_ciega_incompleta")
    metrics = {arm: arm_metrics(arm_reports.get(arm, {})) for arm in ARM_IDS}
    for arm, values in metrics.items():
        if values["jurisdiction_leaks"]:
            blockers.append(f"{arm}:fuga_jurisdiccional")
        if values["unsupported_citations"]:
            blockers.append(f"{arm}:citas_sin_respaldo")
    return {"certifiable": not blockers, "winner": None,
            "blockers": sorted(set(blockers)), "validations": validations,
            "metrics": metrics,
            "note": "El ganador solo se calcula tras desenmascarar revisiones humanas completas."}
