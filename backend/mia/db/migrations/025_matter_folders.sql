-- Mia · 025_matter_folders.sql · EXPEDIENTE VINCULADO (Pilar C · carpeta del asunto)
--
-- Un asunto (matter) puede tener UNA carpeta del disco/nube vinculada: sus documentos
-- (PDF/Word/txt/md) se indexan solos en las MISMAS tablas del expediente (documents +
-- chunks), con detección incremental por sha256 (reusa local_file_hashes de la 016).
-- No es "conocimiento del despacho" (knowledge_chunks); son las piezas del expediente.
--
-- Dos cambios de esquema, ambos idempotentes:
--
--   documents  +sha256 / +source_path / +origin — para distinguir lo que subió el
--              abogado a mano (origin='upload', comportamiento actual) de lo que trajo
--              la carpeta vinculada (origin='folder', source_path = ruta relativa). El
--              sha256 permite deduplicar en la subida manual y detectar cambios en la
--              carpeta. Índice (tenant_id, matter_id, sha256) para el dedupe.
--
--   local_folder_sources +matter_id — vínculo opcional de una fuente de la allowlist a
--              un asunto. kind='knowledge' deja matter_id NULL (igual que hoy);
--              kind='matters' lo exige. ON DELETE CASCADE: borrar el asunto desvincula
--              la carpeta.
--
-- RLS: no se agregan tablas — documents y local_folder_sources ya tienen su política
-- fail-closed (schema.sql / 016). Migración aplicada por `postgres`
-- (execution/init_matter_folders.py). Idempotente: se puede re-ejecutar.

-- ── documents: procedencia + huella para dedupe/incremental ──────────────────
ALTER TABLE documents ADD COLUMN IF NOT EXISTS sha256      text;
ALTER TABLE documents ADD COLUMN IF NOT EXISTS source_path text;   -- ruta relativa (solo origin='folder')
ALTER TABLE documents ADD COLUMN IF NOT EXISTS origin      text NOT NULL DEFAULT 'upload';

-- origin solo puede ser 'upload' (subida manual) o 'folder' (carpeta vinculada).
-- Constraint con nombre para poder agregarla de forma idempotente.
DO $$
BEGIN
  IF NOT EXISTS (
    SELECT 1 FROM pg_constraint
    WHERE conname = 'ck_documents_origin'
      AND conrelid = 'public.documents'::regclass
  ) THEN
    ALTER TABLE documents
      ADD CONSTRAINT ck_documents_origin CHECK (origin IN ('upload', 'folder'));
  END IF;
END $$;

-- Índice del dedupe de subida manual y de la detección de cambios de la carpeta.
CREATE INDEX IF NOT EXISTS idx_documents_sha256 ON documents(tenant_id, matter_id, sha256);

-- ── local_folder_sources: vínculo opcional a un asunto ───────────────────────
ALTER TABLE local_folder_sources
  ADD COLUMN IF NOT EXISTS matter_id uuid REFERENCES matters(id) ON DELETE CASCADE;

CREATE INDEX IF NOT EXISTS idx_local_folder_sources_matter ON local_folder_sources(matter_id);

-- GRANTs coherentes con los existentes (idempotentes; las tablas ya los tienen desde
-- schema.sql / 016, pero se re-otorgan por claridad tras el ALTER, igual que la 016).
GRANT SELECT, INSERT, UPDATE, DELETE ON documents            TO mia_app;
GRANT SELECT, INSERT, UPDATE, DELETE ON local_folder_sources TO mia_app;
