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
from ..jurisdiction.resolver import resolve_jurisdictions_in_connection
from .source_fingerprints import fingerprint, FIELDS


REQUIRED_FINAL_GATES = ("citation_verification", "human_approval")
CHECKER_VERSIONS = {"citation_verification": "citation-verifier-v3",
                    "human_approval": "human-attestation-v1"}


def make_context(run_id: str, jurisdictions: list[str], sources: list, documents: list) -> dict | None:
    entries = []
    for source in [*sources, *documents]:
        if not isinstance(source, dict):
            return None
        kind, identity = source.get("source_kind"), str(source.get("source_id") or source.get("id") or "")
        original = str(source.get("origin_hash") or "")
        reviewed = content_hash(str(source.get("content") or source.get("text") or ""))
        if kind not in ("legal_norm", "jurisprudence", "chunk") or not identity or len(original) != 64:
            return None
        entries.append({"kind": kind, "id": identity, "origin_hash": original,
                        "reviewed_hash": reviewed})
    context = {"run_id": run_id, "jurisdictions": sorted(set(jurisdictions)),
               "sources": sorted(entries, key=lambda e: (e["kind"], e["id"])),
               "checker_versions": CHECKER_VERSIONS}
    return context if valid_context(context) else None


def valid_context(context: object) -> bool:
    if not isinstance(context, dict) or not context.get("run_id") or not context.get("jurisdictions"):
        return False
    if context.get("checker_versions") != CHECKER_VERSIONS or not isinstance(context.get("sources"), list):
        return False
    for source in context["sources"]:
        if not isinstance(source, dict) or source.get("kind") not in ("legal_norm", "jurisprudence", "chunk"):
            return False
        try:
            uuid.UUID(source["id"])
        except (ValueError, KeyError, TypeError):
            return False
        if any(len(str(source.get(k) or "")) != 64 for k in ("origin_hash", "reviewed_hash")):
            return False
    return bool(context["sources"])


def context_hash(context: dict) -> str:
    return content_hash(json.dumps(context, ensure_ascii=False, sort_keys=True, separators=(",", ":")))


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
    return (isinstance(gate, dict) and gate.get("veredicto") == "apto" and
            gate.get("checker_version") == CHECKER_VERSIONS["citation_verification"] and
            (report.get("evidence_coverage") or {}).get("complete") is True)


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
    verification_context: dict | None = None,
) -> None:
    """Añade un recibo histórico; jamás reescribe uno anterior."""
    run = run_id or str(uuid.uuid4())
    sources = sorted({str(x) for x in (source_hashes or []) if str(x)})
    juris = sorted({str(x) for x in (jurisdictions or []) if str(x)})
    ctx_hash = hashlib.sha256(json.dumps(
        {"jurisdictions": juris, "source_hashes": sources},
        sort_keys=True, separators=(",", ":"), ensure_ascii=False,
    ).encode("utf-8")).hexdigest()
    if valid_context(verification_context):
        run = verification_context["run_id"]
        juris = verification_context["jurisdictions"]
        sources = sorted({s["origin_hash"] for s in verification_context["sources"]})
        ctx_hash = context_hash(verification_context)
    event_key = hashlib.sha256(
        f"{run}\x1f{artifact_hash}\x1f{gate}\x1f{checker_version}\x1f{passed}\x1f{ctx_hash}\x1f{trace_id}".encode("utf-8")
    ).hexdigest()
    async with pool.tenant_connection(tenant_id) as conn:
        await conn.execute(
            "INSERT INTO legal_gate_receipts "
            "(tenant_id, matter_id, artifact_hash, gate_name, passed, evidence, run_id, "
            " trace_id, checker_version, context_hash, jurisdiction_codes, source_hashes, event_key) "
            "VALUES (%s::uuid, %s::uuid, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s) "
            "ON CONFLICT (event_key) DO NOTHING",
            (tenant_id, matter_id, artifact_hash, gate, bool(passed), Json(evidence or {}),
             run, trace_id or "", checker_version or "unknown", ctx_hash, juris, sources,
             event_key),
        )


