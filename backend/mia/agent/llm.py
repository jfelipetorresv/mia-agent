"""Mia · agent.llm — router central call_llm(task=...) por el gateway LiteLLM.

Adaptado del patrón `call_llm(task=...)` de Hermes (hermes-ref/agent/
auxiliary_client.py). En Hermes ese archivo tiene ~5.800 líneas porque resuelve
proveedor + auth + formato para ~20 proveedores a mano. En Mia ese trabajo lo
hace LiteLLM (decisión #3): el proxy expone UN endpoint OpenAI-compatible y los
modelos se nombran por alias (litellm_config.yaml). Por eso este router es
delgado: solo mapea `task -> alias` y delega el resto al gateway.

INVARIANTE CRÍTICA (CLAUDE.md §D · decisión #7):
    call_llm(task="compression") = claude-haiku SIEMPRE. Nunca sonnet.
    Está BLOQUEADO aquí: un `model` explícito para compression se ignora.
    No cambiar sin documentar en memory/decisions.md.
"""
from __future__ import annotations

import logging
from typing import Any

from .. import config

logger = logging.getLogger("mia.agent.llm")

# task -> alias de modelo. Los alias viven en litellm_config.yaml (fuente única);
# el gateway resuelve el id real del proveedor. No poner ids largos aquí.
# Mapa COMPLETO de tareas (router principal + tareas auxiliares de AuxiliaryClient).
# Solo se referencian alias que existen hoy en litellm_config.yaml: claude-haiku,
# claude-sonnet y MIA_MODEL. Añadir una tarea con un alias inexistente sería un bug
# latente (el gateway daría 404), así que las auxiliares baratas van a claude-haiku.
_TASK_MODELS: dict[str, str] = {
    "main": config.MIA_MODEL,           # razonamiento principal del agente
    "compression": "claude-haiku",      # INVARIANTE decisión #7 — ver _LOCKED_TASKS
    "verification": "claude-sonnet",     # verificación de citas legales (findings.md)
    "title_generation": "claude-haiku",  # títulos de asunto — barato
    "session_search": "claude-haiku",    # resumen/búsqueda en la sesión — barato
    "web_extract": "claude-haiku",       # extracción de contenido web — barato
    "vision": "claude-sonnet",           # comprensión de documentos/imágenes
    "curator": "claude-sonnet",          # consolidación semántica de playbooks (3b, decisión #18)
}

# Tareas cuyo modelo es un contrato fijo: un `model` explícito NO puede cambiarlo.
_LOCKED_TASKS = frozenset({"compression"})

_DEFAULT_TASK = "main"

_client: Any = None  # openai.OpenAI — import diferido (ver _get_client)


def resolve_model(task: str | None, model: str | None = None) -> str:
    """Resuelve el alias de modelo para un `task`.

    - `compression` está bloqueado a claude-haiku (decisión #7): si llega un
      `model` distinto, se ignora a propósito y se registra un warning.
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
