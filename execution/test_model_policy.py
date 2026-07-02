"""
Mia · test_model_policy.py — gate de CP2 (política de modelo por tenant + proveedor CLI).

Verifica OFFLINE (sin red, sin proxy, sin CLI real: subprocess y shutil.which van MOCKEADOS):

  1. política 'suscripcion' → la cadena de main empieza con cli-claude (CLI de la suscripción).
  2. política 'soberano' → TODO va a mia-local.
  3. política 'nube' → claude-sonnet primero y compression=claude-haiku (decisión #7 restaurada).
  4. compression sigue BLOQUEADA ante un model explícito en las 3 políticas.
  5. CLI ausente (shutil.which→None) → call_llm salta al siguiente proveedor de la cadena.
  6. parse correcto del JSON real del CLI (result/usage → .choices/.usage OpenAI-compatible).
  7. error del CLI (is_error / exit 1 / timeout) → clasificado, saltable, y la cadena avanza.
  8. set/get/reset del ContextVar de política (incluye política inválida → default).
  9. model_policy_for lee tenant_settings.config['model_policy'] (pool mockeado).

HALT si falla (CLAUDE.md §G). Exit 0 = PASS · exit 1 = FAIL.
    .venv\\Scripts\\python.exe execution\\test_model_policy.py
"""
from __future__ import annotations

import asyncio
import json
import subprocess as real_subprocess
import sys
from contextlib import asynccontextmanager
from pathlib import Path
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

from mia.agent import llm, subscription_llm
from mia.agent.error_classifier import LLMErrorKind, classify_llm_error, should_fallback

_results: list[tuple[str, bool]] = []


def check(name: str, ok: bool) -> None:
    _results.append((name, bool(ok)))
    print(("  [OK]   " if ok else "  [FAIL] ") + name)


# ── fixtures del CLI (formato REAL observado en vivo 2026-07-01) ─────────────────
CLI_OK_JSON = json.dumps({
    "type": "result", "subtype": "success", "is_error": False,
    "result": "OK desde la suscripción", "session_id": "sess-123",
    "usage": {"input_tokens": 10, "cache_creation_input_tokens": 5,
              "cache_read_input_tokens": 2, "output_tokens": 7},
})
CLI_ERR_JSON = json.dumps({
    "type": "result", "subtype": "success", "is_error": True, "api_error_status": 404,
    "result": "There's an issue with the selected model", "usage": {},
})


class _FakeProc:
    def __init__(self, stdout: str = "", stderr: str = "", returncode: int = 0) -> None:
        self.stdout, self.stderr, self.returncode = stdout, stderr, returncode


def patch_cli(run_fn, which="C:\\fake\\claude.exe"):
    """Mockea shutil.which y subprocess.run DENTRO de subscription_llm (sin tocar los
    módulos globales). Devuelve lo necesario para restaurar."""
    saved = (subscription_llm.shutil, subscription_llm.subprocess)
    subscription_llm.shutil = SimpleNamespace(which=lambda _n: which)
    subscription_llm.subprocess = SimpleNamespace(
        run=run_fn, TimeoutExpired=real_subprocess.TimeoutExpired)
    return saved


def restore_cli(saved) -> None:
    subscription_llm.shutil, subscription_llm.subprocess = saved


# ── cliente OpenAI falso programable por alias (mismo patrón que test_llm_fallback) ──
def ok_response(text: str = "ok"):
    msg = SimpleNamespace(content=text)
    return SimpleNamespace(choices=[SimpleNamespace(message=msg)], usage=None)


class FakeCompletions:
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


MSG = [{"role": "system", "content": "eres Mia"}, {"role": "user", "content": "hola"}]
_AUX = ("verification", "title_generation", "session_search", "web_extract", "vision", "soul")


def with_policy(policy: str, fn) -> None:
    tok = llm.set_model_policy(policy)
    try:
        fn()
    finally:
        llm.reset_model_policy(tok)


