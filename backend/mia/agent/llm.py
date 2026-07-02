"""Mia · agent.llm — router central call_llm(task=...) por el gateway LiteLLM.

Adaptado del patrón `call_llm(task=...)` de Hermes (hermes-ref/agent/
auxiliary_client.py). En Hermes ese archivo tiene ~5.800 líneas porque resuelve
proveedor + auth + formato para ~20 proveedores a mano. En Mia ese trabajo lo
hace LiteLLM (decisión #3): el proxy expone UN endpoint OpenAI-compatible y los
modelos se nombran por alias (litellm_config.yaml). Por eso este router es
delgado: solo mapea `task -> alias` y delega el resto al gateway.

OVERRIDE 2026-06-20 (sin créditos Anthropic · anula parcialmente la decisión #7):
    Las tareas auxiliares (soul / title_generation / verification / …) apuntan a mia-local.
    `compression` sigue BLOQUEADA en _LOCKED_TASKS (un `model` explícito se ignora) a mia-local
    en vez de claude-haiku. Revertir a claude-haiku cuando haya créditos.

H.5 (cadena de fallback de proveedor, 2026-06-30):
    `_TASK_MODELS` (task→alias único) se reemplaza por `_TASK_FALLBACK_CHAINS` (task→[alias, …]).
    `call_llm` recorre la cadena: si un proveedor se agota con un error que amerita saltar
    (`error_classifier.should_fallback`), pasa al siguiente alias. `main`/`curator` intentan
    `claude-sonnet` y caen a `mia-local`. `compression` mantiene su cadena de un solo alias
    (sin fallback) y su bloqueo. Ver architecture/ y memory/decisions.md.

CP2 (política de modelo por tenant, 2026-07-01 · decisión #27, anticipada en la #26):
    Un ContextVar `_model_policy` (default: config.MIA_MODEL_POLICY) decide QUÉ cadena usa
    cada task. Tres políticas:
      · "suscripcion" → CLI de Claude Code del abogado (aliases "cli-claude" /
        "cli-claude-haiku", despachados a agent/subscription_llm) con fallback a nube y local;
      · "nube"        → API Anthropic vía proxy (restaura la decisión #7: compression=claude-haiku);
      · "soberano"    → todo mia-local (Ollama).
    El middleware fija la política por request (tenant_settings.config['model_policy']);
    los flujos sin request (cron) usan `model_policy_for` / `tenant_model_policy`.
    `_TASK_FALLBACK_CHAINS` se conserva como mapa BASE (compat con gates que lo leen);
    `resolve_fallback_chain` lo superpone con la cadena de la política activa.
"""
from __future__ import annotations

import logging
import time
from contextlib import asynccontextmanager
from contextvars import ContextVar, Token
from typing import Any

from .. import config
from .error_classifier import (
    LLMError,
    LLMErrorKind,
    classify_llm_error,
    is_retryable,
    retry_delay,
    should_fallback,
)

logger = logging.getLogger("mia.agent.llm")

# Reintentos automáticos para errores transitorios (rate limit / timeout / red).
# Los deterministas (auth, modelo inexistente, contexto largo) NO se reintentan.
MAX_RETRIES = 3

# task -> CADENA de aliases de fallback. Los alias viven en litellm_config.yaml (fuente
# única); el gateway resuelve el id real. call_llm prueba los aliases en orden: si el
# proveedor actual se agota con un error "saltable" (should_fallback), pasa al siguiente.
# `compression` tiene cadena de UN alias (bloqueada, sin fallback). `main`/`curator` intentan
# claude-sonnet y caen a mia-local (dev sin créditos → claude-sonnet puede fallar AUTH, que
# NO salta; usar model="mia-local" o ajustar la cadena si se quiere forzar local).
_TASK_FALLBACK_CHAINS: dict[str, list[str]] = {
    "main": ["claude-sonnet", "mia-local"],      # razonamiento principal: sonnet → local
    "curator": ["claude-sonnet", "mia-local"],   # consolidación semántica: sonnet → local
    "compression": ["mia-local"],                # BLOQUEADA (decisión #7), sin fallback
    "verification": ["mia-local"],               # verificación de citas legales
    "title_generation": ["mia-local"],           # títulos de asunto
    "session_search": ["mia-local"],             # resumen/búsqueda en la sesión
    "web_extract": ["mia-local"],                # extracción de contenido web
    "vision": ["mia-local"],                     # comprensión de documentos/imágenes
    "soul": ["mia-local"],                       # generación del SOUL.md (identidad del agente)
}

