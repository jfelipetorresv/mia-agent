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

> **Nota de desfase (2026-07-08):** la sección "Los 5 nodos" arriba describe el grafo previo a
> CP9. El grafo real hoy (`agents/graph.py`) tiene 8 nodos: `intake → facts → research → analysis
> → draft → verification → hitl_checkpoint → finalize` (equipo de especialistas, ver
> `docs/analisis-referencias-2026-07.md`/HANDOFF CP9). `graph.py` es la fuente de verdad; esta
> sección no se reescribió todavía — pendiente de un refresco aparte de este documento.

---

## 7 · Menú de próximos pasos (presentación) — quick win de `claude-for-legal` (2026-07-08)

Ingeniería inversa del plugin marketplace legal de Anthropic (`docs/analisis-claude-for-legal.md`
§2.9, §5.4) señaló un patrón de presentación que MIA no tenía: todo análisis debe cerrar con un
**menú de opciones para que el abogado elija**, nunca con una recomendación implícita única — *"a
draft of the OPTIONS, not a draft of the DECISION... the tree IS the output"*.

**Qué se adoptó (prompt, sin tocar lógica ni el HITL):** la instrucción del especialista de
**análisis** (`agent/prompt_builder.py → GRAPH_NODE_INSTRUCTIONS["analysis"]`) ahora pide, ANTES
del bloque de cierre estructurado (`=== CIERRE DEL DIAGNÓSTICO ===` … `=== FIN DEL CIERRE ===`, que
sigue intacto y se sigue parseando igual con `parse_diagnosis_closing`):

1. **2 a 5 caminos concretos** que el abogado pueda elegir (redactar X / pedir más hechos / esperar
   y observar / escalar o consultar / otro camino) — Mia nunca elige por él.
2. **Una pregunta de segundo orden** — la observación que un revisor pensante notaría y que el
   checklist/análisis de arriba no capturó.

**Ojo (hallazgo de revisor capa 2, corregido antes del commit):** el menú va ANTES del bloque de
cierre, no después — el bloque (que termina en "Riesgo y recomendación") debe seguir siendo lo
ÚLTIMO que emite el especialista. `context_recovery.shrink_text(..., protect_tail=True)` (usado por
`draft_node._shrink()` en `graph.py` cuando el diagnóstico no cabe en el presupuesto) protege el
FINAL del texto recortando el MEDIO — si el menú quedara al final, un recorte por presupuesto
protegería el menú de próximos pasos y arriesgaría cortar el riesgo/recomendación real, justo el
dato jurídico que `protect_tail` existe para proteger. Con el menú ANTES del bloque, `strip_diagnosis_closing`
lo sigue conservando como prosa visible al abogado (queda en la parte "antes del bloque", que la
función preserva igual); es puramente aditivo a la presentación, cero cambio de lógica jurídica.

