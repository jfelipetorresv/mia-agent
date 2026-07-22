"""
Mia · test_eval_panel.py — gate del PANEL DE MÉTRICAS del banco de pruebas (F1 · Frente C).

El hallazgo que ataca: el resumen de una corrida imprimía 3-4 números (casos, llegaron a
borrador, citas sin respaldo, costo). Con eso no se puede decidir nada sobre si el banco
está listo para correr en serio contra el modelo vivo. Este gate cubre el PANEL nuevo
(`backend/mia/eval/harness.py`): cobertura/precisión de respaldo, FALSOS BLOQUEOS (la
métrica que faltaba), detección guardián-vs-modelo-obediente, fuga de jurisdicción por
tasa, abstención honesta, éxito de tarea, latencia p50/p95 (informativa, nunca un gate) y
coste por turno con variabilidad — más la versión del baseline (hash de prompt + modelos
servidos) que viaja al disco.

Todo OFFLINE y puro (sin DB, sin red, sin LLM): las funciones de este frente son agregados
sobre resultados de caso YA calculados (o sobre fixtures que imitan su forma).

Salida: exit 0 = PASS · exit 1 = FAIL.

    .venv\\Scripts\\python.exe execution\\test_eval_panel.py
"""
from __future__ import annotations

import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

from mia.eval import harness  # noqa: E402

_results: list[tuple[str, bool]] = []


def check(name: str, ok) -> None:
    _results.append((name, bool(ok)))
    print(("  [OK]   " if ok else "  [FAIL] ") + name)


# ── FALSOS BLOQUEOS ────────────────────────────────────────────────────────────
def false_block_checks() -> None:
    print("\n-- false_block_signal: la métrica que falta (marcas sobre citas SÍ respaldadas) --")

    sin_marcadas = {"detalle": [{"cita": "Decreto 100 de 2020", "estado": "anotada"},
                                {"cita": "Ley 80 de 1993", "estado": "respaldada"}]}
    r0 = harness.false_block_signal(sin_marcadas, [{"referencia": "Decreto 100 de 2020"}])
    check("sin citas 'marcada' → 0 evaluables, 0 falsos, tasa 0.0",
          r0["citas_marcadas"] == 0 and r0["falsos_bloqueos"] == 0
          and r0["tasa_falsos_bloqueos"] == 0.0)

    # La cita SÍ está en las fuentes del corpus, pero el MODELO la marcó espontáneamente
    # con [VERIFICAR] (estado 'marcada') → falso bloqueo.
    con_respaldo_real = {"detalle": [{"cita": "Ley 1437 de 2011", "estado": "marcada"}]}
    r1 = harness.false_block_signal(con_respaldo_real, [{"referencia": "Ley 1437 de 2011"}])
    check("cita marcada por el modelo pero SÍ respaldada por el corpus → falso bloqueo",
          r1["citas_marcadas"] == 1 and r1["falsos_bloqueos"] == 1
          and r1["tasa_falsos_bloqueos"] == 1.0
          and r1["detalle"] == ["Ley 1437 de 2011"])

    # MUTACIÓN (sobre el dato, no el código): la MISMA cita marcada, pero el corpus de
    # este turno NO la trae — no hay forma de saber si estaba respaldada, así que NO
    # cuenta como falso bloqueo. Demuestra que la señal responde a las FUENTES, no a la
    # sola presencia de la marca.
    r2 = harness.false_block_signal(con_respaldo_real, [{"referencia": "Decreto 19 de 2012"}])
    check("MUTADO — misma cita marcada, pero el corpus NO la respalda → 0 falsos bloqueos "
          "(la señal depende de las fuentes reales, no solo de que exista la marca)",
          r2["citas_marcadas"] == 1 and r2["falsos_bloqueos"] == 0
          and r2["tasa_falsos_bloqueos"] == 0.0)

    r3 = harness.false_block_signal({}, None)
    check("informe vacío/None → no revienta, 0 evaluables", r3["citas_marcadas"] == 0)

    r4 = harness.false_block_signal(None, [{"referencia": "Ley 1437 de 2011"}])
    check("verification_report=None → no revienta (se trata como informe vacío)",
          r4["citas_marcadas"] == 0 and r4["falsos_bloqueos"] == 0)


