"""Gate F2: dedupe, lease, recovery, retry, RLS y allowlist de trabajos."""
from __future__ import annotations

import asyncio
import os
import sys
import uuid
from pathlib import Path

import psycopg
from dotenv import load_dotenv

if sys.platform == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))
sys.path.insert(0, str(ROOT / "execution"))
load_dotenv(ROOT / ".env")

import init_durable_jobs  # noqa: E402
from mia.db import pool  # noqa: E402
from mia.jobs import durable  # noqa: E402


async def main() -> None:
    init_durable_jobs.apply()
    password = os.getenv("PG_PASSWORD", "")
    admin = dict(
        host=os.getenv("PG_HOST", "127.0.0.1"), port=os.getenv("PG_PORT", "5432"),
        dbname=os.getenv("PG_DB", "mia"), user="postgres", password=password,
    )
    tenant_a, tenant_b = str(uuid.uuid4()), str(uuid.uuid4())
    with psycopg.connect(autocommit=True, **admin) as conn:
        conn.execute("INSERT INTO tenants(id,name) VALUES(%s,'Jobs A'),(%s,'Jobs B')",
                     (tenant_a, tenant_b))

    await pool.open_pool()
    try:
        payload = {"source_id": str(uuid.uuid4()), "matter_id": str(uuid.uuid4())}
        first, created = await durable.enqueue_job(
            tenant_a, "matter_folder_sync", payload, "source:a", max_attempts=2
        )
        duplicate, created_again = await durable.enqueue_job(
            tenant_a, "matter_folder_sync", payload, "source:a", max_attempts=2
        )
        assert created and not created_again and first == duplicate

        job1 = await durable.claim_one("worker-1", lease_seconds=5)
        assert str(job1["id"]) == first and job1["attempts"] == 1
        assert await durable.claim_one("worker-other", lease_seconds=5) is None

        # Simula una caída: nadie finaliza y el lease vence.
        with psycopg.connect(autocommit=True, **admin) as conn:
            conn.execute(
                "UPDATE durable_jobs SET lease_expires_at=now()-interval '1 second' WHERE id=%s",
                (first,),
            )
        recovered = await durable.claim_one("worker-2", lease_seconds=30)
        assert str(recovered["id"]) == first and recovered["attempts"] == 2
        assert await durable.finish_success(first, "worker-2", {"pending": 3})
        latest = await durable.latest_job(tenant_a, "matter_folder_sync", "source:a")
        assert latest and latest["status"] == "succeeded" and latest["result"]["pending"] == 3

        # Dedupe solo mientras está activo: al completar se admite una revisión futura.
        next_id, next_created = await durable.enqueue_job(
            tenant_a, "matter_folder_sync", payload, "source:a", max_attempts=2
        )
        assert next_created and next_id != first

        # RLS: otro despacho no puede consultar el historial de A.
        assert await durable.latest_job(tenant_b, "matter_folder_sync", "source:a") is None

        retry_job = await durable.claim_one("worker-r", lease_seconds=30)
        assert str(retry_job["id"]) == next_id
        assert await durable.finish_failure(retry_job, "worker-r", RuntimeError("temporal"))
        with psycopg.connect(autocommit=True, **admin) as conn:
            state = conn.execute(
                "SELECT status, attempts FROM durable_jobs WHERE id=%s", (next_id,)
            ).fetchone()
            assert state == ("queued", 1)
            conn.execute("UPDATE durable_jobs SET available_at=now() WHERE id=%s", (next_id,))
        retry2 = await durable.claim_one("worker-r2", lease_seconds=30)
        assert retry2["attempts"] == 2
        assert await durable.finish_failure(retry2, "worker-r2", RuntimeError("otra vez"))
        with psycopg.connect(autocommit=True, **admin) as conn:
            assert conn.execute(
                "SELECT status FROM durable_jobs WHERE id=%s", (next_id,)
            ).fetchone()[0] == "failed"

        try:
            await durable.enqueue_job(tenant_a, "shell_arbitrario", {}, "x")
            raise AssertionError("tipo desconocido aceptado")
        except ValueError:
            pass

        # Defensa en profundidad: incluso una fila envenenada por acceso directo
        # a la DB se marca fallida y nunca ejecuta payload arbitrario.
        poisoned = str(uuid.uuid4())
        with psycopg.connect(autocommit=True, **admin) as conn:
            conn.execute(
                "INSERT INTO durable_jobs(id,tenant_id,job_type,payload,dedupe_key) "
                "VALUES(%s,%s,'shell_arbitrario','{}','poison')", (poisoned, tenant_a),
            )
        poisoned_job = await durable.claim_one("worker-poison", lease_seconds=30)
        assert str(poisoned_job["id"]) == poisoned
        poison_worker = durable.DurableWorker(concurrency=1)
        poison_worker.worker_id = "worker-poison"
        await poison_worker._execute(poisoned_job)
        with psycopg.connect(autocommit=True, **admin) as conn:
            assert conn.execute(
                "SELECT status FROM durable_jobs WHERE id=%s", (poisoned,)
            ).fetchone()[0] == "failed"

        lease_id, _ = await durable.enqueue_job(
            tenant_a, "matter_folder_sync", payload, "lease-loss", max_attempts=3
        )
        lease_job = await durable.claim_one("worker-loss", lease_seconds=30)
        assert str(lease_job["id"]) == lease_id
        cancelled = asyncio.Event()
        old_handler = durable.HANDLERS["matter_folder_sync"]
        old_heartbeat = durable.heartbeat
        old_interval = durable.HEARTBEAT_SECONDS

        async def wait_forever(_tenant, _payload):
            try:
                await asyncio.Event().wait()
            finally:
                cancelled.set()

        async def lose_lease(*_args, **_kwargs):
            return False

        durable.HANDLERS["matter_folder_sync"] = wait_forever
        durable.heartbeat = lose_lease
        durable.HEARTBEAT_SECONDS = 0.01
        try:
            loss_worker = durable.DurableWorker(concurrency=1)
            loss_worker.worker_id = "worker-loss"
            await loss_worker._execute(lease_job)
        finally:
            durable.HANDLERS["matter_folder_sync"] = old_handler
            durable.heartbeat = old_heartbeat
            durable.HEARTBEAT_SECONDS = old_interval
        assert cancelled.is_set()
        with psycopg.connect(autocommit=True, **admin) as conn:
            assert conn.execute(
                "SELECT status, claimed_by FROM durable_jobs WHERE id=%s", (lease_id,)
            ).fetchone() == ("running", "worker-loss")

        errors_id, _ = await durable.enqueue_job(
            tenant_a, "matter_folder_sync", payload, "heartbeat-errors", max_attempts=3
        )
        errors_job = await durable.claim_one("worker-errors", lease_seconds=30)
        assert str(errors_job["id"]) == errors_id
        cancelled_errors = asyncio.Event()
        heartbeat_calls = 0

        async def wait_for_error_cancel(_tenant, _payload):
            try:
                await asyncio.Event().wait()
            finally:
                cancelled_errors.set()

        async def broken_heartbeat(*_args, **_kwargs):
            nonlocal heartbeat_calls
            heartbeat_calls += 1
            raise ConnectionError("DB temporalmente fuera")

        durable.HANDLERS["matter_folder_sync"] = wait_for_error_cancel
        durable.heartbeat = broken_heartbeat
        durable.HEARTBEAT_SECONDS = 0.01
        try:
            errors_worker = durable.DurableWorker(concurrency=1)
            errors_worker.worker_id = "worker-errors"
            await errors_worker._execute(errors_job)
        finally:
            durable.HANDLERS["matter_folder_sync"] = old_handler
            durable.heartbeat = old_heartbeat
            durable.HEARTBEAT_SECONDS = old_interval
        assert heartbeat_calls == 3 and cancelled_errors.is_set()

        print("PASS: dedupe activo y una nueva ejecución después de completar")
        print("PASS: un lease vencido se recupera tras reinicio sin perder el trabajo")
        print("PASS: reintentos acotados terminan en estado fallido inspeccionable")
        print("PASS: RLS separa despachos y la allowlist rechaza tipos desconocidos")
        print("PASS: una fila envenenada tampoco puede ejecutar un tipo desconocido")
        print("PASS: perder el lease cancela el handler antes de permitir otro claim")
        print("PASS: tres fallos de heartbeat también cancelan antes de vencer el lease")
    finally:
        await pool.close_pool()
        with psycopg.connect(autocommit=True, **admin) as conn:
            conn.execute("DELETE FROM tenants WHERE id IN (%s,%s)", (tenant_a, tenant_b))


asyncio.run(main())
