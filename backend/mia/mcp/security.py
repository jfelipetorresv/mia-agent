"""Mia · mcp.security — primitivas de seguridad para conectar sistemas vía MCP (CP-E6).

Cada función ELEVA una costura ya probada del proyecto en vez de reinventarla:

- ``build_safe_env``  →  entorno saneado del subproceso de CP-S3 (agent_hub) + las
  variables DECLARADAS del servidor. Es el ``_build_safe_env`` de Hermes, pero
  cimentado en la allowlist más estricta que Mia ya usa para los CLIs externos.
- ``interpolate_placeholders`` / ``find_unresolved_placeholders``  →  resuelve
  ``${CLAVE}`` con un resolver inyectado (en producción, el scope de secretos por
  tenant de CP-S2, fail-closed). Un placeholder REQUERIDO sin resolver no arranca.
- ``validate_server_entry``  →  heurística de exfiltración de Hermes (mcp_security):
  un intérprete de shell cuyos args invocan egreso de red se marca sospechoso.
- ``sanitize_error``  →  reusa el redactor de ~39 patrones de CP-S2 (redact_text)
  para que ningún secreto salga en un mensaje de error hacia el LLM o la pantalla.
- ``seal_tool_output``  →  sella la salida del servidor como contenido NO confiable
  (cuarentena universal de CP-S1): datos, no órdenes.
- ``scan_tool_description``  →  avisa (no bloquea) si la descripción de una tool
  trae forma de inyección de prompt.
- ``write_token_file``  →  material de token en disco con permisos 0600.
"""
from __future__ import annotations

import logging
import os
import re
import shlex
import stat
from typing import Any, Callable, Mapping, Optional

from ..agents import untrusted
from ..gateway.agent_hub import sanitize_subprocess_env
from ..security import redact_text

logger = logging.getLogger("mia.mcp.security")


class MCPSecurityError(RuntimeError):
    """La configuración de un servidor MCP tiene forma peligrosa (p. ej. exfiltración).
    El servidor NO se lanza."""


class MCPConfigError(RuntimeError):
    """Configuración incompleta o inconsistente de un servidor MCP (p. ej. un secreto
    requerido sin resolver). Fail-closed: no se lanza a ciegas."""


# ── ${VAR} placeholders ──────────────────────────────────────────────────────
# Cualquier carácter salvo '}' en el nombre (soporta CLAVES con guiones/puntos).
_PLACEHOLDER = re.compile(r"\$\{([^}]+)\}")


