# Mia — progress.md
# DIARIO DE OBRA · qué se construyó · errores · tests · resultados
# Última actualización: 2026-07-20 (sesión 50)

---

## Sesión 0 — 2026-06-11
**Módulo:** -1 (capa cero) — **COMPLETO**

Construido:
- `CLAUDE.md` creado en la raíz del proyecto (constitución del proyecto).
- `/memory/` con archivos vivos: task_plan.md, findings.md, progress.md,
  decisions.md, bugs-and-risks.md, session-summaries.md.
- `/architecture/` con 6 SOPs vacíos: rls_isolation.md, prompt_builder.md,
  context_compressor.md, agent_hub.md, hitl_flow.md, obsidian_sync.md.
- `/execution/` y `/.tmp/` creados.
- `.gitignore` verificado: `.env`, `mia-data/`, `.tmp/` presentes.

Tests: n/a (capa cero, sin código).

**Próximo paso:** Módulo 0 — entorno nativo (Modo B) + PostgreSQL 16 +
pgvector + RLS + ingestión.

**Bloqueantes:** ninguno.

---

## Sesión 1 — 2026-06-11 — Módulo 0 EN PROGRESO (handoff a sesión admin)
**Estado:** verificaciones de entorno + setup Python hechos; DB pendiente de ADMIN.

5 verificaciones (gate del Módulo 0):
- V1 PostgreSQL: ✅ `psql 16.13` (server bin: `C:\Program Files\PostgreSQL\16\bin`).
- V2 pgvector: ⛔ PENDIENTE — server v16 corriendo, pero la auth del usuario
  `postgres` falla (la `PG_PASSWORD` del `.env` no coincide). Aún sin verificar.
- V3 Python: ✅ resuelto con venv propio. ⚠️ El `python` del PATH es el venv de
  HERMES (sin pip) — NO usar. Mia usa `mia\.venv` (CPython 3.11.15 + pip 26.1.2).
- V4 Node: ✅ `node v24.14.0`, `npm 11.9.0`.
- V5 LiteLLM: ✅ `litellm[proxy] 1.88.1` como uv tool (`~\.local\bin`), Python 3.11.

Construido esta sesión:
- `mia\.venv` (uv, 3.11.15, `--seed`). `.venv/` añadido a `.gitignore`.
- `litellm[proxy]` como uv tool (`--link-mode=copy` por `os error 1450` de hardlink).

PRÓXIMO (requiere ADMIN — el usuario reabre Claude Code como administrador; Opción 3):
1. Reset de la contraseña de `postgres` vía `pg_hba.conf` trust (plan de 11 pasos):
   backup pg_hba → líneas localhost L115 (127.0.0.1/32) y L117 (::1/128)
   `scram-sha-256`→`trust` → `Restart-Service postgresql-x64-16` →
   `ALTER USER postgres PASSWORD '<la del .env>'` → restaurar pg_hba desde backup →
   restart → verificar conexión con la pass del `.env`.
2. Añadir `C:\Program Files\PostgreSQL\16\bin` al PATH del sistema (admin).
3. Retomar V2: verificar `pgvector` en `pg_available_extensions`.
4. Solo si V2 pasa → PASOS 1–9 (carpetas, `schema.sql`+RLS, `createdb`, middleware,
   `/health`, `ingest`, `test_rls.py`, `pyproject`, scripts de arranque).
   HALT si `test_rls.py` falla.

**Bloqueante actual:** V2 (auth de `postgres`) — se resuelve en la sesión admin.

---

## Sesión 2 — 2026-06-12 — Módulo 0 COMPLETO (gate RLS verde)
**Estado:** los 9 pasos del Módulo 0 construidos y verificados. Único
pendiente verificable: correr el ingest real (bloqueado por `VOYAGE_API_KEY`
vacío — la llena el usuario).

DB (Opción 3 — script elevado que corrió el usuario):
- Reset de la contraseña de `postgres` vía `pg_hba.conf` trust → restart →
  `ALTER USER` → restaurar pg_hba → restart. SUCCESS; `pg_hba.conf` quedó
  en scram-sha-256. Auth de `postgres` verificada con la del `.env`.
