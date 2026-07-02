"""GEPA loop: aprendizaje procedural por tenant a partir de trazas aprobadas."""
from __future__ import annotations

import asyncio
import json
import os
import re
from collections import Counter, defaultdict
from datetime import datetime, timedelta, timezone
from typing import Any

from psycopg.rows import dict_row
from psycopg.types.json import Json

from ..agent import llm
from ..db import pool
from .trace_capture import TraceCapture


def _parse_ts(value: str | None) -> datetime:
    if not value:
        return datetime.min.replace(tzinfo=timezone.utc)
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return datetime.min.replace(tzinfo=timezone.utc)


def _norm(text: str) -> str:
    words = re.findall(r"\w+", text.lower())
    return " ".join(words[:10])


def _trace_playbook_ids(trace: dict) -> list[str]:
    ids: list[str] = []
    for key in ("playbook_id", "skill_id"):
        if trace.get(key):
            ids.append(str(trace[key]))
    for key in ("playbook_ids", "skill_ids", "activated_playbooks"):
        value = trace.get(key)
        if isinstance(value, list):
            ids.extend(str(v) for v in value)
    meta = trace.get("metadata")
    if isinstance(meta, dict):
        ids.extend(_trace_playbook_ids(meta))
    return list(dict.fromkeys(ids))


def _outcome(trace: dict) -> str | None:
    value = trace.get("hitl_outcome") or trace.get("outcome")
    return str(value) if value else None


