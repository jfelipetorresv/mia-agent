-- Reenvíos del chat: la reserva sobrevive al proceso y no caduca automáticamente.
CREATE TABLE IF NOT EXISTS assistant_chat_requests (
  tenant_id uuid NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
  user_id uuid NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  request_id uuid NOT NULL,
  payload_hash text NOT NULL CHECK (length(payload_hash) = 64),
  status text NOT NULL DEFAULT 'running' CHECK (status IN ('running', 'completed', 'uncertain')),
  response jsonb,
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now(),
  PRIMARY KEY (tenant_id, user_id, request_id),
  CHECK ((status = 'completed') = (response IS NOT NULL))
);
ALTER TABLE assistant_chat_requests ENABLE ROW LEVEL SECURITY;
ALTER TABLE assistant_chat_requests FORCE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS p_assistant_chat_requests ON assistant_chat_requests;
CREATE POLICY p_assistant_chat_requests ON assistant_chat_requests
  USING (tenant_id = app_current_tenant())
  WITH CHECK (tenant_id = app_current_tenant());
GRANT SELECT, INSERT, UPDATE, DELETE ON assistant_chat_requests TO mia_app;
