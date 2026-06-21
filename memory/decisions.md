# Mia — decisions.md
# Decisiones arquitectónicas con razonamiento completo
# Última actualización: 2026-06-14
# (Estas decisiones NO se re-discuten — ver CLAUDE.md sección D)

---

## 1 · 2026-06-01 — LangGraph (sobre CrewAI / AutoGen)
**Decisión:** orquestación con LangGraph.
**Razonamiento:** ofrece `StateGraph` tipado, `AsyncPostgresSaver` para
checkpointing multi-tenant, e `interrupt()` nativo para HITL
(human-in-the-loop). CrewAI/AutoGen no cubren estos tres puntos juntos.

## 2 · 2026-06-01 — PostgreSQL + pgvector como store primario (sobre Pinecone)
**Decisión:** Postgres + pgvector es el store primario.
**Razonamiento:** RLS (Row-Level Security) por tenant es nativo en
Postgres; Pinecone no tiene RLS. Pinecone sigue soportado como store
externo **opcional**.

## 3 · 2026-06-01 — LiteLLM como gateway LLM
**Decisión:** todo el tráfico LLM pasa por LiteLLM.
**Razonamiento:** unifica Claude, GPT, Gemini, Ollama y MiniMax en un solo
endpoint OpenAI-compatible. El prefix caching con TTL de 1h ahorra ~75% en
*matters* largos.

## 4 · 2026-06-01 — SAT-Graph en Postgres puro (no Neo4j)
**Decisión:** el SAT-Graph se implementa en Postgres puro.
**Razonamiento:** el proyecto es SQL-first; Neo4j añadiría una dependencia
de infraestructura sin justificación para la escala actual.

## 5 · 2026-06-01 — Windows como plataforma de desarrollo principal
**Decisión:** desarrollo en Windows, Modo B (nativo).
**Razonamiento:** la laptop del fundador necesita acceso libre a Obsidian y
documentos. Modo A (Docker + WSL2) queda reservado para producción.

## 6 · 2026-06-01 — Core propio (no fork de Hermes)
**Decisión:** core propio adoptando patrones MIT de Hermes.
**Razonamiento:** Hermes es **referencia de código, no dependencia**. Se
adoptan sus patrones, no su base de código.

## 7 · 2026-06-01 — `call_llm(task="compression")` = claude-haiku siempre
**Decisión:** la tarea de compresión usa claude-haiku, nunca sonnet.
**Razonamiento:** coste/latencia para compresión de contexto.
**No cambiar sin documentar aquí** (memory/decisions.md).

## 8 · 2026-06-12 — voyage-law-2 como modelo de embeddings (1024 dims)
**Decisión:** los embeddings de Mia usan `voyage-law-2` (1024 dimensiones).
La columna pgvector es `vector(1024)`, no `vector(1536)`.
**Razonamiento:** voyage-law-2 supera a OpenAI text-embedding-3-large en
~23% en recuperación legal de documentos largos. 1024 dims produce índices
HNSW más livianos que 3-large (3072).
**Integración:** vía LiteLLM (`voyage/voyage-law-2`), consistente con la
decisión #3 (todo el tráfico LLM por LiteLLM). Fallback documentado:
`voyageai` SDK directo.
**Config:** `EMBED_MODEL=voyage-law-2`, `EMBED_DIM=1024`, `VOYAGE_API_KEY`
en `.env`.
**Revisitar:** evaluar `voyage-3-large` en Fase 3 al medir el retriever.

## 9 · 2026-06-13 — Checkpointing LangGraph + RLS (Módulo 1d)
2026-06-13 — Tablas de checkpoint LangGraph creadas por postgres (no mia_app)
vía migración. GRANT DML a mia_app. Aislamiento por thread_id={tenant_id}:{matter_id}
+ validación JWT en endpoints HITL. RLS de dominio (chunks, matters) sigue activo
vía GUC app.tenant_id. Patrón estándar LangGraph; subclasear AsyncPostgresSaver
descartado por fragilidad ante updates.

## 10 · 2026-06-13 — Posición de interrupt() en el grafo (Módulo 1d)
**Decisión:** `interrupt()` es la PRIMERA línea de `hitl_checkpoint_node`. El grafo
se pausa al ENTRAR al nodo (antes de procesar la decisión), emite `awaiting_review`,
y al reanudar `interrupt()` devuelve la decisión del abogado → `finalize_node`.
**Razonamiento:** patrón idiomático de LangGraph HITL; coincide con la descripción
del nodo 4 ("el nodo donde LangGraph hace interrupt()"). Resuelve la ambigüedad del
spec (la otra lectura era interrupt() al final de draft_node).

