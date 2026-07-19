"""Cola durable mínima sobre PostgreSQL portable (sin Redis ni nube).

Entrega at-least-once: cada handler debe ser idempotente. El claim se hace con
la conexión local de sistema; el trabajo real vuelve a las conexiones RLS del
tenant dentro del handler.
"""
from __future__ import annotations

import asyncio
import hashlib
import logging
import os
import socket
import uuid
from collections.abc import Awaitable, Callable, Mapping
from typing import Any

import psycopg
from psycopg.rows import dict_row
from psycopg.types.json import Jsonb

from .. import config
from ..db import pool
from ..security.redact import redact_text

logger = logging.getLogger("mia.jobs")
Handler = Callable[[str, Mapping[str, Any]], Awaitable[dict]]

LEASE_SECONDS = 90
HEARTBEAT_SECONDS = 25
JOB_TIMEOUT_SECONDS = 15 * 60
POLL_SECONDS = 1.0


async def _matter_folder_sync(tenant_id: str, payload: Mapping[str, Any]) -> dict:
    from ..connectors.local_folders import LocalFolderSync, get_matter_sources

    source_id = str(payload.get("source_id") or "")
    matter_id = str(payload.get("matter_id") or "")
    # Valida forma antes de consultar; nunca ejecuta rutas/comandos del payload.
    uuid.UUID(source_id)
    uuid.UUID(matter_id)
    sources = await get_matter_sources(tenant_id, matter_id)
    source = next((item for item in sources if str(item["id"]) == source_id), None)
    if source is None:
        return {"skipped": "source_unavailable"}
    return await LocalFolderSync().sync_source(tenant_id, source)


# Presupuesto de texto que el job reconstruye de los chunks para clasificar. El clasificador
# solo mira la cabecera/primera página y trunca a su propio _MAX_CHARS (~6000); con holgura
# sobre eso basta. Los chunks solapan ~150 chars, ese duplicado en la cabecera es inocuo.
_CLASSIFY_TEXT_BUDGET = 8000

# Columnas REALES de la ficha (migración 045) que la ALTA confianza puede escribir. Lista
# blanca de literales del código — NUNCA se interpola una clave venida del modelo o del payload.
_CLASSIFY_HIGH_COLS = ("tipo", "parte", "folio_radicado")


async def _load_doc_for_classify(
    tenant_id: str, document_id: str
) -> tuple[str, str, str] | None:
    """Carga filename/origin y reconstruye el COMIENZO del texto (desde los chunks) del
    documento para clasificarlo. None si el documento ya no existe (p. ej. un re-sync lo
    reemplazó): en ese caso el job se salta sin ruido."""
    async with pool.tenant_connection(tenant_id) as conn:
        row = await (await conn.execute(
            "SELECT filename, origin FROM documents WHERE id = %s::uuid",
            (document_id,),
        )).fetchone()
        if not row:
            return None
        filename, origin = row[0] or "", row[1] or ""
        chunks = await (await conn.execute(
            "SELECT content FROM chunks WHERE document_id = %s::uuid ORDER BY ord",
            (document_id,),
        )).fetchall()
    parts: list[str] = []
    total = 0
    for (content,) in chunks:
        if not content:
            continue
        parts.append(content)
        total += len(content)
        if total >= _CLASSIFY_TEXT_BUDGET:
            break
    return filename, origin, "\n".join(parts)


async def _persist_classification(
    tenant_id: str, document_id: str, result: Mapping[str, Any]
) -> dict:
    """Aplica el retorno {alta, sugerida} del clasificador sobre `documents` (RLS del tenant):
      · ALTA  → escribe DIRECTO las columnas reales (045); `fecha_documento` con COALESCE para
        NUNCA pisar una fecha ya fijada (dato fidedigno, red adicional al chequeo del clasificador).
      · SUGERIDA → guarda el jsonb en `documents.metadata_sugerida` (046). Ese jsonb ES la marca
        de 'pendiente' (decisión de la fase base: sin flag/status aparte; la lista 'Documentos por
        confirmar' se deriva de `metadata_sugerida IS NOT NULL`). Sin dudas no se toca la columna."""
    alta = result.get("alta") or {}
    sugerida = result.get("sugerida") or {}
    sets: list[str] = []
    params: list[Any] = []
    for campo in _CLASSIFY_HIGH_COLS:  # tipo/parte/folio_radicado (nombres controlados)
        valor = alta.get(campo)
        if valor:
            sets.append(f"{campo} = %s")
            params.append(valor)
    fecha = alta.get("fecha_documento")
    if fecha:
        # COALESCE: si ya hay fecha (correo, etc.) se conserva; solo rellena si estaba NULL.
        sets.append("fecha_documento = COALESCE(fecha_documento, %s)")
        params.append(fecha)
    if sugerida:  # solo hay algo por confirmar si el clasificador dejó dudas
        sets.append("metadata_sugerida = %s")
        params.append(Jsonb(dict(sugerida)))
    if not sets:
        return {"alta": 0, "sugerida": 0, "updated": False}
    params.append(document_id)
    async with pool.tenant_connection(tenant_id) as conn:
        await conn.execute(
            f"UPDATE documents SET {', '.join(sets)} WHERE id = %s::uuid",
            tuple(params),
        )
    return {"alta": len(alta), "sugerida": len(sugerida), "updated": True}


