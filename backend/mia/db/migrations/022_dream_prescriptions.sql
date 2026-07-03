-- Mia · 022_dream_prescriptions.sql · CP-V2 (Ola 4) — auto-diagnóstico prescriptivo
--
-- Memoria de las RECOMENDACIONES del diagnóstico semanal (patrón ClaudeOS
-- dreams/state.json, llevado a Postgres multi-tenant):
--
--   dream_prescriptions — una fila por hallazgo con ID ESTABLE por tenant.
--     `prescription_id` es un slug determinista (mismo problema en semanas
--     distintas = mismo ID) para poder rastrear su edad y NO repetir lo que el
--     abogado ya aceptó o descartó, salvo que la señal reaparezca pasados 30 días.
--     `status`: new (recién detectada) · recurring (sigue apareciendo) ·
--     accepted / dismissed (decisión del abogado, con decided_at).
--     `payload` guarda la última versión completa de la recomendación
--     (título, receta, evidencia, puntaje) — el panel la lee de aquí.
--
-- RLS fail-closed por tenant IGUAL que el resto (ver 017/020/021): ENABLE + FORCE +
-- política ALL con app_current_tenant(). Migración por `postgres`
-- (execution/init_dream_prescriptions.py). Idempotente.

CREATE TABLE IF NOT EXISTS dream_prescriptions (
  id              uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id       uuid NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
  prescription_id varchar(128) NOT NULL,           -- slug estable (p. ej. 'retrabajo-a1b2c3d4')
  status          varchar(16)  NOT NULL DEFAULT 'new'
                  CHECK (status IN ('new', 'recurring', 'accepted', 'dismissed')),
  payload         jsonb NOT NULL DEFAULT '{}'::jsonb,
  first_seen_at   timestamptz NOT NULL DEFAULT now(),
  last_seen_at    timestamptz NOT NULL DEFAULT now(),
  decided_at      timestamptz,                     -- cuándo el abogado aceptó/descartó
  UNIQUE (tenant_id, prescription_id)
);

CREATE INDEX IF NOT EXISTS idx_dream_prescriptions_tenant_status
  ON dream_prescriptions(tenant_id, status);

ALTER TABLE dream_prescriptions ENABLE ROW LEVEL SECURITY;
ALTER TABLE dream_prescriptions FORCE  ROW LEVEL SECURITY;
DROP POLICY IF EXISTS p_dream_prescriptions ON dream_prescriptions;
CREATE POLICY p_dream_prescriptions ON dream_prescriptions
  USING (tenant_id = app_current_tenant())
  WITH CHECK (tenant_id = app_current_tenant());
GRANT SELECT, INSERT, UPDATE, DELETE ON dream_prescriptions TO mia_app;
