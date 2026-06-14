-- Mia · 003_sat_graph.sql · Módulo 3a — SAT-Graph (corpus jurídico COMPARTIDO)
-- Corpus jurídico (normas, relaciones, jurisprudencia) compartido entre TODOS los
-- tenants. Las normas y sentencias de Colombia son públicas → NO es dato por-tenant.
-- EXCEPCIÓN DOCUMENTADA al patrón RLS por-tenant del resto del schema (decisión #16,
-- architecture/rls_isolation.md): RLS habilitado pero con política ABIERTA USING(true).
--
-- Migración aplicada por `postgres` (mia_app NO tiene CREATE). Idempotente: re-ejecutable.

CREATE EXTENSION IF NOT EXISTS pgcrypto;   -- gen_random_uuid() (idempotente)

-- ===================== Tablas =====================

-- Normas: leyes, decretos, sentencias-como-norma, resoluciones, etc.
CREATE TABLE IF NOT EXISTS legal_norms (
  id             uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  norm_type      varchar(50) NOT NULL
                 CHECK (norm_type IN ('ley','decreto','sentencia','resolucion','circular','acuerdo')),
  norm_number    varchar(100),
  issuing_body   varchar(200),
  title          text,
  summary        text,
  full_text      text,
  effective_date date NOT NULL,
  expiry_date    date,                              -- NULL = vigente
  jurisdiction   varchar(50) NOT NULL DEFAULT 'colombia',
  practice_areas text[],
  fts_vector     tsvector,                          -- lo llena el trigger (pesos A/B/C)
  metadata       jsonb NOT NULL DEFAULT '{}'::jsonb,
  created_at     timestamptz NOT NULL DEFAULT now(),
  updated_at     timestamptz NOT NULL DEFAULT now(),
  -- clave de upsert para add_norm ON CONFLICT(norm_number, issuing_body)
  CONSTRAINT uq_legal_norms_number_body UNIQUE (norm_number, issuing_body)
);

-- Relaciones tipadas entre normas (el "grafo" del SAT-Graph).
CREATE TABLE IF NOT EXISTS norm_relations (
  id              uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  source_norm_id  uuid NOT NULL REFERENCES legal_norms(id) ON DELETE CASCADE,
  target_norm_id  uuid NOT NULL REFERENCES legal_norms(id) ON DELETE CASCADE,
  relation_type   varchar(50) NOT NULL
                  CHECK (relation_type IN ('remite_a','modifica_a','deroga_a','excepciona_a',
                                           'define_termino','complementa_a','interpreta_a')),
  effective_date  date,
  notes           text,
  created_at      timestamptz NOT NULL DEFAULT now(),
  CONSTRAINT uq_norm_relations UNIQUE (source_norm_id, target_norm_id, relation_type)
);

-- Jurisprudencia (providencias de altas cortes).
CREATE TABLE IF NOT EXISTS jurisprudence (
  id                  uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  norm_id             uuid REFERENCES legal_norms(id) ON DELETE SET NULL,
  court               varchar(100),
  sala                varchar(100),
  decision_number     varchar(100),
  radicado            varchar(200),
  magistrado_ponente  varchar(200),
  decision_date       date NOT NULL,
  topic               text,
  ratio_decidendi     text,
  obiter_dicta        text,
  keywords            text[],
  fts_vector          tsvector,                      -- lo llena el trigger (pesos A/B/C/D)
  metadata            jsonb NOT NULL DEFAULT '{}'::jsonb,
  created_at          timestamptz NOT NULL DEFAULT now(),
  -- clave de upsert para add_jurisprudence ON CONFLICT(decision_number, court)
  CONSTRAINT uq_jurisprudence_decision_court UNIQUE (decision_number, court)
);

-- ===================== Triggers FTS (configuración 'spanish') =====================
-- Pesos: legal_norms A=title, B=summary, C=full_text.
CREATE OR REPLACE FUNCTION legal_norms_fts_update() RETURNS trigger
LANGUAGE plpgsql AS $$
BEGIN
  NEW.fts_vector :=
      setweight(to_tsvector('spanish', coalesce(NEW.title, '')),     'A') ||
      setweight(to_tsvector('spanish', coalesce(NEW.summary, '')),   'B') ||
      setweight(to_tsvector('spanish', coalesce(NEW.full_text, '')), 'C');
  RETURN NEW;
END $$;

