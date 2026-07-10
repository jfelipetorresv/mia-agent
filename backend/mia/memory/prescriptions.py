"""Mia · memory.prescriptions — auto-diagnóstico prescriptivo (CP-V2, Ola 4).

Evoluciona el "Dreams semanal" a un motor que revisa la actividad REAL del
despacho (trazas de turnos + uso real del LLM en `turn_usage` + guías de
trabajo) y produce hasta 4 RECOMENDACIONES accionables en lenguaje llano,
puntuadas por gravedad × impacto económico × certeza (patrón ClaudeOS
skills/dream, adaptado a lo jurídico).

Tres reglas de rigor (la razón de ser de CP-V2):

  1. ANTI-INVENCIÓN POR CONSTRUCCIÓN: el motor NO usa el LLM. Cada hallazgo
     se calcula contando datos reales (trazas, filas de turn_usage, guías) y
     el texto es una plantilla determinista. La evidencia siempre trae los
     números contados. Si un bucket tiene menos de MIN_BUCKET_EVENTS eventos,
     SE SALTA — mejor callar que confabular.

  2. IDs ESTABLES: el mismo problema en semanas distintas produce el MISMO
     `prescription_id` (slug determinista), para rastrear su edad y no
     duplicar tarjetas en el panel.

  3. MEMORIA DE RECOMENDACIONES (tabla `dream_prescriptions`, RLS): lo que el
     abogado ya ACEPTÓ o DESCARTÓ no se vuelve a mostrar, salvo que la señal
     reaparezca pasados RESURFACE_DAYS días (entonces vuelve como 'recurring').

HEURÍSTICAS DECLARADAS (estimados de negocio, no medición exacta — igual que
CP-V1): REWORK_MINUTES/WASTE_MINUTES son minutos estimados que pierde el
abogado por corrección repetida / borrador rechazado; el bucket de costo
reporta el GASTO REAL pagado (filas de turn_usage con cost_usd > 0) y señala
que en el Panel de control existen motores sin costo por uso. El impacto en
dólares usa la tarifa del despacho (config['value'], CP-V1).

LIMITACIÓN DECLARADA (capa 2, H7): el ID estable de retrabajo se deriva de los
primeros 80 caracteres de la solicitud; si las solicitudes reales traen datos
variables al inicio (número de expediente, fechas), el mismo patrón puede
fragmentarse en contextos distintos y no alcanzar el umbral. Anotado en
Riesgo #44 junto con las demás limitaciones.
"""
from __future__ import annotations

import hashlib
import logging
from datetime import datetime, timedelta, timezone
from typing import Any

from psycopg.types.json import Json

from ..db import pool
from .trace_capture import TraceCapture

logger = logging.getLogger("mia.memory.prescriptions")

# ── Parámetros del motor (declarados, no mágicos) ──────────────────────────────
SIGNAL_DAYS = 30          # ventana de señal: último mes móvil
MIN_BUCKET_EVENTS = 5     # guarda anti-invención: menos de 5 eventos = bucket saltado
TOP_N = 4                 # máximo de recomendaciones surfaceadas
MAX_PER_CATEGORY = 2      # diversidad: no llenar el top con una sola categoría
RESURFACE_DAYS = 30       # lo aceptado/descartado solo vuelve si la señal reaparece tras esto

REWORK_MINUTES = 15       # minutos estimados perdidos por cada corrección repetida
WASTE_MINUTES = 15        # minutos estimados perdidos por cada borrador rechazado
REWORK_CONTEXT_MIN = 3    # correcciones del mismo contexto para considerarlo patrón
REJECTION_RATE_MIN = 0.25  # tasa de rechazo desde la cual hay hallazgo
LOW_APPROVAL_MAX = 0.60   # una guía por debajo de esto (con uso) merece revisión
MIN_PAID_COST_USD = 1.0   # costo pagado mínimo del mes para hablar de costo

