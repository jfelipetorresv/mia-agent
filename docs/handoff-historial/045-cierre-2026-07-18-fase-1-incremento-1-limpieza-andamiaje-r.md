# CIERRE — 2026-07-18, Fase 1 · incremento 1 — limpieza + andamiaje (rama, sin push)

## Qué se hizo
Un solo escritor secuencial sobre rama nueva **`feat/fase1-inc1-cleanup-scaffolding`** (partió de
`feature/robustecimiento-sin-aws`; **sin push**). El árbol traía 8 archivos modificados pre-existentes
(mailbox/stream/ux/dreams + 4 de frontend) — se dejaron **intactos y sin commitear** (no eran de este
encargo). Dos bloques:

**A · Limpieza conservadora (solo evidencia positiva de código muerto).**
- Borradas 4 carpetas **huérfanas sólo-`__pycache__`** (sin `.py` fuente, 0 imports vivos, gitignored):
  `backend/mia/{voice,tools,tasks,audit}/` — reemplazadas hace tiempo por `speech/`, `jobs`+`missions`,
  `observability/audit.py`+`security/redact.py`. Cruft de disco; no tocan git ni runtime.
- Borrado `frontend/app/_components/MatterDriveFolder.tsx` (componente default-export con **0 imports**
  en todo el frontend; nunca se cableó). Único borrado que sí es cambio de git.
- **NO se borró** (queda para decisión del dueño): todas las referencias `hermes` (conector VIVO del
  Agent Hub + aserción de seguridad en `test_secret_scope` + ~30 docstrings de atribución MIT), y
  `rag/ingest_corpus.py` (deprecado pero fixture vivo de `test_sat_graph` + semilla opt-in de packs).
  Ninguno es código muerto. (Las menciones documentales `jarvis`/OpenJarvis se removieron en inc.2.)

**B · Andamiaje Fase 1 (aditivo e idempotente).**
- **Migración `045_fase1_document_provenance.sql`** — ADITIVA. Se descubrió que `documents`/`chunks`
  (Módulo 0) YA existen con `matter_id`, `embedding vector(1024)` y RLS. **Crear tablas `document`/`chunk`
  nuevas habría DUPLICADO** → en su lugar `ALTER TABLE ... ADD COLUMN IF NOT EXISTS`:
  documents += `tipo, folio_radicado, parte, fecha_documento`; chunks += `folio_ancla` + **`procedencia`**
  (`varchar(16)` CHECK `{fidedigno|documento|inferido}` default `documento`) + índice parcial. Campos ya
  existentes se MAPEARON (ruta_fuente→`source_path`, hash→`sha256`, texto_verbatim→`content`), no se
  re-crearon. `tipo`/`parte` texto libre (agnóstico de jurisdicción, sin dominio de país).
- **`backend/mia/onboarding/workspace.py`** — genera en disco (bajo `$MIA_HOME/despachos/<tenant>/`,
  reusando `_safe_tenant`) el árbol que SEPARA estado-de-Mia de fuente: `.mia/` (despacho.md,
  baseline-<fecha>.md, aprendizajes.md PINNED, memoria/INDICE.md) y `expedientes/<alias>/` (ficha.md,
  HANDOFF.md, bitacora/ inbox/ **fuente/** [verbatim inmutable, con LEEME] fichas/ _archivo/). Puro
  (config+stdlib), idempotente, no-destructivo. `extra_carpetas` deja al pack del despacho inyectar
  carpetas jurídicas propias sin hardcodear ningún país.
- **`execution/test_workspace.py`** — gate offline del andamiaje.

## Decisiones del dueño aplicadas (2026-07-18)
Caso demo cerrado/didáctico; cross-matter proactivo (solo argumento abstraído, jamás hechos de cliente,
logueado+HITL); auto solo lo trivial al destilar; allowlist permissive. (El grueso de estas decisiones
aterriza en el **incremento 2** — pipeline de ingesta; el inc.1 dejó el andamiaje que las soporta.)

## Verificación
- **PASÓ:** `test_workspace` **22/22**; HALT `check_env_pins` **10/10**; import de `mia.onboarding.workspace`
  limpio; cleanup verificado por grep (0 imports de los 4 paquetes borrados y de `MatterDriveFolder`).
- **NO verificado (honesto):** migración 045 **no aplicada a DB viva** (idempotente; se aplica sola en el
  próximo `db_bootstrap`/arranque — es capa 3 del dueño; no se levantó la DB portable a propósito).
  `test_rls` **no corrido** (requiere DB viva; el cambio no toca superficie RLS). `tsc`/`next build` del
  frontend **no corridos** (repo pesado, riesgo de cuelgue; el borrado es un archivo sin referencias →
  probado por grep). Regresión completa NO corrida (regla: por tramos).

## Qué sigue — incremento 2
Pipeline de **ingesta → ficha → loops**: cablear `scaffold_despacho_workspace` en el onboarding y
`scaffold_matter_workspace` al crear un asunto; poblar `procedencia`/`folio_ancla`/`tipo` en la ingesta;
aplicar la 045 en vivo y añadir su check al gate del instalador (`/health` migraciones esperadas). Retomar
leyendo esta entrada + `TRASPASO-MODELO.md`; la rama `feat/fase1-inc1-cleanup-scaffolding` está sin push.

---

