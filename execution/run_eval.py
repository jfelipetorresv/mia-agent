"""
Mia · run_eval.py — corre el banco de pruebas de calidad EN VIVO (CP-E4, Ola 5).

Uso (con los servicios vivos: Postgres + LiteLLM :4000 + política de modelo):

    .venv\\Scripts\\python.exe execution\\run_eval.py                 # corrida "antes/después"
    .venv\\Scripts\\python.exe execution\\run_eval.py --run-id mi_corrida
    .venv\\Scripts\\python.exe execution\\run_eval.py --compare A B     # compara dos corridas ya hechas
    .venv\\Scripts\\python.exe execution\\run_eval.py --list-cases     # qué casos hay, sin correr nada
    .venv\\Scripts\\python.exe execution\\run_eval.py --case <id>       # corre UN caso (canónico o de riesgo)
    .venv\\Scripts\\python.exe execution\\run_eval.py --case <id> --repeat 5   # riesgo INTERMITENTE: tasa, no booleano
    .venv\\Scripts\\python.exe execution\\run_eval.py --agentic-compare        # MIA_AGENTIC_READING off→on, esta corrida

Corre los CASOS DE ORO SINTÉTICOS de `mia.eval.cases` por el grafo completo de asunto,
puntúa cada uno con señales deterministas (disciplina de citas, cierre del diagnóstico,
borrador) y guarda la corrida en `mia-data/eval-runs/{run_id}/`. Para medir si un cambio
mejora o empeora la calidad: corre ANTES (en main), corre DESPUÉS (en la rama) y
`--compare antes despues`.

FRENTE E (banco contra el modelo vivo, riesgos reales capturados en pruebas en vivo):
`--case`/`--repeat` corren UN caso de `cases.RISK_CASES` (o uno canónico) las veces que
haga falta y reportan la TASA de fuga de jurisdicción (nunca un booleano de una pasada —
el riesgo es INTERMITENTE). `--agentic-compare` corre el banco DOS veces en este mismo
proceso, alternando `mia.config.MIA_AGENTIC_READING` SOLO para esta corrida (nunca toca el
.env ni deja la bandera encendida al terminar) y compara tokens + motivo de parada de la
lectura agéntica entre el camino clásico y el agéntico.

FRENTE A (tope de gasto fail-closed): esta herramienta llama al modelo DE VERDAD, así que
corre siempre bajo `mia.eval.spend_guard.EvalSpendGuard`, con tres topes:
  · `--max-usd`      tope de ESTA corrida (default `DEFAULT_RUN_LIMIT_USD`);
  · sesión           USD 30 (`SESSION_LIMIT_USD`), PERSISTENTE entre corridas de la misma
                     sesión — `--session-id` (o `MIA_EVAL_SESSION_ID`) dice cuál es;
  · global           techo duro de seguridad sobre todas las sesiones.
El corte ocurre ANTES de la llamada que se pasaría (se estima su coste y se proyecta), deja
un margen para el cierre limpio, y si el gasto acumulado NO se puede verificar NO se gasta.
Cuando corta, el reporte PARCIAL se guarda igual y el motivo queda impreso y en disco.
`--spend` muestra el saldo acumulado y no corre nada.

El gasto del banco NO consume el presupuesto MENSUAL del despacho (lo gobierna este tope, que
es más estricto y fail-closed), y las rutas de red que este tope no puede gobernar —Pinecone
secundario y el CLI de NotebookLM del abogado— quedan DESACTIVADAS durante la corrida y
DECLARADAS en la salida bajo "AVISO — gasto FUERA del tope".

Crea un despacho EFÍMERO de prueba y lo borra al terminar (incl. sus checkpoints). NO usa
datos reales de cliente: eso exige el candado `allow_eval_real_data` del despacho (fail-closed).
"""
from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
from datetime import datetime
from pathlib import Path
from typing import Optional

import psycopg
from dotenv import load_dotenv

if sys.platform == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

ROOT = Path(__file__).resolve().parents[1]
load_dotenv(ROOT / ".env")
sys.path.insert(0, str(ROOT / "backend"))

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

from mia import config                                 # noqa: E402
from mia.agents.state import thread_id_for            # noqa: E402
from mia.db import pool                                # noqa: E402
from mia.eval import cases as cases_mod                # noqa: E402
from mia.eval import compare_reports                   # noqa: E402
from mia.eval import harness                           # noqa: E402
from mia.eval import spend_guard                       # noqa: E402

PG = dict(
    host=os.getenv("PG_HOST", "127.0.0.1"), port=os.getenv("PG_PORT", "5432"),
    dbname=os.getenv("PG_DB", "mia"), user="postgres", password=os.getenv("PG_PASSWORD", ""),
)


