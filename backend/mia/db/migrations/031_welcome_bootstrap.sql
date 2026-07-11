-- Mia · 031_welcome_bootstrap.sql · F3 (bienvenida + activación, sesión 44)
-- Señal pre-login "¿ya hay algún despacho creado en este equipo?" para que el
-- frontend decida "crear despacho" vs "iniciar sesión" ANTES de que exista JWT.
--
-- `tenants` tiene RLS FORCE (id = app_current_tenant()): mia_app SIN contexto de
-- tenant ve 0 filas (fail-closed), así que un simple SELECT no puede responder
-- esta pregunta. Se usa una función SECURITY DEFINER mínima — mismo patrón que
-- `auth_user_by_email` (009_users.sql), que también resuelve algo ANTES del JWT.
-- Devuelve SOLO un booleano de EXISTENCIA (ningún dato de ningún despacho): el
-- mismo nivel de exposición que el endpoint público /api/welcome/status ya asume.

-- Hardening (revisión capa 2): una función SECURITY DEFINER corre con los
-- privilegios del DUEÑO, así que NUNCA debe heredar un search_path atacable. Se
-- fija a `pg_catalog` (nada de `public`, que un rol podría manipular) y se
-- CALIFICA la tabla como `public.tenants` para que la resolución no dependa del
-- search_path del que llama. Idempotente (CREATE OR REPLACE), sin DROP.
CREATE OR REPLACE FUNCTION mia_any_tenant_exists()
RETURNS boolean
LANGUAGE sql
SECURITY DEFINER
SET search_path = pg_catalog
AS $$
  SELECT EXISTS (SELECT 1 FROM public.tenants)
$$;

REVOKE ALL ON FUNCTION mia_any_tenant_exists() FROM PUBLIC;
GRANT EXECUTE ON FUNCTION mia_any_tenant_exists() TO mia_app;
