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
    "mission_decompose": ["mia-local"],          # CP-E5: hitos de un objetivo del expediente
}

# Tareas cuya cadena es un contrato fijo: un `model` explícito NO puede cambiarla.
_LOCKED_TASKS = frozenset({"compression"})

_DEFAULT_TASK = "main"

# ── CP2 · política de modelo por tenant (decisión #27) ──────────────────────────
# CP-OR (2026-07-13): se añade "openrouter" como MOTOR PRINCIPAL propio del abogado
# (su cuenta/clave de OpenRouter, cargada de crédito). A diferencia de "nube" (API
# directa de Anthropic de la instalación), en "openrouter" TODO el razonamiento sale
# por la clave del despacho vía el alias openrouter-* del gateway, con red local final.
VALID_POLICIES = ("suscripcion", "nube", "soberano", "openrouter")

# Tareas auxiliares (baratas): comparten cadena dentro de cada política.
_AUX_TASKS = ("verification", "title_generation", "session_search", "web_extract",
              "vision", "soul", "mission_decompose")

# Aliases de OpenRouter (viven en litellm_config.yaml). `openrouter-sonnet` para el
# razonamiento; `openrouter-haiku` para tareas baratas (compresión/auxiliares). Se
# definen ANTES de _POLICY_CHAINS porque la política "openrouter" los referencia.
OPENROUTER_ALIAS = "openrouter-sonnet"
OPENROUTER_HAIKU_ALIAS = "openrouter-haiku"
# Cualquier alias que salga por la cuenta de OpenRouter (para el salto opcional de
# _call_with_retries: si un alias de OpenRouter falla por AUTH/402 —clave inválida o
# sin saldo, que no salta solo— y hay red después en la cadena, se salta al siguiente).
_OPENROUTER_ALIASES = frozenset({OPENROUTER_ALIAS, OPENROUTER_HAIKU_ALIAS})

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
    # OpenRouter como MOTOR PRINCIPAL (CP-OR): el abogado conecta su propia cuenta de
    # OpenRouter (una clave da acceso a decenas de modelos, con su crédito). El
    # razonamiento principal (main/curator) sale por openrouter-sonnet; las tareas
    # baratas (compression + auxiliares) por openrouter-haiku. En AMBOS casos con red
    # final a mia-local: si la clave se queda sin saldo o es inválida (AUTH/402, que no
    # salta por sí solo), el respaldo openrouter de _call_with_retries salta al local en
    # vez de matar el turno. Elegir esta política ES el consentimiento de enrutar a
    # OpenRouter (no depende del opt-in `allow_openrouter`, que gobierna el overflow de
    # otras políticas). Requiere OPENROUTER_API_KEY en el .env (lo exige la UI de activación).
    "openrouter": {
        "main": [OPENROUTER_ALIAS, "mia-local"],
        "curator": [OPENROUTER_ALIAS, "mia-local"],
        "compression": [OPENROUTER_HAIKU_ALIAS, "mia-local"],
        **{t: [OPENROUTER_HAIKU_ALIAS, "mia-local"] for t in _AUX_TASKS},
    },
}

# CP-S3 · OpenRouter como red de respaldo/overflow ("más uso"). OpenRouter da acceso
# a decenas de modelos con UNA clave; aquí entra como fallback del motor de razonamiento
# (main/curator) ANTES de caer al modelo local. El alias debe existir en
# litellm_config.yaml. Se inserta SOLO si hay OPENROUTER_API_KEY configurada — sin clave,
# incluirlo rompería la cadena con un error de auth (que no salta de proveedor); con la
# ausencia, el alias simplemente no aparece.
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


# CP-OR/CP-S3 (revisión capa 2, MAYOR 1): disponibilidad REAL de la clave de OpenRouter.
# `welcome.set_keys` escribe OPENROUTER_API_KEY al `.env` en disco pero, a propósito, NO la
# inyecta en `config.OPENROUTER_API_KEY` ni en `os.environ` del proceso vivo (esa clave la
# sirve el proxy mia-litellm.exe, un proceso APARTE que solo la lee al arrancar). Por eso, si
# condicionáramos el overflow SOLO a `config.OPENROUTER_API_KEY` (leída UNA vez al importar
# config.py:75), tras guardar la clave y reiniciar EN CALIENTE solo el proxy (restart_litellm,
# que NO reinicia este backend uvicorn) el backend seguiría sin verla hasta un cierre/reapertura
# COMPLETO — el overflow quedaría INERTE pese a que la UI ya limpió el aviso "cierra y reabre".
# Este helper refleja la disponibilidad REAL: config (proceso vivo) O el `.env` en disco. Es
# SEGURO adelantarse al proxy: si el alias openrouter-* se inserta antes de que el proxy tenga
# la clave, la llamada falla AUTH/402 y `_call_with_retries` degrada a mia-local (salto opcional
# de OpenRouter, ya existente). NO seteamos config/os.environ en caliente (respeta el comentario
# de welcome.py). Cache de tiempo corto: se relee el `.env` a lo sumo cada _OPENROUTER_ENV_TTL
# segundos, NO por turno (no golpear disco en cada call_llm).
_OPENROUTER_ENV_TTL = 5.0  # segundos
_openrouter_env_cache: tuple[float, bool] = (0.0, False)


