"""
Mia · test_modo_barreras.py — el MODO declarado de cada barrera contra su conducta REAL.

Antes de este gate, la distinción aviso/muro vivía en comentarios de código
(graph.py, verification.py) y en una bandera de config: nadie auditaba que lo dicho
fuera lo hecho. Este gate porta la idea del `check-catalogo-barreras.py` del harness de
litigio: el catálogo (config/catalogo-barreras.json) declara `"modo": "aviso" | "muro"`
por barrera, y aquí cada declaración se coteja contra el código:

  - una barrera declarada MURO debe efectivamente bloquear (retirar texto, rechazar,
    levantar excepción o impedir el final), y
  - una barrera declarada AVISO no debe poder bloquear (su señal viaja en el informe o
    en el ledger; verification_passes y el flujo de aprobación no dependen de ella).

Cada invariante tiene su VERIFICADOR registrado abajo: devuelve el modo OBSERVADO
('muro' | 'aviso') o lanza con el porqué. Un id del catálogo sin verificador, o un
verificador sin id en el catálogo, también es rojo: nadie declara barreras que este
gate no mire, ni al revés. Verificadores funcionales donde la barrera es una función
pura; estructurales (sobre el código fuente importado) donde el bloqueo vive dentro de
un nodo async del grafo — y eso se declara en cada uno.

Regla de implantación (Pipe 2026-07-27, en la nota del catálogo): toda barrera nueva
nace como AVISO; este gate garantiza que un "muro" no se cuele por comentario.

    .venv\\Scripts\\python.exe execution\\test_modo_barreras.py

Exit 0 = todos los modos declarados coinciden con la conducta; 1 = alguno miente.
"""
from __future__ import annotations

import inspect
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

CATALOGO = ROOT / "config" / "catalogo-barreras.json"

_results: list[tuple[str, bool]] = []


def check(name: str, ok: bool) -> None:
    _results.append((name, bool(ok)))
    print(f"  [{'OK' if ok else 'FAIL'}] {name}")


# ── verificadores: id del catálogo → modo OBSERVADO ─────────────────────────────

def v_gate_lanzador_health() -> str:
    """Estructural: /health es la puerta del producto entero — sin API no hay turno.
    Se comprueba que la ruta exista en la app (el 200 en vivo lo exige
    test_catalogo_barreras, que es HALT-adjacente)."""
    from mia.api.main import app
    rutas = {getattr(r, "path", "") for r in app.routes}
    if "/health" not in rutas:
        raise AssertionError("la app ya no expone /health")
    return "muro"


def v_verification_unavailable_no_final() -> str:
    """Funcional: fail-closed de verdad — sin informe o con alertas abiertas no hay final."""
    from mia.memory.legal_ledger import verification_passes
    ok_gate = {"gate_llm": {"veredicto": "apto", "checker_version": "citation-verifier-v3"}, "evidence_coverage": {"complete": True}}
    bloquea_sin_informe = verification_passes(None) is False
    bloquea_marcadas = verification_passes({"marcadas": 1, **ok_gate}) is False
    bloquea_quemadas = verification_passes({"quemadas": 1, **ok_gate}) is False
    pasa_limpio = verification_passes({"marcadas": 0, **ok_gate}) is True
    if not (bloquea_sin_informe and bloquea_marcadas and bloquea_quemadas and pasa_limpio):
        raise AssertionError("verification_passes ya no es fail-closed")
    return "muro"


def v_hitl_hash_recibo() -> str:
    """Estructural (el bloqueo vive dentro del nodo async): una huella ausente o vieja
    convierte la aprobación en rechazo."""
    from mia.agents.graph import MatterGraphBuilder
    src = inspect.getsource(MatterGraphBuilder.hitl_checkpoint_node)
    if "supplied_hash != draft_hash" not in src or '"rejected"' not in src:
        raise AssertionError("hitl_checkpoint_node ya no rechaza por huella vieja")
    return "muro"


def v_draft_fail_closed_packs() -> str:
    """Funcional: sin packs aguas arriba, StageIncomplete."""
    from mia.agents import stage_gate
    try:
        stage_gate.require_upstream_for_draft({})
    except stage_gate.StageIncomplete:
        return "muro"
    raise AssertionError("require_upstream_for_draft({}) ya NO levanta StageIncomplete")


def v_suggestions_cron() -> str:
    """Estructural: vive en el scheduler, fuera de la ruta del turno — no puede frenar
    un turno ni una aprobación."""
    import mia.agents.graph as g
    if "generate_suggestions" in inspect.getsource(g):
        raise AssertionError("generate_suggestions apareció en la ruta del turno (graph.py)")
    return "aviso"


def v_telegram_lifespan() -> str:
    """Funcional: sin token devuelve 'skipped' sin lanzar — no puede tumbar el API."""
    from mia.channels.telegram_bridge import start_bridge_if_configured
    if start_bridge_if_configured(env={}) != "skipped":
        raise AssertionError("sin token ya no devuelve 'skipped'")
    return "aviso"


