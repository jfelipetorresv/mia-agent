"""
Mia · init_checkpointer.py — migración del checkpointing LangGraph (1d · decisión #9).

Crea las tablas de checkpoint de LangGraph (checkpoints, checkpoint_blobs,
checkpoint_writes, checkpoint_migrations) como `postgres` (mia_app NO tiene CREATE)
y hace GRANT DML a `mia_app`. En runtime el saver corre como mia_app sin tocar DDL.

Idempotente: re-ejecutable. Se corre con el python de mia/.venv:
    .venv\\Scripts\\python.exe execution\\init_checkpointer.py
"""
from __future__ import annotations
import asyncio
import os
import sys
from pathlib import Path

import psycopg
from psycopg.rows import dict_row
from dotenv import load_dotenv

# psycopg async no corre sobre ProactorEventLoop (Windows nativo, Modo B).
if sys.platform == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

ROOT = Path(__file__).resolve().parents[1]  # .../mia
load_dotenv(ROOT / ".env")
sys.path.insert(0, str(ROOT / "backend"))

from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver  # noqa: E402

HOST = os.getenv("PG_HOST", "127.0.0.1")
PORT = os.getenv("PG_PORT", "5432")
DB = os.getenv("PG_DB", "mia")
SUPER_PW = os.getenv("PG_PASSWORD", "")

if not SUPER_PW:
    sys.exit("ERROR: falta PG_PASSWORD en .env (superusuario para la migración)")

# GRANT dinámico: cubre cualquier tabla 'checkpoint%' que cree LangGraph.
_GRANT_SQL = """
DO $$
DECLARE t text;
BEGIN
  FOR t IN SELECT tablename FROM pg_tables
           WHERE schemaname='public' AND tablename LIKE 'checkpoint%' LOOP
    EXECUTE format('GRANT SELECT, INSERT, UPDATE, DELETE ON public.%I TO mia_app', t);
  END LOOP;
END $$;
"""


async def main() -> None:
    kw = dict(host=HOST, port=PORT, dbname=DB, user="postgres", password=SUPER_PW,
              autocommit=True, row_factory=dict_row)
    async with await psycopg.AsyncConnection.connect(**kw) as conn:
        saver = AsyncPostgresSaver(conn)
        await saver.setup()  # CREATE TABLE IF NOT EXISTS ... (como postgres)
        print("[OK] tablas de checkpoint creadas/migradas (rol postgres)")

        await conn.execute(_GRANT_SQL)
        rows = await (await conn.execute(
            "SELECT tablename FROM pg_tables WHERE schemaname='public' "
            "AND tablename LIKE 'checkpoint%' ORDER BY tablename"
        )).fetchall()
        names = [r["tablename"] for r in rows]
        print(f"[OK] GRANT DML a mia_app sobre: {', '.join(names)}")

        ins = await (await conn.execute(
            "SELECT has_table_privilege('mia_app','public.checkpoints','INSERT') AS ok"
        )).fetchone()
        print(f"[INFO] mia_app puede INSERT en checkpoints: {ins['ok']}")

        # Confirmar que NO tienen RLS forzado (aislamiento por thread_id, no por RLS).
        rls = await (await conn.execute(
            "SELECT bool_or(relrowsecurity) AS any_rls FROM pg_class "
            "WHERE relname LIKE 'checkpoint%' AND relnamespace='public'::regnamespace"
        )).fetchone()
        print(f"[INFO] alguna tabla de checkpoint con RLS: {rls['any_rls']} (esperado: False)")
    print("DONE init_checkpointer")


if __name__ == "__main__":
    asyncio.run(main())
