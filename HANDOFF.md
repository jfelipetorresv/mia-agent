# HANDOFF — Mia (traspaso a Cursor)

## Cómo usar este archivo

Cursor lee este archivo al iniciar sesión en el repositorio. Aquí queda
registrado el checkpoint más reciente del trabajo hecho en Claude Code:
qué cambió, qué debe revisarse en el frontend y qué comportamiento se
espera. Al terminar su revisión visual (capa 3), Cursor escribe sus
hallazgos en la sección final "Hallazgos de Cursor (capa 3)" para que
quede trazabilidad de ambas revisiones.

---

## Checkpoint actual: CP-C4b — "Configura a Mia" como onboarding explicativo (2026-07-02)

### Qué cambió (lenguaje simple)

- El recorrido "Configura a Mia" ya no solo detecta qué falta: ahora EXPLICA cada
  paso como un onboarding. Cada tarjeta tiene un botón "¿Qué es esto?" que despliega
  qué es la herramienta, para qué le sirve al despacho y cómo se hace paso a paso.
- Se agregó al final el mapa "¿Qué hace cada sección de Mia?" (Asuntos, Revisión de
  borradores, Conocimiento, Panel de control, este recorrido y Telegram).
- Mia también explica el siguiente paso completo cuando se le pregunta por la
  configuración (por Telegram): antes solo enumeraba, ahora acompaña.

### Frontend a revisar (Cursor — capa 3) + UI PENDIENTE de construir

- `frontend/app/configurar/page.tsx` — guía expandible por paso (contenido del
  servidor, `GET /api/setup/status` → `pasos[].guia` y `secciones`), sección del
  mapa de secciones, accesibilidad de la barra de progreso (`role="progressbar"`
  + aria) y del botón (`aria-expanded`). Foco de capa 3: legibilidad del texto
  largo, jerarquía visual del acordeón, contraste.
- **UI que el backend ya soporta pero el frontend AÚN NO tiene** (hallazgos del
  revisor de capa 2 — las guías se redactaron para no mentir mientras tanto, pero
  la experiencia queda a medias hasta que existan):
  1. **Panel de control · sección "Carpetas de trabajo"** — no existe. Backend
     listo: `GET /api/folders/detected`, `POST /api/folders`, `DELETE
     /api/folders/{id}`, `POST /api/folders/sync`. Debe listar carpetas
     registradas + nubes detectadas, permitir registrar por ruta y quitar.
  2. **Panel de control · tarjeta Obsidian: botón "Instalar Obsidian"** — hoy solo
     hay "Sincronizar" + input "Ruta del vault" (con jerga "vault"). Backend listo:
     `GET /api/obsidian/status`, `POST /api/obsidian/install` (body
     `{"confirmar": true}`), `POST /api/obsidian/bootstrap`. Falta el botón de
     instalar (con confirmación) y suavizar el texto "Ruta del vault" → "espacio de
     notas".
  3. **Pantalla de revisión de borrador · botón "Descargar en Word" + informe de
     verificación de citas** (pendiente de CP9, ver ese checkpoint abajo). Las
     guías de CP-C4b se escribieron asumiendo que ESTO existirá pronto.

### Resultado de verificación (3 capas)

- Capa 1: `test_setup_wizard` extendido **30/30**; regresión completa **43 suites
  verdes** (test_rls 12/12 HALT); `npm run build` verde.
- Capa 2 (revisor independiente): APROBADO CON CORRECCIONES — CORREGIDAS antes del
  commit: (L1) la guía llegaba cortada a 150 caracteres en el chat → ahora completa
  (check a4); (U1/U2/U4/U5/U8) las guías describían pantallas o un chat web que no
  existen → reescritas para decir la verdad del producto HOY y sin referencias
  circulares; (U3) la promesa de Word/verificación se suavizó hasta que Cursor la
  entregue. La UI faltante (carpetas, instalar Obsidian) quedó documentada arriba
  como trabajo pendiente en vez de fingir que existe. Revisión por lectura de
  patrones, no auditoría con herramientas.
