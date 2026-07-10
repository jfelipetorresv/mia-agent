"""Mia · api.routes.guides — entrevista para crear guías de trabajo (Bloque B, B1-B3).

`POST /api/guides/interview` — motor de entrevista STATELESS: el frontend manda el
transcript completo en `messages` y este endpoint responde la siguiente pregunta o el
borrador final. El borrador SOLO existe en esta respuesta HTTP — nunca se escribe en
la base de datos aquí (eso pasa en `POST /api/playbooks`, cuando el abogado pulsa
Guardar). Ver `backend/mia/memory/interviewer.py` para el motor.

Validación 422 en español llano (nada de errores de pydantic en inglés hacia el
abogado): tipo de guía inválido, `messages` que no es una lista, un mensaje sin rol o
sin contenido de texto. `kind='agente'` responde 422 — los agentes jurídicos con
conocimiento propio llegan en el Bloque C.
"""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel

from ...db import pool
from ...memory.interviewer import MatterNotFoundError, interview

router = APIRouter(prefix="/api/guides", tags=["guides"])

_VALID_KINDS = ("guia", "agente")
_VALID_ROLES = ("assistant", "user")


def _tenant(request: Request) -> str:
    tid = getattr(request.state, "tenant_id", None)
    if not tid:
        raise HTTPException(status_code=401, detail="Sin sesión activa")
    return tid


class InterviewRequest(BaseModel):
    kind: str
    messages: Any = None
    matter_id: str | None = None


def _validate_messages(raw: Any) -> list[dict]:
    if not isinstance(raw, list):
        raise HTTPException(status_code=422, detail="El listado de mensajes no es válido.")
    clean: list[dict] = []
    for m in raw:
        if not isinstance(m, dict):
            raise HTTPException(status_code=422, detail="Cada mensaje debe traer rol y contenido.")
        role = m.get("role")
        content = m.get("content")
        if role not in _VALID_ROLES:
            raise HTTPException(status_code=422, detail="Cada mensaje debe traer un rol válido.")
        if not isinstance(content, str) or not content.strip():
            raise HTTPException(status_code=422, detail="Cada mensaje debe traer un contenido de texto.")
        clean.append({"role": role, "content": content})
    return clean


@router.post("/interview")
async def guides_interview(request: Request, body: InterviewRequest):
    tid = _tenant(request)

    if body.kind not in _VALID_KINDS:
        raise HTTPException(status_code=422, detail="Ese tipo de guía no existe.")
    if body.kind == "agente":
        raise HTTPException(
            status_code=422, detail="Los agentes se crean con Mia próximamente."
        )

    messages = _validate_messages(body.messages)

    try:
        return await interview(
            kind=body.kind,
            messages=messages,
            tenant_id=tid,
            matter_id=body.matter_id,
            pool=pool,
        )
    except MatterNotFoundError:
        raise HTTPException(status_code=404, detail="Ese asunto no existe.")
