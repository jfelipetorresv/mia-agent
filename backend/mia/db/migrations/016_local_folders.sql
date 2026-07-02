-- Mia · 016_local_folders.sql · CP-C1 (Pilar C) — carpetas de trabajo del abogado (decisión #30)
--
-- Mia debe conocer las carpetas de trabajo del despacho: disco local, OneDrive y Google
-- Drive (vía sus carpetas espejo de escritorio en Windows) e indexarlas sola, con una
-- ALLOWLIST EXPLÍCITA: solo se escanea lo que el abogado registró. Dos tablas:
--
--   local_folder_sources — la allowlist: una fila por carpeta registrada por el despacho.
--                          kind='knowledge' en v1 (los chunks van a knowledge_chunks);
--                          'matters' (expedientes) queda para una fase posterior.
--   local_file_hashes    — sha256 por archivo y por fuente, para indexación incremental
--                          (mismo patrón que obsidian_file_hashes, migración 004).
--
-- Los chunks van a knowledge_chunks (004) con source = 'local:<source_id>' — así se
-- distinguen de los de Obsidian (source='obsidian') sin tocar el esquema existente.
--
-- RLS fail-closed IGUAL que el resto de tablas por-tenant: ENABLE + FORCE + política ALL
-- con USING/WITH CHECK = app_current_tenant(). Sin GUC `app.tenant_id` → 0 filas.
-- Migración aplicada por `postgres` (execution/init_local_folders.py). Idempotente.

CREATE TABLE IF NOT EXISTS local_folder_sources (
  id          uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id   uuid NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
  path        text NOT NULL,                        -- ruta ABSOLUTA ya resuelta y validada
  label       varchar(200) NOT NULL DEFAULT '',     -- nombre amable ("Tu OneDrive", ...)
  kind        varchar(20) NOT NULL DEFAULT 'knowledge',
  enabled     boolean NOT NULL DEFAULT true,
  created_at  timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS local_file_hashes (
  tenant_id     uuid NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
  source_id     uuid NOT NULL REFERENCES local_folder_sources(id) ON DELETE CASCADE,
  file_path     text NOT NULL,                      -- ruta relativa a la carpeta registrada
  content_hash  varchar(64) NOT NULL,               -- sha256 hex
  updated_at    timestamptz NOT NULL DEFAULT now(),
  PRIMARY KEY (tenant_id, source_id, file_path)
);

-- Una misma carpeta no puede registrarse dos veces para el mismo tenant y kind:
-- UNIQUE a nivel de DB (register_source usa ON CONFLICT sobre esta restricción).
-- Idempotente: se agrega solo si no existe (la 016 original ya corrió en local).
DO $$
BEGIN
  IF NOT EXISTS (
    SELECT 1 FROM pg_constraint
    WHERE conname = 'uq_local_folder_sources_tenant_path_kind'
      AND conrelid = 'public.local_folder_sources'::regclass
  ) THEN
    ALTER TABLE local_folder_sources
      ADD CONSTRAINT uq_local_folder_sources_tenant_path_kind UNIQUE (tenant_id, path, kind);
  END IF;
END $$;

CREATE INDEX IF NOT EXISTS idx_local_folder_sources_tenant ON local_folder_sources(tenant_id);
CREATE INDEX IF NOT EXISTS idx_local_file_hashes_source    ON local_file_hashes(tenant_id, source_id);

-- RLS fail-closed (política estándar del proyecto — ver schema.sql / 004).
ALTER TABLE local_folder_sources ENABLE ROW LEVEL SECURITY;
ALTER TABLE local_folder_sources FORCE  ROW LEVEL SECURITY;
ALTER TABLE local_file_hashes    ENABLE ROW LEVEL SECURITY;
ALTER TABLE local_file_hashes    FORCE  ROW LEVEL SECURITY;

DROP POLICY IF EXISTS p_local_folder_sources ON local_folder_sources;
CREATE POLICY p_local_folder_sources ON local_folder_sources
  USING (tenant_id = app_current_tenant())
  WITH CHECK (tenant_id = app_current_tenant());

DROP POLICY IF EXISTS p_local_file_hashes ON local_file_hashes;
CREATE POLICY p_local_file_hashes ON local_file_hashes
  USING (tenant_id = app_current_tenant())
  WITH CHECK (tenant_id = app_current_tenant());

GRANT SELECT, INSERT, UPDATE, DELETE ON local_folder_sources TO mia_app;
GRANT SELECT, INSERT, UPDATE, DELETE ON local_file_hashes    TO mia_app;