# Tareas cuya cadena es un contrato fijo: un `model` explícito NO puede cambiarla.
_LOCKED_TASKS = frozenset({"compression"})

_DEFAULT_TASK = "main"

# ── CP2 · política de modelo por tenant (decisión #27) ──────────────────────────
VALID_POLICIES = ("suscripcion", "nube", "soberano")

# Tareas auxiliares (baratas): comparten cadena dentro de cada política.
_AUX_TASKS = ("verification", "title_generation", "session_search", "web_extract",
              "vision", "soul")

# Cadenas por política. Se SUPERPONEN a _TASK_FALLBACK_CHAINS (que queda como mapa base,
# compat con tests que lo leen/mutan): un task inyectado ahí (no estándar) sigue resolviendo.
# `compression` sigue en _LOCKED_TASKS en las 3 políticas (un model explícito no la cambia).
_POLICY_CHAINS: dict[str, dict[str, list[str]]] = {
    # Suscripción de Claude Code del abogado (sin billing por API): CLI primero,
    # nube y local como red de seguridad. Auxiliares → hint haiku por el CLI.
    "suscripcion": {
        "main": ["cli-claude", "claude-sonnet", "mia-local"],
        "curator": ["cli-claude", "claude-sonnet", "mia-local"],
        # Sigue BLOQUEADA (model explícito no la cambia), pero con red: si el CLI
        # falla, cae a la API haiku barata (ajuste de la revisión CP2, decisión #27).
        "compression": ["cli-claude-haiku", "claude-haiku"],
        **{t: ["cli-claude-haiku", "mia-local"] for t in _AUX_TASKS},
    },
    # Nube (API Anthropic vía proxy). Restaura la decisión #7: compression=claude-haiku
    # (la clave de Anthropic volvió a funcionar, verificado 2026-07-01).
    "nube": {
        "main": ["claude-sonnet", "mia-local"],
        "curator": ["claude-sonnet", "mia-local"],
        "compression": ["claude-haiku"],
        **{t: ["claude-haiku", "mia-local"] for t in _AUX_TASKS},
    },
    # Soberano: TODO local (Ollama), para despachos que exigen cero salida de datos.
    "soberano": {t: ["mia-local"] for t in ("main", "curator", "compression", *_AUX_TASKS)},
}

# CP-S3 · OpenRouter como red de respaldo en la política 'nube'. OpenRouter da acceso
# a decenas de modelos con UNA clave; aquí entra como fallback de la API directa de
# Anthropic para el razonamiento (main/curator) ANTES de caer al modelo local. El
# alias debe existir en litellm_config.yaml. Se inserta SOLO si hay OPENROUTER_API_KEY
# configurada — sin clave, incluirlo rompería la cadena con un error de auth (que no
# salta de proveedor); con la ausencia, el alias simplemente no aparece.
OPENROUTER_ALIAS = "openrouter-sonnet"
_OPENROUTER_TASKS = ("main", "curator")


def _with_openrouter_fallback(chains: dict[str, list[str]]) -> dict[str, list[str]]:
    """Inserta OPENROUTER_ALIAS justo antes de 'mia-local' en main/curator (o al final
    si no está). No muta el dict recibido."""
    out = dict(chains)
    for task in _OPENROUTER_TASKS:
        chain = list(out.get(task, ()))
        if OPENROUTER_ALIAS in chain:
            continue
        idx = chain.index("mia-local") if "mia-local" in chain else len(chain)
        chain.insert(idx, OPENROUTER_ALIAS)
        out[task] = chain
    return out

# Alias CLI → hint de modelo para subscription_llm ("cli-claude" usa el default de la
# suscripción; "cli-claude-haiku" pide el modelo pequeño para tareas auxiliares baratas).
_CLI_MODEL_HINTS: dict[str, str | None] = {"cli-claude": None, "cli-claude-haiku": "haiku"}

