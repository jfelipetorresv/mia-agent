"""
Mia · test_openrouter_policy.py — gate de CP-OR (OpenRouter como motor principal + overflow).

Verifica OFFLINE (sin red, sin proxy), con un cliente OpenAI FALSO programable por alias:

  0. "openrouter" está registrada en VALID_POLICIES.
  1. política 'openrouter' (motor principal propio): main/curator → openrouter-sonnet→mia-local;
     compression (bloqueada) y auxiliares → openrouter-haiku→mia-local.
  2. overflow ("más uso"): con OPENROUTER_API_KEY + opt-in, 'suscripcion' y 'nube' insertan
     openrouter-sonnet ANTES de mia-local en main/curator.
  3. sin opt-in → NO se inserta el overflow (regla 2: enrutar a un tercero es decisión informada).
  4. sin clave (ni config ni .env) → NO se inserta el overflow (rompería la cadena con AUTH).
  4b. MAYOR 1: clave SOLO en el .env (config vacío, como tras set_keys) → overflow SÍ se activa
      (`_openrouter_key_present` la ve en disco; el overflow no queda inerte tras el reinicio en
      caliente del proxy). 4c: esa misma clave sin opt-in sigue SIN overflow (regla 2 intacta).
  5. 'soberano' NUNCA enruta a OpenRouter, aunque haya clave + opt-in (nada sale del equipo).
  6/7. runtime: con policy 'openrouter', si la clave del abogado es inválida o no tiene saldo
     (AUTH/402, que NO salta solo) y hay red local después, el turno DEGRADA a mia-local
     (salto opcional de OpenRouter generalizado a openrouter-sonnet Y openrouter-haiku).

HALT si falla (CLAUDE.md §G). Exit 0 = PASS · exit 1 = FAIL.
    .venv\\Scripts\\python.exe execution\\test_openrouter_policy.py
"""
from __future__ import annotations

import shutil
import sys
import tempfile
from pathlib import Path
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

from mia.agent import llm

_results: list[tuple[str, bool]] = []


def check(name: str, ok: bool) -> None:
    _results.append((name, bool(ok)))
    print(("  [OK]   " if ok else "  [FAIL] ") + name)


def ok_response(text: str = "ok"):
    msg = SimpleNamespace(content=text)
    return SimpleNamespace(choices=[SimpleNamespace(message=msg)], usage=None)


def http_exc(status: int, msg: str = ""):
    e = Exception(msg or f"http {status}")
    e.status_code = status  # classify por status
    return e


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
    fc = FakeCompletions(script)
    llm._client = SimpleNamespace(chat=SimpleNamespace(completions=fc))
    return fc


MSG = [{"role": "user", "content": "hola"}]
_AUX = ("verification", "title_generation", "session_search", "web_extract",
        "vision", "soul", "mission_decompose")


def with_policy(policy: str, fn) -> None:
    tok = llm.set_model_policy(policy)
    try:
        fn()
    finally:
        llm.reset_model_policy(tok)


def with_overflow(policy: str, key: str, allowed: bool, fn) -> None:
    """Fija política + clave global (config.OPENROUTER_API_KEY) + opt-in del despacho,
    corre fn y restaura todo. Cubre las condiciones del overflow de _active_chains.

    MAYOR 1: `_openrouter_key_present()` primero mira config; con `key` truthy responde
    True sin tocar disco. Para el caso 'sin clave' (key='') se usa `with_overflow_env`
    (aísla también el `.env` en disco, del que ahora depende el helper)."""
    orig_key = llm.config.OPENROUTER_API_KEY
    llm.config.OPENROUTER_API_KEY = key
    llm._openrouter_env_cache = (0.0, False)  # fuerza relectura fresca del helper
    tok = llm.set_model_policy(policy)
    or_tok = llm.set_openrouter_allowed(allowed)
    try:
        fn()
    finally:
        llm.reset_openrouter_allowed(or_tok)
        llm.reset_model_policy(tok)
        llm.config.OPENROUTER_API_KEY = orig_key
        llm._openrouter_env_cache = (0.0, False)


def with_overflow_env(policy: str, config_key: str, env_key: str | None,
                      allowed: bool, fn) -> None:
    """Como `with_overflow` pero controla TAMBIÉN el `.env` en disco (del que depende
    `_openrouter_key_present`, MAYOR 1). `config_key` = valor en config (proceso vivo);
    `env_key` = valor de OPENROUTER_API_KEY en un `.env` TEMPORAL (None = sin esa línea).
    Apunta config.PROJECT_ROOT al tempdir para que el helper lea ESE `.env` y no el del repo."""
    orig_key = llm.config.OPENROUTER_API_KEY
    orig_root = llm.config.PROJECT_ROOT
    tmp = Path(tempfile.mkdtemp(prefix="mia-or-gate-"))
    try:
        env_line = f"OPENROUTER_API_KEY={env_key}\n" if env_key is not None else ""
        (tmp / ".env").write_text("MIA_ENV=dev\n" + env_line, encoding="utf-8")
        llm.config.OPENROUTER_API_KEY = config_key
        llm.config.PROJECT_ROOT = tmp
        llm._openrouter_env_cache = (0.0, False)  # fuerza relectura del `.env` temporal
        tok = llm.set_model_policy(policy)
        or_tok = llm.set_openrouter_allowed(allowed)
        try:
            fn()
        finally:
            llm.reset_openrouter_allowed(or_tok)
            llm.reset_model_policy(tok)
    finally:
        llm.config.OPENROUTER_API_KEY = orig_key
        llm.config.PROJECT_ROOT = orig_root
        llm._openrouter_env_cache = (0.0, False)
        shutil.rmtree(tmp, ignore_errors=True)


