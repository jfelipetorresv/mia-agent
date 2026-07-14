"""Mia · metrics.usage — registro del USO REAL del LLM por llamada (CP-V1, Ola 4).

Hasta CP-V1, `resp.usage` (tokens reales que devuelve TODA respuesta del gateway,
incluido el CLI de la suscripción) se descartaba, y el costo del panel era una
estimación con tarifa fija. Este módulo lo captura en el ÚNICO cuello de botella
(agent/llm.call_llm) y lo persiste en la tabla `turn_usage` (RLS por tenant).

Diseño:
  - SCOPE por ContextVar: el middleware (requests) y tenant_model_policy (cron)
    fijan (tenant_id, matter_id, source); call_llm corre en threads vía
    asyncio.to_thread, que COPIA el contexto → el scope viaja solo.
  - `record()` es sync, barato y JAMÁS lanza: bufferiza en memoria (lock + cota).
  - `flush_pending()` (async) drena el buffer e inserta por tenant bajo RLS.
    Lo llama un flusher periódico del lifespan del API (y el shutdown).
  - Sin scope (gates offline, scripts) `record()` es un no-op.

Los registros son de MÉTRICA, no de facturación: ante un fallo persistente de DB
se reintenta de forma acotada y luego se descarta con log (nunca romper un turno).
"""
from __future__ import annotations

import json
import logging
import threading
from contextvars import ContextVar, Token
from typing import Any

logger = logging.getLogger("mia.metrics.usage")

# ── Precios (USD por 1M de tokens: entrada, salida) por ALIAS del gateway ──────
# Fuente: tabla oficial de Anthropic (consultada 2026-07-02):
#   claude-sonnet-4-6 → $3.00 / $15.00 · claude-haiku-4-5 → $1.00 / $5.00.
# `openrouter-sonnet` sirve el MISMO modelo vía OpenRouter: se aproxima al precio
# base (el fee de OpenRouter no se modela en v1). `cli-*` (suscripción de Claude
# del abogado) y `mia-local` (Ollama) tienen costo MARGINAL cero para el despacho.
# Un alias desconocido cuesta 0 con un aviso único (mejor subreportar que inventar).
PRICES_PER_MTOK: dict[str, tuple[float, float]] = {
    "claude-sonnet": (3.00, 15.00),
    "claude-haiku": (1.00, 5.00),
    "openrouter-sonnet": (3.00, 15.00),
    "openrouter-haiku": (1.00, 5.00),
    "cli-claude": (0.0, 0.0),
    "cli-claude-haiku": (0.0, 0.0),
    "mia-local": (0.0, 0.0),
}

FREE_ALIASES = frozenset({"cli-claude", "cli-claude-haiku", "mia-local"})
UNKNOWN_ALIAS_RATES = (3.00, 15.00)

_scope: ContextVar[tuple[str, str | None, str] | None] = ContextVar(
    "mia_usage_scope", default=None
)

_buffer: list[dict] = []
_lock = threading.Lock()
# Cota del buffer: si el flusher muere o la DB está caída, no crecer sin límite.
MAX_BUFFER = 10_000

_warned_unknown_alias: set[str] = set()


# ── Scope ───────────────────────────────────────────────────────────────────────
def set_usage_scope(tenant_id: str, matter_id: str | None = None,
                    source: str = "api") -> Token:
    """Fija el scope de registro del contexto actual. Devuelve el token para reset."""
    return _scope.set((str(tenant_id), matter_id, source))


def reset_usage_scope(token: Token) -> None:
    _scope.reset(token)


def current_scope() -> tuple[str, str | None, str] | None:
    return _scope.get()


# ── Costo ───────────────────────────────────────────────────────────────────────
def cost_usd(alias: str, prompt_tokens: int, completion_tokens: int) -> float:
    """Costo en USD de una llamada según la tabla de precios del alias."""
    rates = PRICES_PER_MTOK.get(alias)
    if rates is None:
        if alias not in _warned_unknown_alias:
            _warned_unknown_alias.add(alias)
            logger.warning("alias sin precio en PRICES_PER_MTOK: '%s' → se usa tarifa "
                           "conservadora de Sonnet", alias)
        rates = UNKNOWN_ALIAS_RATES
    in_rate, out_rate = rates
    return (prompt_tokens * in_rate + completion_tokens * out_rate) / 1_000_000.0


