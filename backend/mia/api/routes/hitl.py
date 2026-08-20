"""Mia · api.routes.hitl — aprobación del borrador por el abogado (1d · PASO 5).

POST approve | reject | edit reanudan el grafo con `Command(resume=...)` y emiten
finalizing→done en la MISMA respuesta SSE (decisión #11). Todos verifican que el
tenant del JWT es dueño del asunto ANTES de reanudar (tenant cruzado → 401,
decisión #9).
"""
from __future__ import annotations

import logging
from typing import Literal

from fastapi import APIRouter, HTTPException, Request
from langgraph.types import Command
from pydantic import BaseModel, Field
from sse_starlette.sse import EventSourceResponse

from ...agents.checkpointer import open_checkpointer
from ...agents.graph import build_matter_graph
from ...agents.state import thread_id_for
from ...db import pool
from ...memory import legal_ledger
from ._common import assert_owns_matter, require_awaiting_review, sse
from .stream import turno_sse

router = APIRouter(tags=["matters"])
logger = logging.getLogger("mia.api.hitl")

class RejectBody(BaseModel):
    feedback: str = ""


class EditBody(BaseModel):
    # Conservamos ``edits`` como nombre de wire legacy, pero desde P0 su
    # significado es inequívoco: el documento completo escrito por el abogado.
    edits: str = Field(min_length=1)
    draft_hash: str = Field(min_length=64, max_length=64)
    attested: Literal[True]


class Comentario(BaseModel):
    """Un comentario del abogado anclado a un pasaje del borrador (estilo Docs).

    El ancla es el TEXTO citado más su contexto, no un offset: el documento se reescribe
    y los offsets mienten. `parrafo_indice` es solo una pista para desempatar.
    """
    id: str = ""
    texto_citado: str = Field(min_length=1, max_length=2000)
    instruccion: str = Field(min_length=1, max_length=1000)
    parrafo_indice: int = -1
    contexto_antes: str = ""
    contexto_despues: str = ""


class ComentariosBody(BaseModel):
    draft_hash: str = Field(min_length=64, max_length=64)
    comentarios: list[Comentario] = Field(min_length=1, max_length=20)


class ArgumentSelection(BaseModel):
    include: list[str] = Field(default_factory=list)
    exclude: list[str] = Field(default_factory=list)


class ApproveBody(BaseModel):
    draft_hash: str = Field(min_length=64, max_length=64)
    attested: Literal[True]
    argument_selection: ArgumentSelection | None = None


async def _require_current_draft_hash(tenant_id: str, matter_id: str, supplied: str):
    """Rechaza una aprobación tardía o fabricada antes de reanudar el grafo."""
    async with open_checkpointer() as cp:
        graph = build_matter_graph(cp)
        cfg = {"configurable": {"thread_id": thread_id_for(tenant_id, matter_id)}}
        await require_awaiting_review(graph, cfg)
        state = await graph.aget_state(cfg)
    draft = ((state.values or {}).get("draft") if state else "") or ""
    if legal_ledger.content_hash(draft) != supplied:
        raise HTTPException(status_code=409,
                            detail="El borrador cambió. Vuelve a revisarlo antes de aprobarlo.")
    return state