def _make_eval_tenant() -> str:
    with psycopg.connect(autocommit=True, **PG) as c:
        return str(c.execute(
            "INSERT INTO tenants(name) VALUES('[eval] banco de pruebas') RETURNING id"
        ).fetchone()[0])


def _drop_eval_tenant(tenant_id: str, matter_ids: list[str]) -> None:
    with psycopg.connect(autocommit=True, **PG) as c:
        for mid in matter_ids:
            tid = thread_id_for(tenant_id, mid)
            for t in ("checkpoint_writes", "checkpoint_blobs", "checkpoints"):
                try:
                    c.execute(f"DELETE FROM {t} WHERE thread_id=%s", (tid,))
                except Exception:  # noqa: BLE001 — limpieza best-effort
                    pass
        c.execute("DELETE FROM tenants WHERE id = %s", (tenant_id,))


def _print_spend(spend: dict) -> None:
    """Estado del tope de gasto en llano. Si el saldo no se pudo leer, se DICE."""
    if not spend:
        return
    ses = spend.get("session_spent_usd")
    glob = spend.get("global_spent_usd")
    ses_txt = f"USD {ses:.4f}" if isinstance(ses, (int, float)) else "no se pudo leer"
    glob_txt = f"USD {glob:.4f}" if isinstance(glob, (int, float)) else "no se pudo leer"
    print(f"  Gasto de esta corrida: USD {spend.get('run_spent_usd', 0.0):.4f} de un tope de "
          f"USD {spend.get('run_limit_usd', 0.0):.2f} "
          f"(margen de cierre reservado: USD {spend.get('closeout_reserve_usd', 0.0):.2f})")
    print(f"  Sesión '{spend.get('session_id')}': {ses_txt} de USD "
          f"{spend.get('session_limit_usd', 0.0):.2f} · acumulado global: {glob_txt} de USD "
          f"{spend.get('global_limit_usd', 0.0):.2f}")
    print(f"  Llamadas al modelo: {spend.get('calls', 0)} · tokens: "
          f"{spend.get('total_tokens', 0)} · tiempo dentro del modelo: "
          f"{spend.get('llm_seconds', 0.0):.1f}s")
    if spend.get("ledger_error"):
        print(f"  AVISO: {spend['ledger_error']}")
    if spend.get("stopped"):
        print(f"  *** CORTADA POR TOPE DE GASTO: {spend.get('stop_reason')}")
    # Gasto que el tope NO pudo gobernar (callbacks libres que no pasan por las capas
    # envueltas). Se dice en voz alta: un hueco declarado es auditable, uno silencioso no.
    for item in spend.get("gasto_no_gobernado") or []:
        print(f"  AVISO — gasto FUERA del tope ({item.get('que')}): {item.get('detalle')}")
    # Inventario del MODO HERMÉTICO: toda ruta capaz de gastar, con su estado. Se imprime
    # entero y siempre: la promesa del modo es que no hay una cuarta categoría (ni una ruta
    # sin clasificar), y esa promesa solo vale si se puede leer.
    rutas = spend.get("rutas_de_gasto") or []
    if rutas:
        conteo = {}
        for r in rutas:
            conteo[r.get("estado")] = conteo.get(r.get("estado"), 0) + 1
        resumen = " · ".join(f"{k}: {v}" for k, v in sorted(conteo.items()))
        print(f"  Rutas capaces de gastar: {len(rutas)} ({resumen})")
        for r in rutas:
            print(f"    - [{r.get('estado')}] {r.get('ruta')}")


def _print_version(version: dict) -> None:
    """Versión del baseline (F1): con qué prompt y qué modelo corrió esto. Sin esto, dos
    corridas de fechas distintas no se pueden comparar de buena fe (deriva de proveedor
    o de prompt)."""
    if not version:
        return
    modelos = version.get("modelos_servidos") or {}
    modelos_txt = ", ".join(f"{k}×{v}" for k, v in sorted(modelos.items())) or "(sin llamadas)"
    print(f"  Versión — hash de prompt: {version.get('prompt_hash')} · modelos servidos: "
          f"{modelos_txt}")


