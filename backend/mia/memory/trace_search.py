"""Mia · memory.trace_search — búsqueda FTS de trazas por Postgres, SIN LLM (Tarea H.3).

Hermes v0.17.0 hizo `session_search` ~4.500× más rápido eliminando la ruta LLM (que resumía/
rankeaba con un modelo) y usando un índice FTS con ranking BM25. El equivalente en Mia (store =
Postgres) es la tabla `traces` (migración 013) con `tsvector` + índice GIN y ranking `ts_rank_cd`.

Camino caliente 100% SQL: `websearch_to_tsquery('spanish', q)` contra `content_tsv` (columna
generada), `ORDER BY ts_rank_cd(...) DESC`. NINGUNA llamada LLM. Todo bajo `tenant_connection`
(RLS por-tenant): un despacho jamás ve las trazas de otro.
"""
from __future__ import annotations

import logging
import re
from typing import Any

import psycopg
from psycopg.rows import dict_row

from ..db import pool

logger = logging.getLogger("mia.memory.trace_search")

_TS_CONFIG = "spanish"

# Al menos un carácter alfanumérico (incl. acentos): una consulta de solo operadores/puntuación
# (":", "&|!", "()") no tiene términos buscables → se rechaza como malformada (C.3).
_MEANINGFUL = re.compile(r"[0-9A-Za-zÀ-ÿ]")


class TraceSearchError(ValueError):
    """Consulta de búsqueda malformada. El endpoint la mapea a 400 Bad Request (no 500)."""


async def index_trace(
    tenant_id: str,
    *,
    matter_id: str | None,
    input: str,
    output: str,
    model: str | None = None,
    hitl_outcome: str | None = None,
    activated_playbooks: list | None = None,
    retrieved_doc_ids: list | None = None,
    trace_ts: str | None = None,
) -> str | None:
    """Indexa una traza en la tabla `traces` (RLS). Devuelve el id, o None si falla.

    Dual-write: el JSONL (SFT) lo sigue escribiendo `TraceCapture`; esta fila es el índice
    consultable. `content_tsv` se genera sola en el INSERT (columna generada)."""
    ap = [str(x) for x in (activated_playbooks or [])]
    rd = [str(x) for x in (retrieved_doc_ids or [])]
    async with pool.tenant_connection(tenant_id) as conn:
        row = await (await conn.execute(
            "INSERT INTO traces "
            "  (tenant_id, matter_id, input, output, model, hitl_outcome, "
            "   activated_playbooks, retrieved_doc_ids, trace_ts) "
            "VALUES (%s::uuid, %s, %s, %s, %s, %s, %s, %s, %s) RETURNING id::text",
            (tenant_id, matter_id, input, output, model, hitl_outcome, ap, rd, trace_ts),
        )).fetchone()
    return row[0] if row else None


async def search_traces(
    tenant_id: str,
    query: str,
    *,
    limit: int = 20,
    matter_id: str | None = None,
    outcome: str | None = None,
    activated_playbook: str | None = None,
    date_from: Any = None,
    date_to: Any = None,
) -> list[dict]:
    """Busca trazas del tenant por keyword (FTS) con ranking BM-like. SIN LLM.

    `query` vacío devuelve []. Filtros opcionales: matter_id, outcome (hitl_outcome),
    activated_playbook (id contenido en el array), rango temporal [date_from, date_to].
    """
    q = (query or "").strip()
    if not q:
        return []
    if not _MEANINGFUL.search(q):
        raise TraceSearchError("La búsqueda no contiene términos válidos.")

    where = ["content_tsv @@ websearch_to_tsquery(%(cfg)s, %(q)s)"]
    params: dict[str, Any] = {"cfg": _TS_CONFIG, "q": q, "limit": max(1, min(int(limit), 200))}
    if matter_id:
        where.append("matter_id = %(matter_id)s")
        params["matter_id"] = matter_id
    if outcome:
        where.append("hitl_outcome = %(outcome)s")
        params["outcome"] = outcome
    if activated_playbook:
        where.append("%(pb)s = ANY(activated_playbooks)")
        params["pb"] = str(activated_playbook)
    if date_from is not None:
        where.append("trace_ts >= %(date_from)s")
        params["date_from"] = date_from
    if date_to is not None:
        where.append("trace_ts <= %(date_to)s")
        params["date_to"] = date_to

    sql = (
        "SELECT id::text, matter_id, input, output, model, hitl_outcome, "
        "       activated_playbooks, retrieved_doc_ids, trace_ts, "
        "       ts_rank_cd(content_tsv, websearch_to_tsquery(%(cfg)s, %(q)s)) AS rank "
        "FROM traces WHERE " + " AND ".join(where) +
        " ORDER BY rank DESC, trace_ts DESC NULLS LAST LIMIT %(limit)s"
    )
    try:
        async with pool.tenant_connection(tenant_id) as conn:
            async with conn.cursor(row_factory=dict_row) as cur:
                await cur.execute(sql, params)
                return await cur.fetchall()
    except (psycopg.errors.SyntaxError, psycopg.errors.DataException) as e:
        # websearch_to_tsquery es tolerante, pero si el motor FTS rechaza la consulta →
        # 400 (consulta del usuario), no 500 (error del backend).
        raise TraceSearchError("Consulta de búsqueda inválida.") from e
