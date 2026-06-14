"""
Mia · test_plugins.py — gate del Módulo 1c (sistema de plugins, 6 hooks).

Verifica OFFLINE (sin red ni proxy LiteLLM):
  1. Existen EXACTAMENTE los 6 hooks esperados y un hook desconocido falla.
  2. Un plugin de prueba puede INTERCEPTAR cada uno de los 6 hooks (los registra
     y se disparan).
  3. Los hooks se disparan en el ORDEN correcto:
       a) varios plugins para un mismo hook → en orden de registro;
       b) el ciclo de vida completo → en el orden de HOOKS.
  4. La intercepción es real: un plugin muta el ctx (modifica mensajes, reescribe
     la respuesta, bloquea una herramienta) y el efecto se observa.
  5. Integración con MiaAgent: pre_llm_call/post_llm_call se disparan en run_turn
     (call_llm mockeado); sin plugins el turno no cambia.

Salida: exit 0 = PASS.
    .venv\\Scripts\\python.exe execution\\test_plugins.py
"""
from __future__ import annotations
import sys
from pathlib import Path
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))  # para `import mia.*`

from mia.agent import core, llm
from mia.agent.plugins import HOOKS, Plugin, PluginManager

_results: list[tuple[str, bool]] = []


def check(name: str, ok: bool) -> None:
    _results.append((name, bool(ok)))
    print(("  [OK]   " if ok else "  [FAIL] ") + name)


_EXPECTED_HOOKS = (
    "on_session_start",
    "pre_llm_call",
    "pre_tool_call",
    "post_tool_call",
    "post_llm_call",
    "on_session_end",
)


# --- 1 · los 6 hooks, ni más ni menos -----------------------------------------
def test_hook_set() -> None:
    check("hay exactamente 6 hooks", len(HOOKS) == 6)
    check("los 6 nombres son los esperados, en orden", tuple(HOOKS) == _EXPECTED_HOOKS)
    mgr = PluginManager()
    check("PluginManager.HOOKS expone los 6", tuple(mgr.HOOKS) == _EXPECTED_HOOKS)
    # Un hook desconocido falla (fail-fast).
    raised = False
    try:
        mgr.dispatch("on_everything", {})
    except ValueError:
        raised = True
    check("dispatch de un hook desconocido lanza ValueError", raised)


# --- 2 + 4 · un plugin intercepta cada hook -----------------------------------
class _RecorderPlugin(Plugin):
    """Sobre-escribe los 6 hooks y registra el orden en que los recibe."""

    name = "recorder"

    def __init__(self) -> None:
        self.seen: list[str] = []

    def _rec(self, hook: str, ctx: dict) -> None:
        self.seen.append(hook)
        ctx.setdefault("trail", []).append(hook)

    def on_session_start(self, ctx): self._rec("on_session_start", ctx)
    def pre_llm_call(self, ctx): self._rec("pre_llm_call", ctx)
    def pre_tool_call(self, ctx): self._rec("pre_tool_call", ctx)
    def post_tool_call(self, ctx): self._rec("post_tool_call", ctx)
    def post_llm_call(self, ctx): self._rec("post_llm_call", ctx)
    def on_session_end(self, ctx): self._rec("on_session_end", ctx)


def test_intercept_each_hook() -> None:
    mgr = PluginManager()
    rec = _RecorderPlugin()
    mgr.register(rec)

    # El plugin registra (sobre-escribe) los 6 hooks.
    check("el plugin registra los 6 hooks", mgr.hooks_implemented(rec) == list(_EXPECTED_HOOKS))

    # Disparar el ciclo de vida completo en orden → el plugin intercepta cada uno.
    for hook in _EXPECTED_HOOKS:
        mgr.dispatch(hook, {})
    check("el plugin interceptó los 6 hooks", rec.seen == list(_EXPECTED_HOOKS))


# --- 3a · varios plugins → orden de registro ----------------------------------
class _Tagger(Plugin):
    def __init__(self, tag: str) -> None:
        self.tag = tag

    def pre_llm_call(self, ctx):
        ctx.setdefault("order", []).append(self.tag)


