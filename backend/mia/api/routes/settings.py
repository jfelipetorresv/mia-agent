"""Mia · api.routes.settings — ajustes del Agent Hub por tenant (1e · PASO 3).

GET  /settings/agents                  → estado de cada conector para el tenant
POST /settings/agents/{agent_id}/enable
POST /settings/agents/{agent_id}/disable

§G: el abogado ve solo nombres en español ("Asistente de investigación jurídica",
"Editor de documentos"…) y un id neutro (slug); NUNCA la marca del CLI. El estado
persiste por tenant en `tenant_settings` bajo RLS (decisión #12).
"""
from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request

from ...gateway import hub_config
from ...gateway.agent_hub import CONNECTORS, AgentHub, slug_to_key

router = APIRouter(tags=["settings"])
_hub = AgentHub()


def _tenant(request: Request) -> str:
    t = getattr(request.state, "tenant_id", None)
    if not t:
        raise HTTPException(status_code=401, detail="Sin contexto de tenant")
    return t


@router.get("/settings/agents")
async def list_agents(request: Request):
    """Lista los conectores con su estado para el tenant. Solo español, sin marcas."""
    tenant_id = _tenant(request)
    available = _hub.list_available()
    enabled_map = await hub_config.get_hub_config(tenant_id)
    agentes = [
        {
            "id": info["slug"],                 # id público neutro (sin marca)
            "nombre": info["display_name"],     # español (§G)
            "instalado": info["installed"],
            "habilitado": bool(enabled_map.get(key, False)),
        }
        for key, info in available.items()
    ]
    return {"agentes": agentes}


async def _set(request: Request, agent_id: str, enabled: bool):
    tenant_id = _tenant(request)
    key = slug_to_key(agent_id) or (agent_id if agent_id in CONNECTORS else None)
    if key is None:
        raise HTTPException(status_code=404, detail="Asistente no encontrado")
    await hub_config.set_enabled(tenant_id, key, enabled)
    c = CONNECTORS[key]
    return {"id": c.slug, "nombre": c.display_name, "habilitado": enabled}


@router.post("/settings/agents/{agent_id}/enable")
async def enable_agent(agent_id: str, request: Request):
    return await _set(request, agent_id, True)


@router.post("/settings/agents/{agent_id}/disable")
async def disable_agent(agent_id: str, request: Request):
    return await _set(request, agent_id, False)
