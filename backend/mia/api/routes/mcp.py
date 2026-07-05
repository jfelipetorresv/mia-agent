"""Mia · api.routes.mcp — conectar sistemas externos vía MCP, por despacho (CP-E6, Ola 5).

El despacho ve el catálogo de sistemas conectables, habilita los que use con sus
credenciales, y los deshabilita cuando quiera. Consent-first: todo nace apagado y solo
un acto humano explícito lo enciende. Las credenciales viven bajo el scope del despacho
(RLS); esta capa NUNCA devuelve el valor de un secreto, solo si está puesto o no.
"""
from __future__ import annotations

import logging

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel

from ...mcp import catalog as mcp_catalog
from ...mcp import service as mcp_service
from ...mcp.security import MCPConfigError
from ...mcp.service import MCPNotInCatalogError

router = APIRouter(prefix="/mcp", tags=["mcp"])
logger = logging.getLogger("mia.api.mcp")


def _tenant(request: Request) -> str:
    tid = getattr(request.state, "tenant_id", None)
    if not tid:
        raise HTTPException(status_code=401, detail="Sin sesión activa")
    return tid


class EnableBody(BaseModel):
    """Credenciales del despacho para el servidor. `env` = datos NO secretos (URLs);
    `secrets` = tokens de acceso. Solo se aceptan las claves que el catálogo declara."""
    env: dict[str, str] = {}
    secrets: dict[str, str] = {}


@router.get("/catalog")
async def get_catalog():
    """Catálogo curado de sistemas conectables (sin datos del despacho)."""
    return [{
        "slug": d.slug,
        "display_name": d.display_name,
        "description": d.description,
        "permissions_note": d.permissions_note,
        "fields": [{"env_var": s.env_var, "label": s.label,
                    "is_secret": s.is_secret, "required": s.required}
                   for s in d.env_specs],
    } for d in mcp_catalog.list_catalog()]


@router.get("/status")
async def get_status(request: Request):
    """Estado de cada servidor para el despacho: habilitado, configurado, qué falta."""
    tid = _tenant(request)
    try:
        return await mcp_service.mcp_status(tid)
    except Exception:  # noqa: BLE001 — §G: sin jerga al abogado
        logger.exception("mcp status falló (tenant=%s)", tid)
        raise HTTPException(
            status_code=502,
            detail="No pude leer los sistemas conectados en este momento. Intenta de nuevo.")


@router.post("/{slug}/enable")
async def enable(slug: str, body: EnableBody, request: Request):
    """Habilita un servidor con las credenciales del despacho (acto humano explícito)."""
    tid = _tenant(request)
    try:
        await mcp_service.enable_server(tid, slug, body.env, body.secrets)
        return await mcp_service.mcp_status(tid)
    except MCPNotInCatalogError:
        raise HTTPException(status_code=404, detail="Ese sistema no está disponible.")
    except MCPConfigError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except Exception:  # noqa: BLE001
        logger.exception("mcp enable falló (tenant=%s, slug=%s)", tid, slug)
        raise HTTPException(
            status_code=502,
            detail="No pude guardar la conexión en este momento. Intenta de nuevo.")


@router.post("/{slug}/disable")
async def disable(slug: str, request: Request):
    """Deshabilita un servidor (conserva las credenciales para reactivarlo luego)."""
    tid = _tenant(request)
    try:
        await mcp_service.disable_server(tid, slug)
        return await mcp_service.mcp_status(tid)
    except MCPNotInCatalogError:
        raise HTTPException(status_code=404, detail="Ese sistema no está disponible.")
    except Exception:  # noqa: BLE001
        logger.exception("mcp disable falló (tenant=%s, slug=%s)", tid, slug)
        raise HTTPException(
            status_code=502,
            detail="No pude actualizar la conexión en este momento. Intenta de nuevo.")


@router.post("/{slug}/forget")
async def forget(slug: str, request: Request):
    """Borra por completo la conexión y sus credenciales guardadas (acto explícito)."""
    tid = _tenant(request)
    try:
        await mcp_service.forget_server(tid, slug)
        return await mcp_service.mcp_status(tid)
    except MCPNotInCatalogError:
        raise HTTPException(status_code=404, detail="Ese sistema no está disponible.")
    except Exception:  # noqa: BLE001
        logger.exception("mcp forget falló (tenant=%s, slug=%s)", tid, slug)
        raise HTTPException(
            status_code=502,
            detail="No pude borrar la conexión en este momento. Intenta de nuevo.")
