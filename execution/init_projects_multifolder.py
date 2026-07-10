"""
Mia · init_projects_multifolder.py — migración de PROYECTOS + MULTI-CARPETA (Bloque A).

Aplica backend/mia/db/migrations/028_projects_multifolder.sql como `postgres` y verifica
que `matters` tenga `kind`, que `documents` tenga `source_id`/`body`, que el CHECK de
origin acepte 'mia' y que el backfill no haya dejado docs de carpeta sin fuente cuando
su expediente tiene una. Mismo patrón que init_matter_folders.py.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

import psycopg
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[1]
load_dotenv(ROOT / ".env")
MIGRATION = ROOT / "backend" / "mia" / "db" / "migrations" / "028_projects_multifolder.sql"

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
    print("[OK] 028_projects_multifolder.sql aplicado (rol postgres)")
    with psycopg.connect(autocommit=True, **_kw("postgres", SUPER_PW)) as c:
        cols_matters = {r[0] for r in c.execute(
            "SELECT column_name FROM information_schema.columns "
            "WHERE table_schema='public' AND table_name='matters'"
        ).fetchall()}
        cols_doc = {r[0] for r in c.execute(
            "SELECT column_name FROM information_schema.columns "
            "WHERE table_schema='public' AND table_name='documents'"
        ).fetchall()}
        origin_check = c.execute(
            "SELECT pg_get_constraintdef(oid) FROM pg_constraint "
            "WHERE conname='ck_documents_origin' AND conrelid='public.documents'::regclass"
        ).fetchone()
        orphans = c.execute(
            "SELECT COUNT(*) FROM documents d "
            "WHERE d.origin='folder' AND d.source_id IS NULL "
            "AND EXISTS (SELECT 1 FROM local_folder_sources s "
            "            WHERE s.matter_id = d.matter_id AND s.kind='matters')"
        ).fetchone()
        print(f"[INFO] matters: kind presente={'kind' in cols_matters}")
        print(f"[INFO] documents: source_id/body presentes="
              f"{ {'source_id', 'body'}.issubset(cols_doc) }")
        print(f"[INFO] ck_documents_origin acepta 'mia'="
              f"{bool(origin_check and 'mia' in origin_check[0])}")
        print(f"[INFO] docs de carpeta sin fuente (con fuente disponible)={orphans[0]}")
    print("DONE init_projects_multifolder")


if __name__ == "__main__":
    main()
