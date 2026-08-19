"""Mia · setup.first_run — bootstrap de primer arranque (F2, Contrato 1).

Invocable como:
    mia-backend.exe --first-run --pg-bin <dir> --pg-data <dir> --pg-port <port> [--app-dir <dir>]
    python -m mia.setup.first_run --pg-bin <dir> --pg-data <dir> --pg-port <port> [--app-dir <dir>]

La cáscara de escritorio (Tauri) lo llama en una máquina limpia, ANTES de
arrancar Postgres/backend/frontend normalmente, para dejar todo listo: carpeta
de datos, .env semilla, initdb endurecido, rol/DB/extensiones/schema,
migraciones 003→030 y checkpointer. Cada paso es idempotente: una segunda
corrida no debe cambiar nada (ni regenerar secretos del .env).

Progreso: cada paso importante imprime una línea `MIA-SETUP: <texto en llano>`
a stdout, pensada para que la cáscara la muestre tal cual en el splash. En
fallo, el proceso termina con exit != 0 y la ÚLTIMA línea de stdout es un
mensaje en llano (el detalle técnico, si lo hay, va a stderr antes de eso).
"""
from __future__ import annotations

import argparse
import os
import re
import secrets
import shutil
import subprocess
import sys
import traceback
from datetime import datetime, timezone
from pathlib import Path

from dotenv import dotenv_values

from . import db_bootstrap, paths

HOST = "127.0.0.1"

# Marcador de finalización (contrato compartido con la cáscara Rust, sesión 44):
# la cáscara re-ejecuta el setup si falta este archivo, PG_VERSION o el .env. Se
# escribe SOLO como último paso, tras rol/DB/schema/migraciones/checkpointer OK.
COMPLETION_MARKER_NAME = ".mia-setup-complete"

# Subcarpeta privada de app_dir para archivos efímeros del setup (p. ej. el
# pwfile del superusuario de initdb) — nunca %TEMP% compartido con otros
# procesos/usuarios de la máquina.
SETUP_TMP_DIRNAME = ".setup-tmp"


def _progress(msg: str) -> None:
    print(f"MIA-SETUP: {msg}", flush=True)


def _atomic_write_text(path: Path, text: str) -> None:
    """Escribe `text` en `path` de forma atómica: `<path>.tmp` -> flush + fsync
    -> `os.replace`. Nunca un write directo — si el proceso muere a mitad de
    camino (crash, corte de energía), el archivo destino queda intacto (su
    versión anterior) o completo, nunca a medias."""
    tmp_path = path.parent / (path.name + ".tmp")
    with open(tmp_path, "w", encoding="utf-8", newline="\n") as f:
        f.write(text)
        f.flush()
        os.fsync(f.fileno())
    os.replace(tmp_path, path)


def write_completion_marker(app_dir: Path) -> Path:
    """Marcador final `.mia-setup-complete`: una línea con la fecha ISO UTC en
    que el setup terminó bien. Escritura atómica (mismo motivo que el .env)."""
    marker_path = app_dir / COMPLETION_MARKER_NAME
    stamp = datetime.now(timezone.utc).isoformat(timespec="seconds")
    _atomic_write_text(marker_path, stamp + "\n")
    return marker_path