def estimated_call_cost(alias: str, messages: list[dict], max_tokens: int | None,
                        *, task: str | None = None, tools: list | None = None) -> float:
    """Reserva conservadora antes de una llamada pagada; los aliases gratis dan cero."""
    if alias in FREE_ALIASES:
        return 0.0
    rates = PRICES_PER_MTOK.get(alias, UNKNOWN_ALIAS_RATES)
    try:
        payload = json.dumps({"messages": messages, "tools": tools or []}, ensure_ascii=False,
                             default=str)
        prompt_tokens = max(1, (len(payload) + 3) // 4)
    except Exception:  # pragma: no cover
        prompt_tokens = 32_000
    completion_tokens = int(max_tokens or (8_192 if task in (None, "main", "curator") else 4_096))
    completion_tokens = max(1, min(completion_tokens, 64_000))
    in_rate, out_rate = rates
    return round((prompt_tokens * in_rate + completion_tokens * out_rate) / 1_000_000.0, 6)


# ── Registro (sync, nunca lanza) ────────────────────────────────────────────────
def record(alias: str, task: str | None, usage: Any) -> None:
    """Bufferiza el uso de UNA llamada al LLM. Sin scope o sin usage → no-op."""
    try:
        scope = _scope.get()
        if scope is None or usage is None:
            return
        tenant_id, matter_id, source = scope
        prompt = int(getattr(usage, "prompt_tokens", 0) or 0)
        completion = int(getattr(usage, "completion_tokens", 0) or 0)
        total = int(getattr(usage, "total_tokens", 0) or 0) or (prompt + completion)
        row = {
            "tenant_id": tenant_id,
            "matter_id": matter_id,
            "task": (task or "")[:64] or None,
            "model": str(alias)[:128],
            "prompt_tokens": prompt,
            "completion_tokens": completion,
            "total_tokens": total,
            "cost_usd": round(cost_usd(alias, prompt, completion), 6),
            "source": source[:32],
        }
        with _lock:
            if len(_buffer) >= MAX_BUFFER:
                # Descarta lo MÁS VIEJO: métricas recientes valen más que históricas.
                del _buffer[: MAX_BUFFER // 10]
                logger.warning("buffer de uso lleno (%d): se descartó el 10%% más viejo",
                               MAX_BUFFER)
            _buffer.append(row)
    except Exception:  # noqa: BLE001 — una métrica jamás rompe un turno
        logger.exception("record() de uso falló (alias=%s task=%s)", alias, task)


def drain() -> list[dict]:
    """Vacía y devuelve el buffer (para el flusher o los gates)."""
    with _lock:
        rows, _buffer[:] = list(_buffer), []
        return rows


def pending_count() -> int:
    with _lock:
        return len(_buffer)


# ── Persistencia (async, bajo RLS) ──────────────────────────────────────────────
_INSERT_SQL = (
    "INSERT INTO turn_usage (tenant_id, matter_id, task, model, prompt_tokens, "
    "completion_tokens, total_tokens, cost_usd, source) VALUES "
    "(%(tenant_id)s::uuid, %(matter_id)s::uuid, %(task)s, %(model)s, %(prompt_tokens)s, "
    "%(completion_tokens)s, %(total_tokens)s, %(cost_usd)s, %(source)s)"
)


async def flush_pending() -> int:
    """Drena el buffer e inserta en `turn_usage` agrupando por tenant (RLS).

    Si un grupo falla (DB caída, tenant borrado), sus filas se RE-ENCOLAN una vez
    marcadas; a la segunda falla se descartan con log — es métrica, no facturación.
    Devuelve cuántas filas quedaron persistidas.
    """
    rows = drain()
    if not rows:
        return 0
    from ..db import pool  # import diferido: no exigir DB para usar record() offline

    by_tenant: dict[str, list[dict]] = {}
    for r in rows:
        by_tenant.setdefault(r["tenant_id"], []).append(r)

    inserted = 0
    for tenant_id, group in by_tenant.items():
        try:
            async with pool.tenant_connection(tenant_id) as conn:
                for r in group:
                    await conn.execute(_INSERT_SQL, r)
            inserted += len(group)
        except Exception:  # noqa: BLE001 — degradar, no romper el flusher
            retry = [r for r in group if not r.get("_retried")]
            for r in retry:
                r["_retried"] = True
            if retry:
                with _lock:
                    _buffer.extend(retry)
                logger.exception("flush de uso falló para tenant %s: %d filas re-encoladas",
                                 tenant_id, len(retry))
            else:
                logger.exception("flush de uso falló DOS veces para tenant %s: "
                                 "%d filas descartadas", tenant_id, len(group))
    return inserted
