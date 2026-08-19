# CIERRE — 2026-07-19 (2ª sesión) · Primer arranque en vivo + auditoría de usabilidad y RAG

Rama `feat/fase1-inc1-cleanup-scaffolding`. **14 commits, NINGUNO pusheado** (Pipe aprueba el push).
Esta entrada es la más reciente: **empezar por aquí.**

## 1 · Estado del entorno (verificado en vivo hoy)

- **Base de datos portable ARRIBA** en `127.0.0.1:55432` (binarios `postgres16-portable`, NO el `-full`, cuyos backends mueren con 0xC0000142). El `.env` ya apunta ahí (`PG_PORT=55432`).
- **Migraciones 045 y 046 APLICADAS a la base real** (se aplicaron directo, sorteando el landmine de `setup_db.ps1` — ya arreglado, ver §5). Verificado: `chunks.folio_ancla`, `documents.metadata_sugerida`, `tipo/parte/folio_radicado/fecha_documento` existen.
- **`test_rls` 19/19 PASS** contra esa base con las columnas nuevas. El gate crítico está verde.
- **Cuenta de Pipe:** su correo tenía un registro viejo y vacío del 20-jun (despacho "lexia", 0 asuntos/0 documentos) que **se borró** con su OK; se registró de nuevo → tenant **"Torres"** (`fddce561-25c0-451e-b281-18e646269042`).
- **Caso real de prueba:** proyecto **"Proceso 2"** (`a7645d60-…`) con la carpeta `D:\Jurisprudencia seguros\Cumplimiento` vinculada e **indexada correctamente**: 3 documentos, **622 fragmentos, ~743.600 caracteres** (≈370 páginas). NO eran escaneados.

## 2 · El hallazgo central (por qué "MIA no revisa bien la información")

Con 743.600 caracteres de jurisprudencia cargados, **MIA leía 8 fragmentos ≈ 9.600 caracteres por pregunta = el 1,3 %**. No es que analizara mal: es que casi no leía. Además, en proyectos, el conocimiento del despacho se recuperaba y se descartaba, y los fragmentos llegaban sin nombre de archivo. **Tres causas, todas verificadas en código y las tres ya corregidas** (commit `5d3ca3d`) salvo el volumen de lectura (ola 2).

## 3 · Qué se arregló y commiteó hoy

| Commit | Qué |
|---|---|
| `5d3ca3d` | **(a)** `work_node` (grafo de PROYECTO) ahora SÍ entrega el conocimiento del despacho al modelo — antes lo recuperaba, lo pagaba y lo tiraba, y encima L7 le *afirmaba* al modelo que lo tenía. **(b)** El sello pasa de `<<<DOC 1>>>` a `<<<DOC 1 · archivo.pdf · folio 12>>>` (`retrieval.py` ahora trae `filename` y `folio_ancla`): MIA puede citar por nombre y folio. Folio NULL nunca se inventa. **(c)** `GET /wiki/concepts/{n}` ya no devuelve el YAML crudo (nuevo `get_concept_view`). **(d)** Nuevo `frontend/components/MiaMarkdown.tsx`: parser propio, **cero dependencias**, cero `dangerouslySetInnerHTML`, tolerante a SSE; cableado en chat/asuntos/proyectos/memoria y **unifica el resaltado `[VERIFICAR]`** que estaba duplicado y divergente. |
| `1d34031` | **MIA agnóstica**: fuera el sesgo de país (Colombia ya no va primero; eliminada la insignia "Conocimiento jurídico profundo") y de área (ejemplos del onboarding ya no dicen "seguros"/"Aseguradoras (HDI, Zurich, SURA…)"). |
| `3ab3714`, `9c84682` | Arranque de dev: ventanas con `-NoProfile` y minimizadas + lanzador `Abrir Mia.cmd`. |
| `fdad1f1` | Retrospectiva `docs/retrospectives/retrospective-2026-07-19-001-*` + arreglo del chequeo de pgvector de `setup_db.ps1`. |
| `0d7bb6b`, `c447c8c`, `b99c2d0`, `06a4877`, `58ad4c6` | `docs/prueba-en-vivo-inc3.md`: guía de prueba en vivo + las trampas reales del entorno. |

Suites verificadas tras los cambios: `retrieval_knowledge` **36/36** (se corrigió una assertion que esperaba el sello viejo), `untrusted` 28/28, `projects` 33/33, `document_pipeline` 45/45, `citation_guard` 19/19, `context_references` 43/43.

## 4 · OLA 2 — lo siguiente, YA DECIDIDO por Pipe (arrancar por aquí)

1. **Lectura suficiente.** Decisión literal de Pipe: *"debe poder leer lo que se requiera para dar respuesta completa y suficiente; la información que esté en la carpeta o lo que se pida"*. NO es subir una constante: es **recuperación adaptativa**. Hoy `retrieve_rrf` usa `top_k=8, candidates=20` fijos (`agents/retrieval.py:80-81`) y nadie los sobreescribe; el llamador es `intake_node` (`graph.py:883`). El nodo YA tiene shrink por presupuesto (`graph.py:1446-1448`), así que subir es seguro: si no cabe, `context_recovery` recorta solo. Dimensionar contra el caso real (622 fragmentos disponibles).
2. **Guardián de citas también en PROYECTOS.** Hoy `verification_node` solo está cableado en `build()` (`graph.py:1600, 1616-1617`); `build_project` (`graph.py:1623-1645`) es START→intake→delegación→work→END: **un proyecto puede afirmar normas y jurisprudencia sin una sola marca `[VERIFICAR]`**. Pipe: *"debería poder confirmar las normas y jurisprudencia; es parte de la razón de ser de MIA"*. Requiere que `_verify_draft` opere sobre `state['reply']`, no solo `state['draft']` (`graph.py:1382-1387, 1397`).
3. **Panel primero — vía RÁPIDA** (elegida por Pipe): subir Panel al primer lugar en `frontend/app/_components/nav.ts` y que el login aterrice ahí (`login/page.tsx:33`). NO mover la ruta raíz todavía (eso es la vía completa, 9 archivos de enlaces).

