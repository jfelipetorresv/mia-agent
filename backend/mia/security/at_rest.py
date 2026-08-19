"""Cifrado de secretos de tenant almacenados en PostgreSQL/JSONB.

Usa una subllave derivada de la llave de recuperación de Mia. Cada valor queda
atado criptográficamente al tenant y a su propósito, de modo que copiar un token
a otra fila/campo no permite abrirlo allí. Los valores legacy sin prefijo se
leen durante la transición; toda escritura nueva queda cifrada.
"""
from __future__ import annotations

import base64
import os
from pathlib import Path

from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.kdf.hkdf import HKDF

PREFIX = "MIA-ENC-V1:"
_INFO = b"Mia.tenant-secrets.v1"


class SecretDecryptionError(RuntimeError):
    pass


def _app_dir(value: Path | None = None) -> Path:
    if value is not None:
        return Path(value)
    raw = os.getenv("MIA_APP_DIR", "").strip()
    if raw:
        return Path(raw).resolve()
    from .. import config

    return config.PROJECT_ROOT


def _key(app_dir: Path, *, create: bool) -> bytes:
    # Import diferido: evita ciclos (setup.backup importa security.dpapi).
    from ..setup import backup

    root = (
        backup.load_or_create_recovery_key(app_dir)
        if create
        else backup.load_recovery_key(app_dir)
    )
    return HKDF(algorithm=hashes.SHA256(), length=32, salt=None, info=_INFO).derive(root)


def _aad(tenant_id: str, purpose: str) -> bytes:
    tenant = str(tenant_id).strip()
    field = str(purpose).strip()
    if not tenant or not field:
        raise ValueError("tenant_id y purpose son obligatorios para cifrar secretos.")
    return f"{tenant}\0{field}".encode("utf-8")


def is_encrypted(value: str | None) -> bool:
    return bool(value and str(value).startswith(PREFIX))


def encrypt_secret(
    value: str | None,
    *,
    tenant_id: str,
    purpose: str,
    app_dir: Path | None = None,
) -> str:
    text = str(value or "")
    if not text or is_encrypted(text):
        return text
    nonce = os.urandom(12)
    ciphertext = AESGCM(_key(_app_dir(app_dir), create=True)).encrypt(
        nonce, text.encode("utf-8"), _aad(tenant_id, purpose)
    )
    return PREFIX + base64.urlsafe_b64encode(nonce + ciphertext).decode("ascii")


def decrypt_secret(
    value: str | None,
    *,
    tenant_id: str,
    purpose: str,
    app_dir: Path | None = None,
) -> str:
    text = str(value or "")
    if not text or not is_encrypted(text):
        return text  # compatibilidad temporal con datos existentes
    try:
        payload = base64.urlsafe_b64decode(text[len(PREFIX):].encode("ascii"))
        if len(payload) < 12 + 16:
            raise ValueError("payload corto")
        nonce, ciphertext = payload[:12], payload[12:]
        plaintext = AESGCM(_key(_app_dir(app_dir), create=False)).decrypt(
            nonce, ciphertext, _aad(tenant_id, purpose)
        )
        return plaintext.decode("utf-8")
    except Exception as exc:
        raise SecretDecryptionError(
            "No pude abrir una credencial guardada. Usa la llave de recuperación de Mia."
        ) from exc
