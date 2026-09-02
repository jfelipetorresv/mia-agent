# Mia — CLAUDE.md
# Constitución del proyecto · agente legal cognitivo autónomo
# Última actualización: 2026-09-02 · Propietario: Juan Felipe Torres Varela
# LEER ANTES DE TOCAR CUALQUIER ARCHIVO DEL PROYECTO

---

## A · Qué es esta carpeta
Mia es un agente legal cognitivo autónomo desarrollado por Lexia
Intelligence (Juan Felipe Torres Varela, Lexia Abogados, Bogotá,
Colombia). Stack: Python 3.11 + FastAPI + LangGraph +
PostgreSQL/pgvector + Next.js 16.3.
Plataforma: Windows 11 — instalación nativa (Modo B).
Estado: producto con login JWT, ~14 routers `/api`, política de modelo
por defecto `quality_adaptive`, grafo jurídico con HITL por hash,
MCP/warroom/misiones, puente Telegram opt-in en el lifespan del API.
Ver TRASPASO-MODELO.md para el detalle.

El proyecto vive en: "D:\Inteligencia Artificial\Mia-Super Agent\mia"
(la ruta contiene espacios — siempre entre comillas en comandos).

Dos memorias separadas:
- Esta carpeta (/memory/) = memoria de construcción (para Claude Code)
- $MIA_HOME/SOUL.md = memoria del agente (para Mia cuando corra)

---

## B · El objetivo
- Por qué existe: los despachos de abogados del Civil Law
  hispanoamericano no tienen un agente cognitivo propio que aprenda
  su metodología. Mia lo resuelve.
- Terminado se ve como: un agente que un abogado sin background
  técnico puede abrir, subir un expediente, hacer una pregunta, y
  recibir un diagnóstico jurídico verificado (sin una sola afirmación
  sin respaldo) + un borrador de calidad para aprobar. El tiempo del
  recorrido se MIDE y se reporta (p50/p95); no es una promesa fija —
  decisión de Pipe 2026-07-21: "no tienen que ser 10 minutos. puede
  ser más si el resultado es brutal y de calidad". Lo que aprueba o
  reprueba es el respaldo de las afirmaciones, nunca el reloj.
  Comercializable a otros despachos del Civil Law.
- Fuera de alcance (v1): módulo de billing SaaS, segundo paquete de
  jurisdicción, voz nativa, app móvil, integración con sistemas de
  gestión de expedientes externos.

---

## C · Stack
- Backend: Python 3.11 · FastAPI · LangGraph · AsyncPostgresSaver
- Base de datos: PostgreSQL 16 + pgvector (extensión de embeddings)
- LLM Gateway: router propio (`agent/llm.py`) con política
  `quality_adaptive` (CLI de suscripción / Codex local / nube /
  soberano). LiteLLM es un proxy opcional de respaldo, no el camino
  primero del abogado.
- Agent Hub: cinco conectores (investigación, documentos,
  automatización, escritorio, navegación). Solo se habilitan si el
  binario está en PATH y `--help` confirma los flags. Sin confirmar,
  el catálogo los muestra con razón honesta — nunca `[VERIFICAR]`.
- Frontend: Next.js 16.3 App Router · TypeScript · SSE streaming ·
  login en `/login`. No son «5 pantallas»: hay asunto, revisión HITL,
  memoria, configuración (conexiones, ayudantes, protección),
  automatizaciones, misiones, sala de estrategia.
- Knowledge Stores: pgvector (siempre) · Obsidian vault (opcional)
  · Pinecone (opcional)
- Despliegue: procesos nativos Windows (Modo B). "Modo A" (Docker +
  WSL2, producción/clientes) es solo una posibilidad futura fuera
  de alcance de v1: no existe ni un Dockerfile ni un docker-compose
  en el repo (verificado). No vender ni documentar Modo A como
  capacidad disponible.
- Arranque Modo B: `python -m mia.api.run` (API + scheduler +
  puente Telegram si hay token) y `npm run dev` del frontend. El
  proxy LiteLLM es opcional según la política del despacho.
- Herramientas de operaciones (NO son pantallas del abogado):
  `python -m mia.connectors.vault_export`, `mia.rag.corpus_factory`,
  `mia.rag.ingest_corpus`. Viven como CLI de ops.
- `prompt_builder.build_layers` es herramienta de eval/tests, no
  una caja de producto.
- Las skills de Cursor/Codex en `.agents/council|lightrag|playwright`
  NO son boxes de Mia: no se venden en la UI ni en este mapa.
