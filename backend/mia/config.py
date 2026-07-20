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

# --- Lectura adaptativa del expediente (recuperación) ---------------------------
# El tamaño de lectura del expediente DEJA de ser un literal y se DERIVA en cada turno
# de tres señales: cuánto material hay indexado en el asunto, cuánto cabe en el
# presupuesto real del nodo que va a consumirlo (agents/context_recovery.budget_for
# sobre MIA_CONTEXT_WINDOW) y qué tan exigente es la pregunta. Estas constantes son los
# DIALES de esa derivación, no el tamaño en sí. Ninguna depende de país, corte, moneda
# ni idioma: son proporciones y conteos.
#
# Fracción del presupuesto del nodo que la recuperación puede llegar a ocupar. El resto
# queda para el prompt del sistema, la consulta del abogado y la respuesta. Es el margen
# que impide que "leer más" desemboque en un CONTEXT_TOO_LONG en cada turno.
#
# DECISIÓN DEL DUEÑO (2026-07-20): con 0.35 el gasto de IA por turno subía entre 11 y 20
# veces frente al literal de 8 que había antes. Se baja a 0.22 — ~7 veces más lectura que
# antes en vez de ~20, conservando la promesa que el gate `a1` de test_retrieval_adaptativa
# custodia: en un expediente grande Mia lee una FRACCIÓN REAL del material (>10%), no una
# muestra simbólica. Se probó 0.15 y rompía justo esa promesa: recorta el gasto, pero
# devuelve el producto al problema que este bloque vino a resolver.
# Se ajusta AQUÍ y no en MIA_RETRIEVAL_MAX_TOP_K a propósito: un techo bajo hace que los
# tres niveles de exigencia saturen en el mismo valor y la lectura vuelva a ser, de hecho,
# un número fijo.
# Valor PROVISIONAL: el rediseño acordado es la lectura agéntica (ver HANDOFF.md), donde el
# modelo pide más material cuando le falta y nadie tiene que fijar una proporción.
MIA_RETRIEVAL_COVERAGE_FRACTION = float(
    os.getenv("MIA_RETRIEVAL_COVERAGE_FRACTION", "0.22"))
# Tope duro de la fracción anterior una vez aplicado el multiplicador de complejidad.
# Garantía estructural: COVERAGE * complejidad nunca supera esto, así el plan de lectura
# no puede desbordar por diseño el presupuesto del nodo.
MIA_RETRIEVAL_MAX_COVERAGE_FRACTION = float(
    os.getenv("MIA_RETRIEVAL_MAX_COVERAGE_FRACTION", "0.80"))
# Piso histórico: lo que Mia leía ANTES de la lectura adaptativa. Nunca se pide menos.
MIA_RETRIEVAL_MIN_TOP_K = int(os.getenv("MIA_RETRIEVAL_MIN_TOP_K", "8"))
# Riel de seguridad (no es el límite principal: el límite principal es el presupuesto).
# Acota el coste por turno — los mismos fragmentos entran a varios nodos del grafo.
#
# DECISIÓN DEL DUEÑO (2026-07-20). Medido con los defaults reales, un techo de 160
# multiplicaba el gasto de IA por turno entre 11 y 20 veces frente al literal de 8 que
# había antes. Se le presentaron los números y respondió que la forma correcta no es
# elegir un techo, sino que el modelo PIDA más material cuando le falte —como hacen las
# herramientas agénticas de código—, porque así una pregunta trivial cuesta poco y una
# difícil lee lo que necesite, sin que nadie adivine un número. Tiene razón: ver la nota
# de "lectura agéntica" en HANDOFF.md, que es el rediseño pendiente.
# El recorte de gasto se aplicó en MIA_RETRIEVAL_COVERAGE_FRACTION, no aquí: este riel se
# deja holgado a propósito para que siga siendo lo que dice ser —una red de seguridad— y no
# el límite operativo. Un riel que muerde en todos los casos aplasta la adaptabilidad.
MIA_RETRIEVAL_MAX_TOP_K = int(os.getenv("MIA_RETRIEVAL_MAX_TOP_K", "128"))
# Se piden más filas de las que se van a entregar porque el dedup y el tope por documento
# descartan algunas: sin este colchón, "leer 100" acababa entregando 70.
MIA_RETRIEVAL_OVERFETCH = float(os.getenv("MIA_RETRIEVAL_OVERFETCH", "1.5"))
# Candidatos por lista (vector y full-text) antes de fusionar con RRF, como múltiplo de
# lo que se va a entregar. Más candidatos = mejor fusión, más trabajo en la base.
MIA_RETRIEVAL_CANDIDATE_MULTIPLIER = float(
    os.getenv("MIA_RETRIEVAL_CANDIDATE_MULTIPLIER", "3.0"))
MIA_RETRIEVAL_MIN_CANDIDATES = int(os.getenv("MIA_RETRIEVAL_MIN_CANDIDATES", "20"))
MIA_RETRIEVAL_MAX_CANDIDATES = int(os.getenv("MIA_RETRIEVAL_MAX_CANDIDATES", "600"))
# Cuánto del total entregado puede salir de UN mismo documento (0 < f <= 1). Evita que
# los N fragmentos sean todos de la misma pieza habiendo varias relevantes.
MIA_RETRIEVAL_MAX_PER_DOCUMENT_FRACTION = float(
    os.getenv("MIA_RETRIEVAL_MAX_PER_DOCUMENT_FRACTION", "0.5"))
# Solape con el que la ingesta corta los fragmentos (ingest: size=1200, overlap=150).
# El dedup lo usa para recortar la repetición literal entre fragmentos contiguos.
MIA_RETRIEVAL_OVERLAP_CHARS = int(os.getenv("MIA_RETRIEVAL_OVERLAP_CHARS", "150"))
# Similitud (Jaccard sobre n-gramas de palabras) a partir de la cual dos fragmentos se
# consideran el mismo material y solo sobrevive el mejor rankeado.
MIA_RETRIEVAL_DEDUP_SIMILARITY = float(
    os.getenv("MIA_RETRIEVAL_DEDUP_SIMILARITY", "0.85"))
# Vecinos contiguos por fragmento recuperado (ord-r .. ord+r). 0 = apagado (default):
# la función existe y está probada, pero se enciende por instalación tras medirla.
MIA_RETRIEVAL_NEIGHBOR_RADIUS = int(os.getenv("MIA_RETRIEVAL_NEIGHBOR_RADIUS", "0"))
# Notas del despacho: tope al escalado por complejidad. La sección tiene además su
# propio presupuesto DURO (KNOWLEDGE_BUDGET_FRACTION) que este número no puede violar.
MIA_KNOWLEDGE_MIN_TOP_K = int(os.getenv("MIA_KNOWLEDGE_MIN_TOP_K", "4"))
MIA_KNOWLEDGE_MAX_TOP_K = int(os.getenv("MIA_KNOWLEDGE_MAX_TOP_K", "10"))

# Política de modelo POR DEFECTO (CP2 · decisión #27). Valores: "suscripcion" (CLI de
# Claude Code del abogado, sin billing por API) · "nube" (API Anthropic vía proxy) ·
# "soberano" (todo local en Ollama) · "openrouter" (CP-OR: la propia cuenta de OpenRouter
# del abogado como motor principal, con su clave/crédito; exige OPENROUTER_API_KEY). El
# default aplica cuando el tenant no configuró `tenant_settings.config['model_policy']`;
# agent/llm.py la resuelve por request/job.
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
