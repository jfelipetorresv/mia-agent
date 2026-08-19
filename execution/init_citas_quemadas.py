"""
Mia · init_citas_quemadas.py — migración del BANCO DE CITAS QUEMADAS del despacho.

Aplica backend/mia/db/migrations/047_citas_quemadas.sql como `postgres` y verifica que
`burned_citations` exista con RLS forzada y con el índice único por (tenant, cita
normalizada). Mismo patrón que init_soul_versions.py. Idempotente.

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
MIGRATION = ROOT / "backend" / "mia" / "db" / "migrations" / "047_citas_quemadas.sql"

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
    print("[OK] 047_citas_quemadas.sql aplicado (rol postgres)")
    with psycopg.connect(autocommit=True, **_kw("postgres", SUPER_PW)) as c:
        exists = c.execute(
            "SELECT count(*) FROM information_schema.tables WHERE table_name=%s",
            ("burned_citations",),
        ).fetchone()[0]
        rls = c.execute(
            "SELECT relrowsecurity, relforcerowsecurity FROM pg_class WHERE relname=%s",
            ("burned_citations",),
        ).fetchone()
        uq = c.execute(
            "SELECT count(*) FROM pg_indexes WHERE indexname=%s",
            ("uq_burned_citations_tenant_norm",),
        ).fetchone()[0]
        print(f"[INFO] burned_citations existe={bool(exists)}")
        print(f"[INFO] burned_citations RLS enable/force={rls}")
        print(f"[INFO] índice único (tenant, citation_norm) presente={bool(uq)}")
    print("DONE init_citas_quemadas")


if __name__ == "__main__":
    main()
