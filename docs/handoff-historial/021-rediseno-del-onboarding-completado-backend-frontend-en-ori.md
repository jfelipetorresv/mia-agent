## ✅ Rediseño del onboarding — COMPLETADO (backend + frontend en `origin/main`, 2026-07-06)

**Backend** (merge `de6c797`) y **frontend de Cursor** (commit `1487ba6`) ya están en
`origin/main` y verificados (tsc limpio; 3100 sirve 200 sin ChunkError; SummaryMarkdown
calza con `build_summary`). Cursor entregó: resumen llano + detalle técnico plegable,
7 días (con fin de semana), herramientas con descripción, y "Conocimiento" de-jergada.
**Único pendiente = capa 3 EN VIVO de Pipe:** hacer el recorrido de punta a punta en
`http://localhost:3100` y confirmar que el resumen refleja sus respuestas. La spec
original se conserva abajo por trazabilidad; NO rehacer.

<details><summary>Spec original (histórica — ya implementada)</summary>

Pipe probó el onboarding real y pidió arreglos. **El backend ya cambió** (rama
`feat/onboarding-soul-claro`); falta la parte visual. Contexto: el "Configura a Mia"
debe sentirse fácil para un abogado (cero jerga de agentes), estilo wizard de Hermes.

**COMPLETADO** (Cursor capa 3 · 2026-07-06). Detalle en "Hallazgos de Cursor (capa 3)" al final.

**Ya hecho en backend (no tocar, solo consumir):**
- La entrevista ahora trae **13 preguntas** (`GET /api/onboarding/questions`); se
  QUITARON las de "objetivo del año" y "los 3 pilares" (eran confusas). Los `id`
  `p15`/`p16` ya no llegan — si el frontend tiene lógica por-id para ellos, quítala.
- El SOUL.md se genera **determinista y sin placeholders** (nunca más `[CORCHETES]`).
- `POST /api/onboarding/complete` ahora devuelve, además de `soul_content`, un campo
  **`summary`**: un resumen en **lenguaje llano** en Markdown ("### Así entendí a tu
  despacho" + viñetas). ESO es lo que debe ver el abogado al terminar.
- El recorrido "Configura a Mia" ya **no incluye Obsidian** (`GET /api/setup/status`
  devuelve 6 pasos). No lo repongas.

**Frontend a construir (`frontend/app/onboarding/page.tsx` salvo que se indique):**

1. **Pantalla final = el resumen, no el .md crudo.** Hoy se muestra `soul_content` en
   un `<pre>`. Cámbialo por render del campo **`summary`** (Markdown → texto con
   viñetas y negritas, legible). El `soul_content` técnico puede quedar oculto o en un
   "Ver detalle técnico" plegable (opcional, para power users). Encabezado tipo tarjeta.

2. **Días de la semana — agregar SÁBADO y DOMINGO.** La pregunta de ritmo (`p17`) hoy
   muestra checkboxes Lunes–Viernes; hay abogados que trabajan fin de semana. Deja los
   **7 días** (Lunes, Martes, Miércoles, Jueves, Viernes, Sábado, Domingo).

3. **Herramientas (`p18`) — lista curada CON descripción, no texto libre.** Reemplaza
   los chips libres por una lista de opciones (checklist) donde cada una explique qué
   hace Mia con ella. Los valores seleccionados se envían igual (lista de textos) en la
   respuesta del field `memory.tools_that_survived`. Opciones sugeridas + descripción:
   - **Correo** — "Mia vigila tus correos urgentes y te avisa."
   - **Calendario** — "Mia te recuerda tus eventos y audiencias próximas."
   - **Gestor documental** — "Mia consulta los documentos del despacho para responder."
   - **Mensajería (Telegram)** — "Habla con Mia desde tu celular, por texto o por voz."
   - **Carpetas en la nube (OneDrive/Google Drive)** — "Mia conoce las carpetas donde
     guardas tu trabajo."
   - **Notas (Obsidian)** — "Mia guarda y consulta tus notas." *(marcar "próximamente"
     si se quiere, ya que Obsidian está pospuesto)*
   Deja además un campo "otra…" para añadir libremente si el abogado quiere.

4. **De-jergar la pantalla "Conocimiento"** (`frontend/app/memoria/page.tsx`, pestañas
   línea ~14-18). Nombres nuevos (confirmados con Pipe):
   - "Wiki del despacho" → **"Temas que Mia va aprendiendo"**
   - "Lo que Mia sabe" → **"Documentos y fuentes"**
   - "Habilidades" → **"Lo que Mia sabe hacer"**
   - "Sugerencias de Mia" → **"Mejoras que Mia propone"**
   - "Mi despacho" → se queda igual (ya es claro).

**Reglas:** §G sin jerga ("SOUL", "tenant", "playbook", "wiki" no van); textos cálidos
y explicativos (estilo Hermes: cada opción con su descripción, un default sensato); tras
`npm run build` reinicia el dev server. **OJO — puerto:** Mia ahora corre en **3100**
(no 3000; el 3000 es de otro proyecto del equipo). Escribe tus hallazgos abajo.

</details>

---

