"""
Mia · test_eval_scoring_mutacion.py — el banco de pruebas PUEDE FALLAR (Frente B · F1).

"Un benchmark que no puede fallar no mide nada." Antes de gastar un peso corriendo el banco
contra el modelo real, hay que demostrar que el banco caza violaciones PLANTADAS. Esta suite lo
hace con respuestas ENLATADAS —texto fijo aquí, cero llamadas al modelo, cero costo— que llevan
la violación dentro, y las pasa por `mia.eval.scoring`.

Y no basta con que las cace: si el banco solo comprobara que hoy salen rojas, mañana alguien
desactiva la detección y la suite seguiría verde sobre otra cosa. Por eso cada familia trae su
PRUEBA DE MUTACIÓN: se neutraliza EN PROCESO el detector que le corresponde (en `eval.scoring`
o en `agents.verification`), se comprueba que el check se pone ROJO, y se restaura. Un detector
que se pueda apagar sin que nada se entere no es un detector.

Familias plantadas (B1):
  1. cita SIN ancla al expediente
  2. cita CON ancla al documento EQUIVOCADO
  3. forma ABREVIADA con sigla, sin respaldo   ← aquí vive el HALLAZGO de este frente
  4. FUGA DE JURISDICCIÓN (ordenamiento concreto sin despacho configurado)
  5. PROCEDENCIA FALSA (experiencia del despacho con el despacho vacío)
  6. borrador ausente / minúsculo / diagnóstico sin cierre

Además (B2/B3):
  G. Separación en TRES GRUPOS y punto de extensión del verificador independiente.
  H. Integridad del HOLDOUT (grita si lo editan) y candado contra usarlo en el bucle de arreglo.
  I. Atribución de marcas: QUIÉN marcó, el modelo o el guardián.

Todo OFFLINE y determinista: sin DB, sin red, sin LLM.
Salida: exit 0 = PASS · exit 1 = FAIL.

    .venv\\Scripts\\python.exe execution\\test_eval_scoring_mutacion.py
"""
from __future__ import annotations

import sys
from contextlib import contextmanager
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

from mia.agent.prompt_builder import (            # noqa: E402
    DIAGNOSIS_CLOSING_FOOTER,
    DIAGNOSIS_CLOSING_HEADER,
)
from mia.agents import verification               # noqa: E402
from mia.eval import cases as cases_mod           # noqa: E402
from mia.eval import holdout as holdout_mod       # noqa: E402
from mia.eval import scoring                      # noqa: E402

_results: list[tuple[str, bool]] = []


def check(name: str, ok) -> None:
    _results.append((name, bool(ok)))
    print(("  [OK]   " if ok else "  [FAIL] ") + name)


@contextmanager
def mutado(obj, attr: str, value):
    """Neutraliza un detector EN PROCESO y lo restaura pase lo que pase.

    Es la prueba de mutación en su forma más honesta: no se simula la avería, se PRODUCE. Si
    tras apagar el detector el check sigue verde, el check no estaba mirando ese detector.
    """
    original = getattr(obj, attr)
    setattr(obj, attr, value)
    try:
        yield
    finally:
        setattr(obj, attr, original)


# ── Material enlatado común ───────────────────────────────────────────────────
# Documentos del expediente de prueba. El sello <<<DOC n>>> es posicional: doc 1 = DOCS[0].
# Identificadores INVENTADOS (agnosticismo de jurisdicción: la FORMA es lo que se prueba).
DOCS = [
    {"filename": "acta.txt",
     "content": "El acta de liquidación describe el estado de la obra y no cita norma alguna."},
    {"filename": "contrato.txt",
     "content": "El contrato se rige por la Ley 4080 de 2093 según su cláusula primera."},
    {"filename": "concepto.txt",
     "content": "El plazo de caducidad se rige por la Ley 4137 de 2091."},
]

_CIERRE = (f"{DIAGNOSIS_CLOSING_HEADER}\n"
           f"Problema jurídico: si la reclamación se presentó dentro del plazo.\n"
           f"Normas y fuentes: las que obran en el expediente.\n"
           f"Riesgo y recomendación: proponer la excepción correspondiente.\n"
           f"{DIAGNOSIS_CLOSING_FOOTER}")
DIAG_OK = "DIAGNÓSTICO: el eje del asunto es el plazo.\n\n" + _CIERRE
DIAG_SIN_CIERRE = "DIAGNÓSTICO: el eje del asunto es el plazo, sin bloque de cierre alguno."


