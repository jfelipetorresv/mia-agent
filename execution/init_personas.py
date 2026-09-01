"""
Mia · init_personas.py — migración de las personas jurídicas (CP-E3, Ola 5).

Aplica backend/mia/db/migrations/023_personas.sql como `postgres` y verifica que
`personas` (por tenant, RLS) exista. Mismo patrón que init_dream_prescriptions.py.
Idempotente.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

import psycopg
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[1]
load_dotenv(ROOT / ".env")
MIGRATION = ROOT / "backend" / "mia" / "db" / "migrations" / "023_personas.sql"
# D8 · las capacidades del agente llegaron con la 064. Va DESPUÉS de la 023 y es aditiva
# (ADD COLUMN IF NOT EXISTS), así que aplicarla aquí no retrocede nada: sin ella, el CRUD
# de agentes revienta con «column capabilities does not exist» en una base de dev vieja.
MIGRATION_CAPACIDADES = (
    ROOT / "backend" / "mia" / "db" / "migrations" / "064_persona_capabilities.sql")

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
        c.execute(MIGRATION_CAPACIDADES.read_text(encoding="utf-8"))


def main() -> None:
    apply()
    print("[OK] 023_personas.sql + 064_persona_capabilities.sql aplicados (rol postgres)")
    with psycopg.connect(autocommit=True, **_kw("postgres", SUPER_PW)) as c:
        exists = c.execute(
            "SELECT count(*) FROM information_schema.tables WHERE table_name=%s",
            ("personas",),
        ).fetchone()[0]
        print(f"[INFO] personas existe={bool(exists)}")
    print("DONE init_personas")


if __name__ == "__main__":
    main()
