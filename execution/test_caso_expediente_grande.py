"""
Mia · test_caso_expediente_grande.py — gate del caso de oro con expediente GRANDE (N-2).

QUÉ DECIDE ESTE CASO. La decisión pendiente N-2 es si la LECTURA AGÉNTICA queda encendida por
defecto. Con los casos de oro chicos (1-2 documentos de 2 fragmentos) no se puede decidir: la
primera lectura ya ve el expediente entero, así que arrancar corto o largo da igual. El caso
`expediente-voluminoso-cruce-disperso` construye el escenario donde SÍ se ve: cientos de
fragmentos, tres datos decisivos enterrados lejos del inicio en documentos distintos, y una
pregunta que obliga a cruzarlos.

QUÉ SE VERIFICA AQUÍ (todo en frío, sin correr el grafo, sin red, sin DB):

  1. El expediente es realmente GRANDE y el relleno no degeneró (cientos de fragmentos).
  2. Los tres datos decisivos están SELLADOS en el expediente y están ENTERRADOS — no en los
     primeros fragmentos, que es lo único que un arranque corto alcanza a ver. Si un marcador
     se colara al inicio, el caso mediría cero y quedaría verde para siempre.
  3. Cada marcador es ÚNICO en el expediente: si el mismo dato apareciera en varios sitios, la
     señal dejaría de probar que se leyó ESE fragmento.
  4. El caso está FUERA del examen por defecto (no cambia la composición del examen ni quema la
     comparabilidad de las series) pero SÍ es corrible por id desde `run_eval.py`.
  5. La señal `recall_markers_signal` funciona en las DOS direcciones: reconoce el dato cuando
     está (incluso escrito sin tildes o con espacios de más) y REPRUEBA cuando falta. Sin esto
     la señal podría estar siempre en verde y nadie lo notaría.
  6. `compare_agentic_reports` cruza los dos ejes: ahorrar tokens PERDIENDO un dato del
     expediente se reporta como PEOR, y un solo caso que pierda un dato manda el veredicto
     agregado (fail-safe). Es el corazón de la decisión: sin esto, "gastó menos" se leería como
     mejora cuando puede ser el síntoma del defecto.
  7. El caso es SINTÉTICO y agnóstico de jurisdicción: sin datos reales de cliente y sin
     articulado de ningún país (MIA no es de ningún país — regla dura del producto).

Salida: exit 0 = PASS · exit 1 = FAIL.
    .venv\\Scripts\\python.exe execution\\test_caso_expediente_grande.py
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from mia.eval import cases as cases_mod  # noqa: E402
from mia.eval.harness import compare_agentic_reports  # noqa: E402
from mia.eval.scoring import FLAG_MISSING_BURIED_FACT, recall_markers_signal  # noqa: E402

CASE_ID = "expediente-voluminoso-cruce-disperso"

# Cuántos fragmentos iniciales cuentan como "el arranque corto": los marcadores NO pueden
# estar ahí o el caso no probaría nada. Holgado a propósito (el arranque real es más corto).
ARRANQUE_CORTO = 25

_results: list[tuple[str, bool]] = []


def check(nombre: str, ok: bool, detalle: str = "") -> None:
    _results.append((nombre, ok))
    marca = "[OK]  " if ok else "[FAIL]"
    linea = f"  {marca} {nombre}"
    if not ok and detalle:
        linea += f" — {detalle}"
    print(linea)


def main() -> int:  # noqa: C901 — un gate lineal se lee mejor entero
    print("== caso de oro con expediente GRANDE (N-2) ==")

    grandes = cases_mod.load_large_cases()
    caso = next((c for c in grandes if c.id == CASE_ID), None)

    print("\n1 · el expediente es grande de verdad")
    check("el caso existe en LARGE_CASES", caso is not None)
    if caso is None:
        print("\nRESULT: 1/1 checks FAIL")
        return 1

    fragmentos = [ch for d in caso.documents for ch in d.chunks]
    check("tiene al menos 3 documentos", len(caso.documents) >= 3, f"{len(caso.documents)}")
    check("tiene CIENTOS de fragmentos (>= 200)", len(fragmentos) >= 200, f"{len(fragmentos)}")
    check(
        "ningún documento quedó vacío por un fallo del generador",
        all(len(d.chunks) > 0 for d in caso.documents),
    )
    check(
        "el relleno no degeneró a fragmentos idénticos (hay variedad)",
        len(set(fragmentos)) >= len(fragmentos) - 2,
        f"{len(set(fragmentos))} distintos de {len(fragmentos)}",
    )

    print("\n2 · los datos decisivos están sellados y ENTERRADOS")
    check("el caso declara marcadores de recuperación", len(caso.recall_markers) >= 3,
          f"{len(caso.recall_markers)}")
    for marcador in caso.recall_markers:
        m = marcador.lower()
        posiciones = [i for i, ch in enumerate(fragmentos) if m in ch.lower()]
        check(f"el dato {marcador!r} está sellado en el expediente", bool(posiciones))
        check(
            f"el dato {marcador!r} es ÚNICO en el expediente",
            len(posiciones) == 1,
            f"aparece {len(posiciones)} veces",
        )
        # Enterrado = fuera del arranque corto DE SU PROPIO documento (que es la unidad que se
        # lee) y también del expediente concatenado.
        for doc in caso.documents:
            locales = [i for i, ch in enumerate(doc.chunks) if m in ch.lower()]
            if locales:
                check(
                    f"el dato {marcador!r} está enterrado (fragmento {locales[0] + 1} de "
                    f"{len(doc.chunks)} en {doc.filename})",
                    locales[0] >= ARRANQUE_CORTO,
                    f"está en el fragmento {locales[0] + 1}, dentro del arranque corto",
                )

    check(
        "los datos decisivos viven en documentos DISTINTOS (hay que cruzar, no solo leer uno)",
        len({
            d.filename
            for d in caso.documents
            for m in caso.recall_markers
            if any(m.lower() in ch.lower() for ch in d.chunks)
        }) >= 3,
    )

    print("\n3 · fuera del examen por defecto, pero corrible por id")
    ids_examen = {c.id for c in cases_mod.load_golden_cases()}
    check("NO está en el examen por defecto (no quema la comparabilidad de las series)",
          CASE_ID not in ids_examen)
    check("el examen por defecto sigue teniendo sus 9 casos",
          len(cases_mod.load_golden_cases()) == 9,
          f"{len(cases_mod.load_golden_cases())}")
    run_eval_src = (ROOT / "execution" / "run_eval.py").read_text(encoding="utf-8")
    check("run_eval.py lo registra como corrible por id (_all_cases usa load_large_cases)",
          "load_large_cases()" in run_eval_src)
    check("run_eval.py lo lista en --list", "LARGE_CASES" in run_eval_src)

    print("\n4 · la señal de recuperación funciona en las dos direcciones")
    markers = caso.recall_markers
    todos = " ".join(markers)
    s_ok = recall_markers_signal("diagnóstico", f"El borrador menciona {todos}.", markers)
    check("reconoce los datos cuando están", s_ok["ok"] and s_ok["cobertura"] == 1.0,
          f"cobertura={s_ok['cobertura']}")
    check("no marca bandera cuando están todos", s_ok["flags"] == [])

    s_falta = recall_markers_signal("diagnóstico", f"Solo menciono {markers[0]}.", markers)
    check("REPRUEBA cuando falta un dato", not s_falta["ok"])
    check("nombra el dato que falta", markers[1] in s_falta["faltantes"])
    check("marca la bandera de dato ausente en la respuesta",
          s_falta["flags"] == [FLAG_MISSING_BURIED_FACT])
    check("la bandera NO afirma que no lo leyó (límite declarado de la señal)",
          "no_leyo" not in FLAG_MISSING_BURIED_FACT, FLAG_MISSING_BURIED_FACT)
    check("la cobertura refleja lo que falta", 0.0 < (s_falta["cobertura"] or 0) < 1.0,
          f"cobertura={s_falta['cobertura']}")

    s_vacio = recall_markers_signal("", "", markers)
    check("con respuesta vacía la cobertura es 0, no 1", s_vacio["cobertura"] == 0.0)

    # Robustez de forma: sin tildes y con espacios de más debe seguir casando (misma
    # normalización que la cobertura de citas). "otrosí 3" -> "otrosi  3".
    sin_tildes = "otrosi  3"
    s_forma = recall_markers_signal("", f"Se pactó el {sin_tildes} del contrato.", ("otrosí 3",))
    check("casa aunque se escriba sin tildes y con espacios de más", s_forma["ok"])

    # Anti-gate-ciego: un caso SIN marcadores no puede reportarse como recuperación perfecta.
    s_na = recall_markers_signal("d", "b", ())
    check("sin marcadores declarados NO reporta cobertura 1.0 (sería un PASS vacío)",
          s_na["aplica"] is False and s_na["cobertura"] is None)

    print("\n5 · el comparador cruza AHORRO con RECUPERACIÓN (el corazón de N-2)")

    def _rep(cobertura_encontrados: list[str], tokens: int, *, corrio: bool = True) -> dict:
        caso = {
            "case_id": CASE_ID,
            "score": {"total_tokens": tokens},
            "recall_enterrado": {
                "aplica": True,
                "cobertura": round(len(cobertura_encontrados) / len(markers), 4),
                "encontrados": cobertura_encontrados,
                "faltantes": [m for m in markers if m not in cobertura_encontrados],
            },
        }
        if corrio:
            caso["agentic_reading"] = {"stop": "sin_mas_que_leer", "expansions": 2}
        return {"cases": [caso]}

    # (a) ahorra tokens pero PIERDE un dato → PEOR, no mejora.
    peor = compare_agentic_reports(_rep(list(markers), 100_000),
                                   _rep(list(markers[:-1]), 40_000))
    c0 = peor["cases"][0]
    check("ahorrar perdiendo un dato del expediente se reporta como PEOR",
          c0["veredicto"] == "peor", f"veredicto={c0['veredicto']}")
    check("nombra el dato perdido", markers[-1] in c0["recall_perdidos"])
    check("el ahorro de tokens sigue visible (no se esconde)", c0["delta_tokens"] < 0)
    check("un solo caso que pierde un dato manda el veredicto agregado (fail-safe)",
          peor["veredicto_agregado"] == "peor" and peor["n_perdio_dato"] == 1)
    check("la lectura llana explica por qué no es mejora",
          "no es una mejora" in c0["lectura_llana"].lower())

    # (b) mismos datos leyendo menos → mejora legítima.
    mejor = compare_agentic_reports(_rep(list(markers), 100_000),
                                    _rep(list(markers), 40_000))
    check("mismos datos leyendo menos se reporta como MEJOR",
          mejor["cases"][0]["veredicto"] == "mejor")
    check("veredicto agregado igual cuando nadie pierde ni gana datos",
          mejor["veredicto_agregado"] == "igual")

    # (c) encuentra un dato que antes no encontraba → mejora, aunque cueste más.
    gana = compare_agentic_reports(_rep(list(markers[:-1]), 40_000),
                                   _rep(list(markers), 120_000))
    check("encontrar un dato que antes se perdía se reporta como MEJOR aunque cueste más",
          gana["cases"][0]["veredicto"] == "mejor" and gana["cases"][0]["delta_tokens"] > 0)
    check("el veredicto agregado recoge la mejora", gana["veredicto_agregado"] == "mejor")

    # (d) EL BUCLE NO CORRIÓ → no concluyente. Esto pasó DE VERDAD en la primera corrida en vivo
    # (sesión 52): el motor de la suscripción sale por el CLI y no admite herramientas, así que
    # las dos pasadas fueron del MISMO camino clásico. El comparador daba «IGUAL — encontró los
    # mismos datos leyendo menos», que es una etiqueta engañosa sobre ruido del modelo.
    no_corrio = compare_agentic_reports(_rep(list(markers), 122_941, corrio=False),
                                        _rep(list(markers), 116_314, corrio=False))
    cnc = no_corrio["cases"][0]
    check("si la lectura agéntica NO corrió, el veredicto por caso es NO CONCLUYENTE",
          cnc["veredicto"] == "no_concluyente", f"veredicto={cnc['veredicto']}")
    check("y el agregado también (no se sostiene un veredicto sin haber medido)",
          no_corrio["veredicto_agregado"] == "no_concluyente")
    check("la explicación dice que la diferencia de tokens es ruido",
          "ruido" in cnc["lectura_llana"].lower())
    check("no cuenta como caso con recuperación verificada (no corrió el bucle)",
          no_corrio["n_con_recall"] == 0)
    check("run_eval.py imprime el veredicto NO CONCLUYENTE en llano",
          "NO CONCLUYENTE" in run_eval_src)

    # (e) sin marcadores: NO se inventa veredicto de recuperación.
    # El bucle SÍ corrió (si no, manda «no concluyente», que es la regla de más arriba), pero el
    # caso no declara datos enterrados: entonces solo se puede hablar de coste, y se dice.
    _traza = {"stop": "sin_mas_que_leer", "expansions": 1}
    sin = compare_agentic_reports(
        {"cases": [{"case_id": "x", "score": {"total_tokens": 10}, "agentic_reading": _traza}]},
        {"cases": [{"case_id": "x", "score": {"total_tokens": 5}, "agentic_reading": _traza}]},
    )
    check("un caso sin datos enterrados NO recibe veredicto de recuperación inventado",
          sin["cases"][0]["veredicto"] == "solo_coste"
          and sin["veredicto_agregado"] == "sin_datos_que_verificar",
          f"veredicto={sin['cases'][0]['veredicto']} agregado={sin['veredicto_agregado']}")

    print("\n6 · sintético y agnóstico de jurisdicción")
    check("declarado SINTÉTICO (candado de datos reales)", caso.synthetic is True)
    texto = " ".join(fragmentos) + " " + caso.message
    check("no reutiliza la rúbrica jurídica para medir recuperación",
          not caso.rubric)
    # Ni articulado ni siglas de código de ningún país: el caso mide recuperación, no derecho.
    prohibidos = ("artículo", "articulo", "art.", "ley ", "decreto", "código", "codigo",
                  "cco", "cpaca", "cgp")
    encontrados = [p for p in prohibidos if p in texto.lower()]
    check("el expediente NO trae articulado ni siglas de código de ningún país",
          not encontrados, f"aparece: {', '.join(encontrados)}")

    passed = sum(1 for _, ok in _results if ok)
    total = len(_results)
    print(f"\nRESULT: {passed}/{total} checks PASS")
    return 0 if passed == total else 1


if __name__ == "__main__":
    sys.exit(main())
