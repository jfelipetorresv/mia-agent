"""Mia · gateway.hub_config — config del Agent Hub por tenant (1e · PASO 2).

Estado persistido en la tabla `tenant_settings` (decisión #12), bajo
`config->'agent_hub' = { "<agent_key>": true/false }`. DEFAULT: todos
DESHABILITADOS hasta que el tenant los active explícitamente desde el Dashboard.

Todas las operaciones pasan por `pool.tenant_connection` → RLS activo: un tenant
solo lee/escribe SU fila (fail-closed). `set_enabled` escribe con un MERGE jsonb
atómico (sin read-modify-write): ver su docstring.

OJO: habilitar aquí es condición NECESARIA pero NO suficiente para que se delegue. La
decisión completa vive en `gateway/hub_gate.py::delegation_allowed`, que además bloquea
del todo la política 'soberano'. Nadie debe llamar a `is_enabled` para decidir si saca
texto del equipo — para eso está el gate.
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
    """Habilita/deshabilita un conector para el tenant (upsert). Devuelve el mapa nuevo.

    MERGE jsonb ANIDADO y ATÓMICO, sin read-modify-write (mismo criterio que
    `settings.py::put_eval_consent` / `put_model_policy`). El `||` de afuera conserva TODAS
    las demás claves del config ('model_policy', 'allow_openrouter', 'eval'…) y el `||` de
    adentro conserva los demás ayudantes de 'agent_hub'.

    Por qué se cambió: el read-modify-write anterior leía el config ENTERO y lo reescribía
    entero. Dos escrituras concurrentes se pisaban — y no solo entre sí: activar un
    ayudante podía revertir un cambio simultáneo de `model_policy`, es decir, RESUCITAR una
    política de confidencialidad que el despacho acababa de endurecer. Con el merge, cada
    escritura solo toca su propia clave y el candado de `hub_gate` nunca lee una política
    zombi. `tenant_connection` (RLS) sigue garantizando que solo se toca la fila del tenant.
    """
    # `_AGENT_HUB_KEY` va interpolado, no parametrizado (mismo estilo que put_eval_consent
    # con 'eval'): es una CONSTANTE del módulo, jamás entrada del usuario. Además, como
    # parámetro, Postgres no puede inferir su tipo dentro de jsonb_build_object/`->`
    # (IndeterminateDatatype). El valor sí va parametrizado (Json), que es lo que importa.
    async with pool.tenant_connection(tenant_id) as conn:
        row = await (await conn.execute(
            "INSERT INTO tenant_settings (tenant_id, config) "
            f"VALUES (%s::uuid, jsonb_build_object('{_AGENT_HUB_KEY}', %s::jsonb)) "
            "ON CONFLICT (tenant_id) DO UPDATE SET "
            "config = COALESCE(tenant_settings.config, '{}'::jsonb) "
            f"         || jsonb_build_object('{_AGENT_HUB_KEY}', "
            f"              COALESCE(tenant_settings.config->'{_AGENT_HUB_KEY}', '{{}}'::jsonb) "
            f"              || (EXCLUDED.config->'{_AGENT_HUB_KEY}')), "
            "updated_at = now() "
            f"RETURNING config->'{_AGENT_HUB_KEY}'",
            (tenant_id, Json({agent_key: bool(enabled)})),
        )).fetchone()
    # Se devuelve lo que quedó EN LA DB (RETURNING), no lo que se pidió: es lo que el
    # candado va a leer después.
    return dict((row[0] if row else None) or {})
