"""Mia · onboarding — entrevista de identidad del despacho (Módulo 5).

Construye el SOUL.md (la capa 1 del prompt, la identidad del agente) de forma
conversacional a partir de las respuestas del abogado. El SOUL.md vive por tenant
en $MIA_HOME/soul_{tenant_id}.md (estado de instancia por despacho, gitignored).

OJO con los nombres: esto NO es el `/memory/` de construcción (memoria para Claude
Code) ni el paquete `backend/mia/memory/` (memoria en ejecución 2a-2d). Es la
identidad/persona del agente — el SOUL.md que menciona CLAUDE.md (§A).
"""
from __future__ import annotations

from .soul_interview import (
    QUESTIONS,
    SOUL_TEMPLATE,
    SoulInterview,
    load_responses,
    load_soul_snapshot,
    load_soul_text,
    soul_path,
    soul_status,
)

__all__ = [
    "SoulInterview",
    "QUESTIONS",
    "SOUL_TEMPLATE",
    "soul_path",
    "load_soul_text",
    "load_soul_snapshot",
    "soul_status",
    "load_responses",
]