async def _resume(request: Request, matter_id: str, command: dict) -> EventSourceResponse:
    tenant_id = getattr(request.state, "tenant_id", None)
    if not tenant_id:
        raise HTTPException(status_code=401, detail="Sin contexto de tenant")
    await assert_owns_matter(tenant_id, matter_id)  # tenant cruzado -> 401
    if command.get("decision") in ("approved", "editing"):
        supplied = str(command.get("draft_hash") or "")
        if not supplied:
            raise HTTPException(status_code=422, detail="Falta la huella del borrador revisado.")
        review_state = await _require_current_draft_hash(tenant_id, matter_id, supplied)
        if command.get("attested") is not True:
            raise HTTPException(status_code=422,
                                detail="Confirma que revisaste el documento antes de continuar.")
        if command.get("decision") == "approved":
            report = ((review_state.values or {}).get("metadata") or {}).get("verification")
            if not legal_ledger.verification_passes(report):
                raise HTTPException(
                    status_code=409,
                    detail="La revisión independiente todavía no permite emitir esta versión como final.",
                )

    async def eventos():
        # Medición por etapa (sesión 56): el paso «aprobar» del E2E costaba ~90s y ninguna
        # pieza confesaba cuáles eran suyos. Una línea de log con la duración de cada etapa
        # convierte la próxima regresión en una lectura de log, no en una investigación.
        import time as _time
        t0 = _time.perf_counter()
        async with open_checkpointer() as cp:
            graph = build_matter_graph(cp)
            cfg = {"configurable": {"thread_id": thread_id_for(tenant_id, matter_id)}}
            t_abrir = _time.perf_counter() - t0
            t1 = _time.perf_counter()
            await require_awaiting_review(graph, cfg)
            t_estado = _time.perf_counter() - t1
            final_draft = None
            final_metadata: dict = {}
            t2 = _time.perf_counter()
            async for chunk in graph.astream(Command(resume=command), cfg, stream_mode="updates"):
                if "finalize" in chunk:
                    final_draft = (chunk["finalize"] or {}).get("draft")
                    final_metadata = (chunk["finalize"] or {}).get("metadata") or {}
            t_grafo = _time.perf_counter() - t2
            logger.info("resume(%s): abrir=%.1fs estado=%.1fs grafo=%.1fs (tenant=%s matter=%s)",
                        command.get("decision"), t_abrir, t_estado, t_grafo,
                        tenant_id, matter_id)
            final_ready = bool(final_metadata.get("final_ready"))
            pending_review = (command.get("decision") in ("approved", "editing")
                              and not final_ready)
            async with pool.tenant_connection(tenant_id) as conn:
                await conn.execute(
                    "UPDATE matters SET pending_review = %s, "
                    "pending_review_notified_at = CASE WHEN %s THEN pending_review_notified_at ELSE NULL END "
                    "WHERE id = %s::uuid", (pending_review, pending_review, matter_id))
            # La respuesta distingue dos hechos distintos: la decisión ya quedó
            # persistida; el aprendizaje apenas quedó en cola (o bloqueado). Nunca
            # promete "Mia aprendió" antes de que el worker termine.
            actual_status = str(final_metadata.get("final_status")
                                or command.get("decision") or "rejected")
            learning_internal = final_metadata.get("learning") or {
                "decision_saved": True, "status": "not_applicable", "jobs": []}
            jobs = learning_internal.get("jobs") or []
            # El navegador recibe el estado útil, no UUIDs ni nombres internos de jobs.
            learning = {
                "status": learning_internal.get("status") or "not_applicable",
                "queued": sum(1 for job in jobs
                              if job.get("status") in ("queued", "running")),
                "completed": sum(1 for job in jobs if job.get("status") == "succeeded"),
            }
            message = ("Documento final verificado." if final_ready else
                       "Guardé tu revisión, pero el documento aún no supera todos los controles.")
            yield sse("done", message, draft=final_draft, status=actual_status,
                      final_ready=final_ready, final_status=actual_status,
                      decision_saved=True, learning=learning)

    # El cierre del borrador también razona (finalize), así que también puede quedarse sin
    # suscripción y acabar en crédito de pago: mismo envoltorio que el turno, mismo aviso.
    return EventSourceResponse(turno_sse(
        "Mia está finalizando el borrador…", eventos, tenant_id, matter_id,
        error_msg="No se pudo finalizar el borrador. Intenta de nuevo.",
    ))


