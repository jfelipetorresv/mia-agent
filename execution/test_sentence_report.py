# -*- coding: utf-8 -*-
"""
Mia · test_sentence_report.py — gate del INFORME POR ORACIÓN (F2 · espec. por oración).

El informe por oración (`agents/verification.build_sentence_report`) es ADITIVO y READ-ONLY:
eleva la unidad de reporte de la CITA a la ORACIÓN, atribuye cada cita a su oración y MIDE el
residuo por forma — SIN tocar el texto emitido ni las ediciones (esas siguen saliendo de
annotate_draft, §2.1 del diseño). Su peor caso es granularidad imperfecta del informe: nunca
una fuga ni un falso bloqueo.

Cubre (números tras la verificación cruzada de Codex, M1..M4/m1..m3 integrados):
  P · byte a byte EXACTO (M3): el texto EMITIDO y el informe CLÁSICO COMPLETO son idénticos entre
      sentence_report False y True en AMBAS ramas (clásica + omisión), con carve-out del abogado,
      docs fantasma y >50 citas; con True aparece la clave aditiva `oraciones` (y clasifica TODAS
      las citas, no solo 50).
  S · segmentación agnóstica: «Ley 100 de 1993», «C.C.» y «art. 5.» no se parten; dos citas se
      atribuyen a SU oración; bloque `=== … ===` + sus líneas etiquetadas como frontera (regla 50);
      sin oraciones vacías. MUTACIÓN: sin la protección de spans de cita, la cita se PARTE.
  S2 · anclas [doc n] (M1): `[doc 1].` corta tras el `]` (la afirmación desnuda posterior cae en
      el residuo); `[doc. 1]` no se parte; comillas/paréntesis de cierre finales se quedan con su
      oración.
  Q · señal POSITIVA en AMBAS ramas (m6): genérica → `con_omision`; configurada → `con_anotacion`;
      ambas con `sin_respaldo_afirmativa`. MUTACIONES: apagar la heurística → residuo 0; apagar el
      escáner → `con_omision` 0.
  R · rótulo (m1, techo #2): ninguna clave ni estado del bloque `oraciones` dice
      «verificada»/«respaldada». M3 · techo #9 DECLARADO (co-ubicación).
  O · sondas de entailment con ORÁCULO DETERMINISTA (M4): sonda 6 intercepción + mutación de
      salida; sonda 5 residuo + límite declarado; sonda 4 (implicación pura) = REVISIÓN HUMANA.
  M2a · `atribuye_sin_material` calculado en la capa de SCORING (verification queda agnóstico).
  W · cableado real vía graph._verify_draft (ambos modos) + barrera del payload HITL.
  M1-mov · el movimiento de forma/léxico a verification.py queda byte a byte (reexport).
  A · agnosticismo: cero literal de país en `_ASSERT_ABBREVIATIONS`.

OFFLINE (sin DB obligatoria — fail-soft de citation_patterns_for — y sin LLM).
Salida: exit 0 = PASS · exit 1 = FAIL.
    .venv\\Scripts\\python.exe execution\\test_sentence_report.py
"""
from __future__ import annotations
import asyncio
import json
import sys
from contextlib import contextmanager
from pathlib import Path
from types import SimpleNamespace

if sys.platform == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

ROOT = Path(__file__).resolve().parents[1]
from dotenv import load_dotenv  # noqa: E402

load_dotenv(ROOT / ".env")
sys.path.insert(0, str(ROOT / "backend"))

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

from mia.agents import verification            # noqa: E402
from mia.agents.graph import MatterGraphBuilder  # noqa: E402
from mia.eval import harness                    # noqa: E402
from mia.eval import scoring                    # noqa: E402

_results: list[tuple[str, bool]] = []


def check(name: str, ok) -> None:
    _results.append((name, bool(ok)))
    print(("  [OK]   " if ok else "  [FAIL] ") + name)


@contextmanager
def mutado(obj, attr: str, value):
    """Neutraliza un mecanismo EN PROCESO y lo restaura pase lo que pase (prueba de mutación)."""
    original = getattr(obj, attr)
    setattr(obj, attr, value)
    try:
        yield
    finally:
        setattr(obj, attr, original)


