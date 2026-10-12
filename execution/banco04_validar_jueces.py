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
      --salida RUTA_FUERA_DEL_REPO --registro-uso DIR_FUERA_DEL_REPO --hash-congelado HEX
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
from typing import Any, Callable, Mapping

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from mia.eval.banco04 import ceguera, jueces  # noqa: E402
from mia.eval.banco04 import protocolo as P  # noqa: E402
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


CATEGORIA_FUGA = "C08"   # invariante del manifiesto: solo en ítems con jurisdicciones == []


def validar_conjunto(conjunto: Any, *, tipo_esperado: str | None = None,
                     otro: Mapping[str, Any] | None = None) -> list[dict]:
    """Comprobación estricta y local del formato (además de la del cargador de custodia), con
    dos invariantes del manifiesto: C08 solo en ítems sin jurisdicción, y materiales de ajuste
    y reservado disjuntos (`huella_material`) cuando se pasa `otro`. Falla cerrado."""
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
                and it["jurisdicciones"] != []):
            raise ConjuntoInvalido(f"{it['id']}: C08 (fuga) solo en ítems con jurisdicciones == []")
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
                       pares_kappa: list | None = None) -> dict:
    """Exigencias de §8.6 sobre los resultados POR ENTRADA DE VERDAD. Determinista (gate N5).
    Un defecto no evaluado cuenta como NO detectado y un control no evaluado como falso positivo
    (lo que no se pudo juzgar no ayuda al circuito)."""
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


def validar_circuito(items: list[dict], *, opus: jueces.Runner, codex: jueces.Runner,
                     llave: bytes, tipo: str, votante_factory: Callable | None = None) -> dict:
    cegado = comprobar_cegado(items)
    por_item = [evaluar_item(it, opus=opus, codex=codex, llave=llave,
                             votante_factory=votante_factory) for it in items]
    resultados = [v for x in por_item for v in x["verdades"]]
    pares = [p for x in por_item if x["estado"] == "evaluada" for p in x["pares_kappa"]]
    discord = sum(int(x.get("discordancias") or 0) for x in por_item)
    out = evaluar_exigencias(resultados, tipo=tipo, discordancias=discord, pares_kappa=pares)
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


class ReservadoYaUsado(RuntimeError):
    pass


def identidad_sellada_reservado(manifiesto: Mapping[str, Any]) -> str:
    """Identidad SELLADA del reservado: la del artefacto `mutaciones_reservadas` del manifiesto
    (id + sha256 cifrado + sha256 en claro). No depende de nada que el operador elija."""
    arts = [a for a in manifiesto.get("artefactos") or [] if a.get("tipo") == "mutaciones_reservadas"]
    if len(arts) != 1:
        raise SystemExit("el manifiesto no declara exactamente un conjunto reservado")
    a = arts[0]
    if not all(a.get(k) for k in ("id", "sha256_cifrado", "sha256_claro")):
        raise SystemExit("el artefacto reservado del manifiesto está incompleto")
    return hashlib.sha256(f"{a['id']}|{a['sha256_cifrado']}|{a['sha256_claro']}".encode()).hexdigest()


def ruta_registro_uso(identidad: str, environ: Mapping[str, str] | None = None) -> Path:
    """Registro CANÓNICO, no seleccionable: `<MIA_BANCO04_CUSTODIA>/registro-uso/`. Solo se crea
    la marca; nunca se lee nada de la custodia."""
    entorno = os.environ if environ is None else environ
    carpeta = (entorno.get(ENV_CUSTODIA) or "").strip()
    if not carpeta:
        raise SystemExit(f"{ENV_CUSTODIA} no está definida: no hay registro de uso del reservado")
    base = Path(carpeta)
    if _bajo_repo(base):
        raise SystemExit("la custodia no puede estar bajo el repositorio")
    if not re.fullmatch(r"[0-9a-f]{64}", identidad or ""):
        raise SystemExit("identidad sellada inválida")
    return base / SUBDIR_REGISTRO_USO / f"reservado-{identidad}.usado"


