-- Mia · 062_shortcut_prefs.sql · ATAJOS EDITABLES de la firma u organización (bloque D7).
-- Migración ADITIVA e IDEMPOTENTE (CREATE TABLE IF NOT EXISTS). Re-ejecutable sin efecto.
--
-- POR QUÉ EXISTE (punto 18 de la bitácora de feedback 2026-08-19):
--   Los atajos de la conversación vacía se DERIVAN solos de las guías activas y de los
--   agentes del despacho (`backend/mia/memory/atajos.py`). Esa derivación es valiosa —
--   aparecen sin que nadie los configure— pero era la única fuente: para cambiar un atajo
--   había que ir a editar la guía o el agente del que salía, y no había forma de agregar uno
--   propio ni de quitar uno que estorba.
--
--   Esta tabla NO reemplaza la derivación: la CUBRE con una capa de preferencias del
--   despacho. Cada fila dice qué hizo el abogado con UN atajo:
--     · fijarlo   (`pinned`)  → no se cae aunque la guía baje en el ranking de uso
--     · ocultarlo (`hidden`)  → no vuelve a aparecer, sin tener que borrar la guía
--     · renombrarlo (`label`) → cambia el texto VISIBLE, no lo que se envía
--     · agregarlo (`source='propio'`) → un atajo escrito por el abogado, que no deriva de nada
--
--   Si un despacho no toca nada, esta tabla queda vacía y el comportamiento es exactamente
--   el de antes. Es aditiva también en conducta, no solo en esquema.
--
-- AGNÓSTICA DE JURISDICCIÓN (regla dura de CLAUDE.md): no hay ni un vocabulario de país.
--   Solo texto libre que escribe cada despacho.
--
-- Aplicada por `postgres` (mia_app no tiene CREATE). Ver `execution/init_shortcut_prefs.py`.

-- ── La tabla ────────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS shortcut_prefs (
  id           uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id    uuid NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
  -- De dónde sale el atajo al que se refiere esta preferencia:
  --   'guia'   → una fila de `playbooks`     (source_id = playbooks.id)
  --   'agente' → una fila de `personas`      (source_id = personas.id)
  --   'propio' → no deriva de nada: lo escribió el abogado (source_id IS NULL)
  source       varchar(16) NOT NULL
               CONSTRAINT ck_shortcut_prefs_source CHECK (source IN ('guia', 'agente', 'propio')),
  -- Deliberadamente SIN foreign key a playbooks/personas: si el despacho borra una guía, la
  -- preferencia queda huérfana y `list_shortcuts` la ignora (no hay nada que derivar). Una FK
  -- con CASCADE obligaría a elegir una sola tabla destino y no existe tal columna polimórfica
  -- en Postgres. La limpieza de huérfanas es cosmética, no de integridad: nada las lee.
  source_id    uuid,
  -- Nombre VISIBLE del atajo. '' = usar el que se deriva (título de la guía / nombre del
  -- agente). En 'propio' es obligatorio y lo valida la capa de dominio.
  label        text NOT NULL DEFAULT '',
  -- Texto que se PRE-LLENA en el cuadro de mensaje. '' = usar el derivado. En 'propio' es
  -- obligatorio. Renombrar NO cambia esto: el abogado cambia la etiqueta, no la instrucción.
  texto        text NOT NULL DEFAULT '',
  -- Fijado: entra siempre en la conversación vacía, aunque el reparto automático lo dejara
  -- fuera. Lo fijado nunca se descarta en silencio (ver memory/atajos.py).
  pinned       boolean NOT NULL DEFAULT false,
  -- Oculto: no aparece nunca. `pinned` y `hidden` a la vez no tiene sentido; el dominio no lo
  -- permite y aquí queda además como CHECK para que ningún camino futuro lo cuele.
  hidden       boolean NOT NULL DEFAULT false,
  CONSTRAINT ck_shortcut_prefs_pin_o_hide CHECK (NOT (pinned AND hidden)),
  -- Orden entre los fijados y los propios (menor primero). Empate → created_at.
  position     integer NOT NULL DEFAULT 0,
  created_at   timestamptz NOT NULL DEFAULT now(),
  updated_at   timestamptz NOT NULL DEFAULT now()
);

-- Un atajo derivado tiene UNA preferencia por despacho: fijar dos veces la misma guía es
-- fijarla una vez. Los propios quedan fuera del índice (source_id IS NULL): cada uno es una
-- fila distinta identificada por su `id`, y dos atajos propios pueden llamarse igual.
CREATE UNIQUE INDEX IF NOT EXISTS uq_shortcut_prefs_tenant_source
  ON shortcut_prefs(tenant_id, source, source_id)
  WHERE source_id IS NOT NULL;

-- La lectura caliente es «todas las preferencias de este despacho» (una vez por pantalla).
CREATE INDEX IF NOT EXISTS idx_shortcut_prefs_tenant
  ON shortcut_prefs(tenant_id, position, created_at);

-- ── RLS por tenant (mismo patrón que burned_citations, 047) ─────────────────
-- Los atajos de un despacho nombran sus guías, sus agentes y su forma de trabajar: no pueden
-- filtrarse a otro.
ALTER TABLE shortcut_prefs ENABLE ROW LEVEL SECURITY;
ALTER TABLE shortcut_prefs FORCE  ROW LEVEL SECURITY;
DROP POLICY IF EXISTS p_shortcut_prefs ON shortcut_prefs;
CREATE POLICY p_shortcut_prefs ON shortcut_prefs
  USING (tenant_id = app_current_tenant())
  WITH CHECK (tenant_id = app_current_tenant());
GRANT SELECT, INSERT, UPDATE, DELETE ON shortcut_prefs TO mia_app;
