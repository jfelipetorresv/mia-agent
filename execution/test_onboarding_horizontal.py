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

    forbidden = (
        "Colombia", "Espana", "España", "Mexico", "México", "Argentina", "Peru", "Perú", "Chile",
        "Seguros", "Fiscal", "Civil", "Penal", "Laboral", "Contencioso", "Contratos Publicos",
        "Aseguradoras", "Empresas", "Personas", "Sector Publico", "Sector Público",
        "Consejo de Estado", "Corte Constitucional", "Corte Suprema", "Tribunal Adm.",
        "Obsidian", "Claude Code", "Linear", "WhatsApp Business",
    )
    check("onboarding sin opciones jurídicas hardcodeadas", not any(x in onboarding for x in forbidden))
    check("P5 es texto libre", '"p5"' in onboarding and "TEXT_IDS" in onboarding and "SELECT_OPTIONS" in onboarding and "p5:" not in onboarding)
    check("P6/P7/P18 son tags libres", all(f'"{x}"' in onboarding for x in ("p6", "p7", "p18")) and "TAG_IDS" in onboarding)
    check("P8/P9 son texto libre", all(f'"{x}"' in onboarding for x in ("p8", "p9")) and "CHECKBOX_OPTIONS" in onboarding and "p8:" not in onboarding and "p9:" not in onboarding)
    check("P10 usa opciones genéricas", all(x in onboarding for x in ("Narrativo continuo", "Estructurado con secciones", "Depende del tipo de escrito")))
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
