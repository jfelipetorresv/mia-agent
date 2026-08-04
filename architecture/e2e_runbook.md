# Mia · Runbook — Smoke test E2E en vivo (navegador, Modo B)
# Última actualización: 2026-08-04 (recorrido AUTOMATIZADO de primera vez incorporado)

## 0-bis · El recorrido automatizado (F3) — correr esto antes que el manual

El recorrido completo de primera vez está AUTOMATIZADO con Playwright:

    # con DB (55432) + LiteLLM (4000) + backend (8000) + frontend (3100) arriba:
    .venv\Scripts\python.exe e2e\generar_expediente.py        # una vez: expediente fijo
    node e2e\recorrido_primera_vez.mjs --corrida N

Cubre `/register` → `/activar` (auto-salto en dev) → `/onboarding` (7 pasos) →
crear asunto → subir expediente fijo (caso de oro voluminoso, 3 .txt, 252
fragmentos derivados de `backend/mia/eval/cases.py`) → pregunta → borrador →
gate de citas → aprobar → sonda del `## aprendido`. Cronometrado wall-clock por
paso (el reloj arranca al abrir la app con los servicios ya arriba); screenshot
por paso y `tiempos.json` en `validation/screenshots/corrida-N/`. El tiempo se
reporta, no es umbral (decisión de Pipe 2026-07-21). Cada corrida registra un
despacho nuevo (`e2e-<ts>@mia.test`); el freno de registro es 10/hora/IP — si el
429 aparece iterando, reiniciar el backend resetea el contador (vive en memoria).
Resultados y defectos de cada tanda: `validation/validation-log.md`.

El recorrido manual de abajo sigue valiendo como verificación visual humana.

Este runbook es el recorrido MANUAL que ejecuta el fundador para confirmar que Mia
funciona de verdad en un navegador (no solo en TestClient). El gate automatizado
`execution/test_e2e.py` cubre el mismo flujo sin navegador; este runbook lo
complementa con el LLM real y la UI real.

## 0 · Prerrequisitos
- PostgreSQL (clúster portable, puerto **55432** — ver `.env:PG_PORT`) + pgvector corriendo.
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
    cd "D:\Inteligencia Artificial\Mia-Super Agent\mia"; .\scripts\start_litellm.ps1

    # Terminal 2 — API (FastAPI/uvicorn, localhost:8000)
    cd "D:\Inteligencia Artificial\Mia-Super Agent\mia"; .\scripts\start_api.ps1

    # Terminal 3 — frontend (Next.js, localhost:3100 — NO 3000, que lo usa otro
    # proyecto del equipo; puerto fijado en frontend/package.json "dev": "next dev -p 3100")
    cd "D:\Inteligencia Artificial\Mia-Super Agent\mia\frontend"; npm run dev

(También existe `scripts\start_all.ps1`, que levanta los tres en una sola terminal
y espera a que el 3100 responda.)

Verifica salud: `http://localhost:8000/health` debe responder `status: ok` con la
versión de pgvector.

## 2 · Abrir la app
Abre `http://localhost:3100`. La primera vez (sin SOUL.md para el tenant de dev) el
`OnboardingGate` del layout redirige a `/onboarding`.

## 3 · Completar la entrevista de onboarding (SOUL.md)
**Verificado contra el código 2026-07-21**: `backend/mia/onboarding/soul_interview.py:71-104`
define **6 preguntas** (`p1`, `p2`, `p6`, `p20`, `p21`, `p22`); el frontend
(`frontend/app/onboarding/page.tsx:224-238`) inserta una **7ª pantalla local** de
jurisdicción (selector de país, sin id de backend) justo después de `p2`. Total:
**7 pasos**, en 3 bloques (`identity` · `jurisdiction` · `criterio` —
`BLOCK_LABEL` en `page.tsx:72-76`):

1. `p1` — nombre del despacho y firma (`identity.name`).
2. `p2` — ciudad y país (`identity.location`).
3. Jurisdicción — selector de país(es) cuyas reglas aplica el despacho
   (auto-llena `jurisdiction.base`; NO es una pregunta de `soul_interview.py`).
4. `p6` — "¿A quién defiendes y en qué asuntos?"; la misma pantalla recoge también
   `jurisdiction.client_type` (paso fusionado, `page.tsx:278`).
5. `p20` — qué revisa siempre el abogado y qué puede resolver Mia sola
   (`autonomia.reviso_siempre` + `autonomia.decide_solo` en la misma pantalla).
6. `p21` — "¿Qué no debo hacer nunca?" (`nunca`).
7. `p22` — "¿Cuándo das un escrito por terminado?" (`terminado`).

- Barra de progreso "Pregunta X de 7". Cada pregunta muestra su ejemplo.
- Al finalizar, `build_soul()` (`soul_interview.py:325`) **ensambla el SOUL.md
  determinísticamente a partir de las respuestas — NO hay llamada a un LLM**. Las
  secciones que puede contener son `## identity`, `## jurisdiction`, `## autonomia`,
  `## nunca`, `## terminado`, `## aprendido` (`SOUL_SECTIONS`, `soul_interview.py:153-158`);
  cada una solo aparece si hay respuesta — no es un template fijo de 9 secciones.
  `## aprendido` no la llena ninguna pregunta: la escribe `update_soul` desde el
  trabajo real aprobado, después del onboarding.
- El endpoint `POST /api/onboarding/complete` valida las llaves contra los campos
  conocidos y corre `validate_soul` antes de aceptar (`backend/mia/api/routes/ux.py:1627-1660`,
  `_known_fields_only` en la línea 610) — ya no acepta en silencio un perfil vacío.
- "Editar mis respuestas" vuelve al flujo; "Revisar mi perfil" (pantalla de
  "Mi despacho") permite editar los mismos campos después.
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
turno, Módulo 5). Si los 7 pasos del onboarding + los pasos 4-6 de abajo funcionan
en el navegador con el LLM real, Mia v0 está operativa para una demo.

## Self-Annealing
1. **Redirige en bucle a /onboarding** → el backend no responde o el JWT de dev es
   inválido; revisa `NEXT_PUBLIC_DEV_TOKEN` y `/api/onboarding/status`.
2. **El SOUL.md sale casi vacío o sin secciones** → alguna llave de `responses` no
   coincide con `CURRENT_FIELDS`/`LEGACY_*` (`soul_interview.py:117-149`); el endpoint
   ahora rechaza esto con 422 en vez de aceptarlo en silencio — revisa el detalle del
   error, no el LLM (no hay LLM en esta ruta).
3. **El borrador no refleja la voz del despacho** → confirma que existe
   `$MIA_HOME/soul_{tenant}.md` (sin él, `soul_snapshot=None` y el grafo usa el
   system base). `$MIA_HOME` se ancla a `mia-data/` si la ruta del `.env` es relativa.
4. **El streaming no avanza** → revisa el checkpointer Postgres (1d) y el proxy LLM.
