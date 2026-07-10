"""Mia · api.main — app FastAPI (Módulo 0): /health + ejemplo tenant-scoped."""
from __future__ import annotations
import asyncio
import logging
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
from ..security import install_redacting_logging
from .middleware import TenantContextMiddleware
from .routes import (assistant, auth, automations, curator, folders, hitl, learning,
                     mailbox, matter_folders, matter_mail, matter_sources, mcp, missions,
                     personas, policy, remote_drive, settings, setup, sources, speech,
                     stream, traces, ux, value)

# CP-S2: redacción de credenciales en logs desde el import del entrypoint —
# nada que se loguee durante el arranque debe salir sin pasar por el redactor.
install_redacting_logging()


@asynccontextmanager
async def lifespan(app: FastAPI):
    # CP-S2 (segunda pasada, idempotente): uvicorn instala sus handlers DESPUÉS
    # del import del módulo — aquí ya existen y quedan envueltos también.
    install_redacting_logging()
    config.validate_runtime_config()
    await pool.open_pool()
    # Arranque del scheduler de tareas periódicas (Riesgo #22): sin esto, los jobs
    # registrados (obsidian_sync 6h, curator_weekly 168h, feedback_daily 24h) NO se
    # disparan en producción. Corre como tarea de fondo y se detiene en el shutdown.
    scheduler = build_scheduler()
    app.state.scheduler = scheduler
    scheduler_task = asyncio.create_task(scheduler.start())

    # CP-V1 (Ola 4): flusher periódico del uso real del LLM (metrics/usage bufferiza
    # en memoria desde call_llm; aquí se persiste a turn_usage cada 15s y al apagar).
    from ..metrics import usage as usage_metrics

    async def _usage_flusher() -> None:
        while True:
            await asyncio.sleep(15)
            try:
                await usage_metrics.flush_pending()
            except Exception:  # noqa: BLE001 — el flusher nunca muere por un fallo puntual
                logging.getLogger("mia.metrics.usage").exception("flush periódico falló")

    usage_task = asyncio.create_task(_usage_flusher())
    try:
        yield
    finally:
        scheduler.stop()
        scheduler_task.cancel()
        with suppress(asyncio.CancelledError):
            await scheduler_task
        usage_task.cancel()
        with suppress(asyncio.CancelledError):
            await usage_task
        # C.4: drenar las tareas fire-and-forget de skill_improver (H.4) en vuelo ANTES de cerrar
        # el pool, para no perder propuestas a medio escribir en el shutdown.
        from ..agents.graph import drain_bg_tasks
        await drain_bg_tasks()
        # Último flush DESPUÉS del drenado (capa 2 CP-V1, B2): las tareas de fondo
        # también registran uso; y ANTES de cerrar el pool, que lo necesita.
        with suppress(Exception):
            await usage_metrics.flush_pending()
        await pool.close_pool()


# Auditoría 2026-07: en producción las docs interactivas se APAGAN (docs_url/redoc/
# openapi = None) — exponen el mapa completo del API; en dev siguen disponibles.
_docs_kwargs = (
    {"docs_url": None, "redoc_url": None, "openapi_url": None}
    if config.IS_PRODUCTION else {}
)
app = FastAPI(title="Mia API", version="0.0.0", lifespan=lifespan, **_docs_kwargs)


class SecurityHeadersMiddleware:
    """Cabeceras defensivas en TODA respuesta del API (auditoría 2026-07):
    - nosniff: el navegador no reinterpreta el content-type (p. ej. un upload como HTML)
    - DENY frames: el API nunca se embebe en un iframe (clickjacking)
    - Referrer-Policy: las URLs (que pueden llevar ?message= confidencial) no viajan
      como referer a terceros
    - Cache-Control no-store: respuestas con datos de expedientes no quedan en cachés
      intermedios (solo si el handler no fijó ya su propia política, p. ej. SSE)."""

    def __init__(self, app):  # ASGI puro: no consume el body ni interfiere con SSE
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            return await self.app(scope, receive, send)

        async def send_with_headers(message):
            if message["type"] == "http.response.start":
                headers = list(message.get("headers") or [])
                message["headers"] = headers
                existing = {bytes(k).lower() for k, _ in headers}
                for name, value in (
                    (b"x-content-type-options", b"nosniff"),
                    (b"x-frame-options", b"DENY"),
                    (b"referrer-policy", b"no-referrer"),
                    (b"cache-control", b"no-store"),
                ):
                    if name not in existing:
                        headers.append((name, value))
            await send(message)

        await self.app(scope, receive, send_with_headers)


app.add_middleware(TenantContextMiddleware)

