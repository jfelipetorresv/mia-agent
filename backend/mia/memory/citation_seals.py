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
import hashlib
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
                "SELECT citation, citation_norm, fuente_tipo, fuente_ref, fuente_titulo, "
                "source_passage_hash, artifact_hash, jurisdiction_codes "
                "FROM citation_seals ORDER BY created_at DESC"
            )).fetchall()
        data = [
            {"citation": str(r[0] or ""), "citation_norm": str(r[1] or ""),
             "fuente_tipo": str(r[2] or ""), "fuente_ref": str(r[3] or ""),
             "fuente_titulo": str(r[4] or ""), "source_passage_hash": str(r[5] or ""),
             "artifact_hash": str(r[6] or ""), "jurisdiction_codes": list(r[7] or [])}
            for r in rows
        ]
        _cache[str(tenant_id)] = (time.monotonic(), data)
        return data
    except Exception:  # noqa: BLE001 — sin sellos el turno sigue; jamás tumbar nada
        logger.debug("no se pudieron leer los sellos (fail-soft)", exc_info=True)
        return []


def active_source_hashes(sources: list[dict] | None, documents: list[dict] | None) -> set[str]:
    """Huellas del contenido de las fuentes efectivamente disponibles en este turno."""
    hashes: set[str] = set()
    for source in sources or []:
        if not isinstance(source, dict):
            continue
        digest = str(source.get("source_passage_hash") or "")
        if len(digest) == 64:
            hashes.add(digest)
    for document in documents or []:
        if not isinstance(document, dict):
            continue
        content = str(document.get("content") or "")
        if content:
            hashes.add(hashlib.sha256(content.encode("utf-8")).hexdigest())
    return hashes


async def list_compatible_seals(tenant_id: str, *, source_hashes: set[str],
                                jurisdictions: list[str] | None) -> list[dict]:
    """Solo reutiliza un sello si el mismo pasaje sigue presente y su derecho aplica.

    Los sellos heredados con campos vacíos quedan fuera por construcción. Sin fuentes
    actuales tampoco hay reutilización: se vuelve a verificar, nunca se presume.
    """
    if not source_hashes:
        return []
    active_jurisdictions = {str(j) for j in (jurisdictions or []) if str(j)}
    if not active_jurisdictions:
        return []
    out = []
    for seal in await list_seals(tenant_id):
        passage = str(seal.get("source_passage_hash") or "")
        artifact = str(seal.get("artifact_hash") or "")
        seal_jurisdictions = {str(j) for j in (seal.get("jurisdiction_codes") or []) if str(j)}
        if (len(passage) == 64 and len(artifact) == 64 and passage in source_hashes
                and seal_jurisdictions.intersection(active_jurisdictions)):
            out.append(seal)
    return out


async def seal_from_approved_report(tenant_id: str, report: dict,
                                    trace_id: str = "", *, artifact_hash: str = "",
                                    jurisdictions: list[str] | None = None) -> int:
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
        ftipo = str(fuente.get("tipo") or "")
        fref = str(fuente.get("referencia") or "")
        ftitulo = str(fuente.get("titulo") or "")
        # La fuente puede no exponer el pasaje completo; la huella ata al menos la
        # decisión a su identificador + cita exacta. Nunca se confunde con el hash
        # del documento del abogado, que viaja separado en ``artifact_hash``.
        passage = str(fuente.get("source_passage_hash") or "")
        # Un identificador de fuente no es un pasaje. Sin huella de contenido, no
        # nace sello reutilizable (fail-closed).
        if len(passage) != 64 or len(artifact_hash or "") != 64 or not jurisdictions:
            continue
        candidatas.append((cita, norm, ftipo, fref, ftitulo, passage))
    if not candidatas:
        return 0
    try:
        # Ventana quemar↔aprobar: el informe pudo verificarse ANTES de que el abogado
        # quemara la cita. Se re-coteja el banco en el momento de sellar (lectura
        # directa, sin caché) — si la consulta falla, no se sella nada (fail-closed).
        from ..agents import verification as _verification
        from . import burned_citations as _burned
        vivas = await _burned.list_burned(tenant_id, use_cache=False)
        burned_norm = frozenset(
            str(b.get("citation_norm") or "") for b in vivas or [] if isinstance(b, dict))
        burned_norm = frozenset(x for x in burned_norm if x)
        candidatas = [c for c in candidatas
                      if not _verification._is_burned(c[0], burned_norm)]
        if not candidatas:
            return 0
        async with pool.tenant_connection(tenant_id) as conn:
            for cita, norm, ftipo, fref, ftitulo, passage in candidatas:
                await conn.execute(
                    "INSERT INTO citation_seals (tenant_id, citation, citation_norm, "
                    "  fuente_tipo, fuente_ref, fuente_titulo, trace_id, "
                    "  source_passage_hash, artifact_hash, jurisdiction_codes) "
                    "VALUES (%s::uuid, %s, %s, %s, %s, %s, %s, %s, %s, %s) "
                    "ON CONFLICT (tenant_id, citation_norm) DO UPDATE SET "
                    " citation=EXCLUDED.citation, fuente_tipo=EXCLUDED.fuente_tipo, "
                    " fuente_ref=EXCLUDED.fuente_ref, fuente_titulo=EXCLUDED.fuente_titulo, "
                    " trace_id=EXCLUDED.trace_id, source_passage_hash=EXCLUDED.source_passage_hash, "
                    " artifact_hash=EXCLUDED.artifact_hash, "
                    " jurisdiction_codes=EXCLUDED.jurisdiction_codes, created_at=now()",
                    (tenant_id, cita, norm, ftipo, fref, ftitulo, trace_id or "",
                     passage, artifact_hash or "", list(jurisdictions or [])))
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
