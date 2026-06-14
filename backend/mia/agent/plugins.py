"""Mia · agent.plugins — sistema de plugins con 6 hooks de ciclo de vida.

Adaptado del patrón de Hermes (hermes_cli/plugins.py): un `PluginManager` con un
conjunto FIJO de hooks válidos; los plugins registran handlers y el núcleo los
dispara en los puntos del ciclo de vida. Hermes tiene ~12 hooks; Mia fija
EXACTAMENTE 6, en orden de ciclo de vida:

    on_session_start   → arranca la sesión del asunto
      pre_llm_call     → antes de cada llamada al LLM (puede modificar mensajes)
      pre_tool_call    → antes de ejecutar una herramienta (puede BLOQUEARLA)
      post_tool_call   → tras la herramienta (puede modificar su resultado)
      post_llm_call    → tras la respuesta del LLM (puede modificar el texto)
    on_session_end     → cierra la sesión del asunto

Cada hook recibe un `ctx` (dict mutable). Un plugin INTERCEPTA un hook
sobre-escribiendo el método correspondiente y: (a) leyendo el ctx, (b) mutándolo
in-place, o (c) devolviendo un ctx de reemplazo. Para bloquear una herramienta,
`pre_tool_call` marca `ctx["blocked"] = True` (lo honra el executor de tools, 1d).

Wiring (ver core.py): `pre_llm_call`/`post_llm_call` se disparan en
`MiaAgent.run_turn`; `on_session_start`/`on_session_end` en
`start_session`/`end_session`; `pre_tool_call`/`post_tool_call` desde el executor
de herramientas en 1d (todavía no hay tools).
"""
from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger("mia.agent.plugins")

# Los 6 hooks, en ORDEN de ciclo de vida. Esta tupla es el contrato del módulo.
HOOKS: tuple[str, ...] = (
    "on_session_start",
    "pre_llm_call",
    "pre_tool_call",
    "post_tool_call",
    "post_llm_call",
    "on_session_end",
)
_HOOKSET = frozenset(HOOKS)


class Plugin:
    """Base de un plugin. Sobre-escribe los hooks que te interesen; el resto son
    no-op. Heredar de `Plugin` no es obligatorio: el manager acepta cualquier
    objeto que exponga métodos con el nombre de un hook (duck-typing), así que un
    plugin puede implementar solo un subconjunto de los 6.
    """

    name: str = "plugin"

    def on_session_start(self, ctx: dict) -> Any: ...
    def pre_llm_call(self, ctx: dict) -> Any: ...
    def pre_tool_call(self, ctx: dict) -> Any: ...
    def post_tool_call(self, ctx: dict) -> Any: ...
    def post_llm_call(self, ctx: dict) -> Any: ...
    def on_session_end(self, ctx: dict) -> Any: ...


class PluginManager:
    """Registra plugins y dispara hooks en orden de REGISTRO.

    `dispatch(hook, ctx)` recorre los plugins registrados, llama el método del hook
    en cada uno (si lo expone) y devuelve el ctx (posiblemente mutado/reemplazado).
    """

    HOOKS: tuple[str, ...] = HOOKS  # expuesto para inspección

    def __init__(self) -> None:
        self._plugins: list[Any] = []

    def register(self, plugin: Any) -> Any:
        """Registra un plugin. Devuelve el plugin para encadenar."""
        self._plugins.append(plugin)
        logger.debug("plugin registrado: %s", getattr(plugin, "name", plugin))
        return plugin

    @property
    def plugins(self) -> list[Any]:
        """Copia de la lista de plugins, en orden de registro."""
        return list(self._plugins)

    def hooks_implemented(self, plugin: Any) -> list[str]:
        """Qué hooks (de los 6) sobre-escribe realmente este plugin.

        Distingue el método propio del no-op de la base `Plugin`, para poder
        afirmar 'este plugin registra estos hooks'.
        """
        out = []
        for hook in HOOKS:
            method = getattr(type(plugin), hook, None)
            base = getattr(Plugin, hook, None)
            if method is not None and method is not base:
                out.append(hook)
        return out

    def dispatch(self, hook: str, ctx: dict | None = None) -> dict:
        """Dispara `hook` en todos los plugins, en orden de registro.

        Lanza ValueError si el hook no es uno de los 6 (fail-fast, no como Hermes
        que solo avisa). Un plugin puede mutar el ctx in-place o devolver uno nuevo.
        """
        if hook not in _HOOKSET:
            raise ValueError(f"hook desconocido '{hook}'. Válidos: {', '.join(HOOKS)}")
        if ctx is None:
            ctx = {}
        for plugin in self._plugins:
            method = getattr(plugin, hook, None)
            if method is None:
                continue
            result = method(ctx)
            if isinstance(result, dict):  # el plugin puede reemplazar el ctx
                ctx = result
        return ctx
