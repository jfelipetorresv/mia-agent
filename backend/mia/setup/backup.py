"""Backups cifrados y verificables de PostgreSQL para Mia local-first.

El dump nunca se escribe en claro: ``pg_dump`` entrega el flujo por stdout y
AES-256-GCM lo cifra directamente a un ``.partial`` que solo se renombra tras
cerrar y verificar el tag. La llave vive envuelta por Windows DPAPI; una copia
de recuperación puede exportarse para restaurar en otro equipo.
"""
from __future__ import annotations

import base64
import hashlib
import json
import os
import struct
import subprocess
import sys
import threading
import time
import uuid
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import BinaryIO

from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes

from ..security import dpapi

MAGIC = b"MIA-BACKUP-V1\n"
BACKUP_SUFFIX = ".mia-backup"
KEY_FILE_NAME = ".mia-backup-key.dpapi"
RECOVERY_MARKER_NAME = ".mia-backup-recovery-confirmed"
RECOVERY_PREFIX = "MIA-RECOVERY-V1:"
_CHUNK_SIZE = 1024 * 1024
PG_MANIFEST_NAME = "mia-pg-tools.sha256.json"
_RESTORE_LOCK = threading.Lock()


class BackupError(RuntimeError):
    pass


def _atomic_write(path: Path, data: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_name(f".{path.name}.{uuid.uuid4().hex}.tmp")
    try:
        with open(temp, "xb") as handle:
            handle.write(data)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temp, path)
    finally:
        temp.unlink(missing_ok=True)


def _restrict_windows_file(path: Path) -> None:
    if os.name != "nt":
        return
    user = os.environ.get("USERNAME", "").strip()
    if not user:
        raise BackupError("Windows no informó el usuario actual para proteger la llave.")
    domain = os.environ.get("USERDOMAIN", "").strip()
    principal = f"{domain}\\{user}" if domain else user
    system_root = Path(os.environ.get("SYSTEMROOT") or r"C:\Windows")
    icacls = system_root / "System32" / "icacls.exe"
    if not icacls.is_file():
        raise BackupError("Windows no encontró su herramienta segura de permisos.")
    result = subprocess.run(
        [str(icacls), str(path), "/inheritance:r", "/grant:r", f"{principal}:F"],
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        raise BackupError("Windows no pudo restringir el archivo de recuperación.")


def _restrict_or_remove(path: Path) -> None:
    """Nunca deja una llave en claro si Windows no logra proteger su ACL."""
    try:
        _restrict_windows_file(path)
    except Exception:
        path.unlink(missing_ok=True)
        raise


def _atomic_write_private(path: Path, data: bytes) -> None:
    """Protege el temporal ANTES de publicar; conserva el destino viejo si falla."""
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_name(f".{path.name}.{uuid.uuid4().hex}.private")
    try:
        # El archivo nace VACÍO; se restringe antes de que contenga un solo
        # byte sensible. Así no existe una ventana entre escritura e icacls.
        with open(temp, "xb"):
            pass
        _restrict_windows_file(temp)
        with open(temp, "r+b") as handle:
            handle.write(data)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temp, path)
    finally:
        temp.unlink(missing_ok=True)


def store_recovery_key(app_dir: Path, key: bytes) -> Path:
    if len(key) != 32:
        raise ValueError("La llave de backup debe tener exactamente 32 bytes.")
    protected = dpapi.protect(key, description="Mia backup recovery key")
    key_path = app_dir / KEY_FILE_NAME
    _atomic_write_private(key_path, base64.b64encode(protected) + b"\n")
    return key_path


def load_or_create_recovery_key(app_dir: Path) -> bytes:
    key_path = app_dir / KEY_FILE_NAME
    if key_path.exists():
        try:
            protected = base64.b64decode(key_path.read_bytes().strip(), validate=True)
            key = dpapi.unprotect(protected)
        except Exception as exc:
            raise BackupError(
                "No pude abrir la llave local de los respaldos. Usa tu llave de recuperación."
            ) from exc
        if len(key) != 32:
            raise BackupError("La llave local de respaldos tiene un formato inválido.")
        return key

    key = os.urandom(32)
    app_dir.mkdir(parents=True, exist_ok=True)
    store_recovery_key(app_dir, key)
    return key