def _print_panel(panel: dict) -> None:
    """Panel de calidad en llano (F1 · Frente C): los números que SÍ dejan decidir algo,
    explicados para quien no programa. La latencia se informa pero NUNCA es un veredicto
    de pasa/no pasa — decisión del dueño del producto."""
    if not panel or not panel.get("n"):
        return
    n = panel["n"]
    resp = panel.get("respaldo", {})
    det = panel.get("deteccion", {})
    fuga = panel.get("fuga_jurisdiccion", {})
    abst = panel.get("abstencion", {})
    exito = panel.get("exito_tarea", {})
    lat = panel.get("latencia_ms", {})
    coste = panel.get("coste_usd", {})
    print(f"\n  --- Panel de calidad (sobre {n} corrida(s), {panel.get('n_con_error', 0)} con "
          f"error) ---")
    print(f"  Respaldo de citas: {resp.get('citas_respaldadas', 0)}/{resp.get('citas_totales', 0)}"
          f" confirmadas ({resp.get('cobertura_respaldo', 1.0):.0%} de cobertura) · "
          f"precisión de las marcas [VERIFICAR]: {resp.get('precision_respaldo', 1.0):.0%} "
          f"(falsos bloqueos: {resp.get('falsos_bloqueos', 0)} de "
          f"{resp.get('citas_marcadas_evaluables', 0)} marcas propias del modelo evaluables)")
    if resp.get("precision_respaldo_desincronizada"):
        # C-MEN: si las dos fuentes de conteo (falsos del informe vs marcas del score) no
        # cuadran, el número se acotó a [0,1]; el desajuste se DICE, no se esconde.
        print("  AVISO — precisión de respaldo DESINCRONIZADA: los falsos bloqueos superan las "
              "marcas contadas (dos fuentes de conteo distintas). El número se acotó a [0,1]; "
              "revisar el informe de verificación frente al score.")
    print(f"  Quién detectó la falta de respaldo: guardián determinista "
          f"{det.get('tasa_guardian_determinista', 0.0):.0%} de las citas · modelo obediente "
          f"(se marcó solo) {det.get('tasa_modelo_obediente', 0.0):.0%} de las citas")
    # M-2 (decisión de Pipe #45): «Éxito de tarea» inducía a leer «acertó» donde solo decía
    # «no se cayó». Se imprime lo que mide —turnos completados— y, cuando la corrida incluye
    # casos de RIESGO, al lado la señal que sí dice si acertó: se negó correctamente.
    completados = panel.get("turnos_completados") or {
        "n_completados": exito.get("n_con_exito", 0), "tasa": exito.get("tasa", 0.0)}
    print(f"  Fuga de jurisdicción: {fuga.get('n_con_fuga', 0)}/{n} corridas "
          f"({fuga.get('tasa', 0.0):.0%}) · Abstención honesta ('no puedo respaldar esto'): "
          f"{abst.get('n_con_abstencion', 0)}/{n} ({abst.get('tasa', 0.0):.0%}) · "
          f"Turnos completados (respondió sin caerse, con cierre): "
          f"{completados.get('n_completados', 0)}/{n} ({completados.get('tasa', 0.0):.0%})")
    neg = panel.get("negativa_correcta")
    if isinstance(neg, dict) and neg.get("n_casos_riesgo"):
        print(f"  Se negó correctamente (casos de RIESGO — reconoció el límite sin citas sin "
              f"respaldo ni fuga): {neg.get('n_negativa_correcta', 0)}/"
              f"{neg.get('n_casos_riesgo', 0)} ({neg.get('tasa', 0.0):.0%}) — en una trampa, "
              f"NO entregar borrador puede ser la respuesta correcta; ésta es la señal que "
              f"dice si acertó, no la de arriba")
    # N-1: menciones negadas y señales viejas sin texto releíble, si las hubo.
    if fuga.get("n_menciones_negadas"):
        print(f"  (N-1) menciones de una norma acompañadas de negación explícita — NO cuentan "
              f"como fuga: {fuga.get('n_menciones_negadas')}")
    if fuga.get("n_revision_pendiente"):
        print(f"  AVISO (N-1) — {fuga.get('n_revision_pendiente')} corrida(s) traen la señal de "
              f"fuga con la regla ANTERIOR y sin texto releíble para re-decidir: su cifra no es "
              f"comparable. Correr con MIA_EVAL_PERSIST_FULL=1 para que lo sea.")
    if lat.get("n_medidos"):
        print(f"  Latencia (informativa, NUNCA un gate): p50={lat.get('p50', 0.0)/1000:.1f}s · "
              f"p95={lat.get('p95', 0.0)/1000:.1f}s · rango "
              f"[{lat.get('min', 0.0)/1000:.1f}s – {lat.get('max', 0.0)/1000:.1f}s]")
    if coste.get("n_medidos"):
        print(f"  Coste por turno: media USD {coste.get('media', 0.0):.4f} · desviación USD "
              f"{coste.get('desviacion', 0.0):.4f} · rango [USD {coste.get('min', 0.0):.4f} – "
              f"USD {coste.get('max', 0.0):.4f}] · tokens totales: "
              f"{panel.get('tokens_totales', 0)} · llamadas: {panel.get('llamadas_totales', 0)}")


