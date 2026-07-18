"""Mia · api.routes.atajos — atajos de despacho para la conversación vacía (Meta E · Mitad 2).

`GET /api/atajos` -> memory.atajos.list_shortcuts(tenant_id). El abogado pulsa un atajo y el
frontend PRE-LLENA el cuadro de mensaje con su texto reproducible — consent-first, nunca se
auto-envía; el abogado revisa y decide.

Auth: el JWT middleware fija `request.state.tenant_id`; la lectura pasa por RLS
(pool.tenant_connection).
"""
from __future__ import annotations

import logging

from fastapi import APIRouter, HTTPException, Request

from ...memory.atajos import list_shortcuts

router = APIRouter(prefix="/atajos", tags=["atajos"])
logger = logging.getLogger("mia.api.atajos")


def _tenant(request: Request) -> str:
    tid = getattr(request.state, "tenant_id", None)
    if not tid:
        raise HTTPException(status_code=401, detail="Sin sesión activa")
    return tid


@router.get("")
async def obtener_atajos(request: Request):
    tid = _tenant(request)
    return {"atajos": await list_shortcuts(tid)}
