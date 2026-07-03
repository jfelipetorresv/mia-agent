"""Mia · api.routes.value — configuración del "valor entregado" (CP-V1, Ola 4).

El panel muestra el VALOR NETO del mes: horas ahorradas × tarifa − costo real de IA.
Este router deja configurar, POR DESPACHO (tenant_settings.config['value'], RLS):

  - hourly_rate_usd  → tarifa horaria del despacho (USD).
  - draft_minutes    → minutos que le ahorra al abogado un BORRADOR aprobado/editado
                       (un escrito revisado listo para firmar).
  - turn_minutes     → minutos que ahorra cada consulta/análisis dentro de un asunto.

Los tres son ESTIMADOS de negocio con defaults declarados (no medición exacta) —
el panel lo dice en llano ("estimado configurable"). §G: sin jerga técnica.

GET  /api/value/settings → valores efectivos + si son los de fábrica
PUT  /api/value/settings → valida y persiste (merge en el JSONB del tenant)
"""
from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request
from psycopg.types.json import Json
from pydantic import BaseModel

from ...db import pool

router = APIRouter(tags=["value"])

# Defaults de fábrica (aplican hasta que el despacho fije los suyos):
#   tarifa 100 USD/h (neutral; ClaudeOS usa 120 USD/h como referencia),
#   borrador aprobado = 120 min (un escrito revisado), consulta = 15 min.
DEFAULT_HOURLY_RATE_USD = 100.0
DEFAULT_DRAFT_MINUTES = 120
DEFAULT_TURN_MINUTES = 15

_RATE_MAX = 10_000.0
_MINUTES_MAX = 600


def _tenant(request: Request) -> str:
    t = getattr(request.state, "tenant_id", None)
    if not t:
        raise HTTPException(status_code=401, detail="Sin contexto de tenant")
    return t


async def value_settings_for(tenant_id: str) -> dict:
    """Valores efectivos del tenant (config['value'] con defaults). Fail-safe:
    ante datos corruptos cae a los defaults (es un estimado, no un candado)."""
    cfg = {}
    try:
        async with pool.tenant_connection(tenant_id) as conn:
            row = await (await conn.execute(
                "SELECT config->'value' FROM tenant_settings WHERE tenant_id = %s::uuid",
                (tenant_id,),
            )).fetchone()
        if row and isinstance(row[0], dict):
            cfg = row[0]
    except Exception:  # noqa: BLE001 — defaults antes que romper el panel
        pass

    def _num(key: str, default: float, maximum: float) -> float:
        try:
            v = float(cfg.get(key, default))
            return v if 0 < v <= maximum else default
        except (TypeError, ValueError):
            return default

    return {
        "hourly_rate_usd": _num("hourly_rate_usd", DEFAULT_HOURLY_RATE_USD, _RATE_MAX),
        "draft_minutes": int(_num("draft_minutes", DEFAULT_DRAFT_MINUTES, _MINUTES_MAX)),
        "turn_minutes": int(_num("turn_minutes", DEFAULT_TURN_MINUTES, _MINUTES_MAX)),
        "is_default": not cfg,
    }


@router.get("/value/settings")
async def get_value_settings(request: Request):
    return await value_settings_for(_tenant(request))


class ValueSettingsBody(BaseModel):
    hourly_rate_usd: float | None = None
    draft_minutes: int | None = None
    turn_minutes: int | None = None


@router.put("/value/settings")
async def put_value_settings(body: ValueSettingsBody, request: Request):
    tid = _tenant(request)
    updates: dict = {}
    if body.hourly_rate_usd is not None:
        if not (0 < body.hourly_rate_usd <= _RATE_MAX):
            raise HTTPException(status_code=422,
                                detail="La tarifa debe ser mayor que 0 y hasta 10.000 USD/hora.")
        updates["hourly_rate_usd"] = float(body.hourly_rate_usd)
    if body.draft_minutes is not None:
        if not (0 < body.draft_minutes <= _MINUTES_MAX):
            raise HTTPException(status_code=422,
                                detail="Los minutos por borrador deben estar entre 1 y 600.")
        updates["draft_minutes"] = int(body.draft_minutes)
    if body.turn_minutes is not None:
        if not (0 < body.turn_minutes <= _MINUTES_MAX):
            raise HTTPException(status_code=422,
                                detail="Los minutos por consulta deben estar entre 1 y 600.")
        updates["turn_minutes"] = int(body.turn_minutes)
    if not updates:
        raise HTTPException(status_code=422, detail="No hay nada que actualizar.")

    async with pool.tenant_connection(tid) as conn:
        # UPSERT con merge del sub-objeto 'value' (JSONB ||), preservando el resto de
        # config. Insert cubre despachos sin fila aún en tenant_settings.
        await conn.execute(
            "INSERT INTO tenant_settings (tenant_id, config) "
            "VALUES (%s::uuid, jsonb_build_object('value', %s::jsonb)) "
            "ON CONFLICT (tenant_id) DO UPDATE SET config = jsonb_set("
            "coalesce(tenant_settings.config, '{}'::jsonb), '{value}', "
            "coalesce(tenant_settings.config->'value', '{}'::jsonb) || %s::jsonb, true)",
            (tid, Json(updates), Json(updates)),
        )
    return await value_settings_for(tid)