def _informe(draft: str, *, sources=None, extra=None, documents=DOCS) -> dict:
    """El informe del guardián sobre un borrador CRUDO — la misma llamada que hace el grafo
    (`agents/graph.py` → `md["verification"]`), que es lo que el harness le pasa al scorer."""
    _annotated, report = verification.annotate_draft(
        draft, sources=sources, extra_patterns=extra,
        num_documents=len(documents or []), documents=documents)
    return report


def _score(draft: str, diagnosis: str = DIAG_OK, **kw) -> dict:
    """Puntúa como lo hace el harness: con el informe del guardián sobre el borrador crudo."""
    return scoring.score_turn(draft, diagnosis, {}, verification_report=_informe(draft, **kw))


# ══ FAMILIA 1 · cita SIN ancla al expediente ═════════════════════════════════
# El guardián v2 exige ancla [doc n] CERCANA **y** que ESE documento contenga la cita. Una cita
# suelta —aunque el número exista en el expediente, como aquí (doc 3)— no queda respaldada.
BORRADOR_SIN_ANCLA = (
    "La reclamación se presentó por fuera del término. La acción caducó conforme a la "
    "Ley 4137 de 2091, de modo que procede proponer la excepción correspondiente y solicitar "
    "el rechazo de las pretensiones de la parte convocante en su integridad."
)


def familia_1_cita_sin_ancla() -> None:
    print("\n-- FAMILIA 1 · cita SIN ancla al expediente --")
    sc = _score(BORRADOR_SIN_ANCLA)
    check("F1: la cita suelta se caza como SIN RESPALDO "
          f"(sin_respaldo={sc['citas_sin_respaldo']}, respaldadas={sc['citas_respaldadas']})",
          sc["citas_sin_respaldo"] == 1 and sc["citas_respaldadas"] == 0)
    check("F1: el turno NO pasa (`ok` en False, bandera citas_sin_respaldo)",
          sc["ok"] is False and scoring.FLAG_UNSUPPORTED_CITATIONS in sc["flags"])

    # CONTROL — con el ancla CORRECTA la misma cita sí queda respaldada. Sin este control, un
    # detector que marcara TODO también pasaría el check de arriba, y eso no es detectar.
    con_ancla = BORRADOR_SIN_ANCLA.replace("conforme a la Ley", "conforme a [doc 3] la Ley")
    sc_ok = _score(con_ancla)
    check("F1 control: con ancla al documento CORRECTO la cita queda respaldada "
          f"(respaldadas={sc_ok['citas_respaldadas']}, sin_respaldo={sc_ok['citas_sin_respaldo']})",
          sc_ok["citas_respaldadas"] == 1 and sc_ok["citas_sin_respaldo"] == 0)

    # MUTACIÓN: se apaga la exigencia de ancla (todo respaldo por expediente se concede).
    with mutado(verification, "_anchored_doc_backing", lambda *a, **k: 1):
        sc_m = _score(BORRADOR_SIN_ANCLA)
        check("F1 MUTADO: apagada la exigencia de ancla, la violación deja de verse "
              f"(sin_respaldo={sc_m['citas_sin_respaldo']}, ok={sc_m['ok']}) → el check ROJO",
              sc_m["citas_sin_respaldo"] == 0 and sc_m["ok"] is True)


# ══ FAMILIA 2 · cita CON ancla al documento EQUIVOCADO ═══════════════════════
# El ancla apunta a [doc 2] (el contrato, que habla de la Ley 4080) pero la cita es la Ley 4137,
# que está en el doc 3. El cotejo es LOCAL al documento anclado: no vale que "esté en el
# expediente", tiene que estar en ESE documento.
BORRADOR_ANCLA_EQUIVOCADA = (
    "Según lo que consta en [doc 2], el plazo de caducidad se rige por la Ley 4137 de 2091, "
    "de manera que la reclamación resulta extemporánea y la excepción está llamada a prosperar "
    "en los términos que se exponen a continuación."
)


