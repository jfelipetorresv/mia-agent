"""Mia · eval.harness — correr el banco de pruebas y persistir la corrida (CP-E4).

Corre casos de oro por el GRAFO COMPLETO de asunto (headless, sin HTTP) y puntúa cada uno
con `scoring.score_turn`. Reusa exactamente el motor de producción: `initial_state` →
`build_matter_graph` → `astream` hasta el interrupt de HITL (donde el borrador y el informe
de verificación de citas YA existen) → `aget_state` para leer el estado. NO aprueba el
borrador (no toca HITL): solo mide lo que Mia produjo.

CANDADO DE DATOS REALES (regla dura, decisión de Pipe): un caso NO sintético (p. ej. sobre un
expediente real del despacho) SOLO corre si el despacho lo autorizó explícitamente
(`tenant_settings.config['eval']['allow_eval_real_data']`, default False, fail-closed). Sin
autorización → `EvalConsentError`. Los casos canónicos de `cases.py` son sintéticos y corren
sin fricción.

SEPARACIÓN: el harness siembra los asuntos de prueba BAJO el `tenant_id` que recibe (RLS) y
corre; el CICLO DE VIDA del tenant de prueba y la limpieza de checkpoints los maneja el
llamador (`execution/run_eval.py` o el gate) con conexión admin.

FRENTE E (banco contra el modelo vivo): además de `run_case`/`run_suite` (una pasada), este
módulo trae `run_case_n` + `jurisdiction_leak_rate` para riesgos INTERMITENTES (una corrida
limpia no basta) y `compare_agentic_reports` para medir coste/motivo de parada de la lectura
agéntica (`config.MIA_AGENTIC_READING`) sin encender la bandera global — la enciende y apaga
`execution/run_eval.py --agentic-compare`, alrededor de esta misma corrida.

FRENTE A (telemetría de coste + TOPE fail-closed): hasta ahora el banco corría el grafo
contra el modelo VIVO sin fijar el scope de uso, así que sus llamadas reales no quedaban
registradas (`metrics.usage.record` es un no-op sin scope) y —peor— la rama de reserva de
presupuesto de `agent.llm.call_llm`, que solo entra si HAY scope, nunca se activaba: el eval
podía gastar sin ningún techo. Ahora cada corrida:
  · fija la política de modelo del despacho y el scope de uso `source="eval"` (por caso, con
    su `matter_id`), de modo que cada llamada cae en `turn_usage` con tokens, alias y coste;
  · corre SIEMPRE bajo un `eval.spend_guard.EvalSpendGuard` (si el llamador no da uno, se crea
    con los topes por defecto: nunca hay corrida sin techo);
  · al cortar por tope, deja de correr casos y el reporte PARCIAL se devuelve igual, con el
    motivo del corte en `summary.corte` y en `report["spend"]`.
"""
from __future__ import annotations

import asyncio
import hashlib
import logging
import math
import os
import statistics
import time
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Optional

from .. import config, embeddings
from ..agent import prompt_builder
from ..agents import verification
from ..agents.verification import ABSTENTION_PHRASES  # M1: mudado a verification (regla 6)
from ..agents.checkpointer import open_checkpointer
from ..agents.graph import build_matter_graph
from ..agents.state import initial_state, thread_id_for
from ..db import pool
from ..metrics import usage as usage_metrics
from . import spend_guard
from .cases import GoldenCase, load_golden_cases, load_tenant_gold_cases
from .scoring import (
    jurisdiction_leak_signal,
    provenance_signal,
    score_turn,
    substantive_score,
)

logger = logging.getLogger("mia.eval.harness")

_DRAFT_PREVIEW_CHARS = 1200  # cuánto borrador se guarda en la corrida (evita ficheros enormes)


# ── FALSOS BLOQUEOS (F1 · Frente C) ───────────────────────────────────────────
# La métrica que falta y la más importante que nadie mide (decisión del dueño del
# producto, 2026-07-21): un guardián que marca TODO es tan inútil como uno que no marca
# nada. Un falso bloqueo es una marca [VERIFICAR] puesta sobre una afirmación que SÍ
# estaba correctamente respaldada.
def false_block_signal(verification_report: Any, sources: Any) -> dict:
    """Falsos bloqueos: citas que el MODELO marcó espontáneamente con [VERIFICAR]
    (estado 'marcada' en el informe de `agents.verification.annotate_draft`) pero que YA
    estaban respaldadas por el corpus recuperado en el turno — el modelo se autolimitó
    sobre algo que sí tenía soporte.

    POR QUÉ SOLO 'marcada' — `annotate_draft` clasifica cada cita en un `elif` en
    cascada (marcada → respaldada → anotada): una cita que YA trae su propia marca
    nunca se evalúa contra el corpus, así que "¿estaba respaldada de todos modos?" es
    una pregunta abierta SOLO para esa clase. Las 'anotadas' (el GUARDIÁN insertó la
    marca) por construcción YA fallaron ESE MISMO chequeo de respaldo — no pueden ser
    un falso bloqueo bajo la misma regla de cotejo que las produjo.

    LIMITACIÓN DECLARADA (dirección segura — nunca infla el número): solo comprueba
    respaldo por CORPUS (`sources`, el mismo cotejo que usa la disciplina de citas), no
    por ANCLA al expediente (eso exige la posición exacta de la cita en el texto, que el
    informe no conserva). Una cita autolimitada que solo estaba respaldada por el
    expediente (no por el corpus) NO se cuenta aquí como falso bloqueo: se subestima
    antes que inventar un defecto. Si se necesita la cifra completa, el informe de
    verificación tendría que conservar posiciones — pedido para el frente de
    verificación/citas, no de este módulo.

    Puro: no toca DB, red ni reloj.
    """
    report = verification_report if isinstance(verification_report, dict) else {}
    detalle = report.get("detalle")
    marcadas_detalle = [d for d in (detalle or [])
                        if isinstance(d, dict) and d.get("estado") == "marcada"]
    n_marcadas = len(marcadas_detalle)
    if n_marcadas == 0:
        return {"citas_marcadas": 0, "falsos_bloqueos": 0, "tasa_falsos_bloqueos": 0.0,
                "detalle": []}
    index = verification._tokenize_index(
        verification.source_index(sources if isinstance(sources, list) else None))
    culpables = [str(d.get("cita") or "") for d in marcadas_detalle
                if verification._backing_source_tokenized(str(d.get("cita") or ""), index)
                is not None]
    n_falsos = len(culpables)
    return {
        "citas_marcadas": n_marcadas,
        "falsos_bloqueos": n_falsos,
        "tasa_falsos_bloqueos": round(n_falsos / n_marcadas, 4),
        "detalle": culpables[:10],
    }