def test_registration_order() -> None:
    mgr = PluginManager()
    mgr.register(_Tagger("A"))
    mgr.register(_Tagger("B"))
    mgr.register(_Tagger("C"))
    ctx = mgr.dispatch("pre_llm_call", {})
    check("varios plugins se disparan en orden de registro", ctx["order"] == ["A", "B", "C"])


# --- 4 · intercepción real: mutar ctx, reescribir, bloquear -------------------
class _MessageInjector(Plugin):
    def pre_llm_call(self, ctx):
        ctx["messages"].append({"role": "system", "content": "nota inyectada"})


class _ResponseRewriter(Plugin):
    def post_llm_call(self, ctx):
        ctx["content"] = ctx["content"].upper()


class _ToolBlocker(Plugin):
    def pre_tool_call(self, ctx):
        ctx["blocked"] = True
        ctx["block_reason"] = "herramienta no permitida"


def test_real_interception() -> None:
    mgr = PluginManager()
    mgr.register(_MessageInjector())
    ctx = mgr.dispatch("pre_llm_call", {"messages": [{"role": "user", "content": "hola"}]})
    check("pre_llm_call puede inyectar un mensaje", len(ctx["messages"]) == 2)

    mgr2 = PluginManager()
    mgr2.register(_ResponseRewriter())
    ctx2 = mgr2.dispatch("post_llm_call", {"content": "respuesta"})
    check("post_llm_call puede reescribir la respuesta", ctx2["content"] == "RESPUESTA")

    mgr3 = PluginManager()
    mgr3.register(_ToolBlocker())
    ctx3 = mgr3.dispatch("pre_tool_call", {"tool": "borrar_expediente"})
    check("pre_tool_call puede BLOQUEAR una herramienta", ctx3.get("blocked") is True)


# --- 5 · integración con MiaAgent ---------------------------------------------
_captured: dict = {}


def _fake_call_llm(messages, *, task=None, model=None, temperature=None, **kw):
    _captured["messages"] = messages
    msg = SimpleNamespace(content="respuesta original")
    return SimpleNamespace(choices=[SimpleNamespace(message=msg)])


def test_agent_integration() -> None:
    original = llm.call_llm
    llm.call_llm = _fake_call_llm
    try:
        # Sin plugins: el turno no cambia (no-op), la respuesta es la del LLM.
        agent = core.MiaAgent(tenant_id="t-1")
        out = agent.run_turn("¿Caducó la acción?")
        check("sin plugins run_turn devuelve la respuesta del LLM", out == "respuesta original")

        # Con plugins: pre_llm_call inyecta, post_llm_call reescribe.
        agent2 = core.MiaAgent(tenant_id="t-2")
        agent2.plugins.register(_MessageInjector())
        agent2.plugins.register(_ResponseRewriter())
        out2 = agent2.run_turn("¿Y la prescripción?")
        check("pre_llm_call de un plugin llega a call_llm (mensaje inyectado)",
              any(m.get("content") == "nota inyectada" for m in _captured["messages"]))
        check("post_llm_call reescribe la respuesta guardada", out2 == "RESPUESTA ORIGINAL")
        check("el historial guarda la respuesta reescrita",
              agent2.messages[-1] == {"role": "assistant", "content": "RESPUESTA ORIGINAL"})

        # start_session / end_session disparan los hooks de sesión.
        rec = _RecorderPlugin()
        agent3 = core.MiaAgent(tenant_id="t-3")
        agent3.plugins.register(rec)
        agent3.start_session()
        agent3.end_session()
        check("start_session dispara on_session_start", "on_session_start" in rec.seen)
        check("end_session dispara on_session_end", "on_session_end" in rec.seen)
    finally:
        llm.call_llm = original


def main() -> int:
    print("== Módulo 1c · sistema de plugins (6 hooks) ==")
    test_hook_set()
    test_intercept_each_hook()
    test_registration_order()
    test_real_interception()
    test_agent_integration()
    passed = sum(1 for _, ok in _results if ok)
    total = len(_results)
    print(f"\n{passed}/{total} checks PASS")
    return 0 if passed == total else 1


if __name__ == "__main__":
    raise SystemExit(main())
