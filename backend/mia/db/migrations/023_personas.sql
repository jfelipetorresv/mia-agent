-- Mia · 023_personas.sql · CP-E3 (Ola 5) — personas jurídicas especializadas y editables
--
-- Ref ClaudeOS Pantheon (skills/personas/SKILL.md, vite.config.ts::PANTHEON_SEEDS), llevado
-- al dominio multi-despacho de Mia: las personas NO viven en YAML de disco (Mia es
-- multi-tenant con RLS) — viven en esta tabla bajo RLS fail-closed, una por despacho,
-- editables por el despacho. Una persona es "QUIÉN HABLA" en un turno (voz + énfasis +
-- nivel de motor), complementaria a los nodos de CP9 que son "CÓMO TRABAJA".
--
--   personas — una especialidad editable del despacho (litigante, tributarista,
--     revisor de citas…). Se INVOCA por sus frases (`summon_phrases`, el abogado la nombra
--     en su mensaje) o por selección explícita; NUNCA se auto-activa (consent-first).
--
--   `role_prompt` es la voz/método de la persona (autoridad de estilo; el cableado la
--     inyecta SIN poder anular las reglas duras de método y citación de L2/L3).
--   `model_tier` es el ÚNICO control de motor y es fail-closed por construcción:
--     · 'estandar' → respeta la política de modelo del despacho (techo = política; sin override).
--     · 'local'    → fuerza el motor local: estrictamente MÁS privado y barato que la política,
--                    nunca menos. Una persona JAMÁS elige un modelo crudo ni escala a la nube.
--
-- RLS fail-closed por tenant IGUAL que el resto (ver 020_automations.sql / 022_dream_
-- prescriptions.sql): ENABLE + FORCE + política ALL con app_current_tenant(). Migración por
-- `postgres` (execution/init_personas.py). Idempotente.

CREATE TABLE IF NOT EXISTS personas (
  id              uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id       uuid NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
  name            varchar(64)  NOT NULL,            -- "Litigante", "Tributarista"…
  title           varchar(120) NOT NULL DEFAULT '', -- rol corto para la UI ("Estratega procesal")
  role_prompt     text         NOT NULL,            -- la voz/método de la persona (system)
  tone            varchar(160) NOT NULL DEFAULT '', -- estilo/tono ("firme, persuasivo")
  focus_areas     text[]       NOT NULL DEFAULT '{}',-- áreas de énfasis (advisory, no ejecutable)
  model_tier      varchar(16)  NOT NULL DEFAULT 'estandar'
                  CHECK (model_tier IN ('estandar', 'local')),
  summon_phrases  text[]       NOT NULL DEFAULT '{}',-- frases de invocación ("como litigante")
  description     text         NOT NULL DEFAULT '', -- descripción en llano para el abogado
  enabled         boolean      NOT NULL DEFAULT true,
  created_at      timestamptz  NOT NULL DEFAULT now(),
  updated_at      timestamptz  NOT NULL DEFAULT now(),
  -- Nombre único por despacho, insensible a mayúsculas (una persona se nombra por su
  -- nombre; evita colisiones "Litigante"/"litigante" que confundirían la invocación).
  UNIQUE (tenant_id, name)
);

CREATE UNIQUE INDEX IF NOT EXISTS idx_personas_tenant_name_ci
  ON personas(tenant_id, lower(name));
CREATE INDEX IF NOT EXISTS idx_personas_tenant_enabled
  ON personas(tenant_id, enabled);

ALTER TABLE personas ENABLE ROW LEVEL SECURITY;
ALTER TABLE personas FORCE  ROW LEVEL SECURITY;
DROP POLICY IF EXISTS p_personas ON personas;
CREATE POLICY p_personas ON personas
  USING (tenant_id = app_current_tenant())
  WITH CHECK (tenant_id = app_current_tenant());
GRANT SELECT, INSERT, UPDATE, DELETE ON personas TO mia_app;
