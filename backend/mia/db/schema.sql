-- Mia · schema.sql · Módulo 0
-- PostgreSQL 16 + pgvector. Multi-tenant con Row-Level Security (RLS).
-- Aislamiento por tenant vía GUC `app.tenant_id` (FAIL-CLOSED: sin GUC => 0 filas).
-- La aplicación SIEMPRE se conecta como `mia_app` (NOSUPERUSER, NOBYPASSRLS).
-- `postgres` (superusuario) ignora RLS; usar SOLO para migraciones.
-- Idempotente: se puede re-ejecutar.

CREATE EXTENSION IF NOT EXISTS vector;
CREATE EXTENSION IF NOT EXISTS pgcrypto;   -- gen_random_uuid()

-- Tenant actual desde el GUC de sesión/transacción (fail-closed: NULL si no está).
CREATE OR REPLACE FUNCTION app_current_tenant() RETURNS uuid
LANGUAGE sql STABLE AS $$
  SELECT NULLIF(current_setting('app.tenant_id', true), '')::uuid
$$;

-- ===================== Tablas =====================
CREATE TABLE IF NOT EXISTS tenants (
  id          uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  name        text NOT NULL,
  created_at  timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS matters (
  id          uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id   uuid NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
  title       text NOT NULL,
  created_at  timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS documents (
  id          uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id   uuid NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
  matter_id   uuid NOT NULL REFERENCES matters(id) ON DELETE CASCADE,
  filename    text NOT NULL,
  mime        text,
  created_at  timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS chunks (
  id           uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id    uuid NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
  document_id  uuid NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
  ord          int  NOT NULL,
  content      text NOT NULL,
  content_tsv  tsvector GENERATED ALWAYS AS (to_tsvector('spanish', content)) STORED,
  embedding    vector(1024),   -- voyage-law-2 (ver memory/decisions.md #8)
  created_at   timestamptz NOT NULL DEFAULT now()
);

-- Config por tenant (decisión #12). JSONB reutilizable; el Agent Hub (1e) guarda su
-- estado en config->'agent_hub'. Una fila por tenant; aislada por RLS.
CREATE TABLE IF NOT EXISTS tenant_settings (
  tenant_id   uuid PRIMARY KEY REFERENCES tenants(id) ON DELETE CASCADE,
  config      jsonb NOT NULL DEFAULT '{}'::jsonb,
  updated_at  timestamptz NOT NULL DEFAULT now()
);

-- ===================== Índices =====================
CREATE INDEX IF NOT EXISTS idx_matters_tenant   ON matters(tenant_id);
CREATE INDEX IF NOT EXISTS idx_documents_tenant ON documents(tenant_id);
CREATE INDEX IF NOT EXISTS idx_documents_matter ON documents(matter_id);
CREATE INDEX IF NOT EXISTS idx_chunks_tenant    ON chunks(tenant_id);
CREATE INDEX IF NOT EXISTS idx_chunks_document  ON chunks(document_id);
CREATE INDEX IF NOT EXISTS idx_chunks_tsv       ON chunks USING gin(content_tsv);
CREATE INDEX IF NOT EXISTS idx_chunks_embedding ON chunks USING hnsw (embedding vector_cosine_ops);

-- ===================== RLS =====================
-- ENABLE + FORCE en cada tabla; política ALL con USING y WITH CHECK = tenant del GUC.
DO $$
DECLARE t text;
BEGIN
  FOREACH t IN ARRAY ARRAY['tenants','matters','documents','chunks','tenant_settings'] LOOP
    EXECUTE format('ALTER TABLE %I ENABLE ROW LEVEL SECURITY', t);
    EXECUTE format('ALTER TABLE %I FORCE  ROW LEVEL SECURITY', t);
  END LOOP;
END $$;

-- tenants: cada tenant ve/escribe SOLO su propia fila.
DROP POLICY IF EXISTS p_tenants ON tenants;
CREATE POLICY p_tenants ON tenants
  USING (id = app_current_tenant())
  WITH CHECK (id = app_current_tenant());

-- matters / documents / chunks: aislados por tenant_id.
DROP POLICY IF EXISTS p_matters ON matters;
CREATE POLICY p_matters ON matters
  USING (tenant_id = app_current_tenant())
  WITH CHECK (tenant_id = app_current_tenant());

DROP POLICY IF EXISTS p_documents ON documents;
CREATE POLICY p_documents ON documents
  USING (tenant_id = app_current_tenant())
  WITH CHECK (tenant_id = app_current_tenant());

DROP POLICY IF EXISTS p_chunks ON chunks;
CREATE POLICY p_chunks ON chunks
  USING (tenant_id = app_current_tenant())
  WITH CHECK (tenant_id = app_current_tenant());

-- tenant_settings: la PK es tenant_id, así que la política usa esa columna.
DROP POLICY IF EXISTS p_tenant_settings ON tenant_settings;
CREATE POLICY p_tenant_settings ON tenant_settings
  USING (tenant_id = app_current_tenant())
  WITH CHECK (tenant_id = app_current_tenant());

-- ===================== Grants al rol de aplicación =====================
GRANT USAGE ON SCHEMA public TO mia_app;
GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA public TO mia_app;
ALTER DEFAULT PRIVILEGES IN SCHEMA public
  GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO mia_app;
GRANT EXECUTE ON FUNCTION app_current_tenant() TO mia_app;
