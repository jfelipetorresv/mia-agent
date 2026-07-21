"""
Mia · test_eval_substance.py — gate de los INDICIOS DE SUSTANCIA del scorer (eval/scoring.py).

El hallazgo que ataca: el examen de calidad medía citas + un booleano de cierre + 200 chars.
Un ESQUELETO (títulos y frases sueltas, citas marcadas, cero desarrollo) sacaba `ok: True`, así
que ninguna mejora argumental era visible y no había señal de regresión.

Cubre (todo OFFLINE y puro — sin DB, sin red, sin LLM-juez):
  A. DISCRIMINACIÓN: esqueleto vs escrito desarrollado (la prueba de que la señal sirve).
  B. FALSOS POSITIVOS: corto pero bueno (no es esqueleto) · largo y vacío (relleno).
  C. AGNOSTICISMO DE JURISDICCIÓN: el mismo escrito con normas españolas y colombianas da el
     MISMO resultado estructural (regla dura: MIA no es de ningún país).
  D. NO REGRESIÓN DEL CONTRATO: los indicios son INFORMATIVOS — nunca tocan `flags` ni `ok`,
     así que un caso de oro ya confirmado NO se vuelve rojo por esta rúbrica nueva.
  E. Unidad: partición en bloques, títulos por forma, cobertura vs conteo, pureza.

Salida: exit 0 = PASS · exit 1 = FAIL.

    .venv\\Scripts\\python.exe execution\\test_eval_substance.py
"""
from __future__ import annotations

import sys
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
from mia.eval import score_turn, substance_signal  # noqa: E402
from mia.eval import scoring                       # noqa: E402

_results: list[tuple[str, bool]] = []


def check(name: str, ok) -> None:
    _results.append((name, bool(ok)))
    print(("  [OK]   " if ok else "  [FAIL] ") + name)


_CLOSING = (f"{DIAGNOSIS_CLOSING_HEADER}\nProblema jurídico: la caducidad de la acción.\n"
            f"Normas y fuentes: Ley 1437 de 2011 [VERIFICAR]\n"
            f"Riesgo y recomendación: proponer la excepción.\n{DIAGNOSIS_CLOSING_FOOTER}")
_DIAG = "DIAGNÓSTICO: el eje es la caducidad.\n\n" + _CLOSING


# ── Corpus de prueba: prosa jurídica real de los dos tipos ────────────────────
# Las citas van con [VERIFICAR] a propósito: así los DOS borradores salen `ok: True` bajo la
# rúbrica vieja (citas en regla + cierre + >200 chars) y la única diferencia medible entre
# ellos es la sustancia. Eso es exactamente el hallazgo que este gate documenta.

# ESQUELETO: el índice de un escrito. Títulos correctos, cita marcada, cero desarrollo.
SKELETON = """CONTESTACIÓN DE LA DEMANDA

I. Excepción de caducidad

Se propone la excepción de caducidad conforme a la Ley 1437 de 2011 [VERIFICAR].

II. Falta de legitimación en la causa por pasiva

La entidad demandada no es la llamada a responder.

III. Inexistencia de la falla del servicio

No se acreditó la falla del servicio alegada.

IV. Tacha del dictamen pericial

Se tacha el dictamen por falta de fundamentación.

V. Petición

Se solicita denegar las pretensiones de la demanda.
"""