def load_recovery_key(app_dir: Path) -> bytes:
    """Carga una llave existente sin mutar estado si falta o está dañada."""
    key_path = app_dir / KEY_FILE_NAME
    if not key_path.is_file():
        raise BackupError(
            "No encuentro la llave local. Importa tu llave de recuperación antes de continuar."
        )
    try:
        protected = base64.b64decode(key_path.read_bytes().strip(), validate=True)
        key = dpapi.unprotect(protected)
    except Exception as exc:
        raise BackupError(
            "No pude abrir la llave local. Importa tu llave de recuperación."
        ) from exc
    if len(key) != 32:
        raise BackupError("La llave local de respaldos tiene un formato inválido.")
    return key


def export_recovery_key(app_dir: Path, destination: Path) -> Path:
    """Exporta la llave portable SIN asumir que el usuario la conservó."""
    key = load_or_create_recovery_key(app_dir)
    payload = (RECOVERY_PREFIX + base64.urlsafe_b64encode(key).decode("ascii") + "\n").encode()
    # El helper conserva cualquier destino anterior si la ACL del temporal
    # falla; no debe borrarse aquí una copia válida preexistente.
    _atomic_write_private(destination, payload)
    return destination


def import_recovery_key(app_dir: Path, recovery_text: str) -> Path:
    text = recovery_text.strip()
    if not text.startswith(RECOVERY_PREFIX):
        raise BackupError("La llave de recuperación no tiene el formato de Mia.")
    try:
        key = base64.urlsafe_b64decode(text[len(RECOVERY_PREFIX):].encode("ascii"))
    except Exception as exc:
        raise BackupError("La llave de recuperación está dañada.") from exc
    if len(key) != 32:
        raise BackupError("La llave de recuperación está incompleta.")
    key_path = store_recovery_key(app_dir, key)
    _write_recovery_marker(app_dir, key)
    return key_path


def _write_recovery_marker(app_dir: Path, key: bytes) -> Path:
    marker = app_dir / RECOVERY_MARKER_NAME
    digest = hashlib.sha256(key).hexdigest().encode("ascii") + b"\n"
    _atomic_write_private(marker, digest)
    return marker


def recovery_key_confirmed(app_dir: Path, key: bytes | None = None) -> bool:
    """La llave portable fue exportada/importada y corresponde a la llave activa."""
    try:
        # Consultar estado nunca crea una llave como efecto secundario.
        active = key or load_recovery_key(app_dir)
        expected = hashlib.sha256(active).hexdigest()
        return (app_dir / RECOVERY_MARKER_NAME).read_text(encoding="ascii").strip() == expected
    except Exception:
        return False


def recovery_key_text(app_dir: Path) -> str:
    """Texto portable para descargar; no confirma que el usuario lo guardó."""
    key = load_or_create_recovery_key(app_dir)
    return RECOVERY_PREFIX + base64.urlsafe_b64encode(key).decode("ascii") + "\n"


def confirm_recovery_key_saved(app_dir: Path) -> None:
    """Marca confirmada solo una llave local existente."""
    _write_recovery_marker(app_dir, load_recovery_key(app_dir))


def default_backup_dir() -> Path:
    documents = Path(os.environ.get("USERPROFILE") or Path.home()) / "Documents"
    return documents / "Mia Backups"


def _validated_pg_dump(pg_bin: Path) -> Path:
    """Acepta solo el bundle PostgreSQL de Mia y verifica su manifiesto instalado."""
    pg_bin = pg_bin.resolve()
    pg_dump = (pg_bin / "pg_dump.exe").resolve()
    required = ("pg_dump.exe", "pg_restore.exe", "pg_ctl.exe", "pg_isready.exe")
    if (
        not pg_bin.is_absolute()
        or not pg_bin.is_dir()
        or pg_dump.parent != pg_bin
        or any(not (pg_bin / name).is_file() for name in required)
    ):
        raise BackupError(f"La carpeta de PostgreSQL de Mia está incompleta: {pg_bin}")

    # En el bundle instalado no se confía en una ruta tomada del entorno o de
    # un JSON alterado: PostgreSQL debe ser exactamente el hermano que viajó
    # junto al ejecutable (`<instalación>/pgsql/bin`). Program Files protege
    # ese árbol con ACL de administrador.
    if getattr(sys, "frozen", False):
        expected_bin = (Path(sys.executable).resolve().parents[1] / "pgsql" / "bin").resolve()
        if pg_bin != expected_bin:
            raise BackupError("La herramienta de respaldo no pertenece a esta instalación de Mia.")

    manifest_path = pg_bin.parent / PG_MANIFEST_NAME
    require_manifest = bool(getattr(sys, "frozen", False)) or os.getenv(
        "MIA_REQUIRE_PG_MANIFEST", ""
    ).strip() == "1"
    if not manifest_path.is_file():
        if require_manifest:
            raise BackupError("No puedo comprobar la integridad de PostgreSQL de Mia.")
        return pg_dump
    try:
        # Windows PowerShell 5 puede escribir JSON UTF-8 con BOM.
        manifest = json.loads(manifest_path.read_text(encoding="utf-8-sig"))
        expected = manifest["sha256"]
        for name in required:
            digest = hashlib.sha256((pg_bin / name).read_bytes()).hexdigest()
            if digest.lower() != str(expected[name]).lower():
                raise BackupError(
                    f"La herramienta {name} no coincide con la instalación original de Mia."
                )
    except BackupError:
        raise
    except Exception as exc:
        raise BackupError("El manifiesto de PostgreSQL de Mia está dañado.") from exc
    return pg_dump


