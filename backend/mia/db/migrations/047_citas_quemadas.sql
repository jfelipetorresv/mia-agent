-- Mia · 047_citas_quemadas.sql · BANCO DE CITAS QUEMADAS del despacho.
-- Migración ADITIVA e IDEMPOTENTE (CREATE TABLE IF NOT EXISTS). Re-ejecutable sin efecto.
--
-- POR QUÉ EXISTE (decisión de Pipe #46.2, 2026-07-27 — principio portado del harness de
-- litigio del despacho, `scripts/check-citas-quemadas.py`):
--   En julio de 2026, un banco de argumentos que el despacho tenía por «verificado» traía una
--   cita FABRICADA anclada a número y ponente reales. La lección que quedó escrita allí es la
--   que gobierna esta tabla: **lo que no tiene barrera, vuelve.** Verificar una cita falsa una
--   vez no sirve de nada si el sistema puede volver a emitirla mañana.
--
--   Regla del producto: cuando el abogado marca una cita como falsa (fabricada, tergiversada,
--   mal atribuida o simplemente inexistente), esa cita queda QUEMADA para siempre en SU
--   instalación y Mia no la vuelve a emitir. Es la única barrera de las cuatro que nace como
--   MURO y no como aviso, y la razón es que no admite falso positivo: o la cita está en la
--   lista que el propio abogado construyó, o no está. Ningún juicio, ninguna heurística.
--
-- AGNÓSTICA DE JURISDICCIÓN (regla dura de CLAUDE.md): la tabla no trae ni un vocabulario de
--   país. Cada despacho llena su propio banco con las citas de SU ordenamiento; el esquema solo
--   guarda texto normalizado y el motivo en llano. Un despacho español y uno colombiano usan la
--   misma tabla sin que el código sepa la diferencia.
--
-- APRENDIZAJE HEREDADO DEL ORIGINAL (retro 2026-07-23-001 del harness): al DOCUMENTAR una cita
--   quemada hay que usar marcadores explícitos, porque el propio check dispara sobre el texto
--   que la menciona. Aquí eso está resuelto por diseño: la lista vive en una TABLA, no en prosa
--   dentro de los documentos, así que documentar el caso no puede disparar la barrera.
--
-- Aplicada por `postgres` (mia_app no tiene CREATE). Ver `execution/init_citas_quemadas.py`.

-- ── La tabla ────────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS burned_citations (
  id           uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id    uuid NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
  -- Texto de la cita TAL COMO la escribió quien la quemó (para mostrársela al abogado).
  citation     text NOT NULL,
  -- La misma cita NORMALIZADA (minúsculas, sin tildes, separadores colapsados) — es la clave
  -- de comparación. La normalización la hace `agents.verification._normalize`, la MISMA que usa
  -- el escáner de citas: si las dos difirieran, el muro tendría un agujero por construcción.
  citation_norm text NOT NULL,
  -- En llano: por qué está quemada. Va al aviso que ve el abogado, así que se escribe para
  -- que lo lea una persona ("la sentencia real trata otro artículo", "el laudo es de otra
  -- cámara de comercio"), no para una máquina.
  reason       text NOT NULL DEFAULT '',
  -- Quién la quemó. 'abogado' es el caso normal (el HITL de rechazo con motivo); 'mia' queda
  -- disponible para cuando la propia verificación demuestre la falsedad contra la fuente
  -- oficial, sin que nadie tenga que acordarse de registrarla a mano.
  burned_by    varchar(16) NOT NULL DEFAULT 'abogado'
               CHECK (burned_by IN ('abogado', 'mia')),
  -- Pasaje o contexto donde apareció (opcional). Sirve para la revisión posterior: por qué se
  -- creyó buena, y para poder auditar la decisión sin memoria de nadie.
  pasaje       text NOT NULL DEFAULT '',
  created_at   timestamptz NOT NULL DEFAULT now()
);

-- Una cita quemada dos veces en el mismo despacho es la misma cita: la unicidad va sobre la
-- forma normalizada, no sobre el texto crudo ("Ley 4137 de 2091" y "ley 4137 de 2091" son una).
CREATE UNIQUE INDEX IF NOT EXISTS uq_burned_citations_tenant_norm
  ON burned_citations(tenant_id, citation_norm);

-- La lectura caliente es «todas las quemadas de este despacho» (una vez por turno, cacheada).
CREATE INDEX IF NOT EXISTS idx_burned_citations_tenant
  ON burned_citations(tenant_id, created_at DESC);

-- ── RLS por tenant (mismo patrón que soul_versions, 040) ────────────────────
-- El banco de un despacho no puede filtrarse a otro: es la lista de errores que ENCONTRÓ,
-- y esa lista es información sobre sus propios expedientes.
ALTER TABLE burned_citations ENABLE ROW LEVEL SECURITY;
ALTER TABLE burned_citations FORCE  ROW LEVEL SECURITY;
DROP POLICY IF EXISTS p_burned_citations ON burned_citations;
CREATE POLICY p_burned_citations ON burned_citations
  USING (tenant_id = app_current_tenant())
  WITH CHECK (tenant_id = app_current_tenant());
GRANT SELECT, INSERT, UPDATE, DELETE ON burned_citations TO mia_app;