def restrict_env_permissions(env_path: Path) -> None:
    """Blindaje de ACL del `.env` en Windows: quita la herencia de permisos y
    deja SOLO al usuario actual con control total. El `.env` guarda secretos
    (JWT_SECRET, contraseñas de Postgres, LITELLM_MASTER_KEY): sin esto, otras
    cuentas de la máquina podrían leerlo por permisos heredados de la carpeta.

    FAIL-SOFT por contrato: si icacls no está, falla o el entorno no es Windows,
    se registra en stderr y se continúa — NUNCA se tumba el arranque por esto
    (un `.env` un poco más expuesto es peor que MIA que no abre)."""
    if os.name != "nt":
        return
    user = os.environ.get("USERNAME", "").strip()
    if not user:
        print("AVISO: no pude blindar el .env (sin USERNAME en el entorno).", file=sys.stderr)
        return
    domain = os.environ.get("USERDOMAIN", "").strip()
    # DOMAIN\user resuelve mejor tanto cuentas locales como de dominio; si no hay
    # USERDOMAIN, el nombre a secas también lo resuelve icacls en la mayoría de casos.
    principal = f"{domain}\\{user}" if domain else user
    try:
        subprocess.run(
            ["icacls", str(env_path), "/inheritance:r", "/grant:r", f"{principal}:F"],
            check=True, capture_output=True, text=True,
        )
    except Exception as exc:  # noqa: BLE001 — fail-soft: el arranque no depende de esto
        print(
            f"AVISO: no pude restringir los permisos del .env ({type(exc).__name__}): {exc}",
            file=sys.stderr,
        )


def resolve_app_dir(cli_app_dir: str | None) -> Path:
    """--app-dir > env MIA_APP_DIR > la lógica de config.PROJECT_ROOT (importada,
    no duplicada). Se revisan primero el argumento y el env DIRECTAMENTE (no vía
    config) para no depender de si `mia.config` ya fue importado antes en este
    mismo proceso (p. ej. por entry_backend.py, que importa mia.api.main al
    tope del módulo) con un MIA_APP_DIR distinto."""
    if cli_app_dir:
        return Path(cli_app_dir).resolve()
    env_dir = os.getenv("MIA_APP_DIR", "").strip()
    if env_dir:
        return Path(env_dir).resolve()
    from .. import config  # reusa la resolución frozen/dev de config.py

    return config.PROJECT_ROOT


def ensure_seed_env(app_dir: Path, pg_port: int) -> tuple[Path, bool]:
    """.env semilla, generado UNA sola vez. Si ya existe, se deja intacto —
    NUNCA se regeneran secretos existentes (decisión de diseño #3 del plan).
    Devuelve (ruta, True si se acaba de crear)."""
    env_path = app_dir / ".env"
    if env_path.exists():
        return env_path, False

    jwt_secret = secrets.token_urlsafe(48)
    pg_password = secrets.token_urlsafe(24)
    pg_app_password = secrets.token_urlsafe(24)
    # Mismo valor para master_key (LiteLLM) y la API key que el backend manda como
    # Bearer (decisión #3): el proxy exige master_key, el backend manda esa clave.
    litellm_key = "sk-mia-" + secrets.token_urlsafe(24)

    lines = [
        f"JWT_SECRET={jwt_secret}",
        "PG_HOST=127.0.0.1",
        f"PG_PORT={pg_port}",
        "PG_DB=mia",
        f"PG_PASSWORD={pg_password}",
        f"PG_APP_PASSWORD={pg_app_password}",
        f"DATABASE_URL=postgresql://mia_app:{pg_app_password}@127.0.0.1:{pg_port}/mia",
        "LITELLM_BASE_URL=http://127.0.0.1:4000",
        f"LITELLM_API_KEY={litellm_key}",
        f"LITELLM_MASTER_KEY={litellm_key}",
        "MIA_CORS_ORIGINS=http://localhost:3100,http://127.0.0.1:3100",
        "MIA_API_HOST=127.0.0.1",
        "VOYAGE_API_KEY=",
        # MIA_ENV=prod (sub-tarea 7 del contrato): esta instancia corre en el
        # equipo real del abogado, no en un entorno de desarrollo compartido.
        # config.py endurece con esto: docs/redoc apagados, cookies OAuth
        # `secure=True`, JWT exige `exp` — y auth.py SIEMPRE firma `exp`
        # (routes/auth.py:150-152), así que este endurecimiento no rompe el login.
        "MIA_ENV=prod",
        # Las marcas de membresía Codex NO se guardan: Tauri las inyecta solo en
        # el proceso local que inicia. Un bootstrap de servidor no puede heredarlas.
        "",
    ]
    _atomic_write_text(env_path, "\n".join(lines))
    return env_path, True


