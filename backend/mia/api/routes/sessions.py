"""Mia · api.routes.sessions — /daily y /cierre del expediente (Piezas 4c/4d/4e).

Endpoints que el frontend expone con BOTONES (decisión de Pipe: el abogado nunca escribe
comandos técnicos). El router es delgado: valida propiedad del asunto (RLS) y delega el
trabajo al núcleo `onboarding.session_briefing`.

  GET  /api/matters/{id}/daily   → resumen priorizado del día (lo que requiere decisión
                                    del abogado ARRIBA, cada ítem con referencia #N).
  POST /api/matters/{id}/cierre  → destila lo que el abogado decidió/instruyó en la sesión
                                    (cadena barata de LLM) y lo escribe al expediente. Con
                                    `auto: true` solo actúa si el contexto llegó a ~65%.

Ambos son fail-soft: no responden 500 por un tropiezo de disco o de LLM (§G).
"""
from __future__ import annotations

import logging

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel

from ...onboarding import session_briefing
from ._common import assert_owns_matter

router = APIRouter(prefix="/api", tags=["sessions"])
logger = logging.getLogger("mia.api.sessions")


def _tenant(request: Request) -> str:
    tid = getattr(request.state, "tenant_id", None)
    if not tid:
        raise HTTPException(status_code=401, detail="Sin sesión activa")
    return tid


@router.get("/matters/{matter_id}/daily")
async def daily(matter_id: str, request: Request):
    """Resumen priorizado del asunto para arrancar el día (botón 'Al día').

    Lo que requiere decisión del abogado va primero (`requiere_decision: true`), luego lo
    informativo; cada ítem lleva una referencia estable `#N`."""
    tid = _tenant(request)
    await assert_owns_matter(tid, matter_id)
    return await session_briefing.build_daily_briefing(tid, matter_id)


class CierreBody(BaseModel):
    """Transcripción de la sesión que se cierra. `messages` es la conversación visible del
    asunto (cada ítem {role, content}); el núcleo destila SOLO las intervenciones del
    abogado. `auto`/`fill_threshold`/`context_window` habilitan el cierre automático por
    llenado de contexto (~65%) sin cambiar de endpoint."""
    messages: list[dict] = []
    auto: bool = False
    fill_threshold: float | None = None
    context_window: int | None = None


@router.post("/matters/{matter_id}/cierre")
async def cierre(matter_id: str, request: Request, body: CierreBody):
    """Cierra la sesión: destila lo que el abogado decidió/instruyó y lo escribe al
    expediente (bitácora + bloque 'Pendiente de tu decisión' del HANDOFF).

    `auto: true` → solo actúa si la conversación llenó la ventana por encima del umbral
    (~65%); de lo contrario devuelve `triggered: false` sin escribir nada."""
    tid = _tenant(request)
    await assert_owns_matter(tid, matter_id)
    if body.auto:
        threshold = (body.fill_threshold
                     if body.fill_threshold is not None
                     else session_briefing.CONTEXT_FILL_THRESHOLD)
        return await session_briefing.maybe_auto_cierre(
            tid, matter_id, body.messages,
            context_window=body.context_window, fill_threshold=threshold)
    return await session_briefing.distill_and_write_cierre(tid, matter_id, body.messages)
