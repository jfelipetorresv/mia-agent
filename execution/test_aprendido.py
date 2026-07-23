"""
Mia · test_aprendido.py — gate de la sección «## aprendido» que se llena sola.

Paso 7 de docs/diseno-soul-onboarding.md: la entrevista NO se alarga; el perfil se
enriquece solo. De cada borrador que el abogado aprueba, Mia infiere 0..N patrones de
METODOLOGÍA del despacho y los deposita en `## aprendido` vía `update_soul`.

Invariantes que se prueban (cada uno con su mutación demostrada en el encargo):
  A · cada línea nueva lleva [inferido] + fecha absoluta + fuente por tipo de trabajo.
  B · salida ESTRICTA: lo que no es un arreglo JSON de frases se descarta en silencio.
  C · FAIL-SOFT: si el modelo revienta, la aprobación NO se rompe y el perfil no cambia.
  D · dedup exacto y normalizado (el mismo aprendizaje no se repite ni re-inferido otro día).
  E · TOPE que no trunca: al llenarse se deja de añadir; nunca se borra ni recorta.
  F · una línea que el abogado corrigió a mano SOBREVIVE a la siguiente inferencia.
  G · aislamiento: aprender en el despacho A no toca el perfil del despacho B.

OFFLINE — sin DB, sin red: todo es archivo (SOUL.md/responses.json) y funciones puras;
el modelo va mockeado POR ENCIMA de la conversión de caché (se parchea `aprendido.call_llm`,
inmune al meta-gate de aserciones ciegas).

Salida: exit 0 = PASS · exit 1 = FAIL.
    .venv\\Scripts\\python.exe execution\\test_aprendido.py
"""
from __future__ import annotations

import asyncio
import sys
import tempfile
from datetime import date
from pathlib import Path
from types import SimpleNamespace

if sys.platform == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

from mia import config  # noqa: E402
from mia.memory import aprendido as ap  # noqa: E402
from mia.onboarding.soul_interview import (  # noqa: E402
    SoulInterview, load_responses, load_soul_text, soul_path,
)

_results: list[tuple[str, bool]] = []


def check(name: str, ok: bool) -> None:
    _results.append((name, bool(ok)))
    print(("  [OK]   " if ok else "  [FAIL] ") + name)


# ── Modelo mockeado: devuelve lo que ponga _PAYLOAD["value"] (o lanza si _PAYLOAD["raise"]) ──
_PAYLOAD: dict = {"value": "[]", "raise": False}


def fake_llm(messages, *, task=None, **kwargs):
    if _PAYLOAD.get("raise"):
        raise RuntimeError("modelo caído (simulado)")
    return SimpleNamespace(
        choices=[SimpleNamespace(message=SimpleNamespace(content=_PAYLOAD["value"]))])


def set_model(value, *, raises: bool = False) -> None:
    _PAYLOAD["value"] = value
    _PAYLOAD["raise"] = raises


async def seed_profile(tenant: str) -> None:
    """Deja al despacho con un perfil base (como tras el onboarding)."""
    await SoulInterview().update_soul(
        tenant, {"identity.name": {"firm": "Despacho Prueba", "lawyer": "Abg. Prueba"}})


def aprendido_of(tenant: str) -> list[str]:
    val = load_responses(tenant).get("aprendido")
    return val if isinstance(val, list) else ([] if val is None else [val])


DAY = date(2026, 7, 20)


# ══ A · formato: [inferido] + fecha + fuente ══════════════════════════════════
def check_formato() -> None:
    print("\n== A · cada línea nueva: [inferido] + fecha + fuente ==")

    linea = ap.build_line("Estructura sus escritos en secciones numeradas.",
                          source=ap.SOURCE_APROBADO, today=DAY)
    check("A1 · build_line marca la línea como [inferido]", ap.INFERIDO_MARK in linea)
    check("A2 · build_line pone la fecha absoluta del día", "2026-07-20" in linea)
    check("A3 · build_line cita la fuente por tipo de trabajo (no datos del caso)",
          "· fuente: " in linea and ap.SOURCE_APROBADO in linea)


