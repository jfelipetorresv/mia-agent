"""
Mia · init_profiles.py — migración del perfil del despacho (Fase 3 backend · decisión #20).

Aplica backend/mia/db/migrations/007_profiles.sql como `postgres` y verifica que `firm_profiles`
exista con RLS y mia_app INSERT. Idempotente. `apply()` se importa desde el gate.
    .venv\\Scripts\\python.exe execution\\init_profiles.py
"""
from __future__ import annotations
import os
import sys
from pathlib import Path

import psycopg
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[1]
load_dotenv(ROOT / ".env")
MIGRATION = ROOT / "backend" / "mia" / "db" / "migrations" / "007_profiles.sql"

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

HOST = os.getenv("PG_HOST", "127.0.0.1")
PORT = os.getenv("PG_PORT", "5432")
DB = os.getenv("PG_DB", "mia")
SUPER_PW = os.getenv("PG_PASSWORD", "")


def apply() -> None:
    if not SUPER_PW:
        raise RuntimeError("falta PG_PASSWORD en .env (superusuario para la migración)")
    kw = dict(host=HOST, port=PORT, dbname=DB, user="postgres", password=SUPER_PW)
    with psycopg.connect(autocommit=True, **kw) as c:
        c.execute(MIGRATION.read_text(encoding="utf-8"))


def main() -> None:
    apply()
    print("[OK] 007_profiles.sql aplicado (rol postgres)")
    kw = dict(host=HOST, port=PORT, dbname=DB, user="postgres", password=SUPER_PW)
    with psycopg.connect(autocommit=True, **kw) as c:
        ins = c.execute(
            "SELECT has_table_privilege('mia_app', 'public.firm_profiles', 'INSERT')").fetchone()[0]
        rls = c.execute(
            "SELECT relrowsecurity FROM pg_class "
            "WHERE relname='firm_profiles' AND relnamespace='public'::regnamespace").fetchone()[0]
        print(f"[INFO] firm_profiles: mia_app INSERT={ins}  RLS={rls}")
    print("DONE init_profiles")


if __name__ == "__main__":
    main()
