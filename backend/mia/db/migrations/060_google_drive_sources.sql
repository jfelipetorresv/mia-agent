-- Mia · 060_google_drive_sources.sql · Google Drive como conector remoto, al nivel de OneDrive
-- (decisión de Pipe 2026-08-19).
--
-- La 027 creó `remote_drive_sources` con el proveedor congelado a 'microsoft' porque en su
-- momento Google Drive estaba declarado fuera de alcance. Esta migración solo AMPLÍA ese
-- vocabulario a ('microsoft','google'); no cambia ninguna otra columna, índice ni política.
-- Las carpetas ya registradas siguen siendo válidas (provider='microsoft').
--
-- El CHECK pasa de ser anónimo-inline (CREATE TABLE de la 027) a llamarse
-- `ck_remote_drive_sources_provider`, para que el gate estático de vocabularios acumulados
-- (execution/test_migration_contracts.py) pueda leerlo y para poder ampliarlo en el futuro
-- sin volver a editar una migración histórica (que es inmutable, ver config/migration_shas.json).
--
-- Idempotente: se puede re-ejecutar sin efecto.

-- La tabla puede no existir si la 027 no corrió en este entorno: en ese caso no hay nada que
-- ampliar (la 027 la creará ya con su propio CHECK y una instalación futura reejecutará esto).
DO $$
BEGIN
  IF to_regclass('public.remote_drive_sources') IS NULL THEN
    RETURN;
  END IF;

  -- Quita el CHECK inline anónimo de la 027 (nombre por defecto de Postgres) si sigue ahí.
  IF EXISTS (
    SELECT 1 FROM pg_constraint
    WHERE conrelid = 'public.remote_drive_sources'::regclass
      AND conname = 'remote_drive_sources_provider_check'
  ) THEN
    ALTER TABLE remote_drive_sources DROP CONSTRAINT remote_drive_sources_provider_check;
  END IF;

  ALTER TABLE remote_drive_sources DROP CONSTRAINT IF EXISTS ck_remote_drive_sources_provider;
  ALTER TABLE remote_drive_sources
    ADD CONSTRAINT ck_remote_drive_sources_provider CHECK (provider IN ('microsoft', 'google'));
END $$;
