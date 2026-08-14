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
    # La política adaptativa conserva el mismo modelo de costo marginal: estos aliases
    # invocan la suscripción local del abogado, no una API facturable por token.
    "cli-claude-opus": (0.0, 0.0),
    "cli-claude-sonnet": (0.0, 0.0),
    # Adaptador lateral y aislado del benchmark: usa la sesión ChatGPT/Codex,
    # nunca una API facturable por token. No está disponible en producción.
    "cli-codex-eval": (0.0, 0.0),
    "mia-local": (0.0, 0.0),
}

FREE_ALIASES = frozenset({
    "cli-claude", "cli-claude-haiku", "cli-claude-opus", "cli-claude-sonnet",
    "cli-codex-eval", "mia-local",
})
UNKNOWN_ALIAS_RATES = (3.00, 15.00)

_scope: ContextVar[tuple[str, str | None, str] | None] = ContextVar(
    "mia_usage_scope", default=None
)

# F0.1 del plan de eficiencia: NODO del grafo al que se atribuye la llamada
# (facts/research/analysis/draft/verificador_citas/harvest/edit/work…). Mismo
# mecanismo que el scope: graph._llm lo fija alrededor de call_llm y el
# ContextVar viaja al thread de asyncio.to_thread. None = fuera del grafo.
_node: ContextVar[str | None] = ContextVar("mia_usage_node", default=None)


def set_node(node: str | None) -> Token:
    """Fija el nodo del grafo para las llamadas siguientes de ESTE contexto."""
    return _node.set(node or None)


def reset_node(token: Token) -> None:
    _node.reset(token)

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


def cost_usd_cached(alias: str, prompt_tokens: int, completion_tokens: int,
                    cache_read_tokens: int = 0, cache_creation_tokens: int = 0) -> float:
    """Costo en USD con la CACHÉ DE PROMPT desglosada (A-MAY1, 2026-07-21).

    `cost_usd` tarifa TODO el prompt a la entrada normal, y por eso el panel subestimaba las
    ESCRITURAS de caché (2.00x, y LiteLLM las deja FUERA de `prompt_tokens`) y sobreestimaba las
    LECTURAS (0.10x, que van DENTRO de `prompt_tokens`). Aquí se reutiliza la MISMA función que
    ya usa la reserva del banco (`eval.spend_guard.real_call_cost`) para no duplicar los factores
    de tarifa: fuente única de la aritmética de caché. Sin tokens de caché el resultado es
    IDÉNTICO a `cost_usd` por construcción (normal_in = prompt_tokens, los otros dos cubos son 0).

    Fail-safe: si `spend_guard` no se pudiera importar (no debería: es código del propio repo),
    se cae a la tarifa plana `cost_usd` en vez de perder la fila — una métrica jamás rompe nada.
    """
    if not (cache_read_tokens or cache_creation_tokens):
        # Sin caché no hay nada que desglosar: se conserva EXACTAMENTE el camino de siempre.
        return cost_usd(alias, prompt_tokens, completion_tokens)
    try:
        from ..eval import spend_guard  # import diferido (sin ciclo: spend_guard importa usage

        # también en diferido, y ambos módulos ya están cargados en tiempo de ejecución).
        return spend_guard.real_call_cost(
            alias, prompt_tokens, completion_tokens, cache_read_tokens, cache_creation_tokens)
    except Exception:  # noqa: BLE001 — una métrica jamás rompe un turno; se degrada a tarifa plana
        logger.exception("cost_usd_cached: no se pudo desglosar la caché (alias=%s); "
                         "se usa tarifa plana", alias)
        return cost_usd(alias, prompt_tokens, completion_tokens)


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
def _cache_tokens(usage: Any) -> tuple[int, int]:
    """Extrae (cache_read, cache_creation) de un objeto usage, sea cual sea el formato.

    LiteLLM expone la caché de dos formas según el proveedor: (1) estilo OpenAI en
    `prompt_tokens_details.cached_tokens` (solo lectura), y (2) passthrough Anthropic en
    `cache_read_input_tokens` / `cache_creation_input_tokens`. Se prueban ambas; ausencia = 0.
    """
    def _int(value: Any) -> int:
        try:
            return int(value or 0)
        except (TypeError, ValueError):
            return 0

    read = _int(getattr(usage, "cache_read_input_tokens", 0))
    creation = _int(getattr(usage, "cache_creation_input_tokens", 0))
    if not read:
        details = getattr(usage, "prompt_tokens_details", None)
        if isinstance(details, dict):
            read = _int(details.get("cached_tokens"))
        elif details is not None:
            read = _int(getattr(details, "cached_tokens", 0))
    return read, creation


