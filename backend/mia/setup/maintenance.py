"""Mantenimiento seguro de Mia entre PostgreSQL y los servicios de usuario.

No acepta contraseñas por argumentos: siempre las lee del `.env` privado de la
instalación. El modo `startup` limpia restos de una caída y, si hay migraciones
pendientes, crea y verifica una copia antes de aplicar el primer cambio.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import traceback
from pathlib import Path

from dotenv import dotenv_values

from . import backup, db_bootstrap, paths
from .first_run import HOST, resolve_app_dir


def _settings(app_dir: Path, port_override: int | None = None) -> dict:
    env_path = app_dir / ".env"
    if not env_path.is_file():
        raise RuntimeError("No encuentro la configuración local de Mia.")
    values = dotenv_values(env_path)
    password = str(values.get("PG_PASSWORD") or "")
    if not password:
        raise RuntimeError("La configuración local no tiene la llave de la base de datos.")
    return {
        "host": str(values.get("PG_HOST") or HOST),
        "port": int(port_override or values.get("PG_PORT") or 55432),
        "db": str(values.get("PG_DB") or "mia"),
        "password": password,
    }


def resolve_pg_bin(value: str | Path | None = None) -> Path:
    """Ruta entregada por el supervisor; en bundle queda además anclada al exe."""
    raw = str(value or os.getenv("MIA_PG_BIN") or "").strip()
    if raw:
        return Path(raw)
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parents[1] / "pgsql" / "bin"
    raise RuntimeError("Mia no recibió la ubicación de su base de datos.")


def _verified_backup(app_dir: Path, pg_bin: Path, settings: dict) -> Path:
    return backup.create_verified_database_backup(
        pg_bin=pg_bin,
        app_dir=app_dir,
        host=settings["host"],
        port=settings["port"],
        db=settings["db"],
        password=settings["password"],
    )


def startup(app_dir: Path, pg_bin: Path, port: int | None = None) -> list[str]:
    backup.cleanup_decrypted_temps(app_dir)
    settings = _settings(app_dir, port)

    def before_migrations() -> None:
        _verified_backup(app_dir, pg_bin, settings)

    return db_bootstrap.apply_migrations(
        settings["host"], settings["port"], settings["db"], settings["password"],
        paths.migration_paths(), before_first_pending=before_migrations,
    )


def protection_status(app_dir: Path) -> dict:
    files: list[Path] = []
    try:
        files = sorted(
            backup.default_backup_dir().glob("*.mia-backup"),
            key=lambda path: path.stat().st_mtime,
            reverse=True,
        )
    except OSError:
        files = []
    latest = files[0] if files else None
    last_at = None
    if latest is not None:
        try:
            from datetime import datetime, timezone

            last_at = datetime.fromtimestamp(latest.stat().st_mtime, tz=timezone.utc).isoformat()
        except OSError:
            latest = None
    return {
        "recovery_key_created": (app_dir / backup.KEY_FILE_NAME).is_file(),
        "recovery_key_saved": backup.recovery_key_confirmed(app_dir),
        "last_backup_name": latest.name if latest else None,
        "last_backup_at": last_at,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="mia-backend --maintenance")
    parser.add_argument(
        "action",
        choices=("status", "startup", "backup", "verify", "export-key", "confirm-key", "import-key"),
    )
    parser.add_argument("--pg-bin", required=True)
    parser.add_argument("--pg-port", type=int, default=None)
    parser.add_argument("--app-dir", default=None)
    parser.add_argument("--source", default=None)
    parser.add_argument("--destination", default=None)
    args = parser.parse_args(argv)

    app_dir = resolve_app_dir(args.app_dir)
    pg_bin = resolve_pg_bin(args.pg_bin)
    try:
        if args.action == "status":
            print("MIA-MAINTENANCE-JSON:" + json.dumps(protection_status(app_dir)))
        elif args.action == "startup":
            applied = startup(app_dir, pg_bin, args.pg_port)
            print(f"MIA-MAINTENANCE: lista; {len(applied)} actualizaciones aplicadas.")
        elif args.action == "backup":
            _verified_backup(app_dir, pg_bin, _settings(app_dir, args.pg_port))
            print("MIA-MAINTENANCE: copia creada y comprobada.")
        elif args.action == "verify":
            if not args.source:
                raise RuntimeError("Selecciona la copia que quieres comprobar.")
            backup.verify_database_backup(
                backup_path=Path(args.source), app_dir=app_dir, pg_bin=pg_bin,
            )
            print("MIA-MAINTENANCE: la copia está completa y puede recuperarse.")
        elif args.action == "export-key":
            if not args.destination:
                raise RuntimeError("Selecciona dónde guardar la llave de recuperación.")
            backup.export_recovery_key(app_dir, Path(args.destination))
            print("MIA-MAINTENANCE: llave de recuperación guardada.")
        elif args.action == "confirm-key":
            backup.confirm_recovery_key_saved(app_dir)
            print("MIA-MAINTENANCE: llave de recuperación confirmada.")
        else:
            if not args.source:
                raise RuntimeError("Selecciona tu llave de recuperación.")
            recovery_text = Path(args.source).read_text(encoding="utf-8-sig")
            backup.import_recovery_key(app_dir, recovery_text)
            print("MIA-MAINTENANCE: llave de recuperación aceptada.")
        return 0
    except Exception as exc:  # noqa: BLE001 - frontera CLI, detalle al log
        traceback.print_exc(file=sys.stderr)
        print(f"MIA-MAINTENANCE: no se pudo completar: {exc}")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
