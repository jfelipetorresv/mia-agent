"""Mia · memory — subsistema de memoria EN EJECUCIÓN del agente.

OJO: NO confundir con el directorio `/memory/` de la RAÍZ del repo, que es la
memoria de CONSTRUCCIÓN para Claude Code (progress.md, task_plan.md…). Este
paquete Python es la memoria del agente cuando corre:

  2a ProfileManager    — perfiles abogado/despacho, frozen al inicio del asunto.
  2b PlaybookManager   — índice siempre presente + contenido del playbook on-demand.
  2c ContextCompressor — compresión de contexto (claude-haiku) [pendiente].
  2d TraceCapture      — trazas JSONL para SFT/LoRA posterior.
"""
from .curator import Curator
from .feedback_processor import FeedbackProcessor
from .playbook_manager import (
    PLAYBOOK_INDEX_MAX_TOKENS,
    Playbook,
    PlaybookManager,
)
from .profile_manager import (
    PERFIL_ABOGADO_MAX_TOKENS,
    PERFIL_DESPACHO_MAX_TOKENS,
    ProfileManager,
    ProfileSnapshot,
)
from .tokens import estimate_tokens
from .trace_capture import TRACE_SCHEMA, Trace, TraceCapture

__all__ = [
    "ProfileManager",
    "ProfileSnapshot",
    "PERFIL_ABOGADO_MAX_TOKENS",
    "PERFIL_DESPACHO_MAX_TOKENS",
    "Playbook",
    "PlaybookManager",
    "PLAYBOOK_INDEX_MAX_TOKENS",
    "Curator",
    "FeedbackProcessor",
    "TraceCapture",
    "Trace",
    "TRACE_SCHEMA",
    "estimate_tokens",
]
