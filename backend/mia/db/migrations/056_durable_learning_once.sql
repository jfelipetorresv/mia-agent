-- P0 · Cada señal de aprendizaje jurídico es inmutable y se procesa una sola vez.
-- La cola general permite repetir sincronizaciones ya completadas; estos cuatro
-- trabajos, ligados a la huella de un artefacto final, no deben duplicarse jamás.
CREATE UNIQUE INDEX IF NOT EXISTS uq_durable_learning_once
  ON durable_jobs (tenant_id, job_type, dedupe_key)
  WHERE job_type IN (
    'wiki_approved_artifact',
    'learn_approved_artifact',
    'skill_improvement',
    'harvest_lessons'
  );
