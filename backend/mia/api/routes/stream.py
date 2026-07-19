"""Mia · api.routes.stream — SSE del turno del asunto (1d · PASO 4).

POST /matters/{matter_id}/stream  {message}  — camino preferido (el texto no viaja
en la URL). GET con ?message= se mantiene por compatibilidad con gates antiguos.

Abre el SSE: corre intake→analysis→draft y emite eventos hasta que el grafo se
pausa (interrupt) esperando la revisión del abogado. El cierre (finalizing→done)
lo emite el POST de aprobación (decisión #11). El abogado nunca ve jerga técnica
(§G): la capa traduce el avance del grafo a frases del oficio.
"""
from __future__ import annotations

import logging
from typing import Any, AsyncIterator, Awaitable, Callable

from fastapi import APIRouter, HTTPException, Query, Request
from pydantic import BaseModel, Field
from sse_starlette.sse import EventSourceResponse

from ...agents.checkpointer import open_checkpointer
from ...agents.context_references import expand_context_references
from ...agents.graph import (DELEGATION_INTERRUPT_KIND, PROPOSAL_PROMPT, build_matter_graph,
                             build_project_graph)
from ...agents.personas import persona_service
from ...agents.state import initial_state, thread_id_for
from ...config import MIA_CONTEXT_WINDOW
from ...db import pool
from ...observability import audit
from ...policy import budget as policy_budget
from ._common import (assert_owns_matter, load_profile_snapshot, matter_kind,
                      prepare_new_turn, sse)

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
            # CP-HUB2: el turno tiene DOS pausas. Se distinguen por el 'tipo' que cada
            # interrupt trae en su propio payload — no por el orden ni por adivinar. Una
            # propuesta de ayudante NO es un borrador: no marca pending_review (el asunto no
            # tiene nada que aprobar todavía) ni emite 'awaiting_review' (la pantalla del
            # borrador no debe abrirse con un texto que no es un borrador).
            if v.get("tipo") == DELEGATION_INTERRUPT_KIND:
                yield sse("awaiting_delegation", v.get("message", PROPOSAL_PROMPT),
                          propuesta=v.get("propuesta"))
                continue
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


# ── Bloque A (Proyectos) · turno SIN HITL ─────────────────────────────────────
# Avance del único especialista del grafo de proyecto (build_project_graph) → frases
# del oficio (§G). Sin interrupt, sin pending_review: el turno siempre corre completo
# en una sola pasada (intake → work) y termina con el evento 'reply'.
_PROJECT_NODE_PROGRESS = {
    "intake": "Mia está revisando las fuentes del proyecto…",
    "work": "Mia está trabajando…",
}


async def _stream_project_events(
    graph: Any,
    turn_input: dict,
    cfg: dict,
    tenant_id: str,
    matter_id: str,
    is_disconnected: Callable[[], Awaitable[bool]],
    checkpointer: Any = None,
) -> AsyncIterator[dict]:
    """Consume el grafo de un PROYECTO y traduce su avance a eventos SSE (§G).

    Mismo kill-on-disconnect que _stream_turn_events (CP-S3): sin consumidor no tiene
    sentido seguir gastando minutos de razonamiento. NUNCA marca pending_review (eso es
    exclusivo del flujo de asunto con HITL) ni emite 'awaiting_review'.

    CP-HUB2: un proyecto SÍ puede pausarse — no por su resultado (que no se aprueba), sino
    porque Mia proponga sacar texto del computador. El muro de confidencialidad es el mismo
    para asuntos y proyectos."""
    async for chunk in graph.astream(turn_input, cfg, stream_mode="updates"):
        if await is_disconnected():
            logger.info("stream (proyecto): navegador desconectado; se corta el turno "
                        "(tenant=%s matter=%s)", tenant_id, matter_id)
            if checkpointer is not None:
                try:
                    await checkpointer.adelete_thread(cfg["configurable"]["thread_id"])
                except Exception:  # noqa: BLE001 — la limpieza no debe tumbar el corte
                    logger.exception("stream (proyecto): no se pudo limpiar el checkpoint "
                                     "a medias (tenant=%s matter=%s)", tenant_id, matter_id)
            break
        if "__interrupt__" in chunk:
            v = _interrupt_value(chunk)
            if v.get("tipo") == DELEGATION_INTERRUPT_KIND:
                yield sse("awaiting_delegation", v.get("message", PROPOSAL_PROMPT),
                          propuesta=v.get("propuesta"))
            continue
        for node, update in chunk.items():
            if node == "work":
                # work_node lleva su texto en su propio campo 'reply' del estado (ver
                # graph.py) — aquí se traduce al contrato visible del cliente: el
                # evento SSE 'reply'.
                reply = (update or {}).get("reply") or ""
                yield sse("reply", "Mia terminó.", reply=reply)
            elif node in _PROJECT_NODE_PROGRESS:
                yield sse("thinking", _PROJECT_NODE_PROGRESS[node])