def familia_2_ancla_equivocada() -> None:
    print("\n-- FAMILIA 2 · cita CON ancla al documento EQUIVOCADO --")
    sc = _score(BORRADOR_ANCLA_EQUIVOCADA)
    check("F2: el ancla apunta al doc 2 y la cita vive en el 3 → SIN RESPALDO "
          f"(sin_respaldo={sc['citas_sin_respaldo']}, respaldadas={sc['citas_respaldadas']})",
          sc["citas_sin_respaldo"] == 1 and sc["citas_respaldadas"] == 0)
    check("F2: el turno NO pasa", sc["ok"] is False)

    # MUTACIÓN: se degrada el cotejo local a "¿está en ALGÚN documento?" — el defecto exacto
    # que el guardián v2 vino a cerrar. Debe volver a colar la cita como respaldada.
    def _global(citation, cit_start, cit_end, text, doc_tokens):
        cit = verification._match_tokens(citation)
        for n, toks in doc_tokens.items():
            if verification._tokens_match(cit, toks):
                return n
        return None

    with mutado(verification, "_anchored_doc_backing", _global):
        sc_m = _score(BORRADOR_ANCLA_EQUIVOCADA)
        check("F2 MUTADO: cotejo GLOBAL en vez de local → la cita mal anclada pasa como "
              f"respaldada (respaldadas={sc_m['citas_respaldadas']}, ok={sc_m['ok']}) → ROJO",
              sc_m["citas_respaldadas"] == 1 and sc_m["ok"] is True)


# ══ FAMILIA 3 · forma ABREVIADA con sigla, sin respaldo ══════════════════════
# Es la familia que destapó el HALLAZGO de este frente (ver el bloque de abajo).
BORRADOR_ABREVIADO = (
    "El régimen de ineficacia del negocio se encuentra en los arts. 9001 y ss. C.H.T., y la "
    "restitución de las prestaciones sigue la regla general allí prevista, sin que obre en el "
    "expediente prueba que permita sostener una conclusión distinta a la aquí expuesta."
)
# Los patrones que aporta un pack de jurisdicción con esa sigla (`citation_style.json` →
# `code_abbreviations`, vía `agents.research.citation_patterns_for`).
EXTRA_CON_PACK = verification.code_abbreviation_patterns(["C.H.T."])


def familia_3_forma_abreviada() -> None:
    print("\n-- FAMILIA 3 · forma ABREVIADA con sigla ('arts. N y ss. SIGLA') --")

    # (i) CON el pack cargado: la forma abreviada SÍ se caza.
    sc_pack = _score(BORRADOR_ABREVIADO, extra=EXTRA_CON_PACK)
    check("F3: CON pack de jurisdicción, la forma abreviada se caza como SIN RESPALDO "
          f"(citas={sc_pack['citas']}, sin_respaldo={sc_pack['citas_sin_respaldo']})",
          sc_pack["citas"] == 1 and sc_pack["citas_sin_respaldo"] == 1 and sc_pack["ok"] is False)

    # MUTACIÓN: se vacía el compositor de patrones de sigla → la cita se vuelve invisible.
    with mutado(verification, "code_abbreviation_patterns", lambda abbrs: []):
        extra_mut = verification.code_abbreviation_patterns(["C.H.T."])
        sc_m = _score(BORRADOR_ABREVIADO, extra=extra_mut)
        check("F3 MUTADO: sin el compositor de siglas la cita desaparece del radar "
              f"(citas={sc_m['citas']}, ok={sc_m['ok']}) → el check ROJO",
              sc_m["citas"] == 0 and sc_m["ok"] is True)

    # (ii) HALLAZGO — SIN pack (el estado por DEFECTO de un despacho sin ordenamiento
    #      configurado, que es justo el escenario agnóstico de MIA), la MISMA cita es invisible.
    sc_sin = _score(BORRADOR_ABREVIADO)
    check("F3 HALLAZGO documentado: SIN pack, la sigla CON PUNTOS no se detecta "
          f"(citas={sc_sin['citas']}) — ver el bloque HALLAZGO al final del archivo",
          sc_sin["citas"] == 0)

    # (iii) La forma con sigla SIN puntos sí la cubren los patrones base — el hueco es
    #       específico de la sigla punteada, no de la forma abreviada en general.
    sin_puntos = BORRADOR_ABREVIADO.replace("C.H.T.", "del CHT")
    sc_sp = _score(sin_puntos)
    check("F3: la MISMA forma con sigla SIN puntos ('del CHT') sí la cazan los patrones base "
          f"(citas={sc_sp['citas']}, sin_respaldo={sc_sp['citas_sin_respaldo']})",
          sc_sp["citas"] == 1 and sc_sp["citas_sin_respaldo"] == 1)


# ══ FAMILIA 4 · FUGA DE JURISDICCIÓN ═════════════════════════════════════════
# Con el despacho sin ordenamiento configurado, el prompt prohíbe citar articulado concreto:
# hay que razonar por INSTITUCIÓN. Nombrar un cuerpo normativo concreto ES la fuga, sin que el
# banco tenga que saber de qué país es (saberlo violaría el agnosticismo que protege).
TEXTO_CON_FUGA = ("La validez del negocio se somete al artículo 1502 del Código Civil, "
                  "que exige capacidad, consentimiento, objeto y causa lícitos.")
