"""
Mia · test_onboarding_horizontal.py — gate de onboarding horizontal + pulido visual.
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

_results: list[tuple[str, bool]] = []


def check(name: str, ok: bool) -> None:
    _results.append((name, bool(ok)))
    print(("  [OK]   " if ok else "  [FAIL] ") + name)


def main() -> int:
    print("== Onboarding horizontal ==")
    onboarding = (ROOT / "frontend" / "app" / "onboarding" / "page.tsx").read_text(encoding="utf-8")
    sidebar = (ROOT / "frontend" / "app" / "_components" / "Sidebar.tsx").read_text(encoding="utf-8")
    workspace = (ROOT / "frontend" / "app" / "asuntos" / "[id]" / "page.tsx").read_text(encoding="utf-8")
    globals_css = (ROOT / "frontend" / "app" / "globals.css").read_text(encoding="utf-8")

    # Nota (consolidación 2026-07-09, decisión de Pipe): el paso de jurisdicción SÍ
    # hardcodea una lista fija de 21 países hispanohablantes en el frontend — es
    # deliberado (UNA sola pregunta de país, selección múltiple; los países con paquete
    # jurídico llevan insignia, los demás se eligen igual). El resto de conocimiento
    # jurídico (ramas, tipo de cliente, tribunales, marcas) sigue prohibido de hardcodear.
    forbidden = (
        "Seguros", "Fiscal", "Civil", "Penal", "Laboral", "Contencioso", "Contratos Publicos",
        "Aseguradoras", "Empresas", "Personas", "Sector Publico", "Sector Público",
        "Consejo de Estado", "Corte Constitucional", "Corte Suprema", "Tribunal Adm.",
        "Obsidian", "Claude Code", "Linear", "WhatsApp Business",
    )
    check("onboarding sin opciones jurídicas hardcodeadas (fuera de la lista de países)",
          not any(x in onboarding for x in forbidden))
    check("pregunta ÚNICA de país: multi-select de 21 países, Colombia primero, con insignia de paquete",
          "COUNTRY_OPTIONS" in onboarding and '"p5"' not in onboarding
          and onboarding.index('name: "Colombia"') < onboarding.index('name: "Argentina"')
          and "Conocimiento jurídico profundo" in onboarding
          and onboarding.count("¿Con las reglas jurídicas de qué país trabaja tu despacho?") == 1)
    check("la selección de país auto-llena jurisdiction.base (nombres) además de jurisdictions (códigos)",
          'soulResponses["jurisdiction.base"]' in onboarding and "COUNTRY_NAME_BY_CODE" in onboarding)
    check("P6/P7/P18 son tags libres", all(f'"{x}"' in onboarding for x in ("p6", "p7", "p18")) and "TAG_IDS" in onboarding)
    check("P8/P9 son texto libre", all(f'"{x}"' in onboarding for x in ("p8", "p9")) and "TEXT_IDS" in onboarding and "p8:" not in onboarding and "p9:" not in onboarding)
    check("P10/P11/P14/P17 removidas del wizard (voz/límites/ritmo)",
          not any(f'"{x}"' in onboarding for x in ("p10", "p11", "p14", "p17")))
    check("barra de progreso thin", "h-1 w-full" in onboarding)
    check("pregunta centrada", "text-center text-2xl" in onboarding)
    # Los 3 checks siguientes se actualizaron al design system del pase wow
    # (2026-07, aprobado por Pipe): tokens HSL de shadcn en vez de hex crudos.
    # El CONTRATO es el mismo — estado activo visible en el sidebar, burbujas
    # diferenciadas usuario/Mia, paleta definida — con las clases vigentes.
    check("sidebar activo con estado visible (tokens DS)",
          "text-primary" in sidebar and ("bg-accent" in sidebar or "bg-primary/10" in sidebar))
    check("chat usa burbuja de usuario en primario y Mia en tarjeta",
          "bg-primary" in workspace and "text-primary-foreground" in workspace
          and "bg-card" in workspace)
    check("paleta con tokens HSL (claro y oscuro) y primario definido",
          "--primary:" in globals_css and "hsl(var(--" in globals_css
          and globals_css.count("--background:") >= 2)

    passed = sum(1 for _, ok in _results if ok)
    total = len(_results)
    print(f"\nRESULT: {passed}/{total} checks PASS")
    if passed == total:
        print("Onboarding horizontal OK.")
        return 0
    print("Onboarding horizontal FAIL.")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
