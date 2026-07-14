"""
Mia · test_config_tabs.py — gate del checkpoint C3: Configuración en subtabs shadcn
con deep-links por hash.

No toca la DB ni el API: es un gate por string-literal sobre el código fuente del
frontend (mismo patrón de run_frontend_checks() en execution/test_second_brain_ui.py),
porque lo que hay que garantizar es texto/estructura presente en el archivo, no
comportamiento en runtime (eso lo cubre Playwright/QA manual).

Cubre:
  1. configurar/page.tsx importa Tabs/TabsList/TabsTrigger/TabsContent de shadcn.
  2. Los 6 subtabs (incluida protección de datos)
     y el mapa hash→tab con los 4 anclas históricos.
  3. Sincronía con hash viva: 'hashchange' + 'replaceState'.
  4. 'La salud de Mia' se conserva; 'Primeros pasos' presente; contador en el trigger.
  5. Compatibilidad externa intacta: setup.py, dashboard/page.tsx, FuentesPanel.tsx y
     OneDriveFolderPicker.tsx siguen apuntando a los anclas /configurar#... de siempre.
  6. La nav de chips vieja (SECCIONES_NAV / <a href="#...">) desapareció.

Salida: exit 0 = PASS · exit 1 = FAIL.
    .venv\\Scripts\\python.exe execution\\test_config_tabs.py
"""
from __future__ import annotations

import sys
from pathlib import Path

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

ROOT = Path(__file__).resolve().parents[1]

_results: list[tuple[str, bool]] = []


def check(name: str, ok: bool) -> None:
    _results.append((name, bool(ok)))
    print(("  [OK]   " if ok else "  [FAIL] ") + name)


def main() -> int:
    print("== Configuración: subtabs shadcn + deep-links por hash (CP-C3) ==")

    configurar = (ROOT / "frontend" / "app" / "configurar" / "page.tsx").read_text(encoding="utf-8")

    # 1. Import de shadcn Tabs
    check(
        "importa Tabs/TabsList/TabsTrigger/TabsContent de @/components/ui/tabs",
        "TabsList" in configurar
        and "TabsTrigger" in configurar
        and "TabsContent" in configurar
        and '@/components/ui/tabs"' in configurar,
    )

    # 2. Los 6 ids de tab + mapa hash→tab con los anclas históricos
    check(
        "los 6 subtabs están presentes (value=)",
        all(
            f'value="{tid}"' in configurar
            for tid in ["primeros-pasos", "conexiones", "carpetas", "automatizaciones", "valor", "proteccion"]
        ),
    )
    check(
        "el mapa hash→tab conserva los anclas históricos",
        all(h in configurar for h in ["#conexiones", "#carpetas", "#automatizaciones", "#valor", "#proteccion"]),
    )

    # 3. Deep-link vivo (sincronía con hash, no solo al montar)
    check("escucha 'hashchange'", "hashchange" in configurar)
    check("usa 'replaceState' al cambiar de tab", "replaceState" in configurar)

    # 4. Literales de producto conservados + contador en el trigger
    check("'La salud de Mia' se conserva", "La salud de Mia" in configurar)
    check("'Primeros pasos' presente", "Primeros pasos" in configurar)
    check(
        "el trigger de Primeros pasos muestra el contador (s.completados/s.total)",
        "s.completados" in configurar and "s.total" in configurar,
    )

    # 5. Compatibilidad externa: nadie que enlace a /configurar#... quedó roto
    setup_py = (ROOT / "backend" / "mia" / "api" / "routes" / "setup.py").read_text(encoding="utf-8")
    dashboard = (ROOT / "frontend" / "app" / "dashboard" / "page.tsx").read_text(encoding="utf-8")
    fuentes = (ROOT / "frontend" / "app" / "_components" / "FuentesPanel.tsx").read_text(encoding="utf-8")
    onedrive = (ROOT / "frontend" / "app" / "_components" / "OneDriveFolderPicker.tsx").read_text(encoding="utf-8")

    check("setup.py sigue enlazando a /configurar#conexiones", "/configurar#conexiones" in setup_py)
    check("setup.py sigue enlazando a /configurar#carpetas", "/configurar#carpetas" in setup_py)
    check("dashboard/page.tsx sigue enlazando a /configurar#valor", "/configurar#valor" in dashboard)
    check("FuentesPanel.tsx sigue enlazando a /configurar#conexiones", "/configurar#conexiones" in fuentes)
    check("OneDriveFolderPicker.tsx sigue enlazando a /configurar#conexiones", "/configurar#conexiones" in onedrive)

    # 6. La nav de chips vieja desapareció (los triggers la reemplazan)
    check(
        "SECCIONES_NAV / <a href=\"#...\"> viejos ya no están",
        "SECCIONES_NAV" not in configurar and '<a href="#' not in configurar,
    )

    passed = sum(1 for _, ok in _results if ok)
    total = len(_results)
    print(f"\nRESULT: {passed}/{total} checks PASS")
    if passed == total:
        print("Config tabs OK.")
        return 0
    print("Config tabs FAIL.")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
