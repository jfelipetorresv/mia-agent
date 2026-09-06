"""Instala la migración aditiva de memoria para las pruebas/operación local."""
from pathlib import Path
import psycopg

from init_assistant import _kw, SUPER_PW


def apply() -> None:
    path = Path(__file__).resolve().parents[1] / "backend/mia/db/migrations/066_assistant_conversation_memory.sql"
    with psycopg.connect(autocommit=True, **_kw("postgres", SUPER_PW)) as conn:
        conn.execute(path.read_text(encoding="utf-8"))


if __name__ == "__main__":
    apply()
    print("Memoria de conversaciones: migración 066 aplicada.")
