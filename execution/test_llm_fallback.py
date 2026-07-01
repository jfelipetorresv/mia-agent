"""
Mia · test_llm_fallback.py — gate de H.5 (cadena de fallback de proveedor en call_llm).

Verifica OFFLINE (sin red ni proxy), con un cliente OpenAI FALSO cuyo comportamiento se
programa por alias de modelo:

  1. alias1 falla MODEL_UNAVAILABLE → salta a alias2, que responde (sin reintentar alias1).
  2. CONTEXT_TOO_LONG NO avanza la cadena: se propaga la excepción original (la resuelve el
     compresor aguas arriba), alias2 nunca se llama.
  3. AUTH falla rápido: LLMError(kind=AUTH) sin saltar de proveedor.
  4. transitorio (RATE_LIMIT) agota los reintentos del alias y ENTONCES salta al siguiente.
  5. cadena entera agotada → LLMError('ALL_PROVIDERS_EXHAUSTED').
  6. should_fallback(kind) por tipo de error (tabla de decisión).

HALT si falla (CLAUDE.md §G). Exit 0 = PASS · exit 1 = FAIL.
    .venv\\Scripts\\python.exe execution\\test_llm_fallback.py
"""
from __future__ import annotations

import sys
from pathlib import Path
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

from mia.agent import llm
from mia.agent.error_classifier import LLMError, LLMErrorKind, should_fallback

_results: list[tuple[str, bool]] = []


def check(name: str, ok: bool) -> None:
    _results.append((name, bool(ok)))
    print(("  [OK]   " if ok else "  [FAIL] ") + name)


# ── fábricas de resultados para el cliente falso ────────────────────────────────
def ok_response(text: str = "ok"):
    msg = SimpleNamespace(content=text)
    return SimpleNamespace(choices=[SimpleNamespace(message=msg)], usage=None)


def http_exc(status: int, msg: str = ""):
    e = Exception(msg or f"http {status}")
    e.status_code = status          # _status_code lo lee → classify por status
    return e


def context_exc():
    # Sin status: classify detecta CONTEXT_TOO_LONG por el mensaje.
    return Exception("This model's maximum context length exceeded by 5000 tokens")


class FakeCompletions:
    """Programable por alias: script[model] = lista de resultados (el último se repite)."""

    def __init__(self, script: dict[str, list]) -> None:
        self.script = script
        self.calls: list[str] = []

    def create(self, **kwargs):
        model = kwargs["model"]
        self.calls.append(model)
        outcomes = self.script[model]
        idx = min(sum(1 for m in self.calls if m == model) - 1, len(outcomes) - 1)
        outcome = outcomes[idx]
        if isinstance(outcome, BaseException):
            raise outcome
        return outcome

    def count(self, model: str) -> int:
        return sum(1 for m in self.calls if m == model)


def install(script: dict[str, list]) -> FakeCompletions:
    """Instala un cliente falso con el script dado y devuelve las completions (para inspección)."""
    fc = FakeCompletions(script)
    llm._client = SimpleNamespace(chat=SimpleNamespace(completions=fc))
    return fc