# ── ABSTENCIÓN honesta (F1 · Frente C) ────────────────────────────────────────
# Las frases (léxico GENÉRICO del español jurídico, sin país) viven ahora en
# agents/verification.py (M1: el informe por oración las necesita) y se reimportan arriba
# (`ABSTENTION_PHRASES`, regla 6). Su valor y su semántica quedan idénticos.
def abstention_signal(diagnosis: str, draft: str) -> dict:
    """TASA DE ABSTENCIÓN (F1 · Frente C): ¿Mia reconoció, en este turno, que NO puede
    respaldar algo? Determinista y puro — mismo estilo que `scoring.provenance_signal`.

    Deliberadamente CONSERVADOR (subestima antes que inventar): una abstención dicha con
    otras palabras no se detecta. No es lo mismo que `reached_draft=False` (eso es un
    FALLO: el turno no llegó a producir nada); esto mide la abstención HONESTA dentro de
    un turno que SÍ completó — la señal de disciplina que el dueño del producto pidió
    medir (un sistema que nunca dice "no puedo" es sospechoso, no ejemplar).
    """
    texto = verification._normalize((diagnosis or "") + " \n " + (draft or ""))
    hallazgos = [p for p in ABSTENTION_PHRASES if verification._normalize(p) in texto]
    return {"abstiene": bool(hallazgos), "frases_detectadas": hallazgos}


# ── versión del baseline (F1 · "sin eso, comparar dos corridas es engañarse") ──
def prompt_version_hash() -> str:
    """Hash del prompt vigente. Hashea el CÓDIGO FUENTE de `agent.prompt_builder` (las
    diez capas del prompt, CLAUDE.md §C) — ante cualquier cambio de ese módulo el hash
    cambia, así que dos corridas con hashes distintos NO son comparables sin releer qué
    cambió (deriva de prompt).

    LIMITACIÓN DECLARADA: no cubre instrucciones de prompt que vivan en otro módulo (p.
    ej. fragmentos ad hoc de `agents/graph.py`); es una aproximación declarada del
    prompt PRINCIPAL, no un hash exhaustivo de todo lo que el modelo llega a ver. Sin
    fuente legible (empaquetado sin fuente, `__file__` ausente) → 'desconocido', nunca
    un hash inventado que aparente una estabilidad que no existe.
    """
    try:
        src = Path(prompt_builder.__file__).read_bytes()
    except Exception:  # noqa: BLE001 — sin fuente legible, se dice, no se inventa
        return "desconocido"
    return hashlib.sha256(src).hexdigest()[:16]


def served_models_signal(case_results: list[dict]) -> dict:
    """Modelos SERVIDOS en esta corrida, agregados desde `usage.models` de cada caso
    (ya lo persiste `spend_guard.CaseUsage`, ver `harness.run_case`).

    GRANULARIDAD DECLARADA: es el ALIAS de la política (p. ej. 'claude-sonnet'), no el
    snapshot exacto del proveedor (p. ej. 'claude-sonnet-4-6') — `eval.spend_guard.
    _alias_and_cost` solo sustituye el alias por `resp.model` cuando ese valor YA es una
    de las claves de `metrics.usage.PRICES_PER_MTOK` (que son alias, no snapshots de
    proveedor), así que el snapshot real no sobrevive hasta aquí. Si se necesita el pin
    exacto de proveedor, `eval.spend_guard` tendría que exponer el `resp.model` crudo
    por separado del alias de tarifa — pedido para Frente A, no de este módulo.
    """
    conteo: dict[str, int] = {}
    for c in case_results:
        usage = c.get("usage")
        models = usage.get("models") if isinstance(usage, dict) else None
        if isinstance(models, dict):
            for alias, n in models.items():
                conteo[str(alias)] = conteo.get(str(alias), 0) + int(n or 0)
    return conteo


def _percentile(values: list[float], pct: float) -> float:
    """Percentil por interpolación lineal entre rangos (sin dependencias externas).
    Lista vacía → 0.0 (nunca lanza; la latencia se REPORTA, nunca bloquea — ver
    `build_quality_panel`)."""
    if not values:
        return 0.0
    ordered = sorted(values)
    if len(ordered) == 1:
        return round(float(ordered[0]), 1)
    k = (len(ordered) - 1) * (pct / 100.0)
    f, c = math.floor(k), math.ceil(k)
    if f == c:
        return round(float(ordered[int(k)]), 1)
    return round(float(ordered[int(f)] * (c - k) + ordered[int(c)] * (k - f)), 1)


