"""Mia · api.routes.delegation — el abogado responde a una propuesta de ayudante (CP-HUB2).

El turno se pausó en `graph.py::delegation_node` porque Mia decidió por su cuenta que un
ayudante externo ayudaría. El SSE del turno emitió `awaiting_delegation` con el ayudante y
el TEXTO EXACTO que saldría del computador. Aquí el abogado contesta, y el turno SIGUE en la
misma respuesta SSE hasta donde iba (el borrador, o la respuesta del proyecto): decidir
sobre el ayudante no le cuesta el turno.

Es el mismo mecanismo del gate del borrador (decisión #11: `Command(resume=...)` + SSE), no
uno nuevo. La diferencia son las dos comprobaciones que impiden que las dos pausas del turno
se confundan entre sí:
  · `require_awaiting_delegation` — 409 si lo que espera NO es una propuesta de ayudante.
    Sin esto, aprobar un ayudante podría reanudar el gate del borrador.
  · La `huella` — el abogado aprueba UN texto, no "lo que sea que esté pendiente". Si la que
    manda la pantalla no es la del plan que vive en el checkpoint, se rechaza: aprobó otra
    cosa (una pestaña vieja, una propuesta anterior). Fail-closed.

CONTRATO CON LA PANTALLA (§G: sin jerga; el abogado nunca ve 'interrupt', 'checkpoint'…):
  POST /matters/{id}/delegation/aprobar   {"huella": "...", "recordar": false}
  POST /matters/{id}/delegation/descartar {}                → siempre disponible, sin huella
  GET  /matters/{id}/delegation/memoria                     → qué ayudantes no vuelven a preguntar
  DELETE /matters/{id}/delegation/memoria/{slug}            → revocar (vuelve a preguntar)
"""
from __future__ import annotations

import logging

from fastapi import APIRouter, HTTPException, Request
from langgraph.types import Command
from pydantic import BaseModel
from sse_starlette.sse import EventSourceResponse

from ...agents.checkpointer import open_checkpointer
from ...agents.graph import build_matter_graph, build_project_graph
from ...agents.state import thread_id_for
from ...gateway import agent_hub, hub_memory
from ...observability import audit
from ._common import (assert_owns_matter, matter_kind, require_awaiting_delegation,
                      require_uuid, sse)
from .stream import SSE_PING_SECONDS, _stream_project_events, _stream_turn_events

router = APIRouter(tags=["matters"])
logger = logging.getLogger("mia.api.delegation")


class ApproveBody(BaseModel):
    # OBLIGATORIA: es la huella de la propuesta que la pantalla mostró (llega en el evento
    # 'awaiting_delegation'). Sin ella no se aprueba nada — aprobar a ciegas "lo que haya
    # pendiente" es exactamente lo que este endpoint existe para impedir.
    huella: str
    # "No me preguntes más por este ayudante en este asunto". Por (asunto, ayudante), nunca
    # global (ver gateway/hub_memory.py). Solo suprime la pregunta: el candado sigue.
    recordar: bool = False


