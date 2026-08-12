-- Mia · 027_remote_sources.sql · Fase 1 "Fuentes remotas del expediente" — cimientos OAuth
-- multi-proveedor (correos del caso → expediente y OneDrive remoto selectivo llegan en
-- fases POSTERIORES; esta migración solo prepara el terreno).
--
-- Tres cambios, todos idempotentes:
--
--   tenant_oauth_tokens — la PK pasa de (tenant_id) a (tenant_id, provider): un despacho
--     ahora puede tener Microsoft Y Google conectados a la vez (antes, conectar el segundo
--     proveedor pisaba al primero). Migra los datos existentes sin perderlos.
--
--   documents.origin — CHECK ampliado de ('upload','folder') a ('upload','folder','mail',
--     'drive') para que fases futuras puedan marcar de dónde vino cada documento (correo
--     del caso / OneDrive remoto), sin tocar el comportamiento actual (default sigue
--     'upload').
--
--   remote_drive_sources / remote_file_hashes — allowlist y huellas de fuentes remotas de
--     OneDrive (espejo de local_folder_sources/local_file_hashes de la 016, pero para
--     archivos que NUNCA tocan disco local). kind='knowledge' (conocimiento del despacho)
--     o 'matters' (vinculado a un asunto, matter_id NOT NULL en ese caso — se exige en
--     aplicación, igual que local_folder_sources hoy).
--
-- RLS fail-closed IGUAL que el resto de tablas por-tenant: ENABLE + FORCE + política ALL
-- con USING/WITH CHECK = app_current_tenant(). Migración aplicada por `postgres`
-- (execution/init_remote_sources.py). Idempotente: se puede re-ejecutar sin efecto.

-- ── tenant_oauth_tokens: PK (tenant_id) -> (tenant_id, provider) ─────────────────
DO $$
BEGIN
  IF EXISTS (
    SELECT 1 FROM pg_constraint
    WHERE conrelid = 'public.tenant_oauth_tokens'::regclass
      AND contype = 'p'
      AND conkey = ARRAY[
        (SELECT attnum FROM pg_attribute
         WHERE attrelid = 'public.tenant_oauth_tokens'::regclass AND attname = 'tenant_id')
      ]
  ) THEN
    -- la PK vieja era solo (tenant_id): la reemplazamos por (tenant_id, provider).
    ALTER TABLE tenant_oauth_tokens DROP CONSTRAINT tenant_oauth_tokens_pkey;
    ALTER TABLE tenant_oauth_tokens ADD CONSTRAINT tenant_oauth_tokens_pkey
      PRIMARY KEY (tenant_id, provider);
  END IF;
END $$;

-- Si la migración 019 aún no corrió en este entorno (tabla ausente), créala ya con la PK
-- compuesta (idempotente: no pisa un entorno donde 019 ya la creó y el DO $$ de arriba ya
-- la migró).
CREATE TABLE IF NOT EXISTS tenant_oauth_tokens (
  tenant_id      uuid NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
  provider       varchar(16) NOT NULL CHECK (provider IN ('microsoft', 'google')),
  access_token   text NOT NULL,
  refresh_token  text NOT NULL DEFAULT '',
  expires_at     timestamptz,
  scopes         text NOT NULL DEFAULT '',
  connected_at   timestamptz NOT NULL DEFAULT now(),
  updated_at     timestamptz NOT NULL DEFAULT now(),
  PRIMARY KEY (tenant_id, provider)
);

ALTER TABLE tenant_oauth_tokens ENABLE ROW LEVEL SECURITY;
ALTER TABLE tenant_oauth_tokens FORCE  ROW LEVEL SECURITY;

DROP POLICY IF EXISTS p_tenant_oauth_tokens ON tenant_oauth_tokens;
CREATE POLICY p_tenant_oauth_tokens ON tenant_oauth_tokens
  USING (tenant_id = app_current_tenant())
  WITH CHECK (tenant_id = app_current_tenant());

GRANT SELECT, INSERT, UPDATE, DELETE ON tenant_oauth_tokens TO mia_app;


-- ── documents.origin: ampliar a 'mail' y 'drive' (patrón de la 025) ──────────────
ALTER TABLE documents ADD COLUMN IF NOT EXISTS origin text NOT NULL DEFAULT 'upload';

