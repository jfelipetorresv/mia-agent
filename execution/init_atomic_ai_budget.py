"""Aplica manualmente 035_atomic_ai_budget.sql en desarrollo."""
from __future__ import annotations

import os
from pathlib import Path
import psycopg
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[1]
MIGRATION = ROOT / "backend/mia/db/migrations/035_atomic_ai_budget.sql"
load_dotenv(ROOT / ".env")


def apply() -> None:
    with psycopg.connect(
        host=os.getenv("PG_HOST", "127.0.0.1"), port=os.getenv("PG_PORT", "5432"),
        dbname=os.getenv("PG_DB", "mia"), user="postgres",
        password=os.getenv("PG_PASSWORD", ""), autocommit=True,
    ) as conn:
        conn.execute(MIGRATION.read_text(encoding="utf-8"))
    print("[OK] 035_atomic_ai_budget.sql aplicado")


if __name__ == "__main__":
    apply()
