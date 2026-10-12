"""
Mia · banco04_validar_jueces.py — validación de los jueces con mutaciones (§8.6, §10.2.11).

Mide la DECISIÓN FINAL DEL CIRCUITO COMPLETO, no solo la detección: cada salida mutada pasa por
el mismo camino que la medición real (cegado, segmentación, pasada 1 de Opus y Codex, alineación,
adjudicación de tres votos y discordancias).

Conjuntos (los escribe un agente distinto del autor de los prompts; viven CIFRADOS en la custodia
con el esquema `banco04-mutaciones/v1` del manifiesto — ver `docs/banco04-custodia-formato.md`):
  · ajuste    (≥ 30 defectos y ≥ 30 controles): depura los prompts; nunca habilita el circuito.
  · reservado (≥ 30 defectos, ≥ 10 de ellos C12 «cláusula falsa breve» con proporción < 0,20, y
              ≥ 30 controles), de UN SOLO USO y con el evaluador congelado (`--hash-congelado`).

Exigencias del reservado (todas obligatorias; si una falla, el circuito NO se usa y no se juzga la
línea base con él): sensibilidad final ≥ 0,95 · falsos positivos finales ≤ 0,10 · cada juez:
sensibilidad ≥ 0,90 y FP ≤ 0,10 · kappa ≥ 0,6 · sensibilidad en C12 ≥ 0,90 · fracción de defectos
vistos SOLO por Codex que la mayoría descartó ≤ 0,20 · ninguna salida sin evaluar.

UNIDAD DE MEDIDA: cada entrada de `verdad[]` (un ítem puede llevar varias). Regla aplicada aquí
(la `regla_de_deteccion` textual del conjunto vive en custodia y el director la coteja con esta):
  un DEFECTO queda detectado si al menos una unidad común que se solapa con su tramo
  [inicio, fin) del campo queda CONFIRMADA como defecto tras la adjudicación; un CONTROL es
  falso positivo si alguna unidad que se solapa con su tramo queda confirmada. Por juez: la
  unidad marcada como defecto por ese juez. Los tramos se reubican sobre el texto cegado.

Uso:
  .venv\\Scripts\\python.exe execution\\banco04_validar_jueces.py --conjunto-custodia ajuste --salida RUTA
  .venv\\Scripts\\python.exe execution\\banco04_validar_jueces.py --conjunto-custodia reservado \\
      --salida RUTA_FUERA_DEL_REPO --hash-congelado HEX --acreditacion-v13 RUTA \\
      --salida-banco RUTA --salida-custodia RUTA --version 0.4 --versiones-contador 0.4,0.3.3 \\
      --bloque 7
  (el registro de uso único vive en %LOCALAPPDATA%\\MIA-banco04-registro-uso: no se elige)
  (`--conjunto RUTA` lee un JSON descifrado; solo para pruebas fuera del repositorio.)
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import sys
import time
from fractions import Fraction
from pathlib import Path
from typing import Any, Callable, Iterable, Mapping

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from mia.eval.banco04 import ceguera, jueces  # noqa: E402
from mia.eval.banco04 import evaluador_congelado as EV  # noqa: E402
from mia.eval.banco04 import protocolo as P  # noqa: E402
from mia.eval.banco04.custodia import c08_admisible, fuentes_de_otro_ordenamiento  # noqa: E402
from mia.eval.banco04.segmentos import normalizar_saltos  # noqa: E402

FORMATO = "banco04-mutaciones/v1"
CATEGORIA_CLAUSULA_BREVE = "C12"   # invariante del manifiesto de custodia
_CLAVES_TOP = {"schema", "protocolo", "conjunto", "uso", "base", "regla_de_deteccion",
               "categorias", "items", "resumen"}
_CLAVES_ITEM = {"id", "jurisdicciones", "material", "salida", "verdad"}
_CLAVES_MATERIAL = {"mensaje_abogado", "documentos", "mapa_doc", "piezas_fuera_del_mapa",
                    "fuentes_corpus", "aviso_alcance"}
_CLAVES_VERDAD = {"id", "clase", "categoria", "campo", "inicio", "fin", "literal",
                  "estado_esperado", "estados_aceptables", "subtipo_esperado", "nota"}
_CLAVES_VERDAD_OPC = {"oracion", "proporcion_en_oracion", "original", "evidencia_del_error",
                      "respaldo"}


class ConjuntoInvalido(ValueError):
    pass


def _canon(obj: Any) -> bytes:
    return json.dumps(obj, sort_keys=True, ensure_ascii=False, separators=(",", ":")).encode("utf-8")


def huella_material(item: Mapping[str, Any]) -> str:
    return hashlib.sha256(_canon(item["material"])).hexdigest()


CATEGORIA_FUGA = "C08"   # invariante: sin ordenamiento configurado, o con fuente de OTRO (R2-C-N1)


def validar_conjunto(conjunto: Any, *, tipo_esperado: str | None = None,
                     otro: Mapping[str, Any] | None = None) -> list[dict]:
    """Comprobación estricta y local del formato (además de la del cargador de custodia), con
    dos invariantes: C08 solo en ítems sin ordenamiento configurado o configurados para OTRO
    ordenamiento con la fuente no habilitada en el material (R2-C-N1, `custodia.c08_admisible`),
    y materiales de ajuste y reservado disjuntos (`huella_material`) cuando se pasa `otro`.
    Falla cerrado."""
    if not isinstance(conjunto, dict) or set(conjunto) != _CLAVES_TOP:
        raise ConjuntoInvalido("claves de primer nivel")
    # Formato de CUSTODIA (§12.5): el conjunto se coteja contra PROTOCOLO_CUSTODIA, nunca
    # contra VERSION_PROTOCOLO (la v1.3 no tocó ningún artefacto custodiado).
    if conjunto["schema"] != FORMATO or conjunto["protocolo"] != P.PROTOCOLO_CUSTODIA:
        raise ConjuntoInvalido("formato o versión de custodia desconocidos")
    tipo = conjunto["conjunto"]
    if tipo not in ("ajuste", "reservado") or (tipo_esperado and tipo != tipo_esperado):
        raise ConjuntoInvalido("tipo de conjunto inválido")
    items = conjunto["items"]
    if not isinstance(items, list) or not items:
        raise ConjuntoInvalido("items vacío o no es lista")
    ids, n_def, n_ctrl, n_breve = set(), 0, 0, 0
    for it in items:
        if not isinstance(it, dict) or set(it) != _CLAVES_ITEM:
            raise ConjuntoInvalido("claves de item")
        if it["id"] in ids:
            raise ConjuntoInvalido(f"id repetido: {it['id']}")
        ids.add(it["id"])
        mat, sal = it["material"], it["salida"]
        if not isinstance(mat, dict) or set(mat) != _CLAVES_MATERIAL:
            raise ConjuntoInvalido(f"{it['id']}: material")
        if not isinstance(sal, dict) or set(sal) != {"diagnostico", "borrador"}:
            raise ConjuntoInvalido(f"{it['id']}: salida")
        if not isinstance(it["verdad"], list) or not it["verdad"]:
            raise ConjuntoInvalido(f"{it['id']}: verdad vacía")
        if not isinstance(it["jurisdicciones"], list):
            raise ConjuntoInvalido(f"{it['id']}: jurisdicciones")
        if (any(v.get("categoria") == CATEGORIA_FUGA for v in it["verdad"] if isinstance(v, dict))
                and not c08_admisible(it)):
            raise ConjuntoInvalido(f"{it['id']}: C08 (fuga) solo sin ordenamiento configurado o con "
                                   "una fuente de OTRO ordenamiento en el material (R2-C-N1)")
        tramos: dict[str, list[tuple[int, int]]] = {}
        for v in it["verdad"]:
            if not isinstance(v, dict) or not (_CLAVES_VERDAD <= set(v) <= _CLAVES_VERDAD | _CLAVES_VERDAD_OPC):
                raise ConjuntoInvalido(f"{it['id']}: claves de verdad")
            if v["clase"] not in ("defecto", "control") or v["campo"] not in sal:
                raise ConjuntoInvalido(f"{it['id']}/{v['id']}: clase o campo")
            if sal[v["campo"]][v["inicio"]:v["fin"]] != v["literal"]:
                raise ConjuntoInvalido(f"{it['id']}/{v['id']}: salida[campo][inicio:fin] != literal")
            for a, b in tramos.get(v["campo"], []):
                if v["inicio"] < b and v["fin"] > a:
                    raise ConjuntoInvalido(f"{it['id']}/{v['id']}: tramos solapados")
            tramos.setdefault(v["campo"], []).append((v["inicio"], v["fin"]))
            if v["clase"] == "defecto":
                n_def += 1
                if (v["categoria"] == CATEGORIA_CLAUSULA_BREVE
                        and isinstance(v.get("proporcion_en_oracion"), (int, float))
                        and v["proporcion_en_oracion"] < float(P.CLAUSULA_BREVE_FRACCION_MAX)):
                    n_breve += 1
            else:
                n_ctrl += 1
    if n_def < P.VALIDACION_MIN_DEFECTOS or n_ctrl < P.VALIDACION_MIN_CONTROLES:
        raise ConjuntoInvalido(f"tamaño insuficiente: {n_def} defectos, {n_ctrl} controles")
    if tipo == "reservado" and n_breve < P.VALIDACION_MIN_CLAUSULAS_BREVES_RESERVADO:
        raise ConjuntoInvalido(f"el reservado exige ≥ 10 cláusulas falsas breves C12 ({n_breve})")
    if otro is not None:
        if otro.get("conjunto") == tipo:
            raise ConjuntoInvalido("el otro conjunto es del mismo tipo")
        comunes = ({huella_material(i) for i in items}
                   & {huella_material(i) for i in otro.get("items") or []})
        if comunes:
            raise ConjuntoInvalido(f"ajuste y reservado no son disjuntos ({len(comunes)} materiales)")
    return items


def material_para_juez(material: Mapping[str, Any]) -> tuple[list, list, list]:
    """Material del conjunto → (expediente, mapa_docs, fuentes_corpus) del paquete del juez."""
    docs = {d["filename"]: list(d["chunks"]) for d in material["documentos"]}
    expediente = [{"pieza_id": fn, "nombre": fn, "texto": "\n".join(ch)} for fn, ch in docs.items()]
    mapa = []
    for n, ref in sorted(material["mapa_doc"].items(), key=lambda kv: int(kv[0])):
        doc, frag = ref["documento"], int(ref["fragmento"])
        if doc not in docs or not 0 <= frag < len(docs[doc]):
            raise ConjuntoInvalido(f"mapa_doc {n} apunta a un fragmento inexistente")
        mapa.append({"n": int(n), "pieza_id": doc, "fragmento_id": f"{doc}#{frag}",
                     "texto": docs[doc][frag]})
    # El `ref` va COMPLETO (`corpus:…`), igual que lo citan las salidas (`[corpus:…]`); el
    # cotejo normaliza los dos lados con `jueces.clave_corpus`.
    fuentes = [{"ref": f["ref"], "texto": f["texto"],
                **({"jurisdiccion": f["jurisdiccion"]} if f.get("jurisdiccion") else {})}
               for f in material["fuentes_corpus"]]
    return expediente, mapa, fuentes


def reubicar(cegado: str, inicio: int, fin: int, literal: str) -> tuple[int, int] | None:
    """Tramo del literal en el texto CEGADO. Los offsets del conjunto se calcularon sobre el texto
    previo a `normalizar_saltos` y al cegado: se usan solo si `cegado[inicio:fin] == literal`;
    si no, se reubica en la aparición más cercana. None = el literal no sobrevive al cegado."""
    literal = normalizar_saltos(literal)
    if cegado[inicio:fin] == literal:
        return inicio, fin
    pos, i = [], cegado.find(literal)
    while i >= 0:
        pos.append(i)
        i = cegado.find(literal, i + 1)
    if not pos:
        return None
    mejor = min(pos, key=lambda p: abs(p - inicio))
    return mejor, mejor + len(literal)


def comprobar_cegado(items: list[dict]) -> dict:
    """ANTES de juzgar: ¿cada literal de `verdad` sobrevive al cegado? Si alguno se pierde (p. ej.
    un identificador de pieza que el cegado toma por hash o UUID), el conjunto se RECHAZA: medir
    sin su verdad de referencia falsearía la sensibilidad."""
    total, perdidos = 0, []
    for it in items:
        cegados = {campo: ceguera.cegar_texto(it["salida"][campo],
                                              aviso_alcance=it["material"]["aviso_alcance"]).texto
                   for campo in ("diagnostico", "borrador")}
        for v in it["verdad"]:
            total += 1
            if reubicar(cegados[v["campo"]], v["inicio"], v["fin"], v["literal"]) is None:
                perdidos.append(f"{it['id']}/{v['id']}")
    out = {"literales": total, "sobreviven_al_cegado": total - len(perdidos), "perdidos": perdidos}
    if perdidos:
        raise ConjuntoInvalido(f"{len(perdidos)} literales de verdad no sobreviven al cegado: "
                               f"{perdidos[:10]}")
    return out


def evaluar_item(item: Mapping[str, Any], *, opus: jueces.Runner, codex: jueces.Runner,
                 llave: bytes, votante_factory: Callable | None = None,
                 partes: list[str] | None = None) -> dict:
    """Una salida mutada por el circuito completo; resultado por cada entrada de `verdad`."""
    mat = item["material"]
    expediente, mapa, fuentes = material_para_juez(mat)
    paquete, privado = ceguera.preparar_candidato(
        llave=llave, etiqueta_version="mutacion", case_id=item["id"], repeticion=1,
        diagnostico=item["salida"]["diagnostico"], borrador=item["salida"]["borrador"],
        mensaje_abogado=mat["mensaje_abogado"], expediente=expediente, mapa_docs=mapa,
        fuentes_corpus=fuentes, aviso_alcance=mat["aviso_alcance"],
        # I7 (v1.3): las jurisdicciones configuradas del ítem llegan al juez, igual que en medición.
        jurisdicciones_configuradas=list(item["jurisdicciones"]))
    material = jueces.Material.desde_paquete(paquete, partes=partes)
    votante = votante_factory(paquete, material) if votante_factory else None
    r = jueces.pasada1(paquete, material, opus=opus, codex=codex, votante=votante)
    segs = {s["id"]: s for s in privado["segmentos"]}
    verdades = []
    for v in item["verdad"]:
        base = {"item": item["id"], "id": v["id"], "categoria": v["categoria"],
                "es_defecto": v["clase"] == "defecto",
                "proporcion_en_oracion": v.get("proporcion_en_oracion")}
        if r["estado"] != "evaluada":
            verdades.append({**base, "estado": r["estado"]})
            continue
        span = reubicar(privado["texto_cegado"][v["campo"]], v["inicio"], v["fin"], v["literal"])
        if span is None:
            verdades.append({**base, "estado": "literal_perdido_al_cegar"})
            continue
        ls, le = span

        def _toca(u: Mapping[str, Any]) -> bool:
            s = segs[u["segmento"]]
            return s["seccion"] == v["campo"] and any(
                s["inicio"] + a < le and s["inicio"] + b > ls for a, b in u["tramos"])

        unidades = [u for u in r["unidades"] if _toca(u)]
        ids = {u["id"] for u in unidades}
        confirmada = any(d["unidad"] in ids and jueces.es_defecto_confirmado(d)
                         for d in r["decisiones"])
        opus_def = any(u["estado_a"] in P.ESTADOS_DEFECTO for u in unidades)
        codex_def = any(u["estado_b"] in P.ESTADOS_DEFECTO for u in unidades)
        verdades.append({**base, "estado": "evaluada", "detectado_final": confirmada,
                         "detectado_opus": opus_def, "detectado_codex": codex_def,
                         "solo_codex": codex_def and not opus_def,
                         "estado_opus_aceptable": any(u["estado_a"] in v["estados_aceptables"]
                                                      for u in unidades)})
    rechazos = [f"{juez}:{e['codigo']}" for juez in ("opus", "codex")
                for intento in (r.get(juez) or {}).get("intentos") or []
                for e in intento.get("errores") or []]
    return {"item": item["id"], "estado": r["estado"], "verdades": verdades, "rechazos": rechazos,
            "pares_kappa": r.get("pares_kappa") or [],
            "discordancias": len(r.get("discordancias_sin_resolver") or [])}


def _tasa(num: int, den: int) -> Fraction | None:
    return Fraction(num, den) if den else None


def _es_breve(r: Mapping[str, Any]) -> bool:
    return r.get("categoria") == CATEGORIA_CLAUSULA_BREVE


def evaluar_exigencias(resultados: list[dict], *, tipo: str, discordancias: int,
                       pares_kappa: list | None = None, acreditacion: Mapping[str, Any] | None = None,
                       consumo: Mapping[str, Any] | None = None) -> dict:
    """Exigencias de §8.6 sobre los resultados POR ENTRADA DE VERDAD. Determinista (gate N5).
    Un defecto no evaluado cuenta como NO detectado y un control no evaluado como falso positivo
    (lo que no se pudo juzgar no ayuda al circuito).

    Además (ronda 2 de Astra), para habilitar el circuito:
      · R2-C-N1: la acreditación de compatibilidad v1.3 del material reservado, VERIFICADA
        (`verificar_acreditacion`: `{"ok": True, ...}`). Sin ella, o inválida, no se habilita;
      · R2-B-I5: el consumo de TODO el circuito, leído del contador COMPARTIDO, es certificable
        (`consumo["cota_calculable"] is True`). Sin contador o con consumo sin cota, no se habilita."""
    defectos = [r for r in resultados if r["es_defecto"]]
    controles = [r for r in resultados if not r["es_defecto"]]
    no_eval = [r["id"] for r in resultados if r.get("estado") != "evaluada"]
    ev_d = [r for r in defectos if r.get("estado") == "evaluada"]
    ev_c = [r for r in controles if r.get("estado") == "evaluada"]
    falta_c = len(controles) - len(ev_c)
    sens = _tasa(sum(r["detectado_final"] for r in ev_d), len(defectos))
    fp = _tasa(sum(r["detectado_final"] for r in ev_c) + falta_c, len(controles))
    sens_o = _tasa(sum(r["detectado_opus"] for r in ev_d), len(defectos))
    fp_o = _tasa(sum(r["detectado_opus"] for r in ev_c) + falta_c, len(controles))
    sens_x = _tasa(sum(r["detectado_codex"] for r in ev_d), len(defectos))
    fp_x = _tasa(sum(r["detectado_codex"] for r in ev_c) + falta_c, len(controles))
    solo_x = [r for r in ev_d if r["solo_codex"]]
    descarte_x = _tasa(sum(not r["detectado_final"] for r in solo_x), len(solo_x))
    breves = [r for r in defectos if _es_breve(r)]
    sens_b = _tasa(sum(r.get("detectado_final", False) for r in breves), len(breves))
    if pares_kappa is None:
        pares_kappa = [p for r in resultados if r.get("estado") == "evaluada"
                       for p in r.get("pares_kappa") or []]
    kappa = jueces.evaluar_kappa([tuple(p) for p in pares_kappa], conjunto="reservado")
    exig = {
        "sensibilidad_final": (sens, sens is not None and sens >= P.SENSIBILIDAD_CIRCUITO_MIN),
        "falsos_positivos_finales": (fp, fp is not None and fp <= P.FALSOS_POSITIVOS_CIRCUITO_MAX),
        "sensibilidad_opus": (sens_o, sens_o is not None and sens_o >= P.SENSIBILIDAD_JUEZ_MIN),
        "falsos_positivos_opus": (fp_o, fp_o is not None and fp_o <= P.FALSOS_POSITIVOS_JUEZ_MAX),
        "sensibilidad_codex": (sens_x, sens_x is not None and sens_x >= P.SENSIBILIDAD_JUEZ_MIN),
        "falsos_positivos_codex": (fp_x, fp_x is not None and fp_x <= P.FALSOS_POSITIVOS_JUEZ_MAX),
        "descarte_mayoria_solo_codex": (descarte_x, descarte_x is None
                                        or descarte_x <= P.DESCARTE_SOLO_CODEX_MAX),
        "sensibilidad_clausula_breve": (sens_b, sens_b is not None
                                        and sens_b >= P.SENSIBILIDAD_CLAUSULA_BREVE_MIN),
        "kappa": (kappa.get("kappa"), bool(kappa.get("cuenta_como_minimo"))),
        "salidas_sin_evaluar": (len(no_eval), not no_eval),
        # I6: una discordancia material sin resolver impide usar el circuito (§8.5, §8.6).
        "discordancias_sin_resolver": (int(discordancias), int(discordancias) == 0),
        # R2-C-N1: material reservado acreditado compatible con v1.3 (casos, claves, mutaciones y
        # evaluador ligados por hash; cobertura de fugas, incluida la de OTRO ordenamiento).
        "acreditacion_compatibilidad_v13": (
            (acreditacion or {}).get("motivos") if acreditacion is not None else "ausente",
            isinstance(acreditacion, Mapping) and acreditacion.get("ok") is True),
        # R2-B-I5: el consumo del circuito (contador compartido) es certificable.
        "consumo_certificable": (
            (consumo or {}).get("resumen") if consumo is not None else "sin_contador",
            isinstance(consumo, Mapping) and consumo.get("cota_calculable") is True),
    }
    utilizable = all(ok for _, ok in exig.values())
    return {
        "tipo": tipo,
        "exigencias": {k: {"valor": (round(float(v), 4) if isinstance(v, Fraction) else v),
                           "cumple": ok} for k, (v, ok) in exig.items()},
        "circuito_utilizable": utilizable if tipo == "reservado" else False,
        "nota": (None if tipo == "reservado" else
                 "conjunto de ajuste: sirve para depurar prompts; nunca habilita el circuito"),
        "resumen": {"n_defectos": len(defectos), "n_controles": len(controles),
                    "n_clausulas_breves": len(breves), "n_solo_codex": len(solo_x),
                    "no_evaluadas": no_eval,
                    "solo_codex_descartados": [r["id"] for r in solo_x if not r["detectado_final"]]},
        "kappa": {k: (str(v) if isinstance(v, Fraction) else v) for k, v in kappa.items()},
    }


def consumo_del_circuito(control: jueces.ControlCuotaJueces | None) -> dict | None:
    """R2-B-I5: el consumo del circuito leído del CONTADOR COMPARTIDO (relee del disco todo lo que
    gastaron producción, aprobaciones y juicio de las versiones del bloque), no de memoria."""
    if control is None:
        return None
    c = control.ledger.contador()
    desconocidos = [i["id"] for i in control.intentos if i.get("estado") == "desconocido"]
    return {"cota_calculable": bool(c.cota_calculable) and not desconocidos,
            "intentos_desconocidos": desconocidos, "resumen": c.resumen()}


def validar_circuito(items: list[dict], *, opus: jueces.Runner, codex: jueces.Runner,
                     llave: bytes, tipo: str, votante_factory: Callable | None = None,
                     control: jueces.ControlCuotaJueces | None = None,
                     acreditacion: Mapping[str, Any] | None = None) -> dict:
    if tipo == "reservado":
        # R2-B-I5: el reservado solo se juzga con los runners ATADOS al contador compartido.
        if (control is None or getattr(opus, "control", None) is not control
                or getattr(codex, "control", None) is not control):
            raise ValueError("R2-B-I5: el reservado exige que Opus y Codex usen el MISMO control "
                             "de cuota del contador compartido")
    cegado = comprobar_cegado(items)
    por_item = [evaluar_item(it, opus=opus, codex=codex, llave=llave,
                             votante_factory=votante_factory) for it in items]
    resultados = [v for x in por_item for v in x["verdades"]]
    pares = [p for x in por_item if x["estado"] == "evaluada" for p in x["pares_kappa"]]
    discord = sum(int(x.get("discordancias") or 0) for x in por_item)
    out = evaluar_exigencias(resultados, tipo=tipo, discordancias=discord, pares_kappa=pares,
                             acreditacion=acreditacion, consumo=consumo_del_circuito(control))
    out["cegado"] = cegado
    out["resultados"] = resultados
    conteo: dict[str, int] = {}
    for x in por_item:
        for c in x["rechazos"]:
            conteo[c] = conteo.get(c, 0) + 1
    # Para que el director vea la tasa de rechazo del validador (p. ej. posiciones mal contadas en
    # salidas largas) ANTES de gastar el reservado.
    out["rechazos_por_codigo"] = dict(sorted(conteo.items(), key=lambda kv: -kv[1]))
    out["por_item"] = [{k: v for k, v in x.items() if k not in ("verdades", "pares_kappa")}
                       for x in por_item]
    return out


def _bajo_repo(ruta: Path) -> bool:
    try:
        ruta.resolve().relative_to(ROOT.resolve())
        return True
    except ValueError:
        return False


ENV_CUSTODIA = "MIA_BANCO04_CUSTODIA"
SUBDIR_REGISTRO_USO = "registro-uso"
# R2-C-I9: raíz PERMANENTE del registro de uso, independiente de dónde esté el material: no sale de
# MIA_BANCO04_CUSTODIA (que cambia si la custodia se reubica) sino del perfil local del usuario de
# Windows (%LOCALAPPDATA%), con un nombre fijo que ninguna opción ni variable del banco elige.
ENV_RAIZ_PERMANENTE = "LOCALAPPDATA"
DIR_REGISTRO_PERMANENTE = "MIA-banco04-registro-uso"


class ReservadoYaUsado(RuntimeError):
    pass


def identidad_sellada_reservado(manifiesto: Mapping[str, Any]) -> str:
    """Identidad SELLADA del reservado: el sha256 EN CLARO del artefacto `mutaciones_reservadas`
    del manifiesto del repositorio (R2-C-I9: el CONTENIDO, no su ubicación, ni su cifrado — un
    re-cifrado con otro nonce no fabrica un reservado nuevo —, ni su id)."""
    arts = [a for a in manifiesto.get("artefactos") or [] if a.get("tipo") == "mutaciones_reservadas"]
    if len(arts) != 1:
        raise SystemExit("el manifiesto no declara exactamente un conjunto reservado")
    claro = arts[0].get("sha256_claro")
    if not isinstance(claro, str) or not re.fullmatch(r"[0-9a-f]{64}", claro):
        raise SystemExit("el artefacto reservado del manifiesto está incompleto")
    return hashlib.sha256(f"banco04-reservado|{claro}".encode()).hexdigest()


def raiz_registro_uso(environ: Mapping[str, str] | None = None) -> Path:
    """Raíz PERMANENTE del registro (R2-C-I9). Falla cerrado si no hay perfil local, si cae bajo
    el repositorio o DENTRO de la carpeta de custodia (que puede reubicarse)."""
    entorno = os.environ if environ is None else environ
    base = (entorno.get(ENV_RAIZ_PERMANENTE) or "").strip()
    if not base:
        raise SystemExit(f"{ENV_RAIZ_PERMANENTE} no está definida: no hay raíz permanente del "
                         "registro de uso del reservado")
    raiz = Path(base) / DIR_REGISTRO_PERMANENTE
    if _bajo_repo(raiz):
        raise SystemExit("el registro de uso no puede vivir bajo el repositorio")
    cust = (entorno.get(ENV_CUSTODIA) or "").strip()
    if cust:
        try:
            raiz.resolve().relative_to(Path(cust).resolve())
            raise SystemExit("el registro de uso no puede vivir dentro de la custodia (se reubica)")
        except ValueError:
            pass
    return raiz


def ruta_registro_uso(identidad: str, environ: Mapping[str, str] | None = None) -> Path:
    """Marca CANÓNICA del reservado en la raíz permanente: `reservado-<identidad>.usado`."""
    if not re.fullmatch(r"[0-9a-f]{64}", identidad or ""):
        raise SystemExit("identidad sellada inválida")
    return raiz_registro_uso(environ) / f"reservado-{identidad}.usado"


def _marca_custodia(identidad: str, entorno: Mapping[str, str]) -> Path | None:
    """Marca SECUNDARIA en la custodia (la de la ronda 1). Se comprueba y se escribe además de la
    permanente: borrar o cambiar UNA de las dos no basta para repetir."""
    carpeta = (entorno.get(ENV_CUSTODIA) or "").strip()
    if not carpeta or _bajo_repo(Path(carpeta)):
        return None
    return Path(carpeta) / SUBDIR_REGISTRO_USO / f"reservado-{identidad}.usado"


def marcar_uso_unico(identidad: str, environ: Mapping[str, str] | None = None, *,
                     huellas: Iterable[str] = ()) -> Path:
    """Marca de un solo uso del reservado, escrita ANTES de juzgar y conservada aunque la
    validación falle después (§8.6: el usado ya no es reservado). R2-C-I9: vive en la raíz
    PERMANENTE (no depende de MIA_BANCO04_CUSTODIA) y lleva las huellas del MATERIAL de cada ítem:
    se rechaza la misma identidad, y también un reservado «nuevo» que reutilice material ya usado.
    Falla si ya existe."""
    entorno = os.environ if environ is None else environ
    marca = ruta_registro_uso(identidad, entorno)
    huellas = sorted(set(huellas))
    secundaria = _marca_custodia(identidad, entorno)
    if secundaria is not None and secundaria.exists():
        raise ReservadoYaUsado("el conjunto reservado YA se usó (marca en la custodia)")
    marca.parent.mkdir(parents=True, exist_ok=True)
    for previa in sorted(marca.parent.glob("reservado-*.usado")):
        try:
            usadas = set(json.loads(previa.read_text(encoding="utf-8")).get("huellas_material") or [])
        except (OSError, ValueError):
            raise ReservadoYaUsado(f"marca de uso ilegible ({previa.name}): falla cerrado")
        if usadas & set(huellas):
            raise ReservadoYaUsado("el reservado reutiliza material de un reservado ya usado "
                                   f"({len(usadas & set(huellas))} ítems): hace falta material nuevo")
    contenido = json.dumps({"identidad_sellada": identidad, "protocolo": P.VERSION_PROTOCOLO,
                            "protocolo_custodia": P.PROTOCOLO_CUSTODIA, "huellas_material": huellas,
                            "marcado": time.strftime("%Y-%m-%dT%H:%M:%S")})
    try:
        with open(marca, "x", encoding="utf-8") as fh:
            fh.write(contenido)
    except FileExistsError:
        raise ReservadoYaUsado("el conjunto reservado YA se usó: corregir exige un reservado "
                               "nuevo (§8.6)")
    if secundaria is not None:
        secundaria.parent.mkdir(parents=True, exist_ok=True)
        with open(secundaria, "x", encoding="utf-8") as fh:
            fh.write(contenido)
    return marca


# ════════════════════════════════════════════════════════════════════════════════════════
# R2-C-N1 · Acreditación de compatibilidad v1.3 del material reservado
# ════════════════════════════════════════════════════════════════════════════════════════
FORMATO_ACREDITACION = "banco04-acreditacion-compatibilidad/v1"
_CLAVES_ACREDITACION = {"schema", "protocolo", "autor", "autor_independiente", "fecha",
                        "hash_evaluador", "identidad_reservado", "artefactos", "veredicto",
                        "cobertura"}
TIPOS_ACREDITADOS = ("caso", "clave", "mutaciones_ajuste", "mutaciones_reservadas")
CLASES_COBERTURA_V13 = ("fuga_sin_ordenamiento", "fuga_otro_ordenamiento", "negacion_ajena",
                        "control_descriptivo")


def _oracion(texto: str, ini: int, fin: int) -> str:
    return EV._oracion_de(texto, ini, fin)


def _negacion_ajena(texto: str, ini: int, fin: int) -> bool:
    """El tramo [ini, fin) contiene una cita cuya ORACIÓN trae una negación (la regla del
    producto la daría por negada) pero cuya CLÁUSULA no (la cita sigue siendo uso: fuga)."""
    for c in EV.scan_citations(texto, EV.compile_patterns(None)):
        if c["end"] <= ini or c["start"] >= fin:
            continue
        oracion = EV._normalize(_oracion(texto, c["start"], c["end"]))
        if any(p in oracion for p in EV._NEGATION_NORM) and not EV._mencion_negada(
                texto, c["start"], c["end"]):
            return True
    return False


def _cumple_clase(clase: str, item: Mapping[str, Any], v: Mapping[str, Any]) -> bool:
    texto = item["salida"][v["campo"]]
    otras = fuentes_de_otro_ordenamiento(item)
    if clase == "fuga_sin_ordenamiento":
        return v["clase"] == "defecto" and v.get("categoria") == CATEGORIA_FUGA \
            and item["jurisdicciones"] == []
    if clase == "fuga_otro_ordenamiento":
        return v["clase"] == "defecto" and v.get("categoria") == CATEGORIA_FUGA \
            and item["jurisdicciones"] != [] and bool(otras)
    if clase == "negacion_ajena":
        return v["clase"] == "defecto" and v.get("categoria") == CATEGORIA_FUGA \
            and _negacion_ajena(texto, v["inicio"], v["fin"])
    if clase == "control_descriptivo":
        oracion = _oracion(texto, v["inicio"], v["fin"])
        return v["clase"] == "control" and bool(otras) and any(
            jueces.clave_corpus(r) and jueces.clave_corpus(r) in oracion for r in otras)
    return False


def verificar_acreditacion(acreditacion: Any, *, manifiesto: Mapping[str, Any],
                           items: list[dict], hash_evaluador: Mapping[str, Any]) -> dict:
    """R2-C-N1 · ¿El material reservado está acreditado como compatible con v1.3? La acreditación
    la escribe un AUTOR INDEPENDIENTE (este código no la produce: solo la exige y la coteja).

    Vinculaciones exigidas (todas):
      · formato `banco04-acreditacion-compatibilidad/v1`, protocolo = VERSION_PROTOCOLO (v1.3),
        autor declarado e independiente, veredicto `compatible`;
      · `hash_evaluador` = hash COMBINADO del evaluador v1.3 en ejecución (incluye este validador);
      · `identidad_reservado` = identidad sellada del reservado del manifiesto;
      · `artefactos` = {id: sha256_claro} de TODOS los casos, claves y conjuntos de mutaciones del
        manifiesto, exactamente;
      · `cobertura`: para cada clase de `CLASES_COBERTURA_V13`, al menos el mínimo de
        `protocolo.ACREDITACION_V13_MINIMOS` entradas «ITEM/VERDAD» distintas que EXISTEN en el
        reservado cargado y cumplen la clase de forma comprobable: fuga sin ordenamiento; fuga en un
        despacho configurado para OTRO ordenamiento con la fuente no habilitada en el material;
        negación ajena (la oración niega otra cosa y la cita sigue siendo uso); control descriptivo
        (un control cuya oración cita la fuente no habilitada).
    Devuelve {"ok", "motivos", "cobertura_verificada", "sha256"}."""
    motivos: list[str] = []
    if not isinstance(acreditacion, Mapping) or set(acreditacion) != _CLAVES_ACREDITACION:
        return {"ok": False, "motivos": ["acreditacion_ausente_o_claves_invalidas"],
                "cobertura_verificada": {}, "sha256": None}
    a = acreditacion
    huella = hashlib.sha256(_canon(dict(a))).hexdigest()
    if a["schema"] != FORMATO_ACREDITACION:
        motivos.append("formato_desconocido")
    if a["protocolo"] != P.VERSION_PROTOCOLO:
        motivos.append("no_es_de_la_version_del_protocolo")
    if not (isinstance(a["autor"], str) and a["autor"].strip()) or a["autor_independiente"] is not True:
        motivos.append("autor_no_declarado_independiente")
    if a["veredicto"] != "compatible":
        motivos.append("veredicto_no_compatible")
    if a["hash_evaluador"] != hash_evaluador.get("combinado"):
        motivos.append("hash_evaluador_distinto_del_v13_en_ejecucion")
    try:
        ident = identidad_sellada_reservado(manifiesto)
    except SystemExit as exc:
        ident, _ = None, motivos.append(f"manifiesto:{exc}")
    if a["identidad_reservado"] != ident:
        motivos.append("identidad_del_reservado_distinta")
    esperados = {x["id"]: x.get("sha256_claro") for x in manifiesto.get("artefactos") or []
                 if x.get("tipo") in TIPOS_ACREDITADOS}
    if not esperados or a["artefactos"] != esperados:
        motivos.append("hashes_de_casos_claves_o_mutaciones_no_coinciden")
    por_ref = {f"{it['id']}/{v['id']}": (it, v) for it in items for v in it["verdad"]}
    cob = a["cobertura"] if isinstance(a["cobertura"], Mapping) else {}
    verificada: dict[str, int] = {}
    for clase in CLASES_COBERTURA_V13:
        refs = cob.get(clase)
        if not isinstance(refs, list) or len(set(map(str, refs))) != len(refs):
            motivos.append(f"cobertura_mal_formada:{clase}")
            verificada[clase] = 0
            continue
        malas = [r for r in refs if r not in por_ref or not _cumple_clase(clase, *por_ref[r])]
        verificada[clase] = len(refs) - len(malas)
        if malas:
            motivos.append(f"cobertura_no_comprobable:{clase}:{malas[:5]}")
        if verificada[clase] < P.ACREDITACION_V13_MINIMOS[clase]:
            motivos.append(f"cobertura_insuficiente:{clase}:{verificada[clase]}"
                           f"<{P.ACREDITACION_V13_MINIMOS[clase]}")
    return {"ok": not motivos, "motivos": motivos, "cobertura_verificada": verificada,
            "sha256": huella}


def control_de_cuota(*, salida: Path, version: str, bloque: int, prefijo: str,
                     salida_custodia: Path, versiones: tuple) -> jueces.ControlCuotaJueces:
    """I5 / R2-B-I5: control de cuota de los jueces sobre el contador COMPARTIDO del runner
    (`run_banco04.LedgerJuicio`, del otro agente: se usa, no se modifica), OBLIGATORIAMENTE con:
      · la salida custodiada del bloque (donde viven las salidas reservadas y su consumo);
      · las versiones que suman contra el MISMO techo (la propia incluida; en el Bloque 7, las dos
        versiones: 0.4 y la re-producción de 0.3.3)."""
    versiones = tuple(versiones or ())
    if salida_custodia is None:
        raise SystemExit("R2-B-I5: falta --salida-custodia (el contador debe sumar lo custodiado)")
    if not versiones or version not in versiones or len(set(versiones)) != len(versiones):
        raise SystemExit("R2-B-I5: --versiones-contador debe listar las versiones del bloque, "
                         "incluida la propia")
    if bloque == 7 and len(versiones) < 2:
        raise SystemExit("R2-B-I5: en el Bloque 7 suman las DOS versiones (0.4 y 0.3.3)")
    sys.path.insert(0, str(ROOT / "execution"))
    import run_banco04 as rb  # noqa: PLC0415
    ledger = rb.LedgerJuicio(salida, version,
                             nuevo_contador=lambda: rb.contador_desde_protocolo(P, bloque),
                             salida_custodia=Path(salida_custodia), versiones=versiones)
    return jueces.ControlCuotaJueces(ledger=ledger, etapa="validacion", prefijo=prefijo)


def _cargar(a: argparse.Namespace) -> tuple[dict, dict | None]:  # noqa: C901
    """(conjunto, otro_conjunto). Desde la custodia: el claro queda solo en memoria."""
    if a.conjunto_custodia:
        from mia.eval.banco04 import custodia  # noqa: PLC0415 — perezoso a propósito
        otro_nombre = "reservado" if a.conjunto_custodia == "ajuste" else "ajuste"
        with custodia.abrir(custodia.PROPOSITO_MEDICION) as c:
            return c.mutaciones(a.conjunto_custodia), c.mutaciones(otro_nombre)
    # Un conjunto leído de un archivo nunca es el reservado sellado (I9).
    if _bajo_repo(a.conjunto):
        raise SystemExit("un conjunto descifrado no puede leerse desde el repositorio")
    return json.loads(a.conjunto.read_text(encoding="utf-8")), None


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Validación de los jueces con mutaciones (§8.6)")
    fuente = ap.add_mutually_exclusive_group(required=True)
    fuente.add_argument("--conjunto-custodia", choices=("ajuste", "reservado"))
    fuente.add_argument("--conjunto", type=Path)
    ap.add_argument("--salida", required=True, type=Path)
    ap.add_argument("--hash-congelado")
    ap.add_argument("--salida-banco", required=True, type=Path,
                    help="raíz de salida del runner (contador y ledger del circuito, I5)")
    ap.add_argument("--version", required=True, help="versión del ledger del runner")
    ap.add_argument("--bloque", required=True, type=int, choices=(0, 7))
    ap.add_argument("--salida-custodia", required=True, type=Path,
                    help="salida custodiada del runner (R2-B-I5: el contador la suma)")
    ap.add_argument("--versiones-contador", required=True,
                    help="versiones que suman contra el mismo techo, separadas por coma (R2-B-I5)")
    ap.add_argument("--acreditacion-v13", type=Path,
                    help="acreditación de compatibilidad v1.3 del reservado (R2-C-N1; autor "
                         "independiente)")
    a = ap.parse_args(argv)
    versiones = tuple(v for v in a.versiones_contador.split(",") if v)
    conjunto, otro = _cargar(a)
    items = validar_conjunto(conjunto, otro=otro)
    tipo = conjunto["conjunto"]
    comprobar_cegado(items)  # antes de gastar cuota y antes de marcar el reservado como usado
    control = control_de_cuota(salida=a.salida_banco, version=a.version, bloque=a.bloque,
                               prefijo=f"validacion-{tipo}", salida_custodia=a.salida_custodia,
                               versiones=versiones)
    acreditacion = None
    if tipo == "reservado":
        if not a.conjunto_custodia or not a.hash_congelado:
            raise SystemExit("el reservado solo se valida desde la custodia y con --hash-congelado")
        if _bajo_repo(a.salida):
            raise SystemExit("el resultado crudo del reservado vive en custodia, no en el repo")
        congelado = jueces.verificar_congelado(a.hash_congelado)
        from mia.eval.banco04 import custodia  # noqa: PLC0415
        manifiesto = custodia.cargar_manifiesto()
        if a.acreditacion_v13 is None:
            raise SystemExit("R2-C-N1: el reservado no se usa sin --acreditacion-v13")
        acreditacion = verificar_acreditacion(
            json.loads(a.acreditacion_v13.read_text(encoding="utf-8")), manifiesto=manifiesto,
            items=items, hash_evaluador=congelado)
        if not acreditacion["ok"]:
            # Antes de marcar el uso: una acreditación inválida no gasta el reservado.
            raise SystemExit(f"R2-C-N1: acreditación v1.3 inválida: {acreditacion['motivos']}")
        marcar_uso_unico(identidad_sellada_reservado(manifiesto),
                         huellas=[huella_material(i) for i in items])
    out = validar_circuito(items, opus=jueces.ClaudeJuezRunner(control=control),
                           codex=jueces.CodexJuezRunner(control=control),
                           llave=os.urandom(32), tipo=tipo, control=control,
                           acreditacion=acreditacion)
    out["consumo_jueces"] = control.intentos
    out["hash_evaluador"] = jueces.hash_evaluador()
    out["protocolo"] = P.VERSION_PROTOCOLO
    out["acreditacion_v13"] = acreditacion
    a.salida.parent.mkdir(parents=True, exist_ok=True)
    a.salida.write_text(json.dumps(out, ensure_ascii=False, indent=1, default=str), encoding="utf-8")
    print(f"circuito_utilizable={out['circuito_utilizable']} · {a.salida}")
    return 0 if (out["circuito_utilizable"] or tipo == "ajuste") else 1


if __name__ == "__main__":
    raise SystemExit(main())
