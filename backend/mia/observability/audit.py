"""Mia · observability.audit — el sink de auditoría (CP-E1, Ola 5).

Un ÚNICO helper `record()` que persiste una acción en `audit_logs` (append-only,
RLS por tenant, migración 011). Es READ-ONLY sobre el flujo: observa, no controla
— y por eso es FAIL-OPEN: una auditoría JAMÁS puede romper ni frenar la acción que
observa (patrón del observer de Hermes). Si la DB falla, se loguea y se sigue.

Antes de CP-E1 solo el curador (memory/curator.py) escribía en audit_logs, con su
propio helper. Ahora ese helper y el middleware HTTP comparten ESTE sink, para que
haya un rastro uniforme de las acciones del despacho (cumplimiento).
"""
from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger("mia.observability.audit")

# Topes de las columnas de audit_logs (migración 011) — se recortan aquí para que
# un valor largo nunca haga fallar el INSERT (fail-open también ante datos sucios).
_ACTION_MAX = 60
_ENTITY_TYPE_MAX = 60
_ENTITY_ID_MAX = 200
_USER_MAX = 200

_INSERT_SQL = (
    "INSERT INTO audit_logs (tenant_id, user_email, action, entity_type, entity_id, payload) "
    "VALUES (%(tenant_id)s::uuid, %(user_email)s, %(action)s, %(entity_type)s, "
    "%(entity_id)s, %(payload)s::jsonb)"
)


def _clip(value: Any, limit: int) -> str | None:
    if value is None:
        return None
    s = str(value)
    return s[:limit] if s else None


def _build_row(action, tenant_id, user_email, entity_type, entity_id, payload) -> dict:
    import json

    return {
        "tenant_id": str(tenant_id),
        "user_email": _clip(user_email, _USER_MAX),
        "action": _clip(action, _ACTION_MAX) or "accion",
        "entity_type": _clip(entity_type, _ENTITY_TYPE_MAX),
        "entity_id": _clip(entity_id, _ENTITY_ID_MAX),
        "payload": json.dumps(payload or {}, ensure_ascii=False, default=str),
    }


async def record_on_conn(
    conn,
    action: str,
    *,
    tenant_id: str,
    user_email: str | None = None,
    entity_type: str | None = None,
    entity_id: str | None = None,
    payload: dict | None = None,
) -> None:
    """Escribe la auditoría en una CONEXIÓN ya abierta (transaccional). Para
    llamadores que auditan DENTRO de su propia transacción (p. ej. el curador al
    aplicar una propuesta): así el registro es atómico con la acción. NO es
    fail-open — si el INSERT falla, el llamador decide (típicamente rollback)."""
    await conn.execute(
        _INSERT_SQL,
        _build_row(action, tenant_id, user_email, entity_type, entity_id, payload),
    )


async def record(
    action: str,
    *,
    tenant_id: str | None,
    user_email: str | None = None,
    entity_type: str | None = None,
    entity_id: str | None = None,
    payload: dict | None = None,
) -> None:
    """Registra UNA acción en audit_logs bajo el RLS del tenant. FAIL-OPEN: nunca
    lanza — un fallo de auditoría no puede tumbar la acción observada. Sin
    `tenant_id` (p. ej. una acción pre-login) es un no-op silencioso."""
    if not tenant_id:
        return
    try:
        from ..db import pool  # import diferido: no exigir DB para importar el módulo

        row = _build_row(action, tenant_id, user_email, entity_type, entity_id, payload)
        async with pool.tenant_connection(tenant_id) as conn:
            await conn.execute(_INSERT_SQL, row)
    except Exception:  # noqa: BLE001 — la auditoría es observador: nunca rompe el flujo
        logger.exception("audit.record falló (action=%s tenant=%s) — se ignora", action,
                         tenant_id)
