# Handoff Capa 3 — deuda visual pendiente (consolidado para Cursor)

> Proyecto Mia · Lexia Intelligence · rama claude/arranque-fptz34
> Consolida la Capa 3 (revisión visual en vivo) acumulada en 6 superficies del frontend.
> Estándar estético vigente: sesión 44 (`frontend/app/_welcome/` — fondo aurora teal sobre #060606, marca que respira, una pregunta a la vez, framer-motion).

---

## Como usar este archivo
- Es el brief único de TODO lo visual pendiente para Cursor: recorre superficie por superficie, aplica los arreglos y usa la tabla priorizada del final para decidir el orden.
- Cada arreglo viene clasificado como **SEGURO-mecanico** (se puede aplicar sin ver la pantalla: jerga §G, labels/aria faltantes, bugs de lógica) o **NECESITA-VISUAL** (requiere que Pipe o Cursor lo vean: estética, contraste, consistencia, decisiones de copy).
- Al terminar cada superficie, Cursor anota aquí sus hallazgos en vivo (bloque "Hallazgos detectados") y marca qué quedó hecho.

---

## Resumen para Pipe (6 lineas)
Son 6 pantallas grandes ya construidas y con la conexión con el motor de Mia verificada; ninguna está rota, todo lo pendiente es pulido de acabado, accesibilidad y limpieza de lenguaje.
Falta recorrer visualmente las 6: la Bienvenida (sesión 44) ya es el estándar bonito y solo necesita retoques; las otras cinco todavía no adoptaron ese acabado.
Hay 71 detalles en total; 38 se pueden arreglar a ciegas (etiquetas invisibles para lectores de pantalla, textos con palabra técnica, un par de fallas de lógica) y 33 hay que verlos en pantalla (colores, contraste, consistencia, decisiones de nombre).
Las tres pantallas con más deuda son "Diagnóstico y Misión", "Proyectos y Fuentes" y "Guías y conocimiento".
Hay dos arreglos de peso: en el Diagnóstico las citas y datos de plazos deben verse marcados "[VERIFICAR]" como en la revisión del borrador, y al conectar el correo el abogado hoy aterriza en la pestaña equivocada y no ve el mensaje de "cuenta conectada".
Ninguna corrección cambia el contrato con el backend: es todo acabado sobre pantallas que ya funcionan.

---

## Superficie: Bienvenida (sesión 44) — crear despacho → activar → onboarding → celebración

**Archivos:** `frontend/app/register/page.tsx`, `login/page.tsx`, `activar/page.tsx`, `onboarding/page.tsx`, `frontend/app/_welcome/*` (WelcomeShell, WelcomeProgress, BrandMark, MiaLine, Celebration, MotionField, WelcomeField, motion.ts, index.ts), `frontend/app/_components/CountrySelector.tsx`. Backend: `backend/mia/api/routes/welcome.py`, `ux.py`, `settings.py`, `auth.py`.

**Que revisar (cursor_brief):** Es el nuevo estándar visual — register → activar → onboarding → celebración montado sobre `_welcome` (WelcomeShell con aurora teal, constelación de 4 pasos, BrandMark que respira, MiaLine máquina de escribir, Celebration a pantalla completa). El wiring está verificado. **TRAMPA DE REVISIÓN:** `/activar` se AUTO-SALTA a `/onboarding` cuando el status trae `instalado:false` (modo dev) o cuando no falta ninguna clave; en `npm run dev` sobre Linux casi siempre se saltará. Para verla hay que mockear `GET /api/welcome/status` con `{instalado:true, hay_usuario:true, faltan_llaves:{busqueda:true,respaldo:true}, motor_detectado:{claude:false,ollama:false}, politica:'suscripcion'}` y probar el sub-flujo motor→búsqueda→respaldo en las tres políticas (suscripcion/soberano dejan "Omitir"; "nube" no). Arreglar: (1) aria-label en TagInput y botones "quitar tag"; (2) §G del `<details>` que vuelca `soul_content` crudo; (3) contraste de textos muted/70 y /80 sobre #060606; (4) unificar onboarding sobre `WelcomeField`/`font-display`. Confirmar con Pipe que "En la nube" = clave Anthropic.

**Comportamiento esperado:** Riesgo #60 CONFIRMADO OK — en política "nube" la clave de respaldo del motor es OBLIGATORIA ("Terminar y continuar" deshabilitado hasta validar, "Omitir" oculto) y el aviso fuerte "cierra Mia y vuélvela a abrir" se muestra prominente en "Listo" porque el backend devuelve `aviso` al guardar `respaldo`/`openrouter`. Validación en vivo de claves con ✓/spinner/✗ y debounce 700 ms.

**Endpoints reales (verificados):** `POST /api/auth/register` y `/login` → `{token, tenant_id}` (auth.py:158,193); `GET /api/welcome/status` (welcome.py:159); `POST /api/welcome/keys` → `{guardado,mensaje,aviso}` (welcome.py:216); `POST /api/welcome/keys/test` → `{ok,motivo?}` (welcome.py:325); `PUT /api/settings/model-policy` valida `'suscripcion'|'nube'|'soberano'` (settings.py:97-114); `GET /api/onboarding/questions|status`, `POST /draft|/complete`, `GET /api/jurisdictions` (ux.py:1359,1421-1489).

**Hallazgos detectados:**
- §G — `onboarding/page.tsx:324-330`: el `<details>` "Ver el perfil completo que guardé" vuelca `completion.soul_content` crudo en un `<pre>`; el SOUL.md técnico puede exponer nombres de campo/estructura interna (p. ej. `jurisdiction.base`). Verificar que `interview.run_interview()` no emita jerga; si lo hace, ocultar o traducir. (NECESITA-VISUAL)
- §G — `onboarding/page.tsx:97,519,527`: el wizard pinta `current.question`/`current.example` directo del backend; la limpieza depende de `SoulInterview().get_questions()` — revisar ese texto fuente. (NECESITA-VISUAL)
- Accesibilidad — `onboarding/page.tsx:907-920` (TagInput p3/p6/p7 y "Otra herramienta"): el `<input>` no tiene `<label>`/aria-label/id; añadir aria-label llano ("Escribe un rasgo de estilo"). (SEGURO-mecanico)
- Accesibilidad — `onboarding/page.tsx:893-901` y `825-833`: botones de quitar tag/herramienta usan `{tag} ×` sin aria-label (se leen "×/equis"); poner `aria-label={`Quitar ${tag}`}`. (SEGURO-mecanico)
- Accesibilidad — `activar/page.tsx:590,646`: el `hint` de WelcomeField no está enlazado al input vía `aria-describedby`; añadir id + aria-describedby en KeyField. (SEGURO-mecanico)
- Accesibilidad — contraste de `text-muted-foreground/70` y `/80` sobre #060606 ("Opcional — puedes saltarla" onboarding:530, "Toma unos 3 minutos" :433, sub-progreso :497); riesgo WCAG AA. (NECESITA-VISUAL)
- Accesibilidad — `CountrySelector.tsx:56-84`: 21 checkboxes de país sin `<fieldset>`/`role="group"` con la pregunta como nombre accesible. (SEGURO-mecanico)
- Wiring — el campo `openrouter` de KeysBody (welcome.py:206) NUNCA se envía desde `/activar`; "En la nube" mapea a `respaldo`→ANTHROPIC. Confirmar con Pipe si "nube" = Anthropic directo es lo deseado. (NECESITA-VISUAL)
- Consistencia — `onboarding` define su propio `<Field>` (:756-763, `text-xs text-muted-foreground`) en vez de `WelcomeField` (`text-sm font-medium text-foreground`) que usan register/login/activar. Unificar o documentar excepción. (NECESITA-VISUAL)
- Consistencia — MiaLine recibe `font-semibold` en onboarding (:291,313,367,420,520) que pisa `font-display`; tratamiento tipográfico inconsistente de la voz de Mia. (NECESITA-VISUAL)
- Consistencia — inputs de pregunta del onboarding en un solo `<StaggerItem>` (:534); escalonado más pobre que el resto. Cosmético. (NECESITA-VISUAL)
- Nota positiva — el resto del sistema es CONSISTENTE (WelcomeShell, JOURNEY_STEPS con índices coherentes register=0/activar=1/onboarding=2/final=3, login sin progreso a propósito, BrandMark, MiaLine, Celebration, `prefers-reduced-motion` respetado).

---

## Superficie: Proyectos y Fuentes (sesión 39) — workspace libre estilo Cowork

**Archivos:** `frontend/app/proyectos/page.tsx`, `proyectos/[id]/page.tsx`, `frontend/app/_components/FuentesPanel.tsx`, `FolderPicker.tsx`, `MatterDriveFolder.tsx`.

**Que revisar (cursor_brief):** Lista/creación en dos pasos de Proyectos, workspace de 3 columnas (Fuentes · chat con Mia · Archivos) y panel unificado de Fuentes multi-carpeta con salida .docx. Cableado sólido y verificado; sin endpoints rotos ni botones sin handler. Foco Capa 3 por prioridad: (1) accesibilidad — aria-live/role=status a las tres zonas de estado dinámico (línea de estado del chat, saveNotice/downloadError, banner de FuentesPanel) y aria-label al `<textarea>` del chat; (2) estado de error silencioso (`setState([])` = vacío) y error duplicado del stream; (3) consistencia con `_welcome` (migrar animaciones CSS a `motion.ts`, usar BrandMark como avatar de Mia); (4) limpieza §G (borrar `MatterDriveFolder` huérfano, decidir "OneDrive", mostrar `documentos`).

**Comportamiento esperado:** Sin cambios de contrato con backend — es pulido de accesibilidad, estados de error y coherencia estética; NO tocar endpoints ni contrato SSE. El chat de proyecto emite solo `thinking`/`reply`/`error` (sin `awaiting_review`/`draft_ready`; eso es exclusivo del flujo de asunto/HITL).

**Endpoints reales (verificados):** `GET /api/matters?kind=proyecto` (ux.py:137), `POST /api/matters` (ux.py:156), `GET /api/matters/{id}` (ux.py:170, redirige a /asuntos si kind≠proyecto), `GET /api/matters/{id}/sources` (matter_sources.py:170), `POST+sync+DELETE /api/matters/{id}/folders[/{id}]` (matter_folders.py:146/181/204), `POST/DELETE /api/drive/sources/{id}[/sync]` (remote_drive.py:139/167/181), `GET /api/folders/browse` (folders.py:72), `POST/GET /api/matters/{id}/outputs` y `GET …/{id}.docx` (ux.py:255/298/313, guard 422 si no es proyecto), `POST /api/matters/{id}/chat` → stream_url y `GET /stream` (ux.py:354/362 → stream.py:209).

**Hallazgos detectados:**
- §G — `MatterDriveFolder.tsx:197,131`: "Sincronizar ahora" / "No se pudo sincronizar la carpeta" es jerga; además el archivo quedó HUÉRFANO (sin imports tras la unificación en FuentesPanel, que ya usa "Revisar ahora"). Borrarlo. (SEGURO-mecanico)
- §G — "OneDrive" visible en `FuentesPanel.tsx:387` y MatterDriveFolder; nombre de producto borderline. Decidir con Pipe si se mantiene o se neutraliza a "carpeta en la nube". (NECESITA-VISUAL)
- Info descartada — el tipo `Fuente` trae `documentos: number` del backend pero nunca se muestra el conteo; considerar mostrarlo. (NECESITA-VISUAL)
- Accesibilidad — `proyectos/[id]/page.tsx:314`: la línea de estado del chat es un `<div>` sin `role="status"`/`aria-live="polite"`; no anuncia que Mia piensa/termina/falla. (SEGURO-mecanico)
- Accesibilidad — `proyectos/[id]/page.tsx:316-328`: el `<textarea>` solo tiene placeholder; añadir `aria-label="Escribe tu consulta"`. (SEGURO-mecanico)
- Accesibilidad — `proyectos/[id]/page.tsx:351,356`: saveNotice/downloadError sin aria-live; envolver en contenedor `aria-live="polite"`. (SEGURO-mecanico)
- Accesibilidad — `FuentesPanel.tsx:262` (banner éxito/error), `:359` (msgs por-fuente) y `:285` (loadError) sin role=status/aria-live. (SEGURO-mecanico)
- Accesibilidad — contraste de metadatos en `text-xs text-muted-foreground` sobre `bg-card/40` (FuentesPanel:355-357, proyectos/[id]:377); revisar WCAG AA. (NECESITA-VISUAL)
- Wiring — `proyectos/page.tsx:63` y `proyectos/[id]:97`: el catch hace `setState([])`; un fallo de red es indistinguible de "aún no hay". Añadir estado de error de carga diferenciado. (NECESITA-VISUAL)
- Wiring — `proyectos/[id]/page.tsx:152-159`: en el evento `error` se hace `setStatus(mensaje)` Y se reemplaza el último mensaje de Mia con el mismo texto → error duplicado. Dejar uno. (SEGURO-mecanico)
- Consistencia — la superficie usa Tailwind CSS ad-hoc (`animate-slide-up`, `animate-message-in`, delay manual `${i*45}ms` en page.tsx:154) en vez del lenguaje framer-motion de `_welcome/motion.ts` (stepVariants, staggerContainer, MIA_EASE). Migrar. (NECESITA-VISUAL)
- Consistencia — el avatar de Mia en el chat (proyectos/[id]:283) es un círculo + icono Sparkles, no la BrandMark que respira. (NECESITA-VISUAL)
- Consistencia — no hay puente visual (acento aurora/verde `--cta`) entre esta superficie plana y la estética cinematográfica de `_welcome`. (NECESITA-VISUAL)
- Nota positiva — teclado base bien: Radix Dialog/DropdownMenu, Enter envía/Shift+Enter salta línea, FolderPicker con `<nav aria-label>` y `role="alert"`, botón Descargar con aria-label. El hueco real es aria-live.

---

## Superficie: Guías y conocimiento (sesión 40) — pestaña, wizard "Crear con Mia", historial de versiones

**Archivos:** `frontend/app/memoria/page.tsx`, `frontend/app/_components/GuideInterviewWizard.tsx`, `personas/page.tsx`, `configurar/page.tsx`, `asuntos/[id]/page.tsx`. Backend: `ux.py`, `guides.py`, `curator.py`, `personas.py`, `learning.py`.

**Que revisar (cursor_brief):** Página "Conocimiento" con 4 subtabs (Mi despacho / Criterios aprendidos / Guías y habilidades / Mejoras que Mia propone), wizard compartido `GuideInterviewWizard` (kind=guia|agente), "Convertir en guía" en `asuntos/[id]`, agentes jurídicos en `personas`. (1) BUG de wiring del "drift" del curador; (2) estados de error ausentes en crear/corregir/restaurar/aplicar; (3) accesibilidad del wizard (aria-live en pregunta+spinner, role=alert en errores, Label del ChipsField); (4) §G del `<Badge>{p.type}</Badge>` con fallback al slug crudo; (5) consistencia — el wizard "una pregunta a la vez" es el candidato natural a adoptar stepVariants/MIA_EASE. El gate HITL está bien (nada se guarda hasta "Guardar"); NO tocar ese copy.

**Comportamiento esperado:** Al corregir el 409 debe verse "El conocimiento cambió desde que se generó…" (no el genérico) al aprobar una propuesta obsoleta del curador. Ningún borrador (guía o agente) se persiste hasta que el abogado pulsa Guardar.

**Endpoints reales (verificados y montados):** `POST /api/guides/interview` (guides.py:106, stateless, manda transcript completo); `GET/POST /api/playbooks` (?status=todos; origin manual|entrevista|asunto), `GET/{id}`, `PUT`, `/archive`, `/restore`, `/versions`, `/versions/{id}/restore`, `/import` (ux.py:690-915); `GET /api/skills/ranked` (ux.py:1352); `GET/POST/PUT/DELETE /api/personas` (personas.py, prefix /api en main.py:190); `GET /api/proposals`, `POST /apply` (body opcional `{content,title}`), `/ignore` (ux.py:1011-1168); `GET /api/curator/proposals`, `/approve`, `/reject` (409 = drift); `POST /api/learning/run` (learning.py:32); `GET /api/dreams/report` (ux.py:1283); `GET /api/wiki/concepts`, `/{name}`, `POST /{name}/feedback` (ux.py:1251-1270).

**Hallazgos detectados:**
- Wiring (BUG) — `memoria/page.tsx:812`: `curatorAct` usa `e instanceof Error && e.message.includes('409')`, pero `ApiError.message` es el detail en español (curator.py:58), no "409" (el status vive en `e.status`). El mensaje de drift NUNCA se muestra. Corregir a `e instanceof ApiError && e.status === 409`. (SEGURO-mecanico)
- §G (defensa en profundidad) — `memoria/page.tsx:910`: `<Badge>{p.type}</Badge>` pinta el `type` que YA viene etiquetado del backend — `ux.py:1029` aplica `_PROPOSAL_LABEL.get(...)` sobre el mapa de `ux.py:61-67`, donde los CINCO tipos vigentes (`improve_playbook`, `new_playbook`, `flag_gap`, `wiki_correction`, `weekly_report`) SÍ están traducidos al español. HOY NO hay fuga: los tres tipos que antes se citaban (`flag_gap`/`wiki_correction`/`improve_playbook`) renderizan texto limpio ("Brecha de conocimiento", etc.), no el slug. El único riesgo es un `proposal_type` FUTURO que el backend agregue sin etiqueta; añadir un fallback llano en el front por si eso pasa. (SEGURO-mecanico)
- §G — `memoria/page.tsx:68` y `configurar/page.tsx:487-490`: "Guías y habilidades" / "Habilidades activas/archivadas" / "Conceptos" es vocabulario del segundo cerebro (skill/skill_id/approval_rate). Decidir con Pipe si se renombra (p. ej. "Guías que Mia domina") o se queda. (NECESITA-VISUAL)
- Wiring — `memoria/page.tsx:300-312` (create manual) y `:121-125` (Wiki sendCorrection): sin manejo de error; si el POST falla el modal queda abierto sin mensaje. Añadir try/catch con estado de error visible (patrón role=alert de personas). (SEGURO-mecanico)
- Wiring — `memoria/page.tsx:439` (restoreVersion) y `:778` (act apply/ignore): usan `.catch(() => {})` silencioso; el abogado cree que funcionó. Añadir estado de error. (SEGURO-mecanico)
- Accesibilidad — `GuideInterviewWizard.tsx:174-212`: el bloque de pregunta y "Mia está pensando…" sin aria-live; añadir `role="status" aria-live="polite"`. (SEGURO-mecanico)
- Accesibilidad — `GuideInterviewWizard.tsx:214` y `memoria/page.tsx:674`: errores en `<p className="text-sm text-destructive">` sin `role="alert"` (personas:264-266 sí lo tiene — replicar). (SEGURO-mecanico)
- Accesibilidad — `personas/page.tsx:562-600` (ChipsField): `<Label>` de "Áreas de énfasis" y "Frases con las que la llamas" sin `htmlFor`/`id`; input sin nombre accesible. Asociar. (SEGURO-mecanico)
- Accesibilidad — `GuideInterviewWizard.tsx:201-206`: enviar solo con Cmd/Ctrl+Enter sin pista visible (el botón "Continuar" existe :220). Añadir hint "Ctrl+Enter para continuar". (SEGURO-mecanico)
- Accesibilidad — `memoria/page.tsx:469-482`: `importMsg`/`importDetail` en `<p>` sin `role="status"`. (SEGURO-mecanico)
- Accesibilidad/consistencia — `personas:211`, `memoria:398,433`: confirmaciones destructivas con `window.confirm` nativo; considerar AlertDialog de shadcn. (NECESITA-VISUAL)
- Consistencia — toda la superficie usa shell clásico (shadcn Tabs + `animate-slide-up`/`animate-fade-in` con delays manuales), no framer-motion; el wizard conversacional es el candidato natural a stepVariants/MIA_EASE + BrandMark. (NECESITA-VISUAL)
- Nota positiva — consistencia interna buena: icono Sparkles uniforme para "Crear con Mia", copy del gate HITL coherente entre wizard/personas/Sugerencias.

---

## Superficie: Automatizaciones CP-P2 (consent-first)

**Archivos:** `frontend/app/_components/AutomationsSection.tsx`, `frontend/app/configurar/page.tsx`. Backend: `automations.py`, `cron/blueprints.py`, `cron/suggestions.py`, `frontend/lib/api.ts`, `api/main.py`.

**Que revisar (cursor_brief):** Subtab "Automatizaciones" (`TabsContent value="automatizaciones"`, ancla `#automatizaciones`). Cableado SANO y verificado. Solo pulido de UX/a11y/§G — no tocar el contrato. Arreglos por prioridad: (1) §G latente en `paramsSummary()`; (2) reemplazar `window.confirm()` del borrado por AlertDialog; (3) feedback de carga por-acción (aria-busy/spinner); (4) banner de error global mal ubicado + distinguir error de vacío; (5) detalles a11y (aria-hidden en iconos, contraste text-warning, doble control de expansión); (6) consistencia opcional con framer-motion.

**Comportamiento esperado (preservar):** Nada se auto-activa; toda alta es acto humano explícito (rellenar y "Activar", o aceptar una sugerencia). Los avisos de plazo procesal (`is_procedural`/`toca_plazo_procesal`) se muestran ANTES de confirmar; Mia nunca calcula términos. `fill_blueprint` no agenda. NOTA: el fondo aurora/scope dark de `_welcome` NO aplica aquí (es Ajustes) y su ausencia es correcta.

**Endpoints reales (verificados, prefix /api en main.py:184):** `GET /api/automations/blueprints`, `GET /api/automations`, `GET /api/automations/suggestions`, `POST /api/automations {plantilla,valores}`, `DELETE /api/automations/{id}`, `POST /api/automations/suggestions/{id}/accept`, `/dismiss`.

**Hallazgos detectados:**
- §G (latente) — `AutomationsSection.tsx:52-57`: `paramsSummary()` solo traduce `dias_antes`; su fallback vuelca claves snake_case crudas (`hora_envio: 08:00`). Hoy no filtra (solo hay 2 blueprints con `dias_antes`) pero fuga en cuanto se agregue un slot nuevo. Mapear cada clave a su `etiqueta` del catálogo. (SEGURO-mecanico)
- Accesibilidad — `AutomationsSection.tsx:127` (`removeAutomation`): `window.confirm()` nativo rompe foco/estilo; sustituir por AlertDialog. (NECESITA-VISUAL)
- Accesibilidad — botones Activar/Descartar/Quitar (:206-249) solo se deshabilitan con `busy`, sin cambio de texto/spinner/`aria-busy` (solo Crear cambia a "Guardando…" :321). Replicar ese patrón. (SEGURO-mecanico)
- Accesibilidad — `AutomationsSection.tsx:180`: el banner `msg` (role=alert) es único y global arriba; un error de una tarjeta al final aparece lejos sin mover foco/scroll. Llevar foco/scroll al alert o colocar el error junto a la acción. (NECESITA-VISUAL)
- Accesibilidad — iconos Sparkles (:186) y Repeat (:223) sin `aria-hidden`. (SEGURO-mecanico)
- Accesibilidad — verificar contraste AA de `text-warning` sobre `bg-warning/10` en claro y oscuro (:180,201,238,273). (NECESITA-VISUAL)
- Accesibilidad — doble control de expansión: `<button aria-expanded>` del título (:263) y botón "Configurar" (:325) hacen el mismo toggle; sin affordance visible de colapsar salvo reclicar. Consolidar. (NECESITA-VISUAL)
- Wiring — si `load()` falla, `loaded=true` y las tres listas quedan vacías con placeholder "no hay…"; un fallo de red se ve como "sin automatizaciones". Distinguir error de vacío. (NECESITA-VISUAL)
- Consistencia — usa `animate-fade-in`/`animate-slide-up` CSS en vez de framer-motion (`motion.ts`); migración opcional (la ausencia de aurora/dark aquí es correcta). (NECESITA-VISUAL)
- Nota positiva — §G limpio; consent-first satisfecho a nivel de wiring; `<Label htmlFor>` de los campos SÍ están bien asociados (:281-283).

---

## Superficie: Conectar correo/nube (CP-P3) — Microsoft 365 / Google Workspace + carpetas OneDrive

**Archivos:** `frontend/app/_components/OneDriveFolderPicker.tsx`, `MatterDriveFolder.tsx`, `OneDriveSourcesSection.tsx`, `MailboxSection.tsx`, `MailboxSectionLoader.tsx`, `ConexionesSection.tsx`, `CarpetasSection.tsx`, `frontend/app/configurar/page.tsx`. Backend: `mailbox.py`, `remote_drive.py`.

**Que revisar (cursor_brief):** Bloque "Conectar" montado por `ConexionesSection` (vía `MailboxSectionLoader`) en `configurar`, tab `conexiones`, `id="conexiones"`. Cableado COMPLETO y correcto. El abogado ve "Conectar Microsoft 365" / "Conectar Google Workspace" en llano, con casillas opt-in (contenido de correos / archivos de OneDrive); al conectar es redirigido al consentimiento y vuelve a `/configurar?mailbox=conectado`. HAY UN BUG PRIORITARIO en ese redirect. Accesibilidad a cerrar: contraste de archivos no seleccionables, aria-live en "Cargando…" y en los `<p>{msg}</p>`, deshabilitar Conectar/Sincronizar durante la petición. Consistencia: reemplazar `window.confirm()` por el Dialog que ya usa MatterDriveFolder; token en vez de `text-gray-400`.

**Comportamiento esperado:** El primer contacto de "conectar" es opt-in explícito; los sondeos de sync se limpian al desmontar (bien). §G limpio (marcas OK, incluida "Pinecone" que ya está oculta; único borderline: la palabra "índice" en la sección avanzada plegada).

**Endpoints reales (verificados):** `GET /api/mailbox/status`, `POST /api/mailbox/connect/{microsoft|google}?features=mail[,mail_content][,drive]` (devuelve `{url}`; el front hace `window.location.href`), `DELETE /api/mailbox/disconnect?provider=...`, `PUT /api/mailbox/content-analysis`; `GET /api/drive/browse?item_id=...`, `GET/POST /api/drive/sources`, `DELETE /api/drive/sources/{id}`, `POST /api/drive/sources/{id}/sync`. El 503 (`_NO_ACCOUNT`) y 502 (`_GRAPH_DOWN`) existen (remote_drive.py:121,125).

**Hallazgos detectados:**
- Wiring (BUG) — el callback OAuth redirige a `/configurar?mailbox=conectado` SIN hash (`mailbox.py:269 _redirect_frontend`). Sin `#conexiones` el abogado aterriza en "primeros-pasos", `MailboxSection` no se monta y el toast "Cuenta conectada correctamente" (MailboxSection:64) nunca se ve. Anexar `#conexiones` (o forzar el tab cuando `?mailbox` está presente). (SEGURO-mecanico)
- Wiring (mislabel) — `OneDriveFolderPicker.tsx:145-149`: el estado sin cuenta dice "desde el Panel de control" y el botón "Ir al Panel de control", pero `connectHref` por defecto es `/configurar#conexiones` (Configuración). Corregir copy a "Configuración → Conexiones". (SEGURO-mecanico)
- Wiring — `ConexionesSection.tsx:358` ("Conectar" Pinecone) y `:186` ("Sincronizar" Obsidian) no se deshabilitan durante la petición: doble clic posible. Añadir estado busy/disabled. (SEGURO-mecanico)
- Accesibilidad — `MailboxSection.tsx:164`: decide `role=status` vs `role=alert` por coincidencia de string ("correctamente"/"desconectada"); frágil si cambia el copy. Hacerlo robusto (no por string). (SEGURO-mecanico)
- Accesibilidad — `OneDriveFolderPicker.tsx:201`: archivos no-carpeta en `text-muted-foreground/50` (probablemente <4.5:1). Subir a `text-muted-foreground` normal. (SEGURO-mecanico)
- Accesibilidad — `OneDriveFolderPicker.tsx:175-179`: "Cargando…" sin `role=status`/aria-live (el error sí tiene role=alert). (SEGURO-mecanico)
- Accesibilidad — `MatterDriveFolder.tsx:199,207`: `<p>{msg}</p>` de resultado sin role=status/aria-live. (NOTA: archivo huérfano — al borrarlo, este punto desaparece.) (SEGURO-mecanico)
- Accesibilidad — `MailboxSectionLoader.tsx:8`: `text-gray-400` hardcodeado fuera del sistema de tokens; usar `text-muted-foreground`. (SEGURO-mecanico)
- Accesibilidad — `OneDriveFolderPicker.tsx:225`: "Elegir esta carpeta" se deshabilita en la raíz (`!current.id`) sin explicar por qué; añadir texto de ayuda. (SEGURO-mecanico)
- Consistencia/accesibilidad — `OneDriveSourcesSection.tsx:116` y `MailboxSection.tsx:106` usan `window.confirm()` nativo para quitar/desconectar; MatterDriveFolder ya usa un Dialog propio. Unificar al Dialog. (NECESITA-VISUAL)
- §G (borderline) — `ConexionesSection.tsx:344-357`: la marca "Pinecone" YA está oculta — los campos visibles son placeholders genéricos "Clave de acceso" y "Nombre del índice" (:349,355), todo bajo el `<details>` plegado "Memoria ampliada (opcional, avanzado)" con el descargo llano "Si no sabes qué es, no lo necesitas" (:341). El único residuo técnico visible es la palabra "índice". Clasificación Baja/borderline correcta; solo vigilar y decidir con Pipe. (NECESITA-VISUAL)
- Consistencia — toda la superficie es anterior a `_welcome` (tarjetas planas shadcn, `animate-fade-in`, sin framer-motion/BrandMark/aurora); empty-states inconsistentes (OneDriveSourcesSection cuidado; el bloque de correo no tiene equivalente calmado). Esperable en Ajustes, no bloqueante. (NECESITA-VISUAL)
- Nota positiva — cableado OK; sondeos con limpieza en desmontaje; connect() redirige con `window.location.href`.

---

## Superficie: Diagnóstico y Misión (CP-V2/CP-E5) — panel del asunto, tablero de misión, revisión de borrador

**Archivos:** `frontend/app/_components/MissionBoard.tsx`, `frontend/app/asuntos/[id]/page.tsx`, `asuntos/[id]/revisar/page.tsx`. Backend: `missions.py`, `ux.py`.

**Que revisar (cursor_brief):** Panel derecho "Diagnóstico" + "Plan de trabajo", `MissionBoard` (misiones/hitos, modo compact dentro del `<details>` del aside) y la revisión del borrador. PRIORIDAD 1 (regla dura): en el panel de Diagnóstico las citas y datos procesales deben verse marcados `[VERIFICAR]` reutilizando el resaltador que ya existe en `revisar` (renderDraft :25, `<mark>` de token warning; y si aplica `detectarDetonadores`/`EscalamientoBanner`). PRIORIDAD 2: migrar `MissionBoard` de paleta cruda a tokens (theme-aware) y a `<Button variant='cta'>`. PRIORIDAD 3: accesibilidad de `MissionBoard` (aria-label + anillo de foco). PRIORIDAD 4: contador de misiones obsoleto (callback `onChanged`) y ThinkingDots infinitos en error.

**Comportamiento esperado:** El abogado abre el asunto, ve el diagnóstico con toda cita/dato procesal resaltado `[VERIFICAR]`, despliega el Plan de trabajo con un tablero visualmente idéntico al resto (claro y oscuro), y todo botón/campo es operable por teclado y anunciado por lector de pantalla.

**Endpoints reales (verificados, no tocar backend):** `GET/POST /api/missions`, `PUT/DELETE /api/missions/{id}`, `POST /api/missions/{id}/decompose`, `POST /api/missions/{id}/milestones`, `PUT/DELETE /api/missions/{id}/milestones/{mid}`; `GET /api/matters/{id}`, `GET /api/matters/{id}/documents`, `POST /api/matters/{id}/chat` (SSE), `GET /api/matters/{id}/draft` (devuelve diagnosis, diagnosis_summary, verification, hitl_outcome), `GET /api/matters/{id}/draft.docx`, `POST /api/matters/{id}/draft/approve` (body opcional `{edited_text}`), `POST /api/matters/{id}/draft/reject` (body `{reason}`).

**Hallazgos detectados:**
- Wiring / regla dura (P1) — `page.tsx:436` renderiza la prosa del diagnóstico en crudo (`{diagnosis}`) sin resaltador; `SummaryRow` "Normas y fuentes" (:432, render :497) muestra citas en texto plano. Las citas sin respaldo y los datos procesales NO se marcan `[VERIFICAR]`. La maquinaria ya existe en `revisar` (renderDraft :25, detectarDetonadores :83, EscalamientoBanner :89) — reutilizarla. (NECESITA-VISUAL)
- Consistencia (P2) — `MissionBoard.tsx` (todo el archivo) usa paleta Tailwind cruda (`gray-900/400/50`, `white`, `amber-*`) en vez de tokens (`bg-card`, `text-muted-foreground`, `border-border`, `bg-primary`, `text-warning`); NO es theme-aware, se rompe en modo oscuro. Migrar. (NECESITA-VISUAL)
- Consistencia — `MissionBoard` usa `<button className="bg-gray-900 text-white">` en vez de `<Button variant="cta">`. (NECESITA-VISUAL)
- Consistencia — `MissionBoard.tsx:492` marca el hito procesal con `amber-200/50/800` crudos, mientras `revisar` usa el token `warning` (`bg-warning/20`, `<mark>`). Unificar al token. (NECESITA-VISUAL)
- Consistencia — `MissionBoard` no usa framer-motion ni `animate-slide-up`/`animate-fade-in`; entra sin transición. (NECESITA-VISUAL)
- Accesibilidad — `MissionBoard` inputs/selects sin nombre accesible: título de misión (:362), objetivo (:370), resultado (:382), título de hito (:480), select actor (:497). Añadir aria-label. (SEGURO-mecanico)
- Accesibilidad — `MissionBoard.tsx:501,510`: selects con `outline-none` sin anillo de foco de reemplazo; foco por teclado invisible. Añadir ring. (SEGURO-mecanico)
- Accesibilidad — `MissionBoard` usa `focus:border-gray-*` (indicador débil) frente a `focus-visible:ring-2 ring-ring` que sí usa `revisar`. Reemplazar. (SEGURO-mecanico)
- Accesibilidad — `MissionBoard.tsx:215/277/297`: `text-gray-400` sobre fondo claro, contraste bajo AA (parte de la migración a tokens). (NECESITA-VISUAL)
- Accesibilidad — `page.tsx:391`: textarea de consulta principal sin aria-label (solo placeholder). (SEGURO-mecanico)
- Wiring — `page.tsx:75,98-111`: `missionsSummary` se carga una vez al montar; el MissionBoard compacto (:476) crea/edita/elimina en su propio estado y no notifica al padre, así que el badge "N misiones · X/Y hitos" (:464-468) queda obsoleto hasta recargar. Pasar callback `onChanged`. (SEGURO-mecanico)
- Wiring — `page.tsx:206`: en el evento `error` del stream se fija status pero la burbuja optimista de Mia queda con `text=''` → `ThinkingDots` (:356) infinitos. Escribir el texto de error en esa burbuja. (SEGURO-mecanico)
- Wiring — `MissionBoard.tsx:192` (`moveMilestone`): dos PUT secuenciales para intercambiar `seq`; si el segundo falla quedan dos hitos con el mismo seq hasta el `load()` de recuperación. Reordenamiento no atómico (funcional, con parpadeo ante error). (SEGURO-mecanico)
- §G (producto, no duro) — `MissionBoard.tsx:222,254`: "Descompón un objetivo grande en hitos" / "proponer hitos"; "Misión"/"hito" es vocabulario del tablero. Evaluar con Pipe si el abogado los entiende o convienen "plan"/"paso". (NECESITA-VISUAL)

---

## Lista priorizada de arreglos

| Prioridad | Superficie | Hallazgo | Tipo | Clasificación |
|---|---|---|---|---|
| Alta | Diagnóstico y Misión | Diagnóstico pinta citas/datos procesales en crudo, sin marcar `[VERIFICAR]` (page.tsx:436/432/497) — reutilizar renderDraft de `revisar` | §G (regla dura) / wiring | NECESITA-VISUAL |
| Alta | Diagnóstico y Misión | `MissionBoard` en paleta cruda, no theme-aware (se rompe en oscuro) — migrar a tokens | consistencia | NECESITA-VISUAL |
| Alta | Conectar correo/nube | Redirect OAuth sin `#conexiones`: el toast "cuenta conectada" nunca se ve (mailbox.py:269) | wiring | SEGURO-mecanico |
| Alta | Conectar correo/nube | Mislabel "Panel de control" → debe ser "Configuración → Conexiones" (OneDriveFolderPicker:145) | wiring | SEGURO-mecanico |
| Alta | Guías y conocimiento | BUG 409: `e.message.includes('409')` → `e.status===409`; el mensaje de drift nunca aparece (memoria:812) | wiring | SEGURO-mecanico |
| Alta | Proyectos y Fuentes | Línea de estado del chat sin role=status/aria-live (proyectos/[id]:314) | accesibilidad | SEGURO-mecanico |
| Alta | Proyectos y Fuentes | Textarea del chat sin aria-label (proyectos/[id]:316) | accesibilidad | SEGURO-mecanico |
| Alta | Proyectos y Fuentes | Fallo de carga = `setState([])` indistinguible de "vacío" (proyectos:63, [id]:97) | wiring | NECESITA-VISUAL |
| Alta | Guías y conocimiento | Pregunta del wizard + spinner "Mia está pensando" sin aria-live (Wizard:174-212) | accesibilidad | SEGURO-mecanico |
| Alta | Bienvenida | TagInput sin label/aria-label (onboarding:907) | accesibilidad | SEGURO-mecanico |
| Alta | Bienvenida | Botones "quitar tag" `{tag} ×` sin aria-label (onboarding:893,825) | accesibilidad | SEGURO-mecanico |
| Alta | Diagnóstico y Misión | Inputs/selects de MissionBoard sin nombre accesible (362,370,382,480,497) | accesibilidad | SEGURO-mecanico |
| Media | Diagnóstico y Misión | Contador de misiones del header obsoleto — falta callback `onChanged` (page.tsx:464) | wiring | SEGURO-mecanico |
| Media | Diagnóstico y Misión | Evento `error` deja la burbuja en ThinkingDots infinitos (page.tsx:206) | wiring | SEGURO-mecanico |
| Media | Diagnóstico y Misión | Selects `outline-none` sin anillo de foco de reemplazo (MissionBoard:501,510) | accesibilidad | SEGURO-mecanico |
| Media | Diagnóstico y Misión | `focus:border-gray-*` débil en vez de `focus-visible:ring-2 ring-ring` (como `revisar`) | accesibilidad | SEGURO-mecanico |
| Media | Diagnóstico y Misión | Textarea de consulta sin aria-label (page.tsx:391) | accesibilidad | SEGURO-mecanico |
| Media | Diagnóstico y Misión | Botón `<button bg-gray-900>` en vez de `<Button variant=cta>` | consistencia | NECESITA-VISUAL |
| Media | Diagnóstico y Misión | Hito procesal en `amber-*` crudo en vez de token `warning` (:492) | consistencia | NECESITA-VISUAL |
| Media | Diagnóstico y Misión | `text-gray-400` bajo AA (215/277/297) — parte de migración a tokens | accesibilidad | NECESITA-VISUAL |
| Media | Guías y conocimiento | `Badge {p.type}` — hoy sin fuga (backend ya etiqueta los 5 tipos, ux.py:61-67); añadir fallback en el front por si el backend agrega un `proposal_type` FUTURO sin etiqueta (memoria:910) | §G (defensa en profundidad) | SEGURO-mecanico |
| Media | Guías y conocimiento | Crear guía manual y corregir criterio (Wiki) sin manejo de error (memoria:300,121) | wiring | SEGURO-mecanico |
| Media | Guías y conocimiento | restoreVersion/apply/ignore con `.catch(()=>{})` silencioso (memoria:439,778) | wiring | SEGURO-mecanico |
| Media | Guías y conocimiento | Errores del wizard/edición sin role=alert (Wizard:214, memoria:674) | accesibilidad | SEGURO-mecanico |
| Media | Guías y conocimiento | ChipsField: Label no asociado al input (personas:562) | accesibilidad | SEGURO-mecanico |
| Media | Guías y conocimiento | window.confirm en acciones destructivas → AlertDialog (personas:211, memoria:398,433) | accesibilidad | NECESITA-VISUAL |
| Media | Proyectos y Fuentes | saveNotice/downloadError sin aria-live (proyectos/[id]:351,356) | accesibilidad | SEGURO-mecanico |
| Media | Proyectos y Fuentes | Banner/por-fuente/loadError de FuentesPanel sin aria-live (262,359,285) | accesibilidad | SEGURO-mecanico |
| Media | Proyectos y Fuentes | Error del stream duplicado (status + burbuja) (proyectos/[id]:152) | wiring | SEGURO-mecanico |
| Media | Proyectos y Fuentes | Contraste de metadatos `text-xs muted` sobre `bg-card/40` | accesibilidad | NECESITA-VISUAL |
| Media | Proyectos y Fuentes | `MatterDriveFolder` huérfano con "Sincronizar" — borrar archivo | §G | SEGURO-mecanico |
| Media | Proyectos y Fuentes | Motion CSS ad-hoc + stagger manual vs framer-motion `motion.ts` | consistencia | NECESITA-VISUAL |
| Media | Bienvenida | KeyField: hint no enlazado vía aria-describedby (activar:590,646) | accesibilidad | SEGURO-mecanico |
| Media | Bienvenida | CountrySelector: 21 checkboxes sin fieldset/role=group (:56-84) | accesibilidad | SEGURO-mecanico |
| Media | Bienvenida | Contraste de textos muted/70 y /80 sobre #060606 | accesibilidad | NECESITA-VISUAL |
| Media | Bienvenida | `<details>` vuelca `soul_content` crudo — verificar que no exponga campos (onboarding:324) | §G | NECESITA-VISUAL |
| Media | Bienvenida | Onboarding usa `<Field>` propio en vez de `WelcomeField` | consistencia | NECESITA-VISUAL |
| Media | Bienvenida | Ruta OpenRouter inalcanzable: `openrouter` nunca se envía — confirmar con Pipe | wiring | NECESITA-VISUAL |
| Media | Automatizaciones | `paramsSummary` fallback imprime snake_case (fuga §G latente) (:52-57) | §G | SEGURO-mecanico |
| Media | Automatizaciones | Feedback de carga por-acción ausente (aria-busy/spinner) (:206-249) | accesibilidad | SEGURO-mecanico |
| Media | Automatizaciones | window.confirm del borrado → AlertDialog (:127) | accesibilidad | NECESITA-VISUAL |
| Media | Automatizaciones | Banner de error global lejos de la acción; sin foco/scroll (:180) | accesibilidad | NECESITA-VISUAL |
| Media | Automatizaciones | Contraste `text-warning` sobre `bg-warning/10` en claro y oscuro | accesibilidad | NECESITA-VISUAL |
| Media | Automatizaciones | Fallo de carga se ve como "sin automatizaciones" — distinguir error de vacío | wiring | NECESITA-VISUAL |
| Media | Conectar correo/nube | `MailboxSection:164` decide role=status/alert por string match — hacerlo robusto | accesibilidad | SEGURO-mecanico |
| Media | Conectar correo/nube | Archivos no seleccionables `text-muted-foreground/50` bajo AA (OneDriveFolderPicker:201) | accesibilidad | SEGURO-mecanico |
| Media | Conectar correo/nube | "Cargando…" sin role=status/aria-live (OneDriveFolderPicker:175) | accesibilidad | SEGURO-mecanico |
| Media | Conectar correo/nube | Botones Conectar (Pinecone)/Sincronizar (Obsidian) sin disabled/busy — doble clic | wiring | SEGURO-mecanico |
| Media | Conectar correo/nube | "Elegir esta carpeta" deshabilitado en raíz sin explicación (:225) | accesibilidad | SEGURO-mecanico |
| Media | Conectar correo/nube | window.confirm en OneDriveSources/Mailbox → Dialog estilizado (unificar) | consistencia | NECESITA-VISUAL |
| Baja | Bienvenida | MiaLine con `font-semibold` pisa `font-display` en onboarding | consistencia | NECESITA-VISUAL |
| Baja | Bienvenida | Inputs de pregunta en un solo StaggerItem (escalonado pobre) | consistencia | NECESITA-VISUAL |
| Baja | Bienvenida | Texto de herramientas viene del backend — revisar fuente §G (onboarding:97) | §G | NECESITA-VISUAL |
| Baja | Proyectos y Fuentes | "OneDrive" visible — decidir con Pipe si se neutraliza | §G | NECESITA-VISUAL |
| Baja | Proyectos y Fuentes | Conteo `documentos` recibido y descartado — mostrar opcional | consistencia | NECESITA-VISUAL |
| Baja | Proyectos y Fuentes | Avatar Sparkles en el chat en vez de BrandMark | consistencia | NECESITA-VISUAL |
| Baja | Proyectos y Fuentes | Sin puente visual (acento aurora/`--cta`) con `_welcome` | consistencia | NECESITA-VISUAL |
| Baja | Guías y conocimiento | "Habilidades"/"Conceptos" — decidir con Pipe si se renombra | §G | NECESITA-VISUAL |
| Baja | Guías y conocimiento | importMsg sin role=status (memoria:469) | accesibilidad | SEGURO-mecanico |
| Baja | Guías y conocimiento | Ctrl+Enter sin hint visible (Wizard:201) | accesibilidad | SEGURO-mecanico |
| Baja | Guías y conocimiento | Superficie sin framer-motion; wizard candidato a stepVariants/MIA_EASE | consistencia | NECESITA-VISUAL |
| Baja | Automatizaciones | Iconos Sparkles/Repeat sin aria-hidden (:186,223) | accesibilidad | SEGURO-mecanico |
| Baja | Automatizaciones | Doble control de expansión (título aria-expanded + botón "Configurar") | accesibilidad | NECESITA-VISUAL |
| Baja | Automatizaciones | Migrar `animate-*` CSS a framer-motion (opcional) | consistencia | NECESITA-VISUAL |
| Baja | Conectar correo/nube | `MatterDriveFolder` msgs sin role=status (desaparece al borrar el archivo) | accesibilidad | SEGURO-mecanico |
| Baja | Conectar correo/nube | `MailboxSectionLoader` `text-gray-400` crudo → token (:8) | accesibilidad | SEGURO-mecanico |
| Baja | Conectar correo/nube | Marca "Pinecone" ya oculta; único residuo visible es la palabra "índice" (avanzado plegado) — vigilar | §G | NECESITA-VISUAL |
| Baja | Conectar correo/nube | Superficie pre-`_welcome` (tarjetas planas) + empty-states inconsistentes | consistencia | NECESITA-VISUAL |
| Baja | Diagnóstico y Misión | MissionBoard sin transición (no framer-motion) | consistencia | NECESITA-VISUAL |
| Baja | Diagnóstico y Misión | `moveMilestone` no atómico (dos PUT; parpadeo de orden ante error) (:192) | wiring | SEGURO-mecanico |
| Baja | Diagnóstico y Misión | "Misión"/"hito" vocabulario de producto — decidir con Pipe | §G | NECESITA-VISUAL |
