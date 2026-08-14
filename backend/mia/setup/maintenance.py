"""Mantenimiento seguro de Mia entre PostgreSQL y los servicios de usuario.

No acepta contraseñas por argumentos: siempre las lee del `.env` privado de la
instalación. El modo `startup` limpia restos de una caída y, si hay migraciones
pendientes, crea y verifica una copia antes de aplicar el primer cambio.
"""
from __future__ import annotations

import argparse
import json
import logging
import os
import sys
import traceback
from pathlib import Path

from dotenv import dotenv_values
import psycopg
from psycopg.types.json import Json

from . import backup, db_bootstrap, paths
from .first_run import HOST, resolve_app_dir
from ..security.at_rest import encrypt_secret, is_encrypted


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


def _verified_backup(
    app_dir: Path,
    pg_bin: Path,
    settings: dict,
    *,
    require_recovery_confirmation: bool = True,
) -> Path:
    path = backup.create_verified_database_backup(
        pg_bin=pg_bin,
        app_dir=app_dir,
        host=settings["host"],
        port=settings["port"],
        db=settings["db"],
        password=settings["password"],
        require_recovery_confirmation=require_recovery_confirmation,
    )
    # Solo tras un backup ya verificado: "Mia Backups" no debe crecer sin límite
    # con una copia por cada arranque/migración. Un fallo de rotación nunca debe
    # ocultar que el backup en sí ya se creó y verificó correctamente.
    try:
        backup.rotate_backups(directory=path.parent, keep=3)
    except Exception:
        logging.getLogger("mia.setup.maintenance").exception(
            "no se pudieron rotar los respaldos antiguos"
        )
    return path


def _secret_rows(
    settings: dict, tenant_id: str | None = None
) -> tuple[list[tuple], list[tuple]]:
    kw = dict(
        host=settings["host"], port=settings["port"], dbname=settings["db"],
        user="postgres", password=settings["password"],
    )
    with psycopg.connect(**kw) as conn:
        oauth_exists = conn.execute(
            "SELECT to_regclass('public.tenant_oauth_tokens')"
        ).fetchone()[0]
        settings_exists = conn.execute(
            "SELECT to_regclass('public.tenant_settings')"
        ).fetchone()[0]
        where = " WHERE tenant_id=%s::uuid" if tenant_id else ""
        params = (tenant_id,) if tenant_id else ()
        oauth = conn.execute(
            "SELECT tenant_id::text, provider, access_token, refresh_token "
            "FROM tenant_oauth_tokens" + where,
            params,
        ).fetchall() if oauth_exists else []
        configs = conn.execute(
            "SELECT tenant_id::text, config FROM tenant_settings" + where,
            params,
        ).fetchall() if settings_exists else []
    return oauth, configs


def has_unprotected_secrets(settings: dict, tenant_id: str | None = None) -> bool:
    oauth, configs = _secret_rows(settings, tenant_id)
    for _, _, access, refresh in oauth:
        if (access and not is_encrypted(str(access))) or (refresh and not is_encrypted(str(refresh))):
            return True
    for _, raw in configs:
        cfg = raw if isinstance(raw, dict) else {}
        pinecone = cfg.get("pinecone") or {}
        if pinecone.get("api_key") and not is_encrypted(str(pinecone["api_key"])):
            return True
        servers = ((cfg.get("mcp") or {}).get("servers") or {})
        for entry in servers.values():
            if any(value and not is_encrypted(str(value))
                   for value in (entry.get("secrets") or {}).values()):
                return True
    return False


