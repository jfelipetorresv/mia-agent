"""Mia · policy.budget — tope de gasto de IA por despacho (CP-E1, Ola 5).

CP-V1 empezó a MEDIR el gasto real del LLM (tabla `turn_usage`), pero nada lo
LIMITABA: un despacho podía gastar sin techo. Esta política deja fijar un
presupuesto MENSUAL en dólares por despacho; al alcanzarlo, los turnos nuevos se
bloquean con un mensaje en llano hasta que el abogado suba el tope o llegue el mes
siguiente. Es control ACTIVO (puede bloquear), a diferencia de la auditoría.

Reglas de diseño:
  - El presupuesto vive en `tenant_settings.config['policy']['monthly_budget_usd']`
    (jsonb). Ausente, null o <= 0 = SIN límite (el caso por defecto de casi todos).
  - El gasto del mes = SUMA de `turn_usage.cost_usd` del mes calendario UTC en curso,
    bajo RLS del tenant. (Los alias locales/suscripción cuestan 0 — ver metrics/usage.)
  - FAIL-OPEN a propósito: si NO se puede leer el presupuesto o el gasto (DB caída,
    dato corrupto), se PERMITE el turno. Frenar el trabajo legítimo de un abogado por
    un hipo de infraestructura es peor que un posible sobregasto marginal; el error
    se loguea. (Distinto de los candados de confidencialidad, que son fail-closed:
    aquí no hay dato sensible en juego, solo dinero, y el tope es una guardia blanda.)

Límite conocido (declarado): metrics/usage bufferiza el gasto y lo persiste en
lotes → el gasto del mes puede ir unos segundos/minutos atrasado. Para un tope de
costo es una holgura aceptable, no una fuga.
"""
from __future__ import annotations

import logging

logger = logging.getLogger("mia.policy.budget")


class BudgetExceeded(Exception):
    """El despacho alcanzó su tope de gasto de IA del mes. `str(e)` es apto para
    mostrarse al abogado (lenguaje llano, sin jerga)."""


_OVER_BUDGET_MESSAGE = (
    "Este despacho alcanzó su tope de gasto de IA de este mes. "
    "Súbelo en el Panel de control o espera al próximo mes para seguir."
)


async def get_monthly_budget(tenant_id: str) -> float | None:
    """Presupuesto mensual en USD del despacho, o None si no hay tope. Lee
    `config['policy']['monthly_budget_usd']`; cualquier valor no numérico o <= 0
    se interpreta como SIN límite."""
    from ..db import pool

    async with pool.tenant_connection(tenant_id) as conn:
        row = await (await conn.execute(
            "SELECT config->'policy'->'monthly_budget_usd' "
            "FROM tenant_settings WHERE tenant_id = %s::uuid",
            (tenant_id,),
        )).fetchone()
    if not row or row[0] is None:
        return None
    try:
        val = float(row[0])
    except (TypeError, ValueError):
        return None
    return val if val > 0 else None


async def set_monthly_budget(tenant_id: str, value: float | None) -> None:
    """Fija (o quita) el tope mensual. `value` None o <= 0 = SIN límite (guarda
    null). Upsert sobre tenant_settings.config['policy']['monthly_budget_usd']."""
    from ..db import pool

    if value is not None and value <= 0:
        value = None
    async with pool.tenant_connection(tenant_id) as conn:
        # jsonb_set con create_missing NO crea el objeto intermedio 'policy' si falta
        # (hallazgo capa 2 BLOQUEANTE): y TODO tenant nace con config='{}', así que la
        # rama UPDATE es la única de producción. Se fija el objeto 'policy' entero,
        # fusionando (||) sobre el 'policy' existente para no pisar otras claves futuras.
        await conn.execute(
            "INSERT INTO tenant_settings (tenant_id, config) "
            "VALUES (%s::uuid, jsonb_build_object('policy', "
            "  jsonb_build_object('monthly_budget_usd', to_jsonb(%s::numeric)))) "
            "ON CONFLICT (tenant_id) DO UPDATE SET config = jsonb_set("
            "  COALESCE(tenant_settings.config, '{}'::jsonb), '{policy}', "
            "  COALESCE(tenant_settings.config->'policy', '{}'::jsonb) "
            "  || jsonb_build_object('monthly_budget_usd', to_jsonb(%s::numeric)), true)",
            (tenant_id, value, value),
        )


async def month_to_date_cost(tenant_id: str) -> float:
    """Gasto de IA (USD) del mes calendario UTC en curso, bajo RLS del tenant."""
    from ..db import pool

    async with pool.tenant_connection(tenant_id) as conn:
        # Borde del mes anclado en UTC como timestamptz: el `AT TIME ZONE 'UTC'`
        # interno da un timestamp NAIVE que Postgres reinterpretaría en la zona de
        # sesión (el servidor está en America/Bogota, -5h) → el 2º `AT TIME ZONE 'UTC'`
        # lo vuelve timestamptz correcto (hallazgo capa 2: sin esto, el gasto de las
        # primeras 5h de cada mes UTC caía en el mes anterior).
        row = await (await conn.execute(
            "SELECT COALESCE(SUM(cost_usd), 0) FROM turn_usage "
            "WHERE created_at >= "
            "  date_trunc('month', now() AT TIME ZONE 'UTC') AT TIME ZONE 'UTC'",
        )).fetchone()
    return float(row[0]) if row and row[0] is not None else 0.0


async def budget_status(tenant_id: str) -> dict:
    """Estado del tope para el Panel: presupuesto, gasto del mes, restante, si se
    superó, y si es ilimitado. Lenguaje de datos, listo para pantalla."""
    budget = await get_monthly_budget(tenant_id)
    spent = await month_to_date_cost(tenant_id)
    if budget is None:
        return {
            "monthly_budget_usd": None,
            "spent_this_month_usd": round(spent, 2),
            "remaining_usd": None,
            "over_budget": False,
            "unlimited": True,
        }
    return {
        "monthly_budget_usd": round(budget, 2),
        "spent_this_month_usd": round(spent, 2),
        "remaining_usd": round(max(0.0, budget - spent), 2),
        "over_budget": spent >= budget,
        "unlimited": False,
    }


async def enforce_budget(tenant_id: str) -> None:
    """Guardia de gasto para las entradas de turno. Lanza BudgetExceeded si el
    despacho fijó un tope y ya lo alcanzó este mes. FAIL-OPEN: si no se puede leer
    el tope o el gasto, PERMITE el turno (se loguea) — ver el docstring del módulo."""
    try:
        budget = await get_monthly_budget(tenant_id)
        if budget is None:
            return
        spent = await month_to_date_cost(tenant_id)
    except Exception:  # noqa: BLE001 — fail-open: no frenar por un hipo de infraestructura
        logger.exception("no se pudo evaluar el tope de gasto (tenant=%s) — se permite",
                         tenant_id)
        return
    if spent >= budget:
        raise BudgetExceeded(_OVER_BUDGET_MESSAGE)