# Afirmación asertiva SIN cita, > piso de longitud, termina en «.» → residuo por forma.
ASERTIVA = ("El termino de caducidad de la accion se cuenta a partir del dia siguiente a la "
            "ocurrencia del hecho danoso, y la carga de la prueba corresponde integramente a "
            "quien alega la existencia del derecho que reclama dentro del respectivo proceso.")


def _classic(report: dict) -> dict:
    return {k: v for k, v in report.items() if k != "oraciones"}


def _byte_a_byte(name: str, **kw) -> None:
    """El texto EMITIDO y el informe CLÁSICO COMPLETO deben ser idénticos entre sentence_report
    False y True (no solo dos contadores) — M3. Con True aparece la clave aditiva `oraciones`."""
    t_off, r_off = verification.annotate_draft(sentence_report=False, **kw)
    t_on, r_on = verification.annotate_draft(sentence_report=True, **kw)
    ok = (t_off == t_on                          # texto emitido byte a byte
          and _classic(r_on) == r_off            # informe clásico COMPLETO idéntico
          and "oraciones" not in r_off           # el default no gana la clave
          and "oraciones" in r_on)               # el modo por oración sí
    check(name, ok)
    if not ok:
        print(f"         texto_igual={t_off == t_on} clasico_igual={_classic(r_on) == r_off}")


def p_byte_a_byte() -> None:
    print("\n== P · byte a byte EXACTO (texto + informe clásico completo) en AMBAS ramas (M3) ==")
    # Rama clásica (marcado) y rama de omisión, con documentos y ancla mal puesta.
    _byte_a_byte("p1 · byte a byte — rama clásica (omit_unbacked=False)",
                 draft=TEXTO_MAL, documents=DOCS_MAL, num_documents=2, omit_unbacked=False)
    _byte_a_byte("p2 · byte a byte — rama de omisión (omit_unbacked=True)",
                 draft=TEXTO_MAL, documents=DOCS_MAL, num_documents=2, omit_unbacked=True)
    # Carve-out del abogado (lawyer_text): la cita del mensaje del abogado no se omite.
    _byte_a_byte("p3 · byte a byte — carve-out del abogado (lawyer_text)",
                 draft="Aplica la Ley 4137 de 2091 al caso concreto del expediente litigioso.",
                 omit_unbacked=True, lawyer_text="Consulta: ¿aplica la Ley 4137 de 2091 aquí?")
    # Docs fantasma ([doc 9] fuera de rango) — el guardián corre y anota igual en ambos modos.
    _byte_a_byte("p4 · byte a byte — docs fantasma ([doc 9] fuera de rango)",
                 draft="Ver [doc 9] y la Ley 4137 de 2091 del asunto controvertido.",
                 num_documents=1)
    # >50 citas: el informe clásico (detalle capado a 50) idéntico; y el bloque por oración
    # clasifica TODAS (m3: lista SIN capar), no solo las primeras 50.
    many = " ".join(f"La Ley {i} de 2001 dispone algo pertinente al asunto." for i in range(1, 61))
    _byte_a_byte("p5 · byte a byte — borrador con >50 citas (informe clásico intacto)", draft=many)
    _, r_many = verification.annotate_draft(many, sentence_report=True)
    check("p6 · >50 citas: el bloque por oración clasifica TODAS (con_anotacion≥51, no capado a 50)",
          r_many["oraciones"]["con_anotacion"] >= 51)


