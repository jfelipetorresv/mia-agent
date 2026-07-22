# CIERRE — 2026-07-19, Fase 1 · incremento 3 — procedencia+folio, ficha-loader/daily/cierre, clasificador de metadata (rama, sin push)

Rama `feat/fase1-inc1-cleanup-scaffolding`. Orquestado con workflows multi-agente (un escritor por archivo/fase; verificación independiente antes de cada commit). **4 commits, ninguno pusheado.**

## Commit `6b534d1` — limpieza de los 8 sucios pre-existentes
Se quitó SOLO la instrumentación de debug temporal (sesión 153429: log a `debug-153429.log` + imports huérfanos `_Path/_json/_time` en backend; `fetch` a `127.0.0.1:7610` con UUID de prueba en frontend), preservando intacto el trabajo legítimo (delegación CP-HUB2, refactor confidencialidad mensaje→POST body, fix jsonb footgun). 3 archivos ya eran 100% legítimos (`ux.py`, `AsistentesSection.tsx`, `api.ts`). Con esto `ux.py` quedó limpio y ya se puede commitear → desbloquea la nota de colisión del inc.2.

## Commit `1f16bd3` — P1+P2: procedencia diferida + folio_ancla real
- **P1 (`ux.py`)**, aplica la nota de colisión del inc.2: `create_matter()` scaffold del workspace (`scaffold_matter_workspace`, alias=UUID del asunto, threadpool no-fatal, solo `kind=='asunto'`); `upload_document()`→`procedencia='documento'`; `create_output()`→`procedencia='inferido'` (origin='mia', NUNCA 'documento').
- **P2 (folio real)**: `extract._assemble_body` devuelve `folio_map` (folio,ini,fin) contado sobre el cuerpo ensamblado real (evita desalineación por notas OCR/truncado); `ingest.chunk_text_with_folios()` NUEVA sin tocar la firma de `chunk_text` (la usan 5 llamadores); el chunk hereda el folio de su offset de inicio. Cableado en `ux.py::upload_document` + los 3 connectores. Fuentes sin páginas (.txt/.docx/.md, cuerpo de correo) → folio NULL (nunca inventa).

## Commit `a0bde00` — P4: ficha-loader + loops del día
- **ficha-loader** (`onboarding/ficha_loader.py`): lee ficha.md+HANDOFF.md+bitácora del expediente (alias=UUID, vía `workspace.py`), trunca por unidad semántica bajo presupuesto, fail-soft. Enganchado en `agents/graph.py::_matter_context_for` (tier CONTEXT no cacheado) → inyecta la memoria del caso a los 7 nodos sin alterar el orden de capas.
- **`/daily`** (`GET /api/matters/{id}/daily`, router `sessions.py`): briefing determinista sin LLM; "Requiere tu decisión" arriba, refs #N.
- **`/cierre`** (`POST .../cierre`): destila SOLO las intervenciones del abogado con cadena barata; escribe durables a `bitacora/cierre-*` y decisiones abiertas a bloque "Pendiente de tu decisión" separado en HANDOFF.md; si nada durable → `written:false` (no fabrica). Cierre automático: mismo endpoint `{auto:true}` gateado al ~65% de llenado, disparado por el frontend tras cada turno (una vez por sesión).
- **Frontend**: botones "Arrancar el día"/"Cerrar por hoy" + DiarioDialog/CierreDialog en lenguaje llano.
- **TODO documentado**: el cierre-auto backend-side no se cablea porque el checkpoint se borra al cerrar el turno (no hay medidor de llenado en backend); el frontend tiene el medidor real. Si el runner conserva transcript persistente en el futuro, invocar `session_briefing.maybe_auto_cierre`. NO se inventó cron (regla dura).

## Commit `f27aa1f` — P3: clasificador de metadata (infiere y marca la duda)
Decisión de Pipe: MIA infiere tipo/parte/folio_radicado/fecha y **marca la duda** en una **lista propia "Documentos por confirmar"** (no la Pantalla 4), confirmación **campo por campo**.
- **046** aditiva: `documents.metadata_sugerida jsonb` + índice parcial; la lista se deriva de `metadata_sugerida IS NOT NULL` (una sola verdad, sin flag extra).
- **`llm.py`**: task AUX nuevo `doc_classification` (cadena barata Haiku/mia-local), no locked, propagado a las 4 políticas por el spread.
- **`ingest/classify.py`**: `classify_document()` agnóstico de jurisdicción (tipo/parte texto libre, NUNCA vocabulario de un país), umbral por campo (env `MIA_CLASSIFY_MIN_CONFIANZA`, default 0.7), envuelto en la policy del tenant, fail-soft absoluto; no pisa fecha ya fijada.
- **`jobs/durable.py`**: handler recuperable `classify_document` + persistencia por lista blanca de columnas (jamás interpola claves del modelo); alta confianza→columna real, baja→`metadata_sugerida`; `fecha_documento` con COALESCE (no pisa el dato fidedigno del correo). Encolado fail-soft tras el INSERT en los 5 orígenes reales; EXCLUIDOS `create_output` (origin='mia') y el harness.
- **`api/routes/documents_review.py`**: GET pendientes + POST confirmar/editar un campo (mueve de sugerida a columna; NULL cuando no quedan dudas). **Frontend**: `DocumentosPorConfirmarDialog` (aceptar/corregir por campo).

## Verificación
- **PASÓ (capas 1–2, automática + independiente):** `ast.parse` OK en todos los .py de cada pieza; firma de `chunk_text` intacta; valores de procedencia correctos (`documento`/`inferido`); migración 046 sin colisión (max+1); grep sin vocabulario de país en el clasificador; exclusiones correctas (`create_output` no encola, count 0); los 5 orígenes encolan (1 c/u); router `documents_review` registrado; P1/P2/P4 y CP-HUB2 intactos entre piezas; `git grep` sin residuo de debug.
- **NO verificado (honesto) — capa 3 del dueño:** `test_rls` **no corrido** (requiere DB viva; columnas 045/046 heredan RLS, no se tocó lógica RLS). Migraciones **045+046 no aplicadas a DB real** (corren solas en bootstrap). Clasificador, `/daily`·`/cierre`, cierre-auto y encolado de jobs **no probados E2E en vivo** (necesitan Postgres + `DurableWorker` corriendo). **Frontend sin `next build`** (regla del repo: no correr build). El destilado de `/cierre` usa `task='session_search'` (AUX barato) como vehículo de la cadena Haiku — funcional, aunque semánticamente no es "destilar".

## Qué sigue
Capa 3 de Pipe (E2E en máquina con DB+worker+build): aplicar migraciones, correr `test_rls`, subir un doc por cada origen y verificar clasificación + "Documentos por confirmar", probar los botones del día y el cierre-auto al ~65%. Rama sin push (Pipe aprueba). Retomar leyendo esta entrada + `TRASPASO-MODELO.md`.

---

