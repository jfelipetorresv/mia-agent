-- Mia · 034_durable_jobs.sql · trabajos locales recuperables, sin infraestructura externa.

CREATE TABLE IF NOT EXISTS durable_jobs (
  id               uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id        uuid NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
  job_type         varchar(64) NOT NULL,
  payload          jsonb NOT NULL DEFAULT '{}'::jsonb,
  dedupe_key       varchar(200) NOT NULL,
  status           varchar(16) NOT NULL DEFAULT 'queued'
                   CHECK (status IN ('queued', 'running', 'succeeded', 'failed')),
  attempts         integer NOT NULL DEFAULT 0 CHECK (attempts >= 0),
  max_attempts     integer NOT NULL DEFAULT 5 CHECK (max_attempts BETWEEN 1 AND 20),
  available_at     timestamptz NOT NULL DEFAULT now(),
  claimed_at       timestamptz,
  claimed_by       text,
  lease_expires_at timestamptz,
  heartbeat_at     timestamptz,
  started_at       timestamptz,
  finished_at      timestamptz,
  result           jsonb,
  last_error       text,
  created_at       timestamptz NOT NULL DEFAULT now(),
  updated_at       timestamptz NOT NULL DEFAULT now()
);

CREATE UNIQUE INDEX IF NOT EXISTS uq_durable_jobs_active
  ON durable_jobs (tenant_id, job_type, dedupe_key)
  WHERE status IN ('queued', 'running');
CREATE INDEX IF NOT EXISTS idx_durable_jobs_claim
  ON durable_jobs (status, available_at, lease_expires_at, created_at);
CREATE INDEX IF NOT EXISTS idx_durable_jobs_tenant_history
  ON durable_jobs (tenant_id, job_type, dedupe_key, created_at DESC);

ALTER TABLE durable_jobs ENABLE ROW LEVEL SECURITY;
ALTER TABLE durable_jobs FORCE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS p_durable_jobs ON durable_jobs;
CREATE POLICY p_durable_jobs ON durable_jobs
  USING (tenant_id = app_current_tenant())
  WITH CHECK (tenant_id = app_current_tenant());

-- La app solo encola y consulta su propio estado. Reclamar/finalizar es una
-- operación del supervisor local y queda reservada a postgres (BYPASSRLS).
GRANT SELECT, INSERT ON durable_jobs TO mia_app;