# Timeout del CLI por task (revisión CP2): el razonamiento largo (main/curator) puede
# tardar minutos; las tareas auxiliares/compresión no deben retener el request tanto.
_CLI_TIMEOUT_LONG_TASKS = frozenset({"main", "curator"})
_CLI_TIMEOUT_LONG = 300.0   # segundos — main / curator
_CLI_TIMEOUT_SHORT = 120.0  # segundos — resto de tareas

# Aviso ÚNICO por proceso cuando temperature/max_tokens se descartan en aliases cli-*
# (el CLI headless no acepta esos parámetros); evitar spamear el log por llamada.
_warned_cli_dropped_params = False


def _cli_timeout(task: str | None) -> float:
    return _CLI_TIMEOUT_LONG if task in _CLI_TIMEOUT_LONG_TASKS else _CLI_TIMEOUT_SHORT


def _default_policy() -> str:
    """Política por defecto desde config (env MIA_MODEL_POLICY); inválida → 'suscripcion'."""
    p = (getattr(config, "MIA_MODEL_POLICY", "") or "").strip().lower()
    return p if p in VALID_POLICIES else "suscripcion"


_model_policy: ContextVar[str | None] = ContextVar("mia_model_policy", default=None)


def set_model_policy(policy: str | None) -> Token:
    """Fija la política en el contexto actual (middleware por request / cron por job).
    Devuelve el token para `reset_model_policy`. Una política inválida cae al default."""
    p = (policy or "").strip().lower()
    if p not in VALID_POLICIES:
        if p:
            logger.warning("política de modelo inválida '%s'; se usa el default '%s'",
                           policy, _default_policy())
        p = _default_policy()
    return _model_policy.set(p)


def get_model_policy() -> str:
    """Política efectiva del contexto actual (default de config si nadie la fijó)."""
    p = _model_policy.get()
    return p if p in VALID_POLICIES else _default_policy()


def reset_model_policy(token: Token) -> None:
    """Restaura la política previa (usar en finally, simétrico a set_model_policy)."""
    _model_policy.reset(token)


# CP-S3 · opt-in de OpenRouter por tenant (decisión de confidencialidad, regla 2).
_allow_openrouter: ContextVar[bool] = ContextVar("mia_allow_openrouter", default=False)


def set_openrouter_allowed(allowed: bool) -> Token:
    """Fija el opt-in de OpenRouter del contexto actual (middleware por request / cron)."""
    return _allow_openrouter.set(bool(allowed))


def openrouter_allowed() -> bool:
    """True si el despacho del contexto activo autorizó enrutar a OpenRouter."""
    return bool(_allow_openrouter.get())


def reset_openrouter_allowed(token: Token) -> None:
    _allow_openrouter.reset(token)


async def openrouter_allowed_for(tenant_id: str) -> bool:
    """Opt-in de OpenRouter del tenant, de `tenant_settings.config['allow_openrouter']`
    (RLS). Sin fila, valor ausente o error → False (fail-closed: no se enruta a un
    tercero salvo autorización explícita)."""
    try:
        from ..db import pool  # import diferido (mismo criterio que model_policy_for)

        async with pool.tenant_connection(tenant_id) as conn:
            row = await (await conn.execute(
                "SELECT config->>'allow_openrouter' FROM tenant_settings WHERE tenant_id = %s::uuid",
                (tenant_id,),
            )).fetchone()
        return bool(row and str(row[0] or "").strip().lower() in ("true", "1", "yes", "on"))
    except Exception:  # noqa: BLE001 — un fallo de DB no habilita un tercero: default False
        logger.exception("openrouter_allowed_for: no se pudo leer el opt-in del tenant %s",
                         tenant_id)
        return False