## 11 · 2026-06-13 — Coordinación SSE a través del interrupt (Módulo 1d)
**Decisión:** `interrupt()` parte el run en dos llamadas HTTP. `GET
/matters/{id}/stream` corre intake→analysis→draft y emite thinking→draft_ready→
awaiting_review, luego termina (run suspendido). `POST approve|reject|edit` reanuda
con `Command(resume=...)` y emite `finalizing→done` en la MISMA respuesta SSE.
**Razonamiento:** una acción = una respuesta; el cliente ve el cierre en la llamada
con que aprueba. La alternativa (POST→JSON y reabrir GET /stream) requería dos
conexiones y re-attach.

## 12 · 2026-06-13 — `tenant_settings` como config store por tenant (Módulo 1e)
2026-06-13 — tenant_settings como config store por tenant. Tabla nueva (no profiles)
para evitar colisión con ProfileManager in-memory (2a). config jsonb reutilizable
para futuros settings del despacho. RLS + GRANT DML a mia_app, migración por postgres.

## 13 · 2026-06-13 — ContextCompressor: resumen iterativo + anti-thrashing (Módulo 2c)
2026-06-13 — ContextCompressor adopta resumen iterativo (A) y anti-thrashing (B) de
Hermes. Resumen iterativo actualiza el resumen previo en re-compresiones en vez de
rehacerlo — protege contexto jurídico acumulado en matters largos. Anti-thrashing: si
las últimas 2 compresiones ahorraron <10%, no recomprime. Params locked intactos:
threshold=55%, protect_first_n=5, protect_last_n=30, compression→haiku.

## 14 · 2026-06-14 — Riesgo #11 cerrado por reframe (ContextCompressor NO se cablea al grafo)
El ContextCompressor NO se cablea al grafo LangGraph en este sprint.
Razón: los nodos `analysis_node`/`draft_node` arman prompts autocontenidos desde
`_last_user_message(state)` + documentos recuperados. No consumen `state["messages"]`
completo. Cablear el compresor hoy comprimiría un transcript que el LLM no usa →
plumbing inerte.
Además, `state["messages"]` usa reducer `operator.add` (append-only). Reemplazarlo por
lista compactada requiere cambiar el contrato del reducer — toca el gate 1d.
**Decisión:** el compresor vive en `agent/core.py::run_turn` (path de prueba y futuro
path de seguimiento conversacional). Cuando el grafo adopte historial creciente (Fase 3
o decisión de producto posterior), se reabre este ticket con spec propio.

## 15 · 2026-06-14 — ContextCompressor: el resumen va como role="user", no "system" (Riesgo #12)
El mensaje de resumen del ContextCompressor pasa de `role="system"` a `role="user"` con
prefijo `[RESUMEN DE CONTEXTO ANTERIOR]` (+ `SUMMARY_END_MARKER`).
**Razón:** Anthropic toma `system` como parámetro ÚNICO al tope del request; LiteLLM
hoistea todos los mensajes `role="system"` al inicio. Un resumen system insertado en medio
del historial perdería su posición entre cabeza (frozen_inicio) y cola (frozen_final) —
exactamente lo que Hermes evita usando un rol de turno (user/assistant). El bug era latente
también en el path actual (`run_turn`), no solo a futuro en el grafo.
**Alcance:** cambio de spec sobre 2c (que fijaba role="system"). Gate
`test_context_compressor.py` actualizado (`out[5]["role"]=="user"`) → 22/22. NO se insertó
mensaje de ack assistant: el `SUMMARY_END_MARKER` basta para desambiguar y Anthropic fusiona
mensajes consecutivos del mismo rol. Cierra el Riesgo #12.

## 16 · 2026-06-14 — SAT-Graph como corpus jurídico COMPARTIDO (excepción al patrón por-tenant)
**Decisión:** las tablas del SAT-Graph (`legal_norms`, `norm_relations`, `jurisprudence`)
son CORPUS COMPARTIDO entre todos los tenants, NO datos por-tenant. No llevan `tenant_id`.
RLS habilitado con política ABIERTA `USING (true) WITH CHECK (true)`; lectura pública para
mia_app; escritura (curaduría) restringida a mia_app por GRANT.
**Razonamiento:** el corpus normativo y jurisprudencial de Colombia es el mismo para todos
los despachos; duplicarlo por tenant sería absurdo y rompería el ahorro. Las normas y
sentencias son públicas.
**Matiz RLS (importante):** el spec pedía "política SELECT + escritura solo por GRANT". Bajo
`NOBYPASSRLS`, una tabla con RLS habilitado y SIN política permisiva para el comando RECHAZA
la escritura — así mia_app no podría ni siquiera ingerir el corpus. Por eso la política
incluye `WITH CHECK (true)` (una sola policy abierta `FOR ALL`). El "solo mia_app escribe" se
sostiene por GRANT (no existe otro rol no-superusuario). No se usa `FORCE` (el dueño es
`postgres`, superusuario, que ignora RLS de todos modos).
**Acceso:** `SATGraph` usa `pool.connection()` (sin fijar GUC). NO debilita el aislamiento:
las tablas por-tenant siguen fail-closed sin `app.tenant_id`; una conexión sin-GUC solo ve el
corpus compartido. Documentado en `architecture/rls_isolation.md`.

