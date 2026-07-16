"""Mia · connectors.notebooklm — consulta en vivo al NotebookLM del abogado (CP-NLM).

Punto de entrada ÚNICO. `consult_notebook` es la única forma en que una consulta a
NotebookLM (nube de Google) puede salir del sistema, y SIEMPRE pasa por el candado de
confidencialidad (`gate.query_allowed`) antes de tocar la red:

    gate (política ≠ soberano + opt-in) → notebook configurado → CLI → sello anti-inyección

La respuesta entra al agente como CONTEXTO EXTERNO SELLADO (no confiable), nunca como
fuente "respaldada" del corpus ni como documento `[doc n]`: informa el razonamiento pero
cualquier afirmación jurídica sigue exigiendo respaldo real y el gate de citas la marca
[VERIFICAR] si no lo tiene. (Espíritu de las apuestas NotebookLM: no confiar en sus citas.)
"""
from __future__ import annotations

import asyncio
import logging

from ...agents import untrusted
from ...db import pool
from . import client, gate

logger = logging.getLogger("mia.connectors.notebooklm")

# Rótulo del sello (§G: sin jerga técnica; deja claro que es material externo del abogado).
_SEAL_SOURCE = "NotebookLM del abogado (fuente externa · sin verificar)"


async def configured_notebook(tenant_id: str) -> str | None:
    """Id del notebook que el despacho eligió consultar, de
    `tenant_settings.config['notebooklm_notebook']`. None si no hay ninguno o error
    (fail-soft: sin notebook configurado no se consulta nada)."""
    try:
        async with pool.tenant_connection(tenant_id) as conn:
            row = await (await conn.execute(
                "SELECT config->>'notebooklm_notebook' FROM tenant_settings "
                "WHERE tenant_id = %s::uuid",
                (tenant_id,),
            )).fetchone()
        nb = str((row[0] if row else "") or "").strip()
        return nb or None
    except Exception:  # noqa: BLE001 — fail-soft: sin notebook, no se consulta
        logger.warning("notebooklm: no se pudo leer el notebook configurado del tenant %s",
                       tenant_id, exc_info=True)
        return None


async def consult_notebook(
    tenant_id: str, question: str, *, notebook_id: str | None = None,
    runner=None,
) -> str | None:
    """Consulta el NotebookLM del abogado y devuelve la respuesta YA SELLADA como contexto
    externo no confiable, o None si no se debe/puede consultar.

    Devuelve None (sin lanzar) cuando: el gate bloquea (soberano / sin opt-in / error de
    infraestructura), no hay notebook configurado, el CLI no está instalado, o la consulta
    falla. En todos esos casos el turno del abogado continúa con el corpus local — esto es
    un ENRIQUECIMIENTO opcional, nunca un punto de fallo.

    `notebook_id` permite forzar un notebook (tests / usos futuros); por defecto usa el
    configurado por el despacho. `runner` se inyecta en tests (mock del subprocess)."""
    q = str(question or "").strip()
    if not q:
        return None

    allowed, reason = await gate.query_allowed(tenant_id)
    if not allowed:
        logger.info("notebooklm: consulta NO autorizada (tenant=%s, motivo=%s)",
                    tenant_id, reason)
        return None

    nb = (notebook_id or "").strip() or await configured_notebook(tenant_id)
    if not nb:
        logger.info("notebooklm: sin notebook configurado (tenant=%s)", tenant_id)
        return None

    # El CLI es sincrónico (subprocess) → a un hilo para no bloquear el loop.
    raw = await asyncio.to_thread(client.ask, nb, q, runner=runner)
    if not raw:
        return None

    # CP-S1: sello ÚNICO aquí (el cliente devuelve crudo). La respuesta de NotebookLM es
    # contenido externo → "datos, no órdenes", con los `<<<` embebidos neutralizados.
    return untrusted.wrap_untrusted(_SEAL_SOURCE, raw)
