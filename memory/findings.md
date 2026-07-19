# Mia — findings.md
# Patrones de referencia (Hermes) · restricciones técnicas
# Última actualización: 2026-06-30

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

## Patrones clave — orquestación, eficiencia y trazas
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

---

## Hermes v0.17.0 — patrones nuevos relevantes para Mia (2026-06-30)

Referencia actualizada: `hermes-ref/` es ahora un **clon git en v0.17.0** (tag CalVer
`v2026.6.19`, `NousResearch/hermes-agent`); el snapshot previo v0.15.1 quedó archivado en
`../hermes-ref-v0.15.1-snapshot.bak`. Nota de mantenimiento: el proyecto pasó de SemVer a
versionado por fecha → para actualizar usar `git -C hermes-ref fetch --tags` + checkout del tag más
nuevo (no `git pull origin main`, el clon está en detached HEAD sobre el tag). Análisis por 4
lecturas dirigidas (agent core · curator · session_search · skills). Solo ANÁLISIS — no se tocó
código de Mia.

### A · Core del agente (`agent/*` — refactor "16k→3.8k" por descomposición en módulos)
Patrones ausentes en Mia o más maduros que su `agent/core.py` (`run_turn`) + `agents/graph.py`:
1. **Context Engine plugable (Strategy/ABC)** — `agent/context_engine.py`: interfaz abstracta con
   lifecycle (`on_session_start/end`, `should_compress`, `handle_tool_call`) → la compresión es
   intercambiable por config/plugin. → Mia: extraer una `ContextEngine` ABC y que
   `ContextCompressor` la implemente, sin tocar `core.py`.
2. **Turno partido en prólogo/loop/epílogo + `TurnRetryState`** — `turn_context.py`,
   `conversation_loop.py`, `turn_finalizer.py`, `turn_retry_state.py`: ~16 flags booleanos de retry
   colapsados en un dataclass testeable. → Mia: al añadir retry/fallback multi-proveedor (LiteLLM),
   usar un `TurnState` en vez de flags sueltos en `run_turn`/grafo.
3. **Clasificador de errores de API centralizado** — `agent/error_classifier.py` (`FailoverReason`
   enum + hints `retryable`/`should_compress`/`should_rotate_credential`/`should_fallback`). Mia no
   tiene ninguno. → Mia: crear `agent/error_classifier.py` para que `call_llm()` decida reintentar /
   comprimir / fallar — crítico porque LiteLLM enruta a varios proveedores.
4. **Compresión con factibilidad + lock + anti-alucinación** — `conversation_compression.py` /
   `context_compressor.py`: valida ventana del modelo auxiliar, lock anti-concurrencia, recorte de
   imágenes base64 (recupera de 413), y un `SUMMARY_PREFIX` que impide al modelo "retomar" tareas
   del resumen. → Mia: portar el prefijo anti-resume y `check_compression_model_feasibility`
   (validar que claude-haiku tenga ventana) a `context_compressor.py`.
5. **Referencias de contexto inline `@file/@git/@url` con sandbox** — `context_references.py`
   (bloquea `.ssh`/`.aws`/`id_rsa`, raíz permitida). → Mia: permitir `@doc:` / `@expediente:` en el
   chat del abogado con sandbox POR TENANT (refuerza RLS).
6. **Presupuesto de iteraciones thread-safe** — `iteration_budget.py` (`consume/refund/remaining`).
   → Mia: acotar loops de `analysis`/`draft` en el grafo por `matter_id`.
7. **Async/sync bridging sin fugas** — `async_utils.py::safe_schedule_threadsafe` (cierra la
   corrutina si falla el scheduling). → Mia: usarlo donde `agent_hub.py`/`obsidian_sync.py` lanzan
   corrutinas desde hilos de fondo.
8. **God-file decomposition como disciplina documentada** — `agent_init.py` (constructor de 60+
   params movido a función de módulo). → Mia: mover el bootstrap pesado (SOUL/plugins/memory) a un
   `agent/agent_init.py` ANTES de que `core.py` crezca con 1c-1e; registrar en `decisions.md`.

