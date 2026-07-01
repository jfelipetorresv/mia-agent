"""Mia · agent.auxiliary_client — cliente para tareas LLM auxiliares.

Envuelve `call_llm` (el router de llm.py) con una API que DEVUELVE TEXTO en vez
del objeto OpenAI crudo, pensada para las tareas auxiliares del agente: compresión
de contexto, verificación de citas, generación de títulos, búsqueda en sesión,
extracción web y visión.

Adaptado del `agent/auxiliary_client.py` de Hermes (~5.800 líneas): allí esa clase
resuelve ~20 proveedores + auth + formato a mano; en Mia el ruteo lo hace LiteLLM
(decisión #3), así que esto es una FACHADA DELGADA sobre `call_llm`. La lista de
tareas (`TASK_MODELS`) es la misma fuente única que usa el router.

INVARIANTE (CLAUDE.md §D · decisión #7): `complete(task="compression")` usa
claude-haiku SIEMPRE. El bloqueo vive en `llm.resolve_model` (`_LOCKED_TASKS`);
esta fachada lo HEREDA por construcción — un `model` explícito para compression se
ignora aquí también, porque `complete()` se limita a delegar en `call_llm`.
"""
from __future__ import annotations

from typing import Any

from . import llm

# Mapa COMPLETO task -> alias PREFERIDO (primer eslabón de la cadena de fallback).
# Fuente única: llm._TASK_FALLBACK_CHAINS (mismo paquete, H.5). Se re-exporta como público
# para los consumidores de tareas auxiliares que solo necesitan el proveedor preferido.
TASK_MODELS: dict[str, str] = {task: chain[0] for task, chain in llm._TASK_FALLBACK_CHAINS.items()}
LOCKED_TASKS = llm._LOCKED_TASKS


def _as_messages(prompt: str | list[dict]) -> list[dict]:
    """Acepta un string (lo envuelve como mensaje de usuario) o una lista de
    mensajes ya armada, y devuelve siempre una lista de mensajes."""
    if isinstance(prompt, str):
        return [{"role": "user", "content": prompt}]
    return prompt


class AuxiliaryClient:
    """Fachada sobre `call_llm` para tareas auxiliares. `complete()` devuelve texto.

    No mantiene estado: cada llamada resuelve modelo + delega en el router. El
    cliente OpenAI subyacente (apuntado al proxy LiteLLM) lo gestiona llm.py.
    """

    def complete(
        self,
        prompt: str | list[dict],
        *,
        task: str | None = None,
        model: str | None = None,
        temperature: float | None = None,
        max_tokens: int | None = None,
        **extra: Any,
    ) -> str:
        """Ejecuta una tarea auxiliar y devuelve el TEXTO de la respuesta.

        `task` elige el modelo (ver `llm.resolve_model`). `compression` queda
        bloqueado a claude-haiku aunque se pase `model` (decisión #7), porque el
        bloqueo está en `resolve_model`, que `call_llm` invoca.
        """
        resp = llm.call_llm(
            _as_messages(prompt),
            task=task,
            model=model,
            temperature=temperature,
            max_tokens=max_tokens,
            **extra,
        )
        return resp.choices[0].message.content or ""

    @staticmethod
    def model_for(task: str | None, model: str | None = None) -> str:
        """Modelo que se usaría para `task` (sin llamar al LLM). Respeta el bloqueo
        de compression. Útil para inspección, logging y tests."""
        return llm.resolve_model(task, model)


# Instancia por defecto lista para usar (el cliente no tiene estado).
aux = AuxiliaryClient()