def marcar_uso_unico(identidad: str, environ: Mapping[str, str] | None = None) -> Path:
    """Marca de un solo uso del reservado, escrita ANTES de juzgar y conservada aunque la
    validación falle después (§8.6: el usado ya no es reservado). Falla si ya existe."""
    marca = ruta_registro_uso(identidad, environ)
    marca.parent.mkdir(parents=True, exist_ok=True)
    try:
        with open(marca, "x", encoding="utf-8") as fh:
            fh.write(json.dumps({"identidad_sellada": identidad, "protocolo": P.VERSION_PROTOCOLO,
                                 "protocolo_custodia": P.PROTOCOLO_CUSTODIA,
                                 "marcado": time.strftime("%Y-%m-%dT%H:%M:%S")}))
    except FileExistsError:
        raise ReservadoYaUsado("el conjunto reservado YA se usó: corregir exige un reservado "
                               "nuevo (§8.6)")
    return marca


def control_de_cuota(*, salida: Path, version: str, bloque: int, prefijo: str,
                     salida_custodia: Path | None = None) -> jueces.ControlCuotaJueces:
    """I5: control de cuota de los jueces sobre el contador COMPARTIDO del runner
    (`run_banco04.LedgerJuicio`, del otro agente: se usa, no se modifica)."""
    sys.path.insert(0, str(ROOT / "execution"))
    import run_banco04 as rb  # noqa: PLC0415
    ledger = rb.LedgerJuicio(salida, version,
                             nuevo_contador=lambda: rb.contador_desde_protocolo(P, bloque),
                             salida_custodia=salida_custodia, versiones=())
    return jueces.ControlCuotaJueces(ledger=ledger, etapa="validacion", prefijo=prefijo)


def _cargar(a: argparse.Namespace) -> tuple[dict, dict | None]:  # noqa: C901
    """(conjunto, otro_conjunto). Desde la custodia: importación PEREZOSA (otro agente es dueño
    de `custodia.py`); el claro queda solo en memoria."""
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
    ap.add_argument("--salida-custodia", type=Path)
    a = ap.parse_args(argv)
    conjunto, otro = _cargar(a)
    items = validar_conjunto(conjunto, otro=otro)
    tipo = conjunto["conjunto"]
    comprobar_cegado(items)  # antes de gastar cuota y antes de marcar el reservado como usado
    control = control_de_cuota(salida=a.salida_banco, version=a.version, bloque=a.bloque,
                               prefijo=f"validacion-{tipo}", salida_custodia=a.salida_custodia)
    if tipo == "reservado":
        if not a.conjunto_custodia or not a.hash_congelado:
            raise SystemExit("el reservado solo se valida desde la custodia y con --hash-congelado")
        if _bajo_repo(a.salida):
            raise SystemExit("el resultado crudo del reservado vive en custodia, no en el repo")
        jueces.verificar_congelado(a.hash_congelado)
        from mia.eval.banco04 import custodia  # noqa: PLC0415
        marcar_uso_unico(identidad_sellada_reservado(custodia.cargar_manifiesto()))
    out = validar_circuito(items, opus=jueces.ClaudeJuezRunner(control=control),
                           codex=jueces.CodexJuezRunner(control=control),
                           llave=os.urandom(32), tipo=tipo)
    out["consumo_jueces"] = control.intentos
    out["hash_evaluador"] = jueces.hash_evaluador()
    out["protocolo"] = P.VERSION_PROTOCOLO
    a.salida.parent.mkdir(parents=True, exist_ok=True)
    a.salida.write_text(json.dumps(out, ensure_ascii=False, indent=1, default=str), encoding="utf-8")
    print(f"circuito_utilizable={out['circuito_utilizable']} · {a.salida}")
    return 0 if (out["circuito_utilizable"] or tipo == "ajuste") else 1


if __name__ == "__main__":
    raise SystemExit(main())
