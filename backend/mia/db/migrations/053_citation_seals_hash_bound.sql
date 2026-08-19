-- P0 · Un sello no es una autorización global: fija fuente, pasaje y artefacto que lo originó.
ALTER TABLE citation_seals
  ADD COLUMN IF NOT EXISTS source_passage_hash char(64) NOT NULL DEFAULT '',
  ADD COLUMN IF NOT EXISTS artifact_hash char(64) NOT NULL DEFAULT '',
  ADD COLUMN IF NOT EXISTS jurisdiction_codes text[] NOT NULL DEFAULT '{}';

CREATE INDEX IF NOT EXISTS idx_citation_seals_artifact
  ON citation_seals(tenant_id, artifact_hash)
  WHERE artifact_hash <> '';

-- Sellos v1 sin pasaje, versión o jurisdicción nunca califican para reutilización.
UPDATE citation_seals
SET source_passage_hash = '', artifact_hash = '', jurisdiction_codes = '{}'
WHERE source_passage_hash = '' OR artifact_hash = '' OR cardinality(jurisdiction_codes) = 0;
