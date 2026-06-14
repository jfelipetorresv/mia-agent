"""Mia · agents.state — MatterState, el estado tipado del grafo (1d · PASO 1).

El estado de un asunto que viaja por el StateGraph. Es un TypedDict (lo que espera
LangGraph); los nodos devuelven actualizaciones PARCIALES que LangGraph fusiona.

`messages` usa el reducer `operator.add`: un nodo que devuelve `{"messages":[m]}`
AÑADE m al historial (no lo reemplaza). El resto de campos son last-write-wins, así
que un nodo que los toca devuelve el valor completo (p. ej. `metadata` se fusiona a
mano leyendo `state.get("metadata", {})`).

Snapshots FROZEN al inicio del asunto (mismo principio que ProfileManager, 2a):
`soul_snapshot` y `profile_snapshot` se capturan al arrancar el asunto y NO cambian
durante el turno, aunque el perfil/SOUL vivos cambien después.
"""
from __future__ import annotations

import operator
from typing import Annotated, Any, Literal, Optional, TypedDict

# Estados HITL del borrador. El abogado nunca ve estas etiquetas (§G): la capa SSE
# las traduce a frases del oficio ("Esperando tu revisión", "Listo").
HitlStatus = Literal["pending", "approved", "rejected", "editing"]


class MatterState(TypedDict, total=False):
    """Estado de un asunto en el grafo. `total=False`: los nodos devuelven parciales."""

    tenant_id: str          # aislamiento RLS (§G) — nunca se mezcla entre despachos
    matter_id: str          # el asunto en curso
    thread_id: str          # "{tenant_id}:{matter_id}" — clave del checkpoint (decisión #9)

    messages: Annotated[list, operator.add]   # mensajes del turno (reducer: append)

    soul_snapshot: Optional[dict]     # copia frozen del SOUL.md al inicio (Módulo 5; hoy None)
    profile_snapshot: Optional[dict]  # copia frozen del perfil al inicio del asunto (2a)

    documents: list                   # documentos recuperados del RAG (intake_node)
    draft: Optional[str]              # borrador actual (None si aún no hay)
    hitl_status: HitlStatus           # pending | approved | rejected | editing
    trace_id: Optional[str]           # id de la traza JSONL activa (finalize_node)
    metadata: dict                    # datos adicionales (diagnóstico, decisión HITL, usage…)


def thread_id_for(tenant_id: str, matter_id: str) -> str:
    """Clave del checkpoint: `{tenant_id}:{matter_id}` (decisión #9).

    Garantiza que el estado de un asunto de un despacho NUNCA se reanude desde el
    contexto de otro: para reanudar hay que reconstruir este thread_id con el tenant
    del JWT, y los endpoints HITL además verifican la propiedad del asunto.
    """
    return f"{tenant_id}:{matter_id}"


def initial_state(
    tenant_id: str,
    matter_id: str,
    user_message: str,
    *,
    profile_snapshot: Optional[dict] = None,
    soul_snapshot: Optional[dict] = None,
) -> MatterState:
    """Estado inicial de un turno a partir del mensaje del abogado.

    Si el caller no pasa `soul_snapshot`, se carga el SOUL.md del despacho desde
    $MIA_HOME (Módulo 5): así la identidad del agente entra al turno real del grafo.
    Sin onboarding (archivo ausente) queda None → el grafo no antepone identidad.
    """
    if soul_snapshot is None:
        from ..onboarding.soul_interview import load_soul_snapshot  # diferido (sin ciclo)
        soul_snapshot = load_soul_snapshot(tenant_id)
    return MatterState(
        tenant_id=tenant_id,
        matter_id=matter_id,
        thread_id=thread_id_for(tenant_id, matter_id),
        messages=[{"role": "user", "content": user_message}],
        soul_snapshot=soul_snapshot,
        profile_snapshot=profile_snapshot,
        documents=[],
        draft=None,
        hitl_status="pending",
        trace_id=None,
        metadata={},
    )
