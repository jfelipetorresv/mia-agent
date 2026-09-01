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

from ...agents.personas import (CAPABILITIES, PersonaError, capability_available,
                                persona_service)

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
    # Guías del despacho que este agente prioriza (ids). None = no tocar los vínculos.
    playbook_ids: list[str] | None = None
    # D8 · qué puede hacer, además de su encargo en prosa. Vocabulario cerrado validado en
    # el dominio. `None` = NO TOCAR lo que ya tenía, igual que `playbook_ids`: la lista vacía
    # es la forma de quitarlas todas. Tener dos campos del mismo cuerpo con semánticas
    # opuestas para el mismo valor era una trampa — hoy la pantalla siempre manda el campo,
    # pero cualquier guardado parcial futuro (un interruptor de «habilitado», un cliente de
    # otra versión) habría borrado en silencio lo que el abogado concedió.
    capabilities: list[str] | None = None


@router.get("/capacidades")
async def capacidades(request: Request):
    """Las capacidades que se le pueden conceder a un agente, y si ESTA instalación las
    tiene de verdad.

    Marcar una capacidad es una decisión del abogado; que la máquina pueda cumplirla es
    otra cosa. Separarlas es lo que evita la promesa vacía: la pantalla ofrece las tres,
    pero dice cuál no está disponible aquí y por qué, con la misma razón honesta que ya
    usa el catálogo de ayudantes (nunca «[VERIFICAR]», nunca un silencio).

    La disponibilidad la decide `personas.capability_available`, la MISMA función que usa
    la voz del turno. Si esta pantalla midiera por su cuenta, podría decirle al abogado que
    una capacidad está lista mientras el prompt le dice al modelo lo contrario.
    """
    _tenant(request)

    def razon_de(clave: str, falta: str) -> tuple[bool, str]:
        if capability_available(clave):
            return True, ""
        return False, falta

    ocr_ok, ocr_razon = razon_de(
        CAPABILITIES[0],
        "La lectura óptica no está incluida en esta instalación, así que un documento "
        "escaneado sin texto no se puede leer.")
    inv_ok, inv_razon = razon_de(
        CAPABILITIES[1],
        "Todavía no tienes conectado un ayudante de investigación, así que trabajaré solo "
        "con lo que haya en el expediente y en tu conocimiento.")
    doc_ok, doc_razon = razon_de(
        CAPABILITIES[2],
        "Todavía no tienes conectado un ayudante de documentos: puedo redactar igual, pero "
        "sin armar el archivo con su formato.")

    return {"capacidades": [
        {"clave": CAPABILITIES[0],
         "titulo": "Leer imágenes, diagramas y escaneados",
         "descripcion": "Para expedientes que llegan fotografiados o escaneados sin texto.",
         "disponible": ocr_ok, "razon": ocr_razon},
        {"clave": CAPABILITIES[1],
         "titulo": "Buscar normas y jurisprudencia en vivo",
         "descripcion": "Para cuando el expediente no basta y hay que ir a la fuente.",
         "disponible": inv_ok, "razon": inv_razon},
        {"clave": CAPABILITIES[2],
         "titulo": "Redactar documentos largos con su formato",
         "descripcion": "Para escritos completos, no resúmenes.",
         "disponible": doc_ok, "razon": doc_razon},
    ]}


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
        # Los vínculos a guías se fijan tras crear el agente. Si esto falla (tope, guía
        # inexistente), el agente ya quedó creado SIN vínculos y se responde 422 en llano:
        # el abogado corrige las guías y guarda de nuevo (no se pierde el agente).
        if body.playbook_ids is not None:
            await persona_service.set_linked_playbooks(tid, persona.id, body.playbook_ids)
            persona = await persona_service.get_persona(tid, persona.id) or persona
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
        if body.playbook_ids is not None:
            await persona_service.set_linked_playbooks(tid, persona_id, body.playbook_ids)
            persona = await persona_service.get_persona(tid, persona_id) or persona
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
