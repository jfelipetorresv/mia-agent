"""Mia · agent.llm — router central call_llm(task=...) por el gateway LiteLLM.

Adaptado del patrón `call_llm(task=...)` de Hermes (hermes-ref/agent/
auxiliary_client.py). En Hermes ese archivo tiene ~5.800 líneas porque resuelve
proveedor + auth + formato para ~20 proveedores a mano. En Mia ese trabajo lo
hace LiteLLM (decisión #3): el proxy expone UN endpoint OpenAI-compatible y los
modelos se nombran por alias (litellm_config.yaml). Por eso este router es
delgado: solo mapea `task -> alias` y delega el resto al gateway.

OVERRIDE 2026-06-20 (sin créditos Anthropic · anula parcialmente la decisión #7):
    Las tareas auxiliares (soul / title_generation / verification / …) apuntan a mia-local.
    `compression` sigue BLOQUEADA en _LOCKED_TASKS (un `model` explícito se ignora) a mia-local
    en vez de claude-haiku. Revertir a claude-haiku cuando haya créditos.

H.5 (cadena de fallback de proveedor, 2026-06-30):
    `_TASK_MODELS` (task→alias único) se reemplaza por `_TASK_FALLBACK_CHAINS` (task→[alias, …]).
    `call_llm` recorre la cadena: si un proveedor se agota con un error que amerita saltar
    (`error_classifier.should_fallback`), pasa al siguiente alias. `main`/`curator` intentan
    `claude-sonnet` y caen a `mia-local`. `compression` mantiene su cadena de un solo alias
    (sin fallback) y su bloqueo. Ver architecture/ y memory/decisions.md.
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
    should_fallback,
)

logger = logging.getLogger("mia.agent.llm")

# Reintentos automáticos para errores transitorios (rate limit / timeout / red).
# Los deterministas (auth, modelo inexistente, contexto largo) NO se reintentan.
MAX_RETRIES = 3

# task -> CADENA de aliases de fallback. Los alias viven en litellm_config.yaml (fuente
# única); el gateway resuelve el id real. call_llm prueba los aliases en orden: si el
# proveedor actual se agota con un error "saltable" (should_fallback), pasa al siguiente.
# `compression` tiene cadena de UN alias (bloqueada, sin fallback). `main`/`curator` intentan
# claude-sonnet y caen a mia-local (dev sin créditos → claude-sonnet puede fallar AUTH, que
# NO salta; usar model="mia-local" o ajustar la cadena si se quiere forzar local).
_TASK_FALLBACK_CHAINS: dict[str, list[str]] = {
    "main": ["claude-sonnet", "mia-local"],      # razonamiento principal: sonnet → local
    "curator": ["claude-sonnet", "mia-local"],   # consolidación semántica: sonnet → local
    "compression": ["mia-local"],                # BLOQUEADA (decisión #7), sin fallback
    "verification": ["mia-local"],               # verificación de citas legales
    "title_generation": ["mia-local"],           # títulos de asunto
    "session_search": ["mia-local"],             # resumen/búsqueda en la sesión
    "web_extract": ["mia-local"],                # extracción de contenido web
    "vision": ["mia-local"],                     # comprensión de documentos/imágenes
    "soul": ["mia-local"],                       # generación del SOUL.md (identidad del agente)
}

# Tareas cuya cadena es un contrato fijo: un `model` explícito NO puede cambiarla.
_LOCKED_TASKS = frozenset({"compression"})

_DEFAULT_TASK = "main"

_client: Any = None  # openai.OpenAI — import diferido (ver _get_client)


class _FallbackNeeded(Exception):
    """Señal interna: el alias actual se agotó y conviene saltar al siguiente de la cadena.

    Lleva el `kind` clasificado y la excepción original para el diagnóstico final si la
    cadena entera se agota. NO escapa de call_llm (se traduce a LLMError allí).
    """

    def __init__(self, kind: LLMErrorKind, exc: BaseException) -> None:
        super().__init__(kind.value)
        self.kind = kind
        self.exc = exc


def _dedupe_chain(aliases: list[str]) -> list[str]:
    """Quita vacíos y duplicados preservando el orden (primer proveedor gana)."""
    out: list[str] = []
    for a in aliases:
        if a and a not in out:
            out.append(a)
    return out


def resolve_fallback_chain(task: str | None, model: str | None = None) -> list[str]:
    """Cadena de aliases a intentar para un `task` (sin vacíos ni duplicados).

    - `compression` está bloqueado (decisión #7): un `model` distinto se ignora con warning.
    - `model` explícito (tarea no bloqueada) gana como cadena de UN alias (override sin fallback).
    - Sin `model`: la cadena del mapa; un task desconocido cae a la de 'main'.
    """
    if task in _LOCKED_TASKS:
        locked = _TASK_FALLBACK_CHAINS[task]
        if model and model != locked[0]:
            logger.warning(
                "task=%s está bloqueado a %s (decisión #7); se ignora model=%s",
                task, locked[0], model,
            )
        return _dedupe_chain(locked)
    if model:
        return [model]
    chain = _TASK_FALLBACK_CHAINS.get(task or _DEFAULT_TASK, _TASK_FALLBACK_CHAINS[_DEFAULT_TASK])
    return _dedupe_chain(chain)


def resolve_model(task: str | None, model: str | None = None) -> str:
    """Compat: primer alias de la cadena de `task` (el proveedor preferido)."""
    return resolve_fallback_chain(task, model)[0]


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
    """Llamada LLM central y síncrona a través del gateway LiteLLM, con cadena de fallback.

    Devuelve la respuesta OpenAI-compatible (usar resp.choices[0].message.content).
    `task` elige la CADENA de proveedores (ver resolve_fallback_chain); `model` la
    sobre-escribe (cadena de un alias) salvo en tareas bloqueadas.

    Política (patrón Hermes v0.17.0, ver error_classifier):
      - transitorios (rate_limit/timeout/network/server) → reintento con backoff dentro del alias;
      - agotado el alias con un error "saltable" (should_fallback) → siguiente alias de la cadena;
      - AUTH / UNKNOWN → falla rápido con mensaje claro (LLMError), SIN saltar;
      - CONTEXT_TOO_LONG → propaga la excepción original SIN avanzar la cadena (la resuelve el compresor);
      - cadena entera agotada → LLMError('ALL_PROVIDERS_EXHAUSTED').
    call_llm es SÍNCRONO y se invoca vía asyncio.to_thread → time.sleep no bloquea el loop.
    """
    chain = resolve_fallback_chain(task, model)
    base_kwargs: dict[str, Any] = {"messages": messages}
    if temperature is not None:
        base_kwargs["temperature"] = temperature
    if max_tokens is not None:
        base_kwargs["max_tokens"] = max_tokens
    if tools:
        base_kwargs["tools"] = tools
    base_kwargs.update(extra)

    client = _get_client()
    last: _FallbackNeeded | None = None
    for i, alias in enumerate(chain):
        next_alias = chain[i + 1] if i + 1 < len(chain) else None
        try:
            return _call_with_retries(
                client, {**base_kwargs, "model": alias}, MAX_RETRIES,
                task=task, alias=alias, next_alias=next_alias,
            )
        except _FallbackNeeded as fn:
            last = fn                          # sigue con el próximo alias de la cadena
            continue

    # Cadena entera agotada: todos los proveedores fallaron con errores saltables.
    kind = last.kind if last else LLMErrorKind.UNKNOWN
    logger.error("call_llm ALL_PROVIDERS_EXHAUSTED [%s] (task=%s chain=%s): %s",
                 kind.value, task, chain, last.exc if last else None)
    raise LLMError(
        kind, f"ALL_PROVIDERS_EXHAUSTED: la cadena {chain} falló ({kind.value})."
    ) from (last.exc if last else None)


def _call_with_retries(
    client: Any,
    kwargs: dict[str, Any],
    max_retries: int,
    *,
    task: str | None,
    alias: str,
    next_alias: str | None,
) -> Any:
    """Ejecuta UN alias con reintentos. Devuelve la respuesta o decide el destino del error:

    - CONTEXT_TOO_LONG → propaga la original (no reintenta, no salta);
    - error saltable (should_fallback), sea inmediato (model_unavailable) o tras agotar los
      reintentos (rate_limit/timeout/network/server) → `_FallbackNeeded` (la cadena avanza);
    - error no saltable (AUTH/UNKNOWN) → LLMError inmediato (fail-fast).
    """
    for attempt in range(max_retries + 1):     # 1 intento inicial + hasta max_retries reintentos
        try:
            return client.chat.completions.create(**kwargs)
        except Exception as exc:               # noqa: BLE001 — se clasifica y re-lanza abajo
            kind = classify_llm_error(exc)

            if kind is LLMErrorKind.CONTEXT_TOO_LONG:
                logger.warning("call_llm context_too_long (task=%s alias=%s): %s",
                               task, alias, exc)
                raise                          # propaga original: lo maneja la compresión

            # Reintento dentro del alias mientras queden intentos y sea transitorio.
            if is_retryable(kind) and attempt < max_retries:
                delay = retry_delay(kind, attempt)
                logger.warning("call_llm reintento %d/%d [%s] en %.2fs (task=%s alias=%s): %s",
                               attempt + 1, max_retries, kind.value, delay, task, alias, exc)
                time.sleep(delay)
                continue

            # Agotados los reintentos (o error no reintentable): ¿saltar de proveedor?
            if should_fallback(kind):
                # Log estructurado del salto: task, alias agotado, intentos, kind, próximo alias.
                logger.warning(
                    "call_llm fallback",
                    extra={"task": task, "alias": alias, "attempt": attempt,
                           "kind": kind.value, "next_alias": next_alias},
                )
                logger.warning("call_llm salta de proveedor [%s] task=%s %s→%s (tras %d intentos)",
                               kind.value, task, alias, next_alias, attempt + 1)
                raise _FallbackNeeded(kind, exc) from exc

            # No saltable (AUTH/UNKNOWN): falla rápido con mensaje claro.
            logger.error("call_llm fallo no saltable [%s] (task=%s alias=%s): %s",
                         kind.value, task, alias, exc)
            raise LLMError(kind, _clear_message(kind, alias)) from exc

    # Inalcanzable (el loop retorna, reintenta o lanza), pero satisface el análisis estático.
    raise LLMError(LLMErrorKind.UNKNOWN, "call_llm terminó sin resultado")


def _clear_message(kind: LLMErrorKind, model: str) -> str:
    """Mensaje claro (en español, sin jerga técnica de proveedor) por tipo de error."""
    if kind is LLMErrorKind.AUTH:
        return (f"Credenciales inválidas o sin créditos para el modelo '{model}'. "
                "Revisa ANTHROPIC_API_KEY / la cuenta del proveedor.")
    if kind is LLMErrorKind.MODEL_UNAVAILABLE:
        return (f"El modelo '{model}' no está disponible en el gateway. "
                "Revisa litellm_config.yaml y que el proxy esté arriba.")
    return f"Fallo del gateway LLM ({kind.value}) con el modelo '{model}'."
