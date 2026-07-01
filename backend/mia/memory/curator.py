"""Mia · memory.curator — mantenimiento semántico de playbooks (Módulo 3b · decisión #18).

Tarea CRON semanal (domingos 2am, registrada como `curator_weekly` en `cron/scheduler.py`).
Por cada tenant: detecta playbooks redundantes (similitud coseno > 0.85 vía el operador `<=>`
de pgvector sobre el embedding del summary+applies_when), los **consolida** con un LLM fuerte
(`call_llm(task="curator")` → claude-sonnet) en un playbook mejorado, y **poda** los playbooks
sin uso en 90 días (`last_used_at`). Todo bajo `pool.tenant_connection` (RLS).

El LLM y los embeddings son síncronos; se invocan vía `asyncio.to_thread` para no bloquear el
event loop (mismo patrón que `agents/graph.py`).
"""
from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import os
from dataclasses import dataclass, field

from psycopg.rows import dict_row
from psycopg.types.json import Json

from .. import embeddings
from ..agent import llm
from ..db import pool

logger = logging.getLogger("mia.curator")

SIMILARITY_THRESHOLD = 0.85   # similitud coseno por encima de la cual dos playbooks se fusionan
PRUNE_DAYS = 90               # playbooks sin uso en N días se archivan


class _ProposalAbort(Exception):
    """Sentinela interno: aborta la transacción de apply_proposal por drift de estado (C.1)."""


@dataclass
class CuratorProposal:
    """Propuesta de curación (dry-run, patrón Hermes v0.17.0). NO muta nada por sí misma.

    `proposed_merges`   : [{"source_ids": [a, b], "target_title": str, "reason": str}]
    `proposed_deletions`: [{"id": str, "title": str, "reason": str}]
    `snapshot_hash`     : hash del estado de playbooks activos al momento de proponer.
    """

    tenant_id: str
    proposed_merges: list[dict] = field(default_factory=list)
    proposed_deletions: list[dict] = field(default_factory=list)
    snapshot_hash: str = ""
    id: str | None = None                 # se rellena al persistir
    status: str = "pending"

    def is_empty(self) -> bool:
        return not self.proposed_merges and not self.proposed_deletions

    def to_public(self) -> dict:
        """Dict amigable para el endpoint (sin jerga técnica hacia el usuario, §G)."""
        return {
            "id": self.id,
            "status": self.status,
            "merges": self.proposed_merges,
            "deletions": self.proposed_deletions,
            "snapshot_hash": self.snapshot_hash,
        }