def build_quality_panel(case_results: list[dict]) -> dict:
    """Panel de calidad del banco (F1 · Frente C, decisión del dueño del producto
    2026-07-21: "con 3 números no se puede decidir nada"). Reporta, sobre la lista de
    corridas que se le pase (sirve igual para el examen "antes/después" de `run_suite`,
    casos DISTINTOS, que para `run_case_n`, el MISMO caso repetido N veces):

      · COBERTURA/PRECISIÓN del respaldo — de todas las citas, cuántas quedaron
        confirmadas (`cobertura_respaldo`); de las que terminaron marcadas [VERIFICAR],
        cuántas eran necesarias (`precision_respaldo`, el complemento de los falsos
        bloqueos — ver `false_block_signal`);
      · TASA DE DETECCIÓN por vía — guardián determinista (anotó por su cuenta) vs
        modelo obediente (se marcó solo), como fracción de las citas del conjunto;
      · FRECUENCIA DE FUGA DE JURISDICCIÓN — tasa sobre las N corridas de esta lista
        (reusa `scoring.jurisdiction_leak_signal`; nunca un booleano de una sola pasada);
      · TASA DE ABSTENCIÓN — ver `abstention_signal`;
      · ÉXITO DE TAREA — llegó a borrador CON cierre de diagnóstico;
      · LATENCIA p50/p95 — se MIDE y se REPORTA; NINGÚN campo de este panel es un gate
        por tiempo (decisión explícita del dueño del producto, 2026-07-21: "no tienen
        que ser 10 minutos... puede ser más si el resultado es brutal y de calidad");
      · COSTE POR TURNO — media, desviación, mínimo, máximo (con N pequeño la
        variabilidad ES el resultado, no ruido a esconder) — y tokens/llamadas.

    Puro: no toca DB, red ni reloj — agrega lo que cada `case_result` YA trae. Casos que
    NUNCA corrieron de verdad (cortados por el tope antes de `run_case`, sin
    `elapsed_ms`/`usage.cost_usd` reales) se cuentan en `n` pero se EXCLUYEN de latencia
    y coste — meter un 0 falso ahí falsearía la media hacia abajo.
    """
    n = len(case_results)
    if n == 0:
        return {"n": 0}

    sum_citas = sum_respaldadas = sum_marcadas = sum_anotadas = 0
    sum_falsos = sum_marcas_evaluables = 0
    n_con_fuga = n_con_abstencion = n_con_exito = n_errores = 0
    latencias: list[float] = []
    costes: list[float] = []
    tokens_total = 0
    llamadas_total = 0

    for c in case_results:
        if c.get("error"):
            n_errores += 1
        score = c.get("score") or {}
        citas = int(score.get("citas", 0) or 0)
        sum_citas += citas
        sum_respaldadas += int(score.get("citas_respaldadas", 0) or 0)
        sum_marcadas += int(score.get("citas_marcadas", 0) or 0)
        sum_anotadas += int(score.get("citas_sin_respaldo", 0) or 0)

        fb = c.get("false_block") or {}
        sum_falsos += int(fb.get("falsos_bloqueos", 0) or 0)
        sum_marcas_evaluables += int(fb.get("citas_marcadas", 0) or 0)

        # C-MAY1: se AGREGA la señal persistida por `run_case` sobre el TEXTO COMPLETO. Solo
        # como retrocompatibilidad (fixtures o corridas viejas sin la señal) se recalcula
        # sobre el preview — que subestima, porque solo ve _DRAFT_PREVIEW_CHARS.
        jl = c.get("jurisdiction_leak")
        if not isinstance(jl, dict):
            jl = jurisdiction_leak_signal(
                f"{c.get('diagnosis_preview') or ''}\n{c.get('draft_preview') or ''}")
        if jl.get("leak"):
            n_con_fuga += 1

        abst = c.get("abstention")
        if not isinstance(abst, dict):
            abst = abstention_signal(c.get("diagnosis_preview") or "",
                                     c.get("draft_preview") or "")
        if abst.get("abstiene"):
            n_con_abstencion += 1

        if bool(c.get("reached_draft")) and bool(score.get("has_diagnosis_closing")):
            n_con_exito += 1

        if "elapsed_ms" in c:
            latencias.append(float(c.get("elapsed_ms") or 0.0))
        usage = c.get("usage")
        if isinstance(usage, dict) and "cost_usd" in usage:
            costes.append(float(usage.get("cost_usd") or 0.0))
            tokens_total += int(usage.get("total_tokens", 0) or 0)
            llamadas_total += int(usage.get("calls", 0) or 0)

    total_marcas = sum_marcadas + sum_anotadas  # toda cita que terminó con [VERIFICAR]

    # PRECISIÓN DE RESPALDO con clamp [0,1] (C-MEN). El numerador (falsos bloqueos) sale del
    # bucket 'marcada' del informe de verificación; el denominador (total_marcas) de
    # score.citas_marcadas+citas_sin_respaldo — DOS fuentes de conteo distintas que pueden
    # desincronizarse. Sin clamp, `falsos > total_marcas` imprimía un negativo imposible en
    # silencio. Se acota a [0,1] y la desincronía se DECLARA en vez de esconderse: un número
    # imposible tiene que ser VISIBLE, no un negativo mudo.
    _prec_raw = (1.0 - sum_falsos / total_marcas) if total_marcas else 1.0
    _prec_desync = sum_falsos > total_marcas
    precision_respaldo = round(max(0.0, min(1.0, _prec_raw)), 4)

    return {
        "n": n,
        "n_con_error": n_errores,
        "respaldo": {
            "citas_totales": sum_citas,
            "citas_respaldadas": sum_respaldadas,
            "cobertura_respaldo": round(sum_respaldadas / sum_citas, 4) if sum_citas else 1.0,
            "falsos_bloqueos": sum_falsos,
            "citas_marcadas_evaluables": sum_marcas_evaluables,
            "precision_respaldo": precision_respaldo,
            "precision_respaldo_desincronizada": _prec_desync,
        },
        "deteccion": {
            "tasa_guardian_determinista": (round(sum_anotadas / sum_citas, 4)
                                           if sum_citas else 0.0),
            "tasa_modelo_obediente": (round(sum_marcadas / sum_citas, 4)
                                      if sum_citas else 0.0),
        },
        "fuga_jurisdiccion": {"n_con_fuga": n_con_fuga, "tasa": round(n_con_fuga / n, 4)},
        "abstencion": {"n_con_abstencion": n_con_abstencion,
                      "tasa": round(n_con_abstencion / n, 4)},
        "exito_tarea": {"n_con_exito": n_con_exito, "tasa": round(n_con_exito / n, 4)},
        "latencia_ms": {
            "n_medidos": len(latencias),
            "p50": _percentile(latencias, 50),
            "p95": _percentile(latencias, 95),
            "media": round(statistics.fmean(latencias), 1) if latencias else 0.0,
            "min": round(min(latencias), 1) if latencias else 0.0,
            "max": round(max(latencias), 1) if latencias else 0.0,
        },
        "coste_usd": {
            "n_medidos": len(costes),
            "total": round(sum(costes), 6),
            "media": round(statistics.fmean(costes), 6) if costes else 0.0,
            "desviacion": round(statistics.pstdev(costes), 6) if len(costes) > 1 else 0.0,
            "min": round(min(costes), 6) if costes else 0.0,
            "max": round(max(costes), 6) if costes else 0.0,
        },
        "tokens_totales": tokens_total,
        "llamadas_totales": llamadas_total,
    }


@contextmanager
def _unguarded_case():
    """Sustituto de `guard.case(...)` SOLO para el opt-in explícito `allow_unguarded=True`.

    No es un camino por defecto ni silencioso: `run_case` levanta `EvalGuardMissing` si nadie
    lo pidió a mano, y quien lo pide se lleva un aviso ruidoso en el log. Antes esto se
    llamaba `_null_case` y era el DEFAULT: invocar `run_case` directo evadía el tope entero.
    """
    yield None


class EvalConsentError(Exception):
    """Se intentó correr un caso NO sintético sin la autorización del despacho
    (`allow_eval_real_data`). `str(e)` es apto para mostrarse en llano."""


# ── política de eval por despacho (candado de datos reales) ───────────────────
async def read_eval_policy(tenant_id: str) -> dict:
    """Política de eval del despacho, leída de `tenant_settings.config['eval']` (RLS).
    `allow_real_data` (default False, fail-closed): si es False, el harness rechaza correr
    casos NO sintéticos. Un fallo de lectura → False (nunca abre el candado por un hipo)."""
    try:
        async with pool.tenant_connection(tenant_id) as conn:
            row = await (await conn.execute(
                "SELECT config->'eval'->>'allow_eval_real_data' "
                "FROM tenant_settings WHERE tenant_id = %s::uuid",
                (tenant_id,),
            )).fetchone()
        allow = bool(row and str(row[0] or "").strip().lower() in ("true", "1", "yes", "on"))
    except Exception:  # noqa: BLE001 — un fallo de DB NO habilita datos reales: fail-closed
        logger.exception("read_eval_policy: no se pudo leer la política de eval (tenant=%s)",
                         tenant_id)
        allow = False
    return {"allow_real_data": allow}


