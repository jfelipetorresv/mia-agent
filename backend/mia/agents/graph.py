"""Mia · agents.graph — el StateGraph de un asunto: 5 nodos + HITL (1d · PASO 2).

Flujo:   intake → analysis → draft → hitl_checkpoint → finalize → END
                                         │
                                         └─ interrupt() es la PRIMERA línea del
                                            nodo (decisión #10): el grafo se pausa
                                            al ENTRAR, antes de procesar la decisión.

Nodos (async; los clientes LLM/embeddings son síncronos → se llaman vía
asyncio.to_thread para no bloquear el event loop):
  1. intake_node   — recupera documentos del asunto por RAG (RRF, RLS activo).
  2. analysis_node — diagnóstico jurídico estructurado con los documentos.
  3. draft_node    — borrador usando el perfil frozen (2a) y los playbooks (2b).
  4. hitl_checkpoint_node — interrupt(): espera la decisión del abogado.
  5. finalize_node — incorpora el feedback, finaliza y guarda la traza JSONL (2d).

DI: `MatterGraphBuilder` recibe `trace_capture` (testable). Los modelos LLM van por
el gateway (decisión #3); las llamadas usan `call_llm(task=...)` (1a/1b).
"""
from __future__ import annotations

import asyncio
import logging
import re
import time
from typing import Any, Callable, Optional

from langgraph.graph import END, START, StateGraph
from langgraph.types import interrupt

from .. import config, embeddings
from ..agent import llm
from ..agent.context_compressor import ContextCompressor
from ..agent.error_classifier import LLMErrorKind, classify_llm_error
from ..agent.turn_llm_state import TurnLLMState
from ..gateway import hub_config
from ..gateway.agent_hub import AgentHub
from ..db import pool as db_pool
from ..memory.playbook_manager import Playbook, PlaybookManager
from ..memory.tokens import estimate_tokens
from ..memory.trace_capture import TraceCapture
from ..memory import trace_search
from ..memory.skill_improver import SkillImprover
from . import context_recovery, retrieval
from .state import MatterState

logger = logging.getLogger("mia.agents.graph")

# Retiene las tasks fire-and-forget de skill_improver (H.4) para que no las recoja el GC
# antes de terminar (lección de la sesión smoke: no usar create_task suelto).
_BG_TASKS: set = set()


async def drain_bg_tasks() -> None:
    """Espera a las tareas fire-and-forget en vuelo (skill_improver) antes de cerrar el loop.

    C.4: lo llama el shutdown del lifespan (api/main.py) ANTES de cerrar el pool, para que las
    propuestas a medio escribir terminen y no se pierdan silenciosamente en el apagado."""
    if _BG_TASKS:
        await asyncio.gather(*list(_BG_TASKS), return_exceptions=True)

_WORD = re.compile(r"\w+", re.UNICODE)
_MAX_ACTIVE_PLAYBOOKS = 3

# ── Prompts de sistema (Civil Law · §G: sin jerga técnica hacia el usuario) ──

ANALYSIS_SYSTEM = (
    "Eres Mia, agente jurídica del Civil Law hispanoamericano. Analiza el problema "
    "jurídico del abogado con los documentos del expediente. Estructura: (1) hechos "
    "relevantes, (2) problema jurídico, (3) fundamentos de derecho con sus fuentes, "
    "(4) conclusión y recomendación. Nunca inventas normas ni sentencias: lo que no "
    "puedas verificar contra su fuente, márcalo con [VERIFICAR]."
)

DRAFT_SYSTEM = (
    "Eres Mia. Redacta el borrador del escrito jurídico a partir del diagnóstico, el "
    "perfil del despacho y los playbooks aplicables. Tono profesional del oficio. "
    "Marca con [VERIFICAR] cualquier cita que no esté confirmada. Es un borrador para "
    "que el abogado lo apruebe."
)

EDIT_SYSTEM = (
    "Eres Mia. Incorpora al borrador las indicaciones del abogado, conservando lo que "
    "no se pidió cambiar. Devuelve el borrador corregido completo."
)


