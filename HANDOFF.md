# HANDOFF — Mia (traspaso a Cursor)

## Cómo usar este archivo

Cursor lee este archivo al iniciar sesión en el repositorio. Aquí queda
registrado el checkpoint más reciente del trabajo hecho en Claude Code:
qué cambió, qué debe revisarse en el frontend y qué comportamiento se
espera. Al terminar su revisión visual (capa 3), Cursor escribe sus
hallazgos en la sección final "Hallazgos de Cursor (capa 3)" para que
quede trazabilidad de ambas revisiones.

---

## Checkpoint más reciente: Sesión 39 (2026-07-09) — BLOQUE A COMPLETO: Proyectos + carpetas sin fricción

### Qué se hizo esta sesión (lenguaje simple)

Se ejecutó COMPLETO el Bloque A del plan de evolución de producto (aprobado por Pipe), con
orquestación multi-agente según su autorización expresa de la sesión 38:

- **Pestaña "Proyectos" (nueva):** espacio de trabajo libre estilo Claude Cowork — el abogado
  crea un proyecto en 2 pasos, conecta carpetas, chatea con Mia sobre esas fuentes (con memoria
  de la conversación) y guarda los documentos que Mia produce, con descarga en Word. Sin
  diagnóstico ni aprobación de borrador (eso sigue siendo de los Asuntos, separados como pidió Pipe).
- **Fin de las rutas pegadas a mano:** selector visual de carpetas del equipo (navegable, seguro,
  fail-closed) en los 3 sitios donde antes se pegaba la ruta (carpetas de trabajo, carpeta del
  expediente, vault de Obsidian).
- **Varias carpetas por asunto/proyecto** — y de paso se corrigió DE RAÍZ el bug latente de poda
  cruzada (documentado en el plan): con 2 carpetas, el sync de una ya no puede borrar los
  documentos de la otra (ni en carpetas del equipo NI en OneDrive, donde también existía).
- **Panel "Fuentes" unificado** en la pantalla del asunto y del proyecto: carpetas del equipo +
  OneDrive + correos en una sola lista con estados en llano y "+ Conectar fuente".

### Resultado de verificación (3 capas)

- **Capa 1: regresión completa ALL PASS (74 suites)** — línea base sube de 70 a 74:
  `test_matter_folders_multi` 30/30 (el caso del bug de poda cruzada + concurrencia + backfill
  conservador), `test_folder_browse` 15/15, `test_projects` 33/33, `test_matter_sources` 26/26.
  `test_rls` 12/12 y `check_env_pins` 9/9 (HALT) intactos. `npm run build` verde (14 páginas).
- **Capa 2: revisión adversarial multi-agente (contexto fresco)** — 12 hallazgos CONFIRMADOS,
  todos corregidos y re-verificados antes del commit salvo 2 notas aceptadas como deuda:
  2 BLOQUEANTES (el backfill de la migración podía fusionar procedencias y provocar borrado de
  documentos conservados; la poda de OneDrive seguía sin distinguir fuente → borrado cruzado
  con multi-carpeta), 2 MAYORES (carrera de sincronización sin candado en el motor → documentos
  duplicados; el chat de proyecto no recordaba los turnos anteriores), 6 menores (proyectos
  contados como "asuntos" en asistente/dashboard/endpoint legacy, burbuja "pensando" infinita
  en error, doble Enter creaba proyectos duplicados, mensaje con la palabra equivocada).
  Detalle completo en `memory/progress.md` sesión 39.
- **Capa 3: PENDIENTE — recorrido en vivo de Pipe** (ver lista abajo).

### Capa 3 para Pipe (recorrido sugerido en http://localhost:3100)

1. **Proyectos:** crear un proyecto (nombre → conectar carpeta con el selector visual → entrar),
   chatear sobre los documentos, verificar que un segundo mensaje recuerda el anterior, guardar
   una respuesta larga con "Guardar en el proyecto" y descargarla en Word.
