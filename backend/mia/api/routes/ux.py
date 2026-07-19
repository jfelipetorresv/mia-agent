"""Mia · api.routes.ux — superficie /api/* que consumen las 5 pantallas (Fase 3 · decisión #20).

Endpoints nuevos bajo prefijo `/api`, separados de las rutas legacy (`/matters`,
`/matters/{id}/stream`, `/matters/{id}/approve…`) que NO se tocan (gate 1d intacto). Auth: el
JWT middleware existente fija `request.state.tenant_id`; todas las consultas pasan por RLS.

§G (CLAUDE.md): las respuestas NO exponen jerga técnica al abogado — nombres de job, conectores
y modelos se traducen a etiquetas amigables; nunca pgvector/tenant_id/embedding/HITL/LangGraph.
"""
from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import time
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import quote

import psycopg
from fastapi import APIRouter, File, HTTPException, Query, Request, Response, UploadFile
from psycopg.types.json import Json
from psycopg.rows import dict_row
from pydantic import BaseModel, Field
from sse_starlette.sse import EventSourceResponse
from starlette.concurrency import run_in_threadpool

from ... import embeddings
from ...agent.prompt_builder import strip_diagnosis_closing
from ...agents.checkpointer import open_checkpointer
from ...agents.graph import build_matter_graph, MatterGraphBuilder
from ...agents.personas import persona_service
from ...agents.state import HITL_OUTCOME, initial_state, thread_id_for
from ...agents.warroom import WarRoomError, build_panel, propose_panel, run_warroom
from ...agents import retrieval
from ... import config
from ...connectors import ObsidianSync, PineconeConnector
from ...security import assert_no_stray_secret
from ...security.at_rest import encrypt_secret
from ...cron import build_scheduler
from ...db import pool
from ...ingest.extract import extract_text_async, extract_text_detailed_async
from ...ingest.ingest import chunk_text, chunk_text_with_folios
from ...jurisdiction.pack import GENERIC_CODE, list_packs, load_pack
from ...memory.gepa import GEPALoop
from ...memory.playbook_manager import Playbook, PlaybookManager
from ...memory.profile_manager import ProfileManager
from ...memory import soul_manager
from ...memory.trace_capture import TraceCapture
from ...memory.wiki_manager import WikiManager
from ...observability import audit
from ...onboarding.soul_interview import (
    SoulInterview, build_summary, derive_firm_profile, load_responses, soul_status,
)
from ...onboarding.workspace import scaffold_matter_workspace
from ...output.docx_export import draft_to_docx
from ...policy import budget as policy_budget
from ._common import assert_owns_matter, load_profile_snapshot, MAX_UPLOAD_BYTES, _is_uuid, sse
from . import delegation as delegation_routes
from .hitl import _resume
from .stream import SSE_PING_SECONDS, StreamBody, stream_matter

router = APIRouter(prefix="/api", tags=["ux"])

logger = logging.getLogger("mia.api.ux")


# Precio aproximado USD por token (mezcla entrada/salida) — solo para el estimado del dashboard.
_USD_PER_TOKEN = 0.000009

_PROPOSAL_LABEL = {
    "improve_playbook": "Mejorar procedimiento",
    "new_playbook": "Nuevo procedimiento detectado",
    "flag_gap": "Brecha de conocimiento",
    "wiki_correction": "Corrección pendiente",
    "weekly_report": "Resumen semanal",
    # La identidad del despacho (SOUL.md): Mia la PROPONE, nunca la escribe sola.
    "soul_rule": "Ajuste a la descripción de tu despacho",
}
_JOB_LABEL = {
    "sync_obsidian_all_tenants": "Sincronización del conocimiento",
    "curator_weekly": "Depuración del conocimiento",
    "feedback_daily": "Aprendizaje de Mia",
    "dreams_weekly": "Consolidación semanal",
}

# B4 (frente B): el nombre del concepto de una `wiki_correction` vive en la columna
# `target_concept` (migración 026). Antes viajaba codificado dentro de `rationale` con
# este prefijo — el parseo por texto libre quedaba roto en silencio si el prefijo
# cambiaba o el rationale se editaba (hallazgo de revisor capa 2); se conserva SOLO
# como fallback de lectura para filas creadas antes de la migración.
_WIKI_CORRECTION_RATIONALE_PREFIX = "Corrección sugerida para "


def _concept_from_wiki_correction(rationale: str) -> str:
    """Fallback legado: extrae el concepto del `rationale` de una wiki_correction creada
    antes de que existiera la columna `target_concept`."""
    r = (rationale or "").strip()
    if r.startswith(_WIKI_CORRECTION_RATIONALE_PREFIX):
        return r[len(_WIKI_CORRECTION_RATIONALE_PREFIX):].strip()
    return ""


def _available_models() -> list[str]:
    # Ancla de instancia (Fase 4 · R1): la cáscara empaquetada coloca el yaml junto
    # al .env; en desarrollo PROJECT_ROOT es la raíz del repo (mismo lugar histórico).
    from mia import config as _config
    cfg = Path(_config.PROJECT_ROOT) / "litellm_config.yaml"
    if not cfg.exists():
        return []
    out: list[str] = []
    for line in cfg.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line.startswith("- model_name:"):
            out.append(line.split(":", 1)[1].strip())
    return out


def _tenant(request: Request) -> str:
    tid = getattr(request.state, "tenant_id", None)
    if not tid:
        raise HTTPException(status_code=401, detail="Sin sesión activa")
    return tid


# Tipos de espacio válidos (migración 028 · Bloque A): 'asunto' = expediente jurídico
# formal (diagnóstico + borrador + HITL); 'proyecto' = espacio de trabajo libre
# conectado a carpetas, sin diagnóstico ni aprobación.
_MATTER_KINDS = ("asunto", "proyecto")


async def _matter_kind(tid: str, matter_id: str) -> str:
    """Tipo del espacio ('asunto'|'proyecto'). Asume ya validada la propiedad
    (assert_owns_matter) — un matter_id inexistente cae al valor por defecto."""
    async with pool.tenant_connection(tid) as conn:
        row = await (await conn.execute(
            "SELECT kind FROM matters WHERE id = %s::uuid", (matter_id,))).fetchone()
    return row[0] if row else "asunto"


# ── Pantalla 1 / 2 · asuntos ─────────────────────────────────────────────────
class MatterCreate(BaseModel):
    name: str
    description: str = ""
    kind: str = "asunto"


@router.get("/matters")
async def list_matters(request: Request, kind: str = Query("asunto")):
    """Sin `kind` (compat): solo 'asunto' — la lista de Asuntos actual no debe mostrar
    proyectos. `kind=proyecto`: solo proyectos. `kind=todos`: todo. Cualquier otro valor
    se trata como 'asunto' (mismo criterio conservador que el filtro por defecto)."""
    tid = _tenant(request)
    where, params = "", ()
    if kind == "todos":
        where = ""
    else:
        k = "proyecto" if kind == "proyecto" else "asunto"
        where, params = "WHERE kind = %s", (k,)
    async with pool.tenant_connection(tid) as conn:
        rows = await (await conn.execute(
            "SELECT id, title, description, status, created_at, pending_review, kind FROM matters "
            f"{where} ORDER BY created_at DESC", params)).fetchall()
    return [{"id": str(r[0]), "name": r[1], "description": r[2], "status": r[3],
             "created_at": r[4], "pending_review": bool(r[5]), "kind": r[6]} for r in rows]


@router.post("/matters", status_code=201)
async def create_matter(request: Request, body: MatterCreate):
    tid = _tenant(request)
    if body.kind not in _MATTER_KINDS:
        raise HTTPException(status_code=422, detail="Ese tipo de espacio no existe")
    async with pool.tenant_connection(tid) as conn:
        row = await (await conn.execute(
            "INSERT INTO matters (tenant_id, title, description, kind) VALUES (%s::uuid, %s, %s, %s) "
            "RETURNING id, status, created_at",
            (tid, body.name, body.description, body.kind))).fetchone()
    # Andamiaje en disco del expediente (solo Asuntos): alias = UUID del asunto (convención
    # crítica y consistente). El disco es ACCESORIO — jamás debe tumbar el alta, así que va
    # fuera del event loop y en try/except que solo loguea.
    if body.kind == "asunto":
        try:
            await run_in_threadpool(
                scaffold_matter_workspace, tid, str(row[0]), titulo=body.name)
        except Exception:
            logger.exception(
                "no se pudo andamiar el expediente en disco (tenant=%s matter=%s)",
                tid, str(row[0]))
    return {"id": str(row[0]), "name": body.name, "description": body.description,
            "status": row[1], "created_at": row[2], "kind": body.kind}


@router.get("/matters/{matter_id}")
async def get_matter(matter_id: str, request: Request):
    tid = _tenant(request)
    await assert_owns_matter(tid, matter_id)
    async with pool.tenant_connection(tid) as conn:
        row = await (await conn.execute(
            "SELECT id, title, description, status, created_at, kind FROM matters "
            "WHERE id = %s::uuid", (matter_id,))).fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="Asunto no encontrado")
    return {"id": str(row[0]), "name": row[1], "description": row[2], "status": row[3],
            "created_at": row[4], "kind": row[5]}


# ── Pantalla 2 · documentos ──────────────────────────────────────────────────
@router.get("/matters/{matter_id}/documents")
async def list_documents(matter_id: str, request: Request):
    tid = _tenant(request)
    await assert_owns_matter(tid, matter_id)
    async with pool.tenant_connection(tid) as conn:
        rows = await (await conn.execute(
            "SELECT id, filename, mime, created_at FROM documents "
            "WHERE matter_id = %s::uuid ORDER BY created_at DESC", (matter_id,))).fetchall()
    return [{"id": str(r[0]), "name": r[1], "type": r[2], "created_at": r[3]} for r in rows]


@router.post("/matters/{matter_id}/documents", status_code=201)
async def upload_document(matter_id: str, request: Request, response: Response,
                          file: UploadFile = File(...)):
    tid = _tenant(request)
    await assert_owns_matter(tid, matter_id)
    # Lectura ACOTADA (auditoría 2026-07): leer solo hasta el límite + 1 byte evita
    # cargar en RAM un archivo arbitrariamente grande antes de poder rechazarlo.
    data = await file.read(MAX_UPLOAD_BYTES + 1)
    if len(data) > MAX_UPLOAD_BYTES:
        raise HTTPException(status_code=413, detail="El archivo supera el límite de 50 MB.")
    # Dedupe: si este MISMO archivo (huella sha256) ya está en el expediente, no se vuelve
    # a procesar ni a embeber — se avisa en llano y se conserva lo que ya había.
    sha256 = hashlib.sha256(data).hexdigest()
    async with pool.tenant_connection(tid) as conn:
        dup = await (await conn.execute(
            "SELECT id, filename FROM documents WHERE matter_id=%s::uuid AND sha256=%s LIMIT 1",
            (matter_id, sha256))).fetchone()
    if dup:
        # La ruta declara 201 por defecto; un duplicado NO crea nada → se responde 200.
        response.status_code = 200
        return {"status": "duplicado", "id": str(dup[0]), "name": file.filename,
                "message": "Ese documento ya estaba en el expediente — no lo dupliqué."}
    try:
        # M1: la extracción (OCR incluido) es CPU-pesada y va a un hilo — NO al event loop.
        text, meta = await extract_text_detailed_async(file.filename, data)
    except ValueError as e:
        raise HTTPException(status_code=415, detail=str(e))
    # M3: un escaneo del que no se pudo leer NADA no es un documento válido — solo la nota
    # de honestidad pasaría la guarda `if not chunks` de abajo y entraría como éxito falso.
    if not meta.get("has_body", True):
        if meta.get("ocr_unavailable"):
            raise HTTPException(status_code=422, detail=(
                "El documento parece escaneado y este servidor no tiene lectura óptica "
                "instalada — no pude leer su contenido."))
        raise HTTPException(status_code=422, detail="No pude leer texto en este documento.")
    # Troceo con folio: cada chunk lleva el folio (página del PDF) de su offset de inicio,
    # medido sobre el MISMO `text` que devolvió extract (meta['folio_map']). Sin páginas → None.
    pairs = chunk_text_with_folios(text, meta.get("folio_map") or [])
    if not pairs:
        raise HTTPException(status_code=400, detail="El documento está vacío o no tiene texto.")
    vectors = embeddings.embed_texts([c for c, _ in pairs])
    async with pool.tenant_connection(tid) as conn:
        doc_id = (await (await conn.execute(
            "INSERT INTO documents (tenant_id, matter_id, filename, mime, sha256, origin) "
            "VALUES (%s::uuid, %s::uuid, %s, %s, %s, 'upload') RETURNING id",
            (tid, matter_id, file.filename, file.content_type, sha256))).fetchone())[0]
        for i, ((content, folio), vec) in enumerate(zip(pairs, vectors)):
            await conn.execute(
                "INSERT INTO chunks (tenant_id, document_id, ord, content, embedding, procedencia, folio_ancla) "
                "VALUES (%s::uuid, %s, %s, %s, %s, %s, %s)",
                (tid, doc_id, i, content, vec, "documento", folio))
    return {"id": str(doc_id), "name": file.filename, "fragments": len(pairs)}


