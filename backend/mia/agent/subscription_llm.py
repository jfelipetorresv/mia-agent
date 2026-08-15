"""Mia · agent.subscription_llm — proveedor "suscripción": CLI `claude` headless (CP2).

Motor por SUSCRIPCIÓN (decisión #27): en la política `suscripcion` el cerebro principal
de Mia es la suscripción de Claude Code del abogado — el CLI `claude` instalado en la
máquina — sin billing por API. Este módulo invoca el CLI en modo print (headless) y
adapta su JSON a la forma OpenAI-compatible que consume `call_llm` / `graph.py`
(`resp.choices[0].message.content` + `resp.usage.prompt_tokens/completion_tokens`).

Flags verificados EN VIVO con `claude --help` + llamadas de prueba (2026-07-01):
  · `-p --output-format json --max-turns 1` → una respuesta JSON única y sale.
    (`--max-turns` no aparece en --help pero está aceptado — validado en vivo.)
  · `--tools ""`               → deshabilita TODAS las herramientas built-in (documentado
    en --help: 'Use "" to disable all tools'); probado en vivo junto al resto de flags.
  · `--strict-mcp-config`      → solo usa MCP de `--mcp-config`; como NO pasamos
    `--mcp-config`, no se carga NINGÚN servidor MCP. Probado en vivo.
  · `--setting-sources project`→ NO carga settings/CLAUDE.md del usuario (sin esto, la
    respuesta arrastraba el contexto personal del abogado). Con cwd=MIA_HOME tampoco hay
    proyecto → sesión limpia. Probado en vivo.
  · `--model haiku`            → alias aceptado (exit 0, is_error=false) en prueba viva;
    la suscripción puede rutearlo a su modelo pequeño por defecto.

SEGURIDAD (revisión CP2, 2026-07-01):
  · TODO el contenido (system + conversación) viaja por STDIN con separadores claros
    (=== INSTRUCCIONES DEL SISTEMA === / === SOLICITUD ===). NUNCA como argumento de
    línea de comandos: el system incluye texto influenciado por el tenant y un argumento
    hostil podría explotar la expansión de cmd.exe (BatBadBut, CVE-2024-24576). Además
    el stdin no tiene el límite de ~32k chars de la línea de comandos de Windows.
  · En Windows solo se ejecuta un `claude` resuelto a `.exe` real: si `shutil.which`
    devuelve un `.cmd`/`.bat`/`.ps1`, ejecutarlo con lista de args pasa por cmd.exe
    (misma superficie BatBadBut) → se trata como CLI NO disponible y la cadena de
    fallback salta al siguiente proveedor.
  · El subproceso recibe un entorno SANEADO (_sanitized_env): se eliminan variables con
    API_KEY / SECRET / PASSWORD / TOKEN en el nombre, DATABASE_URL y PG_*. Doble motivo:
    (1) con ANTHROPIC_API_KEY presente el CLI facturaría por API en vez de usar la
    SUSCRIPCIÓN (derrota el propósito del feature), y (2) el CLI no necesita los secretos
    de Mia. La sesión OAuth del CLI vive en el perfil del usuario (verificado en vivo:
    la llamada funciona igual con el entorno saneado).

cwd del subproceso = MIA_HOME (mia-data/): el CLI carga contexto de proyecto según su
cwd; anclarlo al directorio de datos evita heredar el CLAUDE.md del repo.

Errores → excepciones con `status_code` para que `error_classifier` las categorice y la
cadena de fallback de `call_llm` salte al siguiente proveedor:
  · CLI ausente            → SubscriptionCLIUnavailable (404 → MODEL_UNAVAILABLE, salto inmediato)
  · timeout                → TimeoutError (→ TIMEOUT, reintenta y luego salta)
  · exit!=0 / is_error /
    JSON no parseable      → SubscriptionCLIError (api_error_status del CLI si vino;
                             si no, 500 → SERVER_ERROR, reintenta y luego salta)
"""
from __future__ import annotations

import json
import logging
import os
import shutil
import subprocess
from pathlib import Path
from types import SimpleNamespace
from typing import Any

from .. import config

logger = logging.getLogger("mia.agent.subscription_llm")

DEFAULT_TIMEOUT = 300  # segundos; configurable por llamada