def _set_conf_value(text: str, key: str, value: str) -> str:
    """Fija `key = value` en un postgresql.conf: reemplaza la línea (comentada o
    no) si existe, o la agrega al final. Idempotente."""
    pattern = re.compile(rf"(?m)^#?\s*{re.escape(key)}\s*=.*$")
    line = f"{key} = {value}"
    if pattern.search(text):
        return pattern.sub(line, text, count=1)
    return text.rstrip("\n") + f"\n{line}\n"


def _require_pg_binaries(pg_bin: Path) -> None:
    missing = [
        exe for exe in ("initdb.exe", "pg_ctl.exe", "postgres.exe", "pg_isready.exe")
        if not (pg_bin / exe).is_file()
    ]
    if missing:
        raise RuntimeError(
            f"No se encontró Postgres en la carpeta indicada ({pg_bin}): "
            f"faltan {', '.join(missing)}."
        )


def _clear_dir_contents(directory: Path) -> None:
    """Vacía el CONTENIDO de `directory` (archivos y subcarpetas) pero deja la
    carpeta misma en su sitio. Nunca toca nada fuera de `directory`."""
    for entry in directory.iterdir():
        if entry.is_dir() and not entry.is_symlink():
            shutil.rmtree(entry, ignore_errors=True)
        else:
            entry.unlink(missing_ok=True)


def run_initdb(
    pg_bin: Path, pg_data: Path, pg_port: int, superuser_pw: str, setup_tmp_dir: Path
) -> bool:
    """initdb endurecido (decisión #7): UTF8, locale C, scram-sha-256, contraseña
    del superusuario vía --pwfile en una subcarpeta PRIVADA de app_dir (nunca
    %TEMP% compartido, nunca en la línea de comandos).

    Se salta si `<pg_data>/PG_VERSION` ya existe. Si `pg_data` existe pero NO
    está vacío y tampoco tiene PG_VERSION, es un initdb interrumpido de una
    corrida anterior (la ruta la controla el instalador, no el usuario): se
    vacía el CONTENIDO de `pg_data` (nunca la carpeta padre ni nada fuera de
    ella) antes de reintentar. Devuelve True si corrió initdb."""
    if (pg_data / "PG_VERSION").exists():
        return False

    if pg_data.exists() and any(pg_data.iterdir()):
        _progress(
            "Se encontró un intento anterior de inicialización incompleto; "
            "se limpia antes de volver a intentarlo..."
        )
        _clear_dir_contents(pg_data)

    pg_data.mkdir(parents=True, exist_ok=True)
    setup_tmp_dir.mkdir(parents=True, exist_ok=True)
    pwfile_path = setup_tmp_dir / "pg-superuser-pw.txt"
    try:
        with open(pwfile_path, "w", encoding="utf-8") as pf:
            pf.write(superuser_pw + "\n")
        subprocess.run(
            [
                str(pg_bin / "initdb.exe"), "-D", str(pg_data), "-U", "postgres",
                f"--pwfile={pwfile_path}", "-E", "UTF8", "--locale=C",
                "--auth=scram-sha-256",
            ],
            check=True, capture_output=True, text=True,
        )
    except subprocess.CalledProcessError as exc:
        raise RuntimeError(f"initdb falló: {exc.stderr or exc.stdout}") from exc
    finally:
        pwfile_path.unlink(missing_ok=True)
        try:
            setup_tmp_dir.rmdir()
        except OSError:
            pass  # no vacía o ya borrada: el finally de main() la limpia igual

    conf_path = pg_data / "postgresql.conf"
    conf_text = conf_path.read_text(encoding="utf-8")
    conf_text = _set_conf_value(conf_text, "listen_addresses", "'127.0.0.1'")
    conf_text = _set_conf_value(conf_text, "port", str(pg_port))
    conf_path.write_text(conf_text, encoding="utf-8")
    return True