# ── Proyectos (Bloque A) · archivos producidos por Mia ───────────────────────
# Solo existen dentro de un PROYECTO (kind='proyecto'): un Asunto no tiene "archivos
# producidos" — su único documento formal es el borrador del grafo (draft.docx arriba).
class OutputCreate(BaseModel):
    title: str = Field(min_length=1, max_length=200)
    content: str = Field(min_length=1, max_length=500_000)


@router.post("/matters/{matter_id}/outputs", status_code=201)
async def create_output(matter_id: str, request: Request, response: Response, body: OutputCreate):
    """Guarda un archivo que Mia produjo en el proyecto (el abogado lo pidió y decidió
    conservarlo). Mismo pipeline EXACTO de upload_document (chunk_text + embed_texts +
    INSERT documents/chunks) para que lo producido quede consultable después por Mia."""
    tid = _tenant(request)
    await assert_owns_matter(tid, matter_id)
    if await _matter_kind(tid, matter_id) != "proyecto":
        raise HTTPException(status_code=422,
                            detail="Los archivos guardados solo existen dentro de un proyecto.")
    # Dedupe por huella del CONTENIDO (igual criterio que upload_document con el archivo):
    # guardar dos veces lo mismo no lo duplica ni lo vuelve a embeber.
    sha256 = hashlib.sha256(body.content.encode("utf-8")).hexdigest()
    async with pool.tenant_connection(tid) as conn:
        dup = await (await conn.execute(
            "SELECT id, filename FROM documents WHERE matter_id=%s::uuid AND origin='mia' "
            "AND sha256=%s LIMIT 1", (matter_id, sha256))).fetchone()
    if dup:
        response.status_code = 200
        return {"status": "duplicado", "id": str(dup[0]), "title": dup[1],
                "message": "Ese archivo ya estaba guardado en el proyecto — no lo dupliqué."}
    chunks = chunk_text(body.content)
    try:
        vectors = embeddings.embed_texts(chunks) if chunks else []
    except Exception:
        # M1 (mismo criterio que upload_document): si falla el embebido no se deja NADA
        # a medias — aquí todavía no se insertó nada en documents/chunks.
        logger.exception("no se pudo guardar el archivo del proyecto (tenant=%s matter=%s)",
                         tid, matter_id)
        raise HTTPException(status_code=502, detail=(
            "No pude guardar este archivo en el proyecto — inténtalo de nuevo en un momento."))
    async with pool.tenant_connection(tid) as conn:
        doc_id = (await (await conn.execute(
            "INSERT INTO documents (tenant_id, matter_id, filename, mime, sha256, origin, body) "
            "VALUES (%s::uuid, %s::uuid, %s, %s, %s, 'mia', %s) RETURNING id",
            (tid, matter_id, body.title, "text/markdown", sha256, body.content))).fetchone())[0]
        for i, (content, vec) in enumerate(zip(chunks, vectors)):
            await conn.execute(
                "INSERT INTO chunks (tenant_id, document_id, ord, content, embedding, procedencia) "
                "VALUES (%s::uuid, %s, %s, %s, %s, %s)",
                (tid, doc_id, i, content, vec, "inferido"))
    return {"id": str(doc_id), "title": body.title, "status": "guardado"}


@router.get("/matters/{matter_id}/outputs")
async def list_outputs(matter_id: str, request: Request):
    tid = _tenant(request)
    await assert_owns_matter(tid, matter_id)
    if await _matter_kind(tid, matter_id) != "proyecto":
        raise HTTPException(status_code=422,
                            detail="Los archivos guardados solo existen dentro de un proyecto.")
    async with pool.tenant_connection(tid) as conn:
        rows = await (await conn.execute(
            "SELECT id, filename, created_at FROM documents "
            "WHERE matter_id=%s::uuid AND origin='mia' ORDER BY created_at DESC",
            (matter_id,))).fetchall()
    return {"outputs": [{"id": str(r[0]), "title": r[1], "created_at": r[2]} for r in rows]}


@router.get("/matters/{matter_id}/outputs/{doc_id}.docx")
async def download_output_docx(matter_id: str, doc_id: str, request: Request):
    """El archivo guardado del proyecto como .docx (calca GET /matters/{id}/draft.docx)."""
    tid = _tenant(request)
    await assert_owns_matter(tid, matter_id)
    if await _matter_kind(tid, matter_id) != "proyecto":
        raise HTTPException(status_code=422,
                            detail="Los archivos guardados solo existen dentro de un proyecto.")
    if not _is_uuid(doc_id):
        raise HTTPException(status_code=404, detail="Ese archivo no existe.")
    async with pool.tenant_connection(tid) as conn:
        row = await (await conn.execute(
            "SELECT filename, body FROM documents "
            "WHERE id=%s::uuid AND matter_id=%s::uuid AND origin='mia'",
            (doc_id, matter_id))).fetchone()
    if not row or not row[1]:
        raise HTTPException(status_code=404, detail="Ese archivo no existe.")
    title, body_text = row[0], row[1]
    data = draft_to_docx(body_text, title=title, author="Mia")
    # filename ASCII-safe + variante UTF-8 (RFC 5987) para títulos con tildes.
    # ASCII-only a propósito (mismo bugfix que download_draft_docx): el header
    # filename= (sin *) no tolera un carácter no-ASCII crudo.
    safe = "".join(c if c.isascii() and (c.isalnum() or c in "-_ ") else ""
                   for c in title).strip() or "documento"
    headers = {
        "Content-Disposition":
            f'attachment; filename="{safe[:60]}.docx"; '
            f"filename*=UTF-8''{quote(title[:60], safe='')}.docx"
    }
    return Response(
        content=data,
        media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        headers=headers,
    )


# ── Pantalla 2 · chat + stream ───────────────────────────────────────────────
class ChatBody(BaseModel):
    message: str


@router.post("/matters/{matter_id}/chat")
async def chat(matter_id: str, request: Request, body: ChatBody):
    """Devuelve la URL del stream SSE. El mensaje NO va en la URL: el cliente lo
    reenvía por POST /stream en el body (confidencialidad — no historial/proxy logs)."""
    tid = _tenant(request)
    await assert_owns_matter(tid, matter_id)
    # body.message se valida (min implícito vía uso) pero no se embebe en la URL.
    if not (body.message or "").strip():
        raise HTTPException(status_code=422, detail="Escribe un mensaje para consultar.")
    return {"stream_url": f"/api/matters/{matter_id}/stream"}


@router.post("/matters/{matter_id}/stream")
async def stream_alias_post(matter_id: str, request: Request, body: StreamBody):
    """Alias /api del SSE por POST — mensaje en body, no en query string."""
    return await stream_matter(matter_id, request, body.message)


@router.get("/matters/{matter_id}/stream")
async def stream_alias(matter_id: str, request: Request, message: str = Query(..., min_length=1)):
    """Alias /api del SSE por GET (compat gates). Preferir POST con body."""
    return await stream_matter(matter_id, request, message)


# ── Pantalla 3 · revisión del borrador ───────────────────────────────────────
@router.get("/matters/{matter_id}/draft")
async def get_draft(matter_id: str, request: Request):
    """Expone el borrador pendiente desde el checkpoint del grafo. 404 si no hay borrador."""
    tid = _tenant(request)
    await assert_owns_matter(tid, matter_id)
    cfg = {"configurable": {"thread_id": thread_id_for(tid, matter_id)}}
    async with open_checkpointer() as cp:
        graph = build_matter_graph(cp)
        state = await graph.aget_state(cfg)
    values = (state.values or {}) if state else {}
    draft = values.get("draft")
    if not draft:
        raise HTTPException(status_code=404, detail="No hay un borrador pendiente de revisión.")
    awaiting = bool(state and state.next)   # el grafo está pausado esperando la revisión
    # Riesgo #25: el diagnóstico jurídico viaja en el mismo estado del checkpoint.
    # CP6: al abogado llega la PROSA sin el bloque de máquina `===` (§G);
    # diagnosis_summary = cierre estructurado (problema/normas/riesgo) para la
    # Pantalla 2; None si el modelo no emitió el bloque.
    md = values.get("metadata") or {}
    # B3 (corrección post-review): el desenlace REAL del HITL (mismo vocabulario que
    # finalize_node usa para la traza: approved/rejected/edited). `awaiting_review=False`
    # por sí solo NO distingue "aprobado" de "rechazado" o "editado" — los tres llegan a
    # END con el grafo ya no pausado (finalize_node conserva el borrador en los tres
    # casos). El frontend usa este campo (no awaiting_review) para decidir si el botón
    # "Convertir en guía" es válido, alineado con el mismo criterio que ya usa
    # interviewer.py para cargar evidencia (`hitl_outcome == 'approved'`).
    hitl_outcome = HITL_OUTCOME.get(values.get("hitl_status"))
    return {"draft": draft, "awaiting_review": awaiting, "hitl_outcome": hitl_outcome,
            "diagnosis": strip_diagnosis_closing(md.get("diagnosis") or "") or None,
            "diagnosis_summary": md.get("diagnosis_summary"),
            # CP9: informe del especialista de verificación de citas (None en
            # borradores de turnos anteriores a CP9).
            "verification": md.get("verification")}


@router.get("/matters/{matter_id}/historial")
async def matter_history(matter_id: str, request: Request):
    """Los turnos previos del asunto, en orden, para repintar el hilo tras un F5 (Riesgo #70).

    El hilo vivía solo en el estado de React: al recargar la página desaparecía aunque los
    turnos estén guardados. Aquí se leen de `traces` bajo RLS (el asunto de otro despacho es
    invisible) y se devuelven como mensajes en orden cronológico. §G: nada de jerga hacia el
    abogado — solo el texto de cada turno."""
    tid = _tenant(request)
    await assert_owns_matter(tid, matter_id)
    async with pool.tenant_connection(tid) as conn:
        rows = await (await conn.execute(
            # matter_id en `traces` es text (así lo escribe index_trace): sin ::uuid.
            "SELECT input, output FROM traces WHERE matter_id = %s "
            "ORDER BY COALESCE(trace_ts, created_at) ASC",
            (str(matter_id),))).fetchall()
    mensajes: list[dict] = []
    for entrada, salida in rows:
        if entrada and str(entrada).strip():
            mensajes.append({"role": "user", "text": str(entrada)})
        if salida and str(salida).strip():
            mensajes.append({"role": "mia", "text": str(salida)})
    return {"mensajes": mensajes}


@router.get("/matters/{matter_id}/draft.docx")
async def download_draft_docx(matter_id: str, request: Request):
    """CP9 · emisión Word: el borrador actual como .docx con formato de escrito.

    Disponible para el borrador pendiente Y para el aprobado (el checkpoint conserva
    el último borrador del asunto). 404 si el asunto aún no tiene borrador."""
    tid = _tenant(request)
    await assert_owns_matter(tid, matter_id)
    cfg = {"configurable": {"thread_id": thread_id_for(tid, matter_id)}}
    async with open_checkpointer() as cp:
        graph = build_matter_graph(cp)
        state = await graph.aget_state(cfg)
    values = (state.values or {}) if state else {}
    draft = values.get("draft")
    if not draft:
        raise HTTPException(status_code=404, detail="El asunto aún no tiene un borrador.")
    async with pool.tenant_connection(tid) as conn:
        row = await (await conn.execute(
            "SELECT title FROM matters WHERE id = %s::uuid", (matter_id,))).fetchone()
    title = (row[0] if row and row[0] else "Borrador")
    data = draft_to_docx(draft, title=title, author="Mia")
    # filename ASCII-safe + variante UTF-8 (RFC 5987) para títulos con tildes.
    # ASCII-only a propósito (bugfix): el header HTTP filename= (sin *) no tolera un
    # carácter no-ASCII crudo (p. ej. 'á' de un título en español pasa isalnum() pero
    # rompe la codificación del header) — la variante con tildes va SOLO en filename*.
    safe = "".join(c if c.isascii() and (c.isalnum() or c in "-_ ") else ""
                   for c in title).strip() or "borrador"
    headers = {
        "Content-Disposition":
            f'attachment; filename="{safe[:60]}.docx"; '
            f"filename*=UTF-8''{quote(title[:60], safe='')}.docx"
    }
    return Response(
        content=data,
        media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        headers=headers,
    )


class ApproveBody(BaseModel):
    edited_text: str | None = None


class RejectBody(BaseModel):
    reason: str = ""


@router.post("/matters/{matter_id}/draft/approve")
async def approve_draft(matter_id: str, request: Request, body: ApproveBody | None = None):
    if body and body.edited_text:
        return await _resume(request, matter_id, {"decision": "editing", "edits": body.edited_text})
    return await _resume(request, matter_id, {"decision": "approved"})


@router.post("/matters/{matter_id}/draft/reject")
async def reject_draft(matter_id: str, request: Request, body: RejectBody | None = None):
    reason = body.reason if body else ""
    return await _resume(request, matter_id, {"decision": "rejected", "feedback": reason})


