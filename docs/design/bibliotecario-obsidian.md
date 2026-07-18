---
titulo: "El Bibliotecario de Obsidian — documento de diseño"
estado: propuesta
fecha: 2026-07-18
autor: Mia (con Pipe)
---

# El Bibliotecario de Obsidian

## 1. La idea en una frase

Hoy Mia es un **inquilino ordenado** del Obsidian del despacho: lee todo el vault y solo
escribe en su propia carpeta (`Mia/`). Este diseño la convierte en **bibliotecaria**: sigue
sin tocar nada sin permiso, pero ahora **organiza** el vault a partir de lo que el abogado
le va dando — construye mapas de conexión sobre los documentos, y —cuando se le autoriza—
ordena carpetas y notas de verdad.

Todo esto es **local-first y confidencial**: corre sobre la base de datos del despacho, no
sale información cruda a servicios externos, y cada cambio queda registrado y es reversible.

## 2. Los dos planos (la clave del diseño)

Separar estos dos planos es la decisión de diseño más importante: tienen riesgo distinto,
y por eso tienen reglas de autonomía distintas.

### Plano 1 — Conocimiento (automático, sin pedir permiso)

Mia construye y mantiene **sola** un mapa de conexiones *encima* de los documentos:
entidades jurídicas (partes, normas, personas, fechas, casos), las relaciones entre ellas,
tags, backlinks, notas-índice y un `MAPA-VAULT.md` general.

Regla de oro: **nunca mueve ni altera un documento del abogado**. Es puramente aditivo
(agrega metadatos y notas nuevas) y reversible (se puede borrar el mapa entero sin perder
ni una palabra de lo que escribió el abogado). Por eso no necesita aprobación: el riesgo de
un mapa mal hecho es "hay que corregirlo", no "se perdió o se movió algo".

Aquí es donde se saca el mayor provecho de las ideas de **megarag** (repo de referencia,
no algo que Mia ya tenga integrado): un grafo de entidades y relaciones, una taxonomía
jurídica **cerrada** (no cualquier
etiqueta que a un LLM se le ocurra), deduplicación por nombre normalizado con fusión y
trazabilidad de origen (de qué documento salió cada dato), y vistas múltiples — recuperar
por caso, por cliente, por tipo de documento o por parte, sin mover un solo archivo.

### Plano 2 — Archivos (autonomía graduada)

Mover, crear o reestructurar carpetas y notas de verdad — tocar el vault del abogado.

Mismo patrón que los modos de delegación que Pipe ya aprobó para los ayudantes externos de
Mia (`backend/mia/gateway/hub_config.py`): **preguntar / autónomo / solo si lo pido**,
configurable por despacho.

