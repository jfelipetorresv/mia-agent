"""Mia · mcp.service — estado y resolución SEGURA de servidores MCP por despacho (CP-E6).

La config de MCP de cada despacho vive en ``tenant_settings.config['mcp']['servers']``
(jsonb, bajo RLS — sin migración, igual que la política de CP-E1 y el correo de CP-P3):

    config['mcp']['servers'][slug] = {
        "enabled": bool,
        "env":     {ENV_VAR: valor},      # variables NO secretas (URLs base, rutas)
        "secrets": {clave: valor},        # secretos del despacho (tokens de acceso)
    }

`resolve_server` es el corazón fail-closed: toma esa fila, resuelve los placeholders
``${clave}`` bajo el scope de secretos del tenant (CP-S2), sanea el entorno del
subproceso (CP-S3) y valida la forma del comando (exfiltración) ANTES de entregar un
spec listo para lanzar. El lanzamiento en vivo (cliente JSON-RPC) es el paso de
activación posterior; esta capa deja todo verificado y seguro.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass

from ..security import get_tenant_secret, tenant_secret_scope
from . import catalog
from .security import (
    MCPConfigError,
    MCPSecurityError,
    build_safe_env,
    find_unresolved_placeholders,
    interpolate_placeholders,
    validate_server_entry,
)

logger = logging.getLogger("mia.mcp.service")


class MCPNotInCatalogError(ValueError):
    """Se pidió un servidor que no está en el catálogo curado."""


@dataclass(frozen=True)
class ResolvedMCPServer:
    """Spec de un servidor MCP listo para lanzar: comando + args + entorno SANEADO
    (allowlist del SO + solo las variables declaradas, ya resueltas). Sin secretos
    de la instalación; sin placeholders colgando."""
    slug: str
    command: str
    args: list[str]
    env: dict[str, str]


# ── lectura de la config del despacho (RLS) ──────────────────────────────────
async def _load_servers(tenant_id: str) -> dict:
    """`config['mcp']['servers']` del despacho (dict vacío si no hay), bajo RLS."""
    from ..db import pool

    async with pool.tenant_connection(tenant_id) as conn:
        row = await (await conn.execute(
            "SELECT config->'mcp'->'servers' FROM tenant_settings "
            "WHERE tenant_id = %s::uuid",
            (tenant_id,),
        )).fetchone()
    if not row or row[0] is None:
        return {}
    servers = row[0]
    return servers if isinstance(servers, dict) else {}


async def _write_server(tenant_id: str, slug: str, entry: dict) -> None:
    """Upsert de una entrada de servidor, fusionando sin pisar otras (RLS).

    Se fija el objeto ``mcp`` ENTERO (path '{mcp}', cuyo padre es la raíz y siempre
    existe → create_missing sí crea 'mcp'): fusiona (||) sobre el 'mcp' previo y,
    dentro, sobre 'servers' previo. Mismo cuidado que el hallazgo capa-2 de CP-E1
    (jsonb_set no crea objetos intermedios ausentes y todo tenant nace con '{}')."""
    import json

    from ..db import pool

    payload = json.dumps({slug: entry})
    async with pool.tenant_connection(tenant_id) as conn:
        await conn.execute(
            "INSERT INTO tenant_settings (tenant_id, config) "
            "VALUES (%s::uuid, jsonb_build_object('mcp', jsonb_build_object("
            "  'servers', %s::jsonb))) "
            "ON CONFLICT (tenant_id) DO UPDATE SET config = jsonb_set("
            "  COALESCE(tenant_settings.config, '{}'::jsonb), '{mcp}', "
            "  COALESCE(tenant_settings.config->'mcp', '{}'::jsonb) "
            "  || jsonb_build_object('servers', "
            "     COALESCE(tenant_settings.config->'mcp'->'servers', '{}'::jsonb) "
            "     || %s::jsonb), true)",
            (tenant_id, payload, payload),
        )


# ── estado para la pantalla (nunca filtra valores de secretos) ───────────────
async def mcp_status(tenant_id: str) -> list[dict]:
    """Estado de cada servidor del catálogo para el despacho: habilitado, si está
    configurado (todos los secretos requeridos presentes) y qué falta. NUNCA incluye
    el valor de un secreto — solo si está o no puesto."""
    servers = await _load_servers(tenant_id)
    out: list[dict] = []
    for desc in catalog.list_catalog():
        saved = servers.get(desc.slug) or {}
        secrets = saved.get("secrets") or {}
        env = saved.get("env") or {}
        missing = [s.label for s in desc.env_specs if s.required and (
            (s.is_secret and not (secrets.get(s.secret_key)))
            or (not s.is_secret and not (env.get(s.env_var))))]
        out.append({
            "slug": desc.slug,
            "display_name": desc.display_name,
            "description": desc.description,
            "permissions_note": desc.permissions_note,
            "fields": [{"env_var": s.env_var, "label": s.label,
                        "is_secret": s.is_secret, "required": s.required}
                       for s in desc.env_specs],
            "enabled": bool(saved.get("enabled")),
            "configured": not missing,
            "missing": missing,
        })
    return out


# ── habilitar / deshabilitar (consent-first, acto humano explícito) ──────────
async def enable_server(tenant_id: str, slug: str, env: dict, secrets: dict) -> None:
    """Habilita un servidor con las credenciales del despacho. Valida contra el
    catálogo (claves declaradas, requeridas presentes) antes de guardar. Fail-closed:
    si falta un secreto requerido, NO se habilita."""
    desc = catalog.get_descriptor(slug)
    if desc is None:
        raise MCPNotInCatalogError(f"El servidor '{slug}' no está en el catálogo.")

    allowed_secret = set(desc.secret_keys())
    allowed_env = set(desc.plain_env_keys())
    clean_secrets = {k: str(v) for k, v in (secrets or {}).items()
                     if k in allowed_secret and str(v).strip()}
    clean_env = {k: str(v) for k, v in (env or {}).items()
                 if k in allowed_env and str(v).strip()}

    missing = [s.label for s in desc.env_specs if s.required and (
        (s.is_secret and s.secret_key not in clean_secrets)
        or (not s.is_secret and s.env_var not in clean_env))]
    if missing:
        raise MCPConfigError(
            "Faltan datos para conectar este sistema: " + "; ".join(missing) + ".")

    await _write_server(tenant_id, slug,
                        {"enabled": True, "env": clean_env, "secrets": clean_secrets})
    logger.info("Servidor MCP '%s' habilitado (tenant=%s)", slug, tenant_id)


async def disable_server(tenant_id: str, slug: str) -> None:
    """Deshabilita un servidor. Conserva las credenciales guardadas (volver a
    habilitarlo no exige re-teclearlas); para borrarlas por completo, usa `forget_server`.

    Baja el flag `enabled` con un jsonb_set DIRIGIDO al path (create_missing=false, sin
    releer): atómico y sin ventana de carrera (hallazgo capa 2 menor). Si el servidor
    nunca se configuró, el path no existe y es un no-op inofensivo."""
    if catalog.get_descriptor(slug) is None:
        raise MCPNotInCatalogError(f"El servidor '{slug}' no está en el catálogo.")
    from ..db import pool

    async with pool.tenant_connection(tenant_id) as conn:
        await conn.execute(
            "UPDATE tenant_settings "
            "SET config = jsonb_set(config, %s::text[], 'false'::jsonb, false) "
            "WHERE tenant_id = %s::uuid",
            (["mcp", "servers", slug, "enabled"], tenant_id))
    logger.info("Servidor MCP '%s' deshabilitado (tenant=%s)", slug, tenant_id)


async def forget_server(tenant_id: str, slug: str) -> None:
    """Borra POR COMPLETO la configuración de un servidor del despacho (incluidas sus
    credenciales). Para cuando el despacho revoca un token en el sistema externo y no
    quiere que Mia lo conserve. Atómico (operador `#-` sobre el path); no-op si no había."""
    if catalog.get_descriptor(slug) is None:
        raise MCPNotInCatalogError(f"El servidor '{slug}' no está en el catálogo.")
    from ..db import pool

    async with pool.tenant_connection(tenant_id) as conn:
        await conn.execute(
            "UPDATE tenant_settings SET config = config #- %s::text[] "
            "WHERE tenant_id = %s::uuid",
            (["mcp", "servers", slug], tenant_id))
    logger.info("Servidor MCP '%s' olvidado (credenciales borradas) (tenant=%s)", slug, tenant_id)


# ── resolución fail-closed (el corazón de seguridad) ─────────────────────────
async def resolve_server(tenant_id: str, slug: str) -> ResolvedMCPServer:
    """Spec seguro y listo para lanzar de un servidor HABILITADO, o excepción.

    Pipeline fail-closed:
      1. El servidor debe estar en el catálogo y HABILITADO para el despacho.
      2. Los ``${clave}`` se resuelven BAJO el scope de secretos del tenant (CP-S2):
         cada valor sale de la clave que ESE despacho configuró, jamás del entorno.
      3. Un placeholder requerido sin resolver ABORTA (MCPConfigError) — no se lanza
         un servidor con un secreto colgando.
      4. La forma del comando se valida contra exfiltración (MCPSecurityError).
      5. El entorno se SANEA (CP-S3): allowlist del SO + solo lo declarado."""
    desc = catalog.get_descriptor(slug)
    if desc is None:
        raise MCPNotInCatalogError(f"El servidor '{slug}' no está en el catálogo.")

    servers = await _load_servers(tenant_id)
    saved = servers.get(slug) or {}
    if not saved.get("enabled"):
        raise MCPConfigError(f"El servidor '{desc.display_name}' no está habilitado.")

    stored_secrets = {k: v for k, v in (saved.get("secrets") or {}).items() if v}
    stored_env = {k: v for k, v in (saved.get("env") or {}).items()
                  if k in set(desc.plain_env_keys()) and v}

    # Un resolver ÚNICO para TODO ${placeholder} — en el entorno, el comando y los
    # args (hallazgo capa 2 BLOQUEANTE: antes solo se interpolaba el entorno, así que
    # un ${DMS_ROOT} en los args quedaba literal y NO lo detectaba el chequeo de
    # colgantes). Prioridad: secreto del scope del tenant (fail-closed, prefijo por
    # slug → sin colisiones), luego la variable NO secreta que el despacho configuró.
    scoped = {f"mcp:{slug}:{k}": str(v) for k, v in stored_secrets.items()}
    with tenant_secret_scope(tenant_id, scoped):
        def _resolve(name: str):
            secret = get_tenant_secret(f"mcp:{slug}:{name}")
            if secret is not None:
                return secret
            return stored_env.get(name)

        resolved_secret_env = interpolate_placeholders(dict(desc.env_template), _resolve)
        resolved_command = interpolate_placeholders(desc.command, _resolve)
        resolved_args = interpolate_placeholders(list(desc.args), _resolve)

    merged_env = {**stored_env, **resolved_secret_env}

    # Fail-closed sobre TODA la superficie de lanzamiento: entorno + comando + args.
    if find_unresolved_placeholders([resolved_command, resolved_args, merged_env]):
        # No revelamos cuáles: solo que falta configurar (§G, sin fugas).
        raise MCPConfigError(
            f"Faltan datos para conectar '{desc.display_name}'. Complétalos antes de usarlo.")

    entry = {"command": resolved_command, "args": resolved_args}
    issues = validate_server_entry(slug, entry)
    if issues:
        logger.warning("Config de MCP '%s' rechazada por forma peligrosa: %s", slug, issues)
        raise MCPSecurityError(
            f"La configuración de '{desc.display_name}' tiene una forma no permitida.")

    safe_env = build_safe_env(merged_env)
    return ResolvedMCPServer(slug=slug, command=resolved_command,
                             args=list(resolved_args), env=safe_env)
