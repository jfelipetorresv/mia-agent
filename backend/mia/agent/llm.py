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
import time
from typing import Any

from .. import config
from .error_classifier import (
    LLMError,
    LLMErrorKind,
    classify_llm_error,
    is_retryable,
    retry_delay,
)

logger = logging.getLogger("mia.agent.llm")

# Reintentos automáticos para errores transitorios (rate limit / timeout / red).
# Los deterministas (auth, modelo inexistente, contexto largo) NO se reintentan.
MAX_RETRIES = 3

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

    # Política de error centralizada (patrón Hermes v0.17.0, ver error_classifier.py):
    # - transitorios (rate_limit/timeout/network) → reintento con backoff exponencial;
    # - AUTH / MODEL_UNAVAILABLE / UNKNOWN → falla rápido con mensaje claro (LLMError);
    # - CONTEXT_TOO_LONG → log + propaga la excepción original (la resuelve el compresor).
    # call_llm es SÍNCRONO y se invoca vía asyncio.to_thread → time.sleep no bloquea el loop.
    last_exc: BaseException | None = None
    for attempt in range(MAX_RETRIES + 1):     # 1 intento inicial + hasta MAX_RETRIES reintentos
        try:
            return _get_client().chat.completions.create(**kwargs)
        except Exception as exc:               # noqa: BLE001 — se clasifica y re-lanza abajo
            kind = classify_llm_error(exc)
            last_exc = exc

            if kind is LLMErrorKind.CONTEXT_TOO_LONG:
                logger.warning("call_llm context_too_long (task=%s model=%s): %s",
                               task, resolved, exc)
                raise                          # propaga original: lo maneja la compresión

            if not is_retryable(kind):
                logger.error("call_llm fallo no reintentable [%s] (task=%s model=%s): %s",
                             kind.value, task, resolved, exc)
                raise LLMError(kind, _clear_message(kind, resolved)) from exc

            if attempt >= MAX_RETRIES:         # transitorio pero se agotaron los reintentos
                logger.error("call_llm agotó reintentos [%s] tras %d intentos "
                             "(task=%s model=%s): %s", kind.value, attempt + 1, task, resolved, exc)
                raise LLMError(
                    kind, f"El proveedor LLM falló ({kind.value}) tras {attempt + 1} intentos."
                ) from exc

            delay = retry_delay(kind, attempt)
            logger.warning("call_llm reintento %d/%d [%s] en %.2fs (task=%s model=%s): %s",
                           attempt + 1, MAX_RETRIES, kind.value, delay, task, resolved, exc)
            time.sleep(delay)

    # Inalcanzable (el loop siempre retorna o lanza), pero satisface el análisis estático.
    raise LLMError(LLMErrorKind.UNKNOWN, "call_llm terminó sin resultado") from last_exc


def _clear_message(kind: LLMErrorKind, model: str) -> str:
    """Mensaje claro (en español, sin jerga técnica de proveedor) por tipo de error."""
    if kind is LLMErrorKind.AUTH:
        return (f"Credenciales inválidas o sin créditos para el modelo '{model}'. "
                "Revisa ANTHROPIC_API_KEY / la cuenta del proveedor.")
    if kind is LLMErrorKind.MODEL_UNAVAILABLE:
        return (f"El modelo '{model}' no está disponible en el gateway. "
                "Revisa litellm_config.yaml y que el proxy esté arriba.")
    return f"Fallo del gateway LLM ({kind.value}) con el modelo '{model}'."