def _last_user_message(state: MatterState) -> str:
    for m in reversed(state.get("messages") or []):
        if isinstance(m, dict) and m.get("role") == "user":
            return m.get("content", "")
    return ""


def _render_soul(snapshot: Optional[dict]) -> str:
    """Texto del SOUL.md del despacho (identidad del agente), o '' si no hay onboarding."""
    if not snapshot:
        return ""
    return str(snapshot.get("content") or "").strip()


def _system_with_soul(state: MatterState, base_system: str) -> str:
    """Antepone la identidad (SOUL.md, Módulo 5) al system prompt del nodo, si existe.

    Sin SOUL.md (soul_snapshot None) devuelve el system base sin cambios → el flujo del
    grafo (y el gate 1d) se comporta igual que antes. Con SOUL.md, la identidad del
    despacho encabeza el prompt para que el análisis y el borrador hablen con su voz.
    """
    soul = _render_soul(state.get("soul_snapshot"))
    if not soul:
        return base_system
    return ("Esta es tu identidad y la voz del despacho (SOUL.md). Razona y redacta "
            "conforme a ella:\n\n" + soul + "\n\n---\n\n" + base_system)


def _tokenize(text: str) -> set[str]:
    return {w.lower() for w in _WORD.findall(text) if len(w) >= 4}


def _score_playbook(row: dict, tokens: set[str]) -> int:
    blob = f"{row.get('title', '')} {row.get('summary', '')} {row.get('applies_when', '')}"
    return len(tokens & _tokenize(blob))


def _select_playbook_ids(rows: list[dict], query: str, *, max_n: int = _MAX_ACTIVE_PLAYBOOKS) -> list[str]:
    """Heurística ligera: activa los playbooks cuyo índice solapa con la consulta."""
    tokens = _tokenize(query)
    if not tokens or not rows:
        return []
    scored = [(str(r["id"]), _score_playbook(r, tokens)) for r in rows]
    scored.sort(key=lambda item: -item[1])
    return [pid for pid, score in scored[:max_n] if score >= 1]


async def _prepare_playbooks(state: MatterState, diagnosis: str) -> tuple[str, str, list[str]]:
    """Carga índice + activa playbooks relevantes. Devuelve (índice, activos, ids)."""
    tenant_id = state["tenant_id"]
    mgr = PlaybookManager(pool=db_pool, tenant_id=tenant_id)
    index = await mgr.get_index(tenant_id)
    if not index:
        return "", "", []

    rows = await mgr.list_active(tenant_id)
    for row in rows:
        mgr.register(Playbook(
            id=str(row["id"]),
            title=row["title"],
            summary=row["summary"],
            applies_when=row["applies_when"],
            content=row["content"],
        ))

    query = f"{_last_user_message(state)}\n{diagnosis}"
    activated = _select_playbook_ids(rows, query)
    for pid in activated:
        mgr.activate(pid)
        await mgr.mark_used(pid, tenant_id)

    return index, mgr.render_active(), activated


def _render_profile(p: Optional[dict]) -> str:
    if not p:
        return "(sin perfil cargado)"
    if p.get("text"):
        return str(p["text"])
    parts = []
    if p.get("abogado"):
        parts.append("Perfil del abogado:\n" + str(p["abogado"]))
    if p.get("despacho"):
        parts.append("Perfil del despacho:\n" + str(p["despacho"]))
    return "\n\n".join(parts) or "(sin perfil cargado)"


def _accum_usage(md: dict, usage: Any) -> None:
    """Acumula el uso de tokens (si la respuesta lo trae) en md['usage']."""
    if usage is None:
        return

    def g(u: Any, *names: str) -> int:
        for n in names:
            v = u.get(n) if isinstance(u, dict) else getattr(u, n, None)
            if v is not None:
                return int(v)
        return 0

    cur = md.get("usage") or {"prompt": 0, "completion": 0, "total": 0}
    cur["prompt"] += g(usage, "prompt_tokens", "prompt")
    cur["completion"] += g(usage, "completion_tokens", "completion")
    cur["total"] += g(usage, "total_tokens", "total")
    md["usage"] = cur


