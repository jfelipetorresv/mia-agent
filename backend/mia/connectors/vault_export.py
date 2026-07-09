"""Mia · connectors.vault_export — backfill de la bóveda visible (Fase 3 · frente C).

Exporta al vault de Obsidian del despacho (SIEMPRE bajo `{vault}/Mia/`, vía
`VaultWriter` — jamás toca las demás notas del abogado):

  1. Los playbooks `status='active'` del tenant → `Mia/procedimientos/{slug}.md`.
  2. Fichas del corpus jurídico ingerido por `rag.corpus_factory`
     (`legal_norms`/`jurisprudence` con `metadata->>'ingesta'='corpus_factory'`) →
     `Mia/corpus/normativa/{slug}.md` y `Mia/corpus/jurisprudencia/{slug}.md`.
     UNA ficha por norma PADRE (agrupa segmentos por `metadata.parent_norm`, nunca
     una ficha por segmento). Las fichas NUNCA llevan el texto completo — solo un
     resumen corto, la fuente oficial y la huella sha256; el texto vive en la DB.

El corpus jurídico es COMPARTIDO entre tenants (decisión #16 — sin `tenant_id`,
conexión `pool.connection()` sin GUC, igual que `rag.sat_graph.SATGraph`); los
playbooks SÍ son por-tenant (`pool.tenant_connection`). La ficha del corpus se
escribe en el vault del tenant que se está exportando — el corpus es compartido,
el vault no.

Las funciones "leer DB" (`_fetch_active_norms`, `_fetch_jurisprudence`,
`_fetch_active_playbooks`) están separadas de las funciones "renderizar ficha"
(`render_norm_ficha`, `render_jurisprudence_ficha`) para que estas últimas sean
testeables sin base de datos (ver `execution/test_vault_export.py`).

Uso (backfill manual, y futuro cron):
    python -m mia.connectors.vault_export --tenant <tenant_id>
    python -m mia.connectors.vault_export --all-tenants
"""
from __future__ import annotations

import asyncio
import logging
import os
from typing import Any, Optional

from psycopg.rows import dict_row

from ..db import pool
from .vault_writer import (
    CORPUS_JURISPRUDENCIA_SUBDIR,
    CORPUS_NORMATIVA_SUBDIR,
    VaultWriter,
    _yaml_text,
    tenant_vault_writer,
)

logger = logging.getLogger("mia.connectors.vault_export")

_RESUMEN_MAX_CHARS = 400


# ── helpers de render (sin DB — testeables con dicts fabricados) ─────────────
def _short(text: Optional[str], n: int = _RESUMEN_MAX_CHARS) -> str:
    t = (text or "").strip()
    if len(t) <= n:
        return t
    return t[:n].rstrip() + "…"


def _fm(pairs: list[tuple[str, str]]) -> str:
    """Frontmatter YAML simple para fichas del corpus (distinto del de
    conceptos/playbooks: campos propios de norma/sentencia, siempre con
    `fuente: Mia` al final por convención del resto del vault)."""
    lines = ["---"]
    for key, value in pairs:
        lines.append(f"{key}: {value}")
    lines.append("fuente: Mia")
    lines.append("---")
    return "\n".join(lines) + "\n"


def _group_norms_by_parent(rows: list[dict]) -> dict[str, list[dict]]:
    """Agrupa filas de `legal_norms` por `metadata.parent_norm` (o su propio
    `norm_number` si la norma no está segmentada). UNA ficha por norma padre —
    NUNCA una ficha por segmento."""
    groups: dict[str, list[dict]] = {}
    for row in rows:
        meta = row.get("metadata") or {}
        parent = meta.get("parent_norm") or row.get("norm_number") or str(row.get("id") or "")
        groups.setdefault(str(parent), []).append(row)
    return groups