async def model_policy_for(tenant_id: str) -> str:
    """Política del tenant leída de `tenant_settings.config['model_policy']` (RLS).

    Para flujos SIN request (cron/background). Sin fila, valor inválido o error de DB →
    default de config. NO toca el ContextVar: combinar con set/reset o `tenant_model_policy`."""
    try:
        from ..db import pool  # import diferido: no exigir DB para usar call_llm offline

        async with pool.tenant_connection(tenant_id) as conn:
            row = await (await conn.execute(
                "SELECT config->>'model_policy' FROM tenant_settings WHERE tenant_id = %s::uuid",
                (tenant_id,),
            )).fetchone()
        p = ((row[0] if row else None) or "").strip().lower()
        if p in VALID_POLICIES:
            return p
    except Exception:  # noqa: BLE001 — un fallo de DB no debe tumbar el job; usa el default
        logger.exception("model_policy_for: no se pudo leer la política del tenant %s", tenant_id)
    return _default_policy()


@asynccontextmanager
async def tenant_model_policy(tenant_id: str):
    """Context manager async: fija la política del tenant y la restaura al salir.
    Para envolver jobs por-tenant de cron/background que llamen al LLM."""
    token = set_model_policy(await model_policy_for(tenant_id))
    or_token = set_openrouter_allowed(await openrouter_allowed_for(tenant_id))
    try:
        yield
    finally:
        reset_openrouter_allowed(or_token)
        reset_model_policy(token)


_client: Any = None  # openai.OpenAI — import diferido (ver _get_client)


class _FallbackNeeded(Exception):
    """Señal interna: el alias actual se agotó y conviene saltar al siguiente de la cadena.

    Lleva el `kind` clasificado y la excepción original para el diagnóstico final si la
    cadena entera se agota. NO escapa de call_llm (se traduce a LLMError allí).
    """

    def __init__(self, kind: LLMErrorKind, exc: BaseException) -> None:
        super().__init__(kind.value)
        self.kind = kind
        self.exc = exc


def _dedupe_chain(aliases: list[str]) -> list[str]:
    """Quita vacíos y duplicados preservando el orden (primer proveedor gana)."""
    out: list[str] = []
    for a in aliases:
        if a and a not in out:
            out.append(a)
    return out


def _active_chains() -> dict[str, list[str]]:
    """Mapa task→cadena efectivo: el base (_TASK_FALLBACK_CHAINS, compat/legacy) superpuesto
    con las cadenas de la política activa (CP2). Los tasks estándar los decide la política;
    un task extra inyectado en el mapa base (p. ej. por un gate) se conserva."""
    merged = dict(_TASK_FALLBACK_CHAINS)
    policy = get_model_policy()
    merged.update(_POLICY_CHAINS[policy])
    # CP-S3: OpenRouter entra SOLO si se cumplen TRES condiciones — política 'nube',
    # clave global configurada (operador) Y opt-in explícito del despacho. El opt-in
    # por tenant satisface la regla 2: enrutar los datos del cliente a un TERCERO
    # adicional (OpenRouter, con su propia política de datos) es decisión informada
    # del despacho, no un efecto colateral de que exista una clave global.
    if (policy == "nube" and getattr(config, "OPENROUTER_API_KEY", "")
            and openrouter_allowed()):
        merged = _with_openrouter_fallback(merged)
    return merged


def resolve_fallback_chain(task: str | None, model: str | None = None) -> list[str]:
    """Cadena de aliases a intentar para un `task` (sin vacíos ni duplicados), según la
    política de modelo activa (CP2 · get_model_policy()).

    - `compression` está bloqueado (decisión #7): un `model` distinto se ignora con warning.
    - `model` explícito (tarea no bloqueada) gana como cadena de UN alias (override sin fallback).
    - Sin `model`: la cadena de la política activa; un task desconocido cae a la de 'main'.
    """
    chains = _active_chains()
    if task in _LOCKED_TASKS:
        locked = chains[task]
        if model and model != locked[0]:
            logger.warning(
                "task=%s está bloqueado a %s (decisión #7); se ignora model=%s",
                task, locked[0], model,
            )
        return _dedupe_chain(locked)
    if model:
        return [model]
    chain = chains.get(task or _DEFAULT_TASK, chains[_DEFAULT_TASK])
    return _dedupe_chain(chain)


def resolve_model(task: str | None, model: str | None = None) -> str:
    """Compat: primer alias de la cadena de `task` (el proveedor preferido)."""
    return resolve_fallback_chain(task, model)[0]


