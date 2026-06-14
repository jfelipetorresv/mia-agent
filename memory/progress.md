# Mia — progress.md
# DIARIO DE OBRA · qué se construyó · errores · tests · resultados
# Última actualización: 2026-06-14

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
