"""Mia · api.routes.citas_quemadas — el banco de citas que el despacho demostró falsas.

Es la puerta que convierte el MURO (decisión de Pipe #46.2) en algo que el abogado usa solo:
cuando encuentra en un borrador una cita que no existe, o que no dice lo que se le atribuye, la
marca aquí y Mia no la vuelve a emitir en esta instalación.

  · `POST   /api/citas-quemadas`      → quema una cita (idempotente; re-quemar actualiza el motivo)
  · `GET    /api/citas-quemadas`      → el banco del despacho, lo más reciente primero
  · `DELETE /api/citas-quemadas`      → la saca del banco (el abogado se corrigió)

TODO EN LLANO (CLAUDE.md §G): el abogado ve «citas marcadas como falsas», nunca «burned» ni
«normalización». Auth: el middleware JWT fija `request.state.tenant_id` y toda consulta pasa por
RLS — el banco de un despacho es información sobre sus expedientes y no se cruza con otro.

Por qué el borrado existe: si quemar fuera definitivo, un error de dedo dejaría inutilizable una
cita legítima para siempre. El muro tiene que ser reversible por quien lo puso.
"""
from __future__ import annotations

import logging

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel

from ...memory import burned_citations

router = APIRouter(prefix="/api/citas-quemadas", tags=["citas_quemadas"])
logger = logging.getLogger("mia.api.citas_quemadas")

# Tope de longitud de lo que se acepta como «cita»: una cita es una referencia, no un párrafo.
# Sin tope, un copiar/pegar del borrador entero entraría al banco y el muro empezaría a retirar
# texto legítimo por contención.
MAX_CITA_CHARS = 300
MAX_MOTIVO_CHARS = 2000


class QuemarBody(BaseModel):
    cita: str
    motivo: str = ""
    # Pasaje donde apareció (opcional): sirve para auditar la decisión después, sin depender de
    # la memoria de nadie.
    pasaje: str = ""


class DesquemarBody(BaseModel):
    cita: str


def _tenant(request: Request) -> str:
    tid = getattr(request.state, "tenant_id", None)
    if not tid:
        raise HTTPException(status_code=401, detail="Sin sesión activa")
    return tid


@router.get("")
async def listar(request: Request):
    """Las citas que este despacho marcó como falsas."""
    tid = _tenant(request)
    try:
        banco = await burned_citations.list_burned(tid, use_cache=False)
    except Exception:  # noqa: BLE001
        logger.exception("listar citas quemadas falló (tenant=%s)", tid)
        raise HTTPException(
            status_code=502,
            detail="No pude cargar las citas marcadas como falsas. Intenta de nuevo.")
    return {"total": len(banco),
            "citas": [{"cita": b["citation"], "motivo": b["reason"]} for b in banco]}


@router.post("")
async def quemar(request: Request, body: QuemarBody):
    """Marca una cita como falsa: Mia no la vuelve a emitir en este despacho."""
    tid = _tenant(request)
    cita = (body.cita or "").strip()
    if not cita:
        raise HTTPException(status_code=400, detail="Escribe la cita que quieres marcar.")
    if len(cita) > MAX_CITA_CHARS:
        raise HTTPException(
            status_code=400,
            detail=("Eso es demasiado largo para ser una cita. Marca solo la referencia "
                    "(por ejemplo, la sentencia o la norma), no el párrafo completo."))
    try:
        r = await burned_citations.burn(
            tid, cita,
            reason=(body.motivo or "")[:MAX_MOTIVO_CHARS],
            burned_by="abogado",
            pasaje=(body.pasaje or "")[:MAX_MOTIVO_CHARS])
    except Exception:  # noqa: BLE001
        logger.exception("quemar cita falló (tenant=%s)", tid)
        raise HTTPException(
            status_code=502,
            detail="No pude marcar la cita en este momento. Intenta de nuevo.")
    if not r.get("ok"):
        raise HTTPException(status_code=400, detail="Escribe la cita que quieres marcar.")
    return {
        "ok": True,
        "cita": r["citation"],
        "ya_estaba": bool(r.get("ya_estaba")),
        "mensaje": ("Ya estaba marcada; actualicé el motivo." if r.get("ya_estaba")
                    else "Marcada. No la volveré a usar en este despacho."),
    }


@router.delete("")
async def desquemar(request: Request, body: DesquemarBody):
    """Saca una cita del banco (la cita sí existe: el abogado se corrigió)."""
    tid = _tenant(request)
    cita = (body.cita or "").strip()
    if not cita:
        raise HTTPException(status_code=400, detail="Indica cuál cita quieres reactivar.")
    try:
        r = await burned_citations.unburn(tid, cita)
    except Exception:  # noqa: BLE001
        logger.exception("desquemar cita falló (tenant=%s)", tid)
        raise HTTPException(
            status_code=502,
            detail="No pude reactivar la cita en este momento. Intenta de nuevo.")
    if not r.get("borradas"):
        raise HTTPException(status_code=404,
                            detail="Esa cita no estaba marcada como falsa.")
    return {"ok": True, "mensaje": "Reactivada. Podré volver a usarla cuando tenga respaldo."}