def v_export_events_reader() -> str:
    """Estructural: lectura pura — el productor no escribe ni rechaza nada."""
    from mia.memory import legal_ledger
    src = inspect.getsource(legal_ledger.list_exports)
    if "INSERT" in src.upper().replace("SELECT", ""):
        raise AssertionError("list_exports ya no es lectura pura")
    return "aviso"


def v_turn_budget_second_pass() -> str:
    """Funcional: la 2ª pasada cara sin autorización levanta TurnBudgetExceeded."""
    from mia.policy import turn_budget as tb
    task = next(iter(tb.EXPENSIVE_TASKS))
    md = {"expensive_calls": [task] * (tb.MAX_UNAUTH_EXPENSIVE + 1)}
    try:
        tb.authorize_expensive(md, task, authorized=False)
    except tb.TurnBudgetExceeded:
        # y con autorización explícita NO bloquea (el muro tiene su puerta)
        tb.authorize_expensive(md, task, authorized=True)
        return "muro"
    raise AssertionError("authorize_expensive ya no corta la pasada cara sin autorización")


def v_citas_quemadas() -> str:
    """Funcional: la cita quemada se RETIRA del texto emitido (eso ES bloquear)."""
    from mia.agents import verification as V
    banco = [{"citation": "Sentencia C-832 de 2002",
              "citation_norm": V._normalize("Sentencia C-832 de 2002"),
              "reason": "prueba del gate de modos"}]
    texto, informe = V.annotate_draft(
        "Se apoya en la Sentencia C-832 de 2002, criterio invocado.", burned=banco)
    if "C-832" in texto or V.BURNED_MARK not in texto:
        raise AssertionError("la cita quemada ya NO se retira del texto emitido")
    if not informe.get("quemadas"):
        raise AssertionError("el informe ya no cuenta las quemadas")
    return "muro"


def _clave_informe_no_bloquea(clave: str) -> None:
    """Un informe limpio de citas + la clave del aviso NO impide el final."""
    from mia.memory.legal_ledger import verification_passes
    report = {"citas": 1, "marcadas": 0, "respaldadas": 1, "anotadas": 0,
              clave: {"n_a_revisar": 2, "aviso": "prueba"},
              "gate_llm": {"veredicto": "apto", "checker_version": "citation-verifier-v3"}, "evidence_coverage": {"complete": True}}
    if verification_passes(report) is not True:
        raise AssertionError(
            f"la clave '{clave}' EMPEZÓ a bloquear el final: eso es un muro sin declarar")


def v_afirmaciones_negativas() -> str:
    """Funcional: el detector existe y su clave del informe no puede bloquear el final."""
    from mia.agents import verification as V
    claims = V.scan_negative_claims("El memorando no menciona a la aseguradora garante.")
    if not claims:
        raise AssertionError("scan_negative_claims ya no detecta la afirmación negativa")
    _clave_informe_no_bloquea("afirmaciones_negativas")
    return "aviso"


def v_contaminacion_expediente() -> str:
    """Funcional sobre el contrato del informe: su clave no puede bloquear el final."""
    import mia.agents.graph as g
    if not hasattr(g, "_check_foreign_parties"):
        raise AssertionError("desapareció _check_foreign_parties")
    _clave_informe_no_bloquea("contaminacion_expediente")
    return "aviso"


def v_fuente_identificacion() -> str:
    """Funcional: la bandera nace APAGADA (aviso). Si el default pasa a exigir, el modo
    observado sube a muro y este gate exige actualizar el catálogo en el mismo commit."""
    from mia import config
    return "muro" if config.MIA_FUENTE_IDENTIFICACION_EXIGIR else "aviso"


def v_raices_datos() -> str:
    """Estructural: el gate vive en execution/, fuera de la ruta del turno."""
    gate = ROOT / "execution" / "test_raices_datos.py"
    if not gate.is_file():
        raise AssertionError("falta execution/test_raices_datos.py")
    for f in (ROOT / "backend" / "mia").rglob("*.py"):
        if "test_raices_datos" in f.read_text(encoding="utf-8", errors="replace"):
            raise AssertionError(f"{f.name} importa el gate de raíces: entró a producción")
    return "aviso"


def v_medicion_por_nodo() -> str:
    """Estructural: gate en execution/ + record() de métricas JAMÁS lanza (no bloquea)."""
    gate = ROOT / "execution" / "test_medicion_por_nodo.py"
    if not gate.is_file():
        raise AssertionError("falta execution/test_medicion_por_nodo.py")
    from mia.metrics import usage
    # record() sin scope es no-op y nunca lanza — se prueba con un usage envenenado
    class _Veneno:
        def __getattr__(self, name):
            raise RuntimeError("veneno")
    usage.record("alias-inexistente", "main", _Veneno())  # si lanza, el gate cae aquí
    return "aviso"