# ── siembra del asunto de prueba (bajo RLS, como la app) ──────────────────────
async def _seed_case_matter(tenant_id: str, case: GoldenCase) -> str:
    """Crea un asunto de prueba con los documentos del caso (documents+chunks) bajo RLS.
    Devuelve el matter_id.

    Los chunks se insertan CON su `embedding` (igual que la ingesta de producción,
    `routes/ux.py`): `matter_has_chunks` y `retrieve_rrf` FILTRAN por `embedding IS NOT NULL`,
    así que sin el vector intake recuperaría 0 documentos y Mia redactaría A CIEGAS — el eval
    dejaría de ejercitar la recuperación del expediente (hallazgo capa 2, M1). Con el embedding,
    intake recupera la evidencia del caso como en un turno real."""
    async with pool.tenant_connection(tenant_id) as conn:
        mid = (await (await conn.execute(
            "INSERT INTO matters(tenant_id, title) VALUES (%s::uuid, %s) RETURNING id",
            (tenant_id, f"[eval] {case.title}"),
        )).fetchone())[0]
        for doc in case.documents:
            did = (await (await conn.execute(
                "INSERT INTO documents(tenant_id, matter_id, filename) "
                "VALUES (%s::uuid, %s::uuid, %s) RETURNING id",
                (tenant_id, str(mid), doc.filename),
            )).fetchone())[0]
            # Embeddings de los chunks del documento (en un hilo: embed_texts es síncrono,
            # como en intake). Vacío/fallo → se inserta sin vector (el turno sigue).
            texts = list(doc.chunks)
            vectors = await asyncio.to_thread(embeddings.embed_texts, texts) if texts else []
            for i, content in enumerate(texts):
                vec = vectors[i] if i < len(vectors) else None
                await conn.execute(
                    "INSERT INTO chunks(tenant_id, document_id, ord, content, embedding) "
                    "VALUES (%s::uuid, %s::uuid, %s, %s, %s)",
                    (tenant_id, str(did), i, content, vec),
                )
    return str(mid)