def run() -> None:
    llm.time.sleep = lambda *_a, **_k: None  # reintentos instantáneos

    # === 0 · política registrada ===
    check("0 · 'openrouter' está en VALID_POLICIES", "openrouter" in llm.VALID_POLICIES)

    # === 1 · política 'openrouter' → motor propio (sonnet razonamiento, haiku barato) ===
    def _or():
        check("1a · [openrouter] main → openrouter-sonnet→mia-local",
              llm.resolve_fallback_chain("main") == ["openrouter-sonnet", "mia-local"])
        check("1b · [openrouter] curator = cadena de main",
              llm.resolve_fallback_chain("curator") == ["openrouter-sonnet", "mia-local"])
        check("1c · [openrouter] compression → openrouter-haiku→mia-local (bloqueada: ignora model)",
              llm.resolve_fallback_chain("compression", model="claude-opus")
              == ["openrouter-haiku", "mia-local"])
        check("1d · [openrouter] auxiliares → openrouter-haiku→mia-local",
              all(llm.resolve_fallback_chain(t) == ["openrouter-haiku", "mia-local"] for t in _AUX))
    with_policy("openrouter", _or)

    # === 2 · overflow ("más uso") en suscripcion y nube con clave + opt-in ===
    def _sus_overflow():
        check("2a · [suscripcion+overflow] main añade OpenRouter tras la suscripción",
              llm.resolve_fallback_chain("main")
              == ["cli-claude", "openrouter-sonnet"])
        check("2b · [suscripcion+overflow] curator conserva su respaldo y añade OpenRouter",
              llm.resolve_fallback_chain("curator")
              == ["cli-claude", "claude-sonnet", "openrouter-sonnet", "mia-local"])
    with_overflow("suscripcion", "sk-or-test", True, _sus_overflow)

    def _nube_overflow():
        check("2c · [nube+overflow] main → claude-sonnet→openrouter-sonnet→mia-local",
              llm.resolve_fallback_chain("main")
              == ["claude-sonnet", "openrouter-sonnet", "mia-local"])
    with_overflow("nube", "sk-or-test", True, _nube_overflow)

    # === 3 · sin opt-in → NO overflow ===
    with_overflow("suscripcion", "sk-or-test", False, lambda: check(
        "3 · [suscripcion] sin opt-in → NO se inserta openrouter",
        "openrouter-sonnet" not in llm.resolve_fallback_chain("main")))

    # === 4 · sin clave (ni en config ni en el .env) → NO overflow ===
    with_overflow_env("suscripcion", "", None, True, lambda: check(
        "4 · [suscripcion] sin clave (config vacío + .env sin la línea) → NO se inserta openrouter",
        "openrouter-sonnet" not in llm.resolve_fallback_chain("main")))

    # === 4b · MAYOR 1: clave SOLO en el .env (config vacío, como tras set_keys) → SÍ overflow ===
    # Reproduce el estado real: `set_keys` escribió OPENROUTER_API_KEY al .env pero NO tocó
    # config.OPENROUTER_API_KEY. `_openrouter_key_present()` la ve en disco y el overflow se activa.
    with_overflow_env("suscripcion", "", "sk-or-solo-en-env", True, lambda: check(
        "4b · [suscripcion] clave SOLO en el .env (config vacío) → overflow ACTIVO (MAYOR 1)",
        llm.resolve_fallback_chain("main")
        == ["cli-claude", "openrouter-sonnet"]))

    # === 4c · clave en el .env pero SIN opt-in → NO overflow (regla 2 intacta) ===
    with_overflow_env("suscripcion", "", "sk-or-solo-en-env", False, lambda: check(
        "4c · [suscripcion] clave en .env pero sin opt-in → NO se inserta openrouter",
        "openrouter-sonnet" not in llm.resolve_fallback_chain("main")))

    # === 5 · soberano nunca enruta a OpenRouter, aun con clave + opt-in ===
    with_overflow("soberano", "sk-or-test", True, lambda: check(
        "5 · [soberano] main → solo mia-local (nada sale del equipo)",
        llm.resolve_fallback_chain("main") == ["mia-local"]))

    # === 6 · runtime: clave inválida (AUTH) en openrouter-sonnet → degrada a mia-local ===
    fc = install({"openrouter-sonnet": [http_exc(401, "invalid key")],
                  "mia-local": [ok_response("local rescata")]})

    def _rescue_sonnet():
        resp = llm.call_llm(MSG, task="main")
        check("6a · [openrouter] AUTH en openrouter-sonnet (no saltable) → degrada a mia-local",
              resp.choices[0].message.content == "local rescata")
        check("6b · openrouter-sonnet se intentó exactamente una vez (AUTH no reintenta)",
              fc.count("openrouter-sonnet") == 1)
    with_policy("openrouter", _rescue_sonnet)

    # === 7 · runtime: openrouter-haiku sin saldo (402) → degrada a mia-local ===
    fc = install({"openrouter-haiku": [http_exc(402, "no credit")],
                  "mia-local": [ok_response("local haiku")]})

    def _rescue_haiku():
        resp = llm.call_llm(MSG, task="verification")
        check("7 · [openrouter] 402 (sin saldo) en openrouter-haiku → degrada a mia-local",
              resp.choices[0].message.content == "local haiku")
    with_policy("openrouter", _rescue_haiku)


def main() -> int:
    print("== CP-OR · OpenRouter como motor principal + overflow (política 'openrouter') ==")
    try:
        run()
    finally:
        llm._client = None

    passed = sum(1 for _, ok in _results if ok)
    total = len(_results)
    print(f"\n{passed}/{total} checks PASS")
    if passed == total:
        print("openrouter policy OK — CP-OR verificado (motor principal + overflow + degradación local).")
        return 0
    print("openrouter policy FAIL — HALT: no avanzar (CLAUDE.md §G).")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
