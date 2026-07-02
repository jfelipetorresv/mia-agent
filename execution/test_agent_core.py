"""
Mia · test_agent_core.py — verificación del Módulo 1a (MiaAgent + router call_llm).

Verifica OFFLINE (sin red ni proxy LiteLLM):
  1. La INVARIANTE crítica (decisión #7/#27): task="compression" está BLOQUEADA
     bajo LAS TRES políticas de modelo (CP2) — un `model` explícito se ignora y
     resuelve al alias que la política determina.
  2. El ruteo por cadena (H.5) bajo política explícita 'nube': main/None/desconocido
     → claude-sonnet→mia-local; auxiliares → claude-haiku; override no bloqueado pasa.
  3. MiaAgent.run_turn: arma [system, user], usa task="main", guarda la
     respuesta y mantiene el historial entre turnos.

call_llm se mockea (no se llama a ningún LLM real). Salida: exit 0 = PASS.

Se ejecuta con el python de mia/.venv:
    .venv\\Scripts\\python.exe execution\\test_agent_core.py
"""
from __future__ import annotations
import sys
from pathlib import Path
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))  # para `import mia.*`

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

from mia import config
from mia.agent import core, llm

_results: list[tuple[str, bool]] = []


def check(name: str, ok: bool) -> None:
    _results.append((name, bool(ok)))
    print(("  [OK]   " if ok else "  [FAIL] ") + name)


# --- 1 + 2 · routing, cadena de fallback (H.5) y la invariante de compression --------
# CP2: el ruteo depende de la POLÍTICA de modelo activa (decisión #27), así que cada
# check fija la política explícitamente con set/reset (patrón de test_model_policy.py).
def _with_policy(policy: str, fn) -> None:
    tok = llm.set_model_policy(policy)
    try:
        fn()
    finally:
        llm.reset_model_policy(tok)


def test_routing() -> None:
    # INVARIANTE (decisión #7/#27): compression BLOQUEADA bajo LAS TRES políticas —
    # el `model` explícito se ignora y resuelve al alias que la política determina.
    locked_first = {"suscripcion": "cli-claude-haiku", "nube": "claude-haiku",
                    "soberano": "mia-local"}
    for pol, exp in locked_first.items():
        def _locked(pol=pol, exp=exp):
            check(f"[{pol}] compression -> {exp}", llm.resolve_model("compression") == exp)
            check(f"[{pol}] compression IGNORA model=claude-sonnet (bloqueo #7/#27)",
                  llm.resolve_model("compression", model="claude-sonnet") == exp)
            check(f"[{pol}] compression IGNORA model=claude-opus (bloqueo #7/#27)",
                  llm.resolve_model("compression", model="claude-opus") == exp)
        _with_policy(pol, _locked)

    # Cadenas H.5 bajo política 'nube' (API Anthropic): main/None/desconocido → sonnet.
    def _nube():
        check("[nube] compression sin fallback (cadena de un alias)",
              llm.resolve_fallback_chain("compression") == ["claude-haiku"])
        check("[nube] verification -> claude-haiku (auxiliar barata)",
              llm.resolve_model("verification") == "claude-haiku")
        check("[nube] main -> claude-sonnet (preferido)", llm.resolve_model("main") == "claude-sonnet")
        check("[nube] main tiene fallback a mia-local",
              llm.resolve_fallback_chain("main") == ["claude-sonnet", "mia-local"])
        check("[nube] task=None -> cadena de main", llm.resolve_model(None) == "claude-sonnet")
        check("[nube] task desconocido -> cadena de main", llm.resolve_model("xyz") == "claude-sonnet")

        # Override explícito (tarea no bloqueada): cadena de UN alias, sin fallback.
        check("[nube] verification SI acepta override (no bloqueada)",
              llm.resolve_model("verification", model="claude-haiku") == "claude-haiku")
        check("[nube] override explícito → cadena de un alias (sin fallback)",
              llm.resolve_fallback_chain("main", model="mia-local") == ["mia-local"])
    _with_policy("nube", _nube)

    # 'soberano': cero salida de datos — todo mia-local.
    def _soberano():
        check("[soberano] verification -> mia-local", llm.resolve_model("verification") == "mia-local")
        check("[soberano] main -> mia-local", llm.resolve_model("main") == "mia-local")
    _with_policy("soberano", _soberano)


# --- 3 · MiaAgent.run_turn ------------------------------------------------------
_captured: dict = {}


def _fake_call_llm(messages, *, task=None, model=None, temperature=None, **kw):
    _captured["messages"] = messages
    _captured["task"] = task
    _captured["model"] = model
    msg = SimpleNamespace(content="respuesta de prueba")
    return SimpleNamespace(choices=[SimpleNamespace(message=msg)])


def test_agent() -> None:
    original = llm.call_llm
    llm.call_llm = _fake_call_llm  # core hace `llm.call_llm(...)` -> ve el parche
    try:
        agent = core.MiaAgent(tenant_id="t-123")
        out = agent.run_turn("¿Caducó la acción?")

        check("run_turn devuelve el contenido del LLM", out == "respuesta de prueba")
        check("usa task='main'", _captured.get("task") == "main")

        sent = _captured.get("messages", [])
        # Desde 1b el system prompt son 10 capas; la identidad (L1) es la primera,
        # así que el contenido EMPIEZA con DEFAULT_IDENTITY (ya no es igual a ella).
        check("primer mensaje es system y empieza con la identidad (L1)",
              bool(sent) and sent[0]["role"] == "system"
              and sent[0]["content"].startswith(core.DEFAULT_IDENTITY))
        check("segundo mensaje es el user con el texto",
              len(sent) >= 2 and sent[1] == {"role": "user", "content": "¿Caducó la acción?"})

        check("historial = [user, assistant] tras 1 turno",
              agent.messages == [
                  {"role": "user", "content": "¿Caducó la acción?"},
                  {"role": "assistant", "content": "respuesta de prueba"},
              ])

        # Segundo turno: el historial crece y el system NO se guarda en messages.
        agent.run_turn("¿Y la prescripción?")
        check("historial crece a 4 tras 2 turnos", len(agent.messages) == 4)
        check("system se reenvía pero no se persiste en messages",
              all(m["role"] != "system" for m in agent.messages))
    finally:
        llm.call_llm = original


def main() -> int:
    print("== Módulo 1a · MiaAgent + router call_llm ==")
    test_routing()
    test_agent()
    passed = sum(1 for _, ok in _results if ok)
    total = len(_results)
    print(f"\n{passed}/{total} checks PASS")
    return 0 if passed == total else 1


if __name__ == "__main__":
    raise SystemExit(main())