def _header_bytes(*, db: str, nonce: bytes) -> bytes:
    header = {
        "created_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "database": db,
        "encryption": "AES-256-GCM",
        "nonce": base64.b64encode(nonce).decode("ascii"),
        "payload": "pg_dump-custom",
        "version": 1,
    }
    encoded = json.dumps(header, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return MAGIC + struct.pack(">I", len(encoded)) + encoded


def create_database_backup(
    *,
    pg_bin: Path,
    app_dir: Path,
    host: str,
    port: int,
    db: str,
    password: str,
    destination_dir: Path | None = None,
    inactivity_timeout_seconds: float = 300.0,
    require_recovery_confirmation: bool = True,
) -> Path:
    """Crea un dump custom cifrado y atómico; devuelve el archivo final."""
    pg_dump = _validated_pg_dump(pg_bin)
    key = load_or_create_recovery_key(app_dir)
    if require_recovery_confirmation and not recovery_key_confirmed(app_dir, key):
        raise BackupError(
            "Antes del primer respaldo, guarda la llave de recuperación en un lugar seguro."
        )
    nonce = os.urandom(12)
    header = _header_bytes(db=db, nonce=nonce)
    encryptor = Cipher(algorithms.AES(key), modes.GCM(nonce)).encryptor()
    encryptor.authenticate_additional_data(header)

    folder = destination_dir or default_backup_dir()
    folder.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    unique = uuid.uuid4().hex[:12]
    final_path = folder / f"mia-{stamp}-{unique}{BACKUP_SUFFIX}"
    partial = final_path.with_name(final_path.name + ".partial")
    error_log = folder / f".{final_path.name}.pgdump-error"

    child_env = {
        "PATH": os.environ.get("PATH", ""),
        "PGPASSWORD": password,
        "SYSTEMROOT": os.environ.get("SYSTEMROOT", ""),
    }
    command = [
        str(pg_dump), "--format=custom", "--no-owner", "--no-acl",
        "--host", host, "--port", str(port), "--username", "postgres", db,
    ]
    process: subprocess.Popen[bytes] | None = None
    plaintext_size = 0
    last_progress = time.monotonic()
    watchdog_stop = threading.Event()

    def _watchdog() -> None:
        while not watchdog_stop.wait(1.0):
            if process is not None and time.monotonic() - last_progress > inactivity_timeout_seconds:
                process.kill()
                return

    watchdog = threading.Thread(target=_watchdog, name="mia-backup-watchdog", daemon=True)
    try:
        with open(error_log, "wb") as errors, open(partial, "wb") as output:
            output.write(header)
            process = subprocess.Popen(
                command,
                stdout=subprocess.PIPE,
                stderr=errors,
                stdin=subprocess.DEVNULL,
                env=child_env,
                shell=False,
            )
            watchdog.start()
            assert process.stdout is not None
            while True:
                # read1 devuelve lo que ya está disponible sin esperar a llenar
                # 1 MiB; el watchdog mide actividad real y no mata un dump lento
                # que siga produciendo bloques pequeños.
                chunk = process.stdout.read1(_CHUNK_SIZE)
                if not chunk:
                    break
                last_progress = time.monotonic()
                plaintext_size += len(chunk)
                output.write(encryptor.update(chunk))
            code = process.wait()
            if code != 0:
                detail = error_log.read_text(encoding="utf-8", errors="replace")[-1200:]
                _save_failure_log(app_dir, detail)
                if time.monotonic() - last_progress > inactivity_timeout_seconds:
                    raise BackupError("El respaldo se detuvo sin responder y fue cancelado.")
                raise BackupError(f"PostgreSQL no pudo crear el respaldo. {detail}".strip())
            if plaintext_size == 0:
                raise BackupError("PostgreSQL produjo un respaldo vacío.")
            output.write(encryptor.finalize())
            output.write(encryptor.tag)
            output.flush()
            os.fsync(output.fileno())
        os.replace(partial, final_path)
        return final_path
    except Exception:
        if process is not None and process.poll() is None:
            process.kill()
            process.wait()
        partial.unlink(missing_ok=True)
        raise
    finally:
        watchdog_stop.set()
        if watchdog.is_alive():
            watchdog.join(timeout=2)
        error_log.unlink(missing_ok=True)


def verify_database_backup(*, backup_path: Path, app_dir: Path, pg_bin: Path) -> dict:
    """Autentica el cifrado y exige que pg_restore reconozca el archivo."""
    pg_restore = _validated_pg_dump(pg_bin).with_name("pg_restore.exe")
    with decrypted_backup_temp(backup_path, app_dir) as (dump_path, header):
        result = subprocess.run(
            [str(pg_restore), "--list", str(dump_path)],
            capture_output=True,
            text=True,
            stdin=subprocess.DEVNULL,
            shell=False,
            timeout=300,
        )
        if result.returncode != 0:
            raise BackupError("PostgreSQL no reconoce el contenido del respaldo.")
    return header


def create_verified_database_backup(**kwargs) -> Path:
    """Crea y verifica; si la verificación falla no publica una copia inútil."""
    path = create_database_backup(**kwargs)
    try:
        verify_database_backup(
            backup_path=path,
            app_dir=Path(kwargs["app_dir"]),
            pg_bin=Path(kwargs["pg_bin"]),
        )
    except Exception:
        path.unlink(missing_ok=True)
        raise
    return path


def _save_failure_log(app_dir: Path, detail: str) -> None:
    """Conserva solo el último diagnóstico técnico, nunca el dump parcial."""
    log_path = app_dir / "logs" / "backup-last-error.log"
    _atomic_write(log_path, (detail.strip() + "\n").encode("utf-8", errors="replace"))
    _restrict_windows_file(log_path)


def _read_header(source: BinaryIO) -> tuple[dict, bytes]:
    magic = source.read(len(MAGIC))
    if magic != MAGIC:
        raise BackupError("El archivo no es un respaldo de Mia compatible.")
    raw_length = source.read(4)
    if len(raw_length) != 4:
        raise BackupError("El encabezado del respaldo está incompleto.")
    length = struct.unpack(">I", raw_length)[0]
    if length <= 0 or length > 64 * 1024:
        raise BackupError("El encabezado del respaldo tiene un tamaño inválido.")
    encoded = source.read(length)
    if len(encoded) != length:
        raise BackupError("El encabezado del respaldo está truncado.")
    try:
        header = json.loads(encoded)
        nonce = base64.b64decode(header["nonce"], validate=True)
    except Exception as exc:
        raise BackupError("El encabezado del respaldo está dañado.") from exc
    if len(nonce) != 12:
        raise BackupError("El respaldo usa un nonce inválido.")
    return header, magic + raw_length + encoded


def _decrypt_backup_to_file(backup_path: Path, app_dir: Path, destination: Path) -> dict:
    """Descifra y autentica un backup a un dump temporal para verificación/restore."""
    key = load_recovery_key(app_dir)
    total = backup_path.stat().st_size
    if total < len(MAGIC) + 4 + 16:
        raise BackupError("El respaldo está vacío o truncado.")
    temp = destination.with_name(destination.name + ".partial")
    try:
        with open(backup_path, "rb") as source:
            header, aad = _read_header(source)
            ciphertext_start = source.tell()
            ciphertext_length = total - ciphertext_start - 16
            if ciphertext_length <= 0:
                raise BackupError("El respaldo no contiene datos.")
            source.seek(total - 16)
            tag = source.read(16)
            source.seek(ciphertext_start)
            nonce = base64.b64decode(header["nonce"])
            decryptor = Cipher(algorithms.AES(key), modes.GCM(nonce, tag)).decryptor()
            decryptor.authenticate_additional_data(aad)
            remaining = ciphertext_length
            with open(temp, "wb") as output:
                while remaining:
                    chunk = source.read(min(_CHUNK_SIZE, remaining))
                    if not chunk:
                        raise BackupError("El respaldo está truncado.")
                    remaining -= len(chunk)
                    output.write(decryptor.update(chunk))
                output.write(decryptor.finalize())
                output.flush()
                os.fsync(output.fileno())
        os.replace(temp, destination)
        _restrict_or_remove(destination)
        return header
    except Exception as exc:
        temp.unlink(missing_ok=True)
        if isinstance(exc, BackupError):
            raise
        raise BackupError("El respaldo está dañado o la llave no corresponde.") from exc


@contextmanager
def decrypted_backup_temp(backup_path: Path, app_dir: Path):
    """Entrega un dump privado solo durante el bloque y siempre lo elimina.

    Esta es la única superficie pública para materializar el dump. La futura
    restauración usa este contexto, ejecuta ``pg_restore`` dentro del bloque y
    no puede olvidar el expediente descifrado en disco.
    """
    with _RESTORE_LOCK, _restore_process_lock(app_dir):
        _cleanup_decrypted_temps_unlocked(app_dir)
        private_dir = app_dir / ".maintenance"
        private_dir.mkdir(parents=True, exist_ok=True)
        _restrict_windows_file(private_dir)
        destination = private_dir / f"restore-{uuid.uuid4().hex}.dump"
        header = _decrypt_backup_to_file(backup_path, app_dir, destination)
        try:
            yield destination, header
        finally:
            destination.unlink(missing_ok=True)
            destination.with_name(destination.name + ".partial").unlink(missing_ok=True)


@contextmanager
def _restore_process_lock(app_dir: Path, timeout_seconds: float = 60.0):
    """Candado interproceso para que dos mantenimientos no borren sus dumps."""
    private_dir = app_dir / ".maintenance"
    private_dir.mkdir(parents=True, exist_ok=True)
    _restrict_windows_file(private_dir)
    lock_path = private_dir / "restore.lock"
    handle = open(lock_path, "a+b")
    if handle.tell() == 0:
        handle.write(b"\0")
        handle.flush()
    deadline = time.monotonic() + timeout_seconds
    locked = False
    try:
        if os.name == "nt":
            import msvcrt

            while not locked:
                try:
                    handle.seek(0)
                    msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
                    locked = True
                except OSError:
                    if time.monotonic() >= deadline:
                        raise BackupError("Otra recuperación de Mia sigue en curso.")
                    time.sleep(0.1)
        else:
            import fcntl

            fcntl.flock(handle.fileno(), fcntl.LOCK_EX)
            locked = True
        yield
    finally:
        if locked:
            if os.name == "nt":
                import msvcrt

                handle.seek(0)
                msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                import fcntl

                fcntl.flock(handle.fileno(), fcntl.LOCK_UN)
        handle.close()


def _cleanup_decrypted_temps_unlocked(app_dir: Path) -> int:
    """Borra restos descifrados de una terminación forzada anterior.

    Debe llamarse al inicio del mantenimiento en cada apertura. También se
    ejecuta antes de cada verificación/restauración, de modo que un corte de
    energía no deja el dump más allá del siguiente arranque.
    """
    private_dir = app_dir / ".maintenance"
    if not private_dir.exists():
        return 0
    removed = 0
    for pattern in ("restore-*.dump", "restore-*.dump.partial"):
        for path in private_dir.glob(pattern):
            if path.is_file():
                path.unlink(missing_ok=True)
                removed += 1
    return removed


def cleanup_decrypted_temps(app_dir: Path) -> int:
    """Limpieza pública serializada entre hilos y procesos de Mia."""
    with _RESTORE_LOCK, _restore_process_lock(app_dir):
        return _cleanup_decrypted_temps_unlocked(app_dir)


def rotate_backups(directory: Path, keep: int = 3) -> list[Path]:
    """Conserva solo los `keep` respaldos más recientes; borra el resto.

    Sin esto, "Mia Backups" crece sin límite en el disco del abogado con un
    respaldo nuevo por cada arranque/migración. Ordena por mtime descendente
    (el mismo criterio que ya usa maintenance.protection_status para "el último
    respaldo") y devuelve las rutas borradas para que el llamador las reporte
    si quiere. Llamar SOLO después de un backup ya verificado — nunca antes,
    para no quedarse sin copias si el nuevo respaldo resulta inválido.
    """
    if keep < 0:
        raise ValueError("keep no puede ser negativo.")
    try:
        files = sorted(
            directory.glob(f"*{BACKUP_SUFFIX}"),
            key=lambda path: path.stat().st_mtime,
            reverse=True,
        )
    except OSError:
        return []
    removed: list[Path] = []
    for path in files[keep:]:
        try:
            path.unlink()
            removed.append(path)
        except OSError:
            continue
    return removed
