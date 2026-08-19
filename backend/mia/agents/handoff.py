"""Traspaso de asunto largo: ficha al cerrar un turno, chequeo al reabrir.

Si un ``[doc n]`` del inventario ya no está, el turno nuevo falla cerrado.
"""
from __future__ import annotations

import logging
from typing import Any

from psycopg.types.json import Json

from ..db import pool
from . import packs

logger = logging.getLogger("mia.agents.handoff")

_DOC_RE = packs._DOC_LOCATOR


class HandoffBroken(Exception):
    """El inventario del traspaso ya no coincide con el expediente."""


async def save_handoff(
    tenant_id: str, matter_id: str, *,
    fact_pack: dict | None, source_pack: dict | None, strategy_pack: dict | None,
    verification: dict | None, documents: list | None,
    decisions: dict | None, reservas: list | None, pendientes: list | None,
) -> None:
    inventory: dict[str, str] = {}
    for i, doc in enumerate(documents or []):
        n = str(i + 1)
        if isinstance(doc, dict):
            inventory[n] = str(doc.get("id") or packs.document_hash(doc))
        else:
            inventory[n] = packs.document_hash(str(doc))
    locators = []
    for hecho in (fact_pack or {}).get("hechos") or []:
        if isinstance(hecho, dict):
            locators.extend(_DOC_RE.findall(str(hecho.get("locator") or "")))
    ficha = {
        "hechos": (fact_pack or {}).get("hechos") or [],
        "fuentes": (source_pack or {}).get("fuentes") or [],
        "argumentos": (strategy_pack or {}).get("argumentos") or [],
        "descartes": (strategy_pack or {}).get("descartes") or [],
        "citas": (verification or {}).get("detalle") or [],
        "decisiones": decisions or {},
        "reservas": reservas or [],
        "pendientes": pendientes or [],
        "doc_inventory": inventory,
        "locators": sorted({int(n) for n in locators}),
    }
    async with pool.tenant_connection(tenant_id) as conn:
        await conn.execute(
            "INSERT INTO matter_handoffs (tenant_id, matter_id, ficha) "
            "VALUES (%s::uuid, %s::uuid, %s) "
            "ON CONFLICT (tenant_id, matter_id) DO UPDATE SET "
            "ficha = EXCLUDED.ficha, updated_at = now()",
            (tenant_id, matter_id, Json(ficha)),
        )


async def load_handoff(tenant_id: str, matter_id: str) -> dict[str, Any] | None:
    try:
        async with pool.tenant_connection(tenant_id) as conn:
            row = await (await conn.execute(
                "SELECT ficha FROM matter_handoffs WHERE matter_id = %s::uuid",
                (matter_id,),
            )).fetchone()
    except Exception:  # noqa: BLE001 — tabla ausente: no hay traspaso que romper
        logger.debug("handoff: no se pudo leer (tenant=%s)", tenant_id, exc_info=True)
        return None
    if not row or not isinstance(row[0], dict):
        return None
    return row[0]


async def check_reopen(tenant_id: str, matter_id: str, documents: list | None) -> None:
    """Falla si un [doc n] del inventario del traspaso ya no está en el expediente."""
    ficha = await load_handoff(tenant_id, matter_id)
    if not ficha:
        return
    inventory = ficha.get("doc_inventory") or {}
    if not isinstance(inventory, dict) or not inventory:
        return
    present: dict[str, str] = {}
    for i, doc in enumerate(documents or []):
        n = str(i + 1)
        if isinstance(doc, dict):
            present[n] = str(doc.get("id") or packs.document_hash(doc))
            present[str(doc.get("id") or "")] = present[n]
        else:
            present[n] = packs.document_hash(str(doc))
    missing: list[str] = []
    for n, token in inventory.items():
        if token in present.values() or n in present:
            continue
        missing.append(f"[doc {n}]")
    locators = ficha.get("locators") or []
    for n in locators:
        key = str(int(n))
        if key not in present and key in inventory:
            if f"[doc {key}]" not in missing:
                missing.append(f"[doc {key}]")
    if missing:
        raise HandoffBroken(
            "Al reabrir el asunto faltan piezas del expediente que el turno anterior "
            "usó: " + ", ".join(missing) + ". Restaura esos documentos o inicia un "
            "turno nuevo sin apoyarte en ese inventario.")


def saved_argument_selection(ficha: dict[str, Any] | None) -> dict[str, Any] | None:
    """La selección HITL persistida en el traspaso, o None si no hay."""
    if not isinstance(ficha, dict):
        return None
    decisions = ficha.get("decisiones")
    if not isinstance(decisions, dict):
        return None
    raw = decisions.get("argument_selection")
    return raw if isinstance(raw, dict) and raw else None


async def cached_facts_for_documents(
    tenant_id: str, matter_id: str, documents: list | None,
) -> tuple[list[dict], list[int]]:
    """(hechos cacheados, índices 0-based SIN cache) para no re-extraer el mismo PDF."""
    docs = documents or []
    hashes = [packs.document_hash(d) for d in docs]
    if not hashes:
        return [], []
    try:
        async with pool.tenant_connection(tenant_id) as conn:
            rows = await (await conn.execute(
                "SELECT doc_hash, hechos FROM matter_document_facts "
                "WHERE matter_id = %s::uuid AND doc_hash = ANY(%s)",
                (matter_id, hashes),
            )).fetchall()
    except Exception:  # noqa: BLE001
        logger.debug("fact cache ilegible (matter=%s)", matter_id, exc_info=True)
        return [], list(range(len(docs)))
    by_hash = {str(r[0]): (r[1] if isinstance(r[1], list) else []) for r in rows}
    cached: list[dict] = []
    missing: list[int] = []
    for i, digest in enumerate(hashes):
        hits = by_hash.get(digest)
        if hits:
            cached.extend(h for h in hits if isinstance(h, dict))
        else:
            missing.append(i)
    return cached, missing


async def store_document_facts(
    tenant_id: str, matter_id: str, documents: list | None, fact_pack: dict | None,
) -> None:
    if not fact_pack or not documents:
        return
    hechos = fact_pack.get("hechos") if isinstance(fact_pack, dict) else None
    if not isinstance(hechos, list):
        return
    per_doc: dict[str, list[dict]] = {}
    for i, doc in enumerate(documents):
        digest = packs.document_hash(doc)
        n = i + 1
        mine = [h for h in hechos if isinstance(h, dict)
                and str(n) in packs._DOC_LOCATOR.findall(str(h.get("locator") or ""))]
        if mine:
            per_doc[digest] = mine
    if not per_doc:
        return
    try:
        async with pool.tenant_connection(tenant_id) as conn:
            for digest, mine in per_doc.items():
                await conn.execute(
                    "INSERT INTO matter_document_facts "
                    "(tenant_id, matter_id, doc_hash, hechos) "
                    "VALUES (%s::uuid, %s::uuid, %s, %s) "
                    "ON CONFLICT (tenant_id, matter_id, doc_hash) DO UPDATE SET "
                    "hechos = EXCLUDED.hechos, updated_at = now()",
                    (tenant_id, matter_id, digest, Json(mine)),
                )
    except Exception:  # noqa: BLE001 — cache best-effort
        logger.debug("no se pudo persistir fact-pack por hash (matter=%s)", matter_id,
                     exc_info=True)
