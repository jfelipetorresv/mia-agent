# -*- coding: utf-8 -*-
"""Mia · test_barrido_de_patron.py — §21 del harness de litigio (2026-08-19).

EL DEFECTO QUE ESTA BARRERA PERSIGUE (caso real del despacho): Pipe señaló UN pasaje con un
defecto de postura; el barrido del documento entero encontró 32 ocurrencias del mismo
patrón. En otra corrida, corregir hallazgo por hallazgo costó CUATRO versiones completas del
escrito. Regla: ante un defecto señalado con un ejemplo, se barre el documento completo por
ese patrón en una sola pasada y se reportan todas sus ocurrencias.

QUÉ FIJA, en los DOS sentidos que exige la regla de implantación de Mia:
  R (REGRESIÓN, debe FALLAR la barrera vieja) · un defecto señalado UNA vez que en realidad
    está en cuatro lugares: el barrido los encuentra todos y lo dice con el número.
  C (CASO CORRECTO, debe PASAR) · un defecto que de verdad ocurre una sola vez no genera
    ruido: no hay barrido que reportar.
  P · el patrón se deriva por ROL y por ESTRUCTURA: una cita SANA (respaldada/sellada) no
    señala ningún patrón, y el cotejo es por secuencia contigua de tokens — «Ley 14» no
    puede casar dentro de «Ley 1437» (lección del P0 de sellos por subcadena).
  M · el defecto que señala el ABOGADO en prosa entra por el mismo mecanismo genérico.
  D · es AVISO y función PURA: señala todas las ocurrencias, no reescribe ninguna.

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


# El mismo defecto en cuatro capítulos distintos. El gate solo señaló el primero.
ESCRITO = "\n\n".join([
    "SEÑOR JUEZ",
    "Primero. El término se cuenta conforme al artículo 90 de la Ley 9999 de 2099.",
    "Segundo. Como quedó dicho, el artículo 90 de la Ley 9999 de 2099 fija el plazo.",
    "Tercero. La caducidad se rige por el artículo 164 de la Ley 1437 de 2011.",
    "Cuarto. Reiterando el artículo 90 de la Ley 9999 de 2099, la solicitud es oportuna.",
    "Quinto. Y por último, el artículo 90 de la Ley 9999 de 2099 cierra el punto.",
])

ESCRITO_UNA_VEZ = "\n\n".join([
    "SEÑOR JUEZ",
    "Primero. El término se cuenta conforme al artículo 90 de la Ley 9999 de 2099.",
    "Segundo. La caducidad se rige por el artículo 164 de la Ley 1437 de 2011.",
    "Tercero. El acto quedó en firme.",
])


def r_regresion() -> None:
    print("\n-- R · el defecto señalado una vez está en cuatro lugares --")
    defectos = [{"cita": "Ley 9999 de 2099", "estado": "anotada"}]
    res = B.barrido_de_patron(ESCRITO, defectos)
    check("r1 · hay barrido que reportar", isinstance(res, dict))
    patrones = (res or {}).get("patrones") or []
    check("r2 · un solo patrón derivado", len(patrones) == 1)
    check("r3 · encuentra las CUATRO ocurrencias, no solo la señalada",
          bool(patrones) and patrones[0]["ocurrencias"] == 4)
    check("r4 · cuenta 3 ocurrencias adicionales a la ya conocida",
          (res or {}).get("ocurrencias_adicionales") == 3)
    aviso = (res or {}).get("aviso", "")
    check("r5 · el aviso está en lenguaje del abogado y dice el número",
          "mismo problema" in aviso and "3 lugares" in aviso)
    check("r6 · el aviso es honesto: los SEÑALA, no promete haberlos reescrito",
          "señalados" in aviso)
    check("r7 · nace como AVISO", (res or {}).get("estado") == "aviso")


def c_caso_correcto() -> None:
    print("\n-- C · el defecto ocurre una sola vez: sin ruido --")
    defectos = [{"cita": "Ley 9999 de 2099", "estado": "anotada"}]
    check("c1 · no hay barrido que reportar",
          B.barrido_de_patron(ESCRITO_UNA_VEZ, defectos) is None)
    check("c2 · sin defectos señalados no se barre nada",
          B.barrido_de_patron(ESCRITO, []) is None)


def p_por_rol_y_estructura() -> None:
    print("\n-- P · el patrón se deriva por rol y se coteja por tokens contiguos --")
    sanas = [{"cita": "Ley 9999 de 2099", "estado": "respaldada"},
             {"cita": "Ley 1437 de 2011", "estado": "sellada"}]
    check("p1 · una cita SANA no señala ningún patrón (decisión por rol, no por texto)",
          B.barrido_de_patron(ESCRITO, sanas) is None)

    # Subcadena vs. token contiguo: «Ley 999» es prefijo textual de «Ley 9999».
    desc = B.descriptor_de_defecto({"cita": "Ley 999 de 2099", "estado": "anotada"})
    check("p2 · el descriptor existe", isinstance(desc, dict))
    check("p3 · NO casa por subcadena dentro de «Ley 9999 de 2099»",
          B.barrer(ESCRITO, desc) == [])
    desc_ok = B.descriptor_de_defecto({"cita": "Ley 9999 de 2099", "estado": "anotada"})
    check("p4 · sí casa la referencia completa", len(B.barrer(ESCRITO, desc_ok)) == 4)
    check("p5 · el cotejo ignora tildes y mayúsculas del OCR",
          len(B.barrer(ESCRITO.upper(), desc_ok)) == 4)
    check("p6 · un defecto sin cita ni pasaje entrecomillado no inventa patrón",
          B.descriptor_de_defecto({"texto": "esto está mal redactado"}) is None)


def m_motivo_del_abogado() -> None:
    print("\n-- M · el defecto que señala el abogado entra por el mismo mecanismo --")
    escrito = "\n\n".join([
        "Primero. Salvo mejor criterio, el término está vencido.",
        "Segundo. La notificación fue tardía.",
        "Tercero. Salvo mejor criterio, procede la excepción.",
    ])
    descs = B.descriptores_del_motivo(
        'No vuelvas a escribir "salvo mejor criterio": somos parte, no relator.')
    check("m1 · deriva el descriptor de lo entrecomillado", len(descs) == 1)
    check("m2 · la clase es de expresión, no de cita",
          bool(descs) and descs[0]["clase"] == "expresion")
    res = B.barrido_de_patron(escrito, descs)
    check("m3 · barre el escrito completo por la expresión del abogado",
          bool(res) and res["patrones"][0]["ocurrencias"] == 2)
    check("m4 · un motivo sin nada entrecomillado no deriva patrón",
          B.descriptores_del_motivo("no me gusta como quedó") == [])


def d_aviso_y_pureza() -> None:
    print("\n-- D · AVISO, pura y fail-soft --")
    copia = ESCRITO
    defectos = [{"cita": "Ley 9999 de 2099", "estado": "anotada"}]
    defectos_copia = [{"cita": "Ley 9999 de 2099", "estado": "anotada"}]
    res = B.barrido_de_patron(ESCRITO, defectos)
    check("d1 · no muta el escrito", ESCRITO == copia)
    check("d2 · no muta los defectos recibidos", defectos == defectos_copia)
    check("d3 · con texto vacío devuelve None", B.barrido_de_patron("", defectos) is None)
    check("d4 · el resultado es serializable (viaja en metadata)",
          all(isinstance(k, str) for k in (res or {})))
    muchos = [{"cita": f"Ley {i} de 2000", "estado": "anotada"} for i in range(50)]
    B.barrido_de_patron(ESCRITO, muchos)  # no debe reventar ni colgarse
    check("d5 · un aluvión de defectos no revienta el barrido", True)


def main() -> int:
    print("== §21 · BARRIDO DE PATRÓN — un ejemplo señalado se barre en todo el escrito ==")
    r_regresion()
    c_caso_correcto()
    p_por_rol_y_estructura()
    m_motivo_del_abogado()
    d_aviso_y_pureza()
    passed = sum(1 for _, ok in _results if ok)
    total = len(_results)
    print(f"\n{passed}/{total} checks PASS")
    if passed == total:
        print("§21 OK — el defecto señalado con un ejemplo se cuenta en todo el documento.")
        return 0
    print("§21 FAIL — el barrido no está encontrando lo que vino a encontrar.")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
