"""Mia · api.routes.traces — búsqueda FTS de trazas (Tarea H.3, session_search sin LLM).

`GET /api/traces/search?q=...&matter_id=...` — búsqueda por keyword sobre las trazas del tenant,
con ranking BM-like (`ts_rank_cd`) y filtros. Todo bajo RLS; ninguna llamada LLM.
"""
from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query, Request

from ...memory import trace_search
from ...memory.trace_search import TraceSearchError

router = APIRouter(prefix="/api/traces", tags=["traces"])


def _tenant(request: Request) -> str:
    tid = getattr(request.state, "tenant_id", None)
    if not tid:
        raise HTTPException(status_code=401, detail="Sin sesión activa")
    return tid


@router.get("/search")
async def traces_search(
    request: Request,
    q: str = Query(..., description="Texto a buscar en las trazas"),
    matter_id: str | None = Query(None),
    outcome: str | None = Query(None),
    limit: int = Query(20, ge=1, le=200),
):
    """Busca en el historial de turnos del despacho por palabras clave (sin LLM)."""
    tid = _tenant(request)
    try:
        return await trace_search.search_traces(
            tid, q, limit=limit, matter_id=matter_id, outcome=outcome)
    except TraceSearchError as e:
        raise HTTPException(status_code=400, detail=str(e))
