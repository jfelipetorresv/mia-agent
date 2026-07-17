-- Mia · 039_obsidian_frontmatter_links.sql · ingesta consciente de la estructura del vault
--
-- PROBLEMA QUE CIERRA: hasta 038, `connectors/obsidian_sync.py` leía el vault de un despacho
-- como si fuera un PDF. El frontmatter YAML entraba como texto literal DENTRO del chunk
-- (basura para el embedding, imposible de filtrar) y los `[[wikilinks]]` no se parseaban
-- jamás: un índice/MOC —el documento más denso en señal de todo el vault, el que dice qué
-- es importante y cómo se relaciona— terminaba como un chunk de enlaces rotos.
--
-- QUÉ AÑADE (aditivo puro: 4 columnas nullables/con DEFAULT sobre knowledge_chunks; NADA se
-- renombra, NADA se borra, ninguna fila existente cambia de significado):
--
--   doc_status   — estado del DOCUMENTO, normalizado a un vocabulario CERRADO de 2 valores:
--                  'verificado' | 'borrador' | NULL. NULL = el vault no lo declara o lo
--                  declara con una palabra que no sabemos mapear. NULL NO significa
--                  "borrador": significa "no sé", y quien recupere debe decidir qué hace
--                  con lo que no sabe. Esto es lo que permite que el criterio verificado del
--                  despacho pese más que su borrador.
--   doc_type     — tipo declarado por el documento (libre, minúsculas: 'nota', 'contrato',
--                  'moc'…). Sin vocabulario cerrado: cada vault nombra sus tipos.
--   frontmatter  — el frontmatter COMPLETO ya parseado y saneado a JSON. Se guarda entero
--                  (no solo los campos que entendemos) porque los campos que hoy son
--                  desconocidos son los que mañana alguien va a querer consultar. El texto
--                  YAML deja de contaminar `content`.
--   links        — los `[[wikilinks]]` de ESTE chunk, con el motivo del vínculo cuando el
--                  vault lo declara: [{"to": ..., "to_key": ..., "rel": ...}].
--
-- POR QUÉ `links` ES POR-CHUNK Y NO POR-DOCUMENTO: no se construye un grafo. El enlace se
-- guarda donde APARECE, que es también donde se recupera: el chunk de un MOC que enumera 40
-- notas ES el chunk que responde "¿qué hay sobre X?". Guardarlo por-chunk sale más barato
-- que denormalizar la lista entera del documento en cada una de sus filas, y es más preciso
-- (se sabe qué SECCIÓN enlaza a qué). Los backlinks se derivan con una consulta, sin tabla
-- nueva, sin RLS nueva, sin superficie nueva que auditar. (Los enlaces declarados en el
-- frontmatter no aparecen en ningún cuerpo: se adjuntan al PRIMER chunk del documento.)
--
-- POR QUÉ NO REUSA `metadata` (jsonb, 004): esa columna es genérica y compartida con los
-- otros sources de knowledge_chunks ('local:<id>'…). Meter ahí YAML escrito a mano por el
-- abogado mezclaría datos de dueños distintos en la misma bolsa. Columna explícita.
--
-- DEGRADACIÓN (el vault que se conecta es el que el despacho YA tiene): sin frontmatter →
-- doc_status/doc_type NULL, frontmatter '{}'; sin wikilinks → links '[]'. Los DEFAULT hacen
-- que la ingesta de hoy sea exactamente la de ayer para un vault de texto plano. Cero
-- backfill: las filas ya indexadas quedan con los DEFAULT y se rellenan solas en el próximo
-- sync (el hash del archivo no cambió, pero tampoco hay nada que reparar: sin frontmatter
-- parseado el comportamiento es el previo).
--
-- AGNÓSTICO: frontmatter y wikilinks son de Obsidian, no de una jurisdicción. Ninguna
-- columna, valor ni índice de esta migración conoce un país.
--
-- RLS: NO se toca. knowledge_chunks ya tiene ENABLE + FORCE + política por app_current_tenant()
-- desde 004; las columnas nuevas viven bajo esa misma política sin cambiarla ni debilitarla.
-- Migración aplicada por `postgres` (mia_app NO tiene CREATE). Idempotente: re-ejecutable.

ALTER TABLE knowledge_chunks ADD COLUMN IF NOT EXISTS doc_status  text;
ALTER TABLE knowledge_chunks ADD COLUMN IF NOT EXISTS doc_type    text;
ALTER TABLE knowledge_chunks ADD COLUMN IF NOT EXISTS frontmatter jsonb NOT NULL DEFAULT '{}'::jsonb;
ALTER TABLE knowledge_chunks ADD COLUMN IF NOT EXISTS links       jsonb NOT NULL DEFAULT '[]'::jsonb;

-- Vocabulario CERRADO en la base, no solo en Python: si algún día otro conector escribe aquí,
-- no puede inventarse un tercer estado a espaldas de quien filtra. NULL sigue permitido.
-- (NOT VALID: no re-valida las filas históricas — todas tienen doc_status NULL, que la
-- restricción acepta; evita un escaneo completo de la tabla al migrar.)
DO $$
BEGIN
  IF NOT EXISTS (
    SELECT 1 FROM pg_constraint
    WHERE conname = 'ck_knowledge_chunks_doc_status'
      AND conrelid = 'knowledge_chunks'::regclass
  ) THEN
    ALTER TABLE knowledge_chunks
      ADD CONSTRAINT ck_knowledge_chunks_doc_status
      CHECK (doc_status IS NULL OR doc_status IN ('verificado', 'borrador')) NOT VALID;
  END IF;
END $$;

-- Índice del filtro real ("dame solo lo verificado" / "no me cites un borrador"). Parcial:
-- la mayoría de los vaults del mundo no declaran estado, y esas filas no merecen ocupar índice.
CREATE INDEX IF NOT EXISTS idx_knowledge_chunks_status
  ON knowledge_chunks(tenant_id, doc_status) WHERE doc_status IS NOT NULL;

-- Backlinks y "qué enlaza a esta nota" sin tabla de grafo:
--   WHERE links @> '[{"to_key": "nota-uno"}]'
-- jsonb_path_ops: índice más pequeño y rápido para @>, que es la ÚNICA consulta que esta
-- columna necesita servir.
CREATE INDEX IF NOT EXISTS idx_knowledge_chunks_links
  ON knowledge_chunks USING gin (links jsonb_path_ops);

-- Los campos de frontmatter que NO normalizamos siguen siendo consultables
--   WHERE frontmatter @> '{"area": "contratación"}'
-- sin que nadie tenga que adivinar el esquema de un vault ajeno.
CREATE INDEX IF NOT EXISTS idx_knowledge_chunks_frontmatter
  ON knowledge_chunks USING gin (frontmatter jsonb_path_ops);

-- Sin GRANT nuevo: mia_app ya tiene SELECT/INSERT/UPDATE/DELETE sobre knowledge_chunks (004)
-- y los privilegios de tabla cubren las columnas nuevas.