## 18 · 2026-06-14 — Playbooks persisten en DB; PlaybookManager pasa a DB-backed (Módulo 3b)
**Decisión:** se añade persistencia en DB para los playbooks. El Módulo 2b
(`PlaybookManager`) se construyó **in-memory** (dataclasses frozen, sin tabla). Para que el
Curator (3b) sea funcional y los playbooks sobrevivan reinicios, se crea la tabla `playbooks`
(migración 005) y `PlaybookManager` gana un backend de DB.
**Interfaz pública intacta:** los métodos sync existentes (`register`, `render_index`,
`get_content`, `activate`, `render_active`, `reset`, …) NO cambian; con `pool=None` el manager
sigue 100% in-memory (el gate 2b `test_playbook_manager.py` queda verde sin tocarlo). Se AÑADEN
métodos async DB-backed (`register_playbook`, `get_index`, `get_playbook`, `mark_used`,
`list_active`) que solo actúan cuando se construye con `PlaybookManager(pool=…, tenant_id=…)`.
**Tabla `playbooks`** (migración 005, RLS por-tenant estándar): id, tenant_id, title, summary,
applies_when, content, status (active|archived|draft), usage_count, last_used_at,
embedding vector(1024) (para similitud del Curator), metadata jsonb, created/updated;
`UNIQUE(tenant_id, title)`; HNSW en embedding + BTREE en (tenant_id, status); GRANT DML a mia_app.
**Curator:** opera sobre la tabla real — `find_candidates` por similitud coseno con el operador
`<=>` de pgvector (`1 - (a.embedding <=> b.embedding) > 0.85`), `consolidate` con
`call_llm(task="curator")`, `prune` por `last_used_at` > 90 días.
**Task LLM:** se añade `"curator": "claude-sonnet"` a `llm._TASK_MODELS` (el alias `claude-sonnet`
resuelve a `anthropic/claude-sonnet-4-6` en `litellm_config.yaml`; NO se usa el id crudo, que
daría 404 latente). `auxiliary_client.TASK_MODELS` es el MISMO dict por referencia.
**Pendiente (riesgo):** ningún caller llena la tabla `playbooks` todavía (el PlaybookManager
in-memory no tenía persistencia y nada más lo usa); el seeding/onboarding de playbooks por
despacho es trabajo futuro.

