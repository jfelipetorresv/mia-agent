"""
Mia · init_sat_graph.py — migración del SAT-Graph (Módulo 3a · decisión #16).

Aplica backend/mia/db/migrations/003_sat_graph.sql como `postgres` (mia_app NO tiene
CREATE) y hace GRANT DML a `mia_app`. El SAT-Graph es corpus COMPARTIDO (no por-tenant):
RLS habilitado con política abierta USING(true) WITH CHECK(true).

Idempotente: re-ejecutable. `apply()` se puede importar desde el gate. Standalone:
    .venv\\Scripts\\python.exe execution\\init_sat_graph.py
"""
from __future__ import annotations
import os
import sys
from pathlib import Path

import psycopg
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[1]          # .../mia
load_dotenv(ROOT / ".env")
MIGRATION = ROOT / "backend" / "mia" / "db" / "migrations" / "003_sat_graph.sql"

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

HOST = os.getenv("PG_HOST", "127.0.0.1")
PORT = os.getenv("PG_PORT", "5432")
DB = os.getenv("PG_DB", "mia")
SUPER_PW = os.getenv("PG_PASSWORD", "")


def apply() -> None:
    """Aplica 003_sat_graph.sql como postgres. Lanza si falta PG_PASSWORD."""
    if not SUPER_PW:
        raise RuntimeError("falta PG_PASSWORD en .env (superusuario para la migración)")
    kw = dict(host=HOST, port=PORT, dbname=DB, user="postgres", password=SUPER_PW)
    with psycopg.connect(autocommit=True, **kw) as c:
        c.execute(MIGRATION.read_text(encoding="utf-8"))


def main() -> None:
    apply()
    print("[OK] 003_sat_graph.sql aplicado (rol postgres)")
    kw = dict(host=HOST, port=PORT, dbname=DB, user="postgres", password=SUPER_PW)
    with psycopg.connect(autocommit=True, **kw) as c:
        tabs = c.execute(
            "SELECT table_name FROM information_schema.tables "
            "WHERE table_schema='public' AND table_name IN "
            "('legal_norms','norm_relations','jurisprudence') ORDER BY table_name"
        ).fetchall()
        print(f"[INFO] tablas SAT-Graph: {', '.join(r[0] for r in tabs)}")
        for t in ("legal_norms", "norm_relations", "jurisprudence"):
            ins = c.execute(
                "SELECT has_table_privilege('mia_app', %s, 'INSERT') AS ok", (f"public.{t}",)
            ).fetchone()[0]
            rls = c.execute(
                "SELECT relrowsecurity FROM pg_class "
                "WHERE relname=%s AND relnamespace='public'::regnamespace", (t,)
            ).fetchone()[0]
            print(f"[INFO] {t}: mia_app INSERT={ins}  RLS={rls}")
    print("DONE init_sat_graph")


if __name__ == "__main__":
    main()
