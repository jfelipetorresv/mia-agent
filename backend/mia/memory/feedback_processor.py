"""Mia · memory.feedback_processor — aprende de las trazas y PROPONE mejoras (Módulo 3e).

Tarea CRON diaria (1am, job `feedback_daily`). Por cada tenant: lee las trazas JSONL del 2d
(enriquecidas a v2, decisión #19), detecta tres señales —rechazos del abogado, ediciones
significativas y respuestas sin documentos— y, cuando un patrón se repite (≥2 veces), genera
PROPUESTAS de mejora a playbooks. NO aplica nada: las propuestas quedan en `feedback_proposals`
con `status='pending'` para que el abogado las revise (Pantalla 4, Fase 3).

`call_llm(task="curator")` (claude-sonnet) redacta el contenido de cada propuesta. Las trazas ya
procesadas se marcan con un watermark por (tenant, día) → no se reanalizan.
"""
from __future__ import annotations

import asyncio
import difflib
import logging
import os
from datetime import datetime, timedelta, timezone

from ..agent import llm
from ..db import pool
from .gepa import trace_playbook_ids
from .trace_capture import TRACE_SCHEMA, TRACE_SCHEMA_V2, TraceCapture

logger = logging.getLogger("mia.feedback")

MIN_OCCURRENCES = 2       # un patrón debe repetirse al menos esto para generar propuesta
EDIT_DIFF_THRESHOLD = 0.20  # >20% de cambio de caracteres = edición significativa
_SIGNAL_TO_TYPE_WHEN_PB = {"HITL_REJECTION": "improve_playbook", "HITL_EDIT": "improve_playbook"}


