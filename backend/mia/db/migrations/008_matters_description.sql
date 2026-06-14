-- Mia · 008_matters_description.sql · Fase 3 frontend — cierra Riesgo #24
-- La tabla matters (Módulo 0) no tenía description ni status; la Pantalla 1/2 los necesita.
-- Migración por `postgres`. Idempotente (ADD COLUMN IF NOT EXISTS).

ALTER TABLE matters ADD COLUMN IF NOT EXISTS description text DEFAULT '';
ALTER TABLE matters ADD COLUMN IF NOT EXISTS status varchar(20) DEFAULT 'active'
  CHECK (status IN ('active', 'archived', 'closed'));