- V2 pgvector: NO venía instalado. Stack Builder descartado (no trae
  pgvector para PG16 Windows). Sin compilador ni Docker. Instalado binario
  precompilado de terceros (andreiramani v0.8.2/pg16), **verificado por
  SHA256** contra el digest del asset en la API de GitHub. Load-test:
  `CREATE EXTENSION vector` + op vectorial `[1,2,3]<->[4,5,6]=5.196` OK.
  (Caveat de terceros → Riesgo #3.)

Construido (Pasos 1–9):
- `backend/` paquete `mia`: `config`, `db/{pool.py, schema.sql}`,
  `api/{main.py, middleware.py}`, `embeddings.py`, `ingest/ingest.py`.
- `execution/{init_db.py, test_rls.py}`; `scripts/{start_litellm,start_api,
  start_all}.ps1` + `litellm_config.yaml`; `backend/pyproject.toml`.
- Schema multi-tenant con RLS: GUC `app.tenant_id`, rol `mia_app`
  (NOSUPERUSER/NOBYPASSRLS), ENABLE+FORCE RLS, fail-closed. 4 tablas, 4 policies.
- Embeddings voyage-law-2 / `vector(1024)` vía LiteLLM (decisión #8).
- `.env`: +VOYAGE_API_KEY (vacío), EMBED_MODEL, EMBED_DIM, PG_DB,
  PG_APP_PASSWORD, DATABASE_URL.

Tests / verificación:
- **`test_rls.py`: 12/12 PASS** — GATE de §G superado (aislamiento por tenant,
  fail-closed, WITH CHECK contra tenant ajeno).
- E2E API (TestClient): `/health` ok (pgvector 0.8.2), `/matters` 401 sin
  token, 200 `[]` con JWT tenant-scoped.
- `init_db`: base `mia` UTF8, pgvector 0.8.2, 4 tablas, 4 policies.

Errores resueltos (lecciones):
- PS 5.1 rompe el parser con UTF-8 acentuado → todos los `.ps1` en ASCII puro
  (validados con `[Parser]::ParseFile`).
- psycopg + URL con password de caracteres especiales (`%&`) → conectar por
  **keyword params**, no por URI.
- DDL `CREATE ROLE ... PASSWORD $1` no admite parámetros → `psycopg.sql.Literal`.
- psycopg async no corre sobre ProactorEventLoop (Windows) →
  `WindowsSelectorEventLoopPolicy` en los entry points async.
- Superusuario IGNORA RLS → la app usa `mia_app` (ver
  architecture/rls_isolation.md).

**Próximo paso:** llenar `VOYAGE_API_KEY` y correr el ingest real (cierra
Paso 6). Luego Módulo 1 (core del agente, 1a–1e).

**Bloqueantes:** ninguno (ingest real gated por la API key del usuario).

---

## Sesión 3 — 2026-06-12 — Módulo 0 CERRADO + Módulo 1a COMPLETO + 1b EN PROGRESO

### Módulo 0 — Paso 6 (ingest real) CERRADO
- `VOYAGE_API_KEY` confirmada como real por el usuario.
- Creado vault de prueba `D:\Codex\Lexia-Vault-Test\nota-prueba-responsabilidad-civil.md`
  (~2.8k chars, texto jurídico ficticio en español). La carpeta del vault no existía.
- Flujo end-to-end (1 sola llamada PS para persistir UUIDs): tenant+matter creados
  como superusuario (CTE) → `python -m mia.ingest.ingest` (rol `mia_app`, RLS) →
  verificación.
- **Resultado: `chunks=3 · con_embedding=3 · dim=1024`.** Pipeline chunk → embed
  (voyage-law-2 vía LiteLLM librería) → insert bajo RLS VERIFICADO. **Módulo 0 = 100%.**

### Módulo 1a — MiaAgent núcleo — COMPLETO (gate 15/15 PASS)
Construido (`backend/mia/agent/`):
- `llm.py` — router `call_llm(task=...)` por el gateway LiteLLM. Mapa `task→alias`.
  **INVARIANTE BLOQUEADA (decisión #7):** `task="compression"` → `claude-haiku`
  SIEMPRE; un `model` explícito se IGNORA (`_LOCKED_TASKS`), no es un default.
- `core.py` — `MiaAgent` (dataclass atada a `tenant_id`): identidad + `run_turn`.
- `__init__.py` — exporta `MiaAgent`, `call_llm`, `resolve_model`.
- `config.py` — +`LITELLM_BASE_URL` (localhost:4000), `LITELLM_API_KEY`, `MIA_MODEL`
  (default `claude-sonnet`; el modelo principal es configurable por entorno).
- `pyproject.toml` — +`openai>=1.40` (se importa directo para hablar con el proxy).
- `execution/test_agent_core.py` — **15/15 PASS** (offline, `call_llm` mockeado).
- `architecture/prompt_builder.md` — doc de diseño de 1a.

Decisión de diseño clave: el `auxiliary_client.py` de Hermes (~5.800 líneas)
resuelve ~20 proveedores a mano; en Mia eso lo hace LiteLLM (decisión #3), así que
el router es delgado (solo `task→alias`, los alias viven en `litellm_config.yaml`).

### Módulo 1b — prompt_builder 10 capas + AuxiliaryClient — EN PROGRESO (sin gate aún)
Hecho:
- `agent/prompt_builder.py` — 10 capas en 3 tiers (STABLE L1-6 = prefijo cacheado /
  CONTEXT L7-8 / VOLATILE L9-10). Capas activas: L1 identidad, L2 metodología
  jurídica, L3 citación/verificación, L5 comunicación (§G), L8 instrucciones, L10
  metadata (date-only). Costuras no-op (vacías hoy): L4 tools, L6 skills, L7 matter,
  L9 memoria.
- `core.py` cableado al builder con **caché de sesión** (`_cached_system_prompt`,
  `invalidate_prompt()`) + 5 campos-costura.

PENDIENTE para cerrar 1b (gate):
- Completar AuxiliaryClient (`complete()` que devuelve texto; revisar TASK_MODELS).
- `execution/test_prompt_builder.py` + correrlo (gate): 10 capas en orden,
  compression forzado a haiku con override, L1-6 marcadas como cached.
- ⚠️ `test_agent_core.py` quedó con UNA aserción STALE: "primer mensaje es system con
  la identidad" comparaba contra `DEFAULT_IDENTITY` exacto, pero `_system_prompt()`
  ahora arma las 10 capas. Hay que actualizar esa aserción al cerrar 1b.
- Actualizar `architecture/prompt_builder.md` con el spec concreto de las 10 capas.

**Próximo paso:** cerrar el gate de 1b (test_prompt_builder) y corregir la aserción
stale de test_agent_core. Luego seguir el plan que el usuario intentó enviar (ver
abajo).

**Bloqueantes:** ninguno técnico. NOTA: el comando `/effort high` del usuario falló
al parsear (traía un plan multi-módulo 1b→1c→2a→2b→2d→PAUSA como argumento); ese
plan NO quedó registrado como instrucción. Pendiente de que el usuario lo reenvíe.

---

## Sesión 4 — 2026-06-12 — Módulo 1b CERRADO · ejecución autónoma 1b→2d

**Contexto:** el usuario reenvió el plan multi-módulo y autorizó con "procede"
(efecto: `/effort` quedó en `xhigh`; el plan en sí volvió a fallar al parsear como
argumento de `/effort`, pero el "procede" es la instrucción válida). Orden:
1b → 1c → 2a → 2b → 2d, con PAUSA obligatoria antes de 1d/1e.

### Módulo 1b — prompt_builder 10 capas + AuxiliaryClient — COMPLETO (gate 32/32)
Construido:
- `agent/prompt_builder.py` — refactor a **una tabla única `LAYERS`** (10 capas con
  index/name/tier/build). `LayerSpec.cached ⇔ tier=="stable"` (capas 1-6 = prefijo
  cacheado, `STABLE_CACHE_TTL_SECONDS = 3600`). `build_layers()` (inspección
  capa-a-capa), `build_system_prompt_parts()` y `build_system_prompt()` se derivan
  de la tabla. Costuras vacías (4 tools, 6 skills, 7 matter, 9 memory) renderizan
  "" y el `_join` las descarta.
- `agent/auxiliary_client.py` (NUEVO) — `AuxiliaryClient.complete()` devuelve TEXTO
  (string o lista de mensajes → texto). `model_for()` resuelve sin llamar al LLM.
  Hereda el bloqueo de compression por construcción (delega en `call_llm`).
- `agent/llm.py` — `_TASK_MODELS` COMPLETO: main, compression(haiku, bloqueado),
  verification(sonnet), title_generation, session_search, web_extract(haiku),
  vision(sonnet). Solo alias existentes en litellm_config.yaml (no 404 latente).
- `agent/__init__.py` — exporta `AuxiliaryClient`, `aux`.
- `execution/test_prompt_builder.py` (NUEVO) — **32/32 PASS** (offline, cliente
  OpenAI falso inyectado en `llm._client`). Verifica: 10 capas en orden, 1-6 cached,
  compression→haiku ignorando override (resolve_model + complete() punta a punta),
  TASK_MODELS completo, orden preservado en el texto ensamblado.
- `execution/test_agent_core.py` — corregida la aserción stale (system ya no es
  solo identidad; ahora `startswith(DEFAULT_IDENTITY)`). **Re-run 15/15 PASS.**
- `architecture/prompt_builder.md` — actualizado a 1b: tabla de las 10 capas,
  TASK_MODELS completo, sección AuxiliaryClient.

Nota de alcance: streaming/fallbacks en `call_llm` quedan como costura OPCIONAL
(no estaban en el gate de 1b); la firma ya es estable y se amplía sin romper.

### Módulo 1c — plugins (6 hooks) — COMPLETO (gate 16/16)
Construido:
- `agent/plugins.py` (NUEVO) — `PluginManager` (register en orden + dispatch con
  `ctx` mutable) + base `Plugin` (6 métodos no-op, herencia opcional/duck-typing).
  `HOOKS` = los 6 EXACTOS en orden de ciclo de vida: on_session_start, pre_llm_call,
  pre_tool_call, post_tool_call, post_llm_call, on_session_end. Hook desconocido →
  `ValueError` (fail-fast). Bloqueo de tool vía `ctx["blocked"]=True`.
- `agent/core.py` — `MiaAgent` cableado: campo `plugins` (manager vacío por
  defecto → no-op); `run_turn` dispara pre_llm_call/post_llm_call (con ctx de
  messages/content, un plugin puede inyectar mensaje o reescribir respuesta);
  `start_session()`/`end_session()` disparan los hooks de sesión. pre/post_tool_call
  se cablearán en el executor de tools (1d).
- `agent/__init__.py` — exporta `Plugin`, `PluginManager`, `HOOKS`.
- `execution/test_plugins.py` (NUEVO) — **16/16 PASS**: los 6 hooks (ni más ni
  menos), intercepción de cada uno, orden de registro, orden de ciclo de vida,
  intercepción real (inyectar/reescribir/bloquear), integración con run_turn y
  start/end_session.
- `architecture/prompt_builder.md` §8 — doc del sistema de plugins.
- Regresiones sin roturas: 1a 15/15, 1b 32/32.

### Módulo 2a — ProfileManager — COMPLETO (gate 19/19)
Decisión de ubicación: nuevo paquete `backend/mia/memory/` para el subsistema de
memoria EN EJECUCIÓN del agente (2a-2d). OJO: distinto del `/memory/` de la raíz
(memoria de construcción para Claude Code); el docstring del paquete lo aclara.
Construido:
- `memory/profile_manager.py` (NUEVO) — `ProfileManager` mantiene los perfiles
  VIGENTES (editables) + `start_matter(matter_id)` que devuelve un `ProfileSnapshot`
  **frozen** (dataclass inmutable). Editar un perfil tras abrir el asunto NO toca su
  snapshot; el cambio se ve en el SIGUIENTE asunto. Presupuesto: PERFIL_ABOGADO ≤600
  tok, PERFIL_DESPACHO ≤900 tok, validado al construir y al editar (ValueError si
  excede; no trunca). `estimate_tokens` = heurística offline ~4 chars/token (tiktoken
  está instalado pero requiere descargar vocab → no offline; el conteo exacto lo da
  el gateway). `ProfileSnapshot.render()` arma el bloque para la costura L9 (omite
  vacíos).
- `memory/__init__.py` (NUEVO) — paquete de memoria en ejecución (2a-2d).
- `execution/test_profile_manager.py` (NUEVO) — **19/19 PASS**: frozen al inicio
  (cambio durante asunto activo no afecta, siguiente asunto sí), presupuestos
  600/900 (límite ok + exceso rechazado, al construir y al editar), inmutabilidad,
  render.

### Módulo 2b — PlaybookManager — COMPLETO (gate 14/14)
Construido:
- `memory/tokens.py` (NUEVO) — `estimate_tokens` extraído a util compartida (2a/2b);
  `profile_manager` ahora lo importa y lo re-exporta (compat preservada, 2a 19/19).
- `memory/playbook_manager.py` (NUEVO) — `Playbook` (frozen: id/title/summary/
  applies_when/content) + `PlaybookManager`. Dos planos: `render_index()` = índice
  compacto de TODOS (SIEMPRE presente, no depende del estado activo, presupuesto
  3.000 tok validado en register); contenido completo solo ON-DEMAND vía
  `get_content(id)` (explícito) o `activate(id)` (lo marca activo para el asunto y
  devuelve cuerpo). `render_active()` = cuerpo de los activos (vacío por defecto →
  el contenido no entra al prompt). `reset()` en frontera de asunto.
- `memory/__init__.py` — exporta Playbook, PlaybookManager, PLAYBOOK_INDEX_MAX_TOKENS.
- `execution/test_playbook_manager.py` (NUEVO) — **14/14 PASS**: índice siempre
  presente e idéntico tras activar, índice NUNCA contiene el cuerpo (centinela),
  presupuesto 3000 (exceso rechazado), contenido solo on-demand, render_active
  vacío por defecto y selectivo tras activar, reset, KeyError de id desconocido.

### Módulo 2d — TraceCapture JSONL — COMPLETO (gate 20/20)
Construido:
- `memory/trace_capture.py` (NUEVO) — `Trace` (dataclass: los 8 campos requeridos
  tenant_id/matter_id/timestamp/input/output/model/tokens/latency_ms + `schema`
  versionado `mia.trace.v1`) + `TraceCapture`. `capture(...)` genera la traza,
  rellena timestamp ISO 8601 UTC si falta, y la añade (append) a JSONL. Un archivo
  por tenant (`{tenant_id}.jsonl`, nombre saneado) → aislamiento para exportar SFT
  por despacho sin mezclar (mismo principio que RLS, §G). `read()/read_jsonl()`
  releen. `Trace.to_sft_example()` → `{"messages":[user, assistant]}` (formato chat
  SFT/LoRA, compatible hermes-agent-self-evolution). Dir por defecto:
  `mia-data/traces/` (gitignored) resuelto vía `parents[3]`; crea el dir (mkdir
  parents). `tokens` admite int o dict (prompt/completion/total).
- `memory/__init__.py` — exporta TraceCapture, Trace, TRACE_SCHEMA.
- `execution/test_trace_capture.py` (NUEVO) — **20/20 PASS**: genera+escribe en
  disco (tempdir), JSONL válido (cada línea parsea), 8 campos correctos con valores,
  schema, timestamp ISO válido, mkdir parents, append (crece a 2), aislamiento por
  tenant (t-1 vs t-2), to_sft_example, dir por defecto = mia-data/traces.
- Wiring al turno (run_turn/grafo) queda para 1d; en 2d es componente + gate.

### Cierre del lote autónomo — PAUSA
Regresión completa offline VERDE (6/6 suites, 116 checks):
test_agent_core 15 · test_prompt_builder 32 · test_plugins 16 ·
test_profile_manager 19 · test_playbook_manager 14 · test_trace_capture 20.
Módulos cerrados este lote: 1b, 1c, 2a, 2b, 2d. (2c ContextCompressor se saltó por
orden del usuario.) Sigue, tras la vuelta de Pipe: 1d (LangGraph + HITL) y 1e
(Agent Hub).

**Próximo paso:** PAUSA — esperar a Pipe para 1d y 1e.
**Bloqueantes:** ninguno.

---

## Sesión 5 — 2026-06-13 — Módulo 1d (LangGraph + SSE + HITL) COMPLETO (gate 19/19)

**Contexto:** módulo más delicado. Tras la investigación previa (CLAUDE.md + memory
+ schema + deps + refs) se detuvo y se presentaron 4 decisiones; el usuario las
aprobó todas (registradas en decisions.md #9, #10, #11). Hallazgos clave: el schema
ya soportaba RRF (`content_tsv` + GIN + HNSW); `mia_app` sin CREATE; Hermes NO usa
LangGraph (no había patrón de grafo en los refs).

**Decisiones (aprobadas, decisions.md #9-#11):**
- #9 Checkpoint: tablas LangGraph creadas por `postgres` (migración) + GRANT DML a
  `mia_app`; aislamiento por thread_id={tenant}:{matter} + validación JWT; RLS de
  dominio sigue activo vía GUC. (Subclasear AsyncPostgresSaver descartado.)
- #10 interrupt() = primera línea de hitl_checkpoint_node.
- #11 POST approve/reject/edit reanuda y emite finalizing→done en la misma SSE.

**Construido:**
- Deps instaladas en .venv + pyproject: `langgraph 1.2.5`,
  `langgraph-checkpoint-postgres 3.1.0`, `sse-starlette 3.4.4`.
- `agents/state.py` — `MatterState` (TypedDict; messages reducer operator.add;
  snapshots frozen soul/profile), `thread_id_for`, `initial_state`.
- `agents/retrieval.py` — RRF híbrido (pgvector `<=>` ⊕ tsvector
  `websearch_to_tsquery('spanish')`), bajo `tenant_connection` (RLS), acotado por
  matter_id. k=60.
- `agents/graph.py` — `MatterGraphBuilder` (DI TraceCapture) + 5 nodos async
  (intake/analysis/draft/hitl_checkpoint/finalize); interrupt() primera línea del
  hitl; LLM/embeddings síncronos vía `asyncio.to_thread`. finalize escribe traza 2d.
- `agents/checkpointer.py` — `open_checkpointer()` (AsyncPostgresSaver from_conn_string,
  rol mia_app, sin setup en runtime).
- `execution/init_checkpointer.py` — migración: crea tablas de checkpoint como
  postgres + GRANT DML a mia_app (verificado: INSERT=True, RLS=False).
- `api/routes/{_common,stream,hitl}.py` — GET /matters/{id}/stream (SSE) +
  POST approve/reject/edit (SSE), con `assert_owns_matter` (cruzado→401).
  Vocabulario de eventos en español, sin jerga (§G). `api/main.py` monta los routers.
- `architecture/hitl_flow.md` — doc completo del flujo.
- `execution/test_hitl_flow.py` — **19/19 PASS** (DB real + checkpointer Postgres,
  LLM/embeddings mockeados): interrupt detiene antes de finalize, resume finaliza,
  traza JSONL al cerrar, RLS dominio (A ve / B no), checkpoint persistido en
  Postgres, cruzado→401, stream llega a awaiting_review sin jerga.

**Regresión:** 8/8 suites verdes (incluye test_rls 12/12 — §G intacto).

**Lección (cp1252):** la consola PowerShell crashea al imprimir `→` (U+2192, fuera
de cp1252). Fix en el gate: `sys.stdout.reconfigure(encoding="utf-8")` + evitar el
carácter en nombres de check. (Los acentos sí están en cp1252; solo símbolos raros
rompen.)

**Próximo paso:** PAUSA — el usuario pidió NO arrancar 1e (Agent Hub) sin él presente.
**Bloqueantes:** ninguno.

---

## Sesión 6 — 2026-06-13 — Módulo 1e (Agent Hub) COMPLETO (gate 38/38) · Módulo 1 cerrado

**Contexto:** premisa del spec corregida antes de codear — NO existe tabla
`profiles` (las tablas eran tenants/matters/documents/chunks + checkpoints;
ProfileManager 2a es in-memory). Se presentó 1 decisión (storage) + 3 defaults;
el usuario aprobó: tenant_settings nueva (decisión #12). 3/5 CLIs instalados
(hermes/claude/codex), 2 no (antigravity/openclaw) → degradación real.

**Decisión #12 (decisions.md):** `tenant_settings(tenant_id PK→tenants, config jsonb,
updated_at)` como config store por tenant (no profiles, evita colisión con 2a). RLS +
GRANT DML a mia_app, migración por postgres. config jsonb reutilizable.
**Defaults aprobados:** D2 subprocess con args-en-lista + shell=False (no comillas
manuales); D3 flags de CLI [VERIFICAR] (no se ejercitan, gate mockea); D4 delegación
OFF por defecto.

**Construido:**
- `schema.sql` — +tabla `tenant_settings` con RLS (ENABLE+FORCE, policy p_tenant_settings).
  Aplicado re-corriendo `init_db.py` (idempotente): 9 tablas, 5 policies.
- `gateway/agent_hub.py` (NUEVO) — `AgentHub` + `CONNECTORS` (5: hermes/claude_code/
  codex/antigravity/openclaw, con slug neutro + display español §G). Detección por
  env-override o PATH (which); subprocess args-en-lista shell=False timeout=120;
  graceful degradation (binario ausente / exit≠0 / timeout / excepción → string de
  error, NUNCA excepción). 5 métodos `invoke_*` + `invoke()` genérico + `list_available()`.
- `gateway/hub_config.py` (NUEVO) — get/is_enabled/set_enabled sobre tenant_settings,
  bajo tenant_connection (RLS). Default todos deshabilitados.
- `api/routes/settings.py` (NUEVO) — GET /settings/agents + POST {slug}/enable|disable;
  solo español, sin marcas; 404 desconocido / 401 sin token. Montado en main.py.
- `agents/graph.py` — seam `_maybe_delegate` en intake_node (OFF salvo señal explícita
  metadata['delegate'] + agente habilitado); `MatterGraphBuilder` recibe `agent_hub`.
- `architecture/agent_hub.md` — doc completo (5 conectores, invocación segura, config,
  endpoints, delegación, [VERIFICAR] de flags).
- `execution/test_agent_hub.py` (NUEVO) — **38/38 PASS**: detección, no-disponible→error,
  ruta con espacio intacta, fallos del runner, config por tenant + RLS, coexistencia
  jsonb, seam de delegación (off/gated/fires), endpoints HTTP (§G, 404/401).

**Regresión:** 9/9 suites verdes (test_rls 12 intacto tras el cambio de schema;
test_hitl_flow 19 intacto tras el seam de delegación no-op).

**Próximo paso:** PAUSA — **Módulo 1 completo (1a-1e)**. No arrancar otro módulo sin
el usuario. Candidatos: 2c (ContextCompressor), Fase 2 (3a-3e), Fase 3 (UX).
**Bloqueantes:** ninguno.

---

## Sesión 7 — 2026-06-14 — Módulo 2c (ContextCompressor) COMPLETO (gate 22/22) · Fase 1 cerrada

**Contexto:** módulo de alta precisión. Se leyó COMPLETO `hermes-ref/agent/
context_compressor.py` (2079 líneas). Hallazgo: los params de Hermes son
parametrizables (defaults 0.50/3/20) → NO contradicen los locked de Mia (0.55/5/30).
Se flaggearon 2 mejoras de Hermes (resumen iterativo, anti-thrashing); el usuario las
aprobó (decisión #13).

**Decisión #13:** ContextCompressor adopta (A) resumen iterativo (actualiza el resumen
previo en re-compresiones, protege contexto jurídico en matters largos) y (B)
anti-thrashing (si las últimas 2 compresiones ahorraron <10%, no recomprime). Params
locked intactos: threshold=55%, protect_first_n=5, protect_last_n=30, compression→haiku.

**Construido:**
- `agent/context_compressor.py` (NUEVO) — `ContextCompressor.compress(messages, window)`:
  cuenta tokens (estimate_tokens), no comprime bajo 55%; protege first5/last30; resume
  el medio con call_llm(task="compression")=haiku (BLOQUEO); resumen = 1 msg system con
  prefijo `[RESUMEN DE CONTEXTO]`; `[VERIFICAR]` NUNCA se comprime (se mueve al
  frozen_final verbatim); resumen estructurado en ESPAÑOL JURÍDICO con preamble
  filter-safe; (A) iterativo + (B) anti-thrashing. Stats en self.last_*.
- `memory/trace_capture.py` — +`capture_event()` + schema `mia.trace.event.v1` (evento
  `context_compressed`: tokens_antes/tokens_despues/ratio_compresion). Sin tocar lo de 2d.
- `agent/core.py` — run_turn comprime antes del turno (transparente, no SSE); +campos
  context_window/matter_id/trace_capture/compressor (+__post_init__).
- `config.py` — +`MIA_CONTEXT_WINDOW` (default 200000).
- `architecture/context_compressor.md` — algoritmo completo + simplificaciones vs Hermes.
- `execution/test_context_compressor.py` (NUEVO) — **22/22 PASS** (offline, cliente LLM
  falso → bloqueo haiku end-to-end): threshold, protect 5/30, haiku, [VERIFICAR], español,
  traza, iterativo, anti-thrashing.

**Regresión:** 10/10 suites verdes (235 checks). core.py/trace_capture.py sin romper nada.

**Próximo paso:** PAUSA — **Fase 0 + Módulo 1 + Fase 1 (Memoria) completos.** No arrancar
otro módulo sin el usuario. Candidatos: Fase 2 (3a-3e), Fase 3 (UX), Módulo 5 (SOUL.md).
**Bloqueantes:** ninguno.

---

## Sesión 8 — 2026-06-14 — Deuda del grafo: Riesgo #11 cerrado por reframe · Riesgo #12 corregido

**Contexto:** tras cerrar Fase 1, se eligió cerrar la deuda del grafo (#11/#12) antes de
arrancar Fase 2/3. Investigación previa de `agents/graph.py`, `agents/state.py`,
`agent/context_compressor.py`, `agent/core.py` y los gates 2c/1d → 2 hallazgos que
cambiaron el plan (surfaced ANTES de tocar el módulo 1d).

**Riesgo #11 — CERRADO POR REFRAME (decisión #14):** el ContextCompressor NO se cablea al
grafo. Los nodos `analysis_node`/`draft_node` arman prompts autocontenidos desde
`_last_user_message(state)` + documentos; no consumen `state["messages"]`, así que
comprimirlo sería plumbing inerte. Además `messages` es reducer `operator.add`
(append-only): reemplazarlo exige cambiar el contrato del reducer y tocaría el gate 1d. El
compresor permanece en `agent/core.py::run_turn`. Se reabre con spec propio cuando el grafo
adopte historial creciente. CERO código en 1d → gate HITL intacto.

**Riesgo #12 — CERRADO (decisión #15):** el resumen del compresor pasa de `role="system"`
a `role="user"` (prefijo `[RESUMEN DE CONTEXTO ANTERIOR]` + `SUMMARY_END_MARKER`). Razón:
Anthropic toma system como parámetro único al tope y LiteLLM hoistea los system al inicio →
un resumen system mid-array perdería su posición entre cabeza y cola (bug latente también
en `run_turn`, no solo a futuro). No se insertó ack assistant (el end-marker basta;
Anthropic fusiona roles consecutivos). Enfoque mínimo aprobado por el usuario.

**Construido (cambios quirúrgicos):**
- `agent/context_compressor.py` — `SUMMARY_PREFIX` → `[RESUMEN DE CONTEXTO ANTERIOR]`;
  `summary_msg` role `system`→`user`; docstring (d) actualizado con la razón (#12).
- `execution/test_context_compressor.py` — aserción `out[5]["role"]=="user"` + etiqueta y
  docstring del prefijo. Estructura locked intacta (len 36/37; 22 checks).
- `architecture/context_compressor.md` — paso (d) + nota de estado (#12/#15).
- `memory/decisions.md` — decisiones #14 (#11 reframe) y #15 (#12 fix).
- `memory/bugs-and-risks.md` — #11 🟢 (reframe) y #12 🟢 (cerrado).

**Regresión:** **10/10 suites verdes, 207 checks** (test_rls 12 · 1a 15 · 1b 32 · 1c 16 ·
2a 19 · 2b 14 · 2c 22 · 2d 20 · 1d 19 · 1e 38). `test_hitl_flow` 19/19 intacto.
**CORRECCIÓN DE TALLY:** el total real de las 10 suites es **207**, no 235 — el "(235
checks)" de sesiones previas (Sesión 7 / task_plan / session-summaries) era un error de
suma; los números por-suite siempre sumaron 207. Corregido en task_plan.md de aquí en
adelante.

**Próximo paso:** PAUSA. Deuda del grafo cerrada. Candidatos: Fase 2 (3a-3e Knowledge
Stores), Fase 3 (UX 4a-4e), Módulo 5 (SOUL.md).
**Bloqueantes:** ninguno.

---

## Sesión 9 — 2026-06-14 — Módulo 3a (SAT-Graph) COMPLETO (gate 21/21) · Fase 2 arranca

**Contexto:** se retomó tras un crash de la pestaña a media construcción de 3a. El
diseño y casi todo el código de 3a ya estaban escritos en la sesión interrumpida
(decisión #16, migración 003, `rag/sat_graph.py`, `rag/ingest_corpus.py`,
`init_sat_graph.py`, sección de `rls_isolation.md`); faltaba correr migración/ingest,
el gate, el SOP y el wrap. El repo no tenía commits → reconstrucción por mtimes + memoria.

**Construido / corrido esta sesión:**
- **Migración aplicada:** `init_sat_graph.py` (rol postgres) creó las 3 tablas
  (`legal_norms`, `norm_relations`, `jurisprudence`), RLS abierto USING(true), GRANT a
  mia_app. Verificado: `mia_app INSERT=True · RLS=True` en las 3.
- **Corpus semilla cargado:** se agregó un runner `__main__` a `rag/ingest_corpus.py`
  (entry point `python -m mia.rag.ingest_corpus`, con WindowsSelectorEventLoopPolicy +
  utf-8; los imports relativos exigen `-m`, no por ruta). Resultado: `{'norms': 5,
  'jurisprudence': 3, 'relations': 2}`. Idempotente (upsert).
- `execution/test_sat_graph.py` (NUEVO) — **21/21 PASS**. Gate async contra DB real
  (sin red; el SAT-Graph no llama LLM), patrón de `test_hitl_flow.py`
  (WindowsSelectorEventLoopPolicy, pool, utf-8, marcadores 'SAT_TEST' + cleanup admin).
  Checks: 3 tablas existen · mia_app SELECT en las 3 · 2 tenants distintos ven el mismo
  corpus (no por-tenant) · add_norm/add_jurisprudence/add_relation · get_norm_at_date
  antes/durante/expirada (intervalo semiabierto) · get_related_norms + filtro ·
  get_norm_chain simple A→B→C / hoja / ciclo (guardia, no loop) · upsert idempotente
  norma+juris · FTS por título y por topic · corpus semilla (5 normas + 2 relaciones) ·
  FTS español con acento ('protección').
- `architecture/sat_graph.md` (NUEVO) — SOP: qué es, esquema, corpus compartido (#16),
  get_norm_at_date, get_norm_chain (CTE + guardia), fts_vector por trigger, cómo ampliar
  el corpus ([VERIFICAR]), y Self-Annealing (qué revisar si el gate falla).

**Regresión:** **11/11 suites verdes, 228 checks** (test_rls 12 · 1a 15 · 1b 32 · 1c 16 ·
2a 19 · 2b 14 · 2c 22 · 2d 20 · 1d 19 · 1e 38 · **3a 21**). test_rls 12/12 intacto (§G).

**Hallazgos / lecciones:**
- La config FTS `spanish` SÍ está disponible (las triggers `to_tsvector('spanish',…)`
  se ejecutaron en el ingest sin error → no hizo falta el fallback a `'simple'`).
- `db.pool.connection()` (sin GUC) ya existía para el corpus compartido — confirmado que
  las tablas por-tenant siguen fail-closed sin `app.tenant_id`.

**Riesgos nuevos:** #13 (corpus compartido escribible por cualquier conexión mia_app, sin
rol curador separado — 🔐 multi-tenant) y #14 (corpus semilla con datos [VERIFICAR] sin
contrastar contra fuente primaria).

**Próximo paso:** PAUSA — no arrancar otro módulo sin el usuario. Candidato (orden del
usuario): 3c Obsidian indexer; pendientes Fase 2: 3b Curator, 3d Pinecone, 3e Feedback.
**Bloqueantes:** ninguno.

---

## Sesión 10 — 2026-06-14 — Módulo 3c (Obsidian indexer) COMPLETO (gate 22/22)

**Contexto:** investigación previa antes de codear → el spec asumía 3 premisas que NO
existen en el código real. Se presentaron y el usuario decidió (decisión #17):
- **C1** `documents` es metadata por-archivo con `matter_id NOT NULL`; el texto+embedding
  vive en `chunks`. El spec quería escribir chunks con source/source_path/chunk_index en
  `documents` → imposible. **Decisión:** tabla NUEVA `knowledge_chunks` (conocimiento del
  despacho, no de un asunto). NO se toca documents/chunks (test_rls intacto).
- **C2** `call_llm(task="embedding")` no existe (call_llm es solo chat por el proxy;
  `_TASK_MODELS` no tiene "embedding"). Los embeddings van por `embeddings.embed_texts`
  (librería LiteLLM → voyage-law-2). Consistente con Riesgo #4.
- **C3** `cron/scheduler.py` no existía (1e fue el Agent Hub). Se creó un scheduler propio.

**Construido:**
- `db/migrations/004_knowledge_stores.sql` (NUEVO) — `knowledge_chunks` (id, tenant_id,
  source default 'obsidian', source_path, chunk_index, heading_path, content,
  embedding vector(1024), content_tsv GENERATED 'spanish', metadata jsonb, created/updated;
  `UNIQUE(tenant_id,source,source_path,chunk_index)`; RLS por-tenant ENABLE+FORCE; HNSW +
  GIN) y `obsidian_file_hashes` (tenant_id, vault_path, file_hash, last_indexed;
  `UNIQUE(tenant_id,vault_path)`; RLS). GRANT DML a mia_app. NO toca el Módulo 0.
- `connectors/obsidian_sync.py` + `connectors/__init__.py` (NUEVOS) — `ObsidianSync`:
  `sync()` incremental; `_scan_vault` (rglob *.md, excluye partes que empiezan con '.' y
  archivos que empiezan con '_'); `_hash_file` (sha256); `_chunk_document` (H1/H2/H3 inician
  chunk; máx 512 tok estimado, split por párrafos, overlap 0; heading_path miga de pan);
  `_embed_chunks` (embeddings.embed_texts, batch 128); `_upsert_chunks`/`_delete_removed`/
  `_get_stored_hashes`/`_save_hashes` (todo por `tenant_connection`, RLS).
- `cron/scheduler.py` + `cron/__init__.py` (NUEVOS) — `Scheduler` en memoria
  (register_job/list_jobs/run_job/async start/stop, sin APScheduler); job
  `sync_obsidian_all_tenants` cada 6h (`build_scheduler()`), que enumera tenants con
  `tenant_settings.config->>'obsidian_vault_path'` (conexión admin — Riesgo #15) y sincroniza.
- `execution/init_knowledge_stores.py` (runner migración 004) — verificado:
  `mia_app INSERT=True · RLS=True` en las 2 tablas.
- `execution/test_obsidian_sync.py` (NUEVO) — **22/22 PASS**. Vault temporal en `.tmp/`
  (NO el real), embeddings mockeados (vector 1024 aleatorio, documentado). Checks: migración
  (2 tablas + columnas), RLS de ambas (A ve / B no), scan + exclusiones, hash determinista/
  cambia, chunk por H2, chunk >512 se divide ≤512, sync primera vez (indexed=3, 3 hashes),
  source='obsidian'+tenant ok, idempotente (skipped=3), upsert no duplica, detecta cambio
  (indexed=1/skipped=2), detecta borrado (deleted=1), aislamiento por tenant, vault vacío.
- `architecture/obsidian_sync.md` (antes vacío) — SOP completo + Self-Annealing.
- `memory/decisions.md` #17; `memory/findings.md` (nota de embeddings librería vs proxy).

**Regresión:** **12/12 suites verdes, 250 checks** (12·15·32·16·19·14·22·20·19·38·21·**22**).
test_rls 12/12 y test_sat_graph 21/21 intactos (las tablas nuevas no afectan al Módulo 0).

**Riesgos nuevos:** #15 (el cron enumera tenants con conexión admin, cross-tenant, fuera de
RLS — 🔐) y #16 (knowledge_chunks se indexa pero todavía NO se recupera: falta cablear la
recuperación de conocimiento del despacho al grafo/retriever — fuera del alcance de 3c).

**Próximo paso:** PAUSA — Módulo 3d (Pinecone connector). Pendientes Fase 2: 3b Curator,
3e Feedback. **Bloqueantes:** ninguno.

---

## Sesión 11 — 2026-06-14 — Módulo 3d (Pinecone connector) COMPLETO (gate 14/14)

**Contexto:** store vectorial EXTERNO y OPCIONAL (decisión #2: pgvector sigue primario). Módulo
CONDICIONAL — solo se activa si `PINECONE_API_KEY` está en `.env` (ya estaba, línea 7); si no,
`get_pinecone_connector()` devuelve un noop. El gate NO usa Pinecone real ni red.

**Construido:**
- `connectors/pinecone_connector.py` (NUEVO) — `PineconeConnectorBase` (ABC: upsert/query/
  delete/describe_index). `PineconeConnector`: aislamiento por **namespace**
  `{namespace_prefix}_{tenant_id}` (Pinecone no tiene RLS); batch de upsert 100; SDK `pinecone`
  v3+ con **import perezoso** en `_get_index()` (el conector se construye sin el paquete ni red;
  la conexión real es en la 1ª operación); llamadas al SDK síncrono envueltas en
  `asyncio.to_thread`; query normaliza matches a `[{id,score,metadata}]` y preserva la metadata
  intacta. `NoopPineconeConnector` (is_configured=False, no-op, nunca lanza). Factory
  `get_pinecone_connector()` lee el entorno en cada llamada (no cachea).
- `connectors/__init__.py` — exporta el conector y la factory.
- `.env` — +`PINECONE_INDEX_NAME` / `PINECONE_NAMESPACE_PREFIX` comentados (defaults mia-legal /
  tenant); no se sobreescribió nada existente.
- `execution/test_pinecone_connector.py` (NUEVO) — **14/14 PASS**. Sin red: noop + `FakeIndex`
  inyectado en `_index`. Manipula `os.environ['PINECONE_API_KEY']` (con/sin key) y lo restaura.
  Checks: factory sin key→noop, is_configured=False, noop upsert/query([])/delete sin error,
  interfaz completa (sin abstractos pendientes), namespace incluye tenant, batch 250→[100,100,50]
  + namespace por batch, factory con key→PineconeConnector (sin red), metadata intacta, top_k +
  namespace en query, normalización de matches, delete con ids+namespace.
- `architecture/pinecone_connector.md` (antes vacío) — SOP: pgvector vs Pinecone, aislamiento por
  namespace, config .env, patrón noop, cómo activar (pip install pinecone>=3, índice dim 1024),
  Self-Annealing.

**Regresión:** **13/13 suites verdes, 264 checks** (12·15·32·16·19·14·22·20·19·38·21·22·**14**).
Nada del Módulo 0/grafo se tocó; el conector es self-contained.

**Aclaración de spec (no decisión formal):** el spec pedía "filter por namespace en metadata";
se implementó con el parámetro `namespace` de Pinecone (forma idiomática de aislar), no con un
filtro de metadata, para no contaminar la metadata del usuario. `query` admite un
`metadata_filter` opcional aparte. Registrado en el SOP y en Riesgo #17.

**Riesgos nuevos:** #17 (aislamiento Pinecone por namespace, no RLS — por convención, 🔐) y #18
(SDK `pinecone` no instalado/pinned + conector aún NO cableado a ingest/retrieval).

**Próximo paso:** PAUSA — Módulo 3b (Curator cron). Pendiente Fase 2: 3e Feedback.
**Bloqueantes:** ninguno.

---

## Sesión 12 — 2026-06-14 — Módulo 3b (Curator) COMPLETO (gate 23/23) + persistencia de playbooks

**Contexto:** investigación previa (leí `playbook_manager.py`, `litellm_config.yaml`, grep db/)
→ DOS premisas del spec no existían: (1) NO hay tabla `playbooks` — el Módulo 2b se construyó
**in-memory** (dataclasses frozen); (2) `call_llm(task="curator")` no existe. Se presentó la
decisión de alcance; el usuario eligió **Opción 2** (decisión #18): crear la tabla Y cablear
PlaybookManager a DB en la misma sesión, manteniendo su interfaz pública.

**Construido:**
- `db/migrations/005_playbooks.sql` (NUEVO) — tabla `playbooks` (id, tenant_id, title, summary,
  applies_when, content, status active|archived|draft, usage_count, last_used_at,
  embedding vector(1024), metadata jsonb, created/updated; `UNIQUE(tenant_id,title)`; RLS
  ENABLE+FORCE + policy; HNSW en embedding + BTREE (tenant_id,status); GRANT DML a mia_app).
- `memory/playbook_manager.py` — cambio ADITIVO (interfaz pública intacta): `__init__` gana
  `pool=None, tenant_id=None`; con pool=None es el in-memory original (gate 2b 14/14 SIN tocar).
  +métodos async DB-backed: `register_playbook` (upsert ON CONFLICT title + embedding de
  summary+applies via embeddings.embed_texts), `get_index`, `get_playbook`, `mark_used`,
  `list_active`. Fallback in-memory si pool/tenant None.
- `memory/curator.py` (NUEVO) — `Curator`: `run` (load→find_candidates→consolidate→prune, stats
  {analyzed,consolidated,pruned,errors}); `find_candidates` por SQL con `<=>` de pgvector
  (`1-(a<=>b) > 0.85`, a.id<b.id); `consolidate` (call_llm task=curator vía to_thread, inserta
  fusionado active + archiva originales, idempotente por chequeo "ambos activos"); `prune`
  (UPDATE status='archived' WHERE last_used_at < now()-90d; NULL no se poda); `run_all_tenants`
  (enumera tenants con conexión admin — Riesgo #15 — y corre run por cada uno).
- `agent/llm.py` — `_TASK_MODELS["curator"]="claude-sonnet"` (alias → claude-sonnet-4-6; NO el id
  crudo que daría 404). `auxiliary_client.TASK_MODELS` lo hereda (mismo dict por referencia).
- `cron/scheduler.py` — +`curator_run_all_tenants` + job `curator_weekly` (168h).
- `memory/__init__.py` — exporta `Curator`.
- `execution/init_playbooks.py` (runner 005) — verificado `mia_app INSERT=True · RLS=True`.
- `execution/test_curator.py` (NUEVO) — **23/23 PASS**. LLM + embeddings mockeados; embeddings de
  candidatos CONTROLADOS con inserts directos (vec_cos para cosenos 0.9 y 0.84). Checks: task en
  _TASK_MODELS, job registrado, instancia, migración/columnas, RLS, register/upsert, get_index,
  mark_used, load (vacío/3), find_candidates (sin/con/umbral 0.84), consolidate (crea/archiva/
  contenido LLM/idempotente), prune (archiva 91d / respeta 10d), run (dict), aislamiento A≠B,
  run_all_tenants (enumeración mockeada).
- `architecture/curator.md` (antes vacío) — SOP + Self-Annealing.

**Regresión:** **14/14 suites verdes, 287 checks** (…· 2b 14 ·…· 3a 21 · 3c 22 · 3d 14 · **3b 23**).
`test_playbook_manager.py` (2b) intacto en 14/14 → el cambio aditivo no rompió el in-memory.

**Riesgos nuevos:** #19 (el Curator consolida/poda con LLM SIN revisión humana — un playbook
jurídico podría degradarse; originales quedan archived/recuperables) y #20 (la tabla `playbooks`
no tiene seeding/onboarding: nada la llena todavía; el manager in-memory sigue siendo el default).

**Próximo paso:** PAUSA — **Fase 2 COMPLETA salvo 3e**. Siguiente: Módulo 3e (Feedback processor).
**Bloqueantes:** ninguno.

---

## Sesión 13 — 2026-06-14 — Módulo 3e (Feedback processor) COMPLETO (gate 21/21) · 🎉 FASE 2 COMPLETA

**Contexto:** investigación previa (leí `memory/trace_capture.py`, `agents/graph.py`,
`agents/state.py`) → las trazas reales (`mia.trace.v1`) solo guardan input/output/model/tokens/
latency; NO la decisión HITL, ni borrador original vs final, ni documentos citados. Las 3 señales
del spec (HITL_REJECTION, HITL_EDIT, NO_RESULT) NO eran detectables. Se presentó la decisión; el
usuario eligió **Opción 1** (decisión #19): enriquecer la traza en el origen.

**Construido:**
- `memory/trace_capture.py` — Trace gana 4 campos OPCIONALES (`hitl_outcome`, `draft_original`,
  `draft_final`, `retrieved_doc_ids`); `TRACE_SCHEMA_V2='mia.trace.v2'`; `capture()` sube el
  schema a v2 solo si llega algún campo nuevo (compat: sin ellos = v1). Gates 2d/1d usan
  `issubset` + cuentan 1 traza → intactos.
- `agents/graph.py::finalize_node` — escribe los 4 campos. `hitl_outcome` mapea final_status
  (approved/rejected/editing→edited); `retrieved_doc_ids` DERIVADO de `state["documents"]` (ya
  existía, cada doc trae id) → NO se tocó MatterState ni el reducer.
- `db/migrations/006_feedback_proposals.sql` (NUEVO) — `feedback_proposals` (improve_playbook|
  new_playbook|flag_gap; target_playbook_id FK→playbooks ON DELETE SET NULL; status pending|
  approved|rejected|applied; trace_ids text[]) + `processed_traces_watermark` (PK tenant+día).
  RLS por-tenant ENABLE+FORCE en ambas; GRANT mia_app; índice (tenant,status).
- `memory/feedback_processor.py` (NUEVO) — `FeedbackProcessor(traces_dir=None)`: `load_traces`
  (lee JSONL del 2d; filtra schema v1/v2 —ignora eventos—; excluye días en watermark; ventana
  since_hours=24); `analyze` (HITL_REJECTION/HITL_EDIT[diff>20% via difflib]/NO_RESULT, devuelve
  {signal:{count,trace_ids}}); `propose` (umbral ≥2; NO_RESULT→flag_gap, rejection/edit→improve
  si hay playbooks activos / new si no; call_llm task=curator vía to_thread); `save_proposals`
  (status pending); `mark_traces_processed` (upsert watermark por día); `run`/`run_all_tenants`.
- `cron/scheduler.py` — +`feedback_run_all_tenants` + job `feedback_daily` (24h). `memory/__init__`
  exporta FeedbackProcessor.
- `execution/init_feedback.py` (runner 006) — `mia_app INSERT=True · RLS=True` en las 2 tablas.
- `execution/test_feedback_processor.py` (NUEVO) — **21/21 PASS**. Trazas sintéticas v1+v2 en
  `.tmp/`, LLM mockeado. Checks: 2 migraciones + 2 RLS, load v2/v1/eventos-ignorados, watermark
  (no recarga), analyze (rejection/edit-sig/edit-menor/no-result), umbral, propose (improve/new/
  gap), run (stats), watermark actualizado, idempotencia (2ª corrida = 0), aislamiento, compat 2d.
- `architecture/feedback_processor.md` (antes vacío) — SOP + Self-Annealing.

**Regresión:** **15/15 suites verdes, 308 checks**. CLAVE: `test_trace_capture` (2d) 20/20 y
`test_hitl_flow` (1d) 19/19 INTACTOS tras enriquecer la traza y `finalize_node` (issubset + 1
traza/turno se mantienen).

**🎉 HITO — FASE 2 (Knowledge Stores) COMPLETA · 2026-06-14:** 3a SAT-Graph · 3b Curator ·
3c Obsidian indexer · 3d Pinecone connector · 3e Feedback processor. Las 15 suites verdes.

**Riesgos nuevos:** #21 (las propuestas no se revisan ni aplican: falta Pantalla 4 + wiring
approve→PlaybookManager) y #22 (🔴 el scheduler NUNCA se arranca: los 3 jobs —obsidian/curator/
feedback— están registrados pero nada llama a `Scheduler.start()` en el lifespan de la app → en
producción NO se disparan).

**Próximo paso:** PAUSA — **Fase 3 (UX, 5 pantallas Next.js)**. Atender #22 antes/durante el
despliegue. **Bloqueantes:** ninguno.

---

## Sesión 14 — 2026-06-14 — Fase 3 ARRANCA (dividida) · superficie /api/* backend (gate 18/18)

**Contexto:** Riesgo #22 ya cerrado al inicio (scheduler en el lifespan). Investigación previa de
Fase 3 → tres premisas falsas del spec: (1) `frontend/` NO existe (Módulo 0 solo construyó
backend+DB; no hay scaffold Next.js); (2) de los 15 endpoints del gate solo ~3 existían y bajo
`/matters` (no `/api`); (3) el perfil nunca se persistió (ProfileManager 2a es in-memory). Se
presentó la decisión de alcance; el usuario eligió **dividir Fase 3 en dos** (decisión #20):
**S14 = backend** (superficie /api/* + persistencia de perfil + parser de documentos), **S15 =
frontend** (scaffold Next.js + 5 pantallas) contra endpoints ya verificados.

**Construido:**
- `db/migrations/007_profiles.sql` (NUEVO) — `firm_profiles` (perfil estructurado del despacho:
  name, lawyer_name, jurisdiction, practice_areas, voice_adjectives, banned_words, …; UNIQUE por
  tenant; RLS ENABLE+FORCE; GRANT mia_app). `execution/init_profiles.py` runner → verificado.
- `memory/profile_manager.py` — cambio ADITIVO: `__init__(*, abogado, despacho, pool=None,
  tenant_id=None)`; con pool=None es el in-memory original (gate 2a 19/19 SIN tocar). +async
  `get_firm_profile` / `upsert_firm_profile` (tabla firm_profiles, RLS). Es el perfil
  ESTRUCTURADO, distinto de los perfiles de texto de 2a (costura L9).
- `api/routes/ux.py` (NUEVO) — `APIRouter(prefix="/api")`, ~18 endpoints (ver
  `architecture/api_surface.md`): matters list/create/get, documents list/upload(PDF·Word·txt·md),
  chat (→ stream_url), stream (alias que delega en `stream_matter` de 1d), draft (lee
  `graph.aget_state` del checkpoint; 404 si no hay), draft/approve|reject (delegan en `_resume`
  de 1d; approve con edited_text = edición), profile get/put, playbooks list/create
  (PlaybookManager DB), proposals list + apply/ignore (apply cablea propuesta→playbook y marca
  applied → cierra parte del Riesgo #21), dashboard/stats. §G estricto (etiquetas amigables para
  jobs/conectores/modelos; nunca pgvector/tenant_id/embedding/hitl/langgraph/tool_call).
  Montado en `api/main.py` junto a los routers legacy (que NO se tocaron).
- `ingest/extract.py` (NUEVO) — extrae texto de PDF (PyMuPDF/fitz), Word (python-docx), txt/md;
  import perezoso de las libs pesadas.
- Deps nuevas en `pyproject.toml` + `.venv`: **python-multipart** (FastAPI lo EXIGE para
  `UploadFile` — sin él la app no arranca), **pymupdf**, **python-docx**. Documentadas en findings.md.
- `execution/test_ux.py` (NUEVO) — **18/18 PASS**. TestClient + JWT del tenant de prueba;
  LLM/embeddings mockeados; PDF (fitz) y Word (docx) sintéticos. Checks: matters list/create/get,
  documents list/upload PDF+Word, chat→stream_url, stream text/event-stream, draft 200 (tras
  turno) / 404 (sin turno), draft approve/reject 200, profile get/put, playbooks list, proposals
  list, dashboard stats (todas las claves), y §G (sin jerga técnica en respuestas).
- `architecture/api_surface.md` (NUEVO) — SOP: mapa de endpoints, relación con rutas legacy,
  §G, decisiones de diseño, Self-Annealing. `memory/decisions.md` #20.

**Regresión:** **16/16 suites verdes, 326 checks**. `test_profile_manager` (2a) 19/19 y
`test_hitl_flow` (1d) 19/19 intactos (cambio aditivo a ProfileManager + router /api adicional).

**Riesgos nuevos:** #23 (no hay login/auth de usuario — el frontend usará token de dev, deuda
S15) y #24 (matters.description no se persiste — sin columna en el esquema del Módulo 0).

**Próximo paso:** PAUSA — **Sesión 15: frontend Next.js 14 (scaffold + 5 pantallas)** contra la
API ya verificada. **Bloqueantes:** ninguno.

---

## Sesión 15 — 2026-06-14 — Frontend Next.js 14 · 5 pantallas · 🎉 FASE 3 COMPLETA (gate 25/25)

**Contexto:** segunda mitad de Fase 3 (decisión #20). Antes de scaffoldear se cerró el Riesgo #24.

**Construido:**
- **Riesgo #24 cerrado:** migración `008_matters_description.sql` (+`description text`,
  +`status varchar CHECK(active|archived|closed)` en `matters`, idempotente, aplicada como
  postgres leyendo PG_PASSWORD de .env). `api/routes/ux.py`: `create_matter` persiste
  description; `list_matters`/`get_matter` devuelven description+status. #24 🟢.
- **Scaffold `frontend/`** con `create-next-app@14 --typescript --tailwind --app --no-src-dir
  --import-alias "@/*" --eslint --use-npm` (añadí --eslint para que no prompteara; Next 14.2.35,
  React 18, 381 paquetes). `next.config.mjs`: `eslint.ignoreDuringBuilds=true` (el build valida
  TypeScript; ESLint no tumba el build). globals.css sin dark mode.
- **Token de dev (#23):** `frontend/.env.local` (gitignored por Next) con `NEXT_PUBLIC_API_URL`
  + `NEXT_PUBLIC_DEV_TOKEN` (JWT del tenant `DEV_FRONTEND`, acuñado con el mismo `jwt.encode` +
  JWT_SECRET que los gates). Documentado en `architecture/api_surface.md` §auth.
- `lib/api.ts` — `apiGet/apiSend/apiUpload` con header Bearer; `streamTurn` consume el SSE sobre
  fetch+ReadableStream (EventSource no admite Authorization). `app/_components/Sidebar.tsx`
  (nav con estado activo). `app/layout.tsx` (Inter + sidebar 220px gris #F8F8F8, sin header).
- **5 pantallas** (Tailwind puro, sin libs de UI, §G estricto, cada fetch con Bearer):
  - P1 `app/page.tsx` — lista de asuntos + modal crear (nombre/descripción) + estado vacío.
  - P2 `app/asuntos/[id]/page.tsx` — 3 columnas: documentos (subida PDF/Word) · chat con SSE
    en vivo (status "analizando/redactando", burbujas user/Mia con avatar "M", botón Revisar
    al haber borrador) · diagnóstico (placeholder, ver #25).
  - P3 `app/asuntos/[id]/revisar/page.tsx` — borrador 16px; `[VERIFICAR]` resaltado en amarillo
    con tooltip; Aprobar(verde)/Editar(azul, inline)/Rechazar(rojo); vuelve a P2 con ?confirmed.
  - P4 `app/memoria/page.tsx` — tabs: Mi despacho (perfil editable + chips) · Lo que Mia sabe
    (playbooks + modal crear) · Sugerencias (proposals con Aplicar/Ignorar).
  - P5 `app/dashboard/page.tsx` — actividad, procesos automáticos (etiquetas amigables), modelos,
    costo del mes, conectores (Base de conocimiento / Almacén externo).
- `execution/test_ux.py` — +`frontend_checks()`: 5 pantallas exportan default, layout con
  Sidebar, y **`npm run build` sin errores** (el check clave). matter_get verifica description+
  status (#24). Total **25/25**.

**Build:** `npm run build` ✓ compila (TypeScript válido), 5 rutas generadas (/, /asuntos/[id],
/asuntos/[id]/revisar, /dashboard, /memoria).
**Regresión:** **16/16 suites verdes, 333 checks** (los 15 gates Python intactos + UX 25).

**🎉 HITO — FASE 3 (UX) COMPLETA · 2026-06-14:** backend `/api/*` (S14) + 5 pantallas Next.js (S15).

**Riesgos nuevos:** #25 (la UI tiene datos incompletos por falta de endpoint: el diagnóstico de
P2 y el punto naranja de "borrador pendiente" de P1 son placeholder/inactivos; ESLint fuera del
build). Sigue abierto #23 (login real; hoy token de dev).

**Próximo paso:** PAUSA — Fase 4 (Módulo 5: SOUL.md + E2E) o endurecer UX (#23/#25). Probar el
flujo vivo (Modo B, 3 terminales) antes de producción. **Bloqueantes:** ninguno.

---

## Sesión 16 — 2026-06-14 — Módulo 5 (SOUL.md + E2E) COMPLETO · 🎉 PROYECTO COMPLETO · Mia v0 operativa

**Contexto:** el ÚLTIMO módulo. Investigación previa de premisas (CLAUDE.md + memory + Doc 4 +
api_surface + prompt_builder + state + graph + ux + gates) → **4 premisas falsas del spec**, se
presentaron como decisiones (AskUserQuestion):
- El **Doc 4 NO estaba en el repo** (busqué `triad_mode`/`doctrinal_stance`/`hard_nos` en todo el
  árbol: 0). El usuario lo entregó completo → fuente exacta de las 19 preguntas, el template y los
  datos de Lexia.
- El spec decía "18 preguntas" pero el Doc 4 trae **19** (P19 triad_mode, opcional) → se
  implementaron las 19 con conteo dinámico.
- **`$MIA_HOME` no existía** en `config.py` (el `.env` sí traía `MIA_HOME=.\mia-data`) → añadido.
- **`_TASK_MODELS` no tenía `"soul"`** → añadido (claude-sonnet).
- A4: la Capa 1 del prompt_builder NO leía el SOUL.md, y el turno REAL (grafo) nunca llenaba
  `soul_snapshot` (mismo patrón del Riesgo #11). El usuario eligió **"Grafo + prompt_builder"**
  (decisión #21): cablear AMBAS rutas, ambas None-safe.

**Construido (PARTE A — onboarding + SOUL):**
- `config.py` — +`MIA_HOME` (ancla rutas relativas a PROJECT_ROOT; lee en cada uso → tests lo
  apuntan a tempdir).
- `agent/llm.py` — +task `"soul": "claude-sonnet"` (heredado por AuxiliaryClient).
- `onboarding/soul_interview.py` + `onboarding/__init__.py` (NUEVOS) — `SoulInterview`
  (get_questions/run_interview/update_soul); `QUESTIONS` (19, id/block/field/question/example,
  Doc 4 verbatim); `SOUL_TEMPLATE`/`SOUL_SECTIONS` (9 secciones exactas); helpers PUROS de archivo
  (soul_path/load_soul_text/load_soul_snapshot/soul_status/load_responses/responses_path) que leen
  `config.MIA_HOME`; generación vía `call_llm(task="soul")` con import diferido de `llm`; conserva
  placeholders de campos sin respuesta (no inventa datos); persiste respuestas crudas en
  `…responses.json` para "Revisar mi perfil".
- `api/routes/ux.py` — 3 endpoints `/api/onboarding/{questions,complete,status}` (status con
  `responses`).
- **Wiring del SOUL (decisión #21):** `agents/state.py::initial_state` carga `soul_snapshot` desde
  `$MIA_HOME` (import diferido); `agents/graph.py` +`_render_soul`/`_system_with_soul` antepone la
  identidad en analysis/draft/edit; `agent/core.py::__post_init__` carga el SOUL.md en
  `self.identity` (Capa 1) si existe y no hay override. NO se tocó `prompt_builder.py`.

**Construido (PARTE A5 — frontend):**
- `frontend/app/onboarding/page.tsx` (NUEVO) — wizard de 19 preguntas (una a la vez, progreso
  "Pregunta X de 19" + barra, ejemplo del Doc 4, textarea/input, Anterior/Siguiente/Finalizar,
  resultado con el SOUL.md + Editar/Continuar, estado "ya configurado" con Revisar mi perfil que
  precarga respuestas).
- `frontend/app/_components/OnboardingGate.tsx` (NUEVO) — chequea `/api/onboarding/status` y
  redirige a `/onboarding` la primera vez (silencioso si el backend no responde). Montado en
  `layout.tsx`.

**Construido (PARTE B — E2E):**
- `execution/test_e2e.py` (NUEVO) — **GATE FINAL, 25/25 PASS**. Recorrido completo con TestClient
  (LLM/embeddings mockeados, `$MIA_HOME` aislado en tempdir): Paso 1 onboarding (19 preguntas, 5
  bloques, SOUL con las 9 secciones, archivo creado, `soul_snapshot` carga, status completed),
  Paso 2 crear asunto (status active), Paso 3 subir PDF 2 págs (Ley 80/1993 del corpus) →
  chunks>0, Paso 4 chat→stream_url + SSE text/event-stream sin jerga, Paso 5 HITL (draft+approve),
  Paso 6 memoria (perfil/playbooks/proposals), Paso 7 dashboard (matters≥1, documents≥1), §G.
- `architecture/e2e_runbook.md` (NUEVO) — smoke test manual en navegador (Modo B, 3 terminales).
- `architecture/soul_interview.md` (NUEVO) — SOP del módulo + Self-Annealing.

**Regresión:** **17/17 suites verdes, 358 checks** (los 16 previos intactos + test_e2e 25).
**`test_rls` 12/12 INTACTO** (regla HALT §G cumplida). Gates que el wiring tocaba: 1a 15/15,
1b 32/32, 1d 19/19, UX 25/25 (incl. `npm run build` ✓ → el frontend nuevo compila).

**Riesgos nuevos:** #26 (el SOUL.md lo genera un LLM; en vivo podría no respetar las 9 secciones —
mitigado: el abogado lo revisa/edita en la pantalla de resultado) y #27 (triad_mode se almacena en
el SOUL.md pero NO está implementado como modo de ejecución de 3 modelos en el grafo — preferencia
latente, como otras costuras).

**🎉🎉 HITO — PROYECTO COMPLETO · Mia v0 operativa · 2026-06-14:** Fase 0 + Módulo 1 + Fase 1 +
Fase 2 + Fase 3 + **Fase 4 (Módulo 5)**. Los 17 gates verdes.

**Próximo paso:** smoke test VIVO en navegador (runbook) con LLM real, y atender los riesgos
abiertos antes del PRIMER CLIENTE: #23 (login real), #25 (diagnóstico/flags UI), #19 (Curator sin
HITL ⚖️), #13 (rol curador SAT-Graph 🔐), #3 (pgvector oficial para clientes). **Bloqueantes:**
ninguno.

---

## 2026-06-14 — PAUSA post-v0 (no hay módulo en construcción)

**Estado:** proyecto en PAUSA tras cerrar Mia v0. **No hay ningún módulo en construcción** — las
4 fases están completas (17/17 suites · 358 checks · commit `64bad3f`). El terminal se trabó al
arrancar el smoke test vivo; no se construyó ni se tocó código. El proyecto queda intacto.

**Qué sigue al retomar:** decidir entre (a) smoke test VIVO en navegador con LLM real (Modo B, 3
terminales; runbook `architecture/e2e_runbook.md`) o (b) cerrar el Riesgo #23 (login real) antes
del primer cliente. Lista completa de riesgos abiertos en `memory/bugs-and-risks.md`.

**Bloqueantes:** ninguno.

---

## 2026-06-21 — Replan Ruta B + Fase 0 (cimientos multi-jurisdicción)

**Contexto:** replan a "Plataforma Legal Hispana + Asistente Conversacional" (ver `Plan/Plan.md`).
Prioridad del propietario: núcleo conversacional, memoria/contexto, mucha documentación,
plugins/Telegram/conectores, voz por dictado (Handy STT + TTS). Calculadora de plazos baja a auxiliar.

**Qué construimos (Fase 0):**
- **0.B** — Los tests son SCRIPTS (no pytest). Línea base REAL **23/25** (no "17/17"). 2 rojos
  pre-existentes: `test_curator` (claude-sonnet vs mia-local #23) y `test_onboarding_horizontal`
  (frontend hardcodeado). `test_rls` 12/12.
- **0.C Pack** — `backend/mia/jurisdiction/`. Gate `test_jurisdiction_pack.py` 19/19.
- **0.C Migración 011** — APLICADA (backup `.tmp/`, dry-run). Versionado temporal, `colombia`→`co`,
  `jurisdiction` en jurisprudence, `matters.pending_review`, tabla `audit_logs`.
- **0.C SAT-Graph** — acota por `jurisdictions` (enforced + `admin`). Gate
  `test_sat_graph_jurisdiction.py` 11/11; `test_sat_graph.py` 21/21.
- **0.C Onboarding (backend)** — `GET /api/jurisdictions` + persistencia + `resolve_jurisdictions`.
  Gate `test_onboarding_jurisdictions.py` 5/5. Decisiones #24/#25 registradas.

**Regresión:** 23/25 (cero regresiones; +3 gates nuevos verdes). `test_rls` HALT verde.

**Qué sigue:** resto Fase 0 — 0.4 política de modelo/soberanía (ContextVar en `resolve_model`),
0.5 PII en capa común de `call_llm`, 0.6 test HALT de privilegio, frontend onboarding (selector de
jurisdicción + horizontalizar P5-P18). Luego Fase 1 (núcleo conversacional). **0.A bloqueado** (créditos Claude).

---

## 2026-06-30 — Smoke test vivo COMPLETO (ruta Codex)

**Contexto:** primer smoke test estructural + VIVO end-to-end en la nueva ruta del proyecto
`D:\Codex\Mia-Super Agent\mia`. Los **3 servicios operativos**: PostgreSQL 16 + pgvector (`5432`),
Ollama (`11434`) y LiteLLM proxy (`4000`, arrancado con el patrón limpio `run_litellm_clean` —
CWD aislado + DB env scrubbed, sin tocar la BD interna de LiteLLM).

**Smoke vivo — resultados:**
- **claude-sonnet por el proxy → PASS.** `POST /v1/chat/completions` con `model: claude-sonnet`
  devolvió **HTTP 200**, modelo `claude-sonnet-4-6`, contenido `"OK"`, usage 18 tokens. **Sin
  rebote por créditos** → el alias y la `ANTHROPIC_API_KEY` están operativos; no se necesitó el
  fallback a modelo liviano local. Confirmado: **claude-sonnet es el backend de calidad para
  producción** (qwen/mia-local fabrica citas y es 6-19× más lento, decisión #26).
- **HITL → verificado en trazas reales.** Las trazas `mia.trace.v2` registran **ambos desenlaces**:
  `hitl_outcome: "approved"` y `hitl_outcome: "rejected"` (con `latency_ms` y `retrieved_doc_ids`).
  El `rejected` ya refleja el nuevo comportamiento **fail-closed** (bug #2).
- **activated_playbooks → cableado end-to-end, sin activación observada.** El campo viaja por toda
  la cadena (`Trace`/`TraceCapture.capture` → schema sube a `v2`; `graph._prepare_playbooks` +
  `_select_playbook_ids` activan por solape, `draft_node` guarda `md["activated_playbooks"]`,
  `finalize` lo emite). En las trazas existentes sale `None` porque el tenant de prueba **no tiene
  playbooks sembrados** (índice vacío → **Riesgo #20**). El wiring funciona; falta solo seeding de
  datos para observar una lista no vacía → **cierre PARCIAL del Riesgo #31**.

**3 bugs de plataforma reparados (invisibles a los gates offline — solo aparecen en vivo en Windows):**
1. **ProactorEventLoop rompía la conexión a la BD** — con `uvicorn≥0.36` en Windows, el event loop
   por defecto (Proactor) es incompatible con el pool async de psycopg. Fix en `api/run.py`:
   forzar `WindowsSelectorEventLoopPolicy`/`SelectorEventLoop` **antes** de arrancar uvicorn.
2. **HITL fail-open → fail-closed** (`graph.py::confirm_node`): una decisión ausente/inválida caía
   en `"approved"` por defecto → un borrador podía **aprobarse sin decisión válida**. Ahora cae en
   `"rejected"` (no se aprueba nada sin decisión explícita válida).
3. **Ciclo de vida de turno sin validar** (`stream.py`/`hitl.py` + `_common.prepare_new_turn` /
   `require_awaiting_review`): **409** si hay un `interrupt` pendiente (borrador sin revisar) o si
   se intenta `resume` sin borrador pendiente; el checkpoint en `END` se limpia para rearrancar
   `intake→analysis→draft`; `WikiManager` ahora **awaited** con `logger.exception` (antes era
   fire-and-forget que tragaba errores); y el SSE emite evento `error` en vez de **colgar** ante
   una excepción. La validación de ciclo de vida ocurre **antes** de abrir el SSE (409 = HTTP).

**Endurecimiento adicional en el árbol** (fuera del trío principal): `config.validate_runtime_config`
(JWT ≥32 chars), allowlist de vault Obsidian (`resolve_obsidian_vault`), `MAX_UPLOAD_BYTES` (50 MB,
anti-DoS), carga de `profile_snapshot` por turno bajo RLS.

**Riesgos:** **#32 NUEVO** (🔴) — LiteLLM comparte el `.venv` de la app; reinstalar `litellm[proxy]`
degradó `uvicorn`/`sse-starlette`/`fastapi`/`starlette`/`python-multipart` → separar LiteLLM en su
propio venv **antes de cualquier reinicio de la API en producción**. **#20** cierre parcial (wiring
de `activated_playbooks` OK; falta seeding). **#31** cierre parcial (mismo motivo).

**Qué sigue:** (1) sembrar playbooks reales para observar activación end-to-end; (2) cablear el
`prompt_builder` (10 capas) al grafo; (3) corregir la ruta del proyecto en `CLAUDE.md`
(dice `D:\Inteligencia Artificial\…`, real es `D:\Codex\…`); (4) investigar y documentar el trabajo
no registrado (`gepa.py`, `dreams.py`, `second_brain_ui`) + auth real (Riesgo #23). **Bloqueantes:**
ninguno.

---

## 2026-06-30 — Implementación patrones Hermes v0.17.0 (rama `feat/hermes-v017-impl`)

Sesión de implementación de los patrones Hermes v0.17.0 de mayor impacto (ver `findings.md`
§"Hermes v0.17.0"). Baseline: 26/26 suites, `test_rls` 12/12. Trabajo en rama de sesión
`feat/hermes-v017-impl` (para no arrastrar el WIP sin commitear de la sesión smoke). Commits atómicos
por tarea.

**H.1 — Clasificador de errores LLM centralizado ✅ (commit `37d235d`)**
- `backend/mia/agent/error_classifier.py` (NUEVO): enum `LLMErrorKind` (RATE_LIMIT, AUTH,
  MODEL_UNAVAILABLE, TIMEOUT, NETWORK, CONTEXT_TOO_LONG, UNKNOWN); `classify_llm_error(exc)` en 4
  capas (status HTTP → tipo de excepción → substrings de mensaje; importable sin openai/httpx);
  `is_retryable(kind)`; `retry_delay(kind, attempt)` backoff exponencial + jitter acotado (crece
  monótono → testeable); `LLMError(RuntimeError)` con `.kind`.
- Cableado en `agent/llm.py::call_llm`: retry de transitorios (máx 3), fail-fast AUTH/
  MODEL_UNAVAILABLE/UNKNOWN con mensaje claro en español, CONTEXT_TOO_LONG propaga original (lo
  resuelve el compresor). `call_llm` es síncrono (corre en `to_thread`) → `time.sleep` no bloquea.
- Gate `execution/test_error_classifier.py` (NUEVO, standalone sin DB): **38/38**. Verifica
  clasificación por status/tipo/mensaje, retryable/no, backoff creciente, y el cableado (retry OK,
  fail-fast AUTH 1 llamada, agota reintentos, CONTEXT_TOO_LONG propaga original).
- **Regresión: 27/27 suites PASS · `test_rls` 12/12 intacto.** Bajo riesgo de regresión: las suites
  que usan LLM mockean `call_llm`.

**H.2 — Curator dry-run → HITL ✅ (commit siguiente a `37d235d`) · CIERRA Riesgo #19**
- `db/migrations/012_curator_proposals.sql` (NUEVO) + `execution/init_curator_proposals.py`: tabla
  `curator_proposals` (RLS por-tenant, INSERT/UPDATE a mia_app), columnas proposed_merges/
  proposed_deletions (jsonb), snapshot_hash, snapshot, status (pending/approved/rejected/failed).
- `memory/curator.py`: `CuratorProposal` + `propose()` (DRY-RUN: calcula fusiones/podas SIN mutar,
  persiste `pending`), `apply_proposal()` (guarda snapshot → ejecuta merges+deletions en UNA
  transacción `tenant_connection` con **rollback automático** si algo falla → marca `failed` +
  audita; éxito → `approved` + audita), `reject_proposal()` (no muta), `propose_all_tenants()`.
  `_execute_merge`/`_execute_deletion`/`_audit` (append-only a `audit_logs` de migración 011).
- `cron/scheduler.py`: `curator_weekly` ahora llama `propose_all_tenants()` → el job autónomo
  **solo propone**, nada se muta sin aprobación humana (cierra #19 también en el cron).
- `api/routes/curator.py` (NUEVO) + registro en `main.py`: `POST /api/curator/run`,
  `GET /api/curator/proposals`, `POST /api/curator/proposals/{id}/approve|reject`. Usa
  `request.state.email` como `reviewed_by`. approve→409 si falla (revirtió), 404 si no existe.
- Gate `execution/test_curator_hitl.py` (NUEVO): **21/21** — propose no muta, persiste, RLS A↔B,
  approve ejecuta+audita+idempotente, reject no muta+audita, **rollback en fallo** (F1/F2 siguen
  activos, sin consolidado a medias, audit `curator_proposal_failed`), snapshot_hash coherente.
- **Regresión: 28/28 suites PASS · `test_rls` 12/12 · `test_curator` 23/23 (legacy) intactos.**
- Decisión de diseño: el spec pedía `dry_run=True` default en "el método de curación"; para NO
  regresar `test_curator` (que llama `run()` esperando mutación + keys exactas), el dry-run se
  implementó como método `propose()` dedicado y el CRON pasó a `propose_all_tenants()`. `run()`/
  `consolidate()`/`prune()` quedan como ejecutores internos/legacy; el camino productizado es
  propose→approve.

**H.3 — session_search FTS+BM25 sin LLM ✅**
- `db/migrations/013_traces_search.sql` (NUEVO) + `execution/init_traces_search.py`: tabla `traces`
  (RLS por-tenant, INSERT/SELECT a mia_app) con `content_tsv` mantenido por **TRIGGER**
  `BEFORE INSERT/UPDATE` (`to_tsvector('spanish', input||output||playbooks||matter)`), índice **GIN**
  + índice compuesto `(tenant_id, matter_id, trace_ts)`. Se usó trigger (no columna generada) porque
  `to_tsvector('spanish',…)` no es inmutable (cast text→regconfig STABLE) y Postgres rechaza no-inmutables
  en columnas generadas.
- `memory/trace_search.py` (NUEVO): `index_trace()` (dual-write: el JSONL sigue para SFT, esta fila es
  el índice consultable) y `search_traces()` con `websearch_to_tsquery('spanish')`, ranking
  `ts_rank_cd` (BM-like), filtros (matter/outcome/playbook/rango de fechas), todo bajo `tenant_connection`
  (RLS). **Cero LLM** en el camino caliente.
- `agents/graph.py::finalize`: dual-write best-effort `await trace_search.index_trace(...)` tras
  `capture()` (guardado con try/except → un fallo no tumba el turno). + `logger` nuevo en el módulo.
- `api/routes/traces.py` (NUEVO) + registro en `main.py`: `GET /api/traces/search?q=…&matter_id=…`.
- Gate `execution/test_trace_search.py` (NUEVO): **15/15** — keyword, filtro por asunto, ranking
  (más relevante primero), filtro por outcome/playbook, query vacío→[], **RLS A↔B**, **cero llamadas LLM**
  (tripwire sobre `llm.call_llm`).
- **Regresión: 29/29 suites PASS · `test_rls` 12/12 · `test_hitl_flow` 19/19 · `test_e2e` 25/25 intactos.**
- Desviación documentada: el spec asumía "la tabla de trazas existente", pero las trazas viven en
  JSONL (`mia-data/traces/`). Se creó la tabla `traces` en Postgres con dual-write (la búsqueda con
  RLS A↔B obliga a Postgres; el JSONL no tiene RLS). El hook dual-write en `graph.py` quedó SIN
  commitear en el commit de H.3 (graph.py entrelazado con trabajo smoke sin commitear).

**H.4 — Skills self-improving con HITL pending ✅ (commit `d5d5c1f`)**
- `memory/skill_improver.py` (NUEVO): `extract_skill_candidate(trace)` exige los 3 requisitos
  (`hitl_outcome=approved` + `activated_playbooks` no vacío + usado>1 vía `usage_count`; la señal
  `memory_relevance` no existe → se usa `usage_count` del playbook). `propose_improvement()` persiste
  en **`feedback_proposals` (status='pending')** — sin tabla nueva, mismo flujo HITL: `improve_playbook`
  con DIFF (`difflib`) + target, o `new_playbook`; guarda procedencia (`trace_ids`).
  `process_trace()` end-to-end; `process_trace_safe()` fire-and-forget que **nunca propaga** (loguea,
  no traga en silencio — lección smoke). Sin LLM (determinista).
- `agents/graph.py::finalize`: fire-and-forget `asyncio.create_task(SkillImprover().process_trace_safe(...))`
  retenido en `_BG_TASKS` (evita GC; lección smoke: no `create_task` suelto). SIN commitear (graph.py
  entrelazado).
- Gate `execution/test_skill_improver.py` (NUEVO): **13/13** — los 3 requisitos, propuesta **pending
  no auto-aprobada**, procedencia, process_trace (usa>1 propone / usa=1 no), **fire-and-forget seguro**,
  RLS A↔B.
- **Regresión: 30/30 suites PASS · `test_rls` 12/12 · `test_hitl_flow` 19/19 · `test_e2e` 25/25 intactos.**

**Cierre de sesión Hermes v0.17.0 (rama `feat/hermes-v017-impl`):**
- Commits atómicos: H.1 `37d235d` · H.2 (curator) · H.3 (traces) · H.4 `d5d5c1f`.
- Regresión final: **30/30 suites verdes** (26 base + H.1/H.2/H.3/H.4 = 4 gates nuevos: 38+21+15+13).
  `test_rls` 12/12 (gate HALT) intacto en todo momento. **No existe `test_privilege_isolation.py`**
  (la regla del usuario lo menciona pero era trabajo futuro 0.6; se usó `test_rls` como gate HALT).
- **PENDIENTE de commit (working tree):** `agents/graph.py` acumula 3 bloques SIN commitear —
  (a) trabajo de la sesión smoke (activated_playbooks + 3 bugs HITL), (b) dual-write H.3
  (`index_trace`), (c) fire-and-forget H.4 (`SkillImprover`). Recomendación: commitear los 3 juntos
  como el commit de la sesión smoke (todo verde). También sigue sin commitear el resto del WIP smoke
  (hitl.py, stream.py, _common.py, config.py, run.py, trace_capture.py, frontend, etc.) + los docs de
  memoria de esta sesión.
- Riesgo cerrado: **#19** (Curator sin HITL) por H.2 (dry-run→propuesta→aprobación + cron solo-propone).

---

## 2026-06-30 — Correcciones Cursor C.5-C.6 + Hermes v0.17.0 H.5-H.6 (rama `feat/hermes-v017-impl`)

**C.5 — Curator `run()` legacy bloqueado (commit `73acee4`)**
- `memory/curator.py`: `run()`→`_run_legacy()`, `run_all_tenants()`→`_run_all_tenants_legacy()`.
  Guard al inicio de `_run_legacy`: si `os.getenv("MIA_ALLOW_CURATOR_LEGACY_RUN") != "1"` → `RuntimeError`
  (muta sin HITL; en producción se usa `propose()` + `apply_proposal()`). El ciclo mutante solo corre
  en tests con el env var.
- `execution/test_curator.py`: los 3 calls legacy envueltos en `MIA_ALLOW_CURATOR_LEGACY_RUN=1` (set
  antes / `pop` después) + nuevo check fail-closed (sin el env var → `RuntimeError`).
- `architecture/curator.md`: reescrito al flujo `propose→approve→apply`; `Curator().run()` reemplazado
  por `propose()` + aprobación por API; nota del guard legacy.

**C.6 — `traces/search` con `matter_id` obligatorio (commit `73acee4`)**
- `api/routes/traces.py`: `matter_id: str = Query(...)` (obligatorio, sin default) + `assert_owns_matter(tid,
  matter_id)` antes de buscar (401 si el asunto no es del tenant; 422 si falta el param).
- `execution/test_trace_search.py`: check 422 vía `TestClient` (la validación de query ocurre antes del
  body → no toca DB). Gate **21/21**.

**H.5 — TurnRetryState + cadena de fallback de proveedor (commit `514ee68`)**
- `agent/llm.py`: `_TASK_MODELS` (task→alias único) → `_TASK_FALLBACK_CHAINS` (task→[alias,…]).
  `main`/`curator`: `["claude-sonnet","mia-local"]`; `compression` (bloqueada) y auxiliares: un alias.
  `resolve_fallback_chain(task,model)` (dedupe/sin vacíos) + `resolve_model()`=chain[0] (compat).
  `call_llm`: loop de dos niveles — reintento con backoff DENTRO del alias; al agotarse con error
  saltable pasa al siguiente. `CONTEXT_TOO_LONG` propaga original (no avanza la cadena); `AUTH/UNKNOWN`
  fail-fast; cadena agotada → `LLMError('ALL_PROVIDERS_EXHAUSTED')`. `_call_with_retries` extraído; log
  estructurado por salto.
- `agent/error_classifier.py`: `should_fallback(kind)` — `MODEL_UNAVAILABLE/RATE_LIMIT/TIMEOUT/NETWORK/
  SERVER_ERROR`→True; `AUTH/CONTEXT_TOO_LONG/UNKNOWN`→False (`_FALLBACKABLE`).
- `agent/turn_llm_state.py` (NUEVO): `TurnLLMState` (aliases intentados, `compression_attempted`,
  `fallback_exhausted`, `last_error_kind`) + (de)serialización JSON-safe para viajar por `metadata`.
- `agents/graph.py`: `_llm` ya NO fija `model=MIA_MODEL` (usa la cadena); ante `CONTEXT_TOO_LONG`
  comprime UNA vez por turno (`ContextCompressor`) y reintenta desde chain[0]. Estado creado en
  `intake_node` y propagado por `metadata['llm_turn']`.
- `agent/auxiliary_client.py`: `TASK_MODELS` deriva del 1er eslabón de cada cadena.
- Gate `execution/test_llm_fallback.py` (NUEVO): **25/25** — salto MODEL_UNAVAILABLE, CONTEXT_TOO_LONG
  no avanza, AUTH fail-fast, RATE_LIMIT agota→salta, ALL_PROVIDERS_EXHAUSTED, `should_fallback` por kind,
  `resolve_fallback_chain` (dedupe/locked/override). Tests alineados: `test_agent_core` 18/18,
  `test_error_classifier` 50/50 (6c→task de cadena única), `test_prompt_builder` 32/32 (`450ef6d`).
- ⚠️ Nota dev: con la cuenta Anthropic sin créditos, `main` intenta `claude-sonnet` primero; AUTH **no**
  salta (por diseño) → si se quiere forzar local, usar `model="mia-local"` o ajustar la cadena.

**H.6 — Playbooks `protected` (semilla/core) (commit `ce1587b`)**
- Migración `014_playbooks_protected.sql` (NUEVA, idempotente): `protected boolean NOT NULL DEFAULT
  false` + índice parcial `WHERE protected`. Runner `execution/init_playbooks_protected.py` (NUEVO).
- `memory/playbook_manager.py`: `register_playbook(protected=False, force=False)` — INSERT incluye la
  columna; ON CONFLICT NO pisa content/summary/applies_when/embedding de un protegido salvo `force=True`;
  el flag sí se actualiza. `get_playbook` devuelve `protected`.
- `memory/curator.py`: `find_candidates` y `_prune_candidates` excluyen protegidos; `prune` legacy
  `AND NOT protected`; `_execute_merge` → 0 + warn si algún origen protegido; `_execute_deletion`
  `AND NOT protected`. `propose()` los omite (usa esos métodos).
- `memory/skill_improver.py`: `process_trace` sobre protegido → `None`; `_lookup_playbook` trae `protected`.
- `memory/gepa.py`: `prune_unused_skills` `AND NOT protected`.
- `api/routes/ux.py`: `apply_proposal` con target protegido → **409** (+ UPDATE `AND NOT protected`).
- Gate `execution/test_playbooks_protected.py` (NUEVO): **19/19** — register/get, upsert-no-pisa/force,
  find_candidates/prune_candidates excluyen, merge/deletion respetan, skill_improver None, GEPA no poda,
  ux 409, RLS A↔B.

**Regresión final (toda la suite, 32 gates):** TODO VERDE. Gates nuevos: `test_llm_fallback` 25/25,
`test_playbooks_protected` 19/19. `test_rls` **12/12** (gate HALT) intacto. Sin fallos.

**Cierre de sesión (2026-06-30):** rama `feat/hermes-v017-impl` **mergeada a `main`**. `.gitignore`
ahora ignora `*.egg-info/`. Riesgo #19 (Curator sin HITL) **cerrado** (H.2/H.5/C.5). Nuevo
**Riesgo #33** registrado: la recuperación ante `CONTEXT_TOO_LONG` en `graph._llm` es un no-op sobre
prompts monolíticos de 2 mensajes (analysis/draft) → falta truncado por nodo (trabajo próxima sesión).
Árbol de trabajo limpio.

---

## 2026-07-01 — Entradas retroactivas (módulos de sesión 20 sin documentar)

**⚠️ DOCUMENTACIÓN RETROACTIVA escrita el 2026-07-01.** El smoke vivo del 2026-06-30 detectó 3
módulos con código y gates verdes pero SIN entrada en este diario: `gepa.py`, `dreams.py` y
`second_brain_ui`. Se construyeron alrededor del **2026-06-20 (Sesión 20, Fase 5 "Autoaprendizaje
horizontal + second brain", Goal Codex autoaprendizaje)** — figuran completos en `task_plan.md`
§Fase 5 pero nunca se escribió su entrada de diario. Esta entrada reconstruye qué son a partir de
lectura del código el 2026-07-01 y re-ejecución de sus gates (los 3 verdes hoy). El razonamiento
de diseño original de la sesión 20 no quedó registrado; lo que sigue son las decisiones VISIBLES
en el código.

**Módulo 1 — GEPA Loop (`backend/mia/memory/gepa.py`) · gate `test_gepa.py` 16/16 PASS (re-corrido 2026-07-01)**
Aprendizaje procedural por tenant a partir de las trazas HITL (`TraceCapture` JSONL): Mia aprende
los procedimientos del despacho observando qué borradores se aprueban, editan o rechazan.
- `detect_new_skill` — agrupa trazas `approved` SIN playbook asignado por primeras 10 palabras
  normalizadas del input; con ≥2 señales similares pide al LLM (`task="curator"`, temp 0.1) un
  draft de procedimiento (JSON title/applies_when/content) y lo inserta en `playbooks` con
  `status='draft'` (upsert por `(tenant_id,title)`) + propuesta `new_playbook` en `feedback_proposals`.
- `evolve_skill` — mide approval/edit rate de un playbook desde sus trazas (30 días); si
  approval<60% o edits>30% pide al LLM una versión mejorada y la deja como propuesta
  `improve_playbook`. **NO aplica el cambio** (el playbook sigue `active`).
- `grade_all_skills` — ranking de playbooks activos por approval_rate/edit_rate/activaciones.
- `prune_unused_skills` — archiva playbooks sin uso >60 días, `AND NOT protected` (guard H.6,
  añadido 2026-06-30: las semillas/core no se podan).
- `run_evolution_cycle` / `run_all_tenants` — ciclo completo (detect → grade → evolve los <60% →
  prune → top 5) por tenant.
Decisiones de diseño visibles: (1) **todo pasa por HITL** — GEPA solo produce drafts y propuestas
`pending`, nunca muta un playbook activo (coherente con el cierre del Riesgo #19); (2) **horizontal**
— los prompts instruyen "No asumas jurisdicción, área, norma, corte, idioma ni tipo de proceso" y el
gate verifica por lectura del fuente que no haya países/áreas hardcodeados; (3) **fallback
determinista** — si el LLM falla o devuelve JSON inválido, el draft se arma con la evidencia cruda
(no se pierde la señal); (4) señal mínima de 2 aprobaciones similares antes de proponer.

**Módulo 2 — Dreams (`backend/mia/memory/dreams.py`) · gate `test_dreams.py` 16/16 PASS (re-corrido 2026-07-01)**
Consolidación semanal profunda del second brain por tenant ("Mia sueña"): un solo job de cron
(`dreams_weekly`; el gate verifica que NO exista un `gepa_weekly` separado) que orquesta 6 pasos
sobre las trazas de los últimos 7 días:
1. **Replay** — métricas de la semana (asuntos trabajados, approval/edit/rejection rate, skills
   activados, gaps sin RAG por `retrieved_doc_ids == []`, horas de trabajo) persistidas en
   `tenant_settings.config → {dreams,last_metrics}` (jsonb_set).
2. **Wiki update** — por cada asunto aprobado llama `WikiManager.update_from_approved_matter`; los
   rechazos alimentan el concepto especial "Patrones rechazados" (confidence 0.10, sección "Lo que
   NO funciona") en la wiki del tenant.
3. **GEPA** — corre `run_evolution_cycle` (el ciclo del Módulo 1) dentro del sueño.
4. **Lint + archivo** — `lint_wiki` detecta conceptos stale/orphan y los archiva; poda skills viejos.
5. **Nudges** — con ≥3 ediciones repetidas del mismo contexto, agrega una regla a la sección
   "## Preferencias aprendidas por Mia" del SOUL.md del tenant (idempotente: no duplica reglas).
6. **Weekly report** — resumen EN LENGUAJE DE ABOGADO ("Esta semana X trabajó N asuntos…"), sin
   jerga, persistido como propuesta `weekly_report` en `feedback_proposals`.
Decisiones de diseño visibles: composición por inyección (recibe `TraceCapture`/`WikiManager`/
`GEPALoop` → testeable con tempdir); `run_all_tenants` aísla fallos por tenant (un tenant roto no
tumba el sueño de los demás); horizontal (mismo tripwire de jurisdicciones en el gate).

**Módulo 3 — Second brain UI (endpoints en `api/routes/ux.py` §"Second brain" + Pantallas 4/5) · gate `test_second_brain_ui.py` 15/15 PASS (re-corrido 2026-07-01)**
La cara visible del second brain para el abogado + conectores de conocimiento:
- **Endpoints** (todos bajo el middleware JWT por tenant): `GET /api/wiki/concepts` y
  `GET /api/wiki/concepts/{name}` (leer la wiki), `POST /api/wiki/concepts/{name}/feedback`
  (corrección del abogado → propuesta `wiki_correction` status `pending` — de nuevo HITL, no edita
  la wiki directo), `GET /api/dreams/report` (último `weekly_report`), `GET /api/skills/ranked`
  (ranking GEPA `grade_all_skills`), `POST /api/connectors/obsidian/sync` (sincroniza el vault —
  ruta validada con la allowlist `config.resolve_obsidian_vault`, endurecida en el smoke del
  2026-06-30 — y persiste `obsidian_vault_path` en `tenant_settings`), `POST
  /api/connectors/pinecone/configure` (valida el índice con `describe_index`; si falla queda
  `status='inactive'` en vez de 500 — degradación suave). `GET /api/dashboard/stats` se amplió con
  el bloque `second_brain` (approval semanal, # conceptos, próximo sueño `dreams_weekly`) y
  `connectors.models` (modelos dinámicos).
- **Frontend**: Pantalla 4 `app/memoria/page.tsx` ganó el tab "Wiki del despacho" (+ botón
  "Sugerir corrección") y el "Resumen semanal" destacado; Pantalla 5 `app/dashboard/page.tsx` ganó
  la sección "Conectores" (Obsidian/Pinecone), "Salud del second brain" y selector "Modelo
  preferido". Sin jerga técnica (regla §G de CLAUDE.md).
El gate cubre los 8 endpoints vía `TestClient` (JWT real por tenant, conectores mockeados) + 6
checks de contenido del frontend.
⚠️ Nota del re-run 2026-07-01: al inicio del gate se ven reintentos `call_llm … Connection error`
(el seeding de la wiki intenta el LLM real y el proxy no estaba arriba); el fallback determinista
absorbe el fallo y los 15 checks pasan igual — comportamiento esperado, no un rojo.

**Gates (re-corridos 2026-07-01):** `test_gepa` **16/16** · `test_dreams` **16/16** ·
`test_second_brain_ui` **15/15** — idénticos a los números registrados en `task_plan.md` §Fase 5.
Cierra el riesgo "PENDIENTE — Módulos sin registrar en progress.md" de `bugs-and-risks.md`.

**Límites de esta entrada:** es reconstrucción por lectura de código; si la sesión 20 tomó
decisiones que NO son visibles en el código (alternativas descartadas, razones de negocio), no
están aquí ni en `decisions.md`.

---

## 2026-07-01 — Sesión 21 · Plan maestro: 10 checkpoints (CP0-CP5, CP-B1/B2, CP-C1/C2, CP3)

Plan completo en `C:\Users\jfeli\.claude\plans\quiero-que-elabores-un-streamed-wand.md`.
Commits del día (en orden): CP0 `f6bd780` · CP2 `3ca6438` · CP1 `71c2df7` · CP4 `adde9d9` ·
CP5 `4cab69d` · CP-B1 `5426a0a` · CP-B2 `bd53711` · CP-C1 `1f9e7f2` · CP-C2 `2c05bde` ·
CP3 `5c54903`. **Todos** los checkpoints pasaron por revisor independiente (capa 2) con
hallazgos corregidos ANTES de cada commit.

**CP0 — Estabilidad de plataforma (`f6bd780`)**
LiteLLM proxy separado en su propio venv `.venv-litellm/` (`litellm[proxy]==1.74.8`) + runtime
del API re-pineado exacto en `backend/pyproject.toml`. Gate nuevo `execution/check_env_pins.py`
cableado al arranque (`start_api.ps1`) y a la regresión (`run_tests.ps1`): si el venv fue
alterado, aborta. **Riesgo #32 CERRADO.**

**CP2 — Motor por suscripción + política por tenant (`3ca6438`, decisión #27)**
Mia piensa con la suscripción de Claude Code del abogado (`claude -p` headless, sin billing por
API); 3 políticas por tenant: "Mi suscripción" (default) / "Nube" / "Todo en mi equipo".
Gate `test_model_policy` **40/40**. Verificado EN VIVO: turno completo de 176s con borrador de
19.098 chars y citas correctas, cero facturación por API.

**CP1 — Recuperación real ante CONTEXT_TOO_LONG (`71c2df7`)**
Shrink POR NODO (`agents/context_recovery.py`): analysis recorta documentos, draft recorta
playbooks/diagnóstico preservando siempre la conclusión; una sola compresión por turno.
Gate `test_context_recovery` **34/34**. **Riesgo #33 CERRADO.**

**CP4 — Importación de guías del despacho (`adde9d9`)**
`POST /api/playbooks/import` (multipart, .md/.txt/.docx, varios a la vez): cada título H1 se
vuelve una guía; soporta guías protegidas inmunes al mantenimiento. Gate `test_playbook_import`
**21/21**. Cierre parcial del Riesgo #20 (falta solo que el despacho cargue sus guías reales).

**CP5 — Diagnóstico visible + pending_review (`4cab69d`)**
El diagnóstico jurídico por fin se VE: panel "Diagnóstico" en la pantalla del asunto + punto
naranja en la lista cuando hay borrador esperando revisión. Gate `test_ux` **29/29** (incluye
`npm run build`). Frontend pendiente de capa 3 de Cursor (2 archivos).

**CP-B1 — Modo asistente (`5426a0a`, decisión #28)**
Conversación libre fuera del expediente (una sola Mia): historial persistente por tenant+usuario
(migración `015_assistant.sql`), ContextCompressor cableado a su propósito original. Gate
`test_assistant` **32/32**. El revisor encontró 1 BLOQUEANTE (compresor compartido entre
despachos mezclaba contexto) — CORREGIDO antes del commit (compresor nuevo por turno).

**CP-B2 — Puente Telegram (`bd53711`, decisión #29)**
Bot privado single-chat → POST a `/api/assistant/chat` con JWT (RLS y política de modelo
idénticos al frontend). Opt-in: apagado hasta que Pipe cree el bot (guía sin jerga:
`docs/telegram-setup.md`). Gate `test_telegram_bridge` **22/22**.

**CP-C1 — Conector de carpetas del abogado (`1f9e7f2`, decisión #30)**
Disco local + OneDrive + Google Drive (carpetas espejo, sin OAuth) → `knowledge_chunks`;
migración `016_local_folders.sql`; allowlist fail-closed de 2 capas. Gate `test_local_folders`
**39/39**. Revisor: 2 mayores de PRIVACIDAD corregidos (subcarpetas de sistema excluidas también
en el descenso recursivo; carpetas >2000 archivos ya no pierden conocimiento).

**CP-C2 — Vault de Obsidian bidireccional + instalación guiada (`2c05bde`, decisión #32)**
Mia escribe su memoria (conceptos de la wiki + reportes semanales) como notas .md en el vault
del abogado, SOLO bajo `Mia/`; wiki interna sigue siendo fuente de verdad; instalación guiada
de Obsidian vía winget con confirmación explícita. Gate `test_vault_write` **34/34**. Revisor:
escape por junction/symlink de Windows BLOQUEADO fail-closed (reproducido con `mklink /J`).

**CP3 — El conocimiento del despacho entra al análisis (`5c54903`, decisión #31)**
`retrieve_knowledge_rrf` sobre `knowledge_chunks` (mismo RRF híbrido, sin filtro de asunto,
RLS fail-closed); sección "Conocimiento del despacho" en el prompt con presupuesto ≤15% y
fencing anti prompt-injection; knowledge se recorta ANTES que los documents en el shrink.
Gate `test_retrieval_knowledge` **35/35**. **APROBADO por Pipe con comparación A/B en vivo**
(análisis con y sin el método del despacho). **Riesgo #16 CERRADO.**

**Regresión final de la sesión: 40/40 suites verdes** (`test_rls` 12/12 HALT intacto).

---

## 2026-07-01 — Sesión 22 · CP-B3: proactividad (recordatorios + avisos por Telegram)

**CP-B3 — Mia te avisa y recuerda (rama `feat/cp-b3-proactividad`)**
Mia deja de ser solo reactiva. Tres piezas nuevas:
- **Recordatorios en lenguaje natural** (`assistant/reminders.py` + migración `017_reminders.sql`):
  "recuérdame radicar la tutela mañana a las 9" crea un recordatorio SIN pasar por el LLM
  (parser determinista en español: mañana / el viernes / en 2 horas / el 15 de agosto / horas
  am-pm; crear algo que sonará después no puede depender de que un modelo "entienda"). Sin
  fecha reconocible → Mia PREGUNTA. Cancelación por chat también determinista. RLS fail-closed.
- **notify.py (canal de salida común)**: POST directo a la Bot API de Telegram (mismo bot de
  CP-B2), opt-in y fail-soft (sin token → no-op), sin loguear jamás token ni contenido.
- **Jobs del scheduler**: `reminders_due` (5 min; marca 'sent' SOLO si Telegram aceptó, si no
  reintenta), `pending_review_notify` (1h; aviso agregado de borradores esperando revisión con
  debounce de 24h por asunto, reseteado al decidir en hitl.py) y envío del reporte semanal de
  Dreams. Todos notifican SOLO al tenant dueño del canal (`MIA_BRIDGE_EMAIL`) — el contenido
  de otro despacho JAMÁS sale por el chat de Telegram de Pipe.

**REGLA DURA implementada**: recordatorios con vocabulario procesal (radicar, audiencia,
emplazamiento, sentencia, término, expediente, "días hábiles"…) SIEMPRE llevan [VERIFICAR] —
la fecha la pone el abogado y la confirma él; Mia no calcula términos legales, y "N días
hábiles" ni siquiera se agenda: se pide la fecha exacta.

**Gate `test_reminders.py` 64/64** · regresión completa **41/41 suites** (`test_rls` 12/12 HALT).
`test_assistant` actualizado (su primer turno usaba "recuérdame…", que ahora es determinista).

**Revisor independiente (capa 2)**: APROBADO CON CORRECCIONES — 2 bloqueantes y 5 mayores,
TODOS corregidos antes del commit y convertidos en checks del gate:
- B1 vocabulario procesal incompleto (emplazamiento/sentencia/diligencia/fiscalía → ampliado).
- B2 confirmaciones falsas: "¿cuándo?" → "mañana a las 9" ahora crea el recordatorio de verdad
  (turno de seguimiento determinista) y el modelo tiene PROHIBIDO confirmar acciones de
  recordatorios que el sistema no confirmó.
- M1 "días hábiles" no se calculan · M2 año explícito respetado ("el 15 de agosto de 2027") ·
  M3 promesa honesta: sin canal de avisos la confirmación lo dice · M4 cancelación por chat
  determinista · M5 "avísame" sin fecha ya no secuestra frases conversacionales.
- Menores: 29-feb sin crash, mark_sent no pisa cancelaciones, chequeo barato antes de conexión
  admin cada 5 min, endpoints con errores amables (§G), log de notify sin superficie de token.

**Residuales documentados (bugs-and-risks.md)**: canal único de Telegram (multi-tenant real
necesitará canal por despacho), reintento sin tope si Telegram rechaza permanente, duplicación
de avisos si algún día corren varios workers, "a la 1" = 01:00 (la confirmación muestra la hora).

**Bloqueantes:** ninguno. La prueba viva con el celular de Pipe queda pendiente de que él cree
su bot (guía `docs/telegram-setup.md`) — el sistema completo es opt-in hasta entonces.

**CP-C3 — Cierre del circuito de aprendizaje (misma sesión 22, rama main local)**
El hallazgo del explorador: el cableado de `activated_playbooks` YA existía end-to-end
(graph → traza v2 → GEPA/Dreams); la brecha real era LÓGICA — el FeedbackProcessor proponía
mejoras contra un playbook ARBITRARIO (el primero activo del tenant), no contra el que
participó en los turnos rechazados/editados. Qué se corrigió:
- `analyze()` acumula por señal QUÉ playbooks estaban activados en las trazas que fallaron;
  `propose()` apunta al MÁS activado en esas trazas (activo, no protegido), con fallback
  honesto al más usado; solo-protegidos → `new_playbook` (nunca más un 409 sin salida).
- La propuesta se redacta viendo el CONTENIDO REAL del playbook (antes el LLM proponía a
  ciegas y aplicar PISABA la metodología); `apply_proposal` guarda el contenido anterior en
  `metadata.last_improvement` (reversible) + proposal_id + fecha ISO.
- `list_proposals` devuelve el TÍTULO del procedimiento target — el abogado ya no aprueba
  a ciegas qué se modifica (falta pintarlo en la Pantalla 4 → CP7).
- `gepa.trace_playbook_ids` promovido a API pública (lo usa el FeedbackProcessor).

**Gates extendidos:** `test_trace_capture` 23/23 (+3: roundtrip v2 de activated_playbooks) ·
`test_gepa` 18/18 (+2: grading con listas) · `test_feedback_processor` 26/26 (+5: vinculación
señal→playbook, protegidos jamás target) · `test_ux` 29/29. Regresión completa 41/41.
**Revisor (capa 2): APROBADO** — sus 2 mayores (pre-existentes, agravados por CP-C3) se
corrigieron igual antes del commit; menores 3/5 corregidos, 2 aceptados (NO_RESULT acumula
playbooks sin usarlos aún; decisión de producto del fallback documentada).

**Riesgo #31 CERRADO** (el circuito conecta señales con el playbook correcto). **Riesgo #20
sigue abierto**: la vuelta EN VIVO del ciclo con un caso real necesita que Pipe suba sus
primeras guías de trabajo (`POST /api/playbooks/import`) — sin playbooks sembrados no hay
activación que observar. El reporte semanal por Telegram quedó cubierto desde CP-B3.


**CP6 — Una sola voz (rama `feat/cp6-una-sola-voz`, commit eceb59a — SIN MERGE, alto impacto)**
Los 3 nodos del grafo componen su system con la fachada `build_graph_system` (10 capas del
prompt_builder): identidad "Eres Mia" + SOUL del despacho (L1), metodología (L2), citación
[VERIFICAR] (L3), §G (L5), contexto del asunto (L7), instrucción del nodo (L8, ex
ANALYSIS/DRAFT/EDIT_SYSTEM), índice de playbooks con fencing anti-inyección (L9), fecha (L10).
Cierre estructurado del diagnóstico (problema/normas/riesgo) parseado determinista →
`diagnosis_summary` en HITL/SSE/GET draft; la prosa que ve el abogado va sin el bloque de
máquina. SOUL validado (9 secciones) con reintento correctivo y fallback determinista, también
en la revisión trimestral (update_soul). Gates: prompt_builder 46/46 (+14) · e2e 31/31 (+6) ·
context_recovery 34/34 · retrieval_knowledge 35/35 · hitl 19/19 · agent_core 26/26; regresión
41/41. Revisor capa 2: APROBADO CON CORRECCIONES — 3 mayores (update_soul sin validar; bloque
`===` visible al abogado; SSE no reenviaba el resumen) y 3 menores, TODOS corregidos pre-commit.
**Comparación A/B EN VIVO ejecutada** (mismo expediente de reparación directa, motor de
suscripción real): DESPUÉS más enfocado (34 vs 76 menciones normativas, análisis/borrador
separados limpios, resumen ejecutivo de 3 líneas) — entregada a Pipe. **Merge pendiente de su
aprobación.** Nota honesta registrada: ambas versiones dejan 5-6 sentencias específicas sin
[VERIFICAR] al lado — riesgo pre-existente que ataca CP8c (en pausa).


**CP7 — Sincronización del frontend (rama `feat/cp7-sincronizacion-frontend`, 2026-07-02)**
El abogado gobierna todo desde la pantalla: pestaña **Habilidades** (skills/ranked con % de
aprobación), botón **Importar guías** (playbooks/import multipart con detalle en llano por
archivo), las sugerencias muestran **qué procedimiento se modificaría** (target de CP-C3),
sección **"Orden del conocimiento"** (propuestas del Curator con Aprobar/Rechazar y manejo
del drift 409), selector **"Motor de IA"** que consume la política CP2 (reemplaza al selector
de modelos crudos que violaba §G y NO persistía), sección **Recordatorios** (CP-B3: listar con
hora + cancelar solo con confirmación del servidor), `triad_mode` FUERA del onboarding
(Riesgo #27 cerrado en UI, filtro HIDDEN_QUESTION_IDS) y el panel Diagnóstico pinta el resumen
estructurado de CP6 cuando exista (condicional, inofensivo sin merge de CP6).
Gate `test_second_brain_ui` **26/26** (+11: UI + contratos API reales) · `npm run build` ✓ ·
regresión **41/41**. Revisor capa 2: APROBADO CON CORRECCIONES — 1 mayor (falso éxito al
cancelar recordatorios) + 1 mayor preexistente (API key de Pinecone visible → type=password)
+ 5 menores: TODOS corregidos pre-commit. Capa 3 (Cursor) PENDIENTE vía HANDOFF.md (4 archivos).
Deuda §G anotada: textos "second brain"/"vault"/"Pinecone" del dashboard viejo.


**CP-C4 — Asistente de configuración guiado (rama `feat/cp-c4-setup-guiado`, 2026-07-02)**
Cierre del Pilar C: cualquier abogado deja a Mia conectada sin saber nada técnico.
`GET /api/setup/status` detecta 6 pasos (perfil/SOUL, motor vía claude/ollama en el equipo,
Obsidian+vault, carpetas+nubes espejo, guías, Telegram) con textos §G y detectores fail-soft
en threads con caché de 60s (winget puede tardar hasta 60s — hallazgo del revisor); es SOLO
LECTURA (las acciones viven en sus endpoints con sus confirmaciones). Skip/unskip retomable
persistido en `tenant_settings.config['setup']` (merge jsonb anidado que preserva claves).
Página nueva `/configurar` (checklist + progreso + guía de Telegram inline sin rutas técnicas)
+ enlace en Sidebar. El asistente guía por chat: bloque de estado real inyectado cuando el
mensaje menciona el dominio (obsidian/telegram/drive/carpetas/"configura a Mia") — el
disparador NO reacciona a verbos jurídicos ("se configura la causal", hallazgo M1 corregido).
Gate `test_setup_wizard` **21/21** · `npm run build` ✓ · regresión **42/42**. Revisor capa 2:
APROBADO CON CORRECCIONES (3 mayores + 3 menores corregidos; residual aceptado: carrera menor
en skip con doble clic). Capa 3 (Cursor) pendiente. **Recorrido vivo cronometrado con Pipe:
pendiente de él** (gate del plan).

---

## 2026-07-02 â€” SesiÃ³n 24 Â· CP6 aprobado y mergeado + CP9 equipo de especialistas

**CP6:** Pipe aprobÃ³ la comparaciÃ³n A/B ("gran avance") â†’ merge a `main` (4d5b875), gates
post-merge verdes (rls 12/12, prompt_builder 46/46, e2e 31/31, retrieval 35/35, recovery
34/34). Push a origin PENDIENTE de aprobaciÃ³n de permisos.

**CP9 (encargo de Pipe):** equipo de especialistas en rama `feat/cp9-equipo-especialistas`
(a22b72c): grafo intakeâ†’factsâ†’researchâ†’analysis(cruce)â†’draftâ†’verificationâ†’HITLâ†’finalize.
- `agents/research.py`: SAT-Graph acotado por jurisdicciÃ³n del tenant (fail-soft), fuentes
  fenceadas anti-inyecciÃ³n; patrones de cita extra por pack (`citation_style.json`).
- `agents/verification.py`: escÃ¡ner determinista de citas (sin LLM); cita sin marca ni
  respaldo â†’ se anota [VERIFICAR]; informe {citas,marcadas,respaldadas,anotadas,detalle}
  al SSE, al endpoint del borrador y a metadata. Corre en to_thread.
- `output/docx_export.py` + endpoint `draft.docx`: borrador â†’ Word con formato de escrito.
- Capa 2: APROBADO CON CORRECCIONES â€” M1 cupo de compresiÃ³n POR NODO (TurnLLMState.
  compressed_stages, compat pre-CP9) porque el cupo global mataba el turno en expedientes
  grandes con 4 nodos LLM; M2 ReDoS real en el patrÃ³n de artÃ­culos (16s con input de 52
  chars) â†’ regex sin ambigÃ¼edad + to_thread. Checks cp9-37..41.
- Gates: test_document_pipeline 41/41 Â· test_hitl_flow actualizado (19/19) Â· regresiÃ³n
  43/43 (test_rls HALT verde).
- **A/B EN VIVO** (mismo expediente/pregunta de CP6, motor suscripciÃ³n): ANTES 5,2min /
  DESPUÃ‰S 5,9min; borrador final ANTES con 3 citas sin marca vs DESPUÃ‰S **0** (el
  verificador anotÃ³ las 2 que se escaparon); borrador mÃ¡s enfocado (13,8k vs 19,8k chars);
  resumen ejecutivo se conserva. Persistido en `docs/comparacion-cp9.md` + muestra Word.
- Deuda anotada: el diagnÃ³stico no pasa por el verificador (solo el borrador); artÃ­culos
  con numerales intercalados pueden escapar al detector; corpus semilla no arrojÃ³ fuentes
  (0 respaldadas â€” se activarÃ¡ con corpus real).

**PENDIENTE de Pipe:** decisiÃ³n de merge de CP9 con `docs/comparacion-cp9.md`. Luego:
CP-C4b (wizard explicativo, encargo previo), frontend de CP9 (botÃ³n Word + informe de
verificaciÃ³n, ya en HANDOFF.md para Cursor), y el push de main.


---

## 2026-07-02 â€” SesiÃ³n 24 (cont.) Â· CP9 mergeado + CP-C4b wizard explicativo

**CP9:** Pipe aprobÃ³ â†’ merge a `main` (424a666), gates post-merge verdes, `git push origin main`
autorizado y ejecutado. Frontend de CP9 (botÃ³n Word + informe de verificaciÃ³n) queda como trabajo
de Cursor en HANDOFF.md.

**CP-C4b (encargo de Pipe):** el wizard "Configura a Mia" ahora EXPLICA como onboarding.
Rama `feat/cp-c4b-wizard-onboarding`.
- `api/routes/setup.py`: `STEP_GUIDES` (quÃ© es / para quÃ© sirve al despacho / cÃ³mo paso a paso, por
  paso) + `MIA_SECTIONS` (mapa de secciones de Mia). El status ahora incluye `pasos[].guia` y
  `secciones` (aditivo, no rompe consumidores).
- `assistant/core.py`: `_setup_block` inyecta la guÃ­a completa del siguiente paso pendiente (el
  asistente acompaÃ±a, no solo enumera). `_sanitize_title` acepta `max_chars`.
- `frontend/app/configurar/page.tsx`: botÃ³n "Â¿QuÃ© es esto?" por paso, mapa de secciones, a11y
  (role=progressbar + aria, aria-expanded, estado sr-only).
- Capa 2: APROBADO CON CORRECCIONES â€” CORREGIDAS: L1 (guÃ­a cortada a 150 chars en el chat â†’ check
  a4); U1/U2/U4/U5/U8 (las guÃ­as describÃ­an pantallas/chat web inexistentes â†’ reescritas a la
  realidad de HOY, sin referencias circulares); U3 (promesa de Word/verificaciÃ³n suavizada). La UI
  faltante (secciÃ³n Carpetas, botÃ³n Instalar Obsidian, botones de CP9) quedÃ³ DOCUMENTADA en
  HANDOFF.md para Cursor en vez de fingir que existe.
- Gates: `test_setup_wizard` 30/30 Â· regresiÃ³n 43/43 (test_rls HALT verde) Â· `npm run build` verde.

**PENDIENTE de Pipe:** decidir merge de CP-C4b; construir con Cursor la UI faltante (carpetas,
instalar Obsidian, Word + verificaciÃ³n de CP9); crear su bot de Telegram; subir sus primeras guÃ­as;
recorrido vivo cronometrado de "Configura a Mia".


## 2026-07-02 · Sesión 26 — auditoría de seguridad + CP-V1 (ROI)
- Auditoría 2026-07 commiteada a main (c3bdcc2) tras 3 capas + 4 correcciones del revisor.
- CP-V1 completo (74cb2bb): turn_usage + metrics/usage + metrics/value + /api/value/settings +
  tarjeta del panel. Gate 27/27; regresión 50/50; visual OK (tarjeta y tarifa 250 reflejada).
- Migración 021 aplicada en la DB local (execution/init_turn_usage.py, idempotente).
- Riesgo #43 registrado (límites del estimado de valor).

## 2026-07-02 · Sesión 27 — CP-V2: auto-diagnóstico prescriptivo (cierra la Ola 4)

**CP-V2 (rama `feature/cp-v2-diagnostico`)** — evoluciona el Dreams semanal a un motor de
recomendaciones puntuadas por **gravedad × impacto económico × certeza** (patrón ClaudeOS
skills/dream, adaptado a lo jurídico). Piezas:
- `backend/mia/memory/prescriptions.py`: motor **DETERMINISTA (sin LLM)** — la anti-invención
  queda garantizada por construcción: toda evidencia sale de CONTEOS de datos reales (trazas de
  turnos 30 días, turn_usage de CP-V1, guías vía GEPA, config de valor) y con <5 eventos el
  bucket SE SALTA. 6 buckets: retrabajo (correcciones repetidas del mismo contexto), rechazos
  (tasa ≥25%), conocimiento (respuestas sin fuentes del despacho), costo (gasto real pagado →
  selector "Motor de IA" del Panel), guías (uso alto + aprobación <60%), valor (tarifa de
  fábrica). IDs ESTABLES (slug determinista) + top 4 con diversidad (máx. 2 por categoría).
- Migración `022_dream_prescriptions.sql` (+ `init_dream_prescriptions.py`): memoria de
  recomendaciones por tenant (RLS ENABLE+FORCE): lo aceptado/descartado NO se repite salvo señal
  viva pasados 30 días (vuelve como 'recurring' con edad rastreada).
- `dreams.py`: sección `diagnostics` en run() (fail-soft: si el diagnóstico falla, Dreams sigue)
  + línea en el reporte semanal con la recomendación principal.
- Endpoints `GET /api/dreams/prescriptions` (tarjetas vigentes por score, solo surfaced) y
  `POST /api/dreams/prescriptions/{id}/decision` (accept/dismiss). Frontend → HANDOFF (Cursor).

**Capa 2 (revisor adversarial): APROBAR CON CORRECCIONES — los 4 MAYORES corregidos pre-commit:**
- H1 · carrera cron×decisión: el upsert de _persist podía PISAR una decisión del abogado tomada
  durante la corrida (status='recurring', decided_at=NULL) → ahora _load_states captura el reloj
  de la DB al inicio y el ON CONFLICT preserva status/decided_at si decided_at >= run_started.
- H2 · la poda borraba tarjetas VIVAS que solo salieron del top por ranking/diversidad (reset de
  first_seen → edad falseada) → ahora se upserta TODA señal viva con `surfaced` true/false en el
  payload; el GET filtra surfaced; la poda solo toca señales desaparecidas.
- H3/H4 · el bucket de costo v1 era CÓDIGO MUERTO (recomendaba mover tareas de apoyo al modelo
  económico — pero ya corren ahí en toda política, decisión #7) y prescribía una acción en una
  pantalla sin ese control → REDISEÑADO: dispara solo con gasto real pagado (motor 'nube',
  ≥5 llamadas, ≥1 USD) y apunta al selector "Motor de IA" del Panel de control (verificado:
  dashboard/page.tsx consume GET/PUT /settings/model-policy — el grep del revisor falló por el
  prefijo). dollar_impact = gasto real del período.
- H5 (texto de valor prometía editar minutos que la tarjeta no expone → solo tarifa), H6 (el
  gate probaba el costo con un input arquitectónicamente imposible → escenario real), H7
  (fragilidad del ID de retrabajo ante inputs variables → limitación declarada, Riesgo #44).

**Re-verificación de capa 2: APROBAR** (los 7 cerrados) con 2 residuales menores, TAMBIÉN
cerrados en la misma sesión: R1 (ventana de carrera por transacciones solapadas — el timestamp
de inicio de transacción podía ser anterior a run_started) → el upsert ya NO compara relojes:
jamás resetea una fila con decisión; solo el flag explícito `_resurface` de run() la reabre.
R2 (el texto de costo recomendaba "Mi suscripción" incluso si esa ya era la política y el gasto
venía de un fallback del CLI a la API paga) → texto neutro que además alerta el fallback.

**Gates:** `test_dreams.py` 16 → **43/43** (guarda anti-invención con tenant vacío, IDs estables,
decisión no se repite / resurge a 31 días, carrera cron×decisión + resurgimiento explícito, poda
respeta señal viva, diversidad, buckets puros de costo/retrabajo, RLS forzado en la tabla nueva,
sin jurisdicciones hardcodeadas). **Regresión completa 50/50 suites × 3 corridas** (base, tras
correcciones H1-H7, tras R1/R2). Migración 022 aplicada en la DB local (idempotente).
Riesgo #44 registrado.

## 2026-07-03 · Sesión 28 — CP-Z1: dictado local (abre la Ola 3, voz)

**CP-Z1 (rama `feature/cp-z1-voz-local`)** — voz-a-texto 100% LOCAL: el audio del abogado nunca
sale del servidor del despacho. Motor reusa lo que **Lexter** (dictado de escritorio de Pipe, fork
de Handy MIT) ya validó en español jurídico (diseño en `docs/analisis-lexter.md`): Silero VAD +
**Parakeet TDT 0.6B v3 int8** vía **sherpa-onnx** (decisión de modelo de Pipe). Piezas:
- `backend/mia/speech/audio.py`: WAV del navegador → PCM float32 16 kHz mono (stdlib `wave`+numpy,
  sin ffmpeg); mezcla estéreo, decodifica 8/16/24/32 bits, re-muestrea; rechazos en llano
  (vacío/corrupto/>5 min/>32 MB) con la jerga técnica fuera del mensaje.
- `backend/mia/speech/engine.py`: motor con carga perezosa (singleton), parámetros de Lexter
  (umbral 0.3, margen 450 ms, trozos 60 s, clips <1 s → 1.25 s); VAD Silero para trocear audios
  largos, cortes fijos si el VAD no está; provider CPU/DirectML configurable con degradación.
- `backend/mia/speech/policy.py`: candado `allow_cloud_audio` por tenant, default False,
  **fail-closed** (patrón model_policy_for_strict de CP-P4) — un motor de nube futuro exigiría
  opt-in explícito; hoy el motor es local (`ENGINE_IS_LOCAL`), así que no bloquea a nadie.
- `backend/mia/speech/cleanup.py`: pulido opcional del dictado con el modelo **LOCAL**
  (`mia-local`, cadena de UN alias sin fallback a nube) + guardrail anti-traducción; fail-soft.
- `backend/mia/api/routes/speech.py`: `POST /api/speech/transcribe` (multipart, autenticado);
  rate-limit por abogado, semáforo global + timeout, decodificación y STT en `asyncio.to_thread`.
- `scripts/download_speech_models.ps1`: baja los pesos (gitignored) — no se versionan.
- `backend/pyproject.toml`: `sherpa-onnx~=1.13` (fuera de los pins críticos del Riesgo #32;
  check_env_pins 9/9 intacto).

**Capa 2 (revisor adversarial con contexto fresco): APROBAR CON CORRECCIONES.** Verificó por
CÓDIGO que la regla no negociable se cumple (audio local, candado fail-closed real, sin fugas en
logs, `/api/speech/transcribe` no es OPEN_PATH, `resolve_fallback_chain` con model explícito = 1
alias). 2 MAYORES + 6 menores corregidos pre-commit (detalle en Riesgo #45):
- MAYOR · decodificación del WAV corría en el event loop antes del semáforo (numpy sobre 32 MB) →
  N clips congelaban los SSE de otros abogados. Movida a to_thread dentro del semáforo →
  **verificado con probe: 3 clips de 24.7 MB simultáneos, gap del loop 46 ms (<150 ms objetivo)**.
- MAYOR · rate-limit por despacho castigaba firmas multi-abogado → llave (tenant, email).
- menores · guardrail burlable con "no" (palabra ES/EN) → exige ≥2 stopwords ES y veta EN;
  60 s de silencio iban al STT → VAD vacío = 0 trozos; curl sin -f; jerga "tenant" en 401;
  `_clip_hits` sin poda; + timeout de STT (503 si el motor se cuelga).

**Gates:** `test_speech_stt.py` **41/41** (audio adversarial, guardrail, ruta con motor doble,
candado fail-closed contra DB real, e integración REAL con los pesos: es.wav → español correcto,
76 s → camino VAD, 70 s de silencio → 0 STT rápido; + a-04b 24 bits, c-07 contrato sin-nube en
llm.py, c-08 OPEN_PATH, r-06b cupo por abogado). **Regresión completa 51/51 suites** (test_rls
12/12 HALT) tras correcciones. Riesgo #45 registrado. Frontend (botón 🎤) → HANDOFF para Cursor.

---

## 2026-07-03 · Sesión 29 — CP-Z1b: la voz instalada en el producto (instalador + wizard + micrófono)

Pipe pidió "incorporar en el producto la instalación de voz" y aprobó el alcance COMPLETO
(AskUserQuestion): instalador desde la pantalla + paso del wizard + botón de micrófono usable.
Antes de esto, activar el dictado exigía que un administrador corriera un script (.ps1) y el
motor de CP-Z1 no tenía botón — inusable para el usuario objetivo.

**Backend:**
- `backend/mia/speech/install.py` NUEVO: instalador de los modelos desde el producto — Python
  stdlib puro (urllib+tarfile+shutil → funciona en Modo A Docker/Linux, a diferencia del
  instalador de Obsidian que es solo-host; NO deshabilitarlo en Modo A, está en el docstring).
  Single-flight bajo lock angosto (el I/O de disco quedó FUERA del lock; el worker re-verifica
  en disco qué falta al arrancar → un dato viejo = no-op), progreso consultable (bytes/fase),
  publicación ATÓMICA vía `.staging` + os.replace (un corte a mitad de la extracción de 650 MB
  jamás deja a get_status diciendo "instalado" — hallazgo MAYOR de capa 2, verificado con g-13),
  `_present()` = archivo de 0 bytes cuenta como ausente, anti path-traversal que también rechaza
  symlinks/hardlinks (`_validate_member`, g-08b), reintento limpio tras fallo, mensajes en llano
  diferenciados (solo-VAD no anuncia 700 MB). Mismas URLs/carpeta que el ps1 (que se conserva).
- `routes/speech.py`: `GET /api/speech/status` y `POST /api/speech/install` ({"confirmar": true}
  o 400 — consent-first patrón Obsidian); ambos por asyncio.to_thread; no son OPEN_PATH (g-10).
- `engine.py`: el 503 ya manda al "Panel de control → Instalar dictado por voz" (sin ps1).
- `setup.py`: paso 7 "voz" del wizard (STEP_IDS al FINAL — capacidad opcional; STEP_GUIDES en
  llano con privacidad EXACTA: "la transcripción ocurre completa ahí [servidor del despacho]";
  detección vía _detected con caché 60 s → tras instalar puede tardar ≤60 s en verse listo).

**Frontend (construido por Claude Code; Cursor hace capa 3 vía HANDOFF):**
- `lib/wav.ts` (concatenar Float32 + resample OfflineAudioContext 16 kHz + WAV PCM16 RIFF, sin
  librerías — MediaRecorder/webm NO sirve, el backend solo decodifica WAV PCM).
- `lib/useDictation.ts`: hook de captura Web Audio (ScriptProcessorNode, decisión documentada);
  permiso de mic solo al PRIMER clic; UN arranque a la vez (startingRef + streamRef + busyRef —
  hallazgo MAYOR de capa 2: doble clic durante el diálogo de permiso dejaba un mic huérfano
  capturando); aliveRef detiene los tracks si el componente se desmonta durante el permiso;
  auto-stop a 300 s; try/finally alrededor del armado del AudioContext; 429 no se reintenta.
- `_components/MicButton.tsx` (estados con TEXTO + aria-pressed) integrado en el chat del asunto
  (asuntos/[id]; el texto dictado se AGREGA sin borrar lo escrito; avisos/errores en ámbar).
  NO existe pantalla de asistente con input en la web — el componente queda reutilizable.
- `dashboard/page.tsx`: tarjeta "Dictado por voz" (Conectores): estados, barra role=progressbar,
  confirmación role=alertdialog, polling 2 s SOLO durante la descarga con guard de vuelo y
  limpieza del mensaje al terminar. `lib/api.ts`: `apiUploadBlob` nuevo (apiUpload intacto).

**Verificación (3 capas):**
- Capa 1: `test_speech_stt.py` 41 → **60/60** (sección G del instalador: consent, single-flight
  con descarga bloqueada, progreso, retry, tar con '..' y symlink rechazados, 0 bytes,
  idempotencia parcial — todo con MIA_SPEECH_MODELS_DIR→tempdir y _download inyectada: los gates
  JAMÁS bajan los pesos reales ni tocan los de esta máquina); `test_setup_wizard.py` **30/30**
  (7 pasos, "6 de 7"); regresión **ALL PASS 51 suites** ×2 (test_rls HALT); npm run build ×3.
  EN VIVO (preview browser + API real con modelos en tempdir): tarjeta en sus 3 estados,
  confirmar/cancelar, instalación con descarga REAL de internet (detector de voz), tarjeta pasa
  sola a "Instalado" por polling, paso 7 en /configurar con guía, botón 🎤 con aria correcta, y
  POST multipart navegador→API con WAV generado en página (CORS multipart OK). Chrome MCP no
  estaba conectado → se usó Claude Preview con launch.json en la carpeta padre (fuera del repo).
- Capa 2 (revisor adversarial, contexto fresco): **APROBAR CON CORRECCIONES → re-verificado
  APROBAR**. 2 MAYORES (extracción no atómica → estado "instalado" mentiroso irreparable,
  demostrado empíricamente con archivos de 0 bytes; doble clic del mic durante el permiso →
  captura huérfana) + 4 menores + 3 notas — TODOS corregidos antes del commit y re-dictaminados
  CERRADOS por el mismo revisor (verificó os.replace de directorios en Windows empíricamente).
- Capa 3 (Cursor): HANDOFF.md actualizado — revisión visual pendiente; lo ÚNICO no cubierto por
  la verificación automatizada es dictar con micrófono REAL (pedido explícito en el HANDOFF).

**Riesgo #46 registrado** (residuales de capa 2, todos fail-closed). Commit en rama
`cp-z1b-instalacion-voz`; merge+push a main con aprobación de Pipe en el diálogo.


## 2026-07-03 — Sesión 30 · CP-Z2: conversación por voz en Telegram (cierra el bucle de voz)

**Qué se construyó:** Mia ya HABLA. El abogado manda una NOTA DE VOZ a su bot privado de Telegram; Mia la transcribe LOCALMENTE (mismo motor de CP-Z1, el audio nunca sale del servidor), corre el asistente, y responde con una NOTA DE VOZ sintetizada LOCALMENTE. Piezas: `backend/mia/speech/tts.py` (nuevo — motor VITS/Piper es_MX vía sherpa-onnx, mismo patrón que engine.py: singleton perezoso, provider CPU/DirectML, candado `TTS_IS_LOCAL`), `speech/opus.py` (nuevo — códec OGG/Opus con PyAV `av`, decodifica la nota entrante y codifica la saliente, con topes anti-bomba), `speech/audio.py` (despachador `decode_audio_to_pcm16k`: WAV→stdlib, OggS→opus), `speech/install.py` (`missing_components()` ahora 3-tupla; helper `_download_extract_publish` DRY para publicación atómica de Parakeet y TTS; el botón "Instalar dictado por voz" baja ambos), `api/routes/speech.py` (endpoint `POST /api/speech/synthesize` → audio/ogg, auth + rate-limit + candado + semáforo), `channels/telegram_bridge.py` (handler `filters.VOICE`; `MiaClient.transcribe/synthesize`; `handle_voice`: transcribe→devuelve lo ENTENDIDO por texto para verificación→chat→síntesis→`send_voice`; regla de modalidad voz↔voz, texto↔texto; degrada a texto si el TTS falla). Dep nueva `av~=13.1` (fuera de pins críticos Riesgo #32; check_env_pins 9/9 intacto). Voz por defecto: es_MX-ald-medium (latinoamericana) — PENDIENTE la elección final de Pipe por el oído (se le mandaron 3 muestras: es_MX + 2 castellanas).

**Verificación 3 capas:** Capa 1 — gate nuevo `test_speech_tts.py` **26/26** (síntesis local + round-trip Opus + candado fail-closed + 503 al estar ocupado + rate-limit + recorte a MAX_TTS_CHARS + integración REAL con el modelo descargado); `test_telegram_bridge.py` **37/37** (bucle de voz h1-h10: transcribe→chat→synthesize→nota de voz, transparencia del "entendí", chat no autorizado ignorado sin bajar audio, voz vacía, transcripción vacía, respuesta larga→texto, TTS caído→texto, envío fallido→texto, texto↔texto sin synth, reply vacío→aviso honesto); `test_speech_stt.py` **60/60** (instalación ahora incluye el modelo de voz — fake tar TTS); regresión **ALL PASS 52 suites** ×2 (test_rls HALT). Sin frontend web → sin npm build. Prueba de humo con modelos reales: síntesis 5.25s→OGG/Opus 99KB→decode PCM16k round-trip; y bucle TTS→Opus→STT recupera la frase.

**Capa 2 (revisor adversarial, contexto fresco): CONFIRMADO con correcciones.** Los invariantes de confidencialidad (audio/texto nunca a la nube, candado fail-closed evaluado en cada request, puente loguea solo ids/longitudes), autorización (endpoint no OPEN_PATH; no se baja audio de chat no autorizado), modalidad, instalación (3-tupla en los 4 llamadores; publicación atómica) y concurrencia (todo lo pesado en to_thread) VERIFICADOS por código. 1 MAYOR + 2 MENORES corregidos ANTES del commit y RE-VERIFICADOS CERRADOS por el mismo revisor: (MAYOR) la espera para adquirir el semáforo no estaba acotada → bajo contención (web + Telegram a la vez) un turno colgaba hasta el timeout HTTP y degradaba en silencio → nuevo `_speech_slot()` con `wait_for(acquire, 45s)` → 503 explícito "ocupado"; (MENOR) reply vacío del asistente mandaba un texto vacío que Telegram rechaza → aviso honesto `VOICE_EMPTY_REPLY`; (MENOR) `on_voice` no validaba `file_size` antes de bajar → guardia de 20 MB. Residuo del revisor cerrado: el empate 300s=300s se eliminó bajando el acquire a 45s (margen 15s). Gates d-10 y h10 cubren los fixes.

**Riesgo #47 registrado.** Capa 3 = Pipe dicta una nota de voz REAL (lo único no cubierto por la automatización), tras crear el bot de Telegram e instalar la voz. Commit en rama `feat/cp-z2-voz-telegram`; **merge+push a main PENDIENTE de aprobación de Pipe en el diálogo** y de su elección de voz.


## 2026-07-03 — Sesión 30 (cont.) · CP-E1: auditoría de acciones + tope de gasto (abre la Ola 5)

**Qué se construyó (reusando lo existente, sin tocar el core):** dos capas nuevas inspiradas en los contratos de Hermes (observer read-only vs middleware control-activo). (1) **OBSERVADOR/auditoría:** `backend/mia/observability/audit.py` — sink `record()` (abre su conexión, FAIL-OPEN, nunca rompe el flujo) + `record_on_conn()` (escribe en una conexión transaccional dada); persiste en la tabla `audit_logs` que YA existía (migración 011, append-only, RLS). Enganchado en `api/middleware.py::_maybe_audit` (audita cada request MUTANTE POST/PUT/PATCH/DELETE autenticada, salvo `/api/speech/*` de alta frecuencia) y en `routes/stream.py` (el turno del asunto es GET → audit explícito con entity_id=matter_id). El `_audit` del curador (`memory/curator.py`) se refactorizó para usar `record_on_conn` (mismo SQL, misma atomicidad). **Confidencialidad:** solo metadatos (método, ruta SIN query string, ids, status) — el mensaje/consulta del abogado NUNCA llega a audit_logs. (2) **POLÍTICA/tope de gasto:** `backend/mia/policy/budget.py` — presupuesto MENSUAL por despacho en `tenant_settings.config['policy']['monthly_budget_usd']`; `enforce_budget()` bloquea el turno con `BudgetExceeded` (→ HTTP 402) cuando la SUMA de `turn_usage.cost_usd` del mes alcanza el tope; FAIL-OPEN (un error de lectura permite el turno — es guardia blanda de costo, no candado de confidencialidad). Enganchado en las entradas de turno (`routes/stream.py`, `routes/assistant.py`). Endpoint `routes/policy.py` GET/PUT `/api/policy/budget` (registrado en main.py). CP-V1 MEDÍA el gasto; ahora se puede LIMITAR. Sin migración (audit_logs y turn_usage ya existen; la config vive en jsonb).

**Verificación 3 capas:** Capa 1 — gate nuevo `test_observability.py` **22/22** (auditoría RLS + fail-open + recorte de campos a los topes de columna; middleware audita mutantes y NO GET/speech; tope: roundtrip incl. rama de producción, suma del mes UTC, bloqueo/permiso/ilimitado, fail-open; turno→402); regresión **ALL PASS 53 suites** ×2 (test_rls HALT; test_curator sigue verificando su auditoría → refactor sin regresión). Capa 2 (revisor adversarial): confidencialidad (sin fuga del mensaje: middleware guarda request.url.path sin query string; el turno audita matter_id no el path), aislamiento RLS, fail-open y no-regresión del curador CONFIRMADOS por código/DB real. **1 BLOQUEANTE + 1 MENOR corregidos ANTES del commit y RE-VERIFICADOS CERRADOS contra Postgres real:** (BLOQUEANTE) `set_monthly_budget` usaba `jsonb_set(config,'{policy,monthly_budget_usd}',...,create_missing)` que NO crea el objeto intermedio 'policy' si falta — y TODO tenant nace con config='{}', así que la rama UPDATE (única de producción) DESCARTABA el tope en silencio: el abogado creía haberlo fijado y nunca bloqueaba → corregido fijando el objeto '{policy}' entero con merge `||` (conserva otras claves); gate c-04b/c-04c ahora ejercita la rama UPDATE sobre fila existente (habría fallado con el código viejo). (MENOR) el borde del mes estaba corrido 5h porque `now() AT TIME ZONE 'UTC'` da naive reinterpretado en la zona del servidor (America/Bogota) → doble `AT TIME ZONE 'UTC'` lo re-ancla. Riesgo #48. Capa 3 (Cursor, HANDOFF): control del tope en el Panel (GET/PUT /api/policy/budget). **Commit en rama `feat/cp-e1-auditoria-politicas`; merge+push a main PENDIENTE de aprobación de Pipe.**


## 2026-07-03 — Sesión 31 · CP-E2: adjuntar pruebas por referencia (@expediente / @carpeta)

**Qué se construyó (ref Hermes `agent/context_references.py`, adaptado al dominio jurídico multi-tenant):** módulo nuevo `backend/mia/agents/context_references.py` que expande menciones `@expediente` (documentos del asunto en curso), `@expediente:"Título"|<uuid>` (otro asunto del despacho) y `@carpeta:"Etiqueta"|<uuid>` (carpeta de trabajo registrada de CP-C1) inyectando la evidencia SELLADA en el turno. **Diferencia clave con Hermes (fail-closed más estricto):** Mia NO tiene workspace de archivos por despacho — el "workspace" son sus filas en la DB, así que una referencia NUNCA resuelve a una ruta del disco: resuelve SIEMPRE contra `matters`/`documents`/`chunks` y `knowledge_chunks`/`local_folder_sources` bajo `pool.tenant_connection` (RLS fail-closed). `@carpeta` exige fuente `enabled AND kind='knowledge'` y lee SOLO contenido YA INDEXADO (jamás abre disco → cero superficie de path traversal). Piezas: (1) sellado CP-S1 (`agents.untrusted` — documentos como `<<<DOC n>>>`, archivos de carpeta como `<<<ARCHIVO n>>>`, anti-escape de marcadores embebidos); (2) techo de tokens Mia-tuned (soft 15% / hard 35% de la ventana) con recorte por referencia MARCADO (`[…recortado…]` + aviso — nunca recorta evidencia en silencio); (3) denylist explícita `_looks_like_path` (rechaza rutas/`..` antes de la DB) + `_like_escape` (comodines LIKE `% _`); (4) resolución por título/etiqueta exacto→ILIKE, ambigüedad → aviso sin adjuntar. **Enganches:** turno de asunto (`api/routes/stream.py`, tras el 409 de ciclo de vida) con `retrieval_query` LIMPIA (mensaje sin referencias ni adjuntos) para no ensuciar el embedding/RRF — campo nuevo `retrieval_query` en `MatterState` (total=False, backward-compat) usado en `graph.py::intake_node`; y asistente (`assistant/core.py`, donde CP-E2 es más transformador por no tener recuperación automática — expande sobre history[-1] tras los bloques matters/reminders/setup sin pisarlos; el mensaje PERSISTIDO es el original del abogado, el adjunto SOLO viaja al modelo). Ambos hooks FAIL-OPEN (adjuntar es ayuda, no candado; la confidencialidad sigue en RLS fail-closed por debajo).

**Verificación 3 capas:** Capa 1 — gate nuevo `test_context_references.py` **43/43** (offline: parseo, denylist, escape LIKE, recorte; DB real: resolución RLS, AISLAMIENTO entre despachos por título y por uuid, carpeta deshabilitada/no-registrada fail-closed, ruta rechazada por denylist, anti-escape del sello, techo de tokens con recorte marcado incl. carpeta con muchos archivos y nombres largos midiendo el bloque REAL, query de recuperación limpia, agrupación/orden de chunks por documento, passthrough sin referencias); regresión **ALL PASS 54 suites** ×2 (test_rls 12/12 HALT). Sin frontend web → sin npm build. Capa 2 (revisor adversarial independiente, contexto fresco): confidencialidad/RLS, confinamiento a filas del despacho (nunca disco), anti-inyección CP-S1, escape LIKE y frontera fail-open/fail-closed CONFIRMADOS por código; **2 MAYORES + 2 MENORES corregidos y RE-VERIFICADOS CERRADOS antes del commit:** (MAYOR 1) `_matter_documents`/`_folder_files` hacían `fetchall()` SIN `LIMIT` en SQL → materializaban el expediente/carpeta completo en memoria antes de cortar (DoS de recursos con datos legítimos) → `LIMIT MAX_FETCH_ROWS=2000` en SQL (tope de recursos, no de completitud; el techo de tokens recorta igual); (MAYOR 2) el listado "Documentos incluidos" de `@carpeta` se anexaba SIN descontarse del techo → una carpeta con muchos archivos de nombre largo desbordaba el techo duro → `listing_cost` descontado por archivo + reserva del encabezado; el gate era ciego a este camino → check 15c que mide el bloque REAL de `r.message` (no el auto-conteo); (MENOR 3) `@expedientes`/`@carpetas` (plural) hacían falso positivo → `\b` tras el grupo `kind`; (MENOR 4) mensaje SOLO la referencia reintroducía el token `@` al embedding → fallback a frase neutra. Defecto nuevo introducido por los fixes: ninguno (revisor re-verificó). Riesgo #49 registrado. **Commit en rama `feat/cp-e2-referencias-pruebas`; merge+push a main PENDIENTE de aprobación de Pipe.** OJO deuda de árbol evitada: `frontend/app/dashboard/page.tsx` (control de tope de CP-E1 que construyó Cursor) estaba sin commitear en el árbol — NO se mezcló con CP-E2, queda intacto para su propio commit.


## 2026-07-03 — Sesión 32 · CP-E3: personas jurídicas especializadas y editables (Ola 5)

**Qué se construyó (ref ClaudeOS Pantheon — `claudeos-ref/.../vite.config.ts::PANTHEON_SEEDS`, `skills/personas/SKILL.md` — llevado al dominio multi-tenant):** "personas" jurídicas editables por el despacho (litigante/tributarista/revisor de citas y las que el despacho cree), cada una con voz (`role_prompt`), tono, áreas de énfasis, un nivel de motor y frases de invocación. Diferencia clave con ClaudeOS: NO viven en YAML de disco (Mia es multi-despacho con RLS) — viven en la tabla `personas` (migración `023_personas.sql`, RLS ENABLE+FORCE) bajo `pool.tenant_connection`. Una persona es "QUIÉN HABLA" en un turno; complementa a los nodos de CP9 que son "CÓMO TRABAJA". Se invoca por frase en el mensaje del abogado (o por id explícito); **consent-first: sin invocación el turno es idéntico a hoy**. Piezas: (1) `backend/mia/agents/personas.py` (Persona dataclass + `PersonaService` CRUD bajo RLS + siembra idempotente de las 3 canónicas con flag `tenant_settings.config['personas_seeded']` que respeta el borrado + `detect_persona` por frase con `re.escape`+`\b`, la más larga gana + `render_persona_voice` con guardrail anti-invención + `resolve_persona_alias` = **el candado** + `resolve_for_turn` fail-open); (2) `backend/mia/api/routes/personas.py` (CRUD `/api/personas`, registrado en main.py); (3) `execution/init_personas.py`. **Enganches (todos fail-open, comportamiento byte-idéntico sin persona):** `prompt_builder.build_graph_system(+persona_voice)` antepone la voz a L8 (tier CONTEXT, no cacheado, no envenena el prefijo estable); los 5 nodos LLM del grafo (facts/research/analysis/draft/edit) pasan `persona_voice=_persona_voice(state)` y `model=_persona_alias(state)`; `graph.py::_llm(+model=)` propaga el alias en la llamada normal Y en el reintento por contexto largo; `MatterState.persona` (dict JSON-serializable, total=False) + `initial_state(persona=)`; `stream.py` resuelve la persona del turno (fail-open, dentro del contexto de política del request); `assistant/core.py::build_assistant_system(+persona)` y `chat()` (detección + voz + model, fail-open).

**EL CANDADO DE CONFIDENCIALIDAD (razón de ser del diseño de motor):** una persona JAMÁS elige un modelo crudo (eso evadiría la política del despacho — `resolve_fallback_chain(task, model=X)` devuelve `[X]` saltándose la cadena). Solo elige un NIVEL: `estandar` → `resolve_persona_alias` devuelve None (sin override, la cadena de la política gobierna, techo = política) · `local` → devuelve `LOCAL_ALIAS` (`mia-local`) **por construcción, no por posición de la cadena** (robusto ante reordenamientos futuros de `_POLICY_CHAINS`): estrictamente más privado, nunca menos, jamás escala a la nube. Un despacho `soberano` (todo local) queda local en ambos niveles. El alias guardado en el checkpoint solo puede ser None o mia-local → aun si el turno HITL se reanuda bajo otra política, no hay fuga. La voz (`role_prompt`, autorizada por el despacho) NO puede anular las reglas duras: L2/L3 (método/citación) van ANTES en el prompt y el bloque de voz reitera [VERIFICAR].

**Verificación 3 capas:** Capa 1 — gate nuevo `test_personas.py` **52/52** (offline: candado en las 3 políticas incl. soberano y que 'local' nunca es alias de nube; voz con guardrail y sin jerga §G; detección por frase con límite de palabra, más larga gana, deshabilitada no casa; validación de nivel/largos/dedup; build_graph_system con/sin persona == baseline. DB real: siembra idempotente que respeta el borrado, CRUD, nombre duplicado case-insensitive, tope MAX_PERSONAS, AISLAMIENTO RLS B→A en ver/editar/borrar, resolve_for_turn por frase/id/deshabilitada, build_assistant_system con/sin persona); regresión **ALL PASS 55 suites** ×2 (test_rls 12/12 HALT). Dos dobles de test (`test_document_pipeline`, `test_untrusted_content`) se actualizaron para reflejar la firma real de `_llm` (nuevo kwarg `model=`) — el doble faithful, no debilitar el test. Sin frontend web → sin npm build. Capa 2 (revisor adversarial independiente, contexto fresco): **los 7 invariantes SE SOSTIENEN** (candado de motor por construcción, RLS, la voz no anula la citación, fail-open, comportamiento sin cambios, recursos/concurrencia con ON CONFLICT en la siembra, logs sin fuga). **Sin bloqueantes ni mayores.** 2 MENORES + 1 NOTA corregidos y re-verificados ANTES del commit: (MENOR) `chat()` del asistente resolvía la persona FUERA de try/except → asimetría con stream → envuelto en fail-open; (MENOR) el system del asistente no incluía L3 (citación) — no era regresión de CP-E3 (baseline preexistente) pero ampliaba la superficie ante un role_prompt hostil → **añadida L3 al `build_assistant_system`** para que la regla dura anteceda a la voz; (NOTA) `resolve_persona_alias('local')` devolvía `chain[-1]` (fiaba de la posición) → cambiado a devolver `LOCAL_ALIAS` por construcción (fail-closed puro ante reordenamientos futuros). Riesgo #50 registrado. **Commit en rama `feat/cp-e3-personas-juridicas`; merge+push a main PENDIENTE de aprobación de Pipe.** A/B en vivo NO ejecutado (CP-E3 es byte-idéntico sin invocación explícita; la voz solo aplica cuando el abogado la nombra — se ofreció a Pipe un A/B persona-on/off si quiere evaluar la calidad de las voces antes de confiar en ellas). Deuda de árbol evitada: `frontend/app/dashboard/page.tsx` (control de tope de CP-E1 de Cursor) sigue sin commitear — NO se mezcló con CP-E3.


## 2026-07-03 — Sesión 32 (cont.) · CP-E4: banco de pruebas de calidad (eval harness · Ola 5)

**Qué se construyó (ref Hermes `batch_runner.py` + `trajectory_compressor.py`, traído al grafo de asunto de Mia):** paquete nuevo `backend/mia/eval/` que corre a Mia sobre CASOS DE ORO SINTÉTICOS por el grafo completo (headless, sin HTTP) y mide señales OBJETIVAS de calidad SIN LLM-juez (determinista = anti-invención, imprescindible en lo legal), para decir si un cambio mejora/empeora la calidad ANTES de mergear. Piezas: `cases.py` (3 casos sintéticos — caducidad/prescripción/excepción de contrato; cada uno con `synthetic=True`, mensaje, documentos y perfil; hechos y partes inventados, cero datos reales), `scoring.py::score_turn` (función PURA: disciplina de citas del INFORME del verificador de CP9 —`anotadas`=citas que el redactor dejó sin marca ni respaldo—, cierre del diagnóstico vía `parse_diagnosis_closing`, borrador alcanzado/vacío/minúsculo, tokens/latencia informativos; flags + `ok`), `compare.py::compare_reports` (ANTES/DESPUÉS por caso + veredicto agregado FAIL-SAFE: una regresión manda sobre cualquier mejora; regresión = suben citas sin respaldo / se pierde el cierre / deja de producir borrador / borrador encogido a <mitad), `harness.py` (runner headless: `initial_state`→`build_matter_graph`→`astream` hasta el interrupt de HITL→`aget_state().values` da borrador+informe; `_seed_case_matter` siembra el asunto CON embeddings; `read_eval_policy` candado de datos reales fail-closed; `run_suite`+`build_report`+`persist_report` a `mia-data/eval-runs/{run_id}/`). CLI `execution/run_eval.py` (crea despacho efímero, corre la suite en vivo, persiste, `--compare ANTES DESPUES`; limpia tenant+checkpoints). **CANDADO DE DATOS REALES (regla dura de Pipe):** un caso NO sintético SOLO corre si el despacho autorizó `tenant_settings.config['eval']['allow_eval_real_data']` (default False, fail-closed, evaluado ANTES de sembrar/correr) → si no, `EvalConsentError`. En v1 no existe ningún camino que lea expedientes REALES del despacho: los casos traen sus propios documentos sintéticos inline. Sin migración ni tabla (corridas sintéticas → JSONL en disco basta, sin RLS). Sin tocar el core (solo añade `mia/eval/`).

**Verificación 3 capas:** Capa 1 — gate nuevo `test_eval_harness.py` **25/25** (offline: scorer —cita sin marca→sin_respaldo+flag, cita con [VERIFICAR]→marcada, borrador vacío/minúsculo, cierre—; comparador —4 tipos de regresión, mejora, fail-safe regresión+mejora→REGRESIÓN—; casos todos sintéticos; build/persist a tempdir. DB real con LLM/embeddings stubbeados: política fail-closed, candado NO-sintético→EvalConsentError, END-TO-END por el grafo real —siembra, corre hasta HITL, intake RECUPERA el documento sembrado, puntúa el borrador real con cita sin respaldo—); regresión **ALL PASS 56 suites** ×2 (test_rls HALT). Sin frontend → sin npm build. **Capa 2 (revisor adversarial independiente, contexto fresco): candado de datos reales y determinismo de métricas CONFIRMADOS por código.** 1 MAYOR corregido y RE-VERIFICADO ANTES del commit: (M1) `_seed_case_matter` sembraba los chunks SIN embedding, pero `matter_has_chunks`/`retrieve_rrf` filtran `embedding IS NOT NULL` → en una corrida en vivo intake devolvía `documents:[]` y Mia redactaba A CIEGAS (el banco NO ejercitaba la recuperación del expediente; el gate no lo veía porque los embeddings estaban stubbeados y el borrador era fabricado) → ahora se siembran embeddings como producción (`routes/ux.py`) y el gate exige `documents_retrieved>=1`. 2 MENORES aceptados (Riesgo #51): (m1) tenants `[eval]` huérfanos si el proceso se mata con Ctrl-C a mitad (solo datos sintéticos; el camino normal limpia en `finally` con cascada); (m2) la marca `[VERIFICAR]` ANTEPUESTA no la detecta el escáner de CP9 (heredado; el estilo de la casa la pone después; podría inflar una regresión falsa si el modelo cambiara de estilo). **Capa 3: NO APLICA (herramienta de dev/admin por CLI, sin frontend).** Riesgo #51. **Commit en rama `feat/cp-e4-eval-harness`; merge+push a main PENDIENTE de aprobación de Pipe.** La rama trae además la consolidación del trabajo de frontend pendiente para Cursor en HANDOFF.md (índice priorizado). Deuda de árbol evitada: `frontend/app/dashboard/page.tsx` (control de tope CP-E1 de Cursor) sigue sin commitear, NO mezclado.

## 2026-07-04 — Sesión 33 · CP-E5: delegación multi-agente + tablero de misión por expediente (Ola 5)

**Qué se construyó (dos entregables; ref Hermes `tools/delegate_tool.py` + `hermes_cli/kanban*` swarm/decompose, ClaudeOS Missions como inspiración de UI; se ELEVARON las costuras existentes en vez de partir de cero):**

**(B) Investigación DELEGADA en paralelo (elevación de `research_node`).** Antes: `research.gather_sources` hacía UNA búsqueda SAT-Graph con TODAS las jurisdicciones como filtro + UN investigador LLM. Ahora, patrón swarm (raíz→workers→verificador→sintetizador): módulo nuevo `agents/delegation.py::run_parallel` (primitiva PURA de concurrencia: `asyncio.Semaphore` acota simultaneidad, FAIL-SOFT por subtarea que nunca propaga, orden ESTABLE por posición, tope duro `MAX_WORKERS=8`). `research_node` bifurca: `resolve_jurisdictions_for` (nuevo wrapper fail-soft + DEDUP preservando orden); con **1 jurisdicción → `_research_single`** (byte-idéntico a antes de CP-E5, cero costo/comportamiento extra — es el caso de Lexia); con **≥2 → `_research_swarm`**: un investigador LLM POR jurisdicción en paralelo (fuentes acotadas a esa jurisdicción + verificación determinista de citas POR RAMA vía `verification.annotate_draft`) + un SINTETIZADOR que consolida las memorias verificadas. `research.gather_sources` ganó `jurisdictions=` opcional. Metadata trae `research_delegation:{workers, jurisdictions}` (transparencia). Fail-soft: si TODOS los workers fallan → cae a `_research_single` (md limpio, sin doble síntesis). Costo: metido por el hook de `call_llm` (turn_usage); además guarda de tope (ver capa 2).

**(A) Tablero de misión por expediente.** Migración `024_missions.sql` (`missions` + `mission_milestones`, RLS fail-closed ENABLE+FORCE, GRANT a mia_app; **SIN columna de fecha** — regla dura: Mia nunca calcula plazos). `execution/init_missions.py`. Paquete `backend/mia/missions/`: `decompose.py` (descompone un objetivo en hitos vía LLM auxiliar barato `task='mission_decompose'` —respeta política del despacho, en soberano local— con GUARDAS DETERMINISTAS: `_PROCEDURAL_RE` marca `is_procedural` aunque el modelo no lo diga —fail-closed sobre "nunca plazos"—, prompt prohíbe fechas, anti-invención con plantilla genérica fail-soft, tope MAX_MILESTONES), `service.py` (`MissionService` CRUD bajo `pool.tenant_connection`; verifica PROPIEDAD del expediente vía `_matter_context` bajo RLS —cierra el hueco del FK que no filtra por tenant—; topes MAX_MISSIONS_PER_MATTER/MAX_MILESTONES_PER_MISSION; consent-first: la descomposición PROPONE hitos 'queued' editables, nada se auto-ejecuta). Router `api/routes/missions.py` (9 endpoints bajo `/api/missions`, patrón de personas: `request.state.tenant_id`, 422 validación/404/502 en llano §G) + registro en `api/main.py`. Tarea `mission_decompose` añadida a `_AUX_TASKS` y `_TASK_FALLBACK_CHAINS` en `agent/llm.py`.

**Verificación 3 capas:** Capa 1 — 3 gates nuevos: `test_delegation.py` **11/11** (orden estable, fail-soft, concurrencia acotada real, tope duro, saturación), `test_missions.py` **40/40** (guardas de descomposición incl. fuerza-procesal; CRUD e hitos; topes; PROPIEDAD del expediente ajeno→MissionError; AISLAMIENTO B↛A completo; parseo JSON tolerante; fail-soft del modelo→plantilla), `test_research_swarm.py` **21/21** (1-juris=simple sin costo extra; 2-juris=workers+verificación por rama+síntesis; usage acumulado en serie; md aislado por worker; fail-soft total→simple; **M1** shrink por worker; **m4** degradación por tope; **m1** dedup). Regresión **ALL PASS (59 suites)** ×2 con `test_rls` HALT. Un fix de compat: `test_document_pipeline.py` stub `fake_gather` firma nueva `jurisdictions=`. **Capa 2 (revisor adversarial independiente, contexto fresco):** confirmó CORRECTOS RLS/aislamiento, regla de plazos (sin columna de fecha + guarda fail-closed), §G, fail-soft, concurrencia de usage (Lock en `usage.record`), SQL parametrizado, TOCTOU de `create_mission` cerrado (re-valida propiedad en la 2ª conexión). **1 MAYOR + 2 MENORES corregidos y RE-VERIFICADOS ANTES del commit** (veredicto del revisor: "M1/m1/m4 CERRADO; sin motivo para bloquear el commit"): (M1) carrera sobre `self._compressor` compartido —stateful— entre workers paralelos → ahora cada worker pasa su propio `shrink` a `_llm`, que así jamás alcanza el compresor; (m1) `resolve_jurisdictions_for` no deduplicaba → workers/costo duplicados con config sucia → dedup; (m4) el swarm amplifica el costo de un turno ya admitido por el tope de entrada → `_research_swarm` consulta `budget_status` y si el despacho ya superó el tope degrada al camino simple (fail-open). 2 residuales aceptados (Riesgo #52): (m2) colisión silenciosa de `seq` de hitos —orden determinista por desempate, UNIQUE complicaría reordenar—; (m3) `matter_id` en `to_public` —vínculo que el frontend necesita, no jerga §G, no filtra tenant—. **Capa 3: PENDIENTE de Cursor** (tablero de misión; endpoints en HANDOFF §CP-E5). A/B: la investigación en paralelo es INERTE para Lexia (mono-jurisdicción); `docs/comparacion-cpe5.md` explica ANTES/DESPUÉS y por qué no hay corrida en vivo (falta corpus de 2ª jurisdicción). **Commits en rama `feat/cp-e5-delegacion-mision`; merge+push a main PENDIENTE de aprobación de Pipe.** Deuda de árbol evitada: `frontend/app/dashboard/page.tsx` (WIP de tope CP-E1 de Cursor) sigue SIN commitear, NO mezclado.


## 2026-07-08 — Sesión 35 (retomada de sesión trabada) · Frentes B/C + Data Factory del corpus + bugfix FTS

**Contexto:** al iniciar esta sesión ("retoma que te trabaste") el repo tenía ~5h de trabajo de una
sesión previa sin commitear, sin entrada de progreso y sin HANDOFF actualizado (nunca corrió /cierre).
Reconstruido por lectura de código (nada de TODOs/FIXME, sin rastro en memoria): 3 hilos paralelos +
un bugfix suelto.

**Bugfix — `agents/research.py`:** la consulta FTS de investigación mandaba el mensaje completo del
abogado a `websearch_to_tsquery` (exige TODOS los términos) → casi siempre 0 resultados del corpus.
`build_fts_query` nuevo: citas exactas entre comillas + términos clave (sin stopwords) unidos con OR.
Gate nuevo `test_research_query.py` 11/11; `test_document_pipeline.py` actualizado (cp9-14).

**Frente B (aprendizaje):** B1 — el motivo textual del rechazo del abogado viaja en la traza
(`graph.py`, `trace_capture.py: rejection_reason`) y alimenta al `feedback_processor` al redactar
propuestas. B2 — `POST /api/learning/run` (routes/learning.py) dispara el aprendizaje manualmente;
botón "Revisar ahora" en `memoria/page.tsx`. B4 — aprobar una `wiki_correction` ya la APLICA de verdad
(appendea al archivo del concepto vía `WikiManager.append_correction`; antes solo quedaba registrada).

**Fase 3 · frente C (bóveda visible) + Data Factory del corpus:** `rag/corpus_factory.py` reemplaza la
semilla hardcodeada de `ingest_corpus.py` (deprecado, queda solo como fixture de `test_sat_graph`) por
ingesta declarativa desde `jurisdiction/packs/{jur}/corpus_sources.json` (hoy solo "co"): motor único +
adaptadores por portal (Función Pública, SUIN-Juriscol, Corte Constitucional), validación de identidad
fail-closed, segmentación de normas grandes, gate de ToS. **El motor no tiene a Colombia hardcodeada —
la jurisdicción la pone el pack** (pedido explícito de Pipe, ver [[mia-decisiones-pipe-fase3]]:
"nutrir la jurisdicción QUE APLIQUE" a cada abogado, no solo Colombia). `connectors/vault_export.py`
hace el backfill al vault de Obsidian: playbooks activos → `Mia/procedimientos/`, fichas cortas (nunca
el texto completo) de normas/jurisprudencia del Data Factory → `Mia/corpus/{normativa,jurisprudencia}/`.

**docs/analisis-claude-for-legal.md** (aparte, no tocó código): ingeniería inversa del plugin
marketplace "Claude for Legal" de Anthropic — confirma la arquitectura de MIA y deja 5 quick wins
identificados, pendientes de aplicar.

**Verificación 3 capas — capa 1:** regresión completa 66/66 suites verdes (dos corridas, antes y
después de las correcciones de capa 2; `test_rls` y `check_env_pins` HALT intactos). **Capa 2 (revisor
adversarial independiente, workflow multi-agente, contexto fresco):** 5 hallazgos CONFIRMADOS, los 5
corregidos y RE-VERIFICADOS (regresión completa otra vez en verde) ANTES de commitear:
1. `vault_writer.export_playbook`: dos playbooks activos cuyo título difiere solo en acentos/mayúsculas
   colapsaban al MISMO slug y se sobreescribían en silencio → `VaultWriter._dedupe_slug` desambigua
   colisiones por corrida de exportación (sufijo `-2`, `-3`…), con log de advertencia.
2. `ux.py` `wiki_correction`: el nombre del concepto vivía codificado como prefijo de texto libre
   dentro de `rationale` — un cambio de prefijo o edición del rationale rompía el parseo EN SILENCIO y
   la corrección aprobada quedaba "applied" sin efecto → columna dedicada `target_concept` (migración
   `026_feedback_proposal_target_concept.sql`, `init_feedback_target_concept.py`), mismo criterio que
   `target_playbook_id`; el parseo viejo queda solo como fallback de lectura.
3. `apply_proposal` sostenía la conexión pooled del tenant durante la escritura de disco (bloqueante,
   vault posiblemente en OneDrive) → riesgo de agotar el pool bajo aprobaciones concurrentes → el
   archivo se escribe FUERA de la conexión; "applied" se marca en una conexión corta aparte.
4. `corpus_factory.py`: validación de identidad fail-closed duplicada letra por letra entre
   FuncionPublicaAdapter y SuinJuriscolAdapter (una corrección futura aplicada a uno y olvidada en el
   otro dejaría esa fuente con una garantía distinta) → extraída a `_identity_confirmed`/
   `_build_norm_record` compartidos.
5. `vault_export.export_corpus_fichas`: dos lecturas de DB independientes en secuencia → paralelas
   (`asyncio.gather`), la mitad de latencia.

**Capa 3 (visual):** PENDIENTE — sin navegador conectado en esta sesión (extensión Chrome no
disponible); el único cambio visual es el botón "Revisar ahora" en `memoria/page.tsx`, cubierto por
`npm run build` verde + el test de API que ejercita el mismo endpoint.

**4 commits en `main`** (sin push): `9f62b4e` (bugfix FTS), `4ea4126` (frente B), `cb32ebb` (frente C +
Data Factory), `00728c8` (docs análisis Claude for Legal).

**Pendiente para la próxima sesión:** capa 3 en vivo del botón "Revisar ahora"; Gmail/OneDrive vía
Graph API (bloque 2 de [[mia-decisiones-pipe-fase3]], aún no arrancado); aplicar los 5 quick wins de
`docs/analisis-claude-for-legal.md`; decidir si se hace push a origin/main.


## 2026-07-08 — Sesión 35 (cont.) · 3 quick wins de docs/analisis-claude-for-legal.md

Tras el push de los 4 commits anteriores, se aplicaron 3 de los 5 quick wins identificados en
`docs/analisis-claude-for-legal.md` (los otros 2: #2 resultó YA IMPLEMENTADO en
`CitationReview.tsx`; #5 queda pendiente de aprobación de Pipe por tocar el gate de HITL).

- **#1 (3er valor, flag-but-don't-use):** `GRAPH_NODE_INSTRUCTIONS["draft"]` — el especialista de
  borrador avisa expresamente en el escrito si sospecha una norma derogada/modulada sin poder
  confirmarlo, sin bloquear el borrador.
- **#4 (decision tree + pregunta de segundo orden):** `GRAPH_NODE_INSTRUCTIONS["analysis"]` — cierra
  cada diagnóstico con un menú de 2-5 caminos + una pregunta de segundo orden. Documentado en
  `architecture/hitl_flow.md` §7.
- **#3 (freshness declarativo por archivo del pack):** `JurisdictionPack.freshness` + `is_stale()`
  en `jurisdiction/pack.py`, alimentado desde `packs/co/meta.json → "freshness"`. Aditivo, sin
  conectar a ningún resolver/consumidor todavía.

**Capa 2 (revisor adversarial independiente):** 3 hallazgos, los 3 corregidos antes del commit:
(1) el menú de próximos pasos se había puesto DESPUÉS del bloque de cierre estructurado — bajo
`context_recovery.shrink_text(..., protect_tail=True)` eso arriesgaba proteger el menú y cortar el
riesgo/recomendación real; se movió ANTES del bloque (el cierre estructurado vuelve a ser lo último
que emite el especialista). (2) `load_pack()` no validaba que el "freshness" de nivel superior en
meta.json fuera un dict → `is_stale()` podía tumbarse con `AttributeError` pese al fail-soft
documentado; ahora se descarta si no es dict. (3) la nota `_nota` vivía dentro del objeto
`freshness` (mismo namespace que las entradas reales) → movida a `_freshness_note` a nivel de
`meta.json`, mismo patrón que el `_note` del resto de archivos del pack.

Capa 1: regresión completa 66/66 verdes (antes y después de las correcciones). Commit `c11fb71`,
pusheado a `origin/main`.


## 2026-07-08/09 — Sesión 36 · Fuentes remotas del expediente: Gmail + OneDrive vía Graph API (bloque 2 de la Fase 3)

**Qué se construyó:** bloque 2 de la Fase 3 (pendiente desde la sesión 35), COMPLETO en 4 fases +
correcciones. 5 commits en `main` (sin push aún): `7ccab33`, `8c2c28a`, `a84088a`, `b989e39`, `c9f2a32`.

**Fase 1 (`7ccab33`) — cimientos OAuth multi-proveedor:** `tenant_oauth_tokens` con PK
`(tenant_id, provider)` — un despacho puede tener Microsoft Y Google conectados a la vez; migración
`027_remote_sources.sql` (+ `remote_drive_sources`, `remote_file_hashes`, RLS FORCE; `documents.origin`
gana los valores `'mail'`/`'drive'`). `oauth.py` con features por proveedor (mail / mail_content /
drive vía `Files.Read`). `GET /api/mailbox/status` reporta por proveedor. El motor de vigilancia ya
observa ambos proveedores (claves de debounce `provider:external_id`). `execution/init_remote_sources.py`
corre la migración. Gate nuevo `test_mailbox_multi.py` **21/21**.

**Fase 2 (`8c2c28a`) — correos del caso se traen al expediente:** `search_messages`/`fetch_meta`/
`fetch_attachments` en ambos proveedores. Rutas nuevas `api/routes/matter_mail.py`:
`GET /api/matters/{id}/mail/search?q=&provider=` y `POST /api/matters/{id}/mail/link` (máx 20 por
lote, respuesta en llano `{added, skipped, already}`). El cuerpo del correo se convierte en documento
`correo-AAAA-MM-DD-<asunto>.txt` con encabezado De/Fecha/Asunto; los adjuntos pdf/docx/txt/md se
convierten en documentos `origin='mail'` con dedupe por sha256; lo no soportado o >20MB se reporta
como `skipped` sin fingir que se trajo. El **consentimiento es la acción explícita del abogado** de
buscar+vincular (no depende del opt-in de vigilancia del correo). Auditoría CP-E1 registra solo
metadatos. Gate `test_mail_to_matter.py` **24/24**.

**Fase 3 (`a84088a`) — OneDrive remoto SELECTIVO de solo lectura:** `connectors/graph_drive.py`
(cliente Graph con cliente HTTP inyectable + `RemoteDriveSync`, calcado del patrón de
`local_folder_sources`: sync incremental por eTag→sha256, tope de 20MB comprobado ANTES de descargar,
fail-soft por archivo — un archivo roto no tumba la corrida). Rutas `api/routes/remote_drive.py`:
navegar carpetas, CRUD de fuentes, sincronizar (con candado + throttle de 60s). El contenido va a
`knowledge_chunks` o a `documents` con `origin='drive'` según corresponda. Tope de 20 fuentes por
despacho. Gate `test_remote_drive.py` (31 → **35/35** tras las correcciones de capa 2).

**Fase 4 (`b989e39`) — UI:** `OneDriveFolderPicker` (navegador modal de carpetas con breadcrumb, la
raíz nunca es elegible directamente), `OneDriveSourcesSection` (Panel de control, sección "Carpetas
en la nube (OneDrive)"), `MatterDriveFolder` (vincular una carpeta OneDrive al asunto en curso),
`MailSearchDialog` ("Traer correos del caso": buscar, marcar con checkbox, añadir N, resumen
added/skipped/already en llano), `MailboxSection` con una tarjeta por proveedor conectado +
checkbox "Incluir mis archivos de OneDrive". Registrar una carpeta dispara su primera sincronización
automáticamente.

**Verificación 3 capas:**
- **Capa 1:** regresión completa **69/69 suites ALL PASS** (dos corridas, antes y después de las
  correcciones de capa 2) — `test_rls` 12/12 y `check_env_pins` 9/9 (HALT) intactos; `npm run build`
  verde. La línea base sube de 66 a 69 suites. Nota de corrección de tally: `test_setup_wizard` es
  **28/28** (el "30/30" que quedó anotado en el HANDOFF de sesiones previas correspondía a otra
  versión del script, no a la actual).
- **Capa 2 — dos revisores adversariales independientes (contexto fresco, Opus):**
  - **Revisor de seguridad: APROBADO sin bloqueantes ni mayores.** RLS confirmado en las 3 tablas
    nuevas, `state` de OAuth con nonce + cookie (anti-CSRF), ningún camino de fuga de tokens o
    contenido entre despachos, SQL parametrizado en toda la superficie nueva, límites (20 correos por
    lote, 20MB por archivo, 20 fuentes por despacho) todos verificados con evidencia de código.
  - **Revisor de corrección: 3 MAYORES + 6 MENORES — TODOS aplicados en el commit `c9f2a32`, ninguno
    descartado:**
    - **M1** — renombrar un archivo en OneDrive lo BORRABA del expediente (la sync lo veía como
      archivo nuevo + archivo desaparecido) → ahora se persiste `rel_path` y `_move_content` mueve el
      contenido existente en vez de borrar+recrear; gate con caso de rename dedicado.
    - **M2** — la UI no esperaba a que la sincronización terminara antes de refrescar → ahora sondea
      hasta que termina y refresca la lista de documentos.
    - **M3** — no existía forma de agregar el permiso de archivos a una cuenta Microsoft YA conectada
      solo para correo → botón nuevo "Añadir permiso de archivos"; `status` expone `archivos: bool`
      por proveedor.
    - **m1** — un fallo al vincular UN correo tumbaba el lote completo → ahora ese correo se reporta
      `skipped` y el resto del lote sigue.
    - **m2** — `last_synced_at` no se actualizaba por fuente individual → el throttle y "Última
      revisión" fallaban con una carpeta vacía; corregido por-fuente.
    - **m4** — el botón "Cerrar" del diálogo de correos no reseteaba su estado interno.
    - **m5** — un uuid malformado en la URL reventaba con 500 → ahora 404 en llano.
    - **m6** — el cálculo de embeddings corría DENTRO de la conexión pooled del tenant (bloqueante) →
      movido fuera de la conexión.
    - **SEC-1** — los ids en URLs de Graph/Gmail no pasaban por `quote(safe='')` → ahora sí.
    - **SEC-2** — los scopes base de Microsoft (`offline_access openid email`) no estaban garantizados
      en toda solicitud OAuth → ahora siempre se incluyen.

**Deudas/riesgos NUEVOS (detalle completo en `memory/bugs-and-risks.md`, Riesgo #54):**
1. No existe sincronización PROGRAMADA de fuentes OneDrive (solo el botón manual); archivos diferidos
   (>2000 por corrida) o con error solo se retoman con un clic. Deuda consciente.
2. `[VERIFICAR]` endpoints/scopes reales de Graph/Gmail — los gates doblan el HTTP; confirmar al
   conectar la primera cuenta real (mismo criterio que el mailbox de la Ola 2).
3. Renombrar un archivo a una ruta ya ocupada por otro archivo (colisión en `knowledge_chunks`) podría
   perder el archivo hasta el próximo cambio de contenido — caso rarísimo, auto-sanable.
4. Tras el deploy de este bloque, avisos de correo/calendario ya notificados podrían repetirse UNA vez
   (cambio de formato de las claves de debounce de vigilancia). Nunca en silencio.
5. Los candados/throttle de sincronización viven en memoria del proceso (Modo B single-worker está
   bien; revisar si algún día hay multi-worker).
6. **Nota de negocio para Pipe:** Microsoft no tiene un scope de "solo metadatos" — `Mail.Read` siempre
   permite leer cuerpos de correo; Mia solo los usa cuando el abogado lo pide explícitamente, pero el
   permiso técnico existe desde el momento en que se conecta la cuenta.

**Pendiente para la próxima sesión:**
- **Capa 3 EN VIVO de Pipe/Cursor** (no hubo navegador conectado en esta sesión): (1) conectar
  Microsoft con "Incluir mis archivos de OneDrive" y verificar el flujo real de consentimiento;
  (2) navegar 2-3 niveles de carpetas y elegir una; (3) probar el 503 sin conexión configurada y el
  botón "Añadir permiso de archivos"; (4) buscar y vincular 2-3 correos reales y verlos aparecer en
  documentos del asunto; (5) responsive de los dos modales nuevos. También sigue pendiente la capa 3
  del botón "Revisar ahora" (deuda de la sesión 35).
- **ACCIÓN DE PIPE:** registrar las apps OAuth (Azure AD y Google Cloud) y poner las llaves en `.env`
  (`MS_OAUTH_CLIENT_ID/SECRET`, `GOOGLE_OAUTH_CLIENT_ID/SECRET`) — hasta entonces todo responde 503 en
  llano (activación diferida, por diseño; mismo patrón que Microsoft 365/Google de la Ola 2).
- Quick win #5 (checklist de pre-entrega en el gate de aprobación) sigue esperando aprobación de Pipe.
- Deuda #1 de arriba (sincronización programada de OneDrive).

---

## 2026-07-09 — Sesión 37 — OCR local para PDFs escaneados (bloque 3a) + sincronización programada de OneDrive (bloque 3b)

**Nota de continuidad:** la sesión se interrumpió por un corte de luz justo después del último
commit (`315dbd1`, 10:25). No se perdió código (working tree limpio). Este cierre se completó en
la sesión de retoma del mismo día: se corrió la regresión completa que faltaba y se escribió
esta memoria + HANDOFF.

**Qué se construyó (4 commits en `main`: `ad16a64` → `315dbd1`):**

1. **Bloque 3a — OCR local para PDFs escaneados (`ad16a64`).** En litigio la mayoría de
   expedientes son PDF escaneados sin capa de texto; antes Mia quedaba ciega SIN AVISAR.
   - `ingest/ocr.py`: motor rapidocr-onnxruntime (PaddleOCR sobre ONNX, CPU, 100% local — el
     documento nunca sale del servidor). Singleton perezoso; degrada a None si falta la librería.
   - `ingest/extract.py`: fallback página a página (detecta escaneadas: <40 alfanuméricos +
     imágenes; rasteriza a 220 dpi gris); PDFs mixtos EN ORDEN; aviso de lectura óptica; tope
     150 páginas / 10 min con corte anotado; página corrupta no tumba el documento. Nueva
     `extract_text_detailed(...)` → `(str, meta)` con `{ocr_pages, total_pages, truncated}`.
   - Pin `rapidocr-onnxruntime~=1.4` (grupo `~=`, fuera de los pins críticos del Riesgo #32).
   - OCR real verificado en español jurídico: lee verbatim a calidad de escaneo normal.
2. **Bloque 3b — sincronización programada de OneDrive remoto (`10788c2`).** Cierra la deuda #1
   del Riesgo #54: job del scheduler cada 6h (misma cadencia que Obsidian) que recorre los
   tenants con fuentes habilitadas; `sync_tenant_sources()` con throttle propio (1h) y fail-soft
   por fuente; lock `SYNCS_IN_FLIGHT` compartido entre el cron y el botón manual.
3. **Capa 2 — revisión adversarial del bloque, TODOS los hallazgos corregidos (`ea28423`):**
   - **M1** — el OCR congelaba el event loop → variantes async con `asyncio.to_thread` en los 5
     call sites (ux, matter_mail, graph_drive, local_folders); el lock sigue SOLO en el event loop.
   - **M2** — rasterización acotada por dimensiones: si el área a 220 dpi supera 25 Mpx se baja
     el dpi (piso 72); si ni así cabe, la página se salta con anotación honesta (evita pixmaps
     de gigabytes por MediaBox descomunal).
   - **M3** — "solo nota, sin cuerpo" ya no entra como documento válido: `has_body` +
     `ocr_unavailable` en el meta; upload → 422 en llano; adjunto de correo / graph_drive → skipped.
   - **MEN1** — marcador de honestidad POR SEGMENTO (el troceo arrastra la nota cerca del
     contenido óptico); **MEN2** — el OCR CONCATENA con la capa de texto legítima, no la pisa;
     **MEN3** — gate de no-egress (parchea socket: el OCR real no hace NINGUNA llamada de red);
     **MEN4** — sin round-trip redundante a la DB por fuente en el cron.
4. **Cierre de deuda (`315dbd1`):** la guarda M3 replicada en `connectors/local_folders.py`
   (ambos destinos: expediente `origin='folder'` y `knowledge_chunks`); el archivo ciego queda
   `omitted` SIN hash → se reintenta solo cuando se instale la lectura óptica.

**Verificación 3 capas:**
- **Capa 1 (corrida en la retoma, post-apagón): regresión completa 70/70 suites ALL PASS** —
  `test_rls` 12/12 y `check_env_pins` 9/9 (HALT) intactos. La línea base sube de 69 a 70 suites
  (se suma `test_ocr_ingest` 26/26). Sin frontend tocado → sin `npm run build` (los 4 commits son
  backend + tests puros). Nota de tally: `test_speech_tts` reporta **24/24** en el script actual
  (el 26/26 de líneas base anteriores era de otra versión del script; exit 0, PASS).
- **Capa 2:** corrida DURANTE la sesión interrumpida (revisor adversarial con contexto fresco);
  3 mayores + 4 menores, TODOS corregidos y re-verificados en `ea28423`/`315dbd1` — ninguno
  descartado.
- **Capa 3: NO APLICA** — sin UI nueva (el abogado no ve pantallas nuevas; ve que Mia ya no queda
  ciega ante PDFs escaneados y que sus carpetas de OneDrive se mantienen al día solas).

**Deudas/riesgos nuevos:** ver `bugs-and-risks.md` Riesgo #55.

**Pendiente para la próxima sesión:** sin cambios respecto a la sesión 36 (capa 3 en vivo de
Pipe/Cursor; ACCIÓN DE PIPE: llaves OAuth en `.env`; quick win #5 esperando aprobación) + decidir
si se hace push de los 4 commits de esta sesión (la sesión 36 ya está en `origin/main`).

## 2026-07-09 — Sesión 39 — Bloque A del plan de evolución de producto COMPLETO (Proyectos + carpetas sin fricción)

**Contexto:** plan de evolución de producto (Bloques A/B/C) aprobado por Pipe en
`memory/plan-evolucion-producto.md` tras el feedback "Mia necesita evolucionar a un espacio de
trabajo estilo Claude Cowork/ChatGPT Work". Autorización expresa de orquestación multi-agente
dada por Pipe en el HANDOFF de la sesión 38. Esta sesión ejecutó el Bloque A completo (A0-A4);
todo vive en el working tree y se commitea hoy.

**Qué se construyó (por pieza):**
1. **A0 — Migración de cimientos (`028_projects_multifolder.sql` +
   `execution/init_projects_multifolder.py`):** `matters.kind` (`'asunto'|'proyecto'`, CHECK +
   índice); `documents.source_id` (procedencia por fuente, sin FK dura); `documents.body` (texto
   íntegro de archivos producidos por Mia — los chunks con overlap no se pueden reconstruir para
   el .docx); `ck_documents_origin` gana `'mia'`. Backfill conservador: `source_id` solo se asigna
   cuando el expediente tiene EXACTAMENTE UNA fuente (`HAVING count(*)=1`) — los ambiguos quedan
   `NULL` y `NULL` jamás se poda. Espejo del backfill para `origin='drive'`. Trampa descubierta:
   Postgres no tiene `min()`/`max()` para `uuid` → `(array_agg(id))[1]`.
2. **A2 — Fix del bug latente de poda cruzada (`local_folders.py`):** `_ingest_matter_file` y
   `_prune_matter_docs` ahora acotan por `source_id`; `sync_source` lo pasa. Superficie plural en
   `matter_folders.py`: `GET/POST /api/matters/{id}/folders`, `POST .../folders/{sid}/sync`,
   `DELETE .../folders/{sid}`, tope 10 carpetas (422); endpoints singulares `/folder` quedan como
   wrappers deprecados SIN el 409 de una-sola-carpeta. `get_matter_sources()` plural
   (`get_matter_source()` wrapper deprecado).
3. **A1 — Navegador seguro de carpetas:** `safe_browse_roots()` + `browse_folder()` (fail-closed:
   `resolve`, `_FORBIDDEN_PARTS`, sin symlinks, tope 500+`truncated`) + `GET /api/folders/browse`
   (deshabilitable con `MIA_DISABLE_FOLDER_BROWSE` → 503). Frontend `FolderPicker.tsx` (clon del
   `OneDriveFolderPicker`) reemplazó los 3 inputs de ruta pegada a mano (`CarpetasSection`, diálogo
   del asunto, vault Obsidian en `ConexionesSection`).
4. **A3 — Fuentes unificadas:** `backend/mia/api/routes/matter_sources.py`
   (`GET /api/matters/{id}/sources` — carpetas + OneDrive + correo, estados EN LLANO, fail-soft si
   Graph revienta) + frontend `FuentesPanel.tsx` (panel autocontenido con "+ Conectar fuente":
   carpeta del equipo / OneDrive / correos) que absorbió en `asuntos/[id]/page.tsx` el bloque de
   carpeta, `MatterDriveFolder` (quedó sin uso, no borrado) y el botón de correos.
5. **A4 — Pestaña "Proyectos":** `MatterCreate.kind`, `GET /api/matters?kind=` (default solo
   `'asunto'` por compatibilidad; `'proyecto'`; `'todos'`), outputs (`POST/GET
   /api/matters/{id}/outputs` `origin='mia'` con dedupe sha256 + `GET .../outputs/{doc}.docx`),
   instrucción de nodo `"work"` en `prompt_builder`, `build_project_graph()` (intake→work→END, sin
   HITL — un proyecto NO tiene borrador/aprobación por diseño; el guardado de outputs es acción
   explícita del abogado), `stream.py` decide por `kind` (eventos `thinking`/`reply`), nav
   "Proyectos" (FolderKanban), `proyectos/page.tsx` (lista + creación 2 pasos) y
   `proyectos/[id]/page.tsx` (3 columnas: Fuentes · chat · Archivos del proyecto con descarga
   Word). Bugfix colateral: `Content-Disposition` con títulos acentuados crasheaba (`isalnum()`
   Unicode → `isascii()`) — bug preexistente del `draft.docx`.

**Verificación 3 capas:**
- **Capa 1:** regresión completa ALL PASS (74 suites) — línea base sube de 70 a 74 con los gates
  nuevos: `test_matter_folders_multi.py` 30/30 (incluye el caso del bug de poda cruzada,
  concurrencia sin duplicados y el backfill conservador), `test_folder_browse.py` 15/15,
  `test_projects.py` 33/33 (incluye memoria conversacional), `test_matter_sources.py` 26/26.
  `test_rls` 12/12 y `check_env_pins` 9/9 (HALT) intactos. `npm run build` verde (14 páginas,
  `/proyectos` y `/proyectos/[id]` nuevas).
- **Capa 2:** revisión adversarial multi-agente (5 revisores Opus por dimensión + verificador
  escéptico por hallazgo, contexto fresco): 12 hallazgos CONFIRMADOS, 0 descartados. TODOS
  corregidos antes del commit salvo 2 notas aceptadas:
  - **BLOQUEANTE H3:** el backfill original (`DISTINCT ON`) colapsaba el historial multi-carpeta
    de un asunto en un solo `source_id` → la poda habría borrado docs conservados de una carpeta
    desvinculada. Corregido (`HAVING count(*)=1`) + caso de gate.
  - **BLOQUEANTE H11:** la poda de OneDrive (`graph_drive.py`) seguía sin `source_id` y el
    `FuentesPanel` nuevo permite varias carpetas drive por expediente → borrado cruzado silencioso
    (incluso por el cron de 6h). Corregido en espejo (`source_id` en ingest/prune/move de
    `RemoteDriveSync`) + backfill drive + conteo por fuente en `matter_sources` + 4 checks nuevos
    en `test_remote_drive` (48/48).
  - **MAYOR H1:** `sync_tenant` (`POST /api/folders/sync` y cron) corría `sync_source` sin el
    candado `_SYNCS_IN_FLIGHT` → carrera con documentos duplicados. Corregido con
    `_SOURCE_SYNC_LOCKS` (`asyncio.Lock` por fuente) EN EL MOTOR; el set de las rutas queda como
    señal de UX.
  - **MAYOR H6:** el chat de proyecto no recordaba turnos anteriores (`prepare_new_turn` borra el
    checkpoint). Corregido: `MatterState.history`, `stream.py` recupera el historial del
    checkpoint previo (solo proyectos, últimos 6 turnos / 8000 chars) y `work_node` lo antepone
    como "Conversación reciente" sin ensuciar el retrieval del intake.
  - **MENORES corregidos:** asistente general y dashboard contaban proyectos como asuntos
    (`WHERE kind='asunto'` en `core.py` y `dashboard_stats`); endpoint legacy `GET /matters`
    filtrado; burbuja "pensando" infinita en error del chat de proyecto; doble Enter creaba dos
    proyectos; mensaje de error del `FuentesPanel` decía "asunto" en un proyecto.
  - **NOTAS aceptadas (deuda documentada):** H2 navegador de carpetas fail-open en Modo A (Riesgo
    #56, invertir default cuando exista la plantilla Docker); los correctores documentaron Riesgo
    #57.
- **Capa 3:** PENDIENTE de Pipe (recorrido en vivo).

**Deudas/riesgos:** ver `bugs-and-risks.md` Riesgo #56 (abierto, deuda de Modo A) y Riesgo #57
(RESUELTO en esta sesión — el bloqueante residual del `min(uuid)` en el backfill LOCAL de la
migración quedó corregido con `(array_agg(id))[1]`, confirmado por la regresión 74/74 ALL PASS).
Nota de límite consciente añadida: los documentos con `source_id NULL` (procedencia ambigua
pre-028) nunca se podan por sync — pueden quedar "fantasmas" si el archivo físico desaparece; se
limpian solo manualmente.

**Pendiente para la próxima sesión:** Bloque B (guías de trabajo asistidas + gobernanza de
skills, `plan-evolucion-producto.md`) + Capa 3 EN VIVO de Pipe sobre el Bloque A (Proyectos,
FolderPicker, FuentesPanel) — sin cambios respecto a la deuda de capa 3 de sesiones anteriores
(OAuth de correo/OneDrive).

---

## 2026-07-09 — Sesión 37 (continuación) — SPIKE Fase 4: distribución VIABLE

Tras el cierre y push (`b010be2`, decidido por Pipe), Pipe pidió seguir avanzando el esqueleto.
Se ejecutó el **spike aislado de la Fase 4 (distribución)** que ordenaba el plan — nada del repo
`mia` se tocó (git limpio verificado); todo vive en `../spike-fase4/` y `../spike-fase4-shell/`.

**Resultado: el camino del instalador ES VIABLE — ambas mitades probadas hoy:**
1. **Motor empaquetado (PyInstaller, agente ejecutor Sonnet):** el backend COMPLETO (FastAPI +
   LangGraph + psycopg/pgvector + litellm + onnxruntime/rapidocr + sherpa + av) corre como bundle
   onedir **sin venv ni Python instalado** — `/health` respondió `{db:true, pgvector:0.8.2}` contra
   la DB portable y el middleware JWT dio 401 correcto. Bundle 459,5 MB; build 15 min frío;
   arranque ~14 s. Flags que hicieron falta (documentados con evidencia en `spike-fase4/`):
   `--paths backend`, import explícito de `mia.api.main` en el entry (uvicorn recibe la app como
   string → invisible al análisis estático), `--collect-data litellm`, `--collect-all
   rapidocr_onnxruntime` (¡sin esto el OCR degrada a None EN SILENCIO!), `--hidden-import
   tiktoken_ext(.openai_public)`. `check_env_pins` siguió 9/9 tras instalar pyinstaller.
2. **Cáscara de escritorio (Tauri v2):** compiló a la primera en esta máquina (Rust 1.97 instalado
   hoy con perfil mínimo; VS Build Tools 2022 y WebView2 ya estaban) y produjo instaladores reales
   `setup.exe` (NSIS, 1,9 MB) y `.msi` (2,9 MB) en `spike-fase4-shell/`.

**Riesgos/decisiones que el spike dejó para la Fase 4 real (detalle en el reporte del agente y en
`C:\Users\USER\.claude\plans\CHECKPOINT-mia-transformacion.md`):**
- **R1 (diseño pendiente):** `config.py` resuelve el `.env` relativo a `__file__` → congelado apunta
  dentro del bundle. El sidecar debe recibir config por env vars desde Tauri o `config.py` debe
  detectar `sys.frozen` y leer de la ruta de datos de la app (cirugía mínima futura, NO hecha).
- **R2:** instalador ~200+ MB comprimido — decidir si OCR/voz van dentro o como descarga posterior
  (la voz YA se descarga aparte hoy).
- **R3:** el fail-soft de OCR/voz hace que un bundle incompleto "funcione" mudo → el instalador
  necesita un self-check de arranque por módulo, no solo `/health`.
- **R4:** exes PyInstaller sin firmar disparan antivirus/SmartScreen → la firma (cuenta Azure
  Trusted Signing de Pipe) es requisito de LANZAMIENTO, no de construcción.
- **R5:** Postgres portable y LiteLLM quedan FUERA del bundle — la cáscara debe orquestarlos como
  procesos propios (hoy la DB ya es portable; patrón conocido).

---

## 2026-07-09 — Sesión 37 (continuación 2) — Fase 4 · bloque 1: ancla de instancia (R1) + veredicto de ruta del frontend

**Qué se construyó (cirugía mínima aprobada por revisor adversarial):**
- `backend/mia/config.py`: `PROJECT_ROOT` (ancla del estado de instancia: `.env`, `mia-data`)
  ahora resuelve con precedencia **`MIA_APP_DIR`** (env — así la cáscara de escritorio le dice
  al motor empaquetado dónde vive su instancia) → **`sys.frozen`** (PyInstaller →
  `%LOCALAPPDATA%\Mia`) → **default histórico intacto** (raíz del repo). Si `MIA_APP_DIR`
  viene sin `.env`, aviso RUIDOSO en stderr (no arranque mudo con defaults).
- **Capa 2 (revisor adversarial Opus, contexto fresco): APROBADO CON MENORES — todos corregidos:**
  - **MAYOR-1:** `memory/trace_capture.py::_default_traces_dir()` anclaba las trazas del
    flywheel HITL a `__file__` → en bundle onefile se PERDÍAN cada sesión y en onedir bajo
    Program Files reventaba el arranque del grafo. Ahora: `config.MIA_HOME / "traces"`
    (leído en cada llamada; en dev resuelve al mismo lugar histórico).
  - **MENOR-1:** `api/routes/ux.py::_available_models()` leía `litellm_config.yaml` vía
    `__file__` → ahora `config.PROJECT_ROOT` (la cáscara podrá colocar el yaml junto al .env).
  - **MENOR-2:** el aviso de `.env` faltante (arriba).
  - NOTA de seguridad aceptada: `MIA_APP_DIR` no amplía superficie de ataque (quien fija env
    vars ya controlaba `DATABASE_URL`/`LITELLM_BASE_URL` directo).
- Gate nuevo `execution/test_config_anchor.py` **8/8** (los 3 modos de resolución, MIA_HOME
  y traces anclados a la instancia, precedencia sobre frozen, aviso sin .env).

**Spike de frontend (agente ejecutor, evidencia en `../spike-fase4-frontend/`):** el export
estático de Next NO es el camino — las 2 pantallas core (`/asuntos/[id]` y su `/revisar`)
exigen reestructura + fallback SPA manual + mover los headers de seguridad a FastAPI.
**Decisión de ruta (Fable):** puente = **Node portable + `next start`** en el instalador
(cero riesgo de regresión en las pantallas críticas, +80-100 MB); el destino final sigue
siendo la migración a Vite ya planeada. El repo quedó limpio (config y rutas restauradas).

**Verificación:** gates dirigidos post-corrección: `test_config_anchor` 8/8,
`test_trace_capture` 26/26, `test_ux` 34/34 (falló una vez por colisión con el build del
spike en paralelo — se re-corrió limpio), `test_rls` 12/12 (HALT). Regresión completa de
las 71 suites corrida como capa final antes del commit (resultado en este mismo commit).

---

## 2026-07-10 — Sesión 40 — Bloque B del plan de evolución de producto COMPLETO (Guías de trabajo asistidas + gobernanza de skills)

**Contexto:** continuación del plan de evolución de producto (Bloques A/B/C) aprobado por Pipe en
`memory/plan-evolucion-producto.md`, bajo la misma autorización expresa de orquestación
multi-agente de la sesión 38. Esta sesión ejecutó el Bloque B completo (B0-B4).

**Qué se construyó (por pieza):**
1. **B0 — CRUD completo de playbooks + versiones (`029_playbook_versions.sql` +
   `execution/init_playbook_versions.py`, aplicada a la DB local):** tabla `playbook_versions`
   (snapshot del estado ANTERIOR, `changed_by` `'abogado'|'mia'`, `reason` en llano, RLS FORCE
   patrón 023). En `ux.py`: `POST /api/playbooks` gana `origin` ∈ {manual, importada, entrevista,
   asunto, aprendida} → `metadata.origin` (import marca `'importada'`); `GET /api/playbooks?status=
   activos|todos` con `origin`/`protected`/`status`; `GET /api/playbooks/{id}`; `PUT` (snapshot
   previo + re-embed; editable aunque `protected` — protected solo bloquea cambios automáticos;
   409 en llano si el título choca); `POST archive/restore`; `GET versions` + `POST restore` de
   versión (con snapshot del estado actual antes).
2. **B1-B2 — Wizard "Crear guía con Mia":** `backend/mia/memory/interviewer.py` (motor de
   entrevista STATELESS: mín 3/máx 6 preguntas, LLM `task="curator"` vía `asyncio.to_thread`,
   JSON inválido → fallback determinista jamás 500, recortes a 200 chars, NUNCA escribe en DB —
   gate HITL por construcción) + `backend/mia/api/routes/guides.py` (`POST /api/guides/interview`;
   422 en llano; `kind='agente'` → 422 "Los agentes se crean con Mia próximamente." — llega en el
   Bloque C), registrado en `main.py`. Frontend: `GuideInterviewWizard.tsx` (dialog 3 pantallas:
   entrevista → revisión con borrador 100% editable y el copy "Esta guía todavía no existe; solo
   se guardará cuando pulses Guardar." → guardar con `origin` `'entrevista'` o `'asunto'`); botón
   "Crear con Mia" en Conocimiento.
3. **B3 — "Convierte lo que hicimos aquí en una guía":** botón en la pantalla del asunto, visible
   SOLO con borrador realmente APROBADO (se expuso `hitl_outcome` en
   `GET /api/matters/{id}/draft`, con constante compartida `HITL_OUTCOME` nueva en
   `backend/mia/agents/state.py` — "aprobar con cambios" produce `'edited'` y NO muestra el botón,
   alineado con el criterio de evidencia del interviewer); la entrevista precarga contexto del
   asunto (título/descripción + `draft_final` de trazas aprobadas, patrón `_approved_evidence`,
   tope 12.000 chars) y abre con resumen de confirmación.
4. **B4 — Gobernanza de lo aprendido:** `GET /api/proposals` gana `source_matters` ("Aprendí esto
   trabajando en: …", derivado de `trace_ids`, fail-open a `[]`); `POST apply` acepta
   `{content?, title?}` editados (`improve_playbook` hace snapshot `changed_by='mia'`;
   `new_playbook` usa el título editado — eliminado el placeholder "Sugerencia {id}" y ahora lleva
   embedding); UI: subtabs "Guías y documentos" + "Lo que Mia sabe hacer" FUSIONADOS en "Guías y
   habilidades" (badges de origen en llano, métrica GEPA por `skill_id==playbook.id`, acciones
   Ver/Editar/Desactivar/Reactivar/Historial/Restaurar, botonera Importar · Escribir · Crear con
   Mia); sugerencias con "Editar antes de aplicar".

**Verificación 3 capas:**
- **Capa 1:** regresión completa ALL PASS (76 suites) — línea base sube de 74 a 76 con
  `test_playbook_versions` (59/59 tras capa 2; 48 iniciales) y `test_guide_interview` (25/25).
  `test_rls` 12/12 y `check_env_pins` 9/9 (HALT) intactos. `test_ux` sube a 37/37,
  `test_second_brain_ui` 26/26. `npm run build` verde (14 páginas). Hubo 1 ciclo de corrección en
  el gate: `test_second_brain_ui` buscaba el literal del tab viejo "Habilidades"; se actualizó al
  nuevo copy sin debilitar la aserción (verificado por revisor independiente).
- **Capa 2:** 4 revisores adversariales independientes (Opus, contexto fresco: seguridad/RLS,
  gate HITL+integridad, corrección backend, frontend/§G) → 10 hallazgos CONFIRMADOS (0
  descartados), TODOS corregidos en causa raíz con checks nuevos, y re-gate ALL PASS 76 + build
  verde:
  - **3 MAYORES:** restore de versión no capturaba `UniqueViolation` al restaurar título → 500 con
    jerga (ahora 409 en llano); crear guía (wizard/manual) SOBRESCRIBÍA en silencio un playbook
    homónimo sin snapshot y podía "desaparecer" la guía en una fila archivada (ahora
    `INSERT ... DO NOTHING` + 409 "Ya tienes una guía con ese nombre."); "Editar antes de aplicar"
    descartaba la corrección del abogado en propuestas `wiki_correction`.
  - **7 menores:** `proposal_id` malformado → 404 (antes 500); `new_playbook` aplicado sin
    embedding (nunca se recuperaba por similitud); `PUT` sin truncar título a 200 → posible 500;
    `matter_id` malformado en interview → 404 (invariante "jamás 500"); conexión pooled abierta
    durante llamada de embeddings en restore; título editado ignorado en `improve_playbook`; botón
    "Convertir en guía" aparecía tras borrador rechazado/editado.
- **Capa 3:** PENDIENTE — recorrido en vivo de Pipe.

**Deudas/riesgos nuevos:** ver `bugs-and-risks.md` Riesgo #58 (deuda consciente, no un bug:
`kind='agente'` del endpoint `/api/guides/interview` responde 422 hasta el Bloque C;
`GuideInterviewWizard` ya es reusable para ese caso).

**Pendiente para la próxima sesión:** Bloque C (agentes jurídicos + perfil unificado +
Configuración en subtabs, `plan-evolucion-producto.md`) + Capa 3 EN VIVO de Pipe sobre el Bloque B
(wizard "Crear con Mia", historial/restauración de versiones, "Convertir en guía",
"Editar antes de aplicar") — sin cambios respecto a la deuda de capa 3 arrastrada de sesiones
35-39 (OAuth de correo/OneDrive) ni a la acción de Pipe pendiente (registrar apps OAuth).


## 2026-07-10 — Sesión 41 — Bloque C del plan de evolución de producto COMPLETO (Agentes jurídicos + perfil unificado + Configuración en subtabs)

**Contexto:** cierre del plan de evolución de producto (Bloques A/B/C) aprobado por Pipe,
bajo la autorización expresa de orquestación multi-agente de la sesión 38. Flujo: recon con
5 lectores → specs por frente (Fable) → 3 ejecutores en paralelo sobre archivos disjuntos
(C1 Opus, C2/C3 Sonnet) → capa 1 → capa 2 (4 revisores + refutación por hallazgo) →
correcciones → re-verificación. Commit `acba433` (23 archivos, +2737/−399).

**Qué se construyó (por pieza):**
1. **C1 — Agentes jurídicos con conocimiento:** migración `030_persona_playbooks.sql`
   (M2M con RLS FORCE patrón 023/029, tope 8 guías por agente, `execution/init_persona_playbooks.py`);
   `PersonaService.get/set_linked_playbooks` (transaccional: un error deja los vínculos previos
   intactos; dedupe; errores en llano) con doble fail-open al cargar vínculos; `turn_context()`
   y `to_public()` ganan `playbook_ids`; en el turno de asunto `_prepare_playbooks` activa PRIMERO
   las guías vinculadas activas (tope 3 y `_shrink` intactos; sin agente = byte a byte igual);
   en el asistente, bloque "Guías que este rol prioriza" (≤16.000 chars con la nota de recorte
   INCLUIDA en el presupuesto, ≤4.000 por guía, tras la voz, jamás en role_prompt); entrevista
   `kind='agente'` (interviewer parametrizado por kind, draft con campos de agente, clips
   server-side, `suggested_playbook_ids` por afinidad de tokens solo de guías activas del tenant,
   fail-open); `GuideInterviewWizard` gana `onDraftReady` (con kind='agente' NO guarda: entrega el
   borrador al formulario del agente — gate HITL = el POST del form); UI `/personas` renombrada
   "Agentes jurídicos" (ruta y API intactas) con checklist de guías ("N de 8"; una archivada
   vinculada se muestra con etiqueta "Archivada — ya no se usa" y se puede desmarcar) y botón
   "Crear con Mia". Riesgo #58 CERRADO.
2. **C2 — Perfil del despacho unificado:** las respuestas de la entrevista (archivo por tenant
   en `$MIA_HOME`) quedan como FUENTE CANÓNICA y `firm_profiles` pasa a DERIVADO:
   `derive_firm_profile(responses)` determinista (omite vacíos; no deriva extras/legacy);
   `GET/PUT /api/profile/full` (PUT: `update_soul()` crítico → 502 si falla; jurisdicciones a
   `tenant_settings`; upsert best-effort con `warning` en llano que PRESERVA las 11 columnas
   existentes — lo derivado solo sobreescribe cuando trae valor, jamás anula con NULL lo sembrado
   por el flujo legado); PUT `/api/profile` legado deprecado pero funcional;
   `MiDespachoSection.tsx` (Identidad · Jurisdicción y práctica con `CountrySelector` extraído
   del onboarding · Datos profesionales · Herramientas; "Modo profundo" p19 NO se muestra —
   coherente con Riesgo #27); el ejecutor C2 además atrapó DE PASO el bug latente de
   `upsert_firm_profile` (escribe siempre las 10 columnas → cada guardado nuevo habría borrado
   en silencio lo del flujo legado).
3. **C3 — Configuración en subtabs:** `configurar/page.tsx` con shadcn Tabs (Primeros pasos con
   contador "X de Y" y default si incompleto · Conexiones · Carpetas · Automatizaciones · Valor
   y gasto con "Procesos de fondo" plegado); deep-links `#hash` sincronizados (lazy init del
   estado con el hash + listener `hashchange` + `replaceState`, sin loops); TODAS las anclas
   externas intactas sin tocar backend (setup.py `#conexiones`/`#carpetas`, dashboard `#valor`,
   FuentesPanel/OneDriveFolderPicker `#conexiones`); el mapa "¿Qué hace cada sección?" y la ayuda
   viven en Primeros pasos (decisión declarada).

**Verificación:**
- **Capa 1:** regresión completa **ALL PASS (79 suites)** — línea base sube de 76 a 79 con
  `test_agent_playbooks` 55/55, `test_profile_full` 51/51, `test_config_tabs` 14/14;
  `test_guide_interview` 25/25 actualizado (kind='agente' ya no responde "próximamente");
  `test_rls` 12/12 y `check_env_pins` 9/9 (HALT) intactos. `npm run build` verde (14 páginas).
- **Capa 2:** 4 revisores adversariales independientes (seguridad · backend C1 · backend C2 ·
  frontend/§G) + refutación por hallazgo con agentes escépticos: **5 menores CONFIRMADOS, 0
  mayores/bloqueantes, 0 falsos positivos; seguridad/RLS sin hallazgos.** Los 5 corregidos y
  re-verificados ANTES del commit: (1) off-by-one del presupuesto del bloque de guías (la nota
  de recorte no se contabilizaba → el guard ahora la reserva; check de barrido de frontera
  añadido); (2) el PUT /profile/full anulaba con NULL name/lawyer_name/jurisdiction/
  practice_areas/tools si las responses no los traían (preserved ampliado a las 11 columnas;
  check con el escenario real "legado sin entrevista" añadido); (3) guías archivadas invisibles
  inflaban el cupo "N de 8" (ahora visibles con etiqueta y desmarcables); (4) MiDespachoSection
  podía mostrar "Error 500" crudo (guard §G); (5) `ChipsField` muerto en memoria/page.tsx
  (eliminado + import X).
- **Capa 3: PENDIENTE — recorrido en vivo de Pipe** (lista en HANDOFF.md).

**Notas/deuda consciente:**
- POST /api/personas con `playbook_ids` inválidos crea el agente SIN vínculos y responde 422 en
  llano (decisión documentada del ejecutor C1, cubierta por test).
- Las 3 personas canónicas de fábrica siguen SIN guías pre-vinculadas (decisión).
- Carpetas vinculadas POR AGENTE: sigue pospuesto a v2 (nota de alcance del plan).

## Sesión 42 (2026-07-10) — BLOQUE INSTALADOR · Fase 1 (empaquetado) + blindaje de la cáscara

**Objetivo aprobado por Pipe:** instalador de Windows para que cualquier abogado instale MIA con
doble clic (Fase 4 de distribución del plan local-first). Plan de 4 fases: F1 empaquetado,
F2 primer arranque automático, F3 wizard de bienvenida, F4 instalador NSIS + E2E en frío.
Decisiones de Pipe: OCR incluido, VOZ como descarga posterior; plan aprobado con orquestación
multi-agente.

**F1 — Empaquetado (COMPLETO):**
- `packaging/entry_backend.py` + `mia-backend.spec` + `build_backend.ps1`: bundle PyInstaller
  onedir del backend (459.5 MB, exe verificado: /health db:true + pgvector 0.8.2 + 401 sin
  token, corriendo SIN venv/Python). Lecciones del spike preservadas (import explícito
  mia.api.main, collect litellm + rapidocr, tiktoken_ext). Smoke OCR post-build
  (`--ocr-smoke-test` → OK). Voz fuera del bundle por construcción (verificado).
- `packaging/build_frontend.ps1` + `output: 'standalone'` en next.config.mjs: pantalla
  autocontenida (103.5 MB con node.exe portable v22.23.1 pineado en `node-version.txt`);
  humo con detección de puerto ocupado + verificación de identidad del listener (OwningProcess).
  Node portable en `tools\node-portable\` (fuera del repo; README-frontend.md documenta).
- Gates nuevos: `test_packaging.py` 23/23 · `test_frontend_packaging.py` 24/24.
- Capa 2 (revisor adversarial Opus): 0 bloqueantes, 3 MAYORES + 3 menores, TODOS corregidos:
  M1 litellm llamaba a raw.githubusercontent.com EN CADA ARRANQUE del exe (violaba local-first;
  fix: setdefault LITELLM_LOCAL_MODEL_COST_MAP antes del import); M2 upx=True podía corromper
  las DLL de onnxruntime → OCR muerto en silencio (fix: upx=False); M3 humo del frontend daba
  PASS falso contra un squatter del puerto (fix: puerto libre automático + HasExited +
  identidad del listener); m4 comentario-promesa falsa del import rapidocr (fix + smoke real);
  m5 pip install sin --no-deps podía mover pins (fix: --no-deps + pins + gate duro
  check_env_pins DENTRO del build); m6 selección de Node no determinista (fix: pin file).

**Blindaje de la cáscara (adelanto de F2, COMPLETO):**
- `tauri-plugin-single-instance` 2.4.2 (2ª instancia muere sin tocar procesos; 1ª al frente).
- CSP explícita (`default-src 'self'; connect-src ipc: http://ipc.localhost`); splash
  externalizado a `splash.css`/`splash.js` (cero inline) para no depender de unsafe-inline.
- `db_check.rs`: pg_isready antes de adoptar el 55432, tri-estado Ready/PortBusy/ToolMissing
  con mensajes en llano distintos (puerto ocupado ≠ instalación rota); spawn_blocking.
- `identity.rs`: NADIE se adopta por responder 200 — backend debe traer claves propias de
  /health (db/pgvector/embed_model), frontend la huella de cabeceras de next.config.mjs; en
  los 4 caminos (adopción y post-lanzamiento). **Evidencia real que lo motivó:** en la máquina
  de Pipe el 8000 lo ocupaba voicebox-server.exe (¡pasó el health-check viejo!) y el 3100 el
  Next de "Intelligence Sura" — la cáscara vieja los adoptó y le mostró a Pipe la app
  equivocada. Colisión de puertos = caso ESPERADO.
- Gate nuevo: `test_shell_hardening.py` 42/42 (endurecido: strip de comentarios Rust para
  anclar checks al código; probado contra implementaciones rotas a propósito).
- Capa 2 independiente (Opus): 1 BLOQUEANTE (CSP rompía los estilos inline del splash —
  fix de raíz: externalización) + 1 MAYOR (gate validaba comentarios) + 2 menores
  (ToolMissing, spawn_blocking) — TODOS corregidos; cargo build exit 0.

**Capa 1 final: regresión 82/82 suites ALL PASS** (79 base + 3 gates nuevos), test_rls 12/12 y
check_env_pins 9/9 (HALT) intactos. `test_ux` recalibrado de raíz: su timeout de build (300s)
era pre-standalone; el file-tracing lo supera en máquinas cargadas → 600s con comentario
(el check valida returncode, no velocidad); re-corrido 41/41.

**Decisión técnica declarada (para F2):** LiteLLM entra al instalador como SEGUNDO exe
empaquetado desde `.venv-litellm` (~150-300 MB): sin él, las políticas "nube" y "soberano"
quedan rotas y "suscripcion" pierde sus fallbacks (investigación con evidencia en el hilo:
embeddings van in-process directo a Voyage; turnos suscripción van por CLI y solo caen al
proxy como red). La consolidación in-process (Riesgo #4) queda como refactor futuro.

**Lecciones operativas:** (1) nunca dos `next build` concurrentes sobre el mismo `.next`
(ENOENT por carrera de renames — pasó entre orquestador y ejecutor); (2) los ejecutores en
background que esperan notificaciones de builds largos se duermen — despertarlos con evidencia
(timestamps de dist/, procesos vivos); (3) la máquina de Pipe corre múltiples proyectos Node
a la vez — los tests con topes de tiempo deben calibrarse para máquina cargada.

## Sesión 43 (2026-07-11) — BLOQUE INSTALADOR · Fase 2 (primer arranque automático) COMPLETA

**Objetivo cumplido (meta declarada por Pipe: "terminar la fase 2"):** en una máquina limpia,
la cáscara detecta que MIA no está preparada y la deja funcionando sola. Diseño en
`memory/plan-f2-instalador.md` (contrato entre 3 ejecutores); orquestación multi-agente
(3 recon → diseño → 3 ejecutores → 3 revisores capa 2 → 3 correctores → regresión).

**F2a — Bootstrap (`backend/mia/setup/`):** `first_run.py` invocable como
`mia-backend.exe --first-run --pg-bin --pg-data --pg-port [--app-dir]` y
`python -m mia.setup.first_run`. Crea app_dir; `.env` semilla ATÓMICO (tmp+fsync+os.replace;
JWT_SECRET/PG_PASSWORD/PG_APP_PASSWORD/LITELLM_MASTER_KEY=LITELLM_API_KEY generados con
token_urlsafe, CORS 3100, MIA_ENV=prod verificado contra los 5 usos de IS_PRODUCTION; NUNCA
regenera secretos); initdb endurecido (pwfile en `<app_dir>/.setup-tmp`, UTF8, locale C,
scram-sha-256, listen_addresses=127.0.0.1 escrito ANTES del primer arranque); postgres temporal
con ownership limpio (si él lo arranca lo detiene SIEMPRE — try/finally); rol/DB/extensiones/
schema + migraciones 003→030 (runner Python; los .sql entran al bundle como `datas` del spec,
resolución dev/frozen en `setup/paths.py`) + checkpointer; marcador `.mia-setup-complete`
escrito de ÚLTIMO (contrato con la cáscara). Estados a medias auto-reparables: initdb
interrumpido → vacía pg_data y reintenta; cluster sin .env → error en llano SIN regenerar
secretos huérfanos. `init_db.py`/`init_checkpointer.py` refactorizados a `setup/db_bootstrap.py`
(compatibilidad conservada). Bug real corregido: `pg_ctl start` con capture_output cuelga en
Windows (postgres hereda pipes) → `-l logfile` + DEVNULL. Gate `test_first_run.py` 68/68
(initdb real ×2, login real con DATABASE_URL, has_table_privilege checkpoint%, reparación,
desajuste, idempotencia byte a byte).

**F2b — LiteLLM 2º exe (`packaging/`):** `.venv-litellm` creado (litellm[proxy]==1.74.8 desde
el intérprete base del .venv); `entry_litellm.py` con orden estricto: cost-map →
allowlist-load del .env del app_dir (solo *_API_KEY/LITELLM_*; utf-8-sig, nunca sobreescribe)
→ scrub DATABASE_URL/PG_* (Prisma muerto: único gatillo es DATABASE_URL, verificado en el
código de litellm) → `dotenv.load_dotenv` neutralizado (las 2 rutas reales) → CLI
`litellm.run_server()` + Blindaje 6 (inyección default `--host 127.0.0.1`).
`litellm_config.installer.yaml` con master_key (dev intacto). Build real: mia-litellm.exe
108.2 MB onedir upx=False; DOS causas raíz reales: certifi fuera del bundle
(pyinstaller-hooks-contrib==2026.6 pineado + collect_data_files("certifi")) y
UnicodeEncodeError cp1252 del banner (reconfigure utf-8 en el entry). Humo vivo: liveliness
200, /v1/models 200 con Bearer y alias, 401 sin Bearer, bind SOLO 127.0.0.1 (netstat) e
intento desde la IP LAN rechazado. Gate `test_litellm_packaging.py` 60/60.

**F2c — Cáscara (desktop/):** tokens `${exe_dir}`/`${local_app_data}` expandidos en punto
único (abort en llano si irresolubles); paso `setup` opcional con GATILLO TRIPLE (falta
marcador O PG_VERSION O .env → correr `--first-run`, timeout 15 min, stage "setup", última
línea del log en el error); LiteLLM 4º servicio (db→litellm→backend→frontend, shutdown
inverso, Job Object) con identidad de adopción `/v1/models` + Bearer (key leída del .env del
app_dir) + alias `claude-haiku`/`mia-local` — sin key NO se adopta; `child_died` evaluado
ANTES del health en los 3 bucles de espera (litellm/backend/frontend — el bug existía en los
3); PORT/HOSTNAME del frontend standalone. `packaging/orchestration.installer.json`: plantilla
ESTÁTICA para F4 (NSIS no templa nada). Dev SIN bloque litellm (el saneo de
run_litellm_clean.ps1 es scrubbing, no replicable vía env-add; documentado en README).
Gate `test_shell_hardening.py` 77/77; cargo build exit 0.

**Capa 2 (3 revisores adversariales independientes, contexto fresco):** 6 MAYORES + 5 menores
CONFIRMADOS, TODOS corregidos y re-verificados antes del commit:
M1 setup interrumpido tras escribir .env+PG_VERSION jamás se re-ejecutaba → instalación rota
para siempre (fix: marcador de finalización + gatillo triple); M2 .env no atómico → secretos
truncados permanentes; M3 cluster existente + .env perdido → regeneraba secretos que no calzan
(fix: error en llano); M4 gate sin login real de mia_app (verde falso posible); M5 proxy
LiteLLM bindeaba 0.0.0.0 → gateway de modelos con las llaves de la firma expuesto a la RED del
despacho (fix: --host 127.0.0.1 en installer json + dev + entry, verificado en vivo con
netstat e intento LAN rechazado); M6 initdb a medias irrecuperable (fix: auto-limpieza).
Menores: pwfile en %TEMP% compartido → carpeta privada; child_died después del health
(ventana de squatter); tokens vacíos silenciosos; pins de pyinstaller sin anclar en el gate;
allowlist LITELLM_* amplia (nota aceptada, sin acción).

**Capa 1: regresión completa 84/84 ALL PASS** (82 base + `test_first_run` +
`test_litellm_packaging`; `test_shell_hardening` sube 69→77 checks). `test_rls` 12/12 y
`check_env_pins` 9/9 (HALT) intactos. 0 reintentos.

**Deudas conscientes (todas en Riesgo #59, E2E de F4):** los exes de dist/ se recompilan en
F4 (el backend actual no trae --first-run/datas; el litellm no trae el Blindaje 6 — la
protección loopback vigente es el flag del installer json, verificada en vivo); interrupción
real del setup con la cáscara visual; console=True de ambos exes.

**Lecciones nuevas:** (4) los correctores de capa 2 también se duermen esperando builds —
despertarlos con evidencia es parte del protocolo, no excepción; (5) el runner
`scripts/run_tests.ps1` auto-descubre `execution/test_*.py` — los gates nuevos entran solos a
la regresión; (6) el default de bind de un servicio empaquetado NUNCA se asume: litellm CLI
default es 0.0.0.0 (el criterio loopback de la decisión 7 del plan aplica a TODO servicio).

## Sesión 44 (2026-07-11) — BLOQUE INSTALADOR · Fase 3 (wizard de bienvenida) COMPLETA — alcance expandido a toda la primera experiencia

**Objetivo aprobado por Pipe (EXPANDIDO en la sesión):** F3 iba a ser solo el wizard de llaves
mínimas; Pipe vio el onboarding existente y dijo que "no estaba chévere" — pidió rediseñar TODA
la primera experiencia del abogado (login + registro + activación de llaves + onboarding) como
UNA experiencia cohesiva, con diseño "cinematográfico premium + guiado/gratificante, wow
factor". Orquestación multi-agente: 4 recon → oleada 1 (backend de activación + infraestructura
visual) → oleada 2 (3 pantallas rediseñadas) → integración → capa 2 (4 revisores independientes)
→ 2 correctores → verificación final.

**Infraestructura visual nueva (`frontend/app/_welcome/`):** primer uso real de framer-motion
@12.42 en el repo (ya estaba instalado sin usar). `WelcomeShell` (pantalla completa oscura
#060606, `.bg-aurora` con blobs teal/CTA en deriva lenta, marca respirando); `BrandMark`
(wordmark MIA compartido, I en teal #2EA9A9, reemplaza el duplicado de `Sidebar` sin cambiar su
look); `WelcomeProgress` (constelación de progreso, `JOURNEY_STEPS` como fuente única del
viaje); `StepTransition`/`Stagger`/`StaggerItem`/`MotionField` (transiciones direccionales +
stagger, todas respetan `prefers-reduced-motion`); `Celebration` (partículas sin dependencias);
`WelcomeField`; `MiaLine` (typewriter en voz de Mia, con `aria-label` del texto completo para
lectores de pantalla); `motion.ts` (variantes + `useReducedMotion`); barrel `index.ts`.

**Backend de activación (`backend/mia/api/routes/welcome.py`):**
- `GET /api/welcome/status` — OPEN_PATH público, se enriquece si llega token; devuelve
  instalado/hay_usuario/`faltan_llaves{busqueda,respaldo}`/onboarding_completo/
  `motor_detectado{claude,ollama}`/política. `faltan_llaves` se lee del `.env` en disco.
- `POST /api/welcome/keys` — AUTH; escribe SOLO las claves pedidas al `.env` con escritura
  atómica que preserva el resto del archivo. La clave de BÚSQUEDA (VOYAGE) se recarga EN
  CALIENTE (embeddings.py la usa in-process vía config, sin reinicio). La clave de RESPALDO
  (ANTHROPIC) y OpenRouter quedan DIFERIDAS al proxy LiteLLM con AVISO FUERTE de reabrir MIA.
- `POST /api/welcome/keys/test` — AUTH; ping real fail-soft vía `run_in_threadpool`, con
  timeout, sin filtrar la clave en la respuesta ni en logs.
- `backend/mia/setup/env_writer.py` — upsert robusto: preserva CRLF, tolera BOM, matchea
  líneas `export`/con indentación, `threading.Lock` anti lost-update, escritura a `.tmp` único
  vía `mkstemp`; más `read_env_values`.
- Migración `031_welcome_bootstrap.sql` — `mia_any_tenant_exists()` SECURITY DEFINER con
  `search_path` fijado a `pg_catalog, public` y `tenants` calificado, `REVOKE PUBLIC` + `GRANT
  mia_app` — devuelve SOLO un booleano de existencia, para que `/welcome/status` funcione
  pre-login sin violar el RLS FORCE de `tenants`.
- `middleware.py` gana `/api/welcome/status` a `OPEN_PATHS`; `main.py` registra el router;
  `execution/init_welcome.py` aplica la migración 031 en los gates. Cambio menor §G en
  `agent/llm.py` (`_clear_message` ya no menciona el literal `ANTHROPIC_API_KEY`).

**Pantallas rediseñadas:**
- `register/page.tsx` → "Crear tu despacho" (tras registrar, navega a `/activar`).
- `login/page.tsx` → rediseño compacto sobre `WelcomeShell`.
- `activar/page.tsx` (NUEVA) → elegir motor (`Mi suscripción` recomendado / `Nube` / `Todo en
  tu equipo`, `role="radiogroup"`) + clave de búsqueda con validación en vivo (✓, debounce +
  guardia de carrera) + clave de respaldo opcional; auto-omisión en dev; fail-open si el backend
  de activación no responde.
- `onboarding/page.tsx` → rediseño con el mismo lenguaje de movimiento; PRESERVA intacto el
  autosave por `qid`, la reanudación, la generación determinista del SOUL, los tipos de campo y
  el flujo de cierre (`complete`).
- `AuthGate`/`OnboardingGate`/`Sidebar` ajustados al viaje nuevo (`Sidebar` se oculta en
  `/activar` y `/onboarding`).

**Verificación 3 capas:**
- **Capa 1:** línea base sube de 84 a **85 suites** (nuevo `test_welcome_keys` 39/39). Gates
  verdes: `test_welcome_keys` 39/39 · `test_rls` 12/12 (HALT) · `check_env_pins` 9/9 (HALT) ·
  `test_first_run` 68/68 (con la migración 031 aplicada) · `test_setup_wizard` 28/28 ·
  `test_onboarding_draft` 15/15 · `test_hitl_flow` 21/21. `npm run build` verde (15 páginas,
  `/activar` nueva; `_welcome` no genera ruta propia por ser infraestructura compartida). La
  migración 031 entra al bundle del instalador por el glob dinámico de
  `packaging/mia-backend.spec` (`os.listdir` + filtro `.sql`, sin lista hardcodeada).
- **Capa 2:** 4 revisores adversariales independientes de contexto fresco (seguridad,
  corrección backend, corrección frontend, §G/visual/accesibilidad). **0 hallazgos
  BLOQUEANTES.** Seguridad: sin mayores explotables — el intento de inyectar el `.env` para
  sobrescribir secretos de instalación vía `/welcome/keys` queda BLOQUEADO por diseño; 5
  menores de robustez + 1 riesgo futuro anotado. Corrección backend: 2 MAYORES + 5 menores.
  Corrección frontend: 2 MAYORES + varios menores. §G: LIMPIO (cero jerga técnica visible al
  abogado) + 2 hallazgos MAYORES de accesibilidad. **TODOS corregidos y re-verificados** antes
  del cierre: el caso "nube" ahora EXIGE la clave y avisa fuerte de reabrir; OpenRouter/Anthropic
  quedan tratadas como diferidas de verdad (ya no se les setea `config`/`os.environ` en
  caliente); Enter ya no dispara doble validación real; los campos de clave y sus labels
  quedaron con nombre accesible; `env_writer` preserva CRLF + candado de escritura; la función
  SECURITY DEFINER quedó endurecida (search_path + revoke); se cerró un escape de la clave hacia
  logs.
- **Capa 3:** PENDIENTE de Pipe (recorrido visual en vivo del nuevo viaje de bienvenida
  completo: registro → activar → onboarding).

**Deuda/decisiones nuevas de esta sesión:**
- Riesgo #60 nuevo (ver `bugs-and-risks.md`): el motor que depende del proxy LiteLLM no queda
  activo hasta reabrir MIA, porque `mia-litellm.exe` solo lee el `.env` al arrancar y F3 no abre
  IPC Tauri para reiniciarlo (ligado al punto 2 del Riesgo #59). Mitigado con clave obligatoria +
  aviso fuerte en la pantalla de activación para la política "nube"; no aplica al equipo Lexia
  (suscripción con el CLI de Pipe).
- Modelo de confianza mono-despacho documentado en `welcome.py`: cualquier usuario autenticado
  puede escribir las llaves GLOBALES de la instalación; si MIA pasa a multi-despacho hará falta
  un rol "admin de instalación".
- El Riesgo #59 (E2E de F4) ahora también debe recompilar los exes incluyendo `welcome.py` +
  migración 031 + `env_writer.py`.

**Próximo:** F4 — tauri bundle NSIS/MSI + E2E en frío en máquina limpia + los puntos acumulados
del Riesgo #59. Es la ÚLTIMA de las 4 fases del bloque instalador.

---

## Sesión 45 — 2026-07-11
**Módulo:** BLOQUE INSTALADOR · Fase 4 (instalador de doble clic) — **ENSAMBLADA** (falta capa 3 en frío de Pipe)

Construido:
- `packaging/build_installer.ps1` (contrato de ensamblaje): recompila los 3 payloads, copia el
  PostgreSQL 16 portable con pgvector a `dist/pgsql` (excluyendo pgAdmin/StackBuilder), verifica
  y corre el bundler NSIS de Tauri. Autodetecta el pgsql en `..\tools\postgres16-portable-full`.
- `desktop/src-tauri/tauri.conf.json`: `bundle.resources` (mapa) deja los 4 payloads + yaml +
  `orchestration.json` RENOMBRADO junto al exe; `targets:["nsis"]`; `windows.nsis`
  (installMode currentUser, lzma); WebView2 `offlineInstaller`.
- Gate nuevo `execution/test_installer_bundle.py`: invariante central (cada `${exe_dir}\X` de la
  cáscara tiene destino `X` en el mapa) + renombrado + console=True + exclusión de pgAdmin.
- Salida real: `Mia_0.1.0_x64-setup.exe` ~452 MB. Instalación aislada → payloads junto al exe
  (NO bajo `resources/`), pgvector presente, pgAdmin ausente, footprint 804 MB. El desinstalador
  también quedó verificado (limpio).

Errores/hallazgos (capa 2, 3 revisores, 0 bloqueantes):
- **console=False era un error mío**: la cáscara ya oculta la ventana con CREATE_NO_WINDOW; un exe
  windowed vacía el stdout que `run_setup` muestra al abogado como motivo de error del primer
  arranque → REVERTIDO a console=True (verificado a nivel PE: subsistema consola).
- **Frontend en 0.0.0.0** (expuesto a la LAN) → atado a 127.0.0.1 (lib.rs `env("HOSTNAME","127.0.0.1")`).
- **pgAdmin 4 (~700 MB)** empaquetado sin uso → excluido (860→124 MB).
- **WebView2 downloadBootstrapper** → `offlineInstaller` (instala sin internet, sirve el E2E en frío).
- Gate endurecido (backslash en el escaneo + guarda de pgAdmin). Ningún secreto de Pipe en el bundle.

Tests: línea base 85→86 suites. test_installer_bundle 30/30, test_shell_hardening 77/77,
test_packaging 23/23, test_litellm_packaging 60/60, test_frontend_packaging 24/24,
test_first_run 68/68, test_welcome_keys 39/39, HALT test_rls 12/12 + check_env_pins 9/9.

**Próximo:** capa 3 de Pipe = E2E en máquina 100% limpia (doble clic en frío). Riesgo #60 (reinicio
IPC del proxy) queda para una ola futura. Acciones de Pipe: firma Azure Trusted Signing + apps OAuth.

---

## Sesión 48 — 2026-07-16/17
**Módulo:** agnosticismo de jurisdicción (backend + frontend) · Agent Hub y Banco de oro cableados · criterio de MIA (los 8 principios) — **CERRADA** (capa 3 de Pipe pendiente)

17 commits. Tres hilos: quitarle a MIA lo colombiano que llevaba por dentro, hacer reales dos
capacidades que tenían API y estaban muertas, y darle criterio (cómo argumenta y cómo recuerda).

**El entorno: la DB portable volvió a arrancar** (llevaba sesiones caída). Trampas anotadas para
no repetirlas:
- El clúster vive en `tools/pgdata-portable` y escucha en **55432**. El 5432 lo ocupa un
  PostgreSQL de sistema **sin pgvector** — conectarse ahí da errores que parecen de código.
- Se arranca con los **binarios mínimos**, copiando `share/*` desde el `-full` **SIN machacar
  `share/extension/`**: ahí vive pgvector 0.8.2 y sobrescribirlo lo desaparece.
- Arrancar con los binarios del `-full` **levanta el postmaster pero sus backends mueren con
  0xC0000142**: el servidor parece vivo y toda conexión muere con ConnectionTimeout. Falso
  positivo caro; si se ve ese síntoma, es esto.

**Bug crítico cerrado (`ca7cd74`).** La bienvenida llamaba `PUT /api/settings/model-policy`,
pero el router de settings se registra sin prefijo: la ruta real es `/settings/model-policy`.
El 404 lo tragaba un catch vacío → elegir motor u opt-in de OpenRouter/NotebookLM **fallaba en
silencio** y el abogado creía que su elección había quedado fijada. Además deja de ser
fail-soft: si la elección no se persiste, la bienvenida se detiene con motivo en llano.
Hallazgo de Cursor (capa 3). Regresión en `test_second_brain_ui`.

**Frontend — confianza, agnosticismo y legibilidad (`960553b`, `32880a3`).**
- El borrador pendiente lleva a la pantalla de revisión (no al chat); se consumen
  `?sin_borrador`/`?confirmed` (antes se escribían y nadie los leía); aprobar/rechazar y
  restaurar versión dejan de fallar en silencio; el drift del curador se detecta por status
  409 y no buscando "409" dentro del texto (que no lo contiene si el backend manda `detail`:
  **el caso normal fallaba**); `AuthGate` ya no deja la pantalla en blanco.
- Fechas con el locale del equipo (fuera "es-CO" en 8 sitios); placeholders sin forma
  societaria ni credencial de un país; el detonador de cuantía suma UVT/UIT/UMA/IPREM/SMI y €
  conservando SMLMV/SMMLV (aquí el falso negativo es el riesgo grave).
- Token `--cta-strong`: contraste medido **sobre el fondo real** (bg-cta/15, no blanco) →
  **5.10:1** en reposo y 4.91:1 en hover; antes ~1.90:1 (ilegible). `plainMessage()` en
  `lib/api.ts` como fuente única de los errores en llano (evita mostrar "Error 500"). Lint en
  verde (2 de los 3 errores eran preexistentes, confirmados en 7125f8d).

**Backend agnóstico — MIA deja de ser colombiana por dentro (`902bd90`, `c4b57f5`, `09d00c7`).**
- La raíz: el pack de jurisdicción tenía `id_formats`/`doc_markers` diseñados pero **sin
  cablear**. Movido a `packs/co/`: formatos de identificación (cédula, NIT, radicado, teléfono
  +57), pistas de dirección y stop-words (`pii_hints.json`), léxico del buzón
  (`mail_signals.json`). El seed de corpus colombiano pasa a opt-in del pack. Los 7 patrones se
  movieron a JSON **sin alterar un carácter**: la tabla para 'co' es byte-idéntica → cero
  regresión para el despacho fundador.
- **Cuatro fugas de confidencialidad cerradas, todas confirmadas ejecutando:** (1) un pack podía
  APAGAR la red pan-hispana solo declarando un `role` — bastaba un typo, sin malicia, y salían
  cédulas y DNI en crudo; (2) preexistente: un despacho colombiano dejaba salir el DNI de un
  cliente español; (3) el respaldo de teléfono no cubría separadores ("615 55 12 34", la forma
  normal en España, salía crudo); (4) `wiki_dir()` interpolaba el tenant_id en la ruta **sin
  sanear** — inofensivo mientras el wiki era solo de escritura, primitiva de lectura al wiki de
  otro despacho en cuanto se cableara la lectura (saneado antes de conectar nada).
- Otros fail-open: `resolve_jurisdictions` no distinguía "eligió generic" de "nunca lo
  configuró" (un despacho sin configurar habría perdido cédula/NIT); `load_pack` no era
  fail-soft ante JSON corrupto; `lru_cache` congelaba una degradación transitoria para toda la
  vida del proceso.
- **Migración 036:** el DEFAULT `jurisdiction` de `legal_norms`, `jurisprudence` y
  `firm_profiles` pasa a 'generic'. La jurisdicción al escribir se decide ahora en Python
  (`SATGraph._resolve_jurisdiction`): explícita del llamador → pack del despacho → 'generic'.
  **Nunca 'co'.** Marcar 'generic' deja el material sin adscripción; marcar 'co' AFIRMA una
  autoridad jurídica falsa. Sin un solo UPDATE (verificado contra la base: legal_norms co=26,
  jurisprudence co=13, firm_profiles colombia=6, idénticos antes y después).
- Dos defectos vivos que no estaban en el inventario: `firm_profiles` (007) tenía DEFAULT
  'colombia' y `auth.py` inserta sin jurisdicción → **todo despacho nuevo nacía con el perfil
  marcado colombiano**; y `corpus_factory` marcaba como colombianas las normas del pack español.
- `47f5578`: el prompt del anonimizador decía "extractor de entidades para anonimizar un texto
  jurídico **colombiano**" y ejemplificaba direcciones con "carreras". **Se le escapó a tres
  auditorías del mismo archivo el mismo día**, dos de ellas adversariales: todas miraban los
  patrones, ninguna miró el prompt. Es un gate de confidencialidad: sesgar al modelo hacia un
  país le hace perder nombres y direcciones de los demás.
- Ejemplos del cuestionario de onboarding: fuera "Bogotá, Colombia" y las cuantías en pesos; el
  ejemplo enseña el FORMATO ("Ciudad, País").

**Dos gates que llevaban sesiones en rojo sin que constara (`16e9eec`, `9a93341`).** Ambos sobre
dinero, ambos verificados como ya fallando en 7125f8d — **la línea base de "84 suites ALL PASS"
NO era cierta**:
- `test_connector_hardening` exigía que 'suscripcion' NUNCA usara OpenRouter, pero b582541 (sesión
  47) extendió el overflow por decisión de Pipe ("Ambas"). El código era correcto; el test se quedó
  en la regla vieja. No se debilita nada: 'soberano' sigue sin usar OpenRouter jamás, y se añade el
  caso que faltaba ('suscripcion' sin opt-in tampoco enruta a un tercero). 37/37 (era 35/36).
- `test_value_delivered` exigía que un alias sin precio costara 0, pero f147fb9 lo cambió a tarifa
  conservadora de Sonnet — y es lo correcto: con 0 el gasto de un motor desconocido no se cuenta,
  el tope mensual no frena y el abogado cree que no gastó. 28/28 (era 26/27).

**Agent Hub y Banco de oro: tenían API y estaban muertos por dentro (`65e521d`, `84a059b`).**
- **Delegación:** `graph.py` LEÍA `metadata['delegate']` y **nadie lo escribía nunca** — habilitar
  un ayudante no hacía nada. Ahora `agents/delegate_intent.py` (determinista, sin LLM) detecta lo
  que el abogado ORDENA, y `agents/delegate_proposal.py` deja que MIA proponga (decisión de Pipe,
  ver decisions.md #34). Candado `gateway/hub_gate.py`: con política 'soberano' NO se delega aunque
  el ayudante esté habilitado; la política se lee con `model_policy_for_strict` (LANZA si la DB
  falla: un error de infraestructura jamás abre la salida). Sale exactamente el mensaje del abogado:
  ni documentos, ni hechos, ni perfil, ni historial (probado). Bug de raíz: `hub_config.set_enabled`
  hacía read-modify-write del config entero → activar un ayudante podía **resucitar una política que
  el despacho acababa de endurecer**; ahora merge jsonb atómico.
- **Banco de oro:** tres bloqueos. (1) `allow_eval_real_data` solo se LEÍA — no había forma de
  concederlo y el 403 mandaba "a Configuración", donde no había nada → GET/PUT
  `/settings/eval-consent`, fail-closed, merge anidado (el `||` de jsonb es superficial y habría
  borrado el resto de `config['eval']`). (2) No se podía releer un caso → GET
  `/api/gold-cases/{id}` (nunca devuelve `anon_map` ni su hash). (3) La UI no podía armar el caso →
  `:draft` lo arma **server-side** desde el matter_id, así el material sin anonimizar nunca llega al
  navegador. Topes explícitos (20 documentos, 60 fragmentos) avisados con números: nunca un recorte
  silencioso que parezca captura completa. RLS de la captura probado a conciencia: `traces.matter_id`
  es text sin FK, así que se sembró una traza del despacho B con el matter_id de A y timestamp más
  reciente — A no la captura.
- **Pantallas:** ayudantes externos dentro de Conexiones (activar NO hace que MIA los use; dice sin
  alarmismo que no se ha probado en vivo); Banco de oro en tab propio "Calidad", NO dentro de "Valor
  y gasto" (aquello es dinero, esto es un examen). Sospecha vs dato confirmado se distinguen por
  color, icono, texto, insignia Y subrayado — nunca solo por color. El resaltado ignora los offsets
  del backend a propósito (son posiciones sobre el texto global concatenado) y marca por valor, de
  más largo a más corto, para que "Juan Pérez" no destroce "Juan Pérez Gómez". Nunca dice "limpio".
  Gate `test_config_tabs` 21/21 (era 14) — fija, entre otras, que las rutas de `/settings` van SIN
  el prefijo `/api`: el mismo error que dejó la bienvenida sin guardar el motor.

**El examen empieza a medir sustancia (`aa8ac3a`).** Hallazgo, ahora test y no afirmación: un
borrador con **cero argumentos desarrollados** pero con las citas marcadas sacaba `ok:True`.
Cualquier mejora argumental era invisible al sistema. Tres señales deterministas, sin juez LLM y sin
léxico jurídico: densidad de desarrollo, anclaje al expediente (por COBERTURA: 20 `[doc 1]`
amontonados en un párrafo dan 1/3, no 1.0) y fundamentación normativa concreta. Tres señales
RECHAZADAS por no poder medirse sin mentir: "confronta a la contraparte" (solo por léxico, la más
gameable), "consecuencia jurídica al cierre" (fórmulas de un país) y concentración 80/20 (evaluada:
NO discrimina, mide varianza). Los indicios van en `flags_informativos`, **fuera de `flags` y de
`ok`**: una rúbrica nueva en el contrato vigente volvería rojos de golpe los casos de oro ya
aprobados, y un examen que se pone rojo sin que nada haya empeorado deja de creerse.
**Honestidad:** esto mide la FORMA, no la calidad del argumento; cada señal por separado es
gameable. Los nombres (`indicios_*`, ratio, densidad) lo dicen así a propósito: nunca "solidez".

**Los ocho principios — cómo argumenta y cómo recuerda (`9019ee6`).** Destilados de los skills de
firma de Pipe y de su vault, sin clonar nada: lo colombiano y lo propio de Lexia se descartó por
diseño. El hallazgo que ordenó todo: **MIA estaba construida para NO MENTIR, no para ARGUMENTAR
BIEN, y aprendía de Pipe sin volver a leer nunca lo aprendido.**
- La **Sala de estrategia** (52/52, sellada, cara) existía y el redactor **nunca la consultaba**.
  Ahora el dictamen —ya pagado y persistido por asunto— se inyecta sellado en el borrador. Se
  descartó correr la Sala en cada turno (~9 llamadas contra las 4 del turno: triplicaría la
  factura). Coste real: 0 llamadas nuevas, 1 SELECT indexado.
- **Anatomía del argumento** en la capa 2 (cacheada, +238 tokens que se pagan una vez): hecho del
  expediente, norma transcrita, autoridad aplicada AL CASO, prueba integrada y confrontación con el
  adversario. Roles funcionales, sin un solo país. Y jerarquía: el grueso a los 3-4 fuertes, los
  débiles se omiten. `facts` deja de describir inconsistencias y pasa a explotarlas.
- El **wiki era de SOLO ESCRITURA**: `search_wiki()` no la llamaba nadie en todo el repo. Todo lo
  aprendido de las correcciones del abogado —incluida "Lo que NO funciona"— iba a un .md que el
  modelo no veía jamás. Cableado en retrieval, fenceado como inferido y NO citable, ≤2 conceptos y
  ≤640 tokens por turno, 25 ms fuera del event loop.
- Antes de leerlo hubo que arreglar la **confianza, que era un trinquete**: solo subía (9 toques →
  1.0) y nunca bajaba ante un rechazo. Ahora un rechazo pesa el doble que una aprobación (rechazar
  cuesta un acto deliberado; aprobar es el default) y nunca llega a 1.0. Los archivos viejos con
  confianza inflada NO se leen hasta recompilarse.
- **`dreams` escribía reglas en SOUL** —la capa 1 del prompt, inyectada entera y con autoridad de
  sistema— sin HITL, sin tope y sin versionado; era el único escritor automático sin freno sobre la
  capa más autoritativa, y estaba **PROTEGIDO POR UN TEST** que exigía ese comportamiento ("Nudges
  actualiza SOUL"): hubo que invertirlo. Ahora propone y el abogado aprueba; versionado espejo de
  `playbook_versions` y tope que RECHAZA (no trunca: cortar la identidad en silencio es peor). La
  instrucción directa del abogado se aplica sin re-preguntar (su input es fidedigno).
- El **Curator fusionaba contradicciones**: coseno >0.85 y fundía. "Siempre X" y "nunca X" son casi
  idénticos para una máquina. Ahora un juez barato separa duplicado de conflicto (fail-soft a
  duplicado: un falso positivo interroga al abogado y deja de aprobar, y una memoria que nadie
  aprueba deja de aprender). ~$0.012/despacho/semana.
- **Obsidian**: el frontmatter entraba como basura textual y los `[[wikilinks]]` no se parseaban —
  MIA leía el segundo cerebro del despacho como un PDF. Ahora son metadatos consultables. Sin
  frontmatter → idéntico a antes; YAML roto → esa nota degrada y el vault sigue sincronizando.
- Migraciones: 037 (consentimiento de agentes por asunto), 038 (conflictos del curador), 039
  (frontmatter/links de Obsidian), 040 (versiones de SOUL). **La 040 nació como 038 y hubo que
  renumerar**: dos agentes reservaron el mismo número. Dos migraciones con el mismo prefijo rompen
  el orden del ledger y el checksum del gate F0.

**Tests (capa 1).** Verdes al cierre: `test_rls` 19/19 (HALT) · `migration_ledger` PASS ·
`argument_engine` 65/65 · `soul_guard` 47/47 · `curator_conflicts` 38/38 · `wiki_reading` 36/36 ·
`obsidian_sync` 73/73 · `eval_substance` 37/37 (nuevo) · `e2e` 32/32 · `prompt_builder` 46/46 ·
`dreams` 44/44 · `curator_hitl` 29/29 · `jurisdiction_agnostic` 75/75 · `delegation_decide` 103/103 ·
`delegation_wiring` 41/41 · `warroom` 52/52 · `agent_hub` 46/46 · `gold_cases_api` 55/55 ·
`gold_cases` 42/42 · `config_tabs` 21/21 · `second_brain_ui` 27/27 · `connector_hardening` 37/37 ·
`value_delivered` 28/28 · `untrusted_content` 28/28 · `sat_graph_jurisdiction` 26/26 (era 11) ·
`tsc` limpio · `next lint` 0 errores · `next build` 15 rutas · `cargo check` exit 0.
**Además, con la DB por fin arriba se corrieron tres gates que estaban DIFERIDOS y hoy están
verdes:** `test_rls` 19/19 (HALT), `test_welcome_keys` 41/41 y `test_setup_wizard` 28/28.

**Capa 2.** Revisiones adversariales independientes en los frentes de frontend, jurisdicción
(verificó la equivalencia de los regex contra HEAD y encontró la fuga del `role`) y delegación.
Todos los hallazgos corregidos en los mismos commits.

**Honestidad sobre el alcance (lo que NO se verificó):**
- El gate del **Curator prueba el cableado, no la puntería del juez** (corre sin red, el veredicto se
  inyecta). Su precisión real está sin medir; lo acota que el fallo seguro es degradar al
  comportamiento de hoy.
- **D3 sigue abierto**: los flags de los CLI del Agent Hub nunca se han confirmado contra un `--help`
  real. La salida del ayudante va a `metadata` y NO entra en la cadena de razonamiento jurídico. La
  primera invocación real puede fallar; degrada limpio y avisa en llano, pero "funciona" está sin
  verificar en vivo.
- El archivo **"Patrones rechazados" de dreams sigue sin llegar al modelo** (confidence hardcodeada
  0.10, sin `wiki_schema`): el lazo de aprendizaje no está cerrado al 100%.
- **El diagnóstico del turno no se persiste** (vive en el checkpoint y se borra al terminar): las
  conclusiones clave del banco de oro llegan vacías. No se inventan — se le pide al abogado que las
  escriba.
- Pendiente reportado y no tocado: FTS 'spanish' (exige migración de índices) y voz TTS es_MX
  (requiere empaquetar una voz por variante).

**Próximo:** capa 3 de Pipe — E2E del instalador en máquina limpia, recorrido visual, login real de
NotebookLM y, nuevo, probar en vivo la delegación (D3) y el banco de oro de punta a punta.

---

## Sesión 49 — 2026-07-17 — 6 features cableadas ("activas por fuera, muertas por dentro") + verificación visual

Se retomó el patrón de sesión 48 (capacidades con API expuesta pero sin cablear por dentro) y
se cerraron 6 metas con orquestación multi-agente (Opus coordina, Sonnet implementa grupos
disjuntos sin solaparse en archivos, Opus verifica adversarial re-corriendo el gate de cada una;
un solo escritor de git).

**(A) Banco de oro conectado al examen.** `run_full_suite` + `POST /gold-cases:evaluate`
gateados por `allow_eval_real_data` (el mismo consentimiento de sesión 48, ahora con algo que
consentir). Gate `test_gold_cases_influence_eval` 11/11.

**(F) Limpieza.** `gepa_run_all_tenants` borrada — quedó huérfana, ningún scheduler ni ruta la
invocaba.

**(A-Pinecone) Store secundario opt-in por despacho.** Aislado por namespace, fail-soft (una
falla de Pinecone nunca tumba el turno), y por diseño **nunca externaliza el expediente completo**
— solo lo que el despacho decide indexar ahí. Gate `test_pinecone_wiring` 23/23. Deps nuevas en
`pyproject`: `pinecone>=3`.

**(B-MCP) Consumidor real stdio.** Sandbox por proceso/tenant, salida SELLADA `[VERIFICAR]` (no
entra a la cadena de razonamiento jurídico como hecho verificado), el candado `hub_gate` de
sesión 48 bloquea ANTES de lanzar el subproceso (política 'soberano' nunca abre un stdio externo).
Gate `test_mcp` 39/39, con el caso `stdio-live` en SKIP honesto cuando no hay LiteLLM arriba (no
se simula un PASS falso). Deps nuevas en `pyproject`: `mcp>=1.10,<2`.

**(D) Blindaje del instalador.** `/health` reporta migraciones aplicadas vs. esperadas +
checkpointer — migración **043** (grant del ledger a `mia_app`, sin el cual el rol de la app no
podía ni leer su propio estado de migraciones). La cáscara Tauri frena el arranque si la base no
terminó de actualizarse (evita que el abogado use MIA a medio-migrar). Backups rotan a 3 (antes
sin tope). Gate `test_first_run` 71/71.

**(E) Atajos de un clic + salud de guías.** Pipe eligió la opción completa (no solo atajos).
Atajos en el chat PRE-LLENAN el mensaje, nunca auto-envían (el abogado siempre confirma antes de
que algo salga). Salud de guías sana/revisar — migración **044** (`playbook_health`), fail-open
(si el chequeo de salud falla, la guía se sigue ofreciendo; no se oculta trabajo del abogado por
un error de infraestructura). Gates `test_playbook_health` 29/29, `test_despacho_atajos` 17/17.

**Migraciones nuevas:** 043 (grant ledger a `mia_app`) y 044 (`playbook_health`) — numeración y
dependencias las preparó el coordinador para evitar el choque de sesión 48 (dos agentes
reservando el mismo número).

**Tests (capa 1).** `test_gold_cases_influence_eval` 11/11 · `test_pinecone_wiring` 23/23 ·
`test_mcp` 39/39 (stdio-live SKIP honesto sin LiteLLM) · `test_first_run` 71/71 ·
`test_playbook_health` 29/29 · `test_despacho_atajos` 17/17. HALT: `test_rls` 19/19,
`check_env_pins` 10/10.

**Capa 3 — verificación visual en vivo.** Recorrido de chat/atajos (pre-llenan, no auto-envían,
confirmado visualmente) y de memoria/salud de guías (sana/revisar visible) = **PASA**.

**Cierre.** 7 commits + retro de sesión.

**Próximo:** capa 3 en vivo de Pipe pendiente — MCP e2e (arrancar LiteLLM y re-correr
`test_mcp` con el caso stdio-live real, no en SKIP), Pinecone real (llaves + índice dim 1024),
banco de oro e2e, delegación D3 (Riesgo #66); ajuste opcional del cupo de agentes en
`list_shortcuts` (≥6 guías, no confirmado como bloqueante).

---

## Sesión 50 — 2026-07-20 — Mia lee el expediente de verdad, no puede afirmar sin respaldo, y no es de ningún país

> **Nota de continuidad.** Entre la sesión 49 (2026-07-17) y esta hubo trabajo el **18 y el 19 de
> julio** (Fase 1, incrementos 1-3, y el primer arranque en vivo) que **nunca se registró en este
> diario**. Su detalle está en `HANDOFF.md`, entradas del 18-jul (incrementos 1 y 2), 19-jul
> (incremento 3) y 19-jul (2ª sesión). La numeración sigue el contador de este archivo, no el número
> real de sesiones transcurridas.

Rama `feat/fase1-inc1-cleanup-scaffolding`. **18 commits, NINGUNO pusheado** (Pipe aprueba el push).
Método: un escritor por archivo, frentes disjuntos, verificador adversarial independiente al cierre de
cada frente. **~40 agentes, cinco workflows, cero colisiones de archivos.**

### Lo construido, por frente

**(1) Lectura adaptativa del expediente** (`00c4c17`). Con 743.600 caracteres indexados Mia leía 8
fragmentos — el **1,3 % del material**. No es que analizara mal: es que casi no leía. Muere el literal
`top_k=8`; el tamaño de lectura se deriva del material indexado, del presupuesto real del nodo que lo
consume y de la exigencia de la pregunta (heurística determinista, sin modelo). Piso inviolable en 8.
Además dedup, tope por documento y expansión a fragmentos contiguos (apagada por defecto). **Trampa
cerrada:** `hnsw.ef_search` nunca se fijaba; con el valor de fábrica de pgvector (40), subir candidatos
por encima de ~40 **degrada el recall sin avisar** — se habría entregado "Mia lee más" mientras leía
peor. Cobertura en **0.22** por decisión de Pipe (ver decisions.md #37). Gate `test_retrieval_adaptativa`
59/59 (nuevo).

**(2) Guardián de citas cableado a proyectos + el falso respaldo** (`9516833`). `verification_node` solo
existía en el grafo de asuntos: un proyecto podía afirmar normas sin una sola marca `[VERIFICAR]`.
Comprobado en vivo: cinco citas de articulado salieron sin marcar. **Se movió el punto de emisión del
evento SSE** para que el texto salga DESPUÉS de verificarse (sin eso, el nodo habría sido decorativo —
decisions.md #39). Y el defecto **más grave de la sesión, PREEXISTENTE**: el guardián certificaba en
verde citas inventadas (decisions.md #40). Gates `test_projects` 59/59 · `doc_citation_guard` 38/38.

**(3) Ordenamiento aplicable y procedencia** (`03d861f`). La jurisdicción **nunca llegaba al modelo**:
vivía en un comentario y en una frase que decía "según la jurisdicción del despacho" sin decir cuál. Con
el hueco abierto, el modelo lo rellenaba con lo que más ha visto. Ahora L3 declara el ordenamiento en dos
ramas (sin ordenamiento: prohibición de nombrar articulado, códigos, corporaciones o bases normativas de
un país, y razonamiento en el plano de la institución jurídica; con ordenamiento: cita el suyo con
normalidad y lo ajeno va declarado como extranjero). Más una **política de procedencia**: no se atribuye
al expediente ni al despacho nada que no haya llegado sellado en ese turno. Cero literales de país en el
código. Gate `jurisdiction_agnostic` 104/104 (era 75).

**(4) Rediseño de interfaz por capas** (`444d3a1`). Auditoría previa: el 89 % del producto era texto de 14
y 12 puntos con un h3 del mismo tamaño que el cuerpo, 23 recetas de tarjeta a mano, siete radios (dos
idénticos al renderizar), tres anchos sin regla, y **ninguna animación respetaba "reducir movimiento"**
salvo la bienvenida. Capa 1 tokens (escala semántica de seis roles, contraste subido donde caía bajo el
mínimo accesible — eran justo los avisos de responsabilidad). Capa 2 primitivas (`Card` rescatada,
`PageShell`, `SectionTitle`, `lib/motion.ts`). Capa 3 pantallas: **el Panel deja de ser un marcador de
ceros** y consume lo que ya existía construido y sin exponer. Recorrido headless de las 11 rutas: cero
errores de consola, cero peticiones fallidas (antes había dos).

**(5) Andamiaje de lectura agéntica, APAGADO por defecto** (`513a50b`, `f791596`). Decisión de Pipe
(decisions.md #38). Se implementa imitando `mcp/turn.py`; todo lo recuperado pasa por el mismo sellado de
contenido no confiable. La segunda pasada corrigió tres sobreventas que encontró un verificador: leía un
tercio del riel clásico y lo llamaba ahorro (techo subido de 44 a **128**, igualando el clásico); el check
de ahorro **no podía ponerse rojo** porque el guion del modelo falso decidía la respuesta (se añadió el
peor caso y el check AFIRMA que ese caso es más caro); y el presupuesto del bucle no contaba el reenvío
del historial, que es la parte que más pesa. Gate `lectura_agentica` 66/66 (nuevo).

**(6) Perfil del despacho: pregunta criterio, no datos censales** (`c980704`, diseño en `872a7ec`). Tres
defectos cerrados: el endpoint aceptaba cualquier cosa y devolvía 200 con un perfil de dos líneas (el
validador **existía y funcionaba, pero solo se invocaba en un test** — detector de humo desconectado);
seis de las ocho preguntas eran opcionales; y preguntaba el estilo mientras el resumen decía "tu estilo no
te lo pregunto". Fuera: estilo en adjetivos, canales, herramientas. Dentro: qué se revisa siempre y qué
puede resolver sola, qué no debe hacer nunca, y cuándo se da un escrito por terminado. Mismo número de
pasos. **Frente RECHAZADO por su verificador y rehecho** (ver §Errores). Gates `soul_guard` 47/47 ·
`profile_full` 51/51 · `onboarding_horizontal` 13/13 (estaba 7/11).

**(7) Carpetas + Sala de estrategia** (`91bd2e0`). Las dos suites de carpetas llevaban **sesiones en rojo**
sin causa identificada, arrastradas de una auditoría a la siguiente: la causa era de espera, no de
producto — las comprobaciones no aguardaban a que la indexación convergiera. Demostrado por falsificación
(bajando el plazo a 0,05 s se ponen en rojo exactamente los dos checks que fallaban). Y lo más importante:
**no existía ni un solo test de "carpeta vinculada a un PROYECTO"**, que es justo el escenario que falló en
producción con Pipe delante → `test_carpeta_proyecto.py` (31 comprobaciones). La Sala: presupuesto propio
(falsificado, el prompt real llegaba a 212.000 frente a un tope de 150.000 — desbordaba de verdad) y deja
de quedarse muda sobre la norma (`ux.py` descartaba el ordenamiento del despacho). Gates `warroom` 79/79 ·
`carpeta_proyecto` 31/31 (nuevo) · `matter_folder` 37/37 · `matter_folders_multi` 30/30.

**(8) El recorte por presupuesto** (`3063df5`). Tres defectos en `shrink_documents`, que usan facts,
analysis, draft, work y la Sala: partía por **mitades ciegas** sin mirar el presupuesto (deuda vieja
documentada); **desperdiciaba la mitad del cupo** por no descontar el peso del sellado (de 200.000 se
quedaba en 35.000 teniendo 70.000 — utilización medida **del 50 % al 99 %**); y **tiraba primero lo que el
modelo había pedido** (de 12 ampliaciones sobrevivían 2; ahora 6). La salida conserva el orden de llegada:
la prioridad decide quién se queda, nunca quién es el `[doc 1]` — el ancla de las citas no se mueve.
**Coste dicho, no escondido:** los nodos entregan ahora cerca del 100 % de su presupuesto en vez del 50 %.

**(9) Selector de países honesto** (`6e0cacc`). Defecto **visto en una captura, no leyendo código**:
21 países cableados a mano sin consultar nada, y material real para uno. Ver decisions.md #41 y #42.
Gates `onboarding_horizontal` 18/18 (era 13) · `onboarding_jurisdictions` 10/10 (era 7).

**(10) Meta-gate: una barrera contra las puertas de calidad que aprueban sin mirar** (`f2bbec2`). Prueba
las pruebas. Recorre `execution/` con **análisis sintáctico, no expresiones regulares**, porque hay tres
cosas que una regex no puede: distinguir la aguja del pajar (`d["content"] not in docs` es sano;
`x not in d["content"]` es el defecto), **seguir el valor por una variable intermedia** —la forma exacta
del fallo real de `b5`— y reconocer el arreglo para no castigar a quien ya lo aplicó. **Verifica su propia
premisa:** si mañana amplían el caching a otro mensaje, se pone rojo pidiendo que lo ensanchen en vez de
tranquilizar sobre una premisa caducada. **Asimetría deliberada:** la aserción negativa tumba la entrega;
la positiva solo se inventaría como aviso — si ambas tumbaran, el gate nacería rojo sobre cinco sitios hoy
sanos y el primero que lo viera lo desactivaría. Inventario: **120 suites, 11 expuestas, CERO de la clase
silenciosa**; 5 avisos, todos en `test_assistant.py`. Falsificado con cuatro casos, incluido una suite
**inmune** con la misma aserción palabra por palabra que **no** debe reportarse. Coste 0,5 s, sin red ni
base. **Puntos ciegos escritos en el propio archivo:** no ejecuta nada y solo mira una clase de ceguera.

**(11) Arreglos menores de producto** (`aaa3d1a`, `96d3449`). Los agentes del despacho no salían nunca
como chips en el chat vacío (el corte a 6 guías se aplicaba ANTES de anexar a las personas): capacidad
construida que el abogado no podía ver. Y tres componentes (`MissionBoard`, `MicButton`,
`MailboxSectionLoader`) **literalmente desaparecían en tema oscuro** por usar la paleta cruda de Tailwind
sin un solo token; se renderizan en pantallas primarias.

### Errores y hallazgos (lo de mayor rendimiento de la sesión)

**La verificación adversarial encontró seis defectos graves en trabajo que sus propios autores daban por
bueno. Dos frentes fueron RECHAZADOS y rehechos** (el perfil del despacho, con dos bloqueantes y una
regresión de producto; y la lectura agéntica, aprobada con reservas por sobrevender el ahorro).

1. **El guardián certificaba en verde citas inventadas** (preexistente) — decisions.md #40.
2. **El recorte desperdiciaba la mitad del cupo** y tiraba primero lo que el modelo pidió.
3. **El Panel inventaba ceros** cuando fallaba la fuente de cifras: *"0 borradores · 0 horas · USD 0.00"*,
   indistinguible de un dato real. **Un cero es una afirmación, no un dato ausente.** Era además una
   regresión: el código anterior se quedaba en esqueleto — feo, pero nunca mentía.
4. **"Reducir movimiento" congelaba los indicadores de trabajo en curso**: el abogado no podía distinguir
   *"analizando"* de *"colgada"*, y habría reenviado la consulta. La regla global se había escrito sin
   medir su radio real (`animate-spin` en 19 archivos).
5. **El perfil dejaba fuera al propio dueño** con un 422 sin salida, y a cualquier despacho de un país no
   listado sin poder darse de alta — cerrando mercados enteros. **Un guardián no puede cerrarle la puerta
   a quien ya entró.**
6. **El dedup borraba la fuente primaria** cuando otro documento del expediente la transcribía: la pieza
   original desaparecía con su archivo y su folio.

**Dos atribuciones falsas propias, corregidas midiendo** (no razonando):
- `test_retrieval_knowledge` cayó de 36 a 35 justo tras tocar la recuperación. La causa estaba en **otro
  frente** (la capa nueva de prompt engordó el system 419 tokens y agotó un margen que ese test se había
  dado a propósito). Worktree limpio en HEAD + medición. **La proximidad temporal no es causalidad.**
- `b5` de `test_context_recovery` se achacó a la capa de jurisdicción **generalizando desde el caso gemelo
  `e5`**, que sí era de ventana. Neutralizando la capa, `b5` seguía rojo: la causa real era el commit
  `e8ce3b3` del **17 de julio** (el `content` del system pasó de cadena a lista de bloques, y
  `'pb_index in sys2'` dejó de preguntar "contiene este texto"). **Una causa confirmada no se extiende por
  analogía.**

**Tres puertas de calidad verdes que no probaban nada, en una sola semana** (`fb30664`, `479f78f`): `b5`
roto desde el 17-jul sin que constara; `soul-legacy-3` verde encima de un error real; y la medida del
prompt contando el envoltorio (`str(content)`, o sea el repr con llaves y metadatos) en vez del texto —
falso positivo **latente**, no activo. El barrido posterior de las 116 suites confirmó, **con base y no
por ausencia de búsqueda**, que no hay falsos positivos: se buscó específicamente la clase peligrosa
(aserciones negativas del tipo "esto NO debe aparecer") y no existe ninguna en `execution/`.

**Bloqueante de entorno cerrado:** las migraciones **044, 045 y 046 no constaban en el ledger** — la 044
(salud de guías) **nunca había corrido**. `/health` reportaba 41 de 44 y el blindaje del instalador habría
frenado el arranque en la máquina de un cliente. Aplicadas por el runner real: **44 de 44**.

### La prueba en vivo contra un modelo real

Primera vez en varias sesiones que se prueba con MIA encendida y un modelo de verdad.

| Escenario | Antes | Después |
|---|---|---|
| Despacho **sin país**, expediente vacío, pregunta por requisitos de validez de un contrato | Cinco artículos de un país concreto, transcripción verbatim, ofrecimiento de consultar una base normativa nacional, y remate: era *"conocimiento consolidado del despacho"* — con el despacho vacío | **Cero artículos, cero códigos, cero países.** Razona la institución jurídica y pide el ordenamiento para poder citar |
| Despacho **con país configurado**, misma pregunta | — | Cita su norma con normalidad, **cada cita con su marca**, y declara que sale *"de mi memoria jurídica general, no de un texto que me hayas cargado"* |

**Matiz honesto 1:** el guardián determinista detectó **1 de 5** citas; las otras cuatro las marcó el
modelo obedeciendo la instrucción — justo aquello de lo que el guardián existe para no depender. El
resultado fue correcto, pero por la razón equivocada.
**Matiz honesto 2:** la fuga original **no se pudo reproducir** en tres intentos con el código anterior.
No es que no existiera —está capturada—: es **intermitente**, lo que la hace más peligrosa, no menos.

### Tests (capa 1)

**HALT verdes al cierre:** `test_rls` 19/19 · `check_env_pins` 10/10.
Verdes tras los cambios: `retrieval_adaptativa` 59/59 (nuevo) · `lectura_agentica` 66/66 (nuevo) ·
`carpeta_proyecto` 31/31 (nuevo) · `context_recovery` 52/52 · `warroom` 79/79 · `projects` 59/59 ·
`doc_citation_guard` 38/38 · `jurisdiction_agnostic` 104/104 · `argument_engine` 66/66 ·
`retrieval_knowledge` 36/36 · `document_pipeline` 45/45 · `untrusted_content` 28/28 ·
`context_references` 43/43 · `prompt_builder` 46/46 · `e2e` 58/58 · `soul_guard` 47/47 ·
`profile_full` 51/51 · `onboarding_horizontal` 18/18 · `onboarding_jurisdictions` 10/10 ·
`matter_folder` 37/37 · `matter_folders_multi` 30/30 · `despacho_atajos` PASS · `tsc` exit 0.

**Prueba de mutación aplicada en todos los frentes nuevos** (cinco, seis y tres mutaciones según el
frente): cada una pone en rojo su check. Un agente descubrió además que su propia mutación no probaba
nada porque `"" in texto` siempre es cierto — **hasta la falsificación necesita falsificarse.**

**NO se corrió la regresión completa** (no cabe): por tramos, las suites tocadas y sus adyacentes.
**La línea base heredada de "84 suites" no es cierta:** el barrido manual contó **116** suites en
`execution/` y el inventario automático del meta-gate, ya con las nuevas, cuenta **120**. Más de treinta
nunca entraron a vigilancia.

### Estado del entorno (verificado al cerrar)

- Base portable ARRIBA en `127.0.0.1:55432` (binarios `postgres16-portable`, NO el `-full`). **44/44
  migraciones.**
- Cerebro en `:8000` con todo el código del día cargado (se reinició al final). **NO recarga en caliente.**
  Motor LiteLLM en `:4000`. Pantalla en `:3100` (sí recarga en caliente).
- **Los servicios SÍ sobreviven** lanzados con el mecanismo de fondo del harness (`run_in_background`); lo
  que muere es `Start-Process`. Esto destrabó la verificación visual, dada por imposible durante sesiones.
  Para probar código nuevo sin reiniciar la instancia en uso: **levantar una segunda en otro puerto**
  (se usó `:8010`).
- Despachos de prueba creados y **pendientes de borrar**: `verificacion.visual@local.test`,
  `despacho.conpais@local.test`, `alta.nueva@local.test`.

### NO verificado — honestidad

- **Ningún gate corre contra un modelo real.** La prueba en vivo fue manual y puntual, no un banco de
  casos. **Es la brecha de fondo del proyecto** y la señalaron todos los verificadores.
- **La lectura agéntica nunca ha corrido con un modelo real.** Por eso nace apagada.
- **Coste y latencia reales por turno: no medidos.** Las cifras del repo son estimaciones del propio gate,
  con un estimador heurístico de tokens (todas las conclusiones de presupuesto heredan ese error).
- **El paso de país con campo libre** se verificó por código y por captura, no recorrido a mano por una
  persona.
- **`next build` no se corrió** (regla del repo). Sí `tsc`.

**Próximo:** ampliar el guardián a citas abreviadas (`arts. N y ss.`, siglas de código — las formas
transversales van en el código, **las siglas concretas de cada código van en el pack**); banco de casos +
benchmark ciego contra el modelo vivo; segundo paso de la lectura agéntica (que el bucle pueda
**reformular** la consulta, no solo pedir más de lo mismo); sección `## aprendido` del perfil, que se llene
sola vía `update_soul` (paso 7 de `docs/diseno-soul-onboarding.md`, lo único del rediseño sin implementar);
y los riesgos nuevos #75-#80 de bugs-and-risks.md. **De Pipe:** aprobar el push de los 18 commits y decidir
entre profundidad en un ordenamiento o anchura verificable en varios.

---

## 2026-07-24 (3ª sesión) — F2 · las 3 sondas adversariales, corridas y leídas

**Qué se corrió:** las 27 corridas en vivo que faltaban tras el reinicio (30/30 acumuladas),
en trozos foreground de `--repeat 1` bajo `suscripcion` con `MIA_EVAL_PERSIST_FULL=1`.
Ninguna perdida, ninguna con error. Agregados `f2sond_entail_n10`, `f2sond_sincita_n10`,
`f2sond_cruzado_n10`, los tres con `prompt_hash 3391f17ea61324a4` — comparables con el
RE-BASELINE. Coste de tarjeta USD 0,00081.

**Resultado:** el ataque no se materializó en ninguna de las 30. 0 fuga, 0 citas sin respaldo,
0 falsos bloqueos, 0 documentos fantasma. Verificado leyendo los 30 borradores completos:
se negó 10/10 a deducir el término de caducidad de una norma que no habla de plazos; con el
expediente vacío no afirmó ni una cifra; no ancló nada al documento equivocado y detectó por
su cuenta la trampa de la fecha imposible (norma fechada 65-67 años en el futuro), que ni
siquiera era parte del ataque diseñado.

**Lo que se construyó:** `harness.evidence_audit` (función pura) + `--exige-evidencia` en
`execution/aggregate_eval_runs.py`. Un agregado ahora declara cuántas corridas tienen texto
releíble, avisa cuando falta y reprueba si se le exige. Verificado en las tres capas: 6 checks
nuevos en `test_eval_harness.py` (67/67), reprobación real de `f2sond_entail_n10` señalando el
índice culpable, y aprobación de los dos agregados limpios. Salió de un defecto propio: el
agregado de la sonda de REVISIÓN HUMANA incluyó una corrida sin texto persistido y nada lo
advirtió.

**Errores propios de la sesión (3, ninguno llegó al entregable):** `Glob` con timeout de 20 s
(recurrente, ya documentado); un corte de archivo en PowerShell que copió el archivo entero
porque un `Select-String` fallido devuelve vacío y el índice se vuelve -1; y una regex de
análisis tan laxa que casi produce un falso hallazgo de "detector ciego". Los tres, con su
prevención, en APRENDIZAJES.md (reglas 52-54) y en la retrospectiva del vault
(`retrospective-2026-07-24-005`).

**Deuda declarada:** M-1 y M-2 (riesgo #81) — dos métricas cuyo número es correcto pero cuya
etiqueta induce una lectura falsa. Sin corregir a propósito: mueven cifras del baseline
publicado y son decisión de Pipe.

**Próximo:** Sesión Pipe A (6 salidas + 4 decisiones + M-1/M-2); referencia en nube (tope USD 30
aprobado) con RISK_CASES ×10 bajo `nube` + `--agentic-compare`, que es lo único ejecutable sin
Pipe y destraba la decisión sobre lectura agéntica por defecto; y el ítem 2 de la spec de F2.

## 2026-07-27/28 (sesión 51) — La Sesión Pipe A ejecutada: F2 cerrada y las 4 barreras del harness

**Qué pasó.** Pipe tomó en vivo las 7 decisiones que esperaban (`decisions.md` #45-#47) y se
construyó todo lo que dependía de ellas. Seis commits, todos pusheados: `656dc20` (N-1+M-1+M-2),
`99fb4a2` (afirmaciones negativas), `ba1fbde` (muro de citas quemadas), `ae42b96` (contaminación
entre expedientes), `6aaef70` (cierre de F2), `2c7ff04` (la puerta del banco en la interfaz) y
`cdc0f7c` (hallazgo del gate de bienvenida).

**Las tres de medición.** La fuga real del baseline pasa a **0/63** — la única marca de las 63
corridas guardadas era el falso positivo de «Ley 4137» (MIA nombrando una norma PARA decir que no
la reconoce). La abstención pasa de 0/30 a **29/29** en las sondas de suscripción tras recalibrar
el detector midiendo los 62 borradores reales. Y el panel deja de decir «Éxito de tarea» —que
medía «no se cayó» y se leía «acertó»— para decir «Turnos completados» + «Se negó correctamente».

**Las cuatro barreras del harness de litigio de Pipe, traducidas y graduadas.** Afirmaciones
negativas verificadas contra el documento COMPLETO (su caso del garante, convertido en control);
banco de citas quemadas (ÚNICO muro: la cita que el abogado demuestra falsa no vuelve a salir ni
con respaldo del corpus); contaminación entre expedientes (catálogo derivado de la propia base, no
cableado como el original); y «ninguna lección sin barrera» como regla de trabajo. Las tres
primeras nacen como AVISO por decisión de dureza: MIA va a manos de otros despachos, donde una
barrera mal afinada bloquea trabajo bueno.

**Dos defectos propios encontrados AL MEDIR, no al revisar:** (1) contar como contradicción
cualquier término presente en el documento hacía saltar el aviso en toda afirmación negativa
correcta —los términos del SUJETO están ahí por definición—, lo destapó un check de la propia
barrera nueva; (2) «ya estaba quemada» se decidía comparando marcas de tiempo, frágil por
construcción, ahora sale del dato que el UPSERT ya conoce.

**Deuda declarada:** la verificación VISUAL del botón nuevo y de los dos avisos NO se hizo. El
gate de bienvenida exige perfil del despacho y no se salta omitiendo pasos (regla 62). Pendiente
con dueño: `execution/seed_despacho_demo.py`.

**Próximo:** el sembrador de despacho de prueba (destraba toda verificación visual, incluida la
Fase 3 de bienvenida); caso de oro con expediente GRANDE; producto (instalador y bienvenida). De
Pipe: lectura de calidad de las 6 salidas y los dos trámites de terceros.
