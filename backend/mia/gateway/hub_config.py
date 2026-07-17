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

import logging

from psycopg.types.json import Json

from ..db import pool

logger = logging.getLogger("mia.gateway.hub_config")

_AGENT_HUB_KEY = "agent_hub"

# ── CP-HUB2 · los tres modos de iniciativa ───────────────────────────────────────
# Guardados en `tenant_settings.config->>'delegation_mode'`. Deciden CUÁNDO Mia puede
# tomar la iniciativa de usar un ayudante externo — NUNCA si le está permitido (eso es
# `hub_gate`, que corre igual en los tres modos y manda sobre todos ellos).
#
#   MODE_ASK  · "pregúntame" (DEFECTO — la decisión de Pipe). Mia determina por su cuenta
#               que necesita un ayudante y lo PROPONE; el abogado ve qué ayudante y el
#               texto exacto que va a salir, y aprueba de un clic. Nada sale antes.
#   MODE_AUTO · "autónomo". Mia delega sin preguntar (sigue pasando por el candado y la
#               salida sigue sellada; el aviso del turno le dice al abogado que salió).
#   MODE_ONLY_EXPLICIT · "solo si lo pido". Sin propuestas: solo delega cuando el abogado
#               NOMBRA al ayudante en su mensaje. Es el comportamiento previo a CP-HUB2.
#
# La invocación explícita funciona IGUAL en los tres: si el abogado lo acaba de ordenar,
# preguntarle "¿confirmas?" sería una pausa de más sobre algo que él mismo pidió.
MODE_ASK = "preguntar"
MODE_AUTO = "autonomo"
MODE_ONLY_EXPLICIT = "solo_si_lo_pido"
VALID_DELEGATION_MODES = (MODE_ASK, MODE_AUTO, MODE_ONLY_EXPLICIT)

DEFAULT_DELEGATION_MODE = MODE_ASK
_DELEGATION_MODE_KEY = "delegation_mode"


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


async def get_delegation_mode(tenant_id: str) -> str:
    """Modo de iniciativa del despacho. Defecto: MODE_ASK ("pregúntame", decisión de Pipe).

    Un valor desconocido en la DB (config editada a mano, versión futura) NO se respeta: se
    degrada a MODE_ONLY_EXPLICIT — el modo sin iniciativa. Igual ante un error de lectura.
    El criterio es el de siempre: si no se puede determinar con certeza qué autonomía
    concedió el despacho, Mia no se la concede sola. Nótese que el peor caso de este
    fail-closed es una molestia (Mia no propone), nunca una fuga: aunque cayera al modo más
    permisivo, `hub_gate` seguiría siendo quien decide si sale un byte."""
    try:
        async with pool.tenant_connection(tenant_id) as conn:
            row = await (await conn.execute(
                "SELECT config->>%s FROM tenant_settings WHERE tenant_id = %s::uuid",
                (_DELEGATION_MODE_KEY, tenant_id),
            )).fetchone()
    except Exception:  # noqa: BLE001 — sin certeza, sin iniciativa
        logger.warning("hub_config: no se pudo leer el modo de delegación (tenant=%s) → "
                       "sin iniciativa", tenant_id, exc_info=True)
        return MODE_ONLY_EXPLICIT
    mode = row[0] if row else None
    if mode is None:
        return DEFAULT_DELEGATION_MODE  # nunca configurado → el defecto del producto
    if mode not in VALID_DELEGATION_MODES:
        logger.warning("hub_config: modo de delegación desconocido %r (tenant=%s) → "
                       "sin iniciativa", mode, tenant_id)
        return MODE_ONLY_EXPLICIT
    return mode


async def set_delegation_mode(tenant_id: str, mode: str) -> str:
    """Fija el modo de iniciativa del despacho. Devuelve el que quedó EN LA DB.

    Mismo MERGE jsonb atómico que `set_enabled`: escribir el modo no puede pisar
    'model_policy' ni 'agent_hub' (ver el porqué en el docstring de set_enabled)."""
    if mode not in VALID_DELEGATION_MODES:
        raise ValueError(f"modo de delegación inválido: {mode!r}")
    async with pool.tenant_connection(tenant_id) as conn:
        row = await (await conn.execute(
            "INSERT INTO tenant_settings (tenant_id, config) "
            f"VALUES (%s::uuid, jsonb_build_object('{_DELEGATION_MODE_KEY}', %s::jsonb)) "
            "ON CONFLICT (tenant_id) DO UPDATE SET "
            "config = COALESCE(tenant_settings.config, '{}'::jsonb) "
            f"         || jsonb_build_object('{_DELEGATION_MODE_KEY}', "
            f"              EXCLUDED.config->'{_DELEGATION_MODE_KEY}'), "
            "updated_at = now() "
            f"RETURNING config->>'{_DELEGATION_MODE_KEY}'",
            (tenant_id, Json(mode)),
        )).fetchone()
    return str(row[0]) if row and row[0] else DEFAULT_DELEGATION_MODE


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
