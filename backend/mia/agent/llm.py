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
from collections.abc import Iterator
from contextlib import asynccontextmanager, contextmanager
from contextvars import ContextVar, Token
from typing import Any

from .. import config
from .error_classifier import (
    LLMError,
    LLMErrorKind,
    classify_llm_error,
    is_retryable,
    provider_never_reached,
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
    "legal_facts": ["claude-sonnet", "mia-local"],
    "legal_research": ["claude-sonnet", "mia-local"],
    "legal_analysis": ["claude-sonnet", "mia-local"],
    "legal_draft": ["claude-sonnet", "mia-local"],
    "legal_verification": ["claude-sonnet", "mia-local"],
    "legal_work": ["claude-sonnet", "mia-local"],
    "legal_edit": ["claude-sonnet", "mia-local"],
    "curator": ["claude-sonnet", "mia-local"],   # consolidación semántica: sonnet → local
    # ¿estos dos playbooks dicen lo mismo o lo contrario? Es una CLASIFICACIÓN de tres
    # salidas, no razonamiento jurídico: entra como AUXILIAR (barata). Ver _AUX_TASKS.
    "curator_conflict": ["mia-local"],           # juez de contradicción del Curator
    # Clasificar metadata de un documento (tipo/parte/radicado/fecha) es TRIAJE barato, no
    # juicio jurídico sustantivo: entra como AUXILIAR (ver _AUX_TASKS), como curator_conflict.
    "doc_classification": ["mia-local"],         # clasificador de metadata en la ingesta
    "compression": ["mia-local"],                # BLOQUEADA (decisión #7), sin fallback
    "verification": ["mia-local"],               # verificación de citas legales
    "title_generation": ["mia-local"],           # títulos de asunto
    "session_search": ["mia-local"],             # resumen/búsqueda en la sesión
    "web_extract": ["mia-local"],                # extracción de contenido web
    "vision": ["mia-local"],                     # comprensión de documentos/imágenes
    "soul": ["mia-local"],                       # generación del SOUL.md (identidad del agente)
    "mission_decompose": ["mia-local"],          # CP-E5: hitos de un objetivo del expediente
    "delegation_triage": ["mia-local"],          # CP-HUB2: ¿hace falta un ayudante externo?
}

# Tareas cuya cadena es un contrato fijo: un `model` explícito NO puede cambiarla.
_LOCKED_TASKS = frozenset({"compression"})

# ── Prefix caching de Anthropic (decisión #3) ───────────────────────────────────
# Aliases que salen por la API DIRECTA de Anthropic (model: anthropic/... en
# litellm_config.yaml). Solo estos soportan el prefix caching de Anthropic con
# `cache_control` en los bloques de content (LiteLLM lo pasa tal cual y añade el header
# de TTL 1h para modelos Claude 4.5+). Los aliases cli-* (CLI de suscripción) y mia-local
# (Ollama) NO lo soportan; openrouter-* se excluye a propósito (motor de un tercero, su
# reporte de tokens cacheados difiere) — la medición del panel apunta a la API directa.
# Fuente única de los modelos: litellm_config.yaml (claude-haiku / claude-sonnet).
_ANTHROPIC_CACHE_ALIASES = frozenset({"claude-haiku", "claude-sonnet"})

_DEFAULT_TASK = "main"

# EF-3: funciones jurídicas separadas como contrato observable. Por ahora comparten el
# mismo piso/cadena de razonamiento que `main`; separarlas evita que telemetría, presupuestos
# y futuras calibraciones confundan investigación, análisis, redacción y verificación.
LEGAL_TASKS = (
    "legal_facts", "legal_research", "legal_analysis", "legal_draft",
    "legal_verification", "legal_work", "legal_edit",
)

# ── CP2 · política de modelo por tenant (decisión #27) ──────────────────────────
# CP-OR (2026-07-13): se añade "openrouter" como MOTOR PRINCIPAL propio del abogado
# (su cuenta/clave de OpenRouter, cargada de crédito). A diferencia de "nube" (API
# directa de Anthropic de la instalación), en "openrouter" TODO el razonamiento sale
# por la clave del despacho vía el alias openrouter-* del gateway, con red local final.
VALID_POLICIES = ("quality_adaptive", "suscripcion", "codex", "nube", "soberano", "openrouter")

# Tareas auxiliares (baratas): comparten cadena dentro de cada política.
# CP-HUB2 · `delegation_triage` (¿le sirve al abogado un ayudante externo en este turno?)
# entra como AUXILIAR y no como `main` por dos razones: es una pregunta de sí/no que no
# necesita el motor de razonamiento jurídico, y corre en CADA turno de un despacho con
# ayudantes activos — pagar sonnet por ella sería un impuesto permanente sobre una función
# que casi siempre responde "no". Al ser auxiliar, en 'soberano' resuelve a mia-local… pero
# ahí NUNCA llega a ejecutarse: `hub_gate.allowed_agents` devuelve [] y el proponente no se
# arma (ver graph.py::_plan_delegation).
#
# `curator_conflict` (¿estos dos playbooks se contradicen?) también es AUXILIAR: corre una vez
# por par candidato en el cron semanal del Curator y su salida es una de tres etiquetas. Pagar
# sonnet por ella no compraría nada — y su modo de fallo ya está cubierto: si el juez revienta o
# responde algo que no se entiende, el Curator lo trata como duplicado (el comportamiento de
# siempre). En 'soberano' resuelve a mia-local, como el resto.
#
# `doc_classification` (¿qué tipo/parte/radicado/fecha tiene este documento recién ingerido?)
# también es AUXILIAR: es TRIAJE de metadata barato, no juicio jurídico sustantivo (que nunca
# corre en modelo local). Corre una vez por documento al ingerirlo y su salida es texto libre
# por campo con una confianza; su modo de fallo ya está cubierto (fail-soft en classify.py: si
# el modelo revienta o el JSON no se entiende, el documento queda sin metadata y la ingesta
# sigue). En 'soberano' resuelve a mia-local, como el resto.
_AUX_TASKS = ("verification", "title_generation", "session_search", "web_extract",
              "vision", "soul", "mission_decompose", "delegation_triage",
              "curator_conflict", "doc_classification")

