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
| CP6 | ⬜ | `prompt_builder` (10 capas) cableado al grafo — ALTO IMPACTO, requiere diff a Pipe antes de ejecutar | — |
| CP7 | ⬜ | Sincronización frontend: selector de motor + UI de conectores/curator/skills/import de guías | — |
| CP-B3 | ✅ | Proactividad: recordatorios en lenguaje natural (parser determinista + regla dura de plazos procesales), aviso de borradores con debounce 24h y reporte semanal por Telegram (jobs `reminders_due` 5min / `pending_review_notify` 1h; migración 017) | `test_reminders` 64/64 |
| CP-B4 | ⬜ | Herramientas reales del asistente (agenda, acciones) | — |
| CP-C3 | ✅ | Cierre del circuito GEPA: las propuestas de mejora apuntan al playbook que participó en las trazas rechazadas/editadas (no a uno arbitrario), se redactan sobre el contenido real, aplicar es reversible (previous_content) y el abogado ve QUÉ procedimiento se modifica. Vuelta EN VIVO pendiente de playbooks de Pipe (Riesgo #20) | `test_feedback_processor` 26/26 · `test_gepa` 18/18 · `test_trace_capture` 23/23 |
| CP-C4 | ⬜ | Asistente de configuración guiado (onboarding técnico sin jerga) | — |
| CP8 | ⬜ | Endurecimiento pre-cliente — EN PAUSA por decisión de prioridad (uso diario Lexia primero) | — |