def _print_summary(report: dict) -> None:
    s = report.get("summary", {})
    print(f"\n=== Corrida {report['run_id']} ===")
    print(f"  Casos: {s.get('n_casos')} · llegaron a borrador: {s.get('n_llegaron_a_borrador')}"
          f" · sin problemas: {s.get('n_sin_problemas')} · con error: {s.get('n_con_error')}")
    print(f"  Total de citas SIN respaldo (a verificar): {s.get('total_citas_sin_respaldo')}")
    print(f"  Costo total: USD {float(s.get('costo_total_usd') or 0.0):.4f} · tokens: "
          f"{s.get('tokens_totales')} · duración total: "
          f"{float(s.get('duracion_total_ms') or 0.0) / 1000:.1f}s")
    _print_version(report.get("version", {}))
    _print_panel(report.get("panel", {}))
    _print_spend(report.get("spend", {}))
    if s.get("corte"):
        print(f"  CORTE: {s['corte']}")
        print("  (el reporte PARCIAL sí quedó guardado — los casos que alcanzaron a correr "
              "se midieron igual)")
    for c in report.get("cases", []):
        sc = c.get("score", {})
        flags = ", ".join(sc.get("flags", [])) or "ok"
        err = f" ERROR: {c['error']}" if c.get("error") else ""
        # marcadas = el MODELO ya trajo su propio [VERIFICAR]; sin_respaldo = las que tuvo
        # que anotar el GUARDIÁN porque no venían marcadas ni respaldadas por el corpus.
        print(f"  · {c['case_id']}: citas={sc.get('citas')} marcadas_modelo="
              f"{sc.get('citas_marcadas')} anotadas_guardian={sc.get('citas_sin_respaldo')} "
              f"respaldadas={sc.get('citas_respaldadas')} cierre={sc.get('has_diagnosis_closing')} "
              f"borrador={sc.get('draft_chars')}c [{flags}]{err}")
        # Coste y duración POR CASO: sin esto no se puede saber qué caso se come el
        # presupuesto (Frente A). `usage` es None si el caso corrió sin guardián.
        u = c.get("usage") or {}
        print(f"      costo=USD {float(u.get('cost_usd') or 0.0):.4f} · llamadas="
              f"{u.get('calls', 0)} · tokens={u.get('total_tokens', 0)} · "
              f"modelo={float(u.get('llm_seconds') or 0.0):.1f}s · "
              f"total={float(c.get('elapsed_ms') or 0.0) / 1000:.1f}s")
        prov = c.get("provenance") or {}
        if prov.get("atribucion_indebida"):
            print(f"    AVISO procedencia: atribuye al despacho/expediente sin material "
                  f"sellado — frases: {prov.get('frases_detectadas')}")


def _all_cases() -> list:
    """Casos registrados que `run_eval.py` puede correr por id: los canónicos + los de
    riesgo (Frente E) + los de expediente GRANDE (N-2). `load_tenant_gold_cases` (Banco de oro
    confirmado) NO entra aquí: exige un tenant real, y este comando trabaja sobre el despacho
    EFÍMERO de prueba.

    `load_golden_cases()` YA incluye los de riesgo desde el 2026-07-27, así que sumarlos otra
    vez los duplicaba en la lista de disponibles. Los GRANDES sí van aparte a propósito: no
    están en el examen por defecto (ver `cases.LARGE_CASES`)."""
    return list(cases_mod.load_golden_cases()) + list(cases_mod.load_large_cases())


def _find_case(case_id: str):
    for c in _all_cases():
        if c.id == case_id:
            return c
    disponibles = ", ".join(c.id for c in _all_cases())
    raise SystemExit(f"No existe el caso '{case_id}'. Disponibles: {disponibles}")


def _print_case_list() -> None:
    print("Casos canónicos (mia.eval.cases.GOLDEN_CASES — examen 'antes/después' de siempre):")
    for c in cases_mod.load_golden_cases():
        print(f"  · {c.id} — {c.title}")
    print("\nCasos de RIESGO (mia.eval.cases.RISK_CASES — Frente E; ya vienen incluidos arriba):")
    for c in cases_mod.RISK_CASES:
        print(f"  · {c.id} — {c.title}")
    print("\nCasos de EXPEDIENTE GRANDE (mia.eval.cases.LARGE_CASES — FUERA del examen por "
          "defecto: cuestan cientos de embeddings y cambiarían la composición del examen. "
          "Se corren a propósito, por id, para decidir si la lectura agéntica queda encendida):")
    for c in cases_mod.load_large_cases():
        n_frag = sum(len(d.chunks) for d in c.documents)
        print(f"  · {c.id} — {c.title} ({len(c.documents)} documentos, {n_frag} fragmentos)")


