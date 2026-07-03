-- Mia · 021_turn_usage.sql · CP-V1 (Ola 4) — valor entregado en lenguaje de negocio
--
-- Registro del USO REAL del LLM por llamada (tokens y costo), que hoy se descarta:
-- `resp.usage` viene en TODAS las respuestas (API OpenAI-compatible del gateway y
-- también el CLI de la suscripción, ver agent/subscription_llm) y nunca se persistía.
-- Con esta tabla el panel puede mostrar "valor neto" = horas ahorradas × tarifa −
-- costo real de IA, en vez de una estimación con tarifa fija inventada.
--
--   turn_usage — una fila por LLAMADA al LLM (un turno puede tener varias: equipo de
--     especialistas de CP9). `model` es el ALIAS del gateway (claude-sonnet, cli-claude,
--     mia-local…); `task` es la tarea del router (main, compression, verification…);
--     `source` distingue quién originó la llamada (api | cron). `cost_usd` se calcula
--     al registrar con la tabla de precios de metrics/usage.py (cli-*/mia-local = 0:
--     costo marginal cero para el despacho). `matter_id` es opcional (el asistente y
--     el cron no siempre tienen asunto).
--
-- RLS fail-closed por tenant IGUAL que el resto (ver 017/020): ENABLE + FORCE +
-- política ALL con app_current_tenant(). Migración por `postgres`
-- (execution/init_turn_usage.py). Idempotente.

CREATE TABLE IF NOT EXISTS turn_usage (
  id                uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id         uuid NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
  matter_id         uuid,                                 -- opcional; sin FK dura (el asunto puede borrarse)
  task              varchar(64),
  model             varchar(128) NOT NULL,
  prompt_tokens     integer NOT NULL DEFAULT 0,
  completion_tokens integer NOT NULL DEFAULT 0,
  total_tokens      integer NOT NULL DEFAULT 0,
  cost_usd          numeric(12,6) NOT NULL DEFAULT 0,
  source            varchar(32) NOT NULL DEFAULT 'api',
  created_at        timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_turn_usage_tenant_time
  ON turn_usage(tenant_id, created_at DESC);

ALTER TABLE turn_usage ENABLE ROW LEVEL SECURITY;
ALTER TABLE turn_usage FORCE  ROW LEVEL SECURITY;
DROP POLICY IF EXISTS p_turn_usage ON turn_usage;
CREATE POLICY p_turn_usage ON turn_usage
  USING (tenant_id = app_current_tenant())
  WITH CHECK (tenant_id = app_current_tenant());
-- DELETE incluido para la autopoda futura (>12 meses); sin UPDATE: el registro es inmutable.
GRANT SELECT, INSERT, DELETE ON turn_usage TO mia_app;
