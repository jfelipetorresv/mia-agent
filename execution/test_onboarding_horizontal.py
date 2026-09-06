"""Mia · gate visual estático del alta y creación simplificadas.

El alta no entrevista ni presupone identidad. Crear un caso solo pide nombre, con
descripción y jurisdicción opcionales; el modo de respuesta directa no se ofrece.
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass


def check(name: str, ok: bool) -> bool:
    print(("  [OK]   " if ok else "  [FAIL] ") + name)
    return bool(ok)


def main() -> int:
    print("== Alta y casos simplificados ==")
    onboarding = (ROOT / "frontend" / "app" / "onboarding" / "page.tsx").read_text(encoding="utf-8")
    cases = (ROOT / "frontend" / "app" / "casos" / "page.tsx").read_text(encoding="utf-8")
    soul = (ROOT / "backend" / "mia" / "onboarding" / "soul_interview.py").read_text(encoding="utf-8")
    ux = (ROOT / "backend" / "mia" / "api" / "routes" / "ux.py").read_text(encoding="utf-8")

    create_route = ux.split("@router.post(\"/matters\"", 1)[1].split("@router.get(\"/matters/{matter_id}\")", 1)[0]

    results = [
        check("el alta no muestra una entrevista",
              'apiSend("POST", "/api/onboarding/complete", { responses: {} })' in onboarding
              and "questions" not in onboarding and "CountrySelector" not in onboarding),
        check("el alta explica el siguiente paso sin exponer implementación",
              "Tu espacio está listo." in onboarding
              and "Crea un caso y conversa con Mia." in onboarding
              and "Cada documento se entrega como borrador para tu" in onboarding
              and "El contexto de tu firma u organización se completará" in onboarding
              and "Puedes revisarlo en Configuración." in onboarding
              and "no necesito una entrevista" not in onboarding
              and "no asumirá quién defiendes" not in onboarding),
        check("las preguntas obligatorias ya no existen",
              "QUESTIONS: list[dict] = []" in soul and "¿A quién defiendes" not in soul
              and "¿Qué quieres revisar siempre" not in soul and "¿Qué no debo hacer nunca" not in soul),
        check("un perfil vacío queda marcado como aprendizaje, sin identidad inventada",
              "Perfil en aprendizaje" in soul and "if body.responses:" in ux),
        check("el diálogo de caso solo pide nombre y contexto opcional",
              "Descripción (opcional)" in cases and "Jurisdicción de este caso" in cases
              and "Modo de trabajo" not in cases and "radiogroup" not in cases),
        check("la pantalla no envía un modo elegible al crear", "kind," not in cases and "setKind" not in cases),
        check("el servidor fija los casos nuevos al flujo con aprobación",
              'kind = "asunto"' in create_route and "body.kind not in _MATTER_KINDS" in create_route),
        check("la lista comunica que todo borrador requiere aprobación",
              "borrador queda esperando tu aprobación" in cases),
    ]
    passed = sum(results)
    print(f"\nRESULT: {passed}/{len(results)} checks PASS")
    return 0 if passed == len(results) else 1


if __name__ == "__main__":
    raise SystemExit(main())
