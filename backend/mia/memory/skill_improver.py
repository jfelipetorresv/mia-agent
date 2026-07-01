"""Mia · memory.skill_improver — auto-mejora de playbooks con HITL pending (Tarea H.4).

Patrón Hermes v0.17.0 (background review: tras cada tarea exitosa se extrae un patrón
reutilizable). LA DIFERENCIA DE DISEÑO DE MIA: Hermes escribe/edita skills SIN gate humano
(`background_review.py`); Mia adopta el DISPARADOR (revisar tras cada caso aprobado) pero NUNCA
persiste como autoritativo — TODO cae en `feedback_proposals` con `status='pending'` para que un
abogado apruebe (mismo flujo HITL existente, sin tabla nueva).

Gate de extracción (los 3 requisitos): la traza debe estar `approved`, tener `activated_playbooks`
no vacío, y el playbook activado debe haberse usado >1 vez (señal de relevancia = `usage_count`).
Sin LLM en el camino: la extracción y el diff son deterministas (fire-and-forget barato).
"""
from __future__ import annotations

import difflib
import logging
from dataclasses import dataclass, field

from psycopg.rows import dict_row

from ..db import pool

logger = logging.getLogger("mia.memory.skill_improver")

MIN_USES = 2   # "usado >1 vez": un patrón recurrente, no un one-off


@dataclass
class SkillCandidate:
    """Un patrón reutilizable detectado en una traza aprobada. NO es autoritativo todavía."""

    tenant_id: str
    matter_id: str
    playbook_ids: list[str]
    pattern: str                       # qué patrón se repitió
    context: str                       # en qué contexto (la consulta del abogado)
    effectiveness: str                 # qué lo hizo efectivo
    trace_ids: list[str] = field(default_factory=list)
    signal_count: int = 1              # nº de usos observados (relevancia)


def _relevance_of(trace: dict) -> int:
    """Señal de relevancia embebida en la traza (si el caller la enriqueció). Default 1."""
    for k in ("relevance", "use_count", "usage_count", "memory_relevance"):
        v = trace.get(k)
        if isinstance(v, int):
            return v
    return 1


def extract_skill_candidate(trace: dict, *, relevance: int | None = None,
                            min_uses: int = MIN_USES) -> SkillCandidate | None:
    """Extrae un `SkillCandidate` de una traza, o None si no cumple los 3 requisitos:
    `hitl_outcome == 'approved'`, `activated_playbooks` no vacío, y relevancia (usos) >= min_uses.

    Determinista y sin DB/LLM: apto para llamarse fire-and-forget en el turno."""
    if trace.get("hitl_outcome") != "approved":
        return None
    playbooks = [str(p) for p in (trace.get("activated_playbooks") or [])]
    if not playbooks:
        return None
    uses = relevance if relevance is not None else _relevance_of(trace)
    if uses < min_uses:
        return None

    consulta = (trace.get("input") or "").strip()
    respuesta = (trace.get("output") or "").strip()
    tid = f"{trace.get('tenant_id')}:{trace.get('matter_id')}:{trace.get('timestamp', '')}"
    return SkillCandidate(
        tenant_id=str(trace.get("tenant_id")),
        matter_id=str(trace.get("matter_id")),
        playbook_ids=playbooks,
        pattern=f"Respuesta aprobada que aplicó {len(playbooks)} playbook(s) y fue reutilizada "
                f"{uses} veces.",
        context=consulta[:500],
        effectiveness=f"El abogado APROBÓ el borrador (outcome=approved); los playbooks "
                      f"{', '.join(playbooks)} aportaron al resultado. Extracto: {respuesta[:200]}",
        trace_ids=[tid],
        signal_count=uses,
    )