2. **Selector de carpetas:** en Configuración → Carpetas y en un asunto ("Conectar fuente →
   Carpeta del equipo"), navegar y elegir sin pegar rutas.
3. **Panel Fuentes del asunto:** vincular 2 carpetas al mismo asunto, "Revisar ahora" en una,
   confirmar que los documentos de la otra no se tocan; el botón de correos sigue ahí.
4. Sigue pendiente la capa 3 arrastrada de sesiones 35-38 (onboarding/panel/rebrand + los 5
   puntos de fuentes remotas) — nada de eso cambió en esta sesión.

### Pendientes y próximo paso

1. **PRÓXIMA SESIÓN: Bloque B** del plan (guías de trabajo asistidas — "Crear guía con Mia" con
   gate HITL por construcción + CRUD/versiones de playbooks + gobernanza de lo aprendido).
   El plan vive en `memory/plan-evolucion-producto.md` (Bloque A ya marcado completado).
2. **ACCIÓN DE PIPE (sin cambio):** registrar las apps OAuth (guía en `docs/guia-conectar-correo-y-nube.md`).
3. Deuda consciente nueva: el navegador de carpetas queda deshabilitable por flag para el futuro
   Modo A/Docker (Riesgo #56); documentos con procedencia ambigua pre-migración nunca se podan
   solos (protección anti-pérdida, Riesgo #57); `MatterDriveFolder.tsx` quedó sin uso (borrar
   en una limpieza futura).

### Trabajo en background sin leer

Nada — todos los workflows y la regresión final se leyeron y quedaron reflejados aquí.

### Decisiones tomadas / suposiciones declaradas

- `documents.body` (texto íntegro) para los archivos que Mia produce: los fragmentos indexados
  llevan traslape y no se pueden reconstruir para el Word. Suposición razonable no prevista en
  el plan, declarada aquí.
- `GET /api/matters` sin parámetro devuelve SOLO asuntos (compatibilidad de la lista actual);
  `?kind=proyecto` y `?kind=todos` para lo demás. Asistente, dashboard y endpoint legacy también
  filtran proyectos.
- Los endpoints singulares `/folder` quedan como wrappers deprecados (sin el 409); el frontend
  ya usa la superficie plural vía FuentesPanel.
- Memoria conversacional del proyecto: corta y presupuestada (últimos 6 turnos / 8.000
  caracteres), solo en proyectos — el flujo de asuntos quedó byte a byte intacto (gate HITL 21/21).

---

## Checkpoint anterior: Sesión 38 (2026-07-09) — Cáscara de escritorio + rediseño onboarding/panel + rebrand visual + PLAN APROBADO de evolución de producto

### Qué se hizo esta sesión (retoma post-apagón, todo en `origin/main`)

- **Cáscara de escritorio Tauri (Fase 4 · bloque 2)** — `35b3a96`: la app que el abogado abre
  y enciende/apaga todo (DB→backend→frontend). E2E de 5 ciclos + Job Object anti-huérfanos
  verificado con crash simulado. Revisión adversarial: 2 mayores + 5 menores corregidos.
- **Onboarding rediseñado** — `46db38c`: 8 preguntas (fuera estilo/límites/ritmo — el estilo
  se aprende del flywheel), UNA pregunta de país con 21 países multi-select, ejemplos sin
  Lexia. e2e 32/32, second_brain_ui 26/26.
- **Panel/Configuración reestructurados** — `0d5e826`: el Panel solo con lo accionable
  (Para tu decisión + recordatorios + recomendaciones + Este mes); Configuración absorbe
  conexiones/carpetas/automatizaciones/valor. Guía OAuth en `docs/guia-conectar-correo-y-nube.md`.
- **Rebrand visual completo** — `13f0d55`: paleta Lexia (teal/negro/degradé verde), sidebar
  negra con wordmark MIA (I en teal), Archivo+Hind, aurora teal, card-depth. Pipe lo vio en
  vivo y le gustó ("me gusta lo que estoy viendo").

### PRÓXIMA SESIÓN: ejecutar el plan de evolución de producto (APROBADO por Pipe)

> **AUTORIZACIÓN EXPRESA DE PIPE (2026-07-09, en sus palabras):** ejecutar el plan
> **usando workflows de orquestación multi-agente desde el arranque, a velocidad
> máxima**. Es decir: al retomar con /arranque, usar el tool Workflow (fan-out de
> ejecutores en paralelo sobre partes disjuntas del Bloque A + verificación
> adversarial multi-agente) sin volver a pedirle permiso. Los límites NO cambian:
> verificación de 3 capas antes del cierre, gate HITL innegociable, HALT si
> test_rls falla, y capa 3 visual sigue siendo de Pipe.

**El plan completo vive en `memory/plan-evolucion-producto.md`** (misma copia en
`C:\Users\USER\.claude\plans\chad-me-gusta-lo-memoized-token.md`). Resumen:
- **Bloque A (EMPEZAR AQUÍ):** pestaña "Proyectos" estilo Claude Cowork (reusa `matters`
  con `kind`), selector visual de carpetas del equipo (fin de rutas pegadas a mano),
  multi-carpeta por asunto (⚠️ PRIMERO `documents.source_id` — hay bug latente de poda
  cruzada documentado en el plan), panel "Fuentes" unificado.
- **Bloque B:** "Crear guía con Mia" (entrevista stateless con gate HITL por construcción),
  CRUD+versiones de playbooks, gobernanza de skills aprendidas (fusionar subtabs).
- **Bloque C:** Personas → "Agentes jurídicos" con conocimiento vinculado, perfil del
  despacho editable (SOUL como fuente canónica, `/api/profile/full`), Configuración en subtabs.
- Decisiones de Pipe: todo en orden A→B→C, un bloque por sesión; Proyectos y Asuntos como
  pestañas SEPARADAS. Verificación 3 capas por bloque; gate HITL innegociable.

**Pendientes de Pipe (sin cambio):** registrar apps OAuth (guía en docs/), capa 3 en vivo
de sesiones 35-36 y del onboarding/panel/rebrand nuevos.

---

## Checkpoint anterior: Sesión 37 (2026-07-09) — OCR local para PDFs escaneados + sincronización automática de OneDrive

### Qué se hizo esta sesión

> Nota: la sesión se interrumpió por un corte de luz tras el último commit; el cierre (regresión
> completa + esta memoria) se completó en la retoma del mismo día. No se perdió trabajo.

- **Bloque 3a — Mia ya lee PDFs escaneados (OCR local):** en litigio la mayoría de expedientes
  son escaneos sin capa de texto; antes Mia quedaba ciega SIN AVISAR. Ahora los lee con un motor
  de lectura óptica que corre 100% en el servidor del despacho (el documento nunca sale de ahí),
  página por página, marcando con honestidad qué partes vienen de lectura óptica. Fail-soft:
  tope de 150 páginas / 10 minutos con corte anotado; una página corrupta no tumba el documento;
  un archivo sin cuerpo legible NO entra como documento válido (se reporta y se reintenta luego).
- **Bloque 3b — las carpetas de OneDrive se mantienen al día solas:** job programado cada 6 horas
  (misma cadencia que Obsidian) que sincroniza las fuentes de OneDrive remoto de cada despacho;
  comparte el candado con el botón manual (nunca corren dobles) y una carpeta rota no tumba las
  demás. Cierra la deuda #1 de la sesión 36.
- **Revisión adversarial (capa 2) corrida y cerrada:** 3 mayores + 4 menores, TODOS corregidos
  antes del cierre (`ea28423` + `315dbd1`): el OCR ya no congela el servidor (async), RAM acotada
  ante PDFs con páginas descomunales, "solo nota sin cuerpo" ya no entra como documento, gate de
  no-egress que PRUEBA que el OCR no hace ninguna llamada de red, y la guarda de cuerpo legible
  replicada también en carpetas locales.

### Frontend a revisar (Cursor — capa 3): NO APLICA

Los 4 commits son backend + tests puros — no hay UI nueva. Sigue pendiente la capa 3 de la
sesión 36 (fuentes remotas) y la del botón "Revisar ahora" (sesión 35) — ver checkpoint anterior.

### Resultado de verificación (3 capas)

- **Capa 1: regresión completa 70/70 suites ALL PASS** (corrida en la retoma post-apagón) —
  `test_rls` 12/12 y `check_env_pins` 9/9 (HALT) intactos; línea base sube de 69 a 70 con
  `test_ocr_ingest` 26/26. Sin frontend tocado → sin `npm run build`. (Nota de tally:
  `test_speech_tts` es 24/24 en el script actual; el 26/26 histórico era de otra versión.)
- **Capa 2:** revisor adversarial independiente — 3 mayores + 4 menores, TODOS corregidos y
  re-verificados; detalle en `memory/progress.md` sesión 37 y Riesgo #55.
- **Capa 3: NO APLICA** (sin UI nueva en esta sesión).

**Commits de esta sesión en `main`, SIN PUSH todavía:** `ad16a64` (OCR bloque 3a), `10788c2`
(cron OneDrive bloque 3b), `ea28423` (correcciones capa 2), `315dbd1` (guarda has_body en
carpetas locales) + el commit de cierre de esta memoria. Los commits de la sesión 36 ya están
en `origin/main`.

**Pendiente real para la próxima sesión:**
1. Capa 3 EN VIVO de Pipe/Cursor — los 5 puntos de la sesión 36 (abajo) + botón "Revisar ahora".
2. **ACCIÓN DE PIPE:** registrar las apps OAuth (Azure AD y Google Cloud) y poner las llaves en
   `.env` — hasta entonces las fuentes remotas responden 503 en llano (por diseño).
3. Quick win #5 (checklist de pre-entrega en el gate de aprobación) espera aprobación de Pipe.
4. Decidir push a `origin/main` de los commits de esta sesión.

---

## Checkpoint anterior: Sesión 36 (2026-07-09) — Fuentes remotas del expediente (Gmail + OneDrive vía la nube)

### Qué se hizo esta sesión

Bloque 2 de la Fase 3 (el que quedó pendiente en el HANDOFF de la sesión 35): el abogado ya puede
traer correos (Microsoft/Google) y carpetas de OneDrive al expediente, con OAuth multi-proveedor de
base (un despacho puede tener Microsoft Y Google conectados a la vez). Construido en 4 fases:

- **Fase 1 — cimientos OAuth multi-proveedor:** `tenant_oauth_tokens` con PK `(tenant_id, provider)`;
  migración `027_remote_sources.sql` (+ `remote_drive_sources`, `remote_file_hashes`, RLS FORCE);
  `documents.origin` gana `'mail'`/`'drive'`. `GET /api/mailbox/status` ahora reporta POR PROVEEDOR.
- **Fase 2 — correos del caso → expediente:** buscar y vincular correos (cuerpo + adjuntos se
  vuelven documentos, dedupe por sha256, máx 20 por lote).
- **Fase 3 — OneDrive remoto SELECTIVO de solo lectura:** navegar carpetas, registrar una fuente,
  sincronizar (incremental por eTag→sha256, tope 20MB por archivo, fail-soft por archivo, tope 20
  fuentes por despacho).
- **Fase 4 — UI:** navegador modal de carpetas, diálogo de búsqueda de correos, tarjetas del Panel
  de control por proveedor con checkbox de OneDrive.

Detalle completo (piezas de código, los 3 mayores + 6 menores corregidos en `c9f2a32`) en
`memory/progress.md` sesión 36 y `memory/bugs-and-risks.md` Riesgo #54.

### Frontend a revisar (Cursor — capa 3, PENDIENTE)

Toda la UI de esta sesión (`OneDriveFolderPicker`, `OneDriveSourcesSection`, `MatterDriveFolder`,
`MailSearchDialog`, `MailboxSection`) pasó `npm run build` verde y está cubierta por gates de API,
pero **nadie la recorrió en un navegador real todavía.** Pendiente:

1. **Conectar Microsoft con "Incluir mis archivos de OneDrive"** y verificar el flujo real de
   consentimiento OAuth (requiere que Pipe haya puesto las llaves en `.env` primero — ver más abajo).
2. **Navegador de carpetas:** entrar 2-3 niveles y elegir una carpeta para sincronizar.
3. **Probar el 503** cuando no hay conexión configurada, y el botón nuevo **"Añadir permiso de
   archivos"** sobre una cuenta Microsoft que solo tenía correo conectado.
4. **Buscar y vincular 2-3 correos reales** desde el diálogo del asunto y verlos aparecer como
   documentos del expediente.
5. **Responsive** de los dos modales nuevos (buscador de correos, navegador de carpetas).

También sigue pendiente la capa 3 del botón "Revisar ahora" (deuda arrastrada de la sesión 35).

**Contratos de los endpoints nuevos (por si Cursor los necesita):**
- `GET /api/mailbox/status` → `{conectado, conexiones:[{proveedor, proveedor_nombre, conectado,
  funciones:[...], archivos:bool}], analisis_contenido, proveedor?, proveedor_nombre?, proveedores?}`
  — `archivos` indica si esa conexión YA tiene permiso de OneDrive (para ofrecer "Añadir permiso").
- `GET /api/matters/{id}/mail/search?q=&provider=` → `{resultados:[{...,provider}]}`; sin `provider`
  busca en todas las cuentas conectadas; sin cuenta conectada → 503 en llano.
- `POST /api/matters/{id}/mail/link` con `{items:[{provider, message_id}]}` (máx 20) →
  `{added:[...], already:[...], skipped:[{name, reason}]}` — un fallo individual nunca tumba el lote.
- `GET /api/drive/browse?item_id=` → `{items:[...]}` (un nivel de OneDrive; sin `item_id` = raíz);
  503 sin cuenta/permiso, 502 si Graph falla.
- `GET /api/drive/sources` / `POST /api/drive/sources` (`{remote_item_id, label?, kind, matter_id?}`)
  / `DELETE /api/drive/sources/{id}` / `POST /api/drive/sources/{id}/sync` (throttle 60s + lock de
  corrida en vuelo, ambos con mensaje en llano).

### Resultado de verificación (3 capas)

- **Capa 1:** regresión completa **69/69 suites ALL PASS** (dos corridas, antes y después de las
  correcciones de capa 2) — `test_rls` 12/12 y `check_env_pins` 9/9 (HALT) intactos; `npm run build`
  verde. Gates nuevos: `test_mailbox_multi.py` 21/21, `test_mail_to_matter.py` 24/24,
  `test_remote_drive.py` 35/35. (Nota de tally: `test_setup_wizard` es 28/28, no el 30/30 que quedó
  anotado en HANDOFFs anteriores — correspondía a otra versión del script.)
- **Capa 2 — dos revisores adversariales independientes (contexto fresco):** seguridad **APROBADO
  sin bloqueantes ni mayores** (RLS, OAuth state con nonce+cookie anti-CSRF, sin fuga de tokens/
  contenido, SQL parametrizado, límites verificados); corrección encontró **3 mayores + 6 menores,
  TODOS corregidos** antes del commit `c9f2a32` (renombrar en OneDrive ya no borra el archivo del
  expediente; la UI espera a que la sync termine; botón para agregar permiso de archivos a una
  cuenta ya conectada; fallo por-correo no tumba el lote; `last_synced_at` por fuente; reset del
  diálogo al cerrar; uuid malformado → 404; embeddings fuera de la conexión pooled; ids de URL
  escapados; scopes base de Microsoft siempre incluidos).
- **Capa 3: PENDIENTE** — sin navegador conectado en esta sesión; ver la lista de 5 puntos arriba.

**5 commits en `main`, SIN PUSH todavía:** `7ccab33` (Fase 1 OAuth), `8c2c28a` (Fase 2 correos),
`a84088a` (Fase 3 OneDrive), `b989e39` (Fase 4 UI), `c9f2a32` (correcciones de capa 2).

**Pendiente real para la próxima sesión:**
1. Capa 3 EN VIVO de Pipe/Cursor (los 5 puntos de arriba) + la capa 3 pendiente del botón "Revisar
   ahora" (sesión 35).
2. **ACCIÓN DE PIPE:** registrar las apps OAuth (Azure AD y Google Cloud) y poner las llaves en
   `.env` (`MS_OAUTH_CLIENT_ID/SECRET`, `GOOGLE_OAUTH_CLIENT_ID/SECRET`) — hasta entonces todo
   responde 503 en llano (activación diferida, por diseño).
3. Quick win #5 (checklist de pre-entrega en el gate de aprobación) sigue esperando aprobación de Pipe.
4. Deuda consciente: sincronización PROGRAMADA de fuentes OneDrive (hoy solo botón manual).
5. Decidir si se hace push a `origin/main` de estos 5 commits.

---

## Checkpoint anterior: Sesión 35 (2026-07-08) — Frentes B/C + Data Factory del corpus + bugfix FTS

### Qué se hizo esta sesión

Sesión de retoma: había ~5h de trabajo de una sesión previa sin commitear ni documentar (nunca corrió
`/cierre`). Se reconstruyó por lectura de código, se verificó y se corrigió antes de commitear:

- **Bugfix** `agents/research.py`: la consulta FTS de investigación mandaba el mensaje completo del
  abogado (0 resultados casi siempre) → ahora usa términos clave + citas exactas en OR.
- **Frente B (aprendizaje):** motivo del rechazo en la traza (B1), botón "Revisar ahora" en
  Conocimiento → `POST /api/learning/run` (B2), aprobar una corrección de wiki ya la aplica de verdad
  al archivo del concepto (B4).
- **Fase 3 · frente C + Data Factory del corpus:** `rag/corpus_factory.py` (motor único, jurisdicción
  por pack JSON — nada de Colombia hardcodeado, ver decisión de Pipe en `memory/progress.md` sesión
  35) + `connectors/vault_export.py` (backfill de playbooks y fichas del corpus al vault de Obsidian).

Detalle completo, con los 5 hallazgos de capa 2 y sus correcciones, en `memory/progress.md` (sesión 35).

### Frontend a revisar (Cursor — capa 3)

- `frontend/app/memoria/page.tsx` (pestaña Sugerencias): botón nuevo **"Revisar ahora"** sobre la
  lista de propuestas — dispara `POST /api/learning/run`, muestra spinner mientras corre y un mensaje
  de resultado ("Mia propuso N mejoras nuevas" / "no encontró nada nuevo"). `npm run build` verde y
  cubierto por gate de API; falta el recorrido visual en vivo (clic real, estados de carga/error).
- Nada más cambió en `frontend/`; el resto de esta sesión fue backend puro (Data Factory, vault export,
  bugfix de investigación) sin superficie nueva para el abogado más allá del botón de arriba.

### Resultado de verificación (3 capas)

- Capa 1: regresión completa **66/66 suites verdes** (dos corridas — antes y después de aplicar las
  correcciones de capa 2), `test_rls`/`check_env_pins` HALT intactos. Gates nuevos: `test_research_query`
  11/11, `test_corpus_factory` 12/12, `test_vault_export` 38/38.
- Capa 2 (revisor adversarial independiente, workflow multi-agente): 5 hallazgos CONFIRMADOS, los 5
  corregidos y RE-VERIFICADOS antes del commit (colisión de slug al exportar playbooks; parseo frágil
  del concepto de una wiki_correction → columna dedicada; conexión pooled sostenida durante E/S de
  disco; lógica de identidad duplicada entre adaptadores del corpus; fetches secuenciales evitables).
- Capa 3: **PENDIENTE** — sin navegador conectado en esta sesión para el recorrido en vivo del botón.

**6 commits en `main`, YA PUSHEADOS a `origin/main`:** `9f62b4e`, `4ea4126`, `cb32ebb`, `00728c8`,
`8376726`, `c11fb71` (el último añade 3 de los 5 quick wins de
`docs/analisis-claude-for-legal.md` — detalle en `memory/progress.md`, regresión 66/66 y capa 2
con 3 hallazgos corregidos antes del commit).

**Pendiente real para la próxima sesión (ya no queda nada "chico" en la cola):**
1. Capa 3 visual en vivo (botón "Revisar ahora" en Conocimiento + los quick wins de prompt no
   tienen UI que revisar, son solo texto de sistema).
2. **Gmail/OneDrive vía Graph API** (bloque 2 de la Fase 3, `mia-decisiones-pipe-fase3` en
   memoria) — es la siguiente pieza grande. Antes de construirla a ciegas, vale la pena que Pipe
   confirme alcance: ¿Gmail primero (correos+adjuntos del caso como parte del expediente) o
   OneDrive vía Graph API primero (la sincronización LOCAL de OneDrive/Google Drive Desktop ya la
   cubre `local_folder_sources`/F3.1 para quien tenga el cliente de escritorio instalado — el
   Graph API solo aporta valor si el abogado NO usa el cliente de escritorio)? Necesita también
   que Pipe registre la app OAuth (mismo patrón "activación diferida" que Microsoft 365/Google ya
   tienen: backend/UI listos, 503 hasta que lleguen las llaves).
3. Quick win #5 (checklist de pre-entrega ejecutado en el gate de aprobación) — requiere
   aprobación previa de Pipe por tocar `hitl_checkpoint`.

---

## ⭐ Trabajo de frontend PENDIENTE para Cursor (consolidado · priorizado · 2026-07-03)

El backend de estos puntos ya está en `origin/main`; falta SOLO la UI. Cada uno tiene su
sección detallada más abajo con endpoints y comportamiento. Orden sugerido:

1. **Control del tope de gasto de IA (CP-E1)** — `GET/PUT /api/policy/budget`. **COMPLETADO** (commit `7030e5e`). Detalle en la sección "CP-E1 · control del tope en el Panel".
2. **Pantalla de gestión de Personas jurídicas (CP-E3, lo más nuevo)** — CRUD
   `GET/POST/PUT/DELETE /api/personas`. **COMPLETADO** (commit `557478c`). Detalle en la sección "CP-E3" arriba de todo.
3. **Tarjetas de "Recomendaciones de Mia" (CP-V2)** — `GET /api/dreams/prescriptions` +
   `POST .../{id}/decision`. **COMPLETADO** (commit `c61912f`). Detalle en la sección "CP-V2".
4. **Automatizaciones (CP-P2)** — plantillas + sugerencias consent-first (`/api/automations/*`). **COMPLETADO** (commit `5642a73`).
5. **Conectar Microsoft 365 / Google (CP-P3)** — botón "Conectar" (`/api/mailbox/*`). **COMPLETADO** (commit `70ac8e7`). OJO:
   la ACTIVACIÓN real (llaves OAuth en `.env`) sigue APLAZADA por decisión de Pipe hasta el producto
   final; la UI está lista y muestra el aviso 503 si el servidor aún no tiene las llaves.

**Reglas para Cursor (recordatorio):** §G sin jerga técnica al abogado (nada de "tenant",
"LangGraph", "modelo", "pgvector"); errores del backend llegan en llano — mostrarlos tal cual;
tras `npm run build` reinicia el dev server (pisa la caché `.next`). Escribe tus hallazgos de
capa 3 al final del archivo.

---

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

## Checkpoint actual: CP-E6 — Más canales (relay) + conectar sistemas vía MCP (2026-07-04)

### Qué cambió (lenguaje simple)

- **Conectar sistemas del despacho (lo nuevo para el abogado):** Mia ahora puede conectarse
  a sistemas externos —**gestión documental** del despacho y **consulta de estados de
  procesos judiciales**— para trabajar con esa información. Todo nace **apagado**: el
  despacho lo enciende con sus credenciales cuando quiere, y lo apaga (o borra las
  credenciales) cuando quiere.
- **Seguridad primero:** las credenciales viven **fuera** del cerebro de Mia; se piden
  tokens de **solo lectura**; y al conectar, ningún secreto interno de Mia se filtra.
- **Más canales:** se preparó el patrón "relay" para que sumar canales (WhatsApp, correo…)
  sea un adaptador delgado, con las llaves del canal fuera del núcleo. El puente de
  Telegram ya usa ese patrón común.

### Frontend PENDIENTE para Cursor — pantalla "Sistemas conectados"

En "Configurar a Mia", una sección nueva para conectar sistemas. Endpoints (`/api/mcp/*`):

- `GET /api/mcp/status` → lista de sistemas. Cada uno trae: `slug`, `display_name`
  (mostrar ESTE, en llano), `description`, `permissions_note` (nota de permisos mínimos —
  mostrarla para tranquilidad del abogado), `fields` (cada uno: `env_var`, `label`,
  `is_secret`, `required`), `enabled`, `configured`, `missing` (etiquetas de lo que falta).
- `POST /api/mcp/{slug}/enable` con body `{ "env": {…}, "secrets": {…} }` → guarda las
  credenciales y habilita. `env` = campos NO secretos (URLs), `secrets` = tokens. Las
  claves van por `env_var`/`secret_key` que da `fields`. Devuelve el status actualizado.
- `POST /api/mcp/{slug}/disable` → apaga sin borrar credenciales. Devuelve status.
- `POST /api/mcp/{slug}/forget` → borra la conexión y sus credenciales. Devuelve status.

Comportamiento esperado en la UI:
- Por cada sistema: nombre + descripción + nota de permisos; un formulario con los
  `fields` (los `is_secret:true` como campo tipo contraseña). Botón "Conectar" (enable),
  y si `enabled`: "Desconectar" (disable) y "Borrar credenciales" (forget).
- El backend **nunca** devuelve el valor de un secreto — no intentes precargarlo; usa
  `configured`/`missing` para mostrar si ya está puesto.
- Errores del backend llegan en llano (§G) — mostrarlos tal cual. Nada de "MCP",
  "servidor", "tenant": el abogado ve "Gestión documental del despacho".
- **No urgente / activación diferida:** igual que "Conectar Microsoft 365", la conexión
  EN VIVO con estos sistemas depende de registrar el servidor real; la UI puede quedar
  lista sin que haya un sistema conectado todavía.

Detalle técnico completo en `docs/canales-y-mcp.md`.

---

## Checkpoint anterior: CP-E5 — Delegación multi-agente + tablero de misión por expediente (2026-07-04)

### Qué cambió (lenguaje simple)

- **Tablero de misión por expediente (lo que ve el abogado):** el abogado puede tomar un
  objetivo grande de un asunto —"preparar la contestación", "alistar la audiencia"— y Mia lo
  **descompone en hitos concretos y ordenados** que se ven como un tablero. Cada hito dice
  qué es, quién lo hace (**Mia lo prepara** o **lo haces tú**) y en qué estado va
  (**pendiente / en curso / hecho**). El abogado **aprueba, edita, reordena y marca avance a
  mano**: nada se ejecuta solo (consent-first).
- **Regla dura respetada:** el tablero **no maneja fechas ni plazos**. Si un hito toca un
  término procesal, queda **marcado para que el abogado lo verifique** (Mia nunca calcula
  plazos). No hay ninguna casilla de fecha en el tablero.
- **Investigación en paralelo (por dentro, no lo ve el abogado):** cuando un despacho trabaja
  en **dos o más jurisdicciones**, Mia ahora investiga cada una **por separado y a la vez**, y
  luego consolida. Para Lexia (solo Colombia) **no cambia nada** hoy: sigue el camino de
  siempre, mismo costo. Detalle en `docs/comparacion-cpe5.md`.

### Frontend a construir (Cursor — capa 3): el tablero de misión

Backend listo en `origin/main` (tras aprobación de Pipe). Falta la **pantalla del tablero**,
idealmente dentro de la vista de un asunto (una pestaña "Plan" o "Misión"). Endpoints (todos
bajo `/api`, auth como el resto; todos devuelven la **misión completa** salvo el DELETE de
misión):

- **`GET /api/missions?matter_id={id}`** → `{missions: [Mission]}`. Misiones del asunto.
- **`POST /api/missions`** body `{matter_id, title, objective, outcome?, auto_decompose?}`
  → `Mission`. Con `auto_decompose` (default true) Mia **propone los hitos** al crear.
- **`POST /api/missions/{id}/decompose`** body `{replace?}` → `Mission`. Re-propone hitos
  (`replace:true` sustituye los actuales; `false` los añade al final).
- **`PUT /api/missions/{id}`** body `{title?, objective?, outcome?, status?}` → `Mission`.
  `status` ∈ `"active"` | `"archived"`.
- **`DELETE /api/missions/{id}`** → `{ok:true}`.
- **`POST /api/missions/{id}/milestones`** body `{title, detail?, actor?, is_procedural?}`
  → `Mission`. Añade un hito manual.
- **`PUT /api/missions/{id}/milestones/{milestoneId}`** body cualquiera de
  `{title?, detail?, actor?, status?, seq?, is_procedural?}` → `Mission`. Avanzar un hito =
  `status:"done"`; reordenar = `seq`.
- **`DELETE /api/missions/{id}/milestones/{milestoneId}`** → `Mission`.

Forma de `Mission`:
```
{ id, matter_id, title, objective, outcome, status,
  progress: { done, total },
  milestones: [ { id, seq, title, detail, actor, status, is_procedural } ] }
```

- **Sin jerga (§G) — traducciones para pantalla:**
  - `actor`: `"mia"` → **"Mia lo prepara"**; `"abogado"` → **"Lo haces tú"**.
  - `status` (hito): `"queued"` → **"Pendiente"**, `"active"` → **"En curso"**, `"done"` → **"Hecho"**.
  - `is_procedural: true` → mostrar un aviso claro tipo **"Toca un plazo — confírmalo tú
    [VERIFICAR]"**. NUNCA calcular ni sugerir una fecha.
  - `progress` → barra "X de Y hitos".
  - `matter_id` es un identificador interno para ligar la misión al asunto (como el id de la
    misión); no mostrarlo como texto al abogado.
- Errores de validación llegan **422** con `detail` en llano (mostrarlo tal cual): título
  vacío, tope de misiones/hitos, misión/hito inexistente, etc. Errores de servicio **502** en
  llano. **404** si la misión no existe.

### Comportamiento esperado

- Crear misión "Preparar la contestación" con objetivo → Mia devuelve 3-8 hitos propuestos
  (pendientes), algunos marcados "Mia lo prepara". El abogado los edita/aprueba y va marcando
  "Hecho"; la barra de progreso sube.
- Si Mia no logra proponer (modelo caído) → devuelve una **lista genérica de planeación**
  editable (el tablero nunca queda vacío). Consent-first: nada se ejecuta solo.
- El objetivo con palabras de plazo ("contestar dentro del término") → el hito correspondiente
  llega **marcado como procesal** para que el abogado confirme el plazo.

### Resultado de verificación (3 capas)

- Capa 1: 3 gates nuevos — `test_delegation.py` **11/11** (concurrencia acotada, orden
  estable, fail-soft, tope duro), `test_missions.py` **40/40** (descomposición con guarda
  procesal fail-closed; CRUD y topes bajo RLS; AISLAMIENTO entre despachos; propiedad del
  expediente), `test_research_swarm.py` **21/21** (1 jurisdicción = camino simple sin costo
  extra; ≥2 = swarm con verificación por rama + síntesis; fail-soft; degradación por tope;
  dedup). Regresión **ALL PASS (59 suites)** con `test_rls` HALT.
- Capa 2 (revisor adversarial independiente): confirmó correctos RLS/aislamiento, regla de
  plazos, §G, fail-soft y concurrencia de uso. 1 MAYOR (carrera sobre el compresor compartido
  en el swarm) + 2 MENORES (dedup de jurisdicciones; degradación por tope) **corregidos y
  re-verificados ANTES del commit**; 2 residuales aceptados (orden de hitos por desempate;
  `matter_id` expuesto a propósito). Ver `memory/progress.md` sesión 33.
- Capa 3: **COMPLETADO** — ver "Hallazgos de Cursor (capa 3)" · 2026-07-04 (CP-E5, commit `f47f143`).

---

## Checkpoint reciente: CP-E4 — Banco de pruebas de calidad (eval harness) (2026-07-03)

### Qué es (lenguaje simple)

- Una herramienta INTERNA para medir si un cambio en Mia **mejora o empeora** la calidad de
  sus análisis, ANTES de confiar en él. Corre a Mia sobre un set de **casos de prueba
  sintéticos** (inventados, sin datos reales de cliente) y puntúa cada resultado con señales
  **objetivas** (sin que otra IA juzgue): cuántas citas quedaron sin respaldo, si el
  diagnóstico trae su cierre estructurado, si produjo borrador. Luego compara "antes vs
  después" y da un veredicto en llano: **mejora / sin cambio / regresión**.
- **No toca datos reales de cliente:** los casos son sintéticos por construcción; correr el
  banco sobre expedientes reales del despacho exige autorización explícita (candado
  fail-closed) — hoy no hay ni pantalla ni caso que lo haga.

### Frontend (Cursor — capa 3): NO aplica

- CP-E4 es una herramienta de **desarrollo/administración por línea de comandos**
  (`execution/run_eval.py`), no una función del producto para el abogado. **No hay UI que
  construir ni revisar.** Un panel de calidad para el despacho podría venir en un checkpoint
  futuro, pero no es parte de este.

### Resultado de verificación (3 capas)

- Capa 1: gate `test_eval_harness.py` **25/25** (scorer determinista; comparador detecta
  regresión/mejora con veredicto fail-safe; casos todos sintéticos; candado de datos reales
  fail-closed; end-to-end por el grafo real con LLM/embeddings stubbeados, incl. que intake
  recupera el expediente sembrado); regresión **ALL PASS (56 suites)** (test_rls HALT).
- Capa 2 (revisor adversarial independiente): candado de datos reales y determinismo de las
  métricas CONFIRMADOS. 1 MAYOR corregido y re-verificado ANTES del commit: el runner sembraba
  los documentos SIN embedding → intake los ignoraba y Mia redactaba "a ciegas" (el banco no
  ejercitaba la recuperación del expediente) → ahora se siembran con embedding como en
  producción y el gate exige que intake recupere el documento. 2 MENORES aceptados (ver
  memory/bugs-and-risks.md Riesgo #51).
- Capa 3: NO APLICA (sin frontend).

---

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

## Checkpoint anterior: CP-E2 — Adjuntar pruebas por referencia (@expediente / @carpeta) (2026-07-03)

### Qué cambió (lenguaje simple)

- El abogado ya puede **traer evidencia a la conversación escribiéndola con `@`**: en el
  chat de un asunto o con Mia (Telegram/asistente) puede escribir `@expediente` (los
  documentos del asunto en curso), `@expediente:"Banco Popular vs Zurich"` (otro asunto
  del despacho, por su nombre) o `@carpeta:"Pruebas Zurich"` (una carpeta de trabajo
  registrada). Mia **expande la mención** e incorpora esa evidencia a su análisis del
  turno, sin que el abogado copie y pegue nada.
- Es donde más sirve **hablando con Mia libremente** (por Telegram o el asistente), que
  antes no traía documentos sola: ahora `@expediente:"..."` mete el expediente a la charla.
- **Privacidad primero:** una mención SOLO resuelve a expedientes y carpetas **del propio
  despacho** (nunca de otro), y **nunca abre un archivo del disco** — lee lo que Mia ya
  tiene indexado. Si el nombre no existe, está deshabilitado, o parece una ruta de
  computador, Mia lo dice en llano y no adjunta nada. Toda la evidencia entra **sellada**
  (Mia la trata como datos del caso, no como órdenes). Si el material referenciado es muy
  grande, se adjunta **recortado con aviso honesto** (nunca finge tener la prueba completa).

### Frontend (Cursor — capa 3): NO hay UI nueva

- CP-E2 es **sintaxis de mensaje** — el abogado escribe `@expediente`/`@carpeta` en el campo
  de chat que YA existe (asunto y, sobre todo, Telegram). No toca `frontend/`. **No hay nada
  que construir ni revisar** en la interfaz para este checkpoint.
- Trabajo FUTURO opcional (no de este checkpoint): un autocompletado que sugiera nombres de
  expedientes/carpetas al teclear `@` en el chat del asunto. Los datos ya existen
  (`GET /api/matters`, `GET /api/folders`). No es necesario para que la función trabaje hoy.
- Nota: sigue pendiente de Cursor el control del tope de gasto de **CP-E1** (ver abajo);
  ese trabajo NO se mezcló con CP-E2.

### Comportamiento esperado

- En un asunto: "Analiza @expediente a fondo" → Mia trabaja con los documentos del asunto
  (igual que antes, pero ahora explícito); "compara con @expediente:\"Otro caso\"" cruza con
  otro expediente del despacho. La búsqueda interna del turno usa el texto SIN la mención
  (no se ensucia con el documento adjunto).
- Con Mia libre (Telegram): "Según @expediente:\"Zurich\" ¿qué defensa tengo?" trae ese
  expediente a la respuesta. Nombre ambiguo o inexistente → aviso en llano, sin adjuntar.

### Resultado de verificación (3 capas)

- Capa 1: gate nuevo `test_context_references.py` **43/43** (parseo + denylist de rutas +
  resolución por título/etiqueta con RLS + AISLAMIENTO entre despachos + sellado
  anti-inyección + techo de tokens con recorte marcado + query de recuperación limpia);
  regresión **ALL PASS (54 suites)** (test_rls 12/12 HALT). Sin frontend web → sin npm build.
- Capa 2 (revisor adversarial independiente): confidencialidad/RLS, confinamiento a las
  filas del despacho (nunca disco), anti-inyección (CP-S1), escape LIKE y fail-open/closed
  CONFIRMADOS. 2 MAYORES (fetch sin LIMIT en SQL → tope de recursos; techo de tokens en el
  listado de carpeta → presupuestado por archivo) + 2 MENORES (`@expedientes` plural;
  query solo-referencia) corregidos y RE-VERIFICADOS CERRADOS antes del commit. Ver
  memory/progress.md sesión 31.
- Capa 3: NO APLICA (sin frontend en este checkpoint).

---

## Checkpoint anterior: CP-E1 — Auditoría de acciones + tope de gasto de IA (2026-07-03)

### Qué cambió (lenguaje simple)

- **Registro de auditoría:** Mia ahora deja rastro de cada acción del despacho
  (quién hizo qué y cuándo) en un registro interno append-only, por despacho. Es
  invisible y no cambia nada de la experiencia; sirve para cumplimiento/confianza
  al vender a firmas grandes. Guarda solo metadatos (acción, ruta, ids, resultado)
  — NUNCA el texto de la consulta ni el contenido del expediente.
- **Tope de gasto de IA:** el despacho puede fijar un presupuesto MENSUAL en dólares.
  Al alcanzarlo, los turnos nuevos se pausan con un aviso en llano hasta que el
  abogado suba el tope o llegue el mes siguiente. Antes solo se MEDÍA el gasto
  (tarjeta "Valor entregado"); ahora se puede LIMITAR.

### Frontend a construir (Cursor — capa 3): control del tope en el Panel

- **`GET /api/policy/budget`** → `{monthly_budget_usd, spent_this_month_usd,
  remaining_usd, over_budget, unlimited}`. `monthly_budget_usd`/`remaining_usd` son
  null cuando es ilimitado (`unlimited: true`).
- **`PUT /api/policy/budget`** body `{"monthly_budget_usd": 100}` (o `null`/0 para
  quitar el tope) → devuelve el estado ya actualizado.
- Sugerencia de UI: en el Panel de control, junto a "Valor entregado este mes",
  un control "Tope de gasto de IA este mes" — input en USD + "Sin límite"; mostrar
  gasto del mes y restante; si `over_budget`, un aviso ámbar "Se alcanzó el tope;
  los turnos están en pausa". Estado vacío/ilimitado en llano.
- El REGISTRO de auditoría es backend-only por ahora (no requiere pantalla); una
  vista "Registro de actividad" es trabajo futuro opcional.

### Comportamiento esperado

- Con tope fijado y gasto por debajo: todo igual. Al superarlo, un asunto o el
  asistente responden **402** con el aviso en llano (mostrar el `detail` tal cual).
- El dictado por voz NO cuenta como "acción" en el registro (alta frecuencia).

### Resultado de verificación (3 capas)

- Capa 1: gate nuevo `test_observability.py` **22/22** (auditoría RLS + fail-open +
  recorte de campos; tope: roundtrip incl. rama de producción, suma del mes UTC,
  bloqueo/permiso, fail-open); regresión **ALL PASS (53 suites)** (test_rls HALT).
  Sin frontend web tocado → sin npm build.
- Capa 2 (revisor adversarial): confidencialidad (sin fuga del mensaje a
  audit_logs — se guarda solo el path, no el query string), aislamiento RLS,
  fail-open y no-regresión del curador CONFIRMADOS. 1 BLOQUEANTE (el tope no
  persistía sobre la fila tenant_settings que todo tenant ya tiene → jsonb_set
  corregido) + 1 MENOR (borde de mes corrido 5h por la zona del servidor)
  corregidos ANTES del commit y re-verificados. Ver memory/progress.md sesión 30.
- Capa 3: COMPLETADO — ver "Hallazgos de Cursor (capa 3)" · 2026-07-04 (CP-E1).

---

## Checkpoint anterior: CP-Z2 — Conversación por voz en Telegram (2026-07-03)

### Qué cambió (lenguaje simple)

- **Mia ya habla.** Si el abogado le manda una NOTA DE VOZ a su bot privado de
  Telegram, Mia la transcribe (en el servidor del despacho, el audio nunca sale de
  ahí), responde, y le devuelve una NOTA DE VOZ hablada. Es el "asistente personal
  en el celular": le hablas y te contesta hablando.
- Regla de modalidad: **voz entra → voz sale; texto entra → texto sale** (el chat
  de texto por Telegram no cambia). Al recibir voz, Mia primero devuelve por
  escrito lo que ENTENDIÓ (para que el abogado verifique la transcripción) y luego
  la nota de voz de la respuesta.
- Respuestas largas (un borrador) siguen yendo por escrito; solo las respuestas
  conversacionales cortas se dicen habladas.

### Frontend (Cursor — capa 3): NO hay UI web nueva

- CP-Z2 vive 100% en el **canal de Telegram** (backend). No toca `frontend/`. El
  asistente conversacional de Mia no tiene pantalla web (es Telegram), así que no
  hay nada que construir ni revisar en la interfaz. El motor de voz de salida
  (`/api/speech/synthesize`, ver abajo) queda **reutilizable** para un futuro botón
  "Escuchar" en la web, pero eso NO es parte de este checkpoint.
- **La capa 3 de este checkpoint la hace Pipe en vivo:** crear el bot de Telegram
  (guía `docs/telegram-setup.md`), instalar la voz desde el Panel (botón "Instalar
  dictado por voz", que ahora también baja el modelo de voz de salida), y **dictar
  una nota de voz real** para oír a Mia responder hablando.

### Endpoint nuevo (por si la web lo usa después)

- **`POST /api/speech/synthesize`** (auth como todo /api/*): body `{"text": "..."}`
  → responde audio **OGG/Opus** (`audio/ogg`), 100% local. Errores en llano: 400
  (texto vacío), 413 (muy largo), 429 (rate-limit), 503 (voz no instalada u
  ocupada), 403 (motor de nube sin opt-in — hoy no aplica, es local).

### Resultado de verificación (3 capas)

- Capa 1: gate nuevo `test_speech_tts.py` **26/26** (síntesis local, códec Opus
  round-trip, candado de privacidad, 503 al estar ocupado, rate-limit);
  `test_telegram_bridge.py` extendido **37/37** (bucle de voz completo, modalidad,
  degradación a texto si el TTS falla, reply vacío, chat no autorizado);
  `test_speech_stt.py` **60/60** (instalación ahora incluye el modelo de voz);
  regresión completa **ALL PASS (52 suites)** (test_rls HALT). Sin `npm build`
  (no hay frontend web).
- Capa 2 (revisor adversarial independiente): confidencialidad, autorización,
  modalidad, instalación y concurrencia CONFIRMADOS; 1 MAYOR (espera del semáforo
  sin tope → 503 explícito) + 2 MENORES (reply vacío, guardia de tamaño) CERRADOS
  antes del commit. Ver memory/progress.md sesión 30.
- Capa 3: PENDIENTE — Pipe dicta una nota de voz real (lo único que la
  verificación automatizada no cubre).

---

## Checkpoint anterior: CP-Z1b — La voz instalada en el producto (2026-07-03)

### Qué cambió (lenguaje simple)

- El dictado por voz ya se instala DESDE LA PANTALLA: tarjeta nueva "Dictado
  por voz" en el Panel de control (sección Conectores) con botón "Instalar
  dictado por voz", confirmación explícita en ámbar, barra de avance de la
  descarga (~700 MB) y mensajes del servidor en llano. Ya no hace falta que un
  administrador corra un script.
- El recorrido "Configura a Mia" tiene el paso 7 "Dictado por voz" (detección
  automática + guía explicativa; "Ir al paso" lleva al Panel).
- El chat del asunto ya tiene el BOTÓN DE MICRÓFONO: dictas, Mia transcribe en
  el servidor del despacho (la voz nunca sale de ahí) e inserta el texto en el
  campo sin borrar lo escrito. Este botón lo construyó Claude Code — Cursor
  hace la revisión visual (capa 3), no la construcción.

### Endpoints para la UI (ya construida — revisar, no construir)

- **`GET /api/speech/status`** → `{estado, listo, mensaje, progreso}` donde
  `estado` ∈ instalado | no_instalado | descargando | error; `progreso` (solo
  descargando) = `{fase, descargado_mb, total_mb, porcentaje}` (total/porcentaje
  pueden ser null si el servidor de descarga no anuncia el tamaño).
- **`POST /api/speech/install`** body `{"confirmar": true}` → `{status, message}`.
  Sin confirmación → 400 con `detail` en llano (mostrarlo tal cual).
- **`POST /api/speech/transcribe`** (de CP-Z1): multipart `audio` WAV PCM16 16k
  + `pulir`; responde `{text, cleaned_text, duration_seconds, message}`.

### Qué revisar visualmente (Cursor — capa 3)

1. **`frontend/app/dashboard/page.tsx` · tarjeta "Dictado por voz"**: estados
   Inactivo / Instalando… (barra `role="progressbar"` con MB) / Instalado;
   confirmación `role="alertdialog"` antes de descargar; Cancelar no descarga;
   tras un error el botón reaparece con el mensaje en ámbar; el refresco es
   automático cada 2 s SOLO mientras descarga.
2. **`frontend/app/configurar/page.tsx`**: el paso 7 "Dictado por voz" se pinta
   con su guía expandible (el contenido viene del servidor — no requirió cambios
   en esta página; verificar que el acordeón y el progreso "N de 7" se vean bien).
3. **Micrófono** (`frontend/app/_components/MicButton.tsx`,
   `frontend/lib/useDictation.ts`, `frontend/lib/wav.ts`, integrado en
   `frontend/app/asuntos/[id]/page.tsx`): estados inactivo → grabando (pulso
   rojo + "Dictando… toca para terminar") → transcribiendo (spinner "Mia está
   escribiendo tu dictado…"); `aria-pressed` alterna; el permiso de micrófono se
   pide solo al primer clic; los errores del backend (400/413/429/503) y el
   aviso "No se escuchó voz en la grabación." salen en ámbar bajo el campo;
   PROBAR CON MICRÓFONO REAL dictando en español (lo único que la verificación
   automatizada no pudo cubrir).

### Comportamiento esperado

- Instalar desde la tarjeta: confirmar → "Empecé a descargar…" → barra avanza →
  la tarjeta pasa sola a "Instalado" (verificado en vivo con descarga real).
- Dictar un clip corto → el texto aparece en el campo en ~1-3 s, agregado al
  final de lo ya escrito. Un clip en silencio → aviso honesto en ámbar.
- Ningún texto visible trae jerga técnica.

### Resultado de verificación (3 capas)

- Capa 1: gate `test_speech_stt.py` extendido 41 → **57/57** (instalador:
  consent-first, single-flight, progreso, retry limpio, tar malicioso rechazado,
  idempotencia — sin descargar los pesos reales); `test_setup_wizard.py`
  **30/30** (7 pasos); regresión completa **ALL PASS (51 suites)**; `npm run
  build` verde ×2; verificación EN VIVO por navegador: tarjeta en sus 3 estados,
  confirmación/cancelar, instalación real (descarga del detector de voz desde
  internet), paso 7 del wizard, botón de micrófono con aria correcta, y POST
  multipart navegador→API con WAV real (CORS OK).
- Capa 2 (revisor adversarial independiente): ver memory/progress.md sesión 29.
- Capa 3 (Cursor): PENDIENTE — revisar lo listado arriba (en especial dictar
  con micrófono real).

---

## Checkpoint anterior: CP-Z1 — Dictado local (voz a texto) (2026-07-02)

### Qué cambió (lenguaje simple)

- Mia ya puede transcribir la voz del abogado SIN que el audio salga de su
  servidor: un nuevo servicio de dictado 100% local (mismo motor y parámetros
  que Lexter, el dictado que Pipe ya usa y validó en español jurídico).
- El backend está completo y probado; falta el botón de micrófono en la web
  (este HANDOFF). Opcionalmente, Mia puede "pulir" la puntuación del dictado
  con su modelo local (si Ollama está corriendo); si no, entrega el texto crudo.
- Si el servidor no tiene el modelo de voz descargado, el botón debe explicar
  en llano lo que el backend responde (503 con instrucción para el administrador).

### Frontend a construir (Cursor — capa 3): botón de micrófono

- **`POST /api/speech/transcribe`** (multipart/form-data, requiere Authorization
  como todo /api/*):
  - campo `audio`: archivo WAV PCM16 **16 kHz mono** (el navegador debe
    re-muestrear antes de enviar — ver nota técnica), máx. 5 minutos / 32 MB.
  - campo opcional `pulir`: `"true"` para pedir la corrección de puntuación con
    el modelo local (fail-soft: puede volver null).
  - Respuesta: `{text, cleaned_text, duration_seconds, message}` — `text` es la
    transcripción cruda; `cleaned_text` la versión pulida o null; `message`
    solo viene cuando no se escuchó voz ("No se escuchó voz en la grabación.").
  - Errores en llano listos para pantalla: 400 (audio ilegible), 413 (muy
    grande), 429 (demasiados clips seguidos), 503 (dictado no instalado en el
    servidor) — mostrar el `detail` tal cual (lib/api.ts ya lo propaga).
- **Nota técnica de captura:** `MediaRecorder` produce webm/opus, que el backend
  NO acepta. Capturar con Web Audio API (`AudioContext` + `MediaStreamSource`),
  acumular Float32, re-muestrear a 16 kHz mono (p. ej. `OfflineAudioContext`) y
  empaquetar WAV PCM16 en el cliente (~30 líneas; sin librerías externas).
- **UI sugerida:** botón 🎤 junto al campo de texto del asunto y del asistente;
  estados: inactivo → grabando (pulso rojo + "Dictando… toca para terminar") →
  transcribiendo (spinner "Mia está escribiendo tu dictado…") → texto insertado
  en el campo (usar `cleaned_text ?? text`). Si `message` viene, mostrarlo en
  ámbar. Accesibilidad: `aria-pressed` en el botón, estado comunicado con texto
  además del color. Pedir permiso de micrófono solo al primer clic.
- Referencia de diseño (OpenJarvis, en disco): `jarvis-ref/OpenJarvis-main/
  frontend/hooks/useSpeech.ts` y `components/Chat/MicButton.tsx`.

### Comportamiento esperado

- Dictar un clip corto en español → el texto aparece en el campo en ~1-3 s
  (motor local, sin GPU). Clips largos (hasta 5 min) tardan más y llegan
  completos. Un clip en silencio → aviso honesto, no texto inventado.
- El audio JAMÁS sale del servidor: no hay que pedir consentimiento de nube.

### Resultado de verificación (3 capas)

- Capa 1: gate nuevo `test_speech_stt.py` 35/35 (incluye integración real con
  el modelo descargado: español correcto y audio de 76 s por el camino VAD);
  regresión completa en verde (test_rls HALT).
- Capa 2 (revisor adversarial independiente): ver memory/progress.md sesión 28.
- Capa 3 (Cursor): PENDIENTE — construir el botón descrito arriba.

---

## Checkpoint anterior: CP-V2 — Auto-diagnóstico prescriptivo (2026-07-02)

### Qué cambió (lenguaje simple)

- La consolidación semanal de Mia ahora produce un DIAGNÓSTICO con hasta 4
  recomendaciones concretas para el despacho ("Ha corregido 6 veces respuestas
  del mismo tipo — suba su guía de trabajo y desaparecen"), cada una con
  evidencia real contada de la actividad (nunca inventada: con menos de 5
  eventos de señal, Mia calla), impacto en dólares según la tarifa del
  despacho, y puntaje que las ordena.
- Lo que el abogado acepta o descarta NO se le vuelve a mostrar, salvo que el
  problema siga vivo pasados 30 días (entonces vuelve marcado como recurrente).
- El reporte semanal menciona cuántas recomendaciones hay y la principal.

### Frontend a construir (Cursor — capa 3): tarjetas de diagnóstico en el panel

- **`GET /api/dreams/prescriptions`** → `{prescriptions: [...]}` ordenadas por
  impacto (máx. 4). Campos por tarjeta: `id`, `category` (retrabajo | rechazos |
  conocimiento | costo | guias | valor), `headline` (título en llano),
  `prescription` (la receta, 3-4 frases), `evidence` (lista de 3 pruebas con
  números reales), `dollar_impact` (USD/mes o null), `time_impact_mins` (o
  null), `status` (`new` | `recurring`), `age_days`.
- **`POST /api/dreams/prescriptions/{id}/decision`** con body
  `{"action": "accept"}` o `{"action": "dismiss"}` → la tarjeta desaparece.
  404 si ya fue decidida (refrescar la lista).
- Sugerencia de UI: sección "Recomendaciones de Mia" en el Panel de control
  (encima o junto a "Valor entregado"); tarjeta con headline + impacto,
  evidencia expandible, botones "Lo haré" (accept) y "Descartar" (dismiss).
  `recurring` con `age_days` alto merece un matiz visual ("lleva N días").
- Estado vacío en llano: "Mia aún no tiene recomendaciones — necesita más
  actividad para hablar con evidencia."
- OJO: las tarjetas reflejan la última consolidación semanal (no tiempo real).

### Resultado de verificación (3 capas)

- Capa 1: gate `test_dreams.py` extendido 16 → **43/43**; regresión completa
  **50/50 suites × 3 corridas** (test_rls 12/12 HALT); migración 022 aplicada
  e idempotente.
- Capa 2 (revisor adversarial independiente): APROBAR tras re-verificación —
  los 4 MAYORES corregidos antes del commit: (H1) una decisión del abogado
  tomada mientras corría el cron semanal podía perderse → el guardado ya nunca
  resetea una fila decidida (solo el resurgimiento explícito a los 30 días);
  (H2) la poda borraba la edad de problemas vivos que solo salieron del top
  por diversidad → ahora se conserva toda señal viva y el panel filtra;
  (H3/H4) la recomendación de costo v1 era imposible de ejecutar (proponía
  mover tareas que YA corren en el modelo económico, hacia una pantalla sin
  ese control) → rediseñada al gasto real pagado + el selector "Motor de IA"
  del Panel de control, verificado que existe y guarda. Menores H5-H7 y
  residuales R1/R2 también cerrados (Riesgo #44).
- Capa 3: COMPLETADO — ver "Hallazgos de Cursor (capa 3)" · 2026-07-04 (CP-V2).

---

## Checkpoint anterior: CP-C4b — "Configura a Mia" como onboarding explicativo (2026-07-02)

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
