"""Memoria derivada con cobertura comprobable; nunca sustituye ni borra originales."""
from __future__ import annotations

import asyncio
import hashlib
import json
import uuid
from datetime import timezone

from ..agent.context_compressor import (
    ContextCompressor, PROTECT_FIRST_N, PROTECT_LAST_N, SUMMARY_PREFIX,
    SUMMARY_END_MARKER, THRESHOLD_PERCENT, VERIFICAR_MARKER,
)
from ..db import pool

VERSION = "assistant-memory-v1"
PAGE_SIZE = 200
MAX_SEGMENTS_PER_TURN = 8
NOTICE = ("No pude recuperar toda la conversación con suficiente seguridad. "
          "No respondí todavía a tu solicitud ni eliminé mensajes. ")


class MemoryUnavailable(ValueError):
    pass


def _hash(rows) -> str:
    return hashlib.sha256(json.dumps(
        [(str(r[0]), r[1].astimezone(timezone.utc).isoformat(), r[2], r[3]) for r in rows],
        ensure_ascii=False, separators=(",", ":"),
    ).encode("utf-8")).hexdigest()


def _message(row) -> dict:
    return {"role": row[2], "content": row[3]}


def _summary(text: str) -> dict:
    return {"role": "user", "content": f"{SUMMARY_PREFIX}\n{text}\n\n{SUMMARY_END_MARKER}"}


async def _load(tenant_id, conversation_id):
    async with pool.tenant_connection(tenant_id) as conn:
        await conn.execute(
            "INSERT INTO assistant_conversation_memory(tenant_id,conversation_id) "
            "SELECT tenant_id,id FROM assistant_conversations WHERE id=%s::uuid "
            "ON CONFLICT DO NOTHING", (conversation_id,))
        cp = await (await conn.execute(
            "SELECT revision,compressor_version,summary,cursor_created_at,cursor_id,covered_hash,ineffective_count,eligible_basis "
            "FROM assistant_conversation_memory WHERE tenant_id=%s::uuid AND conversation_id=%s::uuid",
            (tenant_id,conversation_id))).fetchone()
        if cp is None:
            raise MemoryUnavailable(NOTICE + "No encontré esta conversación.")
        rows = []
        # Un único SELECT con snapshot estable; fetchmany pagina sin saltar prefijos.
        async with conn.cursor(name="memory_" + uuid.uuid4().hex) as cursor:
            await cursor.execute(
                "SELECT id,created_at,role,content FROM assistant_messages "
                "WHERE conversation_id=%s::uuid ORDER BY created_at,id", (conversation_id,))
            while page := await cursor.fetchmany(PAGE_SIZE):
                rows.extend(page)
    return rows, cp


async def _invalidate(tenant_id, conversation_id, revision):
    async with pool.tenant_connection(tenant_id) as conn:
        row = await (await conn.execute(
            "UPDATE assistant_conversation_memory SET revision=revision+1,summary='',"
            "cursor_created_at=NULL,cursor_id=NULL,covered_hash='',compressor_version='',ineffective_count=0,eligible_basis='',updated_at=now() "
            "WHERE tenant_id=%s::uuid AND conversation_id=%s::uuid AND revision=%s RETURNING revision",
            (tenant_id,conversation_id,revision))).fetchone()
        if row is None:
            raise MemoryUnavailable(NOTICE + "La memoria se está actualizando; vuelve a pedirlo al terminar.")
        # Una revisión invalidada puede haber resumido antes un prefijo idéntico.
        # Permitir reconstruirlo; conservar running/uncertain para no duplicar trabajo vivo.
        await conn.execute(
            "UPDATE assistant_memory_attempts SET status='obsolete',updated_at=now() "
            "WHERE tenant_id=%s::uuid AND conversation_id=%s::uuid AND status='completed'",
            (tenant_id,conversation_id))
        return row[0]


