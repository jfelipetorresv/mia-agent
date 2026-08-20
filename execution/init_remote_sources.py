"""
Mia · init_remote_sources.py — migración de cimientos de "fuentes remotas del expediente"
(Fase 1: OAuth multi-proveedor + tablas de OneDrive remoto).

Aplica backend/mia/db/migrations/027_remote_sources.sql como `postgres` y verifica que
`tenant_oauth_tokens` tenga PK compuesta (tenant_id, provider), que `documents.origin`
acepte 'mail'/'drive', y que `remote_drive_sources`/`remote_file_hashes` existan.
Mismo patrón que init_mailbox.py / init_matter_folders.py. Idempotente.
"""
from __future__ import annotations

import os
import re
import sys
from pathlib import Path

import psycopg
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[1]
load_dotenv(ROOT / ".env")
MIGRATIONS_DIR = ROOT / "backend" / "mia" / "db" / "migrations"
MIGRATION = MIGRATIONS_DIR / "027_remote_sources.sql"
# Este script aplica la 027 SUELTA, fuera del orden del bootstrap. Eso tiene un efecto que
# costó encontrar (2026-08-19): la 027 REDEFINE `ck_documents_origin` con el vocabulario que
# era correcto EN SU MOMENTO ('upload','folder','mail','drive'). La 028 legalizó después el
# origen 'mia', así que en cualquier base con documentos de Mia guardados la 027 suelta
# revienta con CheckViolation — y con ella reventaban los gates de OneDrive y de correo, sin
# que nada estuviera mal en el código que probaban. En el arranque real no pasa: db_bootstrap
# aplica 027, 028 y 058 en orden y el vocabulario acaba completo.
#
# Aquí se reproduce ese final: se omite el bloque de `ck_documents_origin` de la 027 (la
# tabla y el resto de la migración sí se aplican tal cual) y se aplican detrás las
# migraciones que son DUEÑAS ACTUALES de los CHECK que a este script le importan.
FOLLOW_UPS = ("058_cumulative_check_vocabularies.sql", "060_google_drive_sources.sql")
# El bloque exacto de la 027 que redefine el CHECK de `documents.origin`.
_ORIGIN_CHECK_BLOCK = re.compile(
    r"ALTER TABLE documents DROP CONSTRAINT IF EXISTS ck_documents_origin;\s*"
    r"ALTER TABLE documents\s*ADD CONSTRAINT ck_documents_origin CHECK\s*\([^;]*\);",
    re.IGNORECASE,
)


def _sql_027() -> str:
    """Texto de la 027 SIN su redefinición de `ck_documents_origin` (ver comentario arriba).
    Si el bloque no se encuentra (migración cambiada), se aplica tal cual: mejor fallar
    ruidosamente que aplicar algo distinto de lo que dice el archivo."""
    text = MIGRATION.read_text(encoding="utf-8")
    recortado, n = _ORIGIN_CHECK_BLOCK.subn(
        "-- (ck_documents_origin lo define la migración 058, dueña actual del vocabulario)\n",
        text)
    return recortado if n == 1 else text

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

HOST = os.getenv("PG_HOST", "127.0.0.1")
PORT = os.getenv("PG_PORT", "5432")
DB = os.getenv("PG_DB", "mia")
SUPER_PW = os.getenv("PG_PASSWORD", "")


def _kw(user: str, password: str) -> dict:
    return dict(host=HOST, port=PORT, dbname=DB, user=user, password=password)


def apply() -> None:
    if not SUPER_PW:
        raise RuntimeError("falta PG_PASSWORD en .env (superusuario para la migración)")
    with psycopg.connect(autocommit=True, **_kw("postgres", SUPER_PW)) as c:
        c.execute(_sql_027())
        for name in FOLLOW_UPS:
            path = MIGRATIONS_DIR / name
            if path.exists():
                c.execute(path.read_text(encoding="utf-8"))


def main() -> None:
    apply()
    print("[OK] 027_remote_sources.sql aplicado (rol postgres)")
    with psycopg.connect(autocommit=True, **_kw("postgres", SUPER_PW)) as c:
        pk_cols = [r[0] for r in c.execute(
            "SELECT a.attname FROM pg_constraint co "
            "JOIN unnest(co.conkey) WITH ORDINALITY AS k(attnum, ord) ON true "
            "JOIN pg_attribute a ON a.attrelid = co.conrelid AND a.attnum = k.attnum "
            "WHERE co.conrelid = 'public.tenant_oauth_tokens'::regclass AND co.contype = 'p' "
            "ORDER BY k.ord"
        ).fetchall()]
        print(f"[INFO] tenant_oauth_tokens PK = {pk_cols} "
              f"(esperado ['tenant_id', 'provider'])")
        origin_ck = c.execute(
            "SELECT pg_get_constraintdef(oid) FROM pg_constraint "
            "WHERE conname = 'ck_documents_origin' AND conrelid = 'public.documents'::regclass"
        ).fetchone()
        print(f"[INFO] documents.origin CHECK = {origin_ck[0] if origin_ck else 'AUSENTE'}")
        for table in ("remote_drive_sources", "remote_file_hashes"):
            exists = c.execute(
                "SELECT count(*) FROM information_schema.tables WHERE table_name=%s",
                (table,),
            ).fetchone()[0]
            print(f"[INFO] {table} existe={bool(exists)}")
    print("DONE init_remote_sources")


if __name__ == "__main__":
    main()
