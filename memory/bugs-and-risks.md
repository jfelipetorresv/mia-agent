# Mia — bugs-and-risks.md
# Riesgos abiertos y watch-outs aún no resueltos
# Última actualización: 2026-06-14

Leyenda: 🔴 abierto · 🟡 mitigado/en observación · 🟢 cerrado

## [CERRADO] Riesgo #28 - Issue #1 cerrado: chat responde con mia-local  [CERRADO 2026-06-20]
**Cierre:** smoke test vivo completado en el asunto "Nueva prueba". Se levanto PostgreSQL 16 portable
con `pgvector 0.8.2` en `127.0.0.1:55432`, se aplicaron `init_db.py` + migraciones 003-008, y
`execution/test_rls.py` paso 12/12. `ollama run qwen2.5:32b "hola"` respondio correctamente tras
reiniciar Ollama sin GPU (`OLLAMA_NO_GPU=1`, `CUDA_VISIBLE_DEVICES=-1`). `mia-local` quedo apuntando a
`ollama/qwen2.5:32b`; el stream del asunto devolvio `draft_ready` y `awaiting_review`. El log de LiteLLM
registro `mia-local`, `qwen2.5:32b`, `POST /chat/completions` y `200 OK`. Regresion completa: 17/17
suites verdes.

**Nota operativa:** el puerto `8000` quedo tomado por un listener huerfano de Windows durante la sesion,
por eso el smoke vivo se verifico en `8001` usando el mismo runner de API y el mismo backend. `start_api.ps1`
queda corregido para usar `mia.api.run`, que fija `WindowsSelectorEventLoopPolicy` antes de uvicorn.

