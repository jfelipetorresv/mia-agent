"""Mia · api.routes.learning — disparo MANUAL del aprendizaje de Mia (frente B · B2).

El FeedbackProcessor corre a diario por cron (`feedback_daily`, 24h). Este endpoint deja
que el abogado lo dispare AHORA para su despacho, sin esperar al ciclo nocturno: revisa las
trazas recientes y deja las propuestas nuevas pendientes de su aprobación (Pantalla 4).

Auth: el JWT middleware fija `request.state.tenant_id` (RLS). Mismo mecanismo que el job
diario, pero para UN tenant (con su política de modelo, igual que `run_all_tenants`).

§G (CLAUDE.md): sin jerga técnica hacia el usuario — la respuesta habla de "propuestas nuevas".
"""
from __future__ import annotations

import logging

from fastapi import APIRouter, HTTPException, Request

from ...agent import llm
from ...memory.feedback_processor import FeedbackProcessor

router = APIRouter(prefix="/api/learning", tags=["learning"])
logger = logging.getLogger("mia.api.learning")


def _tenant(request: Request) -> str:
    tid = getattr(request.state, "tenant_id", None)
    if not tid:
        raise HTTPException(status_code=401, detail="Sin sesión activa")
    return tid


@router.post("/run")
async def learning_run(request: Request):
    """Corre el aprendizaje de Mia sobre las trazas recientes del despacho actual y devuelve
    cuántas propuestas nuevas quedaron pendientes de revisión."""
    tid = _tenant(request)
    # Igual que el job por-tenant de cron: fija la política de modelo del despacho para las
    # llamadas al LLM que redactan las propuestas.
    async with llm.tenant_model_policy(tid):
        stats = await FeedbackProcessor().run(tid)
    return {"propuestas_nuevas": stats.get("proposals_created", 0)}
