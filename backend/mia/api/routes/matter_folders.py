"""Mia · api.routes.matter_folders — EXPEDIENTE VINCULADO (Pilar C · carpeta del asunto).

Superficie HTTP para vincular carpetas del disco/nube a un expediente. Sus documentos
(PDF/Word/txt/md) quedan disponibles para lectura directa en cada conversación. La
importación incremental por huella sigue existiendo como ayuda opcional para búsquedas
ampliadas, separada del vínculo. Se apoya en el mismo conector de la allowlist
(connectors/local_folders), con kind='matters'.

SUPERFICIE PLURAL (Bloque A · evolución de producto — un expediente admite VARIAS carpetas,
hasta MAX_FOLDERS_PER_MATTER; cada una se sincroniza y poda de forma independiente por su
propio `source_id`, corrigiendo el bug de poda cruzada — ver memory/bugs-and-risks.md):

  GET    /api/matters/{id}/folders                → lista de carpetas vinculadas
  POST   /api/matters/{id}/folders                → vincular una carpeta MÁS (lectura directa)
  POST   /api/matters/{id}/folders/{source_id}/sync → sincronizar una carpeta ahora (throttle 60s)
  DELETE /api/matters/{id}/folders/{source_id}     → desvincular esa carpeta (documentos SE CONSERVAN)

SUPERFICIE SINGULAR (DEPRECADA, se conserva por compatibilidad — el frontend actual solo
conoce estos 4 endpoints; migrar a la plural en la próxima ola):

  POST   /api/matters/{id}/folder        → delega en la plural (YA NO hay 409 de "una sola
                                            carpeta"; un expediente admite varias)
  GET    /api/matters/{id}/folder        → resume la carpeta MÁS RECIENTE vinculada
  POST   /api/matters/{id}/folder/sync   → sincroniza TODAS las carpetas del expediente
  DELETE /api/matters/{id}/folder        → desvincula la carpeta MÁS RECIENTE

Todos con assert_owns_matter (pertenencia del asunto) y RLS. §G: mensajes en lenguaje llano,
sin jerga técnica ("expediente", "carpeta vinculada", nunca "tenant"/"sync"/"chunks").
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field

from ...connectors.local_folders import (
    disable_source,
    get_matter_source,
    get_matter_sources,
    register_source,
    source_last_sync,
)
from ...db import pool
from ...jobs import enqueue_job, latest_job
from ._common import assert_owns_matter

router = APIRouter(prefix="/api", tags=["matter_folders"])
logger = logging.getLogger("mia.api.matter_folders")

# Throttle del re-sync manual: si ya hubo sincronización hace menos de esto, no se relanza.
SYNC_THROTTLE_SECONDS = 60

# Tope defensivo: cuántas carpetas puede acumular un mismo expediente (evita que un
# despacho vincule decenas de carpetas por error y sature el escaneo/ingesta).
MAX_FOLDERS_PER_MATTER = 10

# Las revisiones se encolan en PostgreSQL: sobreviven cierres y el índice único
# parcial evita duplicar la misma fuente mientras está pendiente o en curso.


def _tenant(request: Request) -> str:
    tid = getattr(request.state, "tenant_id", None)
    if not tid:
        raise HTTPException(status_code=401, detail="Sin sesión activa")
    return tid


async def _run_sync(tenant_id: str, source: dict) -> bool:
    """Guarda una revisión durable y devuelve si creó una fila nueva."""
    sid = str(source["id"])
    _job_id, created = await enqueue_job(
        tenant_id,
        "matter_folder_sync",
        {"source_id": sid, "matter_id": str(source["matter_id"])},
        f"matter-folder:{sid}",
    )
    return created


async def _spawn_sync(tenant_id: str, source: dict) -> bool:
    """False significa que la misma fuente ya estaba en cola o en curso."""
    return await _run_sync(tenant_id, source)


async def _pending_retry(tenant_id: str, source_id: str) -> int:
    job = await latest_job(
        tenant_id, "matter_folder_sync", f"matter-folder:{source_id}"
    )
    return int(((job or {}).get("result") or {}).get("pending", 0))


async def _get_source_for_matter(tid: str, matter_id: str, source_id: str) -> dict | None:
    """Una carpeta vinculada de la lista plural que pertenezca a ESTE expediente, o None
    (ajena o inexistente → el caller responde 404 en llano, nunca un 500 técnico)."""
    for s in await get_matter_sources(tid, matter_id):
        if s["id"] == source_id:
            return s
    return None


class LinkFolderBody(BaseModel):
    path: str = Field(min_length=1, max_length=4096)
    label: str | None = Field(default=None, max_length=200)


# ═══ Superficie plural (Bloque A · varias carpetas por expediente) ═══

@router.get("/matters/{matter_id}/folders")
async def list_matter_folders(matter_id: str, request: Request):
    """Todas las carpetas vinculadas al expediente, con su estado individual."""
    tid = _tenant(request)
    await assert_owns_matter(tid, matter_id)
    out = []
    for source in await get_matter_sources(tid, matter_id):
        last_sync = await source_last_sync(tid, source["id"])
        async with pool.tenant_connection(tid) as conn:
            files_indexed = (await (await conn.execute(
                "SELECT count(*) FROM documents WHERE matter_id=%s::uuid AND origin='folder' "
                "AND source_id=%s::uuid",
                (matter_id, source["id"]))).fetchone())[0]
        out.append({
            "id": source["id"],
            "path": source["path"],
            "label": source["label"],
            "last_sync": last_sync.isoformat() if last_sync else None,
            "files_indexed": files_indexed,
            "pending_retry": await _pending_retry(tid, source["id"]),
        })
    return {"folders": out}


@router.post("/matters/{matter_id}/folders")
async def link_matter_folder(matter_id: str, body: LinkFolderBody, request: Request):
    """Vincula una carpeta MÁS al expediente (tope defensivo de MAX_FOLDERS_PER_MATTER) y
    la deja disponible para lectura directa en el chat. Importarla al índice queda como
    acción separada y opcional en el panel de fuentes."""
    tid = _tenant(request)
    await assert_owns_matter(tid, matter_id)
    existing = await get_matter_sources(tid, matter_id)
    if len(existing) >= MAX_FOLDERS_PER_MATTER:
        raise HTTPException(
            status_code=422,
            detail=(f"Este expediente ya tiene {MAX_FOLDERS_PER_MATTER} carpetas "
                    "vinculadas, el máximo permitido. Desvincula alguna si quieres "
                    "conectar otra."),
        )
    try:
        source = await register_source(tid, body.path, body.label, kind="matters",
                                       matter_id=matter_id)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception:  # noqa: BLE001 — §G: nunca exponer el error técnico al abogado
        logger.exception("link_matter_folder falló (tenant=%s, matter=%s)", tid, matter_id)
        raise HTTPException(
            status_code=502,
            detail="No pude vincular la carpeta en este momento. Intenta de nuevo en unos minutos.",
        )
    return {
        "status": "linked",
        "id": source["id"],
        "path": source["path"],
        "message": ("Vinculé la carpeta. Mia leerá automáticamente sus documentos "
                    "originales cuando converses sobre este caso."),
    }


@router.post("/matters/{matter_id}/folders/{source_id}/sync")
async def sync_matter_folder(matter_id: str, source_id: str, request: Request):
    """Sincroniza ahora UNA carpeta del expediente (en segundo plano), con throttle: si ya
    se revisó hace menos de 60s, responde 'ya está al día' sin volver a lanzarla."""
    tid = _tenant(request)
    await assert_owns_matter(tid, matter_id)
    source = await _get_source_for_matter(tid, matter_id, source_id)
    if source is None:
        raise HTTPException(status_code=404, detail="No encontré esa carpeta en este expediente.")
    last_sync = await source_last_sync(tid, source["id"])
    if last_sync is not None:
        elapsed = (datetime.now(timezone.utc) - last_sync).total_seconds()
        if elapsed < SYNC_THROTTLE_SECONDS:
            return {"status": "up_to_date",
                    "message": "Esa carpeta ya está al día; la revisé hace un momento."}
    if not await _spawn_sync(tid, source):
        return {"status": "in_progress",
                "message": "Ya estoy revisando esa carpeta; dame un momento."}
    return {"status": "started",
            "message": ("Estoy importando una copia de los documentos para ampliar la "
                        "búsqueda. Puedes seguir conversando mientras tanto.")}


@router.delete("/matters/{matter_id}/folders/{source_id}")
async def unlink_matter_folder(matter_id: str, source_id: str, request: Request):
    """Desvincula UNA carpeta del expediente. Los documentos que ya trajo SE CONSERVAN."""
    tid = _tenant(request)
    await assert_owns_matter(tid, matter_id)
    source = await _get_source_for_matter(tid, matter_id, source_id)
    if source is None:
        raise HTTPException(status_code=404, detail="No encontré esa carpeta en este expediente.")
    await disable_source(tid, source_id)
    return {"status": "unlinked",
            "message": ("Desvinculé la carpeta. Los documentos que ya había traído siguen "
                        "en tu expediente.")}


# ═══ Superficie singular (DEPRECADA — compatibilidad con el frontend actual) ═══
# El frontend de esta ola todavía solo conoce estos 4 endpoints; se conservan como alias
# de compatibilidad sobre la superficie plural hasta que migre (próxima ola). YA NO aplica
# la regla histórica "una carpeta por expediente": ahora un expediente admite varias.

@router.post("/matters/{matter_id}/folder")
async def link_folder(matter_id: str, body: LinkFolderBody, request: Request):
    """DEPRECADO — usar POST /matters/{id}/folders (plural). Delega ahí: ya NO responde
    409 al vincular una segunda carpeta (un expediente admite varias)."""
    return await link_matter_folder(matter_id, body, request)


@router.get("/matters/{matter_id}/folder")
async def folder_status(matter_id: str, request: Request):
    """DEPRECADO — usar GET /matters/{id}/folders (plural). Resume la carpeta MÁS
    RECIENTE vinculada (comportamiento histórico de este endpoint singular)."""
    tid = _tenant(request)
    await assert_owns_matter(tid, matter_id)
    source = await get_matter_source(tid, matter_id)
    if source is None:
        return {"linked": False, "path": None, "last_sync": None,
                "files_indexed": 0, "pending_retry": 0}
    last_sync = await source_last_sync(tid, source["id"])
    async with pool.tenant_connection(tid) as conn:
        files_indexed = (await (await conn.execute(
            "SELECT count(*) FROM documents WHERE matter_id=%s::uuid AND origin='folder' "
            "AND source_id=%s::uuid",
            (matter_id, source["id"]))).fetchone())[0]
    return {
        "linked": True,
        "path": source["path"],
        "last_sync": last_sync.isoformat() if last_sync else None,
        "files_indexed": files_indexed,
        "pending_retry": await _pending_retry(tid, str(source["id"])),
    }


@router.post("/matters/{matter_id}/folder/sync")
async def folder_sync(matter_id: str, request: Request):
    """DEPRECADO — usar POST /matters/{id}/folders/{source_id}/sync (plural). Sincroniza
    TODAS las carpetas vinculadas del expediente (antes solo podía haber una)."""
    tid = _tenant(request)
    await assert_owns_matter(tid, matter_id)
    sources = await get_matter_sources(tid, matter_id)
    if not sources:
        raise HTTPException(status_code=404,
                            detail="Este expediente no tiene una carpeta vinculada.")
    started = False
    all_up_to_date = True
    for source in sources:
        last_sync = await source_last_sync(tid, source["id"])
        if last_sync is not None:
            elapsed = (datetime.now(timezone.utc) - last_sync).total_seconds()
            if elapsed < SYNC_THROTTLE_SECONDS:
                continue
        all_up_to_date = False
        if await _spawn_sync(tid, source):
            started = True
    if started:
        return {"status": "started",
                "message": ("Estoy revisando las carpetas del expediente. Los documentos "
                            "nuevos estarán disponibles en unos minutos.")}
    if all_up_to_date:
        return {"status": "up_to_date",
                "message": "Tu expediente ya está al día; lo revisé hace un momento."}
    return {"status": "in_progress",
            "message": "Ya estoy revisando esas carpetas; dame un momento."}


@router.delete("/matters/{matter_id}/folder")
async def unlink_folder(matter_id: str, request: Request):
    """DEPRECADO — usar DELETE /matters/{id}/folders/{source_id} (plural). Desvincula la
    carpeta MÁS RECIENTE (comportamiento histórico). Los documentos que ya trajo SE
    CONSERVAN."""
    tid = _tenant(request)
    await assert_owns_matter(tid, matter_id)
    source = await get_matter_source(tid, matter_id)
    if source is None:
        raise HTTPException(status_code=404,
                            detail="Este expediente no tiene una carpeta vinculada.")
    await disable_source(tid, source["id"])
    return {"status": "unlinked",
            "message": ("Desvinculé la carpeta. Los documentos que ya había traído siguen "
                        "en tu expediente.")}
