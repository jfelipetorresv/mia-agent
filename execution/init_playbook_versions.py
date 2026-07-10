"""
Mia · init_playbook_versions.py — migración del historial de playbooks (Bloque B · B0).

Aplica backend/mia/db/migrations/029_playbook_versions.sql como `postgres` y verifica que
`playbook_versions` exista con RLS activa. Mismo patrón que init_projects_multifolder.py /
init_personas.py. Idempotente.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

import psycopg
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[1]
load_dotenv(ROOT / ".env")
MIGRATION = ROOT / "backend" / "mia" / "db" / "migrations" / "029_playbook_versions.sql"

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
    print("[OK] 029_playbook_versions.sql aplicado (rol postgres)")
    with psycopg.connect(autocommit=True, **_kw("postgres", SUPER_PW)) as c:
        exists = c.execute(
            "SELECT count(*) FROM information_schema.tables WHERE table_name=%s",
            ("playbook_versions",),
        ).fetchone()[0]
        rls = c.execute(
            "SELECT relrowsecurity, relforcerowsecurity FROM pg_class WHERE relname=%s",
            ("playbook_versions",),
        ).fetchone()
        print(f"[INFO] playbook_versions existe={bool(exists)}")
        print(f"[INFO] playbook_versions RLS enable/force={rls}")
    print("DONE init_playbook_versions")


if __name__ == "__main__":
    main()