async def check_formato_e2e() -> None:
    tenant = "fmt-e2e"
    await seed_profile(tenant)
    set_model('["Cita jurisprudencia solo tras verificar la fuente."]')
    res = await ap.learn_from_approved_draft(tenant, "Texto del borrador aprobado.", today=DAY)
    check("A4 · el enganche reporta 1 aprendizaje añadido", res["added"] == 1)

    lineas = aprendido_of(tenant)
    check("A5 · la sección tiene exactamente la línea nueva", len(lineas) == 1)
    ln = lineas[0] if lineas else ""
    check("A6 · la línea escrita lleva [inferido], fecha y fuente",
          ap.INFERIDO_MARK in ln and "2026-07-20" in ln and "fuente:" in ln)

    soul = load_soul_text(tenant) or ""
    check("A7 · el SOUL.md renderiza la sección '## aprendido' con la línea",
          "## aprendido" in soul and "Cita jurisprudencia solo tras verificar" in soul)


# ══ B · salida estricta: formato inválido se descarta en silencio ═════════════
def check_estricto() -> None:
    print("\n== B · salida estricta (lo que no es arreglo de frases se descarta) ==")

    check("B1 · un arreglo JSON de frases sí se acepta",
          ap._parse_insights('["Usa un tono formal.", "Numera los hechos."]')
          == ["Usa un tono formal.", "Numera los hechos."])
    check("B2 · prosa suelta (no JSON) → se descarta ([])",
          ap._parse_insights("Aprendí que le gusta el tono formal.") == [])
    check("B3 · un objeto JSON (no arreglo) → se descarta ([])",
          ap._parse_insights('{"estilo": "formal"}') == [])
    check("B4 · elementos que no son cadenas se descartan (se filtran, no rompen)",
          ap._parse_insights('["Frase válida.", 3, null, {"x":1}]') == ["Frase válida."])
    check("B5 · una frase desmesuradamente larga (probable volcado del caso) se descarta",
          ap._parse_insights('["' + "x" * (ap.MAX_INSIGHT_CHARS + 5) + '"]') == [])
    check("B6 · el lote se acota a MAX_PER_INFERENCE",
          len(ap._parse_insights("[" + ",".join(f'"frase numero {i}"'
              for i in range(ap.MAX_PER_INFERENCE + 4)) + "]")) == ap.MAX_PER_INFERENCE)


# ══ C · fail-soft: el fallo del modelo no rompe la aprobación ══════════════════
async def check_fail_soft() -> None:
    print("\n== C · fail-soft (el modelo revienta y la aprobación sigue) ==")

    set_model("", raises=True)
    check("C1 · infer_learnings traga el fallo del modelo y devuelve []",
          ap.infer_learnings("un borrador cualquiera") == [])

    tenant = "failsoft"
    await seed_profile(tenant)
    soul_antes = load_soul_text(tenant)
    raised = False
    res = None
    try:
        res = await ap.learn_from_approved_draft(tenant, "Texto del borrador.", today=DAY)
    except Exception:
        raised = True
    check("C2 · learn_from_approved_draft NO propaga la excepción del modelo", not raised)
    check("C3 · con el modelo caído no se añade nada", res is not None and res["added"] == 0)
    check("C4 · con el modelo caído el perfil queda intacto",
          load_soul_text(tenant) == soul_antes and aprendido_of(tenant) == [])
    set_model("[]", raises=False)


# ══ D · dedup exacto y normalizado ════════════════════════════════════════════
def check_dedup_puro() -> None:
    print("\n== D · dedup exacto y normalizado ==")

    base = ap.build_line("Cita la fuente primaria.", source=ap.SOURCE_APROBADO, today=DAY)
    # Exacto: la misma línea no se duplica.
    merged, added, _ = ap.merge_aprendido([base], [base])
    check("D1 · dedup exacto: una línea idéntica no se añade dos veces",
          added == 0 and merged == [base])

    # Normalizado: mismo núcleo con otra fecha, espacios y mayúsculas → no se duplica.
    otro_dia = ap.build_line("cita   la  fuente   PRIMARIA.",
                             source=ap.SOURCE_CORREGIDO, today=date(2027, 1, 1))
    merged2, added2, _ = ap.merge_aprendido([base], [otro_dia])
    check("D2 · dedup normalizado: mismo aprendizaje (otra fecha/espacios/mayúsculas) "
          "no se re-añade", added2 == 0 and merged2 == [base])


