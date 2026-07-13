-- Mia · 033_warroom_results.sql · Sala de estrategia (warroom) — dictamen persistido por asunto
--
-- La "Sala de estrategia" reúne un panel de counsel con posturas OPUESTAS que debaten el
-- asunto citando el expediente [doc n]; un moderador sintetiza un dictamen. Esta tabla guarda
-- la ÚLTIMA convocatoria por asunto (una fila por asunto: la nueva sesión PISA la anterior vía
-- upsert sobre (tenant_id, matter_id)) para que GET /api/matters/{id}/warroom la devuelva sin
-- recomputar el debate.
--
-- El resultado completo (conclusiones + debate + panel + verificación de citas) viaja como
-- jsonb (shape WarRoomResult del contrato). El motor agents/warroom.py NO toca DB: la capa API
-- (routes/ux.py · save_warroom_result) persiste aquí al terminar cada sesión, bajo RLS.
--
-- RLS fail-closed por tenant IGUAL que el resto de tablas por-despacho (patrón 023_personas /
-- 032_gold_cases): ENABLE + FORCE + política ALL con app_current_tenant(). Sin GUC
-- app.tenant_id → 0 filas. Migración aplicada por `postgres`. Idempotente.

CREATE TABLE IF NOT EXISTS warroom_results (
  id          uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id   uuid NOT NULL REFERENCES tenants(id)  ON DELETE CASCADE,
  matter_id   uuid NOT NULL REFERENCES matters(id)  ON DELETE CASCADE,
  -- WarRoomResult del contrato: {conclusions, debate, panel, verification, generated_at}.
  result      jsonb       NOT NULL DEFAULT '{}'::jsonb,
  created_at  timestamptz NOT NULL DEFAULT now(),
  -- Un asunto tiene UNA sala vigente: la nueva convocatoria hace upsert sobre esta clave.
  UNIQUE (tenant_id, matter_id)
);

-- Lectura del dictamen vigente de un asunto (GET .../warroom, .docx, to-draft).
CREATE INDEX IF NOT EXISTS idx_warroom_results_tenant_matter
  ON warroom_results(tenant_id, matter_id);

ALTER TABLE warroom_results ENABLE ROW LEVEL SECURITY;
ALTER TABLE warroom_results FORCE  ROW LEVEL SECURITY;
DROP POLICY IF EXISTS p_warroom_results ON warroom_results;
CREATE POLICY p_warroom_results ON warroom_results
  USING (tenant_id = app_current_tenant())
  WITH CHECK (tenant_id = app_current_tenant());
GRANT SELECT, INSERT, UPDATE, DELETE ON warroom_results TO mia_app;
