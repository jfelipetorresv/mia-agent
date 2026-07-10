-- Mia · 028_projects_multifolder.sql · PROYECTOS + MULTI-CARPETA (Bloque A · evolución de producto)
--
-- Cimientos del Bloque A: la pestaña "Proyectos" reusa matters (kind discrimina) y los
-- documentos ganan procedencia POR FUENTE (source_id) para permitir varias carpetas por
-- asunto/proyecto sin poda cruzada.
--
-- Cuatro cambios de esquema, todos idempotentes:
--
--   matters   +kind — 'asunto' (expediente jurídico formal, comportamiento actual) o
--             'proyecto' (espacio de trabajo libre conectado a carpetas, sin
--             diagnóstico/borrador/HITL). Todo lo existente queda como 'asunto'.
--
--   documents +source_id — de qué fuente vinculada vino el documento (sin FK dura:
--             discrimina origin='folder' → local_folder_sources y origin='drive' →
--             remote_drive_sources; una FK a dos tablas no es posible). Con esto la
--             poda del sync de una carpeta deja de tocar los documentos de otra
--             (bug latente de poda cruzada, ver memory/bugs-and-risks.md).
--             Índice (matter_id, source_id) para ingesta/poda/conteo por fuente.
--
--   documents +body — texto completo SOLO para origin='mia' (archivos producidos por
--             Mia en un proyecto): los chunks llevan overlap y no se pueden
--             reconstruir; la descarga .docx necesita el texto íntegro.
--
--   ck_documents_origin gana 'mia' — lo que Mia produce y el abogado guarda en el
--             proyecto entra al mismo pipeline (chunk+embed) y es consultable después.
--
-- Backfill: los documentos origin='folder' existentes se asignan a la fuente
-- kind='matters' de su expediente SOLO cuando la procedencia es inequívoca (el
-- expediente tiene exactamente UNA fuente en su historial). Un expediente que vinculó
-- y desvinculó carpetas distintas conserva sus documentos con source_id NULL: la poda
-- por fuente NUNCA los toca (protección conservadora) — atribuirlos a la fuente
-- equivocada haría que el sync de esa carpeta los borrara en silencio.
--
-- RLS: no se agregan tablas — matters y documents ya tienen su política fail-closed
-- (schema.sql). Migración aplicada por `postgres` (execution/init_projects_multifolder.py).
-- Idempotente: se puede re-ejecutar.

-- ── matters: discriminador asunto/proyecto ────────────────────────────────────
ALTER TABLE matters ADD COLUMN IF NOT EXISTS kind varchar(20) NOT NULL DEFAULT 'asunto';

DO $$
BEGIN
  IF NOT EXISTS (
    SELECT 1 FROM pg_constraint
    WHERE conname = 'ck_matters_kind'
      AND conrelid = 'public.matters'::regclass
  ) THEN
    ALTER TABLE matters
      ADD CONSTRAINT ck_matters_kind CHECK (kind IN ('asunto', 'proyecto'));
  END IF;
END $$;

CREATE INDEX IF NOT EXISTS idx_matters_tenant_kind ON matters(tenant_id, kind);

-- ── documents: procedencia por fuente + cuerpo de los archivos de Mia ─────────
ALTER TABLE documents ADD COLUMN IF NOT EXISTS source_id uuid;
ALTER TABLE documents ADD COLUMN IF NOT EXISTS body      text;

CREATE INDEX IF NOT EXISTS idx_documents_matter_source ON documents(matter_id, source_id);

-- origin gana 'mia' (drop+add: un CHECK no se puede ampliar in situ).
ALTER TABLE documents DROP CONSTRAINT IF EXISTS ck_documents_origin;
ALTER TABLE documents
  ADD CONSTRAINT ck_documents_origin
  CHECK (origin IN ('upload', 'folder', 'mail', 'drive', 'mia'));

-- ── backfill: docs de carpeta → la fuente de su expediente (solo si es única) ─
-- HAVING count(*) = 1: procedencia inequívoca. Los expedientes con varias fuentes en
-- su historial (p. ej. vinculó A, desvinculó, vinculó B) quedan con source_id NULL a
-- propósito: NULL nunca se poda, así no se pierde nada por atribución equivocada.
-- (array_agg(id))[1] y no min(id): Postgres no tiene min/max nativo para uuid; con
-- HAVING count(*)=1 el resultado es idéntico (un solo candidato por grupo).
UPDATE documents d
SET source_id = sub.id
FROM (
  SELECT matter_id, (array_agg(id))[1] AS id
  FROM local_folder_sources
  WHERE kind = 'matters' AND matter_id IS NOT NULL
  GROUP BY matter_id
  HAVING count(*) = 1
) sub
WHERE d.origin = 'folder'
  AND d.source_id IS NULL
  AND d.matter_id = sub.matter_id;

-- GRANTs coherentes con los existentes (idempotentes, por claridad tras el ALTER).
GRANT SELECT, INSERT, UPDATE, DELETE ON matters   TO mia_app;
GRANT SELECT, INSERT, UPDATE, DELETE ON documents TO mia_app;

-- ── backfill drive: docs de OneDrive → la fuente de su expediente (solo si es única) ──
-- Espejo EXACTO del backfill de 'folder' de arriba, para origin='drive' contra
-- remote_drive_sources (H11 · poda cruzada de OneDrive). Antes de este fix, la poda de
-- RemoteDriveSync solo filtraba por matter_id (nunca por source_id, que no existía para
-- drive), así que un expediente con DOS carpetas de OneDrive vinculadas veía cómo el sync
-- de una borraba en silencio los documentos que trajo la otra. HAVING count(*) = 1:
-- procedencia inequívoca. Los expedientes con varias fuentes drive en su historial (p. ej.
-- vinculó A, desvinculó, vinculó B) quedan con source_id NULL a propósito: NULL nunca se
-- poda (ver `_prune_matter_docs` en graph_drive.py), así no se pierde nada por atribución
-- equivocada.
-- Nota: se usa (array_agg(id))[1] en vez de min(id) — Postgres no tiene min/max nativo
-- para uuid ("function min(uuid) does not exist"). Con HAVING count(*)=1 da exactamente
-- el mismo resultado (solo hay UN candidato por grupo), sin depender de un agregado que
-- este motor no soporta.
UPDATE documents d
SET source_id = sub.id
FROM (
  SELECT matter_id, (array_agg(id))[1] AS id
  FROM remote_drive_sources
  WHERE kind = 'matters' AND matter_id IS NOT NULL
  GROUP BY matter_id
  HAVING count(*) = 1
) sub
WHERE d.origin = 'drive'
  AND d.source_id IS NULL
  AND d.matter_id = sub.matter_id;