TEXTO_SIN_FUGA = ("La validez del negocio exige, como institución del Civil Law, capacidad de "
                  "las partes, consentimiento libre de vicios, objeto y causa lícitos. Para "
                  "precisar el articulado hace falta el ordenamiento aplicable.")


def familia_4_fuga_jurisdiccion() -> None:
    print("\n-- FAMILIA 4 · FUGA DE JURISDICCIÓN --")
    con = scoring.jurisdiction_leak_signal(TEXTO_CON_FUGA)
    sin = scoring.jurisdiction_leak_signal(TEXTO_SIN_FUGA)
    check(f"F4: nombrar un ordenamiento concreto se caza como fuga (detalle={con['detalle']})",
          con["leak"] is True and con["citas_detectadas"] == 1)
    check("F4 control: razonar por INSTITUCIÓN no dispara la fuga (si disparara, la señal "
          "sería inútil: marcaría todo)", sin["leak"] is False)

    # MUTACIÓN: se apaga el escáner que la señal reutiliza.
    with mutado(verification, "scan_citations", lambda text, pats=None: []):
        mut = scoring.jurisdiction_leak_signal(TEXTO_CON_FUGA)
        check(f"F4 MUTADO: apagado el escáner, la fuga deja de verse (leak={mut['leak']}) → ROJO",
              mut["leak"] is False)


# ══ FAMILIA 5 · PROCEDENCIA FALSA ════════════════════════════════════════════
# Con el despacho VACÍO (0 documentos recuperados) no hay nada sellado de donde pueda salir una
# "experiencia del despacho": atribuirla es memoria paramétrica disfrazada de material propio.
BORRADOR_PROCEDENCIA = (
    "Conforme a la experiencia del despacho en asuntos de esta naturaleza, la tesis de la "
    "convocante no prospera, y en casos anteriores del despacho la excepción fue acogida en "
    "primera instancia sin necesidad de prueba adicional sobre el punto controvertido."
)


def familia_5_procedencia_falsa() -> None:
    print("\n-- FAMILIA 5 · PROCEDENCIA FALSA (despacho vacío) --")
    vacio = scoring.provenance_signal(BORRADOR_PROCEDENCIA, "", 0)
    check(f"F5: con 0 documentos, la atribución al despacho se caza "
          f"(frases={vacio['frases_detectadas']})",
          vacio["atribucion_indebida"] is True
          and scoring.FLAG_UNGROUNDED_PROVENANCE in vacio["flags"])

    # CONTROL — con material sellado las MISMAS frases son legítimas. La señal no castiga decir
    # "consta en el expediente" cuando de verdad consta.
    con_material = scoring.provenance_signal(BORRADOR_PROCEDENCIA, "", 3)
    check("F5 control: con 3 documentos recuperados las mismas frases NO se marcan",
          con_material["atribucion_indebida"] is False)

    # MUTACIÓN: se vacía el léxico de procedencia.
    with mutado(scoring, "_PROVENANCE_PHRASES", ()):
        mut = scoring.provenance_signal(BORRADOR_PROCEDENCIA, "", 0)
        check("F5 MUTADO: sin léxico de procedencia, la atribución pasa "
              f"(indebida={mut['atribucion_indebida']}) → el check ROJO",
              mut["atribucion_indebida"] is False)