async def _classify_document(tenant_id: str, payload: Mapping[str, Any]) -> dict:
    """Job recuperable de clasificación de metadata (triaje barato, cadena AUX). Idempotente:
    re-ejecutarlo solo recalcula y re-escribe los mismos campos. Fail-soft heredado del
    clasificador (nunca inventa; cualquier fallo del modelo devuelve un resultado vacío)."""
    from ..ingest.classify import classify_document

    document_id = str(payload.get("document_id") or "")
    uuid.UUID(document_id)  # valida forma; jamás ejecuta rutas/comandos del payload
    loaded = await _load_doc_for_classify(tenant_id, document_id)
    if loaded is None:
        return {"skipped": "document_unavailable"}
    filename, origin, text = loaded
    result = await classify_document(tenant_id, document_id, text, filename, origin)
    return await _persist_classification(tenant_id, document_id, result)


HANDLERS: dict[str, Handler] = {
    "matter_folder_sync": _matter_folder_sync,
    "classify_document": _classify_document,
}


def _validate_type(job_type: str) -> None:
    if job_type not in HANDLERS:
        raise ValueError(f"Tipo de trabajo no permitido: {job_type}")


async def _enqueue_once(
    tenant_id: str,
    job_type: str,
    payload: Mapping[str, Any],
    dedupe_key: str,
    *,
    max_attempts: int = 5,
) -> tuple[str, bool] | None:
    """Encola o devuelve el trabajo activo equivalente (coalescing)."""
    _validate_type(job_type)
    if not dedupe_key or len(dedupe_key) > 200:
        raise ValueError("dedupe_key inválida")
    if not 1 <= max_attempts <= 20:
        raise ValueError("max_attempts fuera de rango")
    async with pool.tenant_connection(tenant_id) as conn:
        row = await (await conn.execute(
            "INSERT INTO durable_jobs(tenant_id, job_type, payload, dedupe_key, max_attempts) "
            "VALUES(%s::uuid, %s, %s, %s, %s) "
            "ON CONFLICT (tenant_id, job_type, dedupe_key) "
            "WHERE status IN ('queued','running') DO NOTHING RETURNING id",
            (tenant_id, job_type, Jsonb(dict(payload)), dedupe_key, max_attempts),
        )).fetchone()
        if row:
            return str(row[0]), True
        existing = await (await conn.execute(
            "SELECT id FROM durable_jobs WHERE tenant_id=%s::uuid AND job_type=%s "
            "AND dedupe_key=%s AND status IN ('queued','running')",
            (tenant_id, job_type, dedupe_key),
        )).fetchone()
    if not existing:  # conflicto terminó entre INSERT y SELECT
        return None
    return str(existing[0]), False


async def enqueue_job(
    tenant_id: str,
    job_type: str,
    payload: Mapping[str, Any],
    dedupe_key: str,
    *,
    max_attempts: int = 5,
) -> tuple[str, bool]:
    """Encola con tres reintentos acotados ante una carrera muy breve."""
    for _ in range(3):
        result = await _enqueue_once(
            tenant_id, job_type, payload, dedupe_key, max_attempts=max_attempts
        )
        if result is not None:
            return result
    raise RuntimeError("No pude estabilizar el trabajo equivalente en la cola.")


async def enqueue_classification(tenant_id: str, document_id: str) -> None:
    """Encola (FAIL-SOFT) la clasificación de metadata de un documento recién ingerido, para el
    handler `classify_document`. `dedupe_key = document_id` ⇒ un solo job vivo por documento (si
    ya hay uno encolado/corriendo, coalesce). NUNCA rompe la ingesta: cualquier fallo al encolar
    se loguea y se traga — el triaje de metadata es un extra opcional, no un requisito de ingesta."""
    try:
        await enqueue_job(
            tenant_id,
            "classify_document",
            {"document_id": str(document_id), "tenant_id": str(tenant_id)},
            dedupe_key=str(document_id),
        )
    except Exception:  # noqa: BLE001 — encolar el triaje jamás debe tumbar la ingesta
        logger.warning(
            "classify: no pude encolar la clasificación del doc %s (ingesta intacta)",
            document_id, exc_info=True,
        )