# Persona ESTÁTICA que reemplaza el system prompt propio del CLI (Claude Code trae una
# personalidad de asistente de código que exige respuestas ultra-concisas: medido en vivo
# 2026-07-01, una demanda salió de 148 chars con la persona default vs 2.410 con override).
# Es una constante SIN contenido del tenant → seguro pasarla como argumento; las
# instrucciones reales (con material del tenant) siguen viajando por stdin.
_PERSONA_OVERRIDE = (
    "Eres Mia, agente jurídica cognitiva de un despacho de abogados. Sigue exactamente "
    "las instrucciones que llegan bajo el encabezado '=== INSTRUCCIONES DEL SISTEMA ===' "
    "del mensaje. Produce documentos y análisis jurídicos COMPLETOS y detallados: nunca "
    "resumas, recortes ni abrevies por brevedad; la extensión que el trabajo jurídico "
    "requiera es la correcta."
)

# Ver el docstring del módulo: cada flag fue confirmado en vivo el 2026-07-01.
_BASE_FLAGS = [
    "-p", "--output-format", "json", "--max-turns", "1",
    "--tools", "",              # sin herramientas built-in
    "--strict-mcp-config",      # sin --mcp-config ⇒ ningún servidor MCP
    "--setting-sources", "project",  # sin settings/CLAUDE.md del usuario
    "--system-prompt", _PERSONA_OVERRIDE,  # anula la persona concisa de Claude Code (estática, sin tenant)
]

# Aliases de modelo que el CLI acepta: "haiku" confirmado en vivo (exit 0, is_error=false);
# "sonnet"/"opus" documentados como ejemplos en `claude --help`. Cualquier otro hint se
# ignora con warning (no se arriesga un 404 por un alias inventado).
_ACCEPTED_MODEL_HINTS = frozenset({"haiku", "sonnet", "opus"})
# `--effort` VERIFICADO contra el `claude --help` real el 2026-08-14: el CLI documenta
# `--effort <level> (low, medium, high, xhigh, max)` — coincide exactamente con este set.
# No es una promesa de que todos los planes tengan el mismo techo: si el CLI no
# acepta un nivel, devuelve su error estructurado y la cadena degrada de forma visible.
_ACCEPTED_EFFORTS = frozenset({"low", "medium", "high", "xhigh", "max"})


def supported_efforts() -> tuple[str, ...]:
    """Niveles de esfuerzo que Mia puede pedir al CLI instalado.

    Es una interfaz pública intencional: la superficie de configuración no debe
    depender de la constante interna que también protege la construcción del comando.
    """
    return tuple(sorted(_ACCEPTED_EFFORTS))

_SYS_HEADER = "=== INSTRUCCIONES DEL SISTEMA ==="
_REQ_HEADER = "=== SOLICITUD ==="

# Variables de entorno que NUNCA deben llegar al subproceso del CLI (revisión CP2):
# cualquier nombre que CONTENGA estas subcadenas (case-insensitive)…
_SENSITIVE_NAME_PARTS = ("API_KEY", "SECRET", "PASSWORD", "TOKEN")
# …más estos nombres/prefijos exactos (conexión a la DB de Mia).
_SENSITIVE_EXACT = ("DATABASE_URL",)
_SENSITIVE_PREFIXES = ("PG_",)


def _is_sensitive_env(name: str) -> bool:
    up = name.upper()
    return (any(p in up for p in _SENSITIVE_NAME_PARTS)
            or up in _SENSITIVE_EXACT
            or any(up.startswith(p) for p in _SENSITIVE_PREFIXES))


def _sanitized_env() -> dict[str, str]:
    """Entorno para el subproceso del CLI SIN los secretos de Mia (ver docstring del
    módulo). Conserva PATH/USERPROFILE/HOME/APPDATA/TEMP etc.: el CLI los necesita para
    encontrar su sesión OAuth local. Quitar ANTHROPIC_API_KEY es lo que garantiza que el
    CLI use la SUSCRIPCIÓN y no facture por API."""
    return {k: v for k, v in os.environ.items() if not _is_sensitive_env(k)}


class SubscriptionCLIError(RuntimeError):
    """Fallo del CLI `claude`. Lleva `status_code` para que error_classifier mapee el kind
    (500 → SERVER_ERROR salvo que el CLI reporte `api_error_status`)."""

    def __init__(self, message: str, *, status_code: int = 500,
                 subtype: str | None = None, stderr: str | None = None) -> None:
        super().__init__(message)
        self.status_code = status_code
        self.subtype = subtype
        self.stderr = stderr