# ── correr UN caso por el grafo completo ──────────────────────────────────────
async def run_case(tenant_id: str, case: GoldenCase, *, tenant_allow_real: Optional[bool] = None,
                   substantive_judge: Optional[callable] = None,
                   allow_unguarded: bool = False) -> dict:
    """Corre un caso de oro por el grafo y devuelve su resultado puntuado.

    FAIL-CLOSED POR DEFECTO (D1): esta función corre el grafo COMPLETO contra el modelo vivo y
    genera embeddings pagados. Si NO hay un `EvalSpendGuard` activo en el contexto, NO corre:
    levanta `EvalGuardMissing`. Antes caía a un contexto nulo y corría igual, así que llamarla
    directo —cosa que puede hacer cualquiera, es pública— evadía el tope entero. Para el caso
    legítimo de correr sin techo (política enteramente gratis: cadenas `cli-*` / `mia-local`,
    coste marginal cero) existe `allow_unguarded=True`: opt-in EXPLÍCITO y ruidoso, nunca el
    default.

    Candado: un caso NO sintético exige `allow_eval_real_data` del despacho. Se puede pasar
    `tenant_allow_real` ya resuelto (para no releer la política por caso); si es None, se lee.

    Si el caso trae `rubric` (caso de oro por-despacho), se añade `result["substantive"]` con la
    calificación sustantiva (cobertura de citas/conclusiones clave). `substantive_judge` es un
    CALLBACK opcional (efecto de red — el juez LLM que ve SOLO texto anonimizado); default None
    mantiene la corrida determinista y sin red.

    EL JUEZ ARBITRARIO NO SE ACEPTA (S5). El tope gobierna lo que pasa por las capas envueltas
    (`agent.llm._invoke` y `embeddings.embed_texts`). Un `substantive_judge` es un callable
    AJENO: puede hacer N peticiones HTTP pagadas por su cuenta y luego UNA llamada gobernada
    solo para "aprobar" cualquier chequeo de evidencia — el contador sube y el gasto real pasa
    sin control. Eso es lo que era la marca `governed_judge`: una bandera burlable, no una
    garantía. Como desde aquí no se puede demostrar por dónde sale un callable ajeno, se
    rechaza en vez de fingir que se gobierna: `substantive_judge` distinto de None levanta
    `spend_guard.UngovernedJudge`. La calificación sustantiva DETERMINISTA (sin juez) sigue
    intacta, y es la que usan las corridas reales — ningún llamador de producción pasa juez.
    """
    if not case.synthetic:
        allow = tenant_allow_real
        if allow is None:
            allow = (await read_eval_policy(tenant_id))["allow_real_data"]
        if not allow:
            raise EvalConsentError(
                "Este caso usa datos reales del despacho. Debes autorizar el uso de datos "
                "reales en las pruebas (Configuración) antes de correrlo.")

    guard = spend_guard.active_guard()
    if guard is None and not allow_unguarded:
        raise spend_guard.EvalGuardMissing(
            "No hay tope de gasto activo. Correr un caso del banco llama al modelo y genera "
            "embeddings PAGADOS, así que no se corre sin techo: usa "
            "`with spend_guard.install(), EvalSpendGuard(...).activate():` (o run_suite / "
            "run_case_n, que ya lo hacen). Si de verdad quieres correr sin tope —solo tiene "
            "sentido con una política enteramente gratis (cli-* / mia-local)— pásalo a mano "
            "con allow_unguarded=True.")
    if guard is None:
        # R4 — el escape NO es un bypass general. Se pidió para el caso en que el tope no
        # aporta nada (política de coste marginal cero); si la cadena de aliases de la política
        # ACTIVA tiene aunque sea uno que factura, se rechaza aunque venga allow_unguarded=True.
        # S3 — "enteramente gratis" incluye los EMBEDDINGS, no solo el modelo. Antes bastaba
        # con que la cadena de aliases fuera gratis (p. ej. 'soberano', LLM local) y el escape
        # se aceptaba… mientras sembrar el caso generaba embeddings de Voyage PAGADOS sin
        # techo. El propio log lo admitía en letra pequeña. La promesa ahora es verdad o no
        # hay escape.
        audit = spend_guard.free_policy_audit()
        if not audit["entirely_free"]:
            raise spend_guard.EvalGuardMissing(
                "allow_unguarded=True solo se acepta si NADA puede facturar: ni el modelo ni "
                f"los embeddings. Con la política activa ('{audit['policy']}') todavía puede "
                f"facturar: {', '.join(audit['lo_que_factura'])}. Corre el caso bajo un "
                "EvalSpendGuard (run_suite / run_case_n ya lo hacen).")
        logger.warning(
            "run_case: caso '%s' corre SIN tope de gasto por opt-in explícito "
            "(allow_unguarded=True). Se aceptó porque NADA puede facturar en esta "
            "instalación: política '%s' (aliases %s) y sin clave de embeddings de pago.",
            case.id, audit["policy"], audit["aliases"])

    # S5 — el juez sustantivo arbitrario NO se acepta en modo hermético. Se comprueba ANTES de
    # sembrar y de correr el grafo, así que no llega a gastar nada.
    if substantive_judge is not None:
        raise spend_guard.UngovernedJudge(
            "El juez sustantivo es un callable ajeno y el banco no puede demostrar por dónde "
            "sale a la red: podría hacer llamadas pagadas por HTTP directo y luego una sola "
            "llamada gobernada para aparentar que está bajo el tope. La marca `governed_judge` "
            "era una bandera burlable, no una garantía, así que se retiró: en modo hermético "
            "el juez arbitrario se RECHAZA. La calificación sustantiva determinista (sin juez) "
            "sigue funcionando igual.")

    case_usage: Optional[spend_guard.CaseUsage] = None
    started = time.perf_counter()
    # La siembra del asunto va DENTRO del contexto del caso: `_seed_case_matter` genera
    # EMBEDDINGS (Voyage, pagado). Antes se sembraba fuera y ese gasto no lo veía ni el tope
    # ni el contador del caso.
    with (guard.case(case.id) if guard is not None else _unguarded_case()) as cu:
        case_usage = cu
        matter_id = await _seed_case_matter(tenant_id, case)
        cfg = {"configurable": {"thread_id": thread_id_for(tenant_id, matter_id)}}
        inp = initial_state(tenant_id, matter_id, case.message,
                            profile_snapshot=case.profile or None)

        # Scope de uso del CASO: `metrics.usage.record` es un no-op sin scope, así que sin
        # esto las llamadas reales del banco no dejaban rastro (ni tokens ni coste).
        # `source="eval"` separa el gasto del banco del de los turnos del abogado en
        # `turn_usage`.
        scope_token = usage_metrics.set_usage_scope(tenant_id, matter_id, source="eval")
        try:
            async with open_checkpointer() as cp:
                graph = build_matter_graph(cp)
                # astream hasta el interrupt de HITL: el borrador y la verificación ya están.
                async for _ in graph.astream(inp, cfg, stream_mode="updates"):
                    pass
                st = await graph.aget_state(cfg)
        finally:
            usage_metrics.reset_usage_scope(scope_token)
    elapsed_ms = round((time.perf_counter() - started) * 1000, 1)

    values = st.values if st is not None else {}
    md = dict(values.get("metadata") or {})
    draft = values.get("draft") or ""
    diagnosis = str(md.get("diagnosis") or "")
    # Se usa el INFORME del verificador del grafo (calculado sobre el borrador ANTES de
    # anotarlo): para cuando llegamos al HITL el borrador ya trae las [VERIFICAR] insertadas,
    # así que re-escanearlo perdería la señal de disciplina. `sources` se pasa como respaldo
    # para el caso sin informe.
    sources = md.get("research_sources")
    score = score_turn(draft, diagnosis, md, sources=sources,
                       verification_report=md.get("verification"))
    documents_retrieved = int(md.get("retrieved", 0) or 0)

    result = {
        "case_id": case.id,
        "title": case.title,
        "matter_id": matter_id,
        "elapsed_ms": elapsed_ms,
        "score": score,
        "verification": md.get("verification") or {},
        # F2: el informe del DIAGNÓSTICO (solo existe bajo jurisdicción desconocida, donde
        # el diagnóstico también pasa por el guardián). Permite asertar que una fuga de
        # jurisdicción fue OMITIDA y no simplemente que "no hubo" (0 fugas sin este
        # informe sería indistinguible de un modelo que dejó de citar — check ciego).
        "verification_diagnosis": md.get("verification_diagnosis") or {},
        # nº de documentos que intake recuperó del expediente del caso (RAG). Con documentos
        # sembrados debe ser > 0: si es 0, el turno corrió a ciegas (regresión de recuperación).
        "documents_retrieved": documents_retrieved,
        "draft_preview": draft[:_DRAFT_PREVIEW_CHARS],
        # el diagnóstico se perdía por completo (solo viajaba dentro del bloque de cierre que
        # `score_turn` parsea): un caso de riesgo (Frente E) puede necesitar leerlo entero, p.
        # ej. para `jurisdiction_leak_signal`, que también puede fugarse en el diagnóstico y no
        # solo en el borrador.
        "diagnosis_preview": diagnosis[:_DRAFT_PREVIEW_CHARS],
        "reached_draft": score["reached_draft"],
        # PROCEDENCIA (Frente E): ¿el turno atribuye al despacho/expediente algo que este
        # turno no selló? Se calcula SIEMPRE (barato y puro) — informativo, no toca `score.ok`.
        "provenance": provenance_signal(draft, diagnosis, documents_retrieved),
        # COSTE del caso (Frente A): llamadas, tokens, USD y segundos dentro del modelo. Con
        # políticas gratis (cli-*, motor local) el coste es 0 pero los tokens SÍ se cuentan.
        "usage": case_usage.as_dict() if case_usage is not None else None,
    }
    # TEXTO COMPLETO opt-in (F1 · paquete de decisión): el preview de 1200 sirve para
    # depurar, no para que un abogado JUZGUE la calidad jurídica de un borrador de ~15k.
    # Se activa por env y no por defecto: engordaría todos los crudos del banco.
    if os.getenv("MIA_EVAL_PERSIST_FULL", "").strip() == "1":
        result["draft_full"] = draft
        result["diagnosis_full"] = diagnosis
    # FALSOS BLOQUEOS (F1 · Frente C): ¿alguna marca [VERIFICAR] espontánea del modelo
    # cayó sobre una cita que YA estaba respaldada por el corpus? Ver `false_block_signal`.
    result["false_block"] = false_block_signal(md.get("verification"), sources)
    # ABSTENCIÓN honesta (F1 · Frente C): ¿el turno reconoció que no puede respaldar algo?
    result["abstention"] = abstention_signal(diagnosis, draft)
    # FUGA DE JURISDICCIÓN (F1 · Frente C · C-MAY1): se calcula sobre el TEXTO COMPLETO del
    # turno (diagnóstico + borrador), NO sobre el preview truncado a _DRAFT_PREVIEW_CHARS.
    # El preview de 1200 es para MOSTRAR, no para MEDIR: un borrador real de ~15k caracteres
    # evaluado sobre su 8% inicial diría "no hay fuga" por construcción. Se persiste aquí,
    # donde el texto entero todavía existe, con el MISMO patrón que la abstención; el panel
    # (`build_quality_panel`) y `jurisdiction_leak_rate` la AGREGAN en vez de recalcularla
    # tarde sobre el preview.
    result["jurisdiction_leak"] = jurisdiction_leak_signal(f"{diagnosis}\n{draft}")
    # Traza de la LECTURA AGÉNTICA (opt-in, `config.MIA_AGENTIC_READING`): cuántas
    # ampliaciones pidió el modelo, con qué motivo y por qué paró (`agents.graph` la escribe
    # en `metadata["agentic_reading"]` — ver `_turn.intake_node`). Antes se calculaba y se
    # perdía: el harness nunca la copiaba al resultado, así que nada por fuera del proceso
    # podía leer el motivo de parada para comparar coste. None cuando el bucle no corrió
    # (bandera apagada, motor sin herramientas, o el expediente no tenía nada que leer).
    if "agentic_reading" in md:
        result["agentic_reading"] = md["agentic_reading"]

    # Hook sustantivo: si el caso trae rúbrica confirmada, calificar la respuesta nueva contra
    # ella. El juez corre FUERA de la ruta pura (callback); sin rúbrica, no se toca nada.
    if getattr(case, "rubric", None):
        # Sin juez (S5): calificación DETERMINISTA de cobertura de citas y conclusiones clave.
        # No sale a la red, así que no hay nada que gobernar.
        result["substantive"] = substantive_score(draft, diagnosis, case.rubric)

    return result


