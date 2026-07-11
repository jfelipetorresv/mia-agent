"""
Mia · init_db.py — Paso 3 del Módulo 0.
Crea el rol `mia_app`, la base `mia`, las extensiones y aplica schema.sql.
Se ejecuta con el python de mia/.venv. Usa el superusuario `postgres`
(solo migraciones). Idempotente.

La lógica de aprovisionamiento vive en mia.setup.db_bootstrap (compartida con
mia.setup.first_run, el bootstrap de primer arranque del instalador — sesión
43): este script solo resuelve la config del repo (.env) y llama las mismas
funciones, para no duplicar el SQL en dos sitios.
"""
from __future__ import annotations
import os
import sys
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[1]          # .../mia
sys.path.insert(0, str(ROOT / "backend"))
load_dotenv(ROOT / ".env")

from mia.setup import db_bootstrap  # noqa: E402
from mia.setup.paths import schema_sql_path  # noqa: E402

HOST = os.getenv("PG_HOST", "127.0.0.1")
PORT = os.getenv("PG_PORT", "5432")
DB = os.getenv("PG_DB", "mia")
SUPER_PW = os.getenv("PG_PASSWORD", "")
APP_PW = os.getenv("PG_APP_PASSWORD", "")

if not SUPER_PW:
    sys.exit("ERROR: falta PG_PASSWORD en .env")
if not APP_PW:
    sys.exit("ERROR: falta PG_APP_PASSWORD en .env")


def main() -> None:
    # --- rol + base (en la base de mantenimiento) ---
    result = db_bootstrap.ensure_app_role_and_database(HOST, PORT, DB, SUPER_PW, APP_PW)
    verb = result["role_verb"]
    print(f"[OK] rol mia_app {'actualizado' if verb == 'ALTER' else 'creado'} "
          "(NOSUPERUSER, NOBYPASSRLS)")
    print(f"[OK] base {DB} {'creada' if result['db_created'] else 'ya existe'}")

    # --- extensiones + schema (en la base mia) ---
    schema_text = schema_sql_path().read_text(encoding="utf-8")
    info = db_bootstrap.apply_extensions_and_schema(HOST, PORT, DB, SUPER_PW, schema_text)
    print("[OK] schema.sql aplicado")
    print(f"[INFO] encoding={info['encoding']}  tablas_public={info['tablas_public']}  "
          f"policies={info['policies']}  pgvector={info['pgvector']}")
    if info["encoding"].upper() != "UTF8":
        print(f"[WARN] la base {DB} no es UTF8 ({info['encoding']}); "
              "revisar para texto jurídico en producción.")

    print("DONE init_db")


if __name__ == "__main__":
    main()
