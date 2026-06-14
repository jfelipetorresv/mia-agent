# Mia · SOP — SAT-Graph (corpus jurídico compartido)
# Cómo Mia consulta normas, relaciones y jurisprudencia de Colombia.
# Última actualización: 2026-06-14 (Módulo 3a)

## Qué es y por qué existe
El **SAT-Graph** es el grafo de conocimiento jurídico de Mia en Postgres puro
(decisión #4 — no Neo4j): un corpus de **normas** (`legal_norms`), **relaciones
tipadas entre normas** (`norm_relations`, el "grafo") y **jurisprudencia**
(`jurisprudence`). Responde preguntas que un retriever vectorial solo no responde:
*¿qué norma estaba vigente en tal fecha?*, *¿qué modificó/derogó a qué?*,
*¿qué sentencias tratan este tema?*. Es la base de la **citación verificable**:
el agente apoya sus afirmaciones en normas con vigencia y procedencia explícitas.

Vive en `backend/mia/rag/`: `sat_graph.py` (clase `SATGraph`) +
`ingest_corpus.py` (corpus semilla). Migración: `db/migrations/003_sat_graph.sql`,
aplicada por `execution/init_sat_graph.py`.

## Esquema de tablas (descripción)
- **`legal_norms`** — una norma (ley, decreto, sentencia-como-norma, resolución,
  circular, acuerdo). Campos clave: `norm_type` (CHECK), `norm_number`,
  `issuing_body`, `title`/`summary`/`full_text`, **`effective_date`** (NOT NULL) y
  **`expiry_date`** (NULL = vigente) para la vigencia temporal, `jurisdiction`
  (default `colombia`), `practice_areas text[]`, `metadata jsonb`, y `fts_vector`
  (lo llena un trigger). Upsert por `UNIQUE (norm_number, issuing_body)`.
- **`norm_relations`** — arista dirigida `source -> target` con `relation_type`
  (CHECK: `remite_a`, `modifica_a`, `deroga_a`, `excepciona_a`, `define_termino`,
  `complementa_a`, `interpreta_a`). FK a `legal_norms` **ON DELETE CASCADE**.
  Upsert por `UNIQUE (source_norm_id, target_norm_id, relation_type)`.
- **`jurisprudence`** — providencia de alta corte: `court`, `sala`,
  `decision_number`, `radicado`, `magistrado_ponente`, `decision_date`, `topic`,
  `ratio_decidendi`, `obiter_dicta`, `keywords text[]`, `fts_vector`. FK opcional
  `norm_id -> legal_norms` **ON DELETE SET NULL**. Upsert por
  `UNIQUE (decision_number, court)`.

## Corpus compartido vs. datos por-tenant (decisión #16)
Las tres tablas son **corpus público COMPARTIDO** entre todos los despachos: las
normas y sentencias de Colombia son las mismas para todos. **NO llevan `tenant_id`.**
Es la **excepción documentada** al patrón RLS por-tenant (ver
`architecture/rls_isolation.md`): RLS habilitado pero con política **abierta**
`USING (true) WITH CHECK (true)`; lectura para cualquier conexión `mia_app`,
escritura (curaduría) restringida a `mia_app` por GRANT (único rol no-superusuario).
Por eso `SATGraph` usa `pool.connection()` (SIN fijar `app.tenant_id`), no
`tenant_connection`. Esto **no** debilita el aislamiento: las tablas por-tenant
siguen fail-closed sin GUC (0 filas), así que una conexión sin-GUC solo ve el corpus.
**Regla:** nunca usar `pool.connection()` para datos por-tenant.

## Consulta temporal — `get_norm_at_date(norm_id, fecha)`
Devuelve la norma **si y solo si** estaba vigente en `fecha`:
`effective_date <= fecha AND (expiry_date IS NULL OR expiry_date > fecha)`.
Intervalo semiabierto `[effective_date, expiry_date)`: el día de derogatoria ya no
cuenta como vigente. `expiry_date IS NULL` = vigente indefinidamente. Devuelve
`None` si la norma no existe o no estaba vigente esa fecha. Índices
`idx_legal_norms_effective` / `_expiry` apoyan el filtro.

## Cadena de modificaciones — `get_norm_chain(norm_id)` (CTE recursivo)
Sigue las aristas salientes de tipo `modifica_a`/`deroga_a` desde `norm_id` con un
**WITH RECURSIVE**: raíz en `depth 0`, descendientes en `depth+1`, ordenado por
`depth`. **Guardia de ciclos:** cada fila acarrea un arreglo `visited` con los ids
del camino; el paso recursivo excluye `WHERE NOT (n.id = ANY(c.visited))`, de modo
que un ciclo `A->B->A` termina (no vuelve a entrar a `A`) en vez de hacer loop
infinito. Una hoja (sin aristas salientes de esos tipos) devuelve solo la raíz.

## Búsqueda — FTS español (`fts_vector` por trigger)
Cada tabla tiene una `fts_vector tsvector` que un **trigger BEFORE INSERT OR UPDATE**
recalcula automáticamente con `setweight(to_tsvector('spanish', …), peso)`:
- `legal_norms`: A=`title`, B=`summary`, C=`full_text`.
- `jurisprudence`: A=`decision_number`, B=`topic`, C=`ratio_decidendi`,
  D=`keywords` (array unido). Índices GIN sobre `fts_vector`.

La config `spanish` hace *stemming* y **plegado de acentos** (`protección`≈`proteccion`).
`search_norms` / `search_jurisprudence` consultan con
`websearch_to_tsquery('spanish', q)` (tolera texto libre de varias palabras; un
`to_tsquery` crudo reventaría) y ordenan por `ts_rank` (desempate por fecha desc).
Nunca pasar el texto del usuario a `to_tsquery` directo.

## Cómo ampliar el corpus
La curaduría se hace con los `add_*` de `SATGraph` (upsert idempotente: re-ingestar
no duplica). El corpus base vive en `ingest_corpus.py` (`_NORMS`, `_JURIS`,
`_RELATIONS`); se carga con:

    python -m mia.rag.ingest_corpus      # desde backend/ (o PYTHONPATH=backend)

**Verificación de citas (regla global):** los datos del corpus semilla son
**SEMILLA de desarrollo**, no citas entregadas a un cliente. Todo dato aproximado o
provisional va marcado con **`[VERIFICAR]`** en `metadata` (y en `summary`/`ratio`)
para auditarlo contra la fuente primaria (SUIN-Juriscol / la corte respectiva) antes
de cualquier uso real. No marcar como verificado lo que no se contrastó.

## Self-Annealing — si el gate falla, revisar en este orden
1. **¿Corrió la migración?** `init_sat_graph.py` debe reportar las 3 tablas con
   `mia_app INSERT=True RLS=True`. Si faltan tablas → re-correr (es idempotente).
2. **¿GRANT a `mia_app`?** Si `SELECT/INSERT` falla para `mia_app`, la migración no
   aplicó el `GRANT` o la política abierta — revisar el bloque RLS de `003`.
3. **FTS vacío** (`search_*` no encuentra nada): confirmar que la config `spanish`
   existe (`SELECT cfgname FROM pg_ts_config WHERE cfgname='spanish'`). Si no está,
   usar `'simple'` en triggers + queries y documentarlo en `findings.md` (la config
   `'simple'` no pliega acentos → el test de acento cambiaría).
4. **`get_norm_chain` no termina / cuelga:** revisar la guardia `visited` del CTE;
   sin ella, un ciclo en `norm_relations` hace loop infinito.
5. **Upsert duplica:** verificar las constraints `UNIQUE` y que el `ON CONFLICT`
   apunte exactamente a esa clave.
6. **`get_norm_at_date` devuelve algo inesperado:** recordar el intervalo
   semiabierto `[effective_date, expiry_date)` (el día de `expiry_date` NO es vigente).
7. **Crash al imprimir en consola PS:** la consola es cp1252; el gate fuerza
   `sys.stdout.reconfigure('utf-8')` y evita símbolos fuera de cp1252 en los nombres.
