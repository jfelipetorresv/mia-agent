-- Mia · 012_curator_proposals.sql · Tarea H.2 — Curator dry-run → HITL (cierra Riesgo #19)
--
-- El Curator (Módulo 3b) fusionaba/podaba playbooks de forma AUTÓNOMA en el cron semanal, sin
-- revisión humana (Riesgo #19: un playbook jurídico podía degradarse sin que nadie lo aprobara).
-- Patrón Hermes v0.17.0 (dry-run → propuesta → HITL): el Curator ahora PROPONE (no ejecuta) y un
-- abogado aprueba/rechaza. Esta tabla persiste esas propuestas.
--
--   curator_proposals — una propuesta de curación por corrida-dry-run y tenant.
--     proposed_merges    : [{source_ids:[uuid,uuid], target_title, reason}]
--     proposed_deletions : [{id, title, reason}]
--     snapshot_hash      : hash del estado de playbooks al proponer (detecta drift antes de aplicar)
--     snapshot           : estado completo de playbooks activos, guardado AL APROBAR (rollback/audit)
--     status             : pending → approved | rejected | failed
--
-- Patrón RLS por-tenant estándar. Migración por `postgres` (mia_app NO tiene CREATE). Idempotente.

CREATE EXTENSION IF NOT EXISTS pgcrypto;    -- gen_random_uuid()

CREATE TABLE IF NOT EXISTS curator_proposals (
  id                 uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id          uuid NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
  proposed_merges    jsonb NOT NULL DEFAULT '[]'::jsonb,
  proposed_deletions jsonb NOT NULL DEFAULT '[]'::jsonb,
  snapshot_hash      varchar(64) NOT NULL,
  snapshot           jsonb,                      -- NULL hasta que se aprueba (estado pre-ejecución)
  stats              jsonb NOT NULL DEFAULT '{}'::jsonb,
  status             varchar(20) NOT NULL DEFAULT 'pending'
                     CHECK (status IN ('pending', 'approved', 'rejected', 'failed')),
  reviewed_at        timestamptz,
  reviewed_by        varchar(200),
  created_at         timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_curator_proposals_tenant_status
  ON curator_proposals(tenant_id, status);

-- ===================== RLS (patrón estándar por-tenant) =====================
ALTER TABLE curator_proposals ENABLE ROW LEVEL SECURITY;
ALTER TABLE curator_proposals FORCE  ROW LEVEL SECURITY;

DROP POLICY IF EXISTS p_curator_proposals ON curator_proposals;
CREATE POLICY p_curator_proposals ON curator_proposals
  USING (tenant_id = app_current_tenant())
  WITH CHECK (tenant_id = app_current_tenant());

GRANT SELECT, INSERT, UPDATE ON curator_proposals TO mia_app;