async def check_dedup_e2e() -> None:
    tenant = "dedup-e2e"
    await seed_profile(tenant)
    set_model('["Redacta los hechos en orden cronológico."]')
    await ap.learn_from_approved_draft(tenant, "Borrador 1.", today=date(2026, 7, 20))
    # Mismo aprendizaje, otro día: no debe duplicar.
    await ap.learn_from_approved_draft(tenant, "Borrador 2.", today=date(2026, 8, 30))
    check("D3 · re-inferir el mismo aprendizaje otro día no duplica la línea",
          len(aprendido_of(tenant)) == 1)


# ══ E · el tope no trunca ══════════════════════════════════════════════════════
def check_tope_puro() -> None:
    print("\n== E · el tope deja de añadir, no trunca ni borra ==")

    lleno = [ap.build_line(f"Aprendizaje número {i}.", source=ap.SOURCE_APROBADO, today=DAY)
             for i in range(ap.APRENDIDO_MAX)]
    nuevos = [ap.build_line("Aprendizaje que ya no cabe.", source=ap.SOURCE_APROBADO, today=DAY)]
    merged, added, dropped = ap.merge_aprendido(lleno, nuevos)
    check("E1 · al tope no se añade la línea nueva", added == 0 and dropped == 1)
    check("E2 · el tope NO trunca: se conservan las MAX entradas anteriores intactas",
          merged == lleno and len(merged) == ap.APRENDIDO_MAX)


async def check_tope_e2e() -> None:
    tenant = "tope-e2e"
    await seed_profile(tenant)
    lleno = [ap.build_line(f"Convención {i}.", source=ap.SOURCE_APROBADO, today=DAY)
             for i in range(ap.APRENDIDO_MAX)]
    await SoulInterview().update_soul(tenant, {"aprendido": list(lleno)})
    set_model('["Un patrón nuevo que llega con la sección llena."]')
    res = await ap.learn_from_approved_draft(tenant, "Borrador.", today=DAY)
    despues = aprendido_of(tenant)
    check("E3 · con la sección llena, la aprobación no añade y reporta lo no cabido",
          res["added"] == 0 and res["dropped"] == 1)
    check("E4 · la sección sigue con las MAX entradas anteriores, ninguna borrada",
          despues == lleno and len(despues) == ap.APRENDIDO_MAX)


# ══ F · una línea corregida a mano por el abogado sobrevive ════════════════════
async def check_edicion_abogado() -> None:
    print("\n== F · la línea que el abogado corrigió a mano sobrevive ==")

    tenant = "edicion"
    await seed_profile(tenant)
    # El abogado escribe/edita a mano (desde «Mi despacho»): una línea SIN el formato
    # [inferido] y una línea inferida que él ajustó.
    manual = "Nunca uso lenguaje coloquial en los escritos."
    inferida_editada = ap.build_line("Firma siempre con el nombre completo del despacho.",
                                     source=ap.SOURCE_APROBADO, today=date(2026, 1, 1))
    await SoulInterview().update_soul(tenant, {"aprendido": [manual, inferida_editada]})

    # Nueva inferencia con aprendizajes DISTINTOS.
    set_model('["Estructura la petición en un solo párrafo final."]')
    await ap.learn_from_approved_draft(tenant, "Borrador nuevo.", today=DAY)
    despues = aprendido_of(tenant)
    check("F1 · la línea manual del abogado sigue presente tras la inferencia",
          manual in despues)
    check("F2 · la línea inferida que el abogado editó sigue presente",
          inferida_editada in despues)
    check("F3 · el aprendizaje nuevo se apendó sin desplazar lo anterior",
          any("un solo párrafo final" in x for x in despues) and len(despues) == 3)

    # Y si el aprendizaje nuevo coincide con una línea manual, se respeta la del abogado
    # (dedup) y no se duplica.
    tenant2 = "edicion-dup"
    await seed_profile(tenant2)
    manual2 = "Cita solo fuentes verificadas."
    await SoulInterview().update_soul(tenant2, {"aprendido": [manual2]})
    set_model('["cita solo fuentes verificadas"]')   # mismo núcleo, otras mayúsculas/puntos
    await ap.learn_from_approved_draft(tenant2, "Borrador.", today=DAY)
    check("F4 · un aprendizaje que repite una línea manual no la reemplaza ni la duplica",
          aprendido_of(tenant2) == [manual2])


