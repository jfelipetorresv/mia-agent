# Mia — Resúmenes de sesión

## 2026-06-20 — Sesión 21 · Smoke test login + onboarding
TL;DR: Login real funciona. Onboarding 15 preguntas ágil.
       SOUL.md generado. Smoke test del chat pendiente.
Qué construimos:
- Fix CORS + rutas actualizadas a nueva ubicación
- Todos los task models → mia-local (Ollama)
- Timeout + fallback sin LLM para onboarding
- Onboarding reducido a 15 preguntas ágiles
- SOUL.md generado exitosamente con datos de Lexia
Qué sigue: smoke test completo — crear asunto,
  enviar mensaje en chat, verificar respuesta de Mia.

## 2026-06-20 — Pausa post-goal second brain
TL;DR: Goal completado (23/23 suites). Smoke test del
       login pendiente — Pipe no tiene acceso al computador.
Estado: 23/23 suites · 7 commits · origin/main en 2cc8a15
Qué sigue: levantar los 3 procesos, smoke test del nuevo
  login en navegador, verificar registro + onboarding
  + chat con el nuevo sistema de auth.

## 2026-06-20 — Sesión 20 · Goal Codex — Autoaprendizaje horizontal
TL;DR: Login real multi-tenant, second brain, WikiManager, GEPA, Dreams,
       conectores UI y onboarding horizontal completados.
Qué construimos:
- Auth real: register/login/me con users por tenant, bcrypt, JWT 7 días y frontend sin token dev.
- WikiManager en $MIA_HOME/wiki/{tenant_id}: conceptos, búsqueda, lint, archivo y update tras HITL.
- GEPA Loop: detecta drafts de procedimientos, propone mejoras y archiva skills sin uso.
- Dreams semanal: replay, wiki update, GEPA, lint, nudges en SOUL.md y weekly report.
- UI second brain: wiki, sugerencias, conectores Obsidian/Pinecone y salud del sistema.
- Onboarding horizontal: sin opciones hardcodeadas de país, jurisdicción, área, cortes o herramientas.
Commits: a755447, 7f443dc, 04bcde0, 2901f2c, ef0fc28, 9fda67f
Regresión: 23/23 suites verdes (17 históricas + 6 gates nuevos). `test_rls.py` 12/12 intacto.
Qué sigue: push a origin/main.

## 2026-06-20 — Sesión 19 · Goal Codex — 4 tareas
TL;DR: Issue #1 cerrado. Mia responde end-to-end con Ollama.
       Onboarding tipado + carga masiva completados.
Qué construimos:
- Issue #1 cerrado: chat responde con mia-local/qwen2.5:32b
- Onboarding con tipos mixtos (checkboxes, selects, chips, toggle)
- Carga masiva de documentos + selector de carpeta + progreso
Commits: 2fba689, b1c0960, 4390a48
Qué sigue: Issues #3 (conectores externos desde UI) y 
           pulir UX/diseño visual

## 2026-06-16 — Sesión 18 · Fix intake + Ollama
TL;DR: Issue #1 casi resuelto. Skip embeddings si chunks=0 + 
       timeout Voyage. Pendiente: verificar respuesta de Ollama.
Qué construimos:
- Fix LITELLM_LOCAL_MODEL_COST_MAP en scripts de arranque
- Skip embeddings en intake_node cuando chunks=0
- Timeout=15 + num_retries=2 en embed_texts
- mia-local (Ollama qwen2.5:32b) en litellm_config.yaml
Commits: 7b6c384, a1c47b6
Qué sigue: reiniciar Terminal 2, enviar mensaje en chat,
  verificar que Terminal 1 muestra llamada a mia-local.
  Si aparece → Issue #1 cerrado. Si Ollama responde → 
  Mia funciona end-to-end.

## 2026-06-16 — Sesión 17 · Smoke test vivo completado
TL;DR: Mia v0 operativa en navegador con LLM real. 4 issues 
       identificados en el smoke test.
Qué funciona:
- Onboarding 19 preguntas → SOUL.md generado ✅
- Crear asunto → aparece en lista ✅
- Workspace abre con avatar M + diagnóstico + área chat ✅
- Pantalla Conocimiento (3 tabs) ✅
- Panel de control con métricas reales ✅
Issues encontrados (priorizados):
1. CRÍTICO: Mia no responde en el chat — el turno del agente 
   no se dispara o no llega al frontend vía SSE.
2. UX: Preguntas del onboarding deberían tener tipos 
   (algunas abiertas, otras selección múltiple / checkboxes)
3. UX: No hay carga masiva de documentos ni conexión a 
   carpeta local
4. CONFIGURACIÓN: Conectores externos (Obsidian vault, 
   Pinecone) no configurables desde la UI todavía
Qué sigue: atacar Issue #1 primero (chat sin respuesta).
Sin ese fix, el sistema no es demostrable.

## 2026-06-15 — Handoff smoke test
TL;DR: Mia corre en el navegador. Bloqueado en CORS — fix listo, 
       pendiente de aplicar y verificar.
Estado: 3 terminales corriendo (litellm :4000, uvicorn :8000, 
        next :3000). Frontend carga. Crear asunto falla con 401 
        por CORS faltante.
Fix pendiente de verificar:
  - CORSMiddleware en main.py (causa raíz)
  - Bypass OPTIONS en middleware.py (defensa en profundidad)
  Claude Code ya tiene el diff exacto. Aplicado pero NO verificado 
  en navegador — Pipe apagó el computador antes de probar.
Qué sigue: arrancar los 3 terminales, abrir localhost:3000, 
  crear asunto "Demanda seguros HDI — prueba Mia" y verificar 
  que funciona.