def s_segmentacion() -> None:
    print("\n== S · segmentación agnóstica (protected_spans es el mecanismo primario) ==")

    t_ley = "El regimen surge de la Ley 100 de 1993, como se explico arriba en el escrito."
    prot_ley = [(c["start"], c["end"]) for c in verification.scan_citations(t_ley)]
    sp_ley = verification.segment_sentences(t_ley, prot_ley)
    check("s1 · «Ley 100 de 1993» no se parte (queda entera en una oración)",
          any("Ley 100 de 1993" in t_ley[s:e] for s, e in sp_ley))

    t_cc = "El contrato se rige por el C.C. segun la clausula tercera del negocio celebrado."
    sp_cc = verification.segment_sentences(t_cc, [])
    check("s2 · «C.C.» no se parte por dentro (iniciales de una sola letra)",
          any("C.C." in t_cc[s:e] for s, e in sp_cc))

    t_art = "El art. 5. resuelve la cuestion sin mas tramite procesal alguno en el caso."
    sp_art = verification.segment_sentences(t_art, [])
    check("s3 · «art. 5.» no corta (abreviatura de forma + inicial de un dígito) → 1 oración",
          len(sp_art) == 1)

    # Atribución: dos citas, cada una en SU oración.
    t_two = "El regimen surge de la Ley 100 de 1993. El plazo se rige por el Decreto 999 de 2001."
    _, rep_two = verification.annotate_draft(t_two, sentence_report=True)
    det = rep_two["oraciones"]["detalle"]
    s_ley = next((d for d in det if any(cc["cita"] == "Ley 100 de 1993" for cc in d["citas"])), None)
    s_dec = next((d for d in det if any(cc["cita"] == "Decreto 999 de 2001" for cc in d["citas"])), None)
    check("s4 · atribución: cada cita cae en SU propia oración (índices distintos, 1 cita c/u)",
          s_ley is not None and s_dec is not None and s_ley["idx"] != s_dec["idx"]
          and len(s_ley["citas"]) == 1 and len(s_dec["citas"]) == 1)

    # MUTACIÓN de la protección: una cita con punto interno se PARTE sin protected_spans.
    t_mut = "El regimen aplica la Ley 25.326 segun el concepto tecnico del expediente completo."
    prot_mut = [(c["start"], c["end"]) for c in verification.scan_citations(t_mut)]
    sp_ok = verification.segment_sentences(t_mut, prot_mut)
    sp_no = verification.segment_sentences(t_mut, [])
    check("s5 · con la protección de spans, «Ley 25.326» queda entera en una oración",
          any("Ley 25.326" in t_mut[s:e] for s, e in sp_ok))
    check("s6 · MUTADO — sin la protección de spans la cita se PARTE (ninguna oración la "
          "contiene entera) → el check discrimina",
          not any("Ley 25.326" in t_mut[s:e] for s, e in sp_no))

    # Regla 50: ninguna oración cruza un marcador de bloque de máquina '===', y las tres líneas
    # etiquetadas del cierre (sin puntuación terminal) NO se funden (frontera por forma).
    t_block = ("Prosa previa al bloque de maquina del cierre del diagnostico.\n"
               "=== CIERRE DEL DIAGNOSTICO ===\n"
               "Problema juridico: la caducidad de la accion\n"
               "Normas y fuentes: las que obran en el expediente\n"
               "Riesgo y recomendacion: proponer la excepcion\n"
               "=== FIN DEL CIERRE ===\nProsa posterior al bloque.")
    sp_block = verification.segment_sentences(t_block, [])
    check("s7 · regla 50: la prosa previa y el interior del bloque === quedan en oraciones "
          "distintas (ninguna cruza el marcador)",
          not any("Prosa previa" in t_block[s:e] and "Problema juridico" in t_block[s:e]
                  for s, e in sp_block))
    check("s8 · las tres líneas etiquetadas del cierre (sin '.') NO se funden entre sí (m1)",
          not any("Problema juridico" in t_block[s:e] and "Riesgo y recomendacion" in t_block[s:e]
                  for s, e in sp_block))
    check("s9 · no hay oraciones vacías / solo-espacio (m1): todo span tiene contenido",
          all(t_block[s:e].strip() for s, e in sp_block))


