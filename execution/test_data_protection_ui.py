"""Gate F1: la protección es simple y solo invoca comandos locales Tauri."""
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
component = (ROOT / "frontend/app/_components/ProteccionDatosSection.tsx").read_text(encoding="utf-8")
page = (ROOT / "frontend/app/configurar/page.tsx").read_text(encoding="utf-8")
shell = (ROOT / "desktop/src-tauri/src/lib.rs").read_text(encoding="utf-8")
api_main = (ROOT / "backend/mia/api/main.py").read_text(encoding="utf-8")

checks = {
    "tab Protección visible": 'value="proteccion"' in page and "ProteccionDatosSection" in page,
    "lenguaje llano": all(text in component for text in [
        "Protección de tus datos", "Guardar llave", "Ya la guardé", "Crear copia ahora"
    ]),
    "confirmación separada": "maintenance_export_key" in component and "maintenance_confirm_key" in component,
    "operaciones solo Tauri": "maintenance_create_backup" in component and "/api/maintenance" not in component,
    "llave no expuesta por HTTP": "maintenance.router" not in api_main,
    "comandos registrados en la cáscara": all(name in shell for name in [
        "maintenance_status", "maintenance_export_key", "maintenance_confirm_key", "maintenance_create_backup"
    ]),
    "backup bloqueado hasta confirmar": "!status?.recovery_key_saved" in component,
}

print("\n=== F1 · Protección de datos en Configuración ===")
failed = []
for label, ok in checks.items():
    print(f"  [{'OK' if ok else 'FAIL'}] {label}")
    if not ok:
        failed.append(label)
if failed:
    raise SystemExit(1)
print("\nPASS: controles simples, locales y con confirmación humana")
