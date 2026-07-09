-- Mia · 026_feedback_proposal_target_concept.sql · Frente B (aprendizaje) — corrección
-- de revisor capa 2: `wiki_correction` guardaba el nombre del concepto codificado dentro
-- de `rationale` (prefijo de texto libre) y `apply_proposal` lo recuperaba parseando ese
-- prefijo — si el prefijo cambia, o el rationale se edita/normaliza, el parseo falla en
-- silencio y la corrección aprobada nunca se escribe (queda "applied" sin efecto).
--
-- Columna dedicada, igual que `target_playbook_id` para `improve_playbook`: el tipo de
-- destino ya no depende de parsear texto libre. Idempotente.

ALTER TABLE feedback_proposals ADD COLUMN IF NOT EXISTS target_concept text;
