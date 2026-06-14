"""
Mia · init_db.py — Paso 3 del Módulo 0.
Crea el rol `mia_app`, la base `mia`, las extensiones y aplica schema.sql.
Se ejecuta con el python de mia/.venv. Usa el superusuario `postgres`
(solo migraciones). Idempotente.
"""
from __future__ import annotations
import os
import sys
from pathlib import Path

import psycopg
from psycopg import sql
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[1]          # .../mia
load_dotenv(ROOT / ".env")
SCHEMA = ROOT / "backend" / "mia" / "db" / "schema.sql"

HOST = os.getenv("PG_HOST", "127.0.0.1")
PORT = os.getenv("PG_PORT", "5432")
DB = os.getenv("PG_DB", "mia")
SUPER_PW = os.getenv("PG_PASSWORD", "")
APP_PW = os.getenv("PG_APP_PASSWORD", "")

if not SUPER_PW:
    sys.exit("ERROR: falta PG_PASSWORD en .env")
if not APP_PW:
    sys.exit("ERROR: falta PG_APP_PASSWORD en .env")

def _kw(dbname: str) -> dict:
    # Parámetros por keyword: psycopg escapa los valores (el password de
    # postgres trae caracteres especiales que romperían una URL).
    return dict(host=HOST, port=PORT, dbname=dbname, user="postgres", password=SUPER_PW)


def main() -> None:
    # --- rol + base (en la base de mantenimiento) ---
    with psycopg.connect(autocommit=True, **_kw("postgres")) as c:
        verb = "ALTER" if c.execute(
            "SELECT 1 FROM pg_roles WHERE rolname='mia_app'"
        ).fetchone() else "CREATE"
        # DDL no admite parámetros ($1) para PASSWORD: literal escapado con sql.Literal.
        c.execute(sql.SQL(
            "{verb} ROLE mia_app WITH LOGIN NOSUPERUSER NOBYPASSRLS "
            "NOCREATEDB NOCREATEROLE PASSWORD {pw}"
        ).format(verb=sql.SQL(verb), pw=sql.Literal(APP_PW)))
        print(f"[OK] rol mia_app {'actualizado' if verb == 'ALTER' else 'creado'} "
              "(NOSUPERUSER, NOBYPASSRLS)")

        if not c.execute("SELECT 1 FROM pg_database WHERE datname=%s", (DB,)).fetchone():
            c.execute(f'CREATE DATABASE "{DB}" OWNER postgres')
            print(f"[OK] base {DB} creada")
        else:
            print(f"[OK] base {DB} ya existe")
        c.execute(f'GRANT CONNECT ON DATABASE "{DB}" TO mia_app')

    # --- extensiones + schema (en la base mia) ---
    with psycopg.connect(autocommit=True, **_kw(DB)) as c:
        c.execute("CREATE EXTENSION IF NOT EXISTS vector")
        c.execute("CREATE EXTENSION IF NOT EXISTS pgcrypto")
        c.execute(SCHEMA.read_text(encoding="utf-8"))
        print("[OK] schema.sql aplicado")

        enc = c.execute(
            "SELECT pg_encoding_to_char(encoding) FROM pg_database WHERE datname=%s",
            (DB,),
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
        print(f"[INFO] encoding={enc}  tablas_public={ntab}  policies={npol}  pgvector={ext}")
        if enc.upper() != "UTF8":
            print(f"[WARN] la base {DB} no es UTF8 ({enc}); revisar para texto jurídico en producción.")

    print("DONE init_db")


if __name__ == "__main__":
    main()