async def latest_job(tenant_id: str, job_type: str, dedupe_key: str) -> dict | None:
    """Último estado visible por el tenant, sin exponer errores técnicos."""
    _validate_type(job_type)
    async with pool.tenant_connection(tenant_id) as conn:
        row = await (await conn.execute(
            "SELECT id, status, attempts, result, created_at, finished_at "
            "FROM durable_jobs WHERE tenant_id=%s::uuid AND job_type=%s AND dedupe_key=%s "
            "ORDER BY created_at DESC LIMIT 1",
            (tenant_id, job_type, dedupe_key),
        )).fetchone()
    if not row:
        return None
    return {
        "id": str(row[0]), "status": row[1], "attempts": row[2],
        "result": row[3] or {}, "created_at": row[4], "finished_at": row[5],
    }


def _admin_kw() -> dict:
    password = os.getenv("PG_PASSWORD", "")
    if not password:
        raise RuntimeError("PG_PASSWORD no está configurada para el trabajador local")
    return {
        "host": os.getenv("PG_HOST", "127.0.0.1"),
        "port": int(os.getenv("PG_PORT", "5432")),
        "dbname": config.PG_DB,
        "user": "postgres",
        "password": password,
        "row_factory": dict_row,
    }


async def _admin_connection():
    return await psycopg.AsyncConnection.connect(**_admin_kw())


async def claim_one(worker_id: str, lease_seconds: int = LEASE_SECONDS) -> dict | None:
    """Claim atómico; también recupera leases vencidos tras una caída."""
    async with await _admin_connection() as conn:
        async with conn.transaction():
            await conn.execute(
                "UPDATE durable_jobs SET status='failed', finished_at=now(), updated_at=now(), "
                "last_error='El trabajo agotó sus intentos tras una interrupción.' "
                "WHERE status='running' AND lease_expires_at < now() AND attempts >= max_attempts"
            )
            row = await (await conn.execute(
                "WITH candidate AS ("
                " SELECT id FROM durable_jobs WHERE "
                " (status='queued' AND available_at <= now()) OR "
                " (status='running' AND lease_expires_at < now() AND attempts < max_attempts) "
                " ORDER BY available_at, created_at FOR UPDATE SKIP LOCKED LIMIT 1"
                ") UPDATE durable_jobs j SET status='running', attempts=j.attempts+1, "
                " claimed_at=now(), claimed_by=%s, lease_expires_at=now()+(%s||' seconds')::interval, "
                " heartbeat_at=now(), started_at=COALESCE(j.started_at, now()), updated_at=now() "
                "FROM candidate c WHERE j.id=c.id RETURNING j.*",
                (worker_id, lease_seconds),
            )).fetchone()
        return dict(row) if row else None


async def _owned_update(job_id: str, worker_id: str, sql: str, params: tuple = ()) -> bool:
    async with await _admin_connection() as conn:
        result = await conn.execute(
            sql + " WHERE id=%s::uuid AND status='running' AND claimed_by=%s",
            (*params, job_id, worker_id),
        )
        await conn.commit()
        return result.rowcount == 1


async def heartbeat(job_id: str, worker_id: str, lease_seconds: int = LEASE_SECONDS) -> bool:
    return await _owned_update(
        job_id, worker_id,
        "UPDATE durable_jobs SET heartbeat_at=now(), "
        "lease_expires_at=now()+(%s||' seconds')::interval, updated_at=now()",
        (lease_seconds,),
    )


async def finish_success(job_id: str, worker_id: str, result: Mapping[str, Any]) -> bool:
    return await _owned_update(
        job_id, worker_id,
        "UPDATE durable_jobs SET status='succeeded', result=%s, finished_at=now(), "
        "lease_expires_at=NULL, heartbeat_at=now(), last_error=NULL, updated_at=now()",
        (Jsonb(dict(result)),),
    )


def _retry_delay(job_id: str, attempts: int) -> int:
    base = min(300, 5 * (2 ** max(0, attempts - 1)))
    jitter = int(hashlib.sha256(f"{job_id}:{attempts}".encode()).hexdigest()[:2], 16) % 6
    return base + jitter


