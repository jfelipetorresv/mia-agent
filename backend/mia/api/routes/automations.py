"""Mia · api.routes.automations — plantillas y automatizaciones (CP-P2, Ola 2).

GET    /api/automations/blueprints            → catálogo de plantillas (formularios)
GET    /api/automations                        → automatizaciones activas del despacho
POST   /api/automations                        → crea una desde una plantilla (acto humano)
DELETE /api/automations/{id}                   → elimina una automatización
GET    /api/automations/suggestions            → sugerencias pendientes (máx 5)
POST   /api/automations/suggestions/{id}/accept  → acepta (crea la automatización)
POST   /api/automations/suggestions/{id}/dismiss → descarta (queda latcheada)

§G: el abogado ve nombres en español y campos con etiquetas llanas — nunca "cron",
"blueprint" ni "job". REGLA DURA: las plantillas que tocan un plazo procesal solo se
crean con su acción explícita (aceptar/rellenar); Mia jamás las auto-activa ni calcula
un término.
"""
from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request

from ...cron import blueprints
from ...cron.suggestions import AutomationService, SuggestionService

router = APIRouter(tags=["automations"])
_automations = AutomationService()
_suggestions = SuggestionService(automations=_automations)


def _tenant(request: Request) -> str:
    t = getattr(request.state, "tenant_id", None)
    if not t:
        raise HTTPException(status_code=401, detail="Sin contexto de tenant")
    return t


@router.get("/automations/blueprints")
async def list_blueprints(request: Request):
    """Catálogo de plantillas rellenables (para pintar formularios, sin jerga)."""
    _tenant(request)
    return {"plantillas": blueprints.catalog_entries()}


@router.get("/automations")
async def list_automations(request: Request):
    """Automatizaciones activas del despacho."""
    return {"automatizaciones": await _automations.list_active(_tenant(request))}


@router.post("/automations")
async def create_automation(request: Request):
    """Crea una automatización desde una plantilla (acto humano explícito).
    Cuerpo: {"plantilla": "<key>", "valores": {...}}."""
    tenant_id = _tenant(request)
    try:
        body = await request.json()
    except Exception:  # noqa: BLE001
        body = None
    key = (body or {}).get("plantilla") if isinstance(body, dict) else None
    valores = (body or {}).get("valores") if isinstance(body, dict) else None
    if not key:
        raise HTTPException(status_code=422, detail="Falta la plantilla.")
    try:
        automation = await _automations.create(tenant_id, str(key), valores)
    except blueprints.BlueprintFillError as e:
        raise HTTPException(status_code=422, detail=str(e)) from e
    return automation


@router.delete("/automations/{automation_id}")
async def delete_automation(automation_id: str, request: Request):
    ok = await _automations.delete(_tenant(request), automation_id)
    if not ok:
        raise HTTPException(status_code=404, detail="Automatización no encontrada")
    return {"eliminada": True}


@router.get("/automations/suggestions")
async def list_suggestions(request: Request):
    """Sugerencias pendientes (Mia propone; el abogado acepta o descarta)."""
    return {"sugerencias": await _suggestions.list_pending(_tenant(request))}


@router.post("/automations/suggestions/{suggestion_id}/accept")
async def accept_suggestion(suggestion_id: str, request: Request):
    tenant_id = _tenant(request)
    try:
        automation = await _suggestions.accept(tenant_id, suggestion_id)
    except blueprints.BlueprintFillError as e:
        raise HTTPException(status_code=422, detail=str(e)) from e
    if automation is None:
        raise HTTPException(status_code=404, detail="Sugerencia no encontrada o ya resuelta")
    return {"aceptada": True, "automatizacion": automation}


@router.post("/automations/suggestions/{suggestion_id}/dismiss")
async def dismiss_suggestion(suggestion_id: str, request: Request):
    ok = await _suggestions.dismiss(_tenant(request), suggestion_id)
    if not ok:
        raise HTTPException(status_code=404, detail="Sugerencia no encontrada o ya resuelta")
    return {"descartada": True}
