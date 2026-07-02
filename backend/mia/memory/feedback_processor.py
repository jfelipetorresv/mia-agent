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
        """Cuenta las tres señales. Devuelve {SIGNAL: {count, trace_ids}}."""
        signals: dict[str, dict] = {
            "HITL_REJECTION": {"count": 0, "trace_ids": []},
            "HITL_EDIT": {"count": 0, "trace_ids": []},
            "NO_RESULT": {"count": 0, "trace_ids": []},
        }
        for t in traces:
            tid = t.get("trace_id")
            outcome = t.get("hitl_outcome")
            if outcome == "rejected":
                signals["HITL_REJECTION"]["count"] += 1
                signals["HITL_REJECTION"]["trace_ids"].append(tid)
            elif outcome == "edited" and self._significant_edit(
                    t.get("draft_original"), t.get("draft_final")):
                signals["HITL_EDIT"]["count"] += 1
                signals["HITL_EDIT"]["trace_ids"].append(tid)
            if not t.get("retrieved_doc_ids"):   # [] o ausente/None
                signals["NO_RESULT"]["count"] += 1
                signals["NO_RESULT"]["trace_ids"].append(tid)
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
        tenant ya tiene playbooks (improve vs new) y de la señal (NO_RESULT → flag_gap)."""
        active = await self._active_playbook_ids(tenant_id)
        proposals: list[dict] = []
        for signal, info in analysis.items():
            if info["count"] < MIN_OCCURRENCES:
                continue
            if signal == "NO_RESULT":
                ptype, target = "flag_gap", None
            elif active:
                ptype, target = "improve_playbook", active[0]
            else:
                ptype, target = "new_playbook", None
            suggested = await asyncio.to_thread(self._draft_proposal, signal, info["count"])
            proposals.append({
                "type": ptype,
                "target_playbook_id": target,
                "suggested_content": suggested,
                "rationale": f"{info['count']} ocurrencias de {signal} en el período.",
                "signal_count": info["count"],
                "trace_ids": [tid for tid in info["trace_ids"] if tid],
            })
        return proposals

    @staticmethod
    def _draft_proposal(signal: str, count: int) -> str:
        """Pide al LLM (task=curator → claude-sonnet) el contenido de la propuesta."""
        messages = [
            {"role": "system", "content": (
                "Eres un curador de la metodología de un despacho. A partir de una señal "
                "repetida en el trabajo de Mia, propones UNA mejora concreta y accionable a los "
                "playbooks (o un playbook nuevo, o señalar un vacío de conocimiento). Devuelve "
                "solo el texto de la propuesta.")},
            {"role": "user", "content": f"Señal: {signal}. Ocurrencias en el período: {count}."},
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

    async def _active_playbook_ids(self, tenant_id: str) -> list[str]:
        async with pool.tenant_connection(tenant_id) as conn:
            rows = await (await conn.execute(
                "SELECT id FROM playbooks WHERE status='active' ORDER BY usage_count DESC"
            )).fetchall()
        return [str(r[0]) for r in rows]

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
