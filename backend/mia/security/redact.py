"""Mia · security.redact — redacción de credenciales en logs (CP-S2).

Patrón Hermes (`agent/redact.py`) adaptado: todo texto que sale por logging pasa
por `redact_text`, que enmascara credenciales conocidas por FORMA (prefijos de
proveedor, asignaciones KEY=valor, campos JSON, headers de autorización, URLs de
conexión con contraseña, JWTs, llaves privadas). El riesgo real en Mia son los
`logger.exception(...)`: los tracebacks de httpx/OpenAI arrastran URLs y headers
con tokens (el token del bot de Telegram viaja EN LA URL de cada request).

SIEMPRE ENCENDIDO — deliberadamente NO existe variable de entorno ni flag de
runtime para apagarlo (Hermes congela un flag en import; Mia va un paso más
lejos: no hay flag). Un producto legal no tiene un caso de uso legítimo para
loguear credenciales en claro.

La máscara preserva prefijo y sufijo (`sk-mia-...ocal`) para poder diagnosticar
QUÉ clave era sin exponerla; tokens cortos se ocultan por completo (`***`).
"""
from __future__ import annotations

import logging
import re

_MASK_HEAD = 6
_MASK_TAIL = 4
# Revisión capa 2 (H5): con floor 18, un secreto de 18 chars revelaba el 56%.
# Con 24, lo revelado nunca pasa de ~42% y las claves reales de proveedor
# (mucho más largas) conservan prefijo/sufijo útiles para diagnóstico.
_MASK_FLOOR = 24  # por debajo de esto, preservar head/tail revelaría demasiado


def mask_secret(value: str, head: int = _MASK_HEAD, tail: int = _MASK_TAIL,
                floor: int = _MASK_FLOOR) -> str:
    """Enmascara un secreto preservando prefijo/sufijo si es lo bastante largo."""
    s = str(value or "")
    if not s:
        return "***"
    if len(s) < floor:
        return "***"
    return f"{s[:head]}...{s[-tail:]}"


# ── Patrones ──────────────────────────────────────────────────────────────────
# 1 · Prefijos de proveedor (token completo identificable por su forma). Incluye
# los del stack de Mia (LiteLLM/OpenAI/Anthropic sk-, Voyage pa-, Pinecone pcsk_,
# Google AIza, Telegram) y el resto del catálogo de Hermes: redactar de más es
# gratis, redactar de menos es una fuga.
_PREFIX_PATTERNS = [
    r"sk-[A-Za-z0-9_-]{10,}",            # OpenAI / Anthropic / LiteLLM / OpenRouter
    r"sk_live_[A-Za-z0-9]{10,}",         # Stripe live
    r"sk_test_[A-Za-z0-9]{10,}",         # Stripe test
    r"rk_live_[A-Za-z0-9]{10,}",         # Stripe restricted
    r"sk_[A-Za-z0-9_]{10,}",             # ElevenLabs y afines (sk_ con guion bajo)
    r"pa-[A-Za-z0-9_-]{10,}",            # Voyage AI (embeddings de Mia)
    r"pcsk_[A-Za-z0-9_-]{10,}",          # Pinecone (clave por despacho)
    r"AIza[A-Za-z0-9_-]{30,}",           # Google API
    r"ghp_[A-Za-z0-9]{10,}",             # GitHub PAT
    r"github_pat_[A-Za-z0-9_]{10,}",     # GitHub PAT fine-grained
    r"gho_[A-Za-z0-9]{10,}",             # GitHub OAuth
    r"ghu_[A-Za-z0-9]{10,}",             # GitHub user-to-server
    r"ghs_[A-Za-z0-9]{10,}",             # GitHub server-to-server
    r"ghr_[A-Za-z0-9]{10,}",             # GitHub refresh
    r"xox[baprs]-[A-Za-z0-9-]{10,}",     # Slack
    r"AKIA[A-Z0-9]{16}",                 # AWS access key id
    r"SG\.[A-Za-z0-9_-]{10,}",           # SendGrid
    r"hf_[A-Za-z0-9]{10,}",              # HuggingFace
    r"r8_[A-Za-z0-9]{10,}",              # Replicate
    r"npm_[A-Za-z0-9]{10,}",             # npm
    r"pypi-[A-Za-z0-9_-]{10,}",          # PyPI
    r"dop_v1_[A-Za-z0-9]{10,}",          # DigitalOcean PAT
    r"doo_v1_[A-Za-z0-9]{10,}",          # DigitalOcean OAuth
    r"pplx-[A-Za-z0-9]{10,}",            # Perplexity
    r"tvly-[A-Za-z0-9]{10,}",            # Tavily
    r"gsk_[A-Za-z0-9]{10,}",             # Groq
    r"xai-[A-Za-z0-9]{30,}",             # xAI
    r"ntn_[A-Za-z0-9]{10,}",             # Notion
    r"fc-[A-Za-z0-9]{10,}",              # Firecrawl
    r"fal_[A-Za-z0-9_-]{10,}",           # Fal.ai
]
_PREFIX_RE = re.compile("|".join(f"(?:{p})" for p in _PREFIX_PATTERNS))