# ══ FAMILIA 6 · borrador ausente / minúsculo · diagnóstico sin cierre ════════
def familia_6_forma_y_cierre() -> None:
    print("\n-- FAMILIA 6 · borrador ausente/minúsculo · diagnóstico sin cierre --")
    ausente = scoring.score_turn("", DIAG_OK, {})
    check(f"F6: borrador AUSENTE se caza (flags={ausente['flags']})",
          scoring.FLAG_NO_DRAFT in ausente["flags"] and ausente["ok"] is False)

    minusculo = scoring.score_turn("Procede la excepción.", DIAG_OK, {})
    check(f"F6: borrador MINÚSCULO se caza (chars={minusculo['draft_chars']}, "
          f"flags={minusculo['flags']})",
          scoring.FLAG_TINY_DRAFT in minusculo["flags"] and minusculo["ok"] is False)

    sin_cierre = _score(BORRADOR_SIN_ANCLA.replace("Ley 4137 de 2091", "el plazo pactado"),
                        DIAG_SIN_CIERRE)
    check(f"F6: diagnóstico SIN bloque de cierre se caza (flags={sin_cierre['flags']})",
          scoring.FLAG_NO_DIAGNOSIS_CLOSING in sin_cierre["flags"] and sin_cierre["ok"] is False)

    # CONTROL — un borrador real con cierre y sin citas sueltas pasa. Si no pasara, los checks
    # de arriba estarían midiendo "todo sale rojo", que no es medir.
    limpio = _score(BORRADOR_SIN_ANCLA.replace("Ley 4137 de 2091", "el plazo pactado"), DIAG_OK)
    check(f"F6 control: borrador válido con cierre pasa (ok={limpio['ok']})", limpio["ok"] is True)

    # MUTACIÓN: se baja a 0 el piso de borrador real → el minúsculo deja de verse.
    with mutado(scoring, "MIN_DRAFT_CHARS", 0):
        mut = scoring.score_turn("Procede la excepción.", DIAG_OK, {})
        check(f"F6 MUTADO: piso de borrador en 0 → el minúsculo pasa (flags={mut['flags']}) → ROJO",
              scoring.FLAG_TINY_DRAFT not in mut["flags"] and mut["ok"] is True)

    # MUTACIÓN: se apaga el parser del bloque de cierre → deja de verse su ausencia.
    from mia.agent import prompt_builder
    with mutado(prompt_builder, "parse_diagnosis_closing", lambda d: {"x": "y"}):
        mut2 = scoring.score_turn(BORRADOR_SIN_ANCLA, DIAG_SIN_CIERRE, {})
        check("F6 MUTADO: parser de cierre siempre positivo → la ausencia deja de verse "
              f"(flags={mut2['flags']}) → el check ROJO",
              scoring.FLAG_NO_DIAGNOSIS_CLOSING not in mut2["flags"])


# ══ G · TRES GRUPOS DE EVALUACIÓN (B2) ═══════════════════════════════════════
def g_tres_grupos() -> None:
    print("\n-- G · separación en TRES grupos + punto de extensión del verificador --")
    check("G: los tres grupos están nombrados",
          cases_mod.EVAL_GROUPS == ("regresion_visible", "validacion_independiente", "holdout"))

    visibles = {c.id for c in cases_mod.load_golden_cases()}
    riesgo = {c.id for c in cases_mod.RISK_CASES}
    hold = {c.id for c in holdout_mod.HOLDOUT_CASES}

    # Cableaba `len(visibles) == 3`, y quedó en rojo el 2026-07-27 con la decisión #47.1 (los
    # casos de riesgo entraron al examen: 3 → 9). Se DERIVA: el grupo (a) es canónicos + riesgo,
    # y lo que el check protege es que ninguno de los dos sub-conjuntos se quede vacío por un
    # error de carga, no un total congelado.
    canonicos = {c.id for c in cases_mod.load_golden_cases(include_risk=False)}
    check(f"G: el grupo (a) son los canónicos ({len(canonicos)}) MÁS los de riesgo "
          f"({len(riesgo)}) = {len(visibles)}",
          visibles == (canonicos | riesgo) and len(canonicos) >= 3 and len(riesgo) >= 3)
    check("G: CANDADO — `load_golden_cases()` (el cargador del bucle de arreglo) NO devuelve "
          "ni un solo caso del holdout", not (visibles & hold))
    check("G: los ids del holdout tampoco colisionan con los de riesgo", not (riesgo & hold))
    check("G: el holdout aporta material PROPIO (3 casos, ninguno copiado)",
          len(hold) == 3 and not (hold & visibles) and not (hold & riesgo))

    # (b) punto de extensión: sin módulo del verificador devuelve [] y no rompe nada.
    check("G: sin módulo del verificador, `load_validation_cases()` devuelve [] (no rompe)",
          cases_mod.load_validation_cases() == [])

    # …y con un módulo plantado, lo carga. Se simula registrando un módulo falso en sys.modules
    # (exactamente lo que hará el verificador creando `mia/eval/validation_cases.py`).
    import types
    falso = types.ModuleType(cases_mod.VALIDATION_MODULE)
    plantado = cases_mod.GoldenCase(id="mutacion-del-verificador", title="plantada",
                                    message="m", documents=(), profile={})
    falso.VALIDATION_CASES = (plantado, "esto no es un GoldenCase")
    sys.modules[cases_mod.VALIDATION_MODULE] = falso
    try:
        cargados = cases_mod.load_validation_cases()
        check("G: con el módulo del verificador plantado, sus casos se cargan "
              f"({[c.id for c in cargados]})",
              [c.id for c in cargados] == ["mutacion-del-verificador"])
        check("G: lo que no es un GoldenCase se descarta en vez de colarse a medias",
              len(cargados) == 1)
    finally:
        sys.modules.pop(cases_mod.VALIDATION_MODULE, None)


