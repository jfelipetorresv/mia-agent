"""
Mia · init_users.py — migración de usuarios reales multi-tenant (Riesgo #23).

Aplica backend/mia/db/migrations/009_users.sql como `postgres` y verifica que
`users` exista con RLS y privilegios para `mia_app`.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

import psycopg
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[1]
load_dotenv(ROOT / ".env")
MIGRATION = ROOT / "backend" / "mia" / "db" / "migrations" / "009_users.sql"

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
    print("[OK] 009_users.sql aplicado (rol postgres)")
    with psycopg.connect(autocommit=True, **_kw("postgres", SUPER_PW)) as c:
        priv = c.execute(
            "SELECT has_table_privilege('mia_app', 'public.users', 'INSERT')"
        ).fetchone()[0]
        rls = c.execute(
            "SELECT relrowsecurity FROM pg_class "
            "WHERE relname='users' AND relnamespace='public'::regnamespace"
        ).fetchone()[0]
        fn = c.execute(
            "SELECT has_function_privilege('mia_app', 'auth_user_by_email(varchar)', 'EXECUTE')"
        ).fetchone()[0]
    print(f"[INFO] users: mia_app INSERT={priv}  RLS={rls}  auth_fn={fn}")
    print("DONE init_users")


if __name__ == "__main__":
    main()
