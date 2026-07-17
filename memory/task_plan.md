# Mia — task_plan.md
# Fases del proyecto · objetivos por módulo · checklists
# Última actualización: 2026-07-17 (sesión 48)

Leyenda: [x] completado · [ ] pendiente · [~] en progreso

---

## Fase 5 — Autoaprendizaje horizontal + second brain (Sesión 20, 2026-06-20)
- [x] Auth real multi-tenant — users, register/login/me, bcrypt, JWT 7 días, frontend con localStorage (gate `test_auth.py` 20/20).
- [x] WikiManager — wiki por tenant en `$MIA_HOME/wiki/{tenant_id}`, conceptos, búsqueda, lint, archivo, HITL background (gate `test_wiki_manager.py` 18/18).
- [x] GEPA Loop — memoria procedural con drafts, propuestas HITL, grading y pruning (gate `test_gepa.py` 16/16).
- [x] Dreams semanal — replay, wiki update, GEPA, lint, nudges, weekly_report (gate `test_dreams.py` 16/16).
- [x] Conectores + UI second brain — endpoints Obsidian/Pinecone/wiki/report/skills y Pantallas 4/5 ampliadas (gate `test_second_brain_ui.py` 15/15).
- [x] Onboarding horizontal + pulido visual — sin opciones hardcodeadas de país/área/cortes/herramientas (gate `test_onboarding_horizontal.py` 10/10).

**Regla vigente:** el sistema es horizontal. Ningún módulo nuevo debe contener conocimiento jurídico específico hardcodeado; el conocimiento específico vive por tenant en wiki, playbooks y SOUL.md.

## Fase 0 — Plumbing
- [x] **Módulo -1** — CLAUDE.md + estructura `/memory/`  ✅ 2026-06-11
- [x] **Módulo 0** — Entorno nativo (Modo B) + DB (PostgreSQL 16 + pgvector) + RLS + ingestión  ✅ 2026-06-12
      (gate `test_rls.py` 12/12; **ingest real CERRADO** 2026-06-12: chunks=3, con_embedding=3, dim=1024)
- [~] **Módulo 1** — Core del agente (1a–1e):
  - [x] 1a — MiaAgent (núcleo del agente)  ✅ 2026-06-12 (gate `test_agent_core.py` 15/15)
  - [x] 1b — prompt_builder (10 capas) + AuxiliaryClient  ✅ 2026-06-12 (gate `test_prompt_builder.py` 32/32)
  - [x] 1c — plugins (6 hooks)  ✅ 2026-06-12 (gate `test_plugins.py` 16/16)
  - [x] 1d — LangGraph StateGraph + SSE streaming + HITL  ✅ 2026-06-13 (gate `test_hitl_flow.py` 19/19)
  - [x] 1e — Agent Hub (conectores a CLIs externos)  ✅ 2026-06-13 (gate `test_agent_hub.py` 38/38)

