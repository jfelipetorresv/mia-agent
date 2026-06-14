"""Mia · db.pool — pool async (psycopg3) con contexto de tenant para RLS."""
from __future__ import annotations
from contextlib import asynccontextmanager

import psycopg
from psycopg_pool import AsyncConnectionPool
from pgvector.psycopg import register_vector_async

from .. import config

_pool: AsyncConnectionPool | None = None


async def _configure(conn: psycopg.AsyncConnection) -> None:
    await register_vector_async(conn)


def get_pool() -> AsyncConnectionPool:
    global _pool
    if _pool is None:
        if not config.DATABASE_URL:
            raise RuntimeError("DATABASE_URL no está configurada en .env")
        _pool = AsyncConnectionPool(
            config.DATABASE_URL, open=False, min_size=1, max_size=10, configure=_configure
        )
    return _pool


async def open_pool() -> None:
    await get_pool().open()


async def close_pool() -> None:
    global _pool
    if _pool is not None:
        await _pool.close()
        _pool = None


@asynccontextmanager
async def tenant_connection(tenant_id: str):
    """Conexión con `app.tenant_id` fijado (RLS activo) dentro de una transacción."""
    async with get_pool().connection() as conn:
        async with conn.transaction():
            await conn.execute("SELECT set_config('app.tenant_id', %s, true)", (str(tenant_id),))
            yield conn


@asynccontextmanager
async def connection():
    """Conexión `mia_app` SIN contexto de tenant — solo para recursos COMPARTIDOS
    (corpus SAT-Graph, decisión #16). NO debilita el aislamiento: las tablas por-tenant
    siguen fail-closed sin `app.tenant_id` (0 filas), así que una conexión sin-GUC solo ve
    el corpus público. NUNCA usar para datos por-tenant — usar `tenant_connection`."""
    async with get_pool().connection() as conn:
        yield conn
