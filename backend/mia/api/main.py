"""Mia · api.main — app FastAPI (Módulo 0): /health + ejemplo tenant-scoped."""
from __future__ import annotations
import asyncio
import sys
from contextlib import asynccontextmanager, suppress

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware

# psycopg async no es compatible con el ProactorEventLoop (default de Windows).
# Modo B es Windows nativo: fijar SelectorEventLoop antes de que uvicorn cree el loop.
if sys.platform == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

from .. import config
from ..cron import build_scheduler
from ..db import pool
from .middleware import TenantContextMiddleware
from .routes import assistant, auth, curator, folders, hitl, settings, stream, traces, ux


@asynccontextmanager
async def lifespan(app: FastAPI):
    config.validate_runtime_config()
    await pool.open_pool()
    # Arranque del scheduler de tareas periódicas (Riesgo #22): sin esto, los jobs
    # registrados (obsidian_sync 6h, curator_weekly 168h, feedback_daily 24h) NO se
    # disparan en producción. Corre como tarea de fondo y se detiene en el shutdown.
    scheduler = build_scheduler()
    app.state.scheduler = scheduler
    scheduler_task = asyncio.create_task(scheduler.start())
    try:
        yield
    finally:
        scheduler.stop()
        scheduler_task.cancel()
        with suppress(asyncio.CancelledError):
            await scheduler_task
        # C.4: drenar las tareas fire-and-forget de skill_improver (H.4) en vuelo ANTES de cerrar
        # el pool, para no perder propuestas a medio escribir en el shutdown.
        from ..agents.graph import drain_bg_tasks
        await drain_bg_tasks()
        await pool.close_pool()


app = FastAPI(title="Mia API", version="0.0.0", lifespan=lifespan)
app.add_middleware(TenantContextMiddleware)

# CORS: el frontend (localhost:3000) llama a la API (localhost:8000) cross-origin
# con header Authorization -> el navegador manda un preflight OPTIONS sin token.
# CORSMiddleware se anade DESPUES para quedar como el mas EXTERNO: contesta el
# preflight (y pone Access-Control-Allow-* en las respuestas reales) ANTES de que
# TenantContextMiddleware pueda rechazarlo con 401.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000", "http://127.0.0.1:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Routers del turno del asunto (Módulo 1d): SSE + HITL.
app.include_router(auth.router)
app.include_router(stream.router)
app.include_router(hitl.router)
# Router de ajustes del Agent Hub (Módulo 1e).
app.include_router(settings.router)
# Superficie /api/* de las 5 pantallas (Fase 3 backend, decisión #20).
app.include_router(ux.router)
# HITL del Curator (H.2, cierra Riesgo #19): propuestas de depuración de playbooks.
app.include_router(curator.router)
# Búsqueda FTS de trazas (H.3): session_search sin LLM.
app.include_router(traces.router)
# MODO ASISTENTE (CP-B1, Pilar B): conversación libre fuera de un asunto → /api/assistant/*.
app.include_router(assistant.router, prefix="/api")
# CARPETAS DE TRABAJO (CP-C1, Pilar C): allowlist de carpetas locales/nubes → /api/folders/*.
app.include_router(folders.router, prefix="/api")
# OBSIDIAN (CP-C2, Pilar C · decisión #32): estado/instalación/bootstrap → /api/obsidian/*.
app.include_router(folders.obsidian_router, prefix="/api")


@app.get("/health")
async def health():
    info = {
        "status": "ok",
        "db": False,
        "pgvector": None,
        "embed_model": config.EMBED_MODEL,
        "embed_dim": config.EMBED_DIM,
    }
    try:
        async with pool.get_pool().connection() as conn:
            row = await (await conn.execute(
                "SELECT extversion FROM pg_extension WHERE extname='vector'"
            )).fetchone()
            info["db"] = True
            info["pgvector"] = row[0] if row else None
    except Exception as e:  # noqa: BLE001 — el /health reporta el fallo, no lo propaga
        info["status"] = "degraded"
        info["error"] = str(e)
    return info


@app.get("/matters")
async def list_matters(request: Request):
    """Ejemplo tenant-scoped: solo devuelve los asuntos del tenant del JWT (RLS)."""
    tenant_id = getattr(request.state, "tenant_id", None)
    if not tenant_id:
        raise HTTPException(status_code=401, detail="Sin contexto de tenant")
    async with pool.tenant_connection(tenant_id) as conn:
        rows = await (await conn.execute(
            "SELECT id, title, created_at FROM matters ORDER BY created_at DESC"
        )).fetchall()
    return [{"id": str(r[0]), "title": r[1], "created_at": r[2].isoformat()} for r in rows]
