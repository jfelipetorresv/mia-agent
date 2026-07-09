"""Mia · api.routes.matter_folders — EXPEDIENTE VINCULADO (Pilar C · carpeta del asunto).

Superficie HTTP para vincular UNA carpeta del disco/nube a un expediente: sus documentos
(PDF/Word/txt/md) se traen solos al asunto, con detección incremental por huella. Se apoya
en el mismo conector de la allowlist (connectors/local_folders), pero con kind='matters':
la ingesta va a documents + chunks del expediente (origin='folder'), no al conocimiento del
despacho.

  POST   /api/matters/{id}/folder        → vincular la carpeta (una por expediente) + sync inicial
  GET    /api/matters/{id}/folder        → estado {linked, path, last_sync, files_indexed, pending_retry}
  POST   /api/matters/{id}/folder/sync   → sincronizar ahora (con throttle de 60s)
  DELETE /api/matters/{id}/folder        → desvincular (los documentos ya traídos SE CONSERVAN)

Todos con assert_owns_matter (pertenencia del asunto) y RLS. §G: mensajes en lenguaje llano,
sin jerga técnica ("expediente", "carpeta vinculada", nunca "tenant"/"sync"/"chunks").
"""
from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timezone

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field

from ...connectors.local_folders import (
    LocalFolderSync,
    disable_source,
    get_matter_source,
    register_source,
    source_last_sync,
)
from ...db import pool
from ._common import assert_owns_matter

router = APIRouter(prefix="/api", tags=["matter_folders"])
logger = logging.getLogger("mia.api.matter_folders")

# Throttle del re-sync manual: si ya hubo sincronización hace menos de esto, no se relanza.
SYNC_THROTTLE_SECONDS = 60

# Referencias vivas a las sincronizaciones en segundo plano (sin esto asyncio puede
# recolectarlas a mitad de camino — mismo patrón que hitl._BACKGROUND_TASKS). Se
# auto-limpian al terminar. `_PENDING_RETRY` recuerda cuántos archivos quedaron
# pendientes (bloqueados, p. ej. abiertos en Word) en la última corrida de cada fuente,
# para poder mostrarlo en el estado del expediente (best-effort en memoria del proceso).
_BACKGROUND_TASKS: set[asyncio.Task] = set()
_PENDING_RETRY: dict[str, int] = {}
# Candado por fuente: dos sincronizaciones simultáneas de la MISMA carpeta duplicarían
# el expediente (documents no tiene UNIQUE por ruta — el borra-y-reinserta de cada sync
# asume que corre solo). Se marca SINCRÓNICAMENTE antes de crear la tarea (sin ventana
# de carrera en el event loop) y se libera en el finally de la corrida.
_SYNCS_IN_FLIGHT: set[str] = set()


def _tenant(request: Request) -> str:
    tid = getattr(request.state, "tenant_id", None)
    if not tid:
        raise HTTPException(status_code=401, detail="Sin sesión activa")
    return tid


async def _run_sync(tenant_id: str, source: dict) -> None:
    """Sincroniza UNA carpeta vinculada en segundo plano y recuerda sus pendientes."""
    try:
        stats = await LocalFolderSync().sync_source(tenant_id, source)
        _PENDING_RETRY[str(source["id"])] = int(stats.get("pending", 0))
    except Exception:  # noqa: BLE001 — un fallo de fondo no debe propagarse a ningún request
        logger.exception("sync de expediente vinculado falló (fuente=%s)", source.get("id"))
    finally:
        _SYNCS_IN_FLIGHT.discard(str(source["id"]))


def _spawn_sync(tenant_id: str, source: dict) -> bool:
    """Lanza la sincronización de una fuente SI no hay otra en vuelo. Devuelve False si
    ya había una corriendo (el caller responde 'ya estoy revisando'). El marcado es
    sincrónico: no hay await entre la comprobación y el add."""
    sid = str(source["id"])
    if sid in _SYNCS_IN_FLIGHT:
        return False
    _SYNCS_IN_FLIGHT.add(sid)
    task = asyncio.create_task(_run_sync(tenant_id, source))
    _BACKGROUND_TASKS.add(task)
    task.add_done_callback(_BACKGROUND_TASKS.discard)
    return True


class LinkFolderBody(BaseModel):
    path: str = Field(min_length=1, max_length=4096)


