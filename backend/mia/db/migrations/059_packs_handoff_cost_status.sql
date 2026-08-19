-- Packs de turno, traspaso de asunto, fact-pack por hash, medición honesta de costo.

ALTER TABLE turn_usage
  ADD COLUMN IF NOT EXISTS cost_status varchar(16) NOT NULL DEFAULT 'medido';

COMMENT ON COLUMN turn_usage.cost_status IS
  'medido = tarifa conocida; estimado = alias sin precio (tarifa conservadora); no_medida = suscripción/local, no fingir USD=0.';

CREATE TABLE IF NOT EXISTS matter_handoffs (
  tenant_id uuid NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
  matter_id uuid NOT NULL REFERENCES matters(id) ON DELETE CASCADE,
  ficha jsonb NOT NULL DEFAULT '{}'::jsonb,
  updated_at timestamptz NOT NULL DEFAULT now(),
  PRIMARY KEY (tenant_id, matter_id)
);

ALTER TABLE matter_handoffs ENABLE ROW LEVEL SECURITY;
ALTER TABLE matter_handoffs FORCE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS p_matter_handoffs ON matter_handoffs;
CREATE POLICY p_matter_handoffs ON matter_handoffs
  USING (tenant_id = app_current_tenant())
  WITH CHECK (tenant_id = app_current_tenant());
GRANT SELECT, INSERT, UPDATE, DELETE ON matter_handoffs TO mia_app;

CREATE TABLE IF NOT EXISTS matter_document_facts (
  tenant_id uuid NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
  matter_id uuid NOT NULL REFERENCES matters(id) ON DELETE CASCADE,
  doc_hash char(64) NOT NULL,
  hechos jsonb NOT NULL DEFAULT '[]'::jsonb,
  updated_at timestamptz NOT NULL DEFAULT now(),
  PRIMARY KEY (tenant_id, matter_id, doc_hash)
);

ALTER TABLE matter_document_facts ENABLE ROW LEVEL SECURITY;
ALTER TABLE matter_document_facts FORCE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS p_matter_document_facts ON matter_document_facts;
CREATE POLICY p_matter_document_facts ON matter_document_facts
  USING (tenant_id = app_current_tenant())
  WITH CHECK (tenant_id = app_current_tenant());
GRANT SELECT, INSERT, UPDATE, DELETE ON matter_document_facts TO mia_app;
