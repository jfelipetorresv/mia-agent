"""
Mia · init_knowledge_stores.py — migración de los knowledge stores (Módulo 3c · decisión #17).

Aplica backend/mia/db/migrations/004_knowledge_stores.sql como `postgres` (mia_app NO tiene
CREATE) y verifica que las 2 tablas (`knowledge_chunks`, `obsidian_file_hashes`) existan con
RLS habilitado y mia_app con INSERT.

Idempotente: re-ejecutable. `apply()` se puede importar desde el gate. Standalone:
    .venv\\Scripts\\python.exe execution\\init_knowledge_stores.py
"""
from __future__ import annotations
import os
import sys
from pathlib import Path

import psycopg
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[1]          # .../mia
load_dotenv(ROOT / ".env")
MIGRATION = ROOT / "backend" / "mia" / "db" / "migrations" / "004_knowledge_stores.sql"

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

HOST = os.getenv("PG_HOST", "127.0.0.1")
PORT = os.getenv("PG_PORT", "5432")
DB = os.getenv("PG_DB", "mia")
SUPER_PW = os.getenv("PG_PASSWORD", "")

_TABLES = ("knowledge_chunks", "obsidian_file_hashes")


def apply() -> None:
    """Aplica 004_knowledge_stores.sql como postgres. Lanza si falta PG_PASSWORD."""
    if not SUPER_PW:
        raise RuntimeError("falta PG_PASSWORD en .env (superusuario para la migración)")
    kw = dict(host=HOST, port=PORT, dbname=DB, user="postgres", password=SUPER_PW)
    with psycopg.connect(autocommit=True, **kw) as c:
        c.execute(MIGRATION.read_text(encoding="utf-8"))


def main() -> None:
    apply()
    print("[OK] 004_knowledge_stores.sql aplicado (rol postgres)")
    kw = dict(host=HOST, port=PORT, dbname=DB, user="postgres", password=SUPER_PW)
    with psycopg.connect(autocommit=True, **kw) as c:
        tabs = c.execute(
            "SELECT table_name FROM information_schema.tables "
            "WHERE table_schema='public' AND table_name = ANY(%s) ORDER BY table_name",
            (list(_TABLES),),
        ).fetchall()
        print(f"[INFO] tablas knowledge stores: {', '.join(r[0] for r in tabs)}")
        for t in _TABLES:
            ins = c.execute(
                "SELECT has_table_privilege('mia_app', %s, 'INSERT') AS ok", (f"public.{t}",)
            ).fetchone()[0]
            rls = c.execute(
                "SELECT relrowsecurity FROM pg_class "
                "WHERE relname=%s AND relnamespace='public'::regnamespace", (t,)
            ).fetchone()[0]
            print(f"[INFO] {t}: mia_app INSERT={ins}  RLS={rls}")
    print("DONE init_knowledge_stores")


if __name__ == "__main__":
    main()
