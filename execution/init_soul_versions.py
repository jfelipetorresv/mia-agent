"""
Mia · init_soul_versions.py — migración del historial de la identidad (SOUL).

Aplica backend/mia/db/migrations/040_soul_versions.sql como `postgres` y verifica que
`soul_versions` exista con RLS forzada y que `feedback_proposals` acepte el tipo
'soul_rule'. Mismo patrón que init_playbook_versions.py. Idempotente.

La base de DEV es anterior al ledger (`mia_schema_migrations`): por eso se aplica con este
script, igual que las demás. En instalaciones nuevas la recoge sola
`setup/paths.migration_paths()` (glob ordenado por nombre).
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

import psycopg
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[1]
load_dotenv(ROOT / ".env")
MIGRATION = ROOT / "backend" / "mia" / "db" / "migrations" / "040_soul_versions.sql"

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
    print("[OK] 040_soul_versions.sql aplicado (rol postgres)")
    with psycopg.connect(autocommit=True, **_kw("postgres", SUPER_PW)) as c:
        exists = c.execute(
            "SELECT count(*) FROM information_schema.tables WHERE table_name=%s",
            ("soul_versions",),
        ).fetchone()[0]
        rls = c.execute(
            "SELECT relrowsecurity, relforcerowsecurity FROM pg_class WHERE relname=%s",
            ("soul_versions",),
        ).fetchone()
        chk = c.execute(
            "SELECT pg_get_constraintdef(oid) FROM pg_constraint "
            "WHERE conname='feedback_proposals_proposal_type_check'",
        ).fetchone()
        print(f"[INFO] soul_versions existe={bool(exists)}")
        print(f"[INFO] soul_versions RLS enable/force={rls}")
        print(f"[INFO] feedback_proposals acepta soul_rule={'soul_rule' in (chk[0] if chk else '')}")
    print("DONE init_soul_versions")


if __name__ == "__main__":
    main()