class SubscriptionCLIUnavailable(SubscriptionCLIError):
    """El CLI `claude` no está instalado o no está en el PATH.

    status 404 → MODEL_UNAVAILABLE → la cadena de fallback salta al siguiente proveedor
    de inmediato (sin reintentos)."""

    def __init__(self, message: str) -> None:
        super().__init__(message, status_code=404)


def _resolve_exe() -> str | None:
    """Ruta del CLI `claude` ejecutable de forma SEGURA, o None si no hay.

    En Windows, si `which` resuelve a un `.cmd`/`.bat`/`.ps1` (no un `.exe`), ejecutarlo
    con lista de args pasa por cmd.exe → inyección por metacaracteres (BatBadBut,
    CVE-2024-24576). En ese caso se trata como NO disponible (con warning) y la cadena
    de fallback de call_llm salta al siguiente proveedor."""
    exe = shutil.which("claude")
    if exe is None:
        return None
    if os.name == "nt" and not exe.lower().endswith(".exe"):
        logger.warning(
            "El CLI 'claude' resolvió a '%s' (no es un .exe): ejecutarlo pasaría por "
            "cmd.exe (riesgo de inyección BatBadBut/CVE-2024-24576). Se trata como CLI "
            "no disponible; la cadena de fallback usará el siguiente proveedor.", exe,
        )
        return None
    return exe


def is_available() -> bool:
    """True si el CLI `claude` está en el PATH y es ejecutable de forma segura (.exe)."""
    return _resolve_exe() is not None


def _flatten_content(content: Any) -> str:
    """Contenido de un message a texto plano (las partes multimodales se serializan)."""
    if content is None:
        return ""
    if isinstance(content, str):
        return content
    try:
        return json.dumps(content, ensure_ascii=False)
    except (TypeError, ValueError):
        return str(content)


def _split_messages(messages: list[dict]) -> tuple[str, str]:
    """Separa los messages en (system, prompt_aplanado).

    Los system van juntos (irán por STDIN bajo === INSTRUCCIONES DEL SISTEMA ===, nunca
    como argumento); el resto de la conversación se aplana a UN texto con marcas de rol
    claras, porque el CLI recibe un solo prompt."""
    system_parts: list[str] = []
    convo_parts: list[str] = []
    for m in messages or []:
        role = (m.get("role") or "user").lower()
        text = _flatten_content(m.get("content")).strip()
        if not text:
            continue
        if role == "system":
            system_parts.append(text)
        elif role == "assistant":
            convo_parts.append(f"[RESPUESTA PREVIA DEL ASISTENTE]\n{text}")
        else:  # user / tool / cualquier otro rol
            convo_parts.append(f"[MENSAJE]\n{text}")
    system = "\n\n".join(system_parts).strip()
    prompt = "\n\n".join(convo_parts).strip() or "(sin mensaje)"
    return system, prompt


def _build_command(exe: str, model_hint: str | None, effort: str | None = None) -> list[str]:
    """Arma la lista de args (NUNCA shell). Defensa en profundidad: NINGÚN contenido
    del tenant (system ni conversación) viaja como argumento — todo va por stdin; aquí
    solo entran flags fijos y el alias de modelo validado contra una allowlist.

    Sin `model_hint` explícito se usa el default de config (MIA_CLI_MODEL, "sonnet"):
    el modelo default de la suscripción puede ser uno grande y lento escribiendo
    documentos extensos — medido en vivo 2026-07-01: un borrador legal completo
    excedió los 300s con el default, mientras sonnet lo produce en ~1-2 min."""
    cmd = [exe, *_BASE_FLAGS]
    hint = model_hint or getattr(config, "MIA_CLI_MODEL", "sonnet")
    if hint:
        if hint in _ACCEPTED_MODEL_HINTS:
            cmd += ["--model", hint]
        else:
            logger.warning("model_hint '%s' no confirmado para el CLI claude; se ignora", hint)
    if effort:
        if effort in _ACCEPTED_EFFORTS:
            cmd += ["--effort", effort]
        else:
            logger.warning("effort '%s' no confirmado para el CLI claude; se ignora", effort)
    return cmd


