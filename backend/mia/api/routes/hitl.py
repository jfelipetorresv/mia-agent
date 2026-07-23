"""Mia · api.routes.hitl — aprobación del borrador por el abogado (1d · PASO 5).

POST approve | reject | edit reanudan el grafo con `Command(resume=...)` y emiten
finalizing→done en la MISMA respuesta SSE (decisión #11). Todos verifican que el
tenant del JWT es dueño del asunto ANTES de reanudar (tenant cruzado → 401,
decisión #9).
"""
from __future__ import annotations

import asyncio
import logging

from fastapi import APIRouter, HTTPException, Request
from langgraph.types import Command
from pydantic import BaseModel
from sse_starlette.sse import EventSourceResponse

from ...agents.checkpointer import open_checkpointer
from ...agents.graph import build_matter_graph
from ...agents.state import thread_id_for
from ...db import pool
from ...memory.wiki_manager import WikiManager
from ._common import assert_owns_matter, require_awaiting_review, sse

router = APIRouter(tags=["matters"])
logger = logging.getLogger("mia.api.hitl")

# Referencias vivas a las tareas de fondo (sin esto, asyncio puede recolectarlas
# a mitad de camino). Se auto-limpian al terminar.
_BACKGROUND_TASKS: set[asyncio.Task] = set()


class RejectBody(BaseModel):
    feedback: str = ""


class EditBody(BaseModel):
    edits: str = ""


async def _resume(request: Request, matter_id: str, command: dict) -> EventSourceResponse:
    tenant_id = getattr(request.state, "tenant_id", None)
    if not tenant_id:
        raise HTTPException(status_code=401, detail="Sin contexto de tenant")
    await assert_owns_matter(tenant_id, matter_id)  # tenant cruzado -> 401

    async def gen():
        yield sse("finalizing", "Mia está finalizando el borrador…")
        try:
            async with open_checkpointer() as cp:
                graph = build_matter_graph(cp)
                cfg = {"configurable": {"thread_id": thread_id_for(tenant_id, matter_id)}}
                await require_awaiting_review(graph, cfg)
                final_draft = None
                async for chunk in graph.astream(Command(resume=command), cfg, stream_mode="updates"):
                    if "finalize" in chunk:
                        final_draft = (chunk["finalize"] or {}).get("draft")
                # Riesgo #25: la decisión quedó tomada (approve/reject/edit) —
                # el asunto ya no tiene borrador esperando revisión. Se resetea también
                # el debounce del aviso (CP-B3): un borrador NUEVO avisa de inmediato.
                async with pool.tenant_connection(tenant_id) as conn:
                    await conn.execute(
                        "UPDATE matters SET pending_review = false, "
                        "pending_review_notified_at = NULL "
                        "WHERE id = %s::uuid", (matter_id,))
                if command.get("decision") == "approved":
                    # El aprendizaje del despacho (wiki) hace VARIAS llamadas al modelo
                    # y puede tardar minutos: no puede retener el "done" — la decisión
                    # del abogado ya quedó registrada arriba. Corre en segundo plano,
                    # fail-open: si falla se pierde UNA actualización de wiki (queda en
                    # el log), nunca la aprobación.
                    async def _wiki_update(tid: str = tenant_id, mid: str = matter_id) -> None:
                        try:
                            await WikiManager().update_from_approved_matter(tid, mid)
                        except Exception:
                            logger.exception("wiki update falló (tenant=%s matter=%s)", tid, mid)
                    task = asyncio.create_task(_wiki_update())
                    _BACKGROUND_TASKS.add(task)
                    task.add_done_callback(_BACKGROUND_TASKS.discard)

                # La sección «lo que he ido aprendiendo de tu trabajo» del perfil se
                # enriquece sola: de este borrador Mia infiere 0..N patrones de metodología
                # del despacho y los deposita en el perfil. Corre al APROBAR y también al
                # CORREGIR (F2: el path `editing` estaba sin cablear y una corrección del
                # abogado es la señal de metodología más rica que existe — el texto final ya
                # incorpora lo que él cambió; la fuente lo dice: SOURCE_CORREGIDO). También
                # en segundo plano y fail-soft absoluto — `learn_from_approved_draft` nunca
                # lanza, pero se envuelve igual: NINGÚN fallo aquí puede rozar la decisión,
                # que ya quedó cerrada arriba. Solo si hubo un borrador que mostrar.
                decision = command.get("decision")
                if final_draft and decision in ("approved", "editing"):
                    async def _aprender(tid: str = tenant_id, mid: str = matter_id,
                                        texto: str = final_draft,
                                        dec: str = decision) -> None:
                        try:
                            from ...memory.aprendido import (
                                SOURCE_APROBADO,
                                SOURCE_CORREGIDO,
                                learn_from_approved_draft,
                            )
                            await learn_from_approved_draft(
                                tid, texto,
                                source=(SOURCE_CORREGIDO if dec == "editing"
                                        else SOURCE_APROBADO))
                        except Exception:
                            logger.exception("aprendido update falló (tenant=%s matter=%s)",
                                             tid, mid)
                    task_ap = asyncio.create_task(_aprender())
                    _BACKGROUND_TASKS.add(task_ap)
                    task_ap.add_done_callback(_BACKGROUND_TASKS.discard)
                yield sse("done", "Listo.", draft=final_draft, status=command.get("decision"))
        except HTTPException:
            raise
        except Exception:
            logger.exception("resume HITL falló (tenant=%s matter=%s)", tenant_id, matter_id)
            yield sse("error", "No se pudo finalizar el borrador. Intenta de nuevo.")

    return EventSourceResponse(gen())


@router.post("/matters/{matter_id}/approve")
async def approve(matter_id: str, request: Request):
    return await _resume(request, matter_id, {"decision": "approved"})


@router.post("/matters/{matter_id}/reject")
async def reject(matter_id: str, request: Request, body: RejectBody):
    return await _resume(request, matter_id, {"decision": "rejected", "feedback": body.feedback})


@router.post("/matters/{matter_id}/edit")
async def edit(matter_id: str, request: Request, body: EditBody):
    return await _resume(request, matter_id, {"decision": "editing", "edits": body.edits})