class MatterGraphBuilder:
    """Construye el grafo del asunto. `trace_capture` se inyecta para los tests."""

    def __init__(self, trace_capture: Optional[TraceCapture] = None,
                 agent_hub: Optional[AgentHub] = None) -> None:
        self.trace_capture = trace_capture or TraceCapture()
        self.hub = agent_hub or AgentHub()
        # H.5: compresor para el rescate CONTEXT_TOO_LONG (una vez por turno, ver _llm).
        self._compressor = ContextCompressor(trace_capture=self.trace_capture)

    async def _maybe_delegate(self, state: MatterState) -> Optional[str]:
        """Delegación OPCIONAL a un CLI externo (1e · PASO 4). OFF salvo que:
        (a) `state.metadata['delegate'] = {'agent': <key>, 'prompt'?: str}` (señal
        explícita puesta por una capa superior), Y (b) el tenant tenga ese agente
        habilitado (hub_config). Si no, devuelve None (transparente al abogado). El
        CLI corre en hilo aparte (subprocess síncrono)."""
        req = (state.get("metadata") or {}).get("delegate")
        if not isinstance(req, dict):
            return None
        agent_key = req.get("agent")
        if not agent_key or not await hub_config.is_enabled(state["tenant_id"], agent_key):
            return None
        prompt = req.get("prompt") or _last_user_message(state)
        return await asyncio.to_thread(self.hub.invoke, agent_key, prompt, state["tenant_id"])

    async def _llm(self, messages: list[dict], *, task: str = "main",
                   state: Optional[MatterState] = None, md: Optional[dict] = None,
                   shrink: Optional[Callable[[], list[dict]]] = None) -> tuple[str, Any]:
        """Llama al LLM por el gateway (cadena de fallback H.5) sin bloquear el event loop.

        Ya NO se fija `model`: call_llm recorre la cadena del task (claude-sonnet→mia-local para
        'main'). Si el prompt excede la ventana (CONTEXT_TOO_LONG) y aún no se comprimió en este
        turno (TurnLLMState en md['llm_turn']), reduce UNA vez y reintenta desde el primer
        proveedor de la cadena. El resto de errores se propaga tal cual (LLMError con su kind).

        CP1 (Riesgo #33): `shrink` es un callable SIN args que devuelve los messages REDUCIDOS.
        Los nodos con prompt monolítico de 2 mensajes (analysis/draft) lo pasan para recortar su
        MATERIAL (documentos/diagnóstico/playbooks) — ContextCompressor no puede reducir 2
        mensajes (protege first=5/last=30). Sin `shrink`, se conserva el camino del compresor
        (nodos con historial, p. ej. finalize/EDIT). Ambos caminos consumen el mismo cupo
        una-sola-compresión-por-turno (turn.mark_compressed())."""
        try:
            resp = await asyncio.to_thread(llm.call_llm, messages, task=task)
        except Exception as exc:  # noqa: BLE001 — solo rescatamos CONTEXT_TOO_LONG; el resto re-lanza
            kind = exc.kind if isinstance(exc, llm.LLMError) else classify_llm_error(exc)
            turn = TurnLLMState.from_dict((md or {}).get("llm_turn"))
            turn.last_error_kind = kind
            if md is not None:
                md["llm_turn"] = turn.to_dict()
            if md is None or not turn.should_compress(kind):
                raise  # no es contexto, ya se comprimió, o no hay md donde coordinar → propaga
            if shrink is not None:
                # CP1 (Riesgo #33): el nodo reconstruye su prompt con el material recortado.
                reduced = shrink()
                # Guard (revisión CP1-H1): si el recorte no redujo nada (p. ej. sin
                # documentos que recortar), el reintento fallaría idéntico — propagar
                # sin quemar el cupo de compresión ni una llamada LLM extra.
                before = sum(estimate_tokens(m.get("content", "")) for m in messages)
                after = sum(estimate_tokens(m.get("content", "")) for m in reduced)
                if after >= before:
                    logger.warning("call_llm context_too_long (task=%s): el shrink del nodo "
                                   "no redujo el prompt (%d→%d tok est.) — se propaga sin reintento",
                                   task, before, after)
                    raise
            else:
                reduced = await asyncio.to_thread(
                    self._compressor.compress, messages, config.MIA_CONTEXT_WINDOW,
                    tenant_id=(state or {}).get("tenant_id"),
                    matter_id=(state or {}).get("matter_id"),
                )
            turn.mark_compressed()
            md["llm_turn"] = turn.to_dict()
            logger.warning("call_llm context_too_long (task=%s) → contexto %s, reintento "
                           "desde el 1er proveedor de la cadena", task,
                           "recortado por el nodo" if shrink is not None else "comprimido")
            resp = await asyncio.to_thread(llm.call_llm, reduced, task=task)
        content = resp.choices[0].message.content or ""
        return content, getattr(resp, "usage", None)

    # ── 1 · intake ──────────────────────────────────────────────────────────
    async def intake_node(self, state: MatterState) -> dict:
        msg = _last_user_message(state)
        # Sin documentos indexados no hay nada que recuperar: evitamos la llamada
        # a embeddings (Voyage) por completo. Si los hay, embebemos y hacemos RRF.
        if await retrieval.matter_has_chunks(state["tenant_id"], state["matter_id"]):
            vecs = await asyncio.to_thread(embeddings.embed_texts, [msg])
            qvec = vecs[0] if vecs else [0.0] * config.EMBED_DIM
            docs = await retrieval.retrieve_rrf(state["tenant_id"], state["matter_id"], msg, qvec)
        else:
            docs = []
        md = dict(state.get("metadata") or {})
        if "turn_started_at" not in md:
            md["turn_started_at"] = time.perf_counter()
        # H.5: estado LLM del turno (cadena de fallback + compresión) se crea en el nodo de
        # contexto (intake) y viaja por metadata para que analysis/draft comprriman UNA sola vez.
        md.setdefault("llm_turn", TurnLLMState().to_dict())
        md.update(stage="intake", retrieved=len(docs))
        delegation = await self._maybe_delegate(state)  # no-op salvo señal + habilitado
        if delegation is not None:
            md["delegation"] = delegation
        return {"documents": docs, "metadata": md}

    # ── 2 · analysis ────────────────────────────────────────────────────────
    async def analysis_node(self, state: MatterState) -> dict:
        msg = _last_user_message(state)
        docs = state.get("documents") or []
        md = dict(state.get("metadata") or {})

        def _messages(doc_list: list) -> list[dict]:
            ctx = "\n\n".join(f"[doc {i + 1}] {d['content']}" for i, d in enumerate(doc_list)) or \
                "(sin documentos recuperados del expediente)"
            return [
                {"role": "system", "content": _system_with_soul(state, ANALYSIS_SYSTEM)},
                {"role": "user", "content": f"Consulta del abogado:\n{msg}\n\nExpediente:\n{ctx}"},
            ]

        def _shrink() -> list[dict]:
            # CP1 (Riesgo #33): ante CONTEXT_TOO_LONG se reconstruye el prompt con los
            # documentos recortados (menos docs + contenido truncado al presupuesto).
            # (futuro) si el estado trae `knowledge`, recortarlo AQUÍ antes que documents.
            budget = context_recovery.budget_for("analysis", config.MIA_CONTEXT_WINDOW)
            return _messages(context_recovery.shrink_documents(docs, budget))

        diagnosis, usage = await self._llm(
            _messages(docs), task="main", state=state, md=md, shrink=_shrink)
        md.update(stage="analysis", diagnosis=diagnosis)
        _accum_usage(md, usage)
        return {"metadata": md}

    # ── 3 · draft ───────────────────────────────────────────────────────────
    async def draft_node(self, state: MatterState) -> dict:
        md_in = state.get("metadata") or {}
        diagnosis = md_in.get("diagnosis", "")
        profile_txt = _render_profile(state.get("profile_snapshot"))
        pb_index, pb_active, activated = await _prepare_playbooks(state, diagnosis)
        pb_parts = [p for p in (pb_index, pb_active) if p]
        playbook_txt = "\n\n".join(pb_parts)
        user_parts = [f"Diagnóstico:\n{diagnosis}", profile_txt]
        if playbook_txt:
            user_parts.append(playbook_txt)
        user_parts.append("Redacta el borrador del escrito.")
        md = dict(md_in)

        def _messages(parts: list[str]) -> list[dict]:
            return [
                {"role": "system", "content": _system_with_soul(state, DRAFT_SYSTEM)},
                {"role": "user", "content": "\n\n".join(parts)},
            ]

        def _shrink() -> list[dict]:
            # CP1 (Riesgo #33): PRIMERO se descartan los playbooks activos (queda solo el
            # índice con marcador) y LUEGO se recorta el diagnóstico preservando su FINAL
            # (la conclusión/recomendación del análisis va al final).
            budget = context_recovery.budget_for("draft", config.MIA_CONTEXT_WINDOW)
            pb_small = (pb_index + "\n" + context_recovery.PLAYBOOKS_TRIMMED_MARKER) \
                if pb_index else ""
            diag_small = context_recovery.shrink_text(diagnosis, budget, protect_tail=True)
            parts = [f"Diagnóstico:\n{diag_small}", profile_txt]
            if pb_small:
                parts.append(pb_small)
            parts.append("Redacta el borrador del escrito.")
            return _messages(parts)

        draft, usage = await self._llm(
            _messages(user_parts), task="main", state=state, md=md, shrink=_shrink)
        md["stage"] = "draft"
        md["activated_playbooks"] = activated
        _accum_usage(md, usage)
        return {"draft": draft, "hitl_status": "pending", "metadata": md}

    # ── 4 · hitl_checkpoint (interrupt PRIMERO, decisión #10) ────────────────
    async def hitl_checkpoint_node(self, state: MatterState) -> dict:
        # interrupt() ES LA PRIMERA LÍNEA: el grafo se pausa al ENTRAR al nodo,
        # antes de procesar nada. El valor surge a la capa SSE como 'awaiting_review'.
        decision = interrupt({
            "message": "Borrador listo para tu aprobación.",
            "draft": state.get("draft"),
        })
        # --- de aquí en adelante solo corre TRAS reanudar con Command(resume=...) ---
        dec = (decision or {}).get("decision")
        if dec not in ("approved", "rejected", "editing"):
            dec = "rejected"  # fail-closed: sin decisión válida no se aprueba
        status = dec
        md = dict(state.get("metadata") or {})
        md["hitl_decision"] = decision
        return {"hitl_status": status, "metadata": md}

    # ── 5 · finalize ─────────────────────────────────────────────────────────
    async def finalize_node(self, state: MatterState) -> dict:
        status = state.get("hitl_status", "approved")
        decision = (state.get("metadata") or {}).get("hitl_decision") or {}
        draft = state.get("draft") or ""
        md = dict(state.get("metadata") or {})

        if status == "editing":
            final, usage = await self._llm([
                {"role": "system", "content": _system_with_soul(state, EDIT_SYSTEM)},
                {"role": "user", "content": f"Borrador:\n{draft}\n\nIndicaciones del abogado:\n"
                                            f"{decision.get('edits', '')}\n\nDevuelve el borrador corregido."},
            ], task="main", state=state, md=md)
            _accum_usage(md, usage)
        else:
            # approved / rejected: se conserva el borrador (el rechazo queda en la traza).
            final = draft

        # Señales HITL para el Feedback processor (3e, decisión #19): la traza v2 registra
        # el desenlace, el borrador original vs. final y los documentos recuperados.
        _OUTCOME = {"approved": "approved", "rejected": "rejected", "editing": "edited"}
        retrieved_doc_ids = [d["id"] for d in (state.get("documents") or [])
                             if isinstance(d, dict) and d.get("id")]
        started = md.get("turn_started_at")
        if started is not None:
            md["latency_ms"] = (time.perf_counter() - float(started)) * 1000
        activated = md.get("activated_playbooks") or []
        trace = self.trace_capture.capture(
            tenant_id=state["tenant_id"],
            matter_id=state["matter_id"],
            input=_last_user_message(state),
            output=final,
            model=config.MIA_MODEL,
            tokens=md.get("usage", {"prompt": 0, "completion": 0, "total": 0}),
            latency_ms=float(md.get("latency_ms", 0.0)),
            hitl_outcome=_OUTCOME.get(status, "approved"),
            draft_original=draft,
            draft_final=final,
            retrieved_doc_ids=retrieved_doc_ids,
            activated_playbooks=activated or None,
        )
        trace_id = f"{state['tenant_id']}:{state['matter_id']}:{trace.timestamp}"
        # Dual-write H.3: además del JSONL (SFT), indexa la traza en Postgres para session_search
        # (FTS sin LLM). Best-effort: un fallo aquí (tabla ausente, DB) NO debe tumbar el turno.
        try:
            await trace_search.index_trace(
                state["tenant_id"],
                matter_id=state["matter_id"],
                input=_last_user_message(state),
                output=final,
                model=config.MIA_MODEL,
                hitl_outcome=_OUTCOME.get(status, "approved"),
                activated_playbooks=activated,
                retrieved_doc_ids=retrieved_doc_ids,
                trace_ts=trace.timestamp,
            )
        except Exception:  # noqa: BLE001 — indexado best-effort, no crítico para el turno
            logger.debug("index_trace falló (best-effort); la traza JSONL sí se escribió", exc_info=True)

        # H.4 skill self-improving: tras registrar la traza, extrae un patrón reutilizable y (si
        # aplica) propone una mejora de playbook con status=pending (HITL). FIRE-AND-FORGET: no
        # bloquea el turno; la task se retiene en _BG_TASKS y process_trace_safe nunca propaga.
        try:
            task = asyncio.create_task(
                SkillImprover().process_trace_safe(state["tenant_id"], trace.to_dict()))
            _BG_TASKS.add(task)
            task.add_done_callback(_BG_TASKS.discard)
        except Exception:  # noqa: BLE001 — lanzar la task es best-effort
            logger.debug("no se pudo lanzar skill_improver (best-effort)", exc_info=True)
        md.update(stage="finalize", final_status=status)
        return {
            "draft": final,
            "trace_id": trace_id,
            "messages": [{"role": "assistant", "content": final}],
            "metadata": md,
        }

    # ── ensamblaje ───────────────────────────────────────────────────────────
    def build(self, checkpointer: Any):
        """Compila el grafo con el checkpointer (AsyncPostgresSaver en runtime)."""
        g = StateGraph(MatterState)
        g.add_node("intake", self.intake_node)
        g.add_node("analysis", self.analysis_node)
        g.add_node("draft", self.draft_node)
        g.add_node("hitl_checkpoint", self.hitl_checkpoint_node)
        g.add_node("finalize", self.finalize_node)

        g.add_edge(START, "intake")
        g.add_edge("intake", "analysis")
        g.add_edge("analysis", "draft")
        g.add_edge("draft", "hitl_checkpoint")
        g.add_edge("hitl_checkpoint", "finalize")
        g.add_edge("finalize", END)

        return g.compile(checkpointer=checkpointer)


def build_matter_graph(checkpointer: Any, *, trace_capture: Optional[TraceCapture] = None,
                       agent_hub: Optional[AgentHub] = None):
    """Atajo: construye el grafo del asunto con el checkpointer dado."""
    return MatterGraphBuilder(trace_capture, agent_hub).build(checkpointer)