### B · Curator autónomo (v0.12.0+, `agent/curator.py` + `curator_backup.py`)
Resuelve directamente el **Riesgo #19** de Mia (Curator consolida/poda sin HITL):
1. **Dry-run como modo HITL de primera clase** — el fork del LLM tiene PROHIBIDO mutar; produce un
   informe de "qué haría" para que un humano apruebe un run real. → Mia: `Curator.run(dry_run=True)`
   que escriba el playbook fusionado a `playbook_proposals` (status='pending_review'), sin tocar
   `playbooks.status`, hasta que el abogado apruebe.
2. **Snapshot + rollback transaccional** — `curator_backup.py`: snapshot automático antes de cada
   pasada, `rollback()` que a su vez respalda el estado actual (reversible). → Mia: `audit_log` con
   snapshot de `content`/`embedding` previos + un endpoint `rollback` (archived→active).
3. **Gate de dos niveles: poda determinista (sin LLM, siempre) vs consolidación LLM (opt-in, OFF por
   defecto)** — Mia hace lo opuesto (fusión LLM riesgosa corre siempre en el cron). → Mia: separar
   `prune` (seguro) de `consolidate` (requiere `MIA_CURATOR_CONSOLIDATE_ENABLED=true` + revisión).
4. **"Nunca borrar, solo archivar" + procedencia verificada (`absorbed_into`)** — reconcilia lo que
   el LLM declara vs. evidencia real de tool-calls (detecta alucinaciones). → Mia: verificar
   post-fusión (coseno del fusionado vs. A y B) antes de archivar; loguear la decisión.
5. **Telemetría de uso multi-señal** — poda por actividad real (use+view+patch, no solo edad) y
   avisa "use=0 = ausencia de evidencia, no falta de valor". → Mia: cruzar `usage_count`/`last_used_at`
   con la similitud >0.85 antes de fusionar; si uno tiene uso reciente alto, marcar para revisión.
6. **Reportes auditables (run.json + REPORT.md con sección Recovery)** — cada corrida es un artefacto
   revisable con el comando de rollback. → Mia: persistir cada `curator_weekly` en tabla
   `curator_runs` (before/after, reversible) visible en el dashboard.
7. **Autonomía acotada por idle + intervalo + defer del 1er run** — se dispara solo con el agente
   idle y difiere la primera corrida un intervalo completo. → Mia: no correr `consolidate` si hubo
   actividad jurídica reciente; defer por tenant nuevo (no fusionar playbooks recién creados).

### C · `session_search` (refactor ~4.500× más rápido, `tools/session_search_tool.py`)
La ganancia mayor viene de **eliminar por completo la ruta LLM** (antes resumía/rankeaba con un
modelo) y reemplazarla por SQL indexado:
1. **Índice invertido FTS5 (SQLite) con BM25, no scan sobre JSONL** — tabla `messages_fts` poblada
   por triggers `AFTER INSERT/UPDATE/DELETE`; `snippet()` genera el fragmento en la misma query.
   → Mia: los JSONL de `trace_capture.py` se re-parsean cada búsqueda; una tabla FTS5 (o el
   `content_tsv` de Postgres que ya usan en `retrieval.py`) sobre las trazas mata el rescaneo.
2. **Índice trigram paralelo para CJK** — segunda tabla FTS5 `tokenize='trigram'` sincronizada.
   → Mia: si indexan texto no-latino en trazas, evita degradar a `LIKE '%...%'` (full scan).
3. **FTS5 modo "inline" (v11) en vez de external-content** — evita el join-back a `messages` en cada
   snippet/rank (más disco, menos latencia de lectura). → Mia: denormalizar el texto dentro del
   índice si el join full-text es el cuello de botella en RRF.
4. **Índices compuestos B-tree para ventanas por sesión** — `(session_id, timestamp)` + doble query
   `id<=? LIMIT n` / `id>? LIMIT n` → ventana O(log n + window), no O(n). → Mia: si `retrieval.py`
   trae "contexto alrededor" de un chunk, un índice `(session_id, seq)` con doble LIMIT.