## 5 · Trampas del entorno (documentadas en `docs/prueba-en-vivo-inc3.md`)

- **MIA NO se mantiene viva si la lanza el asistente**: los servicios mueren al terminar el comando (probado 3 veces, incluso desacoplando por WMI). **Pipe debe abrirla con `Abrir Mia.cmd`** (doble-clic) desde su sesión.
- **`statusline.js` zombis**: había **2.060 procesos node** huérfanos de Claude Code ahogando la máquina (terminal a 5736 ms, Next.js sin poder servir chunks). Limpieza: matar SOLO los `statusline.js` (2086 → 24; terminal a 1917 ms). **Causa raíz sin diagnosticar** — volverán.
- **`ChunkLoadError`**: tuvo TRES causas distintas en la sesión (saturación → recompilación de 50 s tras borrar `.next` → caché del navegador). Si el servidor devuelve 200 en los 6 chunks, el problema es del navegador: abrir **`http://127.0.0.1:3100`** (otro origen ⇒ caché limpio).
- **`setup_db.ps1` ARREGLADO** (`fdad1f1`): su chequeo de pgvector apuntaba al PostgreSQL del sistema (5432, ruta fija) en vez de la base del `.env`, y abortaba las migraciones con una falsa alarma.

## 6 · Auditoría de usabilidad — pendientes con diagnóstico hecho

Los 10 puntos que reportó Pipe fueron auditados (8 agentes + Codex). Lo ya diagnosticado y **no** implementado:

- **Panel**: se siente vacío por una decisión escrita del 2026-07-09 (dejar solo lo accionable y mandar conexiones/salud a Configuración) — Pipe la revierte. **Casi todo ya existe mal expuesto**: `GET /api/setup/status` devuelve 7 pasos en lenguaje llano (perfil, motor de IA, notas, carpetas, guías, Telegram, voz) con estado/detalle/enlace y **solo lo consume `configurar/page.tsx`**. También sin usar: `/api/playbooks/health/summary`, `/api/matters/{id}/daily`, gasto del mes completo, `connectors.models`, `scheduler_jobs`. Además: las rejillas declaran `grid-cols-4` y pintan solo 2 tarjetas (media pantalla vacía).
- **Asunto vs Proyecto**: la diferencia REAL es *con aprobación* (asunto: siempre termina en borrador que Pipe aprueba) vs *sin aprobación* (proyecto: responde y ya). Todo lo demás es idéntico — **la pantalla de proyectos miente al sugerir que ahí "conectas las carpetas que quieras" como si fuera exclusivo: hay que borrarlo**. Asimetrías sin razón de negocio: en un asunto no se puede guardar lo que MIA produjo (3 candados); en un proyecto no se puede convocar la Sala de estrategia. Recomendación: **renombrar, no fusionar**.
- **Conexiones**: Gmail/Outlook/OneDrive están **construidos y muertos** hasta que Pipe registre las apps OAuth en Azure/Google (trámite suyo, no código). Decidir además: ¿una app por despacho o una app de Lexia compartida?
- **Modelos/OpenRouter por agente**: hoy un agente solo elige "motor del despacho" o "siempre local". Abrirlo permitiría evadir la política de gasto/privacidad del despacho — recomendación: **explicar mejor, no abrir**.
- **Bug de Hook**: `frontend/app/chat/page.tsx` invoca `useAtajo` dentro de un callback (viola las reglas de React). Sin diagnosticar si rompe el chat en runtime. Warnings de dependencias en dashboard, `ConnectedSystemsSection` y `FuentesPanel`.
- **Ctrl+K → "Nuevo asunto"** navega a `/?nuevo=1` y `page.tsx` nunca lee ese parámetro: el atajo no abre nada.
- **NO existe control de vencimientos procesales.** Solo recordatorios que pide Pipe por chat. No prometer plazos: sería inventar fechas.

## 7 · Carpetas: 5 fallos reales aún abiertos

La auditoría previa (`mia-cory-audit-worktree/research/cory-audit/`) dejó **2 suites rojas reproducidas**: `test_matter_folder.py` (conteo, throttle, conservación tras `unlink`) y `test_matter_folders_multi.py` (conteo, throttle). **Causa raíz sin identificar.** Son todas de *asuntos*: **no existe ni un solo test de "carpeta vinculada a un PROYECTO"**, que es justo el escenario que falló en producción. De los 11 FAIL de esa regresión, solo ~6 son reales; 4 eran ambientales del worktree (faltaba `PG_PASSWORD`).

## 8 · Pendiente de Pipe (no es código)

- Registrar las **apps OAuth** de Gmail/Outlook/OneDrive.
- **Verificar el inc. 3 en vivo** (nunca se probó con MIA corriendo): folio y procedencia al subir un documento, botones "Arrancar el día"/"Cerrar por hoy", y "Documentos por confirmar".
- Decidir el **push** de los 14 commits.
- Encargo para **Cursor** (rediseño visual de panel y conocimiento) — pendiente de redactar; su rol ya está definido como frontend/capa 3.
- **Rediseño del SOUL/perfil** con las skills de referencia que pasó (`perfil-personal-lexia`, `perfil-completo` — "no tan largo").

---