def _get_client() -> Any:
    """Cliente OpenAI apuntado al proxy LiteLLM. Import diferido (como embeddings.py)."""
    global _client
    if _client is None:
        from openai import OpenAI  # diferido: solo al primer call_llm real

        _client = OpenAI(base_url=config.LITELLM_BASE_URL, api_key=config.LITELLM_API_KEY)
    return _client


def call_llm(
    messages: list[dict],
    *,
    task: str | None = None,
    model: str | None = None,
    temperature: float | None = None,
    max_tokens: int | None = None,
    tools: list | None = None,
    **extra: Any,
) -> Any:
    """Llamada LLM central y síncrona a través del gateway LiteLLM, con cadena de fallback.

    Devuelve la respuesta OpenAI-compatible (usar resp.choices[0].message.content).
    `task` elige la CADENA de proveedores (ver resolve_fallback_chain); `model` la
    sobre-escribe (cadena de un alias) salvo en tareas bloqueadas.

    Política (patrón Hermes v0.17.0, ver error_classifier):
      - transitorios (rate_limit/timeout/network/server) → reintento con backoff dentro del alias;
      - agotado el alias con un error "saltable" (should_fallback) → siguiente alias de la cadena;
      - AUTH / UNKNOWN → falla rápido con mensaje claro (LLMError), SIN saltar;
      - CONTEXT_TOO_LONG → propaga la excepción original SIN avanzar la cadena (la resuelve el compresor);
      - cadena entera agotada → LLMError('ALL_PROVIDERS_EXHAUSTED').
    call_llm es SÍNCRONO y se invoca vía asyncio.to_thread → time.sleep no bloquea el loop.
    """
    chain = resolve_fallback_chain(task, model)
    base_kwargs: dict[str, Any] = {"messages": messages}
    if temperature is not None:
        base_kwargs["temperature"] = temperature
    if max_tokens is not None:
        base_kwargs["max_tokens"] = max_tokens
    if tools:
        base_kwargs["tools"] = tools
    base_kwargs.update(extra)

    client = _get_client()
    last: _FallbackNeeded | None = None
    for i, alias in enumerate(chain):
        next_alias = chain[i + 1] if i + 1 < len(chain) else None
        try:
            return _call_with_retries(
                client, {**base_kwargs, "model": alias}, MAX_RETRIES,
                task=task, alias=alias, next_alias=next_alias,
            )
        except _FallbackNeeded as fn:
            last = fn                          # sigue con el próximo alias de la cadena
            continue

    # Cadena entera agotada: todos los proveedores fallaron con errores saltables.
    kind = last.kind if last else LLMErrorKind.UNKNOWN
    logger.error("call_llm ALL_PROVIDERS_EXHAUSTED [%s] (task=%s chain=%s): %s",
                 kind.value, task, chain, last.exc if last else None)
    raise LLMError(
        kind, f"ALL_PROVIDERS_EXHAUSTED: la cadena {chain} falló ({kind.value})."
    ) from (last.exc if last else None)


def _invoke(client: Any, alias: str, kwargs: dict[str, Any], task: str | None = None) -> Any:
    """Despacha UNA llamada según el alias: los "cli-*" van al CLI de la suscripción
    (agent/subscription_llm); el resto, al proxy LiteLLM (cliente OpenAI). Los errores de
    ambos caminos pasan por el MISMO error_classifier/should_fallback aguas arriba."""
    if alias.startswith("cli-"):
        from . import subscription_llm  # import diferido (mismo criterio que _get_client)

        if kwargs.get("tools"):
            # El CLI headless no soporta tool-calling OpenAI; se ignora con aviso.
            logger.warning("alias %s no soporta 'tools'; se ignoran en esta llamada", alias)
        dropped = [k for k in ("temperature", "max_tokens") if kwargs.get(k) is not None]
        if dropped:
            global _warned_cli_dropped_params
            if not _warned_cli_dropped_params:
                _warned_cli_dropped_params = True
                logger.warning(
                    "los aliases cli-* descartan %s (el CLI headless no los acepta); "
                    "este aviso se emite una sola vez por proceso", dropped,
                )
        return subscription_llm.call_cli(
            kwargs["messages"],
            model_hint=_CLI_MODEL_HINTS.get(alias),
            timeout=_cli_timeout(task),   # 300s main/curator · 120s resto (revisión CP2)
        )
    return client.chat.completions.create(**kwargs)


