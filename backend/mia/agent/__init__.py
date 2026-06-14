"""Mia · agent — núcleo del agente legal cognitivo (Módulo 1).

1a: MiaAgent + router call_llm(task=...) por LiteLLM.
1b (este paquete, hoy): prompt_builder (10 capas) + AuxiliaryClient completo.
1c: plugins (6 hooks). 1d: LangGraph StateGraph + SSE + HITL. 1e: Agent Hub.
"""
from .auxiliary_client import AuxiliaryClient, aux
from .core import MiaAgent
from .llm import call_llm, resolve_model
from .plugins import HOOKS, Plugin, PluginManager

__all__ = [
    "MiaAgent",
    "call_llm",
    "resolve_model",
    "AuxiliaryClient",
    "aux",
    "Plugin",
    "PluginManager",
    "HOOKS",
]
