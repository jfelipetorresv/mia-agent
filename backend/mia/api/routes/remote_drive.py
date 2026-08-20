"""Mia · api.routes.remote_drive — carpetas en la nube SELECTIVAS (Fase 3 · fuentes remotas).

El abogado NAVEGA su nube (para quien NO usa el cliente de escritorio), ELIGE subcarpetas
concretas y Mia las sincroniza de forma incremental hacia el conocimiento del despacho
(kind='knowledge') o hacia un expediente (kind='matters'). SOLO LECTURA.

DOS PROVEEDORES, UNA SOLA FORMA DE API (decisión de Pipe 2026-08-19: Google Drive entra al
nivel de OneDrive): `?provider=microsoft` (default, OneDrive) o `?provider=google` (Google
Drive). El resto del contrato no cambia — un cliente que nunca mande `provider` sigue
hablando de OneDrive exactamente como antes.

  GET    /api/drive/browse?item_id=...&provider=...  → navegar una carpeta (item_id opcional = raíz)
  GET    /api/drive/sources              → carpetas remotas registradas
  POST   /api/drive/sources             → registrar una carpeta elegida
  DELETE /api/drive/sources/{id}        → quitar una carpeta ('knowledge' borra su
                                          conocimiento; 'matters' conserva sus documentos)
  POST   /api/drive/sources/{id}/sync   → sincronizar ahora (throttle 60s + lock anti-duplicado)

§G: el abogado ve "OneDrive", "carpetas", "documentos" — nunca "Graph", "OAuth", "tenant",
"eTag". Sin conexión Microsoft o sin permiso de archivos → 503 en llano; errores de Graph
→ 502 en llano. Los nombres técnicos de los CAMPOS del JSON (item_id, kind) están bien.
"""
from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timezone

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field

from ...connectors.google_drive import GoogleDriveError, GoogleDriveService
from ...connectors.graph_drive import (
    DRIVE_PROVIDERS,
    SYNCS_IN_FLIGHT,
    DuplicateSourceError,
    GraphDriveError,
    GraphDriveService,
    MatterNotFoundError,
    RemoteDriveSync,
    SourceLimitError,
    delete_source,
    get_source,
    list_sources,
    register_source,
    source_last_sync,
)
from ._common import _is_uuid

router = APIRouter(prefix="/api/drive", tags=["remote_drive"])
logger = logging.getLogger("mia.api.remote_drive")

# Throttle del re-sync manual: si ya hubo sincronización hace menos de esto, no se relanza.
SYNC_THROTTLE_SECONDS = 60

# Referencias vivas a las sincronizaciones en segundo plano + candado por fuente (dos syncs
# simultáneas de la MISMA carpeta duplicarían el expediente). Mismo patrón que matter_folders.
_BACKGROUND_TASKS: set[asyncio.Task] = set()
# El candado en sí vive en connectors/graph_drive.py (SYNCS_IN_FLIGHT): así el cron programado
# (cron/scheduler.py::sync_remote_drive_all_tenants) lo comparte sin importar este módulo de
# rutas. Este alias preserva el nombre/comportamiento usado en el resto del archivo y en tests.
_SYNCS_IN_FLIGHT = SYNCS_IN_FLIGHT

_NO_ACCOUNT = {
    "microsoft": ("Conecta tu cuenta de Microsoft con permiso de archivos desde el "
                  "menú Configuración."),
    "google": ("Conecta tu cuenta de Google con permiso de archivos desde el "
               "menú Configuración."),
}
_DRIVE_DOWN = {
    "microsoft": "No pude leer tu OneDrive en este momento. Intenta de nuevo en unos minutos.",
    "google": ("No pude leer tu Google Drive en este momento. Intenta de nuevo en unos "
               "minutos."),
}
# Errores de API de cada proveedor: la ruta los trata igual (502 en llano).
_API_ERRORS = (GraphDriveError, GoogleDriveError)