# ── ABSTENCIÓN honesta ─────────────────────────────────────────────────────────
def abstention_checks() -> None:
    print("\n-- abstention_signal: ¿Mia reconoce cuando NO puede respaldar algo? --")

    honesto = ("El expediente no trae prueba de la cuantía. No cuento con elementos "
               "suficientes para fijar el monto de la indemnización en este turno.")
    r1 = harness.abstention_signal(honesto, "")
    check("frase honesta de abstención → abstiene=True",
          r1["abstiene"] is True and len(r1["frases_detectadas"]) >= 1)

    limpio = "Con fundamento en la Ley 1437 de 2011 se propone la excepción de caducidad."
    r2 = harness.abstention_signal(limpio, "")
    check("sin frase de abstención → abstiene=False", r2["abstiene"] is False)

    # MUTACIÓN: el MISMO texto limpio, se le añade una frase de abstención → debe encender.
    mutado = limpio + " Sin el expediente completo no es posible fundamentar más."
    r3 = harness.abstention_signal(mutado, "")
    check("MUTADO — se añade una frase de abstención al texto limpio → SÍ se detecta",
          r3["abstiene"] is True)

    # También se detecta si viene por el BORRADOR, no solo por el diagnóstico.
    r4 = harness.abstention_signal("", "No cuento con fundamento suficiente para esta parte.")
    check("la abstención en el BORRADOR también se detecta (no solo en el diagnóstico)",
          r4["abstiene"] is True)


# ── build_quality_panel ────────────────────────────────────────────────────────
def _case(case_id, *, citas=0, respaldadas=0, marcadas=0, sin_respaldo=0, reached=True,
         closing=True, elapsed_ms=None, cost_usd=None, tokens=0, calls=0,
         falsos_bloqueos=0, citas_marcadas_evaluables=None, abstiene=False,
         diag="", draft="", error=None) -> dict:
    c: dict = {
        "case_id": case_id,
        "reached_draft": reached,
        "diagnosis_preview": diag,
        "draft_preview": draft,
        "score": {"citas": citas, "citas_respaldadas": respaldadas, "citas_marcadas": marcadas,
                  "citas_sin_respaldo": sin_respaldo, "has_diagnosis_closing": closing},
        "false_block": {"citas_marcadas": (citas_marcadas_evaluables
                                           if citas_marcadas_evaluables is not None else marcadas),
                        "falsos_bloqueos": falsos_bloqueos},
        "abstention": {"abstiene": abstiene, "frases_detectadas": []},
    }
    if error:
        c["error"] = error
    if elapsed_ms is not None:
        c["elapsed_ms"] = elapsed_ms
    if cost_usd is not None:
        c["usage"] = {"cost_usd": cost_usd, "total_tokens": tokens, "calls": calls,
                      "models": {"claude-sonnet": calls}}
    return c


