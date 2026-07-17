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

import logging

from ..db import pool

logger = logging.getLogger("mia.agents.retrieval")

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


# ── Conocimiento del despacho (CP3 · Riesgo #16) ─────────────────────────────
# Mismo RRF híbrido (HNSW + FTS GIN, migración 004) pero sobre `knowledge_chunks`
# (notas de Obsidian + carpetas del abogado). SIN filtro de matter: es conocimiento
# TRANSVERSAL del despacho, no de un asunto. El aislamiento entre despachos lo da
# RLS bajo tenant_connection (fail-closed), igual que en `chunks`.
_KNOWLEDGE_RRF_SQL = """
WITH params AS (
  SELECT %(qvec)s::vector AS qv,
         websearch_to_tsquery('spanish', %(qtext)s) AS qq
),
vec AS (
  SELECT k.id, row_number() OVER (ORDER BY k.embedding <=> p.qv) AS rnk
  FROM knowledge_chunks k
  CROSS JOIN params p
  WHERE k.embedding IS NOT NULL
  ORDER BY k.embedding <=> p.qv
  LIMIT %(cand)s
),
fts AS (
  SELECT k.id, row_number() OVER (ORDER BY ts_rank(k.content_tsv, p.qq) DESC) AS rnk
  FROM knowledge_chunks k
  CROSS JOIN params p
  WHERE k.content_tsv @@ p.qq
  ORDER BY ts_rank(k.content_tsv, p.qq) DESC
  LIMIT %(cand)s
),
fused AS (
  SELECT id, SUM(1.0 / (%(k)s + rnk)) AS score
  FROM (SELECT id, rnk FROM vec UNION ALL SELECT id, rnk FROM fts) u
  GROUP BY id
)
SELECT k.id, k.content, k.source, k.source_path, f.score
FROM fused f
JOIN knowledge_chunks k ON k.id = f.id
ORDER BY f.score DESC
LIMIT %(topk)s
"""


async def retrieve_knowledge_rrf(
    tenant_id: str,
    query_text: str,
    query_vec: list[float],
    *,
    top_k: int = 4,
    candidates: int = 12,
) -> list[dict]:
    """Recupera las `top_k` notas del despacho más relevantes por RRF (vector+FTS).

    Opera sobre `knowledge_chunks` (conocimiento transversal del despacho — CP3,
    Riesgo #16): NO se filtra por asunto. Devuelve
    [{id, content, source, source_path, score}] ya filtrado por tenant (RLS
    fail-closed bajo tenant_connection). Lista vacía si no hay nada indexado.
    """
    args = {
        "qvec": _vector_literal(query_vec),
        "qtext": query_text or "",
        "cand": candidates,
        "k": RRF_K,
        "topk": top_k,
    }
    async with pool.tenant_connection(tenant_id) as conn:
        rows = await (await conn.execute(_KNOWLEDGE_RRF_SQL, args)).fetchall()
    notes = [
        {"id": str(r[0]), "content": r[1], "source": r[2],
         "source_path": r[3], "score": float(r[4])}
        for r in rows
    ]
    # CP-W1 · el wiki DEJA de ser de solo escritura. Va DESPUÉS de las notas del
    # despacho a propósito: aquéllas las escribió un humano, el wiki lo infirió Mia
    # de sus propias trazas — si el presupuesto de la sección aprieta, lo primero
    # que cede es lo inferido. Fail-soft total: ver `wiki_notes`.
    notes.extend(await wiki_notes(tenant_id, query_text))
    return notes


async def wiki_notes(tenant_id: str, query_text: str) -> list[dict]:
    """Conceptos del wiki interno relevantes al turno, con forma de nota del despacho.

    Cierra el lazo del aprendizaje: hasta ahora Mia compilaba lo aprendido de las
    correcciones y los rechazos del abogado (incluida la sección "Lo que NO
    funciona") en ficheros que el modelo NUNCA leía.

    El filtrado duro (corte de confianza, esquema, presupuesto, rótulo de "inferido
    y NO citable") vive en `WikiManager.notes_for_query` — aquí solo se cablea. El
    import es perezoso: el wiki es un módulo de memoria y `retrieval` lo importa el
    grafo; así no se crea un ciclo ni se paga el import cuando no hay wiki.

    FAIL-SOFT: cualquier fallo (sin wiki, fichero ilegible, disco lento) devuelve []
    y la recuperación sigue exactamente como hoy. Jamás tumba el turno del abogado.
    """
    try:
        from ..memory.wiki_manager import WikiManager

        return await WikiManager().notes_for_query(tenant_id, query_text or "")
    except Exception:  # noqa: BLE001 — el wiki nunca puede tumbar el turno
        logger.warning("wiki: lectura omitida en este turno (tenant=%s)",
                       tenant_id, exc_info=True)
        return []


async def wiki_has_concepts(tenant_id: str) -> bool:
    """True si el despacho tiene al menos un concepto en su wiki (chequeo de ficheros).

    Fail-soft: ante cualquier fallo devuelve False (el turno se comporta como hoy).
    """
    try:
        from ..memory.wiki_manager import WikiManager

        concepts = WikiManager().concepts_dir(tenant_id)
        return any(concepts.glob("*.md"))
    except Exception:  # noqa: BLE001
        return False


async def knowledge_exists(tenant_id: str) -> bool:
    """True si el despacho tiene conocimiento transversal que consultar en el turno.

    Dos fuentes: `knowledge_chunks` (notas del vault/carpetas, chequeo BARATO con
    EXISTS sobre los índices de la 004) y el wiki interno (ficheros). Permite a
    intake_node no embeber ni consultar cuando no hay NADA: en ese caso el turno se
    comporta idéntico a hoy (cero llamadas extra a Voyage).

    CP-W1: el OR con el wiki es lo que hace que un despacho SIN Obsidian igual lea
    lo que Mia aprendió de sus aprobaciones y rechazos — sin él, la mitad de los
    despachos nunca cerraría el lazo. Coste: en ese caso el turno paga UN embedding
    de la consulta que hoy no paga (el wiki no lo usa: busca por términos), a cambio
    de que el RRF de notas quede listo si el despacho indexa notas después.
    La query de DB corre bajo tenant_connection -> RLS activo.
    """
    async with pool.tenant_connection(tenant_id) as conn:
        row = await (await conn.execute(
            "SELECT EXISTS (SELECT 1 FROM knowledge_chunks "
            "WHERE embedding IS NOT NULL LIMIT 1)"
        )).fetchone()
    if bool(row[0]):
        return True
    return await wiki_has_concepts(tenant_id)


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
