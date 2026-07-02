-- Mia · 015_assistant.sql · CP-B1 — MODO ASISTENTE (conversación libre fuera de un asunto)
--
-- Hasta ahora Mia solo conversa DENTRO de un expediente (grafo matter-céntrico). El modo
-- asistente (Pilar B) le da al abogado una conversación libre (agenda, recordatorios,
-- investigación, el despacho) con la misma alma (SOUL), memoria e infraestructura. Estas dos
-- tablas guardan ese historial por tenant + usuario:
--
--   assistant_conversations — una fila por conversación (título = primeras palabras del
--                             primer mensaje; user_id opcional: se resuelve por email del JWT).
--   assistant_messages      — los turnos (user/assistant) en orden cronológico.
--
-- RLS fail-closed IGUAL que el resto de tablas por-tenant (schema.sql): ENABLE + FORCE +
-- política ALL con USING/WITH CHECK = app_current_tenant(). Sin GUC `app.tenant_id` → 0 filas.
-- Migración aplicada por `postgres` (execution/init_assistant.py). Idempotente.

CREATE TABLE IF NOT EXISTS assistant_conversations (
  id          uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id   uuid NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
  -- user_id: dueño de la conversación dentro del despacho. Nullable: si el token no trae
  -- un email resoluble a un usuario, la conversación queda a nivel de despacho.
  user_id     uuid REFERENCES users(id) ON DELETE SET NULL,
  title       varchar(200) NOT NULL DEFAULT '',
  created_at  timestamptz NOT NULL DEFAULT now(),
  updated_at  timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS assistant_messages (
  id               uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id        uuid NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
  conversation_id  uuid NOT NULL REFERENCES assistant_conversations(id) ON DELETE CASCADE,
  role             varchar(16) NOT NULL CHECK (role IN ('user', 'assistant', 'system')),
  content          text NOT NULL,
  created_at       timestamptz NOT NULL DEFAULT now()
);

-- Índices: listado de conversaciones por tenant/usuario y lectura del historial en orden.
CREATE INDEX IF NOT EXISTS idx_assistant_conversations_tenant
  ON assistant_conversations(tenant_id, updated_at DESC);
CREATE INDEX IF NOT EXISTS idx_assistant_conversations_user
  ON assistant_conversations(tenant_id, user_id);
CREATE INDEX IF NOT EXISTS idx_assistant_messages_tenant_conv
  ON assistant_messages(tenant_id, conversation_id, created_at);

-- RLS fail-closed (política estándar del proyecto — ver schema.sql).
ALTER TABLE assistant_conversations ENABLE ROW LEVEL SECURITY;
ALTER TABLE assistant_conversations FORCE  ROW LEVEL SECURITY;
ALTER TABLE assistant_messages      ENABLE ROW LEVEL SECURITY;
ALTER TABLE assistant_messages      FORCE  ROW LEVEL SECURITY;

DROP POLICY IF EXISTS p_assistant_conversations ON assistant_conversations;
CREATE POLICY p_assistant_conversations ON assistant_conversations
  USING (tenant_id = app_current_tenant())
  WITH CHECK (tenant_id = app_current_tenant());

DROP POLICY IF EXISTS p_assistant_messages ON assistant_messages;
CREATE POLICY p_assistant_messages ON assistant_messages
  USING (tenant_id = app_current_tenant())
  WITH CHECK (tenant_id = app_current_tenant());

GRANT SELECT, INSERT, UPDATE, DELETE ON assistant_conversations TO mia_app;
GRANT SELECT, INSERT, UPDATE, DELETE ON assistant_messages TO mia_app;