def run() -> None:
    llm.time.sleep = lambda *_a, **_k: None  # reintentos instantáneos

    # === 1 · política 'suscripcion' → CLI primero ===
    def _sus():
        check("1a · [suscripcion] main empieza con cli-claude",
              llm.resolve_fallback_chain("main")[0] == "cli-claude")
        check("1b · [suscripcion] main → cli-claude→claude-sonnet→mia-local",
              llm.resolve_fallback_chain("main") == ["cli-claude", "claude-sonnet", "mia-local"])
        check("1c · [suscripcion] curator = cadena de main",
              llm.resolve_fallback_chain("curator") == ["cli-claude", "claude-sonnet", "mia-local"])
        check("1d · [suscripcion] auxiliares → cli-claude-haiku→mia-local",
              all(llm.resolve_fallback_chain(t) == ["cli-claude-haiku", "mia-local"] for t in _AUX))
        check("1e · [suscripcion] compression → cli-claude-haiku→claude-haiku (red barata si el CLI falla)",
              llm.resolve_fallback_chain("compression") == ["cli-claude-haiku", "claude-haiku"])
    with_policy("suscripcion", _sus)

    # === 2 · política 'soberano' → todo mia-local ===
    def _sob():
        tasks = ("main", "curator", "compression", *_AUX)
        check("2a · [soberano] TODAS las tareas → mia-local",
              all(llm.resolve_fallback_chain(t) == ["mia-local"] for t in tasks))
    with_policy("soberano", _sob)

    # === 3 · política 'nube' → sonnet primero, compression=claude-haiku (decisión #7) ===
    def _nub():
        check("3a · [nube] main → claude-sonnet→mia-local",
              llm.resolve_fallback_chain("main") == ["claude-sonnet", "mia-local"])
        check("3b · [nube] compression → claude-haiku (decisión #7 restaurada)",
              llm.resolve_fallback_chain("compression") == ["claude-haiku"])
        check("3c · [nube] auxiliares → claude-haiku→mia-local",
              all(llm.resolve_fallback_chain(t) == ["claude-haiku", "mia-local"] for t in _AUX))
    with_policy("nube", _nub)

    # === 4 · compression BLOQUEADA ante model explícito en las 3 políticas ===
    expected_locked = {"suscripcion": ["cli-claude-haiku", "claude-haiku"],
                       "nube": ["claude-haiku"], "soberano": ["mia-local"]}
    for pol, exp in expected_locked.items():
        with_policy(pol, lambda pol=pol, exp=exp: check(
            f"4 · [{pol}] compression ignora model explícito → {exp[0]}",
            llm.resolve_fallback_chain("compression", model="claude-opus") == exp))

    # === 5 · CLI ausente (which→None) → call_llm salta al siguiente proveedor ===
    saved = patch_cli(run_fn=lambda *a, **k: _FakeProc(CLI_OK_JSON), which=None)
    try:
        exc = None
        try:
            subscription_llm.call_cli(MSG)
        except Exception as e:  # noqa: BLE001
            exc = e
        check("5a · CLI ausente → SubscriptionCLIUnavailable",
              isinstance(exc, subscription_llm.SubscriptionCLIUnavailable))
        check("5b · is_available() == False con which→None",
              subscription_llm.is_available() is False)
        kind = classify_llm_error(exc)
        check("5c · se clasifica MODEL_UNAVAILABLE (salto inmediato, sin reintentos)",
              kind is LLMErrorKind.MODEL_UNAVAILABLE and should_fallback(kind))

        fc = install({"claude-sonnet": [ok_response("desde sonnet")]})

        def _call():
            resp = llm.call_llm(MSG, task="main")
            check("5d · call_llm (suscripcion, CLI ausente) → responde el siguiente proveedor",
                  resp.choices[0].message.content == "desde sonnet")
            check("5e · claude-sonnet se llamó exactamente una vez", fc.count("claude-sonnet") == 1)
        with_policy("suscripcion", _call)
    finally:
        restore_cli(saved)

    # 5f · blindaje BatBadBut (CVE-2024-24576): un `claude` que resuelve a .cmd/.ps1
    # pasaría por cmd.exe al ejecutarse con lista de args → se trata como NO disponible.
    saved = patch_cli(run_fn=lambda *a, **k: _FakeProc(CLI_OK_JSON), which="C:\\fake\\claude.cmd")
    try:
        exc = None
        try:
            subscription_llm.call_cli(MSG)
        except Exception as e:  # noqa: BLE001
            exc = e
        check("5f · which→claude.cmd (no .exe) → SubscriptionCLIUnavailable (BatBadBut)",
              isinstance(exc, subscription_llm.SubscriptionCLIUnavailable))
        check("5g · is_available() == False con which→.cmd",
              subscription_llm.is_available() is False)
    finally:
        restore_cli(saved)

    # === 6 · parse correcto del JSON real del CLI ===
    captured: dict = {}

    def _run_ok(cmd, **kw):
        captured["cmd"] = cmd
        captured["kw"] = kw
        return _FakeProc(CLI_OK_JSON)

    saved = patch_cli(_run_ok)
    try:
        resp = subscription_llm.call_cli(MSG, model_hint="haiku")
        check("6a · .choices[0].message.content trae el campo 'result'",
              resp.choices[0].message.content == "OK desde la suscripción")
        check("6b · .usage mapea input(+caché)/output → prompt/completion",
              resp.usage.prompt_tokens == 17 and resp.usage.completion_tokens == 7
              and resp.usage.total_tokens == 24)
        cmd = captured["cmd"]
        check("6c · flags base confirmados en vivo (-p, json, max-turns, tools, strict-mcp)",
              "-p" in cmd and "--output-format" in cmd and "json" in cmd
              and "--max-turns" in cmd and "--tools" in cmd and "--strict-mcp-config" in cmd)
        stdin_text = captured["kw"].get("input", "")
        # 6d refinado (fix de calidad 2026-07-01): el CLI recibe un --system-prompt
        # ESTÁTICO (persona de Mia, constante del módulo, SIN contenido del tenant)
        # que anula la persona concisa de Claude Code. El invariante de seguridad
        # real: el system DEL TENANT ("eres Mia" del mensaje) viaja por stdin, y el
        # único --system-prompt en args es exactamente la constante estática.
        sys_flag_vals = [cmd[i + 1] for i, a in enumerate(cmd[:-1]) if a == "--system-prompt"]
        check("6d · system del tenant por stdin; --system-prompt solo la persona estática",
              sys_flag_vals == [subscription_llm._PERSONA_OVERRIDE]
              and "eres Mia" not in " ".join(a for a in cmd if a != subscription_llm._PERSONA_OVERRIDE)
              and subscription_llm._SYS_HEADER in stdin_text and "eres Mia" in stdin_text
              and subscription_llm._REQ_HEADER in stdin_text)
        check("6e · model_hint 'haiku' confirmado → pasa --model haiku",
              "--model" in cmd and "haiku" in cmd)
        check("6f · el prompt del usuario viaja por stdin (no en la línea de comandos)",
              stdin_text.endswith("hola") and "hola" not in cmd)
        check("6g · cwd del subproceso = MIA_HOME (no hereda el CLAUDE.md del repo)",
              captured["kw"].get("cwd") == str(subscription_llm.config.MIA_HOME))
        env = captured["kw"].get("env")
        bad = [k for k in (env or {})
               if any(p in k.upper() for p in ("API_KEY", "SECRET", "PASSWORD", "TOKEN"))
               or k.upper() == "DATABASE_URL" or k.upper().startswith("PG_")]
        check("6i · el subproceso recibe entorno SANEADO (sin *API_KEY/SECRET/PASSWORD/TOKEN, "
              "DATABASE_URL ni PG_*; el CLI usa la suscripción, no la API)",
              isinstance(env, dict) and not bad and "PATH" in env)

        resp2 = subscription_llm.call_cli(MSG, model_hint="alias-inventado")
        check("6h · model_hint no confirmado se ignora con warning (sin --model)",
              "alias-inventado" not in captured["cmd"] and resp2.choices[0].message.content)
    finally:
        restore_cli(saved)

    # === 7 · errores del CLI → clasificados y saltables ===
    saved = patch_cli(lambda *a, **k: _FakeProc(CLI_ERR_JSON, returncode=1))
    try:
        exc = None
        try:
            subscription_llm.call_cli(MSG)
        except Exception as e:  # noqa: BLE001
            exc = e
        check("7a · is_error/exit 1 → SubscriptionCLIError",
              isinstance(exc, subscription_llm.SubscriptionCLIError))
        check("7b · usa api_error_status del CLI (404 → MODEL_UNAVAILABLE, saltable)",
              classify_llm_error(exc) is LLMErrorKind.MODEL_UNAVAILABLE
              and should_fallback(classify_llm_error(exc)))
    finally:
        restore_cli(saved)

    saved = patch_cli(lambda *a, **k: _FakeProc("esto no es JSON", returncode=0))
    try:
        exc = None
        try:
            subscription_llm.call_cli(MSG)
        except Exception as e:  # noqa: BLE001
            exc = e
        kind = classify_llm_error(exc)
        check("7c · JSON no parseable → error 500 (SERVER_ERROR, saltable tras reintentos)",
              isinstance(exc, subscription_llm.SubscriptionCLIError)
              and kind is LLMErrorKind.SERVER_ERROR and should_fallback(kind))
    finally:
        restore_cli(saved)

    def _run_timeout(cmd, **kw):
        raise real_subprocess.TimeoutExpired(cmd, kw.get("timeout", 300))

    saved = patch_cli(_run_timeout)
    try:
        exc = None
        try:
            subscription_llm.call_cli(MSG, timeout=1)
        except Exception as e:  # noqa: BLE001
            exc = e
        check("7d · timeout del subproceso → TimeoutError (TIMEOUT, saltable)",
              isinstance(exc, TimeoutError)
              and classify_llm_error(exc) is LLMErrorKind.TIMEOUT
              and should_fallback(classify_llm_error(exc)))
    finally:
        restore_cli(saved)

    # integración: CLI que falla (is_error) → la cadena avanza hasta claude-sonnet
    saved = patch_cli(lambda *a, **k: _FakeProc(CLI_ERR_JSON, returncode=1))
    try:
        fc = install({"claude-sonnet": [ok_response("rescate en nube")]})

        def _call():
            resp = llm.call_llm(MSG, task="main")
            check("7e · call_llm (suscripcion, CLI en error) → salta y responde claude-sonnet",
                  resp.choices[0].message.content == "rescate en nube")
        with_policy("suscripcion", _call)
    finally:
        restore_cli(saved)

    # === 8 · ContextVar: set / get / reset / inválida ===
    default = llm._default_policy()
    check("8a · sin fijar nada, get_model_policy() = default de config",
          llm.get_model_policy() == default)
    tok = llm.set_model_policy("soberano")
    check("8b · set_model_policy('soberano') → get devuelve 'soberano'",
          llm.get_model_policy() == "soberano")
    llm.reset_model_policy(tok)
    check("8c · reset_model_policy(token) → vuelve al default",
          llm.get_model_policy() == default)
    tok = llm.set_model_policy("politica-inventada")
    check("8d · política inválida → cae al default (no rompe)",
          llm.get_model_policy() == default)
    llm.reset_model_policy(tok)

    # === 9 · model_policy_for lee tenant_settings (pool mockeado) ===
    from mia.db import pool as pool_mod

    def fake_tc(row):
        @asynccontextmanager
        async def _tc(_tenant_id):
            async def _fetchone():
                return row

            async def _execute(*_a, **_k):
                return SimpleNamespace(fetchone=_fetchone)
            yield SimpleNamespace(execute=_execute)
        return _tc

    saved_tc = pool_mod.tenant_connection
    try:
        pool_mod.tenant_connection = fake_tc(("soberano",))
        check("9a · model_policy_for lee config->>'model_policy' del tenant",
              asyncio.run(llm.model_policy_for("t-1")) == "soberano")
        pool_mod.tenant_connection = fake_tc(None)
        check("9b · tenant sin fila/setting → default de config",
              asyncio.run(llm.model_policy_for("t-2")) == default)
        pool_mod.tenant_connection = fake_tc(("valor-basura",))
        check("9c · valor inválido persistido → default (validación contra las 3 políticas)",
              asyncio.run(llm.model_policy_for("t-3")) == default)
    finally:
        pool_mod.tenant_connection = saved_tc


def main() -> int:
    print("== CP2 · política de modelo por tenant + proveedor CLI de suscripción ==")
    try:
        run()
    finally:
        llm._client = None

    passed = sum(1 for _, ok in _results if ok)
    total = len(_results)
    print(f"\n{passed}/{total} checks PASS")
    if passed == total:
        print("model policy OK — CP2 verificado (3 políticas + CLI + ContextVar + tenant_settings).")
        return 0
    print("model policy FAIL — HALT: no avanzar (CLAUDE.md §G).")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
