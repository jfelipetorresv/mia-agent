"""
Mia · init_curator_conflicts.py — migración 038 ("contradicción antes que fusión").

Aplica backend/mia/db/migrations/038_curator_conflicts.sql como `postgres` y verifica que
`curator_proposals` tenga las columnas kind/conflict/resolution con sus CHECK. La DB de dev es
ANTERIOR al ledger de migraciones, por eso existe este runner (mismo patrón que
init_curator_proposals.py / init_matter_agent_consent.py).

Idempotente. `apply()` se importa desde los gates. Standalone:
    .venv\\Scripts\\python.exe execution\\init_curator_conflicts.py
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

import psycopg
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[1]
load_dotenv(ROOT / ".env")
MIGRATION = ROOT / "backend" / "mia" / "db" / "migrations" / "038_curator_conflicts.sql"

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

HOST = os.getenv("PG_HOST", "127.0.0.1")
PORT = os.getenv("PG_PORT", "5432")
DB = os.getenv("PG_DB", "mia")
SUPER_PW = os.getenv("PG_PASSWORD", "")

_TABLE = "curator_proposals"


def _kw() -> dict:
    return dict(host=HOST, port=PORT, dbname=DB, user="postgres", password=SUPER_PW)


def apply() -> None:
    """Aplica 038_curator_conflicts.sql como postgres. Lanza si falta PG_PASSWORD."""
    if not SUPER_PW:
        raise RuntimeError("falta PG_PASSWORD en .env (superusuario para la migración)")
    with psycopg.connect(autocommit=True, **_kw()) as c:
        c.execute(MIGRATION.read_text(encoding="utf-8"))


def main() -> None:
    apply()
    print("[OK] 038_curator_conflicts.sql aplicado (rol postgres)")
    with psycopg.connect(autocommit=True, **_kw()) as c:
        cols = {r[0] for r in c.execute(
            "SELECT column_name FROM information_schema.columns "
            "WHERE table_schema='public' AND table_name=%s", (_TABLE,)).fetchall()}
        print(f"[INFO] {_TABLE}: kind={'kind' in cols} conflict={'conflict' in cols} "
              f"resolution={'resolution' in cols}")
        rls = c.execute(
            "SELECT relrowsecurity, relforcerowsecurity FROM pg_class "
            "WHERE oid = 'public.curator_proposals'::regclass").fetchone()
        print(f"[INFO] {_TABLE}: RLS enable={rls[0]} force={rls[1]}")
    print("DONE init_curator_conflicts")


if __name__ == "__main__":
    main()