# DESARROLLADO: los mismos ejes, argumentados. Cada párrafo ancla en el expediente y trae la
# fuente normativa concreta.
DEVELOPED = """CONTESTACIÓN DE LA DEMANDA

I. Excepción de caducidad

La acción caducó antes de que se radicara la demanda. El daño cuya reparación se reclama se \
consolidó el 3 de marzo de 2019, fecha que la propia parte actora reconoce en el hecho quinto \
de su escrito [doc 1], y la demanda solo se presentó el 10 de septiembre de 2021, dos años y \
seis meses después. El artículo 164 de la Ley 1437 de 2011 [VERIFICAR] fija un término de dos \
años contados desde el día siguiente al hecho dañoso, de modo que el plazo se agotó el 4 de \
marzo de 2021 y la demanda es extemporánea.

II. Falta de legitimación en la causa por pasiva

La entidad demandada no administraba la obra de la que se predica el daño. El acta de entrega \
que obra en el expediente [doc 2] acredita que la operación se trasladó al contratista el 1 de \
febrero de 2019, un mes antes del hecho, y que desde entonces la entidad no conservó facultad \
alguna de dirección. El artículo 140 de la Ley 1437 de 2011 [VERIFICAR] exige demandar a quien \
causó el daño, y la actora no dirigió pretensión alguna contra el contratista.

III. Inexistencia de la falla del servicio

Aun superadas las excepciones anteriores, no hay prueba de la falla. La actora sustenta el \
incumplimiento del deber de mantenimiento en un solo informe interno [doc 3] que se limita a \
describir el estado de la vía, sin pronunciarse sobre su causa ni sobre el estándar exigible. \
El artículo 167 de la Ley 1564 de 2012 [VERIFICAR] radica en quien alega la carga de probar el \
supuesto de hecho, y esa carga no se descargó con un documento que nada dice del nexo causal.
"""


def a_discrimination() -> None:
    print("\n-- A · discriminación: esqueleto vs desarrollado --")

    sk = substance_signal(SKELETON)
    dv = substance_signal(DEVELOPED)
    print(f"     esqueleto  : {sk}")
    print(f"     desarrollado: {dv}")

    # El hallazgo, documentado como prueba: bajo la rúbrica vieja el esqueleto pasa limpio.
    s_sk = score_turn(SKELETON, _DIAG, {})
    check("A1 · el ESQUELETO sigue sacando ok:True bajo la rúbrica vieja (el hallazgo)",
          s_sk["ok"] is True and not s_sk["flags"])
    check("A2 · ...pero ahora la señal nueva lo delata (flags_informativos no vacío)",
          scoring.INFO_FLAG_SKELETON in s_sk["flags_informativos"])

    check("A3 · esqueleto: 0 párrafos desarrollados", sk["parrafos_sustantivos"] == 0)
    check("A4 · desarrollado: 3 párrafos desarrollados", dv["parrafos_sustantivos"] == 3)
    check("A5 · densidad de desarrollo: esqueleto 0.0 vs desarrollado > 0.8",
          sk["densidad_desarrollo"] == 0.0 and dv["densidad_desarrollo"] > 0.8)
    check("A6 · la densidad DISCRIMINA (desarrollado supera al esqueleto por >0.5)",
          dv["densidad_desarrollo"] - sk["densidad_desarrollo"] > 0.5)
    check("A7 · desarrollado: todos los párrafos anclan al expediente ([doc n])",
          dv["anclaje_expediente_ratio"] == 1.0 and dv["parrafos_con_anclaje"] == 3)
    check("A8 · desarrollado: todos los párrafos traen norma concreta",
          dv["fundamentacion_normativa_ratio"] == 1.0 and dv["parrafos_con_norma"] == 3)
    check("A9 · esqueleto: detecta sus títulos (≥4) — es un índice, no un escrito",
          sk["titulos"] >= 4)

    s_dv = score_turn(DEVELOPED, _DIAG, {})
    check("A10 · el DESARROLLADO no dispara ninguna bandera informativa",
          s_dv["flags_informativos"] == [] and s_dv["ok"] is True)