class Curator:
    """Curador de playbooks. Sin estado: cada método toma una conexión del pool."""

    # ── entry point por tenant ────────────────────────────────────────────────
    async def run(self, tenant_id: str) -> dict:
        """Ciclo completo para un tenant. Devuelve {analyzed, consolidated, pruned, errors}."""
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
        sql = (
            "SELECT a.id, b.id, 1 - (a.embedding <=> b.embedding) AS score "
            "FROM playbooks a JOIN playbooks b ON a.id < b.id "
            "WHERE a.status = 'active' AND b.status = 'active' "
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
                "WHERE status = 'active' AND last_used_at IS NOT NULL "
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
                    "WHERE status='active' AND last_used_at IS NOT NULL "
                    "AND last_used_at < now() - (%s * interval '1 day') ORDER BY id", (days,))
                return await cur.fetchall()

    async def propose(self, tenant_id: str, *, threshold: float = SIMILARITY_THRESHOLD,
                      days: int = PRUNE_DAYS, persist: bool = True) -> CuratorProposal:
        """DRY-RUN: calcula fusiones y podas propuestas SIN ejecutarlas y (opcional) persiste
        la propuesta como `pending`. Es el único camino que el cron y el endpoint deben usar
        para NO mutar sin revisión humana (Riesgo #19)."""
        state = await self._snapshot_state(tenant_id)
        by_id = {r["id"]: r for r in state}

        merges: list[dict] = []
        for a_id, b_id, score in await self.find_candidates(tenant_id, threshold):
            a, b = by_id.get(a_id), by_id.get(b_id)
            if not a or not b:
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
            snapshot_hash=self._snapshot_hash(state),
        )
        if persist:
            async with pool.tenant_connection(tenant_id) as conn:
                row = await (await conn.execute(
                    "INSERT INTO curator_proposals "
                    "  (tenant_id, proposed_merges, proposed_deletions, snapshot_hash, stats) "
                    "VALUES (%s::uuid, %s, %s, %s, %s) RETURNING id::text",
                    (tenant_id, Json(merges), Json(deletions), proposal.snapshot_hash,
                     Json({"merges": len(merges), "deletions": len(deletions)})),
                )).fetchone()
                proposal.id = row[0]
        return proposal

    async def list_proposals(self, tenant_id: str, status: str = "pending") -> list[dict]:
        """Propuestas del tenant en un estado (default 'pending')."""
        async with pool.tenant_connection(tenant_id) as conn:
            async with conn.cursor(row_factory=dict_row) as cur:
                await cur.execute(
                    "SELECT id::text, proposed_merges, proposed_deletions, snapshot_hash, "
                    "status, stats, created_at, reviewed_at, reviewed_by "
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
                        "SELECT id::text, proposed_merges, proposed_deletions, snapshot_hash, status "
                        "FROM curator_proposals WHERE id = %s::uuid FOR UPDATE", (proposal_id,))
                    prop = await cur.fetchone()
                    if not prop:
                        return {"status": "not_found", "error": "propuesta inexistente"}
                    if prop["status"] != "pending":
                        return {"status": prop["status"], "error": "la propuesta no está pendiente"}
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

    async def _execute_merge(self, conn, tenant_id: str, merge: dict) -> int:
        """Aplica UNA fusión propuesta (misma lógica que consolidate, desde la propuesta).
        Idempotente: si algún origen ya no está activo, se salta (devuelve 0)."""
        source_ids = [str(s) for s in merge.get("source_ids", [])]
        if len(source_ids) != 2:
            return 0
        async with conn.cursor(row_factory=dict_row) as cur:
            await cur.execute(
                "SELECT id::text, title, summary, applies_when, content, status "
                "FROM playbooks WHERE id = ANY(%s::uuid[])", (source_ids,))
            rows = {r["id"]: r for r in await cur.fetchall()}
        a, b = rows.get(source_ids[0]), rows.get(source_ids[1])
        if not a or not b or a["status"] != "active" or b["status"] != "active":
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
            "WHERE id = %s::uuid AND status='active'", (pid,))
        return cur.rowcount

    @staticmethod
    async def _audit(conn, tenant_id: str, action: str, entity_id: str,
                     payload: dict, user_email: str | None) -> None:
        """Registro append-only en audit_logs (migración 011)."""
        await conn.execute(
            "INSERT INTO audit_logs (tenant_id, user_email, action, entity_type, entity_id, payload) "
            "VALUES (%s::uuid, %s, %s, 'curator_proposal', %s, %s)",
            (tenant_id, user_email, action, entity_id, Json(payload)))

    async def propose_all_tenants(self) -> dict:
        """Como `run_all_tenants` pero SOLO propone (dry-run + persistencia). Lo usa el cron
        semanal para cerrar el Riesgo #19: nada se muta sin que un abogado apruebe la propuesta."""
        out: dict[str, dict] = {}
        for tenant_id in self._list_tenant_ids():
            try:
                p = await self.propose(tenant_id)
                out[tenant_id] = {"proposal_id": p.id, "merges": len(p.proposed_merges),
                                  "deletions": len(p.proposed_deletions)}
            except Exception as e:
                out[tenant_id] = {"error": str(e)}
                logger.exception("curator.propose falló (tenant %s)", tenant_id)
        return out

    # ── todos los tenants (cron) ──────────────────────────────────────────────
    async def run_all_tenants(self) -> dict:
        """Corre `run` para cada tenant. Devuelve {tenant_id: stats}."""
        out: dict[str, dict] = {}
        for tenant_id in self._list_tenant_ids():
            try:
                out[tenant_id] = await self.run(tenant_id)
            except Exception as e:   # un tenant no debe tumbar a los demás
                out[tenant_id] = {"error": str(e)}
                logger.exception("curator.run falló (tenant %s)", tenant_id)
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


def _json_meta(a_id: str, b_id: str, a: dict, b: dict):
    from psycopg.types.json import Json
    return Json({"consolidated_from_ids": [a_id, b_id],
                 "consolidated_from_titles": [a["title"], b["title"]]})