@router.post("/matters/{matter_id}/delegation/aprobar")
async def delegation_aprobar_alias(
    matter_id: str, request: Request, body: delegation_routes.ApproveBody,
):
    """Alias /api de la pausa de ayudante externo (CP-HUB2)."""
    return await delegation_routes.aprobar(matter_id, request, body)


@router.post("/matters/{matter_id}/delegation/descartar")
async def delegation_descartar_alias(matter_id: str, request: Request):
    return await delegation_routes.descartar(matter_id, request)


# ── Pantalla 4 · perfil ──────────────────────────────────────────────────────
class ProfileBody(BaseModel):
    name: str | None = None
    lawyer_name: str | None = None
    tp_number: str | None = None
    jurisdiction: str | None = None
    practice_areas: list[str] | None = None
    voice_adjectives: list[str] | None = None
    banned_words: list[str] | None = None
    preferred_sources: list[str] | None = None
    hard_nos: list[str] | None = None
    rhythm: dict | None = None
    tools: list[str] | None = None


@router.get("/profile")
async def get_profile(request: Request):
    tid = _tenant(request)
    prof = await ProfileManager(pool=pool, tenant_id=tid).get_firm_profile()
    return prof or {}


# DEPRECADO (Bloque C2): usar /api/profile/full — se mantiene por compatibilidad.
@router.put("/profile")
async def put_profile(request: Request, body: ProfileBody):
    tid = _tenant(request)
    return await ProfileManager(pool=pool).upsert_firm_profile(tid, body.model_dump(exclude_none=True))


# ── Pantalla 4 · perfil unificado (Bloque C · C2) ────────────────────────────
# Hasta C2 había DOS fuentes desconectadas: las respuestas del onboarding (archivo por
# tenant, fuente canónica del SOUL.md) y `firm_profiles` (editada por el PUT /api/profile
# legado de arriba, solo llegaba al mensaje del nodo draft). Editar una no actualizaba la
# otra. Ahora /api/profile/full es la única pantalla de edición: escribe SIEMPRE las
# respuestas (fuente canónica) y deriva `firm_profiles` como best-effort auxiliar.
MAX_PROFILE_RESPONSES_BYTES = 200_000


def _validate_responses_shape(responses: dict) -> None:
    """`responses` debe ser un dict de valores simples (str/list/dict anidado un nivel,
    como llegan las respuestas de la entrevista) y no un payload descomunal — en llano,
    para no dejar pasar algo que reviente el merge de `update_soul` más adelante."""
    if not isinstance(responses, dict):
        raise HTTPException(status_code=422, detail="El formato de tu perfil no es válido.")
    size = len(json.dumps(responses, ensure_ascii=False))
    if size > MAX_PROFILE_RESPONSES_BYTES:
        raise HTTPException(
            status_code=422,
            detail="Tu perfil es demasiado extenso para guardarlo. Resume un poco e intenta de nuevo.",
        )

    def _is_simple(value) -> bool:
        if value is None or isinstance(value, (str, bool, int, float)):
            return True
        if isinstance(value, list):
            return all(_is_simple(v) for v in value)
        if isinstance(value, dict):
            return all(isinstance(k, str) and _is_simple(v) for k, v in value.items())
        return False

    for k, v in responses.items():
        if not isinstance(k, str) or not _is_simple(v):
            raise HTTPException(status_code=422, detail="El formato de tu perfil no es válido.")


class ProfileExtras(BaseModel):
    tp_number: str | None = None
    preferred_sources: list[str] | None = None


class ProfileFullBody(BaseModel):
    responses: dict | None = None
    jurisdictions: list[str] | None = None
    extras: ProfileExtras | None = None


async def _read_jurisdictions_config(tid: str) -> list[str]:
    """Códigos de jurisdicción guardados (o [] si nunca se configuraron). Mismo SELECT
    que `jurisdiction.resolver.resolve_jurisdictions`, sin el fallback ['generic'] — aquí
    queremos saber si el abogado configuró algo, no resolver el modo activo."""
    async with pool.tenant_connection(tid) as conn:
        row = await (await conn.execute(
            "SELECT config->'jurisdictions' FROM tenant_settings WHERE tenant_id=%s::uuid", (tid,)
        )).fetchone()
    vals = row[0] if row and row[0] else []
    return [str(c).strip().lower() for c in vals if str(c).strip()]


@router.get("/profile/full")
async def get_profile_full(request: Request):
    """Perfil unificado del despacho: respuestas de la entrevista (fuente canónica),
    jurisdicciones activas y los extras estructurados que solo viven en `firm_profiles`
    (tarjeta profesional, fuentes preferidas). `summary` es el mismo resumen en lenguaje
    llano que se muestra al terminar el onboarding."""
    tid = _tenant(request)
    responses = load_responses(tid)
    jurisdictions = await _read_jurisdictions_config(tid)
    prof = await ProfileManager(pool=pool, tenant_id=tid).get_firm_profile() or {}
    extras = {
        "tp_number": prof.get("tp_number") or "",
        "preferred_sources": prof.get("preferred_sources") or [],
    }
    return {
        "responses": responses,
        "jurisdictions": jurisdictions,
        "extras": extras,
        "summary": build_summary(responses),
        "completed": soul_status(tid)["completed"],
    }


@router.put("/profile/full")
async def put_profile_full(request: Request, body: ProfileFullBody):
    """Guarda el perfil del despacho en la fuente canónica (respuestas de la entrevista)
    y, best-effort, refleja los campos derivables en `firm_profiles`.

    1. `responses`: fusiona con `SoulInterview.update_soul` (merge superficial por clave
       top-level — el llamador debe mandar el objeto COMPLETO por cada clave que edita).
       Si falla, 502 en llano y NO se sigue (es la escritura crítica).
    2. `jurisdictions`: persiste los códigos en `tenant_settings.config.jurisdictions`.
    3. Best-effort: deriva `firm_profiles` de las respuestas actuales + los extras del
       body y hace upsert. Si falla, NO rompe la respuesta — se avisa con `warning`.
    """
    tid = _tenant(request)
    responses = load_responses(tid)

    if body.responses is not None:
        _validate_responses_shape(body.responses)
        try:
            await SoulInterview().update_soul(tid, body.responses)
        except Exception:
            logger.exception("no se pudo actualizar el perfil del despacho (tenant=%s)", tid)
            raise HTTPException(status_code=502, detail="No pudimos guardar tu perfil. Intenta de nuevo.")
        responses = load_responses(tid)

    if body.jurisdictions is not None:
        codes = [str(c).strip().lower() for c in body.jurisdictions if str(c).strip()]
        async with pool.tenant_connection(tid) as conn:
            await conn.execute(
                "INSERT INTO tenant_settings (tenant_id, config) VALUES (%s::uuid, %s) "
                "ON CONFLICT (tenant_id) DO UPDATE SET "
                "config = jsonb_set(tenant_settings.config, '{jurisdictions}', %s::jsonb, true), "
                "updated_at = now()",
                (tid, Json({"jurisdictions": codes}), Json(codes)),
            )

    warning: str | None = None
    try:
        # `upsert_firm_profile` siempre escribe las 10 columnas (no hace update parcial) —
        # sin esto, cada guardado desde aquí BORRARÍA en silencio lo que otro flujo (el PUT
        # /api/profile legado, o una llamada anterior a este mismo endpoint que no volvió a
        # mandar `extras`) ya había guardado en `voice_adjectives`/`banned_words`/`hard_nos`/
        # `rhythm` y en los propios extras. Se preserva leyendo el estado actual primero.
        existing = await ProfileManager(pool=pool, tenant_id=tid).get_firm_profile() or {}
        derived = derive_firm_profile(responses)
        extras = body.extras.model_dump(exclude_none=True) if body.extras else {}
        # Se preservan TODAS las columnas existentes: las derivadas (`derived`) solo
        # SOBREESCRIBEN cuando traen valor — un responses.json sin esos campos jamás
        # anula con NULL lo que otro flujo ya había guardado en firm_profiles.
        preserved = {
            "name": existing.get("name"),
            "lawyer_name": existing.get("lawyer_name"),
            "jurisdiction": existing.get("jurisdiction"),
            "practice_areas": existing.get("practice_areas"),
            "tools": existing.get("tools"),
            "tp_number": existing.get("tp_number"),
            "preferred_sources": existing.get("preferred_sources"),
            "voice_adjectives": existing.get("voice_adjectives"),
            "banned_words": existing.get("banned_words"),
            "hard_nos": existing.get("hard_nos"),
            "rhythm": existing.get("rhythm"),
        }
        await ProfileManager(pool=pool).upsert_firm_profile(tid, {**preserved, **derived, **extras})
    except Exception:
        logger.exception("no se pudo actualizar el perfil auxiliar del despacho (tenant=%s)", tid)
        warning = "Tu perfil quedó guardado. Una parte auxiliar no se pudo actualizar; Mia lo reintentará."

    out: dict = {"ok": True, "summary": build_summary(responses)}
    if warning:
        out["warning"] = warning
    return out


# ── Pantalla 4 · playbooks (Bloque B · B0: CRUD + versiones + origen) ────────
# origin: de dónde salió el playbook — se guarda en metadata.origin (la tabla no gana
# columna nueva; jsonb evita otra migración solo para un rótulo informativo).
_PLAYBOOK_ORIGINS = ("manual", "importada", "entrevista", "asunto", "aprendida")


class PlaybookBody(BaseModel):
    title: str
    summary: str
    applies_when: str
    content: str
    origin: str = "manual"


def _playbook_out(row: dict, *, with_content: bool = False) -> dict:
    """Traduce una fila de `playbooks` a lo que ve el abogado. `origin` sale de
    metadata (default 'manual' para playbooks creados antes de que existiera el campo)."""
    md = row.get("metadata") or {}
    out = {"id": str(row["id"]), "title": row["title"], "summary": row["summary"],
           "applies_when": row["applies_when"], "status": row.get("status", "active"),
           "protected": bool(row.get("protected")), "origin": md.get("origin", "manual"),
           "health_status": row.get("health_status") or "sin_revisar"}
    if with_content:
        out["content"] = row["content"]
    return out


async def _set_playbook_origin(tid: str, playbook_id: str, origin: str) -> None:
    async with pool.tenant_connection(tid) as conn:
        await conn.execute(
            "UPDATE playbooks SET metadata = jsonb_set(COALESCE(metadata, '{}'::jsonb), "
            "'{origin}', to_jsonb(%s::text)) WHERE id = %s::uuid", (origin, playbook_id))


async def _get_playbook_row(tid: str, playbook_id: str) -> dict | None:
    async with pool.tenant_connection(tid) as conn:
        async with conn.cursor(row_factory=dict_row) as cur:
            await cur.execute(
                "SELECT id, title, summary, applies_when, content, status, protected, "
                "usage_count, last_used_at, metadata, created_at, updated_at, "
                "health_status, health_checked_at "
                "FROM playbooks WHERE id = %s::uuid", (playbook_id,))
            return await cur.fetchone()


@router.get("/playbooks")
async def list_playbooks(request: Request, status: str = Query("activos")):
    """`status=activos` (default): solo playbooks activos. `status=todos`: incluye
    archivados. Cualquier otro valor se trata como 'activos' (mismo criterio conservador
    que el filtro de /matters)."""
    tid = _tenant(request)
    where = "" if status == "todos" else "WHERE status = 'active'"
    async with pool.tenant_connection(tid) as conn:
        async with conn.cursor(row_factory=dict_row) as cur:
            await cur.execute(
                "SELECT id, title, summary, applies_when, status, protected, metadata, "
                "health_status "
                f"FROM playbooks {where} ORDER BY usage_count DESC, created_at", ())
            rows = await cur.fetchall()
    return [_playbook_out(r) for r in rows]


@router.get("/playbooks/{playbook_id}")
async def get_playbook_detail(playbook_id: str, request: Request):
    tid = _tenant(request)
    if not _is_uuid(playbook_id):
        raise HTTPException(status_code=404, detail="Esa guía no existe.")
    row = await _get_playbook_row(tid, playbook_id)
    if not row:
        raise HTTPException(status_code=404, detail="Esa guía no existe.")
    return _playbook_out(row, with_content=True)


@router.post("/playbooks", status_code=201)
async def create_playbook(request: Request, body: PlaybookBody):
    """Crea una guía NUEVA. A diferencia de `PlaybookManager.register_playbook` (usado por
    el import y por el seeding, que hacen UPSERT a propósito por título), este camino
    NUNCA pisa una guía existente: si el título ya lo tiene otra guía del despacho (activa
    O archivada) se responde 409 en llano — nada se sobrescribe en silencio ni queda
    "oculta" en una fila archivada (hallazgo mayor del revisor)."""
    tid = _tenant(request)
    if body.origin not in _PLAYBOOK_ORIGINS:
        raise HTTPException(status_code=422, detail="Ese origen no es válido.")
    vec = embeddings.embed_texts([f"{body.summary}\n{body.applies_when}"])[0]
    async with pool.tenant_connection(tid) as conn:
        row = await (await conn.execute(
            "INSERT INTO playbooks (tenant_id, title, summary, applies_when, content, "
            "embedding, metadata) VALUES (%s::uuid, %s, %s, %s, %s, %s, %s) "
            "ON CONFLICT (tenant_id, title) DO NOTHING RETURNING id",
            (tid, body.title, body.summary, body.applies_when, body.content, vec,
             Json({"origin": body.origin})))).fetchone()
    if not row:
        raise HTTPException(status_code=409, detail="Ya tienes una guía con ese nombre.")
    return {"id": str(row[0]), "title": body.title, "origin": body.origin}


