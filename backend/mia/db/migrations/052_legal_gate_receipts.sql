-- P0 · Recibos inmutables: cada gate decide sobre UNA huella de contenido.
CREATE TABLE IF NOT EXISTS legal_gate_receipts (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id uuid NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
  matter_id uuid NOT NULL REFERENCES matters(id) ON DELETE CASCADE,
  artifact_hash char(64) NOT NULL,
  gate_name varchar(64) NOT NULL,
  passed boolean NOT NULL,
  evidence jsonb NOT NULL DEFAULT '{}'::jsonb,
  created_at timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_legal_gate_receipts_lookup
  ON legal_gate_receipts(tenant_id, matter_id, artifact_hash, gate_name, created_at DESC);

ALTER TABLE legal_gate_receipts ENABLE ROW LEVEL SECURITY;
ALTER TABLE legal_gate_receipts FORCE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS p_legal_gate_receipts ON legal_gate_receipts;
CREATE POLICY p_legal_gate_receipts ON legal_gate_receipts
  USING (tenant_id = app_current_tenant())
  WITH CHECK (tenant_id = app_current_tenant());
GRANT SELECT, INSERT ON legal_gate_receipts TO mia_app;
