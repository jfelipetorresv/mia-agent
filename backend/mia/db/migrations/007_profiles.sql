-- Mia · 007_profiles.sql · Fase 3 (backend) — persistencia del perfil del despacho (decisión #20)
-- El Módulo 2a (ProfileManager) era in-memory (perfiles de TEXTO abogado/despacho para el
-- prompt). Esta tabla persiste el perfil ESTRUCTURADO del despacho que edita el abogado en la
-- Pantalla 4 (nombre, jurisdicción, áreas, estilo). Patrón RLS por-tenant. Migración por
-- `postgres`. Idempotente. Una fila por tenant (UNIQUE).

CREATE EXTENSION IF NOT EXISTS pgcrypto;    -- gen_random_uuid()

CREATE TABLE IF NOT EXISTS firm_profiles (
  id                uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id         uuid NOT NULL UNIQUE REFERENCES tenants(id) ON DELETE CASCADE,
  name              varchar(200),                          -- nombre del despacho
  lawyer_name       varchar(200),
  tp_number         varchar(50),                           -- tarjeta profesional
  jurisdiction      varchar(100) NOT NULL DEFAULT 'colombia',
  practice_areas    text[],
  voice_adjectives  text[],                                -- 3 adjetivos de estilo
  banned_words      text[],
  preferred_sources text[],
  hard_nos          text[],
  rhythm            jsonb NOT NULL DEFAULT '{}'::jsonb,
  tools             text[],
  metadata          jsonb NOT NULL DEFAULT '{}'::jsonb,
  created_at        timestamptz NOT NULL DEFAULT now(),
  updated_at        timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_firm_profiles_tenant ON firm_profiles(tenant_id);

-- ===================== RLS (patrón estándar por-tenant) =====================
ALTER TABLE firm_profiles ENABLE ROW LEVEL SECURITY;
ALTER TABLE firm_profiles FORCE  ROW LEVEL SECURITY;

DROP POLICY IF EXISTS p_firm_profiles ON firm_profiles;
CREATE POLICY p_firm_profiles ON firm_profiles
  USING (tenant_id = app_current_tenant())
  WITH CHECK (tenant_id = app_current_tenant());

GRANT SELECT, INSERT, UPDATE, DELETE ON firm_profiles TO mia_app;