def render_norm_ficha(parent_key: str, segments: list[dict]) -> tuple[str, str]:
    """(slug, contenido_markdown) de la ficha de una norma (posiblemente segmentada
    en varias filas de `legal_norms`). NUNCA incluye `full_text` completo — solo un
    resumen corto; el texto íntegro vive en la DB, la ficha es el índice navegable."""

    def _seg_num(r: dict) -> int:
        meta = r.get("metadata") or {}
        try:
            return int(meta.get("segment") or 0)
        except (TypeError, ValueError):
            return 0

    ordered = sorted(segments, key=_seg_num)
    first = ordered[0]
    meta = first.get("metadata") or {}
    title = str(first.get("title") or parent_key).strip()
    source_url = str(meta.get("source_url") or "")
    fetched_at = str(meta.get("fetched_at") or "")
    sha256 = str(meta.get("content_sha256") or "")
    practice_areas = [str(a) for a in (first.get("practice_areas") or [])]
    resumen = _short(first.get("summary") or first.get("full_text"))
    segments_total = meta.get("segments_total") or len(ordered)

    tags = ", ".join(f'"{_yaml_text(a)}"' for a in practice_areas)
    fm_pairs = [
        ("title", f'"{_yaml_text(title)}"'),
        ("norma", f'"{_yaml_text(parent_key)}"'),
        ("fuente_url", f'"{_yaml_text(source_url)}"'),
        ("descargado", fetched_at or '""'),
        ("sha256", sha256 or '""'),
        ("tags", f"[{tags}]"),
    ]

    body_lines = [
        f"# {title}",
        "",
        f"**Número:** {parent_key}",
        f"**Fuente oficial:** {source_url}",
        f"**Descargado:** {fetched_at}",
        f"**Huella (sha256):** {sha256}",
    ]
    if segments_total and int(segments_total) > 1:
        body_lines.append(f"**Segmentos:** {segments_total}")
    if practice_areas:
        body_lines.append(f"**Áreas de práctica:** {', '.join(practice_areas)}")
    body_lines += ["", "## Resumen", resumen or "(sin resumen disponible)"]

    content = _fm(fm_pairs) + "\n" + "\n".join(body_lines)
    return parent_key, content


def render_jurisprudence_ficha(row: dict) -> tuple[str, str]:
    """(slug, contenido_markdown) de la ficha de UNA sentencia. Nunca incluye texto
    completo de la providencia — solo el índice (corte, MP, fecha, tema, fuente)."""
    meta = row.get("metadata") or {}
    court = str(row.get("court") or "")
    decision_number = str(row.get("decision_number") or "")
    mp = str(row.get("magistrado_ponente") or "")
    fecha = str(row.get("decision_date") or "")
    topic = str(row.get("topic") or "")
    source_url = str(meta.get("source_url") or "")

    title = f"{court} {decision_number}".strip() or decision_number or str(row.get("id") or "")
    slug_key = decision_number or title

    fm_pairs = [
        ("title", f'"{_yaml_text(title)}"'),
        ("corte", f'"{_yaml_text(court)}"'),
        ("numero", f'"{_yaml_text(decision_number)}"'),
        ("magistrado_ponente", f'"{_yaml_text(mp)}"'),
        ("fecha", fecha or '""'),
        ("fuente_url", f'"{_yaml_text(source_url)}"'),
    ]
    body_lines = [
        f"# {title}",
        "",
        f"**Corte:** {court}",
        f"**Número:** {decision_number}",
        f"**Magistrado ponente:** {mp}",
        f"**Fecha:** {fecha}",
        f"**Fuente oficial:** {source_url}",
        "",
        "## Tema",
        topic or "(sin tema registrado)",
    ]
    content = _fm(fm_pairs) + "\n" + "\n".join(body_lines)
    return slug_key, content


# ── lectura de DB (separada del render — corpus COMPARTIDO, sin tenant) ──────
async def _fetch_active_norms() -> list[dict]:
    """Normas ingeridas por `corpus_factory` (tabla COMPARTIDA, sin `tenant_id`:
    conexión `pool.connection()` sin GUC — mismo criterio que `SATGraph`)."""
    async with pool.connection() as conn:
        async with conn.cursor(row_factory=dict_row) as cur:
            await cur.execute(
                "SELECT id, norm_number, title, summary, full_text, practice_areas, metadata "
                "FROM legal_norms WHERE metadata->>'ingesta' = 'corpus_factory'"
            )
            return list(await cur.fetchall())


async def _fetch_jurisprudence() -> list[dict]:
    """Providencias ingeridas por `corpus_factory` (tabla COMPARTIDA, sin `tenant_id`)."""
    async with pool.connection() as conn:
        async with conn.cursor(row_factory=dict_row) as cur:
            await cur.execute(
                "SELECT id, court, decision_number, magistrado_ponente, decision_date, "
                "topic, metadata FROM jurisprudence WHERE metadata->>'ingesta' = 'corpus_factory'"
            )
            return list(await cur.fetchall())


async def _fetch_active_playbooks(tenant_id: str) -> list[dict]:
    """Playbooks activos del tenant (tabla POR-TENANT: `pool.tenant_connection`)."""
    async with pool.tenant_connection(tenant_id) as conn:
        async with conn.cursor(row_factory=dict_row) as cur:
            await cur.execute(
                "SELECT title, summary, applies_when, content, status FROM playbooks "
                "WHERE status = 'active' ORDER BY created_at"
            )
            return list(await cur.fetchall())


