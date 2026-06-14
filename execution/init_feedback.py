"""
Mia · init_feedback.py — migración del Feedback processor (Módulo 3e · decisión #19).

Aplica backend/mia/db/migrations/006_feedback_proposals.sql como `postgres` y verifica que las
2 tablas (`feedback_proposals`, `processed_traces_watermark`) existan con RLS y mia_app INSERT.

Idempotente. `apply()` se importa desde el gate. Standalone:
    .venv\\Scripts\\python.exe execution\\init_feedback.py
"""
from __future__ import annotations
import os
import sys
from pathlib import Path

import psycopg
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[1]
load_dotenv(ROOT / ".env")
MIGRATION = ROOT / "backend" / "mia" / "db" / "migrations" / "006_feedback_proposals.sql"

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

HOST = os.getenv("PG_HOST", "127.0.0.1")
PORT = os.getenv("PG_PORT", "5432")
DB = os.getenv("PG_DB", "mia")
SUPER_PW = os.getenv("PG_PASSWORD", "")

_TABLES = ("feedback_proposals", "processed_traces_watermark")


def apply() -> None:
    """Aplica 006_feedback_proposals.sql como postgres. Lanza si falta PG_PASSWORD."""
    if not SUPER_PW:
        raise RuntimeError("falta PG_PASSWORD en .env (superusuario para la migración)")
    kw = dict(host=HOST, port=PORT, dbname=DB, user="postgres", password=SUPER_PW)
    with psycopg.connect(autocommit=True, **kw) as c:
        c.execute(MIGRATION.read_text(encoding="utf-8"))


def main() -> None:
    apply()
    print("[OK] 006_feedback_proposals.sql aplicado (rol postgres)")
    kw = dict(host=HOST, port=PORT, dbname=DB, user="postgres", password=SUPER_PW)
    with psycopg.connect(autocommit=True, **kw) as c:
        for t in _TABLES:
            ins = c.execute(
                "SELECT has_table_privilege('mia_app', %s, 'INSERT')", (f"public.{t}",)
            ).fetchone()[0]
            rls = c.execute(
                "SELECT relrowsecurity FROM pg_class "
                "WHERE relname=%s AND relnamespace='public'::regnamespace", (t,)
            ).fetchone()[0]
            print(f"[INFO] {t}: mia_app INSERT={ins}  RLS={rls}")
    print("DONE init_feedback")


if __name__ == "__main__":
    main()
