# Mia — decisions.md
# Decisiones arquitectónicas con razonamiento completo
# Última actualización: 2026-07-17 (sesión 48)
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

## 24 · 2026-06-21 — Packs de jurisdicción instalables (refina la Decisión #22)
**Decisión:** el código es AGNÓSTICO de jurisdicción. Los datos de referencia jurisdiccional
(festivos, recesos, formatos de ID, marcadores documentales, catálogo de términos, estilo de cita)
viven en **paquetes de jurisdicción instalables** bajo `backend/mia/jurisdiction/packs/{code}/`
(`pack.py` los carga; `GenericPack` es el fallback de modo genérico). El conocimiento del despacho
(voz, métodos, fuentes) sigue viniendo del tenant (SOUL/wiki/playbooks).
**Razón:** la #22 ("cero conocimiento hardcodeado") describe bien el eje del despacho pero se
extralimita al eje de la jurisdicción: no se le puede pedir a un despacho que teclee su calendario
procesal (terceriza el riesgo de malpractice). Dos ejes: Jurisdicción (Pack, público, compartido por
país) + Despacho (Eje 2). Mapea al negocio: Plataforma + Packs (foso por mercado) + Capa del despacho.
**Modo genérico** como cuña de venta: vender hoy en cualquier país; el pack verificado es upsell.
**Cardinal:** un pack con `verified=false` NO se presenta como autoridad verificada.

## 25 · 2026-06-21 — Corpus SAT-Graph particionado por jurisdicción (modifica la Decisión #16)
**Decisión:** el corpus sigue COMPARTIDO entre despachos del MISMO país, pero PARTICIONADO entre
países. `legal_norms`/`jurisprudence` llevan `jurisdiction`; `search_norms`/`search_jurisprudence`
ACOTAN por `jurisdictions` y RECHAZAN búsquedas sin jurisdicción salvo `admin=True` (curaduría).
Migración `011`: unique de `legal_norms` pasa a `(jurisdiction, norm_number, issuing_body,
effective_date)` — el `effective_date` habilita el **versionado temporal** (antes el upsert
sobrescribía y destruía la historia → imposible "norma vigente a la fecha de los hechos").
`jurisprudence` gana columna `jurisdiction` + unique `(jurisdiction, decision_number, court)`.
**Razón:** la #16 (corpus global sin tenant_id) era correcta para un país; para multi-país es una
fuga suave (un despacho mexicano vería normas colombianas como autoridad). Default canónico `co`.
Autoridad persuasiva cross-border: opt-in `include_persuasive` (pendiente; documentado).

