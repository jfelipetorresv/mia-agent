"""Mia · memory.playbook_health — salud de las guías del despacho (Meta E · Mitad 1).

QUÉ ES: un chequeo determinista de las citas de una guía (playbook), reusando el escáner de
verificación ya gateado del turno (agents.verification.annotate_draft — CP9, sin red, sin
costo, mismo motor que anota los borradores). No inventa un criterio jurídico nuevo: solo
cuenta cuántas citas del texto de la guía quedan SIN marcar tras pasar por ese mismo escáner.

  'sano'        → el escáner no tuvo que anotar ninguna cita (todas ya estaban marcadas o
                  respaldadas por el corpus).
  'revisar'     → al menos una cita quedó sin marca ni respaldo.
  'sin_revisar' → default; también el valor FAIL-OPEN si el chequeo no se pudo completar.

FAIL-OPEN (patrón agents.personas.PersonaService): cualquier excepción al leer o analizar una
guía se persiste como 'sin_revisar' con una nota en llano — nunca rompe el flujo del abogado.
Revisar la salud de una guía es una ayuda, no un candado.

§G: todo texto que viaja a la API/UI está en llano ("3 citas sin verificar de 8"), nunca
jerga técnica (nada de "chunk", "embedding", "tenant").
"""
from __future__ import annotations

import logging
import uuid
from typing import Optional

from psycopg.types.json import Json

from ..agents import verification
from ..db import pool

logger = logging.getLogger("mia.memory.playbook_health")

HEALTH_SANO = "sano"
HEALTH_REVISAR = "revisar"
HEALTH_SIN_REVISAR = "sin_revisar"
HEALTH_STATUSES: tuple[str, ...] = (HEALTH_SANO, HEALTH_REVISAR, HEALTH_SIN_REVISAR)

_SIN_REVISAR_REPORT = {
    "status": HEALTH_SIN_REVISAR,
    "mensaje": "No se pudo revisar esta guía todavía. Puedes intentarlo de nuevo.",
    "citas": 0,
    "marcadas": 0,
    "respaldadas": 0,
    "anotadas": 0,
}


class PlaybookHealthError(Exception):
    """Error en llano al calcular o guardar la salud de una guía (apto para el abogado)."""


def _require_uuid(value: str) -> str:
    try:
        return str(uuid.UUID(str(value)))
    except (ValueError, AttributeError, TypeError):
        raise PlaybookHealthError("Identificador de guía inválido.")


def _plural(n: int, singular: str, plural: str) -> str:
    return singular if n == 1 else plural


def check_content_health(content: str) -> dict:
    """Analiza el CONTENIDO de una guía con el escáner determinista de citas (agents.
    verification, ya gateado en CP9): cuenta cuántas quedan sin marcar tras el escaneo.

    Determinista y sin efectos (sin red, sin DB, mismo motor que anota los borradores del
    turno). Nunca lanza — un contenido vacío o sin citas simplemente da 'sano' sin citas.

    Devuelve {"status", "mensaje", "citas", "marcadas", "respaldadas", "anotadas"}. `mensaje`
    ya está en llano (§G), listo para mostrar tal cual en la pantalla.
    """
    text = content or ""
    try:
        _, report = verification.annotate_draft(text)
    except Exception:  # noqa: BLE001 — el escáner es determinista, pero fail-open por si acaso
        logger.warning("playbook_health: el escáner de citas falló sobre el contenido", exc_info=True)
        return dict(_SIN_REVISAR_REPORT)
    total = int(report.get("citas") or 0)
    anotadas = int(report.get("anotadas") or 0)
    status = HEALTH_SANO if anotadas == 0 else HEALTH_REVISAR
    if total == 0:
        mensaje = "Esta guía no tiene citas jurídicas que verificar."
    elif anotadas == 0:
        mensaje = f"{total} {_plural(total, 'cita verificada', 'citas verificadas')} de {total}."
    else:
        mensaje = f"{anotadas} {_plural(anotadas, 'cita sin verificar', 'citas sin verificar')} de {total}."
    return {
        "status": status,
        "mensaje": mensaje,
        "citas": total,
        "marcadas": int(report.get("marcadas") or 0),
        "respaldadas": int(report.get("respaldadas") or 0),
        "anotadas": anotadas,
    }


