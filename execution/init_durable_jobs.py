"""Aplica la cola local durable (034). Idempotente."""
from __future__ import annotations

import os
from pathlib import Path

import psycopg
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[1]
load_dotenv(ROOT / ".env")
MIGRATION = ROOT / "backend/mia/db/migrations/034_durable_jobs.sql"


def apply() -> None:
    password = os.getenv("PG_PASSWORD", "")
    if not password:
        raise RuntimeError("falta PG_PASSWORD en .env")
    with psycopg.connect(
        host=os.getenv("PG_HOST", "127.0.0.1"),
        port=os.getenv("PG_PORT", "5432"),
        dbname=os.getenv("PG_DB", "mia"),
        user="postgres", password=password, autocommit=True,
    ) as conn:
        conn.execute(MIGRATION.read_text(encoding="utf-8"))


if __name__ == "__main__":
    apply()
    print("[OK] 034_durable_jobs.sql aplicado")