async def _claim(tenant_id, conversation_id, input_hash, eligible_hash):
    claim = str(uuid.uuid4())
    async with pool.tenant_connection(tenant_id) as conn:
        row = await (await conn.execute(
            "INSERT INTO assistant_memory_attempts(tenant_id,conversation_id,input_hash,eligible_hash,claim_id,status) "
            "VALUES(%s::uuid,%s::uuid,%s,%s,%s::uuid,'running') "
            "ON CONFLICT(tenant_id,conversation_id,input_hash) DO UPDATE SET claim_id=EXCLUDED.claim_id,"
            "eligible_hash=EXCLUDED.eligible_hash,status='running',updated_at=now() "
            "WHERE assistant_memory_attempts.status IN ('failed','obsolete') OR "
            "(assistant_memory_attempts.status='ineffective' AND "
            "assistant_memory_attempts.eligible_hash<>EXCLUDED.eligible_hash) RETURNING claim_id",
            (tenant_id,conversation_id,input_hash,eligible_hash,claim))).fetchone()
    if row is None:
        raise MemoryUnavailable(NOTICE + "Ese tramo ya se está revisando o no produjo un resumen útil. "
                                "Puedes continuar en una conversación nueva conservando esta como referencia.")
    return claim


async def _attempt_status(tenant_id, conversation_id, claim, status):
    async with pool.tenant_connection(tenant_id) as conn:
        await conn.execute(
            "UPDATE assistant_memory_attempts SET status=%s,updated_at=now() "
            "WHERE tenant_id=%s::uuid AND conversation_id=%s::uuid AND claim_id=%s::uuid AND status='running'",
            (status,tenant_id,conversation_id,claim))


async def _publish(tenant_id, conversation_id, revision, text, last, covered_hash, claim,
                   ineffective_count, eligible_basis):
    async with pool.tenant_connection(tenant_id) as conn:
        # Los triggers de originales toman esta misma fila. Cotejo y CAS son atómicos
        # frente a edición/retroinserción; no hay proveedor dentro de esta transacción.
        await conn.execute("SELECT id FROM assistant_conversations WHERE id=%s::uuid FOR UPDATE", (conversation_id,))
        current = await (await conn.execute(
            "SELECT id,created_at,role,content FROM assistant_messages WHERE conversation_id=%s::uuid "
            "AND (created_at,id)<=(%s,%s::uuid) ORDER BY created_at,id",
            (conversation_id,last[1],str(last[0])))).fetchall()
        if _hash(current) != covered_hash:
            return False
        row = await (await conn.execute(
            "UPDATE assistant_conversation_memory SET revision=revision+1,compressor_version=%s,summary=%s,"
            "cursor_created_at=%s,cursor_id=%s::uuid,covered_hash=%s,ineffective_count=%s,eligible_basis=%s,updated_at=now() "
            "WHERE tenant_id=%s::uuid AND conversation_id=%s::uuid AND revision=%s RETURNING revision",
            (VERSION,text,last[1],str(last[0]),covered_hash,ineffective_count,eligible_basis,tenant_id,conversation_id,revision))).fetchone()
        if row is None:
            return False
        await conn.execute(
            "UPDATE assistant_memory_attempts SET status='completed',updated_at=now() "
            "WHERE tenant_id=%s::uuid AND conversation_id=%s::uuid AND claim_id=%s::uuid",
            (tenant_id,conversation_id,claim))
        return True


def _render(rows, covered, summary):
    head_end = min(PROTECT_FIRST_N, len(rows))
    result = [_message(r) for r in rows[:head_end]]
    if summary:
        result.append(_summary(summary))
    result.extend(_message(r) for r in rows[head_end:covered+1] if VERIFICAR_MARKER in r[3])
    result.extend(_message(r) for r in rows[max(head_end,covered+1):])
    return result


