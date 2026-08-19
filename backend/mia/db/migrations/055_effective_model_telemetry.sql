-- 055 · Política adaptativa de modelos: la columna `model` conserva el alias de
-- enrutamiento para precios/históricos; estas columnas describen la decisión efectiva.
-- Nunca se infiere que un proveedor admitió un modelo o esfuerzo: se persiste lo que
-- `agent.llm` pidió en la llamada que sí respondió.
ALTER TABLE turn_usage ADD COLUMN IF NOT EXISTS effective_model varchar(128);
ALTER TABLE turn_usage ADD COLUMN IF NOT EXISTS effort varchar(16);
ALTER TABLE turn_usage ADD COLUMN IF NOT EXISTS quality_escalation varchar(16);

CREATE INDEX IF NOT EXISTS idx_turn_usage_effective_model
  ON turn_usage(tenant_id, effective_model, created_at DESC);
