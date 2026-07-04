-- Mia · 024_missions.sql · CP-E5 (Ola 5) — tablero de misión por expediente
--
-- Un TABLERO DE MISIÓN descompone un objetivo grande del expediente ("preparar la
-- contestación") en HITOS visibles que el abogado ve, edita y avanza a mano. Inspiración de
-- estructura: Hermes kanban (hermes_cli/kanban_db.py) y ClaudeOS Missions (hermes-mission-
-- control.tsx: Mission + MiniGoal), llevado al dominio multi-despacho de Mia:
--
--   missions            — un objetivo grande de UN expediente (una fila por objetivo).
--   mission_milestones  — los hitos de una misión, en orden, cada uno con su estado.
--
-- CONSENT-FIRST (patrón de Mia, NO el swarm autónomo de Hermes): los hitos son una PROPUESTA
-- editable; NADA se auto-ejecuta. El abogado aprueba, edita y marca avance. `actor` distingue
-- quién hace el hito ('mia' = puede prepararlo el agente / 'abogado' = acción del abogado).
--
-- REGLA DURA JURÍDICA: Mia NUNCA calcula términos ni plazos procesales. Por eso el tablero
-- NO tiene columna de fecha/vencimiento: un hito que toca un término lleva `is_procedural=true`
-- y la UI lo muestra con [VERIFICAR] (el plazo lo fija y confirma el abogado, nunca Mia).
--
-- RLS fail-closed por tenant IGUAL que el resto (ver 023_personas.sql): ENABLE + FORCE +
-- política ALL con app_current_tenant(). Migración por `postgres` (execution/init_missions.py).
-- Idempotente.

CREATE TABLE IF NOT EXISTS missions (
  id           uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id    uuid NOT NULL REFERENCES tenants(id)  ON DELETE CASCADE,
  matter_id    uuid NOT NULL REFERENCES matters(id)  ON DELETE CASCADE,
  title        varchar(160) NOT NULL,               -- título corto ("Preparar la contestación")
  objective    text         NOT NULL,               -- el objetivo en palabras del abogado
  outcome      varchar(240) NOT NULL DEFAULT '',     -- resultado esperado (descriptivo, sin fecha)
  status       varchar(16)  NOT NULL DEFAULT 'active'
               CHECK (status IN ('active', 'archived')),
  created_at   timestamptz  NOT NULL DEFAULT now(),
  updated_at   timestamptz  NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS mission_milestones (
  id            uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id     uuid NOT NULL REFERENCES tenants(id)   ON DELETE CASCADE,
  mission_id    uuid NOT NULL REFERENCES missions(id)  ON DELETE CASCADE,
  seq           integer      NOT NULL DEFAULT 0,       -- orden del hito en el tablero
  title         varchar(160) NOT NULL,
  detail        text         NOT NULL DEFAULT '',      -- qué implica el hito (para el abogado)
  actor         varchar(16)  NOT NULL DEFAULT 'abogado'
                CHECK (actor IN ('mia', 'abogado')),
  status        varchar(16)  NOT NULL DEFAULT 'queued'
                CHECK (status IN ('queued', 'active', 'done')),
  -- Regla dura: un hito que toca término/plazo procesal se marca aquí → la UI lo muestra
  -- con [VERIFICAR]. NUNCA se almacena una fecha calculada por Mia.
  is_procedural boolean      NOT NULL DEFAULT false,
  created_at    timestamptz  NOT NULL DEFAULT now(),
  updated_at    timestamptz  NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_missions_tenant_matter
  ON missions(tenant_id, matter_id, status);
CREATE INDEX IF NOT EXISTS idx_mission_milestones_tenant_mission
  ON mission_milestones(tenant_id, mission_id, seq);

ALTER TABLE missions ENABLE ROW LEVEL SECURITY;
ALTER TABLE missions FORCE  ROW LEVEL SECURITY;
DROP POLICY IF EXISTS p_missions ON missions;
CREATE POLICY p_missions ON missions
  USING (tenant_id = app_current_tenant())
  WITH CHECK (tenant_id = app_current_tenant());
GRANT SELECT, INSERT, UPDATE, DELETE ON missions TO mia_app;

ALTER TABLE mission_milestones ENABLE ROW LEVEL SECURITY;
ALTER TABLE mission_milestones FORCE  ROW LEVEL SECURITY;
DROP POLICY IF EXISTS p_mission_milestones ON mission_milestones;
CREATE POLICY p_mission_milestones ON mission_milestones
  USING (tenant_id = app_current_tenant())
  WITH CHECK (tenant_id = app_current_tenant());
GRANT SELECT, INSERT, UPDATE, DELETE ON mission_milestones TO mia_app;
