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


def litellm_embed_model() -> str:
    """Nombre del modelo de embeddings con prefijo de proveedor para LiteLLM."""
    return EMBED_MODEL if "/" in EMBED_MODEL else f"voyage/{EMBED_MODEL}"