def protect_existing_secrets(
    app_dir: Path, settings: dict, tenant_id: str | None = None
) -> int:
    """Convierte secretos legacy en una transacción; devuelve valores protegidos."""
    oauth, configs = _secret_rows(settings, tenant_id)
    changed = 0
    kw = dict(
        host=settings["host"], port=settings["port"], dbname=settings["db"],
        user="postgres", password=settings["password"],
    )
    with psycopg.connect(**kw) as conn:
        for row_tenant_id, provider, access, refresh in oauth:
            new_access = (
                encrypt_secret(
                    access, tenant_id=row_tenant_id,
                    purpose=f"oauth:{provider}:access", app_dir=app_dir,
                ) if access else access
            )
            new_refresh = (
                encrypt_secret(
                    refresh, tenant_id=row_tenant_id,
                    purpose=f"oauth:{provider}:refresh", app_dir=app_dir,
                ) if refresh else refresh
            )
            access_changed = new_access != access
            refresh_changed = new_refresh != refresh
            if access_changed or refresh_changed:
                conn.execute(
                    "UPDATE tenant_oauth_tokens SET access_token=%s, refresh_token=%s "
                    "WHERE tenant_id=%s::uuid AND provider=%s",
                    (new_access, new_refresh, row_tenant_id, provider),
                )
                changed += int(access_changed) + int(refresh_changed)

        for row_tenant_id, raw in configs:
            cfg = raw if isinstance(raw, dict) else {}
            tenant_changed = 0
            pinecone = cfg.get("pinecone") or {}
            if pinecone.get("api_key") and not is_encrypted(str(pinecone["api_key"])):
                pinecone["api_key"] = encrypt_secret(
                    pinecone["api_key"], tenant_id=row_tenant_id,
                    purpose="pinecone:api_key", app_dir=app_dir,
                )
                cfg["pinecone"] = pinecone
                tenant_changed += 1
            servers = ((cfg.get("mcp") or {}).get("servers") or {})
            for slug, entry in servers.items():
                secrets = entry.get("secrets") or {}
                for key, value in list(secrets.items()):
                    if value and not is_encrypted(str(value)):
                        secrets[key] = encrypt_secret(
                            value, tenant_id=row_tenant_id, purpose=f"mcp:{slug}:{key}",
                            app_dir=app_dir,
                        )
                        tenant_changed += 1
                entry["secrets"] = secrets
            if tenant_changed:
                conn.execute(
                    "UPDATE tenant_settings SET config=%s, updated_at=now() "
                    "WHERE tenant_id=%s::uuid", (Json(cfg), row_tenant_id),
                )
                changed += tenant_changed
        conn.commit()
    return changed


def startup(app_dir: Path, pg_bin: Path, port: int | None = None) -> list[str]:
    backup.cleanup_decrypted_temps(app_dir)
    settings = _settings(app_dir, port)

    backup_done = False

    def before_mutation() -> None:
        nonlocal backup_done
        if not backup_done:
            # El upgrade automático corre antes de que exista una UI donde un
            # usuario antiguo pueda exportar su llave. La copia sigue cifrada,
            # verificada y recuperable en este perfil de Windows (DPAPI); solo
            # se relaja la confirmación portable para romper ese círculo.
            _verified_backup(
                app_dir, pg_bin, settings,
                require_recovery_confirmation=False,
            )
            backup_done = True

    needs_secret_upgrade = has_unprotected_secrets(settings)
    applied = db_bootstrap.apply_migrations(
        settings["host"], settings["port"], settings["db"], settings["password"],
        paths.migration_paths(), before_first_pending=before_mutation,
    )
    if needs_secret_upgrade:
        before_mutation()
        protect_existing_secrets(app_dir, settings)
    return applied


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
        choices=("status", "startup", "backup", "verify", "restore", "export-key", "confirm-key", "import-key"),
    )
    parser.add_argument("--pg-bin", required=True)
    parser.add_argument("--pg-port", type=int, default=None)
    parser.add_argument("--app-dir", default=None)
    parser.add_argument("--source", default=None)
    parser.add_argument("--destination", default=None)
    parser.add_argument(
        "--confirm-database",
        default=None,
        help="Nombre exacto de la base que se autoriza restaurar.",
    )
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
        elif args.action == "restore":
            if not args.source:
                raise RuntimeError("Selecciona la copia que quieres recuperar.")
            settings = _settings(app_dir, args.pg_port)
            if args.confirm_database != settings["db"]:
                raise RuntimeError(
                    f"Confirma la recuperación escribiendo exactamente: {settings['db']}"
                )
            safety = backup.restore_database_backup(
                backup_path=Path(args.source),
                pg_bin=pg_bin,
                app_dir=app_dir,
                host=settings["host"],
                port=settings["port"],
                db=settings["db"],
                password=settings["password"],
                confirmed_database=args.confirm_database,
            )
            print(
                "MIA-MAINTENANCE: recuperación completada; "
                f"la copia de seguridad previa quedó verificada como {safety.name}."
            )
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
