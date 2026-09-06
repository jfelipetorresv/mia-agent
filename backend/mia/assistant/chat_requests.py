"""Reservas durables de turnos: nunca reejecutar una llamada de desenlace incierto."""
from __future__ import annotations

from dataclasses import dataclass, replace
import hashlib
import json
from typing import Awaitable, Callable
import uuid

from ..db import pool


class ChatRequestConflict(Exception):
    """Conflicto recuperable por el usuario; nunca habilita otra inferencia."""


@dataclass(frozen=True)
class PreparedChat:
    tenant_id: str
    user_id: str | None
    conversation_id: str | None
    message: str
    request_id: str | None = None
    payload_hash: str = ""
    cached: dict | None = None


def _key(turn: PreparedChat) -> tuple:
    return turn.tenant_id, turn.user_id, turn.request_id


def _existing(turn: PreparedChat, row) -> PreparedChat:
    if row[0] != turn.payload_hash:
        raise ChatRequestConflict("Este envío ya corresponde a otro mensaje. No se ejecutó de nuevo.")
    if row[1] == "completed" and isinstance(row[2], dict):
        return replace(turn, cached=row[2])
    if row[1] == "running":
        raise ChatRequestConflict(
            "Este envío sigue en curso o no confirmó su cierre. Revisa el historial antes de enviar otro.")
    raise ChatRequestConflict(
        "No pude confirmar cómo terminó este envío. Para evitar duplicarlo, revisa el historial antes de enviar otro.")


async def _lookup(turn: PreparedChat):
    async with pool.tenant_connection(turn.tenant_id) as conn:
        return await (await conn.execute(
            "SELECT payload_hash, status, response FROM assistant_chat_requests "
            "WHERE tenant_id = %s::uuid AND user_id = %s::uuid AND request_id = %s::uuid",
            _key(turn),
        )).fetchone()


async def prepare(tenant_id: str, user_id: str | None, conversation_id: str | None,
                  message: str, *, request_id: str | None = None,
                  before_execute: Callable[[], Awaitable[None]] | None = None) -> PreparedChat:
    """Cache antes de presupuesto; reserva después. Solo transacciones cortas."""
    turn = PreparedChat(tenant_id, user_id, conversation_id, message)
    if request_id is not None:
        if not user_id:
            raise ValueError("No pude identificar al usuario de este envío. Vuelve a iniciar sesión.")
        try:
            request_id = str(uuid.UUID(str(request_id)))
        except (ValueError, TypeError, AttributeError):
            raise ValueError("La identificación del envío no es válida.") from None
        digest = hashlib.sha256(json.dumps(
            {"conversation_id": conversation_id, "message": message},
            ensure_ascii=False, sort_keys=True, separators=(",", ":"),
        ).encode("utf-8")).hexdigest()
        turn = replace(turn, request_id=request_id, payload_hash=digest)
        row = await _lookup(turn)
        if row is not None:
            return _existing(turn, row)
    if before_execute is not None:
        await before_execute()
    if request_id is not None:
        async with pool.tenant_connection(tenant_id) as conn:
            inserted = await (await conn.execute(
                "INSERT INTO assistant_chat_requests (tenant_id, user_id, request_id, payload_hash) "
                "VALUES (%s::uuid, %s::uuid, %s::uuid, %s) "
                "ON CONFLICT (tenant_id, user_id, request_id) DO NOTHING RETURNING request_id",
                (*_key(turn), turn.payload_hash),
            )).fetchone()
        if inserted is None:
            # Otra petición ganó mientras se comprobaba el presupuesto. Su reserva
            # ya está confirmada: no se mantiene ningún lock durante la llamada IA.
            row = await _lookup(turn)
            if row is None:
                raise ChatRequestConflict("No pude confirmar este envío. No se ejecutó de nuevo.")
            return _existing(turn, row)
    return turn


async def complete(turn: PreparedChat, response: dict) -> None:
    if turn.request_id is None:
        return
    async with pool.tenant_connection(turn.tenant_id) as conn:
        row = await (await conn.execute(
            "UPDATE assistant_chat_requests SET status = 'completed', response = %s::jsonb, "
            "updated_at = now() WHERE tenant_id = %s::uuid AND user_id = %s::uuid "
            "AND request_id = %s::uuid AND payload_hash = %s AND status = 'running' RETURNING request_id",
            (json.dumps(response, ensure_ascii=False), *_key(turn), turn.payload_hash),
        )).fetchone()
        if row is None:
            raise ChatRequestConflict("No pude confirmar el cierre de este envío. Revisa el historial.")


async def uncertain(turn: PreparedChat) -> None:
    if turn.request_id is None:
        return
    async with pool.tenant_connection(turn.tenant_id) as conn:
        await conn.execute(
            "UPDATE assistant_chat_requests SET status = 'uncertain', updated_at = now() "
            "WHERE tenant_id = %s::uuid AND user_id = %s::uuid AND request_id = %s::uuid "
            "AND payload_hash = %s AND status = 'running'",
            (*_key(turn), turn.payload_hash),
        )
