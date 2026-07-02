"""Mia · api.routes.assistant — MODO ASISTENTE (CP-B1, Pilar B): conversación libre.

Superficie HTTP del asistente personal (assistant/core.py). v1 SIN SSE: el motor por
suscripción (CLI de Claude Code, CP2) responde en bloque, no streamea — el endpoint
devuelve JSON con la respuesta completa. El streaming del modo asistente se evalúa
cuando el canal lo pida (Telegram en CP-B2 tampoco lo necesita).

Auth: el middleware JWT fija `request.state.tenant_id` (RLS) y `request.state.email`;
el user_id se toma de request.state si algún middleware futuro lo fija, o se resuelve
por email contra `users` bajo RLS. §G: errores sin jerga técnica.
"""
from __future__ import annotations

import logging

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field

from ...assistant.core import AssistantService, ConversationNotFound

router = APIRouter(prefix="/assistant", tags=["assistant"])
logger = logging.getLogger("mia.api.assistant")

# Servicio del proceso — SIN estado entre requests: el ContextCompressor se crea por
# turno dentro de chat() (aislamiento en memoria entre tenants, además del RLS).
_service = AssistantService()


def _tenant(request: Request) -> str:
    tid = getattr(request.state, "tenant_id", None)
    if not tid:
        raise HTTPException(status_code=401, detail="Sin sesión activa")
    return tid


async def _user_id(request: Request, tenant_id: str) -> str | None:
    """user_id del JWT si el middleware lo fijó; si no, se resuelve por email (RLS)."""
    uid = getattr(request.state, "user_id", None)
    if uid:
        return str(uid)
    return await _service.resolve_user_id(tenant_id, getattr(request.state, "email", None))


class ChatBody(BaseModel):
    message: str = Field(min_length=1, max_length=100_000)
    conversation_id: str | None = None


@router.post("/chat")
async def assistant_chat(body: ChatBody, request: Request):
    """Un turno de conversación libre con Mia. Devuelve {conversation_id, reply}."""
    tid = _tenant(request)
    uid = await _user_id(request, tid)
    try:
        conversation_id, reply = await _service.chat(
            tid, uid, body.conversation_id, body.message
        )
    except ConversationNotFound:
        raise HTTPException(status_code=404, detail="No encontré esa conversación.")
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))
    except Exception:  # noqa: BLE001 — §G: nunca exponer el error técnico al abogado
        logger.exception("assistant_chat falló (tenant=%s)", tid)
        raise HTTPException(
            status_code=502,
            detail="No pude responder en este momento. Intenta de nuevo en unos minutos.",
        )
    return {"conversation_id": conversation_id, "reply": reply}


@router.get("/conversations")
async def assistant_conversations(request: Request):
    """Conversaciones del abogado (tenant + usuario), la más reciente primero."""
    tid = _tenant(request)
    uid = await _user_id(request, tid)
    return await _service.list_conversations(tid, uid)


@router.get("/conversations/{conversation_id}/messages")
async def assistant_messages(conversation_id: str, request: Request):
    """Historial de una conversación. Ajena o inexistente → 404 (nunca datos de otro despacho)."""
    tid = _tenant(request)
    try:
        return await _service.list_messages(tid, conversation_id)
    except ConversationNotFound:
        raise HTTPException(status_code=404, detail="No encontré esa conversación.")