def panel_checks() -> None:
    print("\n-- build_quality_panel: agregación (F1 · Frente C) --")

    vacio = harness.build_quality_panel([])
    check("lista vacía → n=0, no revienta", vacio == {"n": 0})

    # Un caso limpio: 2 citas, 1 respaldada + 1 marcada (por el modelo, SIN falso bloqueo),
    # 0 anotadas por el guardián, éxito de tarea, sin fuga, sin abstención.
    c1 = _case("c1", citas=2, respaldadas=1, marcadas=1, sin_respaldo=0,
               elapsed_ms=1000.0, cost_usd=0.10, tokens=500, calls=2)
    # Segundo caso: 1 cita SIN respaldo (el guardián tuvo que anotarla) + fuga de
    # jurisdicción en el borrador + abstención.
    c2 = _case("c2", citas=1, respaldadas=0, marcadas=0, sin_respaldo=1, reached=True,
               closing=False, elapsed_ms=3000.0, cost_usd=0.30, tokens=1500, calls=1,
               abstiene=True, draft="Con fundamento en la Ley 1437 de 2011 se resuelve todo.")
    panel = harness.build_quality_panel([c1, c2])

    check("panel: n=2, sin errores", panel["n"] == 2 and panel["n_con_error"] == 0)
    check("panel: cobertura_respaldo = 1 respaldada / 3 citas totales = 0.3333",
          panel["respaldo"]["citas_totales"] == 3
          and abs(panel["respaldo"]["cobertura_respaldo"] - round(1 / 3, 4)) < 1e-9)
    check("panel: sin falsos bloqueos → precisión de respaldo = 1.0",
          panel["respaldo"]["falsos_bloqueos"] == 0
          and panel["respaldo"]["precision_respaldo"] == 1.0)
    check("panel: tasa_guardian_determinista = 1 anotada / 3 citas",
          abs(panel["deteccion"]["tasa_guardian_determinista"] - round(1 / 3, 4)) < 1e-9)
    check("panel: tasa_modelo_obediente = 1 marcada / 3 citas",
          abs(panel["deteccion"]["tasa_modelo_obediente"] - round(1 / 3, 4)) < 1e-9)
    check("panel: fuga de jurisdicción detectada en 1/2 (c2 cita articulado concreto)",
          panel["fuga_jurisdiccion"]["n_con_fuga"] == 1
          and panel["fuga_jurisdiccion"]["tasa"] == 0.5)
    check("panel: abstención en 1/2", panel["abstencion"]["n_con_abstencion"] == 1
          and panel["abstencion"]["tasa"] == 0.5)
    check("panel: éxito de tarea solo en c1 (c2 no tiene cierre de diagnóstico) → 1/2",
          panel["exito_tarea"]["n_con_exito"] == 1 and panel["exito_tarea"]["tasa"] == 0.5)
    check("panel: latencia p50/p95 calculados sobre los 2 casos medidos",
          panel["latencia_ms"]["n_medidos"] == 2 and panel["latencia_ms"]["max"] == 3000.0
          and panel["latencia_ms"]["min"] == 1000.0)
    check("panel: coste total = 0.40, media = 0.20, tokens totales = 2000",
          abs(panel["coste_usd"]["total"] - 0.40) < 1e-9
          and abs(panel["coste_usd"]["media"] - 0.20) < 1e-9
          and panel["tokens_totales"] == 2000 and panel["llamadas_totales"] == 3)

    # MUTACIÓN: c1 pasa a tener un falso bloqueo (el modelo se marcó de más sobre algo
    # respaldado) → la precisión de respaldo DEBE bajar de 1.0. Es la prueba de que el
    # panel de verdad refleja `false_block_signal` y no un número fijo.
    c1_con_falso = dict(c1)
    c1_con_falso["false_block"] = {"citas_marcadas": 1, "falsos_bloqueos": 1}
    panel_mutado = harness.build_quality_panel([c1_con_falso, c2])
    check("MUTADO — un falso bloqueo en c1 → precisión de respaldo baja de 1.0",
          panel_mutado["respaldo"]["falsos_bloqueos"] == 1
          and panel_mutado["respaldo"]["precision_respaldo"] < 1.0)

    # Casos que NUNCA corrieron de verdad (cortados por el tope, sin elapsed_ms/usage
    # reales) se cuentan en n pero se EXCLUYEN de latencia/coste — un 0 falso ahí
    # falsearía la media a la baja.
    cortado = {"case_id": "c3", "error": "CORTE POR EL TOPE DE GASTO", "reached_draft": False,
              "score": {"citas": 0, "citas_respaldadas": 0, "citas_marcadas": 0,
                        "citas_sin_respaldo": 0, "has_diagnosis_closing": False}}
    panel_con_corte = harness.build_quality_panel([c1, c2, cortado])
    check("panel: un caso cortado por el tope se cuenta en n y en n_con_error, pero NO "
          "contamina latencia/coste (siguen midiendo solo 2, no 3)",
          panel_con_corte["n"] == 3 and panel_con_corte["n_con_error"] == 1
          and panel_con_corte["latencia_ms"]["n_medidos"] == 2
          and panel_con_corte["coste_usd"]["n_medidos"] == 2)