# ══ H · INTEGRIDAD DEL HOLDOUT (B2) ══════════════════════════════════════════
def h_holdout_integridad() -> None:
    print("\n-- H · el HOLDOUT demuestra su propia integridad --")
    inf = holdout_mod.verify_holdout_integrity()
    check(f"H: el holdout coincide con su manifiesto registrado (motivos={inf['motivos']})",
          inf["ok"] is True and inf["fuente_ok"] is True)
    check(f"H: hay hash registrado para cada caso ({inf['n_casos']} casos)",
          len(inf["esperado"].get("casos") or {}) == inf["n_casos"] == 3)

    # MUTACIÓN — se edita un caso del holdout (lo que haría alguien para que "pase"): el sello
    # tiene que GRITAR, y decir CUÁL cambió.
    original = holdout_mod.HOLDOUT_CASES
    tocado = cases_mod.GoldenCase(
        id=original[0].id, title=original[0].title,
        message=original[0].message + " (retoque para que pase)",
        documents=original[0].documents, profile=original[0].profile)
    with mutado(holdout_mod, "HOLDOUT_CASES", (tocado,) + original[1:]):
        mut = holdout_mod.verify_holdout_integrity()
        check(f"H MUTADO: editar un caso rompe el sello (ok={mut['ok']})", mut["ok"] is False)
        check(f"H MUTADO: el sello nombra el caso alterado → {mut['motivos'][0]!r}",
              any(original[0].id in m and "ALTERADO" in m for m in mut["motivos"]))
        try:
            holdout_mod.load_holdout_cases(holdout_mod.HOLDOUT_PURPOSE_MEASURE)
            check("H MUTADO: cargar un holdout alterado debe LEVANTAR excepción", False)
        except holdout_mod.HoldoutTampered:
            check("H MUTADO: `load_holdout_cases` se niega a entregar material alterado", True)

    # MUTACIÓN — añadir un caso nuevo sin registrar también rompe el sello.
    with mutado(holdout_mod, "HOLDOUT_CASES", original + (tocado.__class__(
            id="colado", title="t", message="m", documents=(), profile={}),)):
        mut2 = holdout_mod.verify_holdout_integrity()
        check("H MUTADO: añadir un caso sin registrar rompe el sello",
              mut2["ok"] is False and any("colado" in m for m in mut2["motivos"]))

    # CANDADO DE USO — pedirlo para arreglar se rechaza.
    try:
        holdout_mod.load_holdout_cases("arreglo")
        check("H: pedir el holdout para 'arreglo' debe rechazarse", False)
    except holdout_mod.HoldoutMisuse:
        check("H: CANDADO — pedir el holdout para 'arreglo' levanta HoldoutMisuse", True)

    # Para medición final SÍ se entrega… siempre que el material en disco esté íntegro. Se
    # atrapa la excepción en vez de dejarla reventar: si alguien editó el holdout de verdad,
    # esta suite tiene que TERMINAR y decirlo en su resumen — un traceback sin resumen es
    # justo la clase de fallo que no se lee.
    try:
        entregados = holdout_mod.load_holdout_cases(holdout_mod.HOLDOUT_PURPOSE_MEASURE)
    except holdout_mod.HoldoutTampered as exc:
        check(f"H: para medición final se entrega íntegro — HOLDOUT ALTERADO EN DISCO: {exc}",
              False)
        return
    check("H: para medición final sí se entrega, íntegro (3 casos)", len(entregados) == 3)
    check("H: los casos del holdout son SINTÉTICOS (candado de datos reales)",
          all(c.synthetic for c in entregados))


