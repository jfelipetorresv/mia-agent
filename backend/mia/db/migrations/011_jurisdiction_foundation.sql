-- Mia · 011_jurisdiction_foundation.sql · Fase 0.C — base multi-jurisdicción + auditoría
--
-- Hace la jurisdicción un eje de primera clase y habilita el versionado temporal de normas,
-- más la tabla de auditoría que sostiene la postura conservadora-auditable.
--
--   1) legal_norms  — jurisdicción canónica (colombia->co) + clave única que incluye
--      jurisdiction y effective_date (antes el upsert sobrescribía la versión previa y
--      destruía la historia → imposible "norma vigente a la fecha de los hechos").
--   2) jurisprudence — columna jurisdiction propia (antes solo via norm_id) + clave con
--      jurisdicción (evita colisión de homónimos entre países).
--   3) matters       — pending_review (flag de borrador esperando revisión).
--   4) audit_logs    — NUEVA, RLS por-tenant, append-only (insert/select; sin update/delete).
--
-- Migración por `postgres` (mia_app NO tiene CREATE/ALTER). Idempotente: re-ejecutable.

CREATE EXTENSION IF NOT EXISTS pgcrypto;   -- gen_random_uuid()

-- ============ 1 · legal_norms: jurisdicción canónica + versionado temporal ============
-- Backfill de código largo a canónico corto (co). Futuros: mexico->mx, argentina->ar, espana->es.
UPDATE legal_norms SET jurisdiction = 'co' WHERE lower(jurisdiction) IN ('colombia', 'co');
ALTER TABLE legal_norms ALTER COLUMN jurisdiction SET DEFAULT 'co';

-- Nueva clave de upsert: jurisdiction evita colisión entre países; effective_date permite
-- conservar versiones temporales de la misma norma (vigente vs. la que regía a la fecha).
ALTER TABLE legal_norms DROP CONSTRAINT IF EXISTS uq_legal_norms_number_body;
ALTER TABLE legal_norms DROP CONSTRAINT IF EXISTS uq_legal_norms_jur_number_body_eff;
ALTER TABLE legal_norms ADD CONSTRAINT uq_legal_norms_jur_number_body_eff
  UNIQUE (jurisdiction, norm_number, issuing_body, effective_date);

CREATE INDEX IF NOT EXISTS idx_legal_norms_jurisdiction ON legal_norms(jurisdiction);

-- ============ 2 · jurisprudence: jurisdicción propia ============
ALTER TABLE jurisprudence ADD COLUMN IF NOT EXISTS jurisdiction varchar(50);
-- Backfill: desde la norma vinculada; lo que quede sin norma asume 'co' (seed colombiano).
UPDATE jurisprudence j SET jurisdiction = n.jurisdiction
  FROM legal_norms n WHERE j.norm_id = n.id AND j.jurisdiction IS NULL;
UPDATE jurisprudence SET jurisdiction = 'co' WHERE jurisdiction IS NULL;
ALTER TABLE jurisprudence ALTER COLUMN jurisdiction SET NOT NULL;
ALTER TABLE jurisprudence ALTER COLUMN jurisdiction SET DEFAULT 'co';

ALTER TABLE jurisprudence DROP CONSTRAINT IF EXISTS uq_jurisprudence_decision_court;
ALTER TABLE jurisprudence DROP CONSTRAINT IF EXISTS uq_jurisprudence_jur_decision_court;
ALTER TABLE jurisprudence ADD CONSTRAINT uq_jurisprudence_jur_decision_court
  UNIQUE (jurisdiction, decision_number, court);

CREATE INDEX IF NOT EXISTS idx_jurisprudence_jurisdiction ON jurisprudence(jurisdiction);

-- ============ 3 · matters: pending_review ============
ALTER TABLE matters ADD COLUMN IF NOT EXISTS pending_review boolean NOT NULL DEFAULT false;

-- ============ 4 · audit_logs (NUEVA · postura conservadora-auditable) ============
-- Registra la confirmación humana de plazos, la etiqueta "verificado" y acciones sensibles.
-- Append-only: mia_app puede INSERT/SELECT, no UPDATE/DELETE (el registro no se altera).
CREATE TABLE IF NOT EXISTS audit_logs (
  id          uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id   uuid NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
  user_email  varchar(200),
  action      varchar(60) NOT NULL,
  entity_type varchar(60),
  entity_id   varchar(200),
  payload     jsonb NOT NULL DEFAULT '{}'::jsonb,
  created_at  timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_audit_logs_tenant_created ON audit_logs(tenant_id, created_at DESC);

ALTER TABLE audit_logs ENABLE ROW LEVEL SECURITY;
ALTER TABLE audit_logs FORCE  ROW LEVEL SECURITY;
DROP POLICY IF EXISTS p_audit_logs ON audit_logs;
CREATE POLICY p_audit_logs ON audit_logs
  USING (tenant_id = app_current_tenant())
  WITH CHECK (tenant_id = app_current_tenant());

GRANT SELECT, INSERT ON audit_logs TO mia_app;
