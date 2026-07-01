"""
Mia · init_curator_proposals.py — migración H.2 (Curator dry-run → HITL, cierra Riesgo #19).

Aplica backend/mia/db/migrations/012_curator_proposals.sql como `postgres` y verifica que la
tabla `curator_proposals` exista con RLS y mia_app INSERT/UPDATE.

Idempotente. `apply()` se importa desde el gate. Standalone:
    .venv\\Scripts\\python.exe execution\\init_curator_proposals.py
"""
from __future__ import annotations
import os
import sys
from pathlib import Path

import psycopg
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[1]
load_dotenv(ROOT / ".env")
MIGRATION = ROOT / "backend" / "mia" / "db" / "migrations" / "012_curator_proposals.sql"

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

HOST = os.getenv("PG_HOST", "127.0.0.1")
PORT = os.getenv("PG_PORT", "5432")
DB = os.getenv("PG_DB", "mia")
SUPER_PW = os.getenv("PG_PASSWORD", "")

_TABLE = "curator_proposals"


def apply() -> None:
    """Aplica 012_curator_proposals.sql como postgres. Lanza si falta PG_PASSWORD."""
    if not SUPER_PW:
        raise RuntimeError("falta PG_PASSWORD en .env (superusuario para la migración)")
    kw = dict(host=HOST, port=PORT, dbname=DB, user="postgres", password=SUPER_PW)
    with psycopg.connect(autocommit=True, **kw) as c:
        c.execute(MIGRATION.read_text(encoding="utf-8"))


def main() -> None:
    apply()
    print("[OK] 012_curator_proposals.sql aplicado (rol postgres)")
    kw = dict(host=HOST, port=PORT, dbname=DB, user="postgres", password=SUPER_PW)
    with psycopg.connect(autocommit=True, **kw) as c:
        ins = c.execute(
            "SELECT has_table_privilege('mia_app', %s, 'INSERT')", (f"public.{_TABLE}",)
        ).fetchone()[0]
        upd = c.execute(
            "SELECT has_table_privilege('mia_app', %s, 'UPDATE')", (f"public.{_TABLE}",)
        ).fetchone()[0]
        rls = c.execute(
            "SELECT relrowsecurity FROM pg_class "
            "WHERE relname=%s AND relnamespace='public'::regnamespace", (_TABLE,)
        ).fetchone()[0]
        print(f"[INFO] {_TABLE}: mia_app INSERT={ins} UPDATE={upd}  RLS={rls}")
    print("DONE init_curator_proposals")


if __name__ == "__main__":
    main()