def _to_openai_response(data: dict, *, model_hint: str | None, effort: str | None) -> Any:
    """Adapta el JSON del CLI a la forma OpenAI-compatible que consumen llm.py/graph.py."""
    text = data.get("result") or ""
    u = data.get("usage") or {}

    def _n(key: str) -> int:
        v = u.get(key)
        return int(v) if isinstance(v, (int, float)) else 0

    # prompt_tokens incluye los tokens de caché: es lo que el abogado "gastó" de contexto.
    prompt_tokens = _n("input_tokens") + _n("cache_creation_input_tokens") + _n("cache_read_input_tokens")
    completion_tokens = _n("output_tokens")
    usage = SimpleNamespace(
        prompt_tokens=prompt_tokens,
        completion_tokens=completion_tokens,
        total_tokens=prompt_tokens + completion_tokens,
    )
    message = SimpleNamespace(role="assistant", content=text, tool_calls=None)
    choice = SimpleNamespace(index=0, message=message, finish_reason="stop")
    response = SimpleNamespace(
        id=data.get("session_id") or "cli-claude",
        model="cli-claude",
        choices=[choice],
        usage=usage,
    )
    # Telemetría de verdad: no inferir después el modelo configurado de una etiqueta de
    # ruta. Estos dos campos no cambian el contrato OpenAI-compatible, pero permiten que
    # el router y sus pruebas registren qué se pidió efectivamente al CLI.
    response.mia_model_hint = model_hint or getattr(config, "MIA_CLI_MODEL", "sonnet")
    response.mia_effort = effort or ""
    return response


def call_cli(messages: list[dict], model_hint: str | None = None,
             timeout: float = DEFAULT_TIMEOUT, effort: str | None = None) -> Any:
    """Invoca el CLI `claude` headless y devuelve una respuesta OpenAI-compatible.

    `model_hint` (p. ej. "haiku") se pasa como `--model` solo si es un alias confirmado.
    `effort` se pasa como `--effort` solo desde la política interna de calidad de Mia.
    Lanza TimeoutError / SubscriptionCLIError / SubscriptionCLIUnavailable — todas
    clasificables por error_classifier para que la cadena de fallback avance."""
    exe = _resolve_exe()
    if exe is None:
        raise SubscriptionCLIUnavailable(
            "El CLI 'claude' no está instalado, no está en el PATH, o no resolvió a un "
            ".exe ejecutable de forma segura en esta máquina."
        )

    system, prompt = _split_messages(messages)
    cmd = _build_command(exe, model_hint, effort)
    # El system SIEMPRE va por stdin (nunca como argumento — ver docstring del módulo).
    if system:
        prompt = f"{_SYS_HEADER}\n{system}\n\n{_REQ_HEADER}\n{prompt}"

    # cwd = MIA_HOME (directorio de datos): NO heredar el CLAUDE.md del repo.
    cwd = Path(config.MIA_HOME)
    try:
        cwd.mkdir(parents=True, exist_ok=True)
    except OSError:
        logger.warning("no se pudo asegurar MIA_HOME=%s como cwd del CLI", cwd)

    try:
        proc = subprocess.run(
            cmd,                      # lista de args — nunca shell=True
            input=prompt,             # el prompt viaja por stdin (sin límite de cmdline)
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=timeout,
            cwd=str(cwd),
            env=_sanitized_env(),     # sin secretos de Mia ni ANTHROPIC_API_KEY (ver docstring)
        )
    except subprocess.TimeoutExpired as exc:
        raise TimeoutError(
            f"El CLI 'claude' no respondió en {timeout:.0f}s (timeout)."
        ) from exc

    stdout = (proc.stdout or "").strip()
    stderr = (proc.stderr or "").strip()

    data: dict | None = None
    if stdout:
        try:
            parsed = json.loads(stdout)
            if isinstance(parsed, dict):
                data = parsed
        except (json.JSONDecodeError, ValueError):
            data = None

    if proc.returncode != 0 or data is None or data.get("is_error"):
        subtype = (data or {}).get("subtype")
        api_status = (data or {}).get("api_error_status")
        detail = (data or {}).get("result") or stderr or stdout[:500] or "sin salida del CLI"
        raise SubscriptionCLIError(
            f"CLI claude falló (exit={proc.returncode}, subtype={subtype}): {detail}",
            status_code=api_status if isinstance(api_status, int) else 500,
            subtype=subtype if isinstance(subtype, str) else None,
            stderr=stderr or None,
        )

    return _to_openai_response(data, model_hint=model_hint, effort=effort)
