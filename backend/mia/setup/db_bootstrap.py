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
import hashlib
import re
import sys
from pathlib import Path
from typing import Callable

# psycopg se importa dentro de las funciones que tocan Postgres. El SHA-256
# de migraciones (gate estático / --sellar) no debe exigir el driver: CI lo
# corre antes de `pip install './backend[full]'`.

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

_MIGRATIONS_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS public.mia_schema_migrations (
  filename    text PRIMARY KEY,
  sha256      text NOT NULL,
  applied_at  timestamptz NOT NULL DEFAULT now()
)
"""

# Candado de sesión: impide que dos arranques intenten actualizar el mismo
# esquema a la vez. El valor es propio de Mia y estable entre versiones.
_MIGRATION_LOCK_KEY = 0x4D49414D494752  # "MIAMIGR"


class MigrationChecksumError(RuntimeError):
    """Una migración aplicada cambió de contenido.

    Alterar un archivo histórico vuelve imposible saber qué estructura tiene una
    instalación existente. La salida segura es crear una migración nueva, no
    volver a ejecutar silenciosamente la anterior.
    """


class MigrationPrefixCollisionError(RuntimeError):
    """Dos migraciones comparten el mismo número de prefijo (p. ej. dos `038_`).

    El orden del ledger y el checksum del gate F0 dependen de que el prefijo
    numérico sea único y monótono. Dos archivos con el mismo prefijo hacen que el
    orden dependa del resto del nombre (frágil) y que un agente que trabaje en
    paralelo pise el número de otro. La salida segura es renumerar una de las dos
    antes de aplicar nada. Regla: el número se reserva al EMPEZAR, no al escribir.
    """


_MIGRATION_PREFIX_RE = re.compile(r"^(\d+)_")


def _assert_unique_prefixes(migrations: list[Path]) -> None:
    """Falla si dos migraciones comparten el prefijo numérico.

    Preflight barato y determinista: corre antes de tocar el esquema para que la
    colisión (incidente real de la sesión 48: dos `038`) se detecte como error
    con explicación en vez de romper el orden del ledger a mitad de camino.
    """
    by_prefix: dict[str, list[str]] = {}
    for path in migrations:
        match = _MIGRATION_PREFIX_RE.match(path.name)
        if match is None:
            continue  # archivos sin prefijo numérico no participan del orden
        by_prefix.setdefault(match.group(1), []).append(path.name)
    colisiones = {p: names for p, names in by_prefix.items() if len(names) > 1}
    if colisiones:
        detalle = "; ".join(
            f"{prefix}: {', '.join(sorted(names))}" for prefix, names in sorted(colisiones.items())
        )
        raise MigrationPrefixCollisionError(
            "Números de migración duplicados — renumera una de cada par antes de "
            f"aplicar ({detalle})."
        )


def _lf_bytes(data: bytes) -> bytes:
    """Normaliza saltos de línea a LF. Git en Windows puede materializar CRLF."""
    return data.replace(b"\r\n", b"\n").replace(b"\r", b"\n")


def _digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def migration_sha256(path: Path) -> str:
    """SHA-256 canónico del SQL (LF). Independiente de CRLF vs LF en disco.

    El ledger de instalaciones viejas puede haber registrado el hash CRLF o el
    LF del mismo archivo: ``apply_migrations`` acepta ambos y, si hace falta,
    reescribe el registro al canónico. No reejecuta el SQL. Un cambio de
    *contenido* sigue bloqueando (crea una migración nueva).
    """
    return _digest(_lf_bytes(path.read_bytes()))


def _line_ending_aliases(data: bytes) -> set[str]:
    """Hashes que identifican el mismo SQL con distinta convención de newline."""
    lf = _lf_bytes(data)
    crlf = lf.replace(b"\n", b"\r\n")
    return {_digest(data), _digest(lf), _digest(crlf)}


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
    import psycopg
    from psycopg import sql

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
    import psycopg

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
    host: str,
    port: str | int,
    db: str,
    super_pw: str,
    migrations: list[Path],
    *,
    before_first_pending: Callable[[], None] | None = None,
) -> list[str]:
    """Aplica solo migraciones pendientes, de forma reanudable y verificable.

    Cada archivo SQL y su registro en ``mia_schema_migrations`` viven en UNA
    transacción. Si el SQL falla o el proceso se corta, ese archivo queda sin
    aplicar y el siguiente arranque puede reintentarlo. Un advisory lock evita
    dos migradores simultáneos. Los archivos ya aplicados deben conservar el
    mismo SQL; el SHA-256 canónico es LF. Un checkout Windows (CRLF) contra un
    ledger Linux (LF), o al revés, se acepta y se reescribe el registro al
    canónico — nunca se reejecuta el SQL ni se tocan datos. Si el *contenido*
    cambió, se bloquea el arranque: crea una migración nueva.

    Compatibilidad: instalaciones anteriores no tienen ledger. En la primera
    adopción se vuelven a ejecutar los SQL históricos (todos son idempotentes,
    que era también el contrato anterior) y quedan registrados.
    """
    # Defensa en profundidad: paths.migration_paths() ya ordena, pero este
    # helper también lo garantiza para cualquier llamador futuro.
    import psycopg

    migrations = sorted(migrations, key=lambda path: path.name)
    # Antes de tocar nada: dos migraciones con el mismo prefijo numérico rompen
    # el orden del ledger (incidente real de la sesión 48: dos `038`).
    _assert_unique_prefixes(migrations)
    applied: list[str] = []
    with psycopg.connect(**_super_kw(host, port, db, super_pw)) as c:
        c.execute("SELECT pg_advisory_lock(%s)", (_MIGRATION_LOCK_KEY,))
        try:
            ledger_exists = c.execute(
                "SELECT to_regclass('public.mia_schema_migrations')"
            ).fetchone()[0]
            if ledger_exists:
                rows = c.execute(
                    "SELECT filename, sha256 FROM public.mia_schema_migrations"
                ).fetchall()
                recorded = {str(row[0]): str(row[1]) for row in rows}
            else:
                recorded = {}

            # Preflight COMPLETO antes de tocar el esquema: primero valida todos
            # los checksums históricos y construye la lista pendiente. Así una
            # inconsistencia tardía no aparece después de aplicar otra migración.
            pending: list[tuple[Path, str, str]] = []
            heals: list[tuple[str, str, str]] = []
            for path in migrations:
                raw = path.read_bytes()
                digest = _digest(_lf_bytes(raw))
                previous = recorded.get(path.name)
                if previous is not None:
                    if previous not in _line_ending_aliases(raw):
                        raise MigrationChecksumError(
                            f"La actualización histórica {path.name} cambió después "
                            "de aplicarse. Crea una migración nueva; no modifiques la anterior."
                        )
                    if previous != digest:
                        # Mismo SQL, otro newline. Reescribir el registro; no reejecutar.
                        heals.append((path.name, digest, previous))
                else:
                    migration_sql = path.read_text(encoding="utf-8")
                    if "CONCURRENTLY" in migration_sql.upper():
                        raise ValueError(
                            f"{path.name}: CONCURRENTLY no es compatible con "
                            "el modelo atómico de una transacción por archivo."
                        )
                    pending.append((path, digest, migration_sql))

            # El backup/verificación sucede bajo el MISMO advisory lock y antes
            # de la primera mutación. El callback usa pg_dump en otra conexión;
            # no intenta adquirir este candado y por tanto no se auto-bloquea.
            # Curar checksums de newline no muta el esquema: no dispara backup.
            if pending and before_first_pending is not None:
                before_first_pending()

            # Incluso sin pendientes, una instalación nueva termina con ledger;
            # cuando sí hay pendientes esto ocurre solo DESPUÉS del backup.
            c.execute(_MIGRATIONS_TABLE_SQL)
            for filename, digest, previous in heals:
                c.execute(
                    "UPDATE public.mia_schema_migrations SET sha256 = %s "
                    "WHERE filename = %s AND sha256 = %s",
                    (digest, filename, previous),
                )
            c.commit()

            for path, digest, migration_sql in pending:
                try:
                    c.execute(migration_sql)
                    c.execute(
                        "INSERT INTO public.mia_schema_migrations (filename, sha256) "
                        "VALUES (%s, %s)",
                        (path.name, digest),
                    )
                    c.commit()
                except Exception:
                    c.rollback()
                    raise
                applied.append(path.name)
        finally:
            # El unlock explícito facilita pruebas/reutilización de conexiones;
            # PostgreSQL también lo liberaría al cerrar la sesión. Un error
            # de unlock nunca debe ocultar la causa original de una migración.
            try:
                c.rollback()
                c.execute("SELECT pg_advisory_unlock(%s)", (_MIGRATION_LOCK_KEY,))
                c.commit()
            except Exception:
                c.rollback()
    return applied


async def _setup_checkpointer_async(host: str, port: str | int, db: str, super_pw: str) -> list[str]:
    import psycopg
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
