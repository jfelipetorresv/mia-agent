"""Gate F0: migraciones registradas, atómicas y reanudables.

Usa una base temporal aislada; nunca toca la base ``mia``. Requiere el
PostgreSQL de desarrollo encendido, igual que los gates RLS/E2E existentes.
"""
from __future__ import annotations

import sys
import tempfile
import uuid
from pathlib import Path

import psycopg
from dotenv import dotenv_values
from psycopg import sql

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from mia.setup import db_bootstrap  # noqa: E402


failures: list[str] = []


def check(label: str, condition: bool) -> None:
    print(f"  [{'OK' if condition else 'FAIL'}] {label}")
    if not condition:
        failures.append(label)


env = dotenv_values(ROOT / ".env")
host = str(env.get("PG_HOST") or "127.0.0.1")
port = int(env.get("PG_PORT") or 55432)
password = str(env.get("PG_PASSWORD") or "")
if not password:
    print("  [FAIL] falta PG_PASSWORD en .env; el gate no puede probar atomicidad real")
    raise SystemExit(1)

db_name = f"mia_migration_gate_{uuid.uuid4().hex[:12]}"
admin = dict(host=host, port=port, dbname="postgres", user="postgres", password=password)

print("\n=== F0 · ledger de migraciones ===")
try:
    with psycopg.connect(autocommit=True, **admin) as conn:
        conn.execute(sql.SQL("CREATE DATABASE {}").format(sql.Identifier(db_name)))

    with tempfile.TemporaryDirectory(prefix="mia-migrations-") as td:
        folder = Path(td)
        m1 = folder / "901_gate_alpha.sql"
        m2 = folder / "902_gate_beta.sql"
        m1.write_text("CREATE TABLE gate_alpha (id integer PRIMARY KEY);\n", encoding="utf-8")
        m2.write_text("CREATE TABLE gate_beta (id integer PRIMARY KEY);\n", encoding="utf-8")

        callback_state = {"calls": 0, "before_any_mutation": False}

        def before_first() -> None:
            callback_state["calls"] += 1
            with psycopg.connect(host=host, port=port, dbname=db_name,
                                 user="postgres", password=password) as conn:
                callback_state["before_any_mutation"] = (
                    conn.execute(
                        "SELECT to_regclass('public.mia_schema_migrations'), "
                        "to_regclass('public.gate_alpha')"
                    ).fetchone() == (None, None)
                )

        # Se entrega adrede en orden inverso: el migrador debe ordenar por nombre.
        first = db_bootstrap.apply_migrations(
            host, port, db_name, password, [m2, m1],
            before_first_pending=before_first,
        )
        check("primera corrida aplica ambas migraciones", first == [m1.name, m2.name])
        check("backup-hook corre una sola vez antes de cualquier mutación",
              callback_state == {"calls": 1, "before_any_mutation": True})

        second = db_bootstrap.apply_migrations(
            host, port, db_name, password, [m1, m2],
            before_first_pending=before_first,
        )
        check("segunda corrida no reejecuta migraciones", second == [])
        check("sin pendientes no crea otro backup", callback_state["calls"] == 1)

        with psycopg.connect(host=host, port=port, dbname=db_name,
                             user="postgres", password=password) as conn:
            rows = conn.execute(
                "SELECT filename, sha256 FROM mia_schema_migrations ORDER BY filename"
            ).fetchall()
        check("ledger registra nombre y SHA-256", len(rows) == 2 and all(len(r[1]) == 64 for r in rows))

        original = m1.read_text(encoding="utf-8")
        m1.write_text(original + "-- alterada\n", encoding="utf-8")
        try:
            db_bootstrap.apply_migrations(host, port, db_name, password, [m1, m2])
            checksum_blocked = False
        except db_bootstrap.MigrationChecksumError:
            checksum_blocked = True
        check("archivo histórico alterado bloquea el arranque", checksum_blocked)
        m1.write_text(original, encoding="utf-8")

        broken = folder / "903_gate_atomic.sql"
        broken.write_text(
            "CREATE TABLE gate_must_rollback (id integer);\nESTO NO ES SQL;\n",
            encoding="utf-8",
        )
        try:
            db_bootstrap.apply_migrations(host, port, db_name, password, [m1, m2, broken])
            failed = False
        except psycopg.Error:
            failed = True
        check("migración inválida falla", failed)

        with psycopg.connect(host=host, port=port, dbname=db_name,
                             user="postgres", password=password) as conn:
            table_exists = conn.execute(
                "SELECT to_regclass('public.gate_must_rollback')"
            ).fetchone()[0]
            ledger_exists = conn.execute(
                "SELECT 1 FROM mia_schema_migrations WHERE filename=%s", (broken.name,)
            ).fetchone()
        check("fallo revierte el SQL parcial", table_exists is None)
        check("fallo no deja registro falso", ledger_exists is None)

        broken.write_text("CREATE TABLE gate_must_rollback (id integer);\n", encoding="utf-8")
        resumed = db_bootstrap.apply_migrations(
            host, port, db_name, password, [m1, m2, broken]
        )
        check("siguiente corrida reanuda la migración pendiente", resumed == [broken.name])

        concurrent = folder / "904_gate_concurrently.sql"
        concurrent.write_text(
            "CREATE INDEX CONCURRENTLY gate_idx ON gate_alpha (id);\n", encoding="utf-8"
        )
        try:
            db_bootstrap.apply_migrations(
                host, port, db_name, password, [m1, m2, broken, concurrent]
            )
            concurrently_blocked = False
        except ValueError as exc:
            concurrently_blocked = "CONCURRENTLY" in str(exc)
        check("DDL no transaccional se bloquea con explicación", concurrently_blocked)

        # Riesgo #73: dos migraciones con el mismo prefijo numérico deben fallar
        # con explicación ANTES de tocar el esquema, no romper el orden del ledger.
        dup_a = folder / "906_gate_dup.sql"
        dup_b = folder / "906_gate_dup_other.sql"
        dup_a.write_text("CREATE TABLE gate_dup_a (id integer);\n", encoding="utf-8")
        dup_b.write_text("CREATE TABLE gate_dup_b (id integer);\n", encoding="utf-8")
        try:
            db_bootstrap.apply_migrations(host, port, db_name, password, [m1, dup_a, dup_b])
            prefix_blocked = False
        except db_bootstrap.MigrationPrefixCollisionError as exc:
            prefix_blocked = "906" in str(exc)
        with psycopg.connect(host=host, port=port, dbname=db_name,
                             user="postgres", password=password) as conn:
            dup_leaked = conn.execute("SELECT to_regclass('public.gate_dup_a')").fetchone()[0]
        check("prefijo de migración duplicado se bloquea con explicación",
              prefix_blocked and dup_leaked is None)
        dup_a.unlink()
        dup_b.unlink()

        # La carpeta REAL de migraciones no debe tener prefijos duplicados hoy.
        real_dir = ROOT / "backend" / "mia" / "db" / "migrations"
        real_migrations = sorted(real_dir.glob("*.sql"))
        try:
            db_bootstrap._assert_unique_prefixes(real_migrations)
            real_unique = True
        except db_bootstrap.MigrationPrefixCollisionError as exc:
            real_unique = False
            print(f"       {exc}")
        check("migraciones reales del repo no colisionan en prefijo", real_unique)

        guarded = folder / "905_gate_backup_required.sql"
        guarded.write_text("CREATE TABLE gate_backup_required (id integer);\n", encoding="utf-8")

        def backup_failed() -> None:
            raise RuntimeError("backup simulado falló")

        try:
            db_bootstrap.apply_migrations(
                host, port, db_name, password, [m1, m2, broken, guarded],
                before_first_pending=backup_failed,
            )
            backup_failure_blocked = False
        except RuntimeError as exc:
            backup_failure_blocked = "backup simulado" in str(exc)
        with psycopg.connect(host=host, port=port, dbname=db_name,
                             user="postgres", password=password) as conn:
            guarded_table = conn.execute(
                "SELECT to_regclass('public.gate_backup_required')"
            ).fetchone()[0]
            guarded_ledger = conn.execute(
                "SELECT 1 FROM mia_schema_migrations WHERE filename=%s", (guarded.name,)
            ).fetchone()
        check("si el backup falla no comienza la migración",
              backup_failure_blocked and guarded_table is None and guarded_ledger is None)
finally:
    try:
        with psycopg.connect(autocommit=True, **admin) as conn:
            conn.execute(
                "SELECT pg_terminate_backend(pid) FROM pg_stat_activity "
                "WHERE datname=%s AND pid <> pg_backend_pid()",
                (db_name,),
            )
            conn.execute(sql.SQL("DROP DATABASE IF EXISTS {}").format(sql.Identifier(db_name)))
    except Exception as exc:  # noqa: BLE001
        print(f"  [FAIL] no se pudo limpiar la base temporal {db_name}: {exc}")
        failures.append("limpieza de base temporal")

if failures:
    print(f"\nFAIL: {len(failures)} comprobaciones")
    raise SystemExit(1)
print("\nPASS: migraciones atómicas, verificables y reanudables")
