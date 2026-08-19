-- Mia · 045_fase1_document_provenance.sql · Fase 1 (incremento 1) — andamiaje del
-- pipeline de ingesta/ficha. Migración ADITIVA e IDEMPOTENTE (ADD COLUMN IF NOT EXISTS).
--
-- ENCAJE CON EL ESQUEMA EXISTENTE (Módulo 0: documents/chunks ya existen, schema.sql):
--   El andamiaje de Fase 1 NO crea tablas nuevas `document`/`chunk`: eso DUPLICARÍA las
--   canónicas `documents`/`chunks` (con matter_id, embedding vector(1024) y RLS por
--   tenant ya vivos). En su lugar añade SOLO las columnas de Fase 1 que faltan. Los
--   campos del diseño que ya existen se MAPEAN a las columnas actuales (no se re-crean):
--     · ruta_fuente     → documents.source_path   (migración 025)
--     · hash            → documents.sha256         (migración 025)
--     · texto_verbatim  → chunks.content           (schema.sql; verbatim del origen)
--   Los que faltan se agregan aquí.
--
-- PROCEDENCIA (una sola columna, decisión del dueño 2026-07-18 + principio "input directo
--   del abogado es fidedigno"): vive en el chunk (la unidad de recuperación y cita
--   verbatim). Dominio cerrado {fidedigno | documento | inferido}:
--     · fidedigno = suministrado directo por el abogado (no se verifica)
--     · documento = extraído de un documento fuente ingerido (default)
--     · inferido  = generado/inferido por Mia (sujeto al gate de citas)
--
-- AGNÓSTICO DE JURISDICCIÓN (regla dura): `tipo` y `parte` son texto libre — NO se cierra
--   su dominio a categorías de un país. Cada despacho/pack los puebla a su criterio.
--
-- Aplicada por `postgres` (mia_app no tiene CREATE/ALTER). Re-ejecutable sin efecto. Las
-- columnas nuevas heredan los GRANT de tabla y las políticas RLS ya vigentes.

-- ── documents: metadatos de procedencia documental (Fase 1) ───────────────────
ALTER TABLE documents ADD COLUMN IF NOT EXISTS tipo           text;  -- tipo documental (libre; agnóstico)
ALTER TABLE documents ADD COLUMN IF NOT EXISTS folio_radicado text;  -- folio / número de radicado
ALTER TABLE documents ADD COLUMN IF NOT EXISTS parte          text;  -- parte procesal (libre; agnóstico)
ALTER TABLE documents ADD COLUMN IF NOT EXISTS fecha_documento date; -- fecha propia del documento (≠ created_at = ingesta)

-- ── chunks: ancla de folio para la cita + procedencia (Fase 1) ────────────────
ALTER TABLE chunks ADD COLUMN IF NOT EXISTS folio_ancla text;  -- folio/página de anclaje del extracto verbatim

ALTER TABLE chunks ADD COLUMN IF NOT EXISTS procedencia varchar(16) NOT NULL DEFAULT 'documento';
ALTER TABLE chunks DROP CONSTRAINT IF EXISTS ck_chunks_procedencia;
ALTER TABLE chunks
  ADD CONSTRAINT ck_chunks_procedencia
  CHECK (procedencia IN ('fidedigno', 'documento', 'inferido'));

-- Índice parcial: recuperar rápido lo que Mia infirió (candidato al gate de citas).
CREATE INDEX IF NOT EXISTS idx_chunks_procedencia
  ON chunks (tenant_id, procedencia)
  WHERE procedencia <> 'documento';
