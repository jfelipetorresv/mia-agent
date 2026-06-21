"""Mia · agent.llm — router central call_llm(task=...) por el gateway LiteLLM.

Adaptado del patrón `call_llm(task=...)` de Hermes (hermes-ref/agent/
auxiliary_client.py). En Hermes ese archivo tiene ~5.800 líneas porque resuelve
proveedor + auth + formato para ~20 proveedores a mano. En Mia ese trabajo lo
hace LiteLLM (decisión #3): el proxy expone UN endpoint OpenAI-compatible y los
modelos se nombran por alias (litellm_config.yaml). Por eso este router es
delgado: solo mapea `task -> alias` y delega el resto al gateway.

OVERRIDE 2026-06-20 (sin créditos Anthropic · anula parcialmente la decisión #7):
    Las tareas soul / curator / title_generation / verification apuntan a mia-local.
    `compression` NO tiene fallback en call_llm, así que también va a mia-local; sigue
    BLOQUEADA en _LOCKED_TASKS (un `model` explícito se ignora), solo cambia el destino
    fijo: mia-local en vez de claude-haiku. Revertir a claude-haiku/claude-sonnet cuando
    haya créditos. Documentar el cambio de la invariante #7 en memory/decisions.md.
"""
from __future__ import annotations

import logging
from typing import Any

from .. import config

logger = logging.getLogger("mia.agent.llm")

# task -> alias de modelo. Los alias viven en litellm_config.yaml (fuente única);
# el gateway resuelve el id real del proveedor. No poner ids largos aquí.
# Mapa COMPLETO de tareas (router principal + tareas auxiliares de AuxiliaryClient).
# OVERRIDE 2026-06-20 (decisión #23): TODOS los tasks -> mia-local (cuenta Anthropic sin
# créditos en desarrollo). Revertir a claude-haiku/claude-sonnet cuando haya créditos.
_TASK_MODELS: dict[str, str] = {
    "main": config.MIA_MODEL,            # razonamiento principal del agente (mia-local)
    "compression": "mia-local",          # antes claude-haiku; sin fallback -> mia-local. Sigue en _LOCKED_TASKS
    "verification": "mia-local",          # verificación de citas legales -> mia-local
    "title_generation": "mia-local",      # títulos de asunto -> mia-local
    "session_search": "mia-local",        # resumen/búsqueda en la sesión -> mia-local
    "web_extract": "mia-local",           # extracción de contenido web -> mia-local
    "vision": "mia-local",                # comprensión de documentos/imágenes -> mia-local
    "curator": "mia-local",              # consolidación semántica de playbooks -> mia-local
    "soul": "mia-local",                 # generación del SOUL.md — la identidad del agente -> mia-local
}

# Tareas cuyo modelo es un contrato fijo: un `model` explícito NO puede cambiarlo.
_LOCKED_TASKS = frozenset({"compression"})

_DEFAULT_TASK = "main"

_client: Any = None  # openai.OpenAI — import diferido (ver _get_client)


def resolve_model(task: str | None, model: str | None = None) -> str:
    """Resuelve el alias de modelo para un `task`.

    - `compression` está bloqueado (decisión #7, override 2026-06-20 → mia-local):
      si llega un `model` distinto, se ignora a propósito y se registra un warning.
    - Resto de tareas: un `model` explícito gana; si no, el del mapa; un task
      desconocido cae a 'main'.
    """
    if task in _LOCKED_TASKS:
        locked = _TASK_MODELS[task]
        if model and model != locked:
            logger.warning(
                "task=%s está bloqueado a %s (decisión #7); se ignora model=%s",
                task, locked, model,
            )
        return locked
    if model:
        return model
    return _TASK_MODELS.get(task or _DEFAULT_TASK, _TASK_MODELS[_DEFAULT_TASK])


def _get_client() -> Any:
    """Cliente OpenAI apuntado al proxy LiteLLM. Import diferido (como embeddings.py)."""
    global _client
    if _client is None:
        from openai import OpenAI  # diferido: solo al primer call_llm real

        _client = OpenAI(base_url=config.LITELLM_BASE_URL, api_key=config.LITELLM_API_KEY)
    return _client


def call_llm(
    messages: list[dict],
    *,
    task: str | None = None,
    model: str | None = None,
    temperature: float | None = None,
    max_tokens: int | None = None,
    tools: list | None = None,
    **extra: Any,
) -> Any:
    """Llamada LLM central y síncrona a través del gateway LiteLLM.

    Devuelve la respuesta OpenAI-compatible (usar resp.choices[0].message.content).
    `task` elige el modelo (ver resolve_model); `model` lo sobre-escribe salvo en
    tareas bloqueadas. Mantén la firma estable: 1b añadirá streaming y fallbacks.
    """
    resolved = resolve_model(task, model)
    kwargs: dict[str, Any] = {"model": resolved, "messages": messages}
    if temperature is not None:
        kwargs["temperature"] = temperature
    if max_tokens is not None:
        kwargs["max_tokens"] = max_tokens
    if tools:
        kwargs["tools"] = tools
    kwargs.update(extra)
    return _get_client().chat.completions.create(**kwargs)
