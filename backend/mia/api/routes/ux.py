"""Mia · api.routes.ux — superficie /api/* que consumen las 5 pantallas (Fase 3 · decisión #20).

Endpoints nuevos bajo prefijo `/api`, separados de las rutas legacy (`/matters`,
`/matters/{id}/stream`, `/matters/{id}/approve…`) que NO se tocan (gate 1d intacto). Auth: el
JWT middleware existente fija `request.state.tenant_id`; todas las consultas pasan por RLS.

§G (CLAUDE.md): las respuestas NO exponen jerga técnica al abogado — nombres de job, conectores
y modelos se traducen a etiquetas amigables; nunca pgvector/tenant_id/embedding/HITL/LangGraph.
"""
from __future__ import annotations

import asyncio
import logging
import time
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import quote

from fastapi import APIRouter, File, HTTPException, Query, Request, Response, UploadFile
from psycopg.types.json import Json
from psycopg.rows import dict_row
from pydantic import BaseModel

from ... import embeddings
from ...agent.prompt_builder import strip_diagnosis_closing
from ...agents.checkpointer import open_checkpointer
from ...agents.graph import build_matter_graph
from ...agents.state import thread_id_for
from ... import config
from ...connectors import ObsidianSync, PineconeConnector
from ...security import assert_no_stray_secret
from ...cron import build_scheduler
from ...db import pool
from ...ingest.extract import extract_text
from ...ingest.ingest import chunk_text
from ...jurisdiction.pack import GENERIC_CODE, list_packs, load_pack
from ...memory.gepa import GEPALoop
from ...memory.playbook_manager import Playbook, PlaybookManager
from ...memory.profile_manager import ProfileManager
from ...memory.trace_capture import TraceCapture
from ...memory.wiki_manager import WikiManager
from ...onboarding.soul_interview import SoulInterview, load_responses, soul_status
from ...output.docx_export import draft_to_docx
from ._common import assert_owns_matter, MAX_UPLOAD_BYTES
from .hitl import _resume
from .stream import stream_matter

router = APIRouter(prefix="/api", tags=["ux"])

logger = logging.getLogger("mia.api.ux")

# Timeout duro para la generación del SOUL.md (Ollama puede tardar mucho con el
# modelo 32b o en cold-start). Si se supera, se cae al fallback determinista sin LLM.
_SOUL_TIMEOUT_S = 120

# Precio aproximado USD por token (mezcla entrada/salida) — solo para el estimado del dashboard.
_USD_PER_TOKEN = 0.000009

_PROPOSAL_LABEL = {
    "improve_playbook": "Mejorar procedimiento",
    "new_playbook": "Nuevo procedimiento detectado",
    "flag_gap": "Brecha de conocimiento",
    "wiki_correction": "Corrección pendiente",
    "weekly_report": "Resumen semanal",
}
_JOB_LABEL = {
    "sync_obsidian_all_tenants": "Sincronización del conocimiento",
    "curator_weekly": "Depuración del conocimiento",
    "feedback_daily": "Aprendizaje de Mia",
    "dreams_weekly": "Consolidación semanal",
}


def _available_models() -> list[str]:
    cfg = Path(__file__).resolve().parents[4] / "litellm_config.yaml"
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


# ── Pantalla 1 / 2 · asuntos ─────────────────────────────────────────────────
class MatterCreate(BaseModel):
    name: str
    description: str = ""


@router.get("/matters")
async def list_matters(request: Request):
    tid = _tenant(request)
    async with pool.tenant_connection(tid) as conn:
        rows = await (await conn.execute(
            "SELECT id, title, description, status, created_at, pending_review FROM matters "
            "ORDER BY created_at DESC")).fetchall()
    return [{"id": str(r[0]), "name": r[1], "description": r[2], "status": r[3],
             "created_at": r[4], "pending_review": bool(r[5])} for r in rows]


@router.post("/matters", status_code=201)
async def create_matter(request: Request, body: MatterCreate):
    tid = _tenant(request)
    async with pool.tenant_connection(tid) as conn:
        row = await (await conn.execute(
            "INSERT INTO matters (tenant_id, title, description) VALUES (%s::uuid, %s, %s) "
            "RETURNING id, status, created_at", (tid, body.name, body.description))).fetchone()
    return {"id": str(row[0]), "name": body.name, "description": body.description,
            "status": row[1], "created_at": row[2]}