class PlaybookUpdate(BaseModel):
    title: str | None = None
    summary: str | None = None
    applies_when: str | None = None
    content: str | None = None


@router.put("/playbooks/{playbook_id}")
async def update_playbook(playbook_id: str, request: Request, body: PlaybookUpdate):
    """Edición manual del abogado. Editable AUNQUE el playbook esté protegido —
    `protected` solo bloquea cambios AUTOMÁTICOS (apply_proposal). Antes de escribir,
    guarda un snapshot del estado ANTERIOR en playbook_versions y re-embebe
    (summary+applies_when) igual que register_playbook."""
    tid = _tenant(request)
    if not _is_uuid(playbook_id):
        raise HTTPException(status_code=404, detail="Esa guía no existe.")
    row = await _get_playbook_row(tid, playbook_id)
    if not row:
        raise HTTPException(status_code=404, detail="Esa guía no existe.")
    # `title` es varchar(200) NOT NULL; recortar aquí evita un StringDataRightTruncation
    # no capturado (500 técnico) ante un título editado a mano que exceda el límite —
    # mismo tope que ya aplican el motor de entrevista y la rama new_playbook de abajo.
    new_title = (body.title if body.title is not None else row["title"])[:200]
    new_summary = body.summary if body.summary is not None else row["summary"]
    new_applies = body.applies_when if body.applies_when is not None else row["applies_when"]
    new_content = body.content if body.content is not None else row["content"]
    vec = embeddings.embed_texts([f"{new_summary}\n{new_applies}"])[0]
    async with pool.tenant_connection(tid) as conn:
        await conn.execute(
            "INSERT INTO playbook_versions (tenant_id, playbook_id, title, summary, "
            "applies_when, content, changed_by, reason) VALUES "
            "(%s::uuid, %s::uuid, %s, %s, %s, %s, 'abogado', %s)",
            (tid, playbook_id, row["title"], row["summary"], row["applies_when"],
             row["content"], "Edición manual del abogado"))
        try:
            await conn.execute(
                "UPDATE playbooks SET title=%s, summary=%s, applies_when=%s, content=%s, "
                "embedding=%s, updated_at=now() WHERE id=%s::uuid",
                (new_title, new_summary, new_applies, new_content, vec, playbook_id))
        except psycopg.errors.UniqueViolation:
            raise HTTPException(status_code=409, detail="Ya existe otra guía con ese nombre.")
    updated = await _get_playbook_row(tid, playbook_id)
    return _playbook_out(updated, with_content=True)


@router.post("/playbooks/{playbook_id}/archive")
async def archive_playbook(playbook_id: str, request: Request):
    """Archivar saca el playbook del índice del prompt (get_index filtra status='active')
    sin tocar prompt_builder."""
    tid = _tenant(request)
    if not _is_uuid(playbook_id):
        raise HTTPException(status_code=404, detail="Esa guía no existe.")
    async with pool.tenant_connection(tid) as conn:
        res = await conn.execute(
            "UPDATE playbooks SET status='archived', updated_at=now() WHERE id=%s::uuid",
            (playbook_id,))
    if res.rowcount == 0:
        raise HTTPException(status_code=404, detail="Esa guía no existe.")
    return {"status": "archivada"}


@router.post("/playbooks/{playbook_id}/restore")
async def restore_playbook(playbook_id: str, request: Request):
    tid = _tenant(request)
    if not _is_uuid(playbook_id):
        raise HTTPException(status_code=404, detail="Esa guía no existe.")
    async with pool.tenant_connection(tid) as conn:
        res = await conn.execute(
            "UPDATE playbooks SET status='active', updated_at=now() WHERE id=%s::uuid",
            (playbook_id,))
    if res.rowcount == 0:
        raise HTTPException(status_code=404, detail="Esa guía no existe.")
    return {"status": "activa"}


@router.get("/playbooks/{playbook_id}/versions")
async def list_playbook_versions(playbook_id: str, request: Request):
    tid = _tenant(request)
    if not _is_uuid(playbook_id):
        raise HTTPException(status_code=404, detail="Esa guía no existe.")
    if not await _get_playbook_row(tid, playbook_id):
        raise HTTPException(status_code=404, detail="Esa guía no existe.")
    async with pool.tenant_connection(tid) as conn:
        async with conn.cursor(row_factory=dict_row) as cur:
            await cur.execute(
                "SELECT id, changed_by, reason, created_at, title FROM playbook_versions "
                "WHERE playbook_id = %s::uuid ORDER BY created_at DESC", (playbook_id,))
            rows = await cur.fetchall()
    return {"versions": [{"id": str(r["id"]), "changed_by": r["changed_by"],
                          "reason": r["reason"], "created_at": r["created_at"],
                          "title": r["title"]} for r in rows]}


@router.post("/playbooks/{playbook_id}/versions/{version_id}/restore")
async def restore_playbook_version(playbook_id: str, version_id: str, request: Request):
    """Restaura una versión anterior. Antes de restaurar, guarda snapshot del estado
    ACTUAL (para poder deshacer también la restauración)."""
    tid = _tenant(request)
    if not _is_uuid(playbook_id) or not _is_uuid(version_id):
        raise HTTPException(status_code=404, detail="Esa versión no existe.")
    current = await _get_playbook_row(tid, playbook_id)
    if not current:
        raise HTTPException(status_code=404, detail="Esa guía no existe.")
    async with pool.tenant_connection(tid) as conn:
        async with conn.cursor(row_factory=dict_row) as cur:
            await cur.execute(
                "SELECT title, summary, applies_when, content FROM playbook_versions "
                "WHERE id = %s::uuid AND playbook_id = %s::uuid", (version_id, playbook_id))
            ver = await cur.fetchone()
    if not ver:
        raise HTTPException(status_code=404, detail="Esa versión no existe.")
    # E/S de red (embeddings) FUERA de la conexión pooled del tenant — mismo criterio que
    # update_playbook y que el comentario de apply_proposal sobre no agotar el pool del
    # tenant bajo carga concurrente (hallazgo del revisor).
    vec = embeddings.embed_texts([f"{ver['summary']}\n{ver['applies_when']}"])[0]
    async with pool.tenant_connection(tid) as conn:
        try:
            await conn.execute(
                "INSERT INTO playbook_versions (tenant_id, playbook_id, title, summary, "
                "applies_when, content, changed_by, reason) VALUES "
                "(%s::uuid, %s::uuid, %s, %s, %s, %s, 'abogado', %s)",
                (tid, playbook_id, current["title"], current["summary"], current["applies_when"],
                 current["content"], "Restauración a una versión anterior"))
            await conn.execute(
                "UPDATE playbooks SET title=%s, summary=%s, applies_when=%s, content=%s, "
                "embedding=%s, updated_at=now() WHERE id=%s::uuid",
                (ver["title"], ver["summary"], ver["applies_when"], ver["content"], vec, playbook_id))
        except psycopg.errors.UniqueViolation:
            raise HTTPException(status_code=409, detail="Ya existe otra guía con ese nombre.")
    updated = await _get_playbook_row(tid, playbook_id)
    return _playbook_out(updated, with_content=True)


# ── Pantalla 4 · import de guías de trabajo (Riesgo #20: seeding de playbooks) ──
_PLAYBOOK_IMPORT_EXTS = (".md", ".txt", ".docx")
# Tope de guías por archivo importado (revisión CP4): protege costo de embeddings,
# número de inserts y el tamaño del índice que viaja al prompt.
MAX_IMPORT_SECTIONS = 100
# Marcadores de la línea "cuándo aplica" al inicio del cuerpo de una sección.
_APPLIES_PREFIXES = ("cuándo:", "cuando:", "aplica:")


def _split_level1_sections(text: str) -> list[tuple[str, list[str]]]:
    """Divide el texto por encabezados de nivel 1 ('# Título'). Devuelve
    [(título, líneas_del_cuerpo)]. Sin encabezados de nivel 1 → lista vacía
    (el llamador aplica el fallback de archivo-sin-encabezados)."""
    sections: list[tuple[str, list[str]]] = []
    for line in text.splitlines():
        if line.startswith("# ") and line[2:].strip():
            # títulos al límite de la columna (varchar 200) para no romper el batch
            sections.append((line[2:].strip()[:200], []))
        elif sections:
            sections[-1][1].append(line)
    return sections


def _section_to_playbook(title: str, body_lines: list[str]) -> Playbook:
    """Convierte una sección (título + cuerpo) en un Playbook. Si la primera línea
    del cuerpo empieza con 'Cuándo:'/'Cuando:'/'Aplica:', esa línea es applies_when
    y el resto es content; si no, applies_when se deriva del título y todo es content."""
    body = "\n".join(body_lines).strip()
    first, _, rest = body.partition("\n")
    if first.strip().lower().startswith(_APPLIES_PREFIXES):
        # cap a 200 (revisión CP4): applies_when entra al índice que va SIEMPRE al prompt
        applies_when = first.split(":", 1)[1].strip()[:200]
        content = rest.strip()
    else:
        applies_when = f"asuntos relacionados con: {title}"
        content = body
    summary = (content.splitlines() or [title])[0].strip()[:200] or title
    return Playbook(id="", title=title, summary=summary,
                    applies_when=applies_when, content=content)


@router.post("/playbooks/import")
async def import_playbooks(request: Request,
                           files: list[UploadFile] = File(...),
                           protected: bool = Query(False)):
    """Importa las guías de trabajo del despacho desde archivos .md, .txt o Word .docx
    (varios a la vez). Cada encabezado de nivel 1 ('# Título') es una guía; un archivo
    sin encabezados se importa como UNA guía con el nombre del archivo como título.
    Títulos repetidos se omiten (no pisan lo ya guardado). `protected=true` marca las
    guías como protegidas frente al mantenimiento automático (H.6). Cierra la brecha
    de seeding del Riesgo #20."""
    tid = _tenant(request)
    mgr = PlaybookManager(pool=pool, tenant_id=tid)
    importados: list[str] = []
    omitidos: list[str] = []
    errores: list[str] = []
    seen: set[str] = set()
    for f in files:
        fname = f.filename or "archivo"
        if not fname.lower().endswith(_PLAYBOOK_IMPORT_EXTS):
            errores.append(f"{fname}: tipo de archivo no soportado. Usa .md, .txt o Word .docx.")
            continue
        # Lectura acotada (auditoría 2026-07): mismo criterio que upload_document.
        data = await f.read(MAX_UPLOAD_BYTES + 1)
        if len(data) > MAX_UPLOAD_BYTES:
            errores.append(f"{fname}: el archivo supera el límite de 50 MB.")
            continue
        try:
            # M1: extracción en hilo (no bloquea el event loop en imports grandes de guías).
            text = await extract_text_async(fname, data)
        except ValueError as e:
            errores.append(f"{fname}: {e}")
            continue
        except Exception:
            errores.append(f"{fname}: no se pudo leer el archivo. Verifica que no esté dañado.")
            continue
        if not text.strip():
            errores.append(f"{fname}: el archivo está vacío o no tiene texto.")
            continue
        sections = _split_level1_sections(text)
        if not sections:
            # Sin encabezados '#' (p. ej. un Word plano o un .txt): todo el archivo es UNA guía.
            sections = [(Path(fname).stem[:200], text.splitlines())]
        if len(sections) > MAX_IMPORT_SECTIONS:
            # tope (revisión CP4): cada guía cuesta un insert + una llamada de embeddings,
            # y el índice de guías viaja al prompt en cada consulta del despacho.
            errores.append(f"{fname}: tiene {len(sections)} guías; el máximo por archivo es "
                           f"{MAX_IMPORT_SECTIONS}. Divide el archivo e importa por partes.")
            continue
        for title, body_lines in sections:
            if title in seen or await mgr.get_playbook(title) is not None:
                omitidos.append(title)
                continue
            try:
                pid = await mgr.register_playbook(_section_to_playbook(title, body_lines),
                                                  protected=protected)
                await _set_playbook_origin(tid, pid, "importada")
            except Exception:
                # (revisión CP4) un fallo puntual (p. ej. embeddings caído) no aborta el
                # batch ni deja la respuesta inconsistente: las demás guías siguen.
                logger.exception("import de playbook falló (tenant=%s, título=%s)", tid, title)
                errores.append(f"{title}: no se pudo guardar esta guía. Intenta de nuevo más tarde.")
                continue
            seen.add(title)
            importados.append(title)
    return {"importados": importados, "omitidos": omitidos, "errores": errores}