def _call_with_retries(
    client: Any,
    kwargs: dict[str, Any],
    max_retries: int,
    *,
    task: str | None,
    alias: str,
    next_alias: str | None,
) -> Any:
    """Ejecuta UN alias con reintentos. Devuelve la respuesta o decide el destino del error:

    - CONTEXT_TOO_LONG → propaga la original (no reintenta, no salta);
    - error saltable (should_fallback), sea inmediato (model_unavailable) o tras agotar los
      reintentos (rate_limit/timeout/network/server) → `_FallbackNeeded` (la cadena avanza);
    - error no saltable (AUTH/UNKNOWN) → LLMError inmediato (fail-fast).
    """
    for attempt in range(max_retries + 1):     # 1 intento inicial + hasta max_retries reintentos
        try:
            return _invoke(client, alias, kwargs, task)
        except Exception as exc:               # noqa: BLE001 — se clasifica y re-lanza abajo
            kind = classify_llm_error(exc)

            if kind is LLMErrorKind.CONTEXT_TOO_LONG:
                logger.warning("call_llm context_too_long (task=%s alias=%s): %s",
                               task, alias, exc)
                raise                          # propaga original: lo maneja la compresión

            # Reintento dentro del alias mientras queden intentos y sea transitorio.
            if is_retryable(kind) and attempt < max_retries:
                delay = retry_delay(kind, attempt)
                logger.warning("call_llm reintento %d/%d [%s] en %.2fs (task=%s alias=%s): %s",
                               attempt + 1, max_retries, kind.value, delay, task, alias, exc)
                time.sleep(delay)
                continue

            # Agotados los reintentos (o error no reintentable): ¿saltar de proveedor?
            if should_fallback(kind):
                # Log estructurado del salto: task, alias agotado, intentos, kind, próximo alias.
                logger.warning(
                    "call_llm fallback",
                    extra={"task": task, "alias": alias, "attempt": attempt,
                           "kind": kind.value, "next_alias": next_alias},
                )
                logger.warning("call_llm salta de proveedor [%s] task=%s %s→%s (tras %d intentos)",
                               kind.value, task, alias, next_alias, attempt + 1)
                raise _FallbackNeeded(kind, exc) from exc

            # CP-S3 (revisión capa 2, H2): OpenRouter es un respaldo OPCIONAL. Si su
            # clave es inválida o no tiene saldo (AUTH/402 → no saltable) y hay un
            # proveedor DESPUÉS en la cadena (mia-local), no debe matar el turno: se
            # salta al siguiente. Sin next_alias sí falla claro (era el último recurso).
            if alias == OPENROUTER_ALIAS and next_alias:
                logger.warning("call_llm: el respaldo opcional %s falló [%s]; se salta a "
                               "%s (task=%s)", alias, kind.value, next_alias, task)
                raise _FallbackNeeded(kind, exc) from exc

            # No saltable (AUTH/UNKNOWN): falla rápido con mensaje claro.
            logger.error("call_llm fallo no saltable [%s] (task=%s alias=%s): %s",
                         kind.value, task, alias, exc)
            raise LLMError(kind, _clear_message(kind, alias)) from exc

    # Inalcanzable (el loop retorna, reintenta o lanza), pero satisface el análisis estático.
    raise LLMError(LLMErrorKind.UNKNOWN, "call_llm terminó sin resultado")


def _clear_message(kind: LLMErrorKind, model: str) -> str:
    """Mensaje claro (en español, sin jerga técnica de proveedor) por tipo de error."""
    if kind is LLMErrorKind.AUTH:
        return (f"Credenciales inválidas o sin créditos para el modelo '{model}'. "
                "Revisa ANTHROPIC_API_KEY / la cuenta del proveedor.")
    if kind is LLMErrorKind.MODEL_UNAVAILABLE:
        return (f"El modelo '{model}' no está disponible en el gateway. "
                "Revisa litellm_config.yaml y que el proxy esté arriba.")
    return f"Fallo del gateway LLM ({kind.value}) con el modelo '{model}'."
