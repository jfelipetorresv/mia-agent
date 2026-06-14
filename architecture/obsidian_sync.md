# Mia · SOP — Obsidian indexer (knowledge_chunks)
# Cómo Mia indexa el vault de Obsidian del despacho.
# Última actualización: 2026-06-14 (Módulo 3c)

## Qué hace el sync
`ObsidianSync.sync(vault_path, tenant_id)` mantiene la tabla `knowledge_chunks` en espejo con
el vault de Obsidian de un despacho: escanea los `.md`, detecta nuevos/cambiados/borrados,
trocea respetando los encabezados, embebe (voyage-law-2) y persiste. Devuelve
`{indexed, skipped, deleted, errors}`. Es **incremental**: en cada corrida solo reindexa lo
que cambió. Vive en `backend/mia/connectors/obsidian_sync.py`.

## Por qué `knowledge_chunks` y no `documents` (decisión #17)
Las notas de Obsidian son **conocimiento del DESPACHO**, no de un asunto. La tabla `documents`
del Módulo 0 tiene `matter_id NOT NULL` (todo documento pertenece a un expediente) y el
retriever (`agents/retrieval.py`) acota por `documents.matter_id`. Meter notas del despacho ahí
obligaría a romper esa invariante. Por eso el conocimiento del despacho va en una tabla NUEVA,
`knowledge_chunks` (misma forma que `chunks` —content + `content_tsv` + `embedding vector(1024)`—
pero con `source`/`source_path`/`chunk_index` en vez de `document_id`/`matter_id`). Es la tabla
base para todo conocimiento del despacho que no es un expediente (Obsidian hoy; plantillas,
jurisprudencia local, notas a futuro). RLS por-tenant estándar (igual que `chunks`). No toca el
esquema del Módulo 0.

## Detección de cambios — hash sha256
- `_hash_file(path)` = sha256 del contenido del archivo (hex).
- `obsidian_file_hashes(tenant_id, vault_path, file_hash, last_indexed)` guarda el último hash
  por archivo (RLS por tenant, `UNIQUE(tenant_id, vault_path)`).
- En cada `sync`: si el hash del archivo == el guardado → **skipped**; si difiere o es nuevo →
  se reindexa (**indexed**). Tras procesar, `_save_hashes` deja la tabla de hashes en espejo:
  upsert de los actuales + borra los hashes de archivos que ya no están.
- **Borrados:** `_delete_removed` compara los `source_path` en `knowledge_chunks` contra los
  archivos presentes; los que faltan se eliminan (cuenta **deleted** = nº de archivos).
- Un archivo que falla al indexarse NO guarda su hash → se reintenta la próxima corrida
  (cuenta **errors**, no tumba a los demás).

## Estrategia de chunking — por encabezados markdown
`_chunk_document(content, filepath)` produce `{text, heading_path, position, source_file}`:
- **Cada H1/H2/H3 inicia un chunk nuevo** (`_split_by_headings`). `heading_path` es la miga de
  pan acumulada, p. ej. `"Contratos > Cláusulas > Indemnización"`. El preámbulo antes del primer
  encabezado va con `heading_path` vacío.
- **Tamaño máximo 512 tokens** (estimado ~4 chars/token, `memory/tokens.py`). Si el bloque bajo
  un encabezado excede 512, se divide **por párrafos** (empacando hasta el límite). Un párrafo
  aislado mayor que el límite se parte por caracteres. **Overlap 0** (los encabezados dan el
  contexto). `chunk_index` = posición del chunk dentro del archivo.
- **Upsert** (`_upsert_chunks`): `ON CONFLICT(tenant_id, source, source_path, chunk_index)
  DO UPDATE`; si el archivo encogió, se borran los chunks con índice sobrante.

## Embeddings — librería, no proxy (decisión #17 C2 / Riesgo #4)
`_embed_chunks` usa `embeddings.embed_texts` (LiteLLM **librería** → `voyage-law-2`, 1024 dims),
en batches de 128. NO usa `call_llm(task="embedding")`: ese task no existe; `call_llm` es solo
chat por el proxy. Consistente con el ingest del Módulo 0 y con `findings.md`.

## Configuración del vault por tenant
El vault es **config por despacho**, no se hardcodea (regla de producto en `bugs-and-risks.md`):
`tenant_settings.config->>'obsidian_vault_path'`. El producto se entrega con esa clave vacía;
cada despacho la llena en el onboarding. En desarrollo, `.env` trae
`OBSIDIAN_VAULT_PATH=D:\Codex\Lexia-Vault-Test` como default del tenant de desarrollo.

El job `sync_obsidian_all_tenants` (cron, cada 6h — `cron/scheduler.py`) enumera los tenants con
vault configurado y corre `sync` para cada uno. La enumeración cross-tenant usa una conexión
admin (operación de sistema, **Riesgo #15**); la escritura por tenant pasa por
`pool.tenant_connection` (RLS). El scheduler es un registro propio en memoria (sin APScheduler):
`register_job` / `list_jobs` / `run_job` / `start`.

## Cómo probar manualmente
1. Aplicar la migración: `python "…\execution\init_knowledge_stores.py"`.
2. Poner el vault del tenant de dev en `tenant_settings` (o usar `OBSIDIAN_VAULT_PATH` de `.env`).
3. Sync directo desde un REPL con el pool abierto:
   `await ObsidianSync().sync(r"D:\Codex\Lexia-Vault-Test", "<tenant_uuid>")`.
4. Gate: `python "…\execution\test_obsidian_sync.py"` (usa un vault temporal en `.tmp/`,
   NO el real; embeddings mockeados).

## Self-Annealing — si el gate falla, revisar en este orden
1. **¿Corrió la migración 004?** `init_knowledge_stores.py` debe reportar las 2 tablas con
   `mia_app INSERT=True RLS=True`. Re-correr (idempotente) si faltan.
2. **RLS:** si A ve datos de B (o B los de A), revisar que la policy use
   `tenant_id = app_current_tenant()` y que la app conecte como `mia_app` (nunca postgres).
3. **`indexed`/`skipped` raros:** el incremental depende del hash; si todo se reindexa siempre,
   verificar que `_save_hashes` persiste (RLS: debe correr bajo `tenant_connection`).
4. **Chunks duplicados:** confirmar el `UNIQUE(tenant_id, source, source_path, chunk_index)` y el
   `ON CONFLICT`. Recordar que un re-sync sin cambios se SALTA por hash (no reescribe).
5. **`deleted` no cuenta:** `_delete_removed` cuenta ARCHIVOS (source_path), no chunks.
6. **Chunk > 512 no se divide:** revisar `estimate_tokens` (~4 chars/token) y `_split_to_size`.
7. **Embeddings:** en el gate están mockeados; en vivo necesitan `VOYAGE_API_KEY` y van por
   `embeddings.embed_texts` (librería), no por el proxy chat.
8. **Crash al imprimir (consola cp1252):** el gate fuerza `sys.stdout.reconfigure('utf-8')`.
