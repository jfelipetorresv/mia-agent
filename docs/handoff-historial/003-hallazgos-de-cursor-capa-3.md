## Hallazgos de Cursor (capa 3)

### 2026-07-02 — CP9 + CP-C4b: UI pendiente construida + revisión visual

**Qué se construyó (las 3 piezas pendientes):**

1. **Pantalla de revisión de borrador** (`frontend/app/asuntos/[id]/revisar/page.tsx`):
   - Botón "Descargar en Word" en la cabecera → `GET /api/matters/{id}/draft.docx`.
     Nota técnica: la descarga NO puede ser un enlace directo porque el endpoint
     exige el header Authorization — se añadió `apiDownload()` en `lib/api.ts`
     (fetch → Blob → descarga). El error se muestra inline en ámbar, sin jerga.
   - Informe de verificación de citas bajo el borrador: línea sobria ("Mia revisó
     N citas; M quedaron marcadas para tu verificación") con detalle expandible
     cita por cita (`aria-expanded` en el botón). Cada estado se comunica con
     texto + color (no solo color): "Verifícala tú" / "Con respaldo" / "Anotada".
     Si `verification` es null (borradores previos a CP9) no se muestra nada.

2. **Panel de control · sección "Carpetas de trabajo"** (`frontend/app/dashboard/page.tsx`):
   - Lista las nubes detectadas (OneDrive/Google Drive) con botón "Registrar"
     (o sello "Registrada"), las carpetas registradas con "Quitar", y un
     formulario para registrar por ruta (con nombre opcional).
   - "Quitar" pide confirmación explícita porque borra el conocimiento indexado
     de esa carpeta ("Mia… olvidará lo que leyó de ella") — acción destructiva.
   - Botón "Revisar carpetas ahora" → `POST /api/folders/sync`; el mensaje del
     servidor (en lenguaje llano) se muestra tal cual.
   - Texto de privacidad visible: "Mia solo lee las carpetas que tú registres
     aquí. Nunca revisa nada fuera de ellas."

3. **Panel de control · tarjeta Obsidian** (`frontend/app/dashboard/page.tsx`):
   - Botón "Instalar Obsidian" (solo aparece si `GET /api/obsidian/status`
     reporta que NO está instalado) con confirmación explícita en un panel
     ámbar (`role="alertdialog"`) antes de llamar `POST /api/obsidian/install`
     con `{"confirmar": true}`. Cancelar no instala nada.
   - Se muestra el `message` del status en lenguaje llano bajo el título.
   - Jerga corregida (§G): "Ruta del vault" → label "Ubicación de tu espacio de
     notas"; el error de sync "No se pudo sincronizar el vault." → "…tu espacio
     de notas."

**Hallazgo transversal corregido:** `lib/api.ts` descartaba el `detail` que el
backend redacta en lenguaje llano — todo error llegaba al abogado como
"Error 400". Ahora `checkResponse` lee el `detail` del cuerpo JSON y lo usa
como mensaje, así los textos cuidados del backend (p. ej. por qué una carpeta
no es segura, o la confirmación que exige instalar) por fin se ven en pantalla.

**Deuda §G que sigue abierta (ya anotada en CP7, no se tocó aquí):** la tarjeta
"Pinecone" (con "vectores", "Index") y la sección "Salud del second brain"
("Skills activos/archivados") del panel de control siguen con jerga técnica.

**Consistencia pendiente (menor):** la pantalla de revisión usa `alert()` del
navegador para errores de Aprobar/Rechazar (patrón pre-existente); el resto de
la app usa mensajes inline en ámbar. Unificar cuando se retoque esa pantalla.

**Verificación:** `npm run build` verde (11/11 páginas, sin errores de tipos).

### 2026-07-04 — CP-E1 + CP-E3 + CP-V2: UI pendiente construida (capa 3)

**Qué se construyó (3 commits separados, ya en `origin/main`):**

1. **CP-E1 · Tope de gasto de IA** (`frontend/app/dashboard/page.tsx`):
   - Tarjeta "Tope de gasto de IA este mes" junto a "Valor entregado este mes" (grid de 2 columnas en pantallas grandes).
   - `GET/PUT /api/policy/budget`: input USD + checkbox "Sin límite"; muestra gasto del mes y restante cuando hay tope.
   - Aviso ámbar con `role="alert"` cuando `over_budget`: "Se alcanzó el tope; los turnos están en pausa."
   - Errores del backend (`detail` vía `ApiError`) se muestran tal cual en ámbar.
   - Verificado en vivo: registro de usuario de prueba → PUT tope 100 USD → respuesta coherente (`unlimited=false`, `monthly_budget_usd=100`).

2. **CP-E3 · Personas jurídicas** (`frontend/app/personas/page.tsx`, enlace en `Sidebar.tsx`):
   - Pantalla CRUD completa: lista las 3 personas de fábrica en la primera carga (`GET /api/personas` siembra).
   - Crear, editar (formulario inline), eliminar (con confirmación).
   - §G: `model_tier` como selector "El motor del despacho" / "Siempre el motor local — más privado" — sin nombres de modelo.
   - Etiquetas en llano: `role_prompt` → "Cómo debe razonar y hablar esta persona"; `summon_phrases` → "Frases con las que la llamas en el chat".
   - Errores 422 del backend se propagan tal cual (`ApiError.detail`).
   - Verificado en vivo: API devuelve Litigante, Tributarista, Revisor de citas tras registro.

3. **CP-V2 · Recomendaciones de Mia** (`frontend/app/dashboard/page.tsx`):
   - Sección "Recomendaciones de Mia" en el Panel (encima de valor/tope).
   - `GET /api/dreams/prescriptions` + `POST .../{id}/decision` con botones "Lo haré" / "Descartar".
   - Evidencia expandible (`aria-expanded`); matiz ámbar para `recurring` con `age_days`.
   - Estado vacío en llano: "Mia aún no tiene recomendaciones — necesita más actividad para hablar con evidencia."
   - Verificado en vivo: tenant nuevo → lista vacía (0 recomendaciones); rutas `/dashboard` y `/personas` responden 200.

**Build:** `npm run build` verde tras cada frente (12/12 páginas al final, sin errores de tipos).

**Deuda §G sin tocar (pre-existente):** tarjeta "Pinecone" (vectores, Index) y sección "Salud del second brain" (Skills) siguen con jerga técnica — anotado en CP7.

**Pendiente de Pipe (capa 3 en vivo, no automatizable aquí):** probar aceptar/descartar una recomendación real cuando el cron semanal haya generado tarjetas; invocar una persona editada en el chat de un asunto.

### 2026-07-04 — CP-E5: tablero de misión por expediente (capa 3)

**Qué se construyó** (commit `f47f143`, ya en `origin/main`):

- **`frontend/app/_components/MissionBoard.tsx`** + pestaña **Plan** en `frontend/app/asuntos/[id]/page.tsx` (junto a Consulta).
- CRUD completo vía `/api/missions/*`: crear misión con propuesta automática de hitos, editar título/objetivo, archivar/eliminar, re-proponer hitos (añadir o reemplazar).
- Hitos: editar título, actor, estado, reordenar (↑↓), añadir manual, quitar. Barra de progreso "X de Y hitos" con `role="progressbar"`.
- §G: `mia` → "Mia lo prepara"; `abogado` → "Lo haces tú"; estados → Pendiente / En curso / Hecho; `is_procedural` → aviso "Toca un plazo — confírmalo tú [VERIFICAR]". Sin campos de fecha.
- Errores 422/502 del backend mostrados tal cual (`ApiError.detail`).
- **`npm run build` verde** (12/12 páginas).

**Pendiente de Pipe (capa 3 en vivo):** crear una misión real ("Preparar la contestación"), editar hitos propuestos y marcar avance en un asunto con documentos.

### 2026-07-04 — CP-P2: automatizaciones consent-first (capa 3)

**Qué se construyó** (commit `5642a73`, ya en `origin/main`):

- Sección **Automatizaciones** en el Panel (`AutomationsSection.tsx` + `dashboard/page.tsx`).
- **Sugerencias de Mia:** `GET /api/automations/suggestions` con botones Activar / Descartar; aviso ámbar en plantillas que tocan plazos procesales.
- **Automatizaciones activas:** lista con resumen en llano (p. ej. "3 días de anticipación") y Quitar (`DELETE`).
- **Crear automatización:** catálogo de plantillas (`GET /api/automations/blueprints`) con formularios expandibles por campo (`entero`/`texto`/`opcion`); `POST` con `plantilla` + `valores`. Errores 422 mostrados tal cual.
- §G: sin "blueprint", "cron" ni "job" en pantalla.
- **`npm run build` verde** (12/12 páginas).

**Pendiente de Pipe (capa 3 en vivo):** tener un recordatorio procesal pendiente para que Mia proponga el aviso anticipado; aceptar/descartar en pantalla y verificar que queda activa.

### 2026-07-04 — CP-P3: calendario y correo (Microsoft 365 / Google) (capa 3)

**Qué se construyó** (commit `70ac8e7`, ya en `origin/main`):

- **`MailboxSection.tsx`** + **`MailboxSectionLoader.tsx`** (Suspense para query OAuth).
- **Panel de control · Conectores** y **Configura a Mia**: tarjeta "Calendario y correo".
- `GET /api/mailbox/status` — muestra conectado / proveedor o botones Conectar Microsoft 365 / Google Workspace.
- `POST /api/mailbox/connect/{provider}` → redirige a la URL de consentimiento; opción «Incluir contenido de correos» (`?content=1`).
- `DELETE /api/mailbox/disconnect`; `PUT /api/mailbox/content-analysis` — opt-in de resumen con IA (checkbox).
- Tras OAuth, el backend redirige a `/configurar?mailbox=conectado|error` — la UI muestra el mensaje.
- §G: sin "OAuth", "token" ni "Graph"; errores 503/422 del backend tal cual.
- **`npm run build` verde** (12/12 páginas).

**Pendiente de Pipe:** registrar la app en Azure/Google, pegar llaves en `.env`, y probar el flujo completo de conexión en vivo.

### 2026-07-06 — Rediseño del onboarding + de-jerga de Conocimiento (capa 3)

**Qué se construyó:**

1. **Pantalla final del onboarding** (`frontend/app/onboarding/page.tsx`):
   - Consume `summary` de `POST /api/onboarding/complete` y lo muestra en tarjeta con Markdown legible (viñetas y negritas).
   - El `soul_content` técnico quedó en `<details>` plegable "Ver detalle técnico".
   - Eliminada lógica de preguntas `p15`/`p16` (objetivo del año y pilares) que el backend ya no envía.

2. **Días de la semana (p17):** checkboxes ahora incluyen los 7 días (añadidos Sábado y Domingo).

3. **Herramientas (p18):** reemplazados chips libres por checklist curada con descripción por opción (Correo, Calendario, Gestor documental, Mensajería, Carpetas en la nube, Notas/Obsidian marcada "Próximamente") + campo "Otra herramienta" para texto libre. Los valores se envían como lista de textos en `memory.tools_that_survived`.

4. **Conocimiento** (`frontend/app/memoria/page.tsx`): pestañas renombradas — "Temas que Mia va aprendiendo", "Documentos y fuentes", "Lo que Mia sabe hacer", "Mejoras que Mia propone" (Mi despacho sin cambio).

**Build:** `npm run build` verde (12/12 páginas).

**Pendiente de Pipe (capa 3 en vivo):** completar el onboarding de punta a punta y verificar que el resumen final refleja las respuestas; probar selección de herramientas y días de fin de semana.

### 2026-07-12 — CP-E6: Sistemas conectados (capa 3)

**Qué se construyó:**

- **`frontend/app/_components/ConnectedSystemsSection.tsx`** — UI consent-first sobre `/api/mcp/*`.
- Integrado en **Configuración → Conexiones** (`ConexionesSection.tsx`), alineado al design system actual (`ConnectorCard`, `Button`, `Input`, `Label`).

**Comportamiento:**

- `GET /api/mcp/status` → una tarjeta por sistema (`display_name`, descripción, nota de permisos).
- Formulario con campos `fields` (secretos como password); **Conectar** → `POST .../enable` con `{ env, secrets }`.
- Si habilitado: **Desconectar** (`disable`) y **Borrar credenciales** (`forget`, con confirmación).
- Secretos nunca se precargan; errores del backend en llano (`ApiError.detail`).
- §G: sin "MCP" / "servidor" / "tenant" en pantalla.

**Build:** `npm run build` verde (warnings preexistentes de `useReducedMotion` en `_welcome/`, no bloquean).

**Pendiente de Pipe:** conectar un sistema real cuando el cliente MCP esté activo; OAuth/correo siguen con activación diferida.

### Corrección post-Cursor (Claude Code · verificación de la entrega integrada)

- **Exactitud del resumen del verificador (corregido):** la línea sobria contaba
  solo `marcadas` para decir cuántas citas verificar, pero el abogado debe
  verificar TODA cita con la marca [VERIFICAR] en el texto final = `marcadas`
  (las que ya venían marcadas del redactor) **+ `anotadas`** (las que el
  verificador añadió por no tener respaldo). Con el conteo anterior, un caso real
  (5 citas: 3 marcadas + 2 anotadas + 0 respaldadas) mostraba "3 quedaron
  marcadas" cuando en el borrador hay 5 con marca; y peor, un caso de 0 marcadas
  + 2 anotadas decía "todas quedaron con respaldo" (falso — 2 sin respaldo). Eso
  subrepresentaba justo el riesgo que CP9 existe para evitar. Corregido en
  `revisar/page.tsx` (`porVerificar = marcadas + anotadas`). Build verde,
  regresión 43/43 tras el cambio.

---

