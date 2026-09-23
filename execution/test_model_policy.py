"""
Mia · test_model_policy.py — gate de CP2 (política de modelo por tenant + proveedor CLI).

Verifica OFFLINE (sin red, sin proxy, sin CLI real: subprocess y shutil.which van MOCKEADOS):

  1. políticas de suscripción → solo CLI como salida externa, sin API ni OpenRouter silenciosos.
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
        check("1b · [suscripcion] main no cambia a API/local sin que el abogado lo elija",
              llm.resolve_fallback_chain("main") == ["cli-claude"])
        check("1c · [suscripcion] curator solo conserva CLI y respaldo local",
              llm.resolve_fallback_chain("curator") == ["cli-claude", "mia-local"])
        check("1d · [suscripcion] auxiliares → cli-claude-haiku→mia-local",
              all(llm.resolve_fallback_chain(t) == ["cli-claude-haiku", "mia-local"] for t in _AUX))
        check("1e · [suscripcion] compression queda solo en el CLI de la suscripción",
              llm.resolve_fallback_chain("compression") == ["cli-claude-haiku"])
        check("1f · [suscripcion] funciones jurídicas no cambian a API/local sin consentimiento",
              all(llm.resolve_fallback_chain(t) == ["cli-claude"]
                  for t in llm.LEGAL_TASKS))
    with_policy("suscripcion", _sus)

    # === 1g · política adaptativa: escalamiento determinista y telemetría efectiva ===
    def _adaptive():
        # Decisión de Pipe 2026-08-14: el más inteligente PIENSA Y ORQUESTA (main y
        # legal_analysis en Opus primero, degradando dentro de la misma suscripción);
        # la ejecución dirigida va en Sonnet y lo mecánico en Haiku.
        check("1g · [quality_adaptive] Opus piensa/orquesta; Sonnet ejecuta; Haiku lo mecánico",
              llm.resolve_fallback_chain("main") == [llm.CLI_OPUS_ALIAS, llm.CLI_SONNET_ALIAS]
              and llm.resolve_fallback_chain("legal_analysis")
              == [llm.CLI_OPUS_ALIAS, llm.CLI_SONNET_ALIAS]
              and llm.resolve_fallback_chain("legal_draft") == [llm.CLI_SONNET_ALIAS]
              and llm.resolve_fallback_chain("legal_verification") == [llm.CLI_SONNET_ALIAS]
              and llm.resolve_fallback_chain("verification")[0] == llm.CLI_HAIKU_ALIAS)
        check("1g-bis · la degradación del pensador queda dentro de la suscripción (cli-*)",
              all(a.startswith("cli-") for a in llm.resolve_fallback_chain("main")))
        subscription_tasks = ("main", *llm.LEGAL_TASKS, "curator", "compression", *_AUX)
        check("1g-ter · [quality_adaptive] ninguna tarea estándar contiene una salida API",
              all(all(a.startswith("cli-") or a == "mia-local"
                      for a in llm.resolve_fallback_chain(task))
                  for task in subscription_tasks))
        check("1h · Max solo existe para escalamiento excepcional; caso ordinario conserva xhigh",
              llm._cli_effort(llm.CLI_OPUS_ALIAS, "legal_draft") == "xhigh"
              and llm._cli_effort(llm.CLI_OPUS_ALIAS, "legal_draft", "exceptional") == "max")
        normal = [{"role": "user", "content": "análisis puntual"}]
        huge = [{"role": "user", "content": "x" * llm._EXCEPTIONAL_LEGAL_CONTEXT_CHARS}]
        check("1i · gate determinista: solo expediente jurídico extenso activa excepción",
              llm._automatic_quality_escalation("legal_draft", normal) == "standard"
              and llm._automatic_quality_escalation("legal_draft", huge) == "exceptional"
              and llm._automatic_quality_escalation("main", huge) == "standard")

        captured: dict[str, object] = {}
        saved_call = subscription_llm.call_cli
        try:
            def _cli(messages, model_hint=None, timeout=0, effort=None):
                captured.update(model_hint=model_hint, effort=effort, messages=messages)
                return ok_response("respuesta excepcional")
            subscription_llm.call_cli = _cli
            install({})
            response = llm.call_llm(huge, task="legal_draft")
            check("1j · el gate sí llega al CLI: Opus + --effort max (no capacidad muerta)",
                  response.choices[0].message.content == "respuesta excepcional"
                  and captured.get("model_hint") == "opus" and captured.get("effort") == "max")
        finally:
            subscription_llm.call_cli = saved_call
    with_policy("quality_adaptive", _adaptive)

    from mia.metrics import usage as usage_metrics
    check("1k · aliases adaptativos de suscripción tienen costo marginal cero (sin tarifa ficticia)",
          all(usage_metrics.estimated_call_cost(alias, MSG, 1000, task="legal_draft") == 0.0
              and usage_metrics.cost_usd(alias, 1000, 1000) == 0.0
              for alias in (llm.CLI_OPUS_ALIAS, llm.CLI_SONNET_ALIAS, llm.CLI_HAIKU_ALIAS)))

    # === 1l · Codex productivo es una política explícita, no eval/fallback ===
    def _codex():
        tasks = ("main", *llm.LEGAL_TASKS, "curator", "compression", *_AUX)
        check("1l · [codex] todas las tareas quedan en cli-codex, sin Claude/API/local",
              all(llm.resolve_fallback_chain(t) == [llm.CLI_CODEX_ALIAS] for t in tasks))
    with_policy("codex", _codex)

    # === 2 · política 'soberano' → todo mia-local ===
    def _sob():
        tasks = ("main", *llm.LEGAL_TASKS, "curator", "compression", *_AUX)
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
        check("3d · [nube] funciones jurídicas nunca degradan silenciosamente a local",
              all(llm.resolve_fallback_chain(t) == ["claude-sonnet"]
                  for t in llm.LEGAL_TASKS))
    with_policy("nube", _nub)

    # === 4 · compression BLOQUEADA ante model explícito en todas las políticas ===
    expected_locked = {"quality_adaptive": [llm.CLI_HAIKU_ALIAS],
                       "suscripcion": ["cli-claude-haiku"],
                       "codex": [llm.CLI_CODEX_ALIAS],
                       "nube": ["claude-haiku"], "soberano": ["mia-local"]}
    for pol, exp in expected_locked.items():
        with_policy(pol, lambda pol=pol, exp=exp: check(
            f"4 · [{pol}] compression ignora model explícito → {exp[0]}",
            llm.resolve_fallback_chain("compression", model="claude-opus") == exp))

    # Mutación adversarial: demuestra que la barrera ve reaparecer una API facturada
    # dentro de «Mis suscripciones», incluso en una tarea auxiliar bloqueada.
    original_adaptive_compression = llm._POLICY_CHAINS["quality_adaptive"]["compression"]
    try:
        llm._POLICY_CHAINS["quality_adaptive"]["compression"] = [
            llm.CLI_HAIKU_ALIAS, "claude-haiku",
        ]
        with_policy("quality_adaptive", lambda: check(
            "4b · mutación API en compression es detectada por la barrera de suscripción",
            any(not (a.startswith("cli-") or a == "mia-local")
                for a in llm.resolve_fallback_chain("compression"))))
    finally:
        llm._POLICY_CHAINS["quality_adaptive"]["compression"] = original_adaptive_compression

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

        fc = install({})

        def _call():
            failed = None
            try:
                llm.call_llm(MSG, task="main")
            except Exception as exc:  # expected: selected subscription has no silent substitute
                failed = exc
            check("5d · call_llm (suscripcion, CLI ausente) falla claro sin tocar API/local",
                  isinstance(failed, llm.LLMError) and "cli-claude" in str(failed))
            check("5e · no se llamó claude-sonnet", fc.count("claude-sonnet") == 0)
        with_policy("suscripcion", _call)
    finally:
        restore_cli(saved)

    # 5f · blindaje BatBadBut (CVE-2024-24576): un `claude` que resuelve a .cmd/.ps1
    # pasaría por cmd.exe al ejecutarse con lista de args → se trata como NO disponible.
    # La superficie es Windows (`os.name == "nt"` en subscription_llm._resolve_exe).
    if sys.platform == "win32":
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
    else:
        print("  [SKIP] 5f/5g BatBadBut: cmd.exe solo existe en Windows")

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
        check("6c-bis · --no-session-persistence presente (confirmado en `claude --help`, "
              "2026-09-23): esta llamada es -p/--max-turns 1, sin --resume/--continue, así "
              "que no persistir la sesión no pierde nada y deja de acumular un transcript "
              "de un mensaje por turno en el historial de Claude Code del operador",
              "--no-session-persistence" in cmd)
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

    # integración: CLI que falla → la política de suscripción falla claro, sin cobrar API
    saved = patch_cli(lambda *a, **k: _FakeProc(CLI_ERR_JSON, returncode=1))
    try:
        fc = install({})

        def _call():
            failed = None
            try:
                llm.call_llm(MSG, task="main")
            except Exception as exc:  # expected
                failed = exc
            check("7e · call_llm (suscripcion, CLI en error) no cambia a API sin autorización",
                  isinstance(failed, llm.LLMError) and fc.count("claude-sonnet") == 0)
        with_policy("suscripcion", _call)
    finally:
        restore_cli(saved)

    # === R5-3 · presupuesto POR INTENTO (regresión del R4-CRÍTICO, Codex ronda 4) ===
    # El dinero se reserva/liquida DENTRO de `_invoke_metered`, una vez por POST físico. Estos
    # checks fijan con VALORES CONOCIDOS los tres modos que el bug de Codex evadía (reservar UNA
    # vez por alias y liquidar con el usage del ÚLTIMO intento — o a 0):
    #   (a) N fallos que SÍ llegaron al proveedor → N estimaciones cobradas (no una sola, no 0);
    #   (b) fallos previos a un éxito → CADA intento liquida (no solo el último);
    #   (c) un éxito SIN usage legible → cobra la ESTIMACIÓN (NUNCA 0 — el bug histórico exacto).
    # Todo OFFLINE con el cliente falso (FakeCompletions); reserva/liquidación MOCKEADAS para
    # capturar los importes sin tocar la DB. Mutación (liquidar siempre 0.0, el bug de Codex):
    # al menos un check → ROJO (verificado editando `_invoke_metered` y restaurando).
    from mia.policy import budget as policy_budget

    MSG53 = [{"role": "user", "content": "x" * 4000}]
    # estimated_call_cost('claude-sonnet', MSG53, max_tokens=2000, task='main') → payload fijo:
    EST = 0.033045   # 1015 prompt-tok × 3.00 + 2000 compl-tok × 15.00, por Mtok

    def _ok_usage():
        # éxito con usage conocido: 1.0M prompt + 0.2M completion, SIN caché → 6.00 plano.
        return SimpleNamespace(
            usage=SimpleNamespace(prompt_tokens=1_000_000, completion_tokens=200_000,
                                  total_tokens=1_200_000,
                                  cache_read_input_tokens=0, cache_creation_input_tokens=0),
            choices=[SimpleNamespace(finish_reason="stop",
                                     message=SimpleNamespace(content="ok"))])

    def _ok_no_usage():
        return SimpleNamespace(
            usage=None,
            choices=[SimpleNamespace(finish_reason="stop",
                                     message=SimpleNamespace(content="ok"))])

    class _Boom500(Exception):
        status_code = 500   # llegó al proveedor (INCIERTO → se cobra); 500 → SERVER_ERROR (reintenta)

    def _settlements_for(outcomes: list) -> list[float]:
        """call_llm(model=claude-sonnet, max_tokens=2000) con un guion de intentos; devuelve las
        liquidaciones capturadas (una por POST físico). model explícito → cadena de un alias."""
        settled: list[float] = []
        install({"claude-sonnet": outcomes})
        orig_reserve = policy_budget.reserve_call_sync
        orig_finish = policy_budget.finish_call_sync
        tok = usage_metrics.set_usage_scope("00000000-0000-0000-0000-000000000000", None, "api")
        try:
            policy_budget.reserve_call_sync = lambda tenant, est, **kw: "hold-r53"
            policy_budget.finish_call_sync = (
                lambda tenant, hold, actual: settled.append(round(actual, 6)))
            try:
                llm.call_llm(MSG53, task="main", model="claude-sonnet", max_tokens=2000)
            except Exception:  # noqa: BLE001 — (a) agota la cadena y lanza; irrelevante aquí
                pass
        finally:
            policy_budget.reserve_call_sync = orig_reserve
            policy_budget.finish_call_sync = orig_finish
            usage_metrics.reset_usage_scope(tok)
            usage_metrics.drain()   # limpia el buffer de record() de los éxitos
        return settled

    def _approx(got: list[float], exp: list[float]) -> bool:
        return len(got) == len(exp) and all(abs(g - e) < 1e-9 for g, e in zip(got, exp))

    a53 = _settlements_for([_Boom500(), _Boom500(), _Boom500(), _Boom500()])
    check(f"R5-3(a) · 4 fallos que llegaron al proveedor → 4 estimaciones cobradas "
          f"(liquidaciones={a53}, suma={round(sum(a53), 6)} == 0.13218 = 4×{EST}); "
          f"mutación liquidar 0.0 en la vía de fallo → suma 0 → ROJO",
          _approx(a53, [EST, EST, EST, EST]) and abs(sum(a53) - 0.13218) < 1e-9)

    b53 = _settlements_for([_Boom500(), _Boom500(), _Boom500(), _ok_usage()])
    check(f"R5-3(b) · 3 fallos + éxito → 4 liquidaciones [est,est,est,6.00], no solo la última "
          f"({b53}); mutación liquidar 0.0 en el éxito → la 4ª cae a 0.0 → ROJO",
          _approx(b53, [EST, EST, EST, 6.0]))

    c53 = _settlements_for([_ok_no_usage()])
    check(f"R5-3(c) · éxito SIN usage legible → cobra la ESTIMACIÓN, nunca 0 "
          f"({c53} == [{EST}]); mutación liquidar 0.0 → 0.0 → ROJO (bug histórico de Codex)",
          _approx(c53, [EST]) and EST > 0)

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

    # === 10 · capacidad honesta: ausencia de Claude/Codex no se oculta a la UI ===
    from mia.api.routes import settings
    from mia.agent import codex_subscription_llm
    saved_available = subscription_llm.is_available
    saved_codex_available = codex_subscription_llm.is_available
    saved_codex_detect = codex_subscription_llm.detect_status
    saved_list_available = settings._hub.list_available
    try:
        subscription_llm.is_available = lambda: False
        codex_subscription_llm.is_available = lambda: False
        # D1 (d0aa95b): _codex_capability dejó de mirar is_available() y pasó a
        # detect_status() (tres hechos: instalada / sesión / habilitada). El doble
        # sigue el contrato NUEVO — con el viejo, este check dependía de si la
        # máquina del que corre el gate tiene Codex instalado (regla 78).
        codex_subscription_llm.detect_status = lambda: {
            "instalada": False, "sesion": False, "habilitada_por_politica": False,
            "disponible": False, "motivo": "no_instalada", "ruta": "",
        }
        settings._hub.list_available = lambda: {"codex": {"installed": False}}
        capabilities = settings._model_capabilities()
        check("10a · capabilities expone Claude y Codex ausentes sin prometer disponibilidad",
              capabilities["claude_code"]["installed"] is False
              and capabilities["codex"]["installed"] is False
              and capabilities["codex"]["enabled_here"] is False
              and capabilities["claude_code"]["max_is_exceptional"] is True)
        check("10b · efforts usa la interfaz pública, incluida la capacidad Max excepcional",
              tuple(capabilities["claude_code"]["available_efforts"])
              == subscription_llm.supported_efforts())
        activation = (ROOT / "frontend" / "app" / "activar" / "page.tsx").read_text(encoding="utf-8")
        # 10b-bis (decisión de Pipe 2026-08-14): el default del backend dice lo MISMO que
        # la pantalla de activación — un tenant que nunca guarda queda en la política que
        # la pantalla le mostró seleccionada. Cubre config, el fallback de llm y la UI.
        from mia import config as _config
        check("10b-bis · default backend = default UI = quality_adaptive",
              _config.MIA_MODEL_POLICY == "quality_adaptive"
              and llm._default_policy() == "quality_adaptive"
              and 'useState<Politica>("quality_adaptive")'
              in (ROOT / "frontend" / "app" / "activar" / "page.tsx").read_text(encoding="utf-8"))
        # 10c-bis (auditoría 2026-08-14): `capabilities` dejó de ser payload huérfano —
        # Ajustes deshabilita Codex cuando no está instalado y muestra blocked_reason.
        conexiones = (ROOT / "frontend" / "app" / "_components" /
                      "ConexionesSection.tsx").read_text(encoding="utf-8")
        # D1 (d0aa95b): la UI gatea por `enabled_here` (detectar ≠ habilitar), ya no
        # por `installed`. El gate verifica el concepto con la expresión vigente.
        check("10c-bis · Ajustes lee capabilities: Codex no disponible se deshabilita con razón",
              "capabilities?.codex?.enabled_here === false" in conexiones
              and "blocked_reason" in conexiones)
        check("10c · UI agrupa Claude/Codex como suscripciones y conserva preferencia explícita",
              'title="Mis suscripciones"' in activation
              and '<option value="quality_adaptive">Claude Code</option>' in activation
              and '<option value="codex">Codex</option>' in activation
              and "Requiere un plan Max" not in activation)
    finally:
        subscription_llm.is_available = saved_available
        codex_subscription_llm.is_available = saved_codex_available
        codex_subscription_llm.detect_status = saved_codex_detect
        settings._hub.list_available = saved_list_available


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
        print("model policy OK — políticas + CLI + ContextVar + tenant_settings verificados.")
        return 0
    print("model policy FAIL — HALT: no avanzar (CLAUDE.md §G).")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