def _openrouter_key_present() -> bool:
    """True si hay clave de OpenRouter disponible: en `config` (proceso vivo) O en el `.env`
    en disco. El `.env` se relee a lo sumo cada _OPENROUTER_ENV_TTL s (cache por tiempo)."""
    if (getattr(config, "OPENROUTER_API_KEY", "") or "").strip():
        return True
    global _openrouter_env_cache
    now = time.monotonic()
    ts, cached = _openrouter_env_cache
    if now - ts < _OPENROUTER_ENV_TTL:
        return cached
    present = False
    try:
        from ..setup.env_writer import read_env_values  # import diferido (solo stdlib, sin ciclo)

        values = read_env_values(config.PROJECT_ROOT / ".env")
        present = bool(values.get("OPENROUTER_API_KEY", "").strip())
    except Exception:  # noqa: BLE001 — un fallo de disco no debe tumbar el ruteo del turno
        logger.exception("_openrouter_key_present: no se pudo leer el .env")
        present = False
    _openrouter_env_cache = (now, present)
    return present

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


async def notebooklm_allowed_for(tenant_id: str) -> bool:
    """Opt-in de consulta a NotebookLM (nube de Google) del tenant, de
    `tenant_settings.config['allow_notebooklm']` (RLS). Sin fila, valor ausente o error
    → False (fail-closed: la pregunta que Mia le hace a NotebookLM VIAJA a Google, y ese
    texto puede llevar contexto del caso — solo sale con autorización explícita del
    despacho, misma regla dura que OpenRouter y el análisis de correo).

    OJO: este opt-in es NECESARIO pero NO suficiente. La decisión completa vive en
    `connectors.notebooklm.gate.query_allowed`, que además bloquea del todo la política
    'soberano' (cero salida del equipo) leyéndola con `model_policy_for_strict`."""
    try:
        from ..db import pool  # import diferido (mismo criterio que openrouter_allowed_for)

        async with pool.tenant_connection(tenant_id) as conn:
            row = await (await conn.execute(
                "SELECT config->>'allow_notebooklm' FROM tenant_settings WHERE tenant_id = %s::uuid",
                (tenant_id,),
            )).fetchone()
        return bool(row and str(row[0] or "").strip().lower() in ("true", "1", "yes", "on"))
    except Exception:  # noqa: BLE001 — un fallo de DB no habilita salida a la nube: default False
        logger.exception("notebooklm_allowed_for: no se pudo leer el opt-in del tenant %s",
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


async def model_policy_for_strict(tenant_id: str) -> str:
    """Como model_policy_for pero SIN tragar errores: si la lectura de DB falla, LANZA
    (no cae al default de config).

    Para flujos donde asumir el default de la instalación ante un ERROR sería fail-OPEN
    de confidencialidad — en particular el análisis de contenido de correo (CP-P4): un
    tenant 'soberano' (todo local) JAMÁS debe terminar enviando el cuerpo de un correo a
    la nube porque un timeout de DB hizo caer la política al default 'suscripcion'. El
    llamador debe ABORTAR (degradar) si esto lanza. Fila ausente o valor inválido (estado
    REAL, no error) sí caen al default de config, como en model_policy_for."""
    from ..db import pool

    async with pool.tenant_connection(tenant_id) as conn:
        row = await (await conn.execute(
            "SELECT config->>'model_policy' FROM tenant_settings WHERE tenant_id = %s::uuid",
            (tenant_id,),
        )).fetchone()
    p = ((row[0] if row else None) or "").strip().lower()
    return p if p in VALID_POLICIES else _default_policy()


@asynccontextmanager
async def tenant_model_policy(tenant_id: str):
    """Context manager async: fija la política del tenant y la restaura al salir.
    Para envolver jobs por-tenant de cron/background que llamen al LLM.
    CP-V1: también fija el scope de registro de uso (source='cron') para que el
    gasto de los jobs de fondo cuente en el "valor neto" del panel."""
    from ..metrics import usage as usage_metrics  # import diferido (sin ciclos)

    token = set_model_policy(await model_policy_for(tenant_id))
    or_token = set_openrouter_allowed(await openrouter_allowed_for(tenant_id))
    usage_token = usage_metrics.set_usage_scope(tenant_id, source="cron")
    try:
        yield
    finally:
        usage_metrics.reset_usage_scope(usage_token)
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
    # CP-S3/CP-OR: OpenRouter entra como respaldo/overflow ("más uso") SOLO si se cumplen
    # TRES condiciones — política 'nube' O 'suscripcion', opt-in explícito del despacho Y
    # clave de OpenRouter REALMENTE disponible (`_openrouter_key_present`: config del proceso
    # vivo O el `.env` en disco — ver MAYOR 1, para que el overflow no quede inerte tras
    # guardar la clave + reiniciar el proxy en caliente). El opt-in por tenant satisface la
    # regla 2: enrutar los datos del cliente a un TERCERO adicional (OpenRouter, con su propia
    # política de datos) es decisión informada del despacho, no un efecto colateral de que
    # exista una clave. NO aplica a 'soberano' (nada sale del equipo) ni a 'openrouter' (ahí
    # OpenRouter YA es el motor principal, sin necesidad de insertarlo). Orden del AND: el
    # opt-in (ContextVar barato) va antes que `_openrouter_key_present` (relee el `.env` con
    # cache) para no tocar disco cuando el despacho no autorizó el overflow.
    if (policy in ("nube", "suscripcion") and openrouter_allowed()
            and _openrouter_key_present()):
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
        hold_id: str | None = None
        budget_tenant: str | None = None
        try:
            from ..metrics import usage as usage_metrics
            from ..policy import budget as policy_budget

            scope = usage_metrics.current_scope()
            estimate = usage_metrics.estimated_call_cost(
                alias, messages, max_tokens, task=task, tools=tools)
            if scope is not None and estimate > 0:
                budget_tenant = scope[0]
                try:
                    hold_id = policy_budget.reserve_call_sync(
                        budget_tenant, estimate, model=alias, task=task)
                except (policy_budget.BudgetExceeded,
                        policy_budget.BudgetControlUnavailable):
                    free_fallback = any(
                        usage_metrics.estimated_call_cost(a, [], 1, task=task) == 0
                        for a in chain[i + 1:]
                    )
                    if free_fallback:
                        logger.warning("se omite alias pagado %s para proteger el tope; "
                                       "se usa respaldo gratuito", alias)
                        continue
                    raise
            resp = _call_with_retries(
                client, {**base_kwargs, "model": alias}, MAX_RETRIES,
                task=task, alias=alias, next_alias=next_alias,
            )
            if hold_id and budget_tenant:
                resp_usage = getattr(resp, "usage", None)
                actual = usage_metrics.cost_usd(
                    alias,
                    int(getattr(resp_usage, "prompt_tokens", 0) or 0),
                    int(getattr(resp_usage, "completion_tokens", 0) or 0),
                )
                policy_budget.finish_call_sync(budget_tenant, hold_id, actual)
                hold_id = None
            _record_usage(alias, task, resp)   # CP-V1: tokens reales → turn_usage
            return resp
        except _FallbackNeeded as fn:
            if hold_id and budget_tenant:
                policy_budget.finish_call_sync(budget_tenant, hold_id, None)
            last = fn                          # sigue con el próximo alias de la cadena
            continue
        except BaseException:
            if hold_id and budget_tenant:
                policy_budget.finish_call_sync(budget_tenant, hold_id, None)
            raise

    # Cadena entera agotada: todos los proveedores fallaron con errores saltables.
    kind = last.kind if last else LLMErrorKind.UNKNOWN
    logger.error("call_llm ALL_PROVIDERS_EXHAUSTED [%s] (task=%s chain=%s): %s",
                 kind.value, task, chain, last.exc if last else None)
    raise LLMError(
        kind, f"ALL_PROVIDERS_EXHAUSTED: la cadena {chain} falló ({kind.value})."
    ) from (last.exc if last else None)


def _record_usage(alias: str, task: str | None, resp: Any) -> None:
    """CP-V1 (Ola 4): registra el uso real de la llamada (tokens→costo) en el buffer
    de metrics/usage. Cubre las 3 políticas: la API/OpenRouter traen `resp.usage`
    OpenAI-compatible y el CLI de la suscripción también lo construye
    (subscription_llm). Sin scope fijado (gates offline) es un no-op. JAMÁS rompe
    el turno: cualquier fallo se loguea y se sigue."""
    try:
        from ..metrics import usage as usage_metrics  # import diferido (sin ciclos)

        usage_metrics.record(alias, task, getattr(resp, "usage", None))
    except Exception:  # noqa: BLE001 — una métrica nunca tumba una respuesta buena
        logger.exception("no se pudo registrar el uso (alias=%s task=%s)", alias, task)


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

            # CP-S3/CP-OR (revisión capa 2, H2): los aliases de OpenRouter (respaldo
            # opcional en 'nube'/'suscripcion' o motor principal en 'openrouter'). Si la
            # clave es inválida o no tiene saldo (AUTH/402 → no saltable) y hay un
            # proveedor DESPUÉS en la cadena (mia-local), no debe matar el turno: se salta
            # al siguiente. Sin next_alias sí falla claro (era el último recurso). Cubre
            # openrouter-sonnet Y openrouter-haiku para que la política 'openrouter'
            # degrade con gracia a local cuando la cuenta del abogado se agota.
            if alias in _OPENROUTER_ALIASES and next_alias:
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
                "Revisa la clave de respaldo del motor o la cuenta del proveedor.")
    if kind is LLMErrorKind.MODEL_UNAVAILABLE:
        return (f"El modelo '{model}' no está disponible en el gateway. "
                "Revisa litellm_config.yaml y que el proxy esté arriba.")
    return f"Fallo del gateway LLM ({kind.value}) con el modelo '{model}'."
