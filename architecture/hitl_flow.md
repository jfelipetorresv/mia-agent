# architecture/hitl_flow.md
# Flujo HITL — LangGraph StateGraph + checkpointing + SSE (Módulo 1d)
# Última actualización: 2026-06-30

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

---

## 6 · Lecciones del smoke test vivo (2026-06-30)

El primer smoke **end-to-end en vivo** (no mockeado) destapó 2 bugs del flujo HITL que los
gates offline no veían, porque el gate ejercía el camino feliz con decisiones siempre válidas y
un único turno por asunto. Ambos quedaron reparados; documentados aquí como invariantes a NO
romper.

### 6.1 · La decisión HITL es **fail-closed**, no fail-open

**Bug:** `confirm_node` (lo que corre tras `Command(resume=...)`) derivaba el estado así:

```python
# ANTES (fail-OPEN — peligroso):
dec = (decision or {}).get("decision", "approved")
status = dec if dec in ("approved", "rejected", "editing") else "approved"
```

Una decisión **ausente o inválida** (resume sin payload, valor corrupto, bug aguas arriba) caía
por defecto en `"approved"` → un borrador jurídico podía **aprobarse solo**, sin que el abogado
diera el visto bueno. En un agente legal eso es inaceptable: la aprobación es el acto humano que
sostiene toda la responsabilidad.

```python
# AHORA (fail-CLOSED):
dec = (decision or {}).get("decision")
if dec not in ("approved", "rejected", "editing"):
    dec = "rejected"   # sin decisión válida no se aprueba NADA
status = dec
```

**Invariante:** en cualquier punto donde se resuelva la decisión del abogado, la ausencia de una
decisión explícita y válida debe degradar a **`rejected`** (o pedir de nuevo), nunca a `approved`.
La aprobación SIEMPRE es un acto positivo explícito. Verificado en vivo: las trazas
`mia.trace.v2` registran `hitl_outcome` `approved` **y** `rejected`.

### 6.2 · Guardas de **ciclo de vida del turno** (el checkpoint tiene estado entre requests)

Como `interrupt()` parte el turno en dos HTTP (§3) y el estado persiste en el checkpoint entre
ambos, el mismo `thread_id` puede estar en 3 situaciones: **(a)** sin turno / turno terminado en
`END`, **(b)** pausado en `hitl_checkpoint` (borrador esperando revisión), **(c)** en mitad de
intake→draft. Antes NO se validaba en qué situación estaba, lo que permitía dos carreras:

- **Iniciar un turno nuevo (`stream`) con un borrador pendiente** → se pisaba el `interrupt` y se
  perdía el borrador sin revisar.
- **Reanudar (`approve/reject/edit`) sin un borrador pendiente** → `Command(resume=...)` corría
  sobre un grafo que no estaba pausado, con efectos indefinidos.

**Fix — dos guardas en `api/routes/_common.py`, llamadas ANTES de abrir el SSE** (el 409 debe ser
HTTP, no un evento dentro del stream ya abierto):

- `prepare_new_turn(...)` — antes de un turno nuevo: si `state.next` (hay interrupt pendiente) →
  **409** "Tienes un borrador pendiente…". Si el turno anterior terminó en `END` (`state.values`
  sin `next`) → **borra el thread** del checkpointer para que LangGraph rearranque
  intake→analysis→draft limpio con el mismo `thread_id`.
- `require_awaiting_review(...)` — antes de un resume: si el grafo **no** está pausado en
  `hitl_checkpoint` (`not state.next`) → **409** "No hay borrador pendiente de revisión".

**Robustez del stream (mismo fix):** dos higienes que evitan fallas silenciosas:
- `WikiManager().update_from_approved_matter(...)` pasó de **fire-and-forget**
  (`asyncio.create_task(...)`, que tragaba excepciones y la task era GC-able) a **awaited** dentro
  de un `try/except` con `logger.exception`.
- El generador SSE de `stream`/`hitl` envuelve el cuerpo en `try/except` y emite un evento
  **`error`** ("Mia no pudo completar el turno…") en vez de **colgar** la conexión ante una
  excepción no atrapada.

**Invariante:** todo endpoint que arranque o reanude un grafo DEBE validar el estado del
checkpoint (`graph.aget_state(cfg)`) **antes** de abrir el SSE, y mapear los estados imposibles a
**409**, no a comportamiento indefinido. Complementa el Riesgo #7 (aislamiento por `thread_id`).

> La causa-raíz del 3.er bug del smoke (la conexión a la BD se rompía al arrancar uvicorn en
> Windows) NO es del flujo HITL sino del event loop de asyncio en Windows — documentada aparte en
> `architecture/windows_notes.md`.
