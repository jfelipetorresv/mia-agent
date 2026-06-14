-- Mia · 005_playbooks.sql · Módulo 3b — persistencia de playbooks (decisión #18)
-- El Módulo 2b (PlaybookManager) era in-memory; esta tabla le da persistencia para que el
-- Curator (3b) opere sobre playbooks reales y sobrevivan reinicios. Patrón RLS por-tenant
-- estándar (igual que documents/chunks). Migración aplicada por `postgres`. Idempotente.

CREATE EXTENSION IF NOT EXISTS vector;      -- por si se aplica antes que schema.sql
CREATE EXTENSION IF NOT EXISTS pgcrypto;    -- gen_random_uuid()

CREATE TABLE IF NOT EXISTS playbooks (
  id            uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id     uuid NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
  title         varchar(200) NOT NULL,
  summary       text NOT NULL,                 -- 1 línea, para el índice y la similitud
  applies_when  text NOT NULL,                 -- cuándo aplica
  content       text NOT NULL,                 -- cuerpo completo (on-demand)
  status        varchar(20) NOT NULL DEFAULT 'active'
                CHECK (status IN ('active', 'archived', 'draft')),
  usage_count   integer NOT NULL DEFAULT 0,
  last_used_at  timestamptz,                   -- NULL = nunca usado (no se poda por antigüedad)
  embedding     vector(1024),                  -- voyage-law-2 — similitud semántica del Curator
  metadata      jsonb NOT NULL DEFAULT '{}'::jsonb,
  created_at    timestamptz NOT NULL DEFAULT now(),
  updated_at    timestamptz NOT NULL DEFAULT now(),
  CONSTRAINT uq_playbooks_tenant_title UNIQUE (tenant_id, title)
);

CREATE INDEX IF NOT EXISTS idx_playbooks_tenant_status ON playbooks(tenant_id, status);
CREATE INDEX IF NOT EXISTS idx_playbooks_embedding
  ON playbooks USING hnsw (embedding vector_cosine_ops);

-- ===================== RLS (patrón estándar por-tenant) =====================
ALTER TABLE playbooks ENABLE ROW LEVEL SECURITY;
ALTER TABLE playbooks FORCE  ROW LEVEL SECURITY;

DROP POLICY IF EXISTS p_playbooks ON playbooks;
CREATE POLICY p_playbooks ON playbooks
  USING (tenant_id = app_current_tenant())
  WITH CHECK (tenant_id = app_current_tenant());

GRANT SELECT, INSERT, UPDATE, DELETE ON playbooks TO mia_app;
