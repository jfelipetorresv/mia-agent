-- Mia · 064_persona_capabilities.sql · CAPACIDADES de un agente jurídico (bloque D8).
-- Migración ADITIVA e IDEMPOTENTE (ADD COLUMN IF NOT EXISTS). Re-ejecutable sin efecto.
--
-- POR QUÉ EXISTE (punto 23 de la bitácora de feedback 2026-08-19, decisión D8 de Pipe):
--   El diseñador de agentes deja decir el nombre, el encargo, el tono, las áreas y las
--   frases con las que se le llama — todo texto libre. Lo que NO había era forma de decir
--   QUÉ PUEDE HACER el agente. El único control parecido era el nivel de motor, que cambia
--   la privacidad del modelo, no la capacidad, y por eso el abogado terminaba metiendo
--   «que lea los escaneados» dentro del encargo en prosa, donde no activa nada.
--
--   Las tres capacidades que pidió Pipe existen de verdad en el producto, y por eso se
--   pueden ofrecer sin prometer de más:
--     · 'lectura_visual'      → leer imágenes, diagramas y documentos escaneados (lectura
--                               óptica, componente opcional de la instalación);
--     · 'investigacion_viva'  → buscar normas y jurisprudencia en vivo (ayudante de
--                               investigación o de navegación del Agent Hub);
--     · 'documentos_largos'   → producir documentos largos con su formato (ayudante de
--                               documentos del Agent Hub).
--
--   Una capacidad marcada NO garantiza que exista en ESTA instalación: si el componente o
--   el ayudante no están, la pantalla lo dice con su razón y el agente sigue funcionando
--   sin ella. Marcar es una decisión del abogado; poder es una propiedad de la máquina, y
--   no se confunden. Esta columna guarda lo primero.
--
-- AGNÓSTICA DE JURISDICCIÓN (regla dura de CLAUDE.md): ningún vocabulario de país.
--
-- Aplicada por `postgres` (mia_app no tiene ALTER). Ver `execution/init_personas.py`.

ALTER TABLE personas
  ADD COLUMN IF NOT EXISTS capabilities text[] NOT NULL DEFAULT '{}';

-- El vocabulario se valida en el dominio (`agents/personas.py`) y además aquí, para que
-- ningún camino futuro cuele un valor que la voz del turno no sabría traducir. Se
-- reemplaza completo (DROP + ADD) porque un CHECK no se amplía in situ; al ampliarlo, la
-- lista nueva se construye desde la VIGENTE, nunca desde esta (aprendizaje 86).
ALTER TABLE personas DROP CONSTRAINT IF EXISTS ck_personas_capabilities;
ALTER TABLE personas
  ADD CONSTRAINT ck_personas_capabilities
  CHECK (capabilities <@ ARRAY['lectura_visual', 'investigacion_viva', 'documentos_largos']::text[]);

COMMENT ON COLUMN personas.capabilities IS
  'Capacidades que el abogado le concedió a este agente (D8). Marcarlas es su decisión; '
  'que estén disponibles en la instalación es otra cosa, y la pantalla lo distingue.';