class FeedbackProcessor:
    """Lee trazas, detecta señales y propone mejoras a playbooks (no las aplica)."""

    def __init__(self, traces_dir=None) -> None:
        # TraceCapture sin dir → mia-data/traces (default). El gate pasa un dir temporal.
        self._tc = TraceCapture(traces_dir)

    # ── entry point por tenant ────────────────────────────────────────────────
    async def run(self, tenant_id: str) -> dict:
        """Ciclo completo para un tenant. {traces_analyzed, proposals_created, errors}."""
        stats = {"traces_analyzed": 0, "proposals_created": 0, "errors": 0}
        try:
            traces = await self.load_traces(tenant_id)
            stats["traces_analyzed"] = len(traces)
            if traces:
                analysis = await self.analyze(traces)
                proposals = await self.propose(tenant_id, analysis)
                stats["proposals_created"] = await self.save_proposals(tenant_id, proposals)
                await self.mark_traces_processed(tenant_id, traces)
        except Exception:
            stats["errors"] += 1
            logger.exception("feedback.run falló (tenant %s)", tenant_id)
        return stats

    async def load_traces(self, tenant_id: str, since_hours: int = 24) -> list[dict]:
        """Trazas de turno (v1/v2) del tenant aún NO procesadas (por watermark) y dentro de la
        ventana `since_hours`. Ignora los registros de evento (mia.trace.event.v1)."""
        records = self._tc.read(tenant_id)
        async with pool.tenant_connection(tenant_id) as conn:
            rows = await (await conn.execute(
                "SELECT trace_date FROM processed_traces_watermark")).fetchall()
        processed_dates = {r[0].isoformat() for r in rows}
        cutoff = datetime.now(timezone.utc) - timedelta(hours=since_hours)

        out: list[dict] = []
        for rec in records:
            if rec.get("schema") not in (TRACE_SCHEMA, TRACE_SCHEMA_V2):
                continue   # evento, no traza de turno
            ts = rec.get("timestamp", "")
            day = ts[:10]
            if day in processed_dates:
                continue
            try:
                if datetime.fromisoformat(ts) < cutoff:
                    continue
            except Exception:
                pass
            rec["trace_id"] = f"{tenant_id}:{rec.get('matter_id')}:{ts}"
            out.append(rec)
        return out

    async def analyze(self, traces: list[dict]) -> dict:
        """Cuenta las tres señales. Devuelve {SIGNAL: {count, trace_ids, playbooks}}.

        CP-C3 (cierra Riesgo #31): además del conteo, cada señal de rechazo/edición
        acumula QUÉ playbooks estaban activados en esas trazas (`activated_playbooks`,
        traza v2) — así la propuesta apunta al procedimiento que participó en el turno
        que falló, no a uno arbitrario."""
        signals: dict[str, dict] = {
            "HITL_REJECTION": {"count": 0, "trace_ids": [], "playbooks": {}},
            "HITL_EDIT": {"count": 0, "trace_ids": [], "playbooks": {}},
            "NO_RESULT": {"count": 0, "trace_ids": [], "playbooks": {}},
        }

        def _hit(signal: str, trace: dict) -> None:
            signals[signal]["count"] += 1
            signals[signal]["trace_ids"].append(trace.get("trace_id"))
            for pid in trace_playbook_ids(trace):
                pbs = signals[signal]["playbooks"]
                pbs[pid] = pbs.get(pid, 0) + 1

        for t in traces:
            outcome = t.get("hitl_outcome")
            if outcome == "rejected":
                _hit("HITL_REJECTION", t)
            elif outcome == "edited" and self._significant_edit(
                    t.get("draft_original"), t.get("draft_final")):
                _hit("HITL_EDIT", t)
            if not t.get("retrieved_doc_ids"):   # [] o ausente/None
                _hit("NO_RESULT", t)
        return signals

    @staticmethod
    def _significant_edit(original, final) -> bool:
        """True si el cambio de caracteres entre borrador y final supera el umbral (20%)."""
        if not original or not final:
            return False
        ratio = difflib.SequenceMatcher(None, original, final).ratio()
        return (1.0 - ratio) > EDIT_DIFF_THRESHOLD

    async def propose(self, tenant_id: str, analysis: dict) -> list[dict]:
        """Genera una propuesta por cada señal con ≥ MIN_OCCURRENCES. El tipo depende de si el
        tenant ya tiene playbooks (improve vs new) y de la señal (NO_RESULT → flag_gap).

        CP-C3 (cierra Riesgo #31): el target de 'improve_playbook' es el playbook MÁS
        ACTIVADO en las trazas de la señal (analyze() lo trae en `playbooks`) — el que de
        verdad participó en los turnos rechazados/editados. Sin esa evidencia se cae al
        más usado del tenant. Los playbooks `protected` (H.6) NUNCA son target: si solo
        hay protegidos, la propuesta baja a 'new_playbook' (nunca un 409 sin salida)."""
        active = await self._active_playbooks(tenant_id)
        proposals: list[dict] = []
        for signal, info in analysis.items():
            if info["count"] < MIN_OCCURRENCES:
                continue
            linked = False
            brief = None
            if signal == "NO_RESULT":
                ptype, target = "flag_gap", None
            else:
                target, linked = self._pick_target(info.get("playbooks") or {}, active)
                ptype = "improve_playbook" if target else "new_playbook"
                if target:
                    brief = await self._playbook_brief(tenant_id, target)
            rationale = f"{info['count']} ocurrencias de {signal} en el período."
            if linked:
                # El abogado debe saber QUÉ procedimiento se va a modificar (revisor CP-C3).
                nombre = f" «{brief['title']}»" if brief else ""
                rationale += (f" El procedimiento{nombre} estaba activo en las trazas "
                              "que generaron la señal.")
            elif brief:
                rationale += (f" Se sugiere revisar el procedimiento «{brief['title']}» "
                              "(el más usado del despacho; las trazas no señalan uno específico).")
            suggested = await asyncio.to_thread(
                self._draft_proposal, signal, info["count"], brief)
            proposals.append({
                "type": ptype,
                "target_playbook_id": target,
                "suggested_content": suggested,
                "rationale": rationale,
                "signal_count": info["count"],
                "trace_ids": [tid for tid in info["trace_ids"] if tid],
            })
        return proposals

    @staticmethod
    def _pick_target(activated_counts: dict, active: list[dict]) -> tuple[str | None, bool]:
        """Elige el playbook a mejorar → (target_id | None, vinculado_a_trazas).

        Prioridad: el más activado en las trazas de la señal que siga activo y NO esté
        protegido; fallback: el activo no protegido más usado del tenant. None si no
        hay candidato válido (p. ej. todos protegidos)."""
        unprotected = [str(a["id"]) for a in active if not a.get("protected")]
        allowed = set(unprotected)
        for pid, _n in sorted(activated_counts.items(), key=lambda kv: (-kv[1], kv[0])):
            if str(pid) in allowed:
                return str(pid), True
        return (unprotected[0] if unprotected else None), False

    # Cuánto del contenido actual del playbook ve el LLM al redactar la mejora.
    _BRIEF_CONTENT_MAX_CHARS = 6000

    async def _playbook_brief(self, tenant_id: str, playbook_id: str) -> dict | None:
        """{title, content} del playbook target (bajo RLS) — para que la propuesta se
        redacte SOBRE la metodología real y el abogado sepa qué se va a modificar."""
        async with pool.tenant_connection(tenant_id) as conn:
            row = await (await conn.execute(
                "SELECT title, content FROM playbooks WHERE id = %s::uuid",
                (playbook_id,),
            )).fetchone()
        if not row:
            return None
        return {"title": row[0], "content": (row[1] or "")[:self._BRIEF_CONTENT_MAX_CHARS]}

    @staticmethod
    def _draft_proposal(signal: str, count: int, brief: dict | None = None) -> str:
        """Pide al LLM (task=curator → claude-sonnet) el contenido de la propuesta.

        Hallazgo del revisor CP-C3: cuando hay un playbook target, el LLM ve su
        contenido ACTUAL y propone la versión mejorada COMPLETA (aplicar la propuesta
        reemplaza el contenido — sin ver el original, la metodología real se perdería)."""
        system = (
            "Eres un curador de la metodología de un despacho. A partir de una señal "
            "repetida en el trabajo de Mia, propones UNA mejora concreta y accionable a los "
            "playbooks (o un playbook nuevo, o señalar un vacío de conocimiento). Devuelve "
            "solo el texto de la propuesta.")
        user = f"Señal: {signal}. Ocurrencias en el período: {count}."
        if brief:
            system = (
                "Eres un curador de la metodología de un despacho. Un procedimiento existente "
                "participó en trabajos que el abogado rechazó o corrigió. Devuelve la VERSIÓN "
                "MEJORADA COMPLETA del procedimiento (tu texto reemplazará al actual si el "
                "abogado la aprueba): conserva TODO lo que sigue siendo válido del contenido "
                "actual y ajusta solo lo necesario según la señal. No inventes normas ni "
                "jurisdicción. Devuelve solo el contenido mejorado.")
            user += (f"\n\nProcedimiento a mejorar: {brief['title']}\n"
                     f"Contenido actual:\n{brief['content']}")
        messages = [
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ]
        resp = llm.call_llm(messages, task="curator")
        return resp.choices[0].message.content or ""

    async def save_proposals(self, tenant_id: str, proposals: list[dict]) -> int:
        """Persiste las propuestas en feedback_proposals (status='pending'). Devuelve cuántas."""
        if not proposals:
            return 0
        async with pool.tenant_connection(tenant_id) as conn:
            for p in proposals:
                await conn.execute(
                    "INSERT INTO feedback_proposals "
                    "  (tenant_id, proposal_type, target_playbook_id, suggested_content, "
                    "   rationale, signal_count, trace_ids) "
                    "VALUES (%s::uuid, %s, %s, %s, %s, %s, %s)",
                    (tenant_id, p["type"], p["target_playbook_id"], p["suggested_content"],
                     p["rationale"], p["signal_count"], p["trace_ids"]),
                )
        return len(proposals)

    async def mark_traces_processed(self, tenant_id: str, traces: list[dict]) -> None:
        """Avanza el watermark por (tenant, día) según las trazas procesadas."""
        from collections import Counter
        days = Counter(t["timestamp"][:10] for t in traces if t.get("timestamp"))
        if not days:
            return
        async with pool.tenant_connection(tenant_id) as conn:
            for day, n in days.items():
                await conn.execute(
                    "INSERT INTO processed_traces_watermark "
                    "  (tenant_id, trace_date, last_processed_at, traces_processed) "
                    "VALUES (%s::uuid, %s::date, now(), %s) "
                    "ON CONFLICT (tenant_id, trace_date) DO UPDATE SET "
                    "  last_processed_at = now(), "
                    "  traces_processed = processed_traces_watermark.traces_processed + EXCLUDED.traces_processed",
                    (tenant_id, day, n),
                )

    # ── todos los tenants (cron) ──────────────────────────────────────────────
    async def run_all_tenants(self) -> dict:
        out: dict[str, dict] = {}
        for tenant_id in self._list_tenant_ids():
            try:
                async with llm.tenant_model_policy(tenant_id):  # CP2: política por tenant
                    out[tenant_id] = await self.run(tenant_id)
            except Exception as e:
                out[tenant_id] = {"error": str(e)}
                logger.exception("feedback.run falló (tenant %s)", tenant_id)
        return out

    async def _active_playbooks(self, tenant_id: str) -> list[dict]:
        """Playbooks activos del tenant (más usados primero), con su flag `protected`."""
        async with pool.tenant_connection(tenant_id) as conn:
            rows = await (await conn.execute(
                "SELECT id, protected FROM playbooks WHERE status='active' "
                "ORDER BY usage_count DESC"
            )).fetchall()
        return [{"id": str(r[0]), "protected": bool(r[1])} for r in rows]

    def _list_tenant_ids(self) -> list[str]:
        """Cross-tenant (operación de sistema) → conexión admin (Riesgo #15)."""
        import psycopg

        pw = os.getenv("PG_PASSWORD", "")
        if not pw:
            logger.warning("PG_PASSWORD vacío: el Feedback processor no puede enumerar tenants")
            return []
        kw = dict(host=os.getenv("PG_HOST", "127.0.0.1"), port=os.getenv("PG_PORT", "5432"),
                  dbname=os.getenv("PG_DB", "mia"), user="postgres", password=pw)
        with psycopg.connect(autocommit=True, **kw) as c:
            rows = c.execute("SELECT id FROM tenants").fetchall()
        return [str(r[0]) for r in rows]
