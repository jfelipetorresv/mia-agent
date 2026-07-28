# -*- coding: utf-8 -*-
"""Mia · test_afirmaciones_negativas.py — barrera del principio #46.1 (2026-07-27).

EL DEFECTO QUE ESTA BARRERA PERSIGUE (caso real del harness de litigio del despacho, 6.ª
corrida): el extractor forense informó que un memorando de supervisión «no menciona al
garante»; el escrito se construyó sobre esa base y la verificación demostró que el documento
nombraba a la aseguradora con NIT y póliza en CUATRO lugares. La afirmación habría llegado al
radicable. Regla: el resumen de un extractor NO sustituye al documento, y toda afirmación
negativa sobre el contenido de una pieza se verifica sobre la pieza COMPLETA.

Por qué Mia es especialmente vulnerable: sus mejores salidas de hoy son negativas («el
expediente no contiene norma citable») y las escribe leyendo los FRAGMENTOS recuperados por el
turno, no el documento entero. Misma causa, mismo error.

QUÉ FIJA:
  A · el detector encuentra las formas negativas reales y extrae términos ÚTILES de búsqueda;
  B · no dispara sobre prosa afirmativa ni sobre la abstención honesta del propio turno
      («no puedo redactar»), que es otra cosa y ya tiene su métrica;
  C · la confrontación distingue lo que está en el documento COMPLETO pero NO en el fragmento
      visto — la firma exacta del defecto;
  D · es AVISO: función pura, no edita el borrador, no bloquea, fail-soft ante datos ausentes.

Salida: exit 0 = PASS · exit 1 = FAIL.
"""
from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "backend")))

from mia.agents import verification as V  # noqa: E402

_results: list[tuple[str, bool]] = []


def check(nombre: str, ok: bool) -> None:
    _results.append((nombre, bool(ok)))
    print(f"  [{'OK' if ok else 'XX'}]   {nombre}")


# ── A · detección de las formas negativas ─────────────────────────────────────
CASO_REAL = ("El informe de supervisión no menciona al garante [doc 2], de modo que la "
             "convocatoria no lo alcanzaba.")

FORMAS = (
    ("el caso real del harness (no menciona + ancla)", CASO_REAL, True),
    ("no contiene", "El expediente no contiene ninguna providencia sobre el punto [doc 1].", True),
    ("no analiza", "El dictamen no analiza la vigencia del amparo [doc 3].", True),
    ("guarda silencio", "El acta guarda silencio sobre la cesión [doc 4].", True),
    ("no consta", "No consta en el memorando la fecha de notificación [doc 2].", True),
    ("no aparece", "El nombre del garante no aparece en la comunicación [doc 5].", True),
    ("no examina", "El informe no examina la posición del garante [doc 2].", True),
)


def a_deteccion() -> None:
    print("\n-- A · el detector encuentra las afirmaciones negativas --")
    for etiqueta, texto, esperado in FORMAS:
        hallado = bool(V.scan_negative_claims(texto))
        check(f"A · detecta — {etiqueta}", hallado is esperado)

    claims = V.scan_negative_claims(CASO_REAL)
    c = claims[0]
    check("A · extrae el ancla [doc 2] de la oración", c["docs"] == [2])
    check("A · extrae 'garante' como término de búsqueda (el término del defecto real)",
          "garante" in c["terminos"])
    check("A · NO propone buscar meta-vocabulario ('informe', 'expediente', 'documento'): "
          "buscarlo siempre daría positivo y el aviso sería ruido",
          not ({"informe", "expediente", "documento"} & set(c["terminos"])))
    check("A · reporta la oración completa y sus offsets (para que el abogado la ubique)",
          c["oracion"].startswith("El informe") and c["inicio"] == 0 and c["fin"] > 0)


# ── B · precisión: qué NO es una afirmación negativa sobre un documento ───────
NO_SON = (
    ("prosa afirmativa corriente",
     "El contrato se perfeccionó el 3 de marzo y las obligaciones se cumplieron [doc 1]."),
    ("abstención honesta del turno (es otra cosa y tiene su propia métrica)",
     "No puedo redactar el borrador solicitado mientras el despacho no declare el ordenamiento."),
    ("negación sobre el DERECHO, no sobre el contenido de una pieza",
     "La pretensión no procede porque el término está vencido."),
    ("borrador vacío", ""),
)


def b_precision() -> None:
    print("\n-- B · precisión: no dispara donde no debe --")
    for etiqueta, texto in NO_SON:
        check(f"B · NO lo marca — {etiqueta}", not V.scan_negative_claims(texto))


