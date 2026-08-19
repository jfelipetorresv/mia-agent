"""Mia · api.routes.playbook_health — salud de las guías del despacho (Meta E · Mitad 1).

`POST /api/playbooks/{id}/health` dispara el chequeo determinista de una guía (memory.
playbook_health.check_playbook) y devuelve el resultado EN LLANO (§G): "3 citas sin
verificar de 8", nunca "embedding" ni "chunk". `GET /api/playbooks/health/summary` agrega
los conteos sano/revisar/sin_revisar de las guías activas.

Archivo separado de ux.py (donde vive el resto del CRUD de playbooks) porque esta es una
capacidad nueva e independiente del Meta E. Auth: el JWT middleware fija
`request.state.tenant_id`; toda consulta pasa por RLS.
"""
from __future__ import annotations

import logging

from fastapi import APIRouter, HTTPException, Request

from ...memory.playbook_health import PlaybookHealthError, check_playbook, health_summary

router = APIRouter(prefix="/api/playbooks", tags=["playbook_health"])
logger = logging.getLogger("mia.api.playbook_health")


def _tenant(request: Request) -> str:
    tid = getattr(request.state, "tenant_id", None)
    if not tid:
        raise HTTPException(status_code=401, detail="Sin sesión activa")
    return tid


@router.get("/health/summary")
async def resumen_salud_guias(request: Request):
    """Conteos sano/revisar/sin_revisar de las guías activas del despacho."""
    tid = _tenant(request)
    try:
        return await health_summary(tid)
    except Exception:  # noqa: BLE001
        logger.exception("resumen_salud_guias falló (tenant=%s)", tid)
        raise HTTPException(
            status_code=502,
            detail="No pude cargar el resumen de salud en este momento. Intenta de nuevo.",
        )


@router.post("/{playbook_id}/health")
async def revisar_salud_guia(playbook_id: str, request: Request):
    """Revisa AHORA la salud de una guía y persiste el resultado."""
    tid = _tenant(request)
    try:
        return await check_playbook(tid, playbook_id)
    except PlaybookHealthError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception:  # noqa: BLE001
        logger.exception("revisar_salud_guia falló (tenant=%s guia=%s)", tid, playbook_id)
        raise HTTPException(
            status_code=502,
            detail="No pude revisar esta guía en este momento. Intenta de nuevo.",
        )
