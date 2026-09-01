"""
Mia · init_soul_versions.py — migración del historial de la identidad (SOUL).

Aplica backend/mia/db/migrations/040_soul_versions.sql como `postgres` y verifica que
`soul_versions` exista con RLS forzada y que `feedback_proposals` acepte el tipo
'soul_rule'. Mismo patrón que init_playbook_versions.py. Idempotente.

La base de DEV es anterior al ledger (`mia_schema_migrations`): por eso se aplica con este
script, igual que las demás. En instalaciones nuevas la recoge sola
`setup/paths.migration_paths()` (glob ordenado por nombre).
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

import psycopg
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[1]
load_dotenv(ROOT / ".env")
MIGRATION = ROOT / "backend" / "mia" / "db" / "migrations" / "040_soul_versions.sql"
# La 040 crea `soul_versions` Y reemplaza el CHECK de `feedback_proposals` con la lista de
# tipos que estaba vigente ENTONCES (sin 'harvest_lessons', que llegó con la 049). Re-aplicar
# la 040 sola tumbaba el vocabulario acumulado de la 058 y reventaba con CheckViolation en
# cuanto la base tuviera una fila legítima 'harvest_lessons' (visto 2026-08-25; es el mismo
# defecto del aprendizaje 86, en otro helper). Las migraciones son inmutables, así que aquí
# se aplica la 040 y a continuación la definición VIGENTE del vocabulario, que es idempotente
# (DROP IF EXISTS + ADD). REGLA: un helper de init deja siempre la definición vigente de lo
# que asegura, nunca la de una migración intermedia.
VOCABULARIO_VIGENTE = (
    ROOT / "backend" / "mia" / "db" / "migrations" / "058_cumulative_check_vocabularies.sql")

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


# Encabezado de la sección de la 040 que reemplaza el CHECK de `feedback_proposals`. Todo lo
# que va desde aquí hasta el final del archivo quedó SUPERADO por la 049 y la 058.
_MARCA_VOCABULARIO = "-- ── El tipo de propuesta 'soul_rule'"


def _040_sin_vocabulario_superado() -> str:
    """La 040 SIN su bloque de vocabulario, que hoy es una regresión.

    La 040 hace dos cosas: crea `soul_versions` (sigue siendo lo vigente) y reemplaza el
    CHECK de `feedback_proposals` por la lista de tipos de su momento, que ya no incluye
    todos los que la aplicación usa. Re-aplicarla entera falla con CheckViolation en cuanto
    la base tiene una fila legítima de un tipo posterior, y ese rojo se venía leyendo como
    «fila corrupta» cuando el defecto era el helper (aprendizaje 86, otro helper).

    La migración NO se toca (son inmutables): se recorta aquí, en quien la re-aplica. Si el
    marcador desapareciera de la 040, esto falla RUIDOSAMENTE en vez de aplicar el archivo
    entero por su cuenta: un recorte que se convierte en silencio en «aplicar todo» es
    exactamente la regresión que este código evita.
    """
    sql = MIGRATION.read_text(encoding="utf-8")
    corte = sql.find(_MARCA_VOCABULARIO)
    if corte < 0:
        raise RuntimeError(
            "040_soul_versions.sql ya no tiene el bloque de vocabulario que este helper "
            "recorta. Revisa init_soul_versions.py antes de seguir: aplicarla entera "
            "retrocedería el CHECK de feedback_proposals.")
    recortado = sql[:corte]
    if "CREATE TABLE IF NOT EXISTS soul_versions" not in recortado:
        raise RuntimeError(
            "el recorte de 040_soul_versions.sql se quedó sin la creación de soul_versions; "
            "no se aplica nada.")
    return recortado


def apply() -> None:
    if not SUPER_PW:
        raise RuntimeError("falta PG_PASSWORD en .env (superusuario para la migración)")
    with psycopg.connect(autocommit=True, **_kw("postgres", SUPER_PW)) as c:
        c.execute(_040_sin_vocabulario_superado())
        # El vocabulario lo pone la definición VIGENTE, no la de 2026. Es idempotente
        # (DROP IF EXISTS + ADD) y acumula todos los tipos, así que ninguna fila legítima
        # que ya exista en la base la hace fallar.
        c.execute(VOCABULARIO_VIGENTE.read_text(encoding="utf-8"))


def main() -> None:
    apply()
    print("[OK] 040_soul_versions.sql aplicado (rol postgres)")
    with psycopg.connect(autocommit=True, **_kw("postgres", SUPER_PW)) as c:
        exists = c.execute(
            "SELECT count(*) FROM information_schema.tables WHERE table_name=%s",
            ("soul_versions",),
        ).fetchone()[0]
        rls = c.execute(
            "SELECT relrowsecurity, relforcerowsecurity FROM pg_class WHERE relname=%s",
            ("soul_versions",),
        ).fetchone()
        chk = c.execute(
            "SELECT pg_get_constraintdef(oid) FROM pg_constraint "
            "WHERE conname='feedback_proposals_proposal_type_check'",
        ).fetchone()
        print(f"[INFO] soul_versions existe={bool(exists)}")
        print(f"[INFO] soul_versions RLS enable/force={rls}")
        print(f"[INFO] feedback_proposals acepta soul_rule={'soul_rule' in (chk[0] if chk else '')}")
    print("DONE init_soul_versions")


if __name__ == "__main__":
    main()