5. **Filtros (rol/contenido vacío) empujados a SQL, no a Python** — solo materializa las filas
   devueltas. → Mia: empujar filtros de rol/contenido al predicado SQL/Postgres.
6. **Dedupe por linaje (`parent_session_id` raíz) antes de hidratar** — limita las queries caras a
   `limit` sesiones distintas. → Mia: deduplicar trazas por "conversación raíz" antes de lookups
   RRF/embedding redundantes sobre el mismo hilo.

### D · Skills self-improving (`agent/skill_*` + `background_review.py` + `tools/skill_usage.py`)
Análogo maduro de los PLAYBOOKS de Mia; adoptar el disparador, NO la escritura directa (Mia exige HITL):
1. **Formato skill = frontmatter YAML + progressive disclosure** — `SKILL.md` con metadata tipada
   (`requires_tools`, `platforms`) + `references/templates/scripts/` cargados bajo demanda. → Mia:
   añadir a `Playbook` un `metadata.requires_tools`/`applies_when_env` tipado y mover el detalle a un
   `references/` cargado bajo demanda por `PlaybookManager.render()`.
2. **Activación por índice descriptivo (decide el LLM), no por solape léxico** — lista todas las
   skills como `name: description`; el modelo elige. Más maduro que `_select_playbook_ids` (tokens,
   tope 3). → Mia: mantener el filtro léxico como preselección barata + un paso donde el LLM
   confirme/reordene los top-N.
3. **Bucle de auto-mejora = fork en background tras cada turno** — `background_review.py`: hilo
   daemon clona el agente con solo `memory`+`skill_manage` y actualiza skills. ⚠️ En Hermes escribe
   SIN gate humano. → Mia: adoptar el DISPARADOR (revisar tras cada caso resuelto) pero el fork debe
   escribir `status="pending"`, NO aplicar — es lo que `gepa.py` debe hacer.
4. **Gating por procedencia (`write_origin` ContextVar)** — distingue escritura de `background_review`
   vs `foreground`; solo las auto-creadas quedan bajo el Curator. → Mia: tag `created_by:"gepa_auto"`
   vs `"lawyer_manual"` en `PlaybookManager`, mapeando `auto` → `status="pending"`.
5. **Ciclo de vida por telemetría de uso (mide "¿se usa?", no "¿acertó?")** — sidecar `.usage.json`,
   transición `active→stale(30d)→archived(90d)`, nunca borra, snapshot+rollback, `pin`. → Mia:
   `PlaybookCurator` que cuente activaciones y archive (con snapshot) los sin uso — pero el
   `consolidate` LLM sigue generando propuestas `pending`.
6. **Bundles = composición declarativa (YAML), no fusión por LLM** — agrupa N skills bajo un
   `/comando` auditable. → Mia: un "playbook bundle" (YAML que lista playbook_ids ya aprobados) para
   casos complejos donde el tope de 3 activaciones se queda corto — sin tocar el gate HITL.
7. **Protección estructural por capas (protected/bundled/hub)** — niveles de inmutabilidad que ni el
   agente ni el curator pueden tocar. → Mia: flag `protected=True` en playbooks "seed" regulatorios
   que ni `gepa.py` ni ningún curator futuro pueda editar/archivar (solo admin).

**Síntesis para Mia (dónde apuntan estos patrones):** (1) el clasificador de errores + retry/fallback
es la pieza más transversal y ausente, clave para el multi-proveedor de LiteLLM; (2) el Curator de
Hermes es un plano casi directo para cerrar el Riesgo #19 (dry-run→propuesta, snapshot/rollback,
prune determinista vs consolidate opt-in); (3) FTS5/`content_tsv` sobre las trazas resolvería el
rescaneo de JSONL; (4) en skills, adoptar el disparador de auto-revisión y la procedencia, pero
canalizando SIEMPRE a `status="pending"` (el HITL es la diferencia de diseño no negociable de Mia).
