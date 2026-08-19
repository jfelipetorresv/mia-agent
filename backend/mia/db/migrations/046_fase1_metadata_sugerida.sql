-- Mia · 046_fase1_metadata_sugerida.sql · Fase 1 — la DUDA del clasificador de metadata.
-- Migración ADITIVA e IDEMPOTENTE (ADD COLUMN IF NOT EXISTS). Re-ejecutable sin efecto.
--
-- CONTEXTO (encaje con 045_fase1_document_provenance.sql):
--   La 045 añadió a `documents` las columnas REALES de la ficha (tipo, folio_radicado,
--   parte, fecha_documento), todas nullable y de texto libre (agnósticas de jurisdicción).
--   El clasificador de ingesta (ingest/classify.py) INFIERE esos campos y, por diseño del
--   dueño (2026-07-18), separa por confianza:
--     · ALTA confianza  → escribe DIRECTO la columna real de 045.
--     · BAJA confianza  → NO toca la columna real; deja el campo como SUGERENCIA aquí, para
--       que el abogado lo confirme campo por campo.
--
-- ESQUEMA DE LA DUDA — `documents.metadata_sugerida` jsonb (NULL = nada pendiente):
--   Guarda SOLO los campos dudosos, cada uno con su valor propuesto y su confianza 0..1:
--     {
--       "tipo":           {"valor": "...", "confianza": 0.55},
--       "parte":          {"valor": "...", "confianza": 0.62},
--       "folio_radicado": {"valor": "...", "confianza": 0.48},
--       "fecha_documento":{"valor": "YYYY-MM-DD", "confianza": 0.60}
--     }
--   Ausencia de una clave = ese campo NO está en duda (o fue de alta confianza y ya está en
--   su columna real, o no se pudo determinar y queda sin valor — NUNCA se inventa).
--   metadata_sugerida NULL o '{}'::jsonb vacío = el documento NO tiene nada por confirmar.
--
-- CÓMO SE LISTA "Documentos por confirmar" (decisión de diseño — la más simple y consistente
--   con el patrón de índice parcial de la 045, `idx_chunks_procedencia`):
--   NO se añade una columna de estado (metadata_status) ni una máquina de estados. El estado
--   "pendiente" se DERIVA del dato mismo: un documento está por confirmar sii tiene dudas,
--   es decir `metadata_sugerida IS NOT NULL`. Confirmar un campo = quitar esa clave del jsonb;
--   confirmar el último campo (o rechazar todo) = poner la columna en NULL y el documento sale
--   de la lista. Una sola fuente de verdad, sin riesgo de que un flag y el jsonb se desincronicen.
--   Un índice parcial hace la lista barata sin pesar sobre las filas ya confirmadas.
--
-- AGNÓSTICO DE JURISDICCIÓN (regla dura): los valores propuestos para `tipo` y `parte` son
--   TEXTO LIBRE inferido por el modelo; este esquema no fija ni valida ningún vocabulario de
--   ningún país.
--
-- Aplicada por `postgres` (mia_app no tiene CREATE/ALTER). La columna nueva HEREDA los GRANT de
-- tabla y las políticas RLS por tenant ya vigentes sobre `documents` (schema.sql): NO se añade
-- política RLS ni GRANT nuevos.

-- ── documents: la duda de baja confianza del clasificador (Fase 1) ─────────────
ALTER TABLE documents ADD COLUMN IF NOT EXISTS metadata_sugerida jsonb;  -- {campo:{valor,confianza}} solo campos dudosos; NULL = nada pendiente

-- Índice parcial: "Documentos por confirmar" recupera rápido solo los que tienen dudas,
-- sin costo sobre las filas ya confirmadas (mismo patrón que idx_chunks_procedencia en la 045).
CREATE INDEX IF NOT EXISTS idx_documents_metadata_pendiente
  ON documents (tenant_id)
  WHERE metadata_sugerida IS NOT NULL;
