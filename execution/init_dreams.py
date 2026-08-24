"""
Mia · init_dreams.py — migración de tipos de propuestas para Dreams/Second Brain.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

import psycopg
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[1]
load_dotenv(ROOT / ".env")
# La 010 quedó superada: la 040 añadió 'soul_rule', la 049 añadió 'harvest_lessons' (perdiendo
# 'soul_rule' por el camino) y la 058 dejó el vocabulario ACUMULADO vigente. Re-aplicar aquí la
# 010 tumbaba el CHECK vigente y lo reemplazaba por la lista vieja: cualquier fila legítima
# 'soul_rule'/'harvest_lessons' hacía reventar el script con CheckViolation (visto 2026-08-24).
# Este helper aplica siempre la definición VIGENTE, que es idempotente (DROP IF EXISTS + ADD).
MIGRATION = ROOT / "backend" / "mia" / "db" / "migrations" / "058_cumulative_check_vocabularies.sql"

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

HOST = os.getenv("PG_HOST", "127.0.0.1")
PORT = os.getenv("PG_PORT", "5432")
DB = os.getenv("PG_DB", "mia")
SUPER_PW = os.getenv("PG_PASSWORD", "")


def apply() -> None:
    if not SUPER_PW:
        raise RuntimeError("falta PG_PASSWORD en .env (superusuario para la migración)")
    with psycopg.connect(autocommit=True, host=HOST, port=PORT, dbname=DB, user="postgres", password=SUPER_PW) as c:
        c.execute(MIGRATION.read_text(encoding="utf-8"))


def main() -> None:
    apply()
    print("[OK] 058_cumulative_check_vocabularies.sql aplicado (rol postgres)")
    print("DONE init_dreams")


if __name__ == "__main__":
    main()