# ══ G · aislamiento entre despachos ════════════════════════════════════════════
async def check_aislamiento() -> None:
    print("\n== G · aislamiento entre despachos ==")

    a, b = "despacho-A", "despacho-B"
    await seed_profile(a)
    await seed_profile(b)
    b_soul_antes = load_soul_text(b)

    set_model('["Ordena los anexos al final del escrito."]')
    await ap.learn_from_approved_draft(a, "Borrador del despacho A.", today=DAY)

    check("G1 · cada despacho tiene su propio archivo de perfil",
          soul_path(a) != soul_path(b))
    check("G2 · aprender en A no escribió NADA en la sección de B",
          aprendido_of(b) == [])
    check("G3 · el SOUL.md de B quedó intacto tras aprender en A",
          load_soul_text(b) == b_soul_antes)
    check("G4 · el aprendizaje sí aterrizó en A (no fue un no-op silencioso)",
          any("anexos al final" in x for x in aprendido_of(a)))


# ══ H · cableado del route HITL (F2: la corrección también aprende) ═══════════
def check_cableado_hitl() -> None:
    print("\n== H · cableado en api/routes/hitl.py (editing también aprende) ==")
    # Por fuente y no por HTTP: levantar el stack SSE completo aquí duplicaría
    # test_hitl_flow; lo que este gate protege es que el path `editing` no vuelva
    # a quedar descableado en silencio (estuvo así hasta F2 pese a que el módulo
    # ya traía SOURCE_CORREGIDO).
    src = (ROOT / "backend" / "mia" / "api" / "routes" / "hitl.py").read_text(
        encoding="utf-8")
    check("H1 · el aprendizaje corre al aprobar Y al corregir (no solo approved)",
          'in ("approved", "editing")' in src)
    check("H2 · la corrección aprende con su propia fuente (SOURCE_CORREGIDO)",
          "SOURCE_CORREGIDO" in src and "SOURCE_APROBADO" in src)


async def async_main() -> int:
    print("== Gate · «## aprendido» se llena sola desde el trabajo aprobado ==")
    original_llm = ap.call_llm
    original_home = config.MIA_HOME
    ap.call_llm = fake_llm
    try:
        with tempfile.TemporaryDirectory() as tmp:
            config.MIA_HOME = Path(tmp)
            check_formato()
            await check_formato_e2e()
            check_estricto()
            await check_fail_soft()
            check_dedup_puro()
            await check_dedup_e2e()
            check_tope_puro()
            await check_tope_e2e()
            await check_edicion_abogado()
            await check_aislamiento()
            check_cableado_hitl()
    finally:
        ap.call_llm = original_llm
        config.MIA_HOME = original_home

    passed = sum(1 for _, ok in _results if ok)
    total = len(_results)
    print(f"\nRESULT: {passed}/{total} checks PASS")
    if passed == total:
        print("aprendido OK — el perfil se enriquece solo, sin alargar la entrevista, "
              "y sin romper la aprobación.")
        return 0
    print("aprendido FAIL — no avanzar.")
    return 1


def main() -> int:
    return asyncio.run(async_main())


if __name__ == "__main__":
    raise SystemExit(main())
