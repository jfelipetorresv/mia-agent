"""Mia · agent.core — MiaAgent, el núcleo del agente legal cognitivo.

Adaptado del patrón de Hermes (hermes-ref/agent): un agente con system prompt
estable (prefix cacheado) + historial de conversación que llama al LLM a través
de call_llm(). En 1a el núcleo es deliberadamente mínimo — identidad + un turno
de conversación — para fijar las costuras sin adelantar trabajo:

  · system prompt de 10 capas (stable/context/volatile) → 1b
  · plugins (6 hooks)                                    → 1c
  · LangGraph StateGraph + SSE + HITL                    → 1d
  · Agent Hub (CLIs externos)                            → 1e

Multi-tenant: cada MiaAgent se ata a un `tenant_id` (aislamiento RLS, §G). El
núcleo no toca la DB todavía, pero lleva el tenant para que 1b+ no reescriban
la firma.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any

from .. import config
from . import llm, prompt_builder
from .context_compressor import ContextCompressor
from .plugins import PluginManager

logger = logging.getLogger("mia.agent.core")

# Identidad base de Mia (capa 1 del futuro prompt de 10 capas). Sustituible por
# SOUL.md cuando exista (Módulo 5); en 1a es el valor por defecto.
DEFAULT_IDENTITY = (
    "Eres Mia, una agente juridica cognitiva para despachos de abogados del "
    "Civil Law hispanoamericano. Razonas sobre expedientes, citas fuentes "
    "primarias verificables y entregas diagnosticos y borradores para que un "
    "abogado los apruebe. Eres precisa y prudente: nunca inventas citas legales "
    "— si no puedes verificar una norma o sentencia, lo dices explicitamente."
)


@dataclass
class MiaAgent:
    """Núcleo del agente atado a un tenant. Arma su prompt con las 10 capas (1b)."""

    tenant_id: str
    identity: str = DEFAULT_IDENTITY
    # None (NO un default a config.MIA_MODEL): un `model` explícito viaja como override a
    # call_llm y SALTA toda la política de modelo (resolve_fallback_chain) — incluida la
    # muralla de confidencialidad (un tenant 'soberano' JAMÁS debe salir a la nube por un
    # override colado). Con None gobierna la POLÍTICA activa (revisión capa 2, MENOR 2).
    # Un caller que de veras quiera forzar un alias puede fijarlo a conciencia.
    model: str | None = None
    messages: list[dict] = field(default_factory=list)

    # Costuras que leen las 10 capas del prompt_builder. Vacías hoy; las llenan
    # los módulos posteriores (tools 1c/1d · matter · skills · memoria 2a/2b).
    system_message: str | None = None      # L8 · instrucciones de la sesión
    matter_context: str | None = None      # L7 · contexto del asunto
    tool_names: list[str] = field(default_factory=list)  # L4 · herramientas
    skills_index: str | None = None        # L6 · índice de skills
    memory_block: str | None = None        # L9 · memoria/playbook del despacho

    # Compresión de contexto (2c). `context_window` = ventana del modelo principal;
    # `compressor` se arma en __post_init__ con el trace_capture del agente (si lo hay).
    context_window: int = field(default_factory=lambda: config.MIA_CONTEXT_WINDOW)
    matter_id: str | None = None
    trace_capture: Any = None
    compressor: ContextCompressor | None = None

    # Sistema de plugins (1c): 6 hooks de ciclo de vida. Vacío por defecto, así que
    # disparar un hook sin plugins registrados es no-op (el turno no cambia).
    plugins: PluginManager = field(default_factory=PluginManager)

    # Prompt cacheado por sesión: se arma una vez y se reutiliza entre turnos para
    # mantener caliente el prefix cache del gateway (decisión #3). invalidate() lo
    # resetea tras una compresión de contexto.
    _cached_system_prompt: str | None = field(default=None, repr=False)

    def __post_init__(self) -> None:
        if self.compressor is None:
            self.compressor = ContextCompressor(trace_capture=self.trace_capture)
        # SOUL.md (Módulo 5): la capa 1 (identidad) se toma del SOUL.md del despacho si
        # existe ($MIA_HOME/soul_{tenant_id}.md). Sin onboarding, queda DEFAULT_IDENTITY
        # (el placeholder). Solo sustituye cuando el caller NO pasó una identidad propia.
        if self.identity == DEFAULT_IDENTITY:
            from ..onboarding.soul_interview import load_soul_text  # diferido (sin ciclo)
            soul = load_soul_text(self.tenant_id)
            if soul:
                self.identity = soul

    def _system_prompt(self) -> str:
        """System prompt del turno (10 capas), cacheado por sesión."""
        if self._cached_system_prompt is None:
            self._cached_system_prompt = prompt_builder.build_system_prompt(self)
        return self._cached_system_prompt

    def invalidate_prompt(self) -> None:
        """Fuerza el rebuild del prompt en el próximo turno (tras compresión, 2c)."""
        prompt_builder.invalidate(self)

    def run_turn(self, user_text: str, *, temperature: float | None = None) -> str:
        """Ejecuta un turno: añade el mensaje del usuario, llama al LLM (task='main'),
        guarda la respuesta en el historial y la devuelve.

        Dispara los hooks de plugin `pre_llm_call` (puede modificar mensajes/model/
        temperature) y `post_llm_call` (puede reescribir el texto). Sin plugins
        registrados ambos son no-op y el turno se comporta igual que en 1a/1b.
        """
        self.messages.append({"role": "user", "content": user_text})

        # Compresión de contexto (2c) ANTES del turno — transparente al abogado (no SSE).
        self.messages = self.compressor.compress(
            self.messages, self.context_window,
            tenant_id=self.tenant_id, matter_id=self.matter_id,
        )
        if self.compressor.last_compressed:
            logger.info("turno: contexto comprimido %d -> %d tokens (ahorro %.0f%%)",
                        self.compressor.last_tokens_before, self.compressor.last_tokens_after,
                        self.compressor.last_savings_pct)

        ctx = {
            "messages": [{"role": "system", "content": self._system_prompt()}, *self.messages],
            "task": "main",
            "model": self.model,
            "temperature": temperature,
        }
        self.plugins.dispatch("pre_llm_call", ctx)

        resp = llm.call_llm(
            ctx["messages"],
            task=ctx["task"],
            model=ctx["model"],
            temperature=ctx["temperature"],
        )
        content = resp.choices[0].message.content or ""

        ctx["response"] = resp
        ctx["content"] = content
        self.plugins.dispatch("post_llm_call", ctx)
        content = ctx["content"]  # un plugin pudo reescribir la respuesta

        self.messages.append({"role": "assistant", "content": content})
        return content

    def start_session(self) -> dict:
        """Dispara `on_session_start`. Lo llama el dueño de la sesión (1d / CLI)."""
        return self.plugins.dispatch("on_session_start", {"agent": self})

    def end_session(self) -> dict:
        """Dispara `on_session_end`. Lo llama el dueño de la sesión (1d / CLI)."""
        return self.plugins.dispatch("on_session_end", {"agent": self})
