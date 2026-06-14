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
from typing import Any, Optional

from langgraph.graph import END, START, StateGraph
from langgraph.types import interrupt

from .. import config, embeddings
from ..agent import llm
from ..gateway import hub_config
from ..gateway.agent_hub import AgentHub
from ..memory.trace_capture import TraceCapture
from . import retrieval
from .state import MatterState

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

    async def _llm(self, messages: list[dict], *, task: str = "main") -> tuple[str, Any]:
        """Llama al LLM por el gateway (síncrono) sin bloquear el event loop."""
        resp = await asyncio.to_thread(llm.call_llm, messages, task=task, model=config.MIA_MODEL)
        content = resp.choices[0].message.content or ""
        return content, getattr(resp, "usage", None)

    # ── 1 · intake ──────────────────────────────────────────────────────────
    async def intake_node(self, state: MatterState) -> dict:
        msg = _last_user_message(state)
        vecs = await asyncio.to_thread(embeddings.embed_texts, [msg])
        qvec = vecs[0] if vecs else [0.0] * config.EMBED_DIM
        docs = await retrieval.retrieve_rrf(state["tenant_id"], state["matter_id"], msg, qvec)
        md = dict(state.get("metadata") or {})
        md.update(stage="intake", retrieved=len(docs))
        delegation = await self._maybe_delegate(state)  # no-op salvo señal + habilitado
        if delegation is not None:
            md["delegation"] = delegation
        return {"documents": docs, "metadata": md}

    # ── 2 · analysis ────────────────────────────────────────────────────────
    async def analysis_node(self, state: MatterState) -> dict:
        msg = _last_user_message(state)
        docs = state.get("documents") or []
        ctx = "\n\n".join(f"[doc {i + 1}] {d['content']}" for i, d in enumerate(docs)) or \
            "(sin documentos recuperados del expediente)"
        diagnosis, usage = await self._llm([
            {"role": "system", "content": ANALYSIS_SYSTEM},
            {"role": "user", "content": f"Consulta del abogado:\n{msg}\n\nExpediente:\n{ctx}"},
        ])
        md = dict(state.get("metadata") or {})
        md.update(stage="analysis", diagnosis=diagnosis)
        _accum_usage(md, usage)
        return {"metadata": md}

    # ── 3 · draft ───────────────────────────────────────────────────────────
    async def draft_node(self, state: MatterState) -> dict:
        md_in = state.get("metadata") or {}
        diagnosis = md_in.get("diagnosis", "")
        profile_txt = _render_profile(state.get("profile_snapshot"))
        draft, usage = await self._llm([
            {"role": "system", "content": DRAFT_SYSTEM},
            {"role": "user", "content": f"Diagnóstico:\n{diagnosis}\n\n{profile_txt}\n\n"
                                        "Redacta el borrador del escrito."},
        ])
        md = dict(md_in)
        md["stage"] = "draft"
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
        dec = (decision or {}).get("decision", "approved")
        status = dec if dec in ("approved", "rejected", "editing") else "approved"
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
                {"role": "system", "content": EDIT_SYSTEM},
                {"role": "user", "content": f"Borrador:\n{draft}\n\nIndicaciones del abogado:\n"
                                            f"{decision.get('edits', '')}\n\nDevuelve el borrador corregido."},
            ])
            _accum_usage(md, usage)
        else:
            # approved / rejected: se conserva el borrador (el rechazo queda en la traza).
            final = draft

        # Señales HITL para el Feedback processor (3e, decisión #19): la traza v2 registra
        # el desenlace, el borrador original vs. final y los documentos recuperados.
        _OUTCOME = {"approved": "approved", "rejected": "rejected", "editing": "edited"}
        retrieved_doc_ids = [d["id"] for d in (state.get("documents") or [])
                             if isinstance(d, dict) and d.get("id")]
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
        )
        trace_id = f"{state['tenant_id']}:{state['matter_id']}:{trace.timestamp}"
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