# Aliases de OpenRouter (viven en litellm_config.yaml). `openrouter-sonnet` para el
# razonamiento; `openrouter-haiku` para tareas baratas (compresión/auxiliares). Se
# definen ANTES de _POLICY_CHAINS porque la política "openrouter" los referencia.
OPENROUTER_ALIAS = "openrouter-sonnet"
OPENROUTER_HAIKU_ALIAS = "openrouter-haiku"
# Cualquier alias que salga por la cuenta de OpenRouter (para el salto opcional de
# _call_with_retries: si un alias de OpenRouter falla por AUTH/402 —clave inválida o
# sin saldo, que no salta solo— y hay red después en la cadena, se salta al siguiente).
_OPENROUTER_ALIASES = frozenset({OPENROUTER_ALIAS, OPENROUTER_HAIKU_ALIAS})

# La política adaptativa nombra capacidades, no una presunta superioridad jurídica de un
# proveedor. Opus se reserva para razonamiento jurídico complejo; Sonnet/Haiku para trabajo
# dirigido o mecánico. `max` NO es un modelo: es un esfuerzo excepcional y se exige de forma
# explícita desde el flujo que ya determinó que el caso lo amerita.
CLI_OPUS_ALIAS = "cli-claude-opus"
CLI_SONNET_ALIAS = "cli-claude-sonnet"
CLI_HAIKU_ALIAS = "cli-claude-haiku"
CLI_CODEX_ALIAS = "cli-codex"
QUALITY_ESCALATION_STANDARD = "standard"
QUALITY_ESCALATION_EXCEPTIONAL = "exceptional"
VALID_QUALITY_ESCALATIONS = frozenset({
    QUALITY_ESCALATION_STANDARD, QUALITY_ESCALATION_EXCEPTIONAL,
})
# Un expediente grande y jurídico es el único gatillo automático para el esfuerzo máximo.
# Son caracteres de entrada (no una suposición sobre el mérito del caso), por lo que el
# criterio es determinista, auditable y no añade coste al turno ordinario.
_EXCEPTIONAL_LEGAL_CONTEXT_CHARS = 40_000