# ── C · confrontación contra el documento COMPLETO ────────────────────────────
# El fragmento que el turno recuperó NO menciona al garante; el documento entero sí, cuatro
# veces. Es exactamente el defecto real, reproducido.
FRAGMENTO_VISTO = ("En la visita de supervisión se verificó el avance de obra y se dejó "
                   "constancia del atraso en el frente 2.")
DOCUMENTO_COMPLETO = (
    FRAGMENTO_VISTO + "\n"
    "Se ofició a Mundial de Seguros, en su calidad de garante del contrato, para que "
    "concurriera a la diligencia.\n"
    "El garante fue notificado con NIT 860.000.000 y póliza 2900-1234.\n"
    "La supervisión reiteró al garante la solicitud de comparecencia.")


def c_confrontacion() -> None:
    print("\n-- C · confrontación contra el TEXTO COMPLETO del documento --")
    terminos = V.scan_negative_claims(CASO_REAL)[0]["terminos"]

    v = V.confront_negative_claim(terminos, DOCUMENTO_COMPLETO, FRAGMENTO_VISTO)
    check("C1 · el documento COMPLETO contradice la afirmación negativa", v["contradice"] is True)
    check("C2 · señala 'garante' como presente en el documento", "garante" in v["terminos_en_documento"])
    check("C3 · y como AUSENTE del fragmento que el turno vio — la firma exacta del defecto "
          "(la negativa se afirmó sobre un fragmento, no sobre la pieza)",
          "garante" in v["terminos_no_vistos"])

    # Si el documento completo tampoco lo menciona, la afirmación era CORRECTA: silencio.
    # (Este check destapó un ruido real del diseño: 'supervisión' viene del SUJETO de la frase y
    # está en el documento por definición. De ahí la regla de `confront_negative_claim`:
    # contradice el término presente en el documento y AUSENTE de lo que el turno vio.)
    v2 = V.confront_negative_claim(terminos, FRAGMENTO_VISTO, FRAGMENTO_VISTO)
    check("C4 · si el documento completo tampoco lo menciona, no hay aviso "
          "(la afirmación negativa era correcta)", v2["contradice"] is False)
    check("C4b · los términos del SUJETO de la frase no disparan el aviso: están en el "
          "documento por construcción y harían saltar toda negativa correcta",
          "supervision" in v2["terminos_en_documento"] and v2["terminos_no_vistos"] == [])

    # Sin texto completo que confrontar, la barrera CALLA. No puede afirmar que la negativa
    # es correcta (no verificó) ni inventar una alarma.
    v3 = V.confront_negative_claim(terminos, "", FRAGMENTO_VISTO)
    check("C5 · sin documento completo disponible la barrera calla (no inventa alarma)",
          v3["contradice"] is False and v3["terminos_en_documento"] == [])

    v4 = V.confront_negative_claim([], DOCUMENTO_COMPLETO, FRAGMENTO_VISTO)
    check("C6 · sin términos que buscar, no contradice nada", v4["contradice"] is False)


# ── D · es AVISO: pura, no edita, fail-soft ───────────────────────────────────
def d_es_aviso() -> None:
    print("\n-- D · la barrera AVISA: pura, no edita el borrador, fail-soft --")
    original = CASO_REAL
    copia = str(original)
    V.scan_negative_claims(original)
    check("D1 · no muta el borrador (no edita, no marca, no omite)", original == copia)
    check("D2 · determinista (dos pasadas idénticas)",
          V.scan_negative_claims(original) == V.scan_negative_claims(original))
    check("D3 · None no lanza", V.scan_negative_claims(None) == [])
    check("D4 · varias afirmaciones en un borrador se devuelven en orden de aparición",
          [c["docs"] for c in V.scan_negative_claims(
              "El acta no menciona la cesión [doc 1]. Luego, el informe no analiza el amparo "
              "[doc 4].")] == [[1], [4]])
    sin_ancla = V.scan_negative_claims("El expediente no contiene norma citable sobre el punto.")
    check("D5 · una afirmación negativa SIN ancla se devuelve igual, con docs vacío "
          "(el abogado debe verla aunque no haya pieza contra la que confrontar)",
          len(sin_ancla) == 1 and sin_ancla[0]["docs"] == [])


def main() -> int:
    print("== Barrera · afirmaciones negativas verificadas contra el documento completo ==")
    a_deteccion()
    b_precision()
    c_confrontacion()
    d_es_aviso()

    ok = sum(1 for _, v in _results if v)
    total = len(_results)
    print(f"\n{ok}/{total} checks PASS")
    if ok == total:
        print("Afirmaciones negativas OK — se detectan, se confrontan contra la pieza completa, "
              "y la barrera avisa sin bloquear.")
        return 0
    print("FALLA — el detector de afirmaciones negativas dejó de cubrir su caso o se infló.")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
