-- Mia · 044_playbook_health.sql · Meta E (Mitad 1) — salud de las guías del despacho
--
-- Hoy una guía (playbook) vive o muere sin que nadie sepa si sus citas quedaron sin marcar.
-- Este parche añade un estado de salud PERSISTIDO por guía, calculado por el escáner
-- determinista de citas ya gateado (agents.verification.annotate_draft — CP9), nunca por un
-- criterio jurídico nuevo. §G: los tres valores se traducen en pantalla a "sana / revisar /
-- sin revisar", nunca se muestra el nombre técnico de la columna.
--
-- health_status: 'sano' (el escáner no tuvo que anotar ninguna cita), 'revisar' (encontró al
-- menos una cita sin marcar ni respaldo) o 'sin_revisar' (default; también el valor FAIL-OPEN
-- si el chequeo no se pudo completar — una guía que no se puede evaluar NUNCA rompe el flujo
-- del abogado, memory/playbook_health.py).
-- health_checked_at: cuándo se corrió el último chequeo (NULL = nunca).
-- health_report: informe compacto y serializable del escáner (citas/marcadas/respaldadas/
-- anotadas + mensaje en llano), el mismo shape que ya viaja en metadata de otros informes.
--
-- Patrón calcado de 029_playbook_versions.sql / 040_soul_versions.sql: ALTER TABLE aditivo,
-- índice parcial sobre la tabla ya existente (RLS y GRANT de `playbooks` no cambian — la
-- política p_playbooks de 005_playbooks.sql ya cubre estas columnas nuevas). Migración por
-- `postgres` (execution/init_playbook_health.py). Idempotente.

ALTER TABLE playbooks
  ADD COLUMN IF NOT EXISTS health_status varchar(16) NOT NULL DEFAULT 'sin_revisar'
    CHECK (health_status IN ('sano', 'revisar', 'sin_revisar')),
  ADD COLUMN IF NOT EXISTS health_checked_at timestamptz,
  ADD COLUMN IF NOT EXISTS health_report jsonb NOT NULL DEFAULT '{}'::jsonb;

CREATE INDEX IF NOT EXISTS idx_playbooks_tenant_health
  ON playbooks (tenant_id, health_status)
  WHERE status = 'active';
