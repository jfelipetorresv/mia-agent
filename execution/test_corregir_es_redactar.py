# -*- coding: utf-8 -*-
"""Mia · test_corregir_es_redactar.py — §19 del harness de litigio (2026-08-19).

EL DEFECTO QUE ESTA BARRERA PERSIGUE (caso real del despacho): aplicar las correcciones de
la primera pasada del gate introdujo SIETE errores nuevos en un escrito de 36.788 palabras,
y una reincidencia normativa apareció en texto que se había reescrito precisamente para
corregir el hallazgo anterior. Un gate que corre una sola vez no es un gate: el texto nuevo
que entra al corregir es exactamente igual de sospechoso que el original.

QUÉ FIJA, en los DOS sentidos que exige la regla de implantación de Mia:
  R (REGRESIÓN, debe FALLAR la barrera vieja) · una corrección que arregla la cita señalada
    pero mete otra sin respaldo: el defecto INTRODUCIDO se reporta, con su cita.
  C (CASO CORRECTO, debe PASAR) · una corrección limpia: se reconoce corregida y no se
    inventa ningún defecto introducido.
  A · el acotamiento es real: un defecto que vive en un pasaje NO tocado no se cuenta como
    introducido por la corrección (o el barrido §21 no tendría con qué distinguir).
  D · es AVISO y función PURA: no edita texto, no bloquea, fail-soft ante datos ausentes.

Salida: exit 0 = PASS · exit 1 = FAIL.
"""
from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "backend")))

from mia.agents import barreras_harness as B  # noqa: E402

_results: list[tuple[str, bool]] = []


def check(nombre: str, ok: bool) -> None:
    _results.append((nombre, bool(ok)))
    print(f"  [{'OK' if ok else 'XX'}]   {nombre}")


def _informe(*pares: tuple[str, str]) -> dict:
    """Un informe del verificador con sus citas ya clasificadas por ROL (estado)."""
    return {"citas": len(pares),
            "detalle": [{"cita": c, "estado": e} for c, e in pares]}


ENCABEZADO = "SEÑOR JUEZ\n\nDe la referencia."
PARRAFO_INTACTO = ("La caducidad del medio de control se rige por el término del artículo "
                   "164 de la Ley 1437 de 2011, aplicable al caso.")

ANTES = "\n\n".join([
    ENCABEZADO,
    "El acto se notificó por fuera del plazo del artículo 69 de la Ley 1755 de 2015.",
    PARRAFO_INTACTO,
])

# La corrección cambia SOLO el segundo párrafo: arregla la cita señalada (Ley 1755) y, al
# reescribir, mete una providencia nueva que nadie verificó. Es el defecto de §19.
DESPUES_CON_DEFECTO_NUEVO = "\n\n".join([
    ENCABEZADO,
    "El acto se notificó por fuera del plazo del artículo 67 de la Ley 1437 de 2011, "
    "como lo precisó la Sentencia C-341 de 2014.",
    PARRAFO_INTACTO,
])

DESPUES_LIMPIO = "\n\n".join([
    ENCABEZADO,
    "El acto se notificó por fuera del plazo del artículo 67 de la Ley 1437 de 2011.",
    PARRAFO_INTACTO,
])


def r_regresion() -> None:
    print("\n-- R · la corrección introduce un defecto nuevo (la barrera vieja no lo veía) --")
    informe_antes = _informe(("Ley 1755 de 2015", "anotada"),
                             ("Ley 1437 de 2011", "respaldada"))
    informe_despues = _informe(("Ley 1437 de 2011", "respaldada"),
                               ("Sentencia C-341 de 2014", "anotada"))
    res = B.segunda_pasada(ANTES, informe_antes, DESPUES_CON_DEFECTO_NUEVO, informe_despues)
    check("r1 · hay segunda pasada (el texto cambió)", isinstance(res, dict))
    intro = [d["cita"] for d in (res or {}).get("introducidos", [])]
    check("r2 · reporta la cita INTRODUCIDA por la corrección",
          "Sentencia C-341 de 2014" in intro)
    check("r3 · reconoce que la cita señalada SÍ quedó corregida",
          "Ley 1755 de 2015" in (res or {}).get("corregidos", []))
    check("r4 · acota: 1 solo pasaje reescrito, no el documento entero",
          (res or {}).get("pasajes") == 1)
    aviso = (res or {}).get("aviso", "")
    check("r5 · el aviso está en lenguaje del abogado y nombra el problema nuevo",
          "introdujo" in aviso and "C-341" in aviso)
    check("r6 · nace como AVISO", (res or {}).get("estado") == "aviso")


