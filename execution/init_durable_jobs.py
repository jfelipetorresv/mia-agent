"""Aplica la cola local durable (034) y la unicidad del aprendizaje (056)."""
from __future__ import annotations

import os
from pathlib import Path

import psycopg
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[1]
load_dotenv(ROOT / ".env")
MIGRATIONS = [
    ROOT / "backend/mia/db/migrations/034_durable_jobs.sql",
    ROOT / "backend/mia/db/migrations/056_durable_learning_once.sql",
]


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
        for migration in MIGRATIONS:
            conn.execute(migration.read_text(encoding="utf-8"))


if __name__ == "__main__":
    apply()
    print("[OK] cola durable y unicidad de aprendizaje aplicadas")
