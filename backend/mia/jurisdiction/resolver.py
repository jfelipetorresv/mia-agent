"""Mia · jurisdiction.resolver — jurisdicción(es) activa(s) de un tenant.

Lee `tenant_settings.config['jurisdictions']` (lista de códigos de pack, p. ej. ["co"]).
Un tenant puede ejercer en varias (Bogotá + arbitraje en Panamá). Sin configuración →
["generic"] (modo genérico). Es la fuente del routing jurisdiccional para el SAT-Graph,
el calendario, el chunker y el PII redactor.
"""
from __future__ import annotations

from ..db import pool
from .pack import GENERIC_CODE


def _codes(values: object) -> list[str]:
    """Normaliza una lista JSON sin adivinar códigos. Vacío conserva el fallback seguro."""
    if not isinstance(values, list):
        return []
    seen: set[str] = set()
    out: list[str] = []
    for value in values:
        code = str(value).strip().lower()
        if code and code not in seen:
            seen.add(code)
            out.append(code)
    return out


async def resolve_jurisdictions(tenant_id: str, matter_id: str | None = None) -> list[str]:
    """Jurisdicciones activas con precedencia asunto → firma u organización → genérico.

    `matters.jurisdictions=[]` es la migración compatible: el asunto hereda el perfil de la
    organización. Una lista no vacía es el contexto seleccionado para ESE asunto y gobierna
    todo el turno. La lectura sigue bajo RLS, por lo que un asunto ajeno o inexistente no puede
    aportar una jurisdicción.
    """
    async with pool.tenant_connection(tenant_id) as conn:
        if matter_id:
            cur = await conn.execute(
                "SELECT jurisdictions FROM matters WHERE id = %s::uuid", (str(matter_id),)
            )
            row = await cur.fetchone()
            matter_codes = _codes(row[0] if row else None)
            if matter_codes:
                return matter_codes
        cur = await conn.execute(
            "SELECT config->'jurisdictions' FROM tenant_settings WHERE tenant_id = %s::uuid",
            (str(tenant_id),),
        )
        row = await cur.fetchone()

    codes = _codes(row[0] if row else None)
    return codes or [GENERIC_CODE]