def c_caso_correcto() -> None:
    print("\n-- C · la corrección quedó bien: no se inventa ningún defecto --")
    informe_antes = _informe(("Ley 1755 de 2015", "anotada"),
                             ("Ley 1437 de 2011", "respaldada"))
    informe_despues = _informe(("Ley 1437 de 2011", "respaldada"))
    res = B.segunda_pasada(ANTES, informe_antes, DESPUES_LIMPIO, informe_despues)
    check("c1 · hay segunda pasada", isinstance(res, dict))
    check("c2 · CERO defectos introducidos", (res or {}).get("introducidos") == [])
    check("c3 · la corrección se reconoce",
          (res or {}).get("corregidos") == ["Ley 1755 de 2015"])
    check("c4 · sin defectos persistentes", (res or {}).get("persisten") == [])


def a_acotamiento() -> None:
    print("\n-- A · el acotamiento a los pasajes reescritos es real --")
    # Un defecto que vive en el párrafo INTACTO no lo introdujo la corrección.
    informe_antes = _informe(("Ley 1755 de 2015", "anotada"),
                             ("Ley 1437 de 2011", "anotada"))
    informe_despues = _informe(("Ley 1437 de 2011", "anotada"))
    res = B.segunda_pasada(ANTES, informe_antes, DESPUES_LIMPIO, informe_despues)
    intro = [d["cita"] for d in (res or {}).get("introducidos", [])]
    # 'Ley 1437 de 2011' aparece en el párrafo intacto Y en el reescrito: sí entró al
    # pasaje nuevo, así que se reporta — pero como PERSISTE, no como introducida.
    persist = [d["cita"] for d in (res or {}).get("persisten", [])]
    check("a1 · una cita que ya estaba mal antes NO se rotula como introducida",
          "Ley 1437 de 2011" not in intro)
    check("a2 · se rotula como persistente", "Ley 1437 de 2011" in persist)

    sin_cambio = B.segunda_pasada(ANTES, informe_antes, ANTES, informe_antes)
    check("a3 · sin cambios no hay segunda pasada que reportar", sin_cambio is None)

    parrafos = B.pasajes_modificados(ANTES, DESPUES_CON_DEFECTO_NUEVO)
    check("a4 · el diff marca exactamente un pasaje reescrito",
          len(parrafos) == 1 and parrafos[0]["tipo"] == "reescrito")
    agregado = B.pasajes_modificados(ANTES, ANTES + "\n\nPárrafo nuevo del abogado.")
    check("a5 · un párrafo agregado se marca como agregado",
          len(agregado) == 1 and agregado[0]["tipo"] == "agregado")


def d_aviso_y_pureza() -> None:
    print("\n-- D · AVISO, pura y fail-soft --")
    antes_copia = ANTES
    despues_copia = DESPUES_CON_DEFECTO_NUEVO
    informe = _informe(("Ley 1755 de 2015", "anotada"))
    informe_copia = {"citas": 1, "detalle": [{"cita": "Ley 1755 de 2015", "estado": "anotada"}]}
    B.segunda_pasada(ANTES, informe, DESPUES_CON_DEFECTO_NUEVO, informe)
    check("d1 · no muta los textos", ANTES == antes_copia and
          DESPUES_CON_DEFECTO_NUEVO == despues_copia)
    check("d2 · no muta el informe recibido", informe == informe_copia)
    check("d3 · sin informes previos no revienta",
          isinstance(B.segunda_pasada(ANTES, None, DESPUES_LIMPIO, None), dict))
    check("d4 · con textos vacíos devuelve None", B.segunda_pasada("", None, "", None) is None)
    res = B.segunda_pasada(ANTES, informe, DESPUES_LIMPIO, _informe())
    check("d5 · el resultado es serializable (viaja en metadata)",
          all(isinstance(k, str) for k in (res or {})))


def main() -> int:
    print("== §19 · CORREGIR ES REDACTAR — segunda pasada acotada a lo reescrito ==")
    r_regresion()
    c_caso_correcto()
    a_acotamiento()
    d_aviso_y_pureza()
    passed = sum(1 for _, ok in _results if ok)
    total = len(_results)
    print(f"\n{passed}/{total} checks PASS")
    if passed == total:
        print("§19 OK — el texto nuevo que entra al corregir se verifica como texto nuevo.")
        return 0
    print("§19 FAIL — la segunda pasada no está cazando lo que vino a cazar.")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
