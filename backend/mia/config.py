"""Mia · config — carga .env y expone la configuración del backend."""
from __future__ import annotations
import os
import sys
from pathlib import Path

from dotenv import load_dotenv

# Ancla del estado de INSTANCIA (.env, mia-data). Tres modos, en orden de precedencia:
# 1. MIA_APP_DIR (env): la cáscara de escritorio (Fase 4) le dice al motor dónde vive
#    su instancia — también útil para tests. Manda siempre que venga.
# 2. Empaquetado (PyInstaller expone sys.frozen): __file__ vive DENTRO del bundle y no
#    hay repo → el estado va a la carpeta de datos de la app del usuario.
# 3. Desarrollo (default, sin cambios): la raíz del repo (backend/mia/config.py -> mia/).
_app_dir = os.getenv("MIA_APP_DIR", "").strip()
if _app_dir:
    PROJECT_ROOT = Path(_app_dir).resolve()
    # Fallo ruidoso, no silencioso: si la cáscara pasó una ruta sin .env, el motor
    # arrancaría con TODOS los defaults (DATABASE_URL vacío, etc.) y el síntoma
    # aguas abajo ("JWT_SECRET faltante") no diría la causa real.
    if not (PROJECT_ROOT / ".env").exists():
        print(
            f"[mia.config] AVISO: MIA_APP_DIR={PROJECT_ROOT} no contiene un .env — "
            "el motor arranca con valores por defecto.",
            file=sys.stderr,
        )
elif getattr(sys, "frozen", False):
    PROJECT_ROOT = (Path(os.getenv("LOCALAPPDATA") or Path.home()) / "Mia").resolve()
else:
    PROJECT_ROOT = Path(__file__).resolve().parents[2]
load_dotenv(PROJECT_ROOT / ".env")

PG_DB = os.getenv("PG_DB", "mia")

# Entorno de despliegue (auditoría de seguridad 2026-07): "dev" (default, laptop
# del despacho / Modo B) o "production" (Modo A / servidor expuesto). En producción
# se endurecen automáticamente: docs del API apagadas, exp obligatorio en el JWT.
MIA_ENV = os.getenv("MIA_ENV", "dev").strip().lower()
IS_PRODUCTION = MIA_ENV in ("prod", "production")

# Conexión de la app: rol mia_app (RLS SÍ aplica). NUNCA el superusuario.
DATABASE_URL = os.getenv("DATABASE_URL", "")

JWT_SECRET = os.getenv("JWT_SECRET", "")
JWT_ALG = os.getenv("JWT_ALG", "HS256")
# Vigencia del token de sesión (días). 7 por defecto; bajar en producción si se
# despliega expuesto a internet (no hay revocación de tokens en v1).
JWT_TTL_DAYS = int(os.getenv("MIA_JWT_TTL_DAYS", "7"))

# Orígenes permitidos para CORS (auditoría 2026-07): coma-separados en .env.
# Default: solo el frontend local. En producción DEBE ser el dominio real del
# frontend (nunca "*": las respuestas llevan credenciales).
CORS_ORIGINS = [
    o.strip()
    for o in os.getenv(
        "MIA_CORS_ORIGINS", "http://localhost:3000,http://127.0.0.1:3000"
    ).split(",")
    if o.strip()
]

EMBED_MODEL = os.getenv("EMBED_MODEL", "voyage-law-2")
EMBED_DIM = int(os.getenv("EMBED_DIM", "1024"))
VOYAGE_API_KEY = os.getenv("VOYAGE_API_KEY", "")

# --- Gateway LLM (LiteLLM proxy, decisión #3) ---
# Todo el tráfico LLM pasa por el proxy OpenAI-compatible (Modo B: localhost:4000).
# Los nombres de modelo son los alias de litellm_config.yaml (claude-haiku, claude-sonnet).
LITELLM_BASE_URL = os.getenv("LITELLM_BASE_URL", "http://localhost:4000")
LITELLM_API_KEY = os.getenv("LITELLM_API_KEY", "sk-mia-local")
# CP-S3 · OpenRouter: acceso a decenas de modelos con UNA clave, como red de respaldo
# en la nube (política "nube"). OPCIONAL: sin clave, el proveedor no se ofrece y las
# cadenas de fallback quedan como estaban. La clave la pasa LiteLLM al upstream
# (litellm_config.yaml lee os.environ/OPENROUTER_API_KEY). Costo de pago → poner tope
# de gasto en el panel de OpenRouter al crearla (regla de operación segura).
OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY", "")
# Modelo de razonamiento principal del agente (alias del gateway). Configurable
# por despacho/entorno. compression y verification tienen su propio modelo fijo
# en agent/llm.py (decisión #7) y NO usan esta variable.
MIA_MODEL = os.getenv("MIA_MODEL", "claude-sonnet")
# Ventana de contexto del modelo principal (tokens). La usa el ContextCompressor
# (2c) para el umbral del 55%. Default 200k (claude-sonnet); configurable por entorno.
MIA_CONTEXT_WINDOW = int(os.getenv("MIA_CONTEXT_WINDOW", "200000"))
# Política de modelo POR DEFECTO (CP2 · decisión #27). Valores: "suscripcion" (CLI de
# Claude Code del abogado, sin billing por API) · "nube" (API Anthropic vía proxy) ·
# "soberano" (todo local en Ollama). El default aplica cuando el tenant no configuró
# `tenant_settings.config['model_policy']`; agent/llm.py la resuelve por request/job.
MIA_MODEL_POLICY = os.getenv("MIA_MODEL_POLICY", "suscripcion").strip().lower()
# Modelo que el CLI de la suscripción usa por defecto cuando la tarea no trae hint.
# "sonnet": calidad alta y mucho más rápido escribiendo documentos extensos que el
# modelo grande default del plan (medido 2026-07-01: el default excedió los 300s en un
# borrador legal completo; sonnet lo produce en ~1-2 min). Aliases: sonnet/opus/haiku.
MIA_CLI_MODEL = os.getenv("MIA_CLI_MODEL", "sonnet").strip().lower()