def s_doc_refs() -> None:
    print("\n== S2 · anclas [doc n]: `[doc 1].` corta, `[doc. 1]` no se parte (M1) ==")
    # M1: `[doc 1].` debe cortar DESPUÉS del `]` → la afirmación desnuda posterior NO se fusiona
    # con la oración anclada (antes `prev=''` la guardaba y el residuo bajaba de 1 a 0).
    t = f"El regimen surge del expediente [doc 1]. {ASERTIVA}"
    docone = [{"filename": "d1.txt", "content": "Contenido del documento uno del expediente."}]
    _, rep = verification.annotate_draft(t, documents=docone, num_documents=1, sentence_report=True)
    check("s2a · `[doc 1].` corta tras el ancla → la afirmación desnuda cae en el residuo (M1 bug)",
          rep["oraciones"]["sin_respaldo_afirmativa"] >= 1)
    sp = verification.segment_sentences(t, [])
    check("s2b · `[doc 1].` → el ancla y la afirmación quedan en oraciones DISTINTAS (no fundidas)",
          not any("[doc 1]" in t[s:e] and "termino de caducidad" in t[s:e].lower()
                  for s, e in sp))
    # `[doc. 1]` (punto interno del ancla) NO se parte por dentro (span protegido por _DOC_REF_RE).
    t2 = "Consta en el expediente [doc. 1] la prueba del hecho controvertido dentro del proceso."
    sp2 = verification.segment_sentences(t2, [])
    check("s2c · `[doc. 1]` no se parte por dentro del ancla (protegido)",
          any("[doc. 1]" in t2[s:e] for s, e in sp2))
    # Comillas / paréntesis de cierre finales se quedan con la oración que TERMINA.
    t3 = ("La regla procesal es clara.» Ahora bien, el termino de caducidad exige un "
          "analisis mas detenido del asunto en su conjunto.")
    sp3 = verification.segment_sentences(t3, [])
    check("s2d · comillas de cierre finales («.»») se quedan con la oración que termina",
          any(t3[s:e].rstrip().endswith(".»") for s, e in sp3))


# Doc que NO contiene la cita (mal anclado) y doc que SÍ la contiene (localiza).
DOCS_MAL = [{"filename": "d1.txt", "content": "Contenido uno sin la norma citada."},
            {"filename": "d2.txt", "content": "Contenido dos sin la norma citada tampoco."}]
DOCS_OK = [{"filename": "memo.txt",
            "content": "El memo invoca la Ley 4137 de 2091 en su clausula tercera del negocio."}]
TEXTO_MAL = f"Segun [doc 2], aplica la Ley 4137 de 2091 al caso concreto. {ASERTIVA}"


def q_senal_positiva() -> None:
    print("\n== Q · señal POSITIVA en AMBAS ramas + mutaciones (m6, regla 46) ==")

    # Rama GENÉRICA (omit_unbacked=True): cita sin respaldo → omitida; afirmación → residuo.
    _, rep_gen = verification.annotate_draft(
        TEXTO_MAL, documents=DOCS_MAL, num_documents=2, omit_unbacked=True, sentence_report=True)
    o_gen = rep_gen["oraciones"]
    check("q1 · rama genérica: con_omision≥1 (la cita mal anclada se omite) y "
          "sin_respaldo_afirmativa≥1 (la aseveración desnuda)",
          o_gen["con_omision"] >= 1 and o_gen["sin_respaldo_afirmativa"] >= 1)

    # Rama CONFIGURADA (omit_unbacked=False): la MISMA cita se anota [VERIFICAR].
    _, rep_cfg = verification.annotate_draft(
        TEXTO_MAL, documents=DOCS_MAL, num_documents=2, omit_unbacked=False, sentence_report=True)
    o_cfg = rep_cfg["oraciones"]
    check("q2 · rama configurada: con_anotacion≥1 (la cita se anota, no se omite) y "
          "sin_respaldo_afirmativa≥1 — mismo texto, cero-no-ciego en la rama de marcado (m6)",
          o_cfg["con_anotacion"] >= 1 and o_cfg["sin_respaldo_afirmativa"] >= 1)

    # MUTACIÓN 1: apagar la heurística de asertividad (piso imposible) → residuo cae a 0.
    with mutado(verification, "SUBSTANTIVE_SENTENCE_MIN_CHARS", 10 ** 9):
        _, rep_m1 = verification.annotate_draft(
            TEXTO_MAL, documents=DOCS_MAL, num_documents=2, omit_unbacked=True,
            sentence_report=True)
        check("q3 · MUTADO — piso de asertividad imposible → sin_respaldo_afirmativa cae a 0 → ROJO",
              rep_m1["oraciones"]["sin_respaldo_afirmativa"] == 0)

    # MUTACIÓN 2: apagar el escáner de citas → la atribución cita→oración se apaga → con_omision 0.
    with mutado(verification, "scan_citations", lambda text, patterns=None: []):
        _, rep_m2 = verification.annotate_draft(
            TEXTO_MAL, documents=DOCS_MAL, num_documents=2, omit_unbacked=True,
            sentence_report=True)
        check("q4 · MUTADO — escáner de citas apagado → con_omision cae a 0 (sin atribución) → ROJO",
              rep_m2["oraciones"]["con_omision"] == 0)


