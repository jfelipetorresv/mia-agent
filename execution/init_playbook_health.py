"""
Mia · init_playbook_health.py — migración de salud de guías (Meta E · Mitad 1).

Aplica backend/mia/db/migrations/044_playbook_health.sql como `postgres` y verifica que
`playbooks` tenga las columnas health_status/health_checked_at/health_report. Mismo patrón
que execution/init_playbook_versions.py. Idempotente.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

import psycopg
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[1]
load_dotenv(ROOT / ".env")
MIGRATION = ROOT / "backend" / "mia" / "db" / "migrations" / "044_playbook_health.sql"

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
    print("[OK] 044_playbook_health.sql aplicado (rol postgres)")
    with psycopg.connect(autocommit=True, **_kw("postgres", SUPER_PW)) as c:
        cols = c.execute(
            "SELECT column_name FROM information_schema.columns "
            "WHERE table_name='playbooks' AND column_name IN "
            "('health_status', 'health_checked_at', 'health_report')"
        ).fetchall()
        names = {r[0] for r in cols}
        print(f"[INFO] playbooks columnas de salud presentes={sorted(names)}")
    print("DONE init_playbook_health")


if __name__ == "__main__":
    main()
