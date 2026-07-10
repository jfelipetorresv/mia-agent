# MIA — Evolución de producto: Proyectos, Conocimiento vivo, Agentes y Perfil

## Contexto

Feedback de Pipe (2026-07-09, tras aprobar el rebrand visual): MIA necesita evolucionar de "chat + expedientes" a un espacio de trabajo estilo **Claude Cowork / ChatGPT Work** (investigados en línea: proyecto = carpetas conectadas + hilos + artefactos, agente que trabaja sobre los archivos con todo el conocimiento del sistema). Además: conectar carpetas hoy es hostil (rutas pegadas a mano), las guías de trabajo son difíciles de crear ("uno las tiene en la cabeza pero nadie te ayuda a extraerlas"), las personas jurídicas deben volverse agentes robustos con conocimiento propio, y el perfil/SOUL del despacho quedó sin pantalla de edición. Principio rector innegociable: **usabilidad perfecta, cero confusión** — y **nada generado por IA se guarda sin aprobación del abogado** (gate HITL).

Decisiones de Pipe: ejecutar **todo en orden, bloque por bloque** (A→B→C, un cierre por sesión/checkpoint); **"Proyectos" y "Asuntos" como pestañas separadas** (Asuntos = expediente jurídico formal con diagnóstico/borradores; Proyectos = espacio libre conectado a carpetas).

Ya existe (verificado): asuntos con 1 carpeta local + 1 OneDrive + correos; picker visual SOLO para OneDrive; motor de aprendizaje con gate (skill_improver/feedback_processor/curator → proposals); personas con role_prompt y guardarraíl de voz; `update_soul()` sin endpoint ni UI; shadcn Tabs disponible.

---

## BLOQUE A — Proyectos + carpetas sin fricción (primera sesión)

**Decisión arquitectónica:** reusar `matters` con discriminador `kind ('asunto'|'proyecto')` — todo el sistema (documents, chunks, RLS, retrieval RRF, checkpointer, SSE, dedupe) cuelga de `matter_id`; una entidad nueva duplicaría ~8 tablas y 4 routers. Lo que un proyecto NO necesita (diagnóstico/borrador/HITL/misiones) no vive en el esquema sino en el grafo y la página → grafo alterno liviano + página propia.

### A0. Migración de cimientos — `backend/mia/db/migrations/028_projects_multifolder.sql` (+ `execution/init_projects_multifolder.py`, calcado de `init_matter_folders.py`)
- `matters.kind varchar(20) NOT NULL DEFAULT 'asunto'` + CHECK.
- `documents.source_id uuid` (sin FK dura; discrimina `origin`) + índice `(matter_id, source_id)` + **backfill** de docs `origin='folder'` a su única fuente activa.
- `ck_documents_origin` gana `'mia'` (archivos producidos por Mia).
- ⚠️ **Bug latente descubierto**: `_ingest_matter_file()` y `_prune_matter_docs()` (`local_folders.py:621-668`) filtran por `matter_id+origin` sin distinguir fuente → con 2 carpetas, el sync de B **borraría los docs de A**. `source_id` + scoping van ANTES de quitar el límite de 1 carpeta. Orden estricto A0→A2.

### A1. Selector de carpetas del equipo (fin de rutas pegadas)
- Backend `local_folders.py`: `safe_browse_roots()` (Documentos/Escritorio/Descargas + `detect_cloud_folders()` + unidades navegables-no-registrables) y `browse_folder(path)` — un nivel con `os.scandir` en `asyncio.to_thread`, fail-closed (`resolve` + `is_relative_to` + `_FORBIDDEN_PARTS`), tope 500 + `truncated`.
- `folders.py`: `GET /api/folders/browse[?path=]`. El registro sigue pasando por `register_source()` intacto (allowlist re-valida).
- Frontend: **crear `FolderPicker.tsx`** (clon estructural de `OneDriveFolderPicker.tsx`, contrato `onPicked(path)`) y reemplazar los 3 inputs de ruta manual: `CarpetasSection.tsx`, diálogo "Vincular carpeta" en `asuntos/[id]/page.tsx`, vault de Obsidian en `ConexionesSection.tsx`.
- Riesgo Modo A (Docker): endpoint deshabilitable como `POST /api/obsidian/install`; anotar en `memory/bugs-and-risks.md`.

### A2. Multi-carpeta por asunto/proyecto
- `local_folders.py`: `_ingest_matter_file`/`_prune_matter_docs` con `source_id`; `get_matter_source()` → `get_matter_sources()` (wrapper singular deprecado).
- `matter_folders.py`: superficie plural `GET/POST /api/matters/{id}/folders`, `POST .../folders/{source_id}/sync` (throttle por fuente ya existe), `DELETE .../folders/{source_id}`; quitar el 409; tope defensivo 10 carpetas. Regla "una carpeta no sirve a dos expedientes" intacta.
- Gate nuevo en `execution/`: 2 carpetas vinculadas → la poda de una NO toca los documentos de la otra.