# ── H6 (Bloque A) · memoria conversacional CORTA del proyecto ─────────────────
# Sin helper de presupuesto por lista-de-mensajes en context_recovery (pensado para
# prompts monolíticos de un solo turno de asunto) — tope simple aquí: últimos N turnos
# Y un tope de caracteres, recortando por el lado VIEJO (se conservan los más recientes).
_PROJECT_HISTORY_MAX_TURNS = 6
_PROJECT_HISTORY_MAX_CHARS = 8000


def _budget_project_history(history: list) -> list[dict]:
    """Recorta el historial de un proyecto a un presupuesto sensato antes de pasarlo
    al turno nuevo. Se queda con los últimos `_PROJECT_HISTORY_MAX_TURNS` turnos y,
    dentro de esos, recorta por el lado VIEJO hasta caber en `_PROJECT_HISTORY_MAX_CHARS`
    (siempre conserva al menos el turno más reciente, aunque él solo exceda el tope)."""
    items = [h for h in (history or [])
             if isinstance(h, dict) and str(h.get("text") or "").strip()]
    items = items[-_PROJECT_HISTORY_MAX_TURNS:]
    kept: list[dict] = []
    total_chars = 0
    for item in reversed(items):  # del más reciente hacia atrás
        chars = len(str(item.get("text") or ""))
        if kept and total_chars + chars > _PROJECT_HISTORY_MAX_CHARS:
            break
        kept.append(item)
        total_chars += chars
    kept.reverse()
    return kept


async def _recover_project_history(graph: Any, tenant_id: str, matter_id: str) -> list[dict]:
    """Rescata la conversación previa de un PROYECTO antes de que `prepare_new_turn`
    borre el checkpoint del turno anterior (el grafo arranca cada turno con estado
    fresco por diseño — si no se lee AQUÍ, la memoria del turno anterior se pierde).

    Fail-open (§G): un fallo de lectura deja el turno sin memoria previa, igual que
    el comportamiento de hoy (turno fresco) — nunca tumba el turno nuevo."""
    cfg = {"configurable": {"thread_id": thread_id_for(tenant_id, matter_id)}}
    try:
        st = await graph.aget_state(cfg)
    except Exception:  # noqa: BLE001 — §G: recuperar memoria nunca tumba el turno
        logger.exception("stream (proyecto): no se pudo leer el checkpoint previo "
                         "(tenant=%s matter=%s)", tenant_id, matter_id)
        return []
    if not st or not st.values:
        return []
    return _budget_project_history(st.values.get("history") or [])


class StreamBody(BaseModel):
    message: str = Field(..., min_length=1)


