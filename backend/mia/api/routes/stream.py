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
from typing import Any, AsyncIterator, Awaitable, Callable

from fastapi import APIRouter, HTTPException, Query, Request
from sse_starlette.sse import EventSourceResponse

from ...agents.checkpointer import open_checkpointer
from ...agents.context_references import expand_context_references
from ...agents.graph import build_matter_graph
from ...agents.state import initial_state
from ...config import MIA_CONTEXT_WINDOW
from ...db import pool
from ...observability import audit
from ...policy import budget as policy_budget
from ._common import assert_owns_matter, load_profile_snapshot, prepare_new_turn, sse

router = APIRouter(tags=["matters"])
logger = logging.getLogger("mia.api.stream")

# CP-S3: latido del SSE. sse-starlette envía un comentario ":ping" cada N segundos
# — mantiene viva la conexión a través de proxies durante los minutos que tarda un
# turno, y es el mecanismo con el que detecta que el navegador se fue (al fallar el
# envío, cancela el generador → se corta el turno, ver _stream_turn_events).
SSE_PING_SECONDS = 15


def _interrupt_value(chunk: dict) -> dict:
    try:
        return chunk["__interrupt__"][0].value or {}
    except Exception:
        return {}


# Avance del equipo de especialistas → frases del oficio (§G). El evento de un nodo
# llega cuando ese nodo TERMINA, así que cada mensaje anuncia el paso que ARRANCA.
_NODE_PROGRESS = {
    "intake": "Mia está estableciendo los hechos del expediente…",
    "facts": "Mia está investigando normas y jurisprudencia aplicables…",
    "research": "Mia está cruzando los hechos con el derecho…",
    "analysis": "Mia está redactando el borrador…",
    "draft": "Mia está verificando las citas del borrador…",
}


async def _stream_turn_events(
    graph: Any,
    turn_input: dict,
    cfg: dict,
    tenant_id: str,
    matter_id: str,
    is_disconnected: Callable[[], Awaitable[bool]],
    checkpointer: Any = None,
) -> AsyncIterator[dict]:
    """Consume el grafo y traduce su avance a eventos SSE (§G).

    CP-S3 (kill-on-disconnect): antes de procesar cada actualización del grafo se
    comprueba si el navegador se desconectó; si es así, se ROMPE el bucle — sin
    consumidor no tiene sentido gastar minutos de razonamiento (ni el costo del
    modelo). Extraído del endpoint para poder verificarlo con dobles en el gate.

    CP-S3 (revisión capa 2, bloqueante): el checkpointer PERSISTE el estado tras
    cada nodo. Si se corta a mitad (p. ej. tras `facts`), el thread queda con un
    nodo normal pendiente que `prepare_new_turn` confundiría con "borrador esperando
    revisión" (409 engañoso) y dejaría el asunto atascado sin salida. Por eso, al
    cortar por desconexión se BORRA el checkpoint del thread: el asunto vuelve a
    limpio y el próximo turno arranca de cero (el trabajo a medias no se guarda —
    es exactamente lo que el abogado abandonó al cerrar la pestaña)."""
    async for chunk in graph.astream(turn_input, cfg, stream_mode="updates"):
        if await is_disconnected():
            logger.info("stream: navegador desconectado; se corta el turno "
                        "(tenant=%s matter=%s)", tenant_id, matter_id)
            if checkpointer is not None:
                try:
                    await checkpointer.adelete_thread(cfg["configurable"]["thread_id"])
                except Exception:  # noqa: BLE001 — la limpieza no debe tumbar el corte
                    logger.exception("stream: no se pudo limpiar el checkpoint a medias "
                                     "(tenant=%s matter=%s)", tenant_id, matter_id)
            break
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
                diagnosis_summary=v.get("diagnosis_summary"),
                verification=v.get("verification"),
            )
            continue
        for node in chunk:
            if node in _NODE_PROGRESS:
                yield sse("thinking", _NODE_PROGRESS[node])
            elif node == "verification":
                yield sse("draft_ready", "Borrador listo.")


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

    # CP-E1: tope de gasto de IA del despacho (política activa). El turno es GET/SSE,
    # así que el bloqueo debe ser HTTP ANTES de abrir el stream (como el 409 de ciclo
    # de vida), no un evento. Fail-open: un fallo de lectura permite el turno.
    try:
        await policy_budget.enforce_budget(tenant_id)
    except policy_budget.BudgetExceeded as e:
        raise HTTPException(status_code=402, detail=str(e))

    # CP-E1: rastro de la acción (el turno del asunto es GET → no lo cubre el audit
    # genérico del middleware, que solo audita métodos mutantes).
    await audit.record(
        "matter_turn", tenant_id=tenant_id,
        user_email=getattr(request.state, "email", None),
        entity_type="matter", entity_id=matter_id,
    )

    profile_snapshot = await load_profile_snapshot(tenant_id)

    # Validación de ciclo de vida ANTES de abrir el SSE (409 debe ser HTTP, no evento).
    async with open_checkpointer() as cp:
        graph = build_matter_graph(cp)
        cfg = await prepare_new_turn(cp, graph, tenant_id, matter_id)

    # CP-E2: expandir referencias @expediente/@carpeta a evidencia sellada (RLS,
    # confinado a las filas del despacho). Después del 409 de ciclo de vida para no
    # gastar lecturas si el turno se rechaza. Fail-open: si la expansión falla, el turno
    # sigue con el mensaje tal cual (adjuntar pruebas es una ayuda, no un candado).
    expanded_message = message
    retrieval_query: str | None = None
    try:
        ref_result = await expand_context_references(
            tenant_id, message, matter_id=matter_id, context_length=MIA_CONTEXT_WINDOW)
        if ref_result.expanded:
            expanded_message = ref_result.message
            retrieval_query = ref_result.retrieval_query
    except Exception:  # noqa: BLE001 — §G: adjuntar por referencia nunca tumba el turno
        logger.exception("stream: la expansión de referencias falló (tenant=%s matter=%s)",
                         tenant_id, matter_id)

    turn_input = initial_state(
        tenant_id, matter_id, expanded_message, profile_snapshot=profile_snapshot,
        retrieval_query=retrieval_query,
    )

    async def gen():
        yield sse("thinking", "Mia está revisando el expediente…")
        try:
            async with open_checkpointer() as cp:
                graph = build_matter_graph(cp)
                async for ev in _stream_turn_events(
                    graph, turn_input, cfg, tenant_id, matter_id,
                    request.is_disconnected, checkpointer=cp,
                ):
                    yield ev
        except Exception:
            logger.exception("stream falló (tenant=%s matter=%s)", tenant_id, matter_id)
            yield sse("error", "Mia no pudo completar el turno. Intenta de nuevo.")

    return EventSourceResponse(gen(), ping=SSE_PING_SECONDS)