# ── Pantalla 4 · sugerencias de Mia (feedback_proposals) ─────────────────────
async def _source_matters(conn, trace_ids: list[str] | None) -> list[str]:
    """B4: títulos de los asuntos/proyectos de donde salió una propuesta, derivados de
    `trace_ids` ('tenant:matter:ts', ver feedback_processor.py). split(":", 2) porque el
    timestamp ISO trae colones propios (HH:MM:SS) — solo los DOS primeros colones separan
    tenant/matter. Fail-open: cualquier trace_id mal formado, matter_id inválido o ya
    borrado se ignora en silencio; nunca rompe la lista de propuestas."""
    if not trace_ids:
        return []
    matter_ids: list[str] = []
    seen: set[str] = set()
    for t in trace_ids:
        parts = (t or "").split(":", 2)
        if len(parts) < 2:
            continue
        mid = parts[1]
        if _is_uuid(mid) and mid not in seen:
            seen.add(mid)
            matter_ids.append(mid)
    if not matter_ids:
        return []
    try:
        rows = await (await conn.execute(
            "SELECT title FROM matters WHERE id = ANY(%s::uuid[])", (matter_ids,))).fetchall()
        return [r[0] for r in rows]
    except Exception:  # noqa: BLE001 — la lista de propuestas nunca debe romperse por esto
        logger.exception("no se pudieron resolver los asuntos de origen de una propuesta")
        return []


@router.get("/proposals")
async def list_proposals(request: Request):
    tid = _tenant(request)
    async with pool.tenant_connection(tid) as conn:
        async with conn.cursor(row_factory=dict_row) as cur:
            # CP-C3: se incluye el TÍTULO del playbook target — el abogado debe saber
            # QUÉ procedimiento se modificará al aplicar (hallazgo mayor del revisor).
            await cur.execute(
                "SELECT fp.id, fp.proposal_type, fp.suggested_content, fp.rationale, "
                "       fp.signal_count, fp.created_at, fp.trace_ids, "
                "       COALESCE(pb.title, fp.target_concept) AS target_title "
                "FROM feedback_proposals fp "
                "LEFT JOIN playbooks pb ON pb.id = fp.target_playbook_id "
                "WHERE fp.status = 'pending' ORDER BY fp.created_at DESC")
            rows = await cur.fetchall()
        out = []
        for r in rows:
            out.append({"id": str(r["id"]),
                        "type": _PROPOSAL_LABEL.get(r["proposal_type"], r["proposal_type"]),
                        "suggestion": r["suggested_content"], "reason": r["rationale"],
                        "target": r["target_title"],
                        "times_seen": r["signal_count"], "created_at": r["created_at"],
                        "source_matters": await _source_matters(conn, r["trace_ids"])})
    return out


class ApplyProposalBody(BaseModel):
    """B4: el abogado corrige antes de aplicar — ya no es solo aprobar/ignorar."""
    content: str | None = None
    title: str | None = None


@router.post("/proposals/{proposal_id}/apply")
async def apply_proposal(proposal_id: str, request: Request,
                         body: ApplyProposalBody | None = None):
    """Aplica una propuesta: actualiza/crea un playbook y la marca 'applied' (cierra parte del
    Riesgo #21). `body` opcional deja que el abogado edite el contenido (y, para una guía
    nueva, el título) antes de guardarlo — nunca se guarda a ciegas lo que Mia propuso."""
    tid = _tenant(request)
    if not _is_uuid(proposal_id):
        raise HTTPException(status_code=404, detail="Sugerencia no encontrada o ya revisada.")
    edited_content = body.content if body and body.content else None
    edited_title = body.title if body and body.title else None
    async with pool.tenant_connection(tid) as conn:
        async with conn.cursor(row_factory=dict_row) as cur:
            await cur.execute(
                "SELECT proposal_type, target_playbook_id, suggested_content, rationale, target_concept "
                "FROM feedback_proposals WHERE id = %s::uuid AND status = 'pending'", (proposal_id,))
            p = await cur.fetchone()
        if not p:
            raise HTTPException(status_code=404, detail="Sugerencia no encontrada o ya revisada.")
        note: str | None = None
        if p["proposal_type"] == "improve_playbook" and p["target_playbook_id"]:
            # H.6: no se puede sobrescribir un playbook protegido (semilla/core) desde una
            # sugerencia automática. La propuesta queda pendiente; se responde 409.
            async with conn.cursor(row_factory=dict_row) as cur2:
                await cur2.execute(
                    "SELECT title, summary, applies_when, content, protected FROM playbooks "
                    "WHERE id = %s", (p["target_playbook_id"],))
                target = await cur2.fetchone()
            if target and target["protected"]:
                raise HTTPException(
                    status_code=409,
                    detail="El playbook está protegido y no puede modificarse automáticamente.")
            new_content = edited_content if edited_content is not None else p["suggested_content"]
            # El diálogo "Editar antes de aplicar" muestra el título para TODA propuesta;
            # si el abogado lo cambia aquí también, honrarlo — antes se descartaba en
            # silencio (hallazgo del revisor: parte de la edición surtía efecto y parte no).
            new_title = edited_title[:200] if edited_title else None
            # B0: snapshot del estado ANTERIOR en playbook_versions antes de que Mia lo
            # sobreescriba (changed_by='mia') — complementa metadata.last_improvement.
            if target:
                await conn.execute(
                    "INSERT INTO playbook_versions (tenant_id, playbook_id, title, summary, "
                    "applies_when, content, changed_by, reason) VALUES "
                    "(%s::uuid, %s::uuid, %s, %s, %s, %s, 'mia', %s)",
                    (tid, p["target_playbook_id"], target["title"], target["summary"],
                     target["applies_when"], target["content"],
                     f"Mejora aplicada de una propuesta de Mia "
                     f"({_PROPOSAL_LABEL.get(p['proposal_type'], p['proposal_type'])})"))
            # CP-C3: trazabilidad de la mejora — el playbook registra QUÉ propuesta lo
            # modificó, cuándo, y guarda el CONTENIDO ANTERIOR (metadata.last_improvement):
            # aplicar una mejora deja de ser irreversible (hallazgo mayor del revisor).
            applied_at = datetime.now(timezone.utc).isoformat()
            try:
                await conn.execute(
                    "UPDATE playbooks SET content = %s, title = COALESCE(%s, title), "
                    "updated_at = now(), "
                    "metadata = jsonb_set(COALESCE(metadata, '{}'::jsonb), '{last_improvement}', "
                    "  jsonb_build_object('proposal_id', %s::text, 'applied_at', %s::text, "
                    "                     'previous_content', playbooks.content), true) "
                    "WHERE id = %s AND NOT protected",
                    (new_content, new_title, str(proposal_id), applied_at,
                     p["target_playbook_id"]))
            except psycopg.errors.UniqueViolation:
                raise HTTPException(status_code=409, detail="Ya existe otra guía con ese nombre.")
        elif p["proposal_type"] == "new_playbook":
            new_content = edited_content if edited_content is not None else p["suggested_content"]
            if edited_title:
                new_title = edited_title[:200]
            else:
                # nunca más el placeholder "Sugerencia {id}" — se deriva un título en
                # llano de las primeras palabras de la sugerencia (revisor B4).
                words = (p["suggested_content"] or "").strip().split()
                new_title = (" ".join(words[:8])[:200]
                            or f"Procedimiento sugerido {proposal_id[:8]}")
            new_summary = "Propuesta aplicada de Mia"
            new_applies = "(por afinar)"
            # Re-embed (hallazgo del revisor): sin esto el playbook "aprendido" nace con
            # embedding=NULL y el Curator jamás lo considera en su dedup/consolidación
            # semántica (find_candidates exige embedding IS NOT NULL en ambos lados).
            vec_new = embeddings.embed_texts([f"{new_summary}\n{new_applies}"])[0]
            await conn.execute(
                "INSERT INTO playbooks (tenant_id, title, summary, applies_when, content, "
                "embedding, metadata) VALUES (%s::uuid, %s, %s, %s, %s, %s, %s) "
                "ON CONFLICT (tenant_id, title) DO NOTHING",
                (tid, new_title, new_summary, new_applies, new_content, vec_new,
                 Json({"origin": "aprendida"})))
        # wiki_correction: el append al archivo del concepto es E/S de disco bloqueante
        # (el vault puede vivir en OneDrive) — se hace DESPUÉS de soltar esta conexión
        # pooled (revisor capa 2: sostenerla durante la escritura arriesgaba agotar el
        # pool del tenant bajo carga concurrente). Para los demás tipos, se marca
        # 'applied' aquí mismo, igual que antes.
        # 'soul_rule' se aplica FUERA de esta conexión, igual que wiki_correction: escribe
        # el archivo de identidad en disco y abre su propia transacción para versionar
        # (memory/soul_manager.py). Sostener esta conexión pooled mientras tanto arriesga
        # el pool del tenant; y si el tope rechaza el cambio, la propuesta debe quedarse
        # PENDIENTE — no marcarse aplicada aquí antes de saber si de verdad se aplicó.
        if p["proposal_type"] not in ("wiki_correction", "soul_rule"):
            await conn.execute(
                "UPDATE feedback_proposals SET status = 'applied', reviewed_at = now() "
                "WHERE id = %s::uuid", (proposal_id,))

    if p["proposal_type"] == "soul_rule":
        # La identidad es sagrada: ningún agente la escribe solo. Mia dejó la regla
        # PROPUESTA; este es el momento en que el abogado la aprueba y recién entonces se
        # escribe — con el estado anterior versionado y con tope de tamaño que RECHAZA
        # (nunca trunca: la identidad no se corta a la mitad en silencio).
        rule = edited_content if edited_content is not None else p["suggested_content"]
        try:
            result = await soul_manager.apply_soul_rule_proposal(tid, rule or "")
        except soul_manager.SoulTooLargeError as e:
            # El mensaje YA viene en llano desde el manager (§G). La propuesta sigue
            # pendiente: el abogado recorta su descripción y vuelve a aprobarla.
            raise HTTPException(status_code=409, detail=str(e))
        if not result["applied"]:
            note = "Esa preferencia ya estaba en la descripción de tu despacho."
        async with pool.tenant_connection(tid) as conn2:
            await conn2.execute(
                "UPDATE feedback_proposals SET status = 'applied', reviewed_at = now() "
                "WHERE id = %s::uuid", (proposal_id,))

    if p["proposal_type"] == "wiki_correction":
        # B4 (frente B): aprobar una corrección de la wiki la APLICA de verdad
        # (determinista, sin LLM): appendea la corrección del abogado al archivo del
        # concepto. Si el concepto ya no existe, se marca atendida con nota (fail-open,
        # sin 500) — la corrección igual quedó registrada como propuesta.
        concept = p.get("target_concept") or _concept_from_wiki_correction(p["rationale"])
        appended = False
        # Honrar la corrección EDITADA por el abogado (hallazgo del revisor): "Editar
        # antes de aplicar" se ofrece para toda propuesta, wiki_correction incluida; si se
        # ignora edited_content aquí, lo que queda escrito en el corpus del despacho es el
        # texto crudo de Mia, no lo que el abogado aprobó.
        wiki_content = edited_content if edited_content is not None else p["suggested_content"]
        if concept:
            try:
                appended = await WikiManager().append_correction(
                    tid, concept, wiki_content or "")
            except Exception:  # noqa: BLE001 — el archivo de wiki nunca tumba la aprobación
                logger.exception(
                    "no se pudo appendear la corrección al concepto '%s' (tenant=%s)",
                    concept, tid)
        if not appended:
            note = "La corrección quedó registrada; no se encontró el concepto para actualizar."
        async with pool.tenant_connection(tid) as conn2:
            await conn2.execute(
                "UPDATE feedback_proposals SET status = 'applied', reviewed_at = now() "
                "WHERE id = %s::uuid", (proposal_id,))
    return {"status": "applied", "note": note} if note else {"status": "applied"}


@router.post("/proposals/{proposal_id}/ignore")
async def ignore_proposal(proposal_id: str, request: Request):
    tid = _tenant(request)
    async with pool.tenant_connection(tid) as conn:
        res = await conn.execute(
            "UPDATE feedback_proposals SET status = 'rejected', reviewed_at = now() "
            "WHERE id = %s::uuid AND status = 'pending'", (proposal_id,))
        if res.rowcount == 0:
            raise HTTPException(status_code=404, detail="Sugerencia no encontrada o ya revisada.")
    return {"status": "ignored"}


# ── Second brain · wiki, sugerencias y conectores ─────────────────────────────
class ObsidianSyncBody(BaseModel):
    vault_path: str | None = None


@router.post("/connectors/obsidian/sync")
async def sync_obsidian(request: Request, body: ObsidianSyncBody):
    tid = _tenant(request)
    vault = body.vault_path
    if not vault:
        async with pool.tenant_connection(tid) as conn:
            row = await (await conn.execute(
                "SELECT config->>'obsidian_vault_path' FROM tenant_settings WHERE tenant_id=%s::uuid",
                (tid,),
            )).fetchone()
        vault = row[0] if row else None
    if not vault:
        raise HTTPException(status_code=400, detail="Falta la ruta del vault.")
    try:
        vault = str(config.resolve_obsidian_vault(vault))
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    start = time.perf_counter()
    stats = await ObsidianSync().sync(vault, tid)
    duration_ms = int((time.perf_counter() - start) * 1000)
    async with pool.tenant_connection(tid) as conn:
        await conn.execute(
            "INSERT INTO tenant_settings (tenant_id, config) VALUES (%s::uuid, %s) "
            "ON CONFLICT (tenant_id) DO UPDATE SET "
            "config = jsonb_set(tenant_settings.config, '{obsidian_vault_path}', to_jsonb(%s::text), true), "
            "updated_at = now()",
            (tid, Json({"obsidian_vault_path": vault}), vault),
        )
    return {"status": "ok", "chunks_indexed": stats.get("indexed", 0), "duration_ms": duration_ms}