@router.post("/matters/{matter_id}/stream")
async def stream_matter_post(matter_id: str, request: Request, body: StreamBody):
    """Turno por POST: el mensaje viaja en el body (no en la URL ni en logs de proxy)."""
    return await stream_matter(matter_id, request, body.message)


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

    # Bloque A: 'asunto' (comportamiento actual, INTACTO) vs 'proyecto' (sin HITL).
    # matter_id ya está validado por assert_owns_matter — la lectura va bajo RLS igual.
    kind = await matter_kind(tenant_id, matter_id)
    graph_builder = build_project_graph if kind == "proyecto" else build_matter_graph

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
    prior_history: list[dict] = []
    async with open_checkpointer() as cp:
        graph = graph_builder(cp)
        if kind == "proyecto":
            # H6: leer el checkpoint del turno anterior ANTES de que prepare_new_turn
            # lo borre — es la única ventana en la que la conversación previa existe.
            prior_history = await _recover_project_history(graph, tenant_id, matter_id)
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

    # CP-E3: persona jurídica invocada por el abogado en su mensaje (por frase). Se detecta
    # sobre el mensaje ORIGINAL (las frases de invocación están en las palabras del abogado,
    # no en la evidencia adjunta por CP-E2). El alias de motor se resuelve BAJO la política
    # activa del despacho (ContextVar del request) → nunca escala a la nube. Fail-open: si la
    # resolución falla, el turno sigue sin persona (idéntico a hoy).
    persona_state: dict | None = None
    try:
        persona = await persona_service.resolve_for_turn(tenant_id, message)
        if persona is not None:
            persona_state = persona.turn_context()
    except Exception:  # noqa: BLE001 — §G: aplicar una persona jamás tumba el turno
        logger.exception("stream: no se pudo resolver la persona (tenant=%s matter=%s)",
                         tenant_id, matter_id)

    turn_input = initial_state(
        tenant_id, matter_id, expanded_message, profile_snapshot=profile_snapshot,
        retrieval_query=retrieval_query, persona=persona_state, history=prior_history,
    )

    async def gen():
        if kind == "proyecto":
            yield sse("thinking", "Mia está revisando las fuentes del proyecto…")
        else:
            yield sse("thinking", "Mia está revisando el expediente…")
        try:
            async with open_checkpointer() as cp:
                graph = graph_builder(cp)
                if kind == "proyecto":
                    async for ev in _stream_project_events(
                        graph, turn_input, cfg, tenant_id, matter_id,
                        request.is_disconnected, checkpointer=cp,
                    ):
                        yield ev
                else:
                    async for ev in _stream_turn_events(
                        graph, turn_input, cfg, tenant_id, matter_id,
                        request.is_disconnected, checkpointer=cp,
                    ):
                        yield ev
                # TODO(pieza-4e · cierre automático a ~65%): ESTE es el punto de integración
                # exacto para un cierre auto disparado desde el backend, PERO hoy no hay aquí un
                # presupuesto de contexto que crezca: `prepare_new_turn` BORRA el checkpoint al
                # terminar el turno (_common.py: `adelete_thread` cuando el grafo llega a END),
                # así que `graph.aget_state(cfg)` no acumula la conversación entre turnos y la
                # compresión del runner es REACTIVA (solo ante CONTEXT_TOO_LONG), no un medidor
                # de llenado. El tamaño real de la conversación vive en el FRONTEND (el hilo
                # visible). Por eso el disparo automático lo hace el frontend llamando a
                # POST /api/matters/{id}/cierre con {auto: true, messages: <hilo visible>} cuando
                # detecta ~65% de llenado — misma ruta que el botón manual. Si en el futuro el
                # runner conserva un transcript persistente por sesión, invocar AQUÍ (fail-soft,
                # sin bloquear el cierre del SSE):
                #     await session_briefing.maybe_auto_cierre(tenant_id, matter_id, <messages>)
                # NO se cablea una llamada al LLM dentro del generador SSE sin una fuente real de
                # la conversación (sería inventar el mecanismo — regla dura: cero cron/heurística).
        except Exception:
            logger.exception("stream falló (tenant=%s matter=%s)", tenant_id, matter_id)
            yield sse("error", "Mia no pudo completar el turno. Intenta de nuevo.")

    return EventSourceResponse(gen(), ping=SSE_PING_SECONDS)