_TURN_PREFIX = "mia.trace.v"   # v1/v2 = turnos; mia.trace.event.* = eventos técnicos

# Etiquetas en llano (§G) para las tareas internas del router en la evidencia de costo.
_TASK_LABEL = {
    "main": "análisis y redacción",
    "compression": "resumen de contexto",
    "verification": "verificación de citas",
    "curator": "depuración del conocimiento",
}


def _parse_ts(value: str | None) -> datetime:
    if not value:
        return datetime.min.replace(tzinfo=timezone.utc)
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)
    except ValueError:
        return datetime.min.replace(tzinfo=timezone.utc)


def _is_turn(trace: dict) -> bool:
    schema = str(trace.get("schema") or _TURN_PREFIX)  # trazas viejas sin schema = turno
    return schema.startswith(_TURN_PREFIX)


def _context_key(trace: dict) -> str:
    """Clave de agrupación de contexto (misma que los nudges de Dreams)."""
    return str(trace.get("input") or "")[:80].strip().lower()


def _slug_hash(text: str) -> str:
    return hashlib.sha1(text.encode("utf-8")).hexdigest()[:8]


def score_of(p: dict) -> float:
    """gravedad × max(impacto_dólares, 1) × certeza — el orden del panel."""
    return float(p["severity"]) * max(float(p.get("dollar_impact") or 0.0), 1.0) * float(p["certainty"])


def rank_and_diversify(candidates: list[dict], top_n: int = TOP_N,
                       max_per_category: int = MAX_PER_CATEGORY) -> list[dict]:
    """Ordena por puntaje y limita cuántas entran por categoría (diversidad)."""
    ranked = sorted(candidates, key=score_of, reverse=True)
    picked: list[dict] = []
    per_cat: dict[str, int] = {}
    for p in ranked:
        cat = p["category"]
        if per_cat.get(cat, 0) >= max_per_category:
            continue
        picked.append(p)
        per_cat[cat] = per_cat.get(cat, 0) + 1
        if len(picked) >= top_n:
            break
    return picked


def _prescription(*, pid: str, category: str, headline: str, prescription: str,
                  evidence: list[str], severity: int, certainty: float,
                  time_impact_mins: int | None = None,
                  dollar_impact: float | None = None) -> dict:
    p = {
        "id": pid,
        "category": category,
        "headline": headline,
        "prescription": prescription,
        "evidence": evidence,
        "severity": max(1, min(10, int(severity))),
        "certainty": round(max(0.0, min(1.0, float(certainty))), 2),
        "time_impact_mins": time_impact_mins,
        "dollar_impact": round(dollar_impact, 2) if dollar_impact is not None else None,
    }
    p["score"] = round(score_of(p), 2)
    return p


# ── Buckets (cada uno cuenta datos reales; <MIN_BUCKET_EVENTS → se salta) ───────
def bucket_rework(turns: list[dict], hourly_rate: float) -> list[dict]:
    """RETRABAJO: el abogado corrige una y otra vez respuestas del mismo tipo."""
    edited = [t for t in turns if t.get("hitl_outcome") == "edited"]
    if len(edited) < MIN_BUCKET_EVENTS:
        return []
    by_context: dict[str, list[dict]] = {}
    for t in edited:
        by_context.setdefault(_context_key(t), []).append(t)
    out: list[dict] = []
    for key, items in by_context.items():
        if len(items) < REWORK_CONTEXT_MIN or not key:
            continue
        n = len(items)
        mins = n * REWORK_MINUTES
        excerpt = key[:60]
        out.append(_prescription(
            pid=f"retrabajo-{_slug_hash(key)}",
            category="retrabajo",
            headline=f"Ha corregido {n} veces respuestas del mismo tipo este mes",
            prescription=(
                "Mia sigue produciendo una forma que usted termina reescribiendo. "
                "Suba (o ajuste) la guía de trabajo con la forma final que usted "
                "prefiere para ese tipo de solicitud: Mia la aplicará desde el "
                "primer borrador y esas correcciones desaparecen."
            ),
            evidence=[
                f"{n} respuestas corregidas con la misma solicitud en los últimos {SIGNAL_DAYS} días",
                f'La solicitud empieza por: "{excerpt}…"',
                f"Tiempo estimado perdido: ~{mins} minutos al mes ({REWORK_MINUTES} min por corrección)",
            ],
            severity=min(10, 4 + n),
            certainty=0.7,
            time_impact_mins=mins,
            dollar_impact=mins / 60.0 * hourly_rate,
        ))
    return out