El especialista de **borrador** (`GRAPH_NODE_INSTRUCTIONS["draft"]`) recibió por separado la regla
del "3er valor" (`claude-for-legal` §2.1, quick win #1): si sospecha que una norma citada pudo
haber sido derogada/modulada pero no puede confirmarlo en el turno, debe DECIRLO dentro del propio
escrito en vez de omitirlo o usarla sin duda — sin bloquear el borrador por esto.

**Deliberadamente NO se tocó el cuerpo del `draft`** con un menú de próximos pasos: a diferencia del
diagnóstico (que no es un documento a radicar), el borrador SÍ se exporta a `.docx` como escrito
judicial — anexarle un menú de opciones ahí contaminaría el documento final. El patrón de "menú"
vive solo en el análisis/diagnóstico que ve el abogado en pantalla.

**Pendiente (quick win #5, `docs/analisis-claude-for-legal.md` §5):** un checklist de
pre-entrega EJECUTADO (no solo texto) en el propio gate de aprobación del borrador — toca el flujo
de HITL que Pipe ya clasificó como "resultado legal", así que requiere su aprobación previa antes
de tocar `hitl_checkpoint`/la UI de aprobación. No implementado en esta sesión.

---

## 8 · La SEGUNDA pausa del turno: "Mia decide y me pregunta" (CP-HUB2, 2026-07-16)

Decisión de Pipe: *"parte del encanto de MIA es que puede determinar si necesita agentes o
subagentes"*. Mia ya puede decidir por su cuenta que necesita un **ayudante externo** (Agent Hub) —
pero antes de que salga un byte del computador, el abogado ve **qué ayudante** y **el texto exacto**,
y aprueba de un clic. Con memoria: *"no me preguntes más por este ayudante en este asunto"*.

```
START → intake → delegation → facts → research → analysis → draft → verification
                    │                                                     ↓
                    └─ interrupt() CONDICIONAL                      hitl_checkpoint
                       (solo si hay propuesta que aprobar)                ↓
                                                                     finalize → END
```

### 8.1 · Por qué el turno tiene DOS interrupts y no uno

La pausa del ayudante va **justo después de intake** por una razón de coste del abandono: su salida
va a `metadata` y **nunca** al razonamiento jurídico (D3 sin cerrar), así que no alimenta a ningún
especialista y puede ir en cualquier parte del grafo. Se elige el sitio donde una pausa sin
respuesta cuesta menos: si el abogado no contesta, lo único que queda esperando es el intake.
Colgada tras el análisis, congelaría el turno entero.

### 8.2 · Por qué está partida en dos nodos (lo que NO se puede romper)

Al reanudar un `interrupt()`, **LangGraph re-ejecuta el nodo desde su primera línea**. Si el mismo
nodo decidiera la propuesta (llamando al modelo) y luego preguntara, al aprobar volvería a llamar al
modelo y podría redactar **otro** texto: saldría del equipo algo que el abogado nunca vio, y la
pantalla de aprobación sería teatro. Por eso:

- `intake_node` → `_plan_delegation()` **planifica** (candado, modelo, memoria) y deja el plan en
  `state['delegation_request']`, que **se persiste en el checkpoint**.
- `delegation_node` → `interrupt()` y **lee el texto del estado**; su re-ejecución no decide nada.

Es el mismo patrón que el gate del borrador (`draft_node` calcula → `hitl_checkpoint_node` pregunta).
**Invariante:** un nodo que interrumpe NO puede calcular lo que muestra.

### 8.3 · Que las dos pausas no se confundan ES parte del candado

Con dos interrupts, comprobar solo "¿hay alguna pausa?" deja un agujero real: un `POST /approve`
(aprobar el **borrador**) reanudaría la pausa del **ayudante** y el texto saldría sin que nadie viera
la propuesta. Dos barreras independientes, ambas verificadas en el gate:

1. **Por nodo** (`api/routes/_common.py`): `require_awaiting_review` exige `hitl_checkpoint in
   st.next`; `require_awaiting_delegation` exige `delegation in st.next`. Se usa `st.next` (nombres
   de nodo) y `st.values`, nunca la forma interna del `Interrupt` de LangGraph — contrato estable
   entre versiones. `prepare_new_turn` distingue además **qué** 409 devolver.
2. **Por payload**: la decisión del borrador es `{"decision": "approved"}`; la del ayudante,
   `{"delegacion": "aprobada", "huella": …}`. **No comparten ni una clave**, así que un payload no
   puede leerse como el otro. Todo lo demás cae a "no" (fail-closed, §6.1).

La **huella** (sha256 de ayudante+texto) ata la aprobación a un texto concreto: si la pantalla manda
otra, se rechaza (aprobó una pestaña vieja).

### 8.4 · Lo que el candado NO delega en el abogado

Que haya un humano aprobando **no** es excusa para darle al modelo un gatillo cargado: un control que
depende de leer con atención cada vez se degrada (a la décima propuesta se aprueba sin leer). Los
límites que sostienen la función son estructurales (ver `agents/delegate_proposal.py`):

- El **proponente no ve el expediente**: solo el mensaje limpio del abogado (`retrieval_query`) y el
  catálogo. No puede filtrar lo que nunca leyó.
- El texto propuesto se **sanea a una línea** ≤400 chars (`untrusted.sanitize_field`): no puede
  fingir interfaz ("=== APROBADO ===") y, sobre todo, **es legible** — lo que lo hace revisable.
- El ayudante sale de un **catálogo cerrado** ya filtrado por `hub_gate.allowed_agents`.
- En **'soberano'** el catálogo es `[]`: no se propone, ni se gasta una llamada al modelo. El
  candado se evalúa **antes de proponer** y **otra vez antes de invocar** (la política pudo
  endurecerse mientras la pausa estaba abierta).

### 8.5 · Si el abogado nunca responde

No pasa nada, y ese es el diseño: el grafo queda suspendido, no sale un byte, y el próximo turno del
asunto recibe un **409** que le recuerda la pregunta abierta. Descartar es la salida.

### 8.6 · La memoria y los modos

`matter_agent_consent` (migración 037, RLS) guarda "no me preguntes más" por **(asunto, ayudante)**,
nunca global. **No es un permiso**: solo suprime la pregunta — el candado se evalúa igual, y por eso
el orden de llamada es siempre candado → memoria. Revocar (`DELETE .../delegation/memoria/{slug}`)
devuelve al defecto seguro: preguntar.

`tenant_settings.config->>'delegation_mode'`: `preguntar` (**defecto**, la decisión de Pipe) ·
`autonomo` · `solo_si_lo_pido` (el comportamiento previo a CP-HUB2). La invocación explícita
(nombrar al ayudante en el mensaje) funciona igual en los tres y nunca pregunta: el abogado ya lo
ordenó.

### 8.7 · Cómo verificar

```
.venv\Scripts\python.exe execution\init_matter_agent_consent.py   # migración (1 vez)
.venv\Scripts\python.exe execution\test_delegation_decide.py      # 103/103 (grafo + DB + HTTP)
.venv\Scripts\python.exe execution\test_delegation_wiring.py      # 45/45 (invocación explícita)
```