async def check_playbook(tenant_id: str, playbook_id: str) -> dict:
    """Evalúa y PERSISTE la salud de una guía del despacho (bajo RLS del tenant).

    FAIL-OPEN: cualquier excepción al leer o analizar la guía deja health_status=
    'sin_revisar' con una nota — nunca rompe el flujo del abogado (patrón
    agents.personas.PersonaService.resolve_for_turn). Una guía inexistente/ajena SÍ lanza
    PlaybookHealthError (404 en la API): eso no es un fallo del chequeo, es que no hay nada
    que revisar.
    """
    pid = _require_uuid(playbook_id)
    try:
        async with pool.tenant_connection(tenant_id) as conn:
            row = await (await conn.execute(
                "SELECT content FROM playbooks WHERE id = %s::uuid", (pid,),
            )).fetchone()
        if not row:
            raise PlaybookHealthError("Esa guía no existe en este despacho.")
        report = check_content_health(row[0] or "")
    except PlaybookHealthError:
        raise
    except Exception:  # noqa: BLE001 — §G/FAIL-OPEN: la salud jamás tumba el flujo del abogado
        logger.warning("playbook_health: no se pudo evaluar la guía %s (tenant=%s)",
                       pid, tenant_id, exc_info=True)
        report = dict(_SIN_REVISAR_REPORT)

    async with pool.tenant_connection(tenant_id) as conn:
        updated = await (await conn.execute(
            "UPDATE playbooks SET health_status = %s, health_checked_at = now(), "
            "health_report = %s::jsonb WHERE id = %s::uuid "
            "RETURNING health_status, health_checked_at",
            (report["status"], Json(report), pid),
        )).fetchone()
    if not updated:
        # Carrera rara (la guía se borró entre el SELECT y el UPDATE): mismo mensaje 404.
        raise PlaybookHealthError("Esa guía no existe en este despacho.")
    return {
        "id": pid,
        "health_status": updated[0],
        "health_checked_at": updated[1],
        "mensaje": report["mensaje"],
        "citas": report["citas"],
        "anotadas": report["anotadas"],
    }


async def check_all_active(tenant_id: str) -> list[dict]:
    """Evalúa la salud de TODAS las guías activas del despacho. FAIL-OPEN por guía: si una
    falla (o desaparece a mitad de camino) sigue con las demás, nunca aborta el lote."""
    async with pool.tenant_connection(tenant_id) as conn:
        rows = await (await conn.execute(
            "SELECT id FROM playbooks WHERE status = 'active'"
        )).fetchall()
    results: list[dict] = []
    for r in rows:
        try:
            results.append(await check_playbook(tenant_id, str(r[0])))
        except Exception:  # noqa: BLE001 — una guía que falla no debe tumbar el lote completo
            logger.warning("playbook_health: check_all_active saltó una guía (tenant=%s)",
                           tenant_id, exc_info=True)
    return results


async def health_summary(tenant_id: str) -> dict:
    """Conteos sano/revisar/sin_revisar de las guías ACTIVAS del despacho (para el resumen
    agregado de la pantalla). Siempre trae las tres claves, aunque estén en cero."""
    async with pool.tenant_connection(tenant_id) as conn:
        rows = await (await conn.execute(
            "SELECT health_status, count(*) FROM playbooks "
            "WHERE status = 'active' GROUP BY health_status"
        )).fetchall()
    counts = {s: 0 for s in HEALTH_STATUSES}
    for status, n in rows:
        counts[status if status in counts else HEALTH_SIN_REVISAR] = int(n)
    return counts
