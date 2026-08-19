-- Mia · 035_atomic_ai_budget.sql · control local y atómico del gasto de IA.

CREATE TABLE IF NOT EXISTS ai_budget_months (
  tenant_id uuid NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
  period_start date NOT NULL,
  baseline_usd numeric(12,6) NOT NULL DEFAULT 0 CHECK (baseline_usd >= 0),
  spent_usd numeric(12,6) NOT NULL DEFAULT 0 CHECK (spent_usd >= 0),
  reserved_usd numeric(12,6) NOT NULL DEFAULT 0 CHECK (reserved_usd >= 0),
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now(),
  PRIMARY KEY (tenant_id, period_start)
);

CREATE TABLE IF NOT EXISTS ai_budget_holds (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id uuid NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
  period_start date NOT NULL,
  estimated_usd numeric(12,6) NOT NULL CHECK (estimated_usd > 0),
  actual_usd numeric(12,6),
  model varchar(128) NOT NULL,
  task varchar(64),
  status varchar(16) NOT NULL DEFAULT 'active'
    CHECK (status IN ('active', 'settled', 'released', 'expired')),
  expires_at timestamptz NOT NULL,
  created_at timestamptz NOT NULL DEFAULT now(),
  finished_at timestamptz,
  FOREIGN KEY (tenant_id, period_start)
    REFERENCES ai_budget_months(tenant_id, period_start) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_ai_budget_holds_active
  ON ai_budget_holds (tenant_id, period_start, expires_at) WHERE status = 'active';

ALTER TABLE ai_budget_months ENABLE ROW LEVEL SECURITY;
ALTER TABLE ai_budget_months FORCE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS p_ai_budget_months ON ai_budget_months;
CREATE POLICY p_ai_budget_months ON ai_budget_months
  USING (tenant_id = app_current_tenant()) WITH CHECK (tenant_id = app_current_tenant());

ALTER TABLE ai_budget_holds ENABLE ROW LEVEL SECURITY;
ALTER TABLE ai_budget_holds FORCE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS p_ai_budget_holds ON ai_budget_holds;
CREATE POLICY p_ai_budget_holds ON ai_budget_holds
  USING (tenant_id = app_current_tenant()) WITH CHECK (tenant_id = app_current_tenant());

GRANT SELECT, INSERT, UPDATE ON ai_budget_months TO mia_app;
GRANT SELECT, INSERT, UPDATE ON ai_budget_holds TO mia_app;