# ── correr el MISMO caso N veces (riesgos INTERMITENTES) ──────────────────────
async def run_case_n(tenant_id: str, case: GoldenCase, n: int, *,
                     tenant_allow_real: Optional[bool] = None,
                     substantive_judge: Optional[callable] = None,
                     guard: Optional[spend_guard.EvalSpendGuard] = None) -> list[dict]:
    """Corre el MISMO caso de oro `n` veces SEGUIDAS y devuelve la lista de resultados.

    Existe para los riesgos que solo se ven a veces (p. ej. la fuga de jurisdicción
    capturada en vivo — Frente E): una sola corrida limpia no prueba que el defecto no
    vuelva a pasar, así que hay que poder repetir el MISMO caso y medir una TASA en vez de
    un booleano de una pasada. Cada corrida siembra su PROPIO asunto (matter_id nuevo,
    mismo `case`) — son turnos independientes, no memoria compartida entre corridas.

    `n <= 0` se trata como 1 (nunca corre "cero veces" en silencio — eso sería devolver
    una lista vacía y que el llamador crea que sí se corrió).

    Corre bajo `EvalSpendGuard` igual que `run_suite` (repetir un caso N veces es
    justamente la forma más fácil de quemar dinero sin darse cuenta). Si el tope corta,
    devuelve las corridas YA hechas: el llamador debe mirar `len(resultados)` contra `n`
    antes de leer una tasa — una tasa sobre menos corridas de las pedidas no es la tasa
    que se pidió.
    """
    n = max(1, int(n))
    allow = tenant_allow_real
    if allow is None and not case.synthetic:
        allow = (await read_eval_policy(tenant_id))["allow_real_data"]

    from ..agent import llm as llm_mod

    guard = guard or spend_guard.active_guard() or spend_guard.EvalSpendGuard()
    results: list[dict] = []
    policy_token = llm_mod.set_model_policy(await llm_mod.model_policy_for(tenant_id))
    suite_scope = usage_metrics.set_usage_scope(tenant_id, source="eval")
    try:
        with spend_guard.install(), guard.activate():
            for _ in range(n):
                try:
                    results.append(await run_case(tenant_id, case, tenant_allow_real=allow,
                                                  substantive_judge=substantive_judge))
                except spend_guard.SpendGuardHalt as exc:
                    logger.warning("run_case_n: corte por tope tras %d/%d corridas: %s",
                                   len(results), n, exc)
                    break
    finally:
        usage_metrics.reset_usage_scope(suite_scope)
        llm_mod.reset_model_policy(policy_token)
        try:
            await usage_metrics.flush_pending()
        except Exception:  # noqa: BLE001
            logger.exception("run_case_n: no se pudo persistir el uso del banco")
    return results


def evidence_audit(results: list[dict]) -> dict:
    """¿Se puede VOLVER A LEER el texto que produjo estos números? (F2 · 2026-07-24)

    `MIA_EVAL_PERSIST_FULL=1` guarda `draft_full`/`diagnosis_full`; sin él solo queda el
    preview de `_DRAFT_PREVIEW_CHARS`. Pura: cuenta, no juzga.

    LO QUE ESTO **NO** SIGNIFICA (importa, para no sembrar una alarma falsa): las señales
    que deciden — fuga, abstención, falsos bloqueos, informe por oración — se calculan en
    `run_case` sobre el texto COMPLETO y viajan ya persistidas; el panel las AGREGA en vez
    de recalcularlas sobre el preview (C-MAY1). Un agregado sin texto completo **no tiene
    números falsos**. Lo que pierde es la AUDITABILIDAD: nadie puede releer el borrador para
    juzgarlo a mano.

    Por qué existe: el 2026-07-24 el agregado `f2sond_entail_n10` incluyó una corrida
    (`_smoke`) corrida sin el flag, con su borrador truncado a 1200 caracteres, y NADA lo
    advirtió — en una sonda de `RISK_CASES` declarada de REVISIÓN HUMANA, que es justo
    donde el texto releíble es el entregable. El agregador avisa; con `--exige-evidencia`
    además reprueba.
    """
    n = len(results)
    sin_texto = [i for i, c in enumerate(results)
                 if not (c.get("draft_full") or "").strip()]
    return {
        "n": n,
        "con_texto": n - len(sin_texto),
        "sin_texto": len(sin_texto),
        "indices_sin_texto": sin_texto,
        "completa": n > 0 and not sin_texto,
    }


def jurisdiction_leak_rate(results: list[dict]) -> dict:
    """Tasa de fuga de jurisdicción sobre una lista de corridas del MISMO caso (ver
    `run_case_n`). Aplica `scoring.jurisdiction_leak_signal` al diagnóstico + borrador de
    CADA corrida — reusa el escáner del guardián de citas, no duplica vocabulario de país
    (ver el docstring de `jurisdiction_leak_signal`). Pura: solo lee los resultados que ya
    trae `run_case_n`, no vuelve a tocar la DB.

    Honesto con la intermitencia (regla dura de este banco): devuelve una TASA, nunca un
    solo booleano — una corrida limpia entre cinco no certifica que el riesgo no exista.
    """
    n = len(results)
    detalle: list[dict] = []
    for r in results:
        # C-MAY1: se prefiere la señal persistida por `run_case` sobre el TEXTO COMPLETO;
        # el preview (subestima, solo _DRAFT_PREVIEW_CHARS) es únicamente el respaldo para
        # resultados viejos que no la traen.
        sig = r.get("jurisdiction_leak")
        if not isinstance(sig, dict):
            texto = f"{r.get('diagnosis_preview') or ''}\n{r.get('draft_preview') or ''}"
            sig = jurisdiction_leak_signal(texto)
        detalle.append({"matter_id": r.get("matter_id"), **sig})
    con_fuga = sum(1 for d in detalle if d["leak"])
    return {
        "n": n,
        "n_con_fuga": con_fuga,
        "tasa": round(con_fuga / n, 4) if n else 0.0,
        "detalle": detalle,
    }