- Capa 3 (Cursor): PENDIENTE — revisar la página y, sobre todo, construir la UI
  pendiente de los 3 puntos de arriba.

---

## Checkpoint anterior: CP9 — Equipo de especialistas para producir documentos (2026-07-02)

> Estado: APROBADO por Pipe y mergeado a `main` (2026-07-02). Falta la UI del
> frontend (botón Word + informe de verificación) — ver abajo.

### Qué cambió (lenguaje simple)

- Al preguntar en un asunto, Mia ya no trabaja "de un solo envión": ahora un
  equipo de especialistas hace el trabajo por etapas, cada uno con el estilo
  del despacho — uno establece los HECHOS del expediente, otro INVESTIGA las
  normas y sentencias aplicables según el país del despacho (usando primero el
  corpus jurídico interno del sistema), otro CRUZA hechos con derecho y emite
  el diagnóstico, otro REDACTA el borrador, y un VERIFICADOR revisa cita por
  cita: toda cita sin respaldo queda marcada [VERIFICAR] automáticamente
  (antes se nos escapaban sentencias sin marca — el riesgo detectado en la
  comparación de CP6).
- El avance se ve en vivo en el chat: "estableciendo los hechos…",
  "investigando normas…", "cruzando los hechos con el derecho…",
  "verificando las citas…".
- Botón nuevo posible: **descargar el borrador como documento Word** con
  formato de escrito judicial (el backend ya lo sirve).

### Frontend a revisar (Cursor — capa 3)

