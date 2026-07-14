"""Gate F1: backup cifrado y restauración real en una base limpia."""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import tempfile
import uuid
from pathlib import Path

import psycopg
from dotenv import dotenv_values
from psycopg import sql

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from mia.setup import backup  # noqa: E402


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
    print("  [FAIL] falta PG_PASSWORD en .env")
    raise SystemExit(1)

orchestration = json.loads((ROOT / "desktop" / "orchestration.json").read_text(encoding="utf-8"))
pg_bin = Path(orchestration["db"]["pg_bin"])
pg_dump = pg_bin / "pg_dump.exe"
pg_restore = pg_bin / "pg_restore.exe"
if not pg_dump.is_file() or not pg_restore.is_file():
    print("  [FAIL] el PostgreSQL portable no incluye pg_dump.exe y pg_restore.exe")
    raise SystemExit(1)

source_db = f"mia_backup_source_{uuid.uuid4().hex[:10]}"
restored_db = f"mia_backup_restored_{uuid.uuid4().hex[:10]}"
admin = dict(host=host, port=port, dbname="postgres", user="postgres", password=password)
marker = "expediente-prueba-confidencial-7f91"

print("\n=== F1 · backup cifrado y restaurable ===")
try:
    with psycopg.connect(autocommit=True, **admin) as conn:
        conn.execute(sql.SQL("CREATE DATABASE {}").format(sql.Identifier(source_db)))
        conn.execute(sql.SQL("CREATE DATABASE {}").format(sql.Identifier(restored_db)))
    with psycopg.connect(host=host, port=port, dbname=source_db,
                         user="postgres", password=password) as conn:
        conn.execute("CREATE TABLE asuntos_prueba (id integer PRIMARY KEY, contenido text)")
        conn.execute("INSERT INTO asuntos_prueba VALUES (1, %s)", (marker,))
        conn.commit()

    with tempfile.TemporaryDirectory(prefix="mia-backup-gate-") as td:
        work = Path(td)
        app_dir = work / "app-a"
        backup_dir = work / "backups"
        try:
            backup.create_database_backup(
                pg_dump=pg_dump, app_dir=app_dir, host=host, port=port,
                db=source_db, password=password, destination_dir=backup_dir,
            )
            recovery_required = False
        except backup.BackupError as exc:
            recovery_required = "llave de recuperación" in str(exc)
        check("el primer backup exige guardar la llave de recuperación", recovery_required)

        recovery_file = work / "llave-recuperacion.txt"
        backup.export_recovery_key(app_dir, recovery_file)
        backup_path = backup.create_database_backup(
            pg_dump=pg_dump,
            app_dir=app_dir,
            host=host,
            port=port,
            db=source_db,
            password=password,
            destination_dir=backup_dir,
        )
        check("se crea un .mia-backup final", backup_path.is_file())
        check("no quedan archivos .partial", not list(backup_dir.glob("*.partial")))
        check("el dato confidencial no aparece en claro", marker.encode() not in backup_path.read_bytes())
        check("la llave local existe protegida por DPAPI", (app_dir / backup.KEY_FILE_NAME).is_file())

        recovery_text = recovery_file.read_text(encoding="utf-8").strip()
        check("la llave portable usa formato versionado", recovery_text.startswith(backup.RECOVERY_PREFIX))

        dump_path = work / "source.dump"
        header = backup.decrypt_backup_to_file(backup_path, app_dir, dump_path)
        check("el respaldo autentica y descifra", dump_path.is_file() and dump_path.stat().st_size > 0)
        check("el manifiesto identifica la base", header.get("database") == source_db)

        list_result = subprocess.run(
            [str(pg_restore), "--list", str(dump_path)], capture_output=True, text=True
        )
        check("pg_restore reconoce el dump", list_result.returncode == 0)

        restore_env = {**os.environ, "PGPASSWORD": password}
        restore_result = subprocess.run(
            [
                str(pg_restore), "--exit-on-error", "--single-transaction",
                "--no-owner", "--no-acl", "--host", host, "--port", str(port),
                "--username", "postgres", "--dbname", restored_db, str(dump_path),
            ],
            capture_output=True,
            text=True,
            env=restore_env,
        )
        check("restore real termina sin errores", restore_result.returncode == 0)
        with psycopg.connect(host=host, port=port, dbname=restored_db,
                             user="postgres", password=password) as conn:
            restored = conn.execute(
                "SELECT contenido FROM asuntos_prueba WHERE id=1"
            ).fetchone()[0]
        check("el dato restaurado coincide", restored == marker)

        # Simula equipo nuevo: importa la llave exportada y abre el mismo backup.
        app_dir_b = work / "app-b"
        backup.import_recovery_key(app_dir_b, recovery_text)
        dump_b = work / "source-b.dump"
        backup.decrypt_backup_to_file(backup_path, app_dir_b, dump_b)
        check("la llave exportada permite recuperar en otra instalación", dump_b.read_bytes() == dump_path.read_bytes())

        tampered = work / "tampered.mia-backup"
        shutil.copy2(backup_path, tampered)
        tampered_bytes = bytearray(tampered.read_bytes())
        tampered_bytes[len(tampered_bytes) // 2] ^= 0x01
        tampered.write_bytes(tampered_bytes)
        try:
            backup.decrypt_backup_to_file(tampered, app_dir, work / "tampered.dump")
            tamper_blocked = False
        except backup.BackupError:
            tamper_blocked = True
        check("una alteración del backup se detecta", tamper_blocked)
        check("un backup alterado no deja dump parcial", not (work / "tampered.dump.partial").exists())
finally:
    try:
        with psycopg.connect(autocommit=True, **admin) as conn:
            for name in (source_db, restored_db):
                conn.execute(
                    "SELECT pg_terminate_backend(pid) FROM pg_stat_activity "
                    "WHERE datname=%s AND pid <> pg_backend_pid()", (name,)
                )
                conn.execute(sql.SQL("DROP DATABASE IF EXISTS {}").format(sql.Identifier(name)))
    except Exception as exc:  # noqa: BLE001
        print(f"  [FAIL] limpieza de bases temporales: {exc}")
        failures.append("limpieza de bases temporales")

if failures:
    print(f"\nFAIL: {len(failures)} comprobaciones")
    raise SystemExit(1)
print("\nPASS: backup cifrado, autenticado y restaurado en una base limpia")
