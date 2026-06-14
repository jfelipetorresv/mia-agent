# Mia · Runbook — Smoke test E2E en vivo (navegador, Modo B)
# Última actualización: 2026-06-14 (Módulo 5 · cierre)

Este runbook es el recorrido MANUAL que ejecuta el fundador para confirmar que Mia
funciona de verdad en un navegador (no solo en TestClient). El gate automatizado
`execution/test_e2e.py` cubre el mismo flujo sin navegador; este runbook lo
complementa con el LLM real y la UI real.

## 0 · Prerrequisitos
- PostgreSQL 16 + pgvector corriendo (Módulo 0).
- `.env` con `VOYAGE_API_KEY`, `JWT_SECRET`, `PG_PASSWORD`, claves del proxy.
- `.venv` con todas las deps; `frontend/` con `node_modules` instalados.
- `frontend/.env.local` con `NEXT_PUBLIC_API_URL=http://localhost:8000` y
  `NEXT_PUBLIC_DEV_TOKEN` (JWT del tenant `DEV_FRONTEND`; ver `api_surface.md` §auth).
- El tenant `DEV_FRONTEND` debe existir en la tabla `tenants` (para que matters,
  documentos, etc. tengan a quién pertenecer). El SOUL.md NO necesita fila en DB
  (vive como archivo en `$MIA_HOME/soul_{tenant_id}.md`).

## 1 · Arrancar los 3 procesos de Modo B (3 terminales PowerShell)
La ruta tiene un espacio → SIEMPRE entre comillas.

    # Terminal 1 — gateway LLM (LiteLLM proxy, localhost:4000)
    cd "D:\Codex\Mia-Super Agent\mia"; .\scripts\start_litellm.ps1

    # Terminal 2 — API (FastAPI/uvicorn, localhost:8000)
    cd "D:\Codex\Mia-Super Agent\mia"; .\scripts\start_api.ps1

    # Terminal 3 — frontend (Next.js, localhost:3000)
    cd "D:\Codex\Mia-Super Agent\mia\frontend"; npm run dev

Verifica salud: `http://localhost:8000/health` debe responder `status: ok` con la
versión de pgvector.

## 2 · Abrir la app
Abre `http://localhost:3000`. La primera vez (sin SOUL.md para el tenant de dev) el
`OnboardingGate` del layout redirige a `/onboarding`.

## 3 · Completar la entrevista de onboarding (SOUL.md)
- Responde las 19 preguntas (5 bloques: Identidad · Jurisdicción · Voz jurídica ·
  Misión y ritmo · Modo profundo). Puedes usar los datos de Lexia del Doc 4.
- Barra de progreso "Pregunta X de 19". Cada pregunta muestra su ejemplo.
- Al finalizar, Mia genera tu SOUL.md (call_llm task="soul", claude-sonnet) y lo
  muestra. Revisa que tenga las 9 secciones (`## identity` … `## triad_mode`).
- "Editar" vuelve al flujo; "Continuar a mis asuntos" va a la pantalla 1.
- El archivo queda en `$MIA_HOME/soul_{tenant}.md` (+ `…responses.json`).

## 4 · Crear un asunto y subir un documento
- Pantalla 1 → "Nuevo asunto" (nombre + descripción) → entra al workspace.
- Pantalla 2 → sube un PDF o Word (p. ej. una demanda o un contrato). Mia lo ingiere
  (extracción → chunks → embeddings voyage-law-2). Aparece en la lista de documentos.

## 5 · Hacer una pregunta y ver el streaming
- En el chat del workspace, pregunta algo del expediente
  (p. ej. "¿Cuál es el problema jurídico central?").
- Observa el avance en vivo (SSE): "Mia está analizando…" → "Borrador listo".
- Verifica que el lenguaje sea del oficio (sin jerga técnica, §G).

## 6 · Revisar y aprobar un borrador
- Cuando el borrador esté listo, abre la pantalla 3 (Revisión).
- Revisa el texto; los `[VERIFICAR]` van resaltados (citas sin confirmar).
- Aprobar / Editar (corrección inline) / Rechazar. Al aprobar, el turno se cierra y
  queda la traza JSONL (alimenta el Dashboard y el aprendizaje de Mia).

## 7 · Comprobaciones finales
- Pantalla 5 (Panel): actividad, documentos indexados ≥ 1, costo del mes, conectores.
- Pantalla 4 (Conocimiento): perfil del despacho, playbooks, sugerencias de Mia.
- `/onboarding` ahora muestra "Tu despacho ya está configurado" con "Revisar mi
  perfil" (precarga tus respuestas).

## Qué confirma este runbook
El bucle central del producto end-to-end: **identidad (SOUL.md) → asunto → documento
→ pregunta → diagnóstico → borrador → aprobación**, con la identidad del despacho
realmente influyendo en el turno (el grafo carga `soul_snapshot` al iniciar cada
turno, Módulo 5). Si los 7 pasos funcionan en el navegador con el LLM real, Mia v0
está operativa para una demo.

## Self-Annealing
1. **Redirige en bucle a /onboarding** → el backend no responde o el JWT de dev es
   inválido; revisa `NEXT_PUBLIC_DEV_TOKEN` y `/api/onboarding/status`.
2. **El SOUL.md no tiene las 9 secciones** → el LLM no respetó el template; revisa el
   prompt de `soul_interview._GEN_SYSTEM` o reintenta (la identidad usa sonnet).
3. **El borrador no refleja la voz del despacho** → confirma que existe
   `$MIA_HOME/soul_{tenant}.md` (sin él, `soul_snapshot=None` y el grafo usa el
   system base). `$MIA_HOME` se ancla a `mia-data/` si la ruta del `.env` es relativa.
4. **El streaming no avanza** → revisa el checkpointer Postgres (1d) y el proxy LLM.
