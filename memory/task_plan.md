# Mia — task_plan.md
# Fases del proyecto · objetivos por módulo · checklists
# Última actualización: 2026-07-01

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
- [ ] Gmail/OneDrive vía Graph API (bloque 2 de la Fase 3, ver `mia-decisiones-pipe-fase3` en memoria)
- [ ] Quick win #5: checklist de pre-entrega ejecutado en el gate de aprobación — requiere
      aprobación previa de Pipe antes de tocar `hitl_checkpoint`
