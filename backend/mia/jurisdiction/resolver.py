"""Mia · jurisdiction.resolver — jurisdicción(es) activa(s) de un tenant.

Lee `tenant_settings.config['jurisdictions']` (lista de códigos de pack, p. ej. ["co"]).
Un tenant puede ejercer en varias (Bogotá + arbitraje en Panamá). Sin configuración →
["generic"] (modo genérico). Es la fuente del routing jurisdiccional para el SAT-Graph,
el calendario, el chunker y el PII redactor.
"""
from __future__ import annotations

from ..db import pool
from .pack import GENERIC_CODE


async def resolve_jurisdictions(tenant_id: str) -> list[str]:
    """Códigos de jurisdicción activos del tenant. Fallback ['generic'] si no hay config."""
    async with pool.tenant_connection(tenant_id) as conn:
        cur = await conn.execute(
            "SELECT config->'jurisdictions' FROM tenant_settings WHERE tenant_id = %s::uuid",
            (str(tenant_id),),
        )
        row = await cur.fetchone()

    vals = row[0] if row and row[0] else None
    if not vals:
        return [GENERIC_CODE]
    codes = [str(v).strip().lower() for v in vals if str(v).strip()]
    return codes or [GENERIC_CODE]