### A3. Vista "Fuentes" unificada
- **Crear** `backend/mia/api/routes/matter_sources.py`: `GET /api/matters/{id}/sources` → carpetas del equipo + OneDrive + correos con `estado` EN LLANO desde el backend (una sola fuente de textos §G).
- **Crear** `frontend/app/_components/FuentesPanel.tsx`: lista única + botón "+ Conectar fuente" (3 opciones: carpeta del equipo → FolderPicker; OneDrive → OneDriveFolderPicker; correos → MailSearchDialog). Absorbe y elimina de `asuntos/[id]/page.tsx` el bloque de carpeta (436-497), `MatterDriveFolder` y el botón de correos; reusa el polling 5s/30s existente.

### A4. Pestaña "Proyectos"
- `ux.py`: `MatterCreate.kind`; `GET /api/matters?kind=`; **outputs**: `GET/POST /api/matters/{id}/outputs` (origin='mia', mismo pipeline chunk+embed → lo producido es consultable después) + `GET .../outputs/{doc_id}.docx` (reusa `draft_to_docx`).
- `prompt_builder.py`: instrucción de nodo `"work"` (trabaja sobre las fuentes del proyecto apoyándote en el conocimiento del despacho; conversacional; documentos completos en la respuesta). Mantiene identidad/citación-[VERIFICAR]/§G.
- `graph.py`: `build_project_graph()` = `intake_node` (reuso literal: RRF docs del proyecto + knowledge del despacho) → `work_node` → END. Sin draft/HITL. `stream.py` decide por `matters.kind` (evento `reply`, sin `awaiting_review`).
- Frontend: nav "Proyectos" (`/proyectos`, icono FolderKanban, entre Asuntos y Conocimiento); `proyectos/page.tsx` (lista + creación en 2 pasos: nombre → conectar carpetas con FuentesPanel, "Omitir por ahora"); `proyectos/[id]/page.tsx` (3 columnas: FuentesPanel · chat con "Guardar en el proyecto" bajo respuestas largas · Archivos producidos con descarga .docx).

---

## BLOQUE B — Guías de trabajo asistidas + gobernanza de skills (segunda sesión)

**Decisión transversal:** UN motor de entrevista **stateless** (`backend/mia/memory/interviewer.py` + router `backend/mia/api/routes/guides.py`): el frontend manda el transcript completo; el backend responde la siguiente pregunta o el borrador. **El borrador solo existe en la respuesta HTTP — nunca toca la DB hasta que el abogado pulsa Guardar** (gate por construcción). LLM `task="curator"` (respeta política del despacho, incl. `soberano` 100% local). Contrato: `POST /api/guides/interview {kind:'guia'|'agente', messages[], matter_id?}` → `{done:false, question}` | `{done:true, draft, explanation}`. Mín 3 / máx 6 preguntas; JSON inválido → pregunta de fallback determinista, jamás un 500; recortes server-side a 200 chars (presupuesto índice 3000 tok).

### B0. CRUD completo de playbooks + versiones — migración `028/029_playbook_versions.sql` (RLS patrón 023)
- Tabla `playbook_versions` (snapshot ANTES del cambio, `changed_by ('abogado'|'mia')`, `reason` en llano).
- Endpoints: `GET /api/playbooks/{id}` (con content), `PUT` (snapshot + re-embed; editable aunque `protected` — protected solo bloquea cambios automáticos), `POST .../archive|restore` (archivar sale del índice del prompt vía `get_index` sin tocar prompt builder), `GET .../versions` + `restore`. `POST /api/playbooks` gana `origin` ∈ {manual, importada, entrevista, asunto, aprendida} → `metadata.origin`.

### B1-B2. Wizard "Crear guía con Mia"
- `interviewer.py` + `guides.py` con tests (LLM stubbeado).
- **Crear** `frontend/app/_components/GuideInterviewWizard.tsx` (lo reusa el Bloque C): 3 pantallas — Entrevista (una pregunta por turno) → Revisión (borrador EDITABLE, copy: "Esta guía todavía no existe; solo se guardará cuando pulses Guardar") → Guardar (`POST /api/playbooks origin='entrevista'`). Botón "Crear con Mia" en el subtab de guías de `memoria/page.tsx`.

### B3. "Convierte lo que hicimos aquí en una guía"
- Botón en la pantalla del asunto (visible con borrador aprobado) → mismo wizard con `matter_id`; el backend precarga contexto (matter + draft aprobado + trazas) y Mia abre con resumen de confirmación. Mismo gate.

