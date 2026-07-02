"""
Mia · init_local_folders.py — migración de CARPETAS DE TRABAJO (CP-C1, Pilar C).

Aplica backend/mia/db/migrations/016_local_folders.sql como `postgres` y verifica que
`local_folder_sources` y `local_file_hashes` existan con RLS y privilegios para
`mia_app`. Mismo patrón que init_assistant.py.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

import psycopg
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[1]
load_dotenv(ROOT / ".env")
MIGRATION = ROOT / "backend" / "mia" / "db" / "migrations" / "016_local_folders.sql"

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

HOST = os.getenv("PG_HOST", "127.0.0.1")
PORT = os.getenv("PG_PORT", "5432")
DB = os.getenv("PG_DB", "mia")
SUPER_PW = os.getenv("PG_PASSWORD", "")


def _kw(user: str, password: str) -> dict:
    return dict(host=HOST, port=PORT, dbname=DB, user=user, password=password)


def apply() -> None:
    if not SUPER_PW:
        raise RuntimeError("falta PG_PASSWORD en .env (superusuario para la migración)")
    with psycopg.connect(autocommit=True, **_kw("postgres", SUPER_PW)) as c:
        c.execute(MIGRATION.read_text(encoding="utf-8"))


def main() -> None:
    apply()
    print("[OK] 016_local_folders.sql aplicado (rol postgres)")
    with psycopg.connect(autocommit=True, **_kw("postgres", SUPER_PW)) as c:
        for table in ("local_folder_sources", "local_file_hashes"):
            priv = c.execute(
                "SELECT has_table_privilege('mia_app', %s, 'INSERT')", (f"public.{table}",)
            ).fetchone()[0]
            rls = c.execute(
                "SELECT relrowsecurity AND relforcerowsecurity FROM pg_class "
                "WHERE relname=%s AND relnamespace='public'::regnamespace",
                (table,),
            ).fetchone()[0]
            print(f"[INFO] {table}: mia_app INSERT={priv}  RLS(force)={rls}")
    print("DONE init_local_folders")


if __name__ == "__main__":
    main()