- Archivos clave:
  - backend/mia/agent/prompt_builder.py → 10 capas de prompt
  - backend/mia/agents/graph.py         → LangGraph StateGraph
  - backend/mia/gateway/agent_hub.py    → conectores externos
  - backend/mia/connectors/obsidian_sync.py → sync Obsidian
  - execution/test_rls.py               → test crítico de seguridad

---

## D · Decisiones ya tomadas (no re-discutir)
- 2026-06-01 — LangGraph sobre CrewAI/AutoGen porque ofrece
  StateGraph tipado, AsyncPostgresSaver para checkpointing
  multi-tenant, y interrupt() nativo para HITL.
- 2026-06-01 — PostgreSQL + pgvector sobre Pinecone como store
  primario porque RLS por tenant es nativo en Postgres y Pinecone
  no tiene RLS. Pinecone sigue soportado como store externo opcional.
- 2026-06-01 — LiteLLM como gateway LLM porque unifica Claude, GPT,
  Gemini, Ollama y MiniMax en un endpoint OpenAI-compatible.
  El prefijo estable del prompt (capas 1–6) se marca para el prefix
  caching de Anthropic; el ahorro REAL se MIDE en el panel (cache
  hit-rate), no se afirma un porcentaje fijo.
- 2026-06-01 — SAT-Graph en Postgres puro (no Neo4j) porque el
  proyecto es SQL-first y Neo4j añadiría una dependencia de infra
  sin justificación para la escala actual.
- 2026-06-01 — Windows como plataforma de desarrollo principal.
  Modo B (nativo) para laptop del fundador con acceso libre a
  Obsidian y documentos. Modo A (Docker + WSL2) para producción se
  decidió en su momento pero NUNCA se implementó (0 Dockerfile/
  docker-compose en el repo); queda fuera de alcance de v1.
- 2026-06-01 — Core propio (no fork de Hermes) adoptando patrones
  MIT. Hermes es referencia de código, no dependencia.
- 2026-06-01 — call_llm(task="compression") está BLOQUEADA a la
  cadena barata/local de la política activa del despacho (ningún
  call-site la puede cambiar; un `model=` explícito se ignora,
  `_LOCKED_TASKS`). El modelo concreto depende de la política:
  'suscripcion' = cli-claude-haiku, 'nube' = claude-haiku,
  'soberano' = mia-local (Ollama). No cambiar el bloqueo sin
  documentar en memory/decisions.md.

---

## E · Mapa de memoria (/memory/)
- task_plan.md       → fases del proyecto, objetivos por módulo,
  checklists
- findings.md        → patrones de Hermes, restricciones
  técnicas
- progress.md        → qué se construyó, errores, tests, resultados
  · DIARIO DE OBRA
- decisions.md       → decisiones arquitectónicas con razonamiento
  completo
- session-summaries.md → resúmenes de sesión (TL;DR · qué ·
  decidimos · sigue)
- bugs-and-risks.md  → riesgos abiertos y watch-outs no resueltos

## Continuidad entre sesiones y modelos (raíz del repo)
- HANDOFF.md          → traspaso a Cursor (frontend, capa 3)
- TRASPASO-MODELO.md  → traspaso a cualquier modelo de IA que
  continúe el proyecto — LEER al iniciar sesión en terminal nueva
  (visión, estándar de calidad, ruta y trampas del entorno)

## Mapa de arquitectura (/architecture/)
- rls_isolation.md       → cómo funciona el aislamiento entre tenants
- prompt_builder.md      → las 10 capas del sistema de prompts
- context_compressor.md  → algoritmo del compresor (protect_first=5,
  last=30)
- agent_hub.md           → cómo conectar cada agente externo
  (spawn patterns)
- hitl_flow.md           → el flujo completo de aprobación de
  borradores
- obsidian_sync.md       → rutinas de sync del vault de Obsidian

---

