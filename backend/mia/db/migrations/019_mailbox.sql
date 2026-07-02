-- Mia · 019_mailbox.sql · CP-P3 (Ola 2) — conectores de calendario y correo
--
-- Da a Mia acceso de SOLO LECTURA al calendario y la bandeja del abogado (Microsoft
-- 365 vía Graph, o Google Workspace vía Calendar/Gmail) para volverse proactiva:
-- avisa de eventos próximos (posibles audiencias/plazos) y de correos que PARECEN
-- urgentes — en CP-P3, solo por su METADATA (fechas, remitente, asunto), nunca el
-- cuerpo (el análisis de contenido con IA llega en CP-P4, opt-in por despacho).
--
-- Dos objetos, ambos POR TENANT bajo RLS fail-closed (los tokens de un despacho son
-- de ese despacho; jamás visibles a otro):
--
--   tenant_oauth_tokens — access/refresh token OAuth de la cuenta conectada. Un
--     proveedor por tenant en v1 (PK = tenant_id). El access token es de vida corta;
--     el refresh token lo renueva sin volver a molestar al abogado. Las llaves de la
--     APP OAuth (client_id/secret) NO viven aquí: son de la INSTALACIÓN (una por
--     despliegue), en config.py / .env.
--
--   mailbox_notifications — ledger de "ya avisé de esto" (debounce): evita re-avisar
--     del mismo evento de calendario o del mismo correo urgente en cada ciclo de la
--     vigilancia. (tenant_id, kind, external_id) es único.
--
-- RLS IGUAL que el resto de tablas por-tenant (ver 017_reminders.sql): ENABLE + FORCE
-- + política ALL con USING/WITH CHECK = app_current_tenant(). Sin GUC app.tenant_id →
-- 0 filas. Migración aplicada por `postgres` (execution/init_mailbox.py). Idempotente.

CREATE TABLE IF NOT EXISTS tenant_oauth_tokens (
  tenant_id      uuid PRIMARY KEY REFERENCES tenants(id) ON DELETE CASCADE,
  provider       varchar(16) NOT NULL CHECK (provider IN ('microsoft', 'google')),
  access_token   text NOT NULL,
  refresh_token  text NOT NULL DEFAULT '',
  expires_at     timestamptz,                 -- expiración del access token (UTC)
  scopes         text NOT NULL DEFAULT '',    -- scopes concedidos, separados por espacio
  connected_at   timestamptz NOT NULL DEFAULT now(),
  updated_at     timestamptz NOT NULL DEFAULT now()
);

ALTER TABLE tenant_oauth_tokens ENABLE ROW LEVEL SECURITY;
ALTER TABLE tenant_oauth_tokens FORCE  ROW LEVEL SECURITY;

DROP POLICY IF EXISTS p_tenant_oauth_tokens ON tenant_oauth_tokens;
CREATE POLICY p_tenant_oauth_tokens ON tenant_oauth_tokens
  USING (tenant_id = app_current_tenant())
  WITH CHECK (tenant_id = app_current_tenant());

GRANT SELECT, INSERT, UPDATE, DELETE ON tenant_oauth_tokens TO mia_app;


CREATE TABLE IF NOT EXISTS mailbox_notifications (
  tenant_id    uuid NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
  kind         varchar(16) NOT NULL CHECK (kind IN ('calendar', 'mail')),
  external_id  text NOT NULL,               -- id del evento/correo en el proveedor
  notified_at  timestamptz NOT NULL DEFAULT now(),
  PRIMARY KEY (tenant_id, kind, external_id)
);

ALTER TABLE mailbox_notifications ENABLE ROW LEVEL SECURITY;
ALTER TABLE mailbox_notifications FORCE  ROW LEVEL SECURITY;

DROP POLICY IF EXISTS p_mailbox_notifications ON mailbox_notifications;
CREATE POLICY p_mailbox_notifications ON mailbox_notifications
  USING (tenant_id = app_current_tenant())
  WITH CHECK (tenant_id = app_current_tenant());

GRANT SELECT, INSERT, UPDATE, DELETE ON mailbox_notifications TO mia_app;
