"""
Mia · init_warroom.py — migración de la Sala de estrategia (warroom).

Aplica backend/mia/db/migrations/033_warroom_results.sql como `postgres` y verifica que
`warroom_results` (por tenant, RLS) exista. Mismo patrón que init_personas.py /
init_missions.py. Idempotente. (En el instalador, db_bootstrap.apply_migrations la aplica
automáticamente al enumerar migrations/*.sql — este script es el equivalente manual en dev.)
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

import psycopg
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[1]
load_dotenv(ROOT / ".env")
MIGRATION = ROOT / "backend" / "mia" / "db" / "migrations" / "033_warroom_results.sql"

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
    print("[OK] 033_warroom_results.sql aplicado (rol postgres)")
    with psycopg.connect(autocommit=True, **_kw("postgres", SUPER_PW)) as c:
        exists = c.execute(
            "SELECT count(*) FROM information_schema.tables WHERE table_name=%s",
            ("warroom_results",),
        ).fetchone()[0]
        print(f"[INFO] warroom_results existe={bool(exists)}")
    print("DONE init_warroom")


if __name__ == "__main__":
    main()