def bucket_rejections(turns: list[dict], hourly_rate: float) -> list[dict]:
    """RECHAZOS: demasiados borradores que el abogado descarta por completo."""
    decided = [t for t in turns if t.get("hitl_outcome") in ("approved", "edited", "rejected")]
    if len(decided) < MIN_BUCKET_EVENTS:
        return []
    rejected = [t for t in decided if t.get("hitl_outcome") == "rejected"]
    rate = len(rejected) / len(decided)
    if rate < REJECTION_RATE_MIN:
        return []
    mins = len(rejected) * WASTE_MINUTES
    return [_prescription(
        pid="rechazos-frecuentes",
        category="rechazos",
        headline=f"Descartó {len(rejected)} de cada {len(decided)} borradores este mes",
        prescription=(
            "Una tasa de rechazo así indica que a Mia le falta contexto de cómo "
            "trabaja su despacho. Revise en el panel de conocimiento las mejoras "
            "que Mia ya dejó propuestas, y suba sus guías de trabajo: cada guía "
            "aprobada baja los rechazos de ese tipo de escrito."
        ),
        evidence=[
            f"{len(rejected)} borradores rechazados de {len(decided)} decididos "
            f"en los últimos {SIGNAL_DAYS} días ({rate:.0%})",
            f"Tiempo de revisión perdido: ~{mins} minutos ({WASTE_MINUTES} min por rechazo)",
            "Los rechazos quedan registrados en el concepto 'Patrones rechazados' de su memoria",
        ],
        severity=min(10, round(10 * rate) + 3),
        certainty=0.8,
        time_impact_mins=mins,
        dollar_impact=mins / 60.0 * hourly_rate,
    )]


def bucket_knowledge_gaps(turns: list[dict]) -> list[dict]:
    """CONOCIMIENTO: respuestas que salieron SIN ninguna fuente del despacho."""
    gaps = [t for t in turns if t.get("retrieved_doc_ids") == []]
    if len(gaps) < MIN_BUCKET_EVENTS:
        return []
    total = len(turns)
    share = len(gaps) / total if total else 0.0
    matters = {str(t.get("matter_id")) for t in gaps if t.get("matter_id")}
    return [_prescription(
        pid="conocimiento-sin-fuentes",
        category="conocimiento",
        headline=f"{len(gaps)} respuestas del mes salieron sin ninguna fuente de su despacho",
        prescription=(
            "Mia respondió sin encontrar documentos ni guías suyas que respaldaran "
            "la respuesta. Suba los documentos de esos asuntos y sus guías de "
            "trabajo: las respuestas pasarán a citar material verificable de su "
            "despacho en lugar de conocimiento general."
        ),
        evidence=[
            f"{len(gaps)} de {total} respuestas ({share:.0%}) sin documentos "
            f"recuperados en los últimos {SIGNAL_DAYS} días",
            f"Ocurrió en {len(matters)} asunto(s) distinto(s)",
            "Señal medida en las trazas: la búsqueda interna devolvió cero resultados",
        ],
        severity=min(10, 3 + round(share * 7)),
        certainty=0.9,
    )]