class PineconeConfigBody(BaseModel):
    api_key: str
    index_name: str


@router.post("/connectors/pinecone/configure")
async def configure_pinecone(request: Request, body: PineconeConfigBody):
    tid = _tenant(request)
    # CP-S3 (tripwire): la api_key va en su campo designado; una credencial pegada
    # por error en el NOMBRE del índice se rechaza antes de tocar la DB.
    try:
        assert_no_stray_secret({"index_name": body.index_name})
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    connector = PineconeConnector(body.api_key, body.index_name, "tenant")
    vectors_count = 0
    status = "active"
    try:
        stats = await connector.describe_index()
        total = stats.get("total_vector_count") if isinstance(stats, dict) else None
        vectors_count = int(total or 0)
    except Exception as exc:
        status = "inactive"
        stats = {"error": str(exc)}
    encrypted_api_key = encrypt_secret(
        body.api_key, tenant_id=tid, purpose="pinecone:api_key"
    )
    async with pool.tenant_connection(tid) as conn:
        await conn.execute(
            "INSERT INTO tenant_settings (tenant_id, config) VALUES (%s::uuid, %s) "
            "ON CONFLICT (tenant_id) DO UPDATE SET "
            "config = jsonb_set(tenant_settings.config, '{pinecone}', %s::jsonb, true), updated_at = now()",
            (tid, Json({"pinecone": {"api_key": encrypted_api_key,
                                     "index_name": body.index_name, "status": status}}),
             Json({"api_key": encrypted_api_key, "index_name": body.index_name,
                   "status": status, "stats": stats})),
        )
    return {"status": status, "vectors_count": vectors_count}


@router.get("/wiki/concepts")
async def wiki_concepts(request: Request):
    tid = _tenant(request)
    return await WikiManager().list_concepts(tid)


@router.get("/wiki/concepts/{concept_name}")
async def wiki_concept(concept_name: str, request: Request):
    tid = _tenant(request)
    content = await WikiManager().get_concept(tid, concept_name)
    if content is None:
        raise HTTPException(status_code=404, detail="Concepto no encontrado")
    return {"concept": concept_name, "markdown": content}


class WikiFeedbackBody(BaseModel):
    correction: str


@router.post("/wiki/concepts/{concept_name}/feedback", status_code=201)
async def wiki_feedback(concept_name: str, request: Request, body: WikiFeedbackBody):
    tid = _tenant(request)
    async with pool.tenant_connection(tid) as conn:
        await conn.execute(
            "INSERT INTO feedback_proposals "
            "  (tenant_id, proposal_type, suggested_content, rationale, target_concept) "
            "VALUES (%s::uuid, 'wiki_correction', %s, %s, %s)",
            (tid, body.correction, f"{_WIKI_CORRECTION_RATIONALE_PREFIX}{concept_name}", concept_name),
        )
    return {"status": "pending"}


@router.get("/dreams/report")
async def dreams_report(request: Request):
    tid = _tenant(request)
    async with pool.tenant_connection(tid) as conn:
        row = await (await conn.execute(
            "SELECT suggested_content, created_at FROM feedback_proposals "
            "WHERE proposal_type='weekly_report' ORDER BY created_at DESC LIMIT 1"
        )).fetchone()
    return {"report": row[0], "created_at": row[1]} if row else {"report": None, "created_at": None}


# ── CP-V2 · auto-diagnóstico prescriptivo ─────────────────────────────────────
@router.get("/dreams/prescriptions")
async def dreams_prescriptions(request: Request):
    """Recomendaciones vigentes del diagnóstico (las que el abogado no ha decidido),
    ordenadas por impacto. Cada una trae título, receta, evidencia real y puntaje;
    lo aceptado/descartado no aparece (memoria de recomendaciones, CP-V2)."""
    tid = _tenant(request)
    # `surfaced=true` = las del top del diagnóstico. Las filas con señal viva que
    # salieron del top por ranking/diversidad se conservan (edad real del problema)
    # pero no se muestran (capa 2 de CP-V2, H2). Filas viejas sin la marca cuentan
    # como surfaceadas (compat).
    async with pool.tenant_connection(tid) as conn:
        rows = await (await conn.execute(
            "SELECT prescription_id, status, payload, first_seen_at, last_seen_at "
            "FROM dream_prescriptions WHERE status IN ('new', 'recurring') "
            "AND coalesce((payload->>'surfaced')::boolean, true) "
            "ORDER BY coalesce((payload->>'score')::numeric, 0) DESC"
        )).fetchall()
    now = datetime.now(timezone.utc)
    out = []
    for pid, status, payload, first_seen, last_seen in rows:
        item = dict(payload or {})
        item["id"] = pid
        item["status"] = status
        item["age_days"] = max(0, (now - first_seen).days) if first_seen else 0
        item["last_seen_at"] = last_seen
        out.append(item)
    return {"prescriptions": out}


class PrescriptionDecision(BaseModel):
    action: str  # 'accept' | 'dismiss'


@router.post("/dreams/prescriptions/{prescription_id}/decision")
async def decide_prescription(prescription_id: str, request: Request,
                              body: PrescriptionDecision):
    """El abogado acepta o descarta una recomendación. No se vuelve a mostrar
    salvo que la señal reaparezca pasados 30 días."""
    tid = _tenant(request)
    action = body.action.strip().lower()
    if action not in ("accept", "dismiss"):
        raise HTTPException(status_code=422,
                            detail="La decisión debe ser aceptar o descartar.")
    status = "accepted" if action == "accept" else "dismissed"
    async with pool.tenant_connection(tid) as conn:
        row = await (await conn.execute(
            "UPDATE dream_prescriptions SET status = %s, decided_at = now() "
            "WHERE prescription_id = %s AND status IN ('new', 'recurring') "
            "RETURNING prescription_id",
            (status, prescription_id),
        )).fetchone()
    if not row:
        raise HTTPException(status_code=404,
                            detail="Esa recomendación no existe o ya fue decidida.")
    return {"id": prescription_id, "status": status}


@router.get("/skills/ranked")
async def skills_ranked(request: Request):
    tid = _tenant(request)
    return await GEPALoop().grade_all_skills(tid)


# ── Jurisdicciones (Fase 0.C · packs instalados) ─────────────────────────────
@router.get("/jurisdictions")
async def jurisdictions(request: Request):
    """Opciones de jurisdicción para el onboarding: packs instalados + modo genérico.

    Las opciones NO son hardcodeadas (Decisión #22): se derivan de `packs/` disponibles.
    El frontend las usa para que el abogado seleccione su(s) jurisdicción(es). Un país sin
    pack opera en 'Otra / modo genérico' (cuña de venta: vender hoy, pack como mejora)."""
    _tenant(request)
    options = [{"code": c, "name": load_pack(c).name, "verified": load_pack(c).verified}
               for c in list_packs()]
    options.append({"code": GENERIC_CODE, "name": "Otra / modo genérico", "verified": False})
    return {"jurisdictions": options}


# ── Onboarding · entrevista del SOUL.md (Módulo 5) ───────────────────────────
class OnboardingComplete(BaseModel):
    responses: dict
    jurisdictions: list[str] | None = None


class OnboardingDraft(BaseModel):
    """Borrador parcial de la entrevista (Fase 2): lo que el abogado lleva
    contestado + en qué pregunta va. Se guarda en tenant_settings para que
    recargar o cerrar el navegador NO pierda el progreso. `qid` es el id de la
    pregunta actual: al reanudar se busca POR IDENTIDAD (el índice solo es
    respaldo — la lista de pasos puede cambiar de largo entre sesiones, p.ej.
    si el paso de jurisdicción no cargó, y un índice posicional mostraría otra
    pregunta)."""
    responses: dict
    idx: int = 0
    qid: str | None = None


# Tope del borrador serializado: la entrevista real pesa <5 KB; esto solo
# frena un abuso accidental (respuestas pegadas gigantes) sin molestar a nadie.
MAX_ONBOARDING_DRAFT_CHARS = 40_000


async def _save_onboarding_draft(tid: str, draft: dict | None) -> None:
    """Escribe (o limpia, con None) el objeto '{onboarding}' completo del config.
    Se fija el objeto entero — lección del tope de gasto (CP-E1): jsonb_set con
    create_missing NO crea objetos intermedios y descartaría el dato en silencio."""
    payload = {"draft": draft} if draft is not None else {}
    async with pool.tenant_connection(tid) as conn:
        await conn.execute(
            "INSERT INTO tenant_settings (tenant_id, config) VALUES (%s::uuid, %s) "
            "ON CONFLICT (tenant_id) DO UPDATE SET "
            "config = jsonb_set(tenant_settings.config, '{onboarding}', %s::jsonb, true), "
            "updated_at = now()",
            (tid, Json({"onboarding": payload}), Json(payload)),
        )


async def _load_onboarding_draft(tid: str) -> dict | None:
    async with pool.tenant_connection(tid) as conn:
        row = await (await conn.execute(
            "SELECT config->'onboarding'->'draft' FROM tenant_settings "
            "WHERE tenant_id = %s::uuid", (tid,))).fetchone()
    draft = row[0] if row else None
    return draft if isinstance(draft, dict) and isinstance(draft.get("responses"), dict) else None


@router.get("/onboarding/questions")
async def onboarding_questions(request: Request):
    """Las 13 preguntas de la entrevista (id/block/field/question/example)."""
    _tenant(request)
    return await SoulInterview().get_questions()


@router.post("/onboarding/draft")
async def onboarding_save_draft(request: Request, body: OnboardingDraft):
    """Guarda el avance parcial de la entrevista (autosave del wizard, Fase 2).

    El frontend lo llama al avanzar de pregunta; si falla, el wizard sigue
    funcionando (el autosave es ayuda, no candado)."""
    tid = _tenant(request)
    if len(json.dumps(body.responses, ensure_ascii=False)) > MAX_ONBOARDING_DRAFT_CHARS:
        raise HTTPException(status_code=413, detail="Las respuestas son demasiado largas para guardarlas.")
    idx = max(0, min(int(body.idx), 200))
    qid = (str(body.qid)[:40] if body.qid else None)
    await _save_onboarding_draft(tid, {"responses": body.responses, "idx": idx, "qid": qid})
    return {"ok": True}


@router.post("/onboarding/complete")
async def onboarding_complete(request: Request, body: OnboardingComplete):
    """Genera el SOUL.md del despacho a partir de las respuestas y lo guarda.

    Generación DETERMINISTA (sin LLM, rediseño 2026-07-06): se construye omitiendo lo
    vacío, sin invención ni placeholders. Devuelve `summary` (resumen en lenguaje llano
    que muestra el frontend) además del `soul_content` técnico. El abogado puede refinar
    su perfil luego desde 'Mi despacho'.
    """
    tid = _tenant(request)
    # Defensa en profundidad: las claves reservadas del wizard (prefijo '_', como
    # '_jurisdicciones') jamás forman parte del perfil — el frontend ya las extrae,
    # pero una llamada directa al API no debe poder colarlas en responses.json.
    body.responses = {k: v for k, v in body.responses.items() if not str(k).startswith("_")}
    # Persistir la(s) jurisdicción(es) elegidas (Fase 0.C). Es la fuente del routing
    # jurisdiccional del SAT-Graph, calendario, chunker y PII (resolve_jurisdictions).
    if body.jurisdictions:
        codes = [str(c).strip().lower() for c in body.jurisdictions if str(c).strip()]
        if codes:
            async with pool.tenant_connection(tid) as conn:
                await conn.execute(
                    "INSERT INTO tenant_settings (tenant_id, config) VALUES (%s::uuid, %s) "
                    "ON CONFLICT (tenant_id) DO UPDATE SET "
                    "config = jsonb_set(tenant_settings.config, '{jurisdictions}', %s::jsonb, true), "
                    "updated_at = now()",
                    (tid, Json({"jurisdictions": codes}), Json(codes)),
                )
    interview = SoulInterview()
    # Generación DETERMINISTA (sin LLM): construye el SOUL.md omitiendo lo vacío, sin
    # placeholders ni invención. `summary` es el RESUMEN en lenguaje llano que muestra
    # el frontend ("Así entendí a tu despacho"); el SOUL.md técnico queda por debajo.
    content = await interview.run_interview(tid, body.responses)
    summary = interview.summary(body.responses)
    # Entrevista terminada → el borrador parcial ya no aplica. Fail-open: si la
    # limpieza falla, el status seguirá diciendo completed=true y el frontend
    # ignora el borrador cuando ya está completo.
    try:
        await _save_onboarding_draft(tid, None)
    except Exception:
        logger.exception("no se pudo limpiar el borrador de onboarding (tenant=%s)", tid)
    # puede_importar_guias: el frontend puede ofrecer el paso opcional de importar
    # las guías de trabajo del despacho (POST /api/playbooks/import — Riesgo #20).
    return {"soul_content": content, "summary": summary, "path": f"soul_{tid}.md",
            "generated_by": "deterministic", "puede_importar_guias": True}


