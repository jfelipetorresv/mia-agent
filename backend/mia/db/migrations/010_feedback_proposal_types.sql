-- Mia · 010_feedback_proposal_types.sql · Tipos de propuestas del second brain.

ALTER TABLE feedback_proposals DROP CONSTRAINT IF EXISTS feedback_proposals_proposal_type_check;
ALTER TABLE feedback_proposals ADD CONSTRAINT feedback_proposals_proposal_type_check
  CHECK (proposal_type IN (
    'improve_playbook',
    'new_playbook',
    'flag_gap',
    'wiki_correction',
    'weekly_report'
  ));