def r_rotulo() -> None:
    print("\n== R · rótulo (m1, techo #2): nunca «verificada»/«respaldada» en el bloque ==")

    text_ok = "Segun [doc 1], aplica la Ley 4137 de 2091 al caso planteado por la parte."
    _, rep_ok = verification.annotate_draft(text_ok, documents=DOCS_OK, num_documents=1,
                                            sentence_report=True)
    o = rep_ok["oraciones"]
    check("r1 · la cita anclada a un doc que la contiene → estado 'con_cita_localizada'",
          o["con_cita_localizada"] >= 1)
    check("r2 · rótulo per-cita: la cita localizada se rotula 'cita_localizada', no 'respaldada'",
          any(cc["estado"] == "cita_localizada" for d in o["detalle"] for cc in d["citas"]))

    # Barrera dura: NINGUNA cadena del bloque oraciones dice respaldada/verificada.
    estados = list(o.keys()) + [d["estado"] for d in o["detalle"]] \
        + [cc["estado"] for d in o["detalle"] for cc in d["citas"]]
    check("r3 · ninguna clave ni estado del bloque 'oraciones' usa «respaldada»/«verificada»",
          not any("respaldada" in str(x) or "verificada" in str(x) for x in estados))
    check("r4 · las claves de conteo usan 'con_cita_localizada', jamás 'respaldadas'",
          "con_cita_localizada" in o and "respaldadas" not in o)

    # M3 · techo #9 DECLARADO: proposición desnuda co-ubicada con la cita → NO entra al residuo.
    text_coloc = ("Segun [doc 1], aplica la Ley 4137 de 2091 y el termino de caducidad es de "
                  "dos anos contados desde el hecho, sin que quepa discutirlo en el proceso.")
    _, rep_co = verification.annotate_draft(text_coloc, documents=DOCS_OK, num_documents=1,
                                            sentence_report=True)
    o_co = rep_co["oraciones"]
    check("r5 · M3 techo #9 DECLARADO: la proposición desnuda co-ubicada con la cita queda bajo "
          "con_cita_localizada y NO en el residuo (el residuo es ciego a la co-ubicación)",
          o_co["con_cita_localizada"] >= 1 and o_co["sin_respaldo_afirmativa"] == 0)

    # Serializable y compacto (viaja en metadata / payload HITL).
    check("r6 · el bloque 'oraciones' es serializable a JSON (strings/ints/bools)",
          isinstance(json.dumps(o), str))


