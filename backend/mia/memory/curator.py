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
import logging
import os

from psycopg.rows import dict_row

from .. import embeddings
from ..agent import llm
from ..db import pool

logger = logging.getLogger("mia.curator")

SIMILARITY_THRESHOLD = 0.85   # similitud coseno por encima de la cual dos playbooks se fusionan
PRUNE_DAYS = 90               # playbooks sin uso en N días se archivan


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
