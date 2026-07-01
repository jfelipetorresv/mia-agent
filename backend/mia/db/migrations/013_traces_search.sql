-- Mia · 013_traces_search.sql · Tarea H.3 — session_search FTS (tsvector+GIN) sin LLM
--
-- Hermes v0.17.0 hizo session_search ~4.500× más rápido eliminando la ruta LLM y usando un
-- índice FTS (FTS5+BM25 en su SQLite). Mia usa Postgres como store → el equivalente es una tabla
-- `traces` con `tsvector` + índice GIN, y ranking por `ts_rank_cd` (BM25-like), sin ninguna
-- llamada LLM en el camino caliente.
--
-- Las trazas de Mia viven hoy en JSONL (`mia-data/traces/`, por-tenant) para export SFT. Eso NO
-- tiene RLS ni índice. Esta tabla es el índice CONSULTABLE (dual-write desde el grafo): cada turno
-- escribe la traza al JSONL (como antes) y una fila aquí (con RLS por-tenant) para búsqueda.
--
--   traces — una fila por turno finalizado. `content_tsv` (tsvector) lo mantiene un TRIGGER en
--   cada INSERT/UPDATE. Se usa trigger (no columna generada) porque `to_tsvector('spanish', …)`
--   NO es inmutable (el cast text→regconfig es STABLE) y Postgres rechaza expresiones no-inmutables
--   en columnas generadas; un trigger no tiene esa restricción.
--
-- Patrón RLS por-tenant estándar. Migración por `postgres` (mia_app NO tiene CREATE). Idempotente.

CREATE EXTENSION IF NOT EXISTS pgcrypto;    -- gen_random_uuid()

CREATE TABLE IF NOT EXISTS traces (
  id                  uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id           uuid NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
  matter_id           text,
  input               text NOT NULL DEFAULT '',
  output              text NOT NULL DEFAULT '',
  model               text,
  hitl_outcome        text,               -- approved | rejected | edited
  activated_playbooks text[] NOT NULL DEFAULT '{}',
  retrieved_doc_ids   text[] NOT NULL DEFAULT '{}',
  trace_ts            timestamptz,        -- timestamp de la traza (ISO del JSONL)
  created_at          timestamptz NOT NULL DEFAULT now(),
  content_tsv         tsvector           -- lo llena el trigger trg_traces_tsv
);

-- Trigger que mantiene content_tsv en cada INSERT/UPDATE (input + output + playbooks + matter).
CREATE OR REPLACE FUNCTION traces_tsv_update() RETURNS trigger AS $$
BEGIN
  NEW.content_tsv := to_tsvector('spanish',
    coalesce(NEW.input, '') || ' ' || coalesce(NEW.output, '') || ' ' ||
    coalesce(array_to_string(NEW.activated_playbooks, ' '), '') || ' ' ||
    coalesce(NEW.matter_id, ''));
  RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS trg_traces_tsv ON traces;
CREATE TRIGGER trg_traces_tsv BEFORE INSERT OR UPDATE ON traces
  FOR EACH ROW EXECUTE FUNCTION traces_tsv_update();

-- Índice invertido para el match FTS + ranking (el que da la ganancia de velocidad).
CREATE INDEX IF NOT EXISTS idx_traces_content_tsv ON traces USING GIN (content_tsv);
-- Índice compuesto para el filtro por asunto y orden temporal.
CREATE INDEX IF NOT EXISTS idx_traces_tenant_matter ON traces(tenant_id, matter_id, trace_ts DESC);

-- ===================== RLS (patrón estándar por-tenant) =====================
ALTER TABLE traces ENABLE ROW LEVEL SECURITY;
ALTER TABLE traces FORCE  ROW LEVEL SECURITY;

DROP POLICY IF EXISTS p_traces ON traces;
CREATE POLICY p_traces ON traces
  USING (tenant_id = app_current_tenant())
  WITH CHECK (tenant_id = app_current_tenant());

GRANT SELECT, INSERT ON traces TO mia_app;