- NO se tocó ningún archivo del frontend en este checkpoint: el backend emite
  datos nuevos que la UI puede aprovechar. Trabajo sugerido para la
  Pantalla 2/3 (`frontend/app/asuntos/[id]/page.tsx`):
  1. Botón "Descargar en Word" → `GET /api/matters/{id}/draft.docx`
     (descarga directa; 404 si no hay borrador).
  2. Mostrar el informe del verificador de citas: el SSE `awaiting_review` y
     `GET /api/matters/{id}/draft` ahora traen `verification`:
     `{citas, marcadas, respaldadas, anotadas, detalle:[{cita, estado}]}`.
     Sugerencia: una línea sobria bajo el borrador ("Mia revisó N citas; M
     quedaron marcadas para tu verificación") con detalle expandible.
  3. Los mensajes nuevos del avance ya llegan por el evento `thinking`
     existente — no requiere cambio, solo verificar que se vean bien.

### Comportamiento esperado

- Al preguntar en un asunto: los mensajes de avance cambian por etapa (5
  frases distintas antes de "Borrador listo"); el turno tarda MÁS que antes
  (son 4 pasos de razonamiento en vez de 2 — calidad sobre velocidad).
- El borrador llega con TODAS las citas específicas o marcadas [VERIFICAR] o
  respaldadas en el corpus del sistema; el diagnóstico conserva el resumen en
  3 líneas (problema/normas/riesgo) de CP6.
- El Word descarga con encabezados, viñetas y el pie "no radicar sin
  verificar las citas marcadas".

### Bugs conocidos / fuera de alcance

- El detector de citas es conservador: puede marcar de más (inofensivo — el
  abogado revisa algo que estaba bien), y no detecta una marca escrita ANTES
  de la cita. Artículos con numerales intercalados ("artículo 164, numeral 2,
  literal i del CPACA") pueden escapar al detector — deuda anotada.
- El costo por turno aproximadamente se duplica (4 llamadas de razonamiento
  en vez de 2). Decisión consciente: calidad del documento sobre costo.

### Resultado de verificación (3 capas)

- Capa 1: gate nuevo `test_document_pipeline` **41/41**; regresión completa
  del repo en verde (43 suites; test_rls 12/12 HALT); `test_hitl_flow`
  actualizado al orden nuevo del equipo (19/19).
- Capa 2 (revisor independiente): APROBADO CON CORRECCIONES — 2 mayores
  CORREGIDOS antes del commit: (M1) los expedientes grandes recuperaban su
  turno solo una vez por conversación y ahora cada etapa tiene su propio
  rescate; (M2) un patrón del verificador podía congelar el servidor con
  texto malicioso (confirmado con medición) — reescrito y movido fuera del
  hilo principal; ambos con checks de regresión (cp9-37..41). Menores
  corregidos: nombre de archivo Word con caracteres especiales, contexto
  impreciso al especialista de hechos, color/limpieza del Word. Revisión por
  lectura de patrones conocidos, no auditoría con herramientas de escaneo.
- Capa 3 (Cursor): NO APLICA aún (sin cambios de frontend en este
  checkpoint); queda el trabajo sugerido arriba para cuando se apruebe CP9.

---

## Checkpoint anterior: CP-C4 — "Configura a Mia": el recorrido guiado (2026-07-02)

### Qué cambió (lenguaje simple)

- Página nueva **"Configura a Mia"** (enlace en la barra lateral): un checklist
  de 6 pasos que detecta solo qué está listo y qué falta (perfil, motor de IA,
  Obsidian, carpetas de trabajo, guías, Telegram), con barra de progreso,
  "Ir al paso", guía de Telegram integrada, y "Dejar para después"/"Retomar"
  (el recorrido se recuerda entre sesiones).
- Mia también guía por chat: si le pides "ayúdame a conectar mi Google Drive",
  responde con el estado real de la configuración, no de memoria.
- Detectar NUNCA instala ni registra nada: las acciones viven en sus pantallas
  con sus propias confirmaciones.

### Frontend a revisar (Cursor — capa 3)

- `frontend/app/configurar/page.tsx` (NUEVA) — checklist, progreso, guía de
  Telegram inline, mensajes de error en ámbar. Hallazgo del revisor de capa 2
  DIFERIDO a esta capa: la barra de progreso necesita `role="progressbar"` +
  aria; los estados del paso se comunican en parte solo por color/símbolo
  (accesibilidad).
- `frontend/app/_components/Sidebar.tsx` — enlace nuevo "Configura a Mia".
- Siguen pendientes los 4 archivos de CP7 (sección siguiente) — puede
  revisarse todo junto.

### Resultado de verificación (3 capas)

- Capa 1: regresión **42/42 suites PASS** (test_rls 12/12 HALT); gate nuevo
  `test_setup_wizard` **21/21**; `npm run build` verde.
- Capa 2 (revisor independiente): APROBADO CON CORRECCIONES — 3 mayores
  (disparador del chat confundía verbos jurídicos "se configura la causal";
  detección con winget de hasta 60 s en el camino del request → caché 60 s;
  I/O de disco bloqueando el event loop → threads) y 3 menores: corregidos
  antes del commit. Residual aceptado: carrera menor en "dejar para después"
  con dos clics simultáneos (se autocorrige). Revisión por lectura de
  patrones, no auditoría con herramientas.
- Capa 3 (Cursor): PENDIENTE — archivos listados arriba.

---

## Checkpoint anterior: CP7 — El abogado gobierna todo desde la pantalla (2026-07-02)

### Qué cambió (lenguaje simple)

- Pantalla "Conocimiento": pestaña nueva **Habilidades** (qué tan bien le va a
  Mia con cada procedimiento, con % de aprobación); botón **Importar guías**
  (sube las guías de trabajo del despacho en .md/.txt/Word, con detalle en
  llano de lo que se importó/omitió); cada sugerencia ahora dice **qué
  procedimiento se modificaría**; sección nueva **"Orden del conocimiento"**
  (propuestas de Mia para unir guías repetidas o archivar las sin uso, con
  Aprobar/Rechazar).
- Panel de control: el selector de modelos técnicos se reemplazó por **"Motor
  de IA"** en español llano (Mi suscripción / Nube / Todo en mi equipo) y
  ahora SÍ guarda el cambio; sección nueva **Recordatorios** (ver y cancelar,
  con fecha Y HORA); la clave de Pinecone ya se escribe oculta (••••).
- Onboarding: se retiró la pregunta del "modo profundo" (era una función no
  implementada — no se ofrece lo que no existe).
- Pantalla del asunto: el panel Diagnóstico mostrará el resumen en 3 líneas
  (problema/normas/riesgo) cuando el backend lo emita (llega con CP6, hoy
  pendiente de aprobación de Pipe; sin él, todo se ve como antes).

### Frontend a revisar (Cursor — capa 3) — TODOS los archivos de este checkpoint

- `frontend/app/memoria/page.tsx` — pestaña Habilidades, Importar guías,
  target en sugerencias, sección Orden del conocimiento.
- `frontend/app/dashboard/page.tsx` — Motor de IA, Recordatorios, input de
  clave oculto.
- `frontend/app/onboarding/page.tsx` — pregunta p19 retirada (verificar que la
  navegación entre preguntas no se sienta rota).
- `frontend/app/asuntos/[id]/page.tsx` — resumen estructurado condicional en
  el panel Diagnóstico (los 2 pendientes de CP5 sobre este archivo y
  `frontend/app/page.tsx` siguen abiertos — puede cerrarse todo junto).
- Foco de la capa 3: diseño de interfaz, accesibilidad (labels, foco,
  contraste), consistencia de UX entre secciones nuevas y viejas, y
  superficies de seguridad visibles (ninguna clave/dato sensible en claro).

### Comportamiento esperado

- Con datos: Habilidades lista procedimientos con barra de % aprobado;
  Importar guías muestra "Se importaron N guías…" con detalle por archivo;
  el selector de Motor de IA persiste tras recargar; cancelar un recordatorio
  lo quita SOLO si el servidor confirmó (si falla, aviso en ámbar).
- Sin datos: cada sección nueva tiene su estado vacío en español llano.

### Resultado de verificación (3 capas)

- Capa 1: regresión **41/41 suites PASS** (test_rls 12/12 HALT);
  `test_second_brain_ui` extendido **26/26**; `npm run build` verde.
- Capa 2 (revisor independiente): APROBADO CON CORRECCIONES — 1 mayor
  (cancelar recordatorio mostraba éxito aunque fallara) + 1 mayor
  preexistente (clave de Pinecone visible) + 5 menores: TODOS corregidos
  antes del commit. Revisión por lectura de patrones, no auditoría con
  herramientas. Deuda §G anotada fuera de alcance: textos "second brain",
  "vault", "Pinecone" del dashboard viejo.
- Capa 3 (Cursor): PENDIENTE — revisar los 4 archivos listados arriba y
  devolver hallazgos en la sección final de este documento.

---

## Checkpoint anterior: CP-C3 — El circuito de aprendizaje quedó cerrado (2026-07-01)

### Qué cambió (lenguaje simple)

- Cuando el abogado rechaza o corrige un borrador, la sugerencia de mejora
  que Mia genera ahora apunta al procedimiento que DE VERDAD participó en
  ese trabajo (antes podía proponer mejorar uno cualquiera), se redacta
  viendo el contenido real de ese procedimiento, y al aplicarla queda
  guardada la versión anterior (se puede volver atrás).
- El listado de sugerencias ahora dice QUÉ procedimiento se va a modificar.
- Para ver el ciclo completo en vivo falta UN insumo de negocio: que Pipe
  suba sus primeras guías de trabajo (botón/endpoint de importar guías).

### Frontend a revisar (Cursor — capa 3)

- Sin pantalla nueva. NOTA para CP7: `GET /api/proposals` ahora devuelve un
  campo `target` (título del procedimiento a modificar) — la Pantalla 4
  (memoria) debería mostrarlo junto a cada sugerencia. Siguen PENDIENTES de
  capa 3 los 2 archivos de CP5.

### Resultado de verificación (3 capas)

- Capa 1: regresión completa **41/41 suites PASS** (test_rls 12/12 HALT);
  gates extendidos: test_feedback_processor 26/26, test_gepa 18/18,
  test_trace_capture 23/23, test_ux 29/29.
- Capa 2 (revisor independiente): **APROBADO** sin bloqueantes; sus 2
  hallazgos mayores (del flujo pre-existente de aplicar sugerencias,
  agravados por este checkpoint) se corrigieron antes del commit.
  Revisión por lectura de patrones conocidos, no auditoría con herramientas.
- Capa 3 (Cursor): NO APLICA (sin frontend; ver nota para CP7 arriba).

---

## Checkpoint anterior: CP-B3 — Mia te avisa y recuerda (2026-07-01)

### Qué cambió (lenguaje simple)

- Mia ahora es proactiva: el abogado le pide recordatorios escribiéndole
  normal ("recuérdame radicar la tutela mañana a las 9") y Mia le avisa por
  Telegram a la hora pactada; también avisa cuando un borrador queda
  esperando su revisión (máximo un aviso al día por asunto) y envía el
  reporte semanal de lo aprendido.
- Regla de negocio dura: si el recordatorio menciona un plazo o actuación
  procesal, SIEMPRE va con [VERIFICAR] — la fecha la pone el abogado y la
  confirma él; Mia no calcula términos legales, y "días hábiles" ni se
  agendan: se pide la fecha exacta.
- Todo es opt-in: sin el bot de Telegram configurado, nada suena y Mia lo
  dice honestamente al confirmar ("quedará visible en tu lista de
  recordatorios").

### Frontend a revisar (Cursor — capa 3)

- CP-B3 NO trae pantalla nueva (la UI de recordatorios llega con CP7; ya
  existen los endpoints GET /api/assistant/reminders y POST
  /api/assistant/reminders/{id}/cancel). Siguen PENDIENTES de capa 3 los 2
  archivos de CP5 listados en el checkpoint anterior.

### Resultado de verificación (3 capas)

- Capa 1: regresión completa **41/41 suites PASS** (test_rls 12/12 HALT);
  gate nuevo `test_reminders` **64/64**.
- Capa 2 (revisor independiente, contexto fresco): APROBADO CON
  CORRECCIONES — 2 bloqueantes y 5 mayores, TODOS corregidos antes del
  commit y convertidos en checks del gate (detalle en memory/progress.md,
  sesión 22). Residuales aceptados en memory/bugs-and-risks.md (Riesgo #35).
  Revisión por lectura de patrones conocidos, no auditoría con herramientas.
- Capa 3 (Cursor): NO APLICA (sin frontend en este checkpoint).

---

## Checkpoint anterior: CP3 + CP-C2 — Conocimiento del despacho y vault de Obsidian (2026-07-01)

### Qué cambió (lenguaje simple)

- CP3: Mia ya analiza con el MÉTODO DEL DESPACHO — al diagnosticar un
  asunto usa las notas y criterios internos del despacho (lo indexado
  desde Obsidian y las carpetas de trabajo), siempre como orientación
  de método, nunca en reemplazo de la norma o la sentencia. APROBADO
  por Pipe con una comparación en vivo (mismo caso, con y sin el
  conocimiento del despacho).
- CP-C2: Mia escribe su memoria donde el abogado la ve — su vault de
  Obsidian. Los conceptos que aprende y los reportes semanales quedan
  como notas normales bajo la carpeta `Mia/` del vault; Mia JAMÁS toca
  las notas del abogado. Incluye instalación guiada de Obsidian para
  quien no lo tenga (con confirmación explícita).

### Frontend a revisar (Cursor — capa 3)

- CP3 y CP-C2 no traen pantalla nueva (la UI de conectores llega en
  CP7). Siguen PENDIENTES de la capa 3 los 2 archivos de CP5:
- `frontend/app/page.tsx`: punto naranja en la lista de asuntos cuando
  hay borrador pendiente (title="Borrador esperando tu revisión").
- `frontend/app/asuntos/[id]/page.tsx`: panel "Diagnóstico" (texto con
  scroll interno; estado vacío: "Mia aún no ha analizado este asunto.").

### Comportamiento esperado

- Con notas del despacho indexadas, al preguntar en un asunto el
  análisis refleja el método interno (y sigue marcando [VERIFICAR] lo
  que corresponda). Si el despacho no tiene notas indexadas, todo se
  comporta EXACTAMENTE igual que antes.
- Al consolidarse un concepto o generarse el reporte semanal, aparece
  una nota nueva en `{vault}/Mia/conceptos/` o `{vault}/Mia/reportes/`
  visible en Obsidian; las notas del abogado quedan intactas.

### Bugs conocidos / fuera de alcance

- Menores anotados por los revisores: el presupuesto del 15% para las
  notas usa un estimador de tokens aproximado (podría quedarse corto o
  largo en casos límite); si el disco/OneDrive del vault no está
  disponible, la nota espejo no se escribe (queda solo en el registro
  interno — no se pierde nada, se reintenta en el siguiente ciclo).
- Decisiones de producto pendientes de Pipe (ver bugs-and-risks.md):
  privacidad de las conversaciones del asistente, diagnóstico visible
  tras aprobar, y deshabilitar la instalación de Obsidian en Modo A.

### Resultado de verificación (3 capas)

- Capa 1 (automatizada): regresión completa **40/40 suites PASS**
  (test_rls 12/12 HALT PASS); gates nuevos: test_retrieval_knowledge
  **35/35** y test_vault_write **34/34**.
- Capa 2 (revisores independientes con contexto fresco): CP3 aprobado
  con 1 mayor CORREGIDO (las notas del despacho entran al prompt
  delimitadas y con orden de no obedecer instrucciones embebidas —
  anti-inyección — más margen de recorte y limpieza de metadatos).
  CP-C2 aprobado con 2 mayores CORREGIDOS (escape por junction/symlink
  de Windows hacia fuera del vault BLOQUEADO fail-closed — reproducido
  con mklink /J; escritura al vault ya no congela el servidor con
  discos lentos). Revisión por lectura de patrones conocidos, no
  auditoría con herramientas de escaneo.
- Capa 3 (Cursor): PENDIENTE — revisar los 2 archivos de CP5 listados
  arriba y devolver hallazgos en la sección final.

### Checkpoint anterior: CP-B2 + CP-C1 — Telegram y carpetas del abogado (2026-07-01)

Mia atiende por Telegram (bot privado single-chat, opt-in hasta que
Pipe cree su bot — guía docs/telegram-setup.md) y conoce las carpetas
de trabajo autorizadas (disco, OneDrive, Google Drive); carpetas de
sistema excluidas SIEMPRE. Gates: test_telegram_bridge 22/22 y
test_local_folders 39/39; test_obsidian_sync 22/22 sin regresión.
Revisores: CP-B2 con 2 mayores corregidos (token del bot filtrado a
logs; instructivo roto por espacios de la ruta); CP-C1 con 2 mayores
de privacidad corregidos (subcarpetas de sistema excluidas también en
el descenso recursivo; carpetas >2000 archivos sin pérdida de
conocimiento). Sin frontend (capa 3 no aplica).

### Checkpoint anterior: CP5 + CP-B1 — Diagnóstico visible y modo asistente (2026-07-01)

CP5: panel "Diagnóstico" en la pantalla del asunto + punto naranja de
borrador pendiente en la lista (gate test_ux 29/29 con npm run build);
2 ventanas de carrera de milisegundos anotadas (se autocorrigen solas).
CP-B1: modo asistente — conversación libre con memoria por tenant y
usuario (test_assistant 32/32); el revisor encontró 1 BLOQUEANTE de
confidencialidad entre despachos (compresor compartido) + 2 mayores —
LOS 4 hallazgos corregidos y cubiertos con checks antes del commit.
Capa 3 de Cursor PENDIENTE sobre sus 2 archivos de frontend (los
mismos listados en el checkpoint actual).

---

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
