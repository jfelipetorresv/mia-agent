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
import re
import uuid
from typing import AsyncIterator

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field
from sse_starlette.sse import EventSourceResponse

from ...assistant.core import AssistantService, ConversationNotFound
from ...assistant.chat_requests import ChatRequestConflict
from ...assistant.reminders import ReminderService
from ...policy import budget as policy_budget
from ._common import sse

router = APIRouter(prefix="/assistant", tags=["assistant"])

# CP-S3: latido del SSE (igual que el turno del asunto en stream.py). El turno del
# asistente corre sobre el motor por suscripción (CLI), que responde en BLOQUE: el
# ping mantiene viva la conexión durante los segundos que tarda el modelo en pensar.
SSE_PING_SECONDS = 15
logger = logging.getLogger("mia.api.assistant")

# Servicio del proceso — SIN estado entre requests: el ContextCompressor se crea por
# turno dentro de chat() (aislamiento en memoria entre tenants, además del RLS).
_service = AssistantService()

# El chat general sirve para organización personal. El trabajo jurídico que puede
# acabar en un escrito, una estrategia o una conclusión sobre un caso debe vivir en
# un Asunto: allí sí hay expediente, jurisdicción, fuentes, revisión y ledger. La
# detección es conservadora (acción + objeto jurídico) para no bloquear una charla
# casual por contener una sola palabra como "contrato".
_LEGAL_ACTION = re.compile(
    r"\b(redact\w*|contest\w*|analiz\w*|revis\w*|prepar\w*|elabor\w*|"
    r"impugn\w*|apel\w*|demand\w*|defend\w*|estrateg\w*|argument\w*)\b",
    re.IGNORECASE,
)
_LEGAL_OBJECT = re.compile(
    r"\b(demanda|contestaci[oó]n|contrato|cl[aá]usula|escrito|recurso|caso|"
    r"expediente|sentencia|audiencia|prueba|alegato|concepto jur[ií]dico|"
    r"estrategia jur[ií]dica|acci[oó]n judicial)\b",
    re.IGNORECASE,
)
_MATTER_REDIRECT_MESSAGE = (
    "Para trabajar jurídicamente con precisión necesito hacerlo dentro de un caso, "
    "con su jurisdicción, expediente y verificaciones. Elige un caso o crea uno nuevo."
)


def requires_legal_matter(message: str) -> bool:
    """Detecta solicitudes sustantivas; nunca intenta decidir el derecho aplicable."""
    text = " ".join((message or "").split())
    return bool(_LEGAL_ACTION.search(text) and _LEGAL_OBJECT.search(text))


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
    request_id: uuid.UUID | None = None


async def _prepare_chat(body: ChatBody, request: Request, tid: str):
    async def budget():
        await policy_budget.enforce_budget(tid)
    try:
        uid = await _user_id(request, tid)
        return await _service.prepare_chat(
            tid, uid, body.conversation_id, body.message,
            request_id=str(body.request_id) if body.request_id is not None else None,
            before_execute=budget)
    except policy_budget.BudgetExceeded as e:
        raise HTTPException(status_code=402, detail=str(e))
    except ChatRequestConflict as e:
        raise HTTPException(status_code=409, detail=str(e))
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))
    except Exception:
        logger.exception("No se pudo preparar el envío del asistente (tenant=%s)", tid)
        raise HTTPException(status_code=502, detail="No pude confirmar este envío. Intenta recuperarlo de nuevo.")


@router.post("/chat")
async def assistant_chat(body: ChatBody, request: Request):
    """Un turno de conversación libre con Mia. Devuelve {conversation_id, reply}."""
    tid = _tenant(request)
    if requires_legal_matter(body.message):
        raise HTTPException(status_code=409, detail=_MATTER_REDIRECT_MESSAGE)
    turn = await _prepare_chat(body, request, tid)
    try:
        result = await _service.chat_prepared(turn)
    except ChatRequestConflict as e:
        raise HTTPException(status_code=409, detail=str(e))
    except ConversationNotFound:
        raise HTTPException(status_code=404, detail="No encontré esa conversación.")
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))
    except Exception:  # noqa: BLE001 — §G: nunca exponer el error técnico al abogado
        logger.exception("assistant_chat falló (tenant=%s)", tid)
        raise HTTPException(
            status_code=502,
            detail=("No pude confirmar cómo terminó este envío. Revisa el historial antes de enviar otro."
                    if body.request_id else "No pude responder en este momento. Intenta de nuevo en unos minutos."),
        )
    return result


