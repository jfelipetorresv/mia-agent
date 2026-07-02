-- Mia · 017_reminders.sql · CP-B3 (Pilar B) — proactividad: recordatorios y avisos
--
-- Mia deja de ser solo reactiva: el abogado le pide recordatorios en lenguaje natural
-- desde el chat del asistente ("recuérdame radicar el viernes") y el scheduler los
-- despacha por el canal de salida (Telegram, CP-B2) cuando vencen.
--
--   reminders — un recordatorio por fila, por tenant y usuario. `is_procedural=true`
--               marca los que mencionan plazos/actuaciones procesales: SIEMPRE se
--               entregan con [VERIFICAR] (regla dura del plan: Mia nunca calcula un
--               término legal por su cuenta; la fecha la pone el abogado y la confirma él).
--
-- Además: columna `pending_review_notified_at` en matters — debounce del aviso
-- "tienes un borrador esperando tu revisión" (CP5): se avisa al quedar pendiente y
-- se re-avisa a lo sumo cada 24h; approve/reject/edit la resetean a NULL.
--
-- RLS fail-closed IGUAL que el resto de tablas por-tenant: ENABLE + FORCE + política ALL
-- con USING/WITH CHECK = app_current_tenant(). Sin GUC `app.tenant_id` → 0 filas.
-- Migración aplicada por `postgres` (execution/init_reminders.py). Idempotente.

CREATE TABLE IF NOT EXISTS reminders (
  id             uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id      uuid NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
  user_id        uuid REFERENCES users(id) ON DELETE SET NULL,
  text           text NOT NULL,                       -- qué recordar (lo escribió el abogado)
  due_at         timestamptz NOT NULL,                -- cuándo avisar
  is_procedural  boolean NOT NULL DEFAULT false,      -- plazo/actuación procesal → [VERIFICAR]
  status         varchar(16) NOT NULL DEFAULT 'pending'
                 CHECK (status IN ('pending', 'sent', 'cancelled')),
  created_at     timestamptz NOT NULL DEFAULT now(),
  sent_at        timestamptz
);

-- El job de despacho consulta "pendientes ya vencidos" cada pocos minutos.
CREATE INDEX IF NOT EXISTS idx_reminders_tenant_due ON reminders(tenant_id, status, due_at);

-- RLS fail-closed (política estándar del proyecto — ver schema.sql / 004).
ALTER TABLE reminders ENABLE ROW LEVEL SECURITY;
ALTER TABLE reminders FORCE  ROW LEVEL SECURITY;

DROP POLICY IF EXISTS p_reminders ON reminders;
CREATE POLICY p_reminders ON reminders
  USING (tenant_id = app_current_tenant())
  WITH CHECK (tenant_id = app_current_tenant());

GRANT SELECT, INSERT, UPDATE, DELETE ON reminders TO mia_app;

-- Debounce del aviso de borrador pendiente (CP5 → CP-B3).
ALTER TABLE matters ADD COLUMN IF NOT EXISTS pending_review_notified_at timestamptz;
