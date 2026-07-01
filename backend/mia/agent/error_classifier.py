"""Mia · agent.error_classifier — taxonomía centralizada de errores del gateway LLM.

Adaptado del patrón de Hermes v0.17.0 (`agent/error_classifier.py`: `FailoverReason`
enum + hints de recuperación). En Mia todo el tráfico LLM pasa por el proxy LiteLLM
(decisión #3), que enruta a varios proveedores (Claude/GPT/Gemini/MiniMax/Ollama).
Cada proveedor falla distinto; sin una capa que normalice el error, cada nodo del grafo
lo maneja o lo ignora a su manera (en el smoke vivo 2026-06-30 se vieron fallos
silenciosos). Este módulo mapea CUALQUIER excepción a un `LLMErrorKind` y expone la
política de reintento (`is_retryable` + `retry_delay`).

Importable sin `openai`/`httpx` instalados: la clasificación NO importa esas librerías,
inspecciona el nombre de tipo, el status_code y el mensaje de la excepción.
"""
from __future__ import annotations

import random
from enum import Enum


class LLMErrorKind(str, Enum):
    """Categorías de fallo del gateway LLM. `str` para logging/serialización directa."""

    RATE_LIMIT = "rate_limit"            # 429 / cuota / demasiadas peticiones
    AUTH = "auth"                        # 401/403 / API key inválida / sin créditos
    MODEL_UNAVAILABLE = "model_unavailable"  # 404 / modelo no existe / proveedor caído
    TIMEOUT = "timeout"                  # timeout de request / 408 / 504
    NETWORK = "network"                  # conexión rechazada / DNS / reset
    CONTEXT_TOO_LONG = "context_too_long"   # prompt excede la ventana del modelo
    UNKNOWN = "unknown"                  # no clasificable → no se reintenta


# Kinds que vale la pena reintentar (transitorios). El resto es determinista: reintentar
# no ayuda (AUTH no se arregla solo, un modelo inexistente no aparece, un contexto largo
# sigue largo → eso lo resuelve el compresor, no el retry).
_RETRYABLE = frozenset({LLMErrorKind.RATE_LIMIT, LLMErrorKind.TIMEOUT, LLMErrorKind.NETWORK})

# Backoff exponencial: base * 2**attempt (+ jitter acotado). El jitter se mantiene por
# debajo de `base` para que el retraso crezca de forma estrictamente monótona entre
# intentos (min del intento n+1 > max del intento n), lo que hace el backoff testeable.
_BASE_DELAY = 0.5      # segundos
_MAX_DELAY = 30.0      # tope por intento
_JITTER_MAX = 0.1      # jitter aditivo máximo (< _BASE_DELAY → monotonía garantizada)


class LLMError(RuntimeError):
    """Error normalizado del gateway. Lleva el `kind` para que el caller decida.

    Se lanza en fail-fast (AUTH/MODEL_UNAVAILABLE/UNKNOWN) y al agotar reintentos.
    CONTEXT_TOO_LONG NO se envuelve en `LLMError`: se propaga la excepción original
    para que la capa de compresión aguas arriba la reconozca.
    """

    def __init__(self, kind: LLMErrorKind, message: str) -> None:
        super().__init__(message)
        self.kind = kind


def _status_code(exc: BaseException) -> int | None:
    """Extrae un status HTTP de la excepción, sea cual sea la librería.

    Cubre `openai` (`.status_code`), httpx (`.response.status_code`) y variantes
    que exponen `.code`. Devuelve None si no hay ninguno numérico.
    """
    for attr in ("status_code", "code", "http_status"):
        val = getattr(exc, attr, None)
        if isinstance(val, int):
            return val
    resp = getattr(exc, "response", None)
    if resp is not None:
        val = getattr(resp, "status_code", None)
        if isinstance(val, int):
            return val
    return None


