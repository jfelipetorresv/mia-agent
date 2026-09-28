-- Same final text may be reviewed again under a new live evidence context.
-- Preserve history and original uniqueness for non-final artifacts.
DROP INDEX IF EXISTS uq_legal_artifact_ledger_version;
CREATE UNIQUE INDEX IF NOT EXISTS uq_legal_artifact_ledger_version
  ON legal_artifact_ledger(tenant_id, matter_id, artifact_kind, content_hash,
                          COALESCE(parent_hash, '')) WHERE artifact_kind <> 'final';
CREATE UNIQUE INDEX IF NOT EXISTS uq_legal_final_context
  ON legal_artifact_ledger(tenant_id, matter_id, content_hash, COALESCE(parent_hash, ''),
                          COALESCE(metadata->>'verification_context_hash', ''))
  WHERE artifact_kind = 'final';
