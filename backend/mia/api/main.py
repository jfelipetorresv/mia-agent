"""Mia · api.main — app FastAPI (Módulo 0): /health + ejemplo tenant-scoped."""
from __future__ import annotations
import asyncio
import sys
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, Request

# psycopg async no es compatible con el ProactorEventLoop (default de Windows).
# Modo B es Windows nativo: fijar SelectorEventLoop antes de que uvicorn cree el loop.
if sys.platform == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

from .. import config
from ..db import pool
from .middleware import TenantContextMiddleware
from .routes import hitl, settings, stream


@asynccontextmanager
async def lifespan(app: FastAPI):
    await pool.open_pool()
    yield
    await pool.close_pool()


app = FastAPI(title="Mia API", version="0.0.0", lifespan=lifespan)
app.add_middleware(TenantContextMiddleware)

# Routers del turno del asunto (Módulo 1d): SSE + HITL.
app.include_router(stream.router)
app.include_router(hitl.router)
# Router de ajustes del Agent Hub (Módulo 1e).
app.include_router(settings.router)


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
