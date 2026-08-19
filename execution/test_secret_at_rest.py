"""Gate F1: secretos cifrados por tenant/campo con recuperación portable."""
from __future__ import annotations

import tempfile
from pathlib import Path

from mia.security.at_rest import (
    PREFIX,
    SecretDecryptionError,
    decrypt_secret,
    encrypt_secret,
    is_encrypted,
)
from mia.setup import backup
from mia.security.redact import redact_text


failures: list[str] = []


def check(label: str, condition: bool) -> None:
    print(f"  [{'OK' if condition else 'FAIL'}] {label}")
    if not condition:
        failures.append(label)


print("\n=== F1 · secretos cifrados en reposo ===")
with tempfile.TemporaryDirectory(prefix="mia-secret-at-rest-") as td:
    root = Path(td)
    app_a = root / "app-a"
    secret = "token-ultraconfidencial-91"
    encrypted = encrypt_secret(
        secret, tenant_id="tenant-a", purpose="oauth:google:access", app_dir=app_a
    )
    check("la base recibe un sobre versionado", encrypted.startswith(PREFIX))
    check("el secreto no queda legible", secret not in encrypted and is_encrypted(encrypted))
    check("el tenant y campo correctos lo abren", decrypt_secret(
        encrypted, tenant_id="tenant-a", purpose="oauth:google:access", app_dir=app_a
    ) == secret)

    try:
        decrypt_secret(
            encrypted, tenant_id="tenant-b", purpose="oauth:google:access", app_dir=app_a
        )
        tenant_blocked = False
    except SecretDecryptionError:
        tenant_blocked = True
    check("otro tenant no puede reutilizar el token", tenant_blocked)

    try:
        decrypt_secret(
            encrypted, tenant_id="tenant-a", purpose="oauth:google:refresh", app_dir=app_a
        )
        purpose_blocked = False
    except SecretDecryptionError:
        purpose_blocked = True
    check("otro campo no puede reutilizar el token", purpose_blocked)
    check("un valor legacy sigue legible durante la transición", decrypt_secret(
        "legacy", tenant_id="tenant-a", purpose="oauth:google:access", app_dir=app_a
    ) == "legacy")

    recovery_file = root / "recovery.txt"
    backup.export_recovery_key(app_a, recovery_file)
    recovery_text = recovery_file.read_text(encoding="utf-8")
    check("los logs redactan una llave de recuperación",
          recovery_text.strip() not in redact_text(f"error: {recovery_text.strip()}"))
    app_b = root / "app-b"
    backup.import_recovery_key(app_b, recovery_text)
    check("la llave portable recupera secretos en otro equipo", decrypt_secret(
        encrypted, tenant_id="tenant-a", purpose="oauth:google:access", app_dir=app_b
    ) == secret)

if failures:
    raise SystemExit(1)
print("\nPASS: secretos ilegibles en DB y recuperables con la llave de Mia")