def v_disposicion_hallazgos() -> str:
    """Funcional: los hallazgos sin disposición se REGISTRAN y jamás cambian la decisión."""
    import inspect as _i
    from mia.memory import hallazgos
    from mia.agents.graph import MatterGraphBuilder
    report = {"citas": 2, "marcadas": 1, "respaldadas": 1, "anotadas": 0,
              "detalle": [{"cita": "Ley 99 de 1999, artículo 1", "estado": "marcada"}],
              "gate_llm": {"veredicto": "hallazgos", "detalle": "una duda"}}
    abiertos = hallazgos.pendientes_de_disposicion(report, None)
    if len(abiertos) != 2:
        raise AssertionError(f"pendientes_de_disposicion dejó de extraer ({len(abiertos)})")
    # un informe malformado NUNCA lanza (aviso fail-soft)
    if hallazgos.pendientes_de_disposicion({"detalle": object()}, {"x": object()}) != []:
        raise AssertionError("el aviso dejó de ser fail-soft ante informe malformado")
    src = _i.getsource(MatterGraphBuilder.hitl_checkpoint_node)
    if "hallazgos_sin_disposicion" not in src:
        raise AssertionError("hitl_checkpoint_node ya no registra los hallazgos sin disposición")
    # el registro no puede tocar la decisión: la asignación no reasigna `dec`
    linea = next((ln for ln in src.splitlines() if "pendientes_de_disposicion" in ln), "")
    if linea.strip().startswith("dec"):
        raise AssertionError("la disposición de hallazgos está decidiendo el HITL: eso es un muro")
    return "aviso"


VERIFICADORES = {
    "gate-lanzador-health": v_gate_lanzador_health,
    "verification-unavailable-no-final": v_verification_unavailable_no_final,
    "hitl-hash-recibo": v_hitl_hash_recibo,
    "draft-fail-closed-packs": v_draft_fail_closed_packs,
    "suggestions-cron": v_suggestions_cron,
    "telegram-lifespan": v_telegram_lifespan,
    "export-events-reader": v_export_events_reader,
    "turn-budget-second-pass": v_turn_budget_second_pass,
    "citas-quemadas": v_citas_quemadas,
    "afirmaciones-negativas": v_afirmaciones_negativas,
    "contaminacion-expediente": v_contaminacion_expediente,
    "fuente-identificacion": v_fuente_identificacion,
    "raices-datos": v_raices_datos,
    "medicion-por-nodo": v_medicion_por_nodo,
    "disposicion-hallazgos": v_disposicion_hallazgos,
}

MODOS_VALIDOS = {"aviso", "muro"}


def main() -> int:
    data = json.loads(CATALOGO.read_text(encoding="utf-8"))
    invariantes = data.get("invariantes") or []
    check("el catálogo declara invariantes", bool(invariantes))

    ids = {i.get("id") for i in invariantes}
    sin_verificador = sorted(ids - set(VERIFICADORES))
    check(f"toda barrera del catálogo tiene verificador de modo (faltan: {sin_verificador or 'ninguna'})",
          not sin_verificador)
    huerfanos = sorted(set(VERIFICADORES) - ids)
    check(f"todo verificador tiene su barrera en el catálogo (huérfanos: {huerfanos or 'ninguno'})",
          not huerfanos)

    for item in invariantes:
        iid = item.get("id") or "?"
        modo = item.get("modo")
        check(f"{iid}: declara modo válido ('{modo}')", modo in MODOS_VALIDOS)
        if modo not in MODOS_VALIDOS or iid not in VERIFICADORES:
            continue
        try:
            observado = VERIFICADORES[iid]()
        except Exception as exc:  # noqa: BLE001 — el porqué del verificador ES el mensaje
            check(f"{iid}: verificador de conducta ({type(exc).__name__}: {exc})", False)
            continue
        check(f"{iid}: modo declarado '{modo}' == conducta observada '{observado}'",
              observado == modo)

    failed = [n for n, ok in _results if not ok]
    print(f"\n{len(_results) - len(failed)}/{len(_results)} checks OK")
    if failed:
        print("FAIL:", "; ".join(failed[:8]))
        return 1
    print("PASS: cada modo declarado en el catálogo coincide con la conducta del código.")
    return 0


if __name__ == "__main__":
    codigo = main()
    # Salida DETERMINISTA: v_gate_lanzador_health importa mia.api.main (la app completa)
    # y su teardown de intérprete puede morir con 0xC000013A de forma intermitente bajo
    # el verificador (proceso oculto). El veredicto ya está impreso y decidido: se sale
    # sin teardown para que el exit code sea el del gate, no el de la limpieza de la app.
    sys.stdout.flush()
    sys.stderr.flush()
    import os
    os._exit(codigo)
