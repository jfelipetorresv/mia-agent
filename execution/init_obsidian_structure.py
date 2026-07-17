"""
Mia · init_obsidian_structure.py — migración 039 (estructura del vault de Obsidian).

Aplica backend/mia/db/migrations/039_obsidian_frontmatter_links.sql como `postgres` (mia_app
NO tiene CREATE) y verifica que knowledge_chunks tenga las 4 columnas nuevas
(doc_status, doc_type, frontmatter, links).

POR QUÉ EXISTE ESTE RUNNER: las instalaciones nuevas aplican las migraciones solas por el
ledger (setup/db_bootstrap.apply_migrations, que barre la carpeta ordenada por nombre y ya
recoge la 039 sin tocar nada). La base de desarrollo es ANTERIOR al ledger, así que este
script hace lo mismo que init_knowledge_stores.py hace con la 004: aplicarla a mano, de forma
idempotente. `apply()` se puede importar desde el gate.

    .venv\\Scripts\\python.exe execution\\init_obsidian_structure.py
"""
from __future__ import annotations
import os
import sys
from pathlib import Path

import psycopg
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[1]          # .../mia
load_dotenv(ROOT / ".env")
MIGRATION = (ROOT / "backend" / "mia" / "db" / "migrations"
             / "039_obsidian_frontmatter_links.sql")

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

HOST = os.getenv("PG_HOST", "127.0.0.1")
PORT = os.getenv("PG_PORT", "5432")
DB = os.getenv("PG_DB", "mia")
SUPER_PW = os.getenv("PG_PASSWORD", "")

_COLUMNS = ("doc_status", "doc_type", "frontmatter", "links")


def apply() -> None:
    """Aplica 039 como postgres. Lanza si falta PG_PASSWORD."""
    if not SUPER_PW:
        raise RuntimeError("falta PG_PASSWORD en .env (superusuario para la migración)")
    kw = dict(host=HOST, port=PORT, dbname=DB, user="postgres", password=SUPER_PW)
    with psycopg.connect(autocommit=True, **kw) as c:
        c.execute(MIGRATION.read_text(encoding="utf-8"))


def main() -> None:
    apply()
    print("[OK] 039_obsidian_frontmatter_links.sql aplicado (rol postgres)")
    kw = dict(host=HOST, port=PORT, dbname=DB, user="postgres", password=SUPER_PW)
    with psycopg.connect(autocommit=True, **kw) as c:
        cols = c.execute(
            "SELECT column_name FROM information_schema.columns "
            "WHERE table_schema='public' AND table_name='knowledge_chunks' "
            "AND column_name = ANY(%s) ORDER BY column_name", (list(_COLUMNS),),
        ).fetchall()
        print(f"[INFO] columnas nuevas en knowledge_chunks: {', '.join(r[0] for r in cols)}")
        idx = c.execute(
            "SELECT indexname FROM pg_indexes WHERE tablename='knowledge_chunks' "
            "AND indexname LIKE 'idx_knowledge_chunks_%' ORDER BY indexname"
        ).fetchall()
        print(f"[INFO] índices: {', '.join(r[0] for r in idx)}")
    print("DONE init_obsidian_structure")


if __name__ == "__main__":
    main()
