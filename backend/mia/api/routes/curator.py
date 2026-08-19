"""Mia · api.routes.curator — HITL del Curator (Tarea H.2, cierra Riesgo #19).

El Curator ya no fusiona/poda playbooks solo: PROPONE (dry-run) y el abogado aprueba o rechaza.
Auth: el JWT middleware fija `request.state.tenant_id` (RLS) y `request.state.email`.

§G (CLAUDE.md): sin jerga técnica hacia el usuario — "propuesta de depuración", no "consolidate".
"""
from __future__ import annotations

import logging

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel

from ...memory.curator import Curator
from ._common import require_uuid

router = APIRouter(prefix="/api/curator", tags=["curator"])
logger = logging.getLogger("mia.api.curator")


def _tenant(request: Request) -> str:
    tid = getattr(request.state, "tenant_id", None)
    if not tid:
        raise HTTPException(status_code=401, detail="Sin sesión activa")
    return tid


def _reviewer(request: Request) -> str | None:
    return getattr(request.state, "email", None)


@router.post("/run")
async def curator_run(request: Request):
    """Lanza una revisión en seco: calcula qué playbooks fusionar/archivar SIN ejecutar nada,
    persiste la propuesta como pendiente y la devuelve para revisión."""
    tid = _tenant(request)
    proposal = await Curator().propose(tid)
    return proposal.to_public()


@router.get("/proposals")
async def curator_proposals(request: Request, status: str = "pending"):
    """Lista las propuestas de depuración en un estado (por defecto, las pendientes)."""
    tid = _tenant(request)
    return await Curator().list_proposals(tid, status=status)


@router.post("/proposals/{proposal_id}/approve")
async def curator_approve(proposal_id: str, request: Request):
    """Aprueba una propuesta pendiente: aplica las fusiones/archivados con snapshot + rollback
    automático si algo falla, y deja registro de auditoría."""
    tid = _tenant(request)
    proposal_id = require_uuid(proposal_id, "propuesta")
    result = await Curator().apply_proposal(tid, proposal_id, reviewed_by=_reviewer(request))
    if result.get("status") == "not_found":
        raise HTTPException(status_code=404, detail="Propuesta no encontrada")
    if result.get("status") == "failed":
        # Se revirtió: 409 para que el frontend sepa que no se aplicó nada.
        raise HTTPException(status_code=409, detail="No se pudo aplicar la propuesta; se revirtió.")
    if result.get("error"):
        raise HTTPException(status_code=409, detail=result["error"])
    return result


@router.post("/proposals/{proposal_id}/reject")
async def curator_reject(proposal_id: str, request: Request):
    """Rechaza una propuesta pendiente: no toca ningún playbook, solo la marca rechazada."""
    tid = _tenant(request)
    proposal_id = require_uuid(proposal_id, "propuesta")
    result = await Curator().reject_proposal(tid, proposal_id, reviewed_by=_reviewer(request))
    if result.get("status") == "not_found":
        raise HTTPException(status_code=404, detail="Propuesta no encontrada")
    if result.get("error"):
        raise HTTPException(status_code=409, detail=result["error"])
    return result


class ConflictChoice(BaseModel):
    """'a' | 'b' = con esta versión se queda el despacho (la otra se archiva).
    'none' = las dos siguen vivas (la contradicción es una decisión, no un error)."""

    choice: str


@router.post("/proposals/{proposal_id}/resolve")
async def curator_resolve_conflict(proposal_id: str, body: ConflictChoice, request: Request):
    """Resuelve un conflicto de criterio: el abogado dice cuál de las dos versiones sostiene el
    despacho hoy — o que sostiene las dos. Nunca se funden."""
    tid = _tenant(request)
    proposal_id = require_uuid(proposal_id, "propuesta")
    result = await Curator().resolve_conflict(
        tid, proposal_id, body.choice, reviewed_by=_reviewer(request))
    if result.get("status") == "not_found":
        raise HTTPException(status_code=404, detail="Propuesta no encontrada")
    if result.get("status") == "invalid":
        raise HTTPException(status_code=400, detail=result["error"])
    if result.get("status") == "failed":
        raise HTTPException(status_code=409, detail="No se pudo aplicar tu decisión; se revirtió.")
    if result.get("error"):
        raise HTTPException(status_code=409, detail=result["error"])
    return result