async def resume_con_comentarios(request: Request, matter_id: str,
                                 body: ComentariosBody) -> EventSourceResponse:
    """Corrección acotada: el abogado comentó pasajes concretos y Mia arregla SOLO esos.

    Es un camino propio, no una variante del rechazo: rechazar cierra el turno (el
    borrador se conserva, el motivo va a la traza y no hay nueva redacción), mientras que
    comentar reanuda el grafo hacia una pasada de corrección y devuelve a esta misma
    revisión con el borrador corregido. Colgarlo del rechazo habría cambiado el
    significado de una decisión que ya está cableada en el ledger y en las trazas.
    """
    tenant_id = getattr(request.state, "tenant_id", None)
    if not tenant_id:
        raise HTTPException(status_code=401, detail="Sin contexto de tenant")
    await assert_owns_matter(tenant_id, matter_id)
    # Los comentarios están anclados al TEXTO de la versión que el abogado vio: sobre
    # otra versión no significan nada. Misma huella, mismo 409 en llano que aprobar.
    await _require_current_draft_hash(tenant_id, matter_id, body.draft_hash)
    command = {
        "decision": "comments",
        "draft_hash": body.draft_hash,
        "comentarios": [c.model_dump() for c in body.comentarios],
    }

    async def eventos():
        async with open_checkpointer() as cp:
            graph = build_matter_graph(cp)
            cfg = {"configurable": {"thread_id": thread_id_for(tenant_id, matter_id)}}
            await require_awaiting_review(graph, cfg)
            async for _ in graph.astream(Command(resume=command), cfg,
                                         stream_mode="updates"):
                pass
            state = await graph.aget_state(cfg)
        values = (state.values or {}) if state else {}
        md = values.get("metadata") or {}
        informe = md.get("comentarios_resueltos") or {}
        nuevo = values.get("draft") or ""
        async with pool.tenant_connection(tenant_id) as conn:
            # El borrador corregido vuelve a esperar la revisión del abogado.
            await conn.execute(
                "UPDATE matters SET pending_review = TRUE, "
                "pending_review_notified_at = NULL WHERE id = %s::uuid", (matter_id,))
        yield sse("done",
                  informe.get("resumen") or "Apliqué tus comentarios al borrador.",
                  draft=nuevo,
                  draft_hash=legal_ledger.content_hash(nuevo),
                  status="comentarios_aplicados",
                  comentarios=informe.get("comentarios") or [],
                  avisos=informe.get("avisos") or [],
                  verification=md.get("verification"))

    return EventSourceResponse(turno_sse(
        "Mia está aplicando tus comentarios…", eventos, tenant_id, matter_id,
        error_msg="No se pudieron aplicar tus comentarios. Intenta de nuevo.",
    ))


@router.post("/matters/{matter_id}/comentarios")
async def comentarios(matter_id: str, request: Request, body: ComentariosBody):
    return await resume_con_comentarios(request, matter_id, body)


@router.post("/matters/{matter_id}/approve")
async def approve(matter_id: str, request: Request, body: ApproveBody | None = None):
    if body is None:
        # La propiedad se comprueba dentro de _resume antes de este 422 en la ruta
        # UX; el endpoint legado conserva este guardián explícito para clientes viejos.
        tenant_id = getattr(request.state, "tenant_id", None)
        if not tenant_id:
            raise HTTPException(status_code=401, detail="Sin contexto de tenant")
        await assert_owns_matter(tenant_id, matter_id)
        raise HTTPException(status_code=422, detail="Falta la constancia de revisión humana.")
    return await _resume(request, matter_id,
                         {"decision": "approved", "draft_hash": body.draft_hash,
                          "attested": body.attested,
                          **({"argument_selection": body.argument_selection.model_dump()}
                             if body.argument_selection is not None else {})})


@router.post("/matters/{matter_id}/reject")
async def reject(matter_id: str, request: Request, body: RejectBody):
    return await _resume(request, matter_id, {"decision": "rejected", "feedback": body.feedback})


@router.post("/matters/{matter_id}/edit")
async def edit(matter_id: str, request: Request, body: EditBody):
    return await _resume(request, matter_id, {
        "decision": "editing", "edited_text": body.edits, "draft_hash": body.draft_hash,
        "attested": body.attested,
    })