# 2 · Token de bot de Telegram: en la URL de la API (bot<id>:<token>/método) y
# suelto (<id>:<token de 35 chars>). El hallazgo mayor de CP-B2 era exactamente
# este token filtrado a logs por httpx.
_TELEGRAM_RE = re.compile(r"\bbot\d{6,12}:[A-Za-z0-9_-]{20,}|\b\d{6,12}:AA[A-Za-z0-9_-]{30,}")

# 3 · Asignaciones NOMBRE=valor cuyo nombre delata un secreto (env, .env, logs de
# arranque). Cubre PG_PASSWORD, JWT_SECRET, TELEGRAM_BOT_TOKEN, *_API_KEY, etc.
_ENV_ASSIGN_RE = re.compile(
    r"\b([A-Z][A-Z0-9_]*(?:KEY|TOKEN|SECRET|PASSWORD|PASSWD|CREDENTIAL)S?)"
    r"\s*=\s*(\"[^\"]{4,}\"|'[^']{4,}'|[^\s\"']{4,})"
)

# 4 · Campos JSON/dict sensibles: "api_key": "...", 'password': '...'.
# Revisión capa 2 (H6): sin "key" a secas — es un nombre de campo genérico de
# negocio ({"key": "artículo-90"}); las claves reales ya las atrapan api_key/
# secret/token o el patrón de prefijos de proveedor.
_JSON_KEY_NAMES = (
    "api_key", "apikey", "apiKey", "access_token", "refresh_token", "id_token",
    "token", "secret", "client_secret", "password", "passwd", "authorization",
    "private_key", "jwt",
)
_JSON_FIELD_RE = re.compile(
    r"([\"']({names})[\"']\s*:\s*)[\"']([^\"']{{4,}})[\"']".format(
        names="|".join(_JSON_KEY_NAMES)),
    re.IGNORECASE,
)

# 5 · Headers de autorización (httpx/requests los imprimen en errores y repr).
_AUTH_HEADER_RE = re.compile(
    r"\b(Authorization|Proxy-Authorization|X-Api-Key|Api-Key)"
    r"([\"']?\s*[:=]\s*[\"']?)(Bearer\s+|Basic\s+|Token\s+)?([A-Za-z0-9._~+/=-]{8,})",
    re.IGNORECASE,
)

# 6 · Cadenas de conexión con contraseña: postgres://usuario:PASSWORD@host.
_DB_CONNSTR_RE = re.compile(r"\b([a-z][a-z0-9+.-]*://[^:/\s]+):([^@/\s]{2,})@")

# 6b · Conninfo estilo libpq/psycopg: "host=db user=x password=Clave99 sslmode=…"
# (revisión capa 2, H3: el formato keyword va en minúsculas y sin '://' — los
# errores de conexión de psycopg pueden ecoar el conninfo completo).
_LIBPQ_PASSWORD_RE = re.compile(
    r"\b(password|pwd)(\s*=\s*)('[^']{2,}'|\"[^\"]{2,}\"|\S{2,})", re.IGNORECASE)

# 7 · JWT (tres bloques base64url que arrancan con eyJ = header JSON).
_JWT_RE = re.compile(r"\beyJ[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}\b")

# 8 · Bloques de llave privada PEM completos.
_PRIVATE_KEY_RE = re.compile(
    r"-----BEGIN [A-Z ]*PRIVATE KEY-----.*?-----END [A-Z ]*PRIVATE KEY-----",
    re.DOTALL,
)

# 9 · Parámetros sensibles en query strings de URLs.
_SENSITIVE_QUERY_PARAMS = (
    "access_token", "refresh_token", "id_token", "token", "api_key", "apikey",
    "client_secret", "password", "auth", "jwt", "session", "secret", "key",
    "code", "signature",
)
_URL_QUERY_RE = re.compile(
    r"([?&](?:{names})=)([^&\s\"']{{2,}})".format(names="|".join(_SENSITIVE_QUERY_PARAMS)),
    re.IGNORECASE,
)