# ── precision_respaldo: aritmética fijada con VALORES CONOCIDOS (C-MAY2) ──────
def precision_respaldo_checks() -> None:
    print("\n-- precision_respaldo / cobertura_respaldo: aritmética con valores conocidos "
          "(C-MAY2) --")

    # Dos casos idénticos con números elegidos para que el resultado dependa del DENOMINADOR
    # exacto, no solo de que baje de 1.0:
    #   · total_marcas = Σ(citas_marcadas + citas_sin_respaldo) = (1+1) + (1+1) = 4
    #   · falsos       = Σ falsos_bloqueos                       = 1 + 1        = 2
    #   → precision_respaldo = 1 - 2/4 = 0.5   EXACTO
    #   · citas        = 2 + 2 = 4 · respaldadas = 1 + 1 = 2
    #   → cobertura_respaldo = 2/4 = 0.5       EXACTO
    # Si alguien muta el denominador de precisión (p. ej. total_marcas*2), sale 1-2/8=0.75,
    # que ≠ 0.5 → esta aserción cae. La prueba anterior solo pedía "< 1.0" y por eso era
    # ciega a la aritmética.
    cA = _case("pA", citas=2, respaldadas=1, marcadas=1, sin_respaldo=1,
               falsos_bloqueos=1, citas_marcadas_evaluables=1)
    cB = _case("pB", citas=2, respaldadas=1, marcadas=1, sin_respaldo=1,
               falsos_bloqueos=1, citas_marcadas_evaluables=1)
    panel = harness.build_quality_panel([cA, cB])
    check("precision_respaldo = 1 - (2 falsos / 4 marcas) = 0.5 EXACTO "
          "(fija el denominador total_marcas = Σ citas_marcadas + Σ citas_sin_respaldo)",
          panel["respaldo"]["precision_respaldo"] == 0.5)
    check("cobertura_respaldo = 2 respaldadas / 4 citas = 0.5 EXACTO "
          "(fija su denominador Σ citas)",
          panel["respaldo"]["cobertura_respaldo"] == 0.5)

    # Segundo punto de anclaje con OTRO valor (no 0.5, para que un valor constante casual no
    # pase las dos): total_marcas = (2+1) = 3, falsos = 1 → precision = 1 - 1/3 = 0.6667.
    cC = _case("pC", citas=3, respaldadas=2, marcadas=2, sin_respaldo=1,
               falsos_bloqueos=1, citas_marcadas_evaluables=2)
    panel_c = harness.build_quality_panel([cC])
    check("precision_respaldo = 1 - (1 falso / 3 marcas) = 0.6667 EXACTO",
          panel_c["respaldo"]["precision_respaldo"] == round(1 - 1 / 3, 4))
    check("cobertura_respaldo = 2 respaldadas / 3 citas = 0.6667 EXACTO",
          panel_c["respaldo"]["cobertura_respaldo"] == round(2 / 3, 4))


# ── precision_respaldo: clamp [0,1] + desincronía visible (C-MEN) ─────────────
def precision_clamp_checks() -> None:
    print("\n-- precision_respaldo: clamp [0,1] y desincronía DECLARADA (C-MEN) --")

    # Fuentes de conteo desincronizadas: denominador total_marcas = marcadas(1)+sin_respaldo(0)
    # = 1, pero el numerador falsos_bloqueos = 3 (viene del bucket 'marcada' del informe, otra
    # fuente). 1 - 3/1 = -2 → SIN clamp imprimiría un negativo imposible.
    c_desync = _case("desync", citas=1, respaldadas=0, marcadas=1, sin_respaldo=0,
                     falsos_bloqueos=3, citas_marcadas_evaluables=1)
    panel = harness.build_quality_panel([c_desync])
    check("falsos (3) > marcas (1) → precision_respaldo acotada a 0.0, nunca un negativo",
          panel["respaldo"]["precision_respaldo"] == 0.0)
    check("la desincronía se DECLARA (precision_respaldo_desincronizada=True), no se esconde",
          panel["respaldo"]["precision_respaldo_desincronizada"] is True)

    # Caso sano: falsos <= marcas → sin desincronía y precisión normal.
    c_ok = _case("ok", citas=2, respaldadas=1, marcadas=1, sin_respaldo=1, falsos_bloqueos=1)
    panel_ok = harness.build_quality_panel([c_ok])
    check("caso sano (falsos <= marcas) → desincronizada=False",
          panel_ok["respaldo"]["precision_respaldo_desincronizada"] is False)


