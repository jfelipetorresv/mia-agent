-- Mia · 020_automations.sql · CP-P2 (Ola 2) — plantillas de automatización + sugerencias
--
-- El abogado arma automatizaciones a partir de PLANTILLAS rellenables (cron/blueprints.py)
-- y Mia le PROPONE algunas que él acepta o descarta (consent-first, cron/suggestions.py).
--
--   automations — una automatización ACTIVA por fila (creada solo por un acto humano
--     explícito: aceptar una sugerencia o rellenar una plantilla). `is_procedural`
--     marca las que tocan un plazo procesal (regla dura: nunca se auto-activan y jamás
--     calculan un término; al ejecutarse solo superficie fechas que el abogado ya fijó).
--
--   automation_suggestions — propuestas que Mia surface para que el abogado acepte/
--     descarte. `dedup_key` LATCHEA por (tenant, dedup_key): una vez aceptada o descartada,
--     la misma propuesta NO se vuelve a ofrecer. Máx. 5 'pending' se aplica en la app.
--
-- RLS fail-closed por tenant IGUAL que el resto (ver 017_reminders.sql): ENABLE + FORCE
-- + política ALL con app_current_tenant(). Migración por `postgres` (execution/
-- init_automations.py). Idempotente.

CREATE TABLE IF NOT EXISTS automations (
  id             uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id      uuid NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
  blueprint_key  varchar(64) NOT NULL,
  kind           varchar(64) NOT NULL,
  params         jsonb NOT NULL DEFAULT '{}'::jsonb,
  is_procedural  boolean NOT NULL DEFAULT false,   -- toca un plazo procesal → [VERIFICAR]
  enabled        boolean NOT NULL DEFAULT true,
  created_at     timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_automations_tenant ON automations(tenant_id, kind, enabled);

ALTER TABLE automations ENABLE ROW LEVEL SECURITY;
ALTER TABLE automations FORCE  ROW LEVEL SECURITY;
DROP POLICY IF EXISTS p_automations ON automations;
CREATE POLICY p_automations ON automations
  USING (tenant_id = app_current_tenant())
  WITH CHECK (tenant_id = app_current_tenant());
GRANT SELECT, INSERT, UPDATE, DELETE ON automations TO mia_app;


CREATE TABLE IF NOT EXISTS automation_suggestions (
  id             uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id      uuid NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
  blueprint_key  varchar(64) NOT NULL,
  params         jsonb NOT NULL DEFAULT '{}'::jsonb,
  dedup_key      varchar(128) NOT NULL,            -- latch: (tenant, dedup_key) es único
  rationale      text NOT NULL DEFAULT '',         -- por qué Mia lo propone (español)
  status         varchar(16) NOT NULL DEFAULT 'pending'
                 CHECK (status IN ('pending', 'accepted', 'dismissed')),
  created_at     timestamptz NOT NULL DEFAULT now(),
  resolved_at    timestamptz,
  UNIQUE (tenant_id, dedup_key)
);

CREATE INDEX IF NOT EXISTS idx_suggestions_tenant_status
  ON automation_suggestions(tenant_id, status);

ALTER TABLE automation_suggestions ENABLE ROW LEVEL SECURITY;
ALTER TABLE automation_suggestions FORCE  ROW LEVEL SECURITY;
DROP POLICY IF EXISTS p_automation_suggestions ON automation_suggestions;
CREATE POLICY p_automation_suggestions ON automation_suggestions
  USING (tenant_id = app_current_tenant())
  WITH CHECK (tenant_id = app_current_tenant());
GRANT SELECT, INSERT, UPDATE, DELETE ON automation_suggestions TO mia_app;