def _make_drive_service() -> GraphDriveService:
    """Fabrica el servicio de OneDrive (tokens + refresco + conector). Seam de inyección:
    los gates lo reemplazan por un doble sin red ni cuentas reales."""
    return GraphDriveService()


def _make_google_drive_service() -> GoogleDriveService:
    """Gemelo del anterior para Google Drive. Seam propio para poder doblar UN proveedor sin
    tocar el otro en los gates."""
    return GoogleDriveService()


def _service_for(provider: str):
    """Servicio del proveedor de la carpeta. Cada uno pasa por SU seam (`_make_*`), así un
    gate puede doblar solo OneDrive o solo Google Drive."""
    if provider == "google":
        return _make_google_drive_service()
    return _make_drive_service()


def _check_provider(provider: str) -> str:
    """Valida el proveedor pedido (404 en llano si no es uno de los dos soportados)."""
    if provider not in DRIVE_PROVIDERS:
        raise HTTPException(status_code=404, detail="No reconozco ese servicio de archivos "
                                                    "en la nube.")
    return provider


def _tenant(request: Request) -> str:
    tid = getattr(request.state, "tenant_id", None)
    if not tid:
        raise HTTPException(status_code=401, detail="Sin sesión activa")
    return tid


async def _run_sync(tenant_id: str, source: dict) -> None:
    """Resuelve el conector DEL PROVEEDOR de la fuente y la sincroniza en segundo plano."""
    provider = str(source.get("provider") or "microsoft")
    svc = _service_for(provider)
    try:
        conn = await svc.connector_for(tenant_id)
        if conn is None:
            logger.warning("sync de carpeta en la nube (%s): sin cuenta conectada (fuente=%s)",
                           provider, source.get("id"))
            return
        await RemoteDriveSync(conn).sync_source(tenant_id, source)
    except Exception:  # noqa: BLE001 — un fallo de fondo no debe propagarse a ningún request
        logger.exception("sync de carpeta en la nube falló (fuente=%s)", source.get("id"))
    finally:
        await svc.aclose()
        _SYNCS_IN_FLIGHT.discard(str(source["id"]))


def _spawn_sync(tenant_id: str, source: dict) -> bool:
    """Lanza la sincronización de una fuente SI no hay otra en vuelo. False si ya corría.
    El marcado es sincrónico: sin ventana de carrera en el event loop."""
    sid = str(source["id"])
    if sid in _SYNCS_IN_FLIGHT:
        return False
    _SYNCS_IN_FLIGHT.add(sid)
    task = asyncio.create_task(_run_sync(tenant_id, source))
    _BACKGROUND_TASKS.add(task)
    task.add_done_callback(_BACKGROUND_TASKS.discard)
    return True


class SourceBody(BaseModel):
    remote_item_id: str = Field(min_length=1, max_length=2048)
    label: str | None = Field(default=None, max_length=200)
    kind: str = Field(default="knowledge", max_length=20)
    matter_id: str | None = Field(default=None, max_length=64)
    # "microsoft" (OneDrive) o "google" (Google Drive). Default microsoft: preserva el
    # contrato de los clientes que ya llamaban a esta ruta sin el campo.
    provider: str = Field(default="microsoft", max_length=16)


# ── navegar ───────────────────────────────────────────────────────────────────
@router.get("/browse")
async def browse(request: Request, item_id: str | None = None,
                 provider: str = "microsoft"):
    """Carpetas y archivos de UN nivel de la nube del abogado (item_id opcional = raíz).
    `provider` elige OneDrive (default) o Google Drive. Sin cuenta conectada o sin permiso
    de archivos → 503; error de la API del proveedor → 502 (ambos en llano)."""
    tid = _tenant(request)
    _check_provider(provider)
    svc = _service_for(provider)
    try:
        conn = await svc.connector_for(tid)
        if conn is None:
            raise HTTPException(status_code=503, detail=_NO_ACCOUNT[provider])
        try:
            items = await conn.list_children(item_id or None)
        except _API_ERRORS:
            raise HTTPException(status_code=502, detail=_DRIVE_DOWN[provider])
        return {"items": items}
    finally:
        await svc.aclose()