@router.get("/matters/{matter_id}")
async def get_matter(matter_id: str, request: Request):
    tid = _tenant(request)
    await assert_owns_matter(tid, matter_id)
    async with pool.tenant_connection(tid) as conn:
        row = await (await conn.execute(
            "SELECT id, title, description, status, created_at FROM matters "
            "WHERE id = %s::uuid", (matter_id,))).fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="Asunto no encontrado")
    return {"id": str(row[0]), "name": row[1], "description": row[2], "status": row[3],
            "created_at": row[4]}


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
async def upload_document(matter_id: str, request: Request, file: UploadFile = File(...)):
    tid = _tenant(request)
    await assert_owns_matter(tid, matter_id)
    # Lectura ACOTADA (auditoría 2026-07): leer solo hasta el límite + 1 byte evita
    # cargar en RAM un archivo arbitrariamente grande antes de poder rechazarlo.
    data = await file.read(MAX_UPLOAD_BYTES + 1)
    if len(data) > MAX_UPLOAD_BYTES:
        raise HTTPException(status_code=413, detail="El archivo supera el límite de 50 MB.")
    try:
        text = extract_text(file.filename, data)
    except ValueError as e:
        raise HTTPException(status_code=415, detail=str(e))
    chunks = chunk_text(text)
    if not chunks:
        raise HTTPException(status_code=400, detail="El documento está vacío o no tiene texto.")
    vectors = embeddings.embed_texts(chunks)
    async with pool.tenant_connection(tid) as conn:
        doc_id = (await (await conn.execute(
            "INSERT INTO documents (tenant_id, matter_id, filename, mime) "
            "VALUES (%s::uuid, %s::uuid, %s, %s) RETURNING id",
            (tid, matter_id, file.filename, file.content_type))).fetchone())[0]
        for i, (content, vec) in enumerate(zip(chunks, vectors)):
            await conn.execute(
                "INSERT INTO chunks (tenant_id, document_id, ord, content, embedding) "
                "VALUES (%s::uuid, %s, %s, %s, %s)", (tid, doc_id, i, content, vec))
    return {"id": str(doc_id), "name": file.filename, "fragments": len(chunks)}


# ── Pantalla 2 · chat + stream ───────────────────────────────────────────────
class ChatBody(BaseModel):
    message: str


@router.post("/matters/{matter_id}/chat")
async def chat(matter_id: str, request: Request, body: ChatBody):
    """Devuelve la URL del stream SSE para que el cliente conecte y reciba el turno."""
    tid = _tenant(request)
    await assert_owns_matter(tid, matter_id)
    return {"stream_url": f"/api/matters/{matter_id}/stream?message={quote(body.message)}"}


@router.get("/matters/{matter_id}/stream")
async def stream_alias(matter_id: str, request: Request, message: str = Query(..., min_length=1)):
    """Alias /api del SSE real (reusa el handler de 1d, no duplica la lógica del grafo)."""
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
    return {"draft": draft, "awaiting_review": awaiting,
            "diagnosis": strip_diagnosis_closing(md.get("diagnosis") or "") or None,
            "diagnosis_summary": md.get("diagnosis_summary"),
            # CP9: informe del especialista de verificación de citas (None en
            # borradores de turnos anteriores a CP9).
            "verification": md.get("verification")}


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
    safe = "".join(c if c.isalnum() or c in "-_ " else "" for c in title).strip() or "borrador"
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


@router.put("/profile")
async def put_profile(request: Request, body: ProfileBody):
    tid = _tenant(request)
    return await ProfileManager(pool=pool).upsert_firm_profile(tid, body.model_dump(exclude_none=True))


# ── Pantalla 4 · playbooks ───────────────────────────────────────────────────
class PlaybookBody(BaseModel):
    title: str
    summary: str
    applies_when: str
    content: str


@router.get("/playbooks")
async def list_playbooks(request: Request):
    tid = _tenant(request)
    rows = await PlaybookManager(pool=pool, tenant_id=tid).list_active()
    return [{"id": str(r["id"]), "title": r["title"], "summary": r["summary"],
             "applies_when": r["applies_when"]} for r in rows]


