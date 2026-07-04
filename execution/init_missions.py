"""
Mia · init_missions.py — migración del tablero de misión por expediente (CP-E5, Ola 5).

Aplica backend/mia/db/migrations/024_missions.sql como `postgres` y verifica que
`missions` y `mission_milestones` (por tenant, RLS) existan. Mismo patrón que
init_personas.py. Idempotente.

    .venv\\Scripts\\python.exe execution\\init_missions.py
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

import psycopg
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[1]
load_dotenv(ROOT / ".env")
MIGRATION = ROOT / "backend" / "mia" / "db" / "migrations" / "024_missions.sql"

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
    print("[OK] 024_missions.sql aplicado (rol postgres)")
    with psycopg.connect(autocommit=True, **_kw("postgres", SUPER_PW)) as c:
        for tbl in ("missions", "mission_milestones"):
            exists = c.execute(
                "SELECT count(*) FROM information_schema.tables WHERE table_name=%s",
                (tbl,),
            ).fetchone()[0]
            print(f"[INFO] {tbl} existe={bool(exists)}")
    print("DONE init_missions")


if __name__ == "__main__":
    main()
