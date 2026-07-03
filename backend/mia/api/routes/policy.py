"""Mia · api.routes.policy — políticas por despacho (CP-E1, Ola 5).

Hoy expone el TOPE DE GASTO de IA mensual: consultarlo (con el gasto del mes y lo
restante) y fijarlo/quitarlo. El abogado lo gobierna desde el Panel de control.
"""
from __future__ import annotations

import logging

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel

from ...policy import budget as policy_budget

router = APIRouter(prefix="/policy", tags=["policy"])
logger = logging.getLogger("mia.api.policy")


def _tenant(request: Request) -> str:
    tid = getattr(request.state, "tenant_id", None)
    if not tid:
        raise HTTPException(status_code=401, detail="Sin sesión activa")
    return tid


class BudgetBody(BaseModel):
    """Tope mensual en USD. null o <= 0 = sin límite."""

    monthly_budget_usd: float | None = None


@router.get("/budget")
async def get_budget(request: Request):
    """Estado del tope de gasto: presupuesto, gasto del mes, restante, si se superó."""
    tid = _tenant(request)
    try:
        return await policy_budget.budget_status(tid)
    except Exception:  # noqa: BLE001 — §G: sin jerga al abogado
        logger.exception("get_budget falló (tenant=%s)", tid)
        raise HTTPException(
            status_code=502,
            detail="No pude leer el tope de gasto en este momento. Intenta de nuevo.",
        )


@router.put("/budget")
async def put_budget(body: BudgetBody, request: Request):
    """Fija (o quita) el tope de gasto mensual. Devuelve el estado ya actualizado."""
    tid = _tenant(request)
    try:
        await policy_budget.set_monthly_budget(tid, body.monthly_budget_usd)
        return await policy_budget.budget_status(tid)
    except Exception:  # noqa: BLE001
        logger.exception("put_budget falló (tenant=%s)", tid)
        raise HTTPException(
            status_code=502,
            detail="No pude guardar el tope de gasto en este momento. Intenta de nuevo.",
        )