def bucket_cost(usage_rows: list[dict]) -> list[dict]:
    """COSTO: el despacho está PAGANDO por uso y existen motores sin costo por uso.

    `usage_rows`: agregados de turn_usage → {task, model, prompt_tokens,
    completion_tokens, cost_usd, calls}. Solo hay hallazgo si hubo GASTO REAL
    (cost_usd > 0, es decir motor 'nube' pagado por token — la suscripción y el
    motor local registran costo 0). La acción prescrita existe HOY en el
    producto: el selector "Motor de IA" del Panel de control (capa 2, H3/H4 —
    la versión v1 de este bucket recomendaba un swap por tarea que la
    arquitectura hace imposible: las tareas de apoyo YA corren en el modelo
    económico en toda política).
    """
    paid = [r for r in usage_rows if float(r["cost_usd"]) > 0]
    calls = sum(int(r["calls"]) for r in paid)
    total_cost = sum(float(r["cost_usd"]) for r in paid)
    if calls < MIN_BUCKET_EVENTS or total_cost < MIN_PAID_COST_USD:
        return []
    top = max(paid, key=lambda r: float(r["cost_usd"]))
    top_label = _TASK_LABEL.get(str(top["task"] or ""), "tareas internas")
    return [_prescription(
        pid="costo-pago-por-uso",
        category="costo",
        headline=f"La IA por uso le costó {total_cost:.0f} USD este mes",
        prescription=(
            "Mia está usando un motor que cobra por cada uso. En Configuración, "
            "sección 'Conexiones' → 'Motor de IA', hay opciones sin costo por uso: "
            "la suscripción del asistente de IA o 'Todo en mi equipo'. Si usted ya "
            "eligió una de esas y aun así ve este gasto, el trabajo está cayendo "
            "al modo pagado — vale la pena revisarlo."
        ),
        evidence=[
            f"{calls} llamadas pagadas costaron {total_cost:.2f} USD "
            f"en los últimos {SIGNAL_DAYS} días",
            f"El mayor componente fue {top_label} ({float(top['cost_usd']):.2f} USD)",
            "El motor se cambia en Configuración, sección 'Conexiones' → 'Motor de IA'",
        ],
        severity=min(10, 3 + round(total_cost / 50.0)),
        certainty=0.9,
        dollar_impact=total_cost,
    )]


def bucket_skills(grades: list[dict]) -> list[dict]:
    """GUÍAS: guías de trabajo con uso real pero baja aprobación."""
    out: list[dict] = []
    for g in grades:
        if int(g.get("activations") or 0) < MIN_BUCKET_EVENTS:
            continue
        approval = float(g.get("approval_rate") or 0.0)
        if approval >= LOW_APPROVAL_MAX:
            continue
        title = str(g.get("title") or "")[:80]
        out.append(_prescription(
            pid=f"guia-{_slug_hash(str(g['skill_id']))}",
            category="guias",
            headline=f'La guía "{title}" se usa pero pocas veces convence',
            prescription=(
                "Esa guía se activa con frecuencia y aun así sus resultados se "
                "aprueban poco. Ábrala en el panel de conocimiento y ajústela con "
                "lo que usted corrige a mano — o revise la mejora que Mia ya dejó "
                "propuesta para ella."
            ),
            evidence=[
                f"{int(g['activations'])} usos con {approval:.0%} de aprobación",
                f"El umbral de revisión del despacho es {LOW_APPROVAL_MAX:.0%}",
                f"Tasa de edición sobre esa guía: {float(g.get('edit_rate') or 0.0):.0%}",
            ],
            severity=7,
            certainty=0.85,
        ))
    return out


