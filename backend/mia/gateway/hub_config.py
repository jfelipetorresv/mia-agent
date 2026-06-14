"""Mia · gateway.hub_config — config del Agent Hub por tenant (1e · PASO 2).

Estado persistido en la tabla `tenant_settings` (decisión #12), bajo
`config->'agent_hub' = { "<agent_key>": true/false }`. DEFAULT: todos
DESHABILITADOS hasta que el tenant los active explícitamente desde el Dashboard.

Todas las operaciones pasan por `pool.tenant_connection` → RLS activo: un tenant
solo lee/escribe SU fila (fail-closed). El read-modify-write de `set_enabled` corre
dentro de UNA transacción (tenant_connection abre transacción).
"""
from __future__ import annotations

from psycopg.types.json import Json

from ..db import pool

_AGENT_HUB_KEY = "agent_hub"


async def get_hub_config(tenant_id: str) -> dict:
    """Mapa {agent_key: bool} del tenant ({} si no hay fila ni config)."""
    async with pool.tenant_connection(tenant_id) as conn:
        row = await (await conn.execute(
            "SELECT config FROM tenant_settings WHERE tenant_id = %s::uuid", (tenant_id,)
        )).fetchone()
    config = (row[0] if row else None) or {}
    return dict(config.get(_AGENT_HUB_KEY) or {})


async def is_enabled(tenant_id: str, agent_key: str) -> bool:
    """True si el tenant habilitó ese conector. Default: False."""
    return bool((await get_hub_config(tenant_id)).get(agent_key, False))


async def set_enabled(tenant_id: str, agent_key: str, enabled: bool) -> dict:
    """Habilita/deshabilita un conector para el tenant (upsert). Devuelve el mapa nuevo."""
    async with pool.tenant_connection(tenant_id) as conn:
        row = await (await conn.execute(
            "SELECT config FROM tenant_settings WHERE tenant_id = %s::uuid", (tenant_id,)
        )).fetchone()
        config = (row[0] if row else None) or {}
        hub = dict(config.get(_AGENT_HUB_KEY) or {})
        hub[agent_key] = bool(enabled)
        config[_AGENT_HUB_KEY] = hub
        await conn.execute(
            "INSERT INTO tenant_settings (tenant_id, config) VALUES (%s::uuid, %s) "
            "ON CONFLICT (tenant_id) DO UPDATE SET config = EXCLUDED.config, updated_at = now()",
            (tenant_id, Json(config)),
        )
    return hub
