"""Mia · api.routes.folders — CARPETAS DE TRABAJO del despacho (CP-C1, Pilar C · decisión #30).

Superficie HTTP de la allowlist de carpetas locales/nubes espejo (connectors/local_folders):
  GET    /api/folders/detected  → nubes detectadas (OneDrive/Google Drive) + fuentes registradas
  POST   /api/folders           → registrar una carpeta (validación de seguridad fail-closed)
  DELETE /api/folders/{id}      → deshabilitar una fuente (borra su conocimiento indexado)
  POST   /api/folders/sync      → dispara la sincronización del tenant en segundo plano

Auth: el middleware JWT fija `request.state.tenant_id` (RLS). §G: errores sin jerga técnica.
Privacidad primero: Mia NUNCA escanea nada fuera de las carpetas registradas.
"""
from __future__ import annotations

import logging

from fastapi import APIRouter, BackgroundTasks, HTTPException, Request
from pydantic import BaseModel, Field

from ...connectors.local_folders import (
    LocalFolderSync,
    detect_cloud_folders,
    disable_source,
    list_sources,
    register_source,
)

router = APIRouter(prefix="/folders", tags=["folders"])
logger = logging.getLogger("mia.api.folders")


def _tenant(request: Request) -> str:
    tid = getattr(request.state, "tenant_id", None)
    if not tid:
        raise HTTPException(status_code=401, detail="Sin sesión activa")
    return tid


class FolderBody(BaseModel):
    path: str = Field(min_length=1, max_length=4096)
    label: str | None = Field(default=None, max_length=200)
    kind: str = Field(default="knowledge", max_length=20)


@router.get("/detected")
async def detected_folders(request: Request):
    """Nubes espejo detectadas en este equipo + carpetas ya registradas del despacho."""
    tid = _tenant(request)
    sources = await list_sources(tid, include_disabled=True)
    registered_paths = {s["path"] for s in sources if s["enabled"]}
    detected = [
        {**c, "registered": c["path"] in registered_paths}
        for c in detect_cloud_folders()
    ]
    return {"detected": detected, "sources": sources}


@router.post("")
async def add_folder(body: FolderBody, request: Request):
    """Registra una carpeta en la allowlist del despacho (tras validar que sea segura)."""
    tid = _tenant(request)
    try:
        return await register_source(tid, body.path, body.label, body.kind)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception:  # noqa: BLE001 — §G: nunca exponer el error técnico al abogado
        logger.exception("add_folder falló (tenant=%s)", tid)
        raise HTTPException(
            status_code=502,
            detail="No pude registrar la carpeta en este momento. Intenta de nuevo en unos minutos.",
        )


@router.delete("/{source_id}")
async def remove_folder(source_id: str, request: Request):
    """Deshabilita una fuente y borra su conocimiento indexado (privacidad primero).
    Ajena o inexistente → 404 (nunca datos de otro despacho)."""
    tid = _tenant(request)
    try:
        ok = await disable_source(tid, source_id)
    except Exception:  # uuid inválido u otro fallo → mismo 404, sin filtrar detalles
        ok = False
    if not ok:
        raise HTTPException(status_code=404, detail="No encontré esa carpeta.")
    return {"status": "disabled"}


@router.post("/sync")
async def sync_folders(request: Request, background_tasks: BackgroundTasks):
    """Dispara la sincronización de TODAS las carpetas registradas del tenant en segundo
    plano (no bloquea la respuesta; el resultado queda en knowledge_chunks)."""
    tid = _tenant(request)
    background_tasks.add_task(LocalFolderSync().sync_tenant, tid)
    return {
        "status": "started",
        "message": "Estoy revisando tus carpetas. El conocimiento nuevo estará disponible en unos minutos.",
    }