def bucket_value_config(turns_month: int, value_cfg: dict) -> list[dict]:
    """VALOR: el panel de valor sigue con los números de fábrica."""
    if turns_month < MIN_BUCKET_EVENTS or not value_cfg.get("is_default"):
        return []
    return [_prescription(
        pid="valor-sin-configurar",
        category="valor",
        headline="El panel de valor sigue calculando con la tarifa de fábrica",
        prescription=(
            "Usted ya usa a Mia a diario, pero la tarjeta 'Valor entregado' "
            "calcula con valores genéricos (100 USD/hora). Fije su tarifa real "
            "en esa misma tarjeta: el número que verá cada mes será el de SU "
            "despacho."
        ),
        evidence=[
            f"{turns_month} turnos de trabajo en los últimos {SIGNAL_DAYS} días",
            f"Tarifa configurada: ninguna (usa el valor de fábrica de "
            f"{value_cfg.get('hourly_rate_usd', 100):.0f} USD/hora)",
            "Se cambia en la tarjeta 'Valor entregado este mes' del panel",
        ],
        severity=3,
        certainty=1.0,
    )]


# ── El motor ───────────────────────────────────────────────────────────────────
class PrescriptionEngine:
    """Calcula, puntúa y persiste el diagnóstico prescriptivo de un despacho."""

    def __init__(self, *, trace_capture: TraceCapture | None = None) -> None:
        self.trace_capture = trace_capture or TraceCapture()

    def _window_turns(self, tenant_id: str) -> list[dict]:
        cutoff = datetime.now(timezone.utc) - timedelta(days=SIGNAL_DAYS)
        return [
            t for t in self.trace_capture.read(tenant_id)
            if isinstance(t, dict) and _is_turn(t) and _parse_ts(t.get("timestamp")) >= cutoff
        ]

    async def _usage_rows(self, tenant_id: str) -> list[dict]:
        """Agregados de turn_usage de la ventana. Sin la migración 021 → [] (degrada)."""
        try:
            async with pool.tenant_connection(tenant_id) as conn:
                rows = await (await conn.execute(
                    "SELECT coalesce(task, ''), model, coalesce(sum(prompt_tokens), 0), "
                    "coalesce(sum(completion_tokens), 0), coalesce(sum(cost_usd), 0), count(*) "
                    "FROM turn_usage WHERE created_at >= now() - (%s * interval '1 day') "
                    "GROUP BY 1, 2",
                    (SIGNAL_DAYS,),
                )).fetchall()
            return [
                {"task": r[0], "model": r[1], "prompt_tokens": int(r[2]),
                 "completion_tokens": int(r[3]), "cost_usd": float(r[4]), "calls": int(r[5])}
                for r in rows
            ]
        except Exception:  # noqa: BLE001 — el diagnóstico degrada, no rompe Dreams
            logger.warning("turn_usage no disponible para el diagnóstico; "
                           "bucket de costo saltado", exc_info=True)
            return []

    async def _candidates(self, tenant_id: str) -> list[dict]:
        from ..api.routes.value import value_settings_for  # import local: evita ciclos
        from .gepa import GEPALoop

        turns = self._window_turns(tenant_id)
        value_cfg = await value_settings_for(tenant_id)
        rate = float(value_cfg["hourly_rate_usd"])
        usage_rows = await self._usage_rows(tenant_id)
        try:
            grades = await GEPALoop(trace_capture=self.trace_capture).grade_all_skills(tenant_id)
        except Exception:  # noqa: BLE001
            logger.warning("grade_all_skills falló; bucket de guías saltado", exc_info=True)
            grades = []

        candidates: list[dict] = []
        candidates += bucket_rework(turns, rate)
        candidates += bucket_rejections(turns, rate)
        candidates += bucket_knowledge_gaps(turns)
        candidates += bucket_cost(usage_rows)
        candidates += bucket_skills(grades)
        candidates += bucket_value_config(len(turns), value_cfg)
        return candidates

    async def _load_states(self, tenant_id: str) -> dict[str, dict]:
        async with pool.tenant_connection(tenant_id) as conn:
            rows = await (await conn.execute(
                "SELECT prescription_id, status, first_seen_at, last_seen_at, decided_at "
                "FROM dream_prescriptions"
            )).fetchall()
        return {
            r[0]: {"status": r[1], "first_seen_at": r[2], "last_seen_at": r[3], "decided_at": r[4]}
            for r in rows
        }

    async def _persist(self, tenant_id: str, visible: list[dict]) -> None:
        """Sincroniza la tabla con el diagnóstico vigente.

        - Upsert de TODA tarjeta con señal viva (`visible`), no solo del top-4:
          así una tarjeta que salió del top por ranking/diversidad conserva su
          `first_seen_at` (edad real del problema) para cuando vuelva (capa 2, H2).
          El panel solo muestra las que traen `surfaced=true` en el payload.
        - El upsert JAMÁS resetea una fila con decisión del abogado
          (decided_at IS NOT NULL), salvo que run() la marque explícitamente
          para resurgir (`_resurface`: la decisión pasó los 30 días y la señal
          sigue viva). Sin comparar relojes: cierra la carrera cron×decisión
          por completo, incluida la ventana de transacciones solapadas
          (capa 2, H1 y R1).
        - PODA solo de las tarjetas 'new'/'recurring' cuya SEÑAL desapareció
          (no están en `visible`): se resolvieron solas. Las decisiones del
          abogado NUNCA se podan — son la memoria que evita repetirle lo ya
          decidido."""
        now = datetime.now(timezone.utc)
        ids = [p["id"] for p in visible]
        async with pool.tenant_connection(tenant_id) as conn:
            for p in visible:
                resurface = bool(p.pop("_resurface", False))
                await conn.execute(
                    "INSERT INTO dream_prescriptions "
                    "  (tenant_id, prescription_id, status, payload, first_seen_at, last_seen_at) "
                    "VALUES (%s::uuid, %s, 'new', %s, %s, %s) "
                    "ON CONFLICT (tenant_id, prescription_id) DO UPDATE SET "
                    "  status = CASE WHEN %s THEN 'recurring' "
                    "                WHEN dream_prescriptions.decided_at IS NOT NULL "
                    "                THEN dream_prescriptions.status ELSE 'recurring' END, "
                    "  decided_at = CASE WHEN %s THEN NULL "
                    "                    ELSE dream_prescriptions.decided_at END, "
                    "  payload = EXCLUDED.payload, "
                    "  last_seen_at = EXCLUDED.last_seen_at",
                    (tenant_id, p["id"], Json(p), now, now, resurface, resurface),
                )
            await conn.execute(
                "DELETE FROM dream_prescriptions "
                "WHERE status IN ('new', 'recurring') AND NOT (prescription_id = ANY(%s))",
                (ids,),
            )

    async def run(self, tenant_id: str) -> dict:
        """Diagnóstico completo: candidatos → memoria → top 4 → persistir.

        Devuelve {"prescriptions": [...(surfaceadas)], "candidates_total": n,
        "suppressed": [ids callados por decisión reciente del abogado]}.
        """
        candidates = await self._candidates(tenant_id)
        states = await self._load_states(tenant_id)
        now = datetime.now(timezone.utc)

        visible: list[dict] = []
        suppressed: list[str] = []
        for p in candidates:
            state = states.get(p["id"])
            if state and state["status"] in ("accepted", "dismissed"):
                decided = state["decided_at"] or state["last_seen_at"]
                if decided and (now - decided) < timedelta(days=RESURFACE_DAYS):
                    suppressed.append(p["id"])   # el abogado ya decidió; se respeta
                    continue
                p["status"] = "recurring"        # la señal volvió pasado el plazo
                p["_resurface"] = True           # única vía para resetear una decisión
            elif state:
                p["status"] = "recurring"
            else:
                p["status"] = "new"
            first_seen = state["first_seen_at"] if state else now
            p["age_days"] = max(0, (now - first_seen).days)
            visible.append(p)

        surfaced = rank_and_diversify(visible)
        surfaced_ids = {p["id"] for p in surfaced}
        for p in visible:
            p["surfaced"] = p["id"] in surfaced_ids
        await self._persist(tenant_id, visible)
        return {
            "prescriptions": surfaced,
            "candidates_total": len(candidates),
            "suppressed": suppressed,
        }
