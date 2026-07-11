"""Mia · setup.db_bootstrap — lógica compartida de aprovisionamiento de Postgres.

Extraída de execution/init_db.py y execution/init_checkpointer.py (que ahora
importan estas funciones en vez de duplicar el SQL) para que
`mia.setup.first_run` pueda correr el mismo aprovisionamiento en una máquina
limpia, con un solo Postgres temporal, sin repetir bloques de código.

Todas las funciones reciben host/port/db/credenciales explícitos (nada de
`os.environ` aquí adentro): quien resuelve la configuración es el llamador
(execution/*.py lee .env del repo; first_run.py lee el .env semilla del
app_dir). Todas son idempotentes — se pueden re-ejecutar sin efecto adicional.
"""
from __future__ import annotations

import asyncio
import sys
from pathlib import Path

import psycopg
from psycopg import sql

# GRANT dinámico: cubre cualquier tabla 'checkpoint%' que cree LangGraph (idéntico
# al de execution/init_checkpointer.py original).
_CHECKPOINT_GRANT_SQL = """
DO $$
DECLARE t text;
BEGIN
  FOR t IN SELECT tablename FROM pg_tables
           WHERE schemaname='public' AND tablename LIKE 'checkpoint%' LOOP
    EXECUTE format('GRANT SELECT, INSERT, UPDATE, DELETE ON public.%I TO mia_app', t);
  END LOOP;
END $$;
"""


def _super_kw(host: str, port: str | int, dbname: str, password: str) -> dict:
    # Parámetros por keyword: psycopg escapa los valores (el password del
    # superusuario trae caracteres especiales que romperían una URL).
    return dict(host=host, port=port, dbname=dbname, user="postgres", password=password)


def ensure_app_role_and_database(
    host: str, port: str | int, db: str, super_pw: str, app_pw: str
) -> dict:
    """Crea/actualiza el rol `mia_app` (NOSUPERUSER, NOBYPASSRLS) y la base `db`.

    Devuelve {"role_verb": "ALTER"|"CREATE", "db_created": bool} — el llamador
    decide cómo formatear el mensaje de progreso (execution/*.py imprime
    "[OK] ...", first_run.py imprime "MIA-SETUP: ...").
    """
    with psycopg.connect(autocommit=True, **_super_kw(host, port, "postgres", super_pw)) as c:
        verb = "ALTER" if c.execute(
            "SELECT 1 FROM pg_roles WHERE rolname='mia_app'"
        ).fetchone() else "CREATE"
        # DDL no admite parámetros ($1) para PASSWORD: literal escapado con sql.Literal.
        c.execute(sql.SQL(
            "{verb} ROLE mia_app WITH LOGIN NOSUPERUSER NOBYPASSRLS "
            "NOCREATEDB NOCREATEROLE PASSWORD {pw}"
        ).format(verb=sql.SQL(verb), pw=sql.Literal(app_pw)))

        db_created = False
        if not c.execute("SELECT 1 FROM pg_database WHERE datname=%s", (db,)).fetchone():
            c.execute(f'CREATE DATABASE "{db}" OWNER postgres')
            db_created = True
        c.execute(f'GRANT CONNECT ON DATABASE "{db}" TO mia_app')

    return {"role_verb": verb, "db_created": db_created}


def apply_extensions_and_schema(
    host: str, port: str | int, db: str, super_pw: str, schema_sql_text: str
) -> dict:
    """Extensiones (vector, pgcrypto) + schema.sql, como superusuario. Devuelve
    diagnóstico (encoding, tablas, policies, versión de pgvector)."""
    with psycopg.connect(autocommit=True, **_super_kw(host, port, db, super_pw)) as c:
        c.execute("CREATE EXTENSION IF NOT EXISTS vector")
        c.execute("CREATE EXTENSION IF NOT EXISTS pgcrypto")
        c.execute(schema_sql_text)

        enc = c.execute(
            "SELECT pg_encoding_to_char(encoding) FROM pg_database WHERE datname=%s", (db,)
        ).fetchone()[0]
        ntab = c.execute(
            "SELECT count(*) FROM information_schema.tables WHERE table_schema='public'"
        ).fetchone()[0]
        npol = c.execute(
            "SELECT count(*) FROM pg_policies WHERE schemaname='public'"
        ).fetchone()[0]
        ext = c.execute(
            "SELECT extversion FROM pg_extension WHERE extname='vector'"
        ).fetchone()[0]

    return {"encoding": enc, "tablas_public": ntab, "policies": npol, "pgvector": ext}


def apply_migrations(
    host: str, port: str | int, db: str, super_pw: str, migrations: list[Path]
) -> list[str]:
    """Aplica cada .sql de `migrations`, EN ORDEN, en una sola conexión autocommit
    como superusuario (mia_app no tiene CREATE). Cada archivo ya es idempotente
    (CREATE TABLE IF NOT EXISTS / CREATE OR REPLACE) — no hay tabla de control,
    se re-ejecutan todas siempre (mismo patrón que los init_XXX.py existentes)."""
    applied: list[str] = []
    with psycopg.connect(autocommit=True, **_super_kw(host, port, db, super_pw)) as c:
        for path in migrations:
            c.execute(path.read_text(encoding="utf-8"))
            applied.append(path.name)
    return applied


async def _setup_checkpointer_async(host: str, port: str | int, db: str, super_pw: str) -> list[str]:
    from psycopg.rows import dict_row
    from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver

    kw = dict(host=host, port=port, dbname=db, user="postgres", password=super_pw,
              autocommit=True, row_factory=dict_row)
    async with await psycopg.AsyncConnection.connect(**kw) as conn:
        saver = AsyncPostgresSaver(conn)
        await saver.setup()  # CREATE TABLE IF NOT EXISTS ... (como postgres)
        await conn.execute(_CHECKPOINT_GRANT_SQL)
        rows = await (await conn.execute(
            "SELECT tablename FROM pg_tables WHERE schemaname='public' "
            "AND tablename LIKE 'checkpoint%' ORDER BY tablename"
        )).fetchall()
    return [r["tablename"] for r in rows]


def setup_checkpointer(host: str, port: str | int, db: str, super_pw: str) -> list[str]:
    """Tablas de checkpoint de LangGraph + GRANT DML a mia_app. Devuelve los
    nombres de tabla 'checkpoint%' encontrados. Síncrono: psycopg async no corre
    sobre el ProactorEventLoop por defecto de Windows, así que fijamos la
    política de selector ANTES de crear el loop de asyncio.run()."""
    if sys.platform == "win32":
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
    return asyncio.run(_setup_checkpointer_async(host, port, db, super_pw))
