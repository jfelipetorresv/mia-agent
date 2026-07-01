"""
Mia · test_error_classifier.py — gate del clasificador de errores LLM (Tarea H.1, patrón Hermes v0.17.0).

Standalone, SIN DB y SIN red: verifica la clasificación de cada `LLMErrorKind`, la política
retryable/no-retryable, el crecimiento del backoff, y el cableado en `call_llm` (reintento de
transitorios, fail-fast en AUTH, propagación de CONTEXT_TOO_LONG).

    .venv\\Scripts\\python.exe execution\\test_error_classifier.py

Exit 0 = PASS · exit 1 = FAIL.
"""
from __future__ import annotations
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

from mia.agent import llm                                # noqa: E402
from mia.agent.error_classifier import (                 # noqa: E402
    LLMError,
    LLMErrorKind,
    classify_llm_error,
    is_retryable,
    retry_delay,
)

_results: list[tuple[str, bool]] = []


def check(name: str, ok: bool) -> None:
    _results.append((name, bool(ok)))
    print(("  [OK]   " if ok else "  [FAIL] ") + name)


# ── Excepciones falsas que imitan las de openai/httpx/asyncio ──────────────────
def _exc(type_name: str, message: str = "", *, status_code: int | None = None):
    """Fabrica una excepción con un nombre de tipo y (opcional) status_code dado."""
    attrs = {}
    if status_code is not None:
        attrs["status_code"] = status_code
    cls = type(type_name, (Exception,), attrs)
    return cls(message)


# ── Cliente falso para probar el retry en call_llm ─────────────────────────────
class _FakeCreate:
    """Simula chat.completions.create: lanza `exc` las primeras `fail_n` veces, luego OK."""

    def __init__(self, exc: BaseException, fail_n: int, sentinel):
        self.exc, self.fail_n, self.sentinel = exc, fail_n, sentinel
        self.calls = 0

    def __call__(self, **kwargs):
        self.calls += 1
        if self.calls <= self.fail_n:
            raise self.exc
        return self.sentinel


def _install_fake_client(create_fn):
    fake = type("C", (), {"chat": type("Ch", (), {"completions": type("Co", (), {"create": staticmethod(create_fn)})()})()})()
    llm._client = fake