def b_false_positives() -> None:
    print("\n-- B · falsos positivos: corto-pero-bueno y largo-y-vacío --")

    # Corto pero bueno: UN argumento, bien hecho. Debe pasar limpio (la señal mide desarrollo,
    # no extensión: penalizar lo breve sería premiar el relleno).
    short_good = """Excepción de caducidad

La acción caducó. El daño se consolidó el 3 de marzo de 2019 según el hecho quinto de la \
demanda [doc 1], y esta se radicó el 10 de septiembre de 2021. El artículo 164 de la Ley 1437 \
de 2011 [VERIFICAR] concede dos años desde el día siguiente al hecho, término que venció el 4 \
de marzo de 2021: la demanda es extemporánea y debe rechazarse de plano.
"""
    sg = substance_signal(short_good)
    s_sg = score_turn(short_good, _DIAG, {})
    print(f"     corto-bueno : {sg}")
    check("B1 · corto pero bueno: NO se marca como esqueleto",
          scoring.INFO_FLAG_SKELETON not in s_sg["flags_informativos"])
    check("B2 · corto pero bueno: sin banderas informativas y ok:True",
          s_sg["flags_informativos"] == [] and s_sg["ok"] is True)
    check("B3 · corto pero bueno: 1 párrafo desarrollado, anclado y fundamentado",
          sg["parrafos_sustantivos"] == 1 and sg["anclaje_expediente_ratio"] == 1.0
          and sg["fundamentacion_normativa_ratio"] == 1.0)

    # Largo y vacío: relleno abundante, sin expediente ni norma concreta — solo apelaciones
    # vagas ("las normas aplicables", "reiterada jurisprudencia"), que el escáner NO cuenta.
    long_empty = """CONTESTACIÓN DE LA DEMANDA

Nos permitimos manifestar, con el debido respeto y en el término oportunamente concedido, que \
la demanda instaurada no está llamada a prosperar por las razones que se expondrán a lo largo \
del presente escrito, las cuales encuentran pleno respaldo en las normas aplicables y en la \
reiterada jurisprudencia sobre la materia, tal como se explicará en su debida oportunidad \
procesal ante el despacho de conocimiento.

Debe advertirse que la parte actora no ha logrado desvirtuar en modo alguno la presunción que \
ampara la actuación de nuestra representada, cuyo proceder se ajustó en todo momento a los \
principios que rigen la función administrativa y a los criterios que la doctrina más autorizada \
ha decantado, sin que exista en el plenario elemento alguno que permita arribar a una \
conclusión distinta de la aquí sostenida.

Por lo anterior, y en atención a todo lo expuesto de manera precedente, resulta forzoso concluir \
que las pretensiones de la demanda carecen de vocación de prosperidad, debiendo el despacho \
denegarlas en su integridad conforme a las normas aplicables y a la jurisprudencia reiterada que \
gobierna asuntos de esta naturaleza, con la consecuente condena en costas.
"""
    le = substance_signal(long_empty)
    s_le = score_turn(long_empty, _DIAG, {})
    print(f"     largo-vacío : {le}")
    check("B4 · largo y vacío: la densidad NO lo atrapa (el relleno es prosa larga)",
          le["densidad_desarrollo"] > 0.8
          and scoring.INFO_FLAG_SKELETON not in s_le["flags_informativos"])
    check("B5 · ...pero el ANCLAJE sí: 0 párrafos tocan el expediente",
          le["anclaje_expediente_ratio"] == 0.0
          and scoring.INFO_FLAG_LOW_ANCHORING in s_le["flags_informativos"])
    check("B6 · ...y la FUNDAMENTACIÓN también: apelación vaga ≠ norma concreta",
          le["fundamentacion_normativa_ratio"] == 0.0
          and scoring.INFO_FLAG_LOW_GROUNDING in s_le["flags_informativos"])
    check("B7 · largo y vacío: aun así sale ok:True (los indicios NO bloquean, por diseño)",
          s_le["ok"] is True)


