"""Mia · api.routes.missions — tablero de misión por expediente (CP-E5, Ola 5).

El abogado ve, para un expediente, sus MISIONES (objetivos grandes descompuestos en HITOS
visibles) y las gobierna: crear (con propuesta automática de hitos), editar, reordenar y
marcar avance. Consent-first: la propuesta de hitos es editable; nada se ejecuta solo.

Auth: el middleware JWT fija `request.state.tenant_id` (RLS). §G: errores sin jerga técnica.
"""
from __future__ import annotations

import logging

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field

from ...missions import mission_service
from ...missions.service import MissionError

router = APIRouter(prefix="/missions", tags=["missions"])
logger = logging.getLogger("mia.api.missions")


def _tenant(request: Request) -> str:
    tid = getattr(request.state, "tenant_id", None)
    if not tid:
        raise HTTPException(status_code=401, detail="Sin sesión activa")
    return tid


def _svc_error(op: str, tid: str, exc: Exception) -> HTTPException:
    logger.exception("%s falló (tenant=%s): %s", op, tid, exc)
    return HTTPException(
        status_code=502, detail="No pude completar la acción en este momento. Intenta de nuevo.")


class CreateMissionBody(BaseModel):
    matter_id: str
    title: str = Field(min_length=1, max_length=160)
    objective: str = Field(min_length=1, max_length=4000)
    outcome: str | None = ""
    auto_decompose: bool = True


class UpdateMissionBody(BaseModel):
    title: str | None = None
    objective: str | None = None
    outcome: str | None = None
    status: str | None = None


class DecomposeBody(BaseModel):
    replace: bool = False


class MilestoneBody(BaseModel):
    title: str = Field(min_length=1, max_length=160)
    detail: str | None = ""
    actor: str | None = "abogado"
    is_procedural: bool = False


class UpdateMilestoneBody(BaseModel):
    title: str | None = None
    detail: str | None = None
    actor: str | None = None
    status: str | None = None
    seq: int | None = None
    is_procedural: bool | None = None


@router.get("")
async def list_missions(matter_id: str, request: Request):
    """Misiones (con hitos) de un expediente del despacho."""
    tid = _tenant(request)
    try:
        missions = await mission_service.list_missions(tid, matter_id)
        return {"missions": [m.to_public() for m in missions]}
    except MissionError as e:
        raise HTTPException(status_code=422, detail=str(e))
    except Exception as e:  # noqa: BLE001
        raise _svc_error("list_missions", tid, e)


@router.get("/{mission_id}")
async def get_mission(mission_id: str, request: Request):
    """Una misión con sus hitos."""
    tid = _tenant(request)
    try:
        mission = await mission_service.get_mission(tid, mission_id)
        if mission is None:
            raise HTTPException(status_code=404, detail="No encuentro esa misión.")
        return mission.to_public()
    except MissionError as e:
        raise HTTPException(status_code=422, detail=str(e))
    except HTTPException:
        raise
    except Exception as e:  # noqa: BLE001
        raise _svc_error("get_mission", tid, e)


@router.post("")
async def create_mission(body: CreateMissionBody, request: Request):
    """Crea una misión y (por defecto) propone sus hitos automáticamente."""
    tid = _tenant(request)
    try:
        mission = await mission_service.create_mission(
            tid, body.matter_id, title=body.title, objective=body.objective,
            outcome=body.outcome or "", auto_decompose=body.auto_decompose)
        return mission.to_public()
    except MissionError as e:
        raise HTTPException(status_code=422, detail=str(e))
    except Exception as e:  # noqa: BLE001
        raise _svc_error("create_mission", tid, e)


@router.post("/{mission_id}/decompose")
async def decompose_mission(mission_id: str, body: DecomposeBody, request: Request):
    """(Re)propone hitos para una misión (añade al final o reemplaza, según `replace`)."""
    tid = _tenant(request)
    try:
        mission = await mission_service.decompose_mission(tid, mission_id, replace=body.replace)
        return mission.to_public()
    except MissionError as e:
        raise HTTPException(status_code=422, detail=str(e))
    except Exception as e:  # noqa: BLE001
        raise _svc_error("decompose_mission", tid, e)


@router.put("/{mission_id}")
async def update_mission(mission_id: str, body: UpdateMissionBody, request: Request):
    """Edita la misión (título/objetivo/resultado/estado)."""
    tid = _tenant(request)
    try:
        mission = await mission_service.update_mission(
            tid, mission_id, title=body.title, objective=body.objective,
            outcome=body.outcome, status=body.status)
        return mission.to_public()
    except MissionError as e:
        raise HTTPException(status_code=422, detail=str(e))
    except Exception as e:  # noqa: BLE001
        raise _svc_error("update_mission", tid, e)


@router.delete("/{mission_id}")
async def delete_mission(mission_id: str, request: Request):
    """Elimina una misión y sus hitos."""
    tid = _tenant(request)
    try:
        await mission_service.delete_mission(tid, mission_id)
        return {"ok": True}
    except MissionError as e:
        raise HTTPException(status_code=422, detail=str(e))
    except Exception as e:  # noqa: BLE001
        raise _svc_error("delete_mission", tid, e)


@router.post("/{mission_id}/milestones")
async def add_milestone(mission_id: str, body: MilestoneBody, request: Request):
    """Añade un hito manual al tablero."""
    tid = _tenant(request)
    try:
        mission = await mission_service.add_milestone(
            tid, mission_id, title=body.title, detail=body.detail or "",
            actor=body.actor or "abogado", is_procedural=body.is_procedural)
        return mission.to_public()
    except MissionError as e:
        raise HTTPException(status_code=422, detail=str(e))
    except Exception as e:  # noqa: BLE001
        raise _svc_error("add_milestone", tid, e)


@router.put("/{mission_id}/milestones/{milestone_id}")
async def update_milestone(mission_id: str, milestone_id: str,
                           body: UpdateMilestoneBody, request: Request):
    """Edita un hito (estado/título/detalle/actor/orden). Devuelve la misión completa."""
    tid = _tenant(request)
    try:
        mission = await mission_service.update_milestone(
            tid, milestone_id, title=body.title, detail=body.detail, actor=body.actor,
            status=body.status, seq=body.seq, is_procedural=body.is_procedural)
        return mission.to_public()
    except MissionError as e:
        raise HTTPException(status_code=422, detail=str(e))
    except Exception as e:  # noqa: BLE001
        raise _svc_error("update_milestone", tid, e)


@router.delete("/{mission_id}/milestones/{milestone_id}")
async def delete_milestone(mission_id: str, milestone_id: str, request: Request):
    """Elimina un hito. Devuelve la misión completa."""
    tid = _tenant(request)
    try:
        mission = await mission_service.delete_milestone(tid, milestone_id)
        return mission.to_public()
    except MissionError as e:
        raise HTTPException(status_code=422, detail=str(e))
    except Exception as e:  # noqa: BLE001
        raise _svc_error("delete_milestone", tid, e)