# ── fuga: se agrega desde la señal PERSISTIDA sobre el texto COMPLETO (C-MAY1) ─
def jurisdiction_leak_persisted_checks() -> None:
    print("\n-- build_quality_panel: la fuga se agrega desde la señal PERSISTIDA (texto "
          "COMPLETO), no se recalcula sobre el preview truncado (C-MAY1) --")

    # Preview LIMPIO (sin cita), pero la señal persistida —que run_case calcula sobre el
    # borrador ENTERO— dice que SÍ hubo fuga (la cita vivía más allá de _DRAFT_PREVIEW_CHARS).
    # El panel DEBE contar la fuga desde la señal persistida, no desde el preview.
    c = _case("leak_full", citas=1, respaldadas=1, draft="texto de muestra sin ninguna cita")
    c["jurisdiction_leak"] = {"citas_detectadas": 2, "detalle": ["Ley 1437 de 2011"],
                              "leak": True}
    panel = harness.build_quality_panel([c])
    check("fuga contada desde la señal persistida aunque el preview esté limpio "
          "(si el panel volviera a medir sobre el preview, esto daría 0)",
          panel["fuga_jurisdiccion"]["n_con_fuga"] == 1
          and panel["fuga_jurisdiccion"]["tasa"] == 1.0)

    # La MISMA señal persistida en False manda sobre un preview que SÍ tiene cita: prueba que
    # el panel obedece el texto completo persistido, no el preview.
    c2 = _case("leak_prev", citas=1, respaldadas=1,
               draft="Con fundamento en la Ley 1437 de 2011 se resuelve.")
    c2["jurisdiction_leak"] = {"citas_detectadas": 0, "detalle": [], "leak": False}
    panel2 = harness.build_quality_panel([c2])
    check("señal persistida leak=False manda sobre un preview con cita → 0 fugas",
          panel2["fuga_jurisdiccion"]["n_con_fuga"] == 0)

    # Sin señal persistida (fixture/corrida vieja) → fallback: recalcula sobre el preview.
    c3 = _case("leak_fb", citas=1, respaldadas=1,
               draft="Con fundamento en la Ley 1437 de 2011 se resuelve.")
    panel3 = harness.build_quality_panel([c3])
    check("sin señal persistida → fallback recalcula sobre el preview (retrocompat)",
          panel3["fuga_jurisdiccion"]["n_con_fuga"] == 1)


# ── jurisdiction_leak_rate: la TASA obedece la señal PERSISTIDA (R3-COBERTURA) ─
def jurisdiction_leak_rate_persisted_checks() -> None:
    print("\n-- jurisdiction_leak_rate: la tasa cuenta desde la señal PERSISTIDA sobre el "
          "texto COMPLETO, no recalcula sobre el preview (R3-COBERTURA) --")

    # Hallazgo del verificador (ronda 2): `jurisdiction_leak_rate` PREFIERE la señal que
    # `run_case` persiste sobre el borrador ENTERO, pero mutarla para que la IGNORE (recalcular
    # sobre el preview truncado) dejaba el panel verde — la función estaba sin blindar. El panel
    # (`build_quality_panel`) tiene su propio candado (jurisdiction_leak_persisted_checks), pero
    # NADIE cubría la función `jurisdiction_leak_rate` directamente. Estos checks lo cierran.

    # Preview LIMPIO (sin cita), señal persistida leak=True: la cita vivía más allá del preview.
    # La TASA tiene que contarla. MUTACIÓN: en `jurisdiction_leak_rate`, ignorar
    # `r.get("jurisdiction_leak")` y recalcular sobre el preview → n_con_fuga baja a 0 → ROJO.
    r_persist = harness.jurisdiction_leak_rate([
        {"matter_id": "m1", "diagnosis_preview": "texto de diagnóstico sin ninguna cita",
         "draft_preview": "borrador de muestra completamente limpio",
         "jurisdiction_leak": {"citas_detectadas": 2, "detalle": ["Ley 1437 de 2011"],
                               "leak": True}},
    ])
    check("tasa: preview LIMPIO + señal persistida leak=True → cuenta la fuga (1/1); si la "
          "función recalculara sobre el preview daría 0",
          r_persist["n"] == 1 and r_persist["n_con_fuga"] == 1 and r_persist["tasa"] == 1.0)

    # La inversa (blinda en el otro sentido): preview CON cita, señal persistida leak=False → la
    # tasa NO la cuenta. Si la función mirara el preview, contaría 1 → ROJO. Prueba que manda la
    # señal persistida, no el texto truncado.
    r_persist_false = harness.jurisdiction_leak_rate([
        {"matter_id": "m2",
         "diagnosis_preview": "Con fundamento en la Ley 1437 de 2011 se resuelve.",
         "draft_preview": "Con fundamento en el Decreto 1069 de 2015 se decide.",
         "jurisdiction_leak": {"citas_detectadas": 0, "detalle": [], "leak": False}},
    ])
    check("tasa: preview CON cita + señal persistida leak=False → NO cuenta fuga (0/1); si "
          "mirara el preview contaría 1 (manda la señal persistida)",
          r_persist_false["n"] == 1 and r_persist_false["n_con_fuga"] == 0
          and r_persist_false["tasa"] == 0.0)