## 2026-06-14 — Pausa post-v0
TL;DR: Terminal se trabó al arrancar smoke test. Proyecto intacto. Retomamos mañana.
Estado: 17/17 suites · 358 checks · commit 64bad3f
Qué sigue: decidir entre smoke test vivo o cerrar riesgo #23 (login real) antes del primer cliente.

## 2026-06-14 — Sesión 16 — 🎉 CIERRE DEL PROYECTO
TL;DR: Módulo 5 cerrado (SOUL.md + entrevista de onboarding + prueba E2E). **Mia v0 operativa.**
       Gate `test_e2e.py` 25/25; regresión **17/17 suites · 358 checks**; `test_rls` 12/12 intacto.
Qué construimos:
- Investigación previa → 4 premisas falsas del spec, presentadas como decisiones: el Doc 4 no
  estaba en el repo (el usuario lo entregó → fuente exacta), el spec decía 18 preguntas pero el
  Doc 4 trae 19 (P19 triad_mode opcional), `$MIA_HOME` no existía en config, `_TASK_MODELS` sin
  `"soul"`. Y A4: la Capa 1 no leía el SOUL.md y el grafo nunca llenaba `soul_snapshot` (Riesgo #11).
- PARTE A: `config.MIA_HOME` (ancla rutas relativas); `llm._TASK_MODELS["soul"]="claude-sonnet"`;
  `onboarding/soul_interview.py` (`SoulInterview`: get_questions/run_interview/update_soul; 19
  preguntas; template de 9 secciones; genera el SOUL.md por LLM conservando placeholders; helpers
  puros de archivo; persiste respuestas para "Revisar mi perfil"); 3 endpoints
  `/api/onboarding/*`. Wiring (decisión #21, "Grafo + prompt_builder"): `initial_state` carga
  `soul_snapshot`, `graph.py` lo antepone en analysis/draft/edit, `MiaAgent.__post_init__` lo carga
  en la Capa 1 — todo None-safe, gates intactos. NO se tocó `prompt_builder.py`.
- PARTE A5 (frontend): `app/onboarding/page.tsx` (wizard de 19 preguntas, progreso, ejemplos,
  resultado con el SOUL.md, Editar/Continuar, "Revisar mi perfil") + `OnboardingGate` (redirige a
  /onboarding la primera vez) montado en `layout.tsx`.
- PARTE B: `execution/test_e2e.py` (GATE FINAL, 25/25) — 7 pasos punta a punta con TestClient,
  `$MIA_HOME` aislado en tempdir, LLM/embeddings mockeados, PDF Ley 80/1993. SOPs
  `architecture/{e2e_runbook,soul_interview}.md`.
Qué decidimos: decisión #21 (SOUL.md como archivo en `$MIA_HOME`, sin DB; 19 preguntas; status por
mtime; wiring del soul_snapshot al grafo Y a la Capa 1, None-safe; imports diferidos para evitar
ciclos). Nuevos riesgos #26 (SOUL generado por LLM — mitigado por la revisión humana en la pantalla
de resultado) y #27 (triad_mode se almacena pero no está implementado como modo de ejecución).
Qué sigue: smoke test VIVO en navegador con LLM real (runbook). Antes del PRIMER CLIENTE, atender
riesgos abiertos: #23 (login real), #25 (diagnóstico/flags UI), #19 (Curator sin HITL ⚖️), #13 (rol
curador SAT-Graph 🔐), #3 (pgvector oficial para clientes). No quedan módulos pendientes.

