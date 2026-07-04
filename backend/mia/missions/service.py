"""Mia · missions.service — CRUD del tablero de misión bajo RLS (CP-E5, Ola 5).

Gobierna `missions` + `mission_milestones` (migración 024) por despacho. Cada método abre su
propia `pool.tenant_connection(tenant_id)` (RLS fail-closed) y no comparte estado entre
despachos. Al crear una misión se VERIFICA que el expediente sea del despacho (la lectura bajo
RLS devuelve 0 filas si es de otro): así la misión nunca apunta a un expediente ajeno pese a
que el FK de Postgres no filtre por tenant.

CONSENT-FIRST: `create_mission(auto_decompose=True)` PROPONE hitos (decompose.py); quedan
'queued' y editables. El abogado aprueba, edita, reordena y marca avance. Nada se auto-ejecuta.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Optional
from uuid import UUID

from ..db import pool
from . import decompose

logger = logging.getLogger("mia.missions.service")

MAX_MISSIONS_PER_MATTER = 20
MAX_MILESTONES_PER_MISSION = 30
MAX_TITLE = 160
MAX_OBJECTIVE = 4000
MAX_OUTCOME = 240
MAX_DETAIL = 2000
VALID_MISSION_STATUS = ("active", "archived")
VALID_MILESTONE_STATUS = ("queued", "active", "done")
VALID_ACTORS = ("mia", "abogado")

_MISSION_COLS = "id, matter_id, title, objective, outcome, status, created_at, updated_at"
_MS_COLS = ("id, mission_id, seq, title, detail, actor, status, is_procedural, "
            "created_at, updated_at")


class MissionError(Exception):
    """Error de validación/propiedad → mensaje en llano para el abogado (HTTP 422)."""


# ── validación (pura) ────────────────────────────────────────────────────────
def _require_uuid(value: str, field_name: str = "id") -> str:
    try:
        return str(UUID(str(value)))
    except (ValueError, TypeError, AttributeError):
        raise MissionError(f"{field_name} inválido.")


def _clean(value: object, *, max_len: int, field_name: str, required: bool = False) -> str:
    text = ("" if value is None else str(value)).strip()
    if required and not text:
        raise MissionError(f"{field_name} es obligatorio.")
    if len(text) > max_len:
        raise MissionError(f"{field_name} es demasiado largo (máx {max_len} caracteres).")
    return text


def _clean_actor(value: object) -> str:
    actor = ("abogado" if value is None else str(value)).strip().lower()
    return actor if actor in VALID_ACTORS else "abogado"


def _clean_milestone_status(value: object) -> str:
    st = ("queued" if value is None else str(value)).strip().lower()
    if st not in VALID_MILESTONE_STATUS:
        raise MissionError("Estado de hito inválido.")
    return st


# ── dominio ──────────────────────────────────────────────────────────────────
@dataclass(frozen=True)
class Milestone:
    id: str
    mission_id: str
    seq: int
    title: str
    detail: str
    actor: str
    status: str
    is_procedural: bool

    def to_public(self) -> dict:
        return {
            "id": self.id, "seq": self.seq, "title": self.title, "detail": self.detail,
            "actor": self.actor, "status": self.status, "is_procedural": self.is_procedural,
        }


@dataclass(frozen=True)
class Mission:
    id: str
    matter_id: str
    title: str
    objective: str
    outcome: str
    status: str
    milestones: list[Milestone] = field(default_factory=list)

    def to_public(self) -> dict:
        done = sum(1 for m in self.milestones if m.status == "done")
        return {
            "id": self.id, "matter_id": self.matter_id, "title": self.title,
            "objective": self.objective, "outcome": self.outcome, "status": self.status,
            "progress": {"done": done, "total": len(self.milestones)},
            "milestones": [m.to_public() for m in self.milestones],
        }


def _row_to_milestone(r: tuple) -> Milestone:
    return Milestone(id=str(r[0]), mission_id=str(r[1]), seq=int(r[2]), title=r[3],
                     detail=r[4], actor=r[5], status=r[6], is_procedural=bool(r[7]))


def _row_to_mission(r: tuple, milestones: list[Milestone]) -> Mission:
    return Mission(id=str(r[0]), matter_id=str(r[1]), title=r[2], objective=r[3],
                   outcome=r[4], status=r[5], milestones=milestones)


class MissionService:
    """Tablero de misión por expediente bajo RLS. Sin estado por request."""

    async def _matter_context(self, conn, matter_id: str) -> tuple[str, str]:
        """Título y descripción del expediente — bajo RLS: 0 filas si es de otro despacho.
        Lanza MissionError si no existe/es ajeno (fail-closed sobre propiedad)."""
        row = await (await conn.execute(
            "SELECT title, COALESCE(description, '') FROM matters WHERE id = %s::uuid",
            (matter_id,),
        )).fetchone()
        if not row:
            raise MissionError("No encuentro ese expediente en el despacho.")
        return str(row[0] or ""), str(row[1] or "")

    async def _load_milestones(self, conn, mission_id: str) -> list[Milestone]:
        rows = await (await conn.execute(
            f"SELECT {_MS_COLS} FROM mission_milestones WHERE mission_id = %s::uuid "
            "ORDER BY seq, created_at", (mission_id,),
        )).fetchall()
        return [_row_to_milestone(r) for r in rows]

    # ── lecturas ──────────────────────────────────────────────────────────────
    async def list_missions(self, tenant_id: str, matter_id: str) -> list[Mission]:
        """Misiones (con sus hitos) de un expediente del despacho, más recientes primero."""
        matter_id = _require_uuid(matter_id, "expediente")
        async with pool.tenant_connection(tenant_id) as conn:
            rows = await (await conn.execute(
                f"SELECT {_MISSION_COLS} FROM missions WHERE matter_id = %s::uuid "
                "ORDER BY created_at DESC", (matter_id,),
            )).fetchall()
            out: list[Mission] = []
            for r in rows:
                milestones = await self._load_milestones(conn, str(r[0]))
                out.append(_row_to_mission(r, milestones))
        return out

    async def get_mission(self, tenant_id: str, mission_id: str) -> Optional[Mission]:
        """Una misión (con hitos), o None si no existe/es de otro despacho (RLS)."""
        mission_id = _require_uuid(mission_id, "misión")
        async with pool.tenant_connection(tenant_id) as conn:
            row = await (await conn.execute(
                f"SELECT {_MISSION_COLS} FROM missions WHERE id = %s::uuid", (mission_id,),
            )).fetchone()
            if not row:
                return None
            milestones = await self._load_milestones(conn, mission_id)
        return _row_to_mission(row, milestones)

    # ── creación + descomposición ───────────────────────────────────────────────
    async def create_mission(
        self, tenant_id: str, matter_id: str, *, title: str, objective: str,
        outcome: str = "", auto_decompose: bool = True,
    ) -> Mission:
        """Crea una misión para un expediente del despacho. Con `auto_decompose` propone los
        hitos (consent-first: quedan 'queued' editables). Expediente ajeno → MissionError."""
        matter_id = _require_uuid(matter_id, "expediente")
        title = _clean(title, max_len=MAX_TITLE, field_name="El título", required=True)
        objective = _clean(objective, max_len=MAX_OBJECTIVE, field_name="El objetivo",
                           required=True)
        outcome = _clean(outcome, max_len=MAX_OUTCOME, field_name="El resultado esperado")

        # Propuesta de hitos ANTES de tomar la conexión (el LLM no debe retener la conexión
        # de DB): valida propiedad del expediente en su propia conexión corta.
        proposed: list[dict] = []
        if auto_decompose:
            async with pool.tenant_connection(tenant_id) as conn:
                m_title, m_desc = await self._matter_context(conn, matter_id)
            proposed = await decompose.propose_milestones(
                objective, matter_title=m_title, matter_description=m_desc)

        async with pool.tenant_connection(tenant_id) as conn:
            # Verifica propiedad del expediente (fail-closed) y tope por expediente.
            await self._matter_context(conn, matter_id)
            count = await (await conn.execute(
                "SELECT count(*) FROM missions WHERE matter_id = %s::uuid", (matter_id,),
            )).fetchone()
            if count and count[0] >= MAX_MISSIONS_PER_MATTER:
                raise MissionError(
                    f"Este expediente ya tiene el máximo de misiones ({MAX_MISSIONS_PER_MATTER}). "
                    "Archiva alguna para crear otra.")
            row = await (await conn.execute(
                "INSERT INTO missions (tenant_id, matter_id, title, objective, outcome) "
                "VALUES (%s::uuid, %s::uuid, %s, %s, %s) "
                f"RETURNING {_MISSION_COLS}",
                (tenant_id, matter_id, title, objective, outcome),
            )).fetchone()
            mission_id = str(row[0])
            for seq, it in enumerate(proposed):
                await conn.execute(
                    "INSERT INTO mission_milestones (tenant_id, mission_id, seq, title, detail, "
                    "actor, status, is_procedural) VALUES (%s::uuid, %s::uuid, %s, %s, %s, %s, "
                    "'queued', %s)",
                    (tenant_id, mission_id, seq, it["title"], it["detail"], it["actor"],
                     it["is_procedural"]),
                )
            milestones = await self._load_milestones(conn, mission_id)
        return _row_to_mission(row, milestones)

    async def decompose_mission(
        self, tenant_id: str, mission_id: str, *, replace: bool = False,
    ) -> Mission:
        """(Re)propone hitos para una misión existente. `replace=True` sustituye los hitos
        actuales (borra los que estén 'queued'/'active'/'done' y crea la nueva propuesta);
        `replace=False` AÑADE la propuesta al final. Consent-first: el abogado lo dispara."""
        mission = await self.get_mission(tenant_id, mission_id)
        if mission is None:
            raise MissionError("No encuentro esa misión en el despacho.")
        async with pool.tenant_connection(tenant_id) as conn:
            m_title, m_desc = await self._matter_context(conn, mission.matter_id)
        proposed = await decompose.propose_milestones(
            mission.objective, matter_title=m_title, matter_description=m_desc)
        async with pool.tenant_connection(tenant_id) as conn:
            if replace:
                await conn.execute(
                    "DELETE FROM mission_milestones WHERE mission_id = %s::uuid", (mission_id,))
                base_seq = 0
            else:
                row = await (await conn.execute(
                    "SELECT COALESCE(max(seq), -1) FROM mission_milestones "
                    "WHERE mission_id = %s::uuid", (mission_id,),
                )).fetchone()
                base_seq = int(row[0]) + 1
            # Tope tras la (re)composición.
            existing = 0 if replace else base_seq
            for i, it in enumerate(proposed):
                if existing + i >= MAX_MILESTONES_PER_MISSION:
                    break
                await conn.execute(
                    "INSERT INTO mission_milestones (tenant_id, mission_id, seq, title, detail, "
                    "actor, status, is_procedural) VALUES (%s::uuid, %s::uuid, %s, %s, %s, %s, "
                    "'queued', %s)",
                    (tenant_id, mission_id, base_seq + i, it["title"], it["detail"], it["actor"],
                     it["is_procedural"]),
                )
            await conn.execute(
                "UPDATE missions SET updated_at = now() WHERE id = %s::uuid", (mission_id,))
            milestones = await self._load_milestones(conn, mission_id)
            mrow = await (await conn.execute(
                f"SELECT {_MISSION_COLS} FROM missions WHERE id = %s::uuid", (mission_id,),
            )).fetchone()
        return _row_to_mission(mrow, milestones)

    # ── edición de la misión ────────────────────────────────────────────────────
    async def update_mission(
        self, tenant_id: str, mission_id: str, *, title: Optional[str] = None,
        objective: Optional[str] = None, outcome: Optional[str] = None,
        status: Optional[str] = None,
    ) -> Mission:
        """Edita campos de la misión (los que lleguen no-None). Ajena → MissionError (RLS)."""
        mission_id = _require_uuid(mission_id, "misión")
        sets: list[str] = []
        params: list[object] = []
        if title is not None:
            sets.append("title = %s")
            params.append(_clean(title, max_len=MAX_TITLE, field_name="El título", required=True))
        if objective is not None:
            sets.append("objective = %s")
            params.append(_clean(objective, max_len=MAX_OBJECTIVE, field_name="El objetivo",
                                 required=True))
        if outcome is not None:
            sets.append("outcome = %s")
            params.append(_clean(outcome, max_len=MAX_OUTCOME, field_name="El resultado esperado"))
        if status is not None:
            st = str(status).strip().lower()
            if st not in VALID_MISSION_STATUS:
                raise MissionError("Estado de misión inválido.")
            sets.append("status = %s")
            params.append(st)
        if not sets:
            raise MissionError("No hay cambios que guardar.")
        sets.append("updated_at = now()")
        params.append(mission_id)
        async with pool.tenant_connection(tenant_id) as conn:
            row = await (await conn.execute(
                f"UPDATE missions SET {', '.join(sets)} WHERE id = %s::uuid "
                f"RETURNING {_MISSION_COLS}", tuple(params),
            )).fetchone()
            if not row:
                raise MissionError("No encuentro esa misión en el despacho.")
            milestones = await self._load_milestones(conn, mission_id)
        return _row_to_mission(row, milestones)

    async def delete_mission(self, tenant_id: str, mission_id: str) -> None:
        """Elimina una misión y sus hitos (CASCADE). Ajena/inexistente → MissionError."""
        mission_id = _require_uuid(mission_id, "misión")
        async with pool.tenant_connection(tenant_id) as conn:
            row = await (await conn.execute(
                "DELETE FROM missions WHERE id = %s::uuid RETURNING id", (mission_id,),
            )).fetchone()
        if not row:
            raise MissionError("No encuentro esa misión en el despacho.")

    # ── hitos ────────────────────────────────────────────────────────────────────
    async def add_milestone(
        self, tenant_id: str, mission_id: str, *, title: str, detail: str = "",
        actor: str = "abogado", is_procedural: bool = False,
    ) -> Mission:
        """Añade un hito manual al final del tablero de una misión del despacho."""
        mission_id = _require_uuid(mission_id, "misión")
        title = _clean(title, max_len=MAX_TITLE, field_name="El título del hito", required=True)
        detail = _clean(detail, max_len=MAX_DETAIL, field_name="El detalle del hito")
        actor = _clean_actor(actor)
        async with pool.tenant_connection(tenant_id) as conn:
            mrow = await (await conn.execute(
                f"SELECT {_MISSION_COLS} FROM missions WHERE id = %s::uuid", (mission_id,),
            )).fetchone()
            if not mrow:
                raise MissionError("No encuentro esa misión en el despacho.")
            row = await (await conn.execute(
                "SELECT COALESCE(max(seq), -1), count(*) FROM mission_milestones "
                "WHERE mission_id = %s::uuid", (mission_id,),
            )).fetchone()
            if row and int(row[1]) >= MAX_MILESTONES_PER_MISSION:
                raise MissionError(
                    f"Esta misión ya tiene el máximo de hitos ({MAX_MILESTONES_PER_MISSION}).")
            next_seq = int(row[0]) + 1 if row else 0
            await conn.execute(
                "INSERT INTO mission_milestones (tenant_id, mission_id, seq, title, detail, "
                "actor, status, is_procedural) VALUES (%s::uuid, %s::uuid, %s, %s, %s, %s, "
                "'queued', %s)",
                (tenant_id, mission_id, next_seq, title, detail, actor, bool(is_procedural)),
            )
            await conn.execute(
                "UPDATE missions SET updated_at = now() WHERE id = %s::uuid", (mission_id,))
            milestones = await self._load_milestones(conn, mission_id)
        return _row_to_mission(mrow, milestones)

    async def update_milestone(
        self, tenant_id: str, milestone_id: str, *, title: Optional[str] = None,
        detail: Optional[str] = None, actor: Optional[str] = None,
        status: Optional[str] = None, seq: Optional[int] = None,
        is_procedural: Optional[bool] = None,
    ) -> Mission:
        """Edita un hito (estado/título/detalle/actor/orden). Devuelve la misión completa."""
        milestone_id = _require_uuid(milestone_id, "hito")
        sets: list[str] = []
        params: list[object] = []
        if title is not None:
            sets.append("title = %s")
            params.append(_clean(title, max_len=MAX_TITLE, field_name="El título del hito",
                                 required=True))
        if detail is not None:
            sets.append("detail = %s")
            params.append(_clean(detail, max_len=MAX_DETAIL, field_name="El detalle del hito"))
        if actor is not None:
            sets.append("actor = %s")
            params.append(_clean_actor(actor))
        if status is not None:
            sets.append("status = %s")
            params.append(_clean_milestone_status(status))
        if seq is not None:
            try:
                sets.append("seq = %s")
                params.append(int(seq))
            except (ValueError, TypeError):
                raise MissionError("Orden de hito inválido.")
        if is_procedural is not None:
            sets.append("is_procedural = %s")
            params.append(bool(is_procedural))
        if not sets:
            raise MissionError("No hay cambios que guardar.")
        sets.append("updated_at = now()")
        params.append(milestone_id)
        async with pool.tenant_connection(tenant_id) as conn:
            row = await (await conn.execute(
                f"UPDATE mission_milestones SET {', '.join(sets)} WHERE id = %s::uuid "
                "RETURNING mission_id", tuple(params),
            )).fetchone()
            if not row:
                raise MissionError("No encuentro ese hito en el despacho.")
            mission_id = str(row[0])
            await conn.execute(
                "UPDATE missions SET updated_at = now() WHERE id = %s::uuid", (mission_id,))
            mrow = await (await conn.execute(
                f"SELECT {_MISSION_COLS} FROM missions WHERE id = %s::uuid", (mission_id,),
            )).fetchone()
            milestones = await self._load_milestones(conn, mission_id)
        return _row_to_mission(mrow, milestones)

    async def delete_milestone(self, tenant_id: str, milestone_id: str) -> Mission:
        """Elimina un hito y devuelve la misión completa. Ajeno/inexistente → MissionError."""
        milestone_id = _require_uuid(milestone_id, "hito")
        async with pool.tenant_connection(tenant_id) as conn:
            row = await (await conn.execute(
                "DELETE FROM mission_milestones WHERE id = %s::uuid RETURNING mission_id",
                (milestone_id,),
            )).fetchone()
            if not row:
                raise MissionError("No encuentro ese hito en el despacho.")
            mission_id = str(row[0])
            await conn.execute(
                "UPDATE missions SET updated_at = now() WHERE id = %s::uuid", (mission_id,))
            mrow = await (await conn.execute(
                f"SELECT {_MISSION_COLS} FROM missions WHERE id = %s::uuid", (mission_id,),
            )).fetchone()
            milestones = await self._load_milestones(conn, mission_id)
        return _row_to_mission(mrow, milestones)


mission_service = MissionService()  # instancia compartida