# ── orquestación por tenant ───────────────────────────────────────────────────
async def export_tenant_playbooks(tenant_id: str, writer: VaultWriter) -> int:
    """Exporta todos los playbooks activos del tenant al vault. Devuelve cuántos."""
    rows = await _fetch_active_playbooks(tenant_id)
    for row in rows:
        # E/S de disco síncrona (puede ser lenta con vaults en OneDrive) → a un hilo.
        await asyncio.to_thread(writer.export_playbook, tenant_id, dict(row))
    return len(rows)


async def export_corpus_fichas(writer: VaultWriter) -> dict[str, int]:
    """Exporta las fichas del corpus jurídico COMPARTIDO al vault de `writer`
    (el corpus es igual para todos los tenants; el vault destino no)."""
    # Dos lecturas independientes del corpus compartido — en paralelo, no secuenciales
    # (revisión capa 2: no hay dependencia de orden entre ellas).
    norms, juris = await asyncio.gather(_fetch_active_norms(), _fetch_jurisprudence())

    n = 0
    for parent_key, segments in _group_norms_by_parent(norms).items():
        slug, content = render_norm_ficha(parent_key, segments)
        await asyncio.to_thread(writer._export_ficha, CORPUS_NORMATIVA_SUBDIR, slug, content)
        n += 1

    j = 0
    for row in juris:
        slug, content = render_jurisprudence_ficha(row)
        await asyncio.to_thread(writer._export_ficha, CORPUS_JURISPRUDENCIA_SUBDIR, slug, content)
        j += 1

    return {"normativa": n, "jurisprudencia": j}


async def export_tenant(tenant_id: str) -> dict[str, Any]:
    """Exporta playbooks + fichas del corpus al vault del tenant. Si el tenant no
    tiene vault configurado (o el vault falla), se omite en silencio con log — mismo
    criterio de resiliencia que `wiki_manager._mirror_concept_to_vault`."""
    try:
        writer = await tenant_vault_writer(tenant_id)
    except Exception:  # noqa: BLE001 — un tenant caído no tumba el backfill de los demás
        logger.warning("No pude resolver el vault del tenant %s.", tenant_id, exc_info=True)
        return {"tenant_id": tenant_id, "vault": None}
    if writer is None:
        logger.info("Tenant %s sin vault de Obsidian configurado — se omite.", tenant_id)
        return {"tenant_id": tenant_id, "vault": None}

    try:
        pb_count = await export_tenant_playbooks(tenant_id, writer)
        corpus_stats = await export_corpus_fichas(writer)
    except Exception:  # noqa: BLE001 — fail-soft: un tenant caído no tumba el backfill
        logger.warning("Falló el backfill de la bóveda para el tenant %s.", tenant_id, exc_info=True)
        return {"tenant_id": tenant_id, "vault": str(writer.vault), "error": True}

    return {
        "tenant_id": tenant_id,
        "vault": str(writer.vault),
        "playbooks": pb_count,
        **corpus_stats,
    }


def _list_tenant_ids() -> list[str]:
    """Todos los `tenant_id` (conexión `postgres` superusuario — mismo patrón que
    `memory.dreams.Dreams._list_tenant_ids`, pensado para el cron futuro de
    `--all-tenants`). Vacío (sin lanzar) si `PG_PASSWORD` no está en `.env`."""
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


# ── CLI ──────────────────────────────────────────────────────────────────────
async def _run(tenant_id: Optional[str], all_tenants: bool) -> list[dict[str, Any]]:
    await pool.open_pool()
    try:
        ids = _list_tenant_ids() if all_tenants else ([tenant_id] if tenant_id else [])
        return [await export_tenant(tid) for tid in ids]
    finally:
        await pool.close_pool()


if __name__ == "__main__":
    # Ejecutar como módulo:
    #   python -m mia.connectors.vault_export --tenant <tenant_id>
    #   python -m mia.connectors.vault_export --all-tenants
    import argparse
    import sys

    # psycopg async no corre sobre ProactorEventLoop (Windows nativo, Modo B).
    if sys.platform == "win32":
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass

    parser = argparse.ArgumentParser(
        description="Backfill de la bóveda visible de Mia: playbooks + fichas del corpus."
    )
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--tenant", help="tenant_id a exportar")
    group.add_argument("--all-tenants", action="store_true", help="exporta todos los tenants")
    args = parser.parse_args()

    results = asyncio.run(_run(args.tenant, args.all_tenants))
    print("== Backfill de la bóveda visible ==")
    if not results:
        print("  (sin tenants para exportar)")
    for r in results:
        if r.get("vault") is None:
            print(f"  - {r['tenant_id']}: sin vault configurado — omitido")
        elif r.get("error"):
            print(f"  - {r['tenant_id']}: ERROR durante el backfill (ver log)")
        else:
            print(
                f"  - {r['tenant_id']}: playbooks={r.get('playbooks', 0)} "
                f"normativa={r.get('normativa', 0)} jurisprudencia={r.get('jurisprudencia', 0)}"
            )
