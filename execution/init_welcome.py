"""
Mia · init_welcome.py — migración de F3 (bienvenida) para los gates.

Aplica backend/mia/db/migrations/031_welcome_bootstrap.sql como `postgres`
(la función SECURITY DEFINER `mia_any_tenant_exists` que /api/welcome/status
usa para la señal pre-login "¿ya hay algún despacho?"). Mismo patrón que
init_users.py; idempotente (CREATE OR REPLACE).
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

import psycopg
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[1]
load_dotenv(ROOT / ".env")
MIGRATION = ROOT / "backend" / "mia" / "db" / "migrations" / "031_welcome_bootstrap.sql"

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
    print("[OK] 031_welcome_bootstrap.sql aplicado (rol postgres)")
    with psycopg.connect(autocommit=True, **_kw("postgres", SUPER_PW)) as c:
        fn = c.execute(
            "SELECT has_function_privilege('mia_app', 'mia_any_tenant_exists()', 'EXECUTE')"
        ).fetchone()[0]
    print(f"[INFO] welcome: mia_app EXECUTE mia_any_tenant_exists()={fn}")
    print("DONE init_welcome")


if __name__ == "__main__":
    main()
