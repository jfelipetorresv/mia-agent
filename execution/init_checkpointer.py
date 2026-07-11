"""
Mia · init_checkpointer.py — migración del checkpointing LangGraph (1d · decisión #9).

Crea las tablas de checkpoint de LangGraph (checkpoints, checkpoint_blobs,
checkpoint_writes, checkpoint_migrations) como `postgres` (mia_app NO tiene CREATE)
y hace GRANT DML a `mia_app`. En runtime el saver corre como mia_app sin tocar DDL.

Idempotente: re-ejecutable. Se corre con el python de mia/.venv:
    .venv\\Scripts\\python.exe execution\\init_checkpointer.py

La creación de tablas + GRANT vive en mia.setup.db_bootstrap.setup_checkpointer
(compartida con mia.setup.first_run — sesión 43): este script solo resuelve la
config del repo (.env) y agrega los mismos diagnósticos de antes.
"""
from __future__ import annotations
import os
import sys
from pathlib import Path

import psycopg
from psycopg.rows import dict_row
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[1]  # .../mia
load_dotenv(ROOT / ".env")
sys.path.insert(0, str(ROOT / "backend"))

from mia.setup.db_bootstrap import setup_checkpointer  # noqa: E402

HOST = os.getenv("PG_HOST", "127.0.0.1")
PORT = os.getenv("PG_PORT", "5432")
DB = os.getenv("PG_DB", "mia")
SUPER_PW = os.getenv("PG_PASSWORD", "")

if not SUPER_PW:
    sys.exit("ERROR: falta PG_PASSWORD en .env (superusuario para la migración)")


def main() -> None:
    names = setup_checkpointer(HOST, PORT, DB, SUPER_PW)
    print("[OK] tablas de checkpoint creadas/migradas (rol postgres)")
    print(f"[OK] GRANT DML a mia_app sobre: {', '.join(names)}")

    kw = dict(host=HOST, port=PORT, dbname=DB, user="postgres", password=SUPER_PW,
              autocommit=True, row_factory=dict_row)
    with psycopg.connect(**kw) as conn:
        ins = conn.execute(
            "SELECT has_table_privilege('mia_app','public.checkpoints','INSERT') AS ok"
        ).fetchone()
        print(f"[INFO] mia_app puede INSERT en checkpoints: {ins['ok']}")

        # Confirmar que NO tienen RLS forzado (aislamiento por thread_id, no por RLS).
        rls = conn.execute(
            "SELECT bool_or(relrowsecurity) AS any_rls FROM pg_class "
            "WHERE relname LIKE 'checkpoint%' AND relnamespace='public'::regnamespace"
        ).fetchone()
        print(f"[INFO] alguna tabla de checkpoint con RLS: {rls['any_rls']} (esperado: False)")
    print("DONE init_checkpointer")


if __name__ == "__main__":
    main()
