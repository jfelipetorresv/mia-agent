"""Mia · memory.curator — mantenimiento semántico de playbooks (Módulo 3b · decisión #18).

Tarea CRON semanal (domingos 2am, registrada como `curator_weekly` en `cron/scheduler.py`).
Por cada tenant: detecta playbooks redundantes (similitud coseno > 0.85 vía el operador `<=>`
de pgvector sobre el embedding del summary+applies_when), los **consolida** con un LLM fuerte
(`call_llm(task="curator")` → claude-sonnet) en un playbook mejorado, y **poda** los playbooks
sin uso en 90 días (`last_used_at`). Todo bajo `pool.tenant_connection` (RLS).

CONTRADICCIÓN ANTES QUE FUSIÓN (migración 038)
----------------------------------------------
La similitud coseno NO es compatibilidad. "En estos casos siempre pedimos X" y "en estos casos
nunca pedimos X" son semánticamente casi idénticos: el coseno los ve como gemelos y la fusión
producía una mezcla que no decía NINGUNA de las dos cosas. Ahí es donde el criterio de un
despacho se corrompe sin que nadie lo vea.

Por eso el coseno ya no decide solo. Tras él corre un SEGUNDO paso (`_classify_pair`, juez LLM
barato) que separa DUPLICADO de CONFLICTO:

  · duplicado → fusión propuesta, exactamente como siempre.
  · conflicto → NUNCA se funde. Sube al abogado como elección binaria (A vs B, con su fecha y su
    procedencia, ambas versiones vivas y sin mezclar) en una propuesta `kind='conflict'`.

El umbral es DELIBERADAMENTE conservador (ver `_classify_pair`): ante la duda se trata como
duplicado. Un detector con falsos positivos convierte cada aprobación en un interrogatorio, el
abogado deja de aprobar y la memoria deja de aprender — peor que el problema que arregla. Es
preferible fusionar de más que interrogar de más.

El LLM y los embeddings son síncronos; se invocan vía `asyncio.to_thread` para no bloquear el
event loop (mismo patrón que `agents/graph.py`).
"""
from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import os
import re
from dataclasses import dataclass, field

from psycopg.rows import dict_row
from psycopg.types.json import Json

from .. import embeddings
from ..agent import llm
from ..db import pool
from ..observability import audit

logger = logging.getLogger("mia.curator")

SIMILARITY_THRESHOLD = 0.85   # similitud coseno por encima de la cual dos playbooks se comparan
PRUNE_DAYS = 90               # playbooks sin uso en N días se archivan

# ── juez de contradicción (segundo paso, tras el coseno) ──────────────────────
# DÓNDE ESTÁ EL UMBRAL Y POR QUÉ AHÍ:
#
# Un par sube al abogado como CONFLICTO solo si se cumplen las DOS condiciones:
#   1) el juez responde literalmente "contrarios"  (ni "iguales" ni "no_se"), y
#   2) su confianza declarada es >= 0.85.
#
# Todo lo demás — "iguales", "no_se", confianza baja, JSON ilegible, respuesta vacía, el modelo
# caído, una excepción cualquiera — cae a DUPLICADO, que es el comportamiento de hoy (fusión
# propuesta, que el abogado ya puede rechazar). La asimetría es intencional y es el corazón del
# diseño: los dos errores posibles NO cuestan lo mismo.
#
#   · Falso negativo (un conflicto tratado como duplicado): el abogado ve una propuesta de fusión
#     de más, la rechaza, y todo sigue como antes de este cambio. Coste: un clic.
#   · Falso positivo (dos formulaciones del mismo criterio marcadas como contrarias): el abogado
#     recibe un interrogatorio por nada. Repetido, deja de aprobar — y una memoria que nadie
#     aprueba deja de aprender. Coste: la función entera.
#
# 0.85 y no 0.5: a 0.5 basta con que el juez "se incline" para interrumpir al abogado, y en pares
# con coseno > 0.85 (redacciones casi calcadas) inclinarse es fácil. 0.85 exige que el juez esté
# convencido. Y no 0.95, porque los modelos rara vez declaran confianzas tan altas y el detector
# se volvería decorativo. Si hay que moverlo, BAJARLO es lo peligroso.
CONFLICT_MIN_CONFIDENCE = 0.85
_JUDGE_TASK = "curator_conflict"   # auxiliar/barato en toda política (ver agent/llm.py)
_JUDGE_MAX_CHARS = 4000            # recorte por playbook: acota coste y contexto del juez
_JUDGE_VERDICTS = ("iguales", "contrarios", "no_se")


class _ProposalAbort(Exception):
    """Sentinela interno: aborta la transacción de apply_proposal por drift de estado (C.1)."""


@dataclass
class CuratorProposal:
    """Propuesta de curación (dry-run, patrón Hermes v0.17.0). NO muta nada por sí misma.

    `proposed_merges`   : [{"source_ids": [a, b], "target_title": str, "reason": str}]
    `proposed_deletions`: [{"id": str, "title": str, "reason": str}]
    `snapshot_hash`     : hash del estado de playbooks activos al momento de proponer.
    `raised_conflicts`  : conflictos detectados en esta corrida. NO son parte de esta propuesta:
                          cada uno se persiste como su PROPIA propuesta `kind='conflict'` (se
                          resuelve eligiendo A o B, no aprobando en bloque). Viajan aquí solo
                          para que el cron y el endpoint puedan reportarlos.
    """

    tenant_id: str
    proposed_merges: list[dict] = field(default_factory=list)
    proposed_deletions: list[dict] = field(default_factory=list)
    snapshot_hash: str = ""
    id: str | None = None                 # se rellena al persistir
    status: str = "pending"
    raised_conflicts: list[dict] = field(default_factory=list)

    def is_empty(self) -> bool:
        return not self.proposed_merges and not self.proposed_deletions

    def to_public(self) -> dict:
        """Dict amigable para el endpoint (sin jerga técnica hacia el usuario, §G)."""
        return {
            "id": self.id,
            "status": self.status,
            "merges": self.proposed_merges,
            "deletions": self.proposed_deletions,
            "conflicts": self.raised_conflicts,
            "snapshot_hash": self.snapshot_hash,
        }