class SkillImprover:
    """Orquesta extracción → propuesta HITL. Sin estado; cada método toma el pool."""

    async def propose_improvement(self, candidate: SkillCandidate,
                                  existing_playbook: dict | None) -> dict:
        """Persiste una propuesta de mejora en `feedback_proposals` con `status='pending'`.

        Con `existing_playbook` → `improve_playbook` (target = su id) con un DIFF del contenido
        actual vs. la mejora propuesta. Sin él → `new_playbook`. NUNCA queda aprobada sola."""
        if existing_playbook:
            current = existing_playbook.get("content", "") or ""
            improved = self._improved_content(current, candidate)
            diff = "\n".join(difflib.unified_diff(
                current.splitlines(), improved.splitlines(),
                fromfile="actual", tofile="propuesto", lineterm=""))
            proposal_type = "improve_playbook"
            target_id = str(existing_playbook.get("id")) if existing_playbook.get("id") else None
            suggested = improved
            rationale = (f"Patrón recurrente ({candidate.signal_count} usos) en trazas aprobadas.\n"
                         f"Procedencia: {', '.join(candidate.trace_ids)}\n\nDIFF:\n{diff}")
        else:
            proposal_type = "new_playbook"
            target_id = None
            suggested = f"{candidate.pattern}\n\nContexto: {candidate.context}\n\n{candidate.effectiveness}"
            rationale = (f"Nuevo patrón reutilizable detectado ({candidate.signal_count} usos).\n"
                         f"Procedencia: {', '.join(candidate.trace_ids)}")

        async with pool.tenant_connection(candidate.tenant_id) as conn:
            row = await (await conn.execute(
                "INSERT INTO feedback_proposals "
                "  (tenant_id, proposal_type, target_playbook_id, suggested_content, rationale, "
                "   signal_count, trace_ids, status) "
                "VALUES (%s::uuid, %s, %s, %s, %s, %s, %s, 'pending') RETURNING id::text",
                (candidate.tenant_id, proposal_type, target_id, suggested, rationale,
                 candidate.signal_count, candidate.trace_ids),
            )).fetchone()
        return {"id": row[0], "proposal_type": proposal_type, "status": "pending",
                "target_playbook_id": target_id}

    @staticmethod
    def _improved_content(current: str, candidate: SkillCandidate) -> str:
        """Mejora determinista: anexa una sección de patrón reforzado (sin LLM)."""
        addition = (f"\n\n## Patrón reforzado (auto-detectado, pendiente de revisión)\n"
                    f"{candidate.pattern}\nContexto típico: {candidate.context}")
        if addition.strip() in current:
            return current
        return current.rstrip() + addition

    async def _lookup_playbook(self, tenant_id: str, playbook_id: str) -> dict | None:
        """Trae el playbook activado (id, content, usage_count) bajo RLS. None si no existe."""
        async with pool.tenant_connection(tenant_id) as conn:
            async with conn.cursor(row_factory=dict_row) as cur:
                await cur.execute(
                    "SELECT id::text, title, content, usage_count, protected FROM playbooks "
                    "WHERE id = %s::uuid", (playbook_id,))
                return await cur.fetchone()

    async def process_trace(self, tenant_id: str, trace: dict) -> dict | None:
        """Camino completo: enriquece la relevancia desde el playbook (usage_count), extrae el
        candidato y, si aplica, propone la mejora (pending). Devuelve la propuesta o None."""
        playbooks = [str(p) for p in (trace.get("activated_playbooks") or [])]
        if trace.get("hitl_outcome") != "approved" or not playbooks:
            return None
        existing = await self._lookup_playbook(tenant_id, playbooks[0])
        # H.6: un playbook protegido (semilla/core) NO se mejora automáticamente (inmune al HITL
        # de skills). Se respeta su versión curada a mano.
        if existing and existing.get("protected"):
            return None
        relevance = int(existing["usage_count"]) if existing and existing.get("usage_count") is not None else 1
        candidate = extract_skill_candidate(trace, relevance=relevance)
        if candidate is None:
            return None
        return await self.propose_improvement(candidate, existing)

    async def process_trace_safe(self, tenant_id: str, trace: dict) -> dict | None:
        """Envoltura FIRE-AND-FORGET segura: nunca propaga excepciones (no debe tumbar el turno);
        registra el fallo en vez de tragarlo en silencio (lección de la sesión smoke)."""
        try:
            return await self.process_trace(tenant_id, trace)
        except Exception:  # noqa: BLE001 — best-effort; el turno no depende de esto
            logger.exception("skill_improver falló (tenant=%s); el turno no se ve afectado", tenant_id)
            return None