async def assemble(tenant_id: str, conversation_id: str, window: int, *,
                   compressor_factory=ContextCompressor) -> list[dict]:
    rows, cp = await _load(tenant_id, conversation_id)
    revision, version, summary, cursor_time, cursor_id, covered_hash, ineffective_count, basis = cp
    covered = min(PROTECT_FIRST_N, len(rows)) - 1
    if cursor_id is not None:
        found = next((i for i,r in enumerate(rows) if r[0] == cursor_id and r[1] == cursor_time), -1)
        if (version != VERSION or not summary.strip() or found < covered
                or found >= len(rows)-PROTECT_LAST_N or _hash(rows[:found+1]) != covered_hash):
            revision = await _invalidate(tenant_id, conversation_id, revision)
            summary = ""
            ineffective_count = 0
        else:
            covered = found
    elif summary or version:
        revision = await _invalidate(tenant_id, conversation_id, revision)
        summary = ""
        ineffective_count = 0
    eligible_basis = _hash(rows[PROTECT_FIRST_N:max(PROTECT_FIRST_N,len(rows)-PROTECT_LAST_N)])
    if basis != eligible_basis:
        ineffective_count = 0
    for _ in range(MAX_SEGMENTS_PER_TURN):
        history = _render(rows, covered, summary)
        if ContextCompressor._count(history) < window * THRESHOLD_PERCENT:
            return history
        if ineffective_count >= 2:
            if ContextCompressor._count(history) <= window * 0.8:
                return history
            raise MemoryUnavailable(NOTICE + "Los últimos resúmenes apenas redujeron el contexto. "
                                    "Puedes continuar en otra conversación conservando esta como referencia.")
        eligible = rows[covered+1:max(covered+1,len(rows)-PROTECT_LAST_N)]
        if not eligible:
            return history  # el guard final decide si los originales protegidos caben
        # Limitar por tokens Y por mensajes antes de llamar al resumidor.
        segment = []
        tokens = ContextCompressor._count([_summary(summary)]) if summary else 0
        for row in eligible[:PAGE_SIZE]:
            amount = ContextCompressor._count([_message(row)])
            if tokens + amount > window * 0.45:
                break
            segment.append(row)
            tokens += amount
        to_summarize = [_message(r) for r in segment if VERIFICAR_MARKER not in r[3]]
        if not to_summarize:
            if ContextCompressor._count(history) <= window * 0.8:
                return history
            raise MemoryUnavailable(NOTICE + "Los mensajes o verificaciones pendientes exceden el contexto disponible.")
        next_covered = covered + len(segment)
        next_hash = _hash(rows[:next_covered+1])
        input_hash = hashlib.sha256((VERSION + summary + next_hash).encode("utf-8")).hexdigest()
        try:
            claim = await _claim(tenant_id, conversation_id, input_hash, _hash(eligible))
        except MemoryUnavailable:
            if ContextCompressor._count(history) <= window * 0.8:
                return history
            raise
        try:
            candidate = await asyncio.to_thread(
                compressor_factory().summarize_segment, to_summarize,
                previous_summary=summary, model_context_window=window)
        except asyncio.CancelledError:
            await _attempt_status(tenant_id, conversation_id, claim, "uncertain")
            raise
        except Exception as error:
            await _attempt_status(tenant_id, conversation_id, claim, "failed")
            if ContextCompressor._count(history) <= window * 0.8:
                return history
            raise MemoryUnavailable(NOTICE + "El resumen no terminó. Puedes volver a solicitarlo más tarde.") from error
        candidate_history = _render(rows, next_covered, candidate)
        if not candidate or ContextCompressor._count(candidate_history) >= ContextCompressor._count(history):
            await _attempt_status(tenant_id, conversation_id, claim, "ineffective")
            if ContextCompressor._count(history) <= window * 0.8:
                return history
            raise MemoryUnavailable(NOTICE + "El resumen no redujo el contexto. Puedes abrir una conversación nueva.")
        savings = 1 - ContextCompressor._count(candidate_history) / ContextCompressor._count(history)
        next_ineffective = ineffective_count + 1 if savings < 0.1 else 0
        if not await _publish(tenant_id, conversation_id, revision, candidate,
                              rows[next_covered], next_hash, claim, next_ineffective, eligible_basis):
            await _attempt_status(tenant_id, conversation_id, claim, "obsolete")
            raise MemoryUnavailable(NOTICE + "Los mensajes cambiaron durante la revisión; vuelve a solicitarla.")
        revision += 1
        summary, covered = candidate, next_covered
        ineffective_count = next_ineffective
    history = _render(rows, covered, summary)
    if ContextCompressor._count(history) > window * 0.8:
        raise MemoryUnavailable(NOTICE + "Guardé el avance de memoria. Pide continuar para revisar el tramo restante.")
    return history


def guard_final_context(messages: list[dict], window: int) -> None:
    # Espacio para la respuesta y variación del contador; nunca truncar pendientes.
    if ContextCompressor._count(messages) > window * 0.8:
        raise MemoryUnavailable(NOTICE + "El historial, los pendientes o los adjuntos no caben en este turno. "
                                "Reduce los adjuntos o continúa en otra conversación.")
