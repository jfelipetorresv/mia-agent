## Checkpoint reciente: CP-E3 — Personas jurídicas especializadas y editables (2026-07-03)

### Qué cambió (lenguaje simple)

- Mia ahora tiene **personas jurídicas** que el despacho **edita a su gusto**: un
  **litigante** (estratega procesal), un **tributarista** y un **revisor de citas**
  vienen listos de fábrica, y el despacho puede cambiarlos, deshabilitarlos, borrarlos
  o crear los suyos. Cada persona tiene su **voz** (cómo razona y con qué tono), sus
  **áreas de énfasis**, un **nivel de motor** y sus **frases de invocación**.
- El abogado **invoca** una persona escribiéndola en su propio mensaje — "actúa **como
  litigante** y analiza este asunto", "dame la **perspectiva tributaria**", "**revisa las
  citas** de este borrador" — en el chat de un asunto o hablando con Mia (Telegram). Mia
  adopta esa voz solo para ese turno. **Nada se auto-activa**: sin invocación, Mia trabaja
  exactamente como hoy.
- **Privacidad blindada:** una persona NUNCA puede mandar el trabajo del despacho a un
  motor de nube que su política no permita. Solo puede elegir entre "el motor del despacho"
  (respeta la política) o "siempre el motor local" (más privado y económico) — jamás al
  revés. El revisor de citas usa el motor local de fábrica.
- **La voz no relaja las reglas:** una persona colorea el tono, pero **nunca** puede hacer
  que Mia invente una norma o una cita — la regla de marcar con [VERIFICAR] lo no
  verificable manda siempre, por encima de cualquier persona.

### Frontend a construir (Cursor — capa 3): pantalla de personas en el Panel

- CP-E3 es **backend**; el abogado hoy invoca personas por frase en el chat (que ya
  existe). Falta la pantalla para **gestionarlas**. Endpoints listos (todos bajo `/api`,
  auth como el resto):
  - **`GET /api/personas`** → `{personas: [...]}`. Cada persona: `{id, name, title,
    role_prompt, tone, focus_areas[], model_tier, summon_phrases[], description, enabled}`.
    La primera llamada **siembra** las 3 canónicas del despacho.
  - **`POST /api/personas`** body con los mismos campos (name y role_prompt obligatorios)
    → la persona creada. `model_tier` ∈ `"estandar"` | `"local"`.
  - **`PUT /api/personas/{id}`** → la persona actualizada.
  - **`DELETE /api/personas/{id}`** → `{ok: true}`.
  - Errores de validación llegan **422** con `detail` en llano (mostrarlo tal cual):
    nombre duplicado, nivel inválido, tope alcanzado, etc.
- **Sin jerga (§G):** para `model_tier`, mostrar al abogado dos opciones en llano —
  "El motor del despacho" (`estandar`) y "Siempre el motor local — más privado" (`local`).
  Nunca nombres de modelo. `role_prompt` es "cómo debe razonar y hablar esta persona";
  `summon_phrases` es "frases con las que la llamas en el chat".
- Trabajo FUTURO opcional (no de este checkpoint): autocompletar las frases de invocación
  al teclear en el chat; un selector de persona en el asunto (hoy la invocación es por frase).

### Comportamiento esperado

- En un asunto: "Analiza esto **como litigante**" → Mia razona con voz de litigante en los
  5 especialistas del turno (hechos→investigación→cruce→borrador→corrección), sin cambiar
  el método ni la verificación de citas. Sin frase de persona → turno idéntico a hoy.
- Con Mia libre (Telegram): "**revisa las citas** de este texto: …" → Mia adopta la voz del
  revisor (motor local de fábrica) y marca lo no respaldado con [VERIFICAR].
- Nombre/persona deshabilitada o inexistente → Mia trabaja sin persona (no falla el turno).

### Resultado de verificación (3 capas)

- Capa 1: gate nuevo `test_personas.py` **52/52** (candado de motor fail-closed en las 3
  políticas incl. soberano; voz con guardrail [VERIFICAR] y sin jerga; detección por frase;
  validación; CRUD bajo RLS; AISLAMIENTO entre despachos; siembra idempotente que respeta el
  borrado); regresión **ALL PASS (55 suites)** (test_rls 12/12 HALT). Sin frontend web → sin
  npm build.
- Capa 2 (revisor adversarial independiente): los 7 invariantes SE SOSTIENEN
  (confidencialidad del motor, RLS, la voz no anula la citación, fail-open, comportamiento
  sin cambios, recursos/concurrencia, logs). Sin bloqueantes ni mayores. 2 MENORES
  (fail-open del asistente simétrico a stream; L3 citación añadida al system del asistente
  para que la regla dura preceda a la voz) + 1 NOTA (el candado 'local' devuelve el motor
  local por CONSTRUCCIÓN, no por posición de la cadena) corregidos y re-verificados ANTES
  del commit. Ver memory/progress.md sesión 32.
- Capa 3: COMPLETADO — ver "Hallazgos de Cursor (capa 3)" · 2026-07-04 (CP-E3).

---