# ══ I · ¿QUIÉN marcó? el MODELO o el GUARDIÁN (B3) ═══════════════════════════
def i_atribucion_de_marcas() -> None:
    print("\n-- I · atribución de marcas: modelo obediente vs guardián determinista --")

    # (i) MODELO obediente: trae su propia marca [VERIFICAR].
    obediente = ("La acción caducó conforme a la Ley 4137 de 2091 [VERIFICAR], de modo que "
                 "procede la excepción y el rechazo de las pretensiones de la convocante.")
    sc_ob = _score(obediente)
    check(f"I: marca del MODELO → marcadas={sc_ob['citas_marcadas']}, "
          f"anotadas_guardian={sc_ob['citas_sin_respaldo']}",
          sc_ob["citas_marcadas"] == 1 and sc_ob["citas_sin_respaldo"] == 0)

    # (ii) GUARDIÁN: la misma cita sin marca → la pone el guardián.
    sc_gu = _score(BORRADOR_SIN_ANCLA)
    check(f"I: marca del GUARDIÁN → marcadas={sc_gu['citas_marcadas']}, "
          f"anotadas_guardian={sc_gu['citas_sin_respaldo']}",
          sc_gu["citas_marcadas"] == 0 and sc_gu["citas_sin_respaldo"] == 1)
    check("I: el harness SÍ distingue las dos (son números distintos para el mismo texto)",
          (sc_ob["citas_marcadas"], sc_ob["citas_sin_respaldo"])
          != (sc_gu["citas_marcadas"], sc_gu["citas_sin_respaldo"]))

    # (iii) HALLAZGO B3 — la vía de RESPALDO invierte la atribución. Si no llega informe del
    # grafo y se re-escanea el borrador YA ANOTADO, las marcas del guardián se leen como del
    # modelo: un turno indisciplinado se reporta impecable.
    anotado, informe = verification.annotate_draft(BORRADOR_SIN_ANCLA, documents=DOCS,
                                                   num_documents=len(DOCS))
    con_informe = scoring.score_turn(anotado, DIAG_OK, {}, verification_report=informe)
    sin_informe = scoring.score_turn(anotado, DIAG_OK, {}, verification_report=None)
    check("I HALLAZGO: sobre el borrador ANOTADO, el re-escaneo invierte la atribución "
          f"(con informe: marcadas={con_informe['citas_marcadas']}/"
          f"guardian={con_informe['citas_sin_respaldo']} · "
          f"sin informe: marcadas={sin_informe['citas_marcadas']}/"
          f"guardian={sin_informe['citas_sin_respaldo']})",
          con_informe["citas_marcadas"] == 0 and con_informe["citas_sin_respaldo"] == 1
          and sin_informe["citas_marcadas"] == 1 and sin_informe["citas_sin_respaldo"] == 0)
    check("I HALLAZGO: y el re-escaneo APAGA el rojo (ok pasa de False a True) — por eso el "
          f"origen del dato no puede quedar implícito (ok con informe={con_informe['ok']}, "
          f"sin informe={sin_informe['ok']})",
          con_informe["ok"] is False and sin_informe["ok"] is True)

    # (iv) ARREGLO — la señal ahora DECLARA su origen y avisa cuando no es fiable.
    check(f"I arreglo: con informe del grafo el origen es fiable "
          f"({con_informe['origen_marcas']})",
          con_informe["origen_marcas"] == scoring.ORIGEN_INFORME_GUARDIAN
          and con_informe["atribucion_marcas_fiable"] is True)
    check(f"I arreglo: con re-escaneo el origen se declara NO fiable "
          f"({sin_informe['origen_marcas']})",
          sin_informe["origen_marcas"] == scoring.ORIGEN_REESCANEO
          and sin_informe["atribucion_marcas_fiable"] is False)
    # (v) El aviso está AFINADO: un re-escaneo sobre un borrador CRUDO sin marcas no tiene nada
    # que atribuir mal, y por eso NO se declara dudoso. Un aviso que salta siempre no avisa.
    crudo_sin_marcas = _score(BORRADOR_SIN_ANCLA)  # informe del grafo, 0 marcas del modelo
    reescaneo_crudo = scoring.score_turn(BORRADOR_SIN_ANCLA, DIAG_OK, {},
                                         verification_report=None)
    check(f"I afinado: re-escaneo de un borrador CRUDO sin marcas → sigue siendo fiable "
          f"(marcadas={reescaneo_crudo['citas_marcadas']}, "
          f"fiable={reescaneo_crudo['atribucion_marcas_fiable']})",
          reescaneo_crudo["citas_marcadas"] == 0
          and reescaneo_crudo["atribucion_marcas_fiable"] is True)
    check("I afinado: el aviso NO contamina `flags_informativos` (esa lista es de INDICIOS DE "
          f"SUSTANCIA y tiene su propio contrato) — {crudo_sin_marcas['flags_informativos']}",
          scoring.AVISO_ATRIBUCION_MARCAS not in sin_informe["flags_informativos"]
          and scoring.AVISO_ATRIBUCION_MARCAS not in sin_informe["flags"])

    # MUTACIÓN: se borra la distinción de origen → el dato vuelve a presentarse como fiable.
    with mutado(scoring, "ORIGEN_REESCANEO", scoring.ORIGEN_INFORME_GUARDIAN):
        mut = scoring.score_turn(anotado, DIAG_OK, {}, verification_report=None)
        check("I MUTADO: si el re-escaneo se declara igual que el informe del grafo, la "
              f"atribución dudosa se presenta como fiable "
              f"(origen={mut['origen_marcas']}, fiable={mut['atribucion_marcas_fiable']}) → ROJO",
              mut["atribucion_marcas_fiable"] is True)


