"""Mia · gateway.hub_memory — memoria del "no me preguntes más" (CP-HUB2).

Cuando Mia PROPONE un ayudante externo por su cuenta, el abogado puede decir "no me
preguntes más por este ayudante en este asunto". Esa autorización vive aquí, en la tabla
`matter_agent_consent` (migración 037), con clave **(asunto, ayudante)** — nunca global.

Todo pasa por `pool.tenant_connection` → RLS activo: un despacho solo ve sus filas
(fail-closed; sin el GUC `app.tenant_id` la tabla devuelve 0 filas).

LO QUE ESTA MEMORIA **NO** ES — el punto que no se puede perder de vista:
No es un permiso. Recordar SOLO suprime la PREGUNTA; NO autoriza a sacar nada del equipo.
El candado (`hub_gate.delegation_allowed`: política ≠ 'soberano' + opt-in del despacho) se
evalúa SIEMPRE, en cada turno, ANTES de proponer y OTRA VEZ antes de invocar. Por eso el
orden de llamada en el grafo es candado → memoria, y nunca al revés: si un día alguien
invierte ese orden, una fila vieja de esta tabla se convertiría en una puerta abierta.

MODO DE FALLO: `remembered` es fail-closed hacia **PREGUNTAR** (devuelve False ante
cualquier error). Preguntar de más es una molestia; delegar sin preguntar por un hipo de la
DB es sacar texto del equipo sin consentimiento. Ante la duda, se pregunta.
"""
from __future__ import annotations

import logging

from ..db import pool

logger = logging.getLogger("mia.gateway.hub_memory")


async def remembered(tenant_id: str, matter_id: str, agent_key: str) -> bool:
    """True si el abogado dijo "no me preguntes más" por ESTE ayudante en ESTE asunto.

    Fail-closed hacia preguntar: cualquier error (DB, id mal formado) → False."""
    try:
        async with pool.tenant_connection(tenant_id) as conn:
            row = await (await conn.execute(
                "SELECT 1 FROM matter_agent_consent "
                "WHERE matter_id = %s::uuid AND agent_key = %s",
                (matter_id, agent_key),
            )).fetchone()
        return row is not None
    except Exception:  # noqa: BLE001 — no poder leer la memoria significa PREGUNTAR
        logger.warning("hub_memory: no se pudo leer la memoria (tenant=%s matter=%s "
                       "agent=%s) → se preguntará", tenant_id, matter_id, agent_key,
                       exc_info=True)
        return False


async def remember(tenant_id: str, matter_id: str, agent_key: str) -> None:
    """Guarda "no me preguntes más" para (asunto, ayudante). Idempotente.

    NUNCA lanza: la delegación que el abogado ACABA de aprobar no puede caerse porque no se
    haya podido guardar su preferencia. El costo de fallar aquí es que la próxima vez se le
    vuelva a preguntar — el lado seguro."""
    try:
        async with pool.tenant_connection(tenant_id) as conn:
            await conn.execute(
                "INSERT INTO matter_agent_consent (tenant_id, matter_id, agent_key) "
                "VALUES (%s::uuid, %s::uuid, %s) ON CONFLICT DO NOTHING",
                (tenant_id, matter_id, agent_key),
            )
    except Exception:  # noqa: BLE001
        logger.warning("hub_memory: no se pudo guardar la memoria (tenant=%s matter=%s "
                       "agent=%s); se volverá a preguntar", tenant_id, matter_id, agent_key,
                       exc_info=True)


async def forget(tenant_id: str, matter_id: str, agent_key: str) -> bool:
    """Revoca la memoria de (asunto, ayudante). True si había algo que borrar.

    Al revocar, el estado vuelve al DEFECTO seguro: Mia pregunta otra vez. No desactiva el
    ayudante (eso es el opt-in del despacho, `hub_config`) ni cambia la política."""
    async with pool.tenant_connection(tenant_id) as conn:
        cur = await conn.execute(
            "DELETE FROM matter_agent_consent "
            "WHERE matter_id = %s::uuid AND agent_key = %s",
            (matter_id, agent_key),
        )
    return bool(cur.rowcount)


async def list_for_matter(tenant_id: str, matter_id: str) -> list[str]:
    """Claves de los ayudantes con "no me preguntes más" en ESTE asunto (para la UI)."""
    async with pool.tenant_connection(tenant_id) as conn:
        rows = await (await conn.execute(
            "SELECT agent_key FROM matter_agent_consent "
            "WHERE matter_id = %s::uuid ORDER BY agent_key",
            (matter_id,),
        )).fetchall()
    return [r[0] for r in rows]
