-- 054 · Jurisdicción activa por asunto.
-- [] significa "hereda la selección de la firma u organización" para mantener
-- compatibilidad con los asuntos existentes. Una lista no vacía es el subconjunto elegido
-- expresamente para ese asunto; la API impide que introduzca países ajenos al perfil.
ALTER TABLE matters
  ADD COLUMN IF NOT EXISTS jurisdictions jsonb NOT NULL DEFAULT '[]'::jsonb;

ALTER TABLE matters DROP CONSTRAINT IF EXISTS ck_matters_jurisdictions_array;
ALTER TABLE matters ADD CONSTRAINT ck_matters_jurisdictions_array
  CHECK (jsonb_typeof(jurisdictions) = 'array');

CREATE INDEX IF NOT EXISTS idx_matters_jurisdictions
  ON matters USING gin (jurisdictions);
