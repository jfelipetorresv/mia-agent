-- Mia · 038_curator_conflicts.sql · "Contradicción antes que fusión" — el Curator deja de fundir
-- criterios que se contradicen.
--
-- EL PROBLEMA QUE CIERRA: el Curator buscaba pares de playbooks con similitud coseno > 0.85 y le
-- pedía a un modelo que los FUNDIERA en uno. Pero similitud NO es compatibilidad: "en estos casos
-- siempre pedimos X" y "en estos casos nunca pedimos X" son semánticamente casi idénticos — el
-- coseno los ve como gemelos y la fusión producía una mezcla que no decía NINGUNA de las dos
-- cosas. Ahí es donde el criterio de un despacho se corrompe sin que nadie lo vea: el criterio
-- evoluciona y a veces se INVIERTE, y si la memoria funde la versión vieja con la nueva, Mia
-- acaba operando con un criterio que nadie sostuvo jamás.
--
-- EL PRINCIPIO: si lo nuevo contradice lo existente, no se pisa ni se funde. Se marca el
-- conflicto con AMBAS versiones vivas y su fecha, y decide el dueño. La contradicción es un
-- estado LEGÍTIMO y VISIBLE de la memoria, no un error que se limpia solo.
--
-- QUÉ AÑADE (aditivo e idempotente; ninguna fila existente cambia de comportamiento):
--   kind        — tipo de propuesta. 'cleanup' (lo de siempre: fusiones + podas, se aprueba o se
--                 rechaza en bloque) | 'conflict' (dos versiones enfrentadas; NO se aprueba: se
--                 RESUELVE eligiendo una, o ninguna). DEFAULT 'cleanup' → las propuestas ya
--                 persistidas siguen siendo exactamente lo que eran.
--   conflict    — payload del conflicto, NULL salvo en kind='conflict':
--                 {"a": {id,title,summary,applies_when,extracto,fecha,procedencia,dice},
--                  "b": {...}, "score": 0.93, "confianza": 0.9}
--                 `dice` es el resumen de LO QUE ORDENA CADA VERSIÓN por separado — nunca un
--                 texto ya mezclado: el abogado ve A contra B, no una fusión.
--   resolution  — qué eligió el abogado: 'a' | 'b' | 'none' (dejar las dos vivas). NULL mientras
--                 esté pendiente. Queda para auditoría: quién decidió que el criterio es este.
--
-- POR QUÉ UNA FILA POR CONFLICTO Y NO UNA LISTA DENTRO DE LA PROPUESTA DE LIMPIEZA: aprobar una
-- limpieza es un sí/no en bloque; un conflicto es una ELECCIÓN BINARIA por par. Mezclarlos
-- obligaría al abogado a decidir dos cosas distintas con un solo botón — exactamente el atajo que
-- este cambio existe para impedir.
--
-- Migración por `postgres` (mia_app NO tiene ALTER). No cambia RLS ni grants: `curator_proposals`
-- ya tiene ENABLE+FORCE ROW LEVEL SECURITY y la política p_curator_proposals por tenant (012), y
-- los conflictos viven en esa misma tabla → el aislamiento entre despachos se hereda intacto.

ALTER TABLE curator_proposals ADD COLUMN IF NOT EXISTS kind       varchar(20) NOT NULL DEFAULT 'cleanup';
ALTER TABLE curator_proposals ADD COLUMN IF NOT EXISTS conflict   jsonb;
ALTER TABLE curator_proposals ADD COLUMN IF NOT EXISTS resolution varchar(10);

ALTER TABLE curator_proposals DROP CONSTRAINT IF EXISTS curator_proposals_kind_check;
ALTER TABLE curator_proposals ADD  CONSTRAINT curator_proposals_kind_check
  CHECK (kind IN ('cleanup', 'conflict'));

ALTER TABLE curator_proposals DROP CONSTRAINT IF EXISTS curator_proposals_resolution_check;
ALTER TABLE curator_proposals ADD  CONSTRAINT curator_proposals_resolution_check
  CHECK (resolution IS NULL OR resolution IN ('a', 'b', 'none'));

-- Una propuesta de conflicto SIN payload sería un conflicto invisible: el abogado vería la
-- pregunta sin las dos versiones que tiene que comparar. Se prohíbe en el esquema.
ALTER TABLE curator_proposals DROP CONSTRAINT IF EXISTS curator_proposals_conflict_payload_check;
ALTER TABLE curator_proposals ADD  CONSTRAINT curator_proposals_conflict_payload_check
  CHECK (kind <> 'conflict' OR conflict IS NOT NULL);

-- El Curator, en CADA corrida, pregunta "¿ya le mostré este par al abogado?" antes de volver a
-- gastar el juez y antes de volver a preguntar. Este índice sirve esa consulta
-- (tenant + kind='conflict' + status IN ('pending','rejected')).
CREATE INDEX IF NOT EXISTS idx_curator_proposals_tenant_kind_status
  ON curator_proposals(tenant_id, kind, status);
