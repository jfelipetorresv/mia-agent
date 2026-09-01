"""Gate F1: la protección es simple y solo invoca comandos locales Tauri."""
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
component = (ROOT / "frontend/app/_components/ProteccionDatosSection.tsx").read_text(encoding="utf-8")
page = (ROOT / "frontend/app/configurar/page.tsx").read_text(encoding="utf-8")
shell = (ROOT / "desktop/src-tauri/src/lib.rs").read_text(encoding="utf-8")
api_main = (ROOT / "backend/mia/api/main.py").read_text(encoding="utf-8")

checks = {
    # Los tres checks de abajo llevaban en rojo desde el arreglo del puente (sesión 46) sin
    # causa escrita: estaban clavados al MECANISMO retirado —la IPC directa de la cáscara y
    # los nombres de sus comandos— y a una pestaña propia que el rediseño fusionó dentro de
    # «sistema», con el ancla `#proteccion` intacta. Ninguna de las tres funciones cambió.
    # Re-anclados al CONCEPTO (regla sellada 2026-07-29: los gates verifican el concepto,
    # nunca la implementación concreta ni la redacción).
    "Protección alcanzable desde Configuración": (
        "ProteccionDatosSection" in page and '"#proteccion"' in page
        and 'id="proteccion"' in page),
    "lenguaje llano": all(text in component for text in [
        "Protección de tus datos", "Guardar llave", "Ya la guardé", "Crear copia ahora"
    ]),
    # Sacar la llave y CONFIRMAR que se guardó son dos actos distintos: si fueran uno, el
    # abogado podría creer que tiene copia de su llave sin tenerla.
    "confirmación separada": ("maintenance/export-key" in component
                              and "maintenance/confirm-key" in component),
    # Las operaciones de mantenimiento NO viajan por HTTP: van por el puente en proceso, que
    # no abre puerto y es inalcanzable desde otro programa o desde la red.
    "operaciones solo por el puente de la cáscara, nunca por HTTP": (
        "maintenance/backup" in component
        and "shellInvoke" in component
        and "/api/maintenance" not in component
        and "fetch(" not in component),
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
