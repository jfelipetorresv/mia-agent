"""
Mia · banco04_calibracion.py — paquete de calibración humana ciega (§8.7, §10.2.12).

No consume cuota de modelo: solo genera, valida y coteja paquetes.

  generar   10 salidas estratificadas (4 pequeñas, 2 de riesgo, 4 voluminosas), con las dos
            versiones mezcladas y SIN rótulo; ids por HMAC sobre la llave custodiada y orden
            barajado. El texto pasa por la misma ceguera que ven los jueces. Escribe el paquete
            (para Pipe) y la llave privada (mapeo candidato → versión/caso/corrida), que debe
            quedar FUERA del repositorio.
  plantilla Plantilla de revisión: afirmaciones sin respaldo (literal), omisiones, conducta
            (definitiva / limitada / abstención) y si la aprobaría sin editar.
  validar   Revisión completa y bien formada (adaptado de `provider_benchmark.validate_human_review`).
  cotejar   Regla fijada de antemano: si Pipe marca una afirmación sin respaldo que los jueces no
            confirmaron, los jueces NO certifican el cero; se publica cuántas no vieron.

FORMATO DE `--corridas` (lo produce el agregador del banco):
  {"corridas": [{"version": str, "case_id": str, "estrato": str, "repeticion": int,
                 "diagnostico": str, "borrador": str,
                 "defectos_confirmados": [{"seccion": "diagnostico"|"borrador",
                                           "inicio": int, "fin": int}]}]}
  Las posiciones de `defectos_confirmados` son sobre el texto CEGADO de la sección (el mismo que
  vio el juez: `ceguera.preparar_candidato` → `privado.texto_cegado`).
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any, Mapping

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from mia.eval.banco04 import ceguera  # noqa: E402
from mia.eval.banco04 import protocolo as P  # noqa: E402
from mia.eval.provider_benchmark import sha256_json  # noqa: E402

FORMATO = "banco04-calibracion/v1"
CUOTAS = {"pequenas": 4, "riesgo": 2, "voluminosas": 4}
GRUPO_ESTRATO = {
    P.ESTRATO_A_CANONICOS: "pequenas", P.ESTRATO_C_PEQUENOS: "pequenas",
    P.ESTRATO_A_RIESGO: "riesgo",
    P.ESTRATO_A_VOLUMINOSO: "voluminosas", P.ESTRATO_C_VOLUMINOSOS: "voluminosas",
}
CONDUCTAS = ("definitiva", "limitada", "abstencion")


def _bajo_repo(ruta: Path) -> bool:
    try:
        ruta.resolve().relative_to(ROOT.resolve())
        return True
    except ValueError:
        return False


def seleccionar(corridas: list[dict], llave: bytes) -> list[dict]:
    """Muestra estratificada con las dos versiones mezcladas: dentro de cada grupo se alterna
    versión siguiendo el orden HMAC; determinista con la llave."""
    elegidas: list[dict] = []
    for grupo, cuota in CUOTAS.items():
        pool = [c for c in corridas if GRUPO_ESTRATO.get(c["estrato"]) == grupo]
        por_version: dict[str, list[dict]] = {}
        for c in sorted(pool, key=lambda c: ceguera.clave_orden(
                llave, f"{c['version']}:{c['case_id']}:{c['repeticion']}")):
            por_version.setdefault(c["version"], []).append(c)
        versiones = sorted(por_version)
        i = 0
        while sum(1 for e in elegidas if GRUPO_ESTRATO[e["estrato"]] == grupo) < cuota and any(
                por_version.values()):
            v = versiones[i % len(versiones)]
            if por_version[v]:
                elegidas.append(por_version[v].pop(0))
            i += 1
            if i > 10_000:
                break
    return elegidas


def generar(corridas: list[dict], llave: bytes) -> tuple[dict, dict]:
    sel = seleccionar(corridas, llave)
    items, mapeo = [], {}
    for c in sel:
        cid = ceguera.candidate_id(llave, c["version"], c["case_id"], c["repeticion"],
                                   c["diagnostico"], c["borrador"])
        d = ceguera.cegar_texto(c["diagnostico"])
        b = ceguera.cegar_texto(c["borrador"])
        items.append({"candidate_id": cid, "diagnostico": d.texto, "borrador": b.texto,
                      "aviso_alcance": d.aviso_alcance or b.aviso_alcance})
        mapeo[cid] = {"version": c["version"], "case_id": c["case_id"],
                      "repeticion": c["repeticion"], "estrato": c["estrato"]}
    orden = ceguera.barajar([i["candidate_id"] for i in items], llave)
    items.sort(key=lambda i: orden.index(i["candidate_id"]))
    paquete = {
        "formato": FORMATO, "protocolo": P.VERSION_PROTOCOLO,
        "instrucciones": ("Marque en cada salida: (1) las afirmaciones sin respaldo, copiando el "
                          "literal exacto; (2) las omisiones materiales; (3) si el diagnóstico es "
                          "definitiva, limitada o abstención; (4) si lo aprobaría sin editar."),
        "items": items,
    }
    paquete["packet_sha256"] = sha256_json(paquete)
    llave_privada = {"packet_sha256": paquete["packet_sha256"], "mapeo": mapeo}
    llave_privada["key_sha256"] = sha256_json(llave_privada)
    return paquete, llave_privada


def plantilla(paquete: Mapping[str, Any]) -> dict:
    return {"packet_sha256": paquete["packet_sha256"], "revisor": "",
            "revisiones": [{"candidate_id": i["candidate_id"], "afirmaciones_sin_respaldo": [],
                            "omisiones": [], "conducta": None, "aprobaria_sin_editar": None}
                           for i in paquete["items"]]}


def validar_revision(paquete: Mapping[str, Any], revision: Mapping[str, Any]) -> dict:
    motivos: list[str] = []
    if revision.get("packet_sha256") != paquete.get("packet_sha256"):
        motivos.append("packet_sha256_no_coincide")
    if not str(revision.get("revisor") or "").strip():
        motivos.append("revisor_ausente")
    items = {i["candidate_id"]: i for i in paquete.get("items") or []}
    filas = {r.get("candidate_id"): r for r in revision.get("revisiones") or []}
    if set(filas) != set(items):
        motivos.append("cobertura_incompleta")
    for cid in set(items) & set(filas):
        r = filas[cid]
        if r.get("conducta") not in CONDUCTAS:
            motivos.append(f"{cid}:conducta_invalida")
        if not isinstance(r.get("aprobaria_sin_editar"), bool):
            motivos.append(f"{cid}:aprobaria_invalida")
        if not isinstance(r.get("omisiones"), list):
            motivos.append(f"{cid}:omisiones_invalidas")
        for a in r.get("afirmaciones_sin_respaldo") or []:
            sec = a.get("seccion") if isinstance(a, dict) else None
            lit = a.get("literal") if isinstance(a, dict) else None
            if sec not in ("diagnostico", "borrador") or not lit or lit not in items[cid][sec]:
                motivos.append(f"{cid}:afirmacion_no_localizable")
    return {"completa": not motivos, "motivos": sorted(set(motivos)),
            "n_esperadas": len(items), "n_revisadas": len(set(items) & set(filas))}


def cotejar(paquete: Mapping[str, Any], revision: Mapping[str, Any], llave_privada: Mapping[str, Any],
            corridas: list[dict]) -> dict:
    """Cuántas afirmaciones sin respaldo marcó Pipe que los jueces no confirmaron."""
    val = validar_revision(paquete, revision)
    if not val["completa"]:
        return {"estado": "revision_incompleta", **val}
    if llave_privada.get("packet_sha256") != paquete["packet_sha256"]:
        return {"estado": "llave_no_corresponde"}
    idx = {(c["version"], c["case_id"], c["repeticion"]): c for c in corridas}
    items = {i["candidate_id"]: i for i in paquete["items"]}
    no_vistas: list[dict] = []
    total = 0
    for r in revision["revisiones"]:
        m = llave_privada["mapeo"][r["candidate_id"]]
        corrida = idx[(m["version"], m["case_id"], m["repeticion"])]
        for a in r["afirmaciones_sin_respaldo"]:
            total += 1
            texto = items[r["candidate_id"]][a["seccion"]]
            ini = texto.find(a["literal"])
            fin = ini + len(a["literal"])
            vista = any(d["seccion"] == a["seccion"] and d["inicio"] < fin and d["fin"] > ini
                        for d in corrida.get("defectos_confirmados") or [])
            if not vista:
                no_vistas.append({"candidate_id": r["candidate_id"], "literal": a["literal"]})
    return {"estado": "cotejado", "marcadas_por_pipe": total, "no_vistas_por_los_jueces": len(no_vistas),
            "detalle": no_vistas, "jueces_certifican_el_cero": not no_vistas,
            "rotulo": P.ROTULO_CALIBRADO if not no_vistas else P.ROTULO_AUTOMATICO}


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Paquete de calibración humana ciega (§8.7)")
    sub = ap.add_subparsers(dest="cmd", required=True)
    g = sub.add_parser("generar")
    g.add_argument("--corridas", required=True, type=Path)
    g.add_argument("--llave-archivo", required=True, type=Path)
    g.add_argument("--paquete-salida", required=True, type=Path)
    g.add_argument("--llave-salida", required=True, type=Path)
    t = sub.add_parser("plantilla")
    t.add_argument("--paquete", required=True, type=Path)
    t.add_argument("--salida", required=True, type=Path)
    v = sub.add_parser("validar")
    v.add_argument("--paquete", required=True, type=Path)
    v.add_argument("--revision", required=True, type=Path)
    c = sub.add_parser("cotejar")
    c.add_argument("--paquete", required=True, type=Path)
    c.add_argument("--revision", required=True, type=Path)
    c.add_argument("--llave", required=True, type=Path)
    c.add_argument("--corridas", required=True, type=Path)
    a = ap.parse_args(argv)

    def _leer(p: Path) -> Any:
        return json.loads(p.read_text(encoding="utf-8"))

    if a.cmd == "generar":
        if _bajo_repo(a.llave_salida) or _bajo_repo(a.llave_archivo):
            raise SystemExit("la llave de ceguera y la llave privada viven fuera del repositorio")
        paquete, privada = generar(_leer(a.corridas)["corridas"], a.llave_archivo.read_bytes())
        a.paquete_salida.write_text(json.dumps(paquete, ensure_ascii=False, indent=1), encoding="utf-8")
        a.llave_salida.write_text(json.dumps(privada, ensure_ascii=False, indent=1), encoding="utf-8")
        print(f"paquete {paquete['packet_sha256'][:12]} · {len(paquete['items'])} salidas")
    elif a.cmd == "plantilla":
        a.salida.write_text(json.dumps(plantilla(_leer(a.paquete)), ensure_ascii=False, indent=1),
                            encoding="utf-8")
    elif a.cmd == "validar":
        print(json.dumps(validar_revision(_leer(a.paquete), _leer(a.revision)), ensure_ascii=False))
    else:
        print(json.dumps(cotejar(_leer(a.paquete), _leer(a.revision), _leer(a.llave),
                                 _leer(a.corridas)["corridas"]), ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
