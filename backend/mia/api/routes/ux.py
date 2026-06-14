"""Mia · api.routes.ux — superficie /api/* que consumen las 5 pantallas (Fase 3 · decisión #20).

Endpoints nuevos bajo prefijo `/api`, separados de las rutas legacy (`/matters`,
`/matters/{id}/stream`, `/matters/{id}/approve…`) que NO se tocan (gate 1d intacto). Auth: el
JWT middleware existente fija `request.state.tenant_id`; todas las consultas pasan por RLS.

§G (CLAUDE.md): las respuestas NO exponen jerga técnica al abogado — nombres de job, conectores
y modelos se traducen a etiquetas amigables; nunca pgvector/tenant_id/embedding/HITL/LangGraph.
"""
from __future__ import annotations

from urllib.parse import quote

from fastapi import APIRouter, File, HTTPException, Query, Request, UploadFile
from psycopg.rows import dict_row
from pydantic import BaseModel

from ... import embeddings
from ...agents.checkpointer import open_checkpointer
from ...agents.graph import build_matter_graph
from ...agents.state import thread_id_for
from ...connectors import get_pinecone_connector
from ...cron import build_scheduler
from ...db import pool
from ...ingest.extract import extract_text
from ...ingest.ingest import chunk_text
from ...memory.playbook_manager import Playbook, PlaybookManager
from ...memory.profile_manager import ProfileManager
from ...memory.trace_capture import TraceCapture
from ...onboarding.soul_interview import SoulInterview, load_responses, soul_status
from ._common import assert_owns_matter
from .hitl import _resume
from .stream import stream_matter

router = APIRouter(prefix="/api", tags=["ux"])

# Precio aproximado USD por token (mezcla entrada/salida) — solo para el estimado del dashboard.
_USD_PER_TOKEN = 0.000009

_PROPOSAL_LABEL = {
    "improve_playbook": "Mejorar conocimiento",
    "new_playbook": "Conocimiento nuevo",
    "flag_gap": "Brecha detectada",
}
_JOB_LABEL = {
    "sync_obsidian_all_tenants": "Sincronización del conocimiento",
    "curator_weekly": "Depuración del conocimiento",
    "feedback_daily": "Aprendizaje de Mia",
}


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
            "SELECT id, title, description, status, created_at FROM matters "
            "ORDER BY created_at DESC")).fetchall()
    return [{"id": str(r[0]), "name": r[1], "description": r[2], "status": r[3],
             "created_at": r[4]} for r in rows]


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
    data = await file.read()
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
    return {"draft": draft, "awaiting_review": awaiting}


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


# ── Pantalla 4 · sugerencias de Mia (feedback_proposals) ─────────────────────
@router.get("/proposals")
async def list_proposals(request: Request):
    tid = _tenant(request)
    async with pool.tenant_connection(tid) as conn:
        async with conn.cursor(row_factory=dict_row) as cur:
            await cur.execute(
                "SELECT id, proposal_type, suggested_content, rationale, signal_count, created_at "
                "FROM feedback_proposals WHERE status = 'pending' ORDER BY created_at DESC")
            rows = await cur.fetchall()
    return [{"id": str(r["id"]), "type": _PROPOSAL_LABEL.get(r["proposal_type"], r["proposal_type"]),
             "suggestion": r["suggested_content"], "reason": r["rationale"],
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
            await conn.execute(
                "UPDATE playbooks SET content = %s, updated_at = now() WHERE id = %s",
                (p["suggested_content"], p["target_playbook_id"]))
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


# ── Onboarding · entrevista del SOUL.md (Módulo 5) ───────────────────────────
class OnboardingComplete(BaseModel):
    responses: dict


@router.get("/onboarding/questions")
async def onboarding_questions(request: Request):
    """Las 19 preguntas de la entrevista (id/block/field/question/example)."""
    _tenant(request)
    return await SoulInterview().get_questions()


@router.post("/onboarding/complete")
async def onboarding_complete(request: Request, body: OnboardingComplete):
    """Genera el SOUL.md del despacho a partir de las respuestas y lo guarda."""
    tid = _tenant(request)
    content = await SoulInterview().run_interview(tid, body.responses)
    return {"soul_content": content, "path": f"soul_{tid}.md"}


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
        proposals_pending = await scalar("SELECT count(*) FROM feedback_proposals WHERE status='pending'")
        knowledge_items = await scalar("SELECT count(*) FROM knowledge_chunks")
        last_sync = (await (await conn.execute(
            "SELECT max(last_indexed) FROM obsidian_file_hashes")).fetchone())[0]

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

    return {
        "matters_active": matters_active,
        "documents_indexed": documents_indexed,
        "playbooks_active": playbooks_active,
        "proposals_pending": proposals_pending,
        "knowledge_items": knowledge_items,
        "scheduler_jobs": jobs,
        "cost_month_usd": cost_month_usd,
        "connectors": {
            "knowledge_base": {"active": last_sync is not None, "last_sync": last_sync},
            "external_store": {"active": get_pinecone_connector().is_configured},
            "models": ["Razonamiento principal", "Respuestas rápidas"],
        },
    }
