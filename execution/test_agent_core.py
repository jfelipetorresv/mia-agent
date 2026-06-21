"""
Mia · test_agent_core.py — verificación del Módulo 1a (MiaAgent + router call_llm).

Verifica OFFLINE (sin red ni proxy LiteLLM):
  1. La INVARIANTE crítica (decisión #7, override #23): task="compression" =>
     mia-local SIEMPRE, incluso si se pasa otro `model` explícito (bloqueo).
  2. El mapa task -> modelo (verification=mia-local, main/None=MIA_MODEL).
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

from mia import config
from mia.agent import core, llm

_results: list[tuple[str, bool]] = []


def check(name: str, ok: bool) -> None:
    _results.append((name, bool(ok)))
    print(("  [OK]   " if ok else "  [FAIL] ") + name)


# --- 1 + 2 · routing y la invariante de compression ----------------------------
def test_routing() -> None:
    # OVERRIDE decisión #23 (2026-06-20): todos los tasks -> mia-local (sin créditos Anthropic).
    # compression sigue BLOQUEADA en _LOCKED_TASKS; solo cambió el destino fijo a mia-local.
    check("compression -> mia-local", llm.resolve_model("compression") == "mia-local")
    check(
        "compression IGNORA model=claude-sonnet (bloqueo decision #7/#23)",
        llm.resolve_model("compression", model="claude-sonnet") == "mia-local",
    )
    check(
        "compression IGNORA model=claude-opus (bloqueo decision #7/#23)",
        llm.resolve_model("compression", model="claude-opus") == "mia-local",
    )
    check("verification -> mia-local", llm.resolve_model("verification") == "mia-local")
    check("main -> MIA_MODEL", llm.resolve_model("main") == config.MIA_MODEL)
    check("task=None -> MIA_MODEL", llm.resolve_model(None) == config.MIA_MODEL)
    check("task desconocido -> MIA_MODEL", llm.resolve_model("xyz") == config.MIA_MODEL)
    check(
        "verification SI acepta override (no bloqueada)",
        llm.resolve_model("verification", model="claude-haiku") == "claude-haiku",
    )


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