# --- Memoria del agente en ejecución (Módulo 5) ---
# $MIA_HOME: carpeta donde vive la identidad por despacho (SOUL.md por tenant) y otra
# memoria en ejecución del agente. Es estado de INSTANCIA por despacho (como las API
# keys), no se commitea: default bajo mia-data/ (gitignored). Configurable por entorno
# (.env trae MIA_HOME=.\mia-data). Una ruta RELATIVA se ancla a PROJECT_ROOT para no
# depender del directorio de trabajo (igual criterio que mia-data/traces de 2d). Se lee
# como atributo en cada uso, así los tests pueden apuntarlo a un tempdir reasignando
# config.MIA_HOME.
MIA_HOME = Path(os.getenv("MIA_HOME", "mia-data"))
if not MIA_HOME.is_absolute():
    MIA_HOME = (PROJECT_ROOT / MIA_HOME).resolve()

# --- Conectores de calendario y correo (CP-P3, Ola 2) ---
# Llaves de la APP OAuth de cada proveedor. Son de la INSTALACIÓN (una app registrada
# por despliegue de Mia en Azure AD / Google Cloud), no de un despacho: cada abogado
# CONSIENTE y obtiene su propio token (ese sí por-tenant, en tenant_oauth_tokens). Sin
# estas llaves, el conector del proveedor simplemente no se ofrece (degradación con
# gracia). El client_secret es un secreto de instalación → va en .env, nunca al git.
MS_OAUTH_CLIENT_ID = os.getenv("MS_OAUTH_CLIENT_ID", "")
MS_OAUTH_CLIENT_SECRET = os.getenv("MS_OAUTH_CLIENT_SECRET", "")
GOOGLE_OAUTH_CLIENT_ID = os.getenv("GOOGLE_OAUTH_CLIENT_ID", "")
GOOGLE_OAUTH_CLIENT_SECRET = os.getenv("GOOGLE_OAUTH_CLIENT_SECRET", "")
# URL de callback donde el proveedor devuelve el `code` de consentimiento. Debe
# coincidir EXACTA con la registrada en Azure/Google. Default: backend local (Modo B).
MAILBOX_OAUTH_REDIRECT_URI = os.getenv(
    "MAILBOX_OAUTH_REDIRECT_URI", "http://localhost:8000/api/mailbox/oauth/callback")


def mailbox_oauth_client(provider: str) -> tuple[str, str]:
    """(client_id, client_secret) de la app OAuth del proveedor, o ('','') si no hay."""
    if provider == "microsoft":
        return MS_OAUTH_CLIENT_ID, MS_OAUTH_CLIENT_SECRET
    if provider == "google":
        return GOOGLE_OAUTH_CLIENT_ID, GOOGLE_OAUTH_CLIENT_SECRET
    return "", ""


def validate_runtime_config() -> None:
    """Falla al arrancar si faltan secretos críticos (evita JWT vacío en producción)."""
    if not JWT_SECRET or len(JWT_SECRET) < 32:
        raise RuntimeError(
            "JWT_SECRET debe estar definido en .env y tener al menos 32 caracteres."
        )
    if IS_PRODUCTION and any(o == "*" for o in CORS_ORIGINS):
        raise RuntimeError(
            "MIA_CORS_ORIGINS no puede ser '*' en producción: las respuestas del "
            "API llevan credenciales. Lista los dominios exactos del frontend."
        )


def obsidian_vault_allowlist() -> list[Path]:
    """Raíces permitidas para sync de Obsidian (evita lectura arbitraria del filesystem)."""
    raw = os.getenv("OBSIDIAN_VAULT_ALLOWLIST", "") or os.getenv("OBSIDIAN_VAULT_PATH", "")
    roots = [Path(p.strip()).resolve() for p in raw.split(";") if p.strip()]
    return roots


def resolve_obsidian_vault(vault_path: str) -> Path:
    """Resuelve y valida una ruta de vault contra el allowlist."""
    vault = Path(vault_path).expanduser().resolve()
    if not vault.is_dir():
        raise ValueError(f"La ruta del vault no existe o no es un directorio: {vault}")
    allowlist = obsidian_vault_allowlist()
    if not allowlist:
        raise ValueError(
            "OBSIDIAN_VAULT_PATH u OBSIDIAN_VAULT_ALLOWLIST debe estar configurado en .env"
        )
    for root in allowlist:
        try:
            vault.relative_to(root)
            return vault
        except ValueError:
            continue
    raise ValueError("La ruta del vault no está dentro de las carpetas permitidas.")


def litellm_embed_model() -> str:
    """Nombre del modelo de embeddings con prefijo de proveedor para LiteLLM."""
    return EMBED_MODEL if "/" in EMBED_MODEL else f"voyage/{EMBED_MODEL}"