class Curator:
    """Curador de playbooks. Sin estado: cada método toma una conexión del pool."""

    # ── entry point LEGACY por tenant (muta sin HITL) ─────────────────────────
    async def _run_legacy(self, tenant_id: str) -> dict:
        """LEGACY: ciclo completo que MUTA playbooks sin revisión humana (fusiona/poda directo).

        Reemplazado por el flujo HITL `propose()` + `apply_proposal()` (cierra Riesgo #19). Se
        conserva solo como ejecutor interno/compat de tests; NO usar en producción. Devuelve
        {analyzed, consolidated, pruned, errors}."""
        if os.getenv("MIA_ALLOW_CURATOR_LEGACY_RUN") != "1":
            raise RuntimeError(
                "Curator._run_legacy() muta sin HITL; usar propose() + "
                "apply_proposal(). Solo tests: MIA_ALLOW_CURATOR_LEGACY_RUN=1"
            )
        stats = {"analyzed": 0, "consolidated": 0, "pruned": 0, "errors": 0}
        try:
            stats["analyzed"] = len(await self.load_playbooks(tenant_id))
        except Exception:
            stats["errors"] += 1
            logger.exception("load_playbooks falló (tenant %s)", tenant_id)
        try:
            candidates = await self.find_candidates(tenant_id)
            stats["consolidated"] = await self.consolidate(tenant_id, candidates)
        except Exception:
            stats["errors"] += 1
            logger.exception("consolidate falló (tenant %s)", tenant_id)
        try:
            stats["pruned"] = await self.prune(tenant_id)
        except Exception:
            stats["errors"] += 1
            logger.exception("prune falló (tenant %s)", tenant_id)
        return stats

    async def load_playbooks(self, tenant_id: str) -> list[dict]:
        """Playbooks ACTIVOS del tenant (list[dict])."""
        async with pool.tenant_connection(tenant_id) as conn:
            async with conn.cursor(row_factory=dict_row) as cur:
                await cur.execute(
                    "SELECT id, title, summary, applies_when, content, status, usage_count, "
                    "last_used_at FROM playbooks WHERE status = 'active' ORDER BY created_at")
                return await cur.fetchall()

    async def find_candidates(self, tenant_id: str,
                              threshold: float = SIMILARITY_THRESHOLD) -> list[tuple]:
        """Pares de playbooks activos con similitud coseno > threshold. Usa el operador `<=>`
        de pgvector (distancia coseno): `1 - (a.embedding <=> b.embedding)` = similitud.
        Devuelve [(id_a, id_b, score)] con id_a < id_b (sin duplicar pares ni auto-pares)."""
        # H.6: los playbooks `protected` (semilla/core) quedan fuera de la consolidación.
        sql = (
            "SELECT a.id, b.id, 1 - (a.embedding <=> b.embedding) AS score "
            "FROM playbooks a JOIN playbooks b ON a.id < b.id "
            "WHERE a.status = 'active' AND b.status = 'active' "
            "  AND NOT a.protected AND NOT b.protected "
            "  AND a.embedding IS NOT NULL AND b.embedding IS NOT NULL "
            "  AND 1 - (a.embedding <=> b.embedding) > %(thr)s "
            "ORDER BY score DESC"
        )
        async with pool.tenant_connection(tenant_id) as conn:
            rows = await (await conn.execute(sql, {"thr": threshold})).fetchall()
        return [(str(r[0]), str(r[1]), float(r[2])) for r in rows]

    async def consolidate(self, tenant_id: str, candidates: list[tuple]) -> int:
        """Por cada par candidato: fusiona con el LLM en un playbook nuevo (status active) y
        archiva los dos originales. Idempotente: si alguno del par ya no está activo (p. ej.
        ya se consolidó), se salta. Devuelve el número de consolidaciones."""
        done = 0
        for a_id, b_id, _score in candidates:
            async with pool.tenant_connection(tenant_id) as conn:
                async with conn.cursor(row_factory=dict_row) as cur:
                    await cur.execute(
                        "SELECT id, title, summary, applies_when, content, status "
                        "FROM playbooks WHERE id = ANY(%s::uuid[])", ([a_id, b_id],))
                    rows = {str(r["id"]): r for r in await cur.fetchall()}
                a, b = rows.get(a_id), rows.get(b_id)
                if not a or not b or a["status"] != "active" or b["status"] != "active":
                    continue   # ya consolidado o ausente → idempotente

                fused = await asyncio.to_thread(self._fuse, a, b)
                new_title = f"Consolidado: {a['title']} + {b['title']}"[:200]
                new_summary = f"Fusión de '{a['title']}' y '{b['title']}'."[:1000]
                new_applies = f"{a['applies_when']} | {b['applies_when']}"
                vec = await asyncio.to_thread(
                    lambda: embeddings.embed_texts([f"{new_summary}\n{new_applies}"])[0])

                await conn.execute(
                    "INSERT INTO playbooks "
                    "  (tenant_id, title, summary, applies_when, content, embedding, status, metadata) "
                    "VALUES (%s::uuid, %s, %s, %s, %s, %s, 'active', %s) "
                    "ON CONFLICT (tenant_id, title) DO NOTHING",
                    (tenant_id, new_title, new_summary, new_applies, fused, vec,
                     _json_meta(a_id, b_id, a, b)),
                )
                await conn.execute(
                    "UPDATE playbooks SET status = 'archived', updated_at = now() "
                    "WHERE id = ANY(%s::uuid[])", ([a_id, b_id],))
            done += 1
        return done

    async def prune(self, tenant_id: str, days: int = PRUNE_DAYS) -> int:
        """Archiva los playbooks activos cuyo `last_used_at` es anterior a `days` días.
        Los que nunca se usaron (last_used_at NULL) NO se podan. Devuelve cuántos archivó."""
        async with pool.tenant_connection(tenant_id) as conn:
            cur = await conn.execute(
                "UPDATE playbooks SET status = 'archived', updated_at = now() "
                "WHERE status = 'active' AND NOT protected AND last_used_at IS NOT NULL "
                "AND last_used_at < now() - (%s * interval '1 day')", (days,))
            return cur.rowcount

    # ── dry-run → HITL (Tarea H.2, cierra Riesgo #19) ─────────────────────────
    @staticmethod
    async def _read_active_state(conn) -> list[dict]:
        """Lee los playbooks ACTIVOS usando una conexión dada (para leer dentro de una
        transacción existente y mantener la validación de hash consistente con la ejecución)."""
        async with conn.cursor(row_factory=dict_row) as cur:
            await cur.execute(
                "SELECT id::text, title, summary, applies_when, content, status "
                "FROM playbooks WHERE status = 'active' ORDER BY id")
            return await cur.fetchall()

    async def _snapshot_state(self, tenant_id: str) -> list[dict]:
        """Estado de los playbooks ACTIVOS (para snapshot/rollback y hash). Sin embedding."""
        async with pool.tenant_connection(tenant_id) as conn:
            return await self._read_active_state(conn)

    @staticmethod
    def _snapshot_hash(state: list[dict]) -> str:
        """Hash sha256 estable del estado (id+status+content). Detecta drift antes de aplicar."""
        h = hashlib.sha256()
        for row in sorted(state, key=lambda r: str(r["id"])):
            h.update(f"{row['id']}|{row['status']}|{row.get('content', '')}\n".encode("utf-8"))
        return h.hexdigest()

    async def _prune_candidates(self, tenant_id: str, days: int = PRUNE_DAYS) -> list[dict]:
        """Playbooks activos sin uso en `days` días (candidatos a poda; NO los muta)."""
        async with pool.tenant_connection(tenant_id) as conn:
            async with conn.cursor(row_factory=dict_row) as cur:
                await cur.execute(
                    "SELECT id::text, title FROM playbooks "
                    "WHERE status='active' AND NOT protected AND last_used_at IS NOT NULL "
                    "AND last_used_at < now() - (%s * interval '1 day') ORDER BY id", (days,))
                return await cur.fetchall()

    async def _playbook_facts(self, tenant_id: str) -> dict[str, dict]:
        """Fecha y procedencia de cada playbook activo — lo que el abogado necesita para decidir
        cuál de dos versiones enfrentadas es su criterio de HOY.

        Va aparte de `_snapshot_state` a propósito: ese estado se serializa a jsonb (`snapshot`)
        y alimenta el `snapshot_hash`; meterle `timestamptz` lo rompería. Aquí las fechas salen
        ya como texto ISO y no tocan el hash."""
        async with pool.tenant_connection(tenant_id) as conn:
            async with conn.cursor(row_factory=dict_row) as cur:
                await cur.execute(
                    "SELECT id::text, to_char(updated_at, 'YYYY-MM-DD') AS fecha, "
                    "       COALESCE(metadata->>'origin', 'manual') AS procedencia "
                    "FROM playbooks WHERE status = 'active'")
                return {r["id"]: r for r in await cur.fetchall()}

    async def _known_conflict_pairs(self, tenant_id: str) -> set[frozenset]:
        """Pares que YA se le mostraron al abogado como conflicto y siguen vivos: pendientes de
        decidir (`pending`) o decididos con "déjalas las dos" (`rejected`).

        Sirve a las dos mitades del riesgo: no volver a gastar el juez en un par ya juzgado, y
        —sobre todo— no volver a preguntar cada semana lo mismo. Un despacho que decidió
        conscientemente sostener dos criterios en tensión no puede ser interrogado por ello en
        cada corrida del cron: eso es el interrogatorio que hace que se deje de aprobar."""
        async with pool.tenant_connection(tenant_id) as conn:
            rows = await (await conn.execute(
                "SELECT conflict->'a'->>'id', conflict->'b'->>'id' FROM curator_proposals "
                "WHERE kind = 'conflict' AND status IN ('pending', 'rejected')")).fetchall()
        return {frozenset((r[0], r[1])) for r in rows if r[0] and r[1]}

    async def propose(self, tenant_id: str, *, threshold: float = SIMILARITY_THRESHOLD,
                      days: int = PRUNE_DAYS, persist: bool = True) -> CuratorProposal:
        """DRY-RUN: calcula fusiones y podas propuestas SIN ejecutarlas y (opcional) persiste
        la propuesta como `pending`. Es el único camino que el cron y el endpoint deben usar
        para NO mutar sin revisión humana (Riesgo #19).

        El coseno solo dice "estos dos se parecen". Quién decide si eso es un DUPLICADO
        (fusionable) o un CONFLICTO (jamás fusionable) es `_classify_pair`. Los conflictos NO
        entran en `proposed_merges`: salen de esta propuesta y se persisten como propuestas
        `kind='conflict'` propias."""
        state = await self._snapshot_state(tenant_id)
        by_id = {r["id"]: r for r in state}
        snapshot_hash = self._snapshot_hash(state)
        facts = await self._playbook_facts(tenant_id)
        known = await self._known_conflict_pairs(tenant_id)

        merges: list[dict] = []
        conflicts: list[dict] = []
        for a_id, b_id, score in await self.find_candidates(tenant_id, threshold):
            a, b = by_id.get(a_id), by_id.get(b_id)
            if not a or not b:
                continue
            if frozenset((a_id, b_id)) in known:
                continue   # ya está sobre la mesa del abogado (o él ya dijo "déjalas las dos")
            verdict = await self._classify_pair(a, b)
            if verdict is not None:
                conflicts.append(self._conflict_payload(a, b, facts, score, verdict))
                continue
            merges.append({
                "source_ids": [a_id, b_id],
                "target_title": f"Consolidado: {a['title']} + {b['title']}"[:200],
                "reason": f"Similitud coseno {score:.3f} > {threshold} entre "
                          f"'{a['title']}' y '{b['title']}'.",
            })

        deletions = [
            {"id": r["id"], "title": r["title"],
             "reason": f"Sin uso en más de {days} días."}
            for r in await self._prune_candidates(tenant_id, days)
        ]

        proposal = CuratorProposal(
            tenant_id=tenant_id, proposed_merges=merges, proposed_deletions=deletions,
            snapshot_hash=snapshot_hash, raised_conflicts=conflicts,
        )
        if persist:
            async with pool.tenant_connection(tenant_id) as conn:
                row = await (await conn.execute(
                    "INSERT INTO curator_proposals "
                    "  (tenant_id, kind, proposed_merges, proposed_deletions, snapshot_hash, stats) "
                    "VALUES (%s::uuid, 'cleanup', %s, %s, %s, %s) RETURNING id::text",
                    (tenant_id, Json(merges), Json(deletions), proposal.snapshot_hash,
                     Json({"merges": len(merges), "deletions": len(deletions)})),
                )).fetchone()
                proposal.id = row[0]
                # Una fila por conflicto: cada uno es una elección binaria independiente.
                for c in conflicts:
                    crow = await (await conn.execute(
                        "INSERT INTO curator_proposals "
                        "  (tenant_id, kind, conflict, snapshot_hash, stats) "
                        "VALUES (%s::uuid, 'conflict', %s, %s, %s) RETURNING id::text",
                        (tenant_id, Json(c), proposal.snapshot_hash, Json({"conflicts": 1})),
                    )).fetchone()
                    c["proposal_id"] = crow[0]
        return proposal

    async def list_proposals(self, tenant_id: str, status: str = "pending") -> list[dict]:
        """Propuestas del tenant en un estado (default 'pending'). Incluye las de limpieza
        (kind='cleanup') y los conflictos de criterio (kind='conflict')."""
        async with pool.tenant_connection(tenant_id) as conn:
            async with conn.cursor(row_factory=dict_row) as cur:
                await cur.execute(
                    "SELECT id::text, kind, proposed_merges, proposed_deletions, conflict, "
                    "resolution, snapshot_hash, status, stats, created_at, reviewed_at, "
                    "reviewed_by "
                    "FROM curator_proposals WHERE status = %s ORDER BY created_at DESC",
                    (status,))
                return await cur.fetchall()

    async def apply_proposal(self, tenant_id: str, proposal_id: str, *,
                             reviewed_by: str | None = None) -> dict:
        """Ejecuta una propuesta `pending` de forma ATÓMICA end-to-end (C.1):

        - Transición `pending → applying` con `SELECT … FOR UPDATE` en la MISMA transacción que
          la ejecución → previene doble-approve concurrente (el 2º approver ve status != pending → 409).
        - Valida el `snapshot_hash`: si el estado de playbooks cambió desde que se generó la
          propuesta → `drift` (409, "regenerar"), sin mutar nada.
        - Aplica fusiones+podas y marca `approved` + audita, TODO en una transacción (rollback
          automático si algo falla → marca `failed`)."""
        drift = False
        m_done = d_done = 0
        try:
            async with pool.tenant_connection(tenant_id) as conn:
                async with conn.cursor(row_factory=dict_row) as cur:
                    # Lock de fila + lectura de estado en la misma transacción (anti doble-approve).
                    await cur.execute(
                        "SELECT id::text, kind, proposed_merges, proposed_deletions, "
                        "snapshot_hash, status "
                        "FROM curator_proposals WHERE id = %s::uuid FOR UPDATE", (proposal_id,))
                    prop = await cur.fetchone()
                    if not prop:
                        return {"status": "not_found", "error": "propuesta inexistente"}
                    if prop["status"] != "pending":
                        return {"status": prop["status"], "error": "la propuesta no está pendiente"}
                    # Un conflicto de criterio NO se aprueba en bloque: se resuelve eligiendo una
                    # de las dos versiones (resolve_conflict). Aprobarlo aquí lo daría por
                    # zanjado sin que nadie eligiera nada — justo lo que este cambio impide.
                    if prop["kind"] == "conflict":
                        return {"status": prop["status"],
                                "error": "esta propuesta es un conflicto de criterio: "
                                         "hay que elegir una de las dos versiones"}
                    await conn.execute(
                        "UPDATE curator_proposals SET status='applying' WHERE id = %s::uuid",
                        (proposal_id,))

                    # Validación de snapshot_hash contra el estado ACTUAL (misma transacción).
                    state = await self._read_active_state(conn)
                    if self._snapshot_hash(state) != prop["snapshot_hash"]:
                        drift = True
                        raise _ProposalAbort()   # revierte la transacción (applying→pending)

                    # Snapshot del estado pre-ejecución (rollback/audit).
                    await conn.execute(
                        "UPDATE curator_proposals SET snapshot = %s WHERE id = %s::uuid",
                        (Json(state), proposal_id))

                    for merge in (prop["proposed_merges"] or []):
                        m_done += await self._execute_merge(conn, tenant_id, merge)
                    for deletion in (prop["proposed_deletions"] or []):
                        d_done += await self._execute_deletion(conn, deletion)

                    await conn.execute(
                        "UPDATE curator_proposals SET status='approved', reviewed_at=now(), "
                        "reviewed_by=%s WHERE id = %s::uuid", (reviewed_by, proposal_id))
                    await self._audit(conn, tenant_id, "curator_proposal_approved", proposal_id,
                                      {"merges": m_done, "deletions": d_done}, reviewed_by)
            return {"status": "approved", "merges_done": m_done, "deletions_done": d_done}

        except _ProposalAbort:
            pass  # drift: se maneja abajo (la transacción ya revirtió applying→pending)
        except Exception as e:
            logger.exception("apply_proposal falló (tenant %s, prop %s) → rollback", tenant_id, proposal_id)
            async with pool.tenant_connection(tenant_id) as conn:
                await conn.execute(
                    "UPDATE curator_proposals SET status='failed', reviewed_at=now(), reviewed_by=%s "
                    "WHERE id = %s::uuid AND status IN ('pending','applying')", (reviewed_by, proposal_id))
                await self._audit(conn, tenant_id, "curator_proposal_failed", proposal_id,
                                  {"error": str(e)}, reviewed_by)
            return {"status": "failed", "error": str(e), "merges_done": 0, "deletions_done": 0}

        # drift: el estado cambió desde que se generó la propuesta → 409, sin mutar. Se audita.
        async with pool.tenant_connection(tenant_id) as conn:
            await self._audit(conn, tenant_id, "curator_proposal_drift", proposal_id, {}, reviewed_by)
        return {"status": "drift",
                "error": "El estado cambió desde que se generó la propuesta; regenerar."}

    async def reject_proposal(self, tenant_id: str, proposal_id: str, *,
                              reviewed_by: str | None = None) -> dict:
        """Rechaza una propuesta `pending`: NO muta playbooks, solo marca rejected + audita."""
        async with pool.tenant_connection(tenant_id) as conn:
            async with conn.cursor(row_factory=dict_row) as cur:
                await cur.execute(
                    "SELECT status FROM curator_proposals WHERE id = %s::uuid", (proposal_id,))
                row = await cur.fetchone()
            if not row:
                return {"status": "not_found", "error": "propuesta inexistente"}
            if row["status"] != "pending":
                return {"status": row["status"], "error": "la propuesta no está pendiente"}
            await conn.execute(
                "UPDATE curator_proposals SET status='rejected', reviewed_at=now(), reviewed_by=%s "
                "WHERE id = %s::uuid", (reviewed_by, proposal_id))
            await self._audit(conn, tenant_id, "curator_proposal_rejected", proposal_id, {}, reviewed_by)
        return {"status": "rejected"}

    async def resolve_conflict(self, tenant_id: str, proposal_id: str, choice: str, *,
                               reviewed_by: str | None = None) -> dict:
        """Resuelve un conflicto de criterio: el abogado elige qué versión sostiene el despacho.

        `choice`:
          'a' | 'b' — la elegida queda como está; la otra se ARCHIVA (nunca se borra: sigue en el
                      historial y se puede reactivar). No se funde nada: la versión que sobrevive
                      es literalmente la que el abogado leyó y escogió.
          'none'    — las dos siguen vivas. La contradicción es un estado legítimo de la memoria:
                      un despacho puede sostener dos criterios en tensión y no deberle explicación
                      a nadie. Queda `rejected` para no volver a preguntar lo mismo cada semana.

        Mismas protecciones que `apply_proposal` (son el mismo peligro): `FOR UPDATE` en la misma
        transacción que la ejecución (dos aprobadores concurrentes → el 2º ve status != pending) y
        validación del `snapshot_hash` (si el conocimiento cambió desde que se detectó el
        conflicto, no se archiva nada → `drift`, hay que regenerar)."""
        if choice not in ("a", "b", "none"):
            return {"status": "invalid", "error": "hay que elegir una versión (o ninguna)"}
        drift = False
        archived = 0
        new_status = "pending"
        try:
            async with pool.tenant_connection(tenant_id) as conn:
                async with conn.cursor(row_factory=dict_row) as cur:
                    await cur.execute(
                        "SELECT id::text, kind, conflict, snapshot_hash, status "
                        "FROM curator_proposals WHERE id = %s::uuid FOR UPDATE", (proposal_id,))
                    prop = await cur.fetchone()
                    if not prop:
                        return {"status": "not_found", "error": "propuesta inexistente"}
                    if prop["kind"] != "conflict":
                        return {"status": prop["status"],
                                "error": "esta propuesta no es un conflicto de criterio"}
                    if prop["status"] != "pending":
                        return {"status": prop["status"], "error": "la propuesta no está pendiente"}
                    await conn.execute(
                        "UPDATE curator_proposals SET status='applying' WHERE id = %s::uuid",
                        (proposal_id,))

                    state = await self._read_active_state(conn)
                    if self._snapshot_hash(state) != prop["snapshot_hash"]:
                        drift = True
                        raise _ProposalAbort()   # revierte la transacción (applying→pending)

                    await conn.execute(
                        "UPDATE curator_proposals SET snapshot = %s WHERE id = %s::uuid",
                        (Json(state), proposal_id))

                    if choice in ("a", "b"):
                        loser = (prop["conflict"] or {}).get("b" if choice == "a" else "a", {})
                        loser_id = str(loser.get("id") or "")
                        if not loser_id:
                            raise RuntimeError("el conflicto no tiene las dos versiones")
                        c2 = await conn.execute(
                            "UPDATE playbooks SET status='archived', updated_at=now() "
                            "WHERE id = %s::uuid AND status='active' AND NOT protected",
                            (loser_id,))
                        archived = c2.rowcount

                    new_status = "approved" if choice in ("a", "b") else "rejected"
                    await conn.execute(
                        "UPDATE curator_proposals SET status=%s, resolution=%s, reviewed_at=now(), "
                        "reviewed_by=%s WHERE id = %s::uuid",
                        (new_status, choice, reviewed_by, proposal_id))
                    await self._audit(conn, tenant_id, "curator_conflict_resolved", proposal_id,
                                      {"choice": choice, "archived": archived}, reviewed_by)
            return {"status": new_status, "choice": choice, "archived": archived}

        except _ProposalAbort:
            pass
        except Exception as e:
            logger.exception("resolve_conflict falló (tenant %s, prop %s) → rollback",
                             tenant_id, proposal_id)
            async with pool.tenant_connection(tenant_id) as conn:
                await conn.execute(
                    "UPDATE curator_proposals SET status='failed', reviewed_at=now(), "
                    "reviewed_by=%s WHERE id = %s::uuid AND status IN ('pending','applying')",
                    (reviewed_by, proposal_id))
                await self._audit(conn, tenant_id, "curator_conflict_failed", proposal_id,
                                  {"error": str(e)}, reviewed_by)
            return {"status": "failed", "error": str(e), "archived": 0}

        async with pool.tenant_connection(tenant_id) as conn:
            await self._audit(conn, tenant_id, "curator_proposal_drift", proposal_id, {},
                              reviewed_by)
        return {"status": "drift",
                "error": "El estado cambió desde que se generó la propuesta; regenerar."}

    async def _execute_merge(self, conn, tenant_id: str, merge: dict) -> int:
        """Aplica UNA fusión propuesta (misma lógica que consolidate, desde la propuesta).
        Idempotente: si algún origen ya no está activo, se salta (devuelve 0)."""
        source_ids = [str(s) for s in merge.get("source_ids", [])]
        if len(source_ids) != 2:
            return 0
        async with conn.cursor(row_factory=dict_row) as cur:
            await cur.execute(
                "SELECT id::text, title, summary, applies_when, content, status, protected "
                "FROM playbooks WHERE id = ANY(%s::uuid[])", (source_ids,))
            rows = {r["id"]: r for r in await cur.fetchall()}
        a, b = rows.get(source_ids[0]), rows.get(source_ids[1])
        if not a or not b or a["status"] != "active" or b["status"] != "active":
            return 0
        # H.6: no se fusiona si algún origen está protegido (semilla/core). Defensa en profundidad:
        # find_candidates ya los excluye, pero una propuesta vieja podría referenciarlos.
        if a.get("protected") or b.get("protected"):
            logger.warning("curator._execute_merge: fusión omitida, origen protegido (%s / %s)",
                           source_ids[0], source_ids[1])
            return 0
        fused = await asyncio.to_thread(self._fuse, a, b)
        new_title = merge.get("target_title") or f"Consolidado: {a['title']} + {b['title']}"[:200]
        new_summary = f"Fusión de '{a['title']}' y '{b['title']}'."[:1000]
        new_applies = f"{a['applies_when']} | {b['applies_when']}"
        vec = await asyncio.to_thread(
            lambda: embeddings.embed_texts([f"{new_summary}\n{new_applies}"])[0])
        # C.1.3: si el título consolidado ya existe (p. ej. de una corrida previa) → DO UPDATE
        # (reactiva + actualiza contenido) en vez de DO NOTHING, para NO dejar al tenant sin un
        # playbook activo tras archivar los originales.
        await conn.execute(
            "INSERT INTO playbooks "
            "  (tenant_id, title, summary, applies_when, content, embedding, status, metadata) "
            "VALUES (%s::uuid, %s, %s, %s, %s, %s, 'active', %s) "
            "ON CONFLICT (tenant_id, title) DO UPDATE SET "
            "  summary = EXCLUDED.summary, applies_when = EXCLUDED.applies_when, "
            "  content = EXCLUDED.content, embedding = EXCLUDED.embedding, "
            "  status = 'active', updated_at = now()",
            (tenant_id, new_title, new_summary, new_applies, fused, vec,
             _json_meta(source_ids[0], source_ids[1], a, b)))
        await conn.execute(
            "UPDATE playbooks SET status='archived', updated_at=now() WHERE id = ANY(%s::uuid[])",
            (source_ids,))
        return 1

    @staticmethod
    async def _execute_deletion(conn, deletion: dict) -> int:
        """Archiva (nunca borra) un playbook propuesto para poda. Idempotente."""
        pid = str(deletion.get("id", ""))
        if not pid:
            return 0
        cur = await conn.execute(
            "UPDATE playbooks SET status='archived', updated_at=now() "
            "WHERE id = %s::uuid AND status='active' AND NOT protected", (pid,))
        return cur.rowcount

    @staticmethod
    async def _audit(conn, tenant_id: str, action: str, entity_id: str,
                     payload: dict, user_email: str | None) -> None:
        """Registro append-only en audit_logs (migración 011), DENTRO de la
        transacción del curador (atómico con la acción). Usa el sink compartido de
        CP-E1 (observability.audit)."""
        await audit.record_on_conn(
            conn, action, tenant_id=tenant_id, user_email=user_email,
            entity_type="curator_proposal", entity_id=entity_id, payload=payload)

    async def propose_all_tenants(self) -> dict:
        """Como `run_all_tenants` pero SOLO propone (dry-run + persistencia). Lo usa el cron
        semanal para cerrar el Riesgo #19: nada se muta sin que un abogado apruebe la propuesta."""
        out: dict[str, dict] = {}
        for tenant_id in self._list_tenant_ids():
            try:
                # CP2 (decisión #27): job de fondo sin request → fijar la política de
                # modelo DEL TENANT antes de llamar al LLM; se restaura al salir.
                async with llm.tenant_model_policy(tenant_id):
                    p = await self.propose(tenant_id)
                out[tenant_id] = {"proposal_id": p.id, "merges": len(p.proposed_merges),
                                  "deletions": len(p.proposed_deletions),
                                  "conflicts": len(p.raised_conflicts)}
            except Exception as e:
                out[tenant_id] = {"error": str(e)}
                logger.exception("curator.propose falló (tenant %s)", tenant_id)
        return out

    # ── todos los tenants (LEGACY, muta sin HITL) ─────────────────────────────
    async def _run_all_tenants_legacy(self) -> dict:
        """LEGACY: corre `_run_legacy` (mutación directa) para cada tenant. Reemplazado por
        `propose_all_tenants()` (el cron ya usa ese). Devuelve {tenant_id: stats}."""
        out: dict[str, dict] = {}
        for tenant_id in self._list_tenant_ids():
            try:
                async with llm.tenant_model_policy(tenant_id):  # CP2: política por tenant
                    out[tenant_id] = await self._run_legacy(tenant_id)
            except Exception as e:   # un tenant no debe tumbar a los demás
                out[tenant_id] = {"error": str(e)}
                logger.exception("curator._run_legacy falló (tenant %s)", tenant_id)
        return out

    def _list_tenant_ids(self) -> list[str]:
        """Ids de todos los tenants (operación de SISTEMA, cross-tenant → conexión admin;
        ver Riesgo #15). La curaduría por tenant sí pasa por RLS (tenant_connection)."""
        import psycopg

        pw = os.getenv("PG_PASSWORD", "")
        if not pw:
            logger.warning("PG_PASSWORD vacío: el Curator no puede enumerar tenants")
            return []
        kw = dict(host=os.getenv("PG_HOST", "127.0.0.1"), port=os.getenv("PG_PORT", "5432"),
                  dbname=os.getenv("PG_DB", "mia"), user="postgres", password=pw)
        with psycopg.connect(autocommit=True, **kw) as c:
            rows = c.execute("SELECT id FROM tenants").fetchall()
        return [str(r[0]) for r in rows]

    # ── juez de contradicción: ¿duplicado o conflicto? ────────────────────────
    async def _classify_pair(self, a: dict, b: dict) -> dict | None:
        """Segundo paso tras el coseno. Devuelve el veredicto del conflicto ({dice_a, dice_b,
        confianza}) SOLO si el juez está convencido de que los dos textos se contradicen; en
        cualquier otro caso devuelve None = DUPLICADO (fusionable, comportamiento de siempre).

        FAIL-SOFT: este método no propaga NADA. El juez es una llamada a un modelo dentro del
        cron semanal; si el modelo está caído, tarda, o devuelve basura, el Curator degrada al
        comportamiento de hoy (fusionar) y lo deja escrito en el log — nunca tumba su corrida.
        El coste de degradar es una propuesta de fusión que el abogado puede rechazar; el coste
        de reventar es que el despacho se quede sin curaduría."""
        try:
            raw = await asyncio.to_thread(self._judge, a, b)
        except Exception:
            logger.exception(
                "curator: el juez de contradicción falló (%s / %s) → se trata como duplicado "
                "(degradado al comportamiento previo)", a.get("id"), b.get("id"))
            return None
        if not raw:
            return None

        veredicto = str(raw.get("veredicto", "")).strip().lower()
        if veredicto not in _JUDGE_VERDICTS:
            logger.warning("curator: veredicto ilegible (%r) en %s / %s → duplicado",
                           raw.get("veredicto"), a.get("id"), b.get("id"))
            return None
        if veredicto != "contrarios":
            return None
        try:
            confianza = float(raw.get("confianza", 0.0))
        except (TypeError, ValueError):
            return None
        if confianza < CONFLICT_MIN_CONFIDENCE:
            # El juez se inclina pero no está convencido → duplicado. Ver CONFLICT_MIN_CONFIDENCE.
            logger.info("curator: posible contradicción descartada por confianza %.2f < %.2f "
                        "(%s / %s) → duplicado", confianza, CONFLICT_MIN_CONFIDENCE,
                        a.get("id"), b.get("id"))
            return None

        dice_a = str(raw.get("dice_a") or "").strip()[:300]
        dice_b = str(raw.get("dice_b") or "").strip()[:300]
        if not dice_a or not dice_b:
            # Sin las dos mitades no hay elección binaria que enseñar: no se interrumpe al
            # abogado con media pregunta.
            logger.warning("curator: contradicción sin las dos versiones explicadas (%s / %s) "
                           "→ duplicado", a.get("id"), b.get("id"))
            return None
        return {"dice_a": dice_a, "dice_b": dice_b, "confianza": confianza}

    @staticmethod
    def _judge(a: dict, b: dict) -> dict | None:
        """Llamada síncrona al juez (task auxiliar/barato). Devuelve el JSON parseado o None.

        AGNOSTICISMO (regla dura): el prompt no nombra ningún país, ordenamiento, código ni
        figura jurídica. Pregunta por la estructura lógica de dos instrucciones — obligar vs
        prohibir, afirmar vs negar, dos valores distintos para lo mismo — que es idéntica en
        cualquier jurisdicción. Un detector que reconociera contradicciones por léxico de un
        país solo funcionaría en ese país."""
        messages = [
            {"role": "system", "content": (
                "Eres un comparador de reglas de trabajo. Recibes DOS reglas, A y B, que un "
                "sistema detectó como muy parecidas. Tu ÚNICA tarea es decir si dicen LO MISMO "
                "o si se CONTRADICEN. No juzgues cuál es mejor ni entres en el fondo del asunto.\n"
                "Veredictos posibles:\n"
                "- \"iguales\": dicen lo mismo con otras palabras, o una es un detalle o un caso "
                "particular de la otra. Quien las juntara no perdería ninguna instrucción.\n"
                "- \"contrarios\": aplicadas al MISMO supuesto ordenan cosas incompatibles: una "
                "obliga lo que la otra prohíbe, una afirma lo que la otra niega, o fijan valores, "
                "plazos o umbrales distintos para la misma cosa. Quien siguiera las dos a la vez "
                "no sabría qué hacer.\n"
                "- \"no_se\": no tienes certeza, hablan de supuestos distintos, o el texto no "
                "alcanza para saberlo.\n"
                "REGLA CRÍTICA: ante CUALQUIER duda responde \"no_se\". Marcar como contrarias "
                "dos reglas que en realidad dicen lo mismo es un error CARO; no detectar una "
                "contradicción es un error barato. Sé exigente antes de decir \"contrarios\".\n"
                "Responde ÚNICAMENTE un objeto JSON, sin texto alrededor:\n"
                "{\"veredicto\": \"iguales|contrarios|no_se\", \"confianza\": 0.0-1.0, "
                "\"dice_a\": \"lo que ordena A, máximo 25 palabras\", "
                "\"dice_b\": \"lo que ordena B, máximo 25 palabras\"}\n"
                "\"confianza\" es cuán seguro estás de tu veredicto. \"dice_a\" y \"dice_b\" "
                "describen cada regla POR SEPARADO: jamás las combines en una sola frase.")},
            {"role": "user", "content": (
                f"REGLA A — {a.get('title', '')}\n"
                f"Cuándo aplica: {a.get('applies_when', '')}\n"
                f"{str(a.get('content') or '')[:_JUDGE_MAX_CHARS]}\n\n"
                f"REGLA B — {b.get('title', '')}\n"
                f"Cuándo aplica: {b.get('applies_when', '')}\n"
                f"{str(b.get('content') or '')[:_JUDGE_MAX_CHARS]}")},
        ]
        resp = llm.call_llm(messages, task=_JUDGE_TASK)
        text = (resp.choices[0].message.content or "").strip()
        return _parse_judge_json(text)

    @staticmethod
    def _conflict_payload(a: dict, b: dict, facts: dict[str, dict], score: float,
                          verdict: dict) -> dict:
        """Payload de un conflicto: las DOS versiones vivas, cada una con su fecha y su
        procedencia. Nunca un texto mezclado — el abogado elige entre A y B, no entre una
        fusión y nada."""
        def side(pb: dict, dice: str) -> dict:
            f = facts.get(pb["id"], {})
            return {
                "id": pb["id"],
                "title": pb.get("title", ""),
                "summary": pb.get("summary", ""),
                "applies_when": pb.get("applies_when", ""),
                "extracto": str(pb.get("content") or "")[:1200],
                "fecha": f.get("fecha") or "",
                "procedencia": f.get("procedencia") or "manual",
                "dice": dice,
            }

        return {
            "a": side(a, verdict["dice_a"]),
            "b": side(b, verdict["dice_b"]),
            "score": round(float(score), 3),
            "confianza": round(float(verdict["confianza"]), 2),
        }

    # ── fusión con LLM ────────────────────────────────────────────────────────
    @staticmethod
    def _fuse(a: dict, b: dict) -> str:
        """Pide al LLM fuerte (task=curator → claude-sonnet) un playbook fusionado mejorado."""
        messages = [
            {"role": "system", "content": (
                "Eres un curador de playbooks jurídicos. Recibes DOS playbooks redundantes o "
                "solapados y devuelves UNO solo, mejorado: combina lo mejor de ambos, elimina "
                "repeticiones, conserva todo matiz jurídico relevante y cualquier marca "
                "[VERIFICAR]. Devuelve solo el cuerpo del playbook consolidado.")},
            {"role": "user", "content": (
                f"PLAYBOOK A — {a['title']}\n{a['content']}\n\n"
                f"PLAYBOOK B — {b['title']}\n{b['content']}")},
        ]
        resp = llm.call_llm(messages, task="curator")
        return resp.choices[0].message.content or ""


_JSON_OBJ = re.compile(r"\{.*\}", re.DOTALL)


def _parse_judge_json(text: str) -> dict | None:
    """Extrae el objeto JSON del veredicto. Tolera ```json … ``` y prosa alrededor (los modelos
    pequeños de la política 'soberano' la añaden). Devuelve None si no hay JSON legible — el
    llamador lo trata como duplicado (fail-soft)."""
    if not text:
        return None
    try:
        obj = json.loads(text)
        if isinstance(obj, dict):
            return obj
    except (ValueError, TypeError):
        pass
    m = _JSON_OBJ.search(text)
    if not m:
        return None
    try:
        obj = json.loads(m.group(0))
    except (ValueError, TypeError):
        return None
    return obj if isinstance(obj, dict) else None


def _json_meta(a_id: str, b_id: str, a: dict, b: dict):
    from psycopg.types.json import Json
    return Json({"consolidated_from_ids": [a_id, b_id],
                 "consolidated_from_titles": [a["title"], b["title"]]})