def _load_report(run_id: str) -> dict:
    run_dir = Path(harness._eval_dir()) / run_id
    cases = []
    with (run_dir / "cases.jsonl").open(encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                cases.append(json.loads(line))
    disk = json.loads((run_dir / "summary.json").read_text(encoding="utf-8"))
    # `version` (F1 — hash de prompt + modelos servidos) puede faltar en corridas viejas
    # (persistidas antes de este frente): {} en vez de KeyError, para no romper --compare
    # contra un baseline guardado antes de que esto existiera.
    return {"run_id": run_id, "cases": cases, "summary": disk.get("summary", {}),
            "version": disk.get("version", {})}


def _make_guard(args) -> spend_guard.EvalSpendGuard:
    """Guardián de gasto de ESTA invocación (topes de corrida/sesión/global).

    `source="cli"` NO es decorativo: separa el bolsillo de las pruebas de terminal del de la
    corrida in-app del abogado (`gold-cases:evaluate`, que usa `source="inapp"`). El gasto de
    PRUEBAS nunca debe poder agotar el saldo y bloquear el examen que lanza el despacho —
    ver `spend_guard.default_session_id`.
    """
    return spend_guard.EvalSpendGuard(
        run_limit_usd=(args.max_usd if args.max_usd is not None
                       else spend_guard.DEFAULT_RUN_LIMIT_USD),
        session_id=args.session_id or None,
        source="cli",
    )


EXIT_CORTADA = 2      # la corrida arrancó y el tope la detuvo a mitad
EXIT_BLOQUEADA = 3    # la corrida NI SIQUIERA arrancó (parada del guardián fuera del bucle)


def exit_code_for(report: dict) -> int:
    """Código de salida de una corrida. 2 = CORTADA (incompleta), 0 = completa.

    Mira DOS señales, no una: `summary.corte` (el motivo que el harness cableó al reporte) y
    `spend.stopped` (el guardián quedó parado). Con una sola, un corte que no llegara a
    escribirse en el resumen saldría con código 0 y `--compare` trataría una corrida parcial
    como si fuera entera. Una corrida cortada JAMÁS puede salir con 0.
    """
    summary = report.get("summary") or {}
    spend = report.get("spend") or {}
    return EXIT_CORTADA if (summary.get("corte") or spend.get("stopped")) else 0


async def _run(run_id: str, case_id: Optional[str] = None,
               guard: Optional[spend_guard.EvalSpendGuard] = None) -> dict:
    cases = [_find_case(case_id)] if case_id else None
    await pool.open_pool()
    tenant_id = _make_eval_tenant()
    matter_ids: list[str] = []
    try:
        report = await harness.run_suite(tenant_id, cases, run_id=run_id, guard=guard)
        matter_ids = [c.get("matter_id") for c in report.get("cases", []) if c.get("matter_id")]
        # Se persiste SIEMPRE, también cuando el tope cortó a mitad: el margen de cierre del
        # guardián existe justamente para que este paso alcance a ocurrir.
        harness.persist_report(report)
        return report
    finally:
        await pool.close_pool()
        _drop_eval_tenant(tenant_id, matter_ids)


# ── Frente E: repetir UN caso (riesgo INTERMITENTE — tasa, no booleano) ───────
async def _run_repeat(run_id: str, case_id: str, n: int,
                      guard: Optional[spend_guard.EvalSpendGuard] = None) -> dict:
    case = _find_case(case_id)
    await pool.open_pool()
    tenant_id = _make_eval_tenant()
    matter_ids: list[str] = []
    guard = guard or spend_guard.EvalSpendGuard()
    try:
        results = await harness.run_case_n(tenant_id, case, n, guard=guard)
        matter_ids = [r.get("matter_id") for r in results if r.get("matter_id")]
        # F0.2 (plan de eficiencia): el desglose por nodo se captura ANTES de que
        # _drop_eval_tenant borre las filas de turn_usage del tenant de eval.
        try:
            uso_por_nodo = await harness.usage_by_node(tenant_id)
        except Exception as exc:  # noqa: BLE001 — el desglose jamás tumba la corrida
            print(f"  AVISO: no se pudo capturar el uso por nodo del baseline: {exc}")
            uso_por_nodo = []
        leak = harness.jurisdiction_leak_rate(results)
        # F1 — con N repeticiones del MISMO caso, la variabilidad (coste, latencia,
        # falsos bloqueos...) ES parte del resultado, no ruido a esconder: mismo panel
        # que usa `run_suite`, aquí agregado sobre las N corridas de este caso.
        panel = harness.build_quality_panel(results)
        report = {"run_id": run_id, "case_id": case_id, "n": n, "results": results,
                  "cases": results, "leak": leak, "panel": panel,
                  "uso_por_nodo": uso_por_nodo,
                  "spend": guard.snapshot(),
                  "version": {
                      "prompt_hash": harness.prompt_version_hash(),
                      "modelos_servidos": harness.served_models_signal(results),
                  },
                  "summary": {"repeat": {"case_id": case_id, "n": n, "leak": leak}}}
        # Se persiste SIEMPRE, igual que en `_run`: el baseline se audita contra los
        # crudos en disco, no contra lo que quedó impreso en una consola que ya murió.
        harness.persist_report(report)
        return report
    finally:
        await pool.close_pool()
        _drop_eval_tenant(tenant_id, matter_ids)


def _print_repeat_summary(result: dict) -> None:
    leak = result["leak"]
    print(f"\n=== Repetición del caso '{result['case_id']}' × {result['n']} ===")
    if leak["n"] < result["n"]:
        # Honestidad estadística: la tasa es sobre las corridas que SÍ ocurrieron.
        print(f"  AVISO: se pidieron {result['n']} corridas y solo se hicieron {leak['n']} "
              "(el tope de gasto cortó). La tasa de abajo es sobre esas, no sobre las pedidas.")
    _print_spend(result.get("spend", {}))
    _print_panel(result.get("panel", {}))
    uso = result.get("uso_por_nodo") or []
    if uso:
        print("\n  --- Uso por nodo del grafo (F0, suma de las corridas) ---")
        for fila in uso:
            print(f"  · {fila['node']:<20} {fila['model']:<18} llamadas={fila['llamadas']:<3} "
                  f"prompt={fila['prompt_tokens']:>8} completion={fila['completion_tokens']:>8} "
                  f"total={fila['total_tokens']:>8}")
    print(f"  Fuga de jurisdicción detectada en {leak['n_con_fuga']}/{leak['n']} corridas "
          f"(tasa {leak['tasa']:.0%}). INTERMITENTE por diseño: una sola pasada limpia NO "
          "certifica que no vuelva a pasar.")
    for i, d in enumerate(leak["detalle"], 1):
        marca = "FUGA" if d["leak"] else "ok"
        print(f"  · corrida {i} [{marca}]: citas_detectadas={d['citas_detectadas']}"
              + (f" · ejemplo: {d['detalle'][0]!r}" if d["detalle"] else ""))


# ── Frente E: MIA_AGENTIC_READING off→on, solo esta corrida ───────────────────
async def _run_agentic_compare(run_id: str, case_id: Optional[str],
                               guard: Optional[spend_guard.EvalSpendGuard] = None) -> dict:
    cases = [_find_case(case_id)] if case_id else None
    await pool.open_pool()
    tenant_id = _make_eval_tenant()
    matter_ids: list[str] = []
    original_flag = config.MIA_AGENTIC_READING
    # UN solo guardián para las DOS pasadas: son la misma corrida y comparten el tope
    # (la pasada agéntica es justamente la cara, que es de lo que hay que protegerse).
    guard = guard or spend_guard.EvalSpendGuard()
    try:
        config.MIA_AGENTIC_READING = False
        off_report = await harness.run_suite(tenant_id, cases, run_id=f"{run_id}_agentic_off",
                                             guard=guard)
        matter_ids += [c.get("matter_id") for c in off_report.get("cases", [])
                       if c.get("matter_id")]
        harness.persist_report(off_report)

        config.MIA_AGENTIC_READING = True
        on_report = await harness.run_suite(tenant_id, cases, run_id=f"{run_id}_agentic_on",
                                            guard=guard)
        matter_ids += [c.get("matter_id") for c in on_report.get("cases", [])
                       if c.get("matter_id")]
        harness.persist_report(on_report)

        result = harness.compare_agentic_reports(off_report, on_report)
        result["spend"] = guard.snapshot()
        return result
    finally:
        # SIEMPRE se restaura, pase lo que pase: la bandera es solo de ESTA corrida, nunca
        # queda encendida para el resto del proceso ni se escribe en el .env.
        config.MIA_AGENTIC_READING = original_flag
        await pool.close_pool()
        _drop_eval_tenant(tenant_id, matter_ids)


def _print_agentic_compare(result: dict) -> None:
    print("\n=== MIA_AGENTIC_READING apagada → encendida (solo esta corrida) ===")
    _print_spend(result.get("spend", {}))
    print(f"  Casos comparados: {result['n_total']} · corrió el bucle agéntico en: "
          f"{result['n_corrio_agentic']}/{result['n_total']}")
    if result["n_total"] and result["n_corrio_agentic"] < result["n_total"]:
        print("  AVISO: donde NO corrió, el motor de la política de modelo activa no admite "
              "herramientas (o el tope de ampliaciones está en 0) — el turno se comportó "
              "igual que apagado. Ver agents.retrieval.agentic_reading_available().")
    for c in result["cases"]:
        motivo = c["motivo_parada"] or "n/a (no corrió)"
        print(f"  · {c['case_id']}: tokens off={c['tokens_off']} on={c['tokens_on']} "
              f"(Δ={c['delta_tokens']:+d}) · ampliaciones={c['ampliaciones']} · "
              f"motivo_parada={motivo}")
        # Segundo eje: ¿encontró los datos enterrados? Sin esto, un ahorro de tokens no se
        # puede leer (leer menos es también la forma de perder el dato).
        if c.get("recall_aplica"):
            print(f"      datos enterrados encontrados: apagada {c['recall_off']:.0%} → "
                  f"encendida {c['recall_on']:.0%} · {c['lectura_llana']}")
        else:
            print(f"      {c.get('lectura_llana', '')}")

    if result.get("veredicto_agregado") == "no_concluyente":
        print("\n  VEREDICTO: NO CONCLUYENTE — la lectura agéntica no corrió en ninguno de los "
              "casos, así que esta comparación NO decide si debe quedar encendida. Con el motor "
              "de la suscripción (aliases 'cli-*', que salen por subproceso al CLI) no hay "
              "herramientas y la lectura agéntica está estructuralmente apagada: para decidir "
              "N-2 hay que correr esto bajo una política cuyo motor las admita.")
    elif result.get("n_con_recall"):
        print(f"\n  VEREDICTO ({result['n_con_recall']} caso(s) con datos enterrados que "
              f"verificar): {result['veredicto_agregado'].upper()}")
        if result["veredicto_agregado"] == "peor":
            print("  Basta UN caso que pierda un dato del expediente para que la lectura "
                  "agéntica NO deba quedar encendida por defecto, por mucho que ahorre.")
    else:
        print("\n  VEREDICTO: no se corrió ningún caso con datos enterrados que verificar, así "
              "que esta comparación NO decide si la lectura agéntica debe quedar encendida. "
              "Para eso hay que correr un caso de expediente GRANDE (--list para verlos).")


def main() -> int:
    """Punto de entrada. Ninguna parada del guardián de gasto puede salir con código 0.

    S1 — `_main` puede levantar un `SpendGuardHalt` FUERA del bucle de casos: una ruta del
    registro que no se pudo clasificar (`SpendRouteUnavailable`, el banco no arranca), un juez
    rechazado, un saldo ilegible al activar. Como `SpendGuardHalt` hereda de `BaseException`,
    ningún `except Exception` intermedio se la come; aquí se convierte en salida distinta de
    cero CON EL MOTIVO VISIBLE, en vez de un traceback o —peor— un cero tranquilizador.
    """
    try:
        return _main()
    except spend_guard.SpendGuardHalt as exc:
        print(f"\n*** CORRIDA BLOQUEADA POR EL TOPE DE GASTO ({type(exc).__name__})")
        print(f"    {exc}")
        print("    No se corrió el banco. Esto NO es una corrida completa.")
        return EXIT_BLOQUEADA


def _main() -> int:
    ap = argparse.ArgumentParser(description="Banco de pruebas de calidad de Mia (CP-E4)")
    ap.add_argument("--run-id", default=None, help="id de la corrida (default: eval_<fecha>)")
    ap.add_argument("--compare", nargs=2, metavar=("ANTES", "DESPUES"),
                    help="compara dos corridas ya guardadas por su run_id")
    ap.add_argument("--list-cases", action="store_true",
                    help="lista los casos registrados (canónicos + de riesgo) y termina, "
                         "sin tocar la DB ni el motor")
    ap.add_argument("--case", default=None, metavar="ID",
                    help="corre UN caso por su id (canónico o de RISK_CASES) en vez del "
                         "examen completo; ver --list-cases")
    ap.add_argument("--repeat", type=int, default=None, metavar="N",
                    help="con --case: corre ese caso N veces seguidas y reporta la tasa de "
                         "fuga de jurisdicción (riesgo INTERMITENTE — una pasada no basta)")
    ap.add_argument("--agentic-compare", action="store_true",
                    help="corre el banco DOS veces en este proceso — MIA_AGENTIC_READING "
                         "apagada y luego encendida, SOLO para esta corrida — y compara "
                         "tokens y motivo de parada de la lectura agéntica (con --case, solo "
                         "ese caso; si no, los 3 canónicos)")
    ap.add_argument("--max-usd", type=float, default=None, metavar="USD",
                    help=f"tope de gasto de ESTA corrida en dólares (default "
                         f"{spend_guard.DEFAULT_RUN_LIMIT_USD}). El corte ocurre ANTES de la "
                         "llamada que se pasaría; el reporte parcial se guarda igual")
    ap.add_argument("--session-id", default=None, metavar="ID",
                    help=f"sesión a la que se carga el gasto (default: MIA_EVAL_SESSION_ID o "
                         f"'default'). El tope de sesión es USD "
                         f"{spend_guard.SESSION_LIMIT_USD:.0f} y PERSISTE entre corridas")
    ap.add_argument("--spend", action="store_true",
                    help="muestra el gasto acumulado (sesión y global) y termina, sin correr "
                         "nada ni tocar la DB")
    args = ap.parse_args()

    if args.list_cases:
        _print_case_list()
        return 0

    if args.spend:
        session_id = args.session_id or spend_guard.default_session_id("cli")
        try:
            acc = spend_guard.read_spend(session_id=session_id)
        except spend_guard.SpendControlUnavailable as exc:
            # Fail-closed también al informar: no se inventa un cero tranquilizador.
            print(f"No se pudo leer el gasto acumulado: {exc}")
            return 1
        print(f"Saldo del banco de pruebas (fichero: {spend_guard.default_ledger_path()})")
        print(f"  Sesión '{acc['session_id']}': USD {acc['session_usd']:.4f} de USD "
              f"{spend_guard.SESSION_LIMIT_USD:.2f}")
        print(f"  Acumulado global: USD {acc['global_usd']:.4f} de USD "
              f"{spend_guard.GLOBAL_LIMIT_USD:.2f}")
        return 0

    if args.max_usd is not None and args.max_usd <= 0:
        ap.error("--max-usd debe ser mayor que 0 (un tope de 0 no deja correr nada)")

    if args.compare:
        before, after = _load_report(args.compare[0]), _load_report(args.compare[1])
        # F1 — "ante cualquier cambio de modelo o de prompt el benchmark hay que
        # re-correrlo (deriva de proveedor)": comparar dos corridas con hash de prompt o
        # modelos servidos distintos es engañarse. Se AVISA, no se bloquea (--compare
        # sigue siendo útil para ver el detalle), porque una corrida vieja sin `version`
        # (persistida antes de este frente) no debe convertirse en un error duro.
        v_antes, v_despues = before.get("version") or {}, after.get("version") or {}
        h_antes, h_despues = v_antes.get("prompt_hash"), v_despues.get("prompt_hash")
        m_antes = sorted((v_antes.get("modelos_servidos") or {}).keys())
        m_despues = sorted((v_despues.get("modelos_servidos") or {}).keys())
        if h_antes and h_despues and h_antes != h_despues:
            print(f"  AVISO — el PROMPT cambió entre corridas (hash {h_antes} → {h_despues}): "
                  "esta comparación mide el efecto del cambio de prompt, no solo del código; "
                  "no es una comparación limpia de 'antes/después' del mismo prompt.")
        if m_antes and m_despues and m_antes != m_despues:
            print(f"  AVISO — el MODELO servido cambió entre corridas ({m_antes} → "
                  f"{m_despues}): la diferencia puede venir del proveedor, no del cambio "
                  "que se está evaluando (deriva de proveedor).")
        result = compare_reports(before, after)
        print(f"\n=== Comparación {args.compare[0]} → {args.compare[1]} ===")
        print(f"  Veredicto: {result['overall'].upper()}  "
              f"(regresiones={result['n_regresiones']} mejoras={result['n_mejoras']} "
              f"sin_cambio={result['n_sin_cambio']})")
        for c in result["cases"]:
            det = "; ".join(c["regressions"] + c["improvements"]) or "sin cambios"
            print(f"  · {c['case_id']}: {c['verdict'].upper()} — {det}")
        return 0

    if args.repeat is not None:
        if not args.case:
            ap.error("--repeat exige --case <id> (¿cuál caso repetir?)")
        run_id = args.run_id or f"eval_{datetime.now():%Y%m%d_%H%M%S}"
        result = asyncio.run(_run_repeat(run_id, args.case, args.repeat, _make_guard(args)))
        _print_repeat_summary(result)
        print(f"\nGuardada en mia-data/eval-runs/{run_id}/.")
        return exit_code_for(result)

    if args.agentic_compare:
        run_id = args.run_id or f"eval_{datetime.now():%Y%m%d_%H%M%S}"
        result = asyncio.run(_run_agentic_compare(run_id, args.case, _make_guard(args)))
        _print_agentic_compare(result)
        return exit_code_for(result)

    run_id = args.run_id or f"eval_{datetime.now():%Y%m%d_%H%M%S}"
    report = asyncio.run(_run(run_id, args.case, _make_guard(args)))
    _print_summary(report)
    print(f"\nGuardada en mia-data/eval-runs/{run_id}/. "
          f"Corre otra en la otra rama y usa --compare para el veredicto.")
    # Salida 2 = la corrida se cortó por tope: incompleta, no la compares como si fuera
    # una corrida entera (0 diría "todo bien" y el reporte parcial engañaría al --compare).
    return exit_code_for(report)


if __name__ == "__main__":
    raise SystemExit(main())
