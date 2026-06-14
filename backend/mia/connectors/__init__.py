"""Mia · connectors — conectores a fuentes de conocimiento del despacho.

`ObsidianSync` indexa un vault de Obsidian a la tabla `knowledge_chunks` (decisión #17):
conocimiento del despacho que NO es un expediente (≠ documents/chunks, que son por-asunto).
"""
from .obsidian_sync import ObsidianSync
from .pinecone_connector import (
    NoopPineconeConnector,
    PineconeConnector,
    PineconeConnectorBase,
    get_pinecone_connector,
)

__all__ = [
    "ObsidianSync",
    "PineconeConnectorBase",
    "PineconeConnector",
    "NoopPineconeConnector",
    "get_pinecone_connector",
]