def run() -> None:
    # Reintentos instantáneos: no dormir en el backoff.
    llm.time.sleep = lambda *_a, **_k: None  # type: ignore[assignment]
    # Cadena de prueba de dos proveedores.
    llm._TASK_FALLBACK_CHAINS["faketask"] = ["m1", "m2"]
    MSG = [{"role": "user", "content": "hola"}]

    # === 1 · MODEL_UNAVAILABLE en m1 → salta a m2 (sin reintentar m1) ===
    fc = install({"m1": [http_exc(404, "model not found")], "m2": [ok_response("desde m2")]})
    resp = llm.call_llm(MSG, task="faketask")
    check("1a · MODEL_UNAVAILABLE en m1 → responde m2",
          resp.choices[0].message.content == "desde m2")
    check("1b · m1 NO se reintenta ante MODEL_UNAVAILABLE (1 sola llamada)", fc.count("m1") == 1)
    check("1c · m2 se llama exactamente una vez", fc.count("m2") == 1)

    # === 2 · CONTEXT_TOO_LONG NO avanza la cadena (propaga original, m2 intacto) ===
    fc = install({"m1": [context_exc()], "m2": [ok_response("no debería llamarse")]})
    ctx_ok = False
    try:
        llm.call_llm(MSG, task="faketask")
    except LLMError:
        ctx_ok = False  # NO debe envolverse en LLMError
    except Exception as e:  # noqa: BLE001 — esperamos la excepción ORIGINAL de contexto
        ctx_ok = "context length" in str(e).lower()
    check("2a · CONTEXT_TOO_LONG propaga la excepción original (no LLMError)", ctx_ok)
    check("2b · CONTEXT_TOO_LONG NO salta de proveedor (m2 nunca se llama)", fc.count("m2") == 0)

    # === 3 · AUTH falla rápido (LLMError kind=AUTH), sin saltar ===
    fc = install({"m1": [http_exc(401, "invalid api key")], "m2": [ok_response("no")]})
    auth_kind = None
    try:
        llm.call_llm(MSG, task="faketask")
    except LLMError as e:
        auth_kind = e.kind
    check("3a · AUTH → LLMError(kind=AUTH)", auth_kind is LLMErrorKind.AUTH)
    check("3b · AUTH NO salta de proveedor (m2 nunca se llama)", fc.count("m2") == 0)
    check("3c · AUTH NO reintenta m1 (1 sola llamada)", fc.count("m1") == 1)

    # === 4 · RATE_LIMIT agota reintentos de m1 y ENTONCES salta a m2 ===
    fc = install({"m1": [http_exc(429, "rate limit")], "m2": [ok_response("desde m2 tras 429")]})
    resp = llm.call_llm(MSG, task="faketask")
    check("4a · RATE_LIMIT agotado en m1 → responde m2",
          resp.choices[0].message.content == "desde m2 tras 429")
    check("4b · m1 se reintenta hasta agotar (MAX_RETRIES+1 intentos)",
          fc.count("m1") == llm.MAX_RETRIES + 1)

    # === 5 · cadena entera agotada → ALL_PROVIDERS_EXHAUSTED ===
    fc = install({"m1": [http_exc(404, "model not found")], "m2": [http_exc(404, "model not found")]})
    exhausted_msg = ""
    exhausted_kind = None
    try:
        llm.call_llm(MSG, task="faketask")
    except LLMError as e:
        exhausted_msg = str(e)
        exhausted_kind = e.kind
    check("5a · cadena agotada → LLMError('ALL_PROVIDERS_EXHAUSTED')",
          "ALL_PROVIDERS_EXHAUSTED" in exhausted_msg)
    check("5b · el kind del error final es el del último proveedor (MODEL_UNAVAILABLE)",
          exhausted_kind is LLMErrorKind.MODEL_UNAVAILABLE)
    check("5c · ambos proveedores se intentaron", fc.count("m1") == 1 and fc.count("m2") == 1)

    # === 6 · should_fallback(kind) — tabla de decisión ===
    check("6a · MODEL_UNAVAILABLE → salta", should_fallback(LLMErrorKind.MODEL_UNAVAILABLE) is True)
    check("6b · RATE_LIMIT → salta", should_fallback(LLMErrorKind.RATE_LIMIT) is True)
    check("6c · TIMEOUT → salta", should_fallback(LLMErrorKind.TIMEOUT) is True)
    check("6d · NETWORK → salta", should_fallback(LLMErrorKind.NETWORK) is True)
    check("6e · SERVER_ERROR → salta", should_fallback(LLMErrorKind.SERVER_ERROR) is True)
    check("6f · AUTH → NO salta", should_fallback(LLMErrorKind.AUTH) is False)
    check("6g · CONTEXT_TOO_LONG → NO salta", should_fallback(LLMErrorKind.CONTEXT_TOO_LONG) is False)
    check("6h · UNKNOWN → NO salta", should_fallback(LLMErrorKind.UNKNOWN) is False)

    # === 7 · resolve_fallback_chain — dedupe, locked, override ===
    check("7a · main → cadena claude-sonnet→mia-local",
          llm.resolve_fallback_chain("main") == ["claude-sonnet", "mia-local"])
    check("7b · compression bloqueada (cadena de un alias, ignora model)",
          llm.resolve_fallback_chain("compression", model="claude-opus") == ["mia-local"])
    check("7c · override explícito → cadena de un alias",
          llm.resolve_fallback_chain("main", model="mia-local") == ["mia-local"])
    check("7d · task desconocido → cae a la cadena de main",
          llm.resolve_fallback_chain("no-existe") == ["claude-sonnet", "mia-local"])


def main() -> int:
    print("== Tarea H.5 · cadena de fallback de proveedor (call_llm) ==")
    try:
        run()
    finally:
        llm._client = None
        llm._TASK_FALLBACK_CHAINS.pop("faketask", None)

    passed = sum(1 for _, ok in _results if ok)
    total = len(_results)
    print(f"\n{passed}/{total} checks PASS")
    if passed == total:
        print("llm fallback OK — H.5 verificado (cadena + should_fallback + compresión coordinada).")
        return 0
    print("llm fallback FAIL — HALT: no avanzar (CLAUDE.md §G).")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
