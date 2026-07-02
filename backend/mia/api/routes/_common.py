"""Mia · api.routes._common — helpers compartidos por los routers de 1d."""
from __future__ import annotations

import json
import uuid
from typing import Any

from fastapi import HTTPException

from ...db import pool
from ...memory.profile_manager import ProfileManager
from ...agents.state import thread_id_for

# Límite duro de subida de documentos (50 MB) — evita DoS por memoria.
MAX_UPLOAD_BYTES = 50 * 1024 * 1024


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


def require_uuid(value: str, field: str = "identificador") -> str:
    """CP-S3: valida que un id de ruta sea un UUID ANTES de tocar la DB.

    Un id mal formado se rechaza con 400 en lugar de llegar crudo a SQL (donde
    provocaría un 500 técnico o, sin RLS, una lectura indebida). Complementa la
    barrera de RLS: forma correcta + aislamiento por tenant."""
    if not _is_uuid(value):
        raise HTTPException(status_code=400, detail=f"El {field} no es válido.")
    return str(value)


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


def firm_profile_to_snapshot(prof: dict) -> dict:
    """Convierte firm_profiles (DB) al dict que espera el grafo (_render_profile)."""
    abogado_parts: list[str] = []
    if prof.get("lawyer_name"):
        abogado_parts.append(f"Nombre: {prof['lawyer_name']}")
    if prof.get("tp_number"):
        abogado_parts.append(f"Tarjeta profesional: {prof['tp_number']}")
    if prof.get("practice_areas"):
        abogado_parts.append(f"Áreas: {prof['practice_areas']}")
    despacho_parts: list[str] = []
    if prof.get("name"):
        despacho_parts.append(f"Despacho: {prof['name']}")
    if prof.get("jurisdiction"):
        despacho_parts.append(f"Jurisdicción: {prof['jurisdiction']}")
    if prof.get("voice_adjectives"):
        despacho_parts.append(f"Voz: {prof['voice_adjectives']}")
    if prof.get("preferred_sources"):
        despacho_parts.append(f"Fuentes preferidas: {prof['preferred_sources']}")
    if prof.get("hard_nos"):
        despacho_parts.append(f"Restricciones: {prof['hard_nos']}")
    return {"abogado": "\n".join(abogado_parts), "despacho": "\n".join(despacho_parts)}


async def load_profile_snapshot(tenant_id: str) -> dict | None:
    """Perfil frozen para el turno: lee firm_profiles bajo RLS."""
    prof = await ProfileManager(pool=pool, tenant_id=tenant_id).get_firm_profile(tenant_id)
    if not prof:
        return None
    snap = firm_profile_to_snapshot(prof)
    if not snap["abogado"].strip() and not snap["despacho"].strip():
        return None
    return snap


async def prepare_new_turn(checkpointer: Any, graph: Any, tenant_id: str, matter_id: str) -> dict:
    """Valida el ciclo de vida del checkpoint antes de un turno nuevo.

    - Si hay interrupt pendiente (borrador sin revisar) → 409.
    - Si el turno anterior ya terminó (grafo en END) → borra el checkpoint para
      que LangGraph pueda arrancar intake→analysis→draft de nuevo con el mismo thread_id.
    """
    cfg = {"configurable": {"thread_id": thread_id_for(tenant_id, matter_id)}}
    st = await graph.aget_state(cfg)
    if st and st.next:
        raise HTTPException(
            status_code=409,
            detail="Tienes un borrador pendiente de revisión. Apruébalo o recházalo antes de continuar.",
        )
    if st and st.values:
        await checkpointer.adelete_thread(cfg["configurable"]["thread_id"])
    return cfg


async def require_awaiting_review(graph: Any, cfg: dict) -> None:
    """409 si el grafo no está pausado en hitl_checkpoint."""
    st = await graph.aget_state(cfg)
    if not st or not st.next:
        raise HTTPException(status_code=409, detail="No hay borrador pendiente de revisión.")
