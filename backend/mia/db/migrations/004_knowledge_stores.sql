-- Mia · 004_knowledge_stores.sql · Módulo 3c — Obsidian indexer (decisión #17)
-- Dos tablas para el conocimiento del despacho que NO es un expediente:
--   1) knowledge_chunks  — chunks indexados (texto + embedding) del vault Obsidian
--      (y futuros sources: plantillas, jurisprudencia local, notas). Tabla SEPARADA de
--      documents/chunks porque documents.matter_id es NOT NULL — las notas del despacho
--      no pertenecen a un asunto. Patrón RLS por-tenant estándar (igual que chunks).
--   2) obsidian_file_hashes — sha256 por archivo del vault, para indexación incremental.
--
-- Migración aplicada por `postgres` (mia_app NO tiene CREATE). Idempotente: re-ejecutable.
-- NO toca el esquema del Módulo 0 (documents/chunks/tenant_settings intactos).

CREATE EXTENSION IF NOT EXISTS vector;      -- por si se aplica antes que schema.sql
CREATE EXTENSION IF NOT EXISTS pgcrypto;    -- gen_random_uuid()

-- ===================== knowledge_chunks =====================
CREATE TABLE IF NOT EXISTS knowledge_chunks (
  id           uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id    uuid NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
  source       varchar(50) NOT NULL DEFAULT 'obsidian',  -- preparado para otros sources
  source_path  text NOT NULL,                            -- ruta relativa al vault
  chunk_index  integer NOT NULL,
  heading_path text,                                     -- "Contratos > Cláusulas > Indemnización"
  content      text NOT NULL,
  embedding    vector(1024),                             -- voyage-law-2 (decisión #8)
  content_tsv  tsvector GENERATED ALWAYS AS (to_tsvector('spanish', content)) STORED,
  metadata     jsonb NOT NULL DEFAULT '{}'::jsonb,
  created_at   timestamptz NOT NULL DEFAULT now(),
  updated_at   timestamptz NOT NULL DEFAULT now(),
  CONSTRAINT uq_knowledge_chunks UNIQUE (tenant_id, source, source_path, chunk_index)
);

CREATE INDEX IF NOT EXISTS idx_knowledge_chunks_tenant ON knowledge_chunks(tenant_id);
CREATE INDEX IF NOT EXISTS idx_knowledge_chunks_path   ON knowledge_chunks(tenant_id, source, source_path);
CREATE INDEX IF NOT EXISTS idx_knowledge_chunks_tsv    ON knowledge_chunks USING gin(content_tsv);
CREATE INDEX IF NOT EXISTS idx_knowledge_chunks_embed  ON knowledge_chunks USING hnsw (embedding vector_cosine_ops);

-- ===================== obsidian_file_hashes =====================
CREATE TABLE IF NOT EXISTS obsidian_file_hashes (
  id            uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id     uuid NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
  vault_path    text NOT NULL,                           -- ruta relativa al vault
  file_hash     varchar(64) NOT NULL,
  last_indexed  timestamptz NOT NULL DEFAULT now(),
  CONSTRAINT uq_obsidian_file_hashes UNIQUE (tenant_id, vault_path)
);

CREATE INDEX IF NOT EXISTS idx_obsidian_hashes_tenant ON obsidian_file_hashes(tenant_id);

-- ===================== RLS (patrón estándar por-tenant, igual que documents/chunks) =====================
DO $$
DECLARE t text;
BEGIN
  FOREACH t IN ARRAY ARRAY['knowledge_chunks','obsidian_file_hashes'] LOOP
    EXECUTE format('ALTER TABLE %I ENABLE ROW LEVEL SECURITY', t);
    EXECUTE format('ALTER TABLE %I FORCE  ROW LEVEL SECURITY', t);
  END LOOP;
END $$;

DROP POLICY IF EXISTS p_knowledge_chunks ON knowledge_chunks;
CREATE POLICY p_knowledge_chunks ON knowledge_chunks
  USING (tenant_id = app_current_tenant())
  WITH CHECK (tenant_id = app_current_tenant());

DROP POLICY IF EXISTS p_obsidian_file_hashes ON obsidian_file_hashes;
CREATE POLICY p_obsidian_file_hashes ON obsidian_file_hashes
  USING (tenant_id = app_current_tenant())
  WITH CHECK (tenant_id = app_current_tenant());

-- ===================== Grants al rol de aplicación =====================
GRANT SELECT, INSERT, UPDATE, DELETE ON knowledge_chunks, obsidian_file_hashes TO mia_app;
