"""Mia · setup.paths — resolución de schema.sql y migrations/*.sql en dev y frozen.

En desarrollo estos archivos viven en el paquete real `backend/mia/db/`. En el
bundle de PyInstaller (onedir, mia-backend.spec) se copian con `datas`
explícitas a `mia/db/schema.sql` y `mia/db/migrations/*.sql` dentro de
`sys._MEIPASS` (en onedir, `_MEIPASS` es la propia carpeta del ejecutable, no
un directorio temporal). Un solo helper aquí evita que cada llamador tenga que
conocer esta diferencia.
"""
from __future__ import annotations

import sys
from pathlib import Path


def db_package_dir() -> Path:
    """Carpeta que contiene schema.sql y migrations/ (dev o frozen)."""
    meipass = getattr(sys, "_MEIPASS", None)
    if meipass:
        return Path(meipass) / "mia" / "db"
    return Path(__file__).resolve().parents[1] / "db"


def schema_sql_path() -> Path:
    return db_package_dir() / "schema.sql"


def migrations_dir() -> Path:
    return db_package_dir() / "migrations"


def migration_paths() -> list[Path]:
    """Migraciones 003+ en orden ascendente por nombre (003_..., 004_..., ...)."""
    return sorted(migrations_dir().glob("*.sql"), key=lambda p: p.name)