## 19 · 2026-06-14 — Trazas enriquecidas (mia.trace.v2) con señales HITL (Módulo 3e)
**Decisión:** las trazas JSONL (`mia.trace.v1`) ganan 4 campos OPCIONALES para hacer detectables
las señales del Feedback processor. Las trazas reales solo guardaban
input/output/model/tokens/latency/timestamp — NO la decisión HITL, ni el borrador original vs.
final, ni los documentos citados — así que las señales del spec (HITL_REJECTION, HITL_EDIT,
NO_RESULT) NO eran detectables. Se enriquece la traza EN EL ORIGEN (`finalize_node`).
**Campos nuevos (default None/[]):** `hitl_outcome` ('approved'|'rejected'|'edited'),
`draft_original` (borrador pre-edición), `draft_final` (texto final), `retrieved_doc_ids`
(list[str] de ids de documentos recuperados; [] = NO_RESULT). `schema` sube a `mia.trace.v2`
SOLO cuando la traza trae campos nuevos; sin ellos sigue siendo `mia.trace.v1` (compat hacia
atrás; el processor trata ausencia = None).
**Por qué no rompe gates:** `test_trace_capture` (2d) y `test_hitl_flow` (1d) usan `issubset`
para los campos y cuentan 1 traza por turno → campos extra no los afectan; sigue habiendo UNA
línea de traza por finalize.
**Origen de los datos:** `finalize_node` ya tiene `hitl_decision`/`final_status` en
`state.metadata` y el borrador pre-edición en `state["draft"]`; `retrieved_doc_ids` se DERIVA de
`state["documents"]` (ya existe; cada doc trae `id`) — NO se añadió campo nuevo a MatterState ni
se tocó el reducer.
**Señales (processor):** HITL_REJECTION = `hitl_outcome=='rejected'`; HITL_EDIT =
`hitl_outcome=='edited'` Y diff(draft_original, draft_final) > 20%; NO_RESULT = `retrieved_doc_ids`
vacío/ausente. Umbral: mínimo 2 ocurrencias del mismo patrón para proponer.
**Trazas procesadas:** watermark por (tenant_id, trace_date) en tabla
`processed_traces_watermark` (no se mutan los JSONL append-only ni se marca traza por traza).
**El processor PROPONE, no aplica:** las propuestas van a `feedback_proposals` con
`status='pending'` para revisión del abogado (Pantalla 4, Fase 3). Task LLM: `call_llm(task=
"curator")` (ya existe desde 3b, decisión #18).

## 20 · 2026-06-14 — Fase 3 se divide en dos sesiones (backend / frontend)
**Decisión:** la Fase 3 (UX) se parte en dos. **Sesión 14 (esta):** superficie `/api/*`
completa + persistencia de perfil + exposición del borrador + parser PDF/Word. Gate
`test_ux.py` = endpoints de backend con TestClient. **Sesión 15 (siguiente):** scaffold
Next.js 14 + las 5 pantallas, contra endpoints ya verificados.
**Razón:** `frontend/` NO existe (el Módulo 0 solo construyó backend + DB), faltan ~12 de los
15 endpoints, y `ProfileManager` es in-memory sin tabla (mismo patrón que PlaybookManager en
3b/decisión #18). Construir el frontend sin un backend verificado repetiría el error de premisa.
**Premisas del spec corregidas:** (a) `frontend/` se scaffoldeará desde cero en S15, no "ya
existe"; (b) las rutas reales eran `/matters/*` sin prefijo — la nueva superficie va bajo
`/api/*` y se MANTIENEN las `/matters/*` legacy (no romper el gate 1d `test_hitl_flow`); (c) la
auth JWT ya existe (no "sin auth"): el frontend usará un token de desarrollo (deuda técnica S15);
(d) el perfil estructurado del despacho se persiste en una tabla nueva `firm_profiles` (distinta
de los perfiles de texto in-memory abogado/despacho de 2a, que alimentan la costura L9 del prompt).
**Wiring de propuestas (cierra parte del Riesgo #21):** `POST /api/proposals/{id}/apply` crea o
actualiza un playbook desde la propuesta y la marca `applied`; `/ignore` la marca `rejected`.
**§G en las respuestas:** los endpoints `/api/*` no exponen jerga (nombres de job, modelos,
conectores → etiquetas amigables; nunca pgvector/tenant_id/embedding/hitl/langgraph/tool_call).

## 17 · 2026-06-14 — knowledge_chunks: tabla separada para conocimiento del despacho (Módulo 3c)
**Decisión:** los chunks de Obsidian (conocimiento del despacho) van en una tabla NUEVA
`knowledge_chunks`, no en `documents`/`chunks`.
**Razón:** `documents.matter_id` es NOT NULL — las notas de Obsidian no pertenecen a un asunto
sino al despacho. Hacer `matter_id` nullable rompería la invariante que asumen el RLS y el
retriever actuales (`retrieval.py` acota por `documents.matter_id`). `knowledge_chunks` es la
tabla base para todo conocimiento del despacho que NO es un expediente: vault Obsidian,
plantillas, jurisprudencia local, notas manuales.
**Forma:** `knowledge_chunks(id, tenant_id, source='obsidian' default, source_path, chunk_index,
heading_path, content, embedding vector(1024), content_tsv GENERATED 'spanish', metadata jsonb,
created_at, updated_at)`, `UNIQUE(tenant_id, source, source_path, chunk_index)`. RLS por tenant
(patrón estándar, igual que `chunks`), GRANT DML a `mia_app`, HNSW en embedding + GIN en
content_tsv. Migración 004 (con `obsidian_file_hashes`). NO toca el esquema del Módulo 0
(documents/chunks intactos → `test_rls` sin cambios).
**Correcciones de premisa del spec 3c (decisión #17):** (C1) escribir en `knowledge_chunks`, no
`documents`; (C2) embeddings por `embeddings.embed_texts()` (librería LiteLLM → voyage-law-2),
NO `call_llm(task="embedding")` — ese task no existe; consistente con Riesgo #4; (C3)
`cron/scheduler.py` no existía (1e construyó el Agent Hub) → se crea un scheduler mínimo propio
sin dependencia externa.

## 21 · 2026-06-14 — SOUL.md + entrevista de onboarding (Módulo 5 · cierre)
**Decisión:** el SOUL.md (identidad del agente por despacho) se construye con una entrevista de
**19 preguntas** (Doc 4, 5 bloques) y se guarda como ARCHIVO en `$MIA_HOME/soul_{tenant_id}.md`
(+ `…responses.json`), no en DB. `call_llm(task="soul")=claude-sonnet` (la identidad importa)
rellena el template de 9 secciones; los campos sin respuesta quedan como placeholder (no se
inventan datos). 3 endpoints en `/api/onboarding/*` (questions/complete/status); el status se
deriva de la existencia/mtime del archivo → **sin migración DB**.
**`$MIA_HOME`:** nuevo en `config.py`; el `.env` ya traía `MIA_HOME=.\mia-data`. Una ruta
relativa se ancla a `PROJECT_ROOT` (no depende del CWD); default bajo `mia-data/` (gitignored),
estado de instancia por despacho como las API keys. Se lee como atributo en cada uso (los tests lo
apuntan a un tempdir).
**Wiring del SOUL al turno (alcance "Grafo + prompt_builder", elegido por el usuario):** el spec
A4 solo conectaba el prompt_builder, pero el turno REAL corre por el grafo, que no consumía
`soul_snapshot` (mismo patrón del Riesgo #11). Se decidió cablear AMBAS rutas:
(1) `initial_state()` carga `soul_snapshot` desde `$MIA_HOME` y `graph.py::_system_with_soul`
antepone la identidad en analysis/draft/edit; (2) `MiaAgent.__post_init__` carga el SOUL.md en
`self.identity` (Capa 1). Todo **None-safe**: sin archivo → comportamiento idéntico → gates 1a/1b/
1d intactos. NO se tocó `prompt_builder.py` (la Capa 1 ya leía `agent.identity`). Esto CIERRA en la
práctica el hueco de la costura `soul_snapshot` (antes inerte).
**Premisas del spec corregidas:** (a) el Doc 4 NO estaba en el repo → el usuario lo entregó
completo y es la fuente exacta; (b) el spec decía "18 preguntas" pero el Doc 4 trae **19** (la 19ª,
triad_mode, es opcional) → se implementaron las 19 con conteo dinámico; (c) `$MIA_HOME` no existía
en `config.py` → se añadió; (d) `_TASK_MODELS` no tenía `"soul"` → añadido.
**Imports diferidos:** `state.py`/`core.py` importan los helpers de `onboarding.soul_interview`
DENTRO de la función (no al top) para evitar ciclos y no arrastrar el cliente LLM al grafo.
**Gate:** `execution/test_e2e.py` (25/25) — el GATE FINAL del proyecto.

## 22 · 2026-06-20 — Sistema completamente horizontal
**Decisión:** ningún módulo nuevo tiene conocimiento jurídico hardcodeado. El wiki, los skills y el SOUL.md son el único lugar donde existe conocimiento específico — y lo escribe el uso, no el código.

**Razonamiento:** Mia debe servir para cualquier jurisdicción, país, área del derecho, idioma, corte, norma o tipo de proceso. El producto es el recipiente; cada despacho lo llena con onboarding, documentos, asuntos aprobados, playbooks y correcciones. Por eso WikiManager, GEPA, Dreams, conectores y onboarding se implementan con prompts y controles genéricos.

**Implicación:** las opciones fijas de país/área/cliente/cortes/herramientas se retiran del onboarding. Los módulos nuevos solo pueden guardar o recuperar conocimiento específico si ese conocimiento llegó desde el tenant: SOUL.md, wiki por tenant, trazas aprobadas, playbooks o documentos conectados.

## 23 · 2026-06-20 — Todos los task models a mia-local
**Decisión:** todos los task models de `_TASK_MODELS` (`backend/mia/agent/llm.py`) usan `mia-local`.

**Razón:** cuenta Anthropic sin créditos en desarrollo. Todos los tasks usan mia-local (Ollama qwen2.5:32b). Revertir a Claude cuando se restauren los créditos.

**Implicación:** anula parcialmente la invariante de la decisión #7 (`compression` ya no es claude-haiku, ahora mia-local), pero `compression` SIGUE en `_LOCKED_TASKS` — un `model` explícito se ignora, solo cambió el destino fijo. `verification`/`vision` dejan de usar claude-sonnet; `title_generation`/`session_search`/`web_extract` dejan de usar claude-haiku. Tests de gate actualizados a mia-local: `test_agent_core.py`, `test_context_compressor.py`, `test_prompt_builder.py`.