## Fase 1 — Memoria
- [x] 2a — ProfileManager  (PERFIL_ABOGADO ≤600 tok · PERFIL_DESPACHO ≤900 tok · frozen al inicio del asunto)  ✅ 2026-06-12 (gate `test_profile_manager.py` 19/19)
- [x] 2b — PlaybookManager  (índice ~3k tok siempre presente · contenido completo on-demand)  ✅ 2026-06-12 (gate `test_playbook_manager.py` 14/14) · +persistencia DB 2026-06-14 (decisión #18, Módulo 3b)
- [x] 2c — ContextCompressor  ✅ 2026-06-14 (gate `test_context_compressor.py` 22/22)
- [x] 2d — TraceCapture  (JSONL en mia-data/traces/ · compatible hermes-agent-self-evolution)  ✅ 2026-06-12 (gate `test_trace_capture.py` 20/20)

## Fase 2 — Knowledge Stores
- [x] 3a — SAT-Graph (Postgres puro, no Neo4j)  ✅ 2026-06-14 (gate `test_sat_graph.py` 21/21)
- [x] 3b — Curator (cron semanal)  ✅ 2026-06-14 (gate `test_curator.py` 23/23; decisión #18 playbooks en DB)
- [x] 3c — Obsidian indexer  ✅ 2026-06-14 (gate `test_obsidian_sync.py` 22/22; decisión #17 knowledge_chunks)
- [x] 3d — Pinecone (store externo opcional)  ✅ 2026-06-14 (gate `test_pinecone_connector.py` 14/14; condicional + noop)
- [x] 3e — Feedback processor  ✅ 2026-06-14 (gate `test_feedback_processor.py` 21/21; trazas v2, decisión #19)

**🎉 FASE 2 — KNOWLEDGE STORES COMPLETA · 2026-06-14** (3a-3e, las 15 suites verdes).

## Fase 3 — UX  (DIVIDIDA en dos sesiones, decisión #20)
**Backend (Sesión 14, 2026-06-14) ✅** — superficie `/api/*` completa + persistencia de perfil
(`firm_profiles`) + parser PDF/Word. Gate `test_ux.py` 18/18. SOP `architecture/api_surface.md`.
**Frontend (Sesión 15, pendiente)** — scaffold Next.js 14 + las 5 pantallas, contra la API ya
verificada. `frontend/` NO existe aún (el Módulo 0 no lo creó).
- [x] Backend /api/* (las 5 pantallas)  ✅ 2026-06-14 (gate `test_ux.py` 18/18)
- [x] 4a — Pantalla 1 · Lista de asuntos (Next.js)  ✅ 2026-06-14
- [x] 4b — Pantalla 2 · Workspace (chat + SSE)  ✅ 2026-06-14
- [x] 4c — Pantalla 3 · Revisión de borrador  ✅ 2026-06-14
- [x] 4d — Pantalla 4 · Memoria (perfil + playbooks + sugerencias)  ✅ 2026-06-14
- [x] 4e — Pantalla 5 · Dashboard  ✅ 2026-06-14

**🎉 FASE 3 — UX COMPLETA · 2026-06-14** (backend /api/* S14 + 5 pantallas Next.js S15;
gate `test_ux.py` 25/25, `npm run build` ✓).

## Fase 4 — Personalidad
- [x] **Módulo 5** — Entrevista SOUL.md + prueba E2E  ✅ 2026-06-14 (gate `test_e2e.py` 25/25; decisión #21)

**🎉🎉 PROYECTO COMPLETO · Mia v0 operativa · 2026-06-14** — Fase 0 + Módulo 1 (1a-1e) + Fase 1
(2a-2d) + Fase 2 (3a-3e) + Fase 3 (UX) + Fase 4 (Módulo 5). Los 17 gates verdes (358 checks).

---

**Estado actual:** **PROYECTO COMPLETO — Mia v0 operativa (2026-06-14).** Fase 0 + Módulo 1
(1a-1e) + Fase 1 (2a-2d) + FASE 2 (3a-3e) + FASE 3 (UX) + **FASE 4 (Módulo 5: SOUL.md + E2E)**.
Regresión **17/17 suites verdes**: 1a 15 · 1b 32 · 1c 16 · 2a 19 · 2b 14 · 2c 22 · 2d 20 ·
test_rls 12 · 1d 19 · 1e 38 · 3a 21 · 3c 22 · 3d 14 · 3b 23 · 3e 21 · UX 25 · **Módulo 5 (E2E) 25**.
(**358 checks.**) `test_rls` 12/12 intacto.
Módulo 5 cerrado (2026-06-14): SOUL.md + entrevista de onboarding (19 preguntas del Doc 4, decisión
#21); `$MIA_HOME/soul_{tenant}.md` (sin DB); wiring del `soul_snapshot` al grafo (None-safe, cierra
en la práctica el hueco del Riesgo #11) + a la Capa 1 del MiaAgent; 3 endpoints `/api/onboarding/*`;
pantalla de onboarding + gate de redirección; gate `test_e2e.py` 25/25; SOPs
`architecture/{soul_interview,e2e_runbook}.md`.
**Antes del PRIMER CLIENTE (no bloquean v0, sí producción/multi-tenant):** #23 login real ·
#25 diagnóstico/flags UI · #19 Curator sin HITL ⚖️ · #13 rol curador SAT-Graph 🔐 · #3 pgvector
oficial para clientes · #26 SOUL generado por LLM (revisión humana) · #27 triad_mode no implementado.
Recomendado: smoke test VIVO en navegador con LLM real (runbook).
Deuda del grafo cerrada (2026-06-14): Riesgo #11 por reframe (decisión #14), Riesgo #12
corregido (resumen role="user", decisión #15).
3a cerrado (2026-06-14): corpus jurídico COMPARTIDO en Postgres (decisión #16); migración
+ ingest semilla corridos; gate 21/21; SOP `architecture/sat_graph.md`.
3c cerrado (2026-06-14): Obsidian indexer → tabla NUEVA `knowledge_chunks` (decisión #17,
no toca documents/chunks); sync incremental por hash + chunking por encabezados; scheduler
propio; gate 22/22; SOP `architecture/obsidian_sync.md`.
3d cerrado (2026-06-14): Pinecone connector — store externo OPCIONAL y CONDICIONAL (decisión
#2); noop sin API key; aislamiento por namespace; gate 14/14; SOP
`architecture/pinecone_connector.md`.
3b cerrado (2026-06-14): Curator cron — consolida playbooks por similitud (pgvector <=>, >0.85)
y poda por 90d; persistencia de playbooks en DB (decisión #18, PlaybookManager DB-backed con
interfaz intacta); job `curator_weekly` (168h); gate 23/23; SOP `architecture/curator.md`.
3e cerrado (2026-06-14): Feedback processor — lee trazas v2 (decisión #19, +señales HITL),
detecta rechazos/ediciones/sin-resultado y PROPONE mejoras a playbooks (status pending, no
aplica); watermark por día; job `feedback_daily` (24h); gate 21/21; SOP
`architecture/feedback_processor.md`. **→ Fase 2 COMPLETA.**
Módulo 5 cerrado (2026-06-14): SOUL.md + onboarding (decisión #21); ver el bloque "Estado actual"
arriba. **→ Fase 4 COMPLETA · PROYECTO COMPLETO.**
**Siguiente:** ya no hay módulos pendientes. Trabajo futuro = endurecimiento para producción/primer
cliente (riesgos abiertos) + smoke test vivo en navegador (`architecture/e2e_runbook.md`).

---

## Pendientes — ruta Codex (`D:\Codex\Mia-Super Agent\mia`)
- ✅ **Patrones Hermes v0.17.0 COMPLETO (2026-06-30, rama `feat/hermes-v017-impl` → merge a `main`)**
  — H.1 taxonomía de errores LLM (`error_classifier`, gate 50/50) · H.2 Curator HITL dry-run→propuesta
  (cierra Riesgo #19) · H.3 `session_search` FTS sin LLM (tabla `traces`+GIN, gate 21/21) · H.4 skills
  self-improving con propuesta pending (gate 14/14) · **H.5** cadena de fallback de proveedor en
  `call_llm` + `TurnLLMState` (gate `test_llm_fallback` 25/25) · **H.6** playbooks `protected`
  inmunes al mantenimiento (migración 014, gate `test_playbooks_protected` 19/19).
- ✅ **Correcciones post-review Cursor (2026-06-30)** — C.1-C.4 (commit `357ccea`) + **C.5** (Curator
  legacy con guard `MIA_ALLOW_CURATOR_LEGACY_RUN`) + **C.6** (`traces/search` con `matter_id`
  obligatorio + `assert_owns_matter`), commit `73acee4`.
- ✅ **Regresión final 32/32 gates verdes** · `test_rls` 12/12 (HALT) intacto · rama mergeada a `main`.
- ⬜ **Riesgo #33 (próxima sesión):** recuperación por nodo ante `CONTEXT_TOO_LONG` en `graph.py`
  (el `ContextCompressor` en `_llm` es no-op sobre prompts de 2 mensajes de analysis/draft).
- ✅ **Smoke test vivo COMPLETO (2026-06-30)** — 3 servicios operativos (PG/pgvector 5432, Ollama
  11434, LiteLLM proxy 4000). `claude-sonnet` confirmado por el proxy (HTTP 200, sin rebote de
  créditos). HITL verificado con ambos desenlaces (`approved`/`rejected`) en trazas reales.
  `activated_playbooks` cableado end-to-end (sin activación observada: tenant sin playbooks
  sembrados, Riesgo #20). 3 bugs de plataforma reparados (SelectorEventLoop Windows, HITL
  fail-closed, ciclo de vida de turno + SSE error). Detalle en `progress.md` 2026-06-30.
- ⬜ Sembrar playbooks reales para observar activación end-to-end (cierra del todo #20/#31).
- ⬜ Cablear `prompt_builder` (10 capas) al grafo.
- ⬜ Corregir ruta del proyecto en `CLAUDE.md` (`D:\Inteligencia Artificial\…` → `D:\Codex\…`).
- ⬜ Investigar y documentar trabajo no registrado (`gepa.py`, `dreams.py`, `second_brain_ui`) + auth real (#23).
- ⬜ Separar LiteLLM en su propio venv antes de reiniciar la API en producción (Riesgo #32).

---

## Plan maestro 2026-07-01 (sesión 21)
Plan completo: `C:\Users\jfeli\.claude\plans\quiero-que-elabores-un-streamed-wand.md`
Regresión final de la sesión: **40/40 suites verdes** · capa 2 (revisor independiente) en los 10 checkpoints.

| CP | Estado | Qué es | Gate |
|----|--------|--------|------|
| CP0 | ✅ | LiteLLM en `.venv-litellm` propio + pins exactos + gate `check_env_pins` en arranque y regresión (cierra Riesgo #32) | pins 9/9 |
| CP2 | ✅ | Motor por suscripción (`claude -p`) + 3 políticas por tenant (decisión #27); turno vivo 176s/19k chars sin billing API | `test_model_policy` 40/40 |
| CP1 | ✅ | Shrink por nodo ante CONTEXT_TOO_LONG (cierra Riesgo #33) | `test_context_recovery` 34/34 |
| CP4 | ✅ | Import de guías del despacho (`POST /playbooks/import`, .md/.txt/.docx) | `test_playbook_import` 21/21 |
| CP5 | ✅ | Diagnóstico visible + punto naranja `pending_review` (cierra el grueso del Riesgo #25) | `test_ux` 29/29 |
| CP-B1 | ✅ | Modo asistente — conversación libre con memoria (migración 015; decisión #28) | `test_assistant` 32/32 |
| CP-B2 | ✅ | Puente Telegram opt-in single-chat (decisión #29; guía `docs/telegram-setup.md`) | `test_telegram_bridge` 22/22 |
| CP-C1 | ✅ | Conector carpetas disco/OneDrive/Google Drive (migración 016; decisión #30) | `test_local_folders` 39/39 |
| CP-C2 | ✅ | Vault Obsidian bidireccional (Mia escribe bajo `Mia/`) + instalación guiada (decisión #32) | `test_vault_write` 34/34 |
| CP3 | ✅ | Conocimiento del despacho al análisis (cierra Riesgo #16; decisión #31) — APROBADO por Pipe con A/B en vivo | `test_retrieval_knowledge` 35/35 |
| CP6 | 🟡 | IMPLEMENTADO en rama `feat/cp6-una-sola-voz` (commit eceb59a): fachada de 10 capas para analysis/draft/edit, cierre estructurado del diagnóstico, validación del SOUL con reintento+fallback (también en update_soul). Regresión 41/41; revisor capa 2 APROBADO (3 mayores + 3 menores corregidos). Comparación A/B EN VIVO entregada a Pipe — **PENDIENTE su aprobación para merge** | `test_prompt_builder` 46/46 · `test_e2e` 31/31 |
| CP7 | ✅ | Frontend sincronizado: pestaña Habilidades, Importar guías (con detalle), target en sugerencias, propuestas del Curator (Aprobar/Rechazar), selector Motor de IA (persiste, sin jerga), Recordatorios con hora + cancelar confirmado, triad_mode fuera del onboarding (Riesgo #27), panel Diagnóstico listo para el resumen de CP6. Capa 3 de Cursor PENDIENTE (HANDOFF) | `test_second_brain_ui` 26/26 · `npm run build` ✓ |
| CP-B3 | ✅ | Proactividad: recordatorios en lenguaje natural (parser determinista + regla dura de plazos procesales), aviso de borradores con debounce 24h y reporte semanal por Telegram (jobs `reminders_due` 5min / `pending_review_notify` 1h; migración 017) | `test_reminders` 64/64 |
| CP-B4 | ⬜ | Herramientas reales del asistente (agenda, acciones) | — |
| CP-C3 | ✅ | Cierre del circuito GEPA: las propuestas de mejora apuntan al playbook que participó en las trazas rechazadas/editadas (no a uno arbitrario), se redactan sobre el contenido real, aplicar es reversible (previous_content) y el abogado ve QUÉ procedimiento se modifica. Vuelta EN VIVO pendiente de playbooks de Pipe (Riesgo #20) | `test_feedback_processor` 26/26 · `test_gepa` 18/18 · `test_trace_capture` 23/23 |
| CP-C4 | ✅ | "Configura a Mia": GET /api/setup/status (6 pasos detectados fail-soft, caché 60s, solo lectura), skip/unskip retomable en tenant_settings.config['setup'], página /configurar + guía por chat del asistente. Recorrido vivo cronometrado con Pipe PENDIENTE de él. Capa 3 Cursor pendiente | `test_setup_wizard` 21/21 |
| CP8 | ⬜ | Endurecimiento pre-cliente — EN PAUSA por decisión de prioridad (uso diario Lexia primero) | — |
| CP9 | 🟡 | Equipo de especialistas (encargo de Pipe 2026-07-02 tras aprobar CP6): facts → research (SAT-Graph por jurisdicción) → cruce → redacción → verificación determinista de citas (anota [VERIFICAR] sin marca/respaldo) → emisión Word (draft.docx). IMPLEMENTADO en rama `feat/cp9-equipo-especialistas` (commit a22b72c); capa 2 APROBADO CON CORRECCIONES (M1 cupo compresión por nodo · M2 ReDoS) — corregidas con checks cp9-37..41. Regresión 43/43. **PENDIENTE: comparación A/B en vivo + decisión de Pipe para merge** | `test_document_pipeline` 41/41 · `test_hitl_flow` 19/19 |


## Roadmap 5 olas (aprobado por Pipe 2026-07-02) — plan completo en `docs/plan-ejecucion-olas.md`
De los análisis de Hermes/ClaudeOS/OpenJarvis (`docs/analisis-referencias-2026-07.md`). Pipe
aprobó ejecutar LAS 5 OLAS en este orden. Arrancar por CP-S1 en terminal nueva.

| CP | Ola | Qué es | Ref |
|----|-----|--------|-----|
| CP-S1 | 1 Confidencialidad | Cuarentena universal de contenido no confiable (generalizar el fencing a todo lo externo) | hermes `agent/tool_dispatch_helpers.py` |
| CP-S2 | 1 | Aislamiento fail-closed de secretos + redacción congelada de logs | hermes `agent/secret_scope.py`, `redact.py` |
| CP-S3 | 1 | Endurecimiento de conectores/streaming (argv-exec, tripwire de secretos, heartbeat SSE) | claudeos `vite.config.ts` |
| CP-P1 | 2 Plazos | Motor de vigilancia programada (wake-gate, jobs no_agent) | hermes `cron/scheduler.py` |
| CP-P2 | 2 | Blueprints + sugerencias consent-first (plazos procesales = confirmación humana) | hermes `cron/blueprint_catalog.py`, `suggestions.py` |
| CP-V1 | 4 Valor | "Valor entregado" = horas ahorradas × tarifa − costo, en el panel | claudeos `src/lib/time-saved.ts` |
| CP-V2 | 4 | Auto-diagnóstico prescriptivo riguroso (severidad×impacto×certeza, anti-invención) | claudeos `skills/dream/SKILL.md` |
| CP-Z1 | 3 Voz | Dictado web con STT local (faster-whisper) — **DECISIÓN Pipe: local vs nube** | openjarvis `src/openjarvis/speech/` |
| CP-Z2 | 3 | Respuesta hablada (TTS local) + streaming incremental por frases | openjarvis `speech/tts.py`, `server/stream_bridge.py` |
| CP-Z3 | 3 | (Opcional) Overlay de escritorio omnipresente (cliente delgado) | openjarvis `frontend/src-tauri/src/lib.rs` |
| CP-E1 | 5 Escala | Observer hooks (auditoría) + middleware (políticas por tenant) | hermes `docs/observability/`, `docs/middleware/` |
| CP-E2 | 5 | Adjuntar pruebas por referencia (@expediente/@carpeta) | hermes `agent/context_references.py` |
| CP-E3 | 5 | Personas jurídicas especializadas editables | claudeos Pantheon |
| CP-E4 | 5 | Banco de pruebas de calidad (eval) — **datos reales = aprobación Pipe** | hermes `batch_runner.py` |
| CP-E5 | 5 | Delegación multi-agente + tablero de misión por expediente | hermes `tools/delegate_tool.py`, kanban |
| CP-E6 | 5 | Relay multi-canal (WhatsApp/correo) + MCP con seguridad | hermes `gateway/relay/`, `tools/mcp_tool.py` |

**Orden de ejecución:** Ola 1 → Ola 2 → Ola 4 → Ola 3 → Ola 5.

## Encargo directo de Pipe (2026-07-02, próxima sesión — PRIORIDAD)
| Tarea | Estado | Qué pidió |
|----|--------|--------|
| CP-C4b | 🟡 | Wizard "Configura a Mia" explicativo estilo onboarding: cada paso trae `guia` (qué es / para qué al despacho / cómo paso a paso) + mapa `secciones` de Mia; el asistente acompaña por chat. Rama `feat/cp-c4b-wizard-onboarding`. Capa 2 APROBADO CON CORRECCIONES (L1 guía truncada; U1/U2/U4 guías describían UI inexistente → reescritas a la realidad de hoy; UI faltante documentada para Cursor). Gate `test_setup_wizard` 30/30 · regresión 43/43. **PENDIENTE merge de Pipe** |

---

## Fase 3 · frentes B/C + Data Factory del corpus (Sesión 35, 2026-07-08)
- [x] Bugfix FTS de investigación (`build_fts_query`, gate `test_research_query.py` 11/11)
- [x] Frente B (aprendizaje): B1 motivo del rechazo en la traza · B2 `POST /api/learning/run`
      ("Revisar ahora") · B4 wiki_correction se aplica de verdad
- [x] Fase 3 · frente C (bóveda visible): `vault_export.py` backfill de playbooks + fichas del corpus
- [x] Data Factory del corpus (`rag/corpus_factory.py` + `jurisdiction/packs/co/corpus_sources.json`),
      reemplaza la semilla hardcodeada de `ingest_corpus.py` (deprecado)
- [x] Regresión 66/66 + revisor capa 2 (5 hallazgos corregidos) — ver `progress.md` sesión 35
- [x] 3 de 5 quick wins de `docs/analisis-claude-for-legal.md` (commit `c11fb71`, ver progress.md):
      #1 3er valor en el borrador · #4 menú de próximos pasos + pregunta de segundo orden en el
      análisis · #3 freshness declarativo del pack. #2 ya estaba implementado (CitationReview.tsx);
      #5 pendiente de aprobación de Pipe (toca el gate de HITL/"resultado legal")
- [x] Push a `origin/main` de los 6 commits de la sesión (`9f62b4e..c11fb71`)
- [ ] Capa 3 visual (botón "Revisar ahora") — pendiente de Pipe en vivo
- [x] Gmail/OneDrive vía Graph API (bloque 2 de la Fase 3, ver `mia-decisiones-pipe-fase3` en
      memoria) — ✅ Sesión 36, 2026-07-09
- [ ] Quick win #5: checklist de pre-entrega ejecutado en el gate de aprobación — requiere
      aprobación previa de Pipe antes de tocar `hitl_checkpoint`

## Fase 3 · bloque 2 — Fuentes remotas del expediente: Gmail + OneDrive vía Graph API (Sesión 36, 2026-07-09)
- [x] Fase 1 — cimientos OAuth multi-proveedor (`tenant_oauth_tokens` PK tenant+provider, migración
      `027_remote_sources.sql`, `oauth.py` con features por proveedor) — gate `test_mailbox_multi.py` 21/21
- [x] Fase 2 — correos del caso → expediente (`api/routes/matter_mail.py` buscar/vincular, cuerpo +
      adjuntos como documentos `origin='mail'`, dedupe sha256) — gate `test_mail_to_matter.py` 24/24
- [x] Fase 3 — OneDrive remoto SELECTIVO de solo lectura (`connectors/graph_drive.py`,
      `api/routes/remote_drive.py` browse/CRUD/sync) — gate `test_remote_drive.py` 35/35
- [x] Fase 4 — UI: `OneDriveFolderPicker`, `OneDriveSourcesSection`, `MatterDriveFolder`,
      `MailSearchDialog`, `MailboxSection` con checkbox de OneDrive
- [x] Capa 2: dos revisores adversariales (seguridad APROBADO sin bloqueantes; corrección 3 mayores +
      6 menores, todos corregidos en `c9f2a32`) — ver `progress.md` sesión 36 y Riesgo #54
- [x] Regresión 69/69 suites ×2 (`test_rls`/`check_env_pins` HALT intactos)
- [ ] Capa 3 EN VIVO de Pipe/Cursor (conectar cuenta real, navegar carpetas, probar 503,
      vincular correos, responsive) — pendiente
- [ ] ACCIÓN DE PIPE: registrar apps OAuth (Azure AD + Google Cloud) y poner llaves en `.env`
- [x] Deuda: sincronización PROGRAMADA de fuentes OneDrive — ✅ cerrada en Sesión 37 (bloque 3b)

## Fase 3 · bloque 3 — OCR local + sincronización programada de OneDrive (Sesión 37, 2026-07-09)
- [x] Bloque 3a — OCR local para PDFs escaneados (`ingest/ocr.py` rapidocr-onnxruntime CPU local,
      fallback página a página en `ingest/extract.py`, honestidad por segmento, fail-soft
      150 págs/10 min) — gate `test_ocr_ingest.py` 26/26
- [x] Bloque 3b — cron de OneDrive remoto cada 6h (`sync_tenant_sources` con throttle 1h,
      fail-soft por fuente, lock compartido con el sync manual) — `test_remote_drive.py` 44/44
- [x] Capa 2 adversarial: 3 mayores + 4 menores TODOS corregidos (`ea28423`) + guarda has_body
      en carpetas locales (`315dbd1`) — ver Riesgo #55
- [x] Regresión completa 70/70 suites ALL PASS (corrida en la retoma post-apagón;
      `test_rls`/`check_env_pins` HALT intactos; línea base 69 → 70)
- [ ] Decidir push a `origin/main` de los 4 commits (`ad16a64`..`315dbd1`)

## Evolución de producto — BLOQUE A: Proyectos + carpetas sin fricción (Sesión 39, 2026-07-09)
Plan completo (Bloques A/B/C) en `memory/plan-evolucion-producto.md`, aprobado por Pipe.
- [x] A0 — migración `028_projects_multifolder.sql` (`matters.kind`, `documents.source_id`,
      `documents.body`, `ck_documents_origin` gana `'mia'`, backfill conservador
      `HAVING count(*)=1` espejado a `origin='drive'`) — `execution/init_projects_multifolder.py`
- [x] A2 — fix del bug latente de poda cruzada (`local_folders.py` acota por `source_id`) +
      superficie plural de carpetas por expediente (`matter_folders.py`, tope 10) —
      `test_matter_folders_multi.py` 30/30
- [x] A1 — navegador seguro de carpetas (`safe_browse_roots`/`browse_folder`, fail-closed,
      `MIA_DISABLE_FOLDER_BROWSE`) + `FolderPicker.tsx` — `test_folder_browse.py` 15/15
- [x] A3 — vista "Fuentes" unificada (`matter_sources.py` + `FuentesPanel.tsx`) —
      `test_matter_sources.py` 26/26
- [x] A4 — pestaña "Proyectos" (kind, outputs `.docx`, `build_project_graph()` sin HITL,
      `proyectos/page.tsx` + `proyectos/[id]/page.tsx`) — `test_projects.py` 33/33
- [x] Capa 2: revisión adversarial multi-agente, 12 hallazgos confirmados (2 bloqueantes de
      pérdida de datos, 2 mayores, 5 menores), TODOS corregidos salvo 2 notas de deuda aceptadas
      (Riesgo #56 abierto; Riesgo #57 RESUELTO en esta sesión) — ver `progress.md` sesión 39
- [x] Regresión completa 74/74 suites ALL PASS (línea base 70 → 74); `test_rls`/`check_env_pins`
      HALT intactos; `npm run build` verde
- [ ] Capa 3 EN VIVO de Pipe (Proyectos, FolderPicker, FuentesPanel) — pendiente

## Evolución de producto — BLOQUE B: Guías de trabajo asistidas + gobernanza de skills (Sesión 40, 2026-07-10)
Plan completo (Bloques A/B/C) en `memory/plan-evolucion-producto.md`, aprobado por Pipe.
- [x] B0 — CRUD + versiones de playbooks (migración `029_playbook_versions.sql`, RLS FORCE
      patrón 023, `origin` en metadata, archivar/restaurar, restaurar versión) —
      `execution/init_playbook_versions.py`
- [x] B1-B2 — motor de entrevista stateless (`interviewer.py`, nunca escribe en DB) +
      `POST /api/guides/interview` (`guides.py`) + `GuideInterviewWizard.tsx` — botón
      "Crear con Mia" en Conocimiento — `test_guide_interview.py` 25/25
- [x] B3 — botón "Convertir en guía" en el asunto (solo con borrador aprobado, `hitl_outcome`
      expuesto vía `HITL_OUTCOME` en `state.py`) + precarga de contexto del asunto
- [x] B4 — `source_matters` en propuestas + "Editar antes de aplicar" + subtabs "Guías y
      documentos" / "Lo que Mia sabe hacer" fusionados en "Guías y habilidades"
- [x] Capa 2: 4 revisores adversariales independientes, 10 hallazgos confirmados (3 mayores +
      7 menores), TODOS corregidos — ver `progress.md` sesión 40
- [x] Regresión completa 76/76 suites ALL PASS (línea base 74 → 76,
      `test_playbook_versions.py` 59/59, `test_guide_interview.py` 25/25); `test_rls`/
      `check_env_pins` HALT intactos; `npm run build` verde
- [ ] Capa 3 EN VIVO de Pipe (wizard "Crear con Mia", historial de versiones, "Convertir en
      guía", "Editar antes de aplicar") — pendiente
- [ ] Siguiente: BLOQUE B — guías de trabajo asistidas + gobernanza de skills

## Fase 4 · BLOQUE INSTALADOR (Sesión 42, 2026-07-10) — plan de 4 fases aprobado por Pipe
- [x] F1a — Bundle backend PyInstaller reproducible en el repo (`packaging/`: entry + spec +
      build_backend.ps1; 459.5 MB; /health + 401 verificados sin Python; smoke OCR OK;
      voz fuera por construcción) — gate `test_packaging.py` 23/23
- [x] F1b — Frontend autocontenido (`output: 'standalone'` + node.exe portable v22.23.1
      pineado; ensamblado 103.5 MB; humo con puerto libre + identidad del listener) —
      gate `test_frontend_packaging.py` 24/24
- [x] Blindaje cáscara (adelanto F2): single-instance 2.4.2, CSP + splash externalizado,
      pg_isready tri-estado, identidad backend/frontend en 4 caminos — gate
      `test_shell_hardening.py` 42/42; cargo build exit 0
- [x] Capa 2 ×2 (empaquetado y cáscara): 1 BLOQUEANTE + 4 MAYORES + 5 menores, TODOS corregidos
- [x] Regresión completa 82/82 ALL PASS (79 base + 3 gates nuevos); test_ux recalibrado
      (timeout build 300→600s post-standalone) y re-verificado 41/41
- [x] F2 — Primer arranque automático (sesión 43, 2026-07-11): `mia.setup.first_run` invocable
      como `mia-backend.exe --first-run` (app_dir + .env semilla atómico con secretos generados
      + initdb endurecido loopback/scram + migraciones 003→030 + checkpointer + marcador
      `.mia-setup-complete` al final; idempotente y auto-reparable) — gate `test_first_run.py`
      68/68 con initdb real y login real de mia_app
- [x] F2 — LiteLLM 2º exe: `.venv-litellm` creado + `entry_litellm.py` (cost-map → allowlist
      .env → scrub DATABASE_URL/PG_* → dotenv neutralizado → CLI) + build real 108 MB con humo
      vivo (liveliness 200, /v1/models 200 con Bearer/alias, 401 sin Bearer, bind SOLO
      127.0.0.1 con intento LAN rechazado) — gate `test_litellm_packaging.py` 60/60
- [x] F2 — Cáscara: tokens `${exe_dir}`/`${local_app_data}`, paso `setup` con gatillo triple
      (marcador+PG_VERSION+.env, timeout 15 min), LiteLLM 4º servicio con identidad
      (/v1/models+Bearer+alias), child_died antes del health en los 3 bucles, shutdown inverso
      — `orchestration.installer.json` plantilla estática; gate `test_shell_hardening.py` 77/77;
      cargo build exit 0
- [x] F2 — Capa 2 ×3 (bootstrap, cáscara, litellm): 6 MAYORES + 5 menores confirmados, TODOS
      corregidos y re-verificados (detalle en progress.md sesión 43)
- [x] F2 — Regresión completa 84/84 ALL PASS (82 base + test_first_run + test_litellm_packaging)
- [x] F3 — Wizard de bienvenida (sesión 44, 2026-07-11): alcance EXPANDIDO por Pipe (el
      onboarding existente "no estaba chévere") — login + registro + activación de llaves +
      onboarding rediseñados como UNA experiencia cinematográfica cohesiva (infraestructura
      `frontend/app/_welcome/` con framer-motion, primer uso real en el repo). Backend de
      activación (`welcome.py`: `/api/welcome/status`/`keys`/`keys/test`, `env_writer.py`,
      migración `031_welcome_bootstrap.sql`). Clave de búsqueda (Voyage) activable EN CALIENTE;
      respaldo/OpenRouter diferidos con aviso fuerte de reabrir (Riesgo #60) — gate
      `test_welcome_keys.py` 39/39; regresión 85/85 ALL PASS; capa 2 con 4 revisores
      independientes, 0 bloqueantes, todos los mayores/menores corregidos. Capa 3 EN VIVO de
      Pipe PENDIENTE.
- [x] F4 — instalador NSIS de doble clic ENSAMBLADO (sesión 45): `packaging/build_installer.ps1`
      (recompila 3 payloads + copia pgsql portable con pgvector, sin pgAdmin) + `bundle.resources`
      en tauri.conf.json (payloads + `orchestration.json` renombrado junto al exe, sin subcarpeta
      `resources/` — VERIFICADO empíricamente con install en frío aislado) + `offlineInstaller`
      (instala sin internet) + gate `test_installer_bundle.py`. Salida real:
      `Mia_0.1.0_x64-setup.exe` ~452 MB. console=True (la cáscara oculta la ventana con
      CREATE_NO_WINDOW; cierra Riesgo #59 pt 3/7). Regresión: línea base 85→86 suites; capa 2
      con 3 revisores, 5 hallazgos corregidos. **PENDIENTE = capa 3 de Pipe: E2E en máquina 100%
      limpia (doble clic en frío) — física, no automatizable en la máquina de dev.**
- [x] Reinicio automático del proxy LiteLLM tras guardar clave en el wizard (Riesgo #60) — HECHO en
      la sesión 46 (2026-07-12): comando Tauri `restart_litellm` + invocación desde `/activar`;
      Riesgo #60 CERRADO. Resta solo la confirmación VISUAL en la capa 3 de Pipe.
- [ ] Pre-lanzamiento (acción de Pipe): registrar Azure Trusted Signing (firma) — no bloquea
      el build del equipo

## Sesión 48 (2026-07-16/17) — Agnosticismo de jurisdicción · Agent Hub y Banco de oro · criterio de MIA
- [x] **Entorno** — la DB portable vuelve a arrancar (clúster en `tools/pgdata-portable`, puerto
      55432, binarios mínimos + `share/*` del `-full` sin machacar `share/extension/`). Trampas
      documentadas en progress.md sesión 48.
- [x] Bug crítico de la bienvenida: el motor elegido sí se guarda (ruta sin `/api`) — `ca7cd74`
- [x] Frontend: confianza (deep-link al borrador, fallos que dejan de ser silenciosos, 409 por
      status), agnosticismo (locale del equipo, placeholders sin país, detonador de cuantía con
      UVT/UIT/UMA/IPREM/SMI y €) y legibilidad (`--cta-strong`, 5.10:1 medido sobre el fondo real)
      — `960553b`, `32880a3`
- [x] **Agnosticismo backend** — patrones/pistas/léxico al pack `co/` (byte-idénticos), migración
      036 (DEFAULT de jurisdicción a 'generic'; la decisión pasa a Python, nunca 'co'), ejemplos del
      onboarding sin plaza concreta, prompt del anonimizador sin país. **4 fugas de confidencialidad
      cerradas.** Gate `test_jurisdiction_agnostic` 75/75 — `902bd90`, `c4b57f5`, `09d00c7`, `47f5578`
- [x] Dos gates en rojo desde sesiones anteriores, corregidos: `connector_hardening` 37/37 y
      `value_delivered` 28/28 (la línea base de "84 suites ALL PASS" no era cierta) — `16e9eec`, `9a93341`
- [x] **Agent Hub** — la delegación se cablea de verdad (`delegate_intent` determinista +
      `delegate_proposal` con HITL + candado `hub_gate` fail-closed + merge jsonb atómico en
      `hub_config`); migración 037. Gates `delegation_decide` 103/103, `delegation_wiring` 41/41,
      `agent_hub` 46/46 — `65e521d`
- [x] **Banco de oro** — desbloqueado: consentimiento concedible (`/settings/eval-consent`),
      relectura de un caso (`GET /api/gold-cases/{id}`) y captura armada server-side (el material sin
      anonimizar nunca pasa por el navegador). Gates `gold_cases_api` 55/55, `gold_cases` 42/42 —
      `65e521d`
- [x] **Pantallas** de ayudantes externos (dentro de Conexiones) y del banco de oro (tab propio
      "Calidad"). Gate `test_config_tabs` 21/21 (era 14) — `84a059b`
- [x] El examen mide sustancia: 3 señales deterministas en `flags_informativos` (fuera de `ok`).
      Gate `eval_substance` 37/37 (nuevo) — `aa8ac3a`
- [x] **Los 8 principios** — Sala de estrategia inyectada en el borrador (0 llamadas nuevas),
      anatomía del argumento, wiki cableado en lectura, confianza con rechazo, SOUL con HITL +
      versionado + tope que rechaza, juez de conflictos del Curator, frontmatter/wikilinks de
      Obsidian. Migraciones 038/039/040. Gates `argument_engine` 65/65, `soul_guard` 47/47,
      `curator_conflicts` 38/38, `wiki_reading` 36/36, `obsidian_sync` 73/73, `dreams` 44/44,
      `curator_hitl` 29/29 — `9019ee6`
- [x] **Gates que estaban DIFERIDOS y hoy están verdes** (con la DB arriba): `test_rls` 19/19 (HALT),
      `test_welcome_keys` 41/41, `test_setup_wizard` 28/28
- [ ] **Capa 3 EN VIVO de Pipe** — E2E del instalador en máquina limpia · recorrido visual · login
      real de NotebookLM · **nuevo:** delegación en vivo (Riesgo #66/D3) y banco de oro de punta a
      punta
- [ ] Deuda abierta de esta sesión (ver bugs-and-risks.md #66-#74): persistir el diagnóstico del
      turno (#68), "Patrones rechazados" de dreams al modelo (#69), endpoint de historial del asunto
      (#70), `index_trace` best-effort (#71), medir la puntería del juez del Curator (#67)
- [ ] Backlog acotado del sesgo colombiano: FTS 'spanish' (migración de índices) · voz TTS es_MX
      (una voz por variante)
