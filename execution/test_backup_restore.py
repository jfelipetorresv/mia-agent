"""Gate F1: backup cifrado y restauración real en una base limpia."""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
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
                pg_bin=pg_bin, app_dir=app_dir, host=host, port=port,
                db=source_db, password=password, destination_dir=backup_dir,
            )
            recovery_required = False
        except backup.BackupError as exc:
            recovery_required = "llave de recuperación" in str(exc)
        check("el primer backup exige guardar la llave de recuperación", recovery_required)

        startup_backup = backup.create_verified_database_backup(
            pg_bin=pg_bin, app_dir=app_dir, host=host, port=port,
            db=source_db, password=password, destination_dir=backup_dir,
            require_recovery_confirmation=False,
        )
        check("el upgrade automático puede crear una copia local comprobada",
              startup_backup.is_file())
        check("el upgrade no finge que la llave portable ya fue guardada",
              not backup.recovery_key_confirmed(app_dir))

        recovery_file = work / "llave-recuperacion.txt"
        backup.export_recovery_key(app_dir, recovery_file)
        check("exportar no finge que la llave ya fue guardada",
              not backup.recovery_key_confirmed(app_dir))
        backup.confirm_recovery_key_saved(app_dir)
        backup_path = backup.create_database_backup(
            pg_bin=pg_bin,
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

        # La exportación nunca puede dejar la llave si Windows no logra fijar ACL.
        unsafe_export = work / "llave-insegura.txt"
        original_restrict = backup._restrict_windows_file
        try:
            backup._restrict_windows_file = lambda _path: (_ for _ in ()).throw(
                backup.BackupError("fallo ACL simulado")
            )
            try:
                backup.export_recovery_key(app_dir, unsafe_export)
            except backup.BackupError:
                pass
        finally:
            backup._restrict_windows_file = original_restrict
        check("un fallo de permisos no deja la llave exportada", not unsafe_export.exists())

        existing_export = work / "llave-existente.txt"
        existing_export.write_text("copia-anterior", encoding="utf-8")
        original_restrict = backup._restrict_windows_file
        try:
            backup._restrict_windows_file = lambda _path: (_ for _ in ()).throw(
                backup.BackupError("fallo ACL simulado")
            )
            try:
                backup.export_recovery_key(app_dir, existing_export)
            except backup.BackupError:
                pass
        finally:
            backup._restrict_windows_file = original_restrict
        check("un fallo de permisos conserva una exportación anterior",
              existing_export.read_text(encoding="utf-8") == "copia-anterior")

        # Si falla la ACL al importar/rotar, se conserva la llave local anterior.
        old_blob = (app_dir / backup.KEY_FILE_NAME).read_bytes()
        original_restrict = backup._restrict_windows_file
        try:
            backup._restrict_windows_file = lambda _path: (_ for _ in ()).throw(
                backup.BackupError("fallo ACL simulado")
            )
            try:
                backup.import_recovery_key(app_dir, recovery_text)
            except backup.BackupError:
                pass
        finally:
            backup._restrict_windows_file = original_restrict
        check("un fallo de permisos conserva la llave local anterior",
              (app_dir / backup.KEY_FILE_NAME).read_bytes() == old_blob)

        restore_env = {**os.environ, "PGPASSWORD": password}
        with backup.decrypted_backup_temp(backup_path, app_dir) as (dump_path, header):
            check("el respaldo autentica y descifra", dump_path.is_file() and dump_path.stat().st_size > 0)
            check("el manifiesto identifica la base", header.get("database") == source_db)
            original_dump = dump_path.read_bytes()
            list_result = subprocess.run(
                [str(pg_restore), "--list", str(dump_path)], capture_output=True, text=True
            )
            check("pg_restore reconoce el dump", list_result.returncode == 0)
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
        check("el dump descifrado siempre se elimina", not dump_path.exists())
        with psycopg.connect(host=host, port=port, dbname=restored_db,
                             user="postgres", password=password) as conn:
            restored = conn.execute(
                "SELECT contenido FROM asuntos_prueba WHERE id=1"
            ).fetchone()[0]
        check("el dato restaurado coincide", restored == marker)

        # La misma ruta que usa el CLI debe preservar el estado anterior y
        # restaurar atómicamente la base instalada, no solo descifrar el dump.
        with psycopg.connect(host=host, port=port, dbname=source_db,
                             user="postgres", password=password) as conn:
            conn.execute("UPDATE asuntos_prueba SET contenido='estado-alterado' WHERE id=1")
            conn.commit()
        safety_backup = backup.restore_database_backup(
            backup_path=backup_path,
            pg_bin=pg_bin,
            app_dir=app_dir,
            host=host,
            port=port,
            db=source_db,
            password=password,
            confirmed_database=source_db,
        )
        check("restore CLI crea antes una copia de seguridad verificada",
              safety_backup.is_file())
        with psycopg.connect(host=host, port=port, dbname=source_db,
                             user="postgres", password=password) as conn:
            restored_in_place = conn.execute(
                "SELECT contenido FROM asuntos_prueba WHERE id=1"
            ).fetchone()[0]
        check("restore CLI repone el dato original en la base instalada",
              restored_in_place == marker)

        # Simula equipo nuevo: importa la llave exportada y abre el mismo backup.
        app_dir_b = work / "app-b"
        backup.import_recovery_key(app_dir_b, recovery_text)
        with backup.decrypted_backup_temp(backup_path, app_dir_b) as (dump_b, _):
            check("la llave exportada permite recuperar en otra instalación", dump_b.read_bytes() == original_dump)

        tampered = work / "tampered.mia-backup"
        shutil.copy2(backup_path, tampered)
        tampered_bytes = bytearray(tampered.read_bytes())
        tampered_bytes[len(tampered_bytes) // 2] ^= 0x01
        tampered.write_bytes(tampered_bytes)
        try:
            with backup.decrypted_backup_temp(tampered, app_dir):
                pass
            tamper_blocked = False
        except backup.BackupError:
            tamper_blocked = True
        check("una alteración del backup se detecta", tamper_blocked)
        check("un backup alterado no deja dump parcial", not list((app_dir / ".maintenance").glob("*.partial")))

        # Restaurar no debe inventar una llave nueva ni mutar una instalación vacía.
        empty_app = work / "sin-llave"
        try:
            with backup.decrypted_backup_temp(backup_path, empty_app):
                pass
        except backup.BackupError:
            pass
        check("verificar sin llave no crea una llave nueva", not (empty_app / backup.KEY_FILE_NAME).exists())

        stale = app_dir / ".maintenance" / "restore-corte.dump"
        stale.write_bytes(marker.encode())
        check("el siguiente mantenimiento limpia dumps de una caída anterior",
              backup.cleanup_decrypted_temps(app_dir) == 1 and not stale.exists())

        # En modo instalado un binario sustituido no recibe PGPASSWORD.
        fake_pg = work / "pgsql-falso"
        fake_bin = fake_pg / "bin"
        fake_bin.mkdir(parents=True)
        for tool in ("pg_dump.exe", "pg_restore.exe", "pg_ctl.exe", "pg_isready.exe"):
            (fake_bin / tool).write_bytes(b"no-es-postgresql")
        (fake_pg / backup.PG_MANIFEST_NAME).write_text(
            json.dumps({"version": 1, "sha256": {
                tool: "0" * 64 for tool in
                ("pg_dump.exe", "pg_restore.exe", "pg_ctl.exe", "pg_isready.exe")
            }}), encoding="utf-8"
        )
        try:
            backup.create_database_backup(
                pg_bin=fake_bin, app_dir=app_dir, host=host, port=port,
                db=source_db, password=password, destination_dir=backup_dir,
            )
            substituted_blocked = False
        except backup.BackupError as exc:
            substituted_blocked = "no coincide" in str(exc)
        check("una herramienta PostgreSQL sustituida se bloquea", substituted_blocked)

        # META D (gap 4/5): rotate_backups conserva solo los `keep` más recientes.
        fake_dir = work / "backups-falsos"
        fake_dir.mkdir()
        fake_paths = []
        now = time.time()
        for i in range(5):
            p = fake_dir / f"mia-falso-{i}{backup.BACKUP_SUFFIX}"
            p.write_bytes(b"contenido-falso")
            # mtimes estrictamente descendentes: i=0 es el más antiguo, i=4 el más nuevo.
            os.utime(p, (now + i, now + i))
            fake_paths.append(p)
        removed_fake = backup.rotate_backups(directory=fake_dir, keep=3)
        remaining_fake = {p.name for p in fake_dir.glob(f"*{backup.BACKUP_SUFFIX}")}
        check("rotate_backups (falsos) deja exactamente 3 archivos", len(remaining_fake) == 3)
        check("rotate_backups (falsos) conserva los 3 más recientes",
              remaining_fake == {fake_paths[2].name, fake_paths[3].name, fake_paths[4].name})
        check("rotate_backups (falsos) borra los 2 más antiguos",
              {p.name for p in removed_fake} == {fake_paths[0].name, fake_paths[1].name})

        # 4 respaldos REALES (ya creados por create_verified_database_backup /
        # create_database_backup arriba: 2 en backup_dir) + 2 más -> deben quedar 3.
        backup.create_verified_database_backup(
            pg_bin=pg_bin, app_dir=app_dir, host=host, port=port,
            db=source_db, password=password, destination_dir=backup_dir,
            require_recovery_confirmation=False,
        )
        time.sleep(1.1)  # mtime de FAT/NTFS en llamadas rápidas puede empatar al segundo
        backup.create_verified_database_backup(
            pg_bin=pg_bin, app_dir=app_dir, host=host, port=port,
            db=source_db, password=password, destination_dir=backup_dir,
            require_recovery_confirmation=False,
        )
        before_rotate = list(backup_dir.glob(f"*{backup.BACKUP_SUFFIX}"))
        check("hay 4 respaldos reales antes de rotar", len(before_rotate) == 4)
        backup.rotate_backups(directory=backup_dir, keep=3)
        after_rotate = list(backup_dir.glob(f"*{backup.BACKUP_SUFFIX}"))
        check("rotate_backups (reales) deja exactamente 3 respaldos", len(after_rotate) == 3)
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
