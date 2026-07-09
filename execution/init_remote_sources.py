"""
Mia · init_remote_sources.py — migración de cimientos de "fuentes remotas del expediente"
(Fase 1: OAuth multi-proveedor + tablas de OneDrive remoto).

Aplica backend/mia/db/migrations/027_remote_sources.sql como `postgres` y verifica que
`tenant_oauth_tokens` tenga PK compuesta (tenant_id, provider), que `documents.origin`
acepte 'mail'/'drive', y que `remote_drive_sources`/`remote_file_hashes` existan.
Mismo patrón que init_mailbox.py / init_matter_folders.py. Idempotente.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

import psycopg
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[1]
load_dotenv(ROOT / ".env")
MIGRATION = ROOT / "backend" / "mia" / "db" / "migrations" / "027_remote_sources.sql"

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
    print("[OK] 027_remote_sources.sql aplicado (rol postgres)")
    with psycopg.connect(autocommit=True, **_kw("postgres", SUPER_PW)) as c:
        pk_cols = [r[0] for r in c.execute(
            "SELECT a.attname FROM pg_constraint co "
            "JOIN unnest(co.conkey) WITH ORDINALITY AS k(attnum, ord) ON true "
            "JOIN pg_attribute a ON a.attrelid = co.conrelid AND a.attnum = k.attnum "
            "WHERE co.conrelid = 'public.tenant_oauth_tokens'::regclass AND co.contype = 'p' "
            "ORDER BY k.ord"
        ).fetchall()]
        print(f"[INFO] tenant_oauth_tokens PK = {pk_cols} "
              f"(esperado ['tenant_id', 'provider'])")
        origin_ck = c.execute(
            "SELECT pg_get_constraintdef(oid) FROM pg_constraint "
            "WHERE conname = 'ck_documents_origin' AND conrelid = 'public.documents'::regclass"
        ).fetchone()
        print(f"[INFO] documents.origin CHECK = {origin_ck[0] if origin_ck else 'AUSENTE'}")
        for table in ("remote_drive_sources", "remote_file_hashes"):
            exists = c.execute(
                "SELECT count(*) FROM information_schema.tables WHERE table_name=%s",
                (table,),
            ).fetchone()[0]
            print(f"[INFO] {table} existe={bool(exists)}")
    print("DONE init_remote_sources")


if __name__ == "__main__":
    main()
