"""Mia · rag.sat_graph — SAT-Graph: corpus jurídico COMPARTIDO en Postgres puro (Módulo 3a).

Corpus compartido entre tenants (normas, relaciones tipadas, jurisprudencia). NO es dato
por-tenant (decisión #16): las normas y sentencias son públicas. Por eso `SATGraph` usa una
conexión del pool SIN contexto de tenant (`pool.connection()`); las tablas SAT tienen RLS con
política abierta `USING(true)`. Las tablas por-tenant siguen fail-closed sin GUC.

FTS en español con `websearch_to_tsquery('spanish', …)` + ranking `ts_rank` — mismo patrón
que `agents/retrieval.py` (websearch tolera texto libre de varias palabras; `to_tsquery`
crudo reventaría). Los pesos del `fts_vector` (A/B/C/D) los pone el trigger en la DB.

Vigencia temporal: `get_norm_at_date` resuelve qué norma estaba vigente en una fecha
(`effective_date <= fecha < expiry_date`). `get_norm_chain` sigue `modifica_a`/`deroga_a`
recursivamente (CTE recursivo con guardia de ciclos).
"""
from __future__ import annotations

from datetime import date
from typing import Any, Optional
from uuid import UUID

from psycopg.rows import dict_row
from psycopg.types.json import Json

from ..db import pool

# Campos devueltos en los dicts. Se excluye `fts_vector` a propósito (es ruido para el
# consumidor; el tsvector solo sirve para el índice/búsqueda en la DB).
_NORM_FIELDS = (
    "id", "norm_type", "norm_number", "issuing_body", "title", "summary", "full_text",
    "effective_date", "expiry_date", "jurisdiction", "practice_areas", "metadata",
    "created_at", "updated_at",
)
_JURIS_FIELDS = (
    "id", "norm_id", "jurisdiction", "court", "sala", "decision_number", "radicado",
    "magistrado_ponente", "decision_date", "topic", "ratio_decidendi", "obiter_dicta",
    "keywords", "metadata", "created_at",
)


def _cols(fields: tuple[str, ...], prefix: str = "") -> str:
    p = f"{prefix}." if prefix else ""
    return ", ".join(p + f for f in fields)


