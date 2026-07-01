-- Mia · 014_playbooks_protected.sql · Tarea H.6 — playbooks protegidos (seed / core del despacho)
--
-- Hermes v0.17.0 marca ciertos skills/playbooks como `protected` para que el mantenimiento
-- automático (consolidación, poda, mejora) NO los altere: son la metodología semilla del despacho,
-- curada a mano, y deben sobrevivir a los ciclos del Curator/GEPA/SkillImprover. Sin esta bandera,
-- un playbook "core" podría fusionarse o podarse por antigüedad/solapamiento y perderse.
--
-- Añade `protected boolean NOT NULL DEFAULT false` a `playbooks`. Idempotente (IF NOT EXISTS).
-- Migración aplicada por `postgres` (mia_app NO tiene ALTER). No cambia RLS ni grants existentes.

ALTER TABLE playbooks
  ADD COLUMN IF NOT EXISTS protected boolean NOT NULL DEFAULT false;

-- Índice parcial: acelera los filtros `AND NOT protected` del Curator/GEPA sobre tablas grandes.
CREATE INDEX IF NOT EXISTS idx_playbooks_protected
  ON playbooks(tenant_id) WHERE protected;
