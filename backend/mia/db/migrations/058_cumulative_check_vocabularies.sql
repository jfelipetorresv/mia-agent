-- 058 · Reafirma los CHECK de vocabulario ACUMULADO en una migración propia.
--
-- Por qué existe: el commit 05c8f8c amplió estos vocabularios EDITANDO las
-- migraciones históricas 010/027/040/049 ya aplicadas. El ledger de checksums de
-- db_bootstrap es fail-closed ("no modifiques la anterior") y ese cambio habría
-- bloqueado el arranque de toda instalación existente al actualizar. Las cuatro
-- migraciones volvieron a su contenido registrado y el estado final vive aquí.
-- Regla de APRENDIZAJES 2026-08-12: una migración reejecutable conserva el
-- vocabulario acumulado del esquema vigente.

ALTER TABLE documents DROP CONSTRAINT IF EXISTS ck_documents_origin;
ALTER TABLE documents
  ADD CONSTRAINT ck_documents_origin
  CHECK (origin IN ('upload', 'folder', 'mail', 'drive', 'mia'));

ALTER TABLE feedback_proposals DROP CONSTRAINT IF EXISTS feedback_proposals_proposal_type_check;
ALTER TABLE feedback_proposals
  ADD CONSTRAINT feedback_proposals_proposal_type_check
  CHECK (proposal_type IN (
    'improve_playbook',
    'new_playbook',
    'flag_gap',
    'wiki_correction',
    'weekly_report',
    'soul_rule',
    'harvest_lessons'
  ));