**Modo por defecto: autónomo** (decisión de Pipe, 2026-07-18: "que ordene sola, para
facilitarle la vida al usuario"). Mia organiza el vault sin pedir permiso paso a paso —
**pero solo porque ese automático viene con tres salvaguardas que lo hacen rendir cuentas,
no actuar a ciegas** (condición expresa de Pipe: "que sea rigurosa y deje un log, por si
acaso"):

1. **Registro de auditoría completo.** Cada acción (mover, crear, renombrar, enlazar) queda
   registrada: qué se hizo, cuándo, por qué, y de dónde salió el archivo. El abogado puede
   ver en cualquier momento "esto es lo que Mia ordenó" y un resumen periódico se lo acerca.
2. **Deshacer garantizado.** Toda acción —o una tanda entera— se puede revertir al estado
   anterior exacto. "Revertir" significa volver de inmediato al último estado estable.
3. **Lo irreversible nunca es automático.** Borrar no existe (se archiva). Una fusión que
   podría perder información, o cualquier cosa difícil de deshacer, **siempre** se propone y
   espera aprobación, aunque el modo sea autónomo. El automático solo cubre lo reversible.

Flujo cuando algo sí requiere aprobación (por ser irreversible, o si el despacho baja el
modo a *preguntar*): **"propone → tú apruebas"**. Mia presenta una tabla
`documento → destino → por qué (+ fuente)` y no ejecuta nada hasta que el abogado aprueba —
igual que ya funciona la aprobación de borradores.

## 3. Barreras duras (van en el código, no en una instrucción)

Estas reglas no son una sugerencia de comportamiento: se implementan como validaciones que
rechazan la operación si se incumplen, con el mismo criterio "fail-closed" que ya usa
`vault_writer.py` para su propia carpeta.

1. **Archivar, nunca borrar.** Ninguna operación del bibliotecario borra un archivo del
   abogado; lo máximo que hace es moverlo a `archivo/`.
2. **Aislamiento estricto por cliente/caso.** El bibliotecario jamás cruza, compara ni
   fusiona información entre clientes distintos, incluso dentro del mismo despacho.
3. **Síntesis local o anonimizada.** El contenido de un documento de cliente nunca sale
   crudo hacia un modelo externo; si hace falta resumir o extraer entidades con IA, pasa
   primero por anonimización o se resuelve con el modelo local.
4. **El estado interno de Mia vive FUERA del vault sincronizado.** El vault es del
   despacho; la base de datos de Mia (grafo, propuestas pendientes, historial) vive en
   Postgres, no dentro de la carpeta que Obsidian sincroniza. (Esta regla existe porque en
   el proyecto de referencia `second-brain`, sincronizar el estado del agente dentro del
   vault lo corrompió durante meses — no se repite ese error.)
5. **Ninguna nota sin fuente.** Toda nota que Mia crea es derivada y enlaza al documento
   original; nunca lo reemplaza ni pretende ser la versión definitiva.
6. **Interruptor por nota:** `ia_contexto: excluido | resumen | completo`. El abogado
   decide, nota por nota, qué tan a fondo puede leerla Mia.

## 4. Estructura del vault

Por defecto: **cliente → caso**. Pero el vault del despacho manda: si el abogado ya
organiza distinto, o si el OneDrive/Drive del despacho ya tiene una organización que
funciona, Mia **mapea lo que existe y propone mejoras encima**, sin imponer un molde nuevo.

Frontmatter jurídico (taxonomía cerrada, mismo criterio que ya aplica
`obsidian_sync.py` con `doc_status`/`doc_type` — ver §7):

| Campo | Qué guarda |
|---|---|
| `tipo_nota` | de qué tipo de documento se trata (lista base ampliable, §6) |
| `caso` / `expediente` | a qué asunto pertenece |
| `cliente` / `cliente_id` | a qué cliente pertenece (anonimizado si aplica) |
| `fecha` | fecha del documento o de la nota |
| `tags` | etiquetas libres del abogado |
| `estado_procesal` | en qué etapa está el asunto |
| `ia_contexto` | `excluido \| resumen \| completo` — la barrera dura #6 |
| `origen` | de qué documento/fuente salió esta nota |
| `generado_por` | quién la escribió (abogado o Mia) |
| `estado` | `propuesta \| aprobada` — si es una nota que Mia propuso y aún no se confirma |

Carpetas de referencia:

- **"Sin clasificar"** — no es una carpeta, es una vista inteligente (§6.2): muestra todo lo
  nuevo que aún no tiene sitio, esté donde esté; el archivo se mueve una sola vez a su destino.
- `expedientes/[caso]/` — hechos, pruebas, escritos, correspondencia, jurisprudencia; con
  una nota-índice `CASO.md` viva que se actualiza sola.
- `clientes/[cliente]/`
- `corpus/` — enlaza al corpus jurídico compartido (LLOS).
- `plantillas/`
- `archivo/` — asuntos cerrados (nunca se borra, se archiva).
- `MAPA-VAULT.md` — la vista general que mantiene el Plano 1.

## 5. Cuatro modos operativos

| Modo | Qué hace | Toca archivos |
|---|---|---|
| **Reconocer** | Resume una carpeta o el vault entero sin tocar nada. | No |
| **Proponer** | Arma un plan de organización (tabla destino + por qué) para que el abogado lo apruebe. | No, hasta aprobar |
| **Ejecutar** | Aplica el plan — tras aprobación, o en automático si el modo/riesgo lo permite. Deja registro y opción de deshacer. | Sí |
| **Mantener** | Actualiza el mapa e índices; propone fusiones de notas duplicadas (nunca las fusiona solo). | No, hasta aprobar |

## 6. Decisiones tomadas (Pipe, 2026-07-18)

1. **Tipos de nota — lista fija que cualquier abogado puede ampliar.** Mia parte de una
   lista base cerrada (hecho, prueba, escrito, correspondencia, jurisprudencia, concepto,
   contrato…) para dar consistencia, pero cualquier abogado del despacho puede proponer
   tipos nuevos que se suman a la lista. No es un catálogo congelado ni un caos de etiquetas
   libres: crece con el uso, con orden.
2. **La bandeja de entrada es una vista inteligente, no una carpeta física.** "Lo sin
   clasificar" es una búsqueda que muestra todo lo que aún no tiene sitio, esté donde esté;
   el archivo se mueve **una sola vez**, directo a su destino. Esto permite que el modo
   automático empiece a ordenar desde el primer día sin duplicar movimientos.
3. **Modo automático amplio por defecto — con rigor, log y deshacer** (ver §2). Mia ordena
   sola desde el principio para facilitarle la vida al abogado; la contrapartida obligatoria
   son las tres salvaguardas del Plano 2 (auditoría completa, deshacer garantizado, y lo
   irreversible nunca automático). Sin esas tres, el automático amplio no se activa.
4. **El cliente va con su nombre real en el vault.** El vault vive dentro del perímetro
   confidencial del despacho, así que un alias solo añadiría fricción. La anonimización se
   aplica a lo que sale hacia una IA externa (barrera dura #3), no al contenido interno del
   vault. (Si algún despacho pidiera anonimizar el vault mismo, se trataría como excepción
   configurable, no como el comportamiento por defecto.)

## 7. Plan de construcción por fases

### Fase 1 — Mapa + reglas de enrutamiento + conocimiento automático + documento→nota

**Qué entrega:** `MAPA-VAULT.md` generado y mantenido; reglas de enrutamiento (a qué
carpeta pertenecería cada documento según su frontmatter/ruta actual, sin moverlo);
el grafo de entidades y relaciones (Plano 1) construido sobre lo que ya se indexa del
vault; tags/backlinks/notas-índice automáticos; pipeline que convierte un documento
ingerido en una nota estructurada que enlaza al original.

**Qué reusa:**
- El parser de frontmatter + wikilinks de `backend/mia/connectors/obsidian_sync.py`
  (frontmatter YAML con alias es/en, `[[wikilinks]]` con motivo declarado, chunking por
  encabezados) — no se reescribe, el grafo de entidades se construye **encima** de lo que
  este módulo ya extrae por chunk.
- El pipeline de ingesta de documentos (`backend/mia/ingest/ingest.py` y `mia/ingest/`)
  como base del flujo "documento → nota estructurada".
- El patrón de aislamiento (`pool.tenant_connection`, RLS fail-closed) para las tablas
  nuevas del grafo de entidades.
- El estilo de grafo en Postgres puro de `backend/mia/rag/sat_graph.py` (aristas
  tipadas, resolución temporal, sin Neo4j) — como **inspiración de patrón**, no como
  tabla compartida: el grafo de entidades del bibliotecario es privado por
  cliente/caso, mientras que SAT-Graph es corpus público compartido entre despachos; no
  pueden vivir en las mismas tablas.
- `backend/mia/security/anonymize.py` para cualquier paso donde una entidad se extraiga
  con ayuda de un modelo (cumple la barrera dura de síntesis local/anonimizada).

**Riesgo:** bajo — no mueve nada del abogado; el error más caro posible es un mapa
desactualizado o una entidad mal fusionada, y ambos se corrigen sin pérdida de datos.

**Cómo se verifica:** gates automáticos de que ninguna escritura sale de la carpeta
permitida (mismo test que ya cubre `vault_writer.py`); revisión independiente de que el
grafo no cruza clientes; verificación visual de una muestra del `MAPA-VAULT.md` contra el
vault real; confirmación de que cada nota generada trae su `origen`.

### Fase 2 — Proponer/Ejecutar del Plano de archivos, con aprobación

**Qué entrega:** modo Proponer (tabla documento→destino→por qué) y modo Ejecutar tras
aprobación, para el caso más simple y de mayor valor inmediato: ordenar el `inbox/` y
reubicar archivos sueltos.

**Qué reusa:**
- `backend/mia/connectors/vault_writer.py` como base de la capa de escritura: sus
  validaciones anti-escape, anti-symlink/junction y el saneo de nombres de archivo son
  exactamente las que necesita cualquier escritura fuera de `Mia/`. Se extiende (no se
  reemplaza) porque hoy esa clase solo tiene permiso de escribir dentro de `Mia/`; darle
  permiso —bajo aprobación— de tocar carpetas del abogado es un cambio de alcance que debe
  quedar explícito y revisado, no una ampliación silenciosa.
- El flujo "propone → aprueba" que ya existe para los borradores jurídicos (mismo patrón
  de interacción, otro dominio).

**Riesgo:** medio — ya se tocan archivos del abogado, pero siempre tras aprobación
explícita; el registro de cada movimiento permite deshacer.

**Cómo se verifica:** ningún movimiento ocurre sin una aprobación registrada; prueba de
que "deshacer" devuelve el vault al estado previo bit a bit; confidencialidad (§G):
ninguna ruta de destino se decide comparando contenido de dos clientes distintos.

### Fase 3 — Autonomía graduada + fusión propuesta + vistas múltiples

**Qué entrega:** el interruptor de modo (preguntar/autónomo/solo si lo pido) configurable
por despacho aplicado al Plano de archivos; el modo Mantener proponiendo fusiones de
notas/entidades duplicadas; las vistas múltiples (por caso/cliente/tipo/parte) como
consultas sobre el grafo, no como reestructuración física.

**Qué reusa:**
- El mecanismo de modos de `backend/mia/gateway/hub_config.py`
  (`MODE_ASK="preguntar"`, `MODE_AUTO="autonomo"`, `MODE_ONLY_EXPLICIT="solo_si_lo_pido"`)
  como plantilla directa de configuración — mismo vocabulario que el abogado ya conoce de
  los ayudantes externos.
- El patrón de confianza con evidencia en contra de
  `backend/mia/memory/wiki_manager.py` (`confidence_score`, aprobado/editado/rechazado)
  para decidir cuándo una fusión propuesta merece presentarse como "alta confianza" o
  necesita más evidencia antes de proponerse.

**Riesgo:** medio-alto en el modo automático (por eso es graduado y configurable, y el
umbral de qué entra en automático por defecto es la decisión abierta #3).

**Cómo se verifica:** auditoría de que el modo automático nunca ejecuta lo marcado como
alto impacto; prueba de que una fusión rechazada por el abogado no se vuelve a proponer
igual (mismo criterio de "MIA sabe no mentir" ya aplicado en otros módulos); verificación
de que las vistas múltiples son solo lectura (no generan movimiento de archivos).

---

## Anclaje técnico

*(Sección para quien construya — no necesaria para decidir el producto.)*

Piezas existentes que este diseño reusa, con su rol exacto:

- **`backend/mia/connectors/obsidian_sync.py`** — indexador incremental del vault (hash
  sha256 por archivo) hacia `knowledge_chunks`. Ya separa frontmatter YAML (con alias
  es/en vía `_FIELD_ALIASES`) del cuerpo, ya trocea respetando H1/H2/H3, y ya extrae
  `[[wikilinks]]` con el motivo del vínculo cuando el vault lo declara (`_links_from_text`,
  campos inline de Dataview `clave:: [[destino]]`). El grafo de entidades del Plano 1 se
  construye leyendo esta salida (frontmatter + links por chunk), no reimplementando el
  parser. Grado de degradación ya resuelto ahí (sin PyYAML, YAML roto, sin frontmatter →
  fail-soft) se hereda gratis.
- **`backend/mia/connectors/vault_writer.py`** — hoy la ÚNICA superficie de escritura de
  Mia en el vault, confinada a `{vault}/Mia/`. Trae ya construidas las tres barreras que el
  Plano 2 necesita para escribir fuera de esa carpeta: validación de allowlist
  (`_validated_vault`), anti-junction/symlink (`_mia_root`, reproducido con `mklink /J`),
  slugify seguro con manejo de nombres reservados de Windows (`_slugify`), y
  deduplicación de slugs colisionados (`_dedupe_slug`). Extender el Plano 2 sobre esta
  clase (no crear un escritor paralelo) es la vía de menor riesgo: cambiar `_target()` para
  aceptar destinos fuera de `Mia/` bajo un candado de aprobación explícito, en vez de tocar
  las validaciones de base.
- **`backend/mia/memory/wiki_manager.py`** — el "second brain" interno de Mia
  (`Mia/conceptos/`, `Mia/reportes/`), con `confidence_score(support, contra)`: fórmula de
  confianza con prior de Laplace que SUBE con aprobaciones y BAJA con rechazos/ediciones
  (a diferencia del trinquete viejo que solo subía). Referencia directa para puntuar
  fusiones de entidades propuestas en Fase 3.
- **`backend/mia/rag/sat_graph.py`** — el `SATGraph` existente es corpus jurídico
  **compartido entre tenants** (`legal_norms` + `norm_relations`, RLS `USING(true)`,
  resolución temporal `get_norm_at_date`, cadenas `modifica_a`/`deroga_a` vía CTE
  recursivo). Importante: el grafo de entidades del bibliotecario es el caso **opuesto**
  en aislamiento — privado, por tenant y por cliente/caso — así que necesita tablas nuevas
  (migración nueva bajo `backend/mia/db/migrations/`, siguiendo la numeración existente:
  `003_sat_graph.sql`, `004_knowledge_stores.sql`...) con RLS estricto por tenant, no las
  tablas de SAT-Graph. Lo que sí se reusa es el **patrón**: Postgres puro, aristas
  tipadas con `relation_type`, FTS en español con `websearch_to_tsquery`.
- **`backend/mia/connectors/pinecone_connector.py`** y **`backend/mia/agents/retrieval.py`**
  — store vectorial externo opcional, fail-soft, aislado por namespace
  (`{prefix}_{tenant_id}`), ya cableado como espejo de `knowledge_chunks`
  (`_pinecone_mirror_upsert` en `obsidian_sync.py`). No es necesario para el grafo de
  entidades (Postgres alcanza), pero si en el futuro se necesitara reforzar recuperación
  semántica sobre el grafo, el patrón de espejo fail-soft ya está resuelto ahí.
- **`backend/mia/ingest/ingest.py`** — pipeline genérico de ingesta de documento → chunks
  embebidos → `documents`/`chunks` por tenant/matter. Base del flujo "documento → nota
  estructurada" de la Fase 1; evita crear un tercer camino de ingesta además del de
  `obsidian_sync.py`.
- **`backend/mia/security/anonymize.py`** — pipeline de anonimización ya construido (NER +
  patrones estructurados por país/pack + marcadores estables + reidentificación
  reversible). Es la pieza concreta que cumple la barrera dura "síntesis local o
  anonimizada" cuando el bibliotecario necesite apoyo de un modelo para extraer entidades
  o resumir un documento de cliente.
- **Gap identificado (no existe hoy):** no hay tabla de entidades/relaciones por-tenant
  para documentos del despacho — solo existe frontmatter/links en jsonb por chunk
  (`knowledge_chunks.frontmatter`, `knowledge_chunks.links`) y el corpus compartido de
  SAT-Graph. El grafo de entidades del Plano 1 es la pieza genuinamente nueva de este
  diseño; todo lo demás (parseo, escritura confinada, confianza HITL, aislamiento
  RLS) ya existe y se reusa.
- **Vocabulario de modos** (`backend/mia/gateway/hub_config.py`): `MODE_ASK = "preguntar"`,
  `MODE_AUTO = "autonomo"`, `MODE_ONLY_EXPLICIT = "solo_si_lo_pido"`,
  `VALID_DELEGATION_MODES`, `DEFAULT_DELEGATION_MODE = MODE_ASK`. El Plano 2 debe usar
  este mismo enum (o uno nuevo con las mismas tres cadenas) para que el abogado configure
  un solo concepto de "modo" en toda la aplicación, no uno para ayudantes externos y otro
  distinto para el bibliotecario.
