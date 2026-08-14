-- P0 · Evidencia durable, append-only y ligada a la huella del documento.
CREATE TABLE IF NOT EXISTS legal_artifact_ledger (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id uuid NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
  matter_id uuid NOT NULL REFERENCES matters(id) ON DELETE CASCADE,
  artifact_kind varchar(32) NOT NULL CHECK (artifact_kind IN ('draft', 'attorney_edited', 'final')),
  content text NOT NULL,
  content_hash char(64) NOT NULL,
  parent_hash char(64),
  trace_id text,
  metadata jsonb NOT NULL DEFAULT '{}'::jsonb,
  created_at timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_legal_artifact_ledger_matter
  ON legal_artifact_ledger(tenant_id, matter_id, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_legal_artifact_ledger_hash
  ON legal_artifact_ledger(tenant_id, matter_id, content_hash);
CREATE UNIQUE INDEX IF NOT EXISTS uq_legal_artifact_ledger_version
  ON legal_artifact_ledger(tenant_id, matter_id, artifact_kind, content_hash, COALESCE(parent_hash, ''));

ALTER TABLE legal_artifact_ledger ENABLE ROW LEVEL SECURITY;
ALTER TABLE legal_artifact_ledger FORCE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS p_legal_artifact_ledger ON legal_artifact_ledger;
CREATE POLICY p_legal_artifact_ledger ON legal_artifact_ledger
  USING (tenant_id = app_current_tenant())
  WITH CHECK (tenant_id = app_current_tenant());
GRANT SELECT, INSERT ON legal_artifact_ledger TO mia_app;