## 26 · 2026-06-21 — Ruteo de modelo por tier: nube (calidad) vs soberano (local) [validación 0.A]
**Decisión:** las tareas con contenido jurídico citable (análisis, investigación, verificación,
curator, soul, extracción de hechos) van a **`claude-sonnet` en el tier NUBE**; `mia-local`
(qwen2.5:32b) queda reservado al **tier SOBERANO** (despachos que exigen todo local), con
advertencia explícita de menor disciplina de citas y HITL más estricto.
**Evidencia (validación directa, 2026-06-21, créditos Anthropic restaurados):** en un caso de
arrendamiento de vivienda urbana (rige **Ley 820 de 2003**), qwen **FABRICÓ** "art. 875 y 876 del
Código Civil" con texto entrecomillado falso y régimen equivocado, **sin marcar [VERIFICAR]** pese
a la instrucción explícita → viola la regla cardinal del producto. sonnet citó correctamente Ley
820/2003 art. 22 y CGP arts. 384-388. Latencia: sonnet 4-11s vs qwen 60-201s (6-19× más lento;
análisis = 3.4 min). En redacción sin citas qwen es aceptable; en hechos omitió una parte.
**Implementación:** NO revertir `_TASK_MODELS` a sonnet de forma global (rompería 3 gates puestos a
mia-local por la #23 y el proxy está caído). El ruteo va **por tenant** vía la política de modelo
de la **Fase 0.4** (`ContextVar` + `tenant_settings.config['model_policy']`): `nube` = calidad por
defecto; `soberano` = `mia-local`. El rojo de `test_curator` se cierra al implementar 0.4.
**Implicación:** revierte el espíritu de la #23 (ya hay créditos) pero lo hace configurable, no
hardcodeado. mia-local pasa de "parche por falta de créditos" a "tier soberano de producto".

## 27 · 2026-07-01 — Motor por SUSCRIPCIÓN (CLI de Claude Code) + política de modelo por tenant [CP2]
**Decisión:** Mia puede usar la SUSCRIPCIÓN de Claude Code del abogado (CLI `claude` en modo
headless: `-p --output-format json --max-turns 1`, sin herramientas `--tools ""`, sin MCP
`--strict-mcp-config`, sin settings del usuario `--setting-sources project`, cwd=$MIA_HOME) como
cerebro principal — **sin billing por API**. Tres políticas por tenant en
`tenant_settings.config['model_policy']`, resueltas por un `ContextVar` en `agent/llm.py`
(implementa la Fase 0.4 anticipada en la decisión #26): **`suscripcion`** (default) →
main/curator = `cli-claude`→`claude-sonnet`→`mia-local`, auxiliares y compression =
`cli-claude-haiku`; **`nube`** → `claude-sonnet`→`mia-local`, compression = `claude-haiku`
(restaura la decisión #7 — la clave de Anthropic volvió a funcionar, verificado 2026-07-01);
**`soberano`** → todo `mia-local`. El middleware fija la política por request (caché TTL 60s);
los crons por tenant (curator/feedback/gepa/dreams) la fijan con `llm.tenant_model_policy`.
`compression` sigue en `_LOCKED_TASKS`: un `model` explícito no la cambia en ninguna política.
El abogado la elige en `/settings/model-policy` con etiquetas sin jerga: "Mi suscripción
(recomendado)" / "Nube" / "Todo en mi equipo".
**Razón:** el tier suscripción elimina el costo por token del despacho fundador (ya paga la
suscripción), mantiene calidad Claude para contenido jurídico citable (#26) y deja la nube y lo
local como red de seguridad automática (cadena de fallback H.5, mismo error_classifier).
**Nota de emergencia:** `mia-local` se remapeó a `ollama/qwen2.5:7b-instruct` porque
qwen2.5:32b fue removido de la máquina — restaurar el 32b en litellm_config.yaml si se
reinstala (el 7b es fallback de emergencia, menor disciplina de citas aún que el 32b).
**Gate:** `execution/test_model_policy.py` (offline: subprocess/which mockeados).
**Ajuste (revisión CP2, 2026-07-01):** en `suscripcion`, `compression` = `cli-claude-haiku`→`claude-haiku` (red de seguridad barata si el CLI falla; sigue bloqueada ante `model` explícito).
**Ajuste de calidad (smoke vivo CP2, 2026-07-01):** dos correcciones medidas en vivo sobre el
proveedor CLI: (1) Claude Code trae una persona de asistente de código que exige respuestas
ultra-concisas — un borrador legal salía de 148-1.900 chars; `subscription_llm` ahora pasa un
`--system-prompt` ESTÁTICO (persona de Mia, constante sin contenido del tenant — el system del
tenant sigue por stdin, invariante BatBadBut intacto) que lo anula. (2) El modelo default del
plan es grande y lento escribiendo documentos extensos (>300s → timeout); sin hint explícito el
CLI usa ahora `MIA_CLI_MODEL` (default `sonnet`). Resultado medido: turno completo en 176s con
borrador de 19.098 chars, citas correctas (fuero de maternidad, art. 239 CST) y 47 [VERIFICAR],
todo por suscripción (el proxy no registró ninguna llamada de completions).

## 28 · 2026-07-01 — MODO ASISTENTE: una sola Mia, conversación libre fuera del asunto [CP-B1]
**Decisión:** Mia deja de vivir SOLO dentro de un expediente. El nuevo modo asistente
(`backend/mia/assistant/core.py` + router `/api/assistant/*`) le da al abogado una conversación
libre — agenda, recordatorios, investigación, el despacho — con la MISMA alma e infraestructura:
**una sola Mia**, no un segundo agente. Piezas: (1) identidad = SOUL.md del tenant (capa L1 del
prompt_builder) + comunicación sin jerga (L5) + una instrucción propia (asistente personal;
NUNCA da por definitivo un plazo procesal sin marcarlo [VERIFICAR] para el abogado);
(2) **historial persistente por tenant + usuario** en `assistant_conversations` /
`assistant_messages` (015_assistant.sql, RLS fail-closed estándar); (3) el **ContextCompressor
queda cableado a su propósito original** — historial creciente: si la conversación supera el 55%
de la ventana, se comprime ANTES de llamar al modelo; (4) motor = `call_llm(task="main")` con la
política del tenant (CP2/#27) que ya fija el middleware.
**v1 SIN SSE:** el proveedor por suscripción (CLI de Claude Code) responde en bloque, no
streamea; el endpoint devuelve JSON completo. Telegram (CP-B2) tampoco necesita streaming.
**Herramienta v1 acotada, sin framework:** si el mensaje pregunta por asuntos/borradores
pendientes (keywords), se consulta `matters` bajo RLS y se inyecta un bloque
"=== ESTADO ACTUAL DE TUS ASUNTOS ===" en el mensaje que ve el modelo (el persistido es el
original). Las **herramientas reales llegan con CP-B4**; la escritura de memoria a la wiki del
despacho llega con CP-C2 (TODO en core.py).
**Razón:** es la base del asistente personal estilo ClaudeClaw (Pilar B) que se conecta a
Telegram en CP-B2, sin duplicar identidad, memoria ni política de modelo.
**Gate:** `execution/test_assistant.py` (DB real, LLM mockeado: 32 checks — persistencia,
historial, RLS entre tenants, compresión, bloque de asuntos, 404 fail-closed).
**Refuerzo post-revisión (2026-07-01):** el ContextCompressor se crea NUEVO por turno dentro de
`chat()` (nunca compartido entre requests — su resumen iterativo en memoria mezclaría contexto
de despachos distintos: aislamiento en memoria además del RLS); si la compresión falla, el turno
NO se cae: truncado duro sin LLM (primeros 2 + últimos 30 mensajes con marcador) y continúa.

## 29 · 2026-07-01 — CANAL TELEGRAM: bot privado single-chat, puente → API con JWT, opt-in [CP-B2]
**Decisión:** Mia llega al celular del abogado por Telegram con un puente standalone estilo
ClaudeClaw (`backend/mia/channels/telegram_bridge.py`, `python -m mia.channels.telegram_bridge`,
arranque: `scripts/start_telegram.ps1`). Arquitectura: el puente NO toca la DB ni el motor —
cada mensaje va como POST a `/api/assistant/chat` (CP-B1) con un JWT obtenido vía
`/api/auth/login` (MIA_BRIDGE_EMAIL/PASSWORD; re-login automático ante 401), así RLS y la
política de modelo aplican idéntico al frontend. **Seguridad single-chat:** solo responde al
chat_id de `TELEGRAM_ALLOWED_CHAT_ID`; cualquier otro chat se IGNORA por completo (ni respuesta;
solo se loguea el chat_id — NUNCA contenido del abogado en logs, solo métricas/ids). `/apagar`
desde el chat autorizado detiene el puente (frase de emergencia); `/nueva` resetea el hilo
(conversation_id en memoria). **Resiliencia:** timeout HTTP 300s (el motor por suscripción tarda
1-3 min), errores de red/API → mensaje amable ("Mia está teniendo un problema técnico...") y el
loop sigue; polling con reconexión y backoff. Respuestas > ~3900 chars → archivo .md adjunto
(límite de Telegram ~4096). **Opt-in:** NO está en start_all.ps1; se activa completando las
variables comentadas en .env (guía sin jerga: `docs/telegram-setup.md`). Dependencia:
`python-telegram-bot~=21.0` (~=, no está en los pins críticos del Riesgo #32; gate de pins
verificado 9/9 tras instalar). La lógica es inyectable (MiaClient con HTTP falso, TelegramBridge
con callbacks) — python-telegram-bot solo se importa al arrancar el bot real.
**Razón:** el abogado necesita a Mia fuera del escritorio sin abrir superficie nueva de ataque:
un solo chat autorizado, sin datos en el bot, todo pasa por el API autenticado.
**Gate:** `execution/test_telegram_bridge.py` (22 checks, TODO offline/mockeado: config faltante
amable, chat no autorizado ignorado, POST correcto con Bearer, hilo persistente + /nueva,
adjunto .md, re-login ante 401, /apagar, errores de red sin tumbar el loop, cero contenido en logs).

## #30 — 2026-07-01 · Conector de carpetas de trabajo (disco local + nubes espejo) con allowlist fail-closed de dos capas

**Decisión.** Mia conoce las carpetas de trabajo del abogado — disco local, OneDrive y
Google Drive — leyendo las carpetas ESPEJO de escritorio que esos servicios ya mantienen
en Windows (no APIs de nube en v1: sin OAuth, sin credenciales nuevas, sin superficie de
red adicional). La indexación calca el patrón probado de Obsidian (decisión #17): hash
sha256 incremental por archivo, chunking (encabezados para .md, troceo con overlap para
.txt/.pdf/.docx vía extract_text), embeddings voyage-law-2 en batch por la librería
LiteLLM, y persistencia en `knowledge_chunks` con `source = 'local:<source_id>'` para
distinguir el origen sin tocar el esquema existente.

**Allowlist fail-closed de DOS CAPAS (privacidad primero).** Mia NUNCA escanea nada que
el despacho no haya registrado explícitamente en `local_folder_sources` (migración 016,
RLS fail-closed estándar):
1. **Al registrar** (`validate_source_path`): se rechazan rutas inexistentes, raíces de
   unidad (C:\, D:\) y directorios de sistema (Windows, Program Files, AppData, ...);
   la ruta se guarda ya resuelta (sin symlinks ni `..`).
2. **Al sincronizar**: la raíz se re-resuelve y re-valida en cada corrida, y cada archivo
   se resuelve con `Path.resolve()` — si su ruta real apunta fuera de la carpeta
   registrada (symlink de escape), se omite con log.
Límites defensivos: archivos > 20 MB se omiten; máximo 2000 archivos por sincronización.

**Alcance v1.** `kind = 'knowledge'` únicamente: todo lo indexado alimenta el
conocimiento general del despacho (`knowledge_chunks`). La clasificación de carpetas de
EXPEDIENTES (`kind = 'matters'`, que exigiría mapear archivos a asuntos concretos) queda
para una fase posterior — la columna `kind` ya lo deja preparado.

**Piezas.** Migración `016_local_folders.sql` (+ `execution/init_local_folders.py`),
conector `backend/mia/connectors/local_folders.py` (LocalFolderSync, detect_cloud_folders,
register/list/disable_source), router `/api/folders/*` (detected / registrar / deshabilitar
/ sync en segundo plano), job diario `sync_local_folders_all_tenants` en el scheduler
(hereda el Riesgo #15: la enumeración de tenants usa conexión admin, igual que Obsidian),
y gate `execution/test_local_folders.py`.

**Deshabilitar = olvidar.** Al quitar una carpeta (`DELETE /api/folders/{id}`) se borran
de inmediato sus chunks y hashes: el contenido deja de estar en el conocimiento de Mia
sin esperar al siguiente sync (re-registrarla la re-indexa completa).

**Refuerzos post-revisión (2026-07-01, misma fecha).** Tras revisión independiente se endurecieron tres puntos: (1) PRIVACIDAD — los directorios de sistema (_FORBIDDEN_PARTS: Windows, AppData, ProgramData, ...) se excluyen también durante el descenso recursivo del scan, no solo al validar la raíz (registrar C:\Users\<usuario> ya no puede arrastrar AppData a embeddings); (2) SIN PÉRDIDA DE CONOCIMIENTO — el límite de 2000 pasó a ser una ventana SOLO sobre archivos nuevos/cambiados (pasada previa barata de hashes); los diferidos quedan sin hash y se retoman en la corrida siguiente, y si la enumeración se trunca (tope duro MAX_SCAN_FILES=50000) NO se poda nada (ni chunks ni hashes) en esa corrida; (3) UNIQUE (tenant_id, path, kind) en local_folder_sources a nivel de DB, con register_source atómico vía ON CONFLICT. Gate ampliado a 39/39 checks (test_local_folders.py) y test_obsidian_sync.py 22/22 sin regresión.

## #31 — 2026-07-01 · El conocimiento del despacho entra al análisis (CP3 · cierre del Riesgo #16)

**Decisión.** Mia usa el conocimiento del despacho (`knowledge_chunks`: notas de Obsidian
+ carpetas de trabajo, decisiones #17/#30) al DIAGNOSTICAR. `intake_node` lo recupera con
`retrieve_knowledge_rrf` — el MISMO patrón RRF híbrido (vector HNSW + FTS GIN, k=60) que el
retriever del expediente, pero sobre `knowledge_chunks` y SIN filtro de asunto, porque es
conocimiento TRANSVERSAL del despacho; el aislamiento entre despachos lo da RLS fail-closed
bajo `tenant_connection`, igual que siempre. Top_k = 4 notas.

**Cero costo extra de embeddings.** El vector de la consulta se REUSA: si el asunto tiene
documentos, el mismo embedding del mensaje sirve para expediente y knowledge; si no los
tiene, se embebe SOLO cuando el tenant sí tiene conocimiento indexado (`knowledge_exists`,
un EXISTS barato). Tenant sin knowledge → comportamiento idéntico a antes (cero llamadas
a Voyage y prompt byte a byte igual).

**Presupuesto 15% y jerarquía de fuentes.** En `analysis_node` las notas entran en una
sección claramente separada del user prompt — "Conocimiento del despacho (notas y métodos
internos — orientan el método, NO sustituyen la fuente normativa; mantén la regla
[VERIFICAR])" — con presupuesto DURO ≤15% de `MIA_CONTEXT_WINDOW` (estimate_tokens; las
notas que exceden se truncan con shrink_text y las sobrantes se omiten). La regla
[VERIFICAR] queda intacta: las notas orientan el método, jamás sustituyen la norma o la
sentencia como fuente.

**Knowledge se recorta PRIMERO.** En el rescate de CONTEXT_TOO_LONG (CP1, Riesgo #33) la
primera reducción del analysis vacía el knowledge (queda `KNOWLEDGE_TRIMMED_MARKER`) y deja
los documents INTACTOS si con eso el prompt ya cabe; solo si aun así excede se recortan
también los documents. Razón: la evidencia del expediente es insustituible; el método del
despacho es orientación prescindible bajo presión de contexto.

**Compatibilidad.** `MatterState.knowledge: list[dict]` con `total=False` → los checkpoints
viejos sin el campo siguen siendo válidos (los nodos leen `state.get("knowledge") or []`).

**Gate:** `execution/test_retrieval_knowledge.py` (30/30, DB real + embeddings/LLM
mockeados): relevancia RRF, aislamiento A/B estilo test_rls (ni en retrieve ni en prompt),
prompt idéntico sin knowledge (byte a byte, cero embeddings), presupuesto ≤15% con notas
gigantes, y shrink knowledge-antes-que-documents. Regresión: test_context_recovery 34/34 ·
test_hitl_flow 19/19 · test_rls 12/12.

**Refuerzos post-revisión (2026-07-01, revisión independiente CP3).** (1) SEGURIDAD DEL
PROMPT — las notas del despacho entran al analysis DELIMITADAS con fencing explícito
(`<<<NOTA n · ruta>>> … <<<FIN NOTA n>>>`) y la instrucción de la sección ordena NO
obedecer instrucciones contenidas dentro de las notas ni tratarlas como órdenes del
sistema (anti prompt-injection: son texto de terceros insertado en el prompt).
(2) MARGEN DEL SHRINK — el early-exit "quitar solo knowledge" ya no compara contra el
100% de la ventana sino contra el 85% (`SHRINK_EARLY_EXIT_FRACTION`): el estimador
offline subestima el español legal y el modelo necesita espacio para responder; si con
solo quitar knowledge la estimación queda por encima del 85%, los documents se recortan
TAMBIÉN en la misma pasada (la compresión es una sola por turno y no puede quemarse en
una reducción insuficiente). (3) `metadata.knowledge_retrieved` se escribe siempre que
el tenant tenga conocimiento indexado (aunque el turno recupere 0 notas) y se LIMPIA si
no lo tiene — sin conteos huérfanos de turnos previos. Gates: test_retrieval_knowledge
ampliado a 35/35 · test_context_recovery 34/34 · test_hitl_flow 19/19 sin regresión.

## #32 — 2026-07-01 · Vault de Obsidian BIDIRECCIONAL: Mia escribe su memoria visible SOLO bajo Mia/ (CP-C2, Pilar C)

**Decisión.** La memoria de Mia debe vivir donde el abogado la vea: su vault de Obsidian.
Hasta CP-C1 el vault era SOLO lectura (vault → knowledge_chunks vía obsidian_sync,
decisión #17). CP-C2 agrega la vía de VUELTA: la wiki interna (conceptos del second
brain) y los reportes semanales de Dreams se exportan como notas .md normales al vault,
bajo la subcarpeta `Mia/` (`Mia/conceptos/{slug}.md`, `Mia/reportes/{fecha}-{slug}.md`).
La WIKI INTERNA (mia-data/wiki) sigue siendo la FUENTE DE VERDAD; el vault es el espejo
visible — si el vault falla (disco desconectado, ruta inválida, sin permisos), el export
se registra en el log y la wiki interna NO se pierde ni el flujo se interrumpe.

**Regla anti-colisión dura (el vault es del abogado).** `VaultWriter`
(`backend/mia/connectors/vault_writer.py`) SOLO escribe bajo `{vault}/Mia/`:
1. `vault_path` se valida contra OBSIDIAN_VAULT_PATH/OBSIDIAN_VAULT_ALLOWLIST — las
   mismas raíces permitidas que el sync de lectura (config.obsidian_vault_allowlist).
2. Cada ruta destino se resuelve (`Path.resolve`) y debe quedar dentro de `Mia/`
   (`is_relative_to`); cualquier escape lanza error.
3. Los nombres de nota se sanean a slugs ascii; nombres con `..`, separadores de ruta u
   ocultos se RECHAZAN (no se "arreglan" en silencio).
4. Mia nunca modifica notas del abogado (verificado por hash en el gate).

**Privacidad.** El frontmatter de las notas exportadas lleva solo title / fecha /
`fuente: Mia` y métricas inofensivas (confidence, case_count) — NUNCA el tenant ni
identificadores internos: el vault ya es del despacho y podría compartirse/sincronizarse.

**Cómo sabe Mia el vault del tenant.** El MISMO mecanismo del sync de lectura:
`tenant_settings.config->>'obsidian_vault_path'` (leído con `pool.tenant_connection`,
RLS activo). `register_tenant_vault` usa el mismo upsert que ya usaba
`/api/ux/connectors/obsidian/sync`. Roundtrip cerrado: la nota que Mia escribe bajo
`Mia/` la reindexa obsidian_sync en la corrida siguiente → vuelve a knowledge_chunks
(no hay exclusión: los archivos de Mia no llevan prefijo `_`).

**Bootstrap e instalación guiada (winget).** Si el vault no existe,
`VaultWriter.bootstrap_vault()` crea la estructura mínima (Mia/conceptos, Mia/reportes,
Mia/README.md en lenguaje llano explicando qué escribe Mia ahí). La instalación de
Obsidian es guiada: `connectors/obsidian_install.py` detecta el programa
(%LOCALAPPDATA% + `winget list`; `is_installed()` nunca lanza aunque winget no exista)
e instala con `winget install --id Obsidian.Obsidian -e --silent
--accept-package-agreements --accept-source-agreements` — subprocess con LISTA de
argumentos (sin shell), timeout 600 s, respuesta `(ok, mensaje llano)`.

**Piezas.** `connectors/vault_writer.py` (VaultWriter + tenant_vault_writer/register),
`connectors/obsidian_install.py`, integración quirúrgica en
`memory/wiki_manager.compile_concept` (espejo tras persistir, try/except con log) y
`memory/dreams._weekly_report` (ídem), router `/api/obsidian/*` en
`api/routes/folders.py` (status / install / bootstrap; montado en api/main.py), y gate
`execution/test_vault_write.py`.

**Verificación (gates verdes 2026-07-01).** test_vault_write 29/29 (escritura solo bajo
Mia/, frontmatter sin tenant, escapes rechazados, roundtrip a knowledge_chunks con
embeddings mockeados, nota del abogado intacta por hash, bootstrap + README, vault caído
sin pérdida de la wiki interna, is_installed/install sin winget no lanzan) ·
test_wiki_manager 18/18 · test_dreams 16/16 · test_obsidian_sync 22/22 sin regresión.

**Refuerzos post-revisión (2026-07-01, revisión independiente CP-C2).** (1) ANTI-JUNCTION
— si `{vault}/Mia` es un symlink o un junction de Windows (reparse point; el revisor lo
reprodujo con `mklink /J` hacia fuera de la allowlist), TODA escritura se rechaza
fail-closed con log: `_mia_root()` compara la ruta REAL (`os.path.realpath`, que sí
resuelve junctions) contra la esperada bajo el vault, además de `Path.is_symlink()`.
(2) Los stems reservados de Windows (CON, PRN, AUX, NUL, COM1-9, LPT1-9,
case-insensitive) se renombran con sufijo (`con` → `con-nota`) en `_slugify`. (3) Los
espejos al vault (`export_concept` desde wiki_manager y `export_report` desde dreams)
corren vía `asyncio.to_thread` — la E/S síncrona ya no congela el event loop con vaults
lentos (OneDrive). (4) `POST /api/obsidian/install` exige confirmación explícita
(`{"confirmar": true}`; sin ella responde 400 con mensaje llano) y su docstring documenta
que en despliegue compartido (Modo A) el endpoint debe DESHABILITARSE (Riesgo #10/#15 de
sandbox). (5) El error de vault sin configurar llega al abogado en lenguaje llano
("Falta configurar la ubicación del archivo de notas. Pídele a tu administrador que la
configure."); el detalle técnico queda solo en el log (`VaultConfigError`). Gates:
test_vault_write ampliado a 34/34 (junction REAL con mklink /J + stems reservados) ·
test_wiki_manager 18/18 · test_dreams 16/16 · test_obsidian_sync 22/22 sin regresión.

## #33 — 2026-07-16 · Anonimizador: "enmascarar todo, siempre" (decisión de Pipe)

**Decisión.** El anonimizador aplica SIEMPRE los patrones de **todos los packs instalados** + la
base universal + los respaldos por rol, **sin mirar la jurisdicción del despacho**. `jurisdictions`
desaparece de su API pública (un llamador viejo revienta con TypeError en vez de que se le ignore
en silencio).

**Razonamiento.** El anonimizador es un gate de confidencialidad: si falla, se filtran datos de
clientes reales. **El secreto profesional manda sobre la precisión del análisis.** Se acepta
sobre-enmascarar; no se acepta filtrar un dato por ser de otro país — un despacho colombiano recibe
clientes españoles, y el pack 'co' cubriendo el rol suprimía el respaldo que atrapaba el DNI (fuga
preexistente, confirmada ejecutando). Filtrar la cédula de un cliente es irreversible; enmascarar de
más solo estorba.

**Efecto aceptado y dicho:** `artículos 1494-1495` se enmascara como teléfono. Se prefiere ese ruido
a un dato del cliente en claro.

**Corolario estructural.** Los respaldos por rol (DOCUMENTO/TELEFONO) **no son suprimibles por
configuración**: antes, un pack podía apagar la red pan-hispana con solo declarar un `role` — bastaba
un typo, sin malicia, y salían cédulas y DNI en crudo. Un gate de seguridad que un archivo de datos
puede desactivar no es un gate.

## #34 — 2026-07-17 · Delegación: "MIA decide y me pregunta" (decisión de Pipe)

**Decisión.** MIA puede **decidir por sí misma** que necesita un ayudante externo y **proponerlo** al
abogado. Tres modos por despacho (`tenant_settings.config->>'delegation_mode'`): **preguntar**
(default) · **autonomo** · **solo_si_lo_pido**.

**Razonamiento.** El diseño original (CP-HUB) solo permitía delegar cuando el abogado nombraba al
ayudante en su propio mensaje: el acto de pedirlo ES el consentimiento. Pipe lo rechazó — *"parte del
encanto de MIA es que puede determinar si necesita agentes o subagentes"*. Un asistente que solo
obedece órdenes literales no es un asistente.

**Por qué ahora es aceptable darle la decisión al modelo.** Porque **el modelo ya no abre la puerta**:
entre su decisión y la salida de datos está el abogado aprobando el texto exacto (interrupt HITL en
`graph.py::delegation_node`). Pero "el humano aprueba" NO se acepta como control único —un control que
depende de leer con atención cada vez se degrada a la décima propuesta—, así que hay tres límites
**estructurales** que hacen que, incluso con un proponente 100% controlado por una inyección indirecta
desde un documento del expediente, no haya nada que exfiltrar:
1. **El proponente no ve el expediente.** Solo el mensaje limpio del abogado y el catálogo de
   ayudantes. No se le pide discreción: no puede filtrar lo que nunca leyó.
2. **El texto propuesto no es canal de salida libre.** Saneado y recortado; una línea corta y legible
   no es buen sitio donde esconder un expediente — y, sobre todo, ES legible.
3. **El ayudante sale de un catálogo cerrado** (ya filtrado por `hub_gate.allowed_agents`): slug
   inventado, texto libre o JSON roto → None. Nunca se construye un destino con lo que dijo el modelo.
La propuesta llega a la pantalla **etiquetada** como contenido generado por MIA y potencialmente
influido por un documento, para que el abogado la lea con la desconfianza correcta.

**Lo que NO cambia.** La política manda sobre el toggle: con 'soberano' no se delega aunque el
ayudante esté habilitado, y la política se lee con `model_policy_for_strict` (LANZA si la DB falla —
un error de infraestructura jamás abre la salida).

## #35 — 2026-07-17 · Todo el dinero en dólares (decisión de Pipe)

**Decisión.** El valor y el gasto se muestran **siempre en dólares**, para cualquier despacho. Se
rechazó la moneda por jurisdicción.

**Razonamiento.** El gasto de MIA ocurre en USD (es lo que cobran los proveedores de modelo). La
tarifa del abogado está en su moneda. Mostrar la tarifa en pesos junto a un gasto en USD obliga a una
de dos cosas: **mentir en el "valor neto"** (restar magnitudes de monedas distintas) o **inventar una
tasa de cambio** que nadie mantiene y que envejece mal. Ambas convierten una cifra útil en una cifra
falsa. Una sola moneda, la real del gasto, es honesta aunque sea incómoda.

**Efecto.** Confirma el comportamiento actual: no hubo cambio de código. Queda registrado para que no
se re-abra cada vez que se toca el agnosticismo de jurisdicción.

## #36 — 2026-07-17 · Los 8 principios: destilar los skills y el vault de Pipe, sin clonar nada suyo

**Decisión.** MIA incorpora ocho principios de oficio destilados de dos sistemas de Pipe —sus skills
de firma (cómo analiza) y su vault personal (cómo recuerda)—. **Ninguno se clonó:** lo colombiano y lo
propio de Lexia se descartó por diseño; solo entró lo que un abogado de Madrid o de Ciudad de México
reconocería como oficio.

**Razonamiento.** El hallazgo que ordenó el trabajo: **MIA estaba construida para NO MENTIR, no para
ARGUMENTAR BIEN** — todos los gates eran de veracidad y ninguno de sustancia— y **aprendía de Pipe sin
volver a leer nunca lo aprendido** (el wiki era de solo escritura). Un sistema que no miente pero no
argumenta no sirve; uno que aprende y no recuerda, tampoco.

**Lo que se descartó explícitamente:**
- **Correr la Sala de estrategia en cada turno:** ~9 llamadas contra las 4 del turno → triplicaría la
  factura del despacho. En su lugar se reusa el dictamen ya pagado y persistido por asunto (coste
  real: 0 llamadas nuevas, 1 SELECT indexado).
- **Clonar el criterio jurídico colombiano de Pipe:** violaría la regla dura (MIA no es de ningún
  país). Los roles del argumento son funcionales, sin una sola jurisdicción.
- **Truncar el SOUL al llegar al tope:** rechaza en vez de truncar — cortar la identidad del despacho
  en silencio es peor que fallar ruidosamente.

**Corolarios que quedan como regla.**
- **Ningún escritor automático sin freno sobre la capa 1.** `dreams` escribía reglas en SOUL —
  inyectado entero y con autoridad de sistema— sin HITL, sin tope y sin versionado. Ahora propone y el
  abogado aprueba, con versionado espejo de `playbook_versions`.
- **La confianza no es un trinquete.** Un rechazo pesa el doble que una aprobación (rechazar cuesta un
  acto deliberado; aprobar es el default) y nunca llega a 1.0. Lo aprendido con confianza inflada no
  se lee hasta recompilarse: es lo que evita leer basura con autoridad el día 1.
- **La instrucción directa del abogado se aplica sin re-preguntar** (regla dura: su input es
  fidedigno). El escepticismo aplica a lo que MIA infiere, no a lo que él ordena.
- **Un test puede estar protegiendo un defecto.** El comportamiento peligroso de `dreams` estaba
  fijado por un test que exigía justo eso ("Nudges actualiza SOUL"); hubo que invertirlo. Un gate
  verde no prueba que el diseño sea correcto: prueba que no ha cambiado.