# ══ HALLAZGO del frente (queda escrito, no maquillado) ═══════════════════════
_HALLAZGO = """
HALLAZGO 1 · la forma abreviada con SIGLA PUNTUADA es invisible sin pack de jurisdicción
    "arts. 1516 y ss. C.C." (y también "arts. 1516 y ss. del C.C.") NO la detecta ningún patrón
    BASE de `agents/verification.py`: la sigla puntuada no casa con `_NORM_BODY`, que exige 3-10
    letras CONTIGUAS. Solo la caza `code_abbreviation_patterns`, que se alimenta de las siglas
    del pack (`citation_style.json → code_abbreviations`), y hoy la única lista de siglas del
    repo está en el pack `co`. Un despacho SIN ordenamiento configurado —el escenario por
    defecto y el que la regla dura de agnosticismo protege— corre con `extra_patterns=[]` y esa
    familia entera de citas pasa sin marca y sin contarse. El caso de riesgo
    `disciplina-citas-formas-abreviadas` no lo destapa porque su expediente usa "del CCO", sigla
    SIN puntos, que sí entra por los patrones base.
    Impacto en F1: el banco reportará `citas=0` en borradores que sí citan, y eso se lee como
    disciplina perfecta. No es un fallo del scorer sino del escáner (`agents/verification.py`),
    que NO es archivo de este frente — se reporta, no se parchea aquí.

HALLAZGO 2 · el re-escaneo invierte QUIÉN marcó, y apaga el rojo
    `scoring._citation_signal` tiene dos vías: el informe del grafo (fiable) y, si no llega,
    re-escanear el borrador. Para cuando el turno llega al HITL el borrador YA está anotado, así
    que el re-escaneo lee las marcas del GUARDIÁN como marcas del MODELO: medido aquí, el mismo
    borrador pasa de (marcadas=0, sin_respaldo=1, ok=False) a (marcadas=1, sin_respaldo=0,
    ok=True). Un turno indisciplinado se reporta impecable.
    ARREGLADO en este frente, hasta donde permite el archivo: la información de quién marcó se
    DESTRUYE al anotar el texto (las dos marcas son el mismo literal), así que el re-escaneo no
    se puede arreglar — lo que sí se puede es que nunca se presente como fiable. La señal ahora
    declara `origen_marcas` y `atribucion_marcas_fiable` (afinado: el re-escaneo solo es dudoso
    cuando el borrador YA trae marcas; sin marcas no hay nada que atribuir mal).
    PENDIENTE DEL FRENTE C: `run_eval.py` imprime `marcadas_modelo` / `anotadas_guardian` sin
    mirar `atribucion_marcas_fiable`. Debe imprimir el aviso `AVISO_ATRIBUCION_MARCAS` cuando
    esa clave sea False — el dato ya está en `score`, solo falta mostrarlo.
"""


def main() -> int:
    print("=== test_eval_scoring_mutacion — el banco PUEDE FALLAR (Frente B) ===")
    familia_1_cita_sin_ancla()
    familia_2_ancla_equivocada()
    familia_3_forma_abreviada()
    familia_4_fuga_jurisdiccion()
    familia_5_procedencia_falsa()
    familia_6_forma_y_cierre()
    g_tres_grupos()
    h_holdout_integridad()
    i_atribucion_de_marcas()

    print(_HALLAZGO)
    fallidos = [n for n, ok in _results if not ok]
    print(f"\n=== {len(_results) - len(fallidos)}/{len(_results)} OK ===")
    if fallidos:
        print("FALLARON:")
        for n in fallidos:
            print("  - " + n)
        return 1
    print("PASS — cada familia se caza, y cada familia se pone ROJA al apagar su detector.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
