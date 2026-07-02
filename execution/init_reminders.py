"""
Mia · init_reminders.py — migración de RECORDATORIOS (CP-B3, Pilar B).

Aplica backend/mia/db/migrations/017_reminders.sql como `postgres` y verifica que
`reminders` exista con RLS y privilegios para `mia_app`, y que `matters` tenga la
columna `pending_review_notified_at` (debounce del aviso de borrador pendiente).
Mismo patrón que init_local_folders.py.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

import psycopg
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[1]
load_dotenv(ROOT / ".env")
MIGRATION = ROOT / "backend" / "mia" / "db" / "migrations" / "017_reminders.sql"

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
    print("[OK] 017_reminders.sql aplicado (rol postgres)")
    with psycopg.connect(autocommit=True, **_kw("postgres", SUPER_PW)) as c:
        priv = c.execute(
            "SELECT has_table_privilege('mia_app', 'public.reminders', 'INSERT')"
        ).fetchone()[0]
        rls = c.execute(
            "SELECT relrowsecurity AND relforcerowsecurity FROM pg_class "
            "WHERE relname='reminders' AND relnamespace='public'::regnamespace"
        ).fetchone()[0]
        col = c.execute(
            "SELECT count(*) FROM information_schema.columns "
            "WHERE table_name='matters' AND column_name='pending_review_notified_at'"
        ).fetchone()[0]
        print(f"[INFO] reminders: mia_app INSERT={priv}  RLS(force)={rls}")
        print(f"[INFO] matters.pending_review_notified_at existe={bool(col)}")
    print("DONE init_reminders")


if __name__ == "__main__":
    main()