class SATGraph:
    """Acceso al corpus jurídico compartido. Sin estado: cada método toma una conexión del
    pool (sin GUC de tenant). Los `add_*` escriben (curaduría del corpus, restringida a
    mia_app por GRANT)."""

    # ── consultas temporales ────────────────────────────────────────────────
    async def get_norm_at_date(self, norm_id: Any, fecha: Any) -> Optional[dict]:
        """La norma SI estaba vigente en `fecha` (effective_date <= fecha < expiry_date),
        o None. `fecha` admite date o 'YYYY-MM-DD'."""
        sql = (f"SELECT {_cols(_NORM_FIELDS)} FROM legal_norms "
               "WHERE id = %(id)s::uuid "
               "AND effective_date <= %(f)s::date "
               "AND (expiry_date IS NULL OR expiry_date > %(f)s::date)")
        async with pool.connection() as conn:
            async with conn.cursor(row_factory=dict_row) as cur:
                await cur.execute(sql, {"id": str(norm_id), "f": fecha})
                return await cur.fetchone()

    # ── relaciones ──────────────────────────────────────────────────────────
    async def get_related_norms(self, norm_id: Any,
                                relation_type: Optional[str] = None, *,
                                jurisdictions: Optional[list[str]] = None) -> list[dict]:
        """Normas a las que `norm_id` apunta (aristas salientes). Cada dict es la norma
        destino + `relation_type`/`relation_effective_date`/`relation_notes`. Si
        `relation_type` es None, devuelve todas. `jurisdictions` (opcional) acota las normas
        destino a esas jurisdicciones (None = sin filtro, comportamiento previo)."""
        sql = (f"SELECT {_cols(_NORM_FIELDS, 'n')}, "
               "r.relation_type AS relation_type, "
               "r.effective_date AS relation_effective_date, "
               "r.notes AS relation_notes "
               "FROM norm_relations r JOIN legal_norms n ON n.id = r.target_norm_id "
               "WHERE r.source_norm_id = %(id)s::uuid "
               "AND (%(rt)s::text IS NULL OR r.relation_type = %(rt)s) "
               "AND (%(jurs)s::text[] IS NULL OR n.jurisdiction = ANY(%(jurs)s)) "
               "ORDER BY r.created_at")
        params = {"id": str(norm_id), "rt": relation_type,
                  "jurs": list(jurisdictions) if jurisdictions else None}
        async with pool.connection() as conn:
            async with conn.cursor(row_factory=dict_row) as cur:
                await cur.execute(sql, params)
                return await cur.fetchall()

    async def get_norm_chain(self, norm_id: Any, *,
                             jurisdictions: Optional[list[str]] = None) -> list[dict]:
        """Cadena de modificaciones desde `norm_id`: sigue `modifica_a`/`deroga_a`
        recursivamente (aristas salientes). Devuelve [norma_raíz, ...descendientes] con
        `depth` (0 = la raíz). Guardia de ciclos por camino visitado. Una hoja devuelve
        solo la raíz. `jurisdictions` (opcional) acota los descendientes (None = sin filtro)."""
        sql = (
            "WITH RECURSIVE chain AS ("
            f"  SELECT {_cols(_NORM_FIELDS, 'n')}, 0 AS depth, ARRAY[n.id] AS visited "
            "   FROM legal_norms n WHERE n.id = %(id)s::uuid "
            "  UNION ALL "
            f"  SELECT {_cols(_NORM_FIELDS, 'n')}, c.depth + 1, c.visited || n.id "
            "   FROM chain c "
            "   JOIN norm_relations r ON r.source_norm_id = c.id "
            "        AND r.relation_type IN ('modifica_a','deroga_a') "
            "   JOIN legal_norms n ON n.id = r.target_norm_id "
            "   WHERE NOT (n.id = ANY(c.visited)) "
            "     AND (%(jurs)s::text[] IS NULL OR n.jurisdiction = ANY(%(jurs)s)) "
            ") "
            f"SELECT {_cols(_NORM_FIELDS)}, depth FROM chain ORDER BY depth"
        )
        params = {"id": str(norm_id), "jurs": list(jurisdictions) if jurisdictions else None}
        async with pool.connection() as conn:
            async with conn.cursor(row_factory=dict_row) as cur:
                await cur.execute(sql, params)
                return await cur.fetchall()

    # ── búsqueda FTS (español) · ACOTADA por jurisdicción (Decisión #25) ──────
    async def search_norms(self, query_text: str, limit: int = 10, *,
                           jurisdictions: Optional[list[str]] = None,
                           admin: bool = False) -> list[dict]:
        """FTS sobre legal_norms (config 'spanish'), ordenado por ts_rank, ACOTADO a las
        `jurisdictions` dadas. Sin `jurisdictions` exige `admin=True` (curaduría): una
        búsqueda sin acotar devolvería el corpus de TODOS los países como autoridad → fuga
        cross-jurisdicción (Decisión #25)."""
        if not jurisdictions and not admin:
            raise ValueError("search_norms requiere jurisdictions (o admin=True para curaduría)")
        jur_clause = "AND jurisdiction = ANY(%(jurs)s) " if jurisdictions else ""
        sql = (f"SELECT {_cols(_NORM_FIELDS)}, ts_rank(fts_vector, q) AS rank "
               "FROM legal_norms, websearch_to_tsquery('spanish', %(q)s) q "
               "WHERE fts_vector @@ q " + jur_clause +
               "ORDER BY rank DESC, effective_date DESC LIMIT %(lim)s")
        params: dict[str, Any] = {"q": query_text or "", "lim": limit}
        if jurisdictions:
            params["jurs"] = list(jurisdictions)
        async with pool.connection() as conn:
            async with conn.cursor(row_factory=dict_row) as cur:
                await cur.execute(sql, params)
                return await cur.fetchall()

    async def search_jurisprudence(self, query_text: str, limit: int = 10, *,
                                   jurisdictions: Optional[list[str]] = None,
                                   admin: bool = False) -> list[dict]:
        """FTS sobre jurisprudence (config 'spanish'), ACOTADA por jurisdicción (ver
        `search_norms`). Sin `jurisdictions` exige `admin=True`."""
        if not jurisdictions and not admin:
            raise ValueError("search_jurisprudence requiere jurisdictions (o admin=True)")
        jur_clause = "AND jurisdiction = ANY(%(jurs)s) " if jurisdictions else ""
        sql = (f"SELECT {_cols(_JURIS_FIELDS)}, ts_rank(fts_vector, q) AS rank "
               "FROM jurisprudence, websearch_to_tsquery('spanish', %(q)s) q "
               "WHERE fts_vector @@ q " + jur_clause +
               "ORDER BY rank DESC, decision_date DESC LIMIT %(lim)s")
        params: dict[str, Any] = {"q": query_text or "", "lim": limit}
        if jurisdictions:
            params["jurs"] = list(jurisdictions)
        async with pool.connection() as conn:
            async with conn.cursor(row_factory=dict_row) as cur:
                await cur.execute(sql, params)
                return await cur.fetchall()

    # ── curaduría (escritura) ───────────────────────────────────────────────
    async def add_norm(self, data: dict) -> UUID:
        """Upsert de una norma por (jurisdiction, norm_number, issuing_body, effective_date).
        Incluir `effective_date` en la clave permite el VERSIONADO TEMPORAL: cargar la misma
        norma con otra `effective_date` INSERTA una versión nueva en vez de sobrescribir la
        vigente a la fecha de los hechos (antes el upsert destruía la historia). Devuelve el id."""
        sql = """
        INSERT INTO legal_norms
          (norm_type, norm_number, issuing_body, title, summary, full_text,
           effective_date, expiry_date, jurisdiction, practice_areas, metadata)
        VALUES
          (%(norm_type)s, %(norm_number)s, %(issuing_body)s, %(title)s, %(summary)s,
           %(full_text)s, %(effective_date)s, %(expiry_date)s,
           COALESCE(%(jurisdiction)s, 'co'), %(practice_areas)s, %(metadata)s)
        ON CONFLICT (jurisdiction, norm_number, issuing_body, effective_date) DO UPDATE SET
           norm_type      = EXCLUDED.norm_type,
           title          = EXCLUDED.title,
           summary        = EXCLUDED.summary,
           full_text      = EXCLUDED.full_text,
           effective_date = EXCLUDED.effective_date,
           expiry_date    = EXCLUDED.expiry_date,
           jurisdiction   = EXCLUDED.jurisdiction,
           practice_areas = EXCLUDED.practice_areas,
           metadata       = EXCLUDED.metadata,
           updated_at     = now()
        RETURNING id
        """
        params = {
            "norm_type": data["norm_type"],
            "norm_number": data.get("norm_number"),
            "issuing_body": data.get("issuing_body"),
            "title": data.get("title"),
            "summary": data.get("summary"),
            "full_text": data.get("full_text"),
            "effective_date": data["effective_date"],
            "expiry_date": data.get("expiry_date"),
            "jurisdiction": data.get("jurisdiction"),
            "practice_areas": data.get("practice_areas"),
            "metadata": Json(data.get("metadata") or {}),
        }
        return await self._insert_returning_id(sql, params)

    async def add_jurisprudence(self, data: dict) -> UUID:
        """Upsert de una providencia por (jurisdiction, decision_number, court). La
        jurisdicción evita colisión de homónimos entre países (dos países pueden tener una
        'Sentencia C-123'). Por defecto 'co'. Devuelve el id."""
        sql = """
        INSERT INTO jurisprudence
          (norm_id, jurisdiction, court, sala, decision_number, radicado, magistrado_ponente,
           decision_date, topic, ratio_decidendi, obiter_dicta, keywords, metadata)
        VALUES
          (%(norm_id)s, COALESCE(%(jurisdiction)s, 'co'), %(court)s, %(sala)s,
           %(decision_number)s, %(radicado)s, %(magistrado_ponente)s, %(decision_date)s,
           %(topic)s, %(ratio_decidendi)s, %(obiter_dicta)s, %(keywords)s, %(metadata)s)
        ON CONFLICT (jurisdiction, decision_number, court) DO UPDATE SET
           norm_id            = EXCLUDED.norm_id,
           sala               = EXCLUDED.sala,
           radicado           = EXCLUDED.radicado,
           magistrado_ponente = EXCLUDED.magistrado_ponente,
           decision_date      = EXCLUDED.decision_date,
           topic              = EXCLUDED.topic,
           ratio_decidendi    = EXCLUDED.ratio_decidendi,
           obiter_dicta       = EXCLUDED.obiter_dicta,
           keywords           = EXCLUDED.keywords,
           metadata           = EXCLUDED.metadata
        RETURNING id
        """
        params = {
            "norm_id": str(data["norm_id"]) if data.get("norm_id") else None,
            "jurisdiction": data.get("jurisdiction"),
            "court": data.get("court"),
            "sala": data.get("sala"),
            "decision_number": data.get("decision_number"),
            "radicado": data.get("radicado"),
            "magistrado_ponente": data.get("magistrado_ponente"),
            "decision_date": data["decision_date"],
            "topic": data.get("topic"),
            "ratio_decidendi": data.get("ratio_decidendi"),
            "obiter_dicta": data.get("obiter_dicta"),
            "keywords": data.get("keywords"),
            "metadata": Json(data.get("metadata") or {}),
        }
        return await self._insert_returning_id(sql, params)

    async def add_relation(self, source_id: Any, target_id: Any, relation_type: str,
                           effective_date: Optional[date] = None,
                           notes: Optional[str] = None) -> UUID:
        """Upsert de una relación (source, target, relation_type). Devuelve el id. El
        ON CONFLICT lo hace idempotente (re-ingestar el corpus no duplica)."""
        sql = """
        INSERT INTO norm_relations
          (source_norm_id, target_norm_id, relation_type, effective_date, notes)
        VALUES (%(s)s::uuid, %(t)s::uuid, %(rt)s, %(ed)s, %(n)s)
        ON CONFLICT (source_norm_id, target_norm_id, relation_type) DO UPDATE SET
           effective_date = EXCLUDED.effective_date,
           notes          = EXCLUDED.notes
        RETURNING id
        """
        params = {"s": str(source_id), "t": str(target_id), "rt": relation_type,
                  "ed": effective_date, "n": notes}
        return await self._insert_returning_id(sql, params)

    # ── helper de escritura ─────────────────────────────────────────────────
    @staticmethod
    async def _insert_returning_id(sql: str, params: dict) -> UUID:
        async with pool.connection() as conn:
            async with conn.cursor() as cur:
                await cur.execute(sql, params)
                row = await cur.fetchone()
        return row[0]