def classify_llm_error(exc: BaseException) -> LLMErrorKind:
    """Mapea una excepción del gateway LLM a un `LLMErrorKind`.

    Estrategia en capas (de más fiable a más laxa):
      1) status HTTP (429/401/403/404/408/504) cuando existe;
      2) nombre del tipo de la excepción (openai/httpx/asyncio, sin importarlos);
      3) substrings del mensaje.
    CONTEXT_TOO_LONG se detecta por mensaje aun con status 400/422, porque un prompt
    largo llega como BadRequest y hay que distinguirlo de un 400 genérico.
    """
    name = type(exc).__name__.lower()
    msg = str(exc).lower()
    status = _status_code(exc)

    # 1 · Context overflow primero: llega como 400/422 pero NO es un bad-request cualquiera.
    if any(s in msg for s in (
        "context length", "context_length", "maximum context", "context window",
        "too many tokens", "reduce the length", "prompt is too long", "string too long",
    )):
        return LLMErrorKind.CONTEXT_TOO_LONG

    # 2 · Por status HTTP (lo más fiable cuando está presente).
    if status is not None:
        if status == 429:
            return LLMErrorKind.RATE_LIMIT
        if status in (401, 403):
            return LLMErrorKind.AUTH
        if status == 404:
            return LLMErrorKind.MODEL_UNAVAILABLE
        if status in (408, 504):
            return LLMErrorKind.TIMEOUT
        if status in (502, 503):
            return LLMErrorKind.NETWORK

    # 3 · Por tipo de excepción (nombres de openai/httpx/asyncio).
    if "timeout" in name or "timederror" in name:      # TimeoutError, APITimeoutError, ReadTimeout
        return LLMErrorKind.TIMEOUT
    if "ratelimit" in name:                             # RateLimitError
        return LLMErrorKind.RATE_LIMIT
    if "authentication" in name or "permissiondenied" in name:
        return LLMErrorKind.AUTH
    if "notfound" in name:                              # NotFoundError
        return LLMErrorKind.MODEL_UNAVAILABLE
    if "connection" in name or "connect" in name:       # APIConnectionError, ConnectError, ConnectionError
        return LLMErrorKind.NETWORK

    # 4 · Por substrings del mensaje (último recurso).
    if any(s in msg for s in ("rate limit", "rate_limit", "too many requests", "quota", "429")):
        return LLMErrorKind.RATE_LIMIT
    if any(s in msg for s in (
        "invalid api key", "invalid_api_key", "incorrect api key", "authentication",
        "unauthorized", "api key", "no credit", "insufficient", "credit balance", "billing",
    )):
        return LLMErrorKind.AUTH
    if any(s in msg for s in (
        "model not found", "does not exist", "no such model", "unknown model",
        "model_not_found", "unavailable", "not available",
    )):
        return LLMErrorKind.MODEL_UNAVAILABLE
    if any(s in msg for s in ("timed out", "timeout")):
        return LLMErrorKind.TIMEOUT
    if any(s in msg for s in (
        "connection", "network", "econnrefused", "connection refused",
        "name resolution", "dns", "reset by peer", "unreachable",
    )):
        return LLMErrorKind.NETWORK

    return LLMErrorKind.UNKNOWN


def is_retryable(kind: LLMErrorKind) -> bool:
    """True si vale la pena reintentar (RATE_LIMIT, TIMEOUT, NETWORK)."""
    return kind in _RETRYABLE


def retry_delay(kind: LLMErrorKind, attempt: int,
                *, base: float = _BASE_DELAY, max_delay: float = _MAX_DELAY) -> float:
    """Backoff exponencial con jitter para los kinds reintentables.

    `attempt` es 0-based (0 = primer reintento). Devuelve 0.0 para kinds NO reintentables.
    El crecimiento es estrictamente monótono entre intentos (el jitter es < base), lo que
    permite verificarlo en el gate sin fijar la semilla del RNG.
    """
    if not is_retryable(kind):
        return 0.0
    exp = base * (2 ** max(0, attempt))
    delay = min(exp, max_delay)
    jitter = random.uniform(0.0, _JITTER_MAX)
    return delay + jitter
