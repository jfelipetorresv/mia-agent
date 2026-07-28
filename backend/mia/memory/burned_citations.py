"""
Mia · memory/burned_citations.py — BANCO DE CITAS QUEMADAS del despacho.

QUÉ ES. La lista de citas que el abogado demostró falsas —fabricadas, tergiversadas, mal
atribuidas o inexistentes— para que Mia no las vuelva a emitir NUNCA en esa instalación.

DE DÓNDE SALE (decisión de Pipe #46.2, 2026-07-27). Es el principio portado del harness de
litigio del despacho (`scripts/check-citas-quemadas.py`), y su origen es un defecto real: un
banco de argumentos que el despacho tenía por «verificado» traía una cita FABRICADA anclada a
número y ponente reales. La lección escrita allí gobierna este módulo: **lo que no tiene
barrera, vuelve.** Verificar una cita falsa una vez no sirve si el sistema puede reemitirla.

POR QUÉ ES LA ÚNICA BARRERA QUE ES MURO. De las cuatro que entraron con la decisión #46, tres
nacen como aviso porque un falso positivo bloquearía trabajo bueno. Ésta no puede tener falso
positivo: la cita está en la lista que el propio abogado construyó, o no está. Por eso el muro
va PRIMERO en `annotate_draft`, antes que cualquier vía de respaldo — ni el corpus puede
resucitar una cita quemada, que es exactamente lo que pasó en el caso original.

AGNÓSTICO DE JURISDICCIÓN (regla dura): ni un literal de país. Cada despacho llena su banco con
las citas de SU ordenamiento; aquí solo hay texto y normalización.

AISLAMIENTO: todo corre bajo `pool.tenant_connection` → RLS activo. El banco de un despacho es
información sobre sus propios expedientes y no se filtra a otro.

CACHÉ: el banco se lee una vez por turno y se cachea por tenant con TTL corto. Un banco recién
crecido tarda a lo sumo el TTL en entrar en vigor; quemar una cita invalida la entrada al
instante, así que el caso que importa (el abogado acaba de quemarla) es inmediato.
"""
from __future__ import annotations

import logging
import time
from typing import Optional

from ..agents import verification
from ..db import pool

logger = logging.getLogger("mia.memory.burned_citations")

# TTL de la caché por despacho. Corto a propósito: el coste de leer una lista pequeña es
# despreciable y el riesgo de servir un banco viejo es emitir una cita ya quemada.
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
    """Olvida el banco cacheado de un despacho (tras quemar o desquemar)."""
    _cache.pop(str(tenant_id), None)


async def list_burned(tenant_id: str, *, use_cache: bool = True) -> list[dict]:
    """Banco de citas quemadas del despacho: [{"citation", "citation_norm", "reason"} …].

    Fail-soft: ante cualquier fallo devuelve [] y el turno corre sin muro. Es la dirección
    incómoda pero correcta: si la base no responde, preferimos un borrador que quizá traiga una
    cita quemada (que el abogado ya sabe reconocer) antes que un turno caído. El informe dirá
    `banco_quemadas` ausente, así que la ausencia de muro es visible, no silenciosa.
    """
    if use_cache:
        cached = _cache_get(tenant_id)
        if cached is not None:
            return cached
    try:
        async with pool.tenant_connection(tenant_id) as conn:
            rows = await (await conn.execute(
                "SELECT citation, citation_norm, reason FROM burned_citations "
                "ORDER BY created_at DESC",
            )).fetchall()
    except Exception:  # noqa: BLE001 — leer el banco jamás puede tumbar el turno
        logger.warning("no se pudo leer el banco de citas quemadas (tenant=%s)",
                       tenant_id, exc_info=True)
        return []
    out: list[dict] = []
    for r in rows or []:
        if isinstance(r, dict):
            cita, norm, motivo = r.get("citation"), r.get("citation_norm"), r.get("reason")
        else:
            cita, norm, motivo = r[0], r[1], r[2]
        out.append({"citation": str(cita or ""),
                    "citation_norm": str(norm or ""),
                    "reason": str(motivo or "")})
    _cache[str(tenant_id)] = (time.monotonic(), out)
    return out


async def burn(tenant_id: str, citation: str, *, reason: str = "",
               burned_by: str = "abogado", pasaje: str = "") -> dict:
    """Quema una cita en el banco del despacho. Idempotente por (tenant, forma normalizada).

    `burned_by`: 'abogado' (el caso normal — él la demostró falsa) o 'mia' (la verificación la
    desmintió contra la fuente oficial). `reason` se escribe EN LLANO: se le muestra al abogado.

    Devuelve {"ok", "citation", "citation_norm", "ya_estaba"}. Re-quemar una cita ya quemada
    ACTUALIZA su motivo en vez de fallar: el segundo motivo suele ser el bueno (la primera vez
    se quema con prisa, la segunda con la fuente en la mano).
    """
    cita = str(citation or "").strip()
    norm = verification._normalize(cita)
    if not norm:
        return {"ok": False, "citation": cita, "citation_norm": "", "ya_estaba": False,
                "error": "cita vacía"}
    async with pool.tenant_connection(tenant_id) as conn:
        # `xmax = 0` distingue en la MISMA sentencia la fila insertada de la actualizada — es el
        # dato que el UPSERT ya conoce. (La alternativa que se probó primero, comparar
        # `created_at` con un intervalo de tiempo, es frágil por construcción: dos personas
        # quemando la misma cita en el mismo segundo cambiarían la respuesta.)
        row = await (await conn.execute(
            "INSERT INTO burned_citations (tenant_id, citation, citation_norm, reason, "
            "burned_by, pasaje) VALUES (app_current_tenant(), %s, %s, %s, %s, %s) "
            "ON CONFLICT (tenant_id, citation_norm) DO UPDATE SET "
            "reason = CASE WHEN excluded.reason <> '' THEN excluded.reason "
            "              ELSE burned_citations.reason END "
            "RETURNING (xmax <> 0) AS ya_estaba",
            (cita, norm, str(reason or ""), str(burned_by or "abogado"), str(pasaje or "")),
        )).fetchone()
    invalidate(tenant_id)
    if isinstance(row, dict):
        ya = bool(row.get("ya_estaba"))
    else:
        ya = bool(row[0]) if row else False
    return {"ok": True, "citation": cita, "citation_norm": norm, "ya_estaba": ya}


async def unburn(tenant_id: str, citation: str) -> dict:
    """Saca una cita del banco (el abogado se corrigió: la cita SÍ existe).

    Existe porque el muro tiene que ser reversible por quien lo puso: si quemar fuera
    definitivo, un error de dedo dejaría inutilizable una cita legítima para siempre.
    """
    norm = verification._normalize(str(citation or ""))
    if not norm:
        return {"ok": False, "borradas": 0}
    async with pool.tenant_connection(tenant_id) as conn:
        cur = await conn.execute(
            "DELETE FROM burned_citations WHERE citation_norm = %s", (norm,))
        borradas = int(getattr(cur, "rowcount", 0) or 0)
    invalidate(tenant_id)
    return {"ok": True, "borradas": borradas}
