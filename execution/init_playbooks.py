"""
Mia · init_playbooks.py — migración de la tabla `playbooks` (Módulo 3b · decisión #18).

Aplica backend/mia/db/migrations/005_playbooks.sql como `postgres` (mia_app NO tiene CREATE) y
verifica que la tabla exista con RLS habilitado y mia_app con INSERT.

Idempotente: re-ejecutable. `apply()` se importa desde el gate. Standalone:
    .venv\\Scripts\\python.exe execution\\init_playbooks.py
"""
from __future__ import annotations
import os
import sys
from pathlib import Path

import psycopg
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[1]
load_dotenv(ROOT / ".env")
MIGRATION = ROOT / "backend" / "mia" / "db" / "migrations" / "005_playbooks.sql"

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

HOST = os.getenv("PG_HOST", "127.0.0.1")
PORT = os.getenv("PG_PORT", "5432")
DB = os.getenv("PG_DB", "mia")
SUPER_PW = os.getenv("PG_PASSWORD", "")


def apply() -> None:
    """Aplica 005_playbooks.sql como postgres. Lanza si falta PG_PASSWORD."""
    if not SUPER_PW:
        raise RuntimeError("falta PG_PASSWORD en .env (superusuario para la migración)")
    kw = dict(host=HOST, port=PORT, dbname=DB, user="postgres", password=SUPER_PW)
    with psycopg.connect(autocommit=True, **kw) as c:
        c.execute(MIGRATION.read_text(encoding="utf-8"))


def main() -> None:
    apply()
    print("[OK] 005_playbooks.sql aplicado (rol postgres)")
    kw = dict(host=HOST, port=PORT, dbname=DB, user="postgres", password=SUPER_PW)
    with psycopg.connect(autocommit=True, **kw) as c:
        ins = c.execute(
            "SELECT has_table_privilege('mia_app', 'public.playbooks', 'INSERT')"
        ).fetchone()[0]
        rls = c.execute(
            "SELECT relrowsecurity FROM pg_class "
            "WHERE relname='playbooks' AND relnamespace='public'::regnamespace"
        ).fetchone()[0]
        print(f"[INFO] playbooks: mia_app INSERT={ins}  RLS={rls}")
    print("DONE init_playbooks")


if __name__ == "__main__":
    main()
