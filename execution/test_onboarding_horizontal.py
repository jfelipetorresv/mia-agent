"""
Mia · test_onboarding_horizontal.py — gate de onboarding horizontal + pulido visual.
"""
from __future__ import annotations

import re
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
    # C2 (Bloque C, perfil del despacho editable y unificado): COUNTRY_OPTIONS y el
    # checklist de países se extrajeron a CountrySelector.tsx (compartido con "Mi
    # despacho") — mismo criterio que ya usa este gate para Conexiones (configurar +
    # ConexionesSection.tsx). `onboarding_surface` es lo que antes vivía todo inline.
    country_selector = (ROOT / "frontend" / "app" / "_components" / "CountrySelector.tsx").read_text(encoding="utf-8")
    onboarding_surface = onboarding + country_selector
    # "Mi despacho" edita la MISMA fuente que la entrevista: si la entrevista deja escribir
    # un país fuera de la lista y esta pantalla no, el abogado lo pierde al editar.
    despacho = (ROOT / "frontend" / "app" / "_components" / "MiDespachoSection.tsx").read_text(encoding="utf-8")
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
    # Contrato 2026-07-20: UNA sola pregunta de país, sin país destacado. La lista sigue
    # en orden alfabético (nadie va "primero" — regla dura: Mia no es de ningún país; la
    # versión anterior de este check exigía Colombia arriba y contradecía esa regla).
    paises = re.findall(r'name:\s*"([^"]+)"', country_selector)
    check("pregunta ÚNICA de país, en orden alfabético y sin ningún país destacado",
          "COUNTRY_OPTIONS" in onboarding_surface and '"p5"' not in onboarding
          and len(paises) >= 20 and paises == sorted(paises)
          and onboarding.count("¿Con las reglas jurídicas de qué país trabaja tu despacho?") == 1)
    check("la selección de país auto-llena jurisdiction.base (nombres) además de jurisdictions (códigos)",
          'soulResponses["jurisdiction.base"]' in onboarding and "COUNTRY_NAME_BY_CODE" in onboarding)
    # LA SALIDA. Sin esto, un despacho de un país que no está entre las casillas no puede
    # terminar el alta — cierra mercados enteros y choca de frente con la regla dura del
    # producto. Se exige la vía completa: campo libre + que baste para avanzar + que el
    # dato llegue al perfil + modo general cuando no hay ningún código de paquete.
    check("un país FUERA de la lista tiene salida y no bloquea el alta",
          "JURISDICTION_OTHER_FIELD" in onboarding
          and "asList(answers[JURISDICTION_OTHER_FIELD]).length > 0" in onboarding
          and "GENERIC_JURISDICTION" in onboarding
          and "...otros" in onboarding)
    check("«Mi despacho» también deja editar un país fuera de la lista",
          "otherCountries" in despacho and "GENERIC_JURISDICTION" in despacho)
    # El cuestionario vigente: p6 (a quién defiende / en qué asuntos) y p20/p21 (autonomía,
    # líneas rojas) son chips libres; p22 (estándar de cierre) es texto libre.
    check("P6/P20/P21 son tags libres y P22 texto libre",
          all(f'"{x}"' in onboarding for x in ("p6", "p20", "p21", "p22"))
          and "TAG_IDS" in onboarding and "TEXT_IDS" in onboarding)
    # p19 (modo profundo) es la excepción: se nombra SOLO para filtrarlo si el backend
    # todavía lo enviara (Riesgo #27 — no se ofrece lo que no está implementado).
    check("las preguntas retiradas NO volvieron al wizard (P3/P4/P5/P7-P18)",
          not any(f'"{x}"' in onboarding for x in
                  ("p3", "p4", "p5", "p7", "p8", "p9", "p10", "p11", "p12", "p13",
                   "p14", "p15", "p16", "p17", "p18")))
    check("el modo profundo (p19) solo aparece para quedar OCULTO del wizard",
          'HIDDEN_QUESTION_IDS = new Set(["p19"])' in onboarding
          and onboarding.count('"p19"') == 1)
    check("barra de progreso thin", "h-0.5 w-full" in onboarding)
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
