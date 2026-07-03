# Mia — CLAUDE.md
# Constitución del proyecto · agente legal cognitivo autónomo
# Última actualización: 2026-07-01 · Propietario: Juan Felipe Torres Varela
# LEER ANTES DE TOCAR CUALQUIER ARCHIVO DEL PROYECTO

---

## A · Qué es esta carpeta
Mia es un agente legal cognitivo autónomo desarrollado por Lexia
Intelligence (Juan Felipe Torres Varela, Lexia Abogados, Bogotá,
Colombia). Stack: Python 3.11 + FastAPI + LangGraph +
PostgreSQL/pgvector + Next.js 14.
Plataforma: Windows 11 — instalación nativa (Modo B).
Estado: construcción activa — Fase 0 en progreso.

El proyecto vive en: "D:\Codex\Mia-Super Agent\mia"
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
  recibir un diagnóstico jurídico verificado + borrador para aprobar
  — en 10 minutos. Comercializable a otros despachos del Civil Law.
- Fuera de alcance (v1): módulo de billing SaaS, segundo paquete de
  jurisdicción, voz nativa, app móvil, integración con sistemas de
  gestión de expedientes externos.

---

## C · Stack
- Backend: Python 3.11 · FastAPI · LangGraph · AsyncPostgresSaver
- Base de datos: PostgreSQL 16 + pgvector (extensión de embeddings)
- LLM Gateway: LiteLLM (proxy unificado — Claude, GPT, Gemini,
  MiniMax, Ollama)
- Agent CLIs: Hermes Agent (MIT) · Claude Code · Codex · Antigravity
  · OpenClaw
- Frontend: Next.js 14 App Router · TypeScript · SSE streaming
- Knowledge Stores: pgvector (siempre) · Obsidian vault (opcional)
  · Pinecone (opcional)
- Despliegue: procesos nativos Windows (Modo B). Docker Compose
  disponible para producción/clientes (Modo A).
- Arranque Modo B: 3 terminales PowerShell (litellm / uvicorn /
  npm run dev)
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
  Prefix caching TTL 1h ahorra ~75% en matters largos.
- 2026-06-01 — SAT-Graph en Postgres puro (no Neo4j) porque el
  proyecto es SQL-first y Neo4j añadiría una dependencia de infra
  sin justificación para la escala actual.
- 2026-06-01 — Windows como plataforma de desarrollo principal.
  Modo B (nativo) para laptop del fundador con acceso libre a
  Obsidian y documentos. Modo A (Docker + WSL2) para producción.
- 2026-06-01 — Core propio (no fork de Hermes) adoptando patrones
  MIT. Hermes es referencia de código, no dependencia.
- 2026-06-01 — call_llm(task="compression") = claude-haiku siempre.
  No sonnet. No cambiar sin documentar en memory/decisions.md.

---

## E · Mapa de memoria (/memory/)
- task_plan.md       → fases del proyecto, objetivos por módulo,
  checklists
- findings.md        → patrones de Hermes/OpenJarvis, restricciones
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
- Repos de referencia (en "D:\Codex\Mia-Super Agent\"):
  hermes-ref/ (MIT) · jarvis-ref/ (Apache 2.0) · agent-os-ref/
  · claudeos-ref/
- Hermes docs (leer antes de implementar):
  github.com/mudrii/hermes-agent-docs
  (architecture.md · memory.md · skills.md · plugins.md · cron.md)
- OpenJarvis: scalingintelligence.stanford.edu/blogs/openjarvis/
- Corpus jurídico Colombia: SUIN-Juriscol · Función Pública · SAMAI

---

## G · Overrides específicos del proyecto
- Este proyecto es Windows-first, Modo B (nativo). Siempre usar
  rutas y comandos de PowerShell — NO bash de macOS/Linux.
  Proyecto en "D:\Codex\Mia-Super Agent\mia"
  (comillas obligatorias por los espacios en la ruta).
- Obsidian vault en Windows (Modo B nativo):
  OBSIDIAN_VAULT_PATH=D:\Codex\Lexia-Vault-Test
- El .env NUNCA se commitea. Está en .gitignore.
- El frontend NUNCA muestra terminología técnica al usuario:
  no "HITL", no "LangGraph", no "pgvector", no "tenant_id".
  El abogado ve "asunto", "revisar borrador", "Mia está investigando".
- HALT si el test execution/test_rls.py falla. No avanzar hasta
  que pase.

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

---

# Mia CLAUDE.md · Lexia Intelligence · v1 · 2026-06-11