ALTER TABLE documents DROP CONSTRAINT IF EXISTS ck_documents_origin;
ALTER TABLE documents
  -- `mia` lo añadió la migración 028. Conservarlo hace esta migración realmente
  -- idempotente cuando un gate antiguo la reaplica sobre un esquema más nuevo.
  ADD CONSTRAINT ck_documents_origin CHECK (origin IN ('upload', 'folder', 'mail', 'drive', 'mia'));


-- ── remote_drive_sources: allowlist de fuentes remotas de OneDrive ───────────────
CREATE TABLE IF NOT EXISTS remote_drive_sources (
  id             uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id      uuid NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
  provider       text NOT NULL CHECK (provider IN ('microsoft')),
  remote_item_id text NOT NULL,                    -- id del ítem en el proveedor (driveItem)
  label          text NOT NULL,                    -- nombre amable ("Tu OneDrive", ...)
  kind           text NOT NULL CHECK (kind IN ('knowledge', 'matters')),
  matter_id      uuid REFERENCES matters(id) ON DELETE CASCADE,
  enabled        boolean NOT NULL DEFAULT true,
  created_at     timestamptz NOT NULL DEFAULT now(),
  UNIQUE (tenant_id, provider, remote_item_id, kind)
);

-- last_synced_at: momento de la ÚLTIMA sincronización completada (haya o no archivos). Se
-- actualiza al final de cada corrida. De aquí salen el "última revisión" que ve el abogado y
-- el throttle de re-sync — así una carpeta VACÍA (sin filas en remote_file_hashes) también
-- queda marcada como revisada (antes: last_sync NULL para siempre, throttle nunca aplicaba).
ALTER TABLE remote_drive_sources ADD COLUMN IF NOT EXISTS last_synced_at timestamptz;

CREATE INDEX IF NOT EXISTS idx_remote_drive_sources_tenant ON remote_drive_sources(tenant_id);
CREATE INDEX IF NOT EXISTS idx_remote_drive_sources_matter ON remote_drive_sources(matter_id);

ALTER TABLE remote_drive_sources ENABLE ROW LEVEL SECURITY;
ALTER TABLE remote_drive_sources FORCE  ROW LEVEL SECURITY;

DROP POLICY IF EXISTS p_remote_drive_sources ON remote_drive_sources;
CREATE POLICY p_remote_drive_sources ON remote_drive_sources
  USING (tenant_id = app_current_tenant())
  WITH CHECK (tenant_id = app_current_tenant());

GRANT SELECT, INSERT, UPDATE, DELETE ON remote_drive_sources TO mia_app;


-- ── remote_file_hashes: huellas por archivo remoto (espejo de local_file_hashes) ─
CREATE TABLE IF NOT EXISTS remote_file_hashes (
  tenant_id   uuid NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
  source_id   uuid NOT NULL REFERENCES remote_drive_sources(id) ON DELETE CASCADE,
  item_id     text NOT NULL,                       -- id del archivo/carpeta en el proveedor
  etag        text NOT NULL DEFAULT '',            -- etag/cTag del proveedor (cambio barato)
  sha256      text NOT NULL DEFAULT '',            -- huella de contenido (dedupe/incremental)
  synced_at   timestamptz NOT NULL DEFAULT now(),
  PRIMARY KEY (tenant_id, source_id, item_id)
);

-- rel_path: ruta relativa (dentro de la carpeta registrada) BAJO LA QUE se ingirió el
-- contenido de este archivo. Se guarda para detectar un RENOMBRE/MOVIMIENTO remoto (mismo
-- item_id y mismo contenido, ruta distinta): en ese caso se MUEVE el documento/fragmentos a
-- la ruta nueva en vez de dejarlos huérfanos bajo la vieja (que la poda por ruta borraría).
ALTER TABLE remote_file_hashes ADD COLUMN IF NOT EXISTS rel_path text NOT NULL DEFAULT '';

CREATE INDEX IF NOT EXISTS idx_remote_file_hashes_source ON remote_file_hashes(tenant_id, source_id);

ALTER TABLE remote_file_hashes ENABLE ROW LEVEL SECURITY;
ALTER TABLE remote_file_hashes FORCE  ROW LEVEL SECURITY;

DROP POLICY IF EXISTS p_remote_file_hashes ON remote_file_hashes;
CREATE POLICY p_remote_file_hashes ON remote_file_hashes
  USING (tenant_id = app_current_tenant())
  WITH CHECK (tenant_id = app_current_tenant());

GRANT SELECT, INSERT, UPDATE, DELETE ON remote_file_hashes TO mia_app;
