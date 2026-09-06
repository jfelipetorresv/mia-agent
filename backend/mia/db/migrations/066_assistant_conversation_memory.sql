-- Checkpoints derivados: los originales permanecen íntegros en assistant_messages.
ALTER TABLE assistant_conversations ADD COLUMN IF NOT EXISTS history_revision bigint NOT NULL DEFAULT 0;
CREATE UNIQUE INDEX IF NOT EXISTS uq_assistant_conversations_tenant_id
  ON assistant_conversations(tenant_id, id);

CREATE TABLE IF NOT EXISTS assistant_conversation_memory (
  tenant_id uuid NOT NULL,
  conversation_id uuid NOT NULL,
  revision bigint NOT NULL DEFAULT 0,
  compressor_version text NOT NULL DEFAULT '',
  summary text NOT NULL DEFAULT '',
  cursor_created_at timestamptz,
  cursor_id uuid,
  covered_hash text NOT NULL DEFAULT '',
  updated_at timestamptz NOT NULL DEFAULT now(),
  PRIMARY KEY(tenant_id, conversation_id),
  FOREIGN KEY(tenant_id, conversation_id) REFERENCES assistant_conversations(tenant_id,id) ON DELETE CASCADE,
  CHECK ((cursor_created_at IS NULL) = (cursor_id IS NULL))
);
CREATE TABLE IF NOT EXISTS assistant_memory_attempts (
  tenant_id uuid NOT NULL,
  conversation_id uuid NOT NULL,
  input_hash text NOT NULL,
  eligible_hash text NOT NULL,
  claim_id uuid NOT NULL,
  status text NOT NULL CHECK(status IN ('running','completed','failed','ineffective','uncertain','obsolete')),
  updated_at timestamptz NOT NULL DEFAULT now(),
  PRIMARY KEY(tenant_id, conversation_id, input_hash),
  FOREIGN KEY(tenant_id, conversation_id) REFERENCES assistant_conversations(tenant_id,id) ON DELETE CASCADE
);
ALTER TABLE assistant_conversation_memory ADD COLUMN IF NOT EXISTS ineffective_count integer NOT NULL DEFAULT 0;
ALTER TABLE assistant_conversation_memory ADD COLUMN IF NOT EXISTS eligible_basis text NOT NULL DEFAULT '';
ALTER TABLE assistant_conversation_memory ENABLE ROW LEVEL SECURITY;
ALTER TABLE assistant_conversation_memory FORCE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS p_assistant_conversation_memory ON assistant_conversation_memory;
CREATE POLICY p_assistant_conversation_memory ON assistant_conversation_memory
  USING(tenant_id=app_current_tenant()) WITH CHECK(tenant_id=app_current_tenant());
ALTER TABLE assistant_memory_attempts ENABLE ROW LEVEL SECURITY;
ALTER TABLE assistant_memory_attempts FORCE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS p_assistant_memory_attempts ON assistant_memory_attempts;
CREATE POLICY p_assistant_memory_attempts ON assistant_memory_attempts
  USING(tenant_id=app_current_tenant()) WITH CHECK(tenant_id=app_current_tenant());
GRANT SELECT, INSERT, UPDATE, DELETE ON assistant_conversation_memory, assistant_memory_attempts TO mia_app;

-- Toda modificación del original coordina con el sellado corto del checkpoint.
-- No se mantiene esta fila bloqueada durante ninguna llamada al proveedor.
CREATE OR REPLACE FUNCTION assistant_history_changed() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
  IF TG_OP <> 'INSERT' THEN
    UPDATE assistant_conversations SET history_revision=history_revision+1 WHERE id=OLD.conversation_id;
  END IF;
  IF TG_OP <> 'DELETE' THEN
    UPDATE assistant_conversations SET history_revision=history_revision+1 WHERE id=NEW.conversation_id;
  END IF;
  RETURN NULL;
END $$;
DROP TRIGGER IF EXISTS assistant_history_changed ON assistant_messages;
CREATE TRIGGER assistant_history_changed AFTER INSERT OR UPDATE OR DELETE ON assistant_messages
  FOR EACH ROW EXECUTE FUNCTION assistant_history_changed();
