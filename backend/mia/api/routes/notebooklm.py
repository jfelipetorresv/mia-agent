"""Mia · api.routes.notebooklm — instalar y conectar NotebookLM desde el producto (CP-NLM).

GET  /api/notebooklm/status          → estado (no_instalado/instalando/…/conectado) en llano
POST /api/notebooklm/install         → instala el CLI en background (consent-first)
POST /api/notebooklm/connect         → abre el navegador para el login de Google
POST /api/notebooklm/connect/confirm → «ya inicié sesión»: captura la sesión
GET  /api/notebooklm/notebooks       → lista los notebooks del abogado (para el selector)

La consulta EN VIVO (que sí saca preguntas a Google) NO vive aquí: pasa por el candado de
`connectors/notebooklm/gate.py` durante la investigación. Estas rutas solo instalan/conectan
la herramienta y leen la lista de notebooks del propio abogado (metadata, sin datos de cliente).
El opt-in y el notebook elegido se guardan por `/settings/model-policy` (routes/settings.py).
"""
from __future__ import annotations

import asyncio
import logging

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel

from ...connectors.notebooklm import setup as nlm_setup

logger = logging.getLogger(__name__)

router = APIRouter(tags=["notebooklm"])


class InstallBody(BaseModel):
    """Consent-first (patrón Instalar dictado por voz): sin confirmación, no se instala nada."""

    confirmar: bool = False


def _tenant(request: Request) -> str:
    t = getattr(request.state, "tenant_id", None)
    if not t:
        raise HTTPException(status_code=401, detail="Tu sesión no es válida. Vuelve a iniciar sesión.")
    return t


@router.get("/notebooklm/status")
async def status(request: Request):
    """Estado para la tarjeta de Conexiones (mira disco → thread)."""
    _tenant(request)
    return await asyncio.to_thread(nlm_setup.get_status)


@router.post("/notebooklm/install")
async def install(request: Request, body: InstallBody):
    """Instala el CLL de NotebookLM en un entorno aislado (background, single-flight)."""
    _tenant(request)
    if not body.confirmar:
        raise HTTPException(
            status_code=400,
            detail=("Para continuar necesito tu confirmación: esta acción descarga e instala "
                    "NotebookLM (unos cientos de MB) en este equipo. Vuelve a intentarlo "
                    "confirmando la instalación."),
        )
    return await asyncio.to_thread(nlm_setup.start_install)


@router.post("/notebooklm/connect")
async def connect(request: Request):
    """Abre el navegador para que el abogado inicie sesión en Google (background)."""
    _tenant(request)
    return await asyncio.to_thread(nlm_setup.start_login)


@router.post("/notebooklm/connect/confirm")
async def connect_confirm(request: Request):
    """El abogado pulsó «Ya inicié sesión»: se captura la sesión de Google."""
    _tenant(request)
    return await asyncio.to_thread(nlm_setup.confirm_login)


@router.get("/notebooklm/notebooks")
async def notebooks(request: Request):
    """Notebooks del abogado (para el selector). [] si no está conectado (subprocess → thread)."""
    _tenant(request)
    lista = await asyncio.to_thread(nlm_setup.list_notebooks)
    return {"notebooks": lista}
