"""Mia · api.routes.stream — SSE del turno del asunto (1d · PASO 4).

GET /matters/{matter_id}/stream?message=... abre el SSE: corre intake→analysis→
draft y emite eventos hasta que el grafo se pausa (interrupt) esperando la revisión
del abogado. El cierre (finalizing→done) lo emite el POST de aprobación
(decisión #11). El abogado nunca ve jerga técnica (§G): la capa traduce el avance
del grafo a frases del oficio.

El mensaje del abogado entra como query param `message` (GET no lleva body).
"""
from __future__ import annotations

import logging

from fastapi import APIRouter, HTTPException, Query, Request
from sse_starlette.sse import EventSourceResponse

from ...agents.checkpointer import open_checkpointer
from ...agents.graph import build_matter_graph
from ...agents.state import initial_state
from ...db import pool
from ._common import assert_owns_matter, load_profile_snapshot, prepare_new_turn, sse

router = APIRouter(tags=["matters"])
logger = logging.getLogger("mia.api.stream")


def _interrupt_value(chunk: dict) -> dict:
    try:
        return chunk["__interrupt__"][0].value or {}
    except Exception:
        return {}


@router.get("/matters/{matter_id}/stream")
async def stream_matter(
    matter_id: str,
    request: Request,
    message: str = Query(..., min_length=1),
):
    tenant_id = getattr(request.state, "tenant_id", None)
    if not tenant_id:
        raise HTTPException(status_code=401, detail="Sin contexto de tenant")
    await assert_owns_matter(tenant_id, matter_id)

    profile_snapshot = await load_profile_snapshot(tenant_id)

    # Validación de ciclo de vida ANTES de abrir el SSE (409 debe ser HTTP, no evento).
    async with open_checkpointer() as cp:
        graph = build_matter_graph(cp)
        cfg = await prepare_new_turn(cp, graph, tenant_id, matter_id)

    turn_input = initial_state(
        tenant_id, matter_id, message, profile_snapshot=profile_snapshot
    )

    async def gen():
        yield sse("thinking", "Mia está revisando el expediente…")
        try:
            async with open_checkpointer() as cp:
                graph = build_matter_graph(cp)
                async for chunk in graph.astream(turn_input, cfg, stream_mode="updates"):
                    if "__interrupt__" in chunk:
                        v = _interrupt_value(chunk)
                        # Riesgo #25: marcar el asunto como "borrador esperando revisión"
                        # (RLS activo: el tenant ya fue validado con assert_owns_matter).
                        async with pool.tenant_connection(tenant_id) as conn:
                            await conn.execute(
                                "UPDATE matters SET pending_review = true "
                                "WHERE id = %s::uuid", (matter_id,))
                        yield sse(
                            "awaiting_review",
                            v.get("message", "Borrador listo para tu aprobación."),
                            draft=v.get("draft"),
                            diagnosis=v.get("diagnosis"),
                        )
                        continue
                    for node in chunk:
                        if node == "analysis":
                            yield sse("thinking", "Mia está analizando el problema jurídico…")
                        elif node == "draft":
                            yield sse("draft_ready", "Borrador listo.")
        except Exception:
            logger.exception("stream falló (tenant=%s matter=%s)", tenant_id, matter_id)
            yield sse("error", "Mia no pudo completar el turno. Intenta de nuevo.")

    return EventSourceResponse(gen())
