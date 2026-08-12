-- Mia · 040_soul_versions.sql · La identidad es sagrada: ningún agente la escribe solo.
--
-- NÚMERO: nació como 038 y se renumeró al 040 al integrar. Historia, porque explica un
-- riesgo real del trabajo en paralelo: el 037 se lo llevó `037_matter_agent_consent.sql`
-- (CP-HUB2) y este frente se movió al 038 — que ya estaba asignado a
-- `038_curator_conflicts.sql`. Dos archivos con el MISMO prefijo rompen el orden del
-- ledger (`setup/paths.migration_paths()` ordena por NOMBRE) y el checksum del gate F0.
-- La DB de dev es anterior al ledger y se aplicó a mano, así que renumerar es seguro;
-- las instalaciones nuevas la recogen por orden. Regla para el futuro: el número de
-- migración se reserva al empezar, no al escribir el archivo.
--
-- POR QUÉ EXISTE
-- El SOUL.md es la capa 1 del prompt: se inyecta ENTERA, sin tope y con autoridad de
-- sistema (`agent/prompt_builder.py`). Hasta hoy `memory/dreams.py::_append_soul_rule`
-- escribía reglas ahí AUTOMÁTICAMENTE — sin aprobación del abogado, sin tope de tamaño y
-- sin historial. Era el único escritor automático sin freno sobre la capa de MÁS autoridad
-- del sistema, mientras que los playbooks —que importan menos— sí tenían `playbook_versions`,
-- `changed_by`, motivo en llano y aprobación atómica. La capa mejor protegida era la menos
-- importante. Esta migración invierte eso.
--
-- ESPEJO DELIBERADO DE 029_playbook_versions.sql: mismas columnas de gobierno
-- (`changed_by` ∈ ('abogado','mia'), `reason` SIEMPRE en llano §G, snapshot del estado
-- ANTERIOR, `created_at`). La diferencia es que el estado anterior del SOUL es UN texto
-- (el archivo entero), no una fila con campos.
--
-- FICHERO vs DB (decisión, ver `memory/soul_manager.py`): el SOUL vive en
-- $MIA_HOME/soul_{tenant}.md — fuera de la DB y SIN RLS. Su historial vive AQUÍ, con RLS.
-- El FICHERO es la fuente de verdad (es lo que lee el prompt); esta tabla es el LIBRO DE
-- CUENTAS. Por eso `soul_manager` toma el snapshot leyendo el fichero real en cada cambio,
-- nunca de esta tabla: si un registro se perdiera, el siguiente cambio vuelve a capturar el
-- estado real y el historial se reancla solo. Nunca se reconstruye el SOUL desde la DB.
--
-- Patrón RLS calcado de 029: ENABLE + FORCE + política ALL con app_current_tenant(),
-- GRANT a mia_app. Migración por `postgres` (execution/init_soul_versions.py). Idempotente
-- y aditiva: no toca ni borra nada existente.

CREATE EXTENSION IF NOT EXISTS pgcrypto;    -- gen_random_uuid()

CREATE TABLE IF NOT EXISTS soul_versions (
  id          uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id   uuid NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
  -- Snapshot del SOUL.md COMPLETO tal como estaba ANTES del cambio ('' si no existía:
  -- el primer cambio de un despacho nuevo es un estado anterior legítimamente vacío).
  content     text NOT NULL,
  changed_by  varchar(16) NOT NULL CHECK (changed_by IN ('abogado', 'mia')),
  reason      text NOT NULL DEFAULT '',   -- en llano: qué motivó el cambio (§G)
  created_at  timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_soul_versions_tenant
  ON soul_versions(tenant_id, created_at DESC);

ALTER TABLE soul_versions ENABLE ROW LEVEL SECURITY;
ALTER TABLE soul_versions FORCE  ROW LEVEL SECURITY;
DROP POLICY IF EXISTS p_soul_versions ON soul_versions;
CREATE POLICY p_soul_versions ON soul_versions
  USING (tenant_id = app_current_tenant())
  WITH CHECK (tenant_id = app_current_tenant());
GRANT SELECT, INSERT, UPDATE, DELETE ON soul_versions TO mia_app;

-- ── El tipo de propuesta 'soul_rule' ────────────────────────────────────────
-- Dreams deja de ESCRIBIR el SOUL y pasa a PROPONER por el mecanismo que ya existe
-- (feedback_proposals → Pantalla 4 → POST /proposals/{id}/apply). No se inventa un canal
-- nuevo: el abogado ya sabe dónde aprueba las sugerencias de Mia. Se reemplaza el CHECK
-- completo (mismo patrón que 010_feedback_proposal_types.sql) añadiendo el tipo nuevo.
ALTER TABLE feedback_proposals DROP CONSTRAINT IF EXISTS feedback_proposals_proposal_type_check;
ALTER TABLE feedback_proposals ADD CONSTRAINT feedback_proposals_proposal_type_check
  CHECK (proposal_type IN (
    'improve_playbook',
    'new_playbook',
    'flag_gap',
    'wiki_correction',
    'weekly_report',
    'soul_rule',
    'harvest_lessons'
  ));
