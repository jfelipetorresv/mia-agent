-- Mia · 029_playbook_versions.sql · Bloque B (evolución de producto) — historial de playbooks
--
-- B0 necesita que PUT /api/playbooks/{id} y "aplicar propuesta" dejen de ser destructivos:
-- antes de escribir el nuevo estado se guarda un SNAPSHOT DEL ESTADO ANTERIOR en esta tabla,
-- así el abogado (o Mia) puede volver atrás. `changed_by` distingue si el cambio lo hizo el
-- abogado (edición manual vía PUT) o Mia (propuesta aplicada, aprendizaje automático);
-- `reason` es SIEMPRE una frase en llano (§G), nunca jerga técnica.
--
-- Patrón RLS calcado de 023_personas.sql: ENABLE + FORCE + política ALL con
-- app_current_tenant(), GRANT a mia_app. Migración por `postgres`
-- (execution/init_playbook_versions.py). Idempotente.

CREATE TABLE IF NOT EXISTS playbook_versions (
  id            uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id     uuid NOT NULL REFERENCES tenants(id)   ON DELETE CASCADE,
  playbook_id   uuid NOT NULL REFERENCES playbooks(id) ON DELETE CASCADE,
  title         text NOT NULL,   -- snapshot del estado ANTERIOR al cambio
  summary       text NOT NULL,
  applies_when  text NOT NULL,
  content       text NOT NULL,
  changed_by    varchar(16) NOT NULL CHECK (changed_by IN ('abogado', 'mia')),
  reason        text NOT NULL DEFAULT '', -- en llano: qué motivó el cambio
  created_at    timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_playbook_versions_tenant
  ON playbook_versions(tenant_id);
CREATE INDEX IF NOT EXISTS idx_playbook_versions_tenant_playbook
  ON playbook_versions(tenant_id, playbook_id);

ALTER TABLE playbook_versions ENABLE ROW LEVEL SECURITY;
ALTER TABLE playbook_versions FORCE  ROW LEVEL SECURITY;
DROP POLICY IF EXISTS p_playbook_versions ON playbook_versions;
CREATE POLICY p_playbook_versions ON playbook_versions
  USING (tenant_id = app_current_tenant())
  WITH CHECK (tenant_id = app_current_tenant());
GRANT SELECT, INSERT, UPDATE, DELETE ON playbook_versions TO mia_app;
