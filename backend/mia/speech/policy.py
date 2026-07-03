"""Mia · speech.policy — candado de privacidad del audio (CP-Z1).

Regla de la Ola 3 (decisión de Pipe 2026-07-02): la voz es 100% LOCAL — el
audio del abogado jamás sale de la infraestructura del despacho. Este candado
lo hace estructural, no aspiracional:

  - `allow_cloud_audio` vive POR DESPACHO en tenant_settings.config['speech']
    y su default es False.
  - Lectura FAIL-CLOSED (patrón model_policy_for_strict de CP-P4): si la DB
    falla o el valor es ilegible, se asume False. Ante la duda, el audio NO
    puede ir a la nube.
  - El motor v1 (engine.ENGINE_IS_LOCAL) es local, así que hoy el candado nunca
    bloquea a nadie; existe para que un motor de nube FUTURO no pueda colarse:
    la ruta exige `ENGINE_IS_LOCAL or allow_cloud_audio(tenant)` SIEMPRE.
"""
from __future__ import annotations

import logging

from ..db import pool

logger = logging.getLogger(__name__)


async def allow_cloud_audio(tenant_id: str) -> bool:
    """¿El despacho autorizó explícitamente enviar audio a un motor de nube?

    Default False; SOLO el literal JSON `true` en config['speech']['allow_cloud_audio']
    lo enciende. Cualquier error de lectura → False (fail-closed)."""
    try:
        async with pool.tenant_connection(tenant_id) as conn:
            row = await (await conn.execute(
                "SELECT config->'speech'->'allow_cloud_audio' "
                "FROM tenant_settings WHERE tenant_id = %s::uuid",
                (tenant_id,),
            )).fetchone()
        return bool(row and row[0] is True)
    except Exception:  # noqa: BLE001 — fail-closed: sin certeza, no hay nube
        logger.exception(
            "speech: no se pudo leer allow_cloud_audio del tenant %s — se asume False",
            tenant_id,
        )
        return False
