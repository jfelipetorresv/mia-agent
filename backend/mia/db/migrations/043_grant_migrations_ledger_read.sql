-- Mia · 043_grant_migrations_ledger_read.sql · GRANT de lectura del ledger de migraciones
--
-- FastAPI se conecta siempre como `mia_app` (NOSUPERUSER, NOBYPASSRLS) — nunca como
-- `postgres`. `public.mia_schema_migrations` la crea/llena `apply_migrations()` con el
-- superusuario (db_bootstrap.py) y nunca quedó con GRANT hacia `mia_app`. Sin este GRANT,
-- /health no puede contar cuántas migraciones están aplicadas (para compararlo contra
-- las que trae el bundle) y el instalador no puede detectar una actualización a medias.
--
-- Solo SELECT: mia_app nunca debe poder alterar el propio ledger de migraciones.
-- Idempotente y aditiva. Migración por `postgres` (mia_app no tiene GRANT).

GRANT SELECT ON public.mia_schema_migrations TO mia_app;