@router.post("/matters/{matter_id}/folder")
async def link_folder(matter_id: str, body: LinkFolderBody, request: Request):
    """Vincula una carpeta al expediente (UNA por expediente) y dispara una revisión inicial
    en segundo plano. Si ya hay una carpeta vinculada activa, responde 409 en lenguaje llano."""
    tid = _tenant(request)
    await assert_owns_matter(tid, matter_id)
    if await get_matter_source(tid, matter_id) is not None:
        raise HTTPException(
            status_code=409,
            detail=("Este expediente ya tiene una carpeta vinculada. "
                    "Desvincúlala primero si quieres conectar otra."),
        )
    try:
        source = await register_source(tid, body.path, kind="matters", matter_id=matter_id)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception:  # noqa: BLE001 — §G: nunca exponer el error técnico al abogado
        logger.exception("link_folder falló (tenant=%s, matter=%s)", tid, matter_id)
        raise HTTPException(
            status_code=502,
            detail="No pude vincular la carpeta en este momento. Intenta de nuevo en unos minutos.",
        )
    _spawn_sync(tid, source)
    return {
        "status": "linked",
        "path": source["path"],
        "message": ("Vinculé la carpeta al expediente. Estoy revisando sus documentos; "
                    "estarán disponibles en unos minutos."),
    }


@router.get("/matters/{matter_id}/folder")
async def folder_status(matter_id: str, request: Request):
    """Estado de la carpeta vinculada del expediente (para la pantalla del asunto)."""
    tid = _tenant(request)
    await assert_owns_matter(tid, matter_id)
    source = await get_matter_source(tid, matter_id)
    if source is None:
        return {"linked": False, "path": None, "last_sync": None,
                "files_indexed": 0, "pending_retry": 0}
    last_sync = await source_last_sync(tid, source["id"])
    async with pool.tenant_connection(tid) as conn:
        files_indexed = (await (await conn.execute(
            "SELECT count(*) FROM documents WHERE matter_id=%s::uuid AND origin='folder'",
            (matter_id,))).fetchone())[0]
    return {
        "linked": True,
        "path": source["path"],
        "last_sync": last_sync.isoformat() if last_sync else None,
        "files_indexed": files_indexed,
        "pending_retry": _PENDING_RETRY.get(str(source["id"]), 0),
    }


@router.post("/matters/{matter_id}/folder/sync")
async def folder_sync(matter_id: str, request: Request):
    """Sincroniza ahora la carpeta del expediente (en segundo plano). Con throttle: si ya se
    revisó hace menos de 60s, responde 'ya está al día' sin volver a lanzarla."""
    tid = _tenant(request)
    await assert_owns_matter(tid, matter_id)
    source = await get_matter_source(tid, matter_id)
    if source is None:
        raise HTTPException(status_code=404,
                            detail="Este expediente no tiene una carpeta vinculada.")
    last_sync = await source_last_sync(tid, source["id"])
    if last_sync is not None:
        elapsed = (datetime.now(timezone.utc) - last_sync).total_seconds()
        if elapsed < SYNC_THROTTLE_SECONDS:
            return {"status": "up_to_date",
                    "message": "Tu expediente ya está al día; lo revisé hace un momento."}
    if not _spawn_sync(tid, source):
        return {"status": "in_progress",
                "message": "Ya estoy revisando esa carpeta; dame un momento."}
    return {"status": "started",
            "message": ("Estoy revisando la carpeta del expediente. Los documentos nuevos "
                        "estarán disponibles en unos minutos.")}


@router.delete("/matters/{matter_id}/folder")
async def unlink_folder(matter_id: str, request: Request):
    """Desvincula la carpeta del expediente. Los documentos que ya trajo SE CONSERVAN."""
    tid = _tenant(request)
    await assert_owns_matter(tid, matter_id)
    source = await get_matter_source(tid, matter_id)
    if source is None:
        raise HTTPException(status_code=404,
                            detail="Este expediente no tiene una carpeta vinculada.")
    await disable_source(tid, source["id"])
    _PENDING_RETRY.pop(str(source["id"]), None)
    return {"status": "unlinked",
            "message": ("Desvinculé la carpeta. Los documentos que ya había traído siguen "
                        "en tu expediente.")}
