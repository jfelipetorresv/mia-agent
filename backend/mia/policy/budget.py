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
  - La lectura informativa sigue fail-open para no tumbar una pantalla por un hipo.
    La llamada PAGADA es distinta: reserva saldo de forma atómica antes de salir. Si
    no puede comprobarlo, el router usa un respaldo gratuito o detiene solo ese cobro.
  - `turn_usage` conserva el detalle visible. `ai_budget_months` es el saldo autoritativo
    desde la primera reserva del mes, evitando que el buffer cause carreras o doble conteo.
  - Un hold interrumpido vence como estimación prudente: no es una factura, sino la
    protección necesaria para que un corte incierto nunca abra un hueco de sobregasto.
"""
from __future__ import annotations

import logging
import time
from datetime import datetime, timezone
from typing import Any

import psycopg

logger = logging.getLogger("mia.policy.budget")


class BudgetExceeded(Exception):
    """El despacho alcanzó su tope de gasto de IA del mes. `str(e)` es apto para
    mostrarse al abogado (lenguaje llano, sin jerga)."""


class BudgetControlUnavailable(Exception):
    """No fue posible asegurar una llamada pagada; el router debe usar motor local."""


_OVER_BUDGET_MESSAGE = (
    "Este despacho alcanzó su tope de gasto de IA de este mes. "
    "Súbelo en Configuración o espera al próximo mes para seguir."
)

_CONTROL_UNAVAILABLE_MESSAGE = (
    "No pude comprobar el saldo disponible. Mia usará el motor local para proteger el tope."
)
HOLD_MINUTES = 15


def _period_start() -> str:
    now = datetime.now(timezone.utc)
    return f"{now.year:04d}-{now.month:02d}-01"


def _sync_conn() -> psycopg.Connection:
    from .. import config
    if not config.DATABASE_URL:
        raise RuntimeError("DATABASE_URL no está configurada")
    return psycopg.connect(config.DATABASE_URL)


def _lock_month(conn: Any, tenant_id: str, period: str) -> None:
    conn.execute("SELECT pg_advisory_xact_lock(hashtextextended(%s, 0))",
                 (f"mia-budget:{tenant_id}:{period}",))


def _ensure_month(conn: Any, tenant_id: str, period: str) -> None:
    conn.execute(
        "INSERT INTO ai_budget_months (tenant_id, period_start, baseline_usd, spent_usd) "
        "SELECT %s::uuid, %s::date, COALESCE(SUM(cost_usd), 0), COALESCE(SUM(cost_usd), 0) "
        "FROM turn_usage WHERE created_at >= %s::date::timestamp AT TIME ZONE 'UTC' "
        "ON CONFLICT (tenant_id, period_start) DO NOTHING",
        (tenant_id, period, period),
    )


def _expire_stale(conn: Any, tenant_id: str, period: str) -> None:
    """Un corte incierto se cobra por la reserva: nunca libera gasto posiblemente hecho."""
    row = conn.execute(
        "WITH expired AS (UPDATE ai_budget_holds SET status='expired', "
        "actual_usd=estimated_usd, finished_at=now() WHERE tenant_id=%s::uuid "
        "AND period_start=%s::date AND status='active' AND expires_at<=now() "
        "RETURNING estimated_usd) SELECT COALESCE(SUM(estimated_usd), 0) FROM expired",
        (tenant_id, period),
    ).fetchone()
    expired = float(row[0]) if row else 0.0
    if expired:
        conn.execute(
            "UPDATE ai_budget_months SET reserved_usd=GREATEST(0, reserved_usd-%s), "
            "spent_usd=spent_usd+%s, updated_at=now() "
            "WHERE tenant_id=%s::uuid AND period_start=%s::date",
            (expired, expired, tenant_id, period),
        )


def reserve_call_sync(tenant_id: str, estimated_usd: float, *, model: str,
                      task: str | None) -> str | None:
    """Aparta saldo atómicamente antes de una llamada pagada. None si cuesta cero."""
    if estimated_usd <= 0:
        return None
    period = _period_start()
    try:
        blocked = False
        hold_id: str | None = None
        with _sync_conn() as conn:
            conn.execute("SELECT set_config('app.tenant_id', %s, true)", (tenant_id,))
            _lock_month(conn, tenant_id, period)
            _ensure_month(conn, tenant_id, period)
            _expire_stale(conn, tenant_id, period)
            row = conn.execute(
                "SELECT m.spent_usd, m.reserved_usd, "
                "s.config->'policy'->'monthly_budget_usd' FROM ai_budget_months m "
                "LEFT JOIN tenant_settings s ON s.tenant_id=m.tenant_id "
                "WHERE m.tenant_id=%s::uuid AND m.period_start=%s::date FOR UPDATE OF m",
                (tenant_id, period),
            ).fetchone()
            spent, reserved, raw_budget = float(row[0]), float(row[1]), row[2]
            try:
                monthly = float(raw_budget) if raw_budget is not None else None
            except (TypeError, ValueError):
                monthly = None
            if monthly is not None and monthly > 0 and spent + reserved + estimated_usd > monthly:
                blocked = True
            else:
                hold = conn.execute(
                    "INSERT INTO ai_budget_holds "
                    "(tenant_id, period_start, estimated_usd, model, task, expires_at) "
                    "VALUES (%s::uuid,%s::date,%s,%s,%s,now()+(%s*interval '1 minute')) "
                    "RETURNING id",
                    (tenant_id, period, estimated_usd, model[:128], (task or "")[:64] or None,
                     HOLD_MINUTES),
                ).fetchone()
                conn.execute(
                    "UPDATE ai_budget_months SET reserved_usd=reserved_usd+%s, updated_at=now() "
                    "WHERE tenant_id=%s::uuid AND period_start=%s::date",
                    (estimated_usd, tenant_id, period),
                )
                hold_id = str(hold[0])
        if blocked:
            raise BudgetExceeded(_OVER_BUDGET_MESSAGE)
        return hold_id
    except BudgetExceeded:
        raise
    except Exception as exc:
        logger.exception("no se pudo reservar gasto de IA (tenant=%s model=%s)", tenant_id, model)
        raise BudgetControlUnavailable(_CONTROL_UNAVAILABLE_MESSAGE) from exc


def _finish_call_once(tenant_id: str, hold_id: str | None,
                      actual_usd: float | None) -> bool:
    if not hold_id:
        return True
    try:
        with _sync_conn() as conn:
            conn.execute("SELECT set_config('app.tenant_id', %s, true)", (tenant_id,))
            row = conn.execute(
                "SELECT estimated_usd, period_start FROM ai_budget_holds "
                "WHERE id=%s::uuid AND tenant_id=%s::uuid AND status='active'",
                (hold_id, tenant_id),
            ).fetchone()
            if not row:
                return True
            hold_period = row[1]
            _lock_month(conn, tenant_id, hold_period.isoformat())
            row = conn.execute(
                "SELECT estimated_usd, period_start FROM ai_budget_holds "
                "WHERE id=%s::uuid AND tenant_id=%s::uuid AND status='active' FOR UPDATE",
                (hold_id, tenant_id),
            ).fetchone()
            if not row:
                return True
            estimated, hold_period = float(row[0]), row[1]
            settled = actual_usd is not None
            actual = max(0.0, float(actual_usd or 0.0))
            conn.execute(
                "UPDATE ai_budget_holds SET status=%s, actual_usd=%s, finished_at=now() "
                "WHERE id=%s::uuid",
                ("settled" if settled else "released", actual if settled else None, hold_id),
            )
            conn.execute(
                "UPDATE ai_budget_months SET reserved_usd=GREATEST(0,reserved_usd-%s), "
                "spent_usd=spent_usd+%s, updated_at=now() "
                "WHERE tenant_id=%s::uuid AND period_start=%s::date",
                (estimated, actual if settled else 0.0, tenant_id, hold_period),
            )
        return True
    except Exception:
        logger.exception("no se pudo liquidar reserva de gasto %s (tenant=%s)", hold_id, tenant_id)
        return False


def finish_call_sync(tenant_id: str, hold_id: str | None, actual_usd: float | None) -> bool:
    """Liquida o libera con reintentos breves; nunca rompe una respuesta ya obtenida.

    Si el proceso muere o la base sigue caída, la reserva queda activa y vence como
    estimación prudente. No es una factura: evita que una caída permita sobregasto.
    """
    for attempt in range(3):
        if _finish_call_once(tenant_id, hold_id, actual_usd):
            return True
        if attempt < 2:
            time.sleep(0.1 * (attempt + 1))
    logger.error("reserva %s sigue pendiente tras 3 intentos; vencerá de forma prudente", hold_id)
    return False


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
        period = _period_start()
        await conn.execute(
            "SELECT pg_advisory_xact_lock(hashtextextended(%s, 0))",
            (f"mia-budget:{tenant_id}:{period}",),
        )
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
        period = _period_start()
        account = await (await conn.execute(
            "SELECT spent_usd FROM ai_budget_months "
            "WHERE tenant_id=%s::uuid AND period_start=%s::date",
            (tenant_id, period),
        )).fetchone()
        if account:
            return float(account[0])
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
    reserved = 0.0
    try:
        from ..db import pool
        async with pool.tenant_connection(tenant_id) as conn:
            row = await (await conn.execute(
                "SELECT reserved_usd FROM ai_budget_months "
                "WHERE tenant_id=%s::uuid AND period_start=%s::date",
                (tenant_id, _period_start()),
            )).fetchone()
            reserved = float(row[0]) if row else 0.0
    except Exception:
        logger.exception("no se pudo leer el saldo reservado (tenant=%s)", tenant_id)
    if budget is None:
        return {
            "monthly_budget_usd": None,
            "spent_this_month_usd": round(spent, 2),
            "reserved_usd": round(reserved, 2),
            "remaining_usd": None,
            "over_budget": False,
            "unlimited": True,
        }
    return {
        "monthly_budget_usd": round(budget, 2),
        "spent_this_month_usd": round(spent, 2),
        "reserved_usd": round(reserved, 2),
        "remaining_usd": round(max(0.0, budget - spent - reserved), 2),
        "over_budget": spent + reserved >= budget,
        "unlimited": False,
    }


async def enforce_budget(tenant_id: str) -> None:
    """Guardia de gasto para las entradas de turno. Lanza BudgetExceeded si el
    despacho fijó un tope y ya lo alcanzó este mes. FAIL-OPEN: si no se puede leer
    el tope o el gasto, PERMITE el turno (se loguea) — ver el docstring del módulo."""
    try:
        status = await budget_status(tenant_id)
    except Exception:  # noqa: BLE001 — fail-open: no frenar por un hipo de infraestructura
        logger.exception("no se pudo evaluar el tope de gasto (tenant=%s) — se permite",
                         tenant_id)
        return
    if status.get("over_budget"):
        raise BudgetExceeded(_OVER_BUDGET_MESSAGE)
