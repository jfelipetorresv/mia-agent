"""
Mia · init_watch_engine.py — migración del MOTOR DE VIGILANCIA (CP-P1, Ola 2).

Aplica backend/mia/db/migrations/018_watch_engine.sql como `postgres` y verifica que
`scheduled_claims` exista (tabla de sistema para el claim at-most-once) y que
`reminders` tenga la columna `heads_up_sent_at` (aviso anticipado de plazo próximo).
Mismo patrón que init_reminders.py. Idempotente.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

import psycopg
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[1]
load_dotenv(ROOT / ".env")
MIGRATION = ROOT / "backend" / "mia" / "db" / "migrations" / "018_watch_engine.sql"

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
    print("[OK] 018_watch_engine.sql aplicado (rol postgres)")
    with psycopg.connect(autocommit=True, **_kw("postgres", SUPER_PW)) as c:
        claims = c.execute(
            "SELECT count(*) FROM information_schema.tables "
            "WHERE table_name='scheduled_claims'"
        ).fetchone()[0]
        col = c.execute(
            "SELECT count(*) FROM information_schema.columns "
            "WHERE table_name='reminders' AND column_name='heads_up_sent_at'"
        ).fetchone()[0]
        print(f"[INFO] scheduled_claims existe={bool(claims)}")
        print(f"[INFO] reminders.heads_up_sent_at existe={bool(col)}")
    print("DONE init_watch_engine")


if __name__ == "__main__":
    main()
