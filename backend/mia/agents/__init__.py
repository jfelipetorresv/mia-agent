"""Mia · agents — orquestación del agente con LangGraph (Módulo 1d).

StateGraph tipado (state.py) + 5 nodos (graph.py) + checkpointing
AsyncPostgresSaver (checkpointer.py) con HITL vía interrupt(). El frontend nunca
ve jerga técnica (§G): la capa SSE traduce el avance del grafo a "Mia está
analizando", "Borrador listo para tu aprobación", etc.
"""
from .state import MatterState, thread_id_for

__all__ = ["MatterState", "thread_id_for"]
