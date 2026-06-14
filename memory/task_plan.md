# Mia — task_plan.md
# Fases del proyecto · objetivos por módulo · checklists
# Última actualización: 2026-06-14

Leyenda: [x] completado · [ ] pendiente · [~] en progreso

---

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

## Fase 3 — UX
- [ ] 4a — Pantalla 1 (de las 5)
- [ ] 4b — Pantalla 2
- [ ] 4c — Pantalla 3
- [ ] 4d — Pantalla 4
- [ ] 4e — Pantalla 5

## Fase 4 — Personalidad
- [ ] Módulo 5 — Entrevista SOUL.md + prueba E2E

---

**Estado actual:** **Fase 0 + Módulo 1 (1a-1e) + Fase 1 Memoria (2a-2d) + FASE 2 COMPLETA
(3a-3e) COMPLETOS.**
Regresión 15/15 suites verdes: 1a 15 · 1b 32 · 1c 16 · 2a 19 · 2b 14 · 2c 22 · 2d 20 ·
test_rls 12 · 1d 19 · 1e 38 · 3a 21 · 3c 22 · 3d 14 · 3b 23 · 3e 21. (308 checks.)
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
**Siguiente:** PAUSA — el usuario pidió NO arrancar otro módulo sin él presente.
**Fase 3 — UX (5 pantallas Next.js, 4a-4e).** También: Módulo 5 (SOUL.md).
PENDIENTE TÉCNICO antes/durante Fase 3: Riesgo #22 (arrancar el scheduler en el lifespan de la
app — hoy los jobs no se disparan) y #21 (revisar/aplicar feedback_proposals — Pantalla 4).