@router.post("/playbooks", status_code=201)
async def create_playbook(request: Request, body: PlaybookBody):
    tid = _tenant(request)
    pid = await PlaybookManager(pool=pool, tenant_id=tid).register_playbook(
        Playbook(id="", title=body.title, summary=body.summary,
                 applies_when=body.applies_when, content=body.content))
    return {"id": str(pid), "title": body.title}


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
            text = extract_text(fname, data)
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
                await mgr.register_playbook(_section_to_playbook(title, body_lines),
                                            protected=protected)
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
@router.get("/proposals")
async def list_proposals(request: Request):
    tid = _tenant(request)
    async with pool.tenant_connection(tid) as conn:
        async with conn.cursor(row_factory=dict_row) as cur:
            # CP-C3: se incluye el TÍTULO del playbook target — el abogado debe saber
            # QUÉ procedimiento se modificará al aplicar (hallazgo mayor del revisor).
            await cur.execute(
                "SELECT fp.id, fp.proposal_type, fp.suggested_content, fp.rationale, "
                "       fp.signal_count, fp.created_at, pb.title AS target_title "
                "FROM feedback_proposals fp "
                "LEFT JOIN playbooks pb ON pb.id = fp.target_playbook_id "
                "WHERE fp.status = 'pending' ORDER BY fp.created_at DESC")
            rows = await cur.fetchall()
    return [{"id": str(r["id"]), "type": _PROPOSAL_LABEL.get(r["proposal_type"], r["proposal_type"]),
             "suggestion": r["suggested_content"], "reason": r["rationale"],
             "target": r["target_title"],
             "times_seen": r["signal_count"], "created_at": r["created_at"]} for r in rows]


