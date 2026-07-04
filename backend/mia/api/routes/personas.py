"""Mia · api.routes.personas — personas jurídicas del despacho (CP-E3, Ola 5).

CRUD de las personas editables del despacho (litigante, tributarista, revisor de citas
y las que el despacho cree). El abogado las gobierna desde el Panel de control; se
invocan por sus frases en el chat (asunto/Telegram) o por selección futura en la UI.

Auth: el middleware JWT fija `request.state.tenant_id` (RLS). §G: errores sin jerga.
"""
from __future__ import annotations

import logging

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field

from ...agents.personas import PersonaError, persona_service

router = APIRouter(prefix="/personas", tags=["personas"])
logger = logging.getLogger("mia.api.personas")


def _tenant(request: Request) -> str:
    tid = getattr(request.state, "tenant_id", None)
    if not tid:
        raise HTTPException(status_code=401, detail="Sin sesión activa")
    return tid


class PersonaBody(BaseModel):
    """Payload de crear/actualizar una persona. La validación fina (largos, nivel de
    motor, deduplicación de frases) la hace el dominio y devuelve mensajes en llano."""

    name: str = Field(min_length=1, max_length=64)
    title: str | None = ""
    role_prompt: str = Field(min_length=1, max_length=6000)
    tone: str | None = ""
    focus_areas: list[str] | None = None
    model_tier: str | None = "estandar"
    summon_phrases: list[str] | None = None
    description: str | None = ""
    enabled: bool = True


@router.get("")
async def list_personas(request: Request):
    """Personas del despacho (siembra las canónicas la primera vez)."""
    tid = _tenant(request)
    try:
        personas = await persona_service.list_personas(tid)
        return {"personas": [p.to_public() for p in personas]}
    except Exception:  # noqa: BLE001
        logger.exception("list_personas falló (tenant=%s)", tid)
        raise HTTPException(
            status_code=502,
            detail="No pude cargar las personas en este momento. Intenta de nuevo.",
        )


@router.post("")
async def create_persona(body: PersonaBody, request: Request):
    """Crea una persona nueva del despacho."""
    tid = _tenant(request)
    try:
        persona = await persona_service.create_persona(tid, body.model_dump())
        return persona.to_public()
    except PersonaError as e:
        raise HTTPException(status_code=422, detail=str(e))
    except Exception:  # noqa: BLE001
        logger.exception("create_persona falló (tenant=%s)", tid)
        raise HTTPException(
            status_code=502,
            detail="No pude crear la persona en este momento. Intenta de nuevo.",
        )


@router.put("/{persona_id}")
async def update_persona(persona_id: str, body: PersonaBody, request: Request):
    """Actualiza una persona del despacho."""
    tid = _tenant(request)
    try:
        persona = await persona_service.update_persona(tid, persona_id, body.model_dump())
        return persona.to_public()
    except PersonaError as e:
        # Inexistente/ajena o dato inválido → 422 con el mensaje en llano.
        raise HTTPException(status_code=422, detail=str(e))
    except Exception:  # noqa: BLE001
        logger.exception("update_persona falló (tenant=%s persona=%s)", tid, persona_id)
        raise HTTPException(
            status_code=502,
            detail="No pude guardar la persona en este momento. Intenta de nuevo.",
        )


@router.delete("/{persona_id}")
async def delete_persona(persona_id: str, request: Request):
    """Elimina una persona del despacho."""
    tid = _tenant(request)
    try:
        await persona_service.delete_persona(tid, persona_id)
        return {"ok": True}
    except PersonaError as e:
        raise HTTPException(status_code=422, detail=str(e))
    except Exception:  # noqa: BLE001
        logger.exception("delete_persona falló (tenant=%s persona=%s)", tid, persona_id)
        raise HTTPException(
            status_code=502,
            detail="No pude eliminar la persona en este momento. Intenta de nuevo.",
        )