def record(alias: str, task: str | None, usage: Any,
           *, stop_reason: str | None = None, effective_model: str | None = None,
           effort: str | None = None, quality_escalation: str | None = None) -> None:
    """Bufferiza el uso de UNA llamada al LLM. Sin scope o sin usage → no-op."""
    try:
        scope = _scope.get()
        if scope is None or usage is None:
            return
        tenant_id, matter_id, source = scope
        prompt = int(getattr(usage, "prompt_tokens", 0) or 0)
        completion = int(getattr(usage, "completion_tokens", 0) or 0)
        cache_read, cache_creation = _cache_tokens(usage)
        # R3-MENOR (Codex, ronda 3): LiteLLM deja la ESCRITURA de caché FUERA de `total_tokens`
        # (medido en `llms/anthropic/chat/transformation.py::calculate_usage`), así que el total
        # VISIBLE subreportaba (p. ej. 1,60M en vez de 1,85M con 0,25M de escritura). El COSTE ya
        # estaba bien (cost_usd_cached); esto corrige sólo el TOTAL. Mismo criterio que
        # `eval.spend_guard._extract` — fuente única. La LECTURA ya está DENTRO de prompt_tokens.
        base_total = int(getattr(usage, "total_tokens", 0) or 0) or (prompt + completion)
        total = base_total + cache_creation
        row = {
            "tenant_id": tenant_id,
            "matter_id": matter_id,
            "task": (task or "")[:64] or None,
            "model": str(alias)[:128],
            # `model` conserva el alias histórico (precios/panel existentes); los campos
            # efectivos registran la decisión real del router, sin inventar que todos los
            # proveedores exponen el mismo nombre o nivel de razonamiento.
            "effective_model": str(effective_model or alias)[:128],
            "effort": (str(effort)[:16] if effort else None),
            "quality_escalation": (str(quality_escalation)[:16] if quality_escalation else None),
            "prompt_tokens": prompt,
            "completion_tokens": completion,
            "total_tokens": total,
            # A-MAY1: la caché de prompt se tarifa desglosada (escritura 2x FUERA de
            # prompt_tokens, lectura 0.1x DENTRO). Sin tokens de caché es idéntico a
            # `cost_usd(alias, prompt, completion)` — la fila normal no cambia en nada.
            "cost_usd": round(cost_usd_cached(
                alias, prompt, completion, cache_read, cache_creation), 6),
            "source": source[:32],
            "cache_read_tokens": cache_read,
            "cache_creation_tokens": cache_creation,
            "stop_reason": (str(stop_reason)[:32] if stop_reason else None),
            # F0.1: atribución por nodo del grafo (None = llamada fuera del grafo).
            "node": ((_node.get() or "")[:64] or None),
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
    "INSERT INTO turn_usage (tenant_id, matter_id, task, model, effective_model, effort, "
    "quality_escalation, prompt_tokens, "
    "completion_tokens, total_tokens, cost_usd, source, cache_read_tokens, "
    "cache_creation_tokens, stop_reason, node) VALUES "
    "(%(tenant_id)s::uuid, %(matter_id)s::uuid, %(task)s, %(model)s, %(effective_model)s, "
    "%(effort)s, %(quality_escalation)s, %(prompt_tokens)s, "
    "%(completion_tokens)s, %(total_tokens)s, %(cost_usd)s, %(source)s, "
    "%(cache_read_tokens)s, %(cache_creation_tokens)s, %(stop_reason)s, %(node)s)"
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
