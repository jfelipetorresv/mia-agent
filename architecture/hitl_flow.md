# architecture/hitl_flow.md
# Flujo HITL — LangGraph StateGraph + checkpointing + SSE (Módulo 1d)
# Última actualización: 2026-06-13

> Estado: 1d entregado. Gate `execution/test_hitl_flow.py` **19/19** (integración
> contra la DB real + checkpointer Postgres, LLM/embeddings mockeados). Decisiones
> locked: #9 (checkpoint+RLS), #10 (posición de interrupt), #11 (SSE+resume).

---

## 1 · El grafo del asunto

```
START → intake → analysis → draft → hitl_checkpoint → finalize → END
                                          │
                                          └─ interrupt()  ← PRIMERA línea del nodo
                                             (el grafo se pausa al ENTRAR; decisión #10)
```

`backend/mia/agents/`:
- `state.py` — `MatterState` (TypedDict). `messages` con reducer `operator.add`
  (append); el resto last-write-wins. Snapshots **frozen** al inicio del asunto:
  `soul_snapshot` (Módulo 5; hoy None) y `profile_snapshot` (2a). `thread_id_for()`
  = `"{tenant_id}:{matter_id}"`.
- `graph.py` — `MatterGraphBuilder` (DI de `TraceCapture`) con los 5 nodos.
- `retrieval.py` — RAG híbrido RRF (vector pgvector + full-text tsvector).
- `checkpointer.py` — `open_checkpointer()` → AsyncPostgresSaver (rol `mia_app`).

### Los 5 nodos
1. **intake** — embebe la consulta (voyage-law-2) y recupera los chunks del asunto
   por **RRF** (`embedding <=> qv` ⊕ `content_tsv @@ websearch_to_tsquery`), bajo
   `tenant_connection` (RLS activo, acotado por `matter_id`). → `state.documents`.
2. **analysis** — diagnóstico jurídico estructurado con los documentos (call_llm).
3. **draft** — borrador usando el `profile_snapshot` frozen (2a) y los playbooks
   aplicables (2b). → `state.draft`, `hitl_status="pending"`.
4. **hitl_checkpoint** — `interrupt()` es la **primera línea**: el grafo se pausa al
   entrar, emite `awaiting_review` con el borrador. Al reanudar, `interrupt()`
   devuelve la decisión del abogado → setea `hitl_status` y la guarda.
5. **finalize** — incorpora el feedback (si `editing`), finaliza el borrador y
   **escribe la traza JSONL** (2d). → `state.draft` final, `state.trace_id`.

Los nodos son async; los clientes LLM/embeddings son síncronos → se llaman vía
`asyncio.to_thread` para no bloquear el event loop.

---

## 2 · Checkpointing + RLS (decisión #9)

`AsyncPostgresSaver` persiste el estado del grafo en la **misma** Postgres del
Módulo 0. Reconciliación con el RLS multi-tenant:

- Las tablas de checkpoint (`checkpoints`, `checkpoint_blobs`, `checkpoint_writes`,
  `checkpoint_migrations`) las crea **`postgres`** en una migración
  (`execution/init_checkpointer.py`), porque `mia_app` no tiene `CREATE`. A `mia_app`
  se le hace **GRANT DML**. En runtime el saver corre como `mia_app` y NO toca DDL.
- Esas tablas **no llevan RLS** (LangGraph no lo soporta nativo). El aislamiento del
  estado es por **`thread_id = "{tenant_id}:{matter_id}"`** + la **validación del
  tenant del JWT** en los endpoints HITL (doble barrera).
- El **RLS de dominio sigue activo**: los nodos que tocan la DB (intake/RRF) lo hacen
  vía `tenant_connection`, que fija el GUC `app.tenant_id` (fail-closed). El gate
  verifica que A ve su asunto y B no, y que el cruzado da 401.

> Subclasear `AsyncPostgresSaver` para meterle RLS se descartó por fragilidad ante
> updates de LangGraph (decisión #9).

---

## 3 · Streaming SSE + resume (decisión #11)

`interrupt()` parte el turno en **dos llamadas HTTP**:

- **GET `/matters/{id}/stream?message=...`** (`api/routes/stream.py`) — corre
  intake→analysis→draft y emite, terminando suspendido en el interrupt:
  `thinking` → `thinking` → `draft_ready` → `awaiting_review`.
- **POST `/matters/{id}/approve|reject|edit`** (`api/routes/hitl.py`) — reanuda con
  `Command(resume={...})` y emite `finalizing` → `done` en la MISMA respuesta SSE.

Cada endpoint verifica `assert_owns_matter` (RLS) **antes** de reanudar → tenant
cruzado = **401**. El mensaje del abogado entra como query param `message` (GET no
lleva body).

### Vocabulario de eventos (lo que VE el abogado, §G)
| event             | lo que ve el abogado                                 | cuándo            |
|-------------------|------------------------------------------------------|-------------------|
| `thinking`        | "Mia está revisando el expediente…" / "…analizando…" | intake / analysis |
| `draft_ready`     | "Borrador listo."                                    | fin de draft      |
| `awaiting_review` | "Borrador listo para tu aprobación." + draft         | interrupt         |
| `finalizing`      | "Mia está finalizando el borrador…"                  | resume → finalize |
| `done`            | "Listo." + draft final + status                      | END               |

§G: el `data` de cada evento va en español, sin jerga (`HITL`, `LangGraph`,
`interrupt`, `pgvector`, `tenant`, `checkpoint`). El gate lo verifica.

---

## 4 · Cómo verificar

```
.venv\Scripts\python.exe execution\init_checkpointer.py   # migración (1 vez, como postgres)
.venv\Scripts\python.exe execution\test_hitl_flow.py      # 19/19 (DB real + checkpointer)
```

Gate mínimo (subconjunto de los 19): interrupt detiene el grafo antes de finalizar ✓
· `Command(resume=...)` reanuda ✓ · tenant cruzado → 401 ✓ · traza JSONL al finalizar ✓.

---

## 5 · Costuras hacia adelante
- **soul_snapshot** se llena en el Módulo 5 (SOUL.md); hoy es None.
- **playbooks** (2b): `draft_node` ya recibe el perfil frozen; enganchar la
  activación de playbooks por asunto es el siguiente cableado.
- **Pooling del checkpointer**: hoy `from_conn_string` abre conexión por operación
  (correcto, el estado vive en Postgres). Si la concurrencia lo exige, pasar a un
  `AsyncConnectionPool` dedicado (autocommit + dict_row).
- **1e (Agent Hub)**: conectores a CLIs externos como nodos/herramientas del grafo.