Citas legales: ninguna entregada. El SOUL de Lexia (Doc 4) y el PDF Ley 80/1993 del E2E son datos
de prueba/identidad del despacho, no citas a un cliente; el corpus semilla sigue marcado [VERIFICAR]
(Riesgo #14). El SOUL.md conserva como placeholder los campos sin responder (no inventa datos).

## 2026-06-14 — Handoff pre-Sesión 16
TL;DR: Terminal cerrándose (contexto ~65%) antes de arrancar el Módulo 5.

**Estado exacto:** **Fase 3 COMPLETA y commiteada.** HEAD = `91f0884`. Commits de este terminal:
- `91f0884` feat: frontend Next.js 14 — 5 pantallas (Fase 3 UX)
- `d4f5c57` feat: superficie /api/* completa + persistencia de perfil (Fase 3 backend)
- `3d3929d` fix: arrancar scheduler en lifespan FastAPI (#22)
- `b6f6bf1` Fase 0-2 completa
Regresión **16/16 suites · 333 checks** verdes. `npm run build` ✓ (frontend compila).

**CORRECCIÓN al borrador del handoff:** NO fue "solo planificación". En este terminal SÍ se
construyó toda la Fase 3: Sesión 14 (superficie `/api/*` + persistencia de perfil `firm_profiles`
+ parser PDF/Word, gate `test_ux.py` 18/18) y Sesión 15 (scaffold Next.js 14 + las 5 pantallas +
cierre del Riesgo #24, gate `test_ux.py` 25/25). Dos commits nuevos (`d4f5c57`, `91f0884`).

**Próximo paso EXACTO:** pegar el prompt del **Módulo 5 (Fase 4): entrevista SOUL.md + prueba
E2E** — es el ÚLTIMO módulo del proyecto. Patrón de siempre: investigar premisas → presentar
decisiones (AskUserQuestion) → construir → gate → regresión → wrap → commit. Tras el gate de
Módulo 5 la regresión pasa de 16 a **17 suites** (la "17/17" del borrador es el objetivo FUTURO,
no el estado actual, que es 16/16).

**Opcional antes de Módulo 5:** smoke test VIVO de la UI (Modo B, 3 terminales: `litellm` /
`uvicorn` / `npm run dev`) — NO se hizo esta sesión; solo se verificó `npm run build` + el gate
de endpoints (TestClient). Sería el primer recorrido real en navegador.

**Riesgos abiertos (principales):** #23 (login real; hoy token de dev en frontend/.env.local),
#25 (diagnóstico de P2 y punto "borrador pendiente" de P1 sin endpoint que los alimente), #19
(Curator consolida/poda playbooks SIN revisión humana ⚖️), #13 (corpus SAT-Graph escribible por
cualquier conexión `mia_app`, sin rol curador 🔐). Lista COMPLETA en `memory/bugs-and-risks.md`.

**Arranque rápido próxima sesión:** leer `CLAUDE.md` + `memory/{progress,task_plan,decisions,
bugs-and-risks}.md` + `architecture/api_surface.md`. Entorno: PostgreSQL 16 + pgvector corriendo;
`.venv` con todas las deps; `frontend/` scaffoldeado con node_modules instalados. Tenant de dev:
`DEV_FRONTEND`. El wrap de Sesión 15 YA está commiteado (en `91f0884`); lo ÚNICO sin commitear es
esta entrada de handoff (`memory/session-summaries.md` modificado en el árbol de trabajo).

## 2026-06-14 — Sesión 15
TL;DR: Frontend Next.js 14 — las 5 pantallas. **Fase 3 (UX) COMPLETA.** Riesgo #24 cerrado.
       Gate test_ux.py 25/25 (incl. npm build); regresión 16/16 (333 checks).
Qué construimos:
- Cierre del Riesgo #24: migración `008_matters_description.sql` (+description, +status en
  matters); `ux.py` create/get/list ahora persisten/devuelven description y status. #24 🟢.
- Scaffold `frontend/` con `create-next-app@14` (TypeScript, Tailwind, App Router, no-src-dir,
  alias @/*). Next 14.2.35 + React 18. `next.config.mjs`: eslint.ignoreDuringBuilds (el build
  valida TS; ESLint no lo tumba).
- Token de dev (#23): `frontend/.env.local` (gitignored) con NEXT_PUBLIC_API_URL +
  NEXT_PUBLIC_DEV_TOKEN (JWT del tenant DEV_FRONTEND, acuñado como los gates). Documentado en
  api_surface.md §auth.
- `lib/api.ts` — cliente con Bearer; SSE sobre fetch (streamTurn) porque EventSource no admite
  headers. `app/_components/Sidebar.tsx` (nav activa). `app/layout.tsx` (Inter + sidebar 220px).
- Las 5 pantallas (Tailwind puro, §G, cada fetch con Bearer):
  P1 `app/page.tsx` (lista + modal crear), P2 `app/asuntos/[id]/page.tsx` (3 columnas: docs +
  chat con SSE en vivo + diagnóstico), P3 `app/asuntos/[id]/revisar/page.tsx` (borrador,
  [VERIFICAR] en amarillo, aprobar/editar/rechazar), P4 `app/memoria/page.tsx` (perfil +
  playbooks + sugerencias con aplicar/ignorar), P5 `app/dashboard/page.tsx` (actividad,
  procesos, modelos, costo, conectores — todo con etiquetas amigables).
- `execution/test_ux.py` — +7 checks de frontend (5 pantallas exportan default, layout con
  Sidebar, `npm run build` sin errores). Total 25/25.
Qué decidimos: sin decisión formal nueva. ESLint fuera del build (TS sí se valida). El
diagnóstico (P2) y el punto de "borrador pendiente" (P1) quedan como placeholder (sin endpoint
que los alimente) → Riesgo #25.
Qué sigue: **Fase 4 — Módulo 5 (entrevista SOUL.md + prueba E2E)**, o endurecer la UX (login
real #23, diagnóstico/flags #25). Antes de producción: arrancar backend+frontend juntos (Modo B,
3 terminales) y probar el flujo vivo end-to-end.

Citas legales: ninguna. La UI muestra contenido del backend (sintético en los tests). §G
verificado automáticamente (sin jerga técnica en respuestas ni etiquetas).

## 2026-06-14 — Sesión 14
TL;DR: Fase 3 ARRANCA, dividida en dos (decisión #20). Esta sesión: superficie /api/*
       completa + persistencia de perfil. Gate test_ux.py 18/18; regresión 16/16 (326 checks).
Qué construimos:
- Investigación previa: `frontend/` NO existe (Módulo 0 solo hizo backend); de 15 endpoints del
  gate solo ~3 existían (bajo /matters, no /api); el perfil nunca se persistió (2a in-memory).
  Se presentó y el usuario decidió (decisión #20): Fase 3 en 2 sesiones — S14 backend, S15 frontend.
- `db/migrations/007_profiles.sql` (NUEVO) — tabla `firm_profiles` (perfil estructurado del
  despacho, RLS por-tenant). `memory/profile_manager.py` — ADITIVO: __init__ +pool/+tenant_id;
  con pool=None sigue in-memory (gate 2a 19/19 intacto); +get_firm_profile/upsert_firm_profile.
- `api/routes/ux.py` (NUEVO) — router /api con ~18 endpoints: matters (list/create/get),
  documents (list/upload PDF·Word), chat (devuelve stream_url), stream (alias del SSE de 1d),
  draft (lee el checkpoint; 404 si no hay), draft/approve|reject (delegan en _resume de 1d),
  profile (get/put), playbooks (list/create), proposals (list/apply/ignore — apply cablea
  propuesta→playbook, cierra parte de #21), dashboard/stats. Montado en main.py. §G estricto.
- `ingest/extract.py` (NUEVO) — extrae texto de PDF (PyMuPDF) / Word (python-docx) / txt·md.
- Deps nuevas (pyproject + .venv): python-multipart (FastAPI lo exige para UploadFile), pymupdf,
  python-docx. Documentadas en findings.md.
- `execution/init_profiles.py` (runner 007) + `execution/test_ux.py` (18/18, TestClient + JWT,
  LLM/embeddings mockeados, PDF/Word sintéticos, check §G). `architecture/api_surface.md` (SOP).
Qué decidimos: decisión #20 (Fase 3 en 2 sesiones; /api/* nuevo + /matters legacy intacto;
perfil en firm_profiles; auth = token dev en S15).
Qué sigue: **Sesión 15 — frontend Next.js 14 (scaffold + 5 pantallas)** contra esta API verificada.

Citas legales: ninguna. Los datos del gate (documentos, perfil, playbooks, propuestas) son
sintéticos de prueba. La regla §G se verifica automáticamente (sin jerga técnica en respuestas).

## 2026-06-14 — Sesión 13
TL;DR: Módulo 3e Feedback processor cerrado. Trazas enriquecidas a v2 (decisión #19).
       **HITO: Fase 2 — Knowledge Stores COMPLETA (3a-3e).** 15/15 suites (308 checks).
Qué construimos:
- Investigación previa: las trazas reales (mia.trace.v1) NO registraban la decisión HITL, ni
  el borrador original vs final, ni los documentos citados → las 3 señales del spec no eran
  detectables. Se presentó y el usuario decidió (decisión #19): enriquecer la traza en el
  origen (Opción 1).
- `memory/trace_capture.py` — Trace gana 4 campos OPCIONALES (hitl_outcome, draft_original,
  draft_final, retrieved_doc_ids); schema sube a `mia.trace.v2` solo si traen valor (v1 sin
  ellos sigue válida). `capture()` acepta los kwargs nuevos.
- `agents/graph.py::finalize_node` — escribe los 4 campos: hitl_outcome desde final_status,
  draft_original/final, retrieved_doc_ids DERIVADO de state["documents"] (sin tocar MatterState
  ni el reducer).
- `db/migrations/006_feedback_proposals.sql` (NUEVO) — `feedback_proposals` (proposal_type
  improve_playbook|new_playbook|flag_gap, target_playbook_id, suggested_content, rationale,
  signal_count, trace_ids, status pending|approved|rejected|applied) y
  `processed_traces_watermark` (tenant_id, trace_date, last_processed_at, traces_processed).
  RLS por-tenant en ambas.
- `memory/feedback_processor.py` (NUEVO) — `FeedbackProcessor`: load_traces (v1/v2, ignora
  eventos, excluye días ya procesados por watermark, ventana since_hours), analyze (HITL_REJECTION/
  HITL_EDIT con diff>20% via difflib / NO_RESULT), propose (umbral ≥2; improve/new/flag_gap;
  call_llm task=curator), save_proposals (status pending), mark_traces_processed (watermark),
  run / run_all_tenants.
- `cron/scheduler.py` — +job `feedback_daily` (24h). `memory/__init__.py` exporta FeedbackProcessor.
- `execution/init_feedback.py` (runner 006) y `execution/test_feedback_processor.py` (21/21,
  trazas sintéticas v1+v2 en .tmp, LLM mockeado). `architecture/feedback_processor.md` (SOP).
Qué decidimos: decisión #19 (trazas v2 con señales HITL; processor PROPONE, no aplica;
idempotencia por watermark).
Qué sigue: **Fase 3 — UX (5 pantallas Next.js)**. Antes de Fase 3, ver Riesgo #22 (el scheduler
nunca se arranca: los jobs no se disparan en producción) y #21 (propuestas sin revisar/aplicar).

Citas legales: ninguna. El módulo es infraestructura de aprendizaje; el contenido de trazas y
propuestas del gate es sintético. Las propuestas que generaría en vivo son borradores para que
el ABOGADO revise (no se aplican solas).

## 2026-06-14 — Sesión 12
TL;DR: Módulo 3b Curator cerrado + persistencia de playbooks (decisión #18).
       Gate test_curator 23/23; regresión 14/14 suites (287 checks). Fase 2 COMPLETA.
Qué construimos:
- Investigación previa: el spec asumía una tabla `playbooks` que NO existía (el 2b era
  in-memory). Se presentó y el usuario decidió (decisión #18, Opción 2): crear la tabla Y
  cablear PlaybookManager a DB en la misma sesión, manteniendo su interfaz pública.
- `db/migrations/005_playbooks.sql` (NUEVO) — tabla `playbooks` (title, summary, applies_when,
  content, status active|archived|draft, usage_count, last_used_at, embedding vector(1024),
  metadata; UNIQUE(tenant_id,title); RLS por-tenant; HNSW + BTREE; GRANT mia_app).
- `memory/playbook_manager.py` — ADITIVO: `__init__(pool=None, tenant_id=None)`; con pool=None
  sigue 100% in-memory (gate 2b 14/14 intacto). +métodos async DB: register_playbook (upsert +
  embedding de summary+applies via voyage), get_index, get_playbook, mark_used, list_active.
- `memory/curator.py` (NUEVO) — `Curator`: run/load_playbooks/find_candidates (similitud coseno
  por operador `<=>` de pgvector, umbral 0.85)/consolidate (call_llm task=curator → claude-sonnet,
  archiva originales, idempotente)/prune (last_used_at > 90d, NULL no se poda)/run_all_tenants.
- `agent/llm.py` — +task `"curator": "claude-sonnet"` en _TASK_MODELS (alias que resuelve a
  claude-sonnet-4-6; auxiliary_client.TASK_MODELS es el mismo dict por referencia).
- `cron/scheduler.py` — +job `curator_weekly` (168h, domingos 2am sin timezone en v1).
- `execution/init_playbooks.py` (runner 005) y `execution/test_curator.py` (23/23, LLM+embeddings
  mockeados, embeddings de candidatos controlados con inserts directos para cosenos 0.9/0.84).
- `architecture/curator.md` (antes vacío) — SOP + Self-Annealing.
Qué decidimos: decisión #18 (playbooks persisten en DB; PlaybookManager DB-backed con interfaz
intacta; task curator → claude-sonnet).
Qué sigue: PAUSA — Módulo 3e — Feedback processor (último de Fase 2).

Citas legales: ninguna entregada. El contenido de los playbooks en el gate es filler de prueba.
NOTA jurídica: el Curator consolida/archiva playbooks con LLM SIN revisión humana → Riesgo #19
(un playbook jurídico podría degradarse; originales quedan archived/recuperables).

## 2026-06-14 — Sesión 11
TL;DR: Módulo 3d Pinecone connector cerrado. Gate 14/14; regresión 13/13 suites
       (264 checks). Store externo OPCIONAL y CONDICIONAL (noop sin API key).
Qué construimos:
- `connectors/pinecone_connector.py` (NUEVO) — `PineconeConnectorBase` (ABC: upsert/query/
  delete/describe_index), `PineconeConnector` (real; aislamiento por namespace
  `{prefix}_{tenant_id}`, batch upsert 100, SDK pinecone v3+ con import PEREZOSO),
  `NoopPineconeConnector` (misma interfaz, no-op, is_configured=False) y factory
  `get_pinecone_connector()` (real si hay PINECONE_API_KEY, si no noop).
- `.env`: +PINECONE_INDEX_NAME / PINECONE_NAMESPACE_PREFIX (comentados, defaults mia-legal/
  tenant). PINECONE_API_KEY ya estaba.
- `execution/test_pinecone_connector.py` (NUEVO, 14/14) — sin Pinecone real: noop + índice
  FALSO inyectado en `_index`. Cubre factory con/sin key, noop, interfaz completa, namespace
  por tenant, batch 250→[100,100,50], metadata intacta, top_k, normalización de matches, delete.
- `architecture/pinecone_connector.md` (antes vacío) — SOP + Self-Annealing.
Qué decidimos: sin decisión formal nueva (el módulo aplica decisión #2: pgvector primario,
Pinecone externo opcional). Aclaración de spec registrada en el SOP: el aislamiento es por el
parámetro `namespace` de Pinecone, no por un filtro de metadata (no se contamina la metadata).
Qué sigue: PAUSA — Módulo 3b — Curator cron. Pendiente Fase 2: 3e Feedback processor.

Citas legales: ninguna. El módulo es infraestructura de store vectorial; no genera ni cita
texto jurídico. El gate no toca Pinecone real ni red.

## 2026-06-14 — Sesión 10
TL;DR: Módulo 3c Obsidian indexer CERRADO. Gate test_obsidian_sync 22/22;
       regresión 12/12 suites (250 checks). 3 premisas del spec corregidas.
Qué construimos:
- Investigación previa: el spec asumía 3 cosas que no existían → se presentaron y el
  usuario decidió (decisión #17): (C1) los chunks de Obsidian van a una tabla NUEVA
  `knowledge_chunks`, NO a `documents` (documents.matter_id es NOT NULL; las notas son
  del despacho, no de un asunto); (C2) embeddings por `embeddings.embed_texts` (librería,
  no `call_llm(task="embedding")` que no existe); (C3) `cron/scheduler.py` no existía →
  se creó un scheduler propio mínimo (sin APScheduler).
- `db/migrations/004_knowledge_stores.sql` (NUEVO) — `knowledge_chunks` (source/source_path/
  chunk_index/heading_path/content/embedding(1024)/content_tsv GENERATED/metadata, UNIQUE
  por (tenant,source,source_path,chunk_index), RLS por-tenant + HNSW + GIN) y
  `obsidian_file_hashes` (sha256 por archivo, RLS). NO toca documents/chunks.
- `connectors/obsidian_sync.py` (NUEVO) — `ObsidianSync`: scan (excluye .carpetas y _archivos),
  hash sha256 incremental, chunking por encabezados H1/H2/H3 con máx 512 tok (split por
  párrafos), embed en batches de 128, upsert/borrado en knowledge_chunks y hashes, todo por
  `tenant_connection` (RLS).
- `cron/scheduler.py` (NUEVO) — registro de jobs en memoria (register/list/run/start); job
  `sync_obsidian_all_tenants` cada 6h (enumera tenants con vault configurado y sincroniza).
- `execution/init_knowledge_stores.py` (runner migración 004) y
  `execution/test_obsidian_sync.py` (gate, 22 checks, vault temporal en .tmp/, embeddings
  mockeados). `architecture/obsidian_sync.md` (SOP, antes vacío).
Qué decidimos: decisión #17 (knowledge_chunks tabla separada + correcciones C1/C2/C3).
Qué sigue: PAUSA — Módulo 3d — Pinecone connector. Pendientes Fase 2: 3b Curator, 3e Feedback.

Citas legales: ninguna. El módulo no genera ni cita texto jurídico; el vault de prueba del
gate es contenido filler temporal en .tmp/ (no es el vault real ni datos entregables).

## 2026-06-14 — Sesión 9
TL;DR: Módulo 3a SAT-Graph CERRADO. Corpus semilla cargado en DB.
       Gate test_sat_graph.py 21/21; regresión 11/11 suites (228 checks).
Qué construimos:
- Migración corrida: `init_sat_graph.py` aplicó 003_sat_graph.sql (3 tablas
  legal_norms/norm_relations/jurisprudence, RLS abierto, GRANT a mia_app).
- Corpus semilla cargado: `ingest_corpus.py` (+runner `__main__`, se corre con
  `python -m mia.rag.ingest_corpus`) → 5 normas, 3 providencias, 2 relaciones
  (todas [VERIFICAR]; datos de desarrollo, no citas entregadas).
- `execution/test_sat_graph.py` (NUEVO) — gate async contra DB real, 21 checks:
  tablas, RLS (mia_app SELECT · 2 tenants ven el mismo corpus), curaduría +
  upsert idempotente, vigencia temporal antes/durante/expirada, relaciones +
  filtro, cadena recursiva simple/hoja/ciclo, FTS español con acento, semilla.
- `architecture/sat_graph.md` (NUEVO) — SOP del módulo + Self-Annealing.
Qué decidimos:
- Decisión #16 (ya registrada en Sesión 8 previa al crash): SAT-Graph = corpus
  COMPARTIDO (sin tenant_id), RLS abierto USING(true) WITH CHECK(true), escritura
  por GRANT a mia_app, acceso vía pool.connection() (sin GUC).
- Sin decisiones nuevas esta sesión; se completó la implementación de 3a.
Qué sigue: PAUSA — no arrancar otro módulo sin el usuario. Candidato (orden del
usuario): Módulo 3c — Obsidian indexer. Pendientes Fase 2: 3b Curator, 3d Pinecone,
3e Feedback. Nuevos riesgos #13 (corpus escribible sin rol curador separado, 🔐) y
#14 (corpus semilla [VERIFICAR] sin contrastar).

Citas legales: ninguna entregada al cliente. El corpus semilla (normas y
providencias en ingest_corpus.py) es ILUSTRATIVO/de desarrollo, marcado [VERIFICAR]
en metadata; debe contrastarse contra SUIN-Juriscol / la corte respectiva antes de
cualquier uso real.

## 2026-06-14 — Sesión 8
TL;DR: Cerrada deuda del grafo (#11 reframe, #12 fix quirúrgico).
       Conteo de checks corregido a 207.
Qué construimos:
- Riesgo #11 cerrado por reframe: el ContextCompressor NO se cablea
  al grafo LangGraph hoy (nodos autocontenidos, historial no consumido).
  Decisión #14 registrada.
- Riesgo #12 cerrado con fix mínimo: role="system" → role="user"
  en el mensaje de resumen del ContextCompressor. SUMMARY_PREFIX
  actualizado a "[RESUMEN DE CONTEXTO ANTERIOR]". Decisión #15 registrada.
Qué decidimos:
- Cablear el compresor al grafo queda para cuando el grafo adopte
  historial creciente (Fase 3 o decisión de producto posterior).
- No insertar ack de assistant tras el resumen — SUMMARY_END_MARKER
  es suficiente para desambiguación semántica.
- Conteo canónico de checks: 207 (no 235 — error de tally corregido).
Qué sigue: Fase 2 — Knowledge Stores · Módulo 3a SAT-Graph.

## 2026-06-14 — Sesión 7
**TL;DR:** Módulo 2c (ContextCompressor) COMPLETO → **Fase 1 (Memoria, 2a-2d) cerrada**.
Gate `test_context_compressor.py` 22/22; regresión 10/10 suites (235 checks). PAUSA.

**Qué construimos:**
- Se leyó COMPLETO el `context_compressor.py` de Hermes (2079 líneas). Params no
  contradicen (Hermes parametriza 0.50/3/20; Mia fija 0.55/5/30). Se flaggearon 2
  mejoras → aprobadas (decisión #13).
- `agent/context_compressor.py` (NUEVO) — compress() con threshold 55%, protect 5/30,
  resumen del medio en haiku (BLOQUEO), `[RESUMEN DE CONTEXTO]` como msg system,
  `[VERIFICAR]` preservado verbatim, resumen estructurado en español jurídico,
  (A) iterativo + (B) anti-thrashing.
- `memory/trace_capture.py` +capture_event (evento context_compressed, schema event).
- `agent/core.py` run_turn comprime antes del turno (transparente). `config.py`
  +MIA_CONTEXT_WINDOW. `architecture/context_compressor.md`. Gate 22/22.

**Qué decidimos (decisión #13):** ContextCompressor adopta resumen iterativo (A) y
anti-thrashing (B) de Hermes. Params locked intactos (55%/5/30, compression→haiku).

**Qué sigue:** PAUSA — Fase 0 + Módulo 1 + Fase 1 completos. No arrancar otro módulo sin
el usuario. Candidatos: Fase 2 (3a-3e), Fase 3 (UX), Módulo 5 (SOUL.md). Nuevos Riesgos
#11 (compresor solo en run_turn, no en el grafo) y #12 (resumen role=system mid-array sin
verificar contra Anthropic). #5 ampliado (el umbral de compresión depende del estimador).

**Citas legales:** ninguna entregada al cliente. El texto jurídico en fixtures/prompts
es ilustrativo, sin `[VERIFICAR]` pendientes de fuente real.

## 2026-06-13 — Sesión 6
**TL;DR:** Módulo 1e (Agent Hub) COMPLETO → **Módulo 1 cerrado (1a-1e)**. Gate
`test_agent_hub.py` 38/38; regresión 9/9 suites verdes. PAUSA.

**Qué construimos:**
- Premisa del spec corregida: NO existía tabla `profiles` → decisión #12 (tabla nueva
  `tenant_settings` jsonb, RLS, migración por postgres). 3/5 CLIs instalados
  (hermes/claude/codex) → degradación real.
- `gateway/agent_hub.py` (AgentHub, 5 conectores, detección PATH/env, subprocess
  args-en-lista shell=False, graceful degradation), `gateway/hub_config.py` (config
  por tenant en tenant_settings, RLS), `api/routes/settings.py` (GET + enable/disable,
  §G sin marcas), seam de delegación OFF-por-defecto en `graph.py`,
  `architecture/agent_hub.md`, `execution/test_agent_hub.py` (38/38).
- `schema.sql` +tenant_settings; aplicado re-corriendo init_db.py (9 tablas, 5 policies).

**Qué decidimos:**
- #12 tenant_settings como config store por tenant (no profiles). Defaults: D2
  subprocess args-en-lista (no comillas manuales), D3 flags de CLI [VERIFICAR],
  D4 delegación OFF por defecto.

**Qué sigue:** PAUSA — Módulo 1 completo. No arrancar otro módulo sin el usuario.
Candidatos: 2c (ContextCompressor), Fase 2 (3a-3e), Fase 3 (UX). Nuevos Riesgos #9
(flags [VERIFICAR] + invocación en vivo) y #10 (subprocesos del hub NO acotados por
RLS — relevante para multi-tenant en producción).

**Citas legales:** ninguna entregada al cliente. Único [VERIFICAR] abierto: los flags
de invocación de cada CLI del Agent Hub (no jurídico).

## 2026-06-13 — Sesión 5
**TL;DR:** Módulo 1d (LangGraph StateGraph + SSE + HITL) COMPLETO — el módulo más
delicado. Gate `test_hitl_flow.py` 19/19 contra DB + checkpointer Postgres reales
(LLM/embeddings mockeados). Regresión 8/8 suites verdes (test_rls intacto). PAUSA
antes de 1e.

**Qué construimos:**
- Investigación previa → 4 decisiones presentadas y aprobadas (decisions.md #9-#11).
  Hallazgos: el schema ya soportaba RRF (content_tsv+GIN+HNSW); mia_app sin CREATE;
  Hermes NO usa LangGraph (no había patrón de grafo en los refs).
- `agents/`: `state.py` (MatterState), `retrieval.py` (RRF híbrido), `graph.py`
  (5 nodos async; interrupt() 1ª línea de hitl_checkpoint), `checkpointer.py`
  (AsyncPostgresSaver).
- `execution/init_checkpointer.py` (migración: tablas de checkpoint por postgres +
  GRANT DML a mia_app).
- `api/routes/{_common,stream,hitl}.py` (SSE + approve/reject/edit; cruzado→401;
  eventos en español §G) + `api/main.py` monta los routers.
- `architecture/hitl_flow.md`, `pyproject.toml` (+langgraph 1.2.5,
  langgraph-checkpoint-postgres 3.1.0, sse-starlette 3.4.4).

**Qué decidimos (decisions.md #9-#11):**
- #9 Checkpoint: tablas LangGraph creadas por postgres + GRANT a mia_app; aislamiento
  por thread_id+JWT; RLS de dominio sigue activo. (Subclase RLS-aware descartada.)
- #10 interrupt() = 1ª línea de hitl_checkpoint_node.
- #11 approve/reject/edit reanuda y emite finalizing→done en la misma SSE.

**Qué sigue:** PAUSA — el usuario pidió NO arrancar 1e (Agent Hub) sin él presente.
Pendientes vivos: 2c (ContextCompressor, saltado), Riesgo #4 (LiteLLM librería vs
proxy), y los nuevos Riesgos #7 (invariante de aislamiento del checkpoint) y #8
(pooling del checkpointer).

**Citas legales:** ninguna entregada al cliente. El texto jurídico en fixtures y
prompts (p. ej. "caducidad de la reparación directa, 2 años") es ILUSTRATIVO, no una
cita verificada.

## 2026-06-12 — Sesión 4
**TL;DR:** Lote autónomo 1b→2d cerrado tras "procede" del usuario. 5 módulos con gate
verde (1b 32 · 1c 16 · 2a 19 · 2b 14 · 2d 20) + regresión completa offline 6/6 suites
(116 checks). PAUSA antes de 1d/1e.

**Qué construimos:**
- 1b: `prompt_builder` refactor a tabla única `LAYERS` (10 capas; L1-6 cached TTL 1h),
  `auxiliary_client.py` (`AuxiliaryClient.complete`→texto; `TASK_MODELS` completo),
  `test_prompt_builder.py` 32/32; corregida la aserción stale de 1a (15/15).
- 1c: `plugins.py` (`PluginManager` + 6 hooks en orden de ciclo de vida, intercepción
  real) cableado en `core.py` (run_turn pre/post_llm_call + start/end_session),
  `test_plugins.py` 16/16.
- Paquete nuevo `backend/mia/memory/` (memoria en EJECUCIÓN, ≠ `/memory/` de
  construcción): `tokens.py` (estimador compartido); 2a `profile_manager.py` (perfiles
  600/900 tok, frozen al inicio del asunto) 19/19; 2b `playbook_manager.py` (índice 3k
  siempre presente + contenido on-demand) 14/14; 2d `trace_capture.py` (JSONL por
  tenant, `to_sft_example`, 8 campos) 20/20.

**Qué decidimos:**
- 2c (ContextCompressor) se salta por orden del usuario (el plan iba 2a→2b→2d).
- Estimador de tokens = heurística offline ~4 chars/token (tiktoken baja vocab por red
  → no offline; el conteo exacto lo da el gateway). → Riesgo #5.
- Memoria en ejecución en `backend/mia/memory/` (≠ `/memory/` raíz). → Riesgo #6.
- streaming/fallbacks de `call_llm` y wiring de tracing al turno → diferidos a 1d
  (no estaban en estos gates).

**Qué sigue:** PAUSA. A la vuelta de Pipe: 1d (LangGraph StateGraph + SSE + HITL) y
1e (Agent Hub). Pendiente reconciliar Riesgo #4 (LiteLLM librería vs. proxy).

**Citas legales:** ninguna entregada al cliente esta sesión. El texto jurídico en los
fixtures de test y en las capas de prompt (p. ej. "caducidad 2 años") es ILUSTRATIVO,
no una cita verificada y no se afirma como fuente (regla global de verificación).

## 2026-06-12 — Sesión 3
**TL;DR:** Módulo 0 cerrado al 100% (ingest real verificado: chunks=3, con_embedding=3,
dim=1024). Módulo 1a completo (MiaAgent + router call_llm, gate 15/15). Módulo 1b en
progreso (prompt_builder de 10 capas + cableado con caché de sesión; falta el gate).

**Qué construimos:**
- Cierre del Paso 6 del Módulo 0: vault de prueba + tenant/matter + ingest end-to-end.
- 1a: `agent/{llm,core,__init__}.py`, config (LITELLM_BASE_URL/API_KEY, MIA_MODEL),
  +openai, `test_agent_core.py` 15/15, doc `architecture/prompt_builder.md`.
- 1b (parcial): `agent/prompt_builder.py` (10 capas, 3 tiers) + `core.py` cableado
  (caché de sesión `_cached_system_prompt`, `invalidate_prompt`, 5 campos-costura).

**Qué decidimos:**
- Router LLM delgado sobre LiteLLM (LiteLLM hace lo que los ~5.800 líneas de Hermes;
  alias en `litellm_config.yaml` como fuente única).
- `compression=claude-haiku` implementado como BLOQUEO por código (`_LOCKED_TASKS`),
  no como default (decisión #7).
- Las 10 capas: L1-6 stable (prefijo cacheado), L7-8 context, L9-10 volatile;
  L4/L6/L7/L9 son costuras no-op hasta los módulos que las llenan.

**Qué sigue:** cerrar el gate de 1b (`test_prompt_builder.py`) + corregir la aserción
stale de `test_agent_core.py` (el prompt creció de identidad a 10 capas). Después seguir
el plan 1c→2a→2b→2d con PAUSA antes de 1d/1e. NOTA: el `/effort high` del usuario falló
al parsear y se llevó ese plan como argumento — pendiente de reenvío.

## 2026-06-12 — Sesión 2
**TL;DR:** Módulo 0 completo — PostgreSQL 16 + pgvector 0.8.2 + RLS multi-tenant
(gate `test_rls.py` 12/12) + API FastAPI (`/health`, middleware JWT) + scaffolding
del backend. Solo falta correr el ingest real (gated por `VOYAGE_API_KEY`).

**Qué construimos:**
- Reset de la contraseña de `postgres` (Opción 3, pg_hba trust, script elevado).
- pgvector 0.8.2 instalado en Windows nativo (binario de terceros verificado
  por SHA256) + load-test OK.
- Backend `mia/`: schema+RLS, `init_db`, pool con contexto de tenant, middleware
  JWT, `/health`, `/matters` tenant-scoped, ingest (voyage-law-2), `test_rls`,
  scripts de arranque Modo B, `pyproject` + deps en `.venv`.

**Qué decidimos:**
- Embeddings `voyage-law-2` / `vector(1024)` vía LiteLLM (decisión #8).
- App se conecta como `mia_app` (NOSUPERUSER/NOBYPASSRLS); `postgres` solo
  migraciones. RLS fail-closed por GUC `app.tenant_id`.
- pgvector de terceros es válido SOLO para desarrollo (Riesgo #3 abierto).

**Qué sigue:** llenar `VOYAGE_API_KEY` y correr el ingest real (cierra Paso 6);
luego Módulo 1 (core del agente, 1a–1e).

---

## 2026-06-21 — Replan Ruta B + Fase 0 (cimientos multi-jurisdicción)
TL;DR: replan a "Plataforma Legal Hispana + Asistente Conversacional" (ver `Plan/Plan.md`).
Construida casi toda la Fase 0; validado el modelo. Continuación detallada en
`Plan/Plan.md` → "ESTADO DE EJECUCIÓN".

**Qué construimos:**
- 0.B: revalidé el entorno — los tests son SCRIPTS (no pytest); línea base REAL 23/25 (no 17/17).
- 0.C: migración 011 (versionado temporal + `audit_logs` + `matters.pending_review`), partición
  del corpus por jurisdicción en `sat_graph.py`, abstracción de Pack en `backend/mia/jurisdiction/`,
  y onboarding backend (`GET /api/jurisdictions` + persistencia + `resolve_jurisdictions`).
  +4 gates nuevos verdes (`test_jurisdiction_pack` 19, `test_sat_graph_jurisdiction` 11,
  `test_onboarding_jurisdictions` 5; `test_sat_graph` sigue 21). Cero regresiones.
- 0.A: validación sonnet vs qwen (créditos restaurados).

**Qué decidimos:**
- #24 packs de jurisdicción instalables (refina #22); #25 corpus particionado + versionado temporal
  (modifica #16); #26 ruteo de modelo por tier (nube=sonnet para citas; mia-local=tier soberano)
  — qwen FABRICA citas legales y es 6-19× más lento.

**Qué sigue (resto Fase 0, en orden):** 0.4 política de modelo por tenant (ContextVar en
`resolve_model`; cierra `test_curator`), 0.5 PII en capa común de `call_llm`, 0.6 test HALT de
privilegio, frontend onboarding (cierra `test_onboarding_horizontal`). Luego Fase 1 (núcleo
conversacional). 0.A ya NO está bloqueado (hay créditos). Proxy LiteLLM (4000) suele estar caído.
