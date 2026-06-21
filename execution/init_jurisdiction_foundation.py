"""
Mia · init_jurisdiction_foundation.py — aplica 011_jurisdiction_foundation.sql (Fase 0.C).

Aplica la migración como `postgres` (mia_app NO tiene ALTER/CREATE). Hace la jurisdicción
un eje de primera clase (legal_norms/jurisprudence), habilita el versionado temporal de
normas y crea audit_logs (RLS por-tenant). Idempotente: re-ejecutable.

    .venv\\Scripts\\python.exe execution\\init_jurisdiction_foundation.py
"""
from __future__ import annotations
import os
import sys
from pathlib import Path

import psycopg
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[1]          # .../mia
load_dotenv(ROOT / ".env")
MIGRATION = ROOT / "backend" / "mia" / "db" / "migrations" / "011_jurisdiction_foundation.sql"

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

HOST = os.getenv("PG_HOST", "127.0.0.1")
PORT = os.getenv("PG_PORT", "5432")
DB = os.getenv("PG_DB", "mia")
SUPER_PW = os.getenv("PG_PASSWORD", "")


def apply() -> None:
    """Aplica 011 como postgres. Lanza si falta PG_PASSWORD."""
    if not SUPER_PW:
        raise RuntimeError("falta PG_PASSWORD en .env (superusuario para la migración)")
    kw = dict(host=HOST, port=PORT, dbname=DB, user="postgres", password=SUPER_PW)
    with psycopg.connect(autocommit=True, **kw) as c:
        c.execute(MIGRATION.read_text(encoding="utf-8"))


def main() -> int:
    apply()
    print("011_jurisdiction_foundation.sql aplicada OK (jurisdicción + versionado temporal + audit_logs).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
