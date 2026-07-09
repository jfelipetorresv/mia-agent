"""
Mia · init_matter_folders.py — migración del EXPEDIENTE VINCULADO (Pilar C · carpeta del asunto).

Aplica backend/mia/db/migrations/025_matter_folders.sql como `postgres` y verifica que
`documents` tenga las columnas nuevas (sha256/source_path/origin) y que
`local_folder_sources` tenga `matter_id`. Mismo patrón que init_local_folders.py.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

import psycopg
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[1]
load_dotenv(ROOT / ".env")
MIGRATION = ROOT / "backend" / "mia" / "db" / "migrations" / "025_matter_folders.sql"

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
    print("[OK] 025_matter_folders.sql aplicado (rol postgres)")
    with psycopg.connect(autocommit=True, **_kw("postgres", SUPER_PW)) as c:
        cols_doc = {r[0] for r in c.execute(
            "SELECT column_name FROM information_schema.columns "
            "WHERE table_schema='public' AND table_name='documents'"
        ).fetchall()}
        cols_src = {r[0] for r in c.execute(
            "SELECT column_name FROM information_schema.columns "
            "WHERE table_schema='public' AND table_name='local_folder_sources'"
        ).fetchall()}
        print(f"[INFO] documents: sha256/source_path/origin presentes="
              f"{ {'sha256', 'source_path', 'origin'}.issubset(cols_doc) }")
        print(f"[INFO] local_folder_sources: matter_id presente={'matter_id' in cols_src}")
    print("DONE init_matter_folders")


if __name__ == "__main__":
    main()
