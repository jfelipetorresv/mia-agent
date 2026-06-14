"""Mia · agents.checkpointer — AsyncPostgresSaver multi-tenant (1d · PASO 3).

Checkpointing del grafo en la MISMA Postgres del Módulo 0 (base `mia`, rol
`mia_app`, RLS de dominio activo). Decisión #9:

- Las tablas de checkpoint de LangGraph (checkpoints, checkpoint_blobs,
  checkpoint_writes, checkpoint_migrations) las crea `postgres` en una MIGRACIÓN
  (`execution/init_checkpointer.py`), porque `mia_app` no tiene CREATE. A `mia_app`
  se le hace GRANT DML. En runtime el saver corre como `mia_app` y solo hace
  SELECT/INSERT/UPDATE/DELETE sobre esas tablas (NUNCA DDL).
- Esas tablas NO llevan RLS por tenant (LangGraph no lo soporta de forma nativa).
  El aislamiento del estado es por `thread_id = "{tenant_id}:{matter_id}"` +
  verificación del tenant del JWT en los endpoints HITL.
- El RLS de DOMINIO (chunks, matters…) sigue activo: los nodos que tocan la DB lo
  hacen vía `pool.tenant_connection`, que fija el GUC `app.tenant_id`.

`from_conn_string(DATABASE_URL)` abre y configura la conexión (autocommit +
dict_row) por sí mismo; se usa como context manager por operación de grafo. El
estado persiste en Postgres, así que reabrir entre requests (stream → resume) es
correcto: ese ES el punto del checkpointing en DB.
"""
from __future__ import annotations

from contextlib import asynccontextmanager

from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver

from .. import config


@asynccontextmanager
async def open_checkpointer():
    """Context manager async que entrega un AsyncPostgresSaver listo (rol `mia_app`).

    NO llama a `.setup()`: las tablas ya las creó la migración como `postgres`. Si
    se llamara aquí, `mia_app` (sin CREATE) fallaría — y ese es justamente el guard.
    """
    if not config.DATABASE_URL:
        raise RuntimeError("DATABASE_URL no está configurada en .env")
    async with AsyncPostgresSaver.from_conn_string(config.DATABASE_URL) as saver:
        yield saver
