-- Mia · 009_users.sql · Login real multi-tenant (Riesgo #23)
-- Usuarios por tenant con hash bcrypt. La tabla queda aislada por RLS; el login
-- usa una función SECURITY DEFINER mínima para resolver el tenant por email antes
-- de que exista JWT.

CREATE EXTENSION IF NOT EXISTS pgcrypto;

CREATE TABLE IF NOT EXISTS users (
  id            uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id     uuid NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
  email         varchar(200) UNIQUE NOT NULL,
  password_hash varchar(200) NOT NULL,
  created_at    timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_users_tenant ON users(tenant_id);
CREATE INDEX IF NOT EXISTS idx_users_email ON users(email);

ALTER TABLE users ENABLE ROW LEVEL SECURITY;
ALTER TABLE users FORCE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS p_users ON users;
CREATE POLICY p_users ON users
  USING (tenant_id = current_setting('app.tenant_id')::uuid)
  WITH CHECK (tenant_id = current_setting('app.tenant_id')::uuid);

GRANT SELECT, INSERT, UPDATE, DELETE ON users TO mia_app;

CREATE OR REPLACE FUNCTION auth_user_by_email(p_email varchar)
RETURNS TABLE(id uuid, tenant_id uuid, email varchar, password_hash varchar)
LANGUAGE sql
SECURITY DEFINER
SET search_path = public
AS $$
  SELECT u.id, u.tenant_id, u.email, u.password_hash
  FROM users u
  WHERE lower(u.email) = lower(p_email)
  LIMIT 1
$$;

REVOKE ALL ON FUNCTION auth_user_by_email(varchar) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION auth_user_by_email(varchar) TO mia_app;
