-- Mia · 006_feedback_proposals.sql · Módulo 3e — Feedback processor (decisión #19)
-- Dos tablas:
--   1) feedback_proposals — propuestas de mejora a playbooks que el processor genera a partir
--      de las señales de las trazas (status='pending' → el abogado las revisa en Pantalla 4).
--   2) processed_traces_watermark — marca por (tenant, día) hasta dónde se procesaron las
--      trazas, para no reanalizarlas (JSONL append-only, sin id estable por línea).
-- Patrón RLS por-tenant estándar. Migración por `postgres`. Idempotente.

CREATE EXTENSION IF NOT EXISTS pgcrypto;    -- gen_random_uuid()

-- ===================== feedback_proposals =====================
CREATE TABLE IF NOT EXISTS feedback_proposals (
  id                 uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id          uuid NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
  proposal_type      varchar(30) NOT NULL
                     CHECK (proposal_type IN ('improve_playbook', 'new_playbook', 'flag_gap')),
  target_playbook_id uuid REFERENCES playbooks(id) ON DELETE SET NULL,   -- NULL = playbook nuevo
  suggested_content  text NOT NULL,
  rationale          text NOT NULL,
  signal_count       integer NOT NULL DEFAULT 1,
  trace_ids          text[],                  -- referencias a las trazas origen
  status             varchar(20) NOT NULL DEFAULT 'pending'
                     CHECK (status IN ('pending', 'approved', 'rejected', 'applied')),
  reviewed_at        timestamptz,
  reviewed_by        varchar(200),
  created_at         timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_feedback_proposals_tenant_status
  ON feedback_proposals(tenant_id, status);

-- ===================== processed_traces_watermark =====================
CREATE TABLE IF NOT EXISTS processed_traces_watermark (
  tenant_id         uuid NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
  trace_date        date NOT NULL,
  last_processed_at timestamptz NOT NULL DEFAULT now(),
  traces_processed  integer NOT NULL DEFAULT 0,
  PRIMARY KEY (tenant_id, trace_date)
);

-- ===================== RLS (patrón estándar por-tenant) =====================
DO $$
DECLARE t text;
BEGIN
  FOREACH t IN ARRAY ARRAY['feedback_proposals','processed_traces_watermark'] LOOP
    EXECUTE format('ALTER TABLE %I ENABLE ROW LEVEL SECURITY', t);
    EXECUTE format('ALTER TABLE %I FORCE  ROW LEVEL SECURITY', t);
  END LOOP;
END $$;

DROP POLICY IF EXISTS p_feedback_proposals ON feedback_proposals;
CREATE POLICY p_feedback_proposals ON feedback_proposals
  USING (tenant_id = app_current_tenant())
  WITH CHECK (tenant_id = app_current_tenant());

DROP POLICY IF EXISTS p_processed_traces_watermark ON processed_traces_watermark;
CREATE POLICY p_processed_traces_watermark ON processed_traces_watermark
  USING (tenant_id = app_current_tenant())
  WITH CHECK (tenant_id = app_current_tenant());

GRANT SELECT, INSERT, UPDATE, DELETE ON feedback_proposals, processed_traces_watermark TO mia_app;
