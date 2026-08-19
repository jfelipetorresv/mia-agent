# -*- coding: utf-8 -*-
"""Mia · test_contaminacion_expediente.py — barrera del principio #46.4 (2026-07-27).

EL DEFECTO QUE PERSIGUE (medido en el harness de litigio del despacho,
`check-partes-docx.py`): 5 de 16 escritos históricos traían el nombre de una aseguradora o
entidad de OTRO expediente — un párrafo de una entidad dentro del escrito de otra, una sección
titulada con la aseguradora equivocada. Radicar con la parte equivocada es riesgo procesal y
reputacional directo.

EN MIA ES PEOR QUE UN DEFECTO DE CALIDAD: es el dato de un cliente apareciendo en el escrito de
otro, o sea secreto profesional. Y hasta hoy nada lo vigilaba.

DIFERENCIA CON EL ORIGINAL: el del despacho lleva un catálogo de aseguradoras cableado. Aquí el
catálogo se DERIVA de la base del propio despacho (`documents.parte` de sus otros asuntos), así
que la barrera es agnóstica de jurisdicción y no hay lista que mantener.

QUÉ FIJA:
  A · detecta el nombre de una parte ajena en el escrito, con sus ocurrencias y contexto;
  B · NO avisa de las partes PROPIAS del asunto (sería ruido garantizado en cada escrito);
  C · no avisa por coincidencias parciales ni por nombres demasiado cortos/ambiguos;
  D · es AVISO: pura, no edita el borrador, fail-soft.

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


# Escenario calcado del defecto real: el escrito es del expediente de una entidad y se le
# cuela el nombre de la aseguradora de OTRO caso del despacho.
PROPIAS = ["Aseguradora del Norte", "Consorcio Ferreo del Valle"]
AJENAS = ["Nacional de Seguros", "Transmilenio", "Zurich"]

ESCRITO_CONTAMINADO = (
    "En el presente asunto, el Consorcio Ferreo del Valle incumplio el plazo pactado.\n"
    "La supervision requirio a la Aseguradora del Norte en su calidad de garante.\n"
    "Adicionalmente, Nacional de Seguros expidio la poliza de cumplimiento que ampara "
    "el contrato, y por ello debe responder.")

ESCRITO_LIMPIO = (
    "En el presente asunto, el Consorcio Ferreo del Valle incumplio el plazo pactado y la "
    "Aseguradora del Norte fue requerida como garante.")


def a_detecta() -> None:
    print("\n-- A · detecta la parte de OTRO expediente --")
    r = V.scan_foreign_parties(ESCRITO_CONTAMINADO, AJENAS, PROPIAS)
    check("A1 · encuentra exactamente la parte ajena que se colo", len(r) == 1)
    check("A2 · y la nombra", r and r[0]["parte"] == "Nacional de Seguros")
    check("A3 · cuenta las ocurrencias", r and r[0]["ocurrencias"] == 1)
    check("A4 · da contexto para ubicarla de un golpe",
          r and "poliza de cumplimiento" in r[0]["contexto"])

    # Varias menciones de la misma parte ajena: se agrupan, no se repiten.
    doble = ESCRITO_CONTAMINADO + " Nacional de Seguros no fue notificada."
    r2 = V.scan_foreign_parties(doble, AJENAS, PROPIAS)
    check("A5 · varias menciones de la misma parte ajena se agrupan en una entrada",
          len(r2) == 1 and r2[0]["ocurrencias"] == 2)

    # Dos partes ajenas distintas: en orden de aparición.
    dos = ("Transmilenio suscribio el contrato. Luego, Nacional de Seguros expidio la poliza.")
    r3 = V.scan_foreign_parties(dos, AJENAS, PROPIAS)
    check("A6 · dos partes ajenas distintas, en orden de aparicion",
          [d["parte"] for d in r3] == ["Transmilenio", "Nacional de Seguros"])


def b_no_avisa_de_las_propias() -> None:
    print("\n-- B · no avisa de las partes PROPIAS (seria ruido en cada escrito) --")
    r = V.scan_foreign_parties(ESCRITO_LIMPIO, AJENAS, PROPIAS)
    check("B1 · un escrito que solo nombra a sus propias partes no dispara nada", r == [])
    check("B2 · sin catalogo de partes ajenas, la barrera calla",
          V.scan_foreign_parties(ESCRITO_CONTAMINADO, [], PROPIAS) == []
          and V.scan_foreign_parties(ESCRITO_CONTAMINADO, None, PROPIAS) == [])
    # El caso legítimo que obliga a que esto sea AVISO y no muro: la misma aseguradora litiga
    # en dos casos del despacho. `party_names_for_contamination` ya la excluye de `ajenas`;
    # aquí se fija que, si aun así llegara, la salvaguarda por contención la respeta.
    r2 = V.scan_foreign_parties(
        "La Aseguradora del Norte Sucursal Sur comparecio al proceso.",
        ["Aseguradora del Norte"], ["Aseguradora del Norte Sucursal Sur"])
    check("B3 · si el nombre ajeno es un trozo de una parte PROPIA, no se avisa "
          "(«Aseguradora del Norte» dentro de «Aseguradora del Norte Sucursal Sur»)", r2 == [])


def c_sin_falsos_por_forma() -> None:
    print("\n-- C · sin falsos positivos por forma --")
    check("C1 · no dispara por coincidencia PARCIAL de palabra "
          "(«Zurich» no aparece en «Zurichense»)",
          V.scan_foreign_parties("La entidad Zurichense no es parte.", ["Zurich"], []) == [])
    check("C2 · un nombre demasiado corto/ambiguo no genera aviso "
          "(la barrera no puede avisar por «SA» o «ABC»)",
          V.scan_foreign_parties("La sociedad ABC comparecio.", ["ABC"], []) == [])
    check("C3 · insensible a tildes y mayusculas (el escrito y la ficha no siempre coinciden)",
          len(V.scan_foreign_parties("Segun NACIONAL DE SEGUROS, la poliza expiro.",
                                     ["Nacional de Seguros"], [])) == 1)
    check("C4 · entradas vacias o basura en el catalogo no producen avisos",
          V.scan_foreign_parties(ESCRITO_CONTAMINADO, [None, "", "  ", "a"], PROPIAS) == [])


def d_es_aviso() -> None:
    print("\n-- D · la barrera AVISA: pura, no edita, fail-soft --")
    copia = str(ESCRITO_CONTAMINADO)
    V.scan_foreign_parties(ESCRITO_CONTAMINADO, AJENAS, PROPIAS)
    check("D1 · no muta el borrador", ESCRITO_CONTAMINADO == copia)
    check("D2 · determinista",
          V.scan_foreign_parties(ESCRITO_CONTAMINADO, AJENAS, PROPIAS)
          == V.scan_foreign_parties(ESCRITO_CONTAMINADO, AJENAS, PROPIAS))
    check("D3 · borrador vacio o None no lanza",
          V.scan_foreign_parties("", AJENAS, PROPIAS) == []
          and V.scan_foreign_parties(None, AJENAS, PROPIAS) == [])
    check("D4 · el resultado es serializable (viaja en el informe a la pantalla)",
          all(set(d) == {"parte", "ocurrencias", "contexto"}
              for d in V.scan_foreign_parties(ESCRITO_CONTAMINADO, AJENAS, PROPIAS)))


def main() -> int:
    print("== Barrera · contaminacion entre expedientes ==")
    a_detecta()
    b_no_avisa_de_las_propias()
    c_sin_falsos_por_forma()
    d_es_aviso()

    ok = sum(1 for _, v in _results if v)
    total = len(_results)
    print(f"\n{ok}/{total} checks PASS")
    if ok == total:
        print("Contaminacion entre expedientes OK — detecta la parte ajena, calla ante las "
              "propias, y avisa sin bloquear.")
        return 0
    print("FALLA — la barrera dejo de ver la parte ajena o empezo a avisar de las propias.")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