def c_jurisdiction() -> None:
    print("\n-- C · agnosticismo de jurisdicción --")

    # El MISMO escrito, cambiando SOLO el cuerpo normativo citado. La estructura del
    # razonamiento (ancla, fuente, párrafo) es idéntica → el resultado estructural debe serlo.
    es = (DEVELOPED
          .replace("artículo 164 de la Ley 1437 de 2011", "artículo 25 de la Ley 39/2015")
          .replace("artículo 140 de la Ley 1437 de 2011", "artículo 21 de la Ley 39/2015")
          .replace("artículo 167 de la Ley 1564 de 2012", "artículo 217 de la Ley 1/2000"))
    co = substance_signal(DEVELOPED)
    sp = substance_signal(es)

    structural = ("bloques", "titulos", "parrafos_sustantivos", "parrafos_con_anclaje",
                  "anclaje_expediente_ratio", "parrafos_con_norma",
                  "fundamentacion_normativa_ratio")
    same = {k: co[k] for k in structural} == {k: sp[k] for k in structural}
    check("C1 · normas españolas vs colombianas → MISMO resultado estructural", same)
    check("C2 · el escrito español detecta sus 3 normas concretas",
          sp["fundamentacion_normativa_ratio"] == 1.0)
    check("C3 · mismas banderas informativas en ambas jurisdicciones",
          score_turn(DEVELOPED, _DIAG, {})["flags_informativos"]
          == score_turn(es, _DIAG, {})["flags_informativos"])

    # Sin léxico jurídico: un título se detecta por su FORMA. Un escrito de otro país con otra
    # nomenclatura de títulos se parte igual.
    check("C4 · los títulos se detectan por forma, no por palabra (ni 'PRIMERO' ni 'FUNDAMENTO')",
          scoring._is_header("FUNDAMENTOS DE DERECHO")
          and scoring._is_header("PRIMERO.- Sobre la caducidad")
          and scoring._is_header("2. Da inadmissibilidade"))


def d_no_regression() -> None:
    print("\n-- D · no regresión del contrato (casos de oro ya confirmados) --")

    check("D1 · los indicios NUNCA entran en `flags` (contrato viejo intacto)",
          all(f not in score_turn(SKELETON, _DIAG, {})["flags"]
              for f in (scoring.INFO_FLAG_SKELETON, scoring.INFO_FLAG_LOW_ANCHORING,
                        scoring.INFO_FLAG_LOW_GROUNDING)))
    check("D2 · `ok` sigue gobernado solo por `flags`",
          score_turn(SKELETON, _DIAG, {})["ok"] is True)

    # Todas las claves del contrato viejo siguen ahí (el gate y compare_reports las leen).
    s = score_turn(DEVELOPED, _DIAG, {"usage": {"total": 100}, "stage": "hitl"})
    old_keys = ("reached_draft", "draft_chars", "draft_tokens", "has_diagnosis_closing",
                "stage", "citas", "citas_sin_respaldo", "citas_respaldadas", "citas_marcadas",
                "citas_en_regla_ratio", "total_tokens", "latency_ms", "flags", "ok")
    check("D3 · el scorer conserva TODAS las claves que ya consumían gate y compare",
          all(k in s for k in old_keys))
    check("D4 · las claves nuevas viven aparte (`sustancia` + `flags_informativos`)",
          isinstance(s["sustancia"], dict) and isinstance(s["flags_informativos"], list))

    # Borrador vacío/minúsculo: el fallo ya lo dicen `sin_borrador`/`borrador_minusculo`;
    # no se apilan tres banderas informativas encima del mismo hecho.
    check("D5 · borrador vacío → sin banderas informativas (no se duplica el ruido)",
          score_turn("", "x", {})["flags_informativos"] == [])
    check("D6 · borrador minúsculo → sin banderas informativas (idem)",
          score_turn("muy corto", "x", {})["flags_informativos"] == [])