def redact_text(text: str) -> str:
    """Redacta credenciales conocidas por forma. Idempotente y siempre activo."""
    s = str(text)
    if not s:
        return s
    # Orden: bloques grandes primero (PEM), luego formas específicas, luego
    # genéricas — así la máscara específica no le "come" el contexto a la genérica.
    if "PRIVATE KEY" in s:
        s = _PRIVATE_KEY_RE.sub("[llave privada redactada]", s)
    if "://" in s:
        s = _DB_CONNSTR_RE.sub(r"\1:***@", s)
    if "?" in s or "&" in s:  # rutas relativas también llevan query strings
        s = _URL_QUERY_RE.sub(r"\1***", s)
    s = _LIBPQ_PASSWORD_RE.sub(r"\1\2***", s)
    s = _TELEGRAM_RE.sub("bot***:***", s)
    if "eyJ" in s:
        s = _JWT_RE.sub("eyJ***.[jwt redactado]", s)
    s = _AUTH_HEADER_RE.sub(lambda m: f"{m.group(1)}{m.group(2)}{m.group(3) or ''}***", s)
    s = _JSON_FIELD_RE.sub(lambda m: f"{m.group(1)}\"{mask_secret(m.group(3))}\"", s)
    if "=" in s:
        s = _ENV_ASSIGN_RE.sub(lambda m: f"{m.group(1)}={mask_secret(m.group(2).strip(chr(34) + chr(39)))}", s)
    s = _PREFIX_RE.sub(lambda m: mask_secret(m.group()), s)
    return s


class RedactingFormatter(logging.Formatter):
    """Formatter que redacta credenciales en TODO lo formateado — mensaje,
    argumentos ya interpolados y traceback (exc_info) incluido."""

    def format(self, record: logging.LogRecord) -> str:
        # El traceback se cachea en record.exc_text la primera vez que un
        # formatter lo pinta; si otro handler SIN redacción comparte el record,
        # reusaría el texto crudo. Formatear y redactar también el caché.
        formatted = super().format(record)
        if record.exc_text:
            record.exc_text = redact_text(record.exc_text)
        return redact_text(formatted)


class _RedactingWrapper(logging.Formatter):
    """Envuelve un formatter EXISTENTE sin reemplazarlo (revisión capa 2, H1).

    Los formatters de uvicorn (DefaultFormatter/AccessFormatter) son subclases
    que inyectan campos propios (levelprefix, client_addr, request_line…) en su
    `.format()`. Reconstruirlos como Formatter plano rompía cada registro de
    uvicorn en runtime ("Formatting field not found") — y con ello APAGABA la
    redacción justo en los access logs. Este wrapper delega el formateo al
    original (conservando tipo, style y colores) y solo redacta el resultado."""

    def __init__(self, inner: logging.Formatter) -> None:
        super().__init__()  # base inerte; todo el trabajo lo hace `inner`
        self._inner = inner

    def format(self, record: logging.LogRecord) -> str:
        formatted = self._inner.format(record)
        if record.exc_text:
            record.exc_text = redact_text(record.exc_text)
        return redact_text(formatted)

    def __getattr__(self, name):
        # Solo atributos EXTRA del formatter interno (p. ej. use_colors de
        # uvicorn): los de logging.Formatter ya existen en el propio wrapper y
        # no llegan aquí. Los dunder no se delegan — copy/deepcopy los buscan
        # antes de que _inner exista y entrarían en recursión (capa 2, N1).
        if name.startswith("__") or "_inner" not in self.__dict__:
            raise AttributeError(name)
        return getattr(self._inner, name)


_DEFAULT_FMT = "%(asctime)s %(levelname)s %(name)s: %(message)s"


def install_redacting_logging(level: int = logging.INFO) -> None:
    """Instala la redacción en el logging global. Idempotente — llamable en el
    import del entrypoint Y en el startup del lifespan (uvicorn agrega sus
    handlers después del import; la segunda pasada también los cubre).

    ENVUELVE el formatter de CADA handler existente (raíz y loggers con handler
    propio, p. ej. uvicorn.*) con _RedactingWrapper — el formatter original
    sigue formateando (subclases de uvicorn incluidas); solo se redacta su
    salida. Si la raíz no tiene handlers, agrega uno estándar. Límite conocido:
    un handler agregado DESPUÉS de la última llamada queda sin envolver — por
    eso se llama dos veces (import + lifespan, ya con uvicorn configurado)."""
    root = logging.getLogger()
    if not root.handlers:
        handler = logging.StreamHandler()
        handler.setFormatter(RedactingFormatter(_DEFAULT_FMT))
        root.addHandler(handler)
        root.setLevel(level)
    all_loggers = [root] + [
        lg for lg in logging.Logger.manager.loggerDict.values()
        if isinstance(lg, logging.Logger)
    ]
    for lg in all_loggers:
        for handler in lg.handlers:
            fmt = handler.formatter
            if isinstance(fmt, (RedactingFormatter, _RedactingWrapper)):
                continue
            handler.setFormatter(_RedactingWrapper(fmt or logging.Formatter(_DEFAULT_FMT)))
