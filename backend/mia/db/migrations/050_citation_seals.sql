-- Mia · 050_citation_seals.sql · SELLOS DE VERIFICACIÓN del despacho (F2 del plan de
-- eficiencia, specs/todo/PLAN-principios-harness-llos-eficiencia.md).
-- Migración ADITIVA e IDEMPOTENTE (CREATE TABLE IF NOT EXISTS). Re-ejecutable sin efecto.
--
-- POR QUÉ EXISTE (principio portado del harness de litigio del despacho — el sello como
-- caché de verificación): una cita que ya quedó RESPALDADA por el guardián determinista y
-- APROBADA por el abogado dentro de un borrador no tiene por qué re-auditarse con modelo en
-- cada turno siguiente. El sello registra ESA aprobación; el gate LLM solo audita lo no
-- sellado. Cuanto más maduro el acervo del despacho, más barata cada corrida — y el
-- estándar no se degrada, porque el sello nace de verificación + decisión humana, nunca de
-- una heurística.
--
-- REGLAS DURAS:
--   · El banco de citas QUEMADAS siempre le gana al sello: quemar una cita revoca su sello
--     en la misma transacción (memory/burned_citations.burn).
--   · El sello se coteja con la MISMA normalización del escáner (verification._normalize);
--     si difirieran, la caché tendría un agujero por construcción.
--   · Agnóstica de jurisdicción: solo texto normalizado y la fuente que dio el respaldo.
--
-- Aplicada por `postgres` (mia_app no tiene CREATE), mismo patrón que 047.

CREATE TABLE IF NOT EXISTS citation_seals (
  id            uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id     uuid NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
  -- La cita tal como se aprobó (para mostrársela al abogado).
  citation      text NOT NULL,
  -- La misma cita normalizada — la clave de comparación del muro.
  citation_norm text NOT NULL,
  -- La fuente que dio el respaldo determinista cuando se selló (corpus o expediente).
  fuente_tipo   text NOT NULL DEFAULT '',
  fuente_ref    text NOT NULL DEFAULT '',
  fuente_titulo text NOT NULL DEFAULT '',
  -- De dónde nace el sello. 'aprobacion_abogado' es el único origen de v1: respaldada por
  -- el muro Y dentro de un borrador que el abogado aprobó.
  origen        varchar(32) NOT NULL DEFAULT 'aprobacion_abogado'
                CHECK (origen IN ('aprobacion_abogado')),
  -- Traza del turno cuya aprobación selló (auditable sin memoria de nadie).
  trace_id      text NOT NULL DEFAULT '',
  created_at    timestamptz NOT NULL DEFAULT now()
);

-- La misma cita sellada dos veces es la misma cita: unicidad por forma normalizada.
CREATE UNIQUE INDEX IF NOT EXISTS uq_citation_seals_tenant_norm
  ON citation_seals(tenant_id, citation_norm);

-- La lectura caliente es «todos los sellos de este despacho» (una vez por turno, cacheada).
CREATE INDEX IF NOT EXISTS idx_citation_seals_tenant
  ON citation_seals(tenant_id, created_at DESC);

-- ── RLS por tenant (mismo patrón que burned_citations, 047) ────────────────────
ALTER TABLE citation_seals ENABLE ROW LEVEL SECURITY;
ALTER TABLE citation_seals FORCE  ROW LEVEL SECURITY;
DROP POLICY IF EXISTS p_citation_seals ON citation_seals;
CREATE POLICY p_citation_seals ON citation_seals
  USING (tenant_id = app_current_tenant())
  WITH CHECK (tenant_id = app_current_tenant());
GRANT SELECT, INSERT, UPDATE, DELETE ON citation_seals TO mia_app;