# CORS: el frontend (localhost:3000) llama a la API (localhost:8000) cross-origin
# con header Authorization -> el navegador manda un preflight OPTIONS sin token.
# CORSMiddleware se anade DESPUES para quedar como el mas EXTERNO: contesta el
# preflight (y pone Access-Control-Allow-* en las respuestas reales) ANTES de que
# TenantContextMiddleware pueda rechazarlo con 401.
# Auditoría 2026-07: orígenes desde .env (MIA_CORS_ORIGINS), métodos y headers
# acotados a los que el frontend usa de verdad (antes "*" en ambos).
app.add_middleware(
    CORSMiddleware,
    allow_origins=config.CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"],
    allow_headers=["Authorization", "Content-Type"],
)

# Las cabeceras de seguridad van las MÁS externas: cubren también las respuestas
# del CORSMiddleware y los errores tempranos del middleware de tenant.
app.add_middleware(SecurityHeadersMiddleware)

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
# Frente B (B2): disparo manual del aprendizaje de Mia → POST /api/learning/run.
app.include_router(learning.router)
# Búsqueda FTS de trazas (H.3): session_search sin LLM.
app.include_router(traces.router)
# MODO ASISTENTE (CP-B1, Pilar B): conversación libre fuera de un asunto → /api/assistant/*.
app.include_router(assistant.router, prefix="/api")
# CARPETAS DE TRABAJO (CP-C1, Pilar C): allowlist de carpetas locales/nubes → /api/folders/*.
app.include_router(folders.router, prefix="/api")
# EXPEDIENTE VINCULADO (Pilar C): carpeta del asunto → /api/matters/{id}/folder*. El router
# ya trae su propio prefijo /api (rutas /matters/{id}/...), así que se monta sin prefijo extra.
app.include_router(matter_folders.router)
# Fase 2 · CORREOS DEL CASO → EXPEDIENTE: buscar y vincular correos → /api/matters/{id}/mail/*.
# El router ya trae su propio prefijo /api, se monta sin prefijo extra (igual que matter_folders).
app.include_router(matter_mail.router)
# Bloque A (limpieza) · FUENTES UNIFICADAS del expediente (carpetas + OneDrive + correo)
# en una sola vista → GET /api/matters/{id}/sources. El router ya trae su propio prefijo
# /api, se monta sin prefijo extra (igual que matter_folders/matter_mail).
app.include_router(matter_sources.router)
# Fase 3 · ONEDRIVE REMOTO SELECTIVO: navegar/registrar/sincronizar carpetas → /api/drive/*.
# El router ya trae su propio prefijo /api/drive, se monta sin prefijo extra.
app.include_router(remote_drive.router)
# OBSIDIAN (CP-C2, Pilar C · decisión #32): estado/instalación/bootstrap → /api/obsidian/*.
app.include_router(folders.obsidian_router, prefix="/api")
# CP-C4 · asistente de configuración guiado (estado del recorrido "Configura a Mia")
app.include_router(setup.router, prefix="/api")
# CP-P3 (Ola 2) · conectores de calendario y correo (Microsoft 365 / Google Workspace).
app.include_router(mailbox.router, prefix="/api")
# CP-P2 (Ola 2) · plantillas de automatización + sugerencias consent-first.
app.include_router(automations.router, prefix="/api")
# CP-V1 (Ola 4) · configuración del "valor entregado" (tarifa y estimados por despacho).
app.include_router(value.router, prefix="/api")
# CP-Z1 (Ola 3) · dictado local (Silero VAD + Parakeet v3, 100% en el servidor del despacho).
app.include_router(speech.router, prefix="/api")
app.include_router(policy.router, prefix="/api")
app.include_router(personas.router, prefix="/api")
# CP-E5 (Ola 5) · tablero de misión por expediente (objetivo grande → hitos visibles).
app.include_router(missions.router, prefix="/api")
# CP-E6 (Ola 5) · conectar sistemas externos vía MCP con seguridad (consent-first).
app.include_router(mcp.router, prefix="/api")
# Fase 1b (transformación) · consulta de fuentes del corpus para citas en línea.
app.include_router(sources.router, prefix="/api")


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
    except Exception:  # noqa: BLE001 — el /health reporta el fallo, no lo propaga
        # Auditoría 2026-07: el detalle del error (que puede traer host/usuario de la
        # conexión) va SOLO al log (ya redactado); /health es público y responde genérico.
        logging.getLogger("mia.api.health").exception("health check: la DB no respondió")
        info["status"] = "degraded"
        info["error"] = "db_unavailable"
    return info


@app.get("/matters")
async def list_matters(request: Request):
    """Ejemplo tenant-scoped: solo devuelve los asuntos del tenant del JWT (RLS)."""
    tenant_id = getattr(request.state, "tenant_id", None)
    if not tenant_id:
        raise HTTPException(status_code=401, detail="Sin contexto de tenant")
    async with pool.tenant_connection(tenant_id) as conn:
        rows = await (await conn.execute(
            "SELECT id, title, created_at FROM matters WHERE kind = 'asunto' ORDER BY created_at DESC"
        )).fetchall()
    return [{"id": str(r[0]), "title": r[1], "created_at": r[2].isoformat()} for r in rows]