@router.post("/proposals/{proposal_id}/apply")
async def apply_proposal(proposal_id: str, request: Request):
    """Aplica una propuesta: actualiza/crea un playbook y la marca 'applied' (cierra parte del
    Riesgo #21)."""
    tid = _tenant(request)
    async with pool.tenant_connection(tid) as conn:
        async with conn.cursor(row_factory=dict_row) as cur:
            await cur.execute(
                "SELECT proposal_type, target_playbook_id, suggested_content "
                "FROM feedback_proposals WHERE id = %s::uuid AND status = 'pending'", (proposal_id,))
            p = await cur.fetchone()
        if not p:
            raise HTTPException(status_code=404, detail="Sugerencia no encontrada o ya revisada.")
        if p["proposal_type"] == "improve_playbook" and p["target_playbook_id"]:
            # H.6: no se puede sobrescribir un playbook protegido (semilla/core) desde una
            # sugerencia automática. La propuesta queda pendiente; se responde 409.
            prot = await (await conn.execute(
                "SELECT protected FROM playbooks WHERE id = %s", (p["target_playbook_id"],))).fetchone()
            if prot and prot[0]:
                raise HTTPException(
                    status_code=409,
                    detail="El playbook está protegido y no puede modificarse automáticamente.")
            # CP-C3: trazabilidad de la mejora — el playbook registra QUÉ propuesta lo
            # modificó, cuándo, y guarda el CONTENIDO ANTERIOR (metadata.last_improvement):
            # aplicar una mejora deja de ser irreversible (hallazgo mayor del revisor).
            applied_at = datetime.now(timezone.utc).isoformat()
            await conn.execute(
                "UPDATE playbooks SET content = %s, updated_at = now(), "
                "metadata = jsonb_set(COALESCE(metadata, '{}'::jsonb), '{last_improvement}', "
                "  jsonb_build_object('proposal_id', %s::text, 'applied_at', %s::text, "
                "                     'previous_content', playbooks.content), true) "
                "WHERE id = %s AND NOT protected",
                (p["suggested_content"], str(proposal_id), applied_at,
                 p["target_playbook_id"]))
        elif p["proposal_type"] == "new_playbook":
            await conn.execute(
                "INSERT INTO playbooks (tenant_id, title, summary, applies_when, content) "
                "VALUES (%s::uuid, %s, %s, %s, %s) ON CONFLICT (tenant_id, title) DO NOTHING",
                (tid, f"Sugerencia {proposal_id[:8]}", "Propuesta aplicada de Mia",
                 "(por afinar)", p["suggested_content"]))
        # flag_gap: no crea playbook; solo se marca como atendida.
        await conn.execute(
            "UPDATE feedback_proposals SET status = 'applied', reviewed_at = now() "
            "WHERE id = %s::uuid", (proposal_id,))
    return {"status": "applied"}


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
    async with pool.tenant_connection(tid) as conn:
        await conn.execute(
            "INSERT INTO tenant_settings (tenant_id, config) VALUES (%s::uuid, %s) "
            "ON CONFLICT (tenant_id) DO UPDATE SET "
            "config = jsonb_set(tenant_settings.config, '{pinecone}', %s::jsonb, true), updated_at = now()",
            (tid, Json({"pinecone": {"api_key": body.api_key, "index_name": body.index_name, "status": status}}),
             Json({"api_key": body.api_key, "index_name": body.index_name, "status": status, "stats": stats})),
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
            "  (tenant_id, proposal_type, suggested_content, rationale) "
            "VALUES (%s::uuid, 'wiki_correction', %s, %s)",
            (tid, body.correction, f"Corrección sugerida para {concept_name}"),
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


@router.get("/onboarding/questions")
async def onboarding_questions(request: Request):
    """Las 19 preguntas de la entrevista (id/block/field/question/example)."""
    _tenant(request)
    return await SoulInterview().get_questions()


@router.post("/onboarding/complete")
async def onboarding_complete(request: Request, body: OnboardingComplete):
    """Genera el SOUL.md del despacho a partir de las respuestas y lo guarda.

    Con timeout duro de 120s: si el LLM (Ollama) no responde a tiempo o falla, se
    construye el SOUL.md sin LLM desde las respuestas y el onboarding se marca como
    completado igual. El abogado puede refinar su perfil luego desde 'Mi despacho'.
    """
    tid = _tenant(request)
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
    try:
        content = await asyncio.wait_for(
            interview.run_interview(tid, body.responses), timeout=_SOUL_TIMEOUT_S
        )
        # puede_importar_guias: el frontend puede ofrecer el paso opcional de importar
        # las guías de trabajo del despacho (POST /api/playbooks/import — Riesgo #20).
        return {"soul_content": content, "path": f"soul_{tid}.md", "generated_by": "llm",
                "puede_importar_guias": True}
    except asyncio.TimeoutError:
        logger.warning("SOUL: timeout (%ss) tenant=%s — fallback sin LLM", _SOUL_TIMEOUT_S, tid)
    except Exception as exc:  # noqa: BLE001 — cualquier fallo del gateway cae al fallback
        logger.warning("SOUL: fallo del LLM tenant=%s (%s) — fallback sin LLM", tid, exc)
    content = interview.save_fallback(tid, body.responses)
    return {"soul_content": content, "path": f"soul_{tid}.md", "generated_by": "fallback",
            "puede_importar_guias": True}


@router.get("/onboarding/status")
async def onboarding_status(request: Request):
    """¿El despacho ya tiene SOUL.md? {completed, last_updated, responses}.

    `responses` trae las respuestas guardadas (o {}) para que 'Revisar mi perfil'
    precargue lo que el abogado contestó la última vez.
    """
    tid = _tenant(request)
    return {**soul_status(tid), "responses": load_responses(tid)}


# ── Pantalla 5 · dashboard ───────────────────────────────────────────────────
@router.get("/dashboard/stats")
async def dashboard_stats(request: Request):
    tid = _tenant(request)
    async with pool.tenant_connection(tid) as conn:
        async def scalar(sql):
            return (await (await conn.execute(sql)).fetchone())[0]
        matters_active = await scalar("SELECT count(*) FROM matters")
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

    # Costo aproximado del periodo a partir de las trazas del despacho.
    total_tokens = 0
    for t in TraceCapture().read(tid):
        tok = t.get("tokens")
        if isinstance(tok, dict):
            total_tokens += int(tok.get("total") or 0)
        elif isinstance(tok, int):
            total_tokens += tok
    cost_month_usd = round(total_tokens * _USD_PER_TOKEN, 2)

    jobs = [{"label": _JOB_LABEL.get(j["name"], j["name"]),
             "next_run": j["next_run"], "last_run": j["last_run"]}
            for j in build_scheduler().list_jobs()]
    raw_jobs = build_scheduler().list_jobs()
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
        "connectors": {
            "knowledge_base": {"active": last_sync is not None, "last_sync": last_sync, "chunks": knowledge_items},
            # CP-S2: el estado sale SOLO de la configuración del tenant (RLS) —
            # antes un PINECONE_API_KEY global del entorno marcaba "activo" para
            # todos los despachos (clave de la instalación, no del despacho).
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
