-- 049 · F1.1 del plan de eficiencia: la cosecha de aprendizaje (harvest) deja de correr
-- síncrona dentro del clic de Aprobar y su reporte deja de perderse (antes ni se persistía).
-- Ahora es una PROPUESTA pendiente que el abogado revisa en Memoria — cosecha sin escritura
-- en caliente: Mia propone, el abogado decide.
ALTER TABLE feedback_proposals DROP CONSTRAINT IF EXISTS feedback_proposals_proposal_type_check;
ALTER TABLE feedback_proposals ADD CONSTRAINT feedback_proposals_proposal_type_check
  CHECK (proposal_type IN (
    'improve_playbook',
    'new_playbook',
    'flag_gap',
    'wiki_correction',
    'weekly_report',
    'harvest_lessons',
    'soul_rule'
  ));
