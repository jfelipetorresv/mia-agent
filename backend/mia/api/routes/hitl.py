"""Mia · api.routes.hitl — aprobación del borrador por el abogado (1d · PASO 5).

POST approve | reject | edit reanudan el grafo con `Command(resume=...)` y emiten
finalizing→done en la MISMA respuesta SSE (decisión #11). Todos verifican que el
tenant del JWT es dueño del asunto ANTES de reanudar (tenant cruzado → 401,
decisión #9).
"""
from __future__ import annotations

import asyncio

from fastapi import APIRouter, HTTPException, Request
from langgraph.types import Command
from pydantic import BaseModel
from sse_starlette.sse import EventSourceResponse

from ...agents.checkpointer import open_checkpointer
from ...agents.graph import build_matter_graph
from ...agents.state import thread_id_for
from ...memory.wiki_manager import WikiManager
from ._common import assert_owns_matter, sse

router = APIRouter(tags=["matters"])


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
        async with open_checkpointer() as cp:
            graph = build_matter_graph(cp)
            cfg = {"configurable": {"thread_id": thread_id_for(tenant_id, matter_id)}}
            final_draft = None
            async for chunk in graph.astream(Command(resume=command), cfg, stream_mode="updates"):
                if "finalize" in chunk:
                    final_draft = (chunk["finalize"] or {}).get("draft")
            if command.get("decision") == "approved":
                asyncio.create_task(WikiManager().update_from_approved_matter(tenant_id, matter_id))
            yield sse("done", "Listo.", draft=final_draft, status=command.get("decision"))

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