DROP TRIGGER IF EXISTS trg_legal_norms_fts ON legal_norms;
CREATE TRIGGER trg_legal_norms_fts
  BEFORE INSERT OR UPDATE ON legal_norms
  FOR EACH ROW EXECUTE FUNCTION legal_norms_fts_update();

-- Pesos: jurisprudence A=decision_number, B=topic, C=ratio_decidendi, D=keywords (array->texto).
CREATE OR REPLACE FUNCTION jurisprudence_fts_update() RETURNS trigger
LANGUAGE plpgsql AS $$
BEGIN
  NEW.fts_vector :=
      setweight(to_tsvector('spanish', coalesce(NEW.decision_number, '')),                 'A') ||
      setweight(to_tsvector('spanish', coalesce(NEW.topic, '')),                            'B') ||
      setweight(to_tsvector('spanish', coalesce(NEW.ratio_decidendi, '')),                  'C') ||
      setweight(to_tsvector('spanish', coalesce(array_to_string(NEW.keywords, ' '), '')),   'D');
  RETURN NEW;
END $$;

DROP TRIGGER IF EXISTS trg_jurisprudence_fts ON jurisprudence;
CREATE TRIGGER trg_jurisprudence_fts
  BEFORE INSERT OR UPDATE ON jurisprudence
  FOR EACH ROW EXECUTE FUNCTION jurisprudence_fts_update();

-- ===================== Índices =====================
CREATE INDEX IF NOT EXISTS idx_legal_norms_fts        ON legal_norms USING gin(fts_vector);
CREATE INDEX IF NOT EXISTS idx_legal_norms_effective  ON legal_norms(effective_date);
CREATE INDEX IF NOT EXISTS idx_legal_norms_expiry     ON legal_norms(expiry_date);
CREATE INDEX IF NOT EXISTS idx_legal_norms_areas      ON legal_norms USING gin(practice_areas);
CREATE INDEX IF NOT EXISTS idx_jurisprudence_fts      ON jurisprudence USING gin(fts_vector);
CREATE INDEX IF NOT EXISTS idx_jurisprudence_date     ON jurisprudence(decision_date);
CREATE INDEX IF NOT EXISTS idx_jurisprudence_keywords ON jurisprudence USING gin(keywords);
-- joins de relaciones (get_related_norms / get_norm_chain): índices de FK, baratos.
CREATE INDEX IF NOT EXISTS idx_norm_relations_source  ON norm_relations(source_norm_id);
CREATE INDEX IF NOT EXISTS idx_norm_relations_target  ON norm_relations(target_norm_id);

-- ===================== RLS (corpus compartido — excepción documentada) =====================
-- Decisión #16: estas 3 tablas NO son por-tenant. El corpus jurídico es público.
-- RLS habilitado por uniformidad, pero la política es ABIERTA (USING true): cualquier
-- conexión mia_app (con o sin app.tenant_id) lee el corpus completo. La escritura se
-- restringe a mia_app por GRANT (único rol no-superusuario). Bajo NOBYPASSRLS, una tabla
-- con RLS habilitado y sin política permisiva RECHAZA toda escritura: por eso la policy
-- incluye WITH CHECK (true) — sin ella, el propio ingest de mia_app fallaría.
-- (No se usa FORCE: el dueño es postgres, superusuario, que ignora RLS de todos modos.)
DO $$
DECLARE t text;
BEGIN
  FOREACH t IN ARRAY ARRAY['legal_norms','norm_relations','jurisprudence'] LOOP
    EXECUTE format('ALTER TABLE %I ENABLE ROW LEVEL SECURITY', t);
  END LOOP;
END $$;

DROP POLICY IF EXISTS p_sat_legal_norms ON legal_norms;
CREATE POLICY p_sat_legal_norms ON legal_norms USING (true) WITH CHECK (true);

DROP POLICY IF EXISTS p_sat_norm_relations ON norm_relations;
CREATE POLICY p_sat_norm_relations ON norm_relations USING (true) WITH CHECK (true);

DROP POLICY IF EXISTS p_sat_jurisprudence ON jurisprudence;
CREATE POLICY p_sat_jurisprudence ON jurisprudence USING (true) WITH CHECK (true);

-- ===================== Grants al rol de aplicación =====================
-- Escritura del corpus restringida a mia_app (no hay otro rol no-superusuario).
GRANT SELECT, INSERT, UPDATE, DELETE ON legal_norms, norm_relations, jurisprudence TO mia_app;