# ── correr una SUITE + reporte ────────────────────────────────────────────────
async def run_suite(tenant_id: str, cases: Optional[list[GoldenCase]] = None,
                    *, run_id: str, substantive_judge: Optional[callable] = None,
                    guard: Optional[spend_guard.EvalSpendGuard] = None) -> dict:
    """Corre una lista de casos (por defecto los canónicos sintéticos) y arma el reporte.
    Resuelve la política de datos reales UNA vez. `run_id` lo fija el llamador (con fecha).
    `substantive_judge` (opcional) se pasa a los casos con rúbrica (juez advisory anonimizado).

    TOPE DE GASTO (Frente A): la corrida SIEMPRE ocurre bajo un `EvalSpendGuard`. Si el
    llamador no pasa `guard` y no hay uno activo en el contexto, se crea uno con los topes
    por defecto — no existe la corrida "sin techo". Al cortar por tope, el bucle se detiene
    y el reporte PARCIAL se devuelve igual (con `summary.corte` y `report["spend"]`): cortar
    nunca puede significar perder lo ya medido.

    BOLSILLO SEPARADO (D6): el guardián que se crea aquí por defecto es `source="inapp"`,
    porque el llamador que no pasa `guard` es el harness dentro del proceso de la API
    (`gold-cases:evaluate`). `execution/run_eval.py` pasa el suyo con `source="cli"`. Son
    sesiones de gasto DISTINTAS: una tanda de pruebas desde la terminal no puede agotar el
    saldo del examen que el abogado lanza desde la aplicación, ni al revés.
    """
    cases = cases if cases is not None else load_golden_cases()
    allow_real = (await read_eval_policy(tenant_id))["allow_real_data"]

    from ..agent import llm as llm_mod

    guard = guard or spend_guard.active_guard() or spend_guard.EvalSpendGuard()
    results: list[dict] = []
    corte: Optional[str] = None

    policy_token = llm_mod.set_model_policy(await llm_mod.model_policy_for(tenant_id))
    or_token = llm_mod.set_openrouter_allowed(await llm_mod.openrouter_allowed_for(tenant_id))
    # Scope de la SUITE: cubre cualquier llamada fuera de un caso concreto. `run_case` fija
    # además el suyo, con el matter_id del caso.
    suite_scope = usage_metrics.set_usage_scope(tenant_id, source="eval")
    try:
        with spend_guard.install(), guard.activate():
            for case in cases:
                try:
                    results.append(await run_case(tenant_id, case, tenant_allow_real=allow_real,
                                                  substantive_judge=substantive_judge))
                except EvalConsentError:
                    raise  # el candado de consentimiento NO se traga: sube claro al llamador
                except spend_guard.SpendGuardHalt as exc:
                    # S1 — UNA sola puerta para TODAS las paradas del guardián: tope alcanzado,
                    # saldo no verificable, guardián ausente, juez no gobernado, ruta no
                    # clasificable. Antes había un `except` por subclase concreta y el `except
                    # Exception` de abajo se comía las demás: un juez no gobernado dejaba
                    # corte=None y la corrida BLOQUEADA salía con código 0 (el mismo defecto que
                    # ya se había cerrado para SpendLimitExceeded, reaparecido en otra puerta).
                    # `SpendGuardHalt` hereda de BaseException, así que ningún `except
                    # Exception` del grafo puede tragárselo antes de llegar aquí.
                    corte = str(exc)
                    logger.warning("run_suite: PARADA del tope de gasto (%s) en el caso %s: %s",
                                   type(exc).__name__, case.id, exc)
                    results.append({
                        "case_id": case.id, "title": case.title,
                        "error": f"CORTE POR EL TOPE DE GASTO ({type(exc).__name__}): {exc}",
                        "score": score_turn("", "", {}), "reached_draft": False,
                        "detenido_por_tope": True,
                    })
                    break  # STICKY: el guardián ya no autoriza; seguir solo quemaría tiempo
                except Exception as exc:  # noqa: BLE001 — un caso que falla no tumba la suite
                    logger.exception("run_suite: el caso %s falló", case.id)
                    results.append({
                        "case_id": case.id, "title": case.title, "error": str(exc),
                        "score": score_turn("", "", {}), "reached_draft": False,
                    })
    finally:
        usage_metrics.reset_usage_scope(suite_scope)
        llm_mod.reset_openrouter_allowed(or_token)
        llm_mod.reset_model_policy(policy_token)
        # Persistir el uso medido ANTES de devolver: si el proceso muere después, el gasto
        # del banco ya quedó en `turn_usage`. Nunca rompe la corrida (es métrica).
        try:
            await usage_metrics.flush_pending()
        except Exception:  # noqa: BLE001
            logger.exception("run_suite: no se pudo persistir el uso del banco")

    # CINTURÓN sobre el tirante (D4a): si por cualquier vía el corte no llegó como excepción
    # hasta este bucle pero el guardián SÍ quedó parado, la corrida está CORTADA y tiene que
    # decirlo. Una corrida cortada jamás puede salir con `summary.corte = None` y código 0.
    if corte is None and guard.stop_reason:
        corte = guard.stop_reason
        logger.error("run_suite: el guardián quedó parado sin que el corte llegara al bucle; "
                     "la corrida se reporta CORTADA igual: %s", corte)

    return build_report(run_id, results, spend=guard.snapshot(), corte=corte)


# ── correr la suite COMPLETA: canónicos sintéticos + Banco de oro confirmado ──
async def run_full_suite(tenant_id: str, *, run_id: str,
                         substantive_judge: Optional[callable] = None,
                         guard: Optional[spend_guard.EvalSpendGuard] = None) -> dict:
    """El examen completo del despacho: los 3 casos sintéticos canónicos + los casos de oro que
    el abogado ya CONFIRMÓ (`gold_cases.status='confirmed'`, vía `load_tenant_gold_cases`).

    Los casos confirmados llegan hidratados con `synthetic=True` (`cases._rows_to_cases`): un
    caso de oro guardado ya está anonimizado, así que corre sin pedir el candado de datos
    reales — ese candado protege la CAPTURA (leer el expediente crudo), no la ejecución del
    grafo sobre texto ya anónimo. Delega en `run_suite`, que queda intacto."""
    cases = load_golden_cases() + await load_tenant_gold_cases(tenant_id)
    return await run_suite(tenant_id, cases, run_id=run_id, substantive_judge=substantive_judge,
                           guard=guard)


