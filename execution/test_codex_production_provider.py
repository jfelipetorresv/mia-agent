"""Gate offline del proveedor productivo Codex: contrato, aislamiento y fail-closed.

No abre Codex ni consume cuota. Mockea el subproceso y prueba que la política ``codex``
no puede caer a Claude, API o local cuando Codex falta/falla.
"""
from __future__ import annotations

import json
import subprocess as real_subprocess
import sys
from pathlib import Path
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from mia.agent import codex_subscription_llm as codex, llm
from mia.agent.error_classifier import LLMError, LLMErrorKind, classify_llm_error
from mia import config
from mia.metrics import usage

RESULTS: list[tuple[str, bool]] = []


def check(name: str, value: bool) -> None:
    RESULTS.append((name, bool(value)))
    print(("  [OK]   " if value else "  [FAIL] ") + name)


class Proc:
    returncode = 0
    stdout = '{"usage":{"input_tokens":11,"output_tokens":7}}\n'
    stderr = ""


def main() -> int:
    messages = [{"role": "system", "content": "sistema privado"},
                {"role": "user", "content": "consulta confidencial"}]
    local_cors = ["http://localhost:3100", "http://127.0.0.1:3100"]
    check("0a · prod con app_dir/mode pero sin marca Tauri queda apagado",
          config.codex_membership_allowed("local_individual", "", "127.0.0.1", local_cors) is False)
    check("0b · la instalación Tauri local con loopback sí puede habilitar membresía",
          config.codex_membership_allowed(
              "local_individual", "tauri-local-v1", "127.0.0.1", local_cors,
          ) is True)
    check("0c · host remoto o CORS no local apagan membresía Codex",
          config.codex_membership_allowed(
              "local_individual", "tauri-local-v1", "0.0.0.0", local_cors,
          ) is False and config.codex_membership_allowed(
              "local_individual", "tauri-local-v1", "127.0.0.1", ["https://mia.example"],
          ) is False)
    tauri = (ROOT / "desktop" / "src-tauri" / "src" / "lib.rs").read_text(encoding="utf-8")
    check("0d · ambos lanzamientos Tauri fijan runtime y host loopback",
          tauri.count('command.env("MIA_DESKTOP_RUNTIME", "tauri-local-v1")') == 2
          and tauri.count('command.env("MIA_API_HOST", "127.0.0.1")') == 2)
    bootstrap = (ROOT / "backend" / "mia" / "setup" / "first_run.py").read_text(encoding="utf-8")
    check("0e · bootstrap no persiste las marcas efímeras de membresía",
          '"MIA_CODEX_MEMBERSHIP_MODE=local_individual"' not in bootstrap
          and '"MIA_DESKTOP_RUNTIME=tauri-local-v1"' not in bootstrap)
    captured: dict[str, object] = {}
    old_resolve, old_run = codex._resolve_exe, codex.subprocess.run
    old_local_mode = config.CODEX_MEMBERSHIP_LOCAL_ALLOWED
    try:
        config.CODEX_MEMBERSHIP_LOCAL_ALLOWED = True
        codex._resolve_exe = lambda: Path(r"C:\\Codex\\codex.exe")

        def fake_run(command, **kwargs):
            captured["command"] = command
            captured["kwargs"] = kwargs
            output = Path(command[command.index("--output-last-message") + 1])
            output.write_text(json.dumps({"content": "respuesta segura"}), encoding="utf-8")
            return Proc()

        codex.subprocess.run = fake_run
        response = codex.call_cli(messages, timeout=9, effort="high")
        command = captured["command"]
        kwargs = captured["kwargs"]
        check("1 · salida estructurada se adapta al contrato OpenAI de Mia",
              response.choices[0].message.content == "respuesta segura"
              and response.usage.total_tokens == 18 and response.mia_model_hint == codex.DEFAULT_MODEL)
        check("2 · prompt nunca viaja en la línea de comando",
              "consulta confidencial" not in " ".join(command) and "sistema privado" not in " ".join(command)
              and "consulta confidencial" in kwargs["input"])
        check("3 · aislamiento efectivo: efímero, solo lectura, sin configuración/reglas y sin shell/red/tools",
              all(flag in command for flag in ("--ephemeral", "--ignore-user-config", "--ignore-rules", "--sandbox", "read-only", "--strict-config"))
              and 'web_search="disabled"' in command and "features.shell_tool=false" in command
              and "features.multi_agent=false" in command and kwargs.get("shell", False) is False)
        env = kwargs["env"]
        check("4 · entorno solo conserva OAuth local y no filtra secretos de Mia",
              isinstance(env, dict) and "PATH" in env
              and not any(any(part in name.upper() for part in ("API_KEY", "SECRET", "PASSWORD", "TOKEN"))
                          or name.upper() == "DATABASE_URL" or name.upper().startswith("PG_") for name in env))
    finally:
        codex._resolve_exe, codex.subprocess.run = old_resolve, old_run
        config.CODEX_MEMBERSHIP_LOCAL_ALLOWED = old_local_mode

    old_local_mode = config.CODEX_MEMBERSHIP_LOCAL_ALLOWED
    try:
        config.CODEX_MEMBERSHIP_LOCAL_ALLOWED = False
        codex._resolve_exe = lambda: Path(r"C:\\Codex\\codex.exe")
        blocked = None
        try:
            codex.call_cli(messages)
        except Exception as exc:  # expected
            blocked = exc
        check("5 · la membresía Codex se bloquea fuera de la instalación local del titular",
              isinstance(blocked, codex.CodexCLIUnavailable)
              and "servidor" in str(blocked).lower())
        from mia.api.routes import settings
        capability = settings._model_capabilities()["codex"]
        check("6 · estado/UI marca Codex no disponible fuera del equipo local del titular",
              capability["installed"] is False and capability["local_membership_required"] is True
              and "servidores" in capability["blocked_reason"])
    finally:
        codex._resolve_exe = old_resolve
        config.CODEX_MEMBERSHIP_LOCAL_ALLOWED = old_local_mode

    old_resolve = codex._resolve_exe
    try:
        config.CODEX_MEMBERSHIP_LOCAL_ALLOWED = True
        codex._resolve_exe = lambda: None
        unavailable = None
        try:
            codex.call_cli(messages)
        except Exception as exc:  # expected
            unavailable = exc
        check("7 · Codex ausente falla claro como modelo no disponible", isinstance(unavailable, codex.CodexCLIUnavailable)
              and classify_llm_error(unavailable) is LLMErrorKind.MODEL_UNAVAILABLE)

        token = llm.set_model_policy("codex")
        try:
            llm._client = SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(
                create=lambda **_: (_ for _ in ()).throw(AssertionError("no debe tocar API")))))
            failed = None
            try:
                llm.call_llm(messages, task="legal_draft")
            except Exception as exc:  # expected: chain only cli-codex
                failed = exc
            check("8 · política Codex no cambia en silencio a Claude/API/local", isinstance(failed, LLMError)
                  and "cli-codex" in str(failed))
        finally:
            llm.reset_model_policy(token)
    finally:
        codex._resolve_exe = old_resolve
        config.CODEX_MEMBERSHIP_LOCAL_ALLOWED = old_local_mode

    token = llm.set_model_policy("codex")
    try:
        before = llm.resolve_fallback_chain("legal_draft")
        with llm.eval_provider_override("codex"):
            during = llm.resolve_fallback_chain("legal_draft")
        after = llm.resolve_fallback_chain("legal_draft")
        check("9 · el override de evaluación queda aislado y no convierte producción en cli-codex-eval",
              before == [llm.CLI_CODEX_ALIAS] and during == [llm._EVAL_CODEX_ALIAS]
              and after == [llm.CLI_CODEX_ALIAS])
    finally:
        llm.reset_model_policy(token)

    check("10 · coste marginal de suscripción Codex se registra como cero, no como API ficticia",
          usage.cost_usd("cli-codex", 1_000_000, 1_000_000) == 0.0
          and usage.estimated_call_cost("cli-codex", messages, 1000) == 0.0)
    passed = sum(ok for _, ok in RESULTS)
    print(f"\n{passed}/{len(RESULTS)} checks PASS")
    return 0 if passed == len(RESULTS) else 1


if __name__ == "__main__":
    raise SystemExit(main())