def o_oraculos() -> None:
    print("\n== O · sondas de entailment: oráculos DETERMINISTAS + mutación (M4) ==")
    # El contenido del doc cierra la cita con un conector/punto (la guarda de fronteras del
    # guardián rechaza una cita a la que le sigue una palabra que cambie la norma).
    docs = [{"filename": "concepto.txt",
             "content": "El regimen de nulidades se rige por la Ley 4080 de 2093 en su clausula."},
            {"filename": "acta.txt",
             "content": "Esta acta describe plazos de entrega y canones, sin norma alguna."}]

    # Sonda 6 (soporte cruzado mal anclado) — ORÁCULO: la cita anclada al doc EQUIVOCADO se
    # INTERCEPTA (no localiza). MUTACIÓN de salida: anclada al doc CORRECTO → localiza.
    viol = "Segun [doc 2], el regimen se rige por la Ley 4080 de 2093 en el caso planteado."
    _, r_viol = verification.annotate_draft(viol, documents=docs, num_documents=2,
                                            sentence_report=True)
    ov = r_viol["oraciones"]
    check("o1 · sonda 6 ORÁCULO: cita anclada al doc EQUIVOCADO → interceptada "
          "(con_anotacion≥1, con_cita_localizada=0)",
          ov["con_anotacion"] >= 1 and ov["con_cita_localizada"] == 0)
    ok_ancla = "Segun [doc 1], el regimen se rige por la Ley 4080 de 2093 en el caso planteado."
    _, r_ok = verification.annotate_draft(ok_ancla, documents=docs, num_documents=2,
                                          sentence_report=True)
    check("o2 · sonda 6 MUTACIÓN de salida: ancla al doc CORRECTO → con_cita_localizada≥1 "
          "(el oráculo discrimina, no marca todo)",
          r_ok["oraciones"]["con_cita_localizada"] >= 1)

    # Sonda 5 (afirmación sin cita) — ORÁCULO: residuo determinista; LÍMITE DECLARADO bajo el piso.
    _, r_res = verification.annotate_draft(ASERTIVA, sentence_report=True)
    check("o3 · sonda 5 ORÁCULO: una aseveración desnuda > piso dispara el residuo",
          r_res["oraciones"]["sin_respaldo_afirmativa"] >= 1)
    _, r_corta = verification.annotate_draft("El plazo corre desde la ejecutoria.",
                                             sentence_report=True)
    check("o4 · sonda 5 LÍMITE DECLARADO: por debajo del piso de 180 la aseveración es invisible "
          "(sesgo declarado, no medición del hueco)",
          r_corta["oraciones"]["sin_respaldo_afirmativa"] == 0)

    # Sonda 4 (entailment puro) — SIN oráculo automático: solo se asegura que el informe NUNCA
    # rotule «verificada»; que la cita sostenga la conclusión B es REVISIÓN HUMANA (M4).
    doc_a = [{"filename": "norma.txt",
              "content": "La reparacion directa se rige por el articulo 90 de la Ley 4137 de 2091."}]
    concl_b = ("Segun [doc 1], el articulo 90 de la Ley 4137 de 2091 fija el termino de "
               "caducidad en dos anos.")
    _, r_ent = verification.annotate_draft(concl_b, documents=doc_a, num_documents=1,
                                           sentence_report=True)
    oe = r_ent["oraciones"]
    estados = list(oe.keys()) + [d["estado"] for d in oe["detalle"]] \
        + [cc["estado"] for d in oe["detalle"] for cc in d["citas"]]
    check("o5 · sonda 4 (entailment puro): la cita localiza pero el informe NO rotula "
          "«verificada»/«respaldada» — la implicación queda a REVISIÓN HUMANA, no automática",
          oe["con_cita_localizada"] >= 1
          and not any("verificada" in str(x) or "respaldada" in str(x) for x in estados))


def m2a_provenance() -> None:
    print("\n== M2a · atribuye_sin_material en la capa de SCORING (verification agnóstico) ==")
    draft = ("Conforme a la experiencia del despacho en asuntos de esta naturaleza, la tesis de "
             "la convocante no prospera segun el criterio consolidado del despacho aplicado antes.")
    _, rep = verification.annotate_draft(draft, sentence_report=True)
    sig0 = scoring.sentence_discipline_signal(rep, documents_retrieved=0)
    check("m2a1 · SIN material sellado: la oración con frase de procedencia atribuye al despacho",
          sig0.get("oraciones_atribuye_sin_material", 0) >= 1)
    sig3 = scoring.sentence_discipline_signal(rep, documents_retrieved=3)
    check("m2a2 · MUTADO — CON material sellado la misma oración YA NO atribuye sin material",
          sig3.get("oraciones_atribuye_sin_material", 0) == 0)
    check("m2a3 · verification.py queda AGNÓSTICO: no calcula procedencia (la señal vive en scoring)",
          not hasattr(verification, "_PROVENANCE_PHRASES"))


def _verify(jurisdictions, text):
    state = {"tenant_id": "00000000-0000-0000-0000-000000000000",
             "jurisdictions": jurisdictions, "documents": [], "messages": []}
    md: dict = {}
    asyncio.run(MatterGraphBuilder._verify_draft(SimpleNamespace(), state, md, text))
    return md