async def _respond(request: Request, matter_id: str, *, aprobar: bool,
                   huella: str = "", recordar: bool = False) -> EventSourceResponse:
    tenant_id = getattr(request.state, "tenant_id", None)
    if not tenant_id:
        raise HTTPException(status_code=401, detail="Sin contexto de tenant")
    require_uuid(matter_id, "asunto")
    await assert_owns_matter(tenant_id, matter_id)  # tenant cruzado -> 401

    # El grafo con el que se reanuda tiene que ser EL MISMO con el que se pausó.
    kind = await matter_kind(tenant_id, matter_id)
    graph_builder = build_project_graph if kind == "proyecto" else build_matter_graph

    # Validación ANTES de abrir el SSE (el 409 debe ser HTTP, no un evento dentro de un
    # stream ya abierto — invariante de hitl_flow.md §6.2).
    async with open_checkpointer() as cp:
        graph = graph_builder(cp)
        cfg = {"configurable": {"thread_id": thread_id_for(tenant_id, matter_id)}}
        plan = await require_awaiting_delegation(graph, cfg)
        if aprobar and huella != plan.get("huella"):
            # La pantalla aprobó una propuesta que no es la que está pendiente. No se
            # reanuda: se le vuelve a preguntar con lo que hay.
            logger.warning("delegación: huella de aprobación no coincide (tenant=%s matter=%s)",
                           tenant_id, matter_id)
            raise HTTPException(
                status_code=409,
                detail="La propuesta cambió desde que la viste. Vuelve a revisarla.")

    # Rastro de la decisión: quién autorizó (o descartó) que un texto saliera del computador
    # es justo lo que hay que poder reconstruir después.
    await audit.record(
        "delegation_approved" if aprobar else "delegation_discarded",
        tenant_id=tenant_id, user_email=getattr(request.state, "email", None),
        entity_type="matter", entity_id=matter_id,
    )

    command = Command(resume={
        "delegacion": "aprobada" if aprobar else "descartada",
        "huella": huella,
        "recordar": bool(recordar),
    })

    async def gen():
        yield sse("thinking", "Mia está retomando el trabajo…")
        try:
            async with open_checkpointer() as cp:
                graph = graph_builder(cp)
                events = _stream_project_events if kind == "proyecto" else _stream_turn_events
                # El turno CONTINÚA por donde iba: los mismos generadores del turno normal
                # llevan el hilo hasta 'awaiting_review' (asunto) o 'reply' (proyecto). Lo
                # hecho antes de la pausa vive en el checkpoint y no se repite.
                async for ev in events(graph, command, cfg, tenant_id, matter_id,
                                       request.is_disconnected, checkpointer=cp):
                    yield ev
        except Exception:
            logger.exception("delegación: reanudar el turno falló (tenant=%s matter=%s)",
                             tenant_id, matter_id)
            yield sse("error", "Mia no pudo continuar el turno. Intenta de nuevo.")

    return EventSourceResponse(gen(), ping=SSE_PING_SECONDS)


@router.post("/matters/{matter_id}/delegation/aprobar")
async def aprobar(matter_id: str, request: Request, body: ApproveBody):
    """Autoriza que salga ESE texto hacia ESE ayudante, y sigue el turno."""
    return await _respond(request, matter_id, aprobar=True,
                          huella=body.huella, recordar=body.recordar)


@router.post("/matters/{matter_id}/delegation/descartar")
async def descartar(matter_id: str, request: Request):
    """Descarta la propuesta: no sale nada y el turno sigue con el expediente local.

    Sin huella y sin cuerpo, a propósito: decir "no" es el camino seguro y jamás puede
    quedar bloqueado por un requisito de forma. El abogado siempre puede salir de la pausa."""
    return await _respond(request, matter_id, aprobar=False)


@router.get("/matters/{matter_id}/delegation/memoria")
async def listar_memoria(matter_id: str, request: Request):
    """Ayudantes que en ESTE asunto ya no preguntan (§G: slug neutro + nombre en español)."""
    tenant_id = getattr(request.state, "tenant_id", None)
    if not tenant_id:
        raise HTTPException(status_code=401, detail="Sin contexto de tenant")
    require_uuid(matter_id, "asunto")
    await assert_owns_matter(tenant_id, matter_id)
    keys = await hub_memory.list_for_matter(tenant_id, matter_id)
    return {"ayudantes": [
        {"agente": agent_hub.CONNECTORS[k].slug,
         "nombre": agent_hub.CONNECTORS[k].display_name}
        for k in keys if k in agent_hub.CONNECTORS
    ]}


@router.delete("/matters/{matter_id}/delegation/memoria/{slug}")
async def revocar_memoria(matter_id: str, slug: str, request: Request):
    """Revoca el "no me preguntes más" de un ayudante en este asunto.

    Efecto inmediato y en la dirección segura: la próxima vez Mia vuelve a preguntar. No
    apaga el ayudante (eso es el interruptor del despacho) ni toca la política."""
    tenant_id = getattr(request.state, "tenant_id", None)
    if not tenant_id:
        raise HTTPException(status_code=401, detail="Sin contexto de tenant")
    require_uuid(matter_id, "asunto")
    await assert_owns_matter(tenant_id, matter_id)
    key = agent_hub.slug_to_key(slug)
    if key is None:
        raise HTTPException(status_code=404, detail="Ese asistente no existe.")
    await hub_memory.forget(tenant_id, matter_id, key)
    await audit.record(
        "delegation_memory_revoked", tenant_id=tenant_id,
        user_email=getattr(request.state, "email", None),
        entity_type="matter", entity_id=matter_id,
    )
    # Idempotente: revocar algo que ya no estaba es un éxito, no un 404. Lo que importa es
    # el estado final — Mia vuelve a preguntar.
    return {"ok": True, "agente": slug}
