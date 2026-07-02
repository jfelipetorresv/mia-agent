"""Mia · api.routes.settings — ajustes del Agent Hub por tenant (1e · PASO 3).

GET  /settings/agents                  → estado de cada conector para el tenant
POST /settings/agents/{agent_id}/enable
POST /settings/agents/{agent_id}/disable
GET  /settings/model-policy            → política de modelo efectiva + opciones (CP2)
PUT  /settings/model-policy            → valida y persiste la política del tenant (CP2)

§G: el abogado ve solo nombres en español ("Asistente de investigación jurídica",
"Editor de documentos"…) y un id neutro (slug); NUNCA la marca del CLI. El estado
persiste por tenant en `tenant_settings` bajo RLS (decisión #12).
"""
from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request
from psycopg.types.json import Json

from ...agent import llm
from ...db import pool
from ...gateway import hub_config
from ...gateway.agent_hub import CONNECTORS, AgentHub, slug_to_key
from ..middleware import invalidate_policy_cache

router = APIRouter(tags=["settings"])
_hub = AgentHub()

# §G: etiquetas SIN jerga técnica — el abogado nunca ve "CLI", "API" ni "Ollama".
_POLICY_LABELS: dict[str, str] = {
    "suscripcion": "Mi suscripción (recomendado)",
    "nube": "Nube",
    "soberano": "Todo en mi equipo",
}


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


# ── CP2 · política de modelo por tenant (decisión #27) ──────────────────────────
def _policy_options() -> list[dict]:
    return [{"id": k, "nombre": v} for k, v in _POLICY_LABELS.items()]


@router.get("/settings/model-policy")
async def get_model_policy(request: Request):
    """Política efectiva del tenant + las 3 opciones (etiquetas en español, sin jerga)."""
    tenant_id = _tenant(request)
    policy = await llm.model_policy_for(tenant_id)
    return {
        "politica": policy,
        "nombre": _POLICY_LABELS[policy],
        "opciones": _policy_options(),
    }


@router.put("/settings/model-policy")
async def put_model_policy(request: Request):
    """Valida y persiste la política en tenant_settings.config['model_policy'] con un
    MERGE jsonb atómico (config || {"model_policy": …}): solo toca esa clave, sin
    read-modify-write que pise cambios concurrentes de otros settings (revisión CP2).
    Invalida el caché del middleware: aplica de inmediato."""
    tenant_id = _tenant(request)
    try:
        body = await request.json()
    except Exception:  # noqa: BLE001 — cuerpo no-JSON → 422 uniforme
        body = None
    raw = (body or {}).get("politica") if isinstance(body, dict) else None
    policy = str(raw or "").strip().lower()
    if policy not in _POLICY_LABELS:
        raise HTTPException(
            status_code=422,
            detail="Opción no válida. Usa 'suscripcion', 'nube' o 'soberano'.",
        )
    async with pool.tenant_connection(tenant_id) as conn:
        # Upsert con merge jsonb: `config || {clave nueva}` en el propio UPDATE — atómico,
        # last-write-wins SOLO sobre 'model_policy', el resto del config queda intacto.
        await conn.execute(
            "INSERT INTO tenant_settings (tenant_id, config) VALUES (%s::uuid, %s) "
            "ON CONFLICT (tenant_id) DO UPDATE SET "
            "config = COALESCE(tenant_settings.config, '{}'::jsonb) || EXCLUDED.config, "
            "updated_at = now()",
            (tenant_id, Json({"model_policy": policy})),
        )
    invalidate_policy_cache(tenant_id)
    return {"politica": policy, "nombre": _POLICY_LABELS[policy], "opciones": _policy_options()}
