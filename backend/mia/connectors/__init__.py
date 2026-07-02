"""Mia · connectors — conectores a fuentes de conocimiento del despacho.

`ObsidianSync` indexa un vault de Obsidian a la tabla `knowledge_chunks` (decisión #17):
conocimiento del despacho que NO es un expediente (≠ documents/chunks, que son por-asunto).
`LocalFolderSync` indexa las carpetas de trabajo registradas (allowlist) del abogado —
disco local, OneDrive y Google Drive espejo — a la misma tabla (CP-C1, decisión #30).
`VaultWriter` es la vía de VUELTA (CP-C2, decisión #32): escribe la memoria de Mia
(conceptos y reportes) como notas .md en el vault, SOLO bajo `{vault}/Mia/`.
"""
from .local_folders import LocalFolderSync, detect_cloud_folders
from .obsidian_sync import ObsidianSync
from .vault_writer import VaultWriter
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
    "VaultWriter",
    "PineconeConnectorBase",
    "PineconeConnector",
    "NoopPineconeConnector",
    "get_pinecone_connector",
]