class GEPALoop:
    """Aprende procedimientos del despacho sin aplicar cambios sin revisión humana."""

    def __init__(self, *, trace_capture: TraceCapture | None = None) -> None:
        self.trace_capture = trace_capture or TraceCapture()

    def _recent_traces(self, tenant_id: str, days: int) -> list[dict]:
        cutoff = datetime.now(timezone.utc) - timedelta(days=days)
        return [t for t in self.trace_capture.read(tenant_id) if _parse_ts(t.get("timestamp")) >= cutoff]

    async def _llm_text(self, prompt: str) -> str:
        try:
            resp = await asyncio.to_thread(
                llm.call_llm,
                [{"role": "user", "content": prompt}],
                task="curator",
                temperature=0.1,
            )
            return resp.choices[0].message.content or ""
        except Exception:
            return ""

    async def detect_new_skill(self, tenant_id: str, trace_window: int = 7) -> dict | None:
        traces = [
            t for t in self._recent_traces(tenant_id, trace_window)
            if _outcome(t) == "approved" and not _trace_playbook_ids(t)
        ]
        groups: dict[str, list[dict]] = defaultdict(list)
        for trace in traces:
            key = _norm(str(trace.get("input") or ""))
            if key:
                groups[key].append(trace)
        candidates = sorted(groups.values(), key=len, reverse=True)
        if not candidates or len(candidates[0]) < 2:
            return None

        sample = candidates[0]
        evidence = "\n\n---\n\n".join(
            f"Pregunta:\n{t.get('input', '')}\n\nRespuesta aprobada:\n{t.get('output', '')}"
            for t in sample[:5]
        )
        prompt = (
            "A partir de respuestas aprobadas por el despacho, redacta un draft de procedimiento. "
            "No asumas jurisdiccion, area, norma, corte, idioma ni tipo de proceso. "
            "Devuelve JSON con title, applies_when y content.\n\n"
            f"Evidencia:\n{evidence}"
        )
        raw = await self._llm_text(prompt)
        draft: dict[str, str]
        try:
            parsed = json.loads(raw)
            draft = {
                "title": str(parsed["title"])[:200],
                "applies_when": str(parsed["applies_when"]),
                "content": str(parsed["content"]),
            }
        except Exception:
            first = str(sample[0].get("input") or "procedimiento recurrente")
            draft = {
                "title": f"Procedimiento detectado: {first[:80]}",
                "applies_when": "Cuando aparezca un patrón similar al observado en respuestas aprobadas.",
                "content": evidence,
            }
        draft["status"] = "draft"
        draft["signal_count"] = len(sample)

        async with pool.tenant_connection(tenant_id) as conn:
            row = await (await conn.execute(
                "INSERT INTO playbooks "
                "  (tenant_id, title, summary, applies_when, content, status, metadata) "
                "VALUES (%s::uuid, %s, %s, %s, %s, 'draft', %s) "
                "ON CONFLICT (tenant_id, title) DO UPDATE SET "
                "  applies_when = EXCLUDED.applies_when, content = EXCLUDED.content, "
                "  status = 'draft', metadata = EXCLUDED.metadata, updated_at = now() "
                "RETURNING id",
                (
                    tenant_id,
                    draft["title"],
                    f"Detectado por {len(sample)} aprobaciones similares.",
                    draft["applies_when"],
                    draft["content"],
                    Json({"gepa": {"signal_count": len(sample)}}),
                ),
            )).fetchone()
            await conn.execute(
                "INSERT INTO feedback_proposals "
                "  (tenant_id, proposal_type, target_playbook_id, suggested_content, rationale, signal_count) "
                "VALUES (%s::uuid, 'new_playbook', %s::uuid, %s, %s, %s)",
                (
                    tenant_id,
                    row[0],
                    draft["content"],
                    "Mia detectó respuestas aprobadas recurrentes sin procedimiento asignado.",
                    len(sample),
                ),
            )
        draft["skill_id"] = str(row[0])
        return draft

    async def _playbook(self, tenant_id: str, playbook_id: str) -> dict | None:
        async with pool.tenant_connection(tenant_id) as conn:
            async with conn.cursor(row_factory=dict_row) as cur:
                await cur.execute(
                    "SELECT id, title, summary, applies_when, content, status "
                    "FROM playbooks WHERE id = %s::uuid",
                    (playbook_id,),
                )
                return await cur.fetchone()

    def _traces_for_skill(self, tenant_id: str, playbook_id: str, days: int = 30) -> list[dict]:
        return [t for t in self._recent_traces(tenant_id, days) if playbook_id in _trace_playbook_ids(t)]

    @staticmethod
    def _rates(traces: list[dict]) -> tuple[float, float]:
        if not traces:
            return 0.0, 0.0
        outcomes = [_outcome(t) for t in traces]
        approved = sum(1 for o in outcomes if o == "approved")
        edited = sum(1 for o in outcomes if o == "edited")
        return approved / len(traces), edited / len(traces)

    async def evolve_skill(self, tenant_id: str, playbook_id: str) -> dict:
        pb = await self._playbook(tenant_id, playbook_id)
        if not pb:
            return {
                "skill_id": playbook_id,
                "current_approval_rate": 0.0,
                "edit_rate": 0.0,
                "proposal_created": False,
            }
        traces = self._traces_for_skill(tenant_id, playbook_id)
        approval_rate, edit_rate = self._rates(traces)
        should_propose = bool(traces) and (approval_rate < 0.60 or edit_rate > 0.30)
        if not should_propose:
            return {
                "skill_id": playbook_id,
                "current_approval_rate": approval_rate,
                "edit_rate": edit_rate,
                "proposal_created": False,
            }

        corrections = "\n\n---\n\n".join(
            f"Outcome: {_outcome(t)}\nInput:\n{t.get('input', '')}\nOutput:\n{t.get('output', '')}\nFinal:\n{t.get('draft_final', '')}"
            for t in traces[:10]
        )
        prompt = (
            "Mejora este procedimiento usando las correcciones del despacho. "
            "No asumas jurisdiccion, area, norma, corte, idioma ni tipo de proceso. "
            "Devuelve solo el contenido mejorado; no lo apliques.\n\n"
            f"Procedimiento actual:\n{pb['content']}\n\nTrazas:\n{corrections}"
        )
        improved = await self._llm_text(prompt) or f"{pb['content']}\n\n## Ajustes propuestos\n{corrections}"
        async with pool.tenant_connection(tenant_id) as conn:
            await conn.execute(
                "INSERT INTO feedback_proposals "
                "  (tenant_id, proposal_type, target_playbook_id, suggested_content, rationale, signal_count) "
                "VALUES (%s::uuid, 'improve_playbook', %s::uuid, %s, %s, %s)",
                (
                    tenant_id,
                    playbook_id,
                    improved,
                    f"approval_rate={approval_rate:.2f}; edit_rate={edit_rate:.2f}",
                    len(traces),
                ),
            )
        return {
            "skill_id": playbook_id,
            "current_approval_rate": approval_rate,
            "edit_rate": edit_rate,
            "proposal_created": True,
        }

    async def grade_all_skills(self, tenant_id: str) -> list[dict]:
        async with pool.tenant_connection(tenant_id) as conn:
            async with conn.cursor(row_factory=dict_row) as cur:
                await cur.execute(
                    "SELECT id, title FROM playbooks WHERE status = 'active' ORDER BY created_at"
                )
                playbooks = await cur.fetchall()
        grades: list[dict] = []
        for pb in playbooks:
            traces = self._traces_for_skill(tenant_id, str(pb["id"]))
            approval_rate, edit_rate = self._rates(traces)
            grades.append({
                "skill_id": str(pb["id"]),
                "title": pb["title"],
                "approval_rate": approval_rate,
                "edit_rate": edit_rate,
                "activations": len(traces),
            })
        return sorted(grades, key=lambda x: (x["approval_rate"], -x["edit_rate"], x["activations"]), reverse=True)

    async def prune_unused_skills(self, tenant_id: str, days: int = 60) -> list[str]:
        async with pool.tenant_connection(tenant_id) as conn:
            rows = await (await conn.execute(
                "UPDATE playbooks SET status = 'archived', updated_at = now() "
                "WHERE status = 'active' AND NOT protected "     # H.6: no podar semillas/core
                "AND (last_used_at IS NULL OR last_used_at < now() - (%s * interval '1 day')) "
                "AND created_at < now() - (%s * interval '1 day') "
                "RETURNING id",
                (days, days),
            )).fetchall()
        return [str(r[0]) for r in rows]

    async def run_evolution_cycle(self, tenant_id: str) -> dict:
        new_skill = await self.detect_new_skill(tenant_id)
        grades = await self.grade_all_skills(tenant_id)
        evolved = []
        for grade in grades:
            if grade["activations"] and grade["approval_rate"] < 0.60:
                evolved.append(await self.evolve_skill(tenant_id, grade["skill_id"]))
        pruned = await self.prune_unused_skills(tenant_id)
        top = await self.grade_all_skills(tenant_id)
        return {
            "new_skills_proposed": 1 if new_skill else 0,
            "skills_evolved": sum(1 for item in evolved if item.get("proposal_created")),
            "skills_pruned": pruned,
            "top_skills": top[:5],
        }

    async def run_all_tenants(self) -> dict:
        out: dict[str, dict] = {}
        for tenant_id in self._list_tenant_ids():
            try:
                async with llm.tenant_model_policy(tenant_id):  # CP2: política por tenant
                    out[tenant_id] = await self.run_evolution_cycle(tenant_id)
            except Exception as e:
                out[tenant_id] = {"error": str(e)}
        return out

    def _list_tenant_ids(self) -> list[str]:
        import psycopg

        pw = os.getenv("PG_PASSWORD", "")
        if not pw:
            return []
        kw = dict(
            host=os.getenv("PG_HOST", "127.0.0.1"),
            port=os.getenv("PG_PORT", "5432"),
            dbname=os.getenv("PG_DB", "mia"),
            user="postgres",
            password=pw,
        )
        with psycopg.connect(autocommit=True, **kw) as c:
            rows = c.execute("SELECT id FROM tenants").fetchall()
        return [str(r[0]) for r in rows]