def is_postgres_up(pg_bin: Path, host: str, port: int) -> bool:
    result = subprocess.run(
        [str(pg_bin / "pg_isready.exe"), "-h", host, "-p", str(port)],
        capture_output=True, text=True,
    )
    return result.returncode == 0


def start_own_postgres(pg_bin: Path, pg_data: Path, pg_port: int) -> None:
    """`pg_ctl -w start`: bloquea hasta que Postgres acepta conexiones.

    OJO (Windows, cuelgue real detectado en el gate de la sesión 43): aquí NO
    se puede usar capture_output=True. pg_ctl lanza el demonio postgres.exe,
    que HEREDA los handles de stdout/stderr; leer esos pipes hasta EOF deja a
    este proceso bloqueado mientras Postgres siga vivo. El log del servidor va
    a un archivo (-l) dentro del propio pg_data y de ahí se saca el detalle si
    el arranque falla."""
    log_path = pg_data / "mia-setup-postgres.log"
    result = subprocess.run(
        [
            str(pg_bin / "pg_ctl.exe"), "-D", str(pg_data), "-w",
            "-l", str(log_path), "-o", f"-p {pg_port}", "start",
        ],
        stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
    )
    if result.returncode != 0:
        detail = ""
        if log_path.is_file():
            detail = log_path.read_text(encoding="utf-8", errors="replace")[-2000:]
        raise RuntimeError(f"No se pudo encender la base de datos. {detail}".strip())


def stop_own_postgres(pg_bin: Path, pg_data: Path) -> None:
    """`pg_ctl -m fast stop`. No propaga error: se llama desde cleanup/finally,
    donde ya puede haber otro error en curso que es el que de verdad importa."""
    subprocess.run(
        [str(pg_bin / "pg_ctl.exe"), "-D", str(pg_data), "-m", "fast", "stop"],
        capture_output=True, text=True,
    )


