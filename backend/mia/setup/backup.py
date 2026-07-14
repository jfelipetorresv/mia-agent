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
from datetime import datetime, timezone
from pathlib import Path
from typing import BinaryIO

from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes

from ..security import dpapi

MAGIC = b"MIA-BACKUP-V1\n"
KEY_FILE_NAME = ".mia-backup-key.dpapi"
RECOVERY_MARKER_NAME = ".mia-backup-recovery-confirmed"
RECOVERY_PREFIX = "MIA-RECOVERY-V1:"
_CHUNK_SIZE = 1024 * 1024


class BackupError(RuntimeError):
    pass


def _atomic_write(path: Path, data: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_name(path.name + ".tmp")
    with open(temp, "wb") as handle:
        handle.write(data)
        handle.flush()
        os.fsync(handle.fileno())
    os.replace(temp, path)


def _restrict_windows_file(path: Path) -> None:
    if os.name != "nt":
        return
    user = os.environ.get("USERNAME", "").strip()
    if not user:
        raise BackupError("Windows no informó el usuario actual para proteger la llave.")
    domain = os.environ.get("USERDOMAIN", "").strip()
    principal = f"{domain}\\{user}" if domain else user
    result = subprocess.run(
        ["icacls", str(path), "/inheritance:r", "/grant:r", f"{principal}:F"],
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        raise BackupError("Windows no pudo restringir el archivo de recuperación.")


def store_recovery_key(app_dir: Path, key: bytes) -> Path:
    if len(key) != 32:
        raise ValueError("La llave de backup debe tener exactamente 32 bytes.")
    protected = dpapi.protect(key, description="Mia backup recovery key")
    key_path = app_dir / KEY_FILE_NAME
    _atomic_write(key_path, base64.b64encode(protected) + b"\n")
    _restrict_windows_file(key_path)
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


def export_recovery_key(app_dir: Path, destination: Path) -> Path:
    """Exporta la llave portable. El llamador debe pedir confirmación visible."""
    key = load_or_create_recovery_key(app_dir)
    payload = (RECOVERY_PREFIX + base64.urlsafe_b64encode(key).decode("ascii") + "\n").encode()
    _atomic_write(destination, payload)
    _restrict_windows_file(destination)
    _write_recovery_marker(app_dir, key)
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
    _atomic_write(marker, digest)
    _restrict_windows_file(marker)
    return marker


def recovery_key_confirmed(app_dir: Path, key: bytes | None = None) -> bool:
    """La llave portable fue exportada/importada y corresponde a la llave activa."""
    try:
        active = key or load_or_create_recovery_key(app_dir)
        expected = hashlib.sha256(active).hexdigest()
        return (app_dir / RECOVERY_MARKER_NAME).read_text(encoding="ascii").strip() == expected
    except Exception:
        return False


def default_backup_dir() -> Path:
    documents = Path(os.environ.get("USERPROFILE") or Path.home()) / "Documents"
    return documents / "Mia Backups"


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
    pg_dump: Path,
    app_dir: Path,
    host: str,
    port: int,
    db: str,
    password: str,
    destination_dir: Path | None = None,
) -> Path:
    """Crea un dump custom cifrado y atómico; devuelve el archivo final."""
    pg_dump = pg_dump.resolve()
    if not pg_dump.is_absolute() or pg_dump.name.lower() != "pg_dump.exe" or not pg_dump.is_file():
        raise BackupError(f"No encuentro la herramienta de respaldo: {pg_dump}")
    key = load_or_create_recovery_key(app_dir)
    if not recovery_key_confirmed(app_dir, key):
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
    final_path = folder / f"mia-{stamp}.mia-backup"
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
            assert process.stdout is not None
            while True:
                chunk = process.stdout.read(_CHUNK_SIZE)
                if not chunk:
                    break
                plaintext_size += len(chunk)
                output.write(encryptor.update(chunk))
            code = process.wait()
            if code != 0:
                detail = error_log.read_text(encoding="utf-8", errors="replace")[-1200:]
                _save_failure_log(app_dir, detail)
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
        error_log.unlink(missing_ok=True)


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


def decrypt_backup_to_file(backup_path: Path, app_dir: Path, destination: Path) -> dict:
    """Descifra y autentica un backup a un dump temporal para verificación/restore."""
    key = load_or_create_recovery_key(app_dir)
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
        return header
    except Exception as exc:
        temp.unlink(missing_ok=True)
        if isinstance(exc, BackupError):
            raise
        raise BackupError("El respaldo está dañado o la llave no corresponde.") from exc
