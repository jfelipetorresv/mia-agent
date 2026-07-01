"""Mia · config — carga .env y expone la configuración del backend."""
from __future__ import annotations
import os
from pathlib import Path

from dotenv import load_dotenv

PROJECT_ROOT = Path(__file__).resolve().parents[2]   # backend/mia/config.py -> mia/
load_dotenv(PROJECT_ROOT / ".env")

PG_DB = os.getenv("PG_DB", "mia")

# Conexión de la app: rol mia_app (RLS SÍ aplica). NUNCA el superusuario.
DATABASE_URL = os.getenv("DATABASE_URL", "")

JWT_SECRET = os.getenv("JWT_SECRET", "")
JWT_ALG = os.getenv("JWT_ALG", "HS256")

EMBED_MODEL = os.getenv("EMBED_MODEL", "voyage-law-2")
EMBED_DIM = int(os.getenv("EMBED_DIM", "1024"))
VOYAGE_API_KEY = os.getenv("VOYAGE_API_KEY", "")

# --- Gateway LLM (LiteLLM proxy, decisión #3) ---
# Todo el tráfico LLM pasa por el proxy OpenAI-compatible (Modo B: localhost:4000).
# Los nombres de modelo son los alias de litellm_config.yaml (claude-haiku, claude-sonnet).
LITELLM_BASE_URL = os.getenv("LITELLM_BASE_URL", "http://localhost:4000")
LITELLM_API_KEY = os.getenv("LITELLM_API_KEY", "sk-mia-local")
# Modelo de razonamiento principal del agente (alias del gateway). Configurable
# por despacho/entorno. compression y verification tienen su propio modelo fijo
# en agent/llm.py (decisión #7) y NO usan esta variable.
MIA_MODEL = os.getenv("MIA_MODEL", "claude-sonnet")
# Ventana de contexto del modelo principal (tokens). La usa el ContextCompressor
# (2c) para el umbral del 55%. Default 200k (claude-sonnet); configurable por entorno.
MIA_CONTEXT_WINDOW = int(os.getenv("MIA_CONTEXT_WINDOW", "200000"))

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


def validate_runtime_config() -> None:
    """Falla al arrancar si faltan secretos críticos (evita JWT vacío en producción)."""
    if not JWT_SECRET or len(JWT_SECRET) < 32:
        raise RuntimeError(
            "JWT_SECRET debe estar definido en .env y tener al menos 32 caracteres."
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
