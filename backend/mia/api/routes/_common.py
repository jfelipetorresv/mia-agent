"""Mia · api.routes._common — helpers compartidos por los routers de 1d."""
from __future__ import annotations

import json
import uuid

from fastapi import HTTPException

from ...db import pool


def sse(event: str, message: str, **extra) -> dict:
    """Construye un evento SSE (event + data JSON). El `data` es lo que VE el abogado:
    SIEMPRE en español, sin jerga técnica (§G: nada de 'HITL', 'LangGraph', 'tenant')."""
    data = {"message": message}
    data.update(extra)
    return {"event": event, "data": json.dumps(data, ensure_ascii=False)}


def _is_uuid(s: str) -> bool:
    try:
        uuid.UUID(str(s))
        return True
    except Exception:
        return False


async def assert_owns_matter(tenant_id: str, matter_id: str) -> None:
    """401 si el tenant del JWT no es dueño del asunto.

    La verificación pasa por RLS: bajo `tenant_connection(tenant_id)`, un asunto de
    otro despacho es INVISIBLE (fail-closed). Sumado al thread_id={tenant}:{matter}
    del checkpoint, es la doble barrera de la decisión #9.
    """
    if not _is_uuid(matter_id):
        raise HTTPException(status_code=401, detail="Asunto no autorizado")
    async with pool.tenant_connection(tenant_id) as conn:
        row = await (await conn.execute(
            "SELECT 1 FROM matters WHERE id = %s::uuid", (matter_id,)
        )).fetchone()
    if not row:
        raise HTTPException(status_code=401, detail="Asunto no autorizado")
