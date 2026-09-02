"""Gate F1: mantenimiento automático en la ventana segura del arranque."""
from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
rust = (ROOT / "desktop/src-tauri/src/lib.rs").read_text(encoding="utf-8")
dev = json.loads((ROOT / "desktop/orchestration.json").read_text(encoding="utf-8"))
installer = json.loads(
    (ROOT / "packaging/orchestration.installer.json").read_text(encoding="utf-8")
)
layout = (ROOT / "frontend/app/layout.tsx").read_text(encoding="utf-8")
reminder = (ROOT / "frontend/app/_components/ProtectionReminder.tsx").read_text(encoding="utf-8")
protection = (ROOT / "frontend/app/_components/ProteccionDatosSection.tsx").read_text(encoding="utf-8")

db_ready = rust.index("// --- a1) Protección y actualizaciones locales")
maintenance = rust.index('run_maintenance_action(app.clone(), "startup"')
models = rust.index("// --- a2) Motor de modelos", maintenance)

assert db_ready < maintenance < models
assert 'emit(&app, "maintenance"' in rust
assert dev["maintenance"]["cmd"] and installer["maintenance"]["cmd"]
assert "<ProtectionReminder />" in layout
assert 'shellInvoke<ProtectionStatus>("maintenance/status")' in reminder
assert "/configurar#proteccion" in reminder
assert "dismiss" not in reminder.lower()
assert 'pathname.startsWith("/login")' in reminder
assert 'window.addEventListener("mia:recovery-key-confirmed"' in reminder
assert 'window.dispatchEvent(new Event("mia:recovery-key-confirmed"))' in protection
assert ".catch((err) =>" in reminder
assert "setNeedsKey(!(err instanceof Error" in reminder
assert "err.message === DESKTOP_ONLY_MESSAGE" in reminder

print("PASS: Mia protege y actualiza después de la DB y antes de sus servicios")
print("PASS: el aviso de guardar la llave persiste hasta la confirmación")
