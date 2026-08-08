"""
Mia · memory/citation_seals.py — SELLOS DE VERIFICACIÓN del despacho (F2 del plan de
eficiencia, specs/todo/PLAN-principios-harness-llos-eficiencia.md).

QUÉ ES. El espejo positivo del banco de citas quemadas: la lista de citas que ya quedaron
RESPALDADAS por el guardián determinista Y APROBADAS por el abogado dentro de un borrador.
Una cita sellada no se re-audita con modelo en los turnos siguientes: se resuelve por sello
(estado "sellada" en el informe) y el gate LLM solo ve lo no sellado. Es la palanca del
harness de litigio del despacho que hace que el sistema SE ABARATE al madurar sin bajar el
estándar: el sello nace de verificación + decisión humana, jamás de una heurística.

REGLAS DURAS:
  · QUEMADA GANA: quemar una cita revoca su sello en la misma transacción (ver
    burned_citations.burn). El muro de quemadas se evalúa ANTES que el sello en
    verification.annotate_draft.
  · Solo se sella lo que el muro dio por RESPALDADO en el borrador aprobado (con su
    fuente). Una cita marcada, anotada u omitida no se sella nunca.
  · Misma normalización que el escáner (verification._normalize) — si difirieran, la
    caché tendría un agujero por construcción.

AISLAMIENTO Y CACHÉ: mismo patrón que burned_citations — RLS por tenant_connection, caché
por tenant con TTL corto, invalidación inmediata al sellar o revocar.
"""
from __future__ import annotations

import logging
import time
from typing import Optional

from ..agents import verification
from ..db import pool

logger = logging.getLogger("mia.memory.citation_seals")

_CACHE_TTL_SECONDS = 60.0
_cache: dict[str, tuple[float, list[dict]]] = {}


def _cache_get(tenant_id: str) -> Optional[list[dict]]:
    hit = _cache.get(str(tenant_id))
    if not hit:
        return None
    ts, data = hit
    if (time.monotonic() - ts) > _CACHE_TTL_SECONDS:
        _cache.pop(str(tenant_id), None)
        return None
    return data


def invalidate(tenant_id: str) -> None:
    """Olvida los sellos cacheados de un despacho (tras sellar o revocar)."""
    _cache.pop(str(tenant_id), None)


async def list_seals(tenant_id: str) -> list[dict]:
    """Sellos del despacho: [{"citation", "citation_norm", "fuente_tipo", "fuente_ref",
    "fuente_titulo"} …]. Cacheado por tenant con TTL corto. Fail-soft: ante cualquier
    fallo devuelve [] — sin sellos, el turno queda exactamente como antes de existir F2."""
    cached = _cache_get(tenant_id)
    if cached is not None:
        return cached
    try:
        async with pool.tenant_connection(tenant_id) as conn:
            rows = await (await conn.execute(
                "SELECT citation, citation_norm, fuente_tipo, fuente_ref, fuente_titulo "
                "FROM citation_seals ORDER BY created_at DESC"
            )).fetchall()
        data = [
            {"citation": str(r[0] or ""), "citation_norm": str(r[1] or ""),
             "fuente_tipo": str(r[2] or ""), "fuente_ref": str(r[3] or ""),
             "fuente_titulo": str(r[4] or "")}
            for r in rows
        ]
        _cache[str(tenant_id)] = (time.monotonic(), data)
        return data
    except Exception:  # noqa: BLE001 — sin sellos el turno sigue; jamás tumbar nada
        logger.debug("no se pudieron leer los sellos (fail-soft)", exc_info=True)
        return []


async def seal_from_approved_report(tenant_id: str, report: dict,
                                    trace_id: str = "") -> int:
    """Sella las citas RESPALDADAS del informe de un borrador APROBADO. Devuelve cuántas.

    Solo entra lo que el muro dio por respaldado (estado 'respaldada', con fuente); las
    quemadas del banco no pueden entrar (el detalle jamás las trae como respaldadas, y la
    unicidad + la revocación en burn() cierran la ventana). Idempotente por (tenant, forma
    normalizada). Fail-soft: un fallo pierde ESTE sellado y nada más."""
    detalle = (report or {}).get("detalle") or []
    candidatas = []
    for e in detalle:
        if not isinstance(e, dict) or e.get("estado") != "respaldada":
            continue
        cita = str(e.get("cita") or "").strip()
        norm = verification._normalize(cita)
        if not cita or not norm:
            continue
        fuente = e.get("fuente") or {}
        candidatas.append((cita, norm, str(fuente.get("tipo") or ""),
                           str(fuente.get("referencia") or ""),
                           str(fuente.get("titulo") or "")))
    if not candidatas:
        return 0
    try:
        async with pool.tenant_connection(tenant_id) as conn:
            for cita, norm, ftipo, fref, ftitulo in candidatas:
                await conn.execute(
                    "INSERT INTO citation_seals (tenant_id, citation, citation_norm, "
                    "  fuente_tipo, fuente_ref, fuente_titulo, trace_id) "
                    "VALUES (%s::uuid, %s, %s, %s, %s, %s, %s) "
                    "ON CONFLICT (tenant_id, citation_norm) DO NOTHING",
                    (tenant_id, cita, norm, ftipo, fref, ftitulo, trace_id or ""))
        invalidate(tenant_id)
        return len(candidatas)
    except Exception:  # noqa: BLE001
        logger.warning("no se pudieron sellar las citas del borrador aprobado (fail-soft)",
                       exc_info=True)
        return 0


async def revoke(tenant_id: str, citation: str) -> int:
    """Revoca el sello de una cita (p. ej. al quemarla). Devuelve cuántos borró.

    Borra por coincidencia normalizada EN LOS DOS SENTIDOS (contener/contenida), igual que
    el cotejo del muro: quemar «Sentencia C-832 de 2002» debe revocar el sello de
    «Sentencia C-832 de 2002, M.P. …»."""
    norm = verification._normalize(citation or "")
    if not norm:
        return 0
    try:
        async with pool.tenant_connection(tenant_id) as conn:
            rows = await (await conn.execute(
                "SELECT id, citation_norm FROM citation_seals")).fetchall()
            a_borrar = [r[0] for r in rows
                        if r[1] and (r[1] == norm or norm in r[1] or r[1] in norm)]
            for seal_id in a_borrar:
                await conn.execute("DELETE FROM citation_seals WHERE id = %s", (seal_id,))
        invalidate(tenant_id)
        return len(a_borrar)
    except Exception:  # noqa: BLE001
        logger.warning("no se pudo revocar el sello de una cita quemada", exc_info=True)
        return 0
