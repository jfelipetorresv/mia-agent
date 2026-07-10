-- Mia · 030_persona_playbooks.sql · Bloque C (evolución de producto) — guías vinculadas a un agente
--
-- Un "agente jurídico" (persona, tabla 023) puede PRIORIZAR un conjunto de guías del despacho
-- (playbooks, tabla 005): cuando ese agente trabaja un turno, sus guías vinculadas activas se
-- inyectan PRIMERO. Esta tabla es el vínculo N—N entre `personas` y `playbooks`, con `position`
-- para conservar el orden que el abogado eligió. Tabla nueva y vacía: sin backfill.
--
-- Patrón RLS calcado de 029_playbook_versions.sql: FKs dobles ON DELETE CASCADE (si se borra el
-- agente o la guía, el vínculo se va solo), índices por tenant y por tenant+persona, ENABLE +
-- FORCE + política ALL con app_current_tenant(), GRANT a mia_app. Migración por `postgres`
-- (execution/init_persona_playbooks.py). Idempotente.

CREATE TABLE IF NOT EXISTS persona_playbooks (
  id           uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id    uuid NOT NULL REFERENCES tenants(id)   ON DELETE CASCADE,
  persona_id   uuid NOT NULL REFERENCES personas(id)  ON DELETE CASCADE,
  playbook_id  uuid NOT NULL REFERENCES playbooks(id) ON DELETE CASCADE,
  position     int  NOT NULL DEFAULT 0,   -- orden elegido por el abogado (0 = primera)
  created_at   timestamptz NOT NULL DEFAULT now(),
  UNIQUE (tenant_id, persona_id, playbook_id)
);

CREATE INDEX IF NOT EXISTS idx_persona_playbooks_tenant
  ON persona_playbooks(tenant_id);
CREATE INDEX IF NOT EXISTS idx_persona_playbooks_tenant_persona
  ON persona_playbooks(tenant_id, persona_id);

ALTER TABLE persona_playbooks ENABLE ROW LEVEL SECURITY;
ALTER TABLE persona_playbooks FORCE  ROW LEVEL SECURITY;
DROP POLICY IF EXISTS p_persona_playbooks ON persona_playbooks;
CREATE POLICY p_persona_playbooks ON persona_playbooks
  USING (tenant_id = app_current_tenant())
  WITH CHECK (tenant_id = app_current_tenant());
GRANT SELECT, INSERT, UPDATE, DELETE ON persona_playbooks TO mia_app;