async def finalise_if_gated(
    tenant_id: str, matter_id: str, text: str, *, parent_hash: str = "",
    trace_id: str = "", metadata: dict | None = None,
    verification_context: dict | None = None,
) -> bool:
    """Crea el artefacto final solo si TODOS los gates exigidos aprobaron esa huella.

    La consulta y el INSERT viven en la misma transacción y se repite la huella en
    SQL. Así una aprobación de un borrador previo no puede desbloquear una edición.
    """
    digest = content_hash(text)
    if not valid_context(verification_context):
        return False
    ctx = verification_context
    async with pool.tenant_connection(tenant_id) as conn:
        if not await _context_is_live(conn, tenant_id, matter_id, ctx):
            return False
        rows = await (await conn.execute(
            "SELECT gate_name, passed FROM ("
            " SELECT gate_name, passed, row_number() OVER "
            " (PARTITION BY gate_name ORDER BY created_at DESC, id DESC) AS rn "
            " FROM legal_gate_receipts WHERE matter_id=%s::uuid AND artifact_hash=%s"
            " AND run_id=%s AND context_hash=%s AND ((gate_name='citation_verification' AND checker_version=%s)"
            " OR (gate_name='human_approval' AND checker_version=%s))"
            ") latest WHERE rn=1", (matter_id, digest, ctx["run_id"], context_hash(ctx),
                                      CHECKER_VERSIONS["citation_verification"], CHECKER_VERSIONS["human_approval"]))).fetchall()
        passed = {str(row[0]): bool(row[1]) for row in rows}
        if not all(passed.get(gate) is True for gate in REQUIRED_FINAL_GATES):
            return False
        await conn.execute(
            "INSERT INTO legal_artifact_ledger "
            "(tenant_id, matter_id, artifact_kind, content, content_hash, parent_hash, trace_id, metadata) "
            "VALUES (%s::uuid, %s::uuid, 'final', %s, %s, %s, %s, %s) ON CONFLICT DO NOTHING",
            (tenant_id, matter_id, text, digest, parent_hash or None, trace_id or None,
             Json({**(metadata or {}), "verification_context": ctx,
                   "verification_context_hash": context_hash(ctx)})),
        )
    return True


async def latest_final(tenant_id: str, matter_id: str) -> dict | None:
    """Final más reciente del asunto, visible únicamente bajo RLS del propietario."""
    async with pool.tenant_connection(tenant_id) as conn:
        row = await (await conn.execute(
            "SELECT content, content_hash, created_at, metadata FROM legal_artifact_ledger "
            "WHERE matter_id=%s::uuid AND artifact_kind='final' "
            "ORDER BY created_at DESC, id DESC LIMIT 1", (matter_id,))).fetchone()
    if not row:
        return None
    return {"content": str(row[0]), "content_hash": str(row[1]), "created_at": row[2], "metadata": row[3]}


async def _context_is_live(conn, tenant_id: str, matter_id: str, context: dict) -> bool:
    row = await (await conn.execute("SELECT id FROM matters WHERE id=%s::uuid", (matter_id,))).fetchone()
    if not row:
        return False
    jurisdictions = await resolve_jurisdictions_in_connection(conn, tenant_id, matter_id)
    if sorted(set(jurisdictions)) != context["jurisdictions"]:
        return False
    for source in context["sources"]:
        if source["kind"] == "legal_norm":
            row = await (await conn.execute("SELECT id,norm_type,norm_number,issuing_body,title,full_text,effective_date,expiry_date,jurisdiction FROM legal_norms WHERE id=%s::uuid",
                                           (source["id"],))).fetchone()
        elif source["kind"] == "chunk":
            row = await (await conn.execute("SELECT c.id,c.content,c.document_id,c.ord,c.folio_ancla,d.filename FROM chunks c JOIN documents d ON d.id=c.document_id "
                                           "WHERE c.id=%s::uuid AND d.matter_id=%s::uuid",
                                           (source["id"], matter_id))).fetchone()
        else:
            # SAT stores derived ratio/obiter, not a guaranteed primary judgment.
            return False
        if not row or fingerprint(source["kind"], dict(zip(FIELDS[source["kind"]], row))) != source["origin_hash"]:
            return False
    return True


async def validated_latest_final(tenant_id: str, matter_id: str) -> dict | None:
    """Read final only when its original context, live evidence and receipts remain valid."""
    final = await latest_final(tenant_id, matter_id)
    if not final:
        return None
    metadata = final.get("metadata") or {}
    context = metadata.get("verification_context")
    if not valid_context(context) or metadata.get("verification_context_hash") != context_hash(context):
        return None
    async with pool.tenant_connection(tenant_id) as conn:
        if not await _context_is_live(conn, tenant_id, matter_id, context):
            return None
        rows = await (await conn.execute(
            "SELECT gate_name, passed FROM (SELECT gate_name, passed, row_number() OVER "
            "(PARTITION BY gate_name ORDER BY created_at DESC, id DESC) AS rn FROM legal_gate_receipts "
            "WHERE matter_id=%s::uuid AND artifact_hash=%s AND run_id=%s AND context_hash=%s "
            "AND ((gate_name='citation_verification' AND checker_version=%s) OR "
            "(gate_name='human_approval' AND checker_version=%s))) latest WHERE rn=1",
            (matter_id, final["content_hash"], context["run_id"], context_hash(context),
             CHECKER_VERSIONS["citation_verification"], CHECKER_VERSIONS["human_approval"]))).fetchall()
        passed = {str(row[0]): row[1] for row in rows}
        if not all(passed.get(gate) is True for gate in REQUIRED_FINAL_GATES):
            return None
    return final


async def is_current_final(tenant_id: str, matter_id: str, text: str) -> bool:
    final = await validated_latest_final(tenant_id, matter_id)
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
