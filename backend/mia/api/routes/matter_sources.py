"""Mia · api.routes.matter_sources — FUENTES UNIFICADAS DEL EXPEDIENTE (Bloque A · limpieza).

Vista única y en llano de TODO lo que alimenta a un expediente — carpetas del equipo
(disco/red), carpetas de OneDrive vinculadas y los correos traídos al asunto — sin que
el abogado tenga que visitar tres pantallas distintas para saber qué está leyendo Mia.

  GET /api/matters/{id}/sources → {"sources": [...]}

Contrato de cada item (§G, todo en español llano, sin jerga técnica):
  {"tipo": "carpeta" | "onedrive" | "correo",
   "id": str | None,          # id de la fuente; None solo para el item de correo
   "nombre": str,              # etiqueta o nombre legible
   "detalle": str,             # ruta local, nombre de la carpeta remota, o "" para correo
   "documentos": int,          # documentos que esa fuente trajo al expediente
   "last_sync": str | None,    # ISO de la última revisión, o None si nunca corrió
   "estado": str}              # frase en llano ("3 documentos leídos", "Leyendo la carpeta…"…)

El item de correo aparece SIEMPRE (uno solo, id=None). Las carpetas de OneDrive solo
aparecen si el despacho registró alguna fuente remota kind='matters' de este expediente.

Fail-soft (OneDrive): si el conector remoto falla por lo que sea (sin cuenta conectada,
tabla ausente, Graph caído) las fuentes de OneDrive simplemente no aparecen en la lista
— este endpoint NUNCA responde 500 por eso (§G).

Conteo por fuente (H11): `documents.source_id` ahora SÍ se llena para origin='drive'
(connectors/graph_drive.py, espejo del fix de poda cruzada de LocalFolderSync), así que el
conteo de documentos se reparte POR CARPETA remota exacta (source_id) en vez de atribuir
todo a la primera. Los documentos con `source_id IS NULL` (huérfanos de antes del backfill
de la migración 028, o de un expediente que tuvo varias carpetas en su historial y cuya
procedencia no se pudo determinar sin ambigüedad) NUNCA se le atribuyen a una carpeta
concreta si hoy hay más de una activa — mentirle al abogado sobre qué carpeta trajo qué
sería peor que un conteo incompleto. Con exactamente UNA carpeta activa esos huérfanos SÍ
se le suman (no hay a quién más atribuirlos).
"""
from __future__ import annotations

import logging
from pathlib import Path

from fastapi import APIRouter, HTTPException, Request

from ...connectors import local_folders
from ...connectors.graph_drive import list_sources as list_drive_sources
from ...db import pool
from ._common import assert_owns_matter
from .matter_folders import _SYNCS_IN_FLIGHT

router = APIRouter(prefix="/api", tags=["matter_sources"])
logger = logging.getLogger("mia.api.matter_sources")


def _tenant(request: Request) -> str:
    tid = getattr(request.state, "tenant_id", None)
    if not tid:
        raise HTTPException(status_code=401, detail="Sin sesión activa")
    return tid


def _folder_name(source: dict) -> str:
    """Etiqueta de la carpeta, o la última parte de su ruta si no tiene una."""
    if source.get("label"):
        return source["label"]
    return Path(source["path"]).name or source["path"]


def _folder_status(documentos: int, source_id: str) -> str:
    """Estado en llano de una carpeta LOCAL: revisión en vuelo > documentos leídos > vacía."""
    if source_id in _SYNCS_IN_FLIGHT:
        return "Leyendo la carpeta…"
    if documentos > 0:
        return f"{documentos} documentos leídos"
    return "Aún sin documentos"


def _drive_status(documentos: int, last_sync: str | None) -> str:
    """Estado en llano de una carpeta de OneDrive, basado en `last_synced_at` (única señal
    disponible por fuente individual — ver deuda de `documents.source_id` en el docstring)."""
    if documentos > 0:
        return f"{documentos} documentos leídos"
    if last_sync:
        return "Aún sin documentos"
    return "Todavía no la he revisado"