def e_unit() -> None:
    print("\n-- E · unidad --")

    check("E1 · partición por línea en blanco", len(scoring._split_blocks("a\n\nb\n\nc")) == 3)
    check("E2 · fallback a salto simple (sin líneas en blanco no se cuenta todo como 1 párrafo)",
          len(scoring._split_blocks("a\nb\nc")) == 3)
    check("E3 · una línea corta sin puntuación terminal es título",
          scoring._is_header("I. Excepción de caducidad"))
    check("E4 · una frase corta CON punto es prosa, no título",
          not scoring._is_header("Se propone la excepción de caducidad."))
    check("E5 · un párrafo largo nunca es título",
          not scoring._is_header("x" * (scoring.HEADER_MAX_CHARS + 1)))

    # COBERTURA, no conteo: 20 [doc 1] en un párrafo y nada en los otros dos NO es anclaje.
    p = ("El acta acredita el traslado de la operación al contratista el 1 de febrero de 2019, "
         "un mes antes del hecho que la actora imputa a la entidad demandada en su escrito. ")
    massed = (p + "[doc 1] " * 20 + "\n\n" + p + "más texto de relleno.\n\n"
              + p + "más texto de relleno todavía.")
    ms = substance_signal(massed)
    check("E6 · cobertura, no conteo: 20 [doc n] amontonados → anclaje ≈ 1/3, no 1.0",
          ms["parrafos_sustantivos"] == 3 and ms["parrafos_con_anclaje"] == 1
          and ms["anclaje_expediente_ratio"] < 0.4)

    check("E7 · borrador vacío → señal en ceros, sin excepción",
          substance_signal("")["parrafos_sustantivos"] == 0
          and substance_signal("")["densidad_desarrollo"] == 0.0)
    check("E8 · None → no lanza", substance_signal(None)["bloques"] == 0)

    # Pureza / determinismo: mismo input, mismo output.
    check("E9 · determinista (dos corridas idénticas)",
          substance_signal(DEVELOPED) == substance_signal(DEVELOPED))
    check("E10 · no muta el borrador", (lambda d: (substance_signal(d), d == DEVELOPED)[1])(DEVELOPED))


# ── F · jurisdiction_leak_signal (Frente E): agnóstico de PAÍS, sensible a la FORMA ────
# Mismo espíritu que `c_jurisdiction()` de arriba, pero para la señal de FUGA de jurisdicción
# (ver `scoring.jurisdiction_leak_signal`): reusa el escáner del guardián de citas, así que
# tiene que discriminar la MISMA cita concreta sin importar de qué país sea — la fuga es citar
# articulado concreto bajo jurisdicción desconocida, no citar el de un país en particular.
def f_jurisdiction_leak_agnostic() -> None:
    print("\n-- F · jurisdiction_leak_signal: agnóstico de PAÍS, sensible a la FORMA --")

    razona_por_institucion = (
        "El régimen general de validez de un contrato exige capacidad de las partes, "
        "consentimiento libre de vicios, objeto y causa lícitos; sin conocer bajo qué "
        "ordenamiento trabaja el despacho no es posible precisar más.")
    check("F1 · razona por institución, sin citar articulado concreto → SIN fuga",
          scoring.jurisdiction_leak_signal(razona_por_institucion)["leak"] is False
          and scoring.jurisdiction_leak_signal(razona_por_institucion)["citas_detectadas"] == 0)

    co = razona_por_institucion + " Con fundamento en el artículo 90 de la Ley 1437 de 2011."
    es = razona_por_institucion + " Con fundamento en el artículo 25 de la Ley 39/2015."
    leak_co = scoring.jurisdiction_leak_signal(co)
    leak_es = scoring.jurisdiction_leak_signal(es)
    check("F2 · una cita concreta COLOMBIANA dispara la fuga", leak_co["leak"] is True)
    check("F3 · la MISMA forma de cita, ESPAÑOLA, dispara la fuga IGUAL — no distingue país "
          "(la fuga es la FORMA de citar articulado concreto, no de qué país es la norma)",
          leak_es["leak"] is True and leak_es["citas_detectadas"] == leak_co["citas_detectadas"])
    check("F4 · determinista (dos corridas idénticas dan el mismo resultado)",
          scoring.jurisdiction_leak_signal(co) == scoring.jurisdiction_leak_signal(co))
    check("F5 · None no lanza (borrador vacío del turno)",
          scoring.jurisdiction_leak_signal(None)["leak"] is False)


def main() -> int:
    a_discrimination()
    b_false_positives()
    c_jurisdiction()
    d_no_regression()
    e_unit()
    f_jurisdiction_leak_agnostic()

    passed = sum(1 for _, ok in _results if ok)
    total = len(_results)
    print(f"\nRESULT: {passed}/{total} checks PASS")
    if passed == total:
        print("Indicios de sustancia OK — discriminan esqueleto/desarrollado, "
              "agnósticos de jurisdicción, informativos (no bloquean).")
        return 0
    print("Indicios de sustancia FAIL — HALT: no avanzar (CLAUDE.md §G).")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