# ── versión del baseline (hash de prompt + modelos servidos) ──────────────────
def version_checks() -> None:
    print("\n-- prompt_version_hash / served_models_signal: versionar el baseline (F1) --")

    h1 = harness.prompt_version_hash()
    h2 = harness.prompt_version_hash()
    check("prompt_version_hash: determinista (misma llamada, mismo hash) y no vacío",
          h1 == h2 and bool(h1) and h1 != "desconocido")

    # MUTACIÓN real: el módulo de prompt_builder cambia de contenido en disco → el hash
    # de la SIGUIENTE corrida tiene que ser DISTINTO (si no, dos corridas con prompts
    # distintos se compararían como si fueran el mismo baseline).
    from mia.agent import prompt_builder as pb
    real_path = Path(pb.__file__)
    original = real_path.read_bytes()
    try:
        real_path.write_bytes(original + b"\n# mutacion de prueba del hash de prompt\n")
        h_mutado = harness.prompt_version_hash()
        check("MUTACIÓN REAL — se le añade una línea a prompt_builder.py → el hash CAMBIA "
              "(demuestra que el gate detectaría una deriva de prompt real)",
              h_mutado != h1)
    finally:
        real_path.write_bytes(original)
    h_restaurado = harness.prompt_version_hash()
    check("restaurado el archivo → el hash vuelve a ser el original", h_restaurado == h1)

    # Sin fuente legible (empaquetado sin fuente) → 'desconocido', nunca un hash inventado.
    class _FakeModule:
        __file__ = str(ROOT / "no-existe-de-verdad.py")
    original_file = pb.__file__
    try:
        pb.__file__ = _FakeModule.__file__
        check("sin fuente legible → 'desconocido' (nunca un hash que aparente estabilidad)",
              harness.prompt_version_hash() == "desconocido")
    finally:
        pb.__file__ = original_file

    modelos = harness.served_models_signal([
        {"usage": {"models": {"claude-sonnet": 3, "cli-claude": 1}}},
        {"usage": {"models": {"claude-sonnet": 2}}},
        {"usage": None},
        {},
    ])
    check("served_models_signal: agrega across casos (claude-sonnet=5, cli-claude=1)",
          modelos == {"claude-sonnet": 5, "cli-claude": 1})
    check("served_models_signal: lista vacía → {}", harness.served_models_signal([]) == {})


# ── build_report / persist_report traen panel + version ───────────────────────
def report_checks() -> None:
    print("\n-- build_report / persist_report: panel + version viajan al disco --")

    c1 = _case("c1", citas=1, respaldadas=1, marcadas=0, sin_respaldo=0,
               elapsed_ms=500.0, cost_usd=0.01, tokens=100, calls=1)
    report = harness.build_report("eval_test_panel", [c1])
    check("build_report: trae panel con n_casos == n del panel",
          report["summary"]["n_casos"] == 1 and report["panel"]["n"] == 1)
    check("build_report: trae version con prompt_hash y modelos_servidos",
          bool(report["version"]["prompt_hash"])
          and report["version"]["modelos_servidos"] == {"claude-sonnet": 1})

    with tempfile.TemporaryDirectory() as td:
        run_dir = harness.persist_report(report, base_dir=td)
        import json
        disco = json.loads((run_dir / "summary.json").read_text(encoding="utf-8"))
        check("persist_report: summary.json en disco trae 'panel' y 'version'",
              "panel" in disco and "version" in disco
              and disco["panel"]["n"] == 1
              and disco["version"]["prompt_hash"] == report["version"]["prompt_hash"])


def main() -> int:
    false_block_checks()
    abstention_checks()
    panel_checks()
    precision_respaldo_checks()
    precision_clamp_checks()
    jurisdiction_leak_persisted_checks()
    jurisdiction_leak_rate_persisted_checks()
    version_checks()
    report_checks()

    passed = sum(1 for _, ok in _results if ok)
    total = len(_results)
    print(f"\n{passed}/{total} checks PASS")
    if passed == total:
        print("Panel de métricas OK — F1 · Frente C verificado.")
        return 0
    print("Panel de métricas FAIL — HALT: no avanzar (CLAUDE.md §G).")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