async def _folder_sources(tid: str, matter_id: str) -> list[dict]:
    """Carpetas del equipo (disco/red) vinculadas al expediente, con su conteo POR fuente
    (documents.source_id sí está poblado para origin='folder' desde la migración 028)."""
    out: list[dict] = []
    for source in await local_folders.get_matter_sources(tid, matter_id):
        last_sync = await local_folders.source_last_sync(tid, source["id"])
        async with pool.tenant_connection(tid) as conn:
            documentos = (await (await conn.execute(
                "SELECT count(*) FROM documents WHERE matter_id=%s::uuid AND origin='folder' "
                "AND source_id=%s::uuid",
                (matter_id, source["id"]))).fetchone())[0]
        out.append({
            "tipo": "carpeta",
            "id": source["id"],
            "nombre": _folder_name(source),
            "detalle": source["path"],
            "documentos": documentos,
            "last_sync": last_sync.isoformat() if last_sync else None,
            "estado": _folder_status(documentos, source["id"]),
        })
    return out


async def _onedrive_sources(tid: str, matter_id: str) -> list[dict]:
    """Carpetas de OneDrive vinculadas al expediente, en llano, con su conteo POR fuente
    exacta (documents.source_id sí está poblado para origin='drive' desde H11). Fail-soft:
    cualquier fallo del conector remoto deja la lista vacía en vez de tumbar el endpoint (§G)."""
    try:
        todas = await list_drive_sources(tid)
    except Exception:  # noqa: BLE001 — §G: nunca tumbar la vista de fuentes por esto
        logger.warning("matter_sources: no pude leer las carpetas de OneDrive (tenant=%s)", tid)
        return []
    propias = [s for s in todas
               if s.get("kind") == "matters" and s.get("matter_id") == matter_id]
    if not propias:
        return []

    async with pool.tenant_connection(tid) as conn:
        rows = await (await conn.execute(
            "SELECT source_id, count(*) FROM documents "
            "WHERE matter_id=%s::uuid AND origin='drive' GROUP BY source_id",
            (matter_id,))).fetchall()
    por_fuente = {str(r[0]): r[1] for r in rows if r[0] is not None}
    # Huérfanos sin fuente trazada (source_id NULL): si hoy hay UNA sola carpeta activa, son
    # inequívocamente suyos y se le suman; con varias, atribuírselos a una en concreto sería
    # adivinar — se dejan fuera del conteo por fuente (siguen existiendo, nunca se podan).
    huerfanos = sum(r[1] for r in rows if r[0] is None)

    out: list[dict] = []
    for source in propias:
        documentos = por_fuente.get(source["id"], 0)
        if len(propias) == 1:
            documentos += huerfanos
        nombre = source.get("label") or "Carpeta de OneDrive"
        last_sync = source.get("last_sync")
        out.append({
            "tipo": "onedrive",
            "id": source["id"],
            "nombre": nombre,
            "detalle": nombre,
            "documentos": documentos,
            "last_sync": last_sync,
            "estado": _drive_status(documentos, last_sync),
        })
    return out


async def _mail_source(tid: str, matter_id: str) -> dict:
    """El item de correo del expediente: SIEMPRE presente, uno solo (id=None)."""
    async with pool.tenant_connection(tid) as conn:
        documentos = (await (await conn.execute(
            "SELECT count(*) FROM documents WHERE matter_id=%s::uuid AND origin='mail'",
            (matter_id,))).fetchone())[0]
    return {
        "tipo": "correo",
        "id": None,
        "nombre": "Correos vinculados",
        "detalle": "",
        "documentos": documentos,
        "last_sync": None,
        "estado": (f"{documentos} documentos leídos" if documentos > 0
                   else "Sin correos vinculados todavía"),
    }


@router.get("/matters/{matter_id}/sources")
async def list_matter_sources(matter_id: str, request: Request):
    """Todas las fuentes del expediente (carpetas, OneDrive, correo) en una sola lista."""
    tid = _tenant(request)
    await assert_owns_matter(tid, matter_id)
    out: list[dict] = []
    out.extend(await _folder_sources(tid, matter_id))
    out.extend(await _onedrive_sources(tid, matter_id))
    out.append(await _mail_source(tid, matter_id))
    return {"sources": out}