# ── fuentes registradas ─────────────────────────────────────────────────────────
@router.get("/sources")
async def get_sources(request: Request):
    """Carpetas de OneDrive registradas del despacho (con su última sincronización)."""
    tid = _tenant(request)
    return {"sources": await list_sources(tid)}


@router.post("/sources")
async def add_source(body: SourceBody, request: Request):
    """Registra una carpeta de OneDrive elegida. kind='matters' exige un expediente del
    propio despacho. No dispara la sincronización inicial (usa POST /sources/{id}/sync)."""
    tid = _tenant(request)
    _check_provider(body.provider)
    # Un uuid de expediente mal formado se rechaza en llano (404) antes de tocar la DB, en vez
    # de reventar en un 500/502 genérico al castear a ::uuid (m5, consistente con delete/sync).
    if body.kind == "matters" and body.matter_id and not _is_uuid(body.matter_id):
        raise HTTPException(status_code=404, detail="No encontré ese expediente.")
    try:
        source = await register_source(tid, body.remote_item_id, body.label, body.kind,
                                       body.matter_id, provider=body.provider)
    except MatterNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except DuplicateSourceError as e:
        raise HTTPException(status_code=409, detail=str(e))
    except SourceLimitError as e:
        raise HTTPException(status_code=422, detail=str(e))
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception:  # noqa: BLE001 — §G: nunca exponer el error técnico al abogado
        logger.exception("add_source (carpeta en la nube) falló (tenant=%s)", tid)
        raise HTTPException(
            status_code=502,
            detail="No pude agregar la carpeta en este momento. Intenta de nuevo en unos minutos.")
    return source


@router.delete("/sources/{source_id}")
async def remove_source(source_id: str, request: Request):
    """Quita una carpeta remota. 'knowledge' borra su conocimiento indexado; 'matters'
    conserva los documentos ya traídos al expediente. Ajena/inexistente → 404."""
    tid = _tenant(request)
    try:
        ok = await delete_source(tid, source_id)
    except Exception:  # noqa: BLE001 — uuid inválido u otro fallo → mismo 404, sin filtrar
        ok = False
    if not ok:
        raise HTTPException(status_code=404, detail="No encontré esa carpeta.")
    return {"status": "removed"}


@router.post("/sources/{source_id}/sync")
async def sync_source(source_id: str, request: Request):
    """Sincroniza ahora la carpeta remota (en segundo plano). Throttle: si se revisó hace
    menos de 60s → 'ya está al día'. Lock: si ya hay una corrida en vuelo → 'ya estoy revisando'."""
    tid = _tenant(request)
    # uuid mal formado → 404 en llano antes de castear a ::uuid (m5, evita el 500 técnico).
    if not _is_uuid(source_id):
        raise HTTPException(status_code=404, detail="No encontré esa carpeta.")
    source = await get_source(tid, source_id)
    if source is None:
        raise HTTPException(status_code=404, detail="No encontré esa carpeta.")
    last = await source_last_sync(tid, source_id)
    if last is not None:
        elapsed = (datetime.now(timezone.utc) - last).total_seconds()
        if elapsed < SYNC_THROTTLE_SECONDS:
            return {"status": "up_to_date",
                    "message": "Esa carpeta ya está al día; la revisé hace un momento."}
    if not _spawn_sync(tid, source):
        return {"status": "in_progress",
                "message": "Ya estoy revisando esa carpeta; dame un momento."}
    nombre = DRIVE_PROVIDERS.get(str(source.get("provider") or "microsoft"), "la nube")
    return {"status": "started",
            "message": (f"Estoy revisando la carpeta de {nombre}. Los documentos nuevos "
                        f"estarán disponibles en unos minutos.")}
