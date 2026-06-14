# Mia — findings.md
# Patrones de referencia (Hermes / OpenJarvis) · restricciones técnicas
# Última actualización: 2026-06-14

Los repos de referencia están en "D:\Codex\Mia-Super Agent\" y son SOLO
fuente de patrones, no dependencias ni base del proyecto.

---

## Patrones clave — Hermes (hermes-ref/, MIT)
- **prompt_builder de 10 capas**: las capas 1–6 forman el *cached prefix*
  (estable entre turnos → habilita prefix caching).
- **Router `call_llm(task=...)`**:
  - `compression` → claude-haiku (siempre)
  - `verification` → claude-sonnet
- **context_compressor**: `protect_first_n=5`, `protect_last_n=30`,
  `threshold=55%` (dispara compresión al superar el umbral de contexto).
- **SessionDB**: usa SQLite → **adaptar a PostgreSQL + tsvector** para
  búsqueda full-text en el store primario.
- **Plugins**: 6 hooks de extensión.
- **Curator**: tarea cron semanal (mantenimiento del knowledge store).

## Patrones clave — OpenJarvis (jarvis-ref/, Apache 2.0)
- **Orchestrator–Operative**: separación orquestador / agente operativo.
- **EfficiencyTracker**: medición de eficiencia de ejecución.
- **TraceCapture**: trazas en formato JSONL.

---

## Embeddings: librería, no proxy (Módulo 0 · 3c · decisión #17 C2)
Los embeddings van por la **librería LiteLLM directa** (`embeddings.embed_texts()` →
`litellm.embedding`, `voyage-law-2`, 1024 dims), **no** por el proxy chat. `call_llm` /
`AuxiliaryClient` son SOLO chat-completions por el proxy OpenAI-compatible; no existe el task
`"embedding"` en `_TASK_MODELS`. Cualquier indexer/ingestor (Módulo 0 ingest, Obsidian sync 3c)
embebe con `embeddings.embed_texts`. Consistente con el **Riesgo #4** (dos rutas LiteLLM:
librería para embeddings, proxy para chat).

## SOUL.md / $MIA_HOME — la TERCERA "memoria" (Módulo 5 · decisión #21)
Cuidado con el nombre "memoria": ahora hay TRES cosas distintas (amplía el Riesgo #6).
- `/memory/` raíz = memoria de CONSTRUCCIÓN (para Claude Code; este archivo).
- `backend/mia/memory/` = memoria en EJECUCIÓN 2a-2d (perfil/playbooks/trazas).
- `backend/mia/onboarding/` + `$MIA_HOME/soul_{tenant}.md` = IDENTIDAD/persona del agente (SOUL.md),
  el `$MIA_HOME/SOUL.md` que menciona CLAUDE.md §A.
`config.MIA_HOME` (default `mia-data/`, el `.env` trae `MIA_HOME=.\mia-data`) ancla rutas relativas
a `PROJECT_ROOT` y se lee como atributo en cada uso → los tests lo apuntan a un tempdir. El SOUL.md
NO va en DB (status = existencia/mtime del archivo). El `soul_snapshot` se carga en `initial_state`
(grafo) y la identidad en `MiaAgent.__post_init__` (Capa 1) con imports DIFERIDOS dentro de la
función para evitar ciclos `agents`/`agent` → `onboarding`.

## Dependencias añadidas en Fase 3 backend (Sesión 14)
Para la superficie `/api/*` se instalaron en `.venv` y se declararon en `backend/pyproject.toml`:
- **python-multipart** (`>=0.0.9`) — FastAPI lo EXIGE para `UploadFile`/form-data (sin él,
  importar el router con un endpoint de subida lanza `RuntimeError` al arrancar la app).
- **pymupdf** (`fitz`, `>=1.24`) — extracción de texto de PDF.
- **python-docx** (`>=1.1`) — extracción de texto de Word `.docx`.
Los dos últimos se importan de forma PEREZOSA en `ingest/extract.py` (solo al subir ese tipo).

## Restricciones técnicas
- ⚠️ **Ruta con espacio**: el proyecto vive en
  "D:\Codex\Mia-Super Agent\mia". **Toda ruta en scripts y comandos debe
  ir entre comillas.** Aplica a spawn de CLIs, configs de LiteLLM y
  llamadas `subprocess`. (Ver memory/bugs-and-risks.md, riesgo #1.)
- ⚠️ **Consola PowerShell = cp1252**: imprimir caracteres fuera de cp1252
  (flechas `→`, em-dash `—`, box-drawing) revienta el stdout de Python con
  `UnicodeEncodeError` y aborta el script. Los acentos (á, é, ñ) SÍ están en
  cp1252 (solo se ven como mojibake, no crashean). **Fix** en scripts que
  imprimen: `sys.stdout.reconfigure(encoding="utf-8")` al inicio (ver
  `execution/test_hitl_flow.py`) y evitar símbolos raros en los nombres de check.
  (Detectado en Módulo 1d, Sesión 5.)
