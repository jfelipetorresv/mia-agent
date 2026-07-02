"""Mia · api.routes.folders — CARPETAS DE TRABAJO del despacho (CP-C1, Pilar C · decisión #30).

Superficie HTTP de la allowlist de carpetas locales/nubes espejo (connectors/local_folders):
  GET    /api/folders/detected  → nubes detectadas (OneDrive/Google Drive) + fuentes registradas
  POST   /api/folders           → registrar una carpeta (validación de seguridad fail-closed)
  DELETE /api/folders/{id}      → deshabilitar una fuente (borra su conocimiento indexado)
  POST   /api/folders/sync      → dispara la sincronización del tenant en segundo plano

CP-C2 (Pilar C · decisión #32) añade la superficie de Obsidian (`obsidian_router`):
  GET    /api/obsidian/status     → ¿Obsidian instalado? ¿vault configurado? ruta
  POST   /api/obsidian/install    → instalación guiada vía winget (sin shell; exige
                                    body {"confirmar": true} — deshabilitar en Modo A)
  POST   /api/obsidian/bootstrap  → crea la estructura Mia/ del vault y lo registra

Auth: el middleware JWT fija `request.state.tenant_id` (RLS). §G: errores sin jerga técnica.
Privacidad primero: Mia NUNCA escanea nada fuera de las carpetas registradas.
"""
from __future__ import annotations

import asyncio
import logging

from fastapi import APIRouter, BackgroundTasks, HTTPException, Request
from pydantic import BaseModel, Field

from ...connectors import obsidian_install
from ...connectors import vault_writer as vault_writer_mod
from ...connectors.local_folders import (
    LocalFolderSync,
    detect_cloud_folders,
    disable_source,
    list_sources,
    register_source,
)
from ...connectors.vault_writer import VaultWriter

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


# ═══ Obsidian (CP-C2 · decisión #32): estado, instalación guiada y bootstrap ═══
# La memoria visible de Mia vive en el vault del despacho, SOLO bajo `{vault}/Mia/`
# (la wiki interna sigue siendo la fuente de verdad; el vault es el espejo). Este
# router se monta como /api/obsidian/* en api/main.py.

obsidian_router = APIRouter(prefix="/obsidian", tags=["obsidian"])


class VaultBootstrapBody(BaseModel):
    vault_path: str = Field(min_length=1, max_length=4096)


class InstallBody(BaseModel):
    """Confirmación explícita para instalar software (revisión CP-C2)."""
    confirmar: bool = False


@obsidian_router.get("/status")
async def obsidian_status(request: Request):
    """¿Obsidian está instalado en este equipo? ¿El despacho ya tiene su vault configurado?"""
    tid = _tenant(request)
    installed = await asyncio.to_thread(obsidian_install.is_installed)
    vault_path = None
    try:
        vault_path = await vault_writer_mod.get_tenant_vault_path(tid)
    except Exception:  # noqa: BLE001 — el status nunca falla por la DB; reporta "sin vault"
        logger.exception("obsidian_status: no pude leer el vault configurado (tenant=%s)", tid)
    return {
        "installed": installed,
        "vault_configured": bool(vault_path),
        "vault_path": vault_path,
        "message": (
            "Obsidian está instalado y tu espacio de notas ya está conectado con Mia."
            if installed and vault_path
            else "Obsidian está instalado; falta conectar tu espacio de notas con Mia."
            if installed
            else "Obsidian no está instalado en este equipo. Puedo instalarlo por ti."
        ),
    }


@obsidian_router.post("/install")
async def obsidian_install_app(request: Request, body: InstallBody | None = None):
    """Instala Obsidian en este equipo (instalación guiada vía winget, sin pasos manuales).

    Requiere CONFIRMACIÓN EXPLÍCITA en el body: `{"confirmar": true}`. Sin ella
    responde 400 y NO instala nada (revisión CP-C2: instalar software nunca puede
    dispararse por un clic accidental o un llamado automatizado).

    NOTA DE DESPLIEGUE: en despliegue compartido (Modo A, Docker multi-despacho) este
    endpoint debe DESHABILITARSE — instala software en el host que atiende a varios
    despachos (ver Riesgo #10/#15 de sandbox en memory/bugs-and-risks.md)."""
    _tenant(request)
    if body is None or not body.confirmar:
        raise HTTPException(
            status_code=400,
            detail=(
                "Para continuar necesito tu confirmación: esta acción descarga e "
                "instala el programa Obsidian en este equipo. Vuelve a intentarlo "
                "confirmando la instalación."
            ),
        )
    ok, message = await asyncio.to_thread(obsidian_install.install)
    return {"installed": ok, "message": message}


@obsidian_router.post("/bootstrap")
async def obsidian_bootstrap(body: VaultBootstrapBody, request: Request):
    """Prepara el vault del despacho: valida la ruta (allowlist), crea la carpeta Mia/
    (conceptos, reportes, README) y la registra como el vault del tenant — el mismo
    registro que usa el sync de lectura (tenant_settings.config.obsidian_vault_path)."""
    tid = _tenant(request)
    try:
        writer = VaultWriter(body.vault_path)
        created = await asyncio.to_thread(writer.bootstrap_vault)
    except vault_writer_mod.VaultConfigError as e:
        # Revisión CP-C2 (§G): el detalle técnico (variables .env) va SOLO al log;
        # el abogado recibe la explicación en lenguaje llano.
        logger.error("obsidian_bootstrap: vault sin configurar (tenant=%s): %s", tid, e)
        raise HTTPException(
            status_code=400,
            detail=(
                "Falta configurar la ubicación del archivo de notas. "
                "Pídele a tu administrador que la configure."
            ),
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception:  # noqa: BLE001 — §G: nunca exponer el error técnico al abogado
        logger.exception("obsidian_bootstrap falló (tenant=%s)", tid)
        raise HTTPException(
            status_code=502,
            detail="No pude preparar tu espacio de notas en este momento. Intenta de nuevo en unos minutos.",
        )
    await vault_writer_mod.register_tenant_vault(tid, str(writer.vault))
    return {
        "status": "ok",
        "vault_path": str(writer.vault),
        "created": created,
        "message": (
            "Tu espacio de notas quedó listo. Mia guardará ahí lo que aprende, "
            "dentro de la carpeta 'Mia', sin tocar tus demás notas."
        ),
    }