def interpolate_placeholders(value: Any, resolver: Callable[[str], Optional[str]]) -> Any:
    """Resuelve ``${CLAVE}`` recursivamente en str/dict/list con `resolver(nombre)`.

    Si `resolver` devuelve None para un nombre, se CONSERVA el placeholder literal
    (para que `find_unresolved_placeholders` lo detecte después y el llamador falle
    cerrado). No se cae al entorno del proceso: eso sería servir la credencial de la
    instalación "por si acaso" — justo lo que CP-S2 prohíbe."""
    if isinstance(value, str):
        def _sub(m: "re.Match[str]") -> str:
            name = m.group(1)
            resolved = resolver(name)
            return resolved if resolved is not None else m.group(0)
        return _PLACEHOLDER.sub(_sub, value)
    if isinstance(value, Mapping):
        return {k: interpolate_placeholders(v, resolver) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [interpolate_placeholders(v, resolver) for v in value]
    return value


def find_unresolved_placeholders(value: Any) -> list[str]:
    """Lista de nombres de ``${CLAVE}`` que quedaron SIN resolver en la estructura.

    Vacía = todo resuelto. El llamador la usa para fallar cerrado antes de lanzar
    un servidor con un secreto colgando."""
    found: list[str] = []
    if isinstance(value, str):
        found.extend(m.group(1) for m in _PLACEHOLDER.finditer(value))
    elif isinstance(value, Mapping):
        for v in value.values():
            found.extend(find_unresolved_placeholders(v))
    elif isinstance(value, (list, tuple)):
        for v in value:
            found.extend(find_unresolved_placeholders(v))
    # dedup preservando orden
    seen: set[str] = set()
    out: list[str] = []
    for name in found:
        if name not in seen:
            seen.add(name)
            out.append(name)
    return out


# ── entorno saneado del subproceso (eleva CP-S3) ─────────────────────────────
def build_safe_env(declared_env: Optional[Mapping[str, str]] = None) -> dict[str, str]:
    """Entorno para el subproceso de un servidor MCP: allowlist mínima del SO
    (la misma de los CLIs externos, CP-S3) + SOLO las variables DECLARADAS por el
    servidor (ya resueltas). Ninguna clave de la instalación se hereda.

    Espejo del ``_build_safe_env`` de Hermes, cimentado en el saneador que Mia ya
    aplica en gateway.agent_hub."""
    env = sanitize_subprocess_env(dict(os.environ))
    if declared_env:
        for k, v in declared_env.items():
            if v is not None:
                env[str(k)] = str(v)
    return env


# ── validación de forma sospechosa (puerto de Hermes mcp_security) ───────────
_SHELL_INTERPRETERS = frozenset({
    "bash", "sh", "zsh", "dash", "fish",
    "cmd", "cmd.exe", "powershell", "powershell.exe", "pwsh", "pwsh.exe",
})

_EGRESS_PATTERN = re.compile(
    r"(?<![\w.-])(?:curl|wget|nc|ncat|socat)(?![\w.-])"
    r"|/dev/tcp/"
    r"|\bInvoke-WebRequest\b"
    r"|\bInvoke-RestMethod\b"
    r"|\bSystem\.Net\.WebClient\b",
    re.IGNORECASE,
)

_EXFIL_HINT_PATTERN = re.compile(
    r"\.env\b|--data-binary|--data-raw|\b-X\s+POST\b|\bPOST\b|<\s*[^\s]+",
    re.IGNORECASE,
)


def _command_basename(command: Any) -> str:
    text = str(command or "").strip()
    if not text:
        return ""
    try:
        parts = shlex.split(text, posix=(os.name != "nt"))
    except ValueError:
        parts = text.split()
    first = parts[0] if parts else text
    return os.path.basename(first).lower()


def _inline_script(args: Any) -> str:
    if args is None:
        return ""
    if isinstance(args, (list, tuple)):
        return " ".join(str(item) for item in args)
    return str(args)


def validate_server_entry(name: str, entry: Mapping[str, Any]) -> list[str]:
    """Avisos de seguridad para la config de un servidor MCP (lista vacía = limpio).

    Heurística ESTRECHA de exfiltración de Hermes (#45620): un intérprete de shell
    cuyos argumentos invocan egreso de red. NO es una whitelist — un servidor local
    legítimo puede usar comandos propios, scripts de Python, npx, uvx, etc."""
    if not isinstance(entry, Mapping):
        return []
    basename = _command_basename(entry.get("command"))
    if basename not in _SHELL_INTERPRETERS:
        return []
    script = _inline_script(entry.get("args"))
    if not script or not _EGRESS_PATTERN.search(script):
        return []
    issue = (f"El servidor '{name}' usa un intérprete de shell ('{entry.get('command')}') "
             f"con egreso de red en sus argumentos")
    if _EXFIL_HINT_PATTERN.search(script):
        issue += " y argumentos con forma de exfiltración"
    return [issue]


# ── redacción de errores + sellado de salida ─────────────────────────────────
def sanitize_error(text: Any) -> str:
    """Redacta credenciales de un texto de error antes de devolverlo al LLM/pantalla.
    Reusa el redactor de ~39 patrones de CP-S2 (una fuente de verdad, no un regex
    paralelo que se quede corto)."""
    return redact_text(str(text))


def seal_tool_output(server_label: str, text: str) -> str:
    """Sella la salida de un servidor MCP como contenido NO confiable (CP-S1):
    viaja como datos, jamás como instrucciones, hacia cualquier prompt que la lea."""
    return untrusted.wrap_untrusted(f"salida del sistema externo '{server_label}'", text)


# ── escaneo de descripciones de tools (aviso, no bloqueo) ────────────────────
_INJECTION_PATTERNS = [
    (re.compile(r"ignore\s+(all\s+)?previous\s+instructions", re.I),
     "intento de anular instrucciones ('ignore previous instructions')"),
    (re.compile(r"olvida\s+(todas\s+)?las\s+instrucciones", re.I),
     "intento de anular instrucciones (en español)"),
    (re.compile(r"you\s+are\s+now\s+a", re.I), "intento de suplantar identidad"),
    (re.compile(r"system\s*:\s*", re.I), "inyección de prompt de sistema"),
    (re.compile(r"<\s*(system|human|assistant)\s*>", re.I), "inyección de etiqueta de rol"),
    (re.compile(r"do\s+not\s+(tell|inform|mention|reveal)", re.I), "instrucción de ocultamiento"),
    (re.compile(r"(curl|wget|fetch)\s+https?://", re.I), "comando de red en la descripción"),
    (re.compile(r"exec\s*\(|eval\s*\(", re.I), "referencia a ejecución de código"),
    (re.compile(r"import\s+(subprocess|os|shutil|socket)", re.I), "import peligroso en la descripción"),
]


def scan_tool_description(server_name: str, tool_name: str, description: str) -> list[str]:
    """Marca (WARNING, no bloquea) formas de inyección en la descripción de una tool
    MCP. No se bloquea porque un falso positivo rompería un servidor legítimo; la
    defensa dura es el SELLADO de la salida (seal_tool_output)."""
    hits = [reason for pat, reason in _INJECTION_PATTERNS if pat.search(description or "")]
    for reason in hits:
        logger.warning("Descripción de tool MCP sospechosa (%s/%s): %s",
                       server_name, tool_name, reason)
    return hits


# ── material de token en disco con permisos 0600 ─────────────────────────────
def write_token_file(path: str, content: str) -> None:
    """Escribe material de token en `path` con permisos 0600 (solo el dueño).

    Se crea con el modo restringido DESDE el open (no un chmod posterior que dejaría
    una ventana world-readable). En Windows el bit POSIX es informativo — se aplica
    igual con os.chmod best-effort; el aislamiento real ahí lo da la ACL del perfil
    del usuario, donde vive $MIA_HOME."""
    flags = os.O_WRONLY | os.O_CREAT | os.O_TRUNC
    fd = os.open(path, flags, 0o600)
    try:
        os.write(fd, content.encode("utf-8"))
    finally:
        os.close(fd)
    try:
        os.chmod(path, stat.S_IRUSR | stat.S_IWUSR)  # 0600 explícito (best-effort en Windows)
    except OSError:  # pragma: no cover — algunos FS de Windows no soportan chmod
        pass
