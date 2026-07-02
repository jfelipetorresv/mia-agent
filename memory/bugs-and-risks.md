# Mia — bugs-and-risks.md
# Riesgos abiertos y watch-outs aún no resueltos
# Última actualización: 2026-07-01

Leyenda: 🔴 abierto · 🟡 mitigado/en observación · 🟢 cerrado

## Actualización 2026-06-20 — Sesión 20

### 🟢 Riesgo #23 — Login real multi-tenant cerrado
**Cierre:** migración `009_users.sql`, tabla `users` por tenant con RLS, endpoints
`/api/auth/register`, `/api/auth/login` y `/api/auth/me`, bcrypt cost 12, JWT con expiración de
7 días, frontend con `localStorage['mia_token']`, páginas login/register y logout. Se eliminó
`NEXT_PUBLIC_DEV_TOKEN` de `frontend/.env.local`. Gates: `test_auth.py` 20/20 y `test_rls.py` 12/12.

### 🟢 Riesgo #21 — Propuestas revisables desde UI cerrado
**Cierre:** Pantalla 4 muestra sugerencias pendientes y weekly reports; `apply/ignore` existen
para propuestas, y se agregaron tipos `wiki_correction` y `weekly_report`. GEPA y Dreams proponen
mejoras, pero no aplican conocimiento jurídico/procedural sin revisión humana.

### 🟡 Riesgo #29 — Login usa función SECURITY DEFINER para resolver email antes de RLS
Para hacer login, la app necesita encontrar el usuario por email antes de conocer su tenant.
`users` mantiene RLS por tenant, y `auth_user_by_email(email)` es una función `SECURITY DEFINER`
mínima que devuelve id, tenant_id, email y password_hash.

**Riesgo:** cualquier función `SECURITY DEFINER` es una excepción controlada al modelo normal de RLS.
Si se amplía sin cuidado podría filtrar datos cross-tenant. **Mitigación:** devuelve solo la fila
por email único y el password se valida con bcrypt. **Acción:** auditar antes de multi-tenant
productivo y considerar un rol auth dedicado.

### 🟡 Riesgo #30 — Pinecone API key se guarda en tenant_settings sin cifrado
`/api/connectors/pinecone/configure` guarda `{api_key,index_name}` en `tenant_settings.config`.
El spec permitió "encriptado o como está"; se eligió "como está" para cerrar el flujo local.

**Riesgo:** en producción, una lectura indebida de DB expondría la API key del tenant.
**Acción:** cifrar secretos por tenant o moverlos a un vault/secret manager antes de producción.

### 🟢 Riesgo #31 — GEPA depende de trazas con activación de playbook para medir skills  [CERRADO 2026-07-01, CP-C3]
**Resolución (CP-C3, sesión 22):** el cableado ya existía (graph.py registra
`activated_playbooks` en la traza v2 desde el smoke de 2026-06-30); CP-C3 cerró la brecha
LÓGICA restante — el FeedbackProcessor ahora vincula cada señal (rechazo/edición) con los
playbooks activados en ESAS trazas y propone mejorar el correcto (no uno arbitrario); la
propuesta se redacta sobre el contenido real del playbook; aplicarla guarda el contenido
anterior en `metadata.last_improvement` (reversible) y el abogado ve qué procedimiento se
modifica (`target` en GET /api/proposals). Gates: test_feedback_processor 26/26 ·
test_gepa 18/18 · test_trace_capture 23/23. **Residual → Riesgo #20:** la vuelta EN VIVO
del ciclo espera que Pipe suba sus guías (sin playbooks sembrados no hay activación que
observar). Detalle original ↓
GEPA soporta `playbook_id`, `playbook_ids`, `skill_id`, `skill_ids` o `activated_playbooks` en
trazas JSONL. Las trazas del grafo no siempre registraban qué playbook se activó.

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

