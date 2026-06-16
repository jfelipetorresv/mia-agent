"""Mia · agents.retrieval — recuperación híbrida RRF (1d · intake_node).

Combina búsqueda vectorial (pgvector, `embedding <=> qv`) y full-text (tsvector
`content_tsv @@ websearch_to_tsquery('spanish', …)`) con Reciprocal Rank Fusion:

    score(doc) = Σ  1 / (k + rank_en_cada_lista)

El schema (Módulo 0) ya trae ambos índices: GIN sobre `content_tsv` y HNSW sobre
`embedding`. No hace falta cambiar el schema.

AISLAMIENTO: la query corre bajo `pool.tenant_connection` → el GUC `app.tenant_id`
queda fijado y RLS filtra por tenant (FAIL-CLOSED). Además se acota al asunto por
`documents.matter_id`. Así "el RLS sigue activo" en las queries de dominio del grafo
aunque el checkpoint se persista aparte (decisión #9).
"""
from __future__ import annotations

from ..db import pool

# k de RRF: 60 es el valor estándar de la literatura (Cormack et al.). Amortigua el
# peso de los primeros puestos sin que una sola lista domine.
RRF_K = 60


def _vector_literal(vec: list[float]) -> str:
    """Serializa el vector de consulta como literal pgvector `[a,b,c]` para `::vector`.

    Se castea como texto a propósito: es robusto independientemente de si el adapter
    de pgvector está registrado en la conexión.
    """
    return "[" + ",".join(f"{x:.8f}" for x in vec) + "]"


_RRF_SQL = """
WITH params AS (
  SELECT %(qvec)s::vector AS qv,
         websearch_to_tsquery('spanish', %(qtext)s) AS qq
),
vec AS (
  SELECT c.id, row_number() OVER (ORDER BY c.embedding <=> p.qv) AS rnk
  FROM chunks c
  JOIN documents d ON d.id = c.document_id
  CROSS JOIN params p
  WHERE d.matter_id = %(matter)s AND c.embedding IS NOT NULL
  ORDER BY c.embedding <=> p.qv
  LIMIT %(cand)s
),
fts AS (
  SELECT c.id, row_number() OVER (ORDER BY ts_rank(c.content_tsv, p.qq) DESC) AS rnk
  FROM chunks c
  JOIN documents d ON d.id = c.document_id
  CROSS JOIN params p
  WHERE d.matter_id = %(matter)s AND c.content_tsv @@ p.qq
  ORDER BY ts_rank(c.content_tsv, p.qq) DESC
  LIMIT %(cand)s
),
fused AS (
  SELECT id, SUM(1.0 / (%(k)s + rnk)) AS score
  FROM (SELECT id, rnk FROM vec UNION ALL SELECT id, rnk FROM fts) u
  GROUP BY id
)
SELECT c.id, c.content, f.score
FROM fused f
JOIN chunks c ON c.id = f.id
ORDER BY f.score DESC
LIMIT %(topk)s
"""


async def retrieve_rrf(
    tenant_id: str,
    matter_id: str,
    query_text: str,
    query_vec: list[float],
    *,
    top_k: int = 8,
    candidates: int = 20,
) -> list[dict]:
    """Recupera los `top_k` chunks más relevantes del asunto por RRF (vector+FTS).

    Devuelve [{id, content, score}], ya filtrado por tenant (RLS) y por asunto.
    Lista vacía si el asunto no tiene chunks indexados todavía.
    """
    args = {
        "qvec": _vector_literal(query_vec),
        "qtext": query_text or "",
        "matter": matter_id,
        "cand": candidates,
        "k": RRF_K,
        "topk": top_k,
    }
    async with pool.tenant_connection(tenant_id) as conn:
        rows = await (await conn.execute(_RRF_SQL, args)).fetchall()
    return [{"id": str(r[0]), "content": r[1], "score": float(r[2])} for r in rows]


async def matter_has_chunks(tenant_id: str, matter_id: str) -> bool:
    """True si el asunto tiene al menos un chunk con embedding indexado.

    Permite a intake_node saltarse embeddings+RRF cuando no hay nada que
    recuperar (asunto sin documentos): evita la llamada a Voyage por completo.
    Corre bajo tenant_connection -> RLS activo (mismo aislamiento que retrieve_rrf).
    """
    async with pool.tenant_connection(tenant_id) as conn:
        row = await (await conn.execute(
            "SELECT EXISTS (SELECT 1 FROM chunks c JOIN documents d ON d.id = c.document_id "
            "WHERE d.matter_id = %s AND c.embedding IS NOT NULL)",
            (matter_id,),
        )).fetchone()
    return bool(row[0])