@router.post("/chat/stream")
async def assistant_chat_stream(body: ChatBody, request: Request):
    """Igual que POST /chat pero por SSE — la respuesta llega en cuanto está lista,
    precedida de un aviso de "pensando" para que la pantalla nunca muestre un
    spinner mudo (Fase 1: velocidad percibida).

    El motor por suscripción responde en BLOQUE (no hay tokens sueltos que streamear),
    así que reutilizamos íntegro `_service.chat()` — misma lógica, mismos recordatorios,
    misma persistencia, mismo tope de gasto. El SSE solo cambia la ENTREGA: emite
    `thinking` de inmediato y luego `reply` con el texto completo; el efecto de
    escritura progresiva lo hace el navegador. Contrato listo para tokens reales el
    día que el motor los soporte, sin tocar la pantalla.

    Las validaciones que deben ser HTTP (sin sesión → 401, tope de gasto → 402) se
    lanzan ANTES de abrir el stream, igual que el turno del asunto (stream.py)."""
    tid = _tenant(request)
    if requires_legal_matter(body.message):
        async def matter_required() -> AsyncIterator[dict]:
            yield sse("matter_required", _MATTER_REDIRECT_MESSAGE, redirect="/")

        return EventSourceResponse(matter_required(), ping=SSE_PING_SECONDS)
    # Cache validado antes del tope; un envío NUEVO conserva el 402 previo al SSE.
    turn = await _prepare_chat(body, request, tid)

    async def gen() -> AsyncIterator[dict]:
        yield sse("thinking", "Mia está pensando…")
        try:
            result = await _service.chat_prepared(turn)
        except ChatRequestConflict as e:
            yield sse("error", str(e))
            return
        except ConversationNotFound:
            yield sse("error", "No encontré esa conversación.")
            return
        except ValueError as e:
            # §G: los ValueError del asistente ya vienen en lenguaje llano.
            yield sse("error", str(e))
            return
        except Exception:  # noqa: BLE001 — §G: nunca exponer el error técnico al abogado
            logger.exception("assistant_chat_stream falló (tenant=%s)", tid)
            yield sse("error", "No pude confirmar cómo terminó este envío. Revisa el historial antes de enviar otro."
                      if body.request_id else "No pude responder en este momento. Intenta de nuevo en unos minutos.")
            return
        yield sse("reply", result["reply"], conversation_id=result["conversation_id"],
                  request_id=result["request_id"], cached=result["cached"])

    return EventSourceResponse(gen(), ping=SSE_PING_SECONDS)


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


# ── CP-B3 · recordatorios (la creación es por chat, en lenguaje natural) ─────
_reminders = ReminderService()


@router.get("/reminders")
async def assistant_reminders(request: Request):
    """Recordatorios pendientes del despacho, el más próximo primero."""
    tid = _tenant(request)
    try:
        return await _reminders.list_pending(tid)
    except Exception:  # noqa: BLE001 — §G: nunca exponer el error técnico al abogado
        logger.exception("listar recordatorios falló (tenant=%s)", tid)
        raise HTTPException(
            status_code=502,
            detail="No pude consultar tus recordatorios en este momento. Intenta de nuevo.",
        )


@router.post("/reminders/{reminder_id}/cancel")
async def assistant_reminder_cancel(reminder_id: str, request: Request):
    """Cancela un recordatorio pendiente. Ajeno o inexistente → 404 (RLS incluido)."""
    tid = _tenant(request)
    try:
        uuid.UUID(reminder_id)
    except (ValueError, AttributeError, TypeError):
        # Id mal formado = "no existe" (404), nunca un error técnico (500).
        raise HTTPException(status_code=404, detail="No encontré ese recordatorio.")
    try:
        cancelled = await _reminders.cancel(tid, reminder_id)
    except Exception:  # noqa: BLE001 — DB caída NO es "no existe": §G, error amable
        logger.exception("cancelar recordatorio falló (tenant=%s)", tid)
        raise HTTPException(
            status_code=502,
            detail="No pude cancelar el recordatorio en este momento. Intenta de nuevo.",
        )
    if not cancelled:
        raise HTTPException(status_code=404, detail="No encontré ese recordatorio.")
    return {"status": "cancelled"}
