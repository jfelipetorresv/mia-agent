# CIERRE — 2026-07-18, Fase 1 · incremento 2 — Jarvis + cableado ingesta/onboarding (rama, sin push)

## Qué se hizo (un solo escritor; los 8 sucios pre-existentes NO se tocaron ni commitearon)
**A · Limpieza Jarvis (documental).** Removidas las **28 menciones** `jarvis`/`OpenJarvis` (revisión
independiente: **0 código derivado vivo**; la voz se construyó sobre Lexter/Handy MIT, no sobre OpenJarvis;
ninguna atribución Apache 2.0 era legalmente exigible). Edición mínima y quirúrgica en 8 docs: `CLAUDE.md`,
`TRASPASO-MODELO.md`, `HANDOFF.md`, `docs/{analisis-referencias-2026-07, plan-ejecucion-olas}.md`,
`memory/{findings, progress, session-summaries, task_plan}.md`. Se preservaron TODAS las atribuciones
`hermes`/MIT (código realmente incorporado — asunto distinto de Jarvis, no se tocó).

**B · Cableado inc2 (aditivo, en archivos NO-sucios).**
- **Onboarding despacho:** `auth.py::register()` llama `scaffold_despacho_workspace(tenant, despacho_nombre=
  firm_name)` vía `run_in_threadpool`, tras crear la fila del tenant, en `try/except` no-fatal (el disco es
  accesorio; jamás tumba el alta). Idempotente.
- **Procedencia en ingesta (4 de 5 sitios documentales):** `procedencia='documento'` explícito en el INSERT
  a `chunks` de `ingest/ingest.py`, `connectors/local_folders.py`, `connectors/graph_drive.py` y
  `api/routes/matter_mail.py`. (El 5.º — `ux.py::upload_document` — quedó DIFERIDO por colisión, ver abajo.)
- **Quick win metadata:** `matter_mail._ingest_document` puebla `documents.fecha_documento` con la fecha ISO
  del correo (`_parse_mail_date`: parsea YYYY-MM-DD; si no es inequívoca → NULL, **nunca inventa fecha**).
- **/health estructural:** `api/main.py::health()` añade `provenance_ready` (sonda a
  `information_schema.columns`, sin GRANT extra) que exige las 6 columnas de la 045 — el instalador puede
  sumarla al gate de 'ready'.
- **Migración 045:** NO requiere código de aplicación: `setup/paths.migration_paths()` la toma por glob; se
  aplica sola en `first_run` (instalación) y `maintenance.startup` (arranque). Aditiva/idempotente; ya en el bundle.

## COLISIÓN con los 8 sucios (regla "no forzar"): `ux.py`
`ux.py` es uno de los 8 sucios (trae el refactor vivo de delegación CP-HUB2 + POST `/stream`, sin commitear).
Dos cableados de inc2 caen en `ux.py` → **NO se forzaron**: se revirtieron a baseline y `ux.py` quedó EXACTO
como estaba (verificado por grep + py_compile). **Pendiente de aplicar por el dueño al cerrar/limpiar su batch
dirty:**
1. `create_matter()` (solo `kind=='asunto'`): tras el INSERT a `matters`, `await run_in_threadpool(
   scaffold_matter_workspace, tid, str(row[0]), titulo=body.name)` en try/except no-fatal. Imports:
   `from starlette.concurrency import run_in_threadpool` y `from ...onboarding.workspace import
   scaffold_matter_workspace`. alias=UUID; los proyectos ya tienen su propio multifolder.
2. `upload_document()` y `create_output()`: añadir `procedencia` al INSERT de `chunks` — `'documento'` en
   `upload_document` (subida manual, sitio PRINCIPAL) y `'inferido'` en `create_output` (origin='mia',
   contenido PRODUCIDO por Mia, sujeto al gate de citas — NUNCA 'documento').

## Verificación
- **PASÓ:** `test_workspace` **22/22**; HALT `check_env_pins` **10/10**; `py_compile` de los 7 archivos
  editados; import limpio de auth/matter_mail/connectors/ingest + `ux.py` revertido + `_parse_mail_date`
  (ISO→date, no-ISO→None). Grep: 0 menciones jarvis fuera de la nota de esta entrada; 0 marcadores inc2 en `ux.py`.
- **NO verificado (honesto):** `test_rls` **no corrido** (requiere DB viva; las columnas 045 heredan RLS, no
  se tocó lógica RLS) — re-correr en capa 3. 045 **no aplicada a DB viva** (corre sola en bootstrap = capa 3
  del dueño; no se levantó la DB portable). `/health provenance_ready`, `register`+`create_matter` y mail-link
  **no probados en vivo** (necesitan servidor+DB = capa 3). Sin frontend en inc2 → sin `next build`.

## Qué sigue — incremento 3
Aplicar la **nota de colisión de `ux.py`** (arriba) al limpiar los 8 sucios; **folio_ancla real** (mapa
chunk→página en `ingest/extract.py`; hoy NULL — nunca inventar folio); resto de metadata documental
(`tipo`/`parte`/`folio_radicado`) vía clasificador; ficha-loader; loops `/daily`+`/cierre`. Retomar leyendo
esta entrada + `TRASPASO-MODELO.md`. Rama `feat/fase1-inc1-cleanup-scaffolding`, sin push.

---