def main(argv: list[str] | None = None) -> int:
    # La cascara Tauri lee este stdout con fs::read_to_string (UTF-8 estricto)
    # para mostrarle al abogado la ULTIMA LINEA como motivo del fallo. En
    # Windows, sin esto, Python decide la codificacion segun el locale de la
    # maquina (cp1252 en un Windows en espanol): los acentos del mensaje
    # saldrian en bytes que Rust no puede leer y el abogado se quedaria sin
    # motivo. Se fija explicitamente para no depender de la maquina destino.
    for _stream in (sys.stdout, sys.stderr):
        try:
            _stream.reconfigure(encoding="utf-8", errors="replace")  # type: ignore[union-attr]
        except (AttributeError, ValueError, OSError):
            pass  # fail-soft: nunca impedir el primer arranque por esto

    parser = argparse.ArgumentParser(prog="mia-backend --first-run")
    parser.add_argument("--pg-bin", required=True)
    parser.add_argument("--pg-data", required=True)
    parser.add_argument("--pg-port", required=True, type=int)
    parser.add_argument("--app-dir", default=None)
    args = parser.parse_args(argv)

    pg_bin = Path(args.pg_bin)
    pg_data = Path(args.pg_data)
    pg_port = args.pg_port
    app_dir = resolve_app_dir(args.app_dir)
    setup_tmp_dir = app_dir / SETUP_TMP_DIRNAME

    started_own_postgres = False
    stopped_own_postgres = False

    def stop_if_needed() -> None:
        nonlocal stopped_own_postgres
        if started_own_postgres and not stopped_own_postgres:
            stop_own_postgres(pg_bin, pg_data)
            stopped_own_postgres = True

    try:
        _progress("Preparando la carpeta de datos de Mia...")
        app_dir.mkdir(parents=True, exist_ok=True)

        # Desajuste cluster-existe + .env-ausente: si ya hay un cluster
        # inicializado pero se perdió (o nunca existió en este app_dir) el
        # .env, NO se puede regenerar secretos — quedarían sin calzar con las
        # credenciales ya grabadas dentro del cluster (rol mia_app, etc.).
        # Mejor exigir borrar el cluster que dejar a Mia con una contraseña
        # que nunca va a servir.
        env_path = app_dir / ".env"
        if (pg_data / "PG_VERSION").exists() and not env_path.exists():
            raise RuntimeError(
                "MIA encontró una base de datos previa pero se perdió su "
                f"configuración. Para empezar de cero, borra la carpeta {pg_data} "
                "y vuelve a abrir MIA."
            )

        _progress("Generando la configuración inicial...")
        env_path, created = ensure_seed_env(app_dir, pg_port)
        _progress(".env creado." if created else "La configuración ya existía, se conserva.")
        # Blindaje de ACL del .env (Windows): tras escribirlo, restringe su
        # lectura al usuario actual. Idempotente y fail-soft: se aplica corra o
        # no se haya recién creado, por si una corrida anterior lo dejó sin ACL.
        restrict_env_permissions(env_path)

        env_values = dotenv_values(env_path)
        super_pw = env_values.get("PG_PASSWORD") or ""
        app_pw = env_values.get("PG_APP_PASSWORD") or ""
        db_name = env_values.get("PG_DB") or "mia"
        if not super_pw or not app_pw:
            raise RuntimeError(
                "La configuración (.env) no tiene las contraseñas de base de datos."
            )

        _require_pg_binaries(pg_bin)

        _progress("Inicializando la base de datos por primera vez (puede tardar unos minutos)...")
        if not run_initdb(pg_bin, pg_data, pg_port, super_pw, setup_tmp_dir):
            _progress("La base de datos ya estaba inicializada, se conserva.")

        _progress("Encendiendo la base de datos...")
        if is_postgres_up(pg_bin, HOST, pg_port):
            _progress("La base de datos ya estaba encendida, se reutiliza.")
        else:
            start_own_postgres(pg_bin, pg_data, pg_port)
            started_own_postgres = True
            _progress("Base de datos encendida.")

        _progress("Creando el usuario y la base de datos de Mia...")
        db_bootstrap.ensure_app_role_and_database(HOST, pg_port, db_name, super_pw, app_pw)

        _progress("Aplicando la estructura de datos (tablas y extensiones)...")
        schema_text = paths.schema_sql_path().read_text(encoding="utf-8")
        db_bootstrap.apply_extensions_and_schema(HOST, pg_port, db_name, super_pw, schema_text)

        _progress("Aplicando las actualizaciones de la base de datos...")
        migrations = paths.migration_paths()
        applied = db_bootstrap.apply_migrations(HOST, pg_port, db_name, super_pw, migrations)
        _progress(f"Se aplicaron {len(applied)} actualizaciones.")

        _progress("Preparando la memoria de conversación del agente...")
        db_bootstrap.setup_checkpointer(HOST, pg_port, db_name, super_pw)

        # Marcador de finalización: ÚLTIMO paso, solo tras rol/DB/schema/
        # migraciones/checkpointer OK. La cáscara lo usa para decidir si debe
        # re-ejecutar el setup; escribirlo antes de tiempo lo volvería falso.
        write_completion_marker(app_dir)

        stop_if_needed()
        _progress("Todo quedó listo. Mia puede arrancar.")
        return 0
    except Exception as exc:  # noqa: BLE001 - error de preparación inicial: se reporta en llano
        traceback.print_exc()  # detalle técnico a stderr; NUNCA es la última línea de stdout
        _progress(f"No se pudo preparar Mia: {exc}")
        return 1
    finally:
        stop_if_needed()  # red de seguridad si el error ocurrió después de encender Postgres
        # Limpieza de la subcarpeta privada de temporales del setup (pwfile de
        # initdb, etc.): siempre, corra o no haya corrido initdb en esta
        # ejecución, y también si una corrida anterior dejó restos por un
        # crash a mitad de camino.
        shutil.rmtree(setup_tmp_dir, ignore_errors=True)


if __name__ == "__main__":
    sys.exit(main())
