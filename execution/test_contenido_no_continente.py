# -*- coding: utf-8 -*-
"""Mia · test_contenido_no_continente.py — §23 del harness de litigio (2026-08-19).

EL DEFECTO QUE ESTA BARRERA PERSIGUE (el más grave encontrado en el harness): 17 de las 36
fuentes de un paquete traían un TEXTO QUE NO ERA DE LA NORMA QUE DECÍAN CITAR, con toda la
cadena de verificación en verde. Las fichas del corpus estaban bien; el defecto lo metía el
paso que copiaba al paquete, y se cotejaba el HASH del archivo —que coincidía— y jamás el
texto. Sellar el continente no es verificar el contenido.

Y su variante gemela: una providencia se citó como «sentencia de 2013» sin radicado, sala ni
ponente, porque el contrato del paquete no pedía esos datos. La regla se le exige a quien
puede cumplirla: la fuente entra con identificación mínima o entra con razón honesta.

QUÉ HABÍA ANTES EN MIA (medido leyendo el código, no supuesto):
  · `packs.source_pack_from_research` sellaba cada fuente con `chunk_hash` — el continente.
  · `verification._backing_source_tokenized` cotejaba la CITA (la referencia: «Ley 1437 de
    2011, artículo 138») contra las claves de la fuente: identidad del documento.
  · NADIE cotejaba el PASAJE que la fuente aporta contra el contenido del que dice salir, y
    ningún campo de `Fuente` era obligatorio salvo `referencia` y `chunk_hash`.
QUÉ SE AÑADIÓ: `barreras_harness.similitud` / `identificacion` / `revisar_fuentes`, llamadas
desde `graph._commit_research_sources` — o sea, ANTES de que la fuente llegue al redactor.

QUÉ FIJA, en los DOS sentidos que exige la regla de implantación de Mia:
  R (REGRESIÓN, debe FALLAR la barrera vieja) · una fuente cuyo hash coincide pero cuyo
    pasaje es de OTRA norma: se detecta y se nombra.
  C (CASO CORRECTO, debe PASAR) · una fuente cuyo pasaje sí sale de su contenido y trae su
    identificación completa: no genera ni un aviso.
  I · identificación mínima por CAMPO NOMBRADO (rol), nunca adivinando dentro de la cadena
    de la referencia.
  U · el umbral es el del harness (75 %) y es configurable.
  D · nace como AVISO: informa y no retira la fuente mientras el modo exigido esté apagado.

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


TEXTO_1437 = ("Artículo 138. Nulidad y restablecimiento del derecho. Toda persona que se "
              "crea lesionada en un derecho subjetivo amparado en una norma jurídica podrá "
              "pedir que se declare la nulidad del acto administrativo particular y se le "
              "restablezca el derecho.")

TEXTO_1755 = ("Artículo 14. Términos para resolver las distintas modalidades de peticiones. "
              "Salvo norma legal especial, toda petición deberá resolverse dentro de los "
              "quince días siguientes a su recepción.")

FUENTE_SANA = {
    "referencia": "Ley 1437 de 2011, artículo 138",
    "tipo": "ley", "numero": "1437", "fecha": "2011",
    "pasaje": ("Toda persona que se crea lesionada en un derecho subjetivo amparado en una "
               "norma jurídica podrá pedir que se declare la nulidad del acto "
               "administrativo particular"),
    "content": TEXTO_1437,
}

# El defecto de las 17/36: el hash del archivo cuadra, pero el pasaje es de OTRA norma.
FUENTE_CONTENIDO_AJENO = {
    "referencia": "Ley 1437 de 2011, artículo 138",
    "tipo": "ley", "numero": "1437", "fecha": "2011",
    "chunk_hash": "a" * 64,
    "pasaje": ("Salvo norma legal especial, toda petición deberá resolverse dentro de los "
               "quince días siguientes a su recepción"),
    "content": TEXTO_1437,
}

# La providencia «de 2013» sin radicado ni sala.
FUENTE_SIN_IDENTIFICACION = {
    "referencia": "sentencia de 2013",
    "pasaje": "La entidad debe motivar el acto",
    "content": "La entidad debe motivar el acto que impone la sanción.",
}


def r_regresion() -> None:
    print("\n-- R · el hash cuadra y el contenido es de otra norma --")
    res = B.revisar_fuentes([FUENTE_SANA, FUENTE_CONTENIDO_AJENO])
    check("r1 · la revisión reporta algo", isinstance(res, dict))
    fallos = [d["referencia"] for d in (res or {}).get("pasaje_no_coincide", [])]
    check("r2 · caza la fuente cuyo pasaje no sale de su contenido", len(fallos) == 1)
    check("r3 · la fuente sana no se denuncia",
          (res or {}).get("verificadas") == 1)
    aviso = (res or {}).get("aviso", "")
    check("r4 · el aviso está en lenguaje del abogado",
          "no corresponde a la norma que dicen citar" in aviso)
    razon = (res or {}).get("pasaje_no_coincide", [{}])[0].get("razon", "")
    check("r5 · la razón dice que el sello coincide y el contenido no",
          "sello" in razon.lower() and "contenido" in razon.lower())

    # La comprobación de fondo: el hash es idéntico y el texto no lo es.
    check("r6 · similitud por debajo del umbral en el caso ajeno",
          B.similitud(FUENTE_CONTENIDO_AJENO["pasaje"], TEXTO_1437) < 0.75)
    check("r7 · similitud alta en el caso legítimo",
          B.similitud(FUENTE_SANA["pasaje"], TEXTO_1437) >= 0.75)
    check("r8 · el pasaje ajeno SÍ sale de su verdadera norma (no es un detector ciego)",
          B.similitud(FUENTE_CONTENIDO_AJENO["pasaje"], TEXTO_1755) >= 0.75)


def c_caso_correcto() -> None:
    print("\n-- C · una fuente bien identificada y bien copiada no genera ruido --")
    check("c1 · fuente sana devuelve cobertura sin aviso", B.revisar_fuentes([FUENTE_SANA])["cobertura_completa"] and not B.revisar_fuentes([FUENTE_SANA])["aviso"])
    check("c2 · sin fuentes devuelve None", B.revisar_fuentes([]) is None)
    check("c3 · una fuente sin contenido no es un defecto: es no verificable",
          B.revisar_fuentes([{"referencia": "Ley 1437 de 2011", "tipo": "ley",
                              "numero": "1437", "fecha": "2011",
                              "pasaje": "algo"}])["no_verificables_total"] == 1)


def i_identificacion() -> None:
    print("\n-- I · identificación mínima por campo nombrado, no por adivinanza --")
    ident = B.identificacion(FUENTE_SIN_IDENTIFICACION)
    check("i1 · detecta que faltan los tres campos",
          set(ident["faltan"]) == {"tipo", "numero", "fecha"})
    check("i2 · la fuente sana está completa", B.identificacion(FUENTE_SANA)["faltan"] == [])
    check("i3 · acepta radicado como número",
          B.identificacion({"tipo": "sentencia", "radicado": "25000-23-41-000",
                            "fecha": "2013"})["faltan"] == [])
    check("i4 · lee también el sub-bloque `identificacion` de la ficha",
          B.identificacion({"identificacion": {"tipo": "decreto", "numero": "1082",
                                               "fecha": "2015"}})["faltan"] == [])
    check("i5 · NO adivina el número dentro de la cadena de la referencia",
          B.identificacion({"referencia": "Ley 1437 de 2011"})["faltan"] != [])

    res = B.revisar_fuentes([FUENTE_SIN_IDENTIFICACION])
    check("i6 · la revisión la reporta", isinstance(res, dict))
    check("i7 · con la razón honesta de por qué",
          "no es citable" in (res or {}).get("sin_identificacion", [{}])[0].get("razon", ""))


def u_umbral() -> None:
    print("\n-- U · el umbral es el del harness y es configurable --")
    from mia import config  # noqa: PLC0415 -- se lee aquí a propósito
    check("u1 · el umbral inicial es 75 % como en el harness",
          abs(config.MIA_FUENTE_SIMILITUD_UMBRAL - 0.75) < 1e-9)
    # Una copia con deriva: el pasaje viene de la norma correcta pero le metieron palabras
    # que la norma no tiene. Pasa el 75 % del harness y no pasa un 95 %.
    con_deriva = dict(FUENTE_SANA)
    con_deriva["pasaje"] = ("Toda persona natural o jurídica que se crea gravemente "
                            "lesionada en un derecho subjetivo suyo amparado en una norma "
                            "jurídica vigente podrá pedir que se declare la nulidad")
    check("u2 · con el umbral del harness la copia con deriva pasa",
          not B.revisar_fuentes([con_deriva])["pasaje_no_coincide"])
    res = B.revisar_fuentes([con_deriva], umbral=0.95)
    check("u3 · subir el umbral la caza y el umbral usado viaja en el informe",
          isinstance(res, dict) and res.get("umbral") == 0.95)
    check("u4 · bajarlo lo relaja",
          not B.revisar_fuentes([FUENTE_CONTENIDO_AJENO], umbral=0.05)["pasaje_no_coincide"])


def d_aviso() -> None:
    print("\n-- D · nace como AVISO: informa, no retira la fuente --")
    fuentes = [FUENTE_SANA, FUENTE_CONTENIDO_AJENO, FUENTE_SIN_IDENTIFICACION]
    res = B.revisar_fuentes(fuentes)
    check("d1 · el estado declarado es aviso", (res or {}).get("estado") == "aviso")
    check("d2 · ninguna fuente sale marcada como excluida",
          all(not d.get("excluida")
              for g in ("pasaje_no_coincide", "sin_identificacion")
              for d in (res or {}).get(g, [])))
    check("d3 · el filtro deja pasar TODAS las fuentes en modo aviso",
          len(B.filtrar_fuentes(fuentes, res)) == 3)

    duro = B.revisar_fuentes(fuentes, exigir=True)
    check("d4 · con `exigir` el estado cambia", (duro or {}).get("estado") == "exigido")
    check("d5 · y ahí sí la fuente defectuosa no entra",
          len(B.filtrar_fuentes(fuentes, duro)) < 3)
    check("d6 · el aviso duro dice que no entraron",
          "no entraron" in (duro or {}).get("aviso", ""))

    copia = dict(FUENTE_SANA)
    B.revisar_fuentes([FUENTE_SANA])
    check("d7 · no muta las fuentes recibidas", FUENTE_SANA == copia)
    check("d8 · datos basura no revientan la revisión",
          B.revisar_fuentes(["no soy un dict", None]) is None)


def main() -> int:
    print("== §23 · VERIFICAR EL CONTENIDO, NO EL CONTINENTE ==")
    r_regresion()
    c_caso_correcto()
    i_identificacion()
    u_umbral()
    d_aviso()
    passed = sum(1 for _, ok in _results if ok)
    total = len(_results)
    print(f"\n{passed}/{total} checks PASS")
    if passed == total:
        print("§23 OK — el pasaje se coteja contra su fuente, no solo contra su hash.")
        return 0
    print("§23 FAIL — el contenido sigue pasando por el sello del continente.")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
