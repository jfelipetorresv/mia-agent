"""
Mia · init_shortcut_prefs.py — migración de los ATAJOS EDITABLES del despacho (bloque D7).

Aplica backend/mia/db/migrations/062_shortcut_prefs.sql como `postgres` y verifica que
`shortcut_prefs` exista con RLS forzada, con el índice único parcial por (tenant, fuente,
id de origen) y con el CHECK que impide fijar y ocultar el mismo atajo. Mismo patrón que
init_citas_quemadas.py. Idempotente.

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
MIGRATION = ROOT / "backend" / "mia" / "db" / "migrations" / "062_shortcut_prefs.sql"

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
    print("[OK] 062_shortcut_prefs.sql aplicado (rol postgres)")
    with psycopg.connect(autocommit=True, **_kw("postgres", SUPER_PW)) as c:
        exists = c.execute(
            "SELECT count(*) FROM information_schema.tables WHERE table_name=%s",
            ("shortcut_prefs",),
        ).fetchone()[0]
        rls = c.execute(
            "SELECT relrowsecurity, relforcerowsecurity FROM pg_class WHERE relname=%s",
            ("shortcut_prefs",),
        ).fetchone()
        uq = c.execute(
            "SELECT count(*) FROM pg_indexes WHERE indexname=%s",
            ("uq_shortcut_prefs_tenant_source",),
        ).fetchone()[0]
        ck = c.execute(
            "SELECT count(*) FROM pg_constraint WHERE conname=%s",
            ("ck_shortcut_prefs_pin_o_hide",),
        ).fetchone()[0]
        print(f"[INFO] shortcut_prefs existe={bool(exists)}")
        print(f"[INFO] shortcut_prefs RLS enable/force={rls}")
        print(f"[INFO] índice único parcial (tenant, source, source_id) presente={bool(uq)}")
        print(f"[INFO] CHECK fijado-o-oculto presente={bool(ck)}")
    print("DONE init_shortcut_prefs")


if __name__ == "__main__":
    main()
