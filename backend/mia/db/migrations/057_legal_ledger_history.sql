-- P0 hardening · recibos históricos, contexto verificable y FK tenant↔matter.
DROP INDEX IF EXISTS uq_legal_gate_receipt_once;

ALTER TABLE legal_gate_receipts
  ADD COLUMN IF NOT EXISTS run_id text NOT NULL DEFAULT '',
  ADD COLUMN IF NOT EXISTS trace_id text NOT NULL DEFAULT '',
  ADD COLUMN IF NOT EXISTS checker_version text NOT NULL DEFAULT 'unknown',
  ADD COLUMN IF NOT EXISTS context_hash char(64) NOT NULL DEFAULT '',
  ADD COLUMN IF NOT EXISTS jurisdiction_codes text[] NOT NULL DEFAULT '{}',
  ADD COLUMN IF NOT EXISTS source_hashes text[] NOT NULL DEFAULT '{}',
  ADD COLUMN IF NOT EXISTS event_key char(64);

UPDATE legal_gate_receipts
SET run_id = id::text,
    event_key = encode(digest(id::text || ':' || artifact_hash || ':' || gate_name, 'sha256'), 'hex')
WHERE event_key IS NULL;
ALTER TABLE legal_gate_receipts ALTER COLUMN event_key SET NOT NULL;
CREATE UNIQUE INDEX IF NOT EXISTS uq_legal_gate_receipt_event
  ON legal_gate_receipts(event_key);
CREATE INDEX IF NOT EXISTS idx_legal_gate_receipts_latest
  ON legal_gate_receipts(tenant_id, matter_id, artifact_hash, gate_name, created_at DESC, id DESC);

CREATE TABLE IF NOT EXISTS legal_export_events (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id uuid NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
  matter_id uuid NOT NULL REFERENCES matters(id) ON DELETE CASCADE,
  artifact_hash char(64) NOT NULL,
  export_format varchar(32) NOT NULL,
  actor varchar(64) NOT NULL,
  created_at timestamptz NOT NULL DEFAULT now()
);

CREATE UNIQUE INDEX IF NOT EXISTS uq_matters_tenant_id ON matters(tenant_id, id);
DO $$ BEGIN
  IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname='fk_legal_artifact_matter_tenant') THEN
    ALTER TABLE legal_artifact_ledger ADD CONSTRAINT fk_legal_artifact_matter_tenant
      FOREIGN KEY (tenant_id, matter_id) REFERENCES matters(tenant_id, id) ON DELETE CASCADE;
  END IF;
  IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname='fk_legal_receipt_matter_tenant') THEN
    ALTER TABLE legal_gate_receipts ADD CONSTRAINT fk_legal_receipt_matter_tenant
      FOREIGN KEY (tenant_id, matter_id) REFERENCES matters(tenant_id, id) ON DELETE CASCADE;
  END IF;
  IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname='fk_legal_export_matter_tenant') THEN
    ALTER TABLE legal_export_events ADD CONSTRAINT fk_legal_export_matter_tenant
      FOREIGN KEY (tenant_id, matter_id) REFERENCES matters(tenant_id, id) ON DELETE CASCADE;
  END IF;
END $$;

ALTER TABLE legal_export_events ENABLE ROW LEVEL SECURITY;
ALTER TABLE legal_export_events FORCE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS p_legal_export_events ON legal_export_events;
CREATE POLICY p_legal_export_events ON legal_export_events
  USING (tenant_id=app_current_tenant()) WITH CHECK (tenant_id=app_current_tenant());
GRANT SELECT, INSERT ON legal_export_events TO mia_app;
