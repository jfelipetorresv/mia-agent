"""
Mia · init_traces_search.py — migración H.3 (índice FTS de trazas para session_search sin LLM).

Aplica backend/mia/db/migrations/013_traces_search.sql como `postgres` y verifica que la tabla
`traces` exista con RLS, columna generada `content_tsv` y el índice GIN.

Idempotente. `apply()` se importa desde el gate. Standalone:
    .venv\\Scripts\\python.exe execution\\init_traces_search.py
"""
from __future__ import annotations
import os
import sys
from pathlib import Path

import psycopg
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[1]
load_dotenv(ROOT / ".env")
MIGRATION = ROOT / "backend" / "mia" / "db" / "migrations" / "013_traces_search.sql"

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

HOST = os.getenv("PG_HOST", "127.0.0.1")
PORT = os.getenv("PG_PORT", "5432")
DB = os.getenv("PG_DB", "mia")
SUPER_PW = os.getenv("PG_PASSWORD", "")


def apply() -> None:
    """Aplica 013_traces_search.sql como postgres. Lanza si falta PG_PASSWORD."""
    if not SUPER_PW:
        raise RuntimeError("falta PG_PASSWORD en .env (superusuario para la migración)")
    kw = dict(host=HOST, port=PORT, dbname=DB, user="postgres", password=SUPER_PW)
    with psycopg.connect(autocommit=True, **kw) as c:
        c.execute(MIGRATION.read_text(encoding="utf-8"))


def main() -> None:
    apply()
    print("[OK] 013_traces_search.sql aplicado (rol postgres)")
    kw = dict(host=HOST, port=PORT, dbname=DB, user="postgres", password=SUPER_PW)
    with psycopg.connect(autocommit=True, **kw) as c:
        ins = c.execute(
            "SELECT has_table_privilege('mia_app', 'public.traces', 'INSERT')").fetchone()[0]
        rls = c.execute(
            "SELECT relrowsecurity FROM pg_class "
            "WHERE relname='traces' AND relnamespace='public'::regnamespace").fetchone()[0]
        gin = c.execute(
            "SELECT count(*) FROM pg_indexes "
            "WHERE tablename='traces' AND indexname='idx_traces_content_tsv'").fetchone()[0]
        print(f"[INFO] traces: mia_app INSERT={ins}  RLS={rls}  GIN={bool(gin)}")
    print("DONE init_traces_search")


if __name__ == "__main__":
    main()