@router.get("/onboarding/status")
async def onboarding_status(request: Request):
    """¿El despacho ya tiene SOUL.md? {completed, last_updated, responses}.

    `responses` trae las respuestas guardadas (o {}) para que 'Revisar mi perfil'
    precargue lo que el abogado contestó la última vez. `draft` (Fase 2) trae el
    avance parcial del wizard si el abogado lo dejó a medias (o null) — fail-open:
    si no se puede leer, el wizard simplemente arranca de cero.
    """
    tid = _tenant(request)
    try:
        draft = await _load_onboarding_draft(tid)
    except Exception:
        logger.exception("no se pudo leer el borrador de onboarding (tenant=%s)", tid)
        draft = None
    return {**soul_status(tid), "responses": load_responses(tid), "draft": draft}


# ── Pantalla 5 · dashboard ───────────────────────────────────────────────────
@router.get("/dashboard/stats")
async def dashboard_stats(request: Request):
    tid = _tenant(request)
    async with pool.tenant_connection(tid) as conn:
        async def scalar(sql):
            return (await (await conn.execute(sql)).fetchone())[0]
        matters_active = await scalar("SELECT count(*) FROM matters WHERE kind='asunto' AND status='active'")
        documents_indexed = await scalar("SELECT count(*) FROM documents")
        playbooks_active = await scalar("SELECT count(*) FROM playbooks WHERE status='active'")
        playbooks_archived = await scalar("SELECT count(*) FROM playbooks WHERE status='archived'")
        proposals_pending = await scalar("SELECT count(*) FROM feedback_proposals WHERE status='pending'")
        knowledge_items = await scalar("SELECT count(*) FROM knowledge_chunks")
        last_sync = (await (await conn.execute(
            "SELECT max(last_indexed) FROM obsidian_file_hashes")).fetchone())[0]
        settings = (await (await conn.execute(
            "SELECT config FROM tenant_settings WHERE tenant_id=%s::uuid", (tid,))).fetchone())
        latest_report = (await (await conn.execute(
            "SELECT created_at FROM feedback_proposals WHERE proposal_type='weekly_report' "
            "ORDER BY created_at DESC LIMIT 1")).fetchone())
        config_json = settings[0] if settings else {}
        # CP-V1: costo REAL del mes desde turn_usage (tokens reales × precio por
        # modelo, capturados en cada llamada al LLM por metrics/usage). Frontera de
        # mes en UTC (misma que el filtro de trazas). Si la migración 021 no está
        # aplicada, DEGRADA al estimado legacy en vez de tumbar el panel entero.
        real_cost_usd = 0.0
        usage_calls_month = 0
        cache_read_month = 0
        prompt_tokens_month = 0
        try:
            usage_row = await (await conn.execute(
                "SELECT coalesce(sum(cost_usd), 0), count(*), "
                "       coalesce(sum(cache_read_tokens), 0), coalesce(sum(prompt_tokens), 0) "
                "FROM turn_usage WHERE created_at >= "
                "(date_trunc('month', now() AT TIME ZONE 'utc') AT TIME ZONE 'utc')"
            )).fetchone()
            real_cost_usd = float(usage_row[0])
            usage_calls_month = int(usage_row[1])
            cache_read_month = int(usage_row[2])
            prompt_tokens_month = int(usage_row[3])
        except Exception:  # noqa: BLE001 — sin turn_usage el panel sigue funcionando
            logger.warning("turn_usage no disponible (¿falta init_turn_usage?); "
                           "el costo cae al estimado legacy", exc_info=True)
        # OJO: si esta consulta falla, la TRANSACCIÓN queda abortada — no agregar
        # más consultas después de este punto dentro del mismo `with` (fallarían
        # con InFailedSqlTransaction). Debe seguir siendo la última del bloque.

    # CP-V1 · valor entregado del MES: horas ahorradas (estimado configurable por
    # despacho) × tarifa − costo real de IA. La clasificación de trazas (borrador
    # sustancial vs consulta; eventos técnicos y rechazos excluidos; solo el mes)
    # vive en metrics/value.summarize_traces — función pura cubierta por el gate.
    # LIMITACIÓN DECLARADA: el costo no incluye embeddings (voyage no pasa por
    # call_llm) — subreporta el costo, nunca infla el valor.
    month_prefix = datetime.now(timezone.utc).strftime("%Y-%m")
    from ...metrics.value import summarize_traces
    tsum = summarize_traces(TraceCapture().read(tid), month_prefix)
    drafts_month, turns_month = tsum["drafts"], tsum["turns"]
    # Fallback legacy: si turn_usage aún no registró nada (instalación recién
    # migrada), se estima con tarifa fija SOLO sobre los tokens de ESTE mes.
    cost_month_usd = round(real_cost_usd, 2) if usage_calls_month else round(
        tsum["legacy_tokens_month"] * _USD_PER_TOKEN, 2)

    from .value import value_settings_for  # import local: evita ciclos entre routers
    vcfg = await value_settings_for(tid)
    hours_saved = round(
        (drafts_month * vcfg["draft_minutes"] + turns_month * vcfg["turn_minutes"]) / 60.0, 1)
    gross_usd = round(hours_saved * vcfg["hourly_rate_usd"], 2)
    net_usd = round(gross_usd - cost_month_usd, 2)

    # Caché de prompt: mide de verdad el ahorro que la arquitectura AFIRMA (~75% por
    # prefix caching). hit-rate = tokens de entrada servidos desde caché / tokens de
    # entrada totales del mes. None (no 0%) mientras no haya señal: cli-* y mia-local
    # no reportan caché, así que solo el path API/OpenRouter la alimenta — se declara.
    cache_hit_rate = (round(cache_read_month / prompt_tokens_month, 4)
                      if prompt_tokens_month else None)

    # B3 (frente B): el panel muestra el reloj REAL de los jobs (next_run/last_run). Hay que
    # leer el scheduler VIVO (el que corre en el lifespan, api/main.py) — no construir uno
    # nuevo, que nace con next_run/last_run en None. Fallback fail-open a uno recién armado
    # (p. ej. en tests sin lifespan): el panel sigue respondiendo aunque sin horas reales.
    live = getattr(request.app.state, "scheduler", None)
    raw_jobs = live.list_jobs() if live is not None else build_scheduler().list_jobs()
    jobs = [{"label": _JOB_LABEL.get(j["name"], j["name"]),
             "next_run": j["next_run"], "last_run": j["last_run"]}
            for j in raw_jobs]
    dreams_next = next((j["next_run"] for j in raw_jobs if j["name"] == "dreams_weekly"), None)
    concepts_count = len(await WikiManager().list_concepts(tid))
    dreams_metrics = ((config_json or {}).get("dreams") or {}).get("last_metrics") or {}
    pinecone_cfg = ((config_json or {}).get("pinecone") or {})

    return {
        "matters_active": matters_active,
        "documents_indexed": documents_indexed,
        "playbooks_active": playbooks_active,
        "playbooks_archived": playbooks_archived,
        "proposals_pending": proposals_pending,
        "knowledge_items": knowledge_items,
        "scheduler_jobs": jobs,
        "cost_month_usd": cost_month_usd,
        # Ahorro por caché de prompt, MEDIDO (no afirmado). rate=None → aún sin señal.
        "cache": {
            "hit_rate": cache_hit_rate,
            "read_tokens_month": cache_read_month,
            "prompt_tokens_month": prompt_tokens_month,
        },
        # CP-V1 · tarjeta "Valor entregado este mes" (todo en llano, §G).
        "value": {
            "hours_saved": hours_saved,
            "hourly_rate_usd": vcfg["hourly_rate_usd"],
            "gross_usd": gross_usd,
            "cost_usd": cost_month_usd,
            "net_usd": net_usd,
            "drafts_approved": drafts_month,
            "consultations": turns_month,
            "draft_minutes": vcfg["draft_minutes"],
            "turn_minutes": vcfg["turn_minutes"],
            "is_default_config": vcfg["is_default"],
        },
        "connectors": {
            "knowledge_base": {"active": last_sync is not None, "last_sync": last_sync, "chunks": knowledge_items},
            # CP-S2: el estado sale SOLO de la configuración del tenant (RLS) —
            # antes un PINECONE_API_KEY global del entorno marcaba "activo" para
            # todos los despachos (clave de la instalación, no del despacho).
            # Módulo A: ya hay tráfico real (sync + retrieval lo usan como store
            # secundario opt-in); este indicador sigue leyendo solo el status
            # guardado — no hace ninguna llamada de red aquí.
            "external_store": {"active": bool(pinecone_cfg.get("status") == "active"),
                               "vectors_count": (((pinecone_cfg.get("stats") or {}).get("total_vector_count")) or 0)},
            "models": _available_models(),
        },
        "second_brain": {
            "weekly_approval_rate": dreams_metrics.get("approval_rate", 0),
            "concepts_count": concepts_count,
            "skills_active": playbooks_active,
            "skills_archived": playbooks_archived,
            "next_consolidation": dreams_next,
            "last_report": latest_report[0] if latest_report else None,
        },
    }


# ── Sala de estrategia (warroom) · panel + streaming SSE + persistencia ───────
# La "Sala de estrategia" (nombre interno: warroom) reúne un panel de counsel con posturas
# OPUESTAS que debaten el asunto citando el expediente; un moderador sintetiza un dictamen.
# Solo ASUNTOS. §G: al abogado NUNCA se le muestra "agente", "war room", "LLM" ni "panel"
# como jerga — el copy visible vive en el frontend; aquí los textos SSE ya vienen en llano
# desde el motor (agents/warroom.py).
#
# El motor NO toca DB (persiste el resultado en el estado en memoria). Esta capa cablea el
# retrieval del expediente (intake_node, el MISMO RRF/RLS del grafo), corre el motor y
# persiste el último dictamen por asunto en `warroom_results` (migración 033, RLS fail-closed).


async def save_warroom_result(tenant_id: str, matter_id: str, result: dict) -> None:
    """Guarda (upsert) el último dictamen de la Sala del asunto bajo RLS. Una fila por
    asunto: la nueva convocatoria PISA la anterior (clave única tenant_id+matter_id)."""
    async with pool.tenant_connection(tenant_id) as conn:
        await conn.execute(
            "INSERT INTO warroom_results (tenant_id, matter_id, result) "
            "VALUES (%s::uuid, %s::uuid, %s) "
            "ON CONFLICT (tenant_id, matter_id) DO UPDATE SET "
            "  result = EXCLUDED.result, created_at = now()",
            (tenant_id, matter_id, Json(result)))


async def get_warroom_result(tenant_id: str, matter_id: str) -> dict | None:
    """El último dictamen (WarRoomResult) del asunto, o None si nunca se convocó (RLS)."""
    async with pool.tenant_connection(tenant_id) as conn:
        row = await (await conn.execute(
            "SELECT result FROM warroom_results WHERE matter_id = %s::uuid", (matter_id,))).fetchone()
    return row[0] if row and row[0] else None


async def _assert_warroom_matter(tid: str, matter_id: str) -> None:
    """La Sala de estrategia solo existe en un ASUNTO (no en un proyecto)."""
    if await _matter_kind(tid, matter_id) != "asunto":
        raise HTTPException(status_code=422,
                            detail="La sala de estrategia solo existe dentro de un asunto.")


async def _warroom_state(tenant_id: str, matter_id: str, question: str) -> tuple[dict, MatterGraphBuilder]:
    """Arma el `state` del asunto con el retrieval del expediente (mismo intake_node/RRF/RLS
    del grafo) para correr la Sala. Devuelve (state, builder). El área del especialista se
    deriva SIN LLM del state (metadata del asunto → default 'derecho procesal' si hay
    expediente), como en el grafo."""
    profile_snapshot = await load_profile_snapshot(tenant_id)
    state = initial_state(tenant_id, matter_id, question, profile_snapshot=profile_snapshot)
    builder = MatterGraphBuilder()
    intake = await builder.intake_node(state)
    state["documents"] = intake.get("documents") or []
    state["knowledge"] = intake.get("knowledge") or []
    state["metadata"] = intake.get("metadata") or {}
    return state, builder


async def _available_personas(tenant_id: str) -> list:
    """Agentes jurídicos del despacho para AJUSTAR el panel (fail-open: [] si algo falla —
    la propuesta base es sintética y no depende de que el despacho haya creado personas)."""
    try:
        return await persona_service.list_personas(tenant_id)
    except Exception:  # noqa: BLE001 — §G: listar agentes jamás tumba la Sala
        logger.warning("warroom: no se pudieron listar los agentes del despacho (tenant=%s)",
                       tenant_id, exc_info=True)
        return []


