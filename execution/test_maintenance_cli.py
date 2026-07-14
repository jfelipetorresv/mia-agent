"""Gate F1: frontera CLI de mantenimiento, sin secretos en argumentos/salida."""
from __future__ import annotations

import contextlib
import io
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from mia.setup import maintenance  # noqa: E402


failures: list[str] = []


def check(label: str, condition: bool) -> None:
    print(f"  [{'OK' if condition else 'FAIL'}] {label}")
    if not condition:
        failures.append(label)


print("\n=== F1 · CLI de mantenimiento ===")
with tempfile.TemporaryDirectory(prefix="mia-maint-cli-") as td:
    app_dir = Path(td) / "app"
    app_dir.mkdir()
    pg_bin = Path(td) / "pgsql" / "bin"
    source = Path(td) / "recovery.txt"
    source.write_text("MIA-RECOVERY-V1:prueba", encoding="utf-8")

    calls: list[tuple] = []
    original_startup = maintenance.startup
    original_settings = maintenance._settings
    original_verified = maintenance._verified_backup
    original_verify = maintenance.backup.verify_database_backup
    original_export = maintenance.backup.export_recovery_key
    original_confirm = maintenance.backup.confirm_recovery_key_saved
    original_import = maintenance.backup.import_recovery_key
    try:
        maintenance.startup = lambda a, p, port=None: calls.append(("startup", a, p, port)) or ["031.sql"]
        maintenance._settings = lambda a, port=None: {
            "host": "127.0.0.1", "port": 55432, "db": "mia", "password": "SECRETO-NO-SALIR"
        }
        maintenance._verified_backup = lambda a, p, s: calls.append(("backup", a, p)) or Path("ok")
        maintenance.backup.verify_database_backup = lambda **kw: calls.append(("verify", kw["backup_path"])) or {}
        maintenance.backup.export_recovery_key = lambda a, d: calls.append(("export", d)) or d
        maintenance.backup.confirm_recovery_key_saved = lambda a: calls.append(("confirm", a))
        maintenance.backup.import_recovery_key = lambda a, text: calls.append(("import", text)) or a

        output = io.StringIO()
        error = io.StringIO()
        with contextlib.redirect_stdout(output), contextlib.redirect_stderr(error):
            rc_start = maintenance.main([
                "startup", "--pg-bin", str(pg_bin), "--pg-port", "55555",
                "--app-dir", str(app_dir),
            ])
            rc_backup = maintenance.main([
                "backup", "--pg-bin", str(pg_bin), "--app-dir", str(app_dir),
            ])
            rc_verify = maintenance.main([
                "verify", "--pg-bin", str(pg_bin), "--app-dir", str(app_dir),
                "--source", str(source),
            ])
            rc_export = maintenance.main([
                "export-key", "--pg-bin", str(pg_bin), "--app-dir", str(app_dir),
                "--destination", str(Path(td) / "export.txt"),
            ])
            rc_confirm = maintenance.main([
                "confirm-key", "--pg-bin", str(pg_bin), "--app-dir", str(app_dir),
            ])
            rc_import = maintenance.main([
                "import-key", "--pg-bin", str(pg_bin), "--app-dir", str(app_dir),
                "--source", str(source),
            ])

        combined = output.getvalue() + error.getvalue()
        check("los seis comandos terminan correctamente",
              [rc_start, rc_backup, rc_verify, rc_export, rc_confirm, rc_import]
              == [0, 0, 0, 0, 0, 0])
        check("startup conserva app-dir, pg-bin y puerto", calls[0] == (
            "startup", app_dir.resolve(), pg_bin, 55555
        ))
        check("backup, verify, export e import llegan a la operación correcta",
              [c[0] for c in calls] == ["startup", "backup", "verify", "export", "confirm", "import"])
        check("ninguna contraseña viaja por argumentos o salida",
              "SECRETO-NO-SALIR" not in combined and
              all("password" not in arg.lower() for arg in sys.argv))
        check("los mensajes finales son breves y en lenguaje llano",
              combined.count("MIA-MAINTENANCE:") == 6 and "Traceback" not in combined)
    finally:
        maintenance.startup = original_startup
        maintenance._settings = original_settings
        maintenance._verified_backup = original_verified
        maintenance.backup.verify_database_backup = original_verify
        maintenance.backup.export_recovery_key = original_export
        maintenance.backup.confirm_recovery_key_saved = original_confirm
        maintenance.backup.import_recovery_key = original_import

if failures:
    print(f"\nFAIL: {len(failures)} comprobaciones")
    raise SystemExit(1)
print("\nPASS: CLI de mantenimiento segura y sin secretos")
