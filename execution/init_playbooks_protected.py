"""
Mia · init_playbooks_protected.py — migración H.6 (columna `protected` en playbooks).

Aplica backend/mia/db/migrations/014_playbooks_protected.sql como `postgres` y verifica que la
columna `protected` exista con DEFAULT false.

Idempotente. `apply()` se importa desde el gate. Standalone:
    .venv\\Scripts\\python.exe execution\\init_playbooks_protected.py
"""
from __future__ import annotations
import os
import sys
from pathlib import Path

import psycopg
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[1]
load_dotenv(ROOT / ".env")
MIGRATION = ROOT / "backend" / "mia" / "db" / "migrations" / "014_playbooks_protected.sql"

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

HOST = os.getenv("PG_HOST", "127.0.0.1")
PORT = os.getenv("PG_PORT", "5432")
DB = os.getenv("PG_DB", "mia")
SUPER_PW = os.getenv("PG_PASSWORD", "")


def apply() -> None:
    """Aplica 014_playbooks_protected.sql como postgres. Lanza si falta PG_PASSWORD."""
    if not SUPER_PW:
        raise RuntimeError("falta PG_PASSWORD en .env (superusuario para la migración)")
    kw = dict(host=HOST, port=PORT, dbname=DB, user="postgres", password=SUPER_PW)
    with psycopg.connect(autocommit=True, **kw) as c:
        c.execute(MIGRATION.read_text(encoding="utf-8"))


def main() -> None:
    apply()
    print("[OK] 014_playbooks_protected.sql aplicado (rol postgres)")
    kw = dict(host=HOST, port=PORT, dbname=DB, user="postgres", password=SUPER_PW)
    with psycopg.connect(autocommit=True, **kw) as c:
        col = c.execute(
            "SELECT data_type, column_default FROM information_schema.columns "
            "WHERE table_name='playbooks' AND column_name='protected'").fetchone()
        print(f"[INFO] playbooks.protected: type={col[0] if col else None}  default={col[1] if col else None}")
    print("DONE init_playbooks_protected")


if __name__ == "__main__":
    main()