## 🟢 Riesgo #16 — knowledge_chunks se indexa pero todavía NO se recupera  [CERRADO 2026-07-01, CP3]
**Cierre:** el conocimiento del despacho ya llega al análisis (decisión #31). `retrieval.py`
ganó `retrieve_knowledge_rrf` (mismo RRF híbrido vector+FTS que el del expediente, sobre
`knowledge_chunks`, SIN filtro de asunto — es conocimiento transversal — y bajo
`tenant_connection`/RLS fail-closed) y `knowledge_exists` (chequeo barato). `intake_node`
REUSA el embedding del mensaje (cero llamadas extra a Voyage; si el asunto no tiene documentos,
embebe solo cuando hay knowledge) y `analysis_node` añade la sección "Conocimiento del despacho"
al prompt con presupuesto duro ≤15% de la ventana; sin knowledge el prompt queda byte a byte
idéntico a antes. En el shrink de CONTEXT_TOO_LONG (CP1), el knowledge se recorta ANTES que los
documents. Gate: `execution/test_retrieval_knowledge.py` 30/30 (relevancia, aislamiento A/B
estilo test_rls, prompt idéntico sin knowledge, presupuesto, shrink); regresión
`test_context_recovery.py` 34/34 · `test_hitl_flow.py` 19/19 · `test_rls.py` 12/12.

Histórico: el Módulo 3c llenaba `knowledge_chunks` (conocimiento del despacho), pero NINGÚN
path lo leía: `agents/retrieval.py` (RRF) consultaba solo `chunks` acotado por
`documents.matter_id`. El agente no usaba el conocimiento de Obsidian/carpetas al analizar.

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

## 🟢 Riesgo #19 — El Curator consolida y poda playbooks SIN revisión humana  [CERRADO 2026-06-30, H.2/H.5/C.5] ⚖️
**Cierre:** H.2 introdujo el flujo HITL `propose → approve → apply` (`Curator.propose` persiste una
propuesta en seco; la aprobación por API ejecuta la fusión/poda de forma atómica con validación de
`snapshot_hash`), y el cron `curator_weekly` pasó a **solo proponer**. C.5 (2026-06-30) selló el
ciclo mutante antiguo: `run()`→`_run_legacy()` bloqueado por el guard `MIA_ALLOW_CURATOR_LEGACY_RUN=1`
(exclusivo de tests) → en producción es IMPOSIBLE mutar playbooks sin aprobación. Refuerzo H.6: los
playbooks `protected` (semilla/core) quedan fuera de consolidación y poda aunque se apruebe una
corrida. Gates: `test_curator_hitl` 29/29, `test_curator` 24/24, `test_playbooks_protected` 19/19.

**(histórico) Estado original del riesgo:**
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
**Actualización 2026-07-01 (CP4):** mecanismo de import listo (POST /playbooks/import + gate); falta solo que el despacho cargue sus guías reales — el cierre definitivo llega con la primera traza viva con activated_playbooks no vacío.

Se creó la tabla `playbooks` y el PlaybookManager DB-backed (decisión #18), pero NINGÚN flujo la
llena todavía: el manager in-memory (`pool=None`) sigue siendo el default y no hay onboarding que
registre los playbooks de un despacho en DB. El Curator corre sobre una tabla que, en producción,
hoy estaría vacía (sus stats serían 0).

**Riesgo:** valor latente; el Curator no hace nada útil hasta que haya playbooks persistidos
(igual que knowledge_chunks/Pinecone, Riesgos #16/#18). **Acción (módulo/flujo futuro):** cablear
el alta de playbooks por despacho (onboarding o import) a `PlaybookManager(pool=…).register_playbook`,
y decidir si el prompt_builder pasa a leer el índice desde DB (`get_index`) en vez del in-memory.

**Cierre PARCIAL (2026-06-30, smoke vivo):** se CONFIRMÓ que el wiring de consumo funciona end-to-end
— `graph._prepare_playbooks` carga el índice, activa por solape (`_select_playbook_ids`, tope 3),
`mark_used`, y `draft_node`/`finalize` emiten `activated_playbooks` a la traza (`mia.trace.v2`).
Lo que falta es SOLO el **seeding de datos**: en el smoke las trazas salieron con
`activated_playbooks: None` porque el tenant de prueba no tiene playbooks en DB. Cierra del todo
cuando un onboarding/import siembre playbooks reales y se observe una traza con lista no vacía.

**Avance (2026-06-30, H.6):** se añadió la infraestructura de **playbooks `protected`** (columna
`protected`, `register_playbook(protected=True, force=…)`) para que el seeding futuro pueda marcar
los playbooks semilla como inmunes al mantenimiento automático. Sigue faltando el flujo de
onboarding/import que efectivamente los inserte; H.6 deja lista la bandera que ese flujo usará.
Mismo cierre parcial aplica al **Riesgo #31** (las activaciones ya se registran en la traza; faltaba
el cableado al grafo, ahora hecho — solo falta el dato).

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

---

## 🟢 PENDIENTE DE REVISIÓN — Módulos sin registrar en progress.md  [CERRADO 2026-07-01]
**Cierre (2026-07-01):** se revisó el código de los 3 módulos, se re-corrieron sus gates (los 3
verdes: `test_gepa` 16/16 · `test_dreams` 16/16 · `test_second_brain_ui` 15/15, idénticos a los
números de `task_plan.md` §Fase 5) y se escribió la entrada retroactiva en `progress.md`
(**"## 2026-07-01 — Entradas retroactivas (módulos de sesión 20 sin documentar)"**) que documenta
qué es cada módulo, qué hace, las decisiones de diseño visibles en el código y el resultado de su
gate. Queda marcado explícitamente que es documentación retroactiva (los módulos son de la Sesión
20, 2026-06-20, Fase 5). Límite del cierre: es reconstrucción por lectura de código — el
razonamiento original de la sesión 20 (alternativas descartadas) no es recuperable.

**(histórico) Estado original del riesgo:**
Hay código en el árbol que **no figura en `progress.md`** (cuya última entrada de diario es
2026-06-21 "Replan Ruta B + Fase 0"): `backend/mia/memory/gepa.py`, `backend/mia/memory/dreams.py`,
y la UI/tests de `second_brain_ui` (p. ej. `execution/test_gepa.py`, `execution/test_dreams.py`,
`execution/test_second_brain_ui.py`). Esto indica **trabajo posterior a la última entrada del
diario que no quedó documentado** en el DIARIO DE OBRA.

**Riesgo:** la memoria de construcción (fuente de verdad para Claude Code entre sesiones) está
desincronizada del código real; al retomar se pueden tomar decisiones sobre un estado mal
entendido (qué existe, qué pasa sus tests, qué decisiones lo respaldan).
**Acción:** revisar qué son GEPA / dreams / second_brain_ui, correr sus gates, y escribir las
entradas faltantes en `progress.md` + `session-summaries.md` (y `decisions.md` si hubo decisiones
de diseño). Detectado durante el smoke test vivo del 2026-06-30.

---

## 🟢 Riesgo #32 — LiteLLM comparte el `.venv` de la app y degrada versiones al reinstalar  [detectado 2026-06-30, smoke vivo] [CERRADO 2026-07-01, CP0] 🔐
**Resolución (2026-07-01, checkpoint CP0):** LiteLLM proxy separado en `.venv-litellm/` propio
(`litellm[proxy]==1.74.8`); `scripts/start_litellm.ps1` arranca desde ahí. Runtime del API
re-pineado EXACTO en `backend/pyproject.toml` (fastapi/uvicorn/starlette/sse-starlette/
python-multipart/psycopg/psycopg-pool/litellm/websockets — websockets 13.1 era degradación
remanente, restaurada a 15.0.1). Gate nuevo `execution/check_env_pins.py` cableado a
`start_api.ps1` (aborta el arranque si el venv fue alterado) y a `run_tests.ps1` (aborta la
regresión). Deuda declarada: uvicorn 0.29.0 y sse-starlette 3.0.3 quedaron pineadas a las
versiones que dejó la degradación (funcionales, 32/32 verde); subirlas es tarea aparte y
controlada ahora que el proxy tiene venv propio. Detalle original ↓
LiteLLM se ejecuta desde el MISMO `.venv` que la API de Mia (`backend/`). Reinstalar
`litellm[proxy]` (necesario para reparar el proxy / Prisma en esta sesión) **bajó/movió versiones
de paquetes compartidos** con FastAPI/uvicorn de la app: `uvicorn`, `sse-starlette`,
`fastapi`/`starlette` y `python-multipart`. Como la API de Mia depende EXACTAMENTE de esas
librerías (SSE de `stream.py`/`hitl.py`, uploads `multipart`, el ASGI server), un pin que LiteLLM
arrastre puede romper el arranque de uvicorn o cambiar el comportamiento de SSE/streaming en
producción de forma silenciosa.

**Riesgo:** un reinstall de LiteLLM antes de un reinicio de la API en producción puede dejar la API
con dependencias incompatibles → caída del servidor o regresión de SSE/uploads que NO se ve hasta
el primer turno real. Es el mismo patrón que el Riesgo #4 (LiteLLM como librería vs. proxy): dos
consumidores acoplados por el entorno.

**Mitigación hoy:** el smoke vivo corre LiteLLM con `scripts/run_litellm_clean.ps1` (CWD aislado +
DB env scrubbed), pero eso NO aísla las versiones de paquetes: el `.venv` sigue siendo uno solo.

**Acción (antes de cualquier reinicio de la API en producción):** **separar LiteLLM en su PROPIO
venv** (p. ej. `.venv-litellm/`) y arrancar el proxy desde ahí; el `.venv` de la app queda con sus
pins intactos. Tras separarlos, re-pinear FastAPI/uvicorn/sse-starlette/starlette/python-multipart
en `backend/pyproject.toml` a las versiones probadas y verificar el arranque de uvicorn + un turno
SSE completo. Mientras compartan venv, NO reinstalar `litellm[proxy]` con la API productiva viva.

## 🟢 Riesgo #33 — CONTEXT_TOO_LONG en el grafo: la recuperación por compresión es un no-op  [detectado 2026-06-30, H.5] [CERRADO 2026-07-01, CP1] ⚖️
**Resolución (2026-07-01, checkpoint CP1):** nuevo `backend/mia/agents/context_recovery.py` con
helpers puros (`shrink_documents` / `shrink_text` / `budget_for`) que recortan el MATERIAL del
prompt por nodo; `graph.py::_llm` acepta un `shrink` opcional que ante CONTEXT_TOO_LONG rearma el
prompt reducido (analysis: menos documentos + contenido truncado; draft: playbooks → solo índice y
diagnóstico recortado preservando la conclusión), manteniendo el contrato una-sola-compresión-por-
turno (TurnLLMState). Los nodos sin `shrink` (finalize/EDIT) conservan el camino del
ContextCompressor. Gate nuevo `execution/test_context_recovery.py` (offline) + regresión
`test_llm_fallback.py` y `test_hitl_flow.py` verdes. Detalle original ↓
El rescate de contexto que añadió H.5 en `agents/graph.py::_llm` NO funciona para los prompts que
realmente pueden desbordarse. Cuando una llamada falla con `CONTEXT_TOO_LONG`, `_llm` invoca
`ContextCompressor.compress(messages, …)` y reintenta; pero los nodos `analysis_node` y `draft_node`
arman prompts **monolíticos de solo 2 mensajes** (`[system, user]`), y el compresor protege cabeza
(`protect_first_n=5`) y cola (`protect_last_n=30`): con 2 mensajes no hay "bloque del medio" que
resumir → `compress()` **devuelve los mismos 2 mensajes** y el reintento falla exactamente igual.
El material que sí pesa (los `documents` embebidos en el user de `analysis`, y el
`diagnosis`+`playbooks` del user de `draft`) queda intacto.

**Riesgo:** un expediente grande o muchos documentos recuperados pueden hacer que el turno falle con
`CONTEXT_TOO_LONG` sin recuperación efectiva → el abogado ve un error en vez de un análisis/borrador.
La maquinaria de H.5 (TurnLLMState, `compression_attempted`, reintento desde chain[0]) está bien
cableada, pero le falta el paso que de verdad reduce el tamaño. **Alcance:** afecta solo la ruta de
desbordamiento de contexto; el turno normal y el fallback de proveedor (H.5) funcionan.

**Acción (próxima sesión):** añadir **truncado/recuperación por nodo** en `graph.py` antes del
reintento — en `analysis_node` recortar/resumir `documents` (p. ej. menos docs o snippets más
cortos vía `retrieval`), y en `draft_node` recortar `diagnosis`/`playbooks` — de modo que el
reintento parta de un `user` genuinamente más chico. Alternativa: que `_llm` (o un helper
`context_recovery` por nodo) reconstruya el mensaje `user` reducido en vez de delegar en
`ContextCompressor`, que está pensado para historiales de conversación, no para prompts de 2 mensajes.
Cubrir con un gate que fuerce `CONTEXT_TOO_LONG` en el 1er intento y verifique que el 2º manda un
prompt más corto.

## 🟡 Riesgo #34 — Política de modelo: caché por proceso y CLI colgado pueden retener el request  [detectado 2026-07-01, revisión CP2]
Dos modos de degradación del motor por suscripción (decisión #27), aceptables hoy pero a vigilar:
**(1) Caché de política por proceso.** El middleware cachea `model_policy` por tenant con TTL 60s
**en memoria del proceso**. Con VARIOS workers de uvicorn (o API replicada, Modo A), un PUT a
`/settings/model-policy` solo invalida el caché del worker que atendió el PUT: los demás pueden
servir hasta ~60s con la política VIEJA. En Modo B (1 worker) no pasa. **Acción al pasar a Modo A:**
invalidación compartida (Postgres LISTEN/NOTIFY o bajar el TTL) o aceptar los 60s documentándolo.
**(2) CLI colgado = request retenido minutos.** Si el CLI `claude` no responde, cada intento espera
el timeout completo (300s main/curator, 120s resto) y `call_llm` reintenta hasta 3 veces DENTRO del
alias antes de saltar de proveedor: en el peor caso un turno puede quedar retenido varios minutos
antes de caer a la nube/local. Mitigación parcial ya aplicada (timeout por task); si aparece en uso
real, bajar reintentos para aliases `cli-*` (el CLI local rara vez se recupera reintentando) o
timeout más agresivo con detección de "CLI muerto" (circuit breaker por proceso).

## 🟡 Decisiones de producto PENDIENTES DE PIPE  [registrado 2026-07-01, sesión 21]
Tres decisiones de negocio quedaron abiertas durante el plan maestro; no son bugs, pero
condicionan comportamiento visible al cliente y deben resolverse antes de endurecer (CP8):
1. **Privacidad intra-despacho de las conversaciones del asistente (CP-B1):** hoy las
   conversaciones del modo asistente son visibles a NIVEL DE DESPACHO (cualquier abogado del
   tenant puede verlas). ¿Deben ser privadas por usuario? Anotado por el revisor de CP-B1.
2. **Diagnóstico visible tras aprobar (CP5):** el panel "Diagnóstico" puede seguir mostrando
   el análisis del último turno ya decidido. ¿Se oculta/archiva tras aprobar o rechazar?
3. **Endpoint de instalación de Obsidian en Modo A (CP-C2):** `POST /api/obsidian/install`
   ejecuta winget en el HOST — correcto en Modo B (laptop de un despacho), pero en despliegue
   compartido (Modo A) DEBE DESHABILITARSE (documentado en su docstring; Riesgos #10/#15 de
   sandbox). Requiere gate de despliegue antes del primer cliente Modo A.

## 🟡 Riesgo #35 — Notificaciones proactivas: canal ÚNICO de Telegram y residuales de CP-B3  [registrado 2026-07-01, revisión CP-B3]
CP-B3 quedó verde (gate 64/64, 2 bloqueantes y 5 mayores del revisor corregidos), pero deja
residuales ACEPTADOS y documentados, a resolver antes del multi-tenant real:
1. **Canal único**: hay UN bot y UN chat (el de `MIA_BRIDGE_EMAIL`). Los demás despachos pueden
   crear recordatorios y Mia les avisa honestamente que no les sonará (quedan visibles en su
   lista); el multi-tenant real necesita canal por despacho (token/chat en `tenant_settings`).
   El aislamiento está garantizado: los jobs solo despachan al tenant dueño del canal.
2. **Reintento sin tope**: un mensaje que Telegram rechace PERMANENTEMENTE (p. ej. 400) se
   reintenta cada 5 min sin contador ni cuarentena. A escala de un despacho es inocuo.
3. **Varios workers = avisos duplicados**: el scheduler vive en el lifespan de FastAPI (patrón
   preexistente); con >1 worker de uvicorn habría N schedulers. Modo B usa 1 worker.
4. **Horas ambiguas**: "a la 1" = 01:00 (la confirmación muestra la hora exacta, es detectable).
   "avísame mañana qué opinas" crea un recordatorio en vez de conversar (disparador débil CON
   fecha se intercepta; sin fecha ya no — hallazgo M5 corregido a medias por diseño).
5. **Canal atado a `users.email`**: si el usuario del puente se elimina y otro despacho registra
   ese mismo correo, las notificaciones cambiarían de tenant en silencio. Supuesto operativo:
   el correo del puente no se recicla entre despachos.

## 🟡 Riesgo #36 — Cuarentena universal (CP-S1): residuales aceptados  [registrado 2026-07-02, revisión CP-S1]
CP-S1 quedó verde (gate 28/28, hallazgos H1 mayor y H2 menor del revisor CORREGIDOS antes del
commit: se eliminó la guarda anti doble-envoltura burlable y se alineó la instrucción de citas
del especialista de hechos al sello <<<DOC n>>>). Residuales aceptados:
1. **Overhead del sello no descontado en shrink_documents (H3)**: el encabezado de documentos
   (~40 tokens) + sellos (~8-10/doc) no se restan del presupuesto al recortar. Caso patológico
   (muchos docs justo en el límite tras CONTEXT_TOO_LONG) fallaría el turno con error claro, no
   se cuelga (guard after>=before de graph.py). Preexistente a CP-S1, agravado marginalmente.
   Fix futuro: descontar el overhead en shrink_documents o budget_for.
2. **neutralize() solo atrapa ASCII (H4)**: homoglifos Unicode (＜＜＜ fullwidth, 〈〈〈) no se
   neutralizan. Riesgo teórico bajo: el sello real es ASCII exacto; un lookalike no cierra el
   bloque. Límite conocido, anotado.
3. **Alcance deliberado**: playbooks y perfil NO se cuarentenan (contenido editorial del
   despacho aprobado vía HITL — son instrucciones legítimas); el mensaje del abogado y su
   Telegram privado tampoco (es el principal que da órdenes). Si en el futuro los playbooks
   se importan de fuentes NO curadas por el despacho, revisar esta decisión.