def build_report(run_id: str, case_results: list[dict], *,
                 spend: Optional[dict] = None, corte: Optional[str] = None) -> dict:
    """Arma el reporte de una corrida a partir de los resultados por caso. Puro.

    `spend` es la foto del tope (`EvalSpendGuard.snapshot()`) y `corte` el motivo por el que
    la corrida se detuvo, si se detuvo. Ambos viajan al reporte PERSISTIDO: un corte que no
    queda escrito es un corte que nadie puede auditar después.

    `report["panel"]` (F1 · Frente C, ver `build_quality_panel`) y `report["version"]`
    (F1 — versionar el baseline: hash del prompt + modelos servidos, ver
    `prompt_version_hash`/`served_models_signal`) viajan AL LADO del resumen de siempre:
    ningún consumidor del resumen viejo se rompe, y quien quiera decidir algo tiene el
    panel completo en vez de tres números.
    """
    n = len(case_results)
    reached = sum(1 for c in case_results if c.get("reached_draft"))
    clean = sum(1 for c in case_results if (c.get("score") or {}).get("ok"))
    total_unsup = sum(int((c.get("score") or {}).get("citas_sin_respaldo", 0) or 0)
                      for c in case_results)
    errored = sum(1 for c in case_results if c.get("error"))
    total_cost = sum(float((c.get("usage") or {}).get("cost_usd", 0.0) or 0.0)
                     for c in case_results)
    total_tokens = sum(int((c.get("usage") or {}).get("total_tokens", 0) or 0)
                       for c in case_results)
    total_ms = sum(float(c.get("elapsed_ms", 0.0) or 0.0) for c in case_results)
    return {
        "run_id": run_id,
        "cases": case_results,
        "spend": spend or {},
        "panel": build_quality_panel(case_results),
        "version": {
            "prompt_hash": prompt_version_hash(),
            "modelos_servidos": served_models_signal(case_results),
        },
        "summary": {
            "n_casos": n,
            "n_llegaron_a_borrador": reached,
            "n_sin_problemas": clean,
            "n_con_error": errored,
            "total_citas_sin_respaldo": total_unsup,
            "costo_total_usd": round(total_cost, 6),
            "tokens_totales": total_tokens,
            "duracion_total_ms": round(total_ms, 1),
            "corte": corte,
        },
    }


# ── comparar CON/SIN lectura agéntica (MIA_AGENTIC_READING, Frente E) ─────────
def compare_agentic_reports(off_report: dict, on_report: dict) -> dict:
    """Compara coste en tokens y motivo de parada de la lectura agéntica entre dos corridas
    del MISMO banco — una con `config.MIA_AGENTIC_READING` apagada y otra encendida SOLO
    para esa corrida (ver `execution/run_eval.py --agentic-compare`, que es quien pone y
    quita la bandera; esta función es pura y no la toca).

    OJO — la bandera encendida NO garantiza que el bucle corra: `agents.retrieval.
    agentic_reading_available()` exige ADEMÁS que el motor de la política de modelo activa
    admita herramientas (`agents.retrieval.chain_supports_tools`, lectura de solo lectura
    para este frente). Si no las admite, el turno se comporta igual que apagado y
    `agentic_reading` viaja en None; este comparador lo REPORTA como tal
    (`corrio_agentic: False`) en vez de esconderlo o inventar un motivo de parada."""
    off_idx = {c["case_id"]: c for c in off_report.get("cases", []) if c.get("case_id")}
    on_idx = {c["case_id"]: c for c in on_report.get("cases", []) if c.get("case_id")}
    common = sorted(set(off_idx) & set(on_idx))

    per_case: list[dict] = []
    for cid in common:
        o, n = off_idx[cid], on_idx[cid]
        o_tokens = int((o.get("score") or {}).get("total_tokens", 0) or 0)
        n_tokens = int((n.get("score") or {}).get("total_tokens", 0) or 0)
        trace = n.get("agentic_reading")
        trace = trace if isinstance(trace, dict) else None
        per_case.append({
            "case_id": cid,
            "tokens_off": o_tokens,
            "tokens_on": n_tokens,
            "delta_tokens": n_tokens - o_tokens,
            "motivo_parada": trace.get("stop") if trace else None,
            "ampliaciones": trace.get("expansions") if trace else None,
            "corrio_agentic": trace is not None,
        })

    return {
        "cases": per_case,
        "n_total": len(per_case),
        "n_corrio_agentic": sum(1 for c in per_case if c["corrio_agentic"]),
        "only_off": sorted(cid for cid in off_idx if cid not in on_idx),
        "only_on": sorted(cid for cid in on_idx if cid not in off_idx),
    }


# ── persistencia (JSONL bajo mia-data — corridas SINTÉTICAS, sin RLS necesaria) ─
def _eval_dir(base_dir: Optional[str] = None) -> Path:
    base = Path(base_dir) if base_dir else Path(config.MIA_HOME) / "eval-runs"
    return base


def persist_report(report: dict, *, base_dir: Optional[str] = None) -> Path:
    """Escribe la corrida en `mia-data/eval-runs/{run_id}/` (cases.jsonl + summary.json).
    Datos SINTÉTICOS (no de cliente) → JSONL en disco basta, sin tabla RLS. Devuelve el dir.

    VERSIONAR EL BASELINE (F1): `panel` y `version` (hash del prompt + modelos servidos)
    viajan al disco junto al resumen — sin eso, comparar dos corridas de fechas distintas
    es engañarse: un cambio de modelo o de prompt invalida la comparación y solo se puede
    saber leyendo lo que quedó escrito aquí, no lo que se recuerde de memoria.
    """
    import json

    run_dir = _eval_dir(base_dir) / report["run_id"]
    run_dir.mkdir(parents=True, exist_ok=True)
    with (run_dir / "cases.jsonl").open("w", encoding="utf-8") as f:
        for c in report.get("cases", []):
            f.write(json.dumps(c, ensure_ascii=False) + "\n")
    (run_dir / "summary.json").write_text(
        json.dumps({"run_id": report["run_id"], "summary": report.get("summary", {}),
                    # el estado del TOPE viaja al disco: si la corrida se cortó, el motivo
                    # tiene que poder leerse después sin haber estado mirando la consola.
                    "spend": report.get("spend", {}),
                    "panel": report.get("panel", {}),
                    "version": report.get("version", {})},
                   ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return run_dir