async def finish_failure(
    job: Mapping[str, Any], worker_id: str, error: BaseException, *, permanent: bool = False
) -> bool:
    attempts = int(job["attempts"])
    exhausted = permanent or attempts >= int(job["max_attempts"])
    status = "failed" if exhausted else "queued"
    delay = 0 if exhausted else _retry_delay(str(job["id"]), attempts)
    message = redact_text(str(error))[:1000] or error.__class__.__name__
    return await _owned_update(
        str(job["id"]), worker_id,
        "UPDATE durable_jobs SET status=%s, last_error=%s, "
        "available_at=now()+(%s||' seconds')::interval, "
        "finished_at=CASE WHEN %s THEN now() ELSE NULL END, "
        "claimed_by=NULL, claimed_at=NULL, lease_expires_at=NULL, updated_at=now()",
        (status, message, delay, exhausted),
    )


class DurableWorker:
    def __init__(self, *, concurrency: int = 2) -> None:
        self.concurrency = max(1, min(int(concurrency), 4))
        self.worker_id = f"{os.getpid()}@{socket.gethostname()}:{uuid.uuid4().hex[:8]}"
        self._running = False
        self._tasks: set[asyncio.Task] = set()

    async def _heartbeat_loop(self, job_id: str, lost_lease: asyncio.Event) -> None:
        consecutive_errors = 0
        while True:
            await asyncio.sleep(HEARTBEAT_SECONDS)
            try:
                if not await heartbeat(job_id, self.worker_id):
                    lost_lease.set()
                    return
                consecutive_errors = 0
            except Exception:
                consecutive_errors += 1
                logger.exception("no pude renovar el lease del trabajo %s", job_id)
                # 3 fallos ocurren a los 75 s, antes del lease de 90 s. Se
                # cancela el handler para que nunca siga vivo cuando otro worker
                # pueda reclamar la fila.
                if consecutive_errors >= 3:
                    lost_lease.set()
                    return

    async def _execute(self, job: Mapping[str, Any]) -> None:
        job_id = str(job["id"])
        lost_lease = asyncio.Event()
        pulse = asyncio.create_task(self._heartbeat_loop(job_id, lost_lease))
        handler_task: asyncio.Task | None = None
        lease_wait: asyncio.Task | None = None
        try:
            handler = HANDLERS.get(str(job["job_type"]))
            if handler is None:
                await finish_failure(job, self.worker_id, ValueError("Tipo no permitido"), permanent=True)
                return
            handler_task = asyncio.create_task(
                handler(str(job["tenant_id"]), dict(job["payload"]))
            )
            lease_wait = asyncio.create_task(lost_lease.wait())
            done, _pending = await asyncio.wait(
                {handler_task, lease_wait},
                timeout=JOB_TIMEOUT_SECONDS,
                return_when=asyncio.FIRST_COMPLETED,
            )
            if handler_task not in done:
                handler_task.cancel()
                await asyncio.gather(handler_task, return_exceptions=True)
                if lost_lease.is_set():
                    logger.warning("trabajo %s detenido al perder su lease", job_id)
                    return  # no cambia la fila; el lease vencido permite recuperarla
                raise TimeoutError("El trabajo superó el tiempo máximo permitido.")
            result = await handler_task
            if not await finish_success(job_id, self.worker_id, result):
                logger.warning("trabajo %s terminó después de perder su lease", job_id)
        except asyncio.CancelledError:
            raise  # deja el lease; el próximo arranque lo recupera
        except Exception as exc:  # noqa: BLE001 - frontera durable
            logger.exception("trabajo durable %s falló", job_id)
            await finish_failure(job, self.worker_id, exc)
        finally:
            if lease_wait is not None:
                lease_wait.cancel()
            if handler_task is not None and not handler_task.done():
                handler_task.cancel()
            pulse.cancel()
            await asyncio.gather(
                *(task for task in (handler_task, lease_wait, pulse) if task is not None),
                return_exceptions=True,
            )

    async def start(self) -> None:
        self._running = True
        while self._running:
            done = {task for task in self._tasks if task.done()}
            for task in done:
                exc = None if task.cancelled() else task.exception()
                if exc is not None:
                    logger.error(
                        "un trabajo durable terminó fuera de su frontera",
                        exc_info=(type(exc), exc, exc.__traceback__),
                    )
            self._tasks.difference_update(done)
            try:
                while self._running and len(self._tasks) < self.concurrency:
                    job = await claim_one(self.worker_id)
                    if job is None:
                        break
                    task = asyncio.create_task(self._execute(job))
                    self._tasks.add(task)
            except Exception:
                logger.exception("el trabajador durable no pudo reclamar trabajos")
            await asyncio.sleep(POLL_SECONDS)

    async def stop(self, grace_seconds: float = 30.0) -> None:
        self._running = False
        if not self._tasks:
            return
        _done, pending = await asyncio.wait(self._tasks, timeout=grace_seconds)
        for task in pending:
            task.cancel()
        if pending:
            await asyncio.gather(*pending, return_exceptions=True)
