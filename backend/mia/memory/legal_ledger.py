"""Ledger jurídico append-only y ligado a la huella del artefacto.

El checkpoint de LangGraph es estado de ejecución, no evidencia de que un documento
concreto pasó los controles. Este módulo registra cada versión y cada recibo en
Postgres bajo RLS. Un final solo puede nacer si los recibos aprobados corresponden
exactamente a su ``content_hash``.
"""
from __future__ import annotations

import hashlib
import json
import uuid
from typing import Any

from psycopg.types.json import Json

from ..db import pool


REQUIRED_FINAL_GATES = ("citation_verification", "human_approval")
_PASSING_VERIFIER_STATES = frozenset({"apto", "sin_citas", "sello"})


def content_hash(text: str) -> str:
    """SHA-256 estable de la versión exacta que vio/escribió el abogado."""
    return hashlib.sha256((text or "").encode("utf-8")).hexdigest()


def verification_passes(report: dict | None) -> bool:
    """Solo un informe sin alertas abiertas puede habilitar un documento final.

    La ausencia del informe nunca equivale a aprobación. El verificador independiente
    debe dejar un estado positivo explícito; caída o salida ambigua bloquean el final.
    """
    if not isinstance(report, dict):
        return False
    unresolved = ("marcadas", "anotadas", "omitidas", "quemadas")
    if any(report.get(key) for key in unresolved):
        return False
    gate = report.get("gate_llm")
    return isinstance(gate, dict) and gate.get("veredicto") in _PASSING_VERIFIER_STATES


async def append_artifact(
    tenant_id: str, matter_id: str, text: str, *, kind: str,
    parent_hash: str = "", trace_id: str = "", metadata: dict | None = None,
) -> str:
    """Registra una versión sin sobrescribir las anteriores y devuelve su hash."""
    digest = content_hash(text)
    async with pool.tenant_connection(tenant_id) as conn:
        await conn.execute(
            "INSERT INTO legal_artifact_ledger "
            "(tenant_id, matter_id, artifact_kind, content, content_hash, parent_hash, trace_id, metadata) "
            "VALUES (%s::uuid, %s::uuid, %s, %s, %s, %s, %s, %s) ON CONFLICT DO NOTHING",
            (tenant_id, matter_id, kind, text, digest, parent_hash or None,
             trace_id or None, Json(metadata or {})),
        )
    return digest


async def record_gate(
    tenant_id: str, matter_id: str, artifact_hash: str, *, gate: str,
    passed: bool, evidence: dict | None = None, run_id: str = "", trace_id: str = "",
    checker_version: str = "", jurisdictions: list[str] | None = None,
    source_hashes: list[str] | set[str] | None = None,
) -> None:
    """Añade un recibo histórico e idempotente; jamás reescribe uno anterior."""
    run = run_id or str(uuid.uuid4())
    sources = sorted({str(x) for x in (source_hashes or []) if str(x)})
    juris = sorted({str(x) for x in (jurisdictions or []) if str(x)})
    context_hash = hashlib.sha256(json.dumps(
        {"jurisdictions": juris, "source_hashes": sources},
        sort_keys=True, separators=(",", ":"), ensure_ascii=False,
    ).encode("utf-8")).hexdigest()
    event_key = hashlib.sha256(
        f"{run}\x1f{artifact_hash}\x1f{gate}\x1f{checker_version}\x1f{passed}\x1f{context_hash}".encode("utf-8")
    ).hexdigest()
    async with pool.tenant_connection(tenant_id) as conn:
        await conn.execute(
            "INSERT INTO legal_gate_receipts "
            "(tenant_id, matter_id, artifact_hash, gate_name, passed, evidence, run_id, "
            " trace_id, checker_version, context_hash, jurisdiction_codes, source_hashes, event_key) "
            "VALUES (%s::uuid, %s::uuid, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s) "
            "ON CONFLICT (event_key) DO NOTHING",
            (tenant_id, matter_id, artifact_hash, gate, bool(passed), Json(evidence or {}),
             run, trace_id or "", checker_version or "unknown", context_hash, juris, sources,
             event_key),
        )


