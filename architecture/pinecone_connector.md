# Mia · SOP — Pinecone connector (store vectorial externo opcional)
# Última actualización: 2026-06-14 (Módulo 3d)

## Cuándo usar Pinecone vs. pgvector
El store vectorial **primario es PostgreSQL + pgvector** (decisión #2): RLS nativo por tenant,
una sola pieza de infra, sin servicio externo. Pinecone es un store **EXTERNO y OPCIONAL** para
despachos que ya lo usan o que necesitan escalar la búsqueda vectorial fuera de Postgres. No es
obligatorio: un despacho sin Pinecone funciona 100% con pgvector.

El módulo es **CONDICIONAL**: `get_pinecone_connector()` devuelve un `PineconeConnector` real
solo si `PINECONE_API_KEY` está en el entorno; si no, devuelve un `NoopPineconeConnector` (misma
interfaz, no hace nada, loggea un aviso). Así el resto del código llama al conector sin
ramificar: si Pinecone no está, las operaciones son no-ops seguras.

## Interfaz (`PineconeConnectorBase`, ABC)
- `async upsert(tenant_id, vectors)` — `vectors=[{id, values, metadata}]`. Batch de 100.
- `async query(tenant_id, vector, top_k=10, metadata_filter=None)` — vecinos más cercanos.
- `async delete(tenant_id, ids)` — borra por id.
- `async describe_index()` — estadísticas del índice.

Las llamadas al SDK (síncrono) se envuelven en `asyncio.to_thread` para no bloquear el event
loop. El SDK `pinecone` (v3+) se importa de forma **perezosa** dentro de `_get_index()`: el
conector se construye sin tener el paquete instalado ni tocar la red; la conexión real ocurre en
la primera operación.

## Aislamiento por namespace (Pinecone NO tiene RLS)
Pinecone no tiene Row-Level Security. El aislamiento entre despachos se hace por **namespace**:
`{namespace_prefix}_{tenant_id}` (default prefix `tenant`, p. ej. `tenant_<uuid>`). Cada
operación (upsert/query/delete) va acotada a su namespace. La **metadata del vector se preserva
intacta** (no se le inyectan campos); el namespace —no un campo de metadata— es el mecanismo de
aislamiento idiomático de Pinecone. `query` admite además un `metadata_filter` opcional para
filtros de negocio, pero el aislamiento NO depende de él.

> ⚠️ Aclaración de spec: el spec original pedía "filter por namespace en metadata". Se implementó
> con el **parámetro `namespace`** de Pinecone (la forma correcta de aislar), no con un filtro de
> metadata, para no contaminar la metadata del usuario. Ver Riesgo #17.

## Configuración en `.env`
- `PINECONE_API_KEY` — si está, el conector se activa; si no, modo noop. (Único disparador.)
- `PINECONE_INDEX_NAME` — default `mia-legal`.
- `PINECONE_NAMESPACE_PREFIX` — default `tenant`.

Los dos últimos van comentados en `.env` (se usan los defaults salvo que se descomenten). El
producto se entrega sin `PINECONE_API_KEY` → noop por defecto.

## Patrón noop
`NoopPineconeConnector.is_configured == False`. `upsert`/`delete` devuelven stats vacías con
`{"skipped": True}`, `query` devuelve `[]`, todo loggeando "Pinecone no configurado". Nunca
lanza: el código que lo usa no necesita try/except ni ramas `if pinecone`.

## Cómo activar para un tenant
1. `pip install "pinecone>=3"` en el `.venv` (SDK oficial v3+; NO instalado por defecto).
2. Crear el índice en Pinecone con dimensión **1024** (voyage-law-2, decisión #8) y métrica
   coseno.
3. Poner `PINECONE_API_KEY` (y opcionalmente `PINECONE_INDEX_NAME`) en `.env`.
4. El namespace del tenant se deriva solo (`{prefix}_{tenant_id}`); no hay que crearlo a mano.
5. (Pendiente, Riesgo #18) cablear ingest/retrieval para escribir/leer por el conector — hoy el
   conector existe pero ningún path lo usa todavía.

## Self-Annealing — si el gate falla, revisar en este orden
1. **Factory devuelve el tipo equivocado:** `get_pinecone_connector()` lee `PINECONE_API_KEY`
   EN CADA LLAMADA (no cachea). El gate manipula `os.environ`; si falla, revisar que no haya un
   import que cachee la key.
2. **El gate intenta conectar a Pinecone:** no debe. Los tests inyectan `connector._index =
   FakeIndex()`; si se construye sin inyectar y se llama una operación, `_get_index()` importaría
   `pinecone` y conectaría. Mantener la inyección.
3. **Batch incorrecto:** `UPSERT_BATCH = 100`; 250 vectores → [100, 100, 50].
4. **Namespace sin tenant:** `_namespace(tenant_id)` = `f"{prefix}_{tenant_id}"`.
5. **Import error de `pinecone`:** solo debe ocurrir en uso real (perezoso). Si rompe al importar
   el módulo o al construir, algún import dejó de ser perezoso.