def run() -> None:
    # ===================== 1 · Clasificación por status HTTP =====================
    check("status 429 → RATE_LIMIT", classify_llm_error(_exc("E", "x", status_code=429)) is LLMErrorKind.RATE_LIMIT)
    check("status 401 → AUTH", classify_llm_error(_exc("E", "x", status_code=401)) is LLMErrorKind.AUTH)
    check("status 403 → AUTH", classify_llm_error(_exc("E", "x", status_code=403)) is LLMErrorKind.AUTH)
    check("status 404 → MODEL_UNAVAILABLE", classify_llm_error(_exc("E", "x", status_code=404)) is LLMErrorKind.MODEL_UNAVAILABLE)
    check("status 408 → TIMEOUT", classify_llm_error(_exc("E", "x", status_code=408)) is LLMErrorKind.TIMEOUT)
    check("status 504 → TIMEOUT", classify_llm_error(_exc("E", "x", status_code=504)) is LLMErrorKind.TIMEOUT)
    check("status 503 → NETWORK", classify_llm_error(_exc("E", "x", status_code=503)) is LLMErrorKind.NETWORK)

    # ===================== 2 · Clasificación por tipo de excepción ===============
    check("APITimeoutError → TIMEOUT", classify_llm_error(_exc("APITimeoutError")) is LLMErrorKind.TIMEOUT)
    check("asyncio TimeoutError → TIMEOUT", classify_llm_error(TimeoutError()) is LLMErrorKind.TIMEOUT)
    check("RateLimitError → RATE_LIMIT", classify_llm_error(_exc("RateLimitError")) is LLMErrorKind.RATE_LIMIT)
    check("AuthenticationError → AUTH", classify_llm_error(_exc("AuthenticationError")) is LLMErrorKind.AUTH)
    check("NotFoundError → MODEL_UNAVAILABLE", classify_llm_error(_exc("NotFoundError")) is LLMErrorKind.MODEL_UNAVAILABLE)
    check("APIConnectionError → NETWORK", classify_llm_error(_exc("APIConnectionError")) is LLMErrorKind.NETWORK)

    # ===================== 3 · Clasificación por mensaje =========================
    check("msg 'rate limit exceeded' → RATE_LIMIT", classify_llm_error(Exception("Rate limit exceeded, retry")) is LLMErrorKind.RATE_LIMIT)
    check("msg 'invalid api key' → AUTH", classify_llm_error(Exception("Invalid API key provided")) is LLMErrorKind.AUTH)
    check("msg 'credit balance too low' → AUTH", classify_llm_error(Exception("Your credit balance is too low")) is LLMErrorKind.AUTH)
    check("msg 'model does not exist' → MODEL_UNAVAILABLE", classify_llm_error(Exception("The model does not exist")) is LLMErrorKind.MODEL_UNAVAILABLE)
    check("msg 'timed out' → TIMEOUT", classify_llm_error(Exception("Request timed out")) is LLMErrorKind.TIMEOUT)
    check("msg 'connection refused' → NETWORK", classify_llm_error(Exception("Connection refused")) is LLMErrorKind.NETWORK)
    check("msg 'maximum context length' → CONTEXT_TOO_LONG", classify_llm_error(Exception("This model's maximum context length is 8192 tokens")) is LLMErrorKind.CONTEXT_TOO_LONG)
    check("CONTEXT gana sobre 400 (bad request con context length)", classify_llm_error(_exc("BadRequestError", "maximum context length exceeded", status_code=400)) is LLMErrorKind.CONTEXT_TOO_LONG)
    check("desconocido → UNKNOWN", classify_llm_error(Exception("algo raro sin pistas")) is LLMErrorKind.UNKNOWN)

    # ===================== 4 · is_retryable =====================================
    check("RATE_LIMIT retryable", is_retryable(LLMErrorKind.RATE_LIMIT))
    check("TIMEOUT retryable", is_retryable(LLMErrorKind.TIMEOUT))
    check("NETWORK retryable", is_retryable(LLMErrorKind.NETWORK))
    check("AUTH NO retryable", not is_retryable(LLMErrorKind.AUTH))
    check("MODEL_UNAVAILABLE NO retryable", not is_retryable(LLMErrorKind.MODEL_UNAVAILABLE))
    check("CONTEXT_TOO_LONG NO retryable", not is_retryable(LLMErrorKind.CONTEXT_TOO_LONG))
    check("UNKNOWN NO retryable", not is_retryable(LLMErrorKind.UNKNOWN))

    # ===================== 5 · Backoff crece entre reintentos ====================
    d0 = retry_delay(LLMErrorKind.RATE_LIMIT, 0)
    d1 = retry_delay(LLMErrorKind.RATE_LIMIT, 1)
    d2 = retry_delay(LLMErrorKind.RATE_LIMIT, 2)
    check("retry_delay crece estrictamente (d0<d1<d2)", d0 < d1 < d2)
    check("retry_delay(no-retryable) == 0.0", retry_delay(LLMErrorKind.AUTH, 0) == 0.0)
    check("retry_delay respeta el tope max_delay", retry_delay(LLMErrorKind.TIMEOUT, 20, max_delay=5.0) <= 5.0 + 0.1)

    # ===================== 6 · Cableado en call_llm ==============================
    # Sin delays reales (patch de time.sleep) para que el gate sea rápido.
    _orig_sleep = llm.time.sleep
    llm.time.sleep = lambda *_a, **_k: None
    try:
        # 6a · transitorio: falla 2 veces (NETWORK) y luego responde → éxito, 3 llamadas.
        sentinel = object()
        fc = _FakeCreate(_exc("APIConnectionError"), fail_n=2, sentinel=sentinel)
        _install_fake_client(fc)
        got = llm.call_llm([{"role": "user", "content": "hola"}], task="main")
        check("call_llm reintenta transitorio y termina OK", got is sentinel and fc.calls == 3)

        # 6b · AUTH → fail-fast, UNA sola llamada, LLMError con kind=AUTH.
        fc = _FakeCreate(_exc("AuthenticationError", "invalid api key"), fail_n=99, sentinel=sentinel)
        _install_fake_client(fc)
        auth_kind = None
        try:
            llm.call_llm([{"role": "user", "content": "x"}], task="main")
        except LLMError as e:
            auth_kind = e.kind
        check("call_llm AUTH falla rápido (1 llamada, sin reintentos)", fc.calls == 1)
        check("call_llm AUTH lanza LLMError(kind=AUTH)", auth_kind is LLMErrorKind.AUTH)

        # 6c · transitorio persistente → agota reintentos (MAX_RETRIES+1 llamadas) y lanza LLMError.
        fc = _FakeCreate(_exc("RateLimitError", "429", status_code=429), fail_n=99, sentinel=sentinel)
        _install_fake_client(fc)
        exhausted = None
        try:
            llm.call_llm([{"role": "user", "content": "x"}], task="main")
        except LLMError as e:
            exhausted = e.kind
        check("call_llm agota reintentos (MAX_RETRIES+1 llamadas)", fc.calls == llm.MAX_RETRIES + 1)
        check("call_llm tras agotar lanza LLMError(kind=RATE_LIMIT)", exhausted is LLMErrorKind.RATE_LIMIT)

        # 6d · CONTEXT_TOO_LONG → propaga la excepción ORIGINAL (no LLMError), 1 llamada.
        original = _exc("BadRequestError", "maximum context length is 8192 tokens", status_code=400)
        fc = _FakeCreate(original, fail_n=99, sentinel=sentinel)
        _install_fake_client(fc)
        propagated, is_llmerror = None, False
        try:
            llm.call_llm([{"role": "user", "content": "x"}], task="main")
        except LLMError:
            is_llmerror = True
        except Exception as e:  # noqa: BLE001
            propagated = e
        check("call_llm CONTEXT_TOO_LONG propaga original (no LLMError, 1 llamada)",
              propagated is original and not is_llmerror and fc.calls == 1)
    finally:
        llm.time.sleep = _orig_sleep
        llm._client = None


def main() -> int:
    print("== Tarea H.1 · Clasificador de errores LLM centralizado ==")
    run()
    passed = sum(1 for _, ok in _results if ok)
    total = len(_results)
    print(f"\n{passed}/{total} checks PASS")
    if passed == total:
        print("error_classifier OK — H.1 verificado.")
        return 0
    print("error_classifier FAIL — HALT: no avanzar (CLAUDE.md §G).")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