## F · Referencias
- Repos de referencia (en "D:\Inteligencia Artificial\Mia-Super Agent\"):
  hermes-ref/ (MIT) · agent-os-ref/
  · claudeos-ref/
- Hermes docs (leer antes de implementar):
  github.com/mudrii/hermes-agent-docs
  (architecture.md · memory.md · skills.md · plugins.md · cron.md)
- Corpus jurídico Colombia: SUIN-Juriscol · Función Pública · SAMAI

---

## G · Overrides específicos del proyecto
- Este proyecto es Windows-first, Modo B (nativo). Siempre usar
  rutas y comandos de PowerShell — NO bash de macOS/Linux.
  Proyecto en "D:\Inteligencia Artificial\Mia-Super Agent\mia"
  (comillas obligatorias por los espacios en la ruta).
- Obsidian vault en Windows (Modo B nativo):
  OBSIDIAN_VAULT_PATH=<ruta del vault de Obsidian del despacho>
  (configurable por instalación; no hay ruta fija cableada)
- El .env NUNCA se commitea. Está en .gitignore.
- El frontend NUNCA muestra terminología técnica al usuario:
  no "HITL", no "LangGraph", no "pgvector", no "tenant_id".
  El abogado ve "asunto", "revisar borrador", "Mia está investigando".
- HALT si el test execution/test_rls.py falla. No avanzar hasta
  que pase.
- HALT si execution/test_gates_no_ciegos.py falla. Es el meta-gate
  que impide que una puerta de calidad apruebe sin mirar: detecta
  aserciones que quedaron ciegas por el formato del mensaje de
  sistema. Las peligrosas son las negativas ("esta jerga NO debe
  aparecer", "este dato NO debe filtrarse"), porque al romperse se
  quedan VERDES para siempre. En julio de 2026 hubo tres puertas
  verdes que no probaban nada, una rota tres días sin constar.
  Cuesta 0,5 s: va en el tramo rápido junto a test_rls y
  check_env_pins, no en la regresión completa (que no cabe y se
  corre por tramos, así que en la práctica no se corre).

---

## Memory Save — protocolo de cierre de sesión
Cuando Pipe diga "wrap up", "guardar" o "cerrar sesión":
1. Actualizar memory/progress.md con qué se construyó
2. Actualizar memory/task_plan.md marcando módulos completados
3. Agregar entrada a memory/session-summaries.md:
   ## YYYY-MM-DD — Sesión N
   TL;DR: (1 línea)
   Qué construimos:
   Qué decidimos:
   Qué sigue:
4. Si se encontraron y resolvieron errores, escribir la lección
   en el SOP de /architecture/ correspondiente.
5. Revisar memory/bugs-and-risks.md: cerrar riesgos resueltos,
   agregar riesgos nuevos detectados en la sesión.
No escribir nada sin trigger explícito del usuario.
## H · Sistema de tres memorias (no mezclar)

El ecosistema Mia tiene exactamente tres tipos de memoria. Mezclarlas es la causa raíz de la mayoría de inconsistencias entre sesiones.

| Memoria | Dónde vive | Qué guarda |
|---|---|---|
| **Canónica del despacho** | `Lexia-Vault\` (Obsidian, indexado por Mia) | Jurisprudencia, normativa, plantillas, procedimientos, criterios, aprendizajes del despacho |
| **De construcción de Mia** | `/memory/` en este repo + `APRENDIZAJES.md` | Decisiones de arquitectura, errores resueltos, estado del proyecto — ESTE repo |
| **De herramienta/sesión** | Contexto interno del agente (Claude Code, Antigravity, Cursor) | Atajos locales, quirks del entorno — caché, no verdad |

**Criterio de frontera:**
- ¿Sirve a cualquier LLM en cualquier herramienta del despacho? → **Lexia-Vault**
- ¿Es sobre el código o la arquitectura de Mia? → **`/memory/` de este repo**
- ¿Solo sirve a esta sesión? → **memoria de herramienta** (no persistir)

**Vault governance:** Las reglas de juego del Lexia-Vault viven en `Lexia-Vault\AGENTS.md`.
Las plantillas para crear vaults de nuevos abogados/despachos viven en `mia/specs/vault-scaffold/`.
El script de creación automática es `mia/scripts/create_vault_scaffold.py`.
El hook de onboarding está en `execution/init_knowledge_stores.py` (lee `OBSIDIAN_VAULT_*` del `.env`).

---

## I · Estándar de Diseño Frontend Obligatorio
- **Referencia Canónica Estética:** "MIA Onboarding Unificado" (Neumorfismo Pro en Tema Claro/Oscuro con paleta Teal/Azul Oxígeno, elevación tridimensional suave `shadow-neu-raised`, inputs incrustados `shadow-neu-sunken`, fondo vivo `bg-mesh-living`, tipografía premium y elementos 3D cristalizados flotantes `animate-float`).
- Cualquier desarrollo o modificación en `frontend/` DEBE seguir la especificación técnica en [`frontend_design_spec.md`](file:///d:/Inteligencia%20Artificial/Mia-Super%20Agent/mia/frontend_design_spec.md).
- PROHIBIDO romper la armonía visual o revertir a tarjetas y botones planos sin elevación neumórfica.

---

# Mia CLAUDE.md · Lexia Intelligence · v1 · 2026-06-11
