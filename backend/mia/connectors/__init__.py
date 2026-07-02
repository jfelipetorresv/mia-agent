"""Mia · connectors — conectores a fuentes de conocimiento del despacho.

`ObsidianSync` indexa un vault de Obsidian a la tabla `knowledge_chunks` (decisión #17):
conocimiento del despacho que NO es un expediente (≠ documents/chunks, que son por-asunto).
`LocalFolderSync` indexa las carpetas de trabajo registradas (allowlist) del abogado —
disco local, OneDrive y Google Drive espejo — a la misma tabla (CP-C1, decisión #30).
"""
from .local_folders import LocalFolderSync, detect_cloud_folders
from .obsidian_sync import ObsidianSync
from .pinecone_connector import (
    NoopPineconeConnector,
    PineconeConnector,
    PineconeConnectorBase,
    get_pinecone_connector,
)

__all__ = [
    "LocalFolderSync",
    "detect_cloud_folders",
    "ObsidianSync",
    "PineconeConnectorBase",
    "PineconeConnector",
    "NoopPineconeConnector",
    "get_pinecone_connector",
]
