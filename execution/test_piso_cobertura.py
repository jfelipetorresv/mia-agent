"""
Mia · test_piso_cobertura.py — gate del BARRIDO DE COBERTURA (alcance, sesión 53).

EL DEFECTO QUE CUSTODIA, medido en el piloto con expediente real (arbitraje de 574
fragmentos): Mia leyó 128 fragmentos —el techo— y NO vio las fechas que sostenían la
prescripción. No razonó mal: no vio el material. La causa no es un ranking roto, es lo que
un ranking hace: ordenar por parecido con la pregunta. El dato decisivo suele estar donde
nadie preguntó, y zonas enteras del expediente quedan ciegas sin que nada avise.

La corrección es de CÓDIGO, no de modelo: un barrido regular del expediente que se paga con
la COLA de la lista (donde el parecido ya es marginal), sin una llamada más y sin un token
más de contexto. Importa que sea de código porque bajo SUSCRIPCIÓN —el modo de venta— no hay
herramientas y la lectura agéntica está apagada: ahí el modelo no puede pedir nada.

Historia que este gate conserva: el primer intento cubría solo las piezas HUÉRFANAS (las que
no recibían ni un fragmento). Se midió con el caso de oro voluminoso y no movió la aguja —sus
tres documentos ya recibían material y los datos seguían enterrados—, así que el barrido pasó
a ser por ZONAS dentro de cada pieza. Se deja escrito para que nadie vuelva a la versión
simple pensando que basta.

Lo que este gate NO afirma: que el barrido garantice encontrar un dato concreto. Con 98
fragmentos de 252 se ve el 39% del expediente, se lea como se lea. Lo que cambia es DÓNDE
cae ese 39%.

Puro: sin DB, sin modelo, sin red. Salida: exit 0 = PASS · exit 1 = FAIL.
    .venv\\Scripts\\python.exe execution\\test_piso_cobertura.py
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

from mia import config  # noqa: E402
from mia.agents import retrieval  # noqa: E402

_results: list[tuple[str, bool]] = []


def check(nombre: str, ok: bool, detalle: str = "") -> None:
    _results.append((nombre, bool(ok)))
    linea = ("  [OK]   " if ok else "  [FAIL] ") + nombre
    if not ok and detalle:
        linea += f" — {detalle}"
    print(linea)


def _docs(*pares) -> list[dict]:
    """(document_id, n) → n fragmentos leídos de esa pieza, desde su PRINCIPIO: es lo que
    hace un ranking cuando el dato decisivo no se parece a la pregunta."""
    salida = []
    for doc_id, n in pares:
        salida += [{"document_id": doc_id, "content": f"{doc_id}-{i}", "ord": i}
                   for i in range(n)]
    return salida


def _inv(*pares) -> list[dict]:
    return [{"document_id": d, "filename": f"{d}.pdf", "n_chunks": n} for d, n in pares]


def main() -> int:  # noqa: C901
    print("== gate: barrido de cobertura del expediente ==")

    print("\n1 · qué piezas quedaron sin leer (la señal de prioridad)")
    docs = _docs(("A", 6), ("B", 2))
    inv = _inv(("A", 40), ("B", 10), ("C", 30), ("D", 5))
    huerfanas = [d["document_id"] for d in retrieval.unread_documents(docs, inv)]
    check("se detectan las piezas con CERO fragmentos leídos",
          huerfanas == ["C", "D"], str(huerfanas))
    check("y primero la que más expediente deja ciego", huerfanas[:1] == ["C"], str(huerfanas))
    check("sin inventario no inventa nada", retrieval.unread_documents(docs, []) == [])
    check("sin lectura previa, todas están sin leer",
          len(retrieval.unread_documents([], inv)) == 4)

    print("\n2 · el barrido NO agranda la lectura: sale de la cola")
    docs32 = _docs(("A", 20), ("B", 12))
    inv32 = _inv(("A", 40), ("B", 12), ("C", 30), ("D", 20), ("E", 15))
    piezas, reservados = retrieval.plan_coverage(docs32, inv32, top_k=32)
    check("el barrido elige posiciones que leer", len(piezas) >= 1, str(piezas))
    check("no supera la reserva del top_k",
          reservados <= int(32 * config.MIA_RETRIEVAL_COVERAGE_RESERVE_FRACTION),
          str(reservados))
    check("la reserva es exactamente lo que pide cada pieza",
          reservados == sum(len(p["ords"]) for p in piezas), str(reservados))
    check("nunca deja la lista principal por debajo de la mitad del turno",
          len(docs32) - reservados >= 32 // 2, f"{len(docs32)} - {reservados}")
    ids = {p["document_id"] for p in piezas}
    check("alcanza piezas de las que no se había leído nada",
          bool(ids & {"C", "D", "E"}), str(ids))

    print("\n3 · el barrido no relee, no se sale de la pieza y no se repite")
    for p in piezas:
        n = next(d["n_chunks"] for d in inv32 if d["document_id"] == p["document_id"])
        check(f"posiciones dentro de la pieza {p['document_id']}",
              all(0 <= o < n for o in p["ords"]), str(p["ords"]))
        check(f"sin posiciones repetidas en {p['document_id']}",
              len(set(p["ords"])) == len(p["ords"]), str(p["ords"]))
    leidos_a = {d["ord"] for d in docs32 if d["document_id"] == "A"}
    pa = next((p for p in piezas if p["document_id"] == "A"), None)
    if pa is not None:
        check("no gasta reserva releyendo lo ya leído",
              not (set(pa["ords"]) & leidos_a), str(pa["ords"]))

    print("\n4 · cuándo NO hace nada")
    # En una lectura corta el barrido no se abstiene —una pieza entera sin leer es
    # justamente lo que hay que corregir— pero se lleva SOLO la reserva: la relevancia
    # conserva la mayoría del turno.
    piezas_c, reservados_c = retrieval.plan_coverage(
        _docs(("A", 8)), _inv(("A", 8), ("B", 50)), 8)
    check("en una lectura corta el barrido se lleva solo la reserva",
          reservados_c <= max(1, int(8 * config.MIA_RETRIEVAL_COVERAGE_RESERVE_FRACTION)),
          str(reservados_c))
    check("y la relevancia conserva al menos la mitad del turno",
          8 - reservados_c >= 4, str(reservados_c))
    check("lo que barre es la pieza que no se había leído",
          [p["document_id"] for p in piezas_c] == ["B"], str(piezas_c))
    check("sin inventario no hay nada que barrer",
          retrieval.plan_coverage(docs32, [], 32) == ([], 0))
    check("sin lectura no hay cola de la que sacar el barrido",
          retrieval.plan_coverage([], inv32, 32) == ([], 0))
    check("una pieza leída ENTERA no pide nada más",
          retrieval.plan_coverage(_docs(("A", 20)), _inv(("A", 20)), 32) == ([], 0),
          str(retrieval.plan_coverage(_docs(("A", 20)), _inv(("A", 20)), 32)))

    print("\n5 · el caso que lo motivó: el dato enterrado LEJOS del inicio")
    docs_p = _docs(("demanda", 40), ("poliza", 30), ("actas", 28))
    inv_p = _inv(("demanda", 200), ("poliza", 150), ("actas", 120))
    piezas_p, reservados_p = retrieval.plan_coverage(docs_p, inv_p, top_k=128)
    check("el barrido alcanza las tres piezas",
          len({p["document_id"] for p in piezas_p}) == 3, str(piezas_p))
    pares = [(max(p["ords"]),
              next(d["n_chunks"] for d in inv_p if d["document_id"] == p["document_id"]))
             for p in piezas_p]
    check("y llega al ÚLTIMO tramo de cada pieza, no solo al principio",
          all(fondo > 0.5 * n for fondo, n in pares), str(pares))
    check("cubre zonas que el ranking no tocó (más allá de lo ya leído)",
          all(min(p["ords"]) >= 0 for p in piezas_p)
          and any(max(p["ords"]) > 40 for p in piezas_p), str(pares))
    check("y sigue costando una fracción de la lectura, no el doble",
          reservados_p <= 32, str(reservados_p))

    print("\n6 · está cableado donde hacía falta (sin herramientas = suscripción)")
    fuente = (ROOT / "backend" / "mia" / "agents" / "graph.py").read_text(encoding="utf-8")
    i_enabled = fuente.find("if not enabled:")
    tramo = fuente[i_enabled:i_enabled + 700] if i_enabled > 0 else ""
    check("el camino SIN lectura agéntica aplica el barrido",
          "_cover_unread_documents" in tramo, tramo[:120])
    check("y el camino agéntico también lo aplica",
          fuente.count("_cover_unread_documents") >= 3,
          str(fuente.count("_cover_unread_documents")))
    check("el barrido lee por POSICIÓN, no por parecido (si no, traería más de lo mismo)",
          "retrieve_document_ords" in fuente)
    # Medido: la primera versión deduplicaba DESPUÉS de ceder la cola y el turno acababa
    # leyendo 86 fragmentos donde antes leía 98. Barrer no puede costar material.
    i_barrido = fuente.find("async def _cover_unread_documents")
    cuerpo = fuente[i_barrido:i_barrido + 3000]
    check("el barrido no encoge la lectura: dedup ANTES de ceder la cola",
          cuerpo.find("dedupe_chunks") < cuerpo.find("conservados = docs["), "orden invertido")

    print("\n7 · lo que ninguna recuperación puede prometer, se DICE")
    # El límite es estructural: leer 98 de 252 fragmentos ve el 39% del expediente, se
    # reparta como se reparta. Ninguna técnica garantiza haber visto un dato puntual. Lo
    # que sí se puede es declarar el alcance — misma disciplina que el muro de citas.
    from mia.agents.graph import _aviso_de_alcance  # noqa: E402

    check("sin medición no se inventa una cifra", _aviso_de_alcance({}) is None)
    check("un expediente leído entero no advierte nada",
          _aviso_de_alcance({"alcance_lectura": {"leidos": 40, "total": 40}}) is None)
    aviso = _aviso_de_alcance({"alcance_lectura": {"leidos": 98, "total": 252}})
    check("un expediente leído a medias SÍ lo declara", aviso is not None)
    if aviso:
        check("dice cuánto leyó, en números que el abogado puede comprobar",
              aviso["leidos"] == 98 and aviso["total"] == 252 and aviso["porcentaje"] == 39,
              str(aviso))
        texto = aviso["aviso"].lower()
        check("dice qué puede haberse quedado fuera", "fecha" in texto or "puntual" in texto)
        check("y qué puede hacer el abogado con eso",
              "pregúntame" in texto or "indícame" in texto, texto[-120:])
        check("§G: sin jerga técnica",
              not any(t in texto for t in ("chunk", "top_k", "embedding", "ranking",
                                           "retrieval")), texto)
    rev = (ROOT / "frontend" / "app" / "_components" / "CitationReview.tsx").read_text(
        encoding="utf-8")
    check("y la pantalla lo pinta", "alcance_lectura" in rev and "alcance.porcentaje" in rev)

    passed = sum(1 for _, ok in _results if ok)
    total = len(_results)
    print(f"\nRESULT: {passed}/{total} checks PASS")
    return 0 if passed == total else 1


if __name__ == "__main__":
    sys.exit(main())