async def finalise_if_gated(
    tenant_id: str, matter_id: str, text: str, *, parent_hash: str = "",
    trace_id: str = "", metadata: dict | None = None,
) -> bool:
    """Crea el artefacto final solo si TODOS los gates exigidos aprobaron esa huella.

    La consulta y el INSERT viven en la misma transacción y se repite la huella en
    SQL. Así una aprobación de un borrador previo no puede desbloquear una edición.
    """
    digest = content_hash(text)
    async with pool.tenant_connection(tenant_id) as conn:
        rows = await (await conn.execute(
            "SELECT gate_name, passed FROM ("
            " SELECT gate_name, passed, row_number() OVER "
            " (PARTITION BY gate_name ORDER BY created_at DESC, id DESC) AS rn "
            " FROM legal_gate_receipts WHERE matter_id=%s::uuid AND artifact_hash=%s"
            ") latest WHERE rn=1", (matter_id, digest))).fetchall()
        passed = {str(row[0]): bool(row[1]) for row in rows}
        if not all(passed.get(gate) is True for gate in REQUIRED_FINAL_GATES):
            return False
        await conn.execute(
            "INSERT INTO legal_artifact_ledger "
            "(tenant_id, matter_id, artifact_kind, content, content_hash, parent_hash, trace_id, metadata) "
            "VALUES (%s::uuid, %s::uuid, 'final', %s, %s, %s, %s, %s) ON CONFLICT DO NOTHING",
            (tenant_id, matter_id, text, digest, parent_hash or None, trace_id or None,
             Json(metadata or {})),
        )
    return True


async def latest_final(tenant_id: str, matter_id: str) -> dict | None:
    """Final más reciente del asunto, visible únicamente bajo RLS del propietario."""
    async with pool.tenant_connection(tenant_id) as conn:
        row = await (await conn.execute(
            "SELECT content, content_hash, created_at FROM legal_artifact_ledger "
            "WHERE matter_id=%s::uuid AND artifact_kind='final' "
            "ORDER BY created_at DESC, id DESC LIMIT 1", (matter_id,))).fetchone()
    if not row:
        return None
    return {"content": str(row[0]), "content_hash": str(row[1]), "created_at": row[2]}


async def is_current_final(tenant_id: str, matter_id: str, text: str) -> bool:
    final = await latest_final(tenant_id, matter_id)
    return bool(final and final["content_hash"] == content_hash(text))


async def record_export(tenant_id: str, matter_id: str, artifact_hash: str, *,
                        export_format: str, actor: str = "abogado") -> None:
    """Registra cada descarga final como evento auditable; nunca contiene el documento."""
    async with pool.tenant_connection(tenant_id) as conn:
        await conn.execute(
            "INSERT INTO legal_export_events "
            "(tenant_id, matter_id, artifact_hash, export_format, actor) "
            "VALUES (%s::uuid, %s::uuid, %s, %s, %s)",
            (tenant_id, matter_id, artifact_hash, export_format, actor),
        )


async def list_exports(tenant_id: str, *, matter_id: str | None = None,
                       limit: int = 50) -> list[dict[str, Any]]:
    """Lectura de salidas finales. Nunca incluye el documento, solo la auditoría."""
    cap = max(1, min(int(limit), 200))
    async with pool.tenant_connection(tenant_id) as conn:
        if matter_id:
            rows = await (await conn.execute(
                "SELECT matter_id, artifact_hash, export_format, actor, created_at "
                "FROM legal_export_events WHERE matter_id = %s::uuid "
                "ORDER BY created_at DESC LIMIT %s",
                (matter_id, cap))).fetchall()
        else:
            rows = await (await conn.execute(
                "SELECT matter_id, artifact_hash, export_format, actor, created_at "
                "FROM legal_export_events ORDER BY created_at DESC LIMIT %s",
                (cap,))).fetchall()
    return [
        {
            "matter_id": str(row[0]),
            "artifact_hash": str(row[1]),
            "export_format": str(row[2]),
            "actor": str(row[3]),
            "created_at": row[4],
        }
        for row in rows
    ]
