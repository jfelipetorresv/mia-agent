"""Mia · setup_db_steps.py — pasos Python de scripts/setup_db.ps1.

Antes vivian como here-strings de PowerShell (`& $py -c @"..."@`) dentro de
setup_db.ps1, y ese formato revienta en Windows PowerShell 5.1 (deuda anotada
en HANDOFF 2026-08-15/18). Ahora el .ps1 solo orquesta y este archivo hace el
trabajo. ASCII puro a proposito, como el .ps1.

Subcomandos (mismos exit codes que tenian los bloques embebidos):
  check-pgvector            0 = disponible o no-verificable (fail-open con aviso)
                            2 = la base configurada NO tiene pgvector
  apply-migration <ruta>    0 = aplicada · !=0 = fallo real

Uso:  .venv\\Scripts\\python.exe scripts\\setup_db_steps.py check-pgvector
"""
from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def _load_env() -> None:
    from dotenv import load_dotenv

    load_dotenv(ROOT / ".env")


def _connect(**extra):
    import psycopg

    return psycopg.connect(
        host=os.getenv("PG_HOST", "127.0.0.1"),
        port=os.getenv("PG_PORT", "5432"),
        dbname=os.getenv("PG_DB", "mia"),
        user="postgres",
        password=os.getenv("PG_PASSWORD", ""),
        autocommit=True,
        **extra,
    )


def check_pgvector() -> int:
    """Verifica pgvector en la base que REALMENTE se va a usar (la del .env).

    Si no se puede verificar NO bloquea (fail-open con aviso): init_db dara el
    error real. Historia completa en el comentario de setup_db.ps1.
    """
    _load_env()
    try:
        with _connect(connect_timeout=8) as conn:
            ok = conn.execute(
                "SELECT 1 FROM pg_available_extensions WHERE name='vector'"
            ).fetchone()
        return 0 if ok else 2
    except Exception as e:  # noqa: BLE001 — fail-open deliberado, documentado arriba
        print("AVISO: no se pudo verificar pgvector (" + type(e).__name__ + "); se continua.")
        return 0


def apply_migration(sql_path: str) -> int:
    _load_env()
    sql = Path(sql_path).read_text(encoding="utf-8")
    with _connect() as conn:
        conn.execute(sql)
    print("OK")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="cmd", required=True)
    sub.add_parser("check-pgvector")
    mig = sub.add_parser("apply-migration")
    mig.add_argument("sql_path")
    args = parser.parse_args()

    if args.cmd == "check-pgvector":
        return check_pgvector()
    return apply_migration(args.sql_path)


if __name__ == "__main__":
    raise SystemExit(main())