**Historico del bloqueo:** La Tarea 1 (cerrar Issue #1: chat sin respuesta) no se pudo confirmar end-to-end porque las rutas
`/api/matters` quedan esperando una conexiÃ³n a `DATABASE_URL=postgresql://mia_app:***@127.0.0.1:5432/mia`.
`Test-NetConnection 127.0.0.1:5432` falla, no hay servicio `postgres*`/`pgsql*` visible, `where pg_ctl`
no encuentra binario, y la API termina con `psycopg_pool.PoolTimeout: couldn't get a connection after
30.00 sec`.

**ActualizaciÃ³n 2026-06-20:** se instalÃ³ PostgreSQL 16.14 con winget y se logrÃ³ levantarlo manualmente
con `pg_ctl` en `127.0.0.1:5432`, pero `CREATE EXTENSION vector` sigue bloqueado porque `pgvector`
no estÃ¡ disponible en la instalaciÃ³n nueva. El binario Windows `vector.v0.8.2-pg16.zip` fue descargado,
pero copiar `vector.dll` a `C:\Program Files\PostgreSQL\16\lib` falla con `Access denied`; esta sesiÃ³n
no tiene elevaciÃ³n para escribir en `Program Files`. Sin `pgvector`, `init_db.py`, `test_rls.py` y las
suites con DB real no son una prueba vÃ¡lida del estado del producto.

**Estado parcial:** `start_api.ps1` sÃ­ levanta uvicorn, Next escucha en 3000 y LiteLLM escucha en 4000.
LiteLLM requiriÃ³ reparar el `.venv` local y un workaround para no inicializar Prisma cuando se usa
sin base propia. `mia-local` quedÃ³ apuntando a `qwen3-coder:30b` porque `ollama run qwen2.5:32b "hola"`
no terminÃ³ en ~13 minutos y el modelo no apareciÃ³ en `ollama list`; `qwen3-coder:30b` sÃ­ respondiÃ³.

**AcciÃ³n requerida para cerrar Issue #1:** instalar `pgvector` en la instancia local de PostgreSQL 16
(requiere elevaciÃ³n o reinstalaciÃ³n en ruta escribible), correr `execution/init_db.py` y migraciones,
luego repetir el smoke test del asunto "Nueva prueba" y confirmar en el log de LiteLLM una llamada a
`mia-local` antes de marcar el issue como cerrado.

**Impacto en regresiÃ³n:** la regresiÃ³n completa 17/17 no puede finalizar mientras PostgreSQL/pgvector
no estÃ© completamente operativo. Las 8 suites offline verificadas el 2026-06-20 pasaron; las suites que
usan DB real quedan bloqueadas por la falta de extensiÃ³n `vector`.

---

## 🟡 Riesgo #1 — Ruta del proyecto contiene un espacio
El proyecto vive en "D:\Codex\Mia-Super Agent\mia" ("Mia-Super Agent"
tiene un espacio). Riesgo de errores en:
- scripts de spawn de CLIs (Módulo 1e),
- configs de LiteLLM,
- comandos `subprocess`.

**Mitigación:** toda ruta entre comillas; validar en cada módulo.

## 🟢 Riesgo #2 — Versión de PostgreSQL + disponibilidad de pgvector  [CERRADO 2026-06-12]
Había que verificar PG 16 y la disponibilidad de pgvector antes del Módulo 0.

**Resuelto:** PostgreSQL **16.13** (instalación EDB en
`C:\Program Files\PostgreSQL\16`, NO winget) verificado; **pgvector 0.8.2**
instalado y load-tested (`CREATE EXTENSION vector` + operación vectorial OK).
La auth del superusuario `postgres` se reparó (Opción 3, pg_hba trust).
El caveat de que el binario de pgvector es de terceros sigue vivo en el
**Riesgo #3**.

## 🔴 Riesgo #3 — pgvector en Windows nativo (Modo B clientes)
El pgvector instalado en esta máquina usa un binario precompilado de
terceros (andreiramani, GitHub). Válido para desarrollo. NO apto para
producción ni máquinas de clientes en Modo B.

**Acción requerida antes de Fase 5:** resolver pgvector en Windows por
ruta oficial para garantizar que Mia se pueda entregar a clientes sin
dependencias de terceros no oficiales. Opciones a evaluar:
- Stack Builder de PostgreSQL — ⛔ verificado 2026-06-12: NO incluye
  pgvector para PG16 Windows (el catálogo `applications-v2.xml` solo
  trae PostGIS, pgAgent, pgBouncer, psqlODBC, Slony-I; los docs de EDB
  solo documentan pgvector en Linux). Esta vía queda descartada.
- Compilación MSVC desde fuente oficial (pgvector/pgvector).
- Redefinir entrega a clientes como Modo A (Docker + imagen oficial
  `pgvector/pgvector:pg16`).

**Procedencia del binario de desarrollo:** vector v0.8.2 para PG16
(tag `0.8.2_16.1`), verificado por SHA256 contra el digest del asset
en la API de GitHub antes de instalar. DLL probablemente sin firma
Authenticode (build comunitario).

## 🟡 Riesgo #4 — LiteLLM usado de dos formas (librería vs. proxy)  [detectado 2026-06-12, Sesión 3]
`embeddings.py` (Módulo 0) llama a LiteLLM como **librería** (`litellm.embedding`,
con `VOYAGE_API_KEY` directa). El agente (Módulo 1) llama al **proxy** OpenAI-compatible
(wire OpenAI a `localhost:4000`, alias `claude-haiku`/`claude-sonnet`). Ambos caminos
son válidos, pero conviven dos rutas para "todo el tráfico LLM por LiteLLM" (decisión #3).

**Riesgo:** caching/observabilidad/costos quedan divididos; un cambio en el proxy no
afecta a los embeddings y viceversa. No bloquea nada hoy.
**Acción:** decidir un criterio único al construir el retriever (Fase 2 / 3a) —
probablemente todo por el proxy. Documentado también en `architecture/prompt_builder.md` §6.

## 🟡 Riesgo #5 — Presupuestos de tokens con estimador heurístico  [detectado 2026-06-12, Sesión 4]
`memory/tokens.py::estimate_tokens` usa ~4 caracteres/token (heurística offline,
determinista). NO es el tokenizer real de Anthropic. Los presupuestos que dependen de
él —PERFIL_ABOGADO ≤600, PERFIL_DESPACHO ≤900, índice de playbooks ≤3.000— son
APROXIMADOS: un perfil podría pasar el guardarraíl y exceder el presupuesto real, o
al revés. ALCANCE AMPLIADO (2c, Sesión 7): el umbral de compresión del
ContextCompressor (55% de la ventana) y el cálculo de ahorro también usan este
estimador — la compresión podría dispararse antes o después de lo real.

**Por qué se hizo así:** tiktoken está instalado (0.13.0) pero baja su vocab BPE por
red en el primer uso → rompería los gates offline; además no es el tokenizer de
Anthropic. El conteo exacto lo da el gateway aguas arriba.
**Acción:** si los presupuestos se vuelven críticos, sustituir por un conteo real
(p. ej. el contador de tokens de Anthropic vía el gateway) detrás de la misma firma
`estimate_tokens`. No bloquea hoy.

## 🟡 Riesgo #6 — Colisión de nombre `memory/` (paquete vs. build)  [detectado 2026-06-12, Sesión 4]
Hay DOS cosas llamadas "memory":
- `/memory/` en la raíz del repo = memoria de CONSTRUCCIÓN para Claude Code
  (progress.md, task_plan.md, este archivo).
- `backend/mia/memory/` = paquete Python de la memoria EN EJECUCIÓN del agente
  (2a ProfileManager · 2b PlaybookManager · 2d TraceCapture · `tokens.py`).
Rutas distintas, pero el nombre puede confundir en conversación o en imports.

**Mitigación:** el docstring de `backend/mia/memory/__init__.py` lo aclara
explícitamente. Si genera fricción, renombrar el paquete (p. ej. `runtime_memory/`)
es trivial y de bajo riesgo. No bloquea hoy.

## 🟡 Riesgo #7 — Aislamiento del checkpoint depende de thread_id + JWT (no RLS)  [detectado 2026-06-13, Sesión 5] 🔐
Decisión #9: las tablas de checkpoint de LangGraph NO tienen RLS. El aislamiento del
estado del grafo entre despachos se sostiene en DOS invariantes de código:
1. `thread_id = "{tenant_id}:{matter_id}"` se construye SIEMPRE con el tenant del JWT
   (nunca con un valor del cliente), y
2. los endpoints HITL llaman `assert_owns_matter` (RLS) ANTES de reanudar.

**Riesgo:** si un módulo futuro que toque el grafo (1e, UI, un cron) construye el
thread_id con un tenant no verificado u omite `assert_owns_matter`, el aislamiento se
rompe (un despacho podría leer/reanudar el asunto de otro). El RLS de dominio NO
cubre esto porque las tablas de checkpoint no lo tienen.
**Mitigación:** invariante documentada en `architecture/hitl_flow.md` §2 y verificada
en el gate (cruzado→401, A ve/B no). **Regla:** todo punto que reanude/lea un grafo
DEBE derivar el thread_id del JWT y verificar propiedad. No bloquea hoy.

## 🟡 Riesgo #8 — Checkpointer abre conexión por operación (sin pool)  [detectado 2026-06-13, Sesión 5]
`agents/checkpointer.py::open_checkpointer` usa `AsyncPostgresSaver.from_conn_string`,
que abre una conexión por operación de grafo (stream y resume son requests distintos).
Es CORRECTO (el estado vive en Postgres), pero bajo concurrencia alta puede ser
ineficiente.

**Acción:** si la concurrencia lo exige, pasar a un `AsyncConnectionPool` dedicado
para el checkpointer (autocommit + dict_row), abierto en el lifespan. No bloquea hoy.

## 🟡 Riesgo #9 — Agent Hub: flags de CLI sin verificar + invocación en vivo  [detectado 2026-06-13, Sesión 6]
`gateway/agent_hub.py::CONNECTORS[*].build_args` define los flags de invocación de
cada CLI (hermes/claude_code/codex/antigravity/openclaw) con valores **[VERIFICAR]**:
no se confirmaron contra el `--help` real de cada herramienta. El gate mockea el
subprocess, así que no se ejercitan.

**Riesgo:** la primera invocación en vivo podría fallar/colgar por flags incorrectos.
Además, invocar estos CLIs cuesta tokens y tiene efectos secundarios.
**Mitigación hoy:** opt-in por tenant + default OFF + delegación OFF por defecto →
no se invoca nada sin activación explícita. **Acción:** confirmar `build_args` de
cada CLI antes del primer uso real (y medir coste/latencia).

## 🟡 Riesgo #10 — Agent Hub: los subprocesos NO están acotados por RLS  [detectado 2026-06-13, Sesión 6] 🔐
El aislamiento multi-tenant de Mia es a nivel **DB** (RLS por `app.tenant_id`). Pero
un CLI que el hub lanza con `subprocess` corre como el **usuario del SO**, con acceso
al filesystem completo del host — **fuera** del alcance del RLS. Si en producción
(Modo A, varios despachos por host) un CLI habilitado por el tenant A recibe datos y
escribe/lee en disco, podría tocar datos de otro tenant a nivel de archivos.

**No bloquea en Modo B** (laptop de un solo despacho). **Acción antes de Fase 5 /
multi-tenant real:** acotar cada subproceso (cwd por tenant, sandbox/contenedor,
usuario del SO dedicado, o whitelist de rutas) para que el aislamiento del SO iguale
al de la DB. Documentado en `architecture/agent_hub.md`.

## 🟢 Riesgo #11 — Compresión solo en MiaAgent.run_turn, no en el grafo 1d  [CERRADO POR REFRAME 2026-06-14]
El ContextCompressor (2c) está cableado en `agent/core.py::run_turn` (el loop simple de
MiaAgent). El TURNO REAL del producto ocurre en el grafo LangGraph (1d,
`agents/graph.py`), que HOY NO llama al compresor. Además el estado del compresor
(`_previous_summary` del resumen iterativo, `_ineffective_count` del anti-thrashing)
vive en la instancia (per-MiaAgent), no en MatterState.

**Riesgo:** en el flujo de producción (grafo) la compresión no está activa; y si se
cablea al grafo (stateless, checkpointed), el estado iterativo/anti-thrash debe migrar a
MatterState o se perdería entre requests.
**Acción:** al integrar la compresión en el grafo, llevar `_previous_summary` y
`_ineffective_count` a MatterState (o al checkpoint). No bloquea hoy (run_turn funciona).

**Cerrado por reframe (2026-06-14, decisión #14):** el ContextCompressor NO se cablea al
grafo en este sprint. Los nodos analysis/draft arman prompts autocontenidos desde
`_last_user_message(state)` + documentos; no consumen `state["messages"]`, así que
comprimirlo sería plumbing inerte. Además `messages` es `operator.add` (append-only):
reemplazarlo por una lista compactada exige cambiar el reducer y tocaría el gate 1d. El
compresor permanece en `agent/core.py::run_turn`. Se reabre con spec propio cuando el
grafo adopte historial creciente (Fase 3 o decisión de producto posterior).

## 🟢 Riesgo #12 — Resumen de compresión como role="system" mid-array  [CERRADO 2026-06-14]
El spec de 2c exige insertar el resumen como UN mensaje `role="system"` con prefijo
`[RESUMEN DE CONTEXTO]` en medio del historial. Anthropic (vía LiteLLM) espera el system
como parámetro ÚNICO al tope, no como turno intermedio; el proxy podría fusionar/hoistear
los system al inicio, perdiendo la posición del resumen (entre cabeza y cola). Hermes lo
evita a propósito usando role user/assistant para el resumen.

**Riesgo:** el resumen podría moverse al tope o comportarse distinto según cómo LiteLLM
traduzca a Anthropic — sin verificar en vivo (el gate es offline).
**Acción:** verificar el comportamiento real contra el proxy; si el system se hoistea,
cambiar el resumen a role="user"/"assistant" con su marcador de fin (como Hermes). No
bloquea hoy (gate offline verde).

**Cerrado (2026-06-14, decisión #15):** se adoptó el fix directamente — el resumen pasa a
`role="user"` con prefijo `[RESUMEN DE CONTEXTO ANTERIOR]` + `SUMMARY_END_MARKER`. No se
esperó a la verificación en vivo: que Anthropic hoistee los system es comportamiento
documentado del proveedor (system = parámetro único al tope), así que el rol de turno es la
opción provider-correcta independientemente del proxy. Gate `test_context_compressor.py`
22/22; regresión 10/10 suites verdes (207 checks).

## 🟡 Riesgo #13 — Corpus SAT-Graph escribible por cualquier conexión mia_app  [detectado 2026-06-14, Sesión 9] 🔐
El corpus compartido (`legal_norms`, `norm_relations`, `jurisprudence`, decisión #16)
tiene RLS con política ABIERTA `USING(true) WITH CHECK(true)` y la escritura se restringe
a `mia_app` solo por GRANT — pero `mia_app` es el MISMO rol que usa toda la app. No hay un
rol de curaduría separado: cualquier ruta de código que tome `pool.connection()` puede
INSERT/UPDATE/DELETE sobre el corpus, no solo el flujo de curaduría.

**Riesgo:** en multi-tenant (Modo A, varios despachos), un bug o un path no previsto podría
mutar el corpus jurídico compartido que ven TODOS los despachos. No bloquea en Modo B
(un solo despacho, curaduría manual). **Acción antes de Fase 5 / multi-tenant real:**
separar la escritura del corpus (rol curador dedicado con GRANT de escritura, mia_app solo
SELECT; o un servicio de curaduría aparte) para que la lectura del producto no pueda
escribir el corpus.

## 🟡 Riesgo #14 — Corpus semilla del SAT-Graph con datos [VERIFICAR]  [detectado 2026-06-14, Sesión 9]
`rag/ingest_corpus.py` precarga 5 normas + 3 providencias + 2 relaciones de Colombia como
DATOS SEMILLA de desarrollo. Varios campos son aproximados o provisionales (fechas, ratio
decidendi, identificadores de jurisprudencia) y van marcados `[VERIFICAR]` en `metadata` /
`summary` / `ratio_decidendi`.

**Riesgo:** si el agente cita este corpus tal cual, entregaría citas no contrastadas contra
la fuente primaria — viola la regla global de verificación de citas. **Mitigación hoy:** son
datos de desarrollo, ninguna cita se ha entregado a un cliente; los marcadores `[VERIFICAR]`
permiten auditarlos. **Acción antes de uso real:** contrastar cada norma/providencia contra
SUIN-Juriscol / Función Pública / la corte respectiva y limpiar los marcadores; no presentar
como verificado nada que siga marcado.

## 🟡 Riesgo #15 — Cron de Obsidian enumera tenants con conexión admin (fuera de RLS)  [detectado 2026-06-14, Sesión 10] 🔐
El job `sync_obsidian_all_tenants` (`cron/scheduler.py`) necesita saber QUÉ tenants tienen
`tenant_settings.config->>'obsidian_vault_path'` configurado. Eso es cross-tenant y bajo RLS
(fail-closed) no es visible desde una sola conexión `mia_app`. `_enumerate_obsidian_targets`
usa por eso una conexión **admin (`postgres`)** para leer `tenant_settings`.

**Riesgo:** es una conexión superusuario en runtime (rompe el principio "la app nunca usa
postgres"). La ESCRITURA por tenant sí pasa por `tenant_connection` (RLS); solo la enumeración
es admin. **No bloquea en Modo B** (un solo despacho). **Acción antes de multi-tenant real:**
reemplazar por una función `SECURITY DEFINER` que devuelva (tenant_id, vault_path) con EXECUTE
para `mia_app`, o un rol/servicio de cron dedicado. Documentado en `architecture/obsidian_sync.md`.

## 🟡 Riesgo #16 — knowledge_chunks se indexa pero todavía NO se recupera  [detectado 2026-06-14, Sesión 10]
El Módulo 3c llena `knowledge_chunks` (conocimiento del despacho), pero NINGÚN path lo lee aún:
`agents/retrieval.py` (RRF) consulta solo `chunks` acotado por `documents.matter_id`. El agente
todavía NO usa el conocimiento de Obsidian al analizar/redactar.

**Riesgo:** indexar sin recuperar es valor latente; podría darse por "ya funciona" cuando aún
no llega al grafo. **Acción (módulo futuro, fuera de 3c):** cablear la recuperación del
conocimiento del despacho —un RRF sobre `knowledge_chunks` (HNSW + content_tsv ya están)— a una
capa del prompt o a un nodo del grafo. Decidir cómo se mezcla con la recuperación por-asunto.
No bloquea hoy.

## 🟡 Riesgo #17 — Pinecone: aislamiento por namespace, no por RLS (por convención)  [detectado 2026-06-14, Sesión 11] 🔐
Pinecone NO tiene Row-Level Security. El aislamiento entre despachos en `PineconeConnector` se
sostiene en UNA convención de código: cada operación usa el namespace `{prefix}_{tenant_id}`,
derivado SIEMPRE del `tenant_id` recibido (el caller no pasa el namespace crudo).

**Riesgo:** si un path futuro construye el namespace con un tenant no verificado, omite el
namespace, o consulta a nivel de índice (sin namespace), un despacho podría leer vectores de
otro. Es el mismo tipo de invariante-por-código que el checkpoint de LangGraph (Riesgo #7) y los
subprocesos del hub (Riesgo #10). **Mitigación hoy:** el conector deriva el namespace
internamente; el caller solo da `tenant_id`. **Acción antes de uso real multi-tenant:** validar
que ningún call exponga el namespace crudo y considerar un índice por tenant si se requiere
aislamiento físico. Documentado en `architecture/pinecone_connector.md`.

## 🟡 Riesgo #18 — Pinecone: SDK no instalado/pinned + conector no cableado todavía  [detectado 2026-06-14, Sesión 11]
Dos cosas pendientes para que Pinecone sea utilizable en vivo:
1. El SDK `pinecone` (v3+) NO está instalado en el `.venv` ni pinneado en `pyproject`. El
   conector lo importa de forma PEREZOSA (`_get_index()`), así que el módulo y el gate corren sin
   él; pero la PRIMERA operación real fallaría con ImportError si no se instala antes.
2. Ningún path escribe/lee por el conector todavía (igual que knowledge_chunks en Riesgo #16):
   el ingest (Módulo 0 / 3c) y el retriever (1d) solo usan pgvector. Pinecone está construido
   pero desconectado del flujo.

**Riesgo:** valor latente + sorpresa en el primer uso real (dependencia faltante). No bloquea hoy
(noop/condicional). **Acción al activar Pinecone:** `pip install "pinecone>=3"` + pinnearlo, crear
el índice (dim 1024, coseno), y cablear ingest/retrieval para escribir/consultar por el conector.

## 🟡 Riesgo #19 — El Curator consolida y poda playbooks SIN revisión humana  [detectado 2026-06-14, Sesión 12] ⚖️
`Curator.consolidate` fusiona dos playbooks con un LLM (`task=curator`) y archiva los originales
automáticamente cuando la similitud coseno supera 0.85; `prune` archiva por antigüedad. No hay
HITL: un playbook jurídico podría degradarse si la fusión del LLM pierde un matiz, o dos
playbooks parecidos pero NO equivalentes podrían colapsarse.

**Mitigación hoy:** los originales quedan en `status='archived'` (NO se borran → recuperables);
la tabla soporta `status='draft'`. **Riesgo:** en producción, una corrida semanal podría alterar
el conocimiento del despacho sin que nadie lo apruebe. **Acción antes de uso real:** insertar el
playbook fusionado como `draft` (no `active`) y exigir aprobación del abogado (HITL) antes de
activarlo; registrar la consolidación para auditoría (ya queda el linaje en `metadata`).
Considerar un umbral más alto y/o tope de consolidaciones por corrida.

## 🟡 Riesgo #20 — La tabla `playbooks` no tiene seeding/onboarding  [detectado 2026-06-14, Sesión 12]
Se creó la tabla `playbooks` y el PlaybookManager DB-backed (decisión #18), pero NINGÚN flujo la
llena todavía: el manager in-memory (`pool=None`) sigue siendo el default y no hay onboarding que
registre los playbooks de un despacho en DB. El Curator corre sobre una tabla que, en producción,
hoy estaría vacía (sus stats serían 0).

**Riesgo:** valor latente; el Curator no hace nada útil hasta que haya playbooks persistidos
(igual que knowledge_chunks/Pinecone, Riesgos #16/#18). **Acción (módulo/flujo futuro):** cablear
el alta de playbooks por despacho (onboarding o import) a `PlaybookManager(pool=…).register_playbook`,
y decidir si el prompt_builder pasa a leer el índice desde DB (`get_index`) en vez del in-memory.

## 🟢 Riesgo #22 — El scheduler nunca se arranca: los jobs cron NO se disparan  [CERRADO 2026-06-14, Sesión 14]
`cron/scheduler.py` registra 3 jobs (`sync_obsidian_all_tenants` 6h, `curator_weekly` 168h,
`feedback_daily` 24h) vía `build_scheduler()`, pero NADIE llamaba a `Scheduler.start()`: el
lifespan de la app (`api/main.py`) no lo arrancaba → las 3 automatizaciones estaban INERTES en
producción.

**Cerrado (2026-06-14):** el `lifespan` de FastAPI (`api/main.py`) arranca el scheduler como
tarea de fondo tras abrir el pool (`asyncio.create_task(scheduler.start())`) y lo detiene en el
shutdown (`scheduler.stop()` + cancelación de la tarea, antes de `pool.close_pool()`). Además se
ajustó `Scheduler.start()` para agendar la PRIMERA corrida de cada job a un intervalo de
distancia (no en el arranque): un job diario/semanal no debe correr en cada reinicio, y así los
gates que instancian la app (`test_hitl_flow`, `test_agent_hub`) no disparan los jobs. Regresión
15/15 verde tras el cambio. Documentado en `architecture/feedback_processor.md` §"Arranque en
producción". Para forzar una corrida manual: `run_job("feedback_daily")`.

## 🟡 Riesgo #21 — Las propuestas de feedback no se revisan ni se aplican  [detectado 2026-06-14, Sesión 13]
El Feedback processor (3e) escribe `feedback_proposals` con `status='pending'`, pero NINGÚN flujo
las consume: no existe la Pantalla 4 (Memoria, Fase 3) para que el abogado las apruebe/rechace, ni
el wiring que, al aprobar una `improve_playbook`/`new_playbook`, registre/actualice el playbook vía
`PlaybookManager`. El bucle de aprendizaje queda ABIERTO (se proponen mejoras que nadie revisa).

**Riesgo:** valor latente (como knowledge_chunks/Pinecone/playbooks, Riesgos #16/#18/#20). Nota
secundaria: una traza histórica v1 (sin `retrieved_doc_ids`) cuenta como NO_RESULT → al procesar
trazas v1 acumuladas podría inflar propuestas `flag_gap`. **Acción (Fase 3):** construir la
Pantalla 4 (listar/aprobar/rechazar propuestas) y conectar la aprobación con el PlaybookManager;
considerar limitar el análisis a trazas v2 para las señales que dependen de campos nuevos.

## 🟡 Riesgo #23 — No hay login/auth de usuario; el frontend usará un token de desarrollo  [detectado 2026-06-14, Sesión 14] 🔐
El middleware exige `Authorization: Bearer <jwt>` con `tenant_id` en todo salvo `/health`, pero
NO existe un flujo de login: los tokens se acuñan fuera (los gates hacen `jwt.encode(...,
JWT_SECRET)`). El frontend (Sesión 15) necesitará un JWT para llamar a `/api/*` y, sin login,
usará un **token de desarrollo hardcodeado** (un solo tenant de dev) — deuda técnica explícita.

**Riesgo:** un token de dev en el frontend NO es seguro para producción ni multi-tenant real
(cualquiera con el token actúa como ese despacho). **Acción (antes de producción):** construir
un flujo de autenticación real (login → emisión de JWT con `tenant_id`, expiración, refresh) o
integrar un IdP. Hasta entonces, el frontend de S15 queda restringido a desarrollo local.

## 🟢 Riesgo #24 — `matters.description` no se persiste  [CERRADO 2026-06-14, Sesión 15]
`POST /api/matters` aceptaba `{name, description}` pero la tabla `matters` solo tenía `title` →
la `description` se devolvía en la respuesta pero NO se guardaba.

**Cerrado (2026-06-14):** migración `008_matters_description.sql` añadió `description text
DEFAULT ''` y `status varchar(20) DEFAULT 'active' CHECK (active|archived|closed)`. `create_matter`
ahora persiste `description`; `list_matters`/`get_matter` devuelven `description` y `status`.
Verificado: las columnas existen y los endpoints las exponen (gate `test_ux.py`).

## 🟡 Riesgo #25 — La UI tiene datos incompletos por falta de endpoint  [detectado 2026-06-14, Sesión 15]
Dos elementos de las pantallas no tienen un endpoint que los alimente y quedan como
placeholder/inactivos:
1. **Diagnóstico (Pantalla 2, columna derecha):** "Problema jurídico / Normas / Riesgo" se
   muestran vacíos. El grafo SÍ produce un diagnóstico (`analysis_node` lo guarda en
   `state.metadata['diagnosis']`), pero NINGÚN endpoint lo expone y el SSE no lo emite.
2. **Punto naranja "borrador pendiente" (Pantalla 1):** `GET /api/matters` no devuelve un flag
   de borrador pendiente (habría que consultar el checkpoint por asunto), así que el punto nunca
   se muestra.
Nota menor: el build del frontend IGNORA ESLint (`next.config.mjs`) — el type-check de TS sí
corre; las reglas de estilo no tumban el build.

**Acción (endurecer UX):** (a) exponer el diagnóstico estructurado (un campo en el SSE
`awaiting_review` o un `GET /api/matters/{id}/diagnosis`); (b) añadir `pending_review` a cada
item de `GET /api/matters` (join con checkpoints o una bandera en `matters`). No bloquea el flujo
principal (preguntar → borrador → aprobar) que sí funciona.

## 🟡 Riesgo #26 — El SOUL.md lo genera un LLM (estructura no garantizada en vivo)  [detectado 2026-06-14, Sesión 16]
`SoulInterview.run_interview` arma el SOUL.md con `call_llm(task="soul")=claude-sonnet` a partir
del template de 9 secciones. El gate (`test_e2e`) MOCKEA el LLM, así que en vivo el modelo podría
no respetar exactamente los 9 encabezados o reformular un campo. La identidad es la capa MÁS
importante del prompt; un SOUL.md mal formado degradaría todos los turnos.

**Mitigación hoy:** (1) el abogado REVISA y puede EDITAR el SOUL.md en la pantalla de resultado del
onboarding antes de continuar (HITL real); (2) `_GEN_SYSTEM` instruye conservar encabezados y
placeholders y NO inventar datos; (3) las respuestas crudas quedan en `…responses.json` (regenerable).
**Acción antes del primer cliente:** validar el SOUL.md generado contra `SOUL_SECTIONS` (las 9
secciones) tras `run_interview` y reintentar/avisar si falta alguna; considerar un render
determinista del template como fallback si el LLM falla.

## 🟡 Riesgo #27 — triad_mode se almacena pero NO está implementado  [detectado 2026-06-14, Sesión 16]
La pregunta 19 (triad_mode) captura si el despacho quiere "modo de análisis profundo" (tres modelos
en ciclo cerrado) y se guarda en la sección `## triad_mode` del SOUL.md. Pero NO existe ningún modo
de ejecución de triada en el grafo: hoy es solo una preferencia almacenada (valor latente, como
knowledge_chunks/Pinecone/playbooks en Riesgos #16/#18/#20).

**Riesgo:** un despacho podría habilitarlo esperando un comportamiento que no ocurre. **Acción
(módulo/flujo futuro):** implementar el modo triada (p. ej. analizar→criticar→sintetizar con 2-3
modelos distintos para matters de alta complejidad, gated por `triad_mode.enabled` + el trigger) o,
hasta entonces, no ofrecerlo como activo en la UI. No bloquea v0.

---

## 📐 REGLA DE ARQUITECTURA — Separación producto vs. instancia personal
(Nota permanente — es una regla de producto, no un bug. Aquí queda visible.)

Mia es un producto genérico para vender a despachos del Civil Law
(Lexia Intelligence), distinto de la IP privada de Lexia Abogados.
Por tanto:
- El vault de Obsidian NUNCA va hardcodeado en el producto.
  `OBSIDIAN_VAULT_PATH` es configuración por despacho (igual que las
  API keys). El producto se entrega con esa variable VACÍA; cada
  cliente la llena en el onboarding.
- En desarrollo se usa `D:\Codex\Lexia-Vault-Test` (vault de prueba
  con 3–4 notas representativas), NO el vault de jurisprudencia
  real del fundador.
- El vault de jurisprudencia real se conecta solo en la instancia
  personal de producción, después de que Mia esté probada.