# Cadenas por política. Se SUPERPONEN a _TASK_FALLBACK_CHAINS (que queda como mapa base,
# compat con tests que lo leen/mutan): un task inyectado ahí (no estándar) sigue resolviendo.
# `compression` sigue en _LOCKED_TASKS en las 3 políticas (un model explícito no la cambia).
_POLICY_CHAINS: dict[str, dict[str, list[str]]] = {
    # Calidad adaptativa — DECISIÓN DE PIPE 2026-08-14: «el más inteligente piensa y
    # orquesta y define quién ejecuta según la tarea». El razonamiento que gobierna el
    # turno (main, que orquesta, y legal_analysis, que piensa el caso) va en Opus/xhigh
    # PRIMERO, con degradación DENTRO de la misma suscripción a Sonnet (mismo proveedor,
    # mismo consentimiento, mismo pagador — no es un cambio de motor). La EJECUCIÓN
    # dirigida (hechos, investigación, redacción, verificación, edición) va en Sonnet;
    # lo mecánico en Haiku. Los timeouts de Opus ya no cuestan 4×300 s por nodo: un
    # timeout de cli-* no se reintenta dentro del alias (auditoría 2026-08-14).
    # Los asuntos jurídicos no saltan a API/local sin consentimiento explícito.
    "quality_adaptive": {
        # `main` puede transportar trabajo jurídico aunque el clasificador no haya
        # asignado aún una subtarea. Conserva el consentimiento estricto de
        # LEGAL_TASKS: la degradación es solo entre alias de la MISMA suscripción.
        "main": [CLI_OPUS_ALIAS, CLI_SONNET_ALIAS],
        "legal_analysis": [CLI_OPUS_ALIAS, CLI_SONNET_ALIAS],
        **{t: [CLI_SONNET_ALIAS]
           for t in LEGAL_TASKS if t != "legal_analysis"},
        "curator": [CLI_SONNET_ALIAS, "claude-sonnet", "mia-local"],
        "compression": [CLI_HAIKU_ALIAS, "claude-haiku"],
        **{t: [CLI_HAIKU_ALIAS, "mia-local"] for t in _AUX_TASKS},
    },
    # Suscripción de Claude Code: en funciones jurídicas no hay red pagada/local.
    # La elección de esta política es consentimiento para Claude Code, no para que Mia
    # cambie proveedor con datos del asunto. Auxiliares mantienen rutas económicas.
    "suscripcion": {
        "main": ["cli-claude"],
        **{t: ["cli-claude"] for t in LEGAL_TASKS},
        "curator": ["cli-claude", "claude-sonnet", "mia-local"],
        # Sigue BLOQUEADA (model explícito no la cambia), pero con red: si el CLI
        # falla, cae a la API haiku barata (ajuste de la revisión CP2, decisión #27).
        "compression": ["cli-claude-haiku", "claude-haiku"],
        **{t: ["cli-claude-haiku", "mia-local"] for t in _AUX_TASKS},
    },
    # Codex es un proveedor productivo alternativo, no un alias de evaluación ni un
    # fallback de Claude. Cadena de un alias: ausencia, auth o timeout se comunican y
    # preservan que el abogado eligió exactamente este motor para datos del asunto.
    "codex": {t: [CLI_CODEX_ALIAS] for t in (
        "main", *LEGAL_TASKS, "curator", "compression", *_AUX_TASKS)},
    # Nube (API Anthropic vía proxy). Restaura la decisión #7: compression=claude-haiku
    # (la clave de Anthropic volvió a funcionar, verificado 2026-07-01).
    "nube": {
        "main": ["claude-sonnet", "mia-local"],
        **{t: ["claude-sonnet"] for t in LEGAL_TASKS},
        "curator": ["claude-sonnet", "mia-local"],
        "compression": ["claude-haiku"],
        **{t: ["claude-haiku", "mia-local"] for t in _AUX_TASKS},
    },
    # Soberano: TODO local (Ollama), para despachos que exigen cero salida de datos.
    "soberano": {t: ["mia-local"] for t in ("main", *LEGAL_TASKS, "curator", "compression", *_AUX_TASKS)},
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
        **{t: [OPENROUTER_ALIAS] for t in LEGAL_TASKS},
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
_OPENROUTER_TASKS = ("main", *LEGAL_TASKS, "curator")


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
_CLI_MODEL_HINTS: dict[str, str | None] = {
    "cli-claude": None,
    CLI_OPUS_ALIAS: "opus",
    CLI_SONNET_ALIAS: "sonnet",
    CLI_HAIKU_ALIAS: "haiku",
}


def _cli_effort(alias: str, task: str | None, escalation: str | None = None) -> str:
    """Nivel de razonamiento por función, con Max únicamente en una escalada explícita.

    El gatillo es auditable: una solicitud explícita o el contexto jurídico extraordinariamente
    extenso que detecta `_automatic_quality_escalation`. Por defecto Mia usa el nivel suficiente
    y preserva costo/latencia. Las tareas auxiliares nunca escalan.
    """
    if alias == CLI_HAIKU_ALIAS:
        return "low"
    if alias == CLI_SONNET_ALIAS:
        return "high"
    if alias == CLI_CODEX_ALIAS:
        return "xhigh" if escalation == QUALITY_ESCALATION_EXCEPTIONAL else "high"
    if alias in (CLI_OPUS_ALIAS, "cli-claude"):
        if (escalation == QUALITY_ESCALATION_EXCEPTIONAL
                and task in {"main", *LEGAL_TASKS}):
            return "max"
        return "xhigh" if alias == CLI_OPUS_ALIAS else "high"
    return "medium"


def _automatic_quality_escalation(task: str | None, messages: list[dict]) -> str:
    """Aplica Max solo a expedientes jurídicos excepcionalmente extensos.

    La decisión no depende de instrucciones del usuario ni de una clasificación opaca:
    exige política adaptativa, función jurídica y un umbral fijo de contexto. Quien llama
    puede aún solicitar una escalada explícita, que queda registrada en telemetría.
    """
    if get_model_policy() != "quality_adaptive" or task not in LEGAL_TASKS:
        return QUALITY_ESCALATION_STANDARD
    size = sum(len(str(message.get("content") or "")) for message in messages)
    if size >= _EXCEPTIONAL_LEGAL_CONTEXT_CHARS:
        return QUALITY_ESCALATION_EXCEPTIONAL
    return QUALITY_ESCALATION_STANDARD

# Timeout del CLI por task (revisión CP2): el razonamiento largo (main/curator) puede
# tardar minutos; las tareas auxiliares/compresión no deben retener el request tanto.
_CLI_TIMEOUT_LONG_TASKS = frozenset({"main", "curator", "legal_analysis"})
_CLI_TIMEOUT_LONG = 300.0   # segundos — main / curator
_CLI_TIMEOUT_SHORT = 120.0  # segundos — resto de tareas

# Aviso ÚNICO por proceso cuando temperature/max_tokens se descartan en aliases cli-*
# (el CLI headless no acepta esos parámetros); evitar spamear el log por llamada.
_warned_cli_dropped_params = False


def _cli_timeout(task: str | None) -> float:
    return _CLI_TIMEOUT_LONG if task in _CLI_TIMEOUT_LONG_TASKS else _CLI_TIMEOUT_SHORT


def _default_policy() -> str:
    """Política por defecto desde config; sin valor → suscripción estable."""
    p = (getattr(config, "MIA_MODEL_POLICY", "") or "").strip().lower()
    return p if p in VALID_POLICIES else "suscripcion"


_model_policy: ContextVar[str | None] = ContextVar("mia_model_policy", default=None)

# Ruta lateral del banco: jamás se configura por tenant ni aparece en VALID_POLICIES.
# Solo el harness puede abrir este ContextVar explícitamente y siempre se restaura por token.
_EVAL_CODEX_ALIAS = "cli-codex-eval"
_eval_provider_override: ContextVar[str | None] = ContextVar(
    "mia_eval_provider_override", default=None)
_eval_provider_call_budget: ContextVar[dict[str, int] | None] = ContextVar(
    "mia_eval_provider_call_budget", default=None)


@contextmanager
def eval_provider_override(provider: str | None, *, max_calls: int = 64) -> Iterator[None]:
    """Fuerza un proveedor durante un eval; fail-closed y fuera de rutas productivas."""
    normalized = (provider or "").strip().lower()
    if normalized not in ("", "codex"):
        raise ValueError("El único override eval soportado es 'codex'.")
    if max_calls < 1:
        raise ValueError("max_calls debe ser positivo.")
    token = _eval_provider_override.set(normalized or None)
    budget_token = _eval_provider_call_budget.set(
        {"used": 0, "max": int(max_calls)} if normalized else None)
    try:
        yield
    finally:
        _eval_provider_call_budget.reset(budget_token)
        _eval_provider_override.reset(token)


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


# ── CAMBIOS DE MOTOR del turno (sesión 52) ────────────────────────────────────
# El modo de venta es la SUSCRIPCIÓN que el abogado ya paga, y la cadena de respaldo puede
# acudir a crédito de API o a OpenRouter cuando la suscripción no alcanza — eso es deliberado
# (decisión de Pipe). Lo que faltaba era DECÍRSELO: en el piloto con un expediente real la
# suscripción expiró y el turno se atendió con crédito de tarjeta sin que nada en pantalla lo
# mencionara. Un cargo que el abogado no esperaba es un cargo que no autorizó.
#
# Aquí solo se ACUMULA el hecho; el aviso en llano lo arma `aviso_cambio_de_motor` y quien
# pinta la pantalla decide dónde ponerlo. Se usa un ContextVar (mismo patrón que la política de
# modelo y el tope de gasto) para no tener que pasar un acumulador por toda la pila de llamadas.
_cambios_de_motor: ContextVar[list[dict] | None] = ContextVar("mia_cambios_de_motor", default=None)

# ── CIRCUIT-BREAKER de la suscripción por TURNO (sesión 56) ───────────────────
# El salto rápido (sesión 52) evita gastar reintentos dentro de UNA llamada, pero cada nodo
# del grafo vuelve a resolver la cadena y vuelve a intentar la suscripción desde cero: con un
# expediente que no cabe, 2-3 nodos × 300s ≈ los ~13 minutos medidos antes de que el turno
# terminara de caer al respaldo. Un timeout del CLI no es transitorio dentro del mismo turno
# (el expediente no se achica entre nodos), así que el primer timeout de un alias `cli-*`
# lo marca AGOTADO por el resto del turno y los nodos siguientes saltan directo al respaldo.
# Por ALIAS, no global: que `cli-claude` no aguante el expediente no dice nada de
# `cli-claude-haiku`, cuyas tareas auxiliares mandan prompts pequeños.
_suscripcion_agotada: ContextVar[set[str] | None] = ContextVar(
    "mia_suscripcion_agotada", default=None)


def _marcar_alias_agotado(alias: str) -> None:
    """Marca un alias de la suscripción como agotado por el resto del turno. Sin contexto de
    turno activo (tests/scripts que llaman a call_llm directo) no hace nada."""
    agotados = _suscripcion_agotada.get()
    if agotados is not None:
        agotados.add(alias)


def _alias_agotado(alias: str) -> bool:
    agotados = _suscripcion_agotada.get()
    return agotados is not None and alias in agotados

# Prefijo de los aliases que corren sobre la suscripción del abogado (subproceso al CLI). Su
# coste es CUOTA, no dólares. Todo lo demás en la cadena cuesta dinero o es local.
_PREFIJO_SUSCRIPCION = "cli-"


def _registrar_cambio_de_motor(task: str | None, desde: str, hacia: str, motivo: str) -> None:
    """Anota que el turno cambió de motor. Nunca falla: si no hay recolector activo, no hace nada
    (así los tests y los scripts que llaman a `call_llm` directo no necesitan montar contexto)."""
    registro = _cambios_de_motor.get()
    if registro is None:
        return
    registro.append({"task": task, "desde": desde, "hacia": hacia, "motivo": motivo})


@contextmanager
def recolectar_cambios_de_motor() -> Iterator[list[dict]]:
    """Recoge los cambios de motor que ocurran dentro del bloque.

    La lista se puede leer DESPUÉS de salir del bloque (es la misma que se fue llenando), que es
    como la usa el turno: abre el recolector alrededor del grafo y al terminar arma el aviso.
    """
    registro: list[dict] = []
    token = _cambios_de_motor.set(registro)
    # El recolector delimita el TURNO: el circuit-breaker de la suscripción vive y muere con él,
    # así un timeout en un turno jamás castiga al siguiente (el próximo turno vuelve a intentar
    # la suscripción primero, que es la promesa del producto).
    token_agotados = _suscripcion_agotada.set(set())
    try:
        yield registro
    finally:
        _cambios_de_motor.reset(token)
        _suscripcion_agotada.reset(token_agotados)


def aviso_cambio_de_motor(cambios: list[dict] | None) -> dict | None:
    """Aviso EN LLANO de que la suscripción no alcanzó y el turno se atendió con crédito.

    Devuelve None cuando no hay nada que decir: sin cambios, o cuando el cambio no salió de la
    suscripción hacia un motor de pago (p. ej. un salto entre motores de nube, que no cambia
    quién paga, o una caída al motor local, que tampoco cuesta dinero).

    §G: ni un alias, ni un nombre de proveedor, ni la palabra 'fallback' — el abogado lee qué
    pasó, qué le costó y qué puede hacer.
    """
    if not cambios:
        return None
    desde_suscripcion = [c for c in cambios
                         if str(c.get("desde", "")).startswith(_PREFIJO_SUSCRIPCION)
                         and not str(c.get("hacia", "")).startswith(_PREFIJO_SUSCRIPCION)
                         # La caída al motor local no cuesta dinero: afirmarle al abogado
                         # que "lo resolví con crédito de pago" sería un cobro inventado.
                         and not str(c.get("hacia", "")).startswith("mia-local")]
    if not desde_suscripcion:
        return None

    por_tiempo = any(c.get("motivo") == "timeout" for c in desde_suscripcion)
    causa = ("El trabajo era demasiado grande para tu suscripción y no alcanzó a responder"
             if por_tiempo else
             "Tu suscripción no pudo atender esta consulta")
    return {
        "hubo_cambio": True,
        "veces": len(desde_suscripcion),
        "por_tiempo": por_tiempo,
        "aviso": (
            f"{causa}. Para no dejarte sin respuesta lo resolví con crédito de pago, y eso tiene "
            "un costo que verás en el consumo de este turno. Tu suscripción se usa primero "
            "siempre; el crédito solo entra cuando ella se queda corta."
        ),
        "sugerencia": (
            "Esto es exactamente lo que evita un plan Max: los expedientes grandes caben "
            "completos en lo que ya pagas, sin cargos aparte y sin que yo tenga que quedarme a "
            "medias. Si trabajas asuntos de este tamaño, te lo recomiendo de una."
        ),
    }


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


def resolve_fallback_chain(task: str | None, model: str | None = None,
                           quality_escalation: str | None = None) -> list[str]:
    """Cadena de aliases a intentar para un `task` (sin vacíos ni duplicados), según la
    política de modelo activa (CP2 · get_model_policy()).

    - `compression` está bloqueado (decisión #7): un `model` distinto se ignora con warning.
    - `model` explícito (tarea no bloqueada) gana como cadena de UN alias (override sin fallback).
    - Sin `model`: la cadena de la política activa; un task desconocido cae a la de 'main'.
    - `quality_escalation` no altera por sí sola la cadena; habilita el esfuerzo Max solo
      durante una invocación explícitamente excepcional de la política adaptativa.
    """
    # El override del banco gana incluso sobre `model=` y tareas bloqueadas: mezclar un
    # segundo motor invalidaría el brazo. Cadena de un alias = sin fallback silencioso.
    if _eval_provider_override.get() == "codex":
        return [_EVAL_CODEX_ALIAS]
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
    # La escalada excepcional es un cambio deliberado de profundidad, no una política
    # escondida: únicamente quality_adaptive, main/legal y sin proveedor seleccionado.
    if (get_model_policy() == "quality_adaptive"
            and quality_escalation == QUALITY_ESCALATION_EXCEPTIONAL
            and task in {"main", *LEGAL_TASKS}):
        chain = [CLI_OPUS_ALIAS, *chain]
    return _dedupe_chain(chain)


def resolve_model(task: str | None, model: str | None = None) -> str:
    """Compat: primer alias de la cadena de `task` (el proveedor preferido)."""
    return resolve_fallback_chain(task, model)[0]


def _messages_with_cache(messages: list[dict], alias: str) -> list[dict]:
    """`messages` con el PREFIJO ESTABLE del system marcado para el prefix caching de
    Anthropic, o los `messages` sin tocar.

    Solo actúa para los aliases de la API directa de Anthropic (_ANTHROPIC_CACHE_ALIASES).
    El prompt_builder registró dónde termina el tier estable (capas 1-6) del system; aquí
    se parte ese string en dos bloques de content: [estable + cache_control TTL 1h] +
    [resto sin cache]. La concatenación es byte-idéntica al string original — el modelo ve
    el MISMO texto; solo se añade la metadata de cacheo. Devuelve una lista NUEVA (call_llm
    reutiliza `messages` a lo largo de la cadena de fallback y de los reintentos: nunca se
    muta). Si el system no está registrado o no es un string, se deja intacto (sin caching,
    degradación limpia)."""
    if alias not in _ANTHROPIC_CACHE_ALIASES:
        return messages
    from . import prompt_builder  # diferido: sin ciclo (prompt_builder no importa llm)

    out: list[dict] = []
    marked = False
    for m in messages:
        if (not marked and m.get("role") == "system"
                and isinstance(m.get("content"), str)):
            split = prompt_builder.cache_split(m["content"])
            if split is not None:
                stable, rest = split
                blocks: list[dict] = [{
                    "type": "text", "text": stable,
                    "cache_control": {"type": "ephemeral", "ttl": "1h"},
                }]
                if rest:
                    blocks.append({"type": "text", "text": rest})
                out.append({**m, "content": blocks})
                marked = True
                continue
        out.append(m)
    return out


def _get_client() -> Any:
    """Cliente OpenAI apuntado al proxy LiteLLM. Import diferido (como embeddings.py).

    A-BLOQ (2026-07-21) · `max_retries=0`: MIA hace SUS PROPIOS reintentos (uno por intento,
    cada uno reservado y contado por separado por el guardián de gasto — ver
    `_call_with_retries` y `eval.spend_guard`). El SDK de OpenAI/LiteLLM reintenta 2 veces por
    dentro por defecto y sólo expone el ERROR FINAL: un `APIConnectionError` de "no conecté"
    podía llegar tras 2 POST que SÍ alcanzaron al proveedor (y pudieron facturar), y el
    clasificador, viendo sólo el último, devolvía la reserva por dinero ya gastado. Con
    `max_retries=0` cada petición física es un intento único: si sale un error de conexión, es
    que ESE —el único— intento no salió, así que "no conecté" vuelve a ser cierto por
    construcción y `provider_never_reached` no abre un hueco. Los reintentos legítimos siguen
    ocurriendo, pero los hace MIA (reservados) en vez del SDK (invisibles)."""
    global _client
    if _client is None:
        from openai import OpenAI  # diferido: solo al primer call_llm real

        _client = OpenAI(base_url=config.LITELLM_BASE_URL, api_key=config.LITELLM_API_KEY,
                         max_retries=0)
    return _client


def call_llm(
    messages: list[dict],
    *,
    task: str | None = None,
    model: str | None = None,
    temperature: float | None = None,
    max_tokens: int | None = None,
    tools: list | None = None,
    quality_escalation: str | None = None,
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
    escalation = ((quality_escalation if quality_escalation is not None
                   else _automatic_quality_escalation(task, messages))
                  .strip().lower())
    if escalation not in VALID_QUALITY_ESCALATIONS:
        raise ValueError("quality_escalation debe ser 'standard' o 'exceptional'.")
    chain = resolve_fallback_chain(task, model, escalation)
    base_kwargs: dict[str, Any] = {"messages": messages}
    if temperature is not None:
        base_kwargs["temperature"] = temperature
    if max_tokens is not None:
        base_kwargs["max_tokens"] = max_tokens
    if tools:
        base_kwargs["tools"] = tools
    base_kwargs.update(extra)

    from ..metrics import usage as usage_metrics
    from ..policy import budget as policy_budget

    client = _get_client()
    last: _FallbackNeeded | None = None
    for i, alias in enumerate(chain):
        next_alias = chain[i + 1] if i + 1 < len(chain) else None
        # Circuit-breaker del turno: si este alias de la suscripción ya expiró en un nodo
        # anterior, no se vuelve a pagar el timeout — se salta directo al respaldo (con el
        # mismo registro que un salto normal, para que el aviso de costo cuente completo).
        # Si es el ÚLTIMO de la cadena se intenta igual: mejor tarde que sin respuesta.
        if alias.startswith(_PREFIJO_SUSCRIPCION) and _alias_agotado(alias) and next_alias:
            logger.warning(
                "call_llm: la suscripción (%s) ya expiró en este turno; se salta directo a %s "
                "sin volver a esperar el timeout (task=%s)", alias, next_alias, task)
            _registrar_cambio_de_motor(task, alias, next_alias, LLMErrorKind.TIMEOUT.value)
            continue
        try:
            # Prefix caching de Anthropic: marca el prefijo estable del system SOLO para
            # los aliases de la API directa (el resto recibe los messages sin cambios).
            # R4-CRÍTICO (Codex, ronda 4): la reserva/liquidación del presupuesto MENSUAL de
            # producción ya NO vive aquí (una por alias, liquidada con el usage del ÚLTIMO
            # intento). Vive DENTRO de cada intento, en `_invoke_metered` (lo llama
            # `_call_with_retries` una vez por POST físico), que es el único punto donde se
            # gasta el dinero de verdad. Así (a) los intentos que fallan tras llegar al
            # proveedor, (b) los previos a un éxito y (c) un éxito sin usage se contabilizan
            # cada uno, en vez de eludir el tope. Mismo modelo por-intento que eval.spend_guard.
            alias_messages = _messages_with_cache(messages, alias)
            retry_kwargs: dict[str, Any] = {}
            # Se omite el argumento estándar para conservar el contrato de los dobles de
            # prueba y de extensiones existentes; solo la escalada excepcional necesita
            # atravesar la pila de invocación.
            if escalation == QUALITY_ESCALATION_EXCEPTIONAL:
                retry_kwargs["quality_escalation"] = escalation
            max_retries = 0 if _eval_provider_override.get() else MAX_RETRIES
            resp = _call_with_retries(
                client, {**base_kwargs, "messages": alias_messages, "model": alias},
                max_retries, task=task, alias=alias, next_alias=next_alias, **retry_kwargs,
            )
            # Metadatos de decisión para la telemetría. No alteran la respuesta pública
            # OpenAI-compatible; sí impiden que el panel confunda un alias de ruta con el
            # modelo/esfuerzo que realmente se le pidió al CLI.
            _record_usage(
                alias, task, resp,
                effective_model=(getattr(resp, "mia_model_hint", None)
                                 or getattr(resp, "model", alias)),
                effort=(getattr(resp, "mia_effort", None)
                        or (_cli_effort(alias, task, escalation) if alias.startswith("cli-") else None)),
                quality_escalation=escalation,
            )   # CP-V1: tokens reales → turn_usage
            return resp
        except (policy_budget.BudgetExceeded, policy_budget.BudgetControlUnavailable):
            # El presupuesto MENSUAL cortó ESTE alias pagado (la reserva del primer intento no
            # cupo, o no se pudo comprobar el saldo). Si queda un respaldo GRATIS más adelante
            # en la cadena, se salta a él para proteger el tope sin frenar el trabajo; si no,
            # se propaga el corte al llamador (una llamada pagada no evade el tope). Es la
            # MISMA política de respaldo gratuito de antes, ahora disparada por intento.
            free_fallback = any(
                usage_metrics.estimated_call_cost(a, [], 1, task=task) == 0
                for a in chain[i + 1:]
            )
            if free_fallback:
                logger.warning("se omite alias pagado %s para proteger el tope; "
                               "se usa respaldo gratuito", alias)
                continue
            raise
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


def _record_usage(alias: str, task: str | None, resp: Any, *,
                  effective_model: str | None = None, effort: str | None = None,
                  quality_escalation: str | None = None) -> None:
    """CP-V1 (Ola 4): registra el uso real de la llamada (tokens→costo) en el buffer
    de metrics/usage. Cubre las 3 políticas: la API/OpenRouter traen `resp.usage`
    OpenAI-compatible y el CLI de la suscripción también lo construye
    (subscription_llm). Sin scope fijado (gates offline) es un no-op. JAMÁS rompe
    el turno: cualquier fallo se loguea y se sigue."""
    try:
        from ..metrics import usage as usage_metrics  # import diferido (sin ciclos)

        # finish_reason distingue una respuesta completa ('stop') de una truncada por tope
        # ('length') o de tool_calls; defensivo porque el CLI de suscripción puede no traerlo.
        stop_reason = None
        try:
            choices = getattr(resp, "choices", None) or []
            if choices:
                stop_reason = getattr(choices[0], "finish_reason", None)
        except Exception:  # noqa: BLE001 — nunca romper por leer un campo opcional
            stop_reason = None
        usage_metrics.record(
            alias, task, getattr(resp, "usage", None), stop_reason=stop_reason,
            effective_model=effective_model or getattr(resp, "mia_model_hint", None)
            or getattr(resp, "model", alias),
            effort=effort or getattr(resp, "mia_effort", None),
            quality_escalation=quality_escalation,
        )
    except Exception:  # noqa: BLE001 — una métrica nunca tumba una respuesta buena
        logger.exception("no se pudo registrar el uso (alias=%s task=%s)", alias, task)


def _invoke(client: Any, alias: str, kwargs: dict[str, Any], task: str | None = None,
            quality_escalation: str | None = None) -> Any:
    """Despacha UNA llamada según el alias: los "cli-*" van al CLI de la suscripción
    (agent/subscription_llm); el resto, al proxy LiteLLM (cliente OpenAI). Los errores de
    ambos caminos pasan por el MISMO error_classifier/should_fallback aguas arriba."""
    if alias == _EVAL_CODEX_ALIAS:
        if _eval_provider_override.get() != "codex":
            raise RuntimeError("cli-codex-eval solo puede ejecutarse dentro del harness eval.")
        from ..eval.codex_cli_adapter import call_graph_cli

        budget = _eval_provider_call_budget.get()
        if budget is None or budget["used"] >= budget["max"]:
            raise RuntimeError("tope_de_llamadas_codex_eval_alcanzado")
        budget["used"] += 1

        if kwargs.get("tools"):
            logger.warning("el brazo Codex eval no admite tools; se ignoran en esta llamada")
        return call_graph_cli(
            kwargs["messages"], timeout=int(_cli_timeout(task)),
            reasoning_effort="max",
        )
    if alias == CLI_CODEX_ALIAS:
        from . import codex_subscription_llm

        if kwargs.get("tools"):
            logger.warning("Codex productivo no admite tools; se ignoran en esta llamada")
        dropped = [k for k in ("temperature", "max_tokens") if kwargs.get(k) is not None]
        if dropped:
            logger.warning("Codex productivo descarta %s; el CLI aislado no los acepta", dropped)
        return codex_subscription_llm.call_cli(
            kwargs["messages"], timeout=_cli_timeout(task),
            effort=_cli_effort(alias, task, quality_escalation),
        )
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
            effort=_cli_effort(alias, task, quality_escalation),
        )
    return client.chat.completions.create(**kwargs)


def _invoke_metered(client: Any, alias: str, kwargs: dict[str, Any],
                    task: str | None = None,
                    quality_escalation: str | None = None) -> Any:
    """UN intento físico contra el proveedor, con la reserva/liquidación del presupuesto
    MENSUAL de producción POR INTENTO (R4-CRÍTICO, Codex ronda 4).

    El dinero se gasta en CADA intento que sale al proveedor, no en `call_llm`:
    `_call_with_retries` invoca esto hasta MAX_RETRIES+1 veces por alias y `call_llm` recorre
    la cadena. Reservar UNA vez por alias y liquidar con el usage del ÚLTIMO intento dejaba sin
    contabilizar (a) los intentos que fallaron tras llegar al proveedor, (b) los previos a un
    éxito, y (c) un éxito sin usage (liquidaba a 0) — hasta 4 POST pagados por proveedor que
    eludían el tope mensual. Mismo modelo por-intento que `eval.spend_guard._guarded_invoke`
    (fuente de inspiración):

      · reserva la estimación de ESTE intento antes de salir;
      · fallo INCIERTO (llegó o pudo llegar al proveedor) → COBRA la estimación (no libera);
      · `provider_never_reached` DEMOSTRABLE → devuelve la reserva (el proveedor no cobró);
      · éxito con usage → COBRA el coste real (`cost_usd_cached`, la MISMA fuente única que el
        panel y el banco: escritura de caché 2.00x FUERA de prompt_tokens, lectura 0.10x DENTRO;
        sin tokens de caché es IDÉNTICO a la tarifa plana — R3-ALTO);
      · éxito SIN usage legible → COBRA la estimación (NUNCA 0).

    Sin scope (gates offline), scope de EVAL (lo gobierna `eval.spend_guard`, fail-closed) o
    coste 0 (aliases `cli-*`/local de la política de suscripción): NO reserva — delega directo
    y la suscripción sigue costando cero. `BudgetExceeded`/`BudgetControlUnavailable` de la
    reserva se PROPAGAN a `call_llm`, que decide el respaldo gratuito de la cadena.
    """
    from ..metrics import usage as usage_metrics
    from ..policy import budget as policy_budget

    scope = usage_metrics.current_scope()
    estimate = usage_metrics.estimated_call_cost(
        alias, kwargs.get("messages") or [], kwargs.get("max_tokens"),
        task=task, tools=kwargs.get("tools"))
    is_eval = scope is not None and scope[2] == "eval"
    if scope is None or estimate <= 0 or is_eval:
        return _invoke(client, alias, kwargs, task, quality_escalation)

    budget_tenant = scope[0]
    hold_id = policy_budget.reserve_call_sync(budget_tenant, estimate, model=alias, task=task)
    if not hold_id:                       # estimate>0 pero la reserva no apartó nada: sin cobro
        return _invoke(client, alias, kwargs, task, quality_escalation)
    try:
        resp = _invoke(client, alias, kwargs, task, quality_escalation)
    except BaseException as exc:
        # INCIERTO se cobra; solo un fallo que DEMOSTRABLEMENTE no llegó al proveedor devuelve.
        never_reached = provider_never_reached(exc)
        policy_budget.finish_call_sync(
            budget_tenant, hold_id, 0.0 if never_reached else estimate)
        raise
    resp_usage = getattr(resp, "usage", None)
    cache_read, cache_creation = usage_metrics._cache_tokens(resp_usage)
    prompt = int(getattr(resp_usage, "prompt_tokens", 0) or 0)
    completion = int(getattr(resp_usage, "completion_tokens", 0) or 0)
    if resp_usage is None or (prompt == 0 and completion == 0
                              and cache_read == 0 and cache_creation == 0):
        actual = estimate                 # (c) sin usage no se puede afirmar menos → cobra estim.
    else:
        actual = usage_metrics.cost_usd_cached(
            alias, prompt, completion, cache_read, cache_creation)
    policy_budget.finish_call_sync(budget_tenant, hold_id, actual)
    return resp


def _call_with_retries(
    client: Any,
    kwargs: dict[str, Any],
    max_retries: int,
    *,
    task: str | None,
    alias: str,
    next_alias: str | None,
    quality_escalation: str | None = None,
) -> Any:
    """Ejecuta UN alias con reintentos. Devuelve la respuesta o decide el destino del error:

    - CONTEXT_TOO_LONG → propaga la original (no reintenta, no salta);
    - error saltable (should_fallback), sea inmediato (model_unavailable) o tras agotar los
      reintentos (rate_limit/timeout/network/server) → `_FallbackNeeded` (la cadena avanza);
    - error no saltable (AUTH/UNKNOWN) → LLMError inmediato (fail-fast).
    """
    for attempt in range(max_retries + 1):     # 1 intento inicial + hasta max_retries reintentos
        try:
            if quality_escalation is None:
                return _invoke_metered(client, alias, kwargs, task)
            return _invoke_metered(client, alias, kwargs, task, quality_escalation)
        except Exception as exc:               # noqa: BLE001 — se clasifica y re-lanza abajo
            # El presupuesto MENSUAL (R4-CRÍTICO) reserva/ liquida DENTRO de `_invoke_metered`,
            # por intento. Un corte del tope NO es un error del proveedor: no se clasifica ni se
            # reintenta aquí; se propaga a `call_llm`, que decide el respaldo gratuito de la
            # cadena. (Import diferido para no crear ciclo al cargar el módulo.)
            from ..policy.budget import BudgetControlUnavailable, BudgetExceeded
            if isinstance(exc, (BudgetExceeded, BudgetControlUnavailable)):
                raise
            kind = classify_llm_error(exc)

            if kind is LLMErrorKind.CONTEXT_TOO_LONG:
                logger.warning("call_llm context_too_long (task=%s alias=%s): %s",
                               task, alias, exc)
                raise                          # propaga original: lo maneja la compresión

            # SALTO RÁPIDO ante timeout de la SUSCRIPCIÓN (sesión 52, medido con un expediente
            # real). Un timeout del CLI de la suscripción con un expediente grande no es un
            # tropiezo transitorio: es que el trabajo no cabe en ese motor, y el reintento manda
            # EL MISMO prompt gigante, que vuelve a expirar. En el piloto costó tres esperas de
            # 300s —15 minutos tirados— antes de saltar al motor de crédito, que respondió a la
            # primera. Ante timeout de un alias `cli-*` se salta ya, en vez de agotar reintentos
            # que por construcción van a fallar igual. Los demás errores del CLI (y los timeouts
            # de cualquier otro proveedor, que sí suelen ser transitorios) mantienen su política
            # de reintento intacta.
            if kind is LLMErrorKind.TIMEOUT and alias.startswith("cli-"):
                # Sesión 56: todo timeout de la suscripción dispara el circuit-breaker del
                # TURNO — los nodos siguientes del grafo ya no vuelven a intentar este alias
                # (el expediente no se achica entre nodos; eran ~300s perdidos por nodo).
                _marcar_alias_agotado(alias)

            if (kind is LLMErrorKind.TIMEOUT and alias.startswith("cli-")
                    and attempt < max_retries and next_alias):
                logger.warning(
                    "call_llm: timeout de la suscripción (task=%s alias=%s) — el trabajo no cabe "
                    "en ese motor y reintentar manda el mismo prompt: se salta ya a %s sin gastar "
                    "los %d reintentos", task, alias, next_alias, max_retries)
                _registrar_cambio_de_motor(task, alias, next_alias, kind.value)
                raise _FallbackNeeded(kind, exc) from exc

            # Reintento dentro del alias mientras queden intentos y sea transitorio.
            # EXCEPCIÓN (auditoría 2026-08-14): un timeout de `cli-*` es determinista
            # por volumen — reintentar manda el MISMO prompt y vuelve a expirar. Con
            # respaldo se salta (bloque de arriba); SIN respaldo (cadenas de un alias:
            # quality_adaptive/codex) tampoco se reintenta: eran hasta 4×300 s por nodo
            # para fallar igual. Falla claro ya.
            if (is_retryable(kind) and attempt < max_retries
                    and not (kind is LLMErrorKind.TIMEOUT and alias.startswith("cli-"))):
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
                _registrar_cambio_de_motor(task, alias, next_alias, kind.value)
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