### B4. Gobernanza de lo aprendido
- Backend: `GET /api/proposals` gana `source_matters` (títulos derivados de `trace_ids` "tenant:matter:ts", fail-open) → UI "Aprendí esto trabajando en: …"; `POST /api/proposals/{id}/apply` acepta `{content?, title?}` editados (el humano corrige, no solo aprueba; reemplaza el placeholder feo "Sugerencia {id}"); apply hace snapshot a versions.
- UI: **fusionar los subtabs "Guías y documentos" + "Lo que Mia sabe hacer"** en uno solo (son la misma entidad partida en dos vistas): lista con badge de origen en llano, métrica GEPA (`/api/skills/ranked`), acciones Ver/Editar/Desactivar/Historial, botonera Importar · Escribir · **Crear con Mia**; propuestas con "Editar antes de aplicar".

---

## BLOQUE C — Agentes jurídicos + perfil unificado + Configuración en subtabs (tercera sesión)

### C1. Personas → "Agentes jurídicos" con conocimiento
- Migración `persona_playbooks` (M2M, RLS patrón 023); tope 8 guías por agente.
- `personas.py`: `get/set_linked_playbooks`; `turn_context()` gana `playbook_ids`.
- Inyección SIN romper el guardarraíl: en turno de asunto, `_prepare_playbooks` activa primero los vinculados (respetando `_MAX_ACTIVE_PLAYBOOKS` y el orden de descarte del compresor); en modo asistente, bloque de material "Guías que este rol prioriza" (≤4k tok) DESPUÉS de las capas de método — el conocimiento jamás entra en `role_prompt`.
- UI: renombrar superficie a "Agentes jurídicos" (ruta `/personas` y API quedan); selector de guías en `PersonaFormPanel`; **"Crear con Mia"** = `GuideInterviewWizard kind='agente'` → revisión en el form precargado (con `suggested_playbook_ids`) → Guardar.

### C2. Perfil del despacho editable y unificado
- **Fuente de verdad: `soul_responses` canónico; `firm_profiles` derivado** (`derive_firm_profile(responses)` determinista; extras propios: `tp_number`, `preferred_sources`).
- Endpoints: `GET/PUT /api/profile/full` — el PUT hace `update_soul()` (crítico) y luego upsert de firm_profiles (best-effort con warning en llano); devuelve el summary regenerado. `PUT /api/profile` legado deprecado.
- UI: `MiDespachoSection.tsx` (rework del subtab "Mi despacho"): Identidad · Jurisdicción y práctica (mismo selector de países del onboarding) · Datos profesionales · Herramientas · Modo profundo. Nota: "Es lo mismo que respondiste al conocer a Mia; edítalo sin repetir la entrevista."

### C3. Configuración en subtabs
- `configurar/page.tsx` con shadcn Tabs: **Primeros pasos** (default si incompleto, contador en el trigger) · Conexiones · Carpetas · Automatizaciones · Valor y gasto (+ Procesos de fondo plegado).
- **Deep-links críticos**: mapear `#conexiones/#carpetas/#automatizaciones/#valor` → tab en el mount y actualizar hash al cambiar (los `enlace` de setup.py y el dashboard siguen funcionando sin tocar backend).

---

## Verificación (cada bloque, antes de su commit)

1. **Capa 1**: suites dirigidas nuevas (gate multi-carpeta anti-poda-cruzada; interviewer con LLM stub; RLS de tablas nuevas) + regresión completa (`scripts/run_tests.ps1`, HALT en `test_rls` y `check_env_pins`) + `npm run build`.
2. **Capa 2**: revisor adversarial independiente (Opus, contexto fresco) por bloque; correcciones antes del cierre.
3. **Capa 3**: recorrido en vivo de Pipe (es el juez de usabilidad); pendientes se anotan en HANDOFF.
4. Gate HITL verificado explícitamente en B/C: abortar cualquier wizard no deja NADA en DB.

## Archivos críticos
- `backend/mia/connectors/local_folders.py` · `backend/mia/api/routes/matter_folders.py` · `backend/mia/agents/graph.py` · `backend/mia/api/routes/ux.py` · `backend/mia/memory/playbook_manager.py` · `backend/mia/agents/personas.py` · `backend/mia/onboarding/soul_interview.py`
- `frontend/app/asuntos/[id]/page.tsx` · `frontend/app/memoria/page.tsx` · `frontend/app/configurar/page.tsx` · `frontend/app/_components/OneDriveFolderPicker.tsx` (molde) · nav.ts
- Nuevos: `FolderPicker.tsx`, `FuentesPanel.tsx`, `GuideInterviewWizard.tsx`, `MiDespachoSection.tsx`, `proyectos/*`, `interviewer.py`, `guides.py`, `matter_sources.py`, migraciones 028-029.

## Nota de alcance
- Carpetas vinculadas POR AGENTE: pospuesto a v2 (documentado; hoy el RAG es por asunto/proyecto, no por rol).
- El OAuth de Microsoft/Google sigue pendiente de la acción de Pipe (guía en `docs/guia-conectar-correo-y-nube.md`) — los flujos de correo/OneDrive del Bloque A degradan en llano hasta entonces.