@router.get("/matters/{matter_id}/warroom/panel")
async def warroom_panel(matter_id: str, request: Request):
    """PanelProposal: los 3-4 counsel que MIA propone (posturas sintéticas) + los Agentes
    del despacho disponibles para ajustar. El área del especialista se deriva sin LLM (state
    mínimo: si el asunto tiene expediente, se incluye el especialista con el área por defecto)."""
    tid = _tenant(request)
    await assert_owns_matter(tid, matter_id)
    await _assert_warroom_matter(tid, matter_id)
    # State mínimo para propose_panel: basta saber si el asunto YA tiene expediente indexado
    # (para incluir el especialista). No se corre retrieval ni LLM — es una lectura barata.
    has_docs = await retrieval.matter_has_chunks(tid, matter_id)
    state = {"documents": [{"placeholder": True}] if has_docs else [], "metadata": {}}
    personas = await _available_personas(tid)
    proposed = [p.to_public() for p in propose_panel(state, personas)]
    available = [{"persona_id": p.id, "name": p.name, "title": p.title,
                  "focus_areas": list(p.focus_areas)} for p in personas if p.enabled]
    return {"proposed": proposed, "available": available}


class WarroomPanelSpec(BaseModel):
    """Una selección del abogado en el modal. `persona_id` None = counsel sintético de la
    postura; si no es None, un Agente real del despacho ocupa esa silla."""
    persona_id: str | None = None
    stance: str = "defensor"


class WarroomStartBody(BaseModel):
    """Body de POST /warroom: el panel ajustado por el abogado + una pregunta opcional. El
    frontend manda el Panelist completo; los campos extra (name/stance_label/focus) se ignoran."""
    panel: list[WarroomPanelSpec] = []
    question: str | None = None


# Tope defensivo de counsel por sesión (el motor degrada solo por presupuesto; esto acota el
# abuso desde el cliente antes de correr N llamadas LLM en paralelo).
_WARROOM_MAX_PANEL = 6
_WARROOM_MIN_PANEL = 2

# Consulta por defecto cuando el abogado no escribe nada puntual en el modal: da al retrieval
# del expediente y a los panelistas un foco general (mismo espíritu que el default del motor).
_WARROOM_DEFAULT_QUESTION = (
    "Analiza integralmente el expediente para contrastar posturas y definir la estrategia.")


@router.post("/matters/{matter_id}/warroom")
async def warroom_start(matter_id: str, request: Request, body: WarroomStartBody):
    """Handshake: valida el panel y devuelve la URL del SSE (calca POST /chat). El panel
    (solo persona_id+stance) y la pregunta viajan en el query del stream."""
    tid = _tenant(request)
    await assert_owns_matter(tid, matter_id)
    await _assert_warroom_matter(tid, matter_id)
    if len(body.panel) < _WARROOM_MIN_PANEL:
        raise HTTPException(status_code=422,
                            detail="Suma al menos dos counsel para convocar la sala de estrategia.")
    if len(body.panel) > _WARROOM_MAX_PANEL:
        raise HTTPException(status_code=422,
                            detail=f"La sala admite hasta {_WARROOM_MAX_PANEL} counsel. Quita alguno.")
    specs = [{"persona_id": p.persona_id, "stance": p.stance} for p in body.panel]
    panel_q = quote(json.dumps(specs, ensure_ascii=False))
    question_q = quote(body.question or "")
    return {"stream_url":
            f"/api/matters/{matter_id}/warroom/stream?panel={panel_q}&question={question_q}"}


def _warroom_sse(event: str, payload: dict) -> dict:
    """Traduce un evento del motor al contrato SSE §G. 'thinking'/'error' llevan su texto en
    `message`; 'counsel_turn'/'conclusions_ready' llevan su payload estructurado tal cual."""
    if event in ("thinking", "error"):
        return sse(event, str(payload.get("message") or ""))
    return sse(event, "", **payload)


@router.get("/matters/{matter_id}/warroom/stream")
async def warroom_stream(matter_id: str, request: Request,
                         panel: str = Query(""), question: str = Query("")):
    """SSE de la Sala (calca stream_matter): arma el state con el retrieval del expediente,
    resuelve el panel, corre el motor y reenvía sus eventos ('thinking', 'counsel_turn',
    'conclusions_ready'). WarRoomError → evento 'error' en llano. Al terminar, persiste el
    dictamen. Respeta el tope de gasto (402 ANTES de abrir el stream) y corta al desconectarse."""
    tenant_id = _tenant(request)
    await assert_owns_matter(tenant_id, matter_id)
    await _assert_warroom_matter(tenant_id, matter_id)

    # CP-E1: tope de gasto del despacho ANTES de abrir el SSE (el turno es GET → el bloqueo
    # debe ser HTTP, no un evento). Fail-open: un fallo de lectura permite la sesión.
    try:
        await policy_budget.enforce_budget(tenant_id)
    except policy_budget.BudgetExceeded as e:
        raise HTTPException(status_code=402, detail=str(e))

    await audit.record(
        "warroom_session", tenant_id=tenant_id,
        user_email=getattr(request.state, "email", None),
        entity_type="matter", entity_id=matter_id,
    )

    # Panel seleccionado por el abogado (persona_id+stance). Un query malformado cae a []
    # → build_panel propone el panel completo (fail-safe, nunca 500).
    try:
        specs = json.loads(panel) if panel else []
        if not isinstance(specs, list):
            specs = []
    except (ValueError, TypeError):
        specs = []

    # MENOR 4 · el POST valida 2..6, pero el stream (GET) es invocable directo → re-valida
    # aquí el mismo clamp. Por encima del máximo se trunca (guarda anti-costo antes de abrir N
    # llamadas LLM); por debajo del mínimo cae a [] → build_panel propone el panel completo
    # (fail-safe, nunca corre con menos de dos counsel).
    if len(specs) > _WARROOM_MAX_PANEL:
        specs = specs[:_WARROOM_MAX_PANEL]
    if len(specs) < _WARROOM_MIN_PANEL:
        specs = []

    async def gen():
        yield sse("thinking", "Mia está reuniendo la sala de estrategia…")
        loop = asyncio.get_running_loop()
        queue: asyncio.Queue = asyncio.Queue()
        DONE = object()

        async def emit(event: str, payload: dict) -> None:
            await queue.put((event, payload))

        async def runner():
            try:
                effective_q = (question or "").strip() or _WARROOM_DEFAULT_QUESTION
                state, builder = await _warroom_state(tenant_id, matter_id, effective_q)
                personas = await _available_personas(tenant_id)
                panel_objs = build_panel(state, specs, personas)
                await run_warroom(builder, state, panel_objs, question=effective_q, emit=emit)
                result = state.get("warroom_result")
                if result:
                    await save_warroom_result(tenant_id, matter_id, result)
            except WarRoomError as e:
                # Mensaje del motor YA en llano (§G).
                await queue.put(("error", {"message": str(e)}))
            except Exception:  # noqa: BLE001 — nada técnico llega al abogado (§G)
                logger.exception("warroom: la sesión falló (tenant=%s matter=%s)",
                                 tenant_id, matter_id)
                await queue.put(("error", {"message":
                    "Mia no pudo completar la sala de estrategia. Intenta de nuevo."}))
            finally:
                await queue.put(DONE)

        task = loop.create_task(runner())
        try:
            while True:
                # Kill-on-disconnect (como _stream_turn_events): sin consumidor no se sigue
                # gastando minutos de razonamiento ni el costo del modelo.
                if await request.is_disconnected():
                    logger.info("warroom: navegador desconectado; se corta la sesión "
                                "(tenant=%s matter=%s)", tenant_id, matter_id)
                    task.cancel()
                    break
                try:
                    item = await asyncio.wait_for(queue.get(), timeout=1.0)
                except asyncio.TimeoutError:
                    continue
                if item is DONE:
                    break
                event, payload = item
                yield _warroom_sse(event, payload)
        finally:
            if not task.done():
                task.cancel()

    return EventSourceResponse(gen(), ping=SSE_PING_SECONDS)


@router.get("/matters/{matter_id}/warroom")
async def warroom_get(matter_id: str, request: Request):
    """El último dictamen de la Sala del asunto, o `{result: null}` si nunca se convocó.
    Encaja con parseWarroomGet del frontend."""
    tid = _tenant(request)
    await assert_owns_matter(tid, matter_id)
    await _assert_warroom_matter(tid, matter_id)
    return {"result": await get_warroom_result(tid, matter_id)}


def _warroom_to_markdown(result: dict) -> str:
    """Formatea el dictamen (conclusiones + debate) a markdown ligero para draft_to_docx
    (mismo markdown que emiten los nodos del grafo: #/##, **negrilla**, - viñetas)."""
    conc = (result or {}).get("conclusions") or {}
    lines: list[str] = ["# Dictamen de la sala de estrategia", ""]
    tesis = conc.get("tesis_viable")
    if tesis:
        lines += [f"**Tesis viable:** {tesis}", ""]

    def _section(title: str, items) -> None:
        vals = [str(x).strip() for x in (items or []) if str(x).strip()]
        if not vals:
            return
        lines.append(f"## {title}")
        lines.extend(f"- {v}" for v in vals)
        lines.append("")

    _section("Fortalezas", conc.get("fortalezas"))
    _section("Riesgos", conc.get("riesgos"))
    _section("Puntos ciegos", conc.get("puntos_ciegos"))
    if (conc.get("estrategia") or "").strip():
        lines += ["## Estrategia", conc["estrategia"].strip(), ""]
    if (conc.get("proximo_paso") or "").strip():
        lines += ["## Próximo paso", conc["proximo_paso"].strip(), ""]

    debate = (result or {}).get("debate") or []
    if debate:
        lines += ["## Debate del panel", ""]
        for t in debate:
            if not isinstance(t, dict):
                continue
            header = f"### Ronda {t.get('round', 1)} — {t.get('stance_label') or ''} ({t.get('name') or ''})"
            lines += [header, str(t.get("text") or "").strip(), ""]
    return "\n".join(lines)


@router.get("/matters/{matter_id}/warroom.docx")
async def download_warroom_docx(matter_id: str, request: Request):
    """El dictamen de la Sala como .docx (calca download_draft_docx: markdown → draft_to_docx,
    Content-Disposition ASCII-safe + filename* UTF-8). 404 si el asunto aún no tiene dictamen."""
    tid = _tenant(request)
    await assert_owns_matter(tid, matter_id)
    await _assert_warroom_matter(tid, matter_id)
    result = await get_warroom_result(tid, matter_id)
    if not result:
        raise HTTPException(status_code=404,
                            detail="La sala de estrategia aún no tiene un dictamen.")
    async with pool.tenant_connection(tid) as conn:
        row = await (await conn.execute(
            "SELECT title FROM matters WHERE id = %s::uuid", (matter_id,))).fetchone()
    base = (row[0] if row and row[0] else "Dictamen")
    title = f"Dictamen — {base}"
    data = draft_to_docx(_warroom_to_markdown(result), title=title, author="Mia")
    # filename ASCII-safe + variante UTF-8 (RFC 5987) para títulos con tildes (mismo bugfix
    # que download_draft_docx: el header filename= sin * no tolera un carácter no-ASCII crudo).
    safe = "".join(c if c.isascii() and (c.isalnum() or c in "-_ ") else ""
                   for c in title).strip() or "dictamen"
    headers = {
        "Content-Disposition":
            f'attachment; filename="{safe[:60]}.docx"; '
            f"filename*=UTF-8''{quote(title[:60], safe='')}.docx"
    }
    return Response(
        content=data,
        media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        headers=headers,
    )


@router.post("/matters/{matter_id}/warroom/to-draft")
async def warroom_to_draft(matter_id: str, request: Request):
    """Convierte el dictamen en un borrador: siembra un mensaje con la estrategia acordada y
    arranca el GRAFO DE ASUNTO normal (build_matter_graph vía /stream) para que el borrador
    pase por el gate de citas y el flujo HITL habitual. Devuelve `{stream_url}` (calca /chat)."""
    tid = _tenant(request)
    await assert_owns_matter(tid, matter_id)
    await _assert_warroom_matter(tid, matter_id)
    result = await get_warroom_result(tid, matter_id)
    if not result:
        raise HTTPException(status_code=404,
                            detail="La sala de estrategia aún no tiene un dictamen que convertir.")
    conc = (result.get("conclusions") or {})
    estrategia = (conc.get("estrategia") or "").strip()
    if not estrategia:
        raise HTTPException(status_code=422,
                            detail="El dictamen no tiene una estrategia que convertir en borrador.")
    proximo = (conc.get("proximo_paso") or "").strip()
    partes = [
        "Redacta un borrador siguiendo esta estrategia acordada en la sala de estrategia:",
        "",
        estrategia,
    ]
    if proximo:
        partes += ["", f"Próximo paso definido por la sala: {proximo}"]
    message = "\n".join(partes)
    # El texto de la estrategia NO va en la URL: la pantalla lo manda en el body del POST /stream.
    return {"stream_url": f"/api/matters/{matter_id}/stream", "message": message}
