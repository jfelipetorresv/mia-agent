"""
Mia · test_activar_motor_unico.py — gate del bloque D4 («un solo motor, claves
entendibles», bitácora UX 2026-08-19, puntos 2-4).

Custodia, sobre frontend/app/activar/page.tsx (checks estáticos, mismo criterio
que test_onboarding_horizontal.py):

  M · UN paso de motor: la detección PRESELECCIONA (no solo etiqueta), y la
      tarjeta de OpenRouter NO compite como motor hermano — solo aparece en
      instalaciones que ya venían con esa política guardada.
  H · Honestidad de Codex (commit d0aa95b): la etiqueta sale de los TRES hechos
      separados (instalada / sesión / habilitada por política) y jamás dice
      «no está instalada» cuando sí lo está.
  K · UNA sola pantalla de claves: los sub-pasos separados de búsqueda y
      respaldo desaparecieron; la clave de búsqueda se enuncia como REQUISITO
      con su consecuencia, no como consejo.
  C · OpenRouter como consentimiento consciente: `allow_openrouter` viaja SOLO
      con la casilla de consentimiento expresa (o cuando OpenRouter ES el motor
      elegido), nunca como efecto colateral de pegar una clave; el copy dice qué
      es, que solo entra si el principal falla, que el gasto lo paga el abogado
      y que los datos salen a un servicio externo.
  G · §G: sin jerga técnica en lo que puede llegar a la pantalla.

Los checks exigen el CONCEPTO, no la redacción literal, salvo donde la palabra
es el concepto (p. ej. «requisito»). Exit 0 = PASS · 1 = FAIL.
    .venv\\Scripts\\python.exe execution\\test_activar_motor_unico.py
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


def sin_comentarios(src: str) -> str:
    """El código sin comentarios de línea — aproximadamente lo que el abogado
    PUEDE llegar a ver. Los checks de jerga se hacen sobre esto: un comentario
    puede nombrar lo técnico para explicarlo; la pantalla no."""
    return "\n".join(re.sub(r"(?<!:)//.*", "", line) for line in src.split("\n"))


def main() -> int:
    print("== D4 · un solo motor, claves entendibles (activar) ==")
    page_path = ROOT / "frontend" / "app" / "activar" / "page.tsx"
    src = page_path.read_text(encoding="utf-8")
    visible = sin_comentarios(src)

    # ── M · un paso de motor con preselección real ─────────────────────────────
    check("M1 · la detección PRESELECCIONA el motor (no solo pinta una etiqueta)",
          "preseleccionMotor" in src
          and "setPolitica(preseleccionMotor(s))" in src
          and "motor_detectado" in src)
    # La preselección respeta la política guardada cuando su motor sigue presente,
    # y si no, manda lo detectado (Claude Code → Codex → Ollama → nube).
    presel = src[src.index("function preseleccionMotor"):]
    presel = presel[:presel.index("\n}")]
    check("M2 · orden de preferencia: Claude detectado → adaptativa; luego Codex; luego local",
          presel.index('d.claude) return "quality_adaptive"')
          < presel.index('d.codex) return "codex"')
          < presel.index('d.ollama) return "soberano"'))
    # OpenRouter NO es una tarjeta hermana del grupo de motores: solo se pinta si
    # la instalación YA venía con esa política (no cambiarle el motor en silencio).
    or_card = src.find('title="Tu cuenta de OpenRouter"')
    guard = src.rfind('status.politica === "openrouter" && (', 0, or_card if or_card > 0 else 0)
    check("M3 · la tarjeta de OpenRouter NO compite como motor: solo con política ya guardada",
          or_card > 0 and guard > 0 and (or_card - guard) < 400)
    check("M4 · el orden del teclado se construye del MISMO arreglo condicional (engineOrder)",
          "const engineOrder: Politica[]" in src
          and 'status.politica === "openrouter" ? (["openrouter"]' in src
          and "const order = engineOrder" in src)

    # ── H · honestidad de Codex (tres hechos separados, d0aa95b) ───────────────
    check("H1 · la etiqueta de Codex sale de motor_estado (instalada/sesion/habilitada)",
          "etiquetaCodex" in src
          and "motor_estado?.codex" in src
          and "habilitada_por_politica" in src
          and re.search(r"if \(!e\.instalada\) return undefined", src) is not None)
    check("H2 · jamás dice «no está instalada» en pantalla",
          "no está instalada" not in visible and "no está instalado" not in visible)

    # ── K · una sola pantalla de claves, con requisitos como requisitos ────────
    check("K1 · los sub-pasos separados de búsqueda/respaldo desaparecieron",
          "const stepClaves" in src
          and "const stepBusqueda" not in src
          and "const stepRespaldo =" not in src)
    check("K2 · la clave de búsqueda se enuncia como REQUISITO con su consecuencia",
          "requisito" in visible
          and "sin ella no leo ni encuentro nada" in visible.lower())
    check("K3 · el camino de omitir la búsqueda dice la consecuencia de frente",
          "Seguir sin activar la búsqueda" in src)
    check("K4 · solo se muestran las claves que aplican al motor elegido",
          "{respaldoEsMotor && (" in src
          and "{openrouterEsMotor && (" in src
          and "{respaldoAplica && !respaldoEsMotor && (" in src)
    check("K5 · en «nube» la clave ES el motor y se dice (no «respaldo» a secas)",
          "esta clave ES tu motor" in src)
    check("K6 · con motor obligatorio la pantalla no deja continuar sin su clave validada",
          '(!respaldoEsMotor || respaldo.state === "ok")' in src
          and '(!openrouterEsMotor || openrouter.state === "ok")' in src)
    # En «soberano» (nada sale del equipo) no se ofrece ningún respaldo externo.
    check("K7 · «soberano» no ofrece respaldos externos (ni clave de respaldo ni OpenRouter)",
          'politica !== "soberano"' in src
          and 'const respaldoAplica = politica !== "openrouter" && politica !== "soberano"' in src)

    # ── C · OpenRouter: consentimiento consciente, no efecto colateral ─────────
    check("C1 · existe la casilla de consentimiento expresa (checkbox real)",
          'type="checkbox"' in src and "orConsent" in src
          and "setOrConsent(e.target.checked)" in src)
    check("C2 · allow_openrouter viaja SOLO bajo consentimiento (o cuando ES el motor)",
          "const openrouterAutorizado = openrouterEsMotor || (openrouterRespaldoAplica && orConsent)"
          in src
          and src.count("allow_openrouter: true") == 1
          and "conectoOpenrouter ? { allow_openrouter: true }" in src)
    check("C3 · la clave de respaldo de OpenRouter solo se envía con el consentimiento",
          "openrouterAutorizado && openrouter.state" in src
          and "if (conectoOpenrouter) payload.openrouter" in src)
    consent_txt = visible.lower()
    check("C4 · el copy dice que SOLO entra cuando el motor principal falla",
          "cuando tu motor principal falla" in consent_txt
          or "cuando mi motor principal falle" in consent_txt)
    check("C5 · el copy dice que el gasto lo paga el abogado",
          "el gasto corre por tu cuenta" in consent_txt or "ese uso lo pago yo" in consent_txt)
    check("C6 · el copy dice que los datos salen a un servicio externo",
          "servicio externo" in consent_txt)
    check("C7 · la explicación usa la nota de Mia (NotaMia), visible y no cerrable",
          "NotaMia" in src and 'id="activar-openrouter-respaldo"' in src
          and "cerrable={false}" in src)

    # ── G · §G: sin jerga técnica en lo visible ────────────────────────────────
    jerga = [p for p in ("API key", "api key", "endpoint", "embedding", "LLM", "fallback")
             if p in visible]
    check("G1 · sin jerga técnica en lo que puede llegar a la pantalla",
          not jerga)

    passed = sum(1 for _, ok in _results if ok)
    total = len(_results)
    print(f"\nRESULT: {passed}/{total} checks PASS")
    if passed == total:
        print("Activar D4 OK — un solo motor con preselección, claves entendibles y "
              "consentimiento expreso de OpenRouter.")
        return 0
    print("Activar D4 FAIL — revisar antes de entregar.")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
