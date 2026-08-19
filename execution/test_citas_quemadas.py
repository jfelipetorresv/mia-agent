# -*- coding: utf-8 -*-
"""Mia · test_citas_quemadas.py — barrera del MURO de citas quemadas (principio #46.2).

EL DEFECTO QUE PERSIGUE (caso real del despacho, julio 2026): un banco de argumentos que el
despacho tenía por «verificado» traía una cita FABRICADA anclada a número y ponente reales. La
verificación contra las relatorías oficiales la desmintió. La lección que quedó escrita en el
harness del despacho es la que gobierna esta barrera: **lo que no tiene barrera, vuelve** —
verificar una cita falsa una vez no sirve de nada si el sistema puede reemitirla mañana.

POR QUÉ ESTA SÍ ES MURO (y las otras tres de la decisión #46 son aviso): no admite falso
positivo. La cita está en la lista que el propio abogado construyó, o no está. No hay
heurística, ni parecido, ni juicio de la máquina.

QUÉ FIJA:
  A · una cita quemada se RETIRA del texto emitido y queda en el informe;
  B · el muro gana al RESPALDO: ni el corpus ni el ancla al expediente resucitan una cita
      quemada — que es exactamente cómo se colό el defecto original (un banco «verificado»
      respaldaba una cita fabricada);
  C · sin banco, el comportamiento queda idéntico a antes de existir la barrera;
  D · el cotejo es tonto a propósito: normaliza y cruza, con contención literal para las citas
      que se escriben con y sin complementos. Nada de semejanza.

Las citas de ejemplo son las que el despacho quemó de verdad (documentadas en su harness), y
están aquí SOLO como datos de prueba: este archivo no las afirma como buenas ni las cita.

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


# Citas realmente quemadas por el despacho (solo como datos de prueba).
BANCO = [
    {"citation": "Sentencia C-832 de 2002",
     "citation_norm": V._normalize("Sentencia C-832 de 2002"),
     "reason": "el pasaje atribuido es fabricado; la sentencia real trata otro artículo"},
    {"citation": "Sentencia SU-259 de 2021",
     "citation_norm": V._normalize("Sentencia SU-259 de 2021"),
     "reason": "la unificación que se le atribuye no existe"},
]


def a_se_retira() -> None:
    print("\n-- A · una cita quemada se retira del texto emitido --")
    borrador = ("El régimen aplicable se apoya en la Sentencia C-832 de 2002, que fija el "
                "criterio invocado por la contraparte.")
    texto, informe = V.annotate_draft(borrador, burned=BANCO)

    check("A1 · la cita quemada NO aparece en el texto emitido",
          "C-832" not in texto)
    check("A2 · en su lugar queda una marca visible y en lenguaje del abogado",
          V.BURNED_MARK in texto)
    check("A3 · el informe la cuenta como quemada", informe.get("quemadas") == 1)
    check("A4 · el informe dice de qué tamaño es el banco que se aplicó",
          informe.get("banco_quemadas") == 2)
    check("A5 · el texto original de la cita queda en el informe (trazabilidad: el abogado "
          "debe poder ver QUÉ se retiró)",
          any(d.get("estado") == "quemada" and "C-832" in d.get("cita", "")
              for d in informe.get("detalle") or []))
    check("A6 · el aviso explica por qué se retiró", "no se vuelven a emitir"
          in (informe.get("aviso_quemadas") or "").lower()
          or "marcó como falsas" in (informe.get("aviso_quemadas") or ""))
    check("A7 · el resto del borrador queda intacto",
          "criterio invocado por la contraparte" in texto)


def b_gana_al_respaldo() -> None:
    print("\n-- B · el MURO gana al respaldo (el caso que originó el principio) --")
    borrador = "Como lo indicó la Sentencia C-832 de 2002, procede la excepción."
    # Una fuente que "respalda" la cita quemada: es exactamente el banco «verificado» que
    # respaldaba una cita fabricada en el caso real.
    fuentes = [{"tipo": "jurisprudencia", "referencia": "Sentencia C-832 de 2002",
                "titulo": "Ficha del banco del despacho",
                "content": "Sentencia C-832 de 2002 — ficha del banco interno."}]
    texto, informe = V.annotate_draft(borrador, sources=fuentes, burned=BANCO)
    check("B1 · con banco quemado, la cita se retira AUNQUE una fuente la respalde",
          "C-832" not in texto and informe.get("quemadas") == 1)
    check("B2 · y NO se cuenta como respaldada (el respaldo no puede resucitarla)",
          informe.get("respaldadas") == 0)

    # Control: SIN banco, esa misma cita con esa misma fuente sí se respalda. Si este control
    # se rompiera, el test A estaría pasando por otra razón y no probaría el muro.
    texto2, informe2 = V.annotate_draft(borrador, sources=fuentes)
    check("B3 · CONTROL — sin banco, la misma cita con la misma fuente queda respaldada y en "
          "el texto (prueba de que lo que la retira es el muro, no otra cosa)",
          "C-832" in texto2 and informe2.get("respaldadas") == 1)


def c_sin_banco_identico() -> None:
    print("\n-- C · sin banco, el comportamiento es el de siempre --")
    borrador = "La Sentencia C-832 de 2002 sostiene el criterio."
    t_sin, i_sin = V.annotate_draft(borrador)
    t_vacio, i_vacio = V.annotate_draft(borrador, burned=[])
    check("C1 · `burned=None` y `burned=[]` dan el MISMO resultado",
          (t_sin, i_sin) == (t_vacio, i_vacio))
    check("C2 · sin banco, el informe no trae las claves del muro "
          "(el informe clásico queda byte a byte igual)",
          "quemadas" not in i_sin and "banco_quemadas" not in i_sin)
    check("C3 · sin banco, la cita permanece en el texto (se marca o se respalda, según el "
          "camino de siempre)", "C-832" in t_sin)


def d_cotejo_tonto() -> None:
    print("\n-- D · el cotejo normaliza y cruza; nada de semejanza --")
    idx = V._burned_index(BANCO)
    check("D1 · misma cita con otras mayúsculas/tildes -> quemada",
          V._is_burned("sentencia c-832 de 2002", idx))
    check("D2 · la cita con complementos (ponente, etc.) -> quemada "
          "(la misma cita se escribe con y sin ellos)",
          V._is_burned("Sentencia C-832 de 2002, M.P. Jaime Araújo Rentería", idx))
    check("D3 · una cita DISTINTA del mismo año NO se quema "
          "(el muro no puede tocar citas buenas)",
          not V._is_burned("Sentencia C-833 de 2002", idx))
    check("D4 · una cita de otra clase NO se quema",
          not V._is_burned("Ley 1437 de 2011", idx))
    check("D5 · el índice acepta strings pelados y dicts de la tabla, indistintamente",
          V._burned_index(["Sentencia C-832 de 2002"]) <= idx)
    check("D6 · entradas vacías o basura no crean entradas en el banco",
          V._burned_index([None, "", {"citation": ""}, {}]) == frozenset())
    check("D7 · cita vacía nunca está quemada (no bloquea por nada)",
          not V._is_burned("", idx) and not V._is_burned(None, idx))


def main() -> int:
    print("== Barrera · MURO del banco de citas quemadas del despacho ==")
    a_se_retira()
    b_gana_al_respaldo()
    c_sin_banco_identico()
    d_cotejo_tonto()

    ok = sum(1 for _, v in _results if v)
    total = len(_results)
    print(f"\n{ok}/{total} checks PASS")
    if ok == total:
        print("Muro de citas quemadas OK — la cita retirada no vuelve, ni con respaldo; "
              "sin banco nada cambia.")
        return 0
    print("FALLA — el muro dejó de retirar una cita quemada o empezó a tocar citas buenas.")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
