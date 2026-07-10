"""Mia · api.routes.guides — entrevista para crear guías de trabajo (Bloque B, B1-B3).

`POST /api/guides/interview` — motor de entrevista STATELESS: el frontend manda el
transcript completo en `messages` y este endpoint responde la siguiente pregunta o el
borrador final. El borrador SOLO existe en esta respuesta HTTP — nunca se escribe en
la base de datos aquí (eso pasa en `POST /api/playbooks`, cuando el abogado pulsa
Guardar). Ver `backend/mia/memory/interviewer.py` para el motor.

Validación 422 en español llano (nada de errores de pydantic en inglés hacia el
abogado): tipo de guía inválido, `messages` que no es una lista, un mensaje sin rol o
sin contenido de texto.

Bloque C: `kind='agente'` diseña un agente jurídico (rol experto). Cuando la entrevista
termina (`done:true`), este endpoint SUGIERE guías del despacho que encajan con el agente
(`suggested_playbook_ids`) por solapamiento de términos — solo una sugerencia; el abogado
decide. Fail-open: si la sugerencia falla, se devuelve lista vacía y el flujo sigue.
"""
from __future__ import annotations

import logging
import re
from typing import Any

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel

from ...db import pool
from ...memory.interviewer import MatterNotFoundError, interview

router = APIRouter(prefix="/api/guides", tags=["guides"])
logger = logging.getLogger("mia.api.guides")

_VALID_KINDS = ("guia", "agente")
_VALID_ROLES = ("assistant", "user")

# Sugerencia de guías para un agente: mismo criterio ligero que el selector del grafo
# (agents/graph.py::_select_playbook_ids) — solape de términos de ≥4 letras, score>=1.
_WORD = re.compile(r"\w+", re.UNICODE)
_MAX_SUGGESTED = 5


def _tokens(text: str) -> set[str]:
    return {w.lower() for w in _WORD.findall(text) if len(w) >= 4}


async def _suggest_playbook_ids(tenant_id: str, draft: dict) -> list[str]:
    """Ids de las guías ACTIVAS del despacho que más solapan con el agente propuesto
    (role_prompt + descripción + áreas de énfasis). Top ≤5. FAIL-OPEN → []."""
    try:
        query = " ".join([
            str(draft.get("role_prompt", "")),
            str(draft.get("description", "")),
            " ".join(str(x) for x in (draft.get("focus_areas") or [])),
        ])
        qtokens = _tokens(query)
        if not qtokens:
            return []
        async with pool.tenant_connection(tenant_id) as conn:
            rows = await (await conn.execute(
                "SELECT id, title, summary, applies_when FROM playbooks WHERE status = 'active'"
            )).fetchall()
        scored: list[tuple[str, int]] = []
        for r in rows:
            blob = f"{r[1] or ''} {r[2] or ''} {r[3] or ''}"
            score = len(qtokens & _tokens(blob))
            if score >= 1:
                scored.append((str(r[0]), score))
        scored.sort(key=lambda item: -item[1])
        return [pid for pid, _ in scored[:_MAX_SUGGESTED]]
    except Exception:  # noqa: BLE001 — sugerir guías jamás tumba la entrevista
        logger.warning("guides: no se pudieron sugerir guías para el agente (tenant=%s)",
                       tenant_id, exc_info=True)
        return []


def _tenant(request: Request) -> str:
    tid = getattr(request.state, "tenant_id", None)
    if not tid:
        raise HTTPException(status_code=401, detail="Sin sesión activa")
    return tid


class InterviewRequest(BaseModel):
    kind: str
    messages: Any = None
    matter_id: str | None = None


def _validate_messages(raw: Any) -> list[dict]:
    if not isinstance(raw, list):
        raise HTTPException(status_code=422, detail="El listado de mensajes no es válido.")
    clean: list[dict] = []
    for m in raw:
        if not isinstance(m, dict):
            raise HTTPException(status_code=422, detail="Cada mensaje debe traer rol y contenido.")
        role = m.get("role")
        content = m.get("content")
        if role not in _VALID_ROLES:
            raise HTTPException(status_code=422, detail="Cada mensaje debe traer un rol válido.")
        if not isinstance(content, str) or not content.strip():
            raise HTTPException(status_code=422, detail="Cada mensaje debe traer un contenido de texto.")
        clean.append({"role": role, "content": content})
    return clean


@router.post("/interview")
async def guides_interview(request: Request, body: InterviewRequest):
    tid = _tenant(request)

    if body.kind not in _VALID_KINDS:
        raise HTTPException(status_code=422, detail="Ese tipo de guía no existe.")

    messages = _validate_messages(body.messages)

    try:
        result = await interview(
            kind=body.kind,
            messages=messages,
            tenant_id=tid,
            matter_id=body.matter_id,
            pool=pool,
        )
    except MatterNotFoundError:
        raise HTTPException(status_code=404, detail="Ese asunto no existe.")

    # Bloque C: al cerrar una entrevista de agente, sugerimos guías del despacho que encajan.
    if body.kind == "agente" and isinstance(result, dict) and result.get("done"):
        result["suggested_playbook_ids"] = await _suggest_playbook_ids(
            tid, result.get("draft") or {})
    return result