def w_cableado() -> None:
    print("\n== W · cableado real vía graph._verify_draft + barrera del payload HITL ==")
    texto = f"Segun lo anterior, aplica la Ley 4137 de 2091 al caso. {ASERTIVA}"

    md_gen = _verify(["generic"], texto)
    o_gen = (md_gen.get("verification") or {}).get("oraciones") or {}
    check("w1 · rama genérica cableada: _verify_draft activa el informe con con_omision≥1 y "
          "sin_respaldo_afirmativa≥1",
          o_gen.get("con_omision", 0) >= 1 and o_gen.get("sin_respaldo_afirmativa", 0) >= 1)

    md_co = _verify(["co"], texto)
    o_co = (md_co.get("verification") or {}).get("oraciones") or {}
    check("w2 · rama configurada cableada: mismo texto → con_anotacion≥1 y "
          "sin_respaldo_afirmativa≥1 (m6)",
          o_co.get("con_anotacion", 0) >= 1 and o_co.get("sin_respaldo_afirmativa", 0) >= 1)

    check("w3 · barrera HITL: el informe que viaja bajo 'verification' trae la clave 'oraciones'",
          "oraciones" in (md_gen.get("verification") or {}))

    # El payload del checkpoint HITL reenvía el informe COMPLETO de 'verification' (oraciones
    # viaja con él, igual que docs_fantasma/omitidas). Barrera de cableado, como el check c7.
    graph_src = (ROOT / "backend" / "mia" / "agents" / "graph.py").read_text(encoding="utf-8")
    interrupt_block = graph_src.split("Borrador listo para tu aprobación.", 1)[1].split(
        "de aquí en adelante", 1)[0]
    check("w4 · barrera HITL: el payload reenvía el informe COMPLETO de 'verification' "
          "(la clave 'oraciones' viaja dentro, no se recorta)",
          '"verification": (state.get("metadata") or {}).get("verification")' in interrupt_block)


def m1_reexport() -> None:
    print("\n== M1-mov · el movimiento de forma/léxico queda byte a byte (reexport, regla 6) ==")
    check("m1a · scoring._is_header ES el mismo objeto que verification._is_header",
          scoring._is_header is verification._is_header)
    check("m1b · scoring reexporta los pisos con el mismo valor (180 / 120)",
          scoring.SUBSTANTIVE_PARAGRAPH_MIN_CHARS == verification.SUBSTANTIVE_PARAGRAPH_MIN_CHARS == 180
          and scoring.HEADER_MAX_CHARS == verification.HEADER_MAX_CHARS == 120)
    check("m1c · harness.ABSTENTION_PHRASES ES el mismo objeto que verification.ABSTENTION_PHRASES",
          harness.ABSTENTION_PHRASES is verification.ABSTENTION_PHRASES)
    check("m1d · substance_signal sigue vivo: título por forma, párrafo largo no es título",
          scoring._is_header("FUNDAMENTOS DE DERECHO") and not scoring._is_header("x" * 200))
    check("m1e · abstention_signal sigue detectando una frase de la lista fija",
          harness.abstention_signal("no cuento con elementos suficientes para esto", "")["abstiene"]
          is True)


def a_agnosticismo() -> None:
    print("\n== A · agnosticismo: cero literal de país en _ASSERT_ABBREVIATIONS ==")
    paises = ("colombia", "mexico", "espana", "españa", "chile", "argentina", "peru",
              "ecuador", "cpaca", "tutela", "codigo civil", "juriscol", "suin")
    joined = " ".join(verification._ASSERT_ABBREVIATIONS).lower()
    check("a1 · _ASSERT_ABBREVIATIONS no trae literal de país / código / corte",
          not any(p in joined for p in paises))


def main() -> int:
    print("== Informe POR ORACIÓN (F2 · espec. por oración) ==")
    p_byte_a_byte()
    s_segmentacion()
    s_doc_refs()
    q_senal_positiva()
    r_rotulo()
    o_oraculos()
    m2a_provenance()
    w_cableado()
    m1_reexport()
    a_agnosticismo()

    passed = sum(1 for _, ok in _results if ok)
    total = len(_results)
    print(f"\n{passed}/{total} checks PASS")
    if passed == total:
        print("informe por oración OK — aditivo, read-only, agnóstico; residuo INFORMATIVO nunca gate.")
        return 0
    print("informe por oración FAIL — HALT: no avanzar (CLAUDE.md §G).")
    for n, ok in _results:
        if not ok:
            print("   - " + n)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
