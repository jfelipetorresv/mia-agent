# Mia — bugs-and-risks.md
# Riesgos abiertos y watch-outs aún no resueltos
# Última actualización: 2026-07-17 (sesión 48)

Leyenda: 🔴 abierto · 🟡 mitigado/en observación · 🟢 cerrado

## Actualización 2026-07-16/17 — Sesión 48 (agnosticismo de jurisdicción · Agent Hub y Banco de oro · criterio)

### 🟢 Riesgo — La bienvenida no guardaba el motor elegido (CERRADO, `ca7cd74`)
`/activar` llamaba `PUT /api/settings/model-policy`, pero el router de settings se registra SIN
prefijo (`api/main.py:159`): la ruta real es `/settings/model-policy`. El 404 lo tragaba un catch
vacío → elegir motor y los opt-in de OpenRouter/NotebookLM **fallaban en silencio** y el abogado
creía que su elección había quedado fijada. **Cierre:** ruta corregida + el fallo deja de ser
fail-soft (la bienvenida se detiene con motivo en llano en vez de decir "listo" sobre una config
que no se aplicó). Regresión en `test_second_brain_ui`; `test_config_tabs` (21/21) fija además que
las rutas de `/settings` van sin `/api`. Hallazgo de Cursor en capa 3.

### 🟢 Riesgo — Dos gates llevaban sesiones en rojo sin que constara (CERRADOS, `16e9eec` + `9a93341`)
**La línea base de "84 suites ALL PASS" NO era cierta.** Ambos fallaban ya en 7125f8d (verificado),
ambos sobre dinero, y en los dos casos el código era correcto y el test se había quedado en la regla
vieja: `test_connector_hardening` fijaba que 'suscripcion' nunca usara OpenRouter (b582541 lo cambió
por decisión de Pipe, "Ambas") y `test_value_delivered` fijaba que un alias sin precio costara 0
(f147fb9 lo pasó a tarifa conservadora de Sonnet — con 0, el gasto de un motor desconocido no se
cuenta, el tope mensual no frena y el abogado cree que no gastó). Hoy: 37/37 y 28/28.
**Lección:** un gate en rojo que nadie mira es peor que no tenerlo — afirma una seguridad que no
existe. La línea base se re-corre por tramos (no cabe entera en una tanda).

### 🟢 Riesgo — Sesgo colombiano hardcodeado en el backend (CERRADO, `902bd90`/`c4b57f5`/`09d00c7`/`47f5578`)
MIA nacía colombiana por dentro (REGLA DURA: MIA se adapta al despacho que la instala). Cerrado en
cuatro commits: patrones/pistas/léxico al pack, DEFAULT de jurisdicción a 'generic' (migración 036)
con la decisión movida a Python (nunca 'co'), ejemplos del onboarding sin plaza concreta, y el
prompt del anonimizador sin nombrar país. **Cuatro fugas de confidencialidad cerradas** en el
camino (ver progress.md sesión 48), todas confirmadas ejecutando. Guardián: `test_jurisdiction_
agnostic` 75/75 (el prompt no puede volver a nombrar un país ni un formato local).
**Backlog acotado que queda, con su razón de no tocarse hoy:** FTS 'spanish' (exige migración de
índices) y voz TTS es_MX (exige empaquetar una voz por variante).

### 🔴 Riesgo #66 — D3: los flags de los CLI del Agent Hub nunca se han probado contra un `--help` real
Sucesor vivo del Riesgo #9. La delegación ya está cableada de verdad (`delegate_intent` +
`delegate_proposal` + `hub_gate`), pero **ningún ayudante externo se ha invocado en vivo**: los flags
con los que MIA llama a cada CLI están calcados de la documentación, no confirmados contra el
programa instalado. **Riesgo:** la primera invocación real puede fallar. **Lo que lo acota:** degrada
limpio y avisa en llano, y la salida del ayudante va a `metadata` — **NO entra en la cadena de
razonamiento jurídico**. **Honestidad:** "funciona" está sin verificar; los gates prueban el
cableado y el candado, no la invocación. **Acción:** capa 3 de Pipe (probar la delegación en vivo).

### 🟡 Riesgo #67 — El juez de conflictos del Curator está probado en cableado, NO en puntería
`test_curator_conflicts` 38/38 corre **sin red**: el veredicto del juez se inyecta. Que el juez
distinga de verdad un duplicado de una contradicción ("siempre X" vs "nunca X") **está sin medir**.
**Lo que lo acota:** fail-soft a duplicado, es decir, el fallo seguro es degradar al comportamiento
de hoy; y un falso positivo solo interroga al abogado. **Acción:** medir la precisión contra casos
reales cuando haya volumen.

### 🔴 Riesgo #68 — El diagnóstico del turno no se persiste (se pierde dato de valor cada turno)
El diagnóstico vive en el checkpoint y se borra al terminar el turno. **Efecto hoy:** las
conclusiones clave del banco de oro llegan **vacías** en la captura automática (no se inventan: se le
pide al abogado que las escriba). **Efecto de fondo:** cada turno tira a la basura la parte más
valiosa del razonamiento, justo la que serviría para el examen y para aprender.
**Acción:** persistir el diagnóstico por turno (probablemente junto a `traces`) antes de apoyarse en
la captura automática.

### 🔴 Riesgo #69 — El archivo "Patrones rechazados" de dreams sigue sin llegar al modelo
El lazo de aprendizaje NO está cerrado al 100%: lo que el despacho rechaza se escribe, pero el
modelo no lo lee (confidence hardcodeada en 0.10, sin `wiki_schema`). El resto del wiki ya sí se
lee (`9019ee6`), este archivo no. **Efecto:** MIA puede repetir un patrón que el abogado ya rechazó.

### 🔴 Riesgo #70 — El hilo de mensajes del asunto no sobrevive a un F5
No hay endpoint de historial: los turnos están en `traces` pero **nadie los muestra**. El abogado
recarga la página y el hilo desaparece — el dato existe, la pantalla no lo pide. Se vive como
pérdida de trabajo aunque no lo sea.

### 🟡 Riesgo #71 — `index_trace` es best-effort: si esa fila falla, el asunto queda incapturable
La indexación de la traza no bloquea el turno (bien: no se le tumba el trabajo al abogado por un
índice). Pero si esa fila no se escribe, el banco de oro **no encuentra el turno** y el 409
("ya capturado") mentiría. **Acción:** decidir si se reintenta o si se detecta la ausencia en vez de
asumirla.

### 🟡 Riesgo #72 — SOUL, wiki y trazas viven en ficheros SIN RLS 🔐
El aislamiento entre despachos de todo lo que vive en disco (no en Postgres) depende de **sanear el
nombre del fichero**: `_safe_tenant` colapsa entradas distintas a la misma carpeta. Hoy NO es
explotable — los tenant_id son UUID y no colisionan al sanearse — pero es **estructural**: la
garantía no la da el motor, la da una función de nombres. `wiki_dir()` interpolaba el tenant_id sin
sanear y se corrigió esta sesión (era una primitiva de lectura al wiki de otro despacho en cuanto se
cableara la lectura). **Acción:** si algún día los identificadores dejan de ser UUID, esto es un
bloqueante.

### 🟡 Riesgo #73 — El número de migración se reserva al ESCRIBIR, no al empezar
Dos agentes de esta sesión crearon el mismo `038` y hubo que renumerar (soul → 040). Dos migraciones
con el mismo prefijo rompen el orden del ledger y el checksum del gate F0.
**Regla nueva (vinculante):** el número de migración se **reserva al empezar** el trabajo, no al
escribir el archivo. Aplica en particular al trabajo multi-agente sobre el mismo repo.

### 🟡 Riesgo #74 — Capa 3 de Pipe: la deuda acumulada crece con dos frentes nuevos
Además del E2E del instalador en máquina limpia, el recorrido visual y el login real de NotebookLM,
ahora hay que probar **en vivo la delegación (D3, ver #66)** y **el banco de oro de punta a punta**.
Ninguno de los dos se ha ejercido con un caso real por un humano.

## Actualización 2026-07-13/14 — Sesión 47 (Sala de estrategia + OpenRouter)

### 🟡 Riesgo #62 — Slugs de modelo de OpenRouter sin validar contra el catálogo
Los alias `openrouter-sonnet`/`openrouter-haiku` (`litellm_config.yaml` + installer) usan
`openrouter/anthropic/claude-sonnet-4.6` y `openrouter/anthropic/claude-haiku-4.5`, calcados del
patrón, pero NO verificados contra openrouter.ai/models (sin clave en el entorno de build).
**Riesgo:** un slug inexistente hace que el motor OpenRouter caiga a `mia-local` (MODEL_UNAVAILABLE
salta) sin romper el turno, pero pierde la nube en silencio. **Mitigación:** degradación con gracia
+ el ping `_probar_openrouter` fallaría en la validación en vivo si el slug no existe. **Acción de
Pipe:** confirmar los slugs exactos antes de vender.

### 🟢 Riesgo #63 — Overflow de OpenRouter inerte tras reinicio en caliente (CERRADO)
El respaldo/overflow condicionaba a `config.OPENROUTER_API_KEY` (snapshot de import-time); como
`restart_litellm` reinicia solo el proxy, el backend no veía la clave nueva hasta reabrir del todo,
pero la UI limpiaba el aviso. **Cierre:** helper `_openrouter_key_present()` en `llm.py` lee config
O el `.env` en disco (cache 5s); no setea config/os.environ en caliente (respeta la decisión de
welcome.py); seguro porque un alias insertado antes de que el proxy tenga la clave degrada a local
vía el salto AUTH/402. Gate: test_openrouter_policy 16/16 (incluye el caso clave-solo-en-.env).

### 🟢 Riesgo #64 — Sala de estrategia: inyección de 2º orden y costo (CERRADOS/mitigados)
(a) El texto de cada panelista se reinyectaba sin sellar a la ronda 2 y al moderador → ahora
envuelto con `untrusted.fence_block("INTERVENCION", …)` ("DATOS, no órdenes"); el gate de citas
corre sobre cada salida. (b) Costo por convocatoria (varios counsel) → `enforce_budget` (402 al
100% del tope) + degradación funcional a 3 panelistas sin réplicas desde `WARROOM_DEGRADE_AT_FRACTION=0.85`.
(c) `warroom_results` cubierta por `test_rls` (+7 checks A/B). RLS fail-closed por tenant.

### 🟡 Riesgo #65 — Sala de estrategia sin capa 3 (recorrido visual de Pipe)
Las dos features tienen capas 1-2 verdes pero NO se han recorrido en vivo (igual que el resto de
capas 3 acumuladas). Watch-out: streaming del debate en vivo (eventos `counsel_turn`) y el bloque
colapsable no probados con un asunto real por un humano.

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

## 🟡 Riesgo #37 — Secretos y logs (CP-S2): residuales y decisión pendiente  [registrado 2026-07-02, revisión CP-S2]
CP-S2 quedó verde (gate 39/39; el revisor RECHAZÓ la primera versión por H1 — el instalador del
redactor rompía los formatters de uvicorn y apagaba la redacción en los access logs — CORREGIDO
con wrapper que envuelve el formatter original sin reemplazarlo + checks s2-17b/c/d con los
formatters reales de uvicorn; H3 libpq, H5 floor de máscara y H6 falsos positivos también
corregidos). Residuales:
1. **DECISIÓN DE PIPE PENDIENTE (H2)**: la clave de Pinecone que el despacho configura se guarda
   EN CLARO en tenant_settings (JSONB, protegida por RLS). Un dump/backup de la BD la expone.
   Opciones: cifrarla en reposo (pgcrypto — requiere decidir gestión de la llave de cifrado) o
   aceptar el texto plano en v1 como deuda declarada. En logs SÍ queda enmascarada.
2. **Límite conocido (H4)**: JWT_SECRET es una cadena sin forma — si un log lo interpola desnudo,
   ningún patrón lo atrapa (hoy ningún logger lo hace; PyJWT no lo incluye en sus errores).
3. **Sin llamador vivo (H7)**: get_pinecone_connector() fail-closed no tiene caller de producción
   aún (Pinecone es opcional, fuera de la ruta caliente). Al cablear ingest/query de Pinecone,
   envolver con tenant_secret_scope — no hay enforcement automático en la capa de request.
4. **Handlers tardíos**: un handler de logging agregado DESPUÉS del startup del lifespan queda
   sin redactor (se instala en import + lifespan; librerías que agreguen handlers luego escapan).

## 🟡 Riesgo #38 — Endurecimiento y OpenRouter (CP-S3): residuales aceptados  [registrado 2026-07-02, revisión CP-S3]
CP-S3 quedó verde (gate 36/36; el revisor RECHAZÓ la v1 por un BLOQUEANTE — el corte por
desconexión dejaba el checkpoint a medias y el asunto atascado con un 409 engañoso; CORREGIDO
borrando el checkpoint del thread al cortar, con checks s3-04b/c). También corregidos H2 (un
OpenRouter sin saldo/clave inválida ya NO mata la cadena: salta a mia-local — check s3-22),
H3/confidencialidad (OpenRouter es OPT-IN por despacho vía tenant_settings.config['allow_openrouter'],
default OFF — no basta la clave global; checks s3-18b) y H5 (doble invocación del subprocess
evitada con inspect.signature). Residuales:
1. **Env por-conector (H4)**: sanitize_subprocess_env quita TODA credencial al subproceso de los
   CLIs de delegación (hermes/codex/antigravity/openclaw). Un CLI que autentique por variable de
   entorno (p. ej. Codex con OPENAI_API_KEY) quedaría inutilizable. HOY sin impacto: la delegación
   NO tiene caller de producción y sus build_args están [VERIFICAR]. Al cablear un CLI real,
   añadir una allowlist POR conector de las vars que ese CLI necesita (no volver a la global).
2. **Corte solo en frontera de nodo (H6)**: el kill-on-disconnect se evalúa cuando un nodo termina;
   la llamada LLM de analysis/draft (minutos) corre hasta el final aunque el navegador ya se fue.
   El ahorro es parcial, no instantáneo. Aceptable.
3. **Tripwire de cobertura mínima (H7)**: hoy solo cablea configure_pinecone (index_name). El perfil
   del despacho, notas y playbooks —donde un abogado realistamente pegaría una clave— no están
   cubiertos. Extender assert_no_stray_secret a esas escrituras en una ola futura.
4. **DECISIÓN DE PIPE**: OpenRouter enruta datos del cliente a un TERCERO adicional (con su propia
   política de datos/entrenamiento). Está listo pero OFF por despacho. Antes de encenderlo para un
   despacho con datos reales: revisar la política de privacidad de OpenRouter y desactivar el
   logging/entrenamiento en la cuenta (regla 2). La clave necesita tope de gasto en su panel.
5. **Menores de la re-verificación (capa 2, no bloqueantes)**: (a) si la DB falla JUSTO en el corte
   por desconexión, adelete_thread falla y el asunto podría re-atascarse (requiere desconexión +
   fallo de DB simultáneos; lo mejor alcanzable sin un reaper de fondo). (b) La detección de `env`
   del runner (inspect.signature) no cubre runners con `**kwargs` — ninguno existe hoy; si se
   introduce, detectar también VAR_KEYWORD.

## 🟢 Riesgo #39 — Motor de vigilancia (CP-P1): residuales menores  [registrado 2026-07-02, revisión CP-P1]
CP-P1 quedó verde (gate 24/24; capa 2 APROBADO CON CORRECCIONES — el código cumple la regla dura
y el at-most-once por inspección; se CORRIGIÓ H1: el gate doblaba el SQL de la regla dura y el CAS,
ahora se ejercitan contra Postgres REAL (checks p1-db1..7: solo procesales en ventana salen, no
procesales excluidos, debounce real, RLS, CAS concurrente y protección de release ajeno); H4:
run_watch ahora captura la excepción del check y degrada sin apoyarse en el loop del scheduler).
Residuales menores:
1. **H2 · re-aviso sin tope si mark_heads_up falla tras envío exitoso**: mismo trade-off consciente
   que reminders_due (nunca perder un aviso a costa de posible duplicado). La ventana es estrecha
   (la DB acaba de leer bien). Aceptable.
2. **H3 · edición de fecha del recordatorio**: hoy no existe editar due_at (solo create/cancel). Si
   se agrega, resetear heads_up_sent_at = NULL o el nuevo plazo no recibiría aviso anticipado.
3. **Alcance de CP-P1**: se entregó el MOTOR (Watch/run_watch: claim at-most-once + wake-gate +
   no_agent/agent) y UNA vigilancia concreta (plazos procesales próximos, no_agent). "Correo urgente
   de autoridad" NO se construyó (no hay conector de email en Mia — sería build nuevo, futura ola).
   La "revisión semanal de expediente" (vigilancia tipo 'agent' con wake-gate) queda como próxima
   pieza fácil sobre el motor ya existente.
4. **At-most-once solo en las vigilancias nuevas**: los jobs viejos (obsidian, curator, dreams,
   feedback, reminders_due) siguen SIN claim (Modo B single-worker). Migrarlos a run_watch/claim
   cuando haya multi-worker cierra del todo el Riesgo #22.

## 🟢 Riesgo #40 — Conectores de calendario/correo (CP-P3): residuales  [registrado 2026-07-02, revisión CP-P3]
CP-P3 quedó verde (gate test_mailbox.py 45/45; regresión 48/48; capa 2 APROBADO CON CORRECCIONES,
sin bloqueantes). Se CORRIGIÓ el hallazgo MAYOR #1 (fijación de cuenta OAuth cross-tenant): el
`state` firmado ahora lleva un `nonce` que también viaja en cookie HttpOnly/SameSite=Lax de la
sesión que pulsó "conectar"; el callback exige que coincidan (secrets.compare_digest) → ata el
consentimiento a ese navegador. Y el MENOR #3 (crecimiento sin cota del ledger mailbox_notifications):
mark_notified autopoda las filas del tenant con notified_at > 30 días. Residuales abiertos:
1. **#2 · `state` reusable dentro de su ventana de 10 min (no one-time estricto)**: el binding a
   cookie del #1 lo mitiga (un state interceptado sin la cookie de la sesión no sirve). Para one-time
   estricto haría falta un ledger de `jti` consumidos. Aceptable para Modo B; endurecer en multi-tenant.
2. **#4 · costo/carga de la vigilancia Google cada 30 min**: Gmail hace 1+N HTTP por ciclo (listar +
   una por mensaje, hasta 25) por tenant. Degradación ante 429 es correcta (MailboxAPIError→silencio),
   pero es watch-out de escala/rate-limit a vigilar cuando haya varios despachos con Google conectado.
3. **Matiz regla dura**: un evento con pinta procesal cuya fecha `parse_dt` no supo leer se DESCARTA
   (watch_engine descarta eventos sin `start`). Es fail-safe (no inventa fecha), pero preferible
   avisarlo con "fecha por confirmar". Aceptable v1.
4. **CP-P3 es metadata-only**: las vigilancias leen fecha/remitente/asunto y NUNCA el cuerpo del
   correo a un LLM. El análisis de CONTENIDO con IA (opt-in allow_content_analysis, ya cableado
   fail-closed) es CP-P4 — ahí el cuerpo debe viajar SELLADO (untrusted.wrap_untrusted, CP-S1) y solo
   bajo la política de modelo del tenant.
5. **Pendiente de Pipe / frontend (Cursor)**: registrar la app OAuth en Azure (guía en
   docs/conectar-calendario-correo.md) y pegar MS_OAUTH_CLIENT_ID/SECRET en .env; Cursor debe armar
   el botón "Conectar Microsoft 365/Google" en la pantalla Configura a Mia (llama POST
   /api/mailbox/connect/{provider} y redirige a la url; muestra estado con GET /api/mailbox/status).

## 🟢 Riesgo #41 — Análisis de contenido de correo con IA (CP-P4): notas  [registrado 2026-07-02, revisión CP-P4]
CP-P4 quedó verde (gate test_mailbox.py 56/56; regresión 48/48). Capa 2 RECHAZÓ v1 por un
BLOQUEANTE de confidencialidad y luego APROBÓ el fix: **fail-OPEN de la política de modelo** —
`model_policy_for` TRAGA el error de DB y devuelve el default de config ('suscripcion'=nube), así
que un tenant 'soberano' cuya lectura de política fallara habría mandado el CUERPO del correo del
cliente a la nube. FIX: `llm.model_policy_for_strict` (lee sin try/except → LANZA ante error de DB;
fila ausente/valor inválido = estado real → default). `_summarize_urgent_mail` lee la política
PRIMERO con el strict; si lanza → aborta el resumen y degrada a metadata (el cuerpo ni se toca sin
política cierta). Gate mp-c5b lo prueba (policy indeterminada → 0 llamadas al LLM). Notas abiertas:
1. **Google requiere reconsentir para contenido**: gmail.metadata NO lee el cuerpo; hay que
   reconectar con content=1 (gmail.readonly). Si el tenant activó allow_content_analysis pero
   conectó solo-metadata, fetch_body falla → degrada a metadata (no rompe). Microsoft (Mail.Read)
   ya trae el cuerpo, sin reconsentir.
2. **Garantía por prompt, no estructural**: que Mia "no responda ni actúe" el correo y marque
   [VERIFICAR] en plazos se sostiene en el SYSTEM_PROMPT; no hay superficie de acción real (solo
   envía texto por Telegram), así que el riesgo es acotado, pero es guía por prompt.
3. **Costo del resumen**: cada ciclo con opt-in ON y correos urgentes nuevos gasta LLM (bajo la
   política del tenant). Acotado por el wake-gate (solo urgentes-no-avisados) y el debounce, pero
   vigilar si un despacho recibe muchos institucionales/día.
4. **PENDIENTE DE PIPE (confidencialidad)**: encender allow_content_analysis para un despacho con
   datos reales manda el cuerpo del correo al LLM de su política. Si es 'nube'/'suscripción', eso es
   un proveedor de IA — su regla dura exige aprobación explícita por despacho. Default OFF; 'soberano'
   lo mantiene 100% local.

## 🟢 Riesgo #42 — Plantillas + sugerencias consent-first (CP-P2): notas  [registrado 2026-07-02, revisión CP-P2]
CP-P2 cierra la Ola 2 en verde (gate test_blueprints.py 24/24; regresión 49/49). Capa 2
APROBÓ CON CORRECCIONES (2 menores de concurrencia; regla dura y RLS sólidas, sin bloqueantes).
Corregidos ambos con un `pg_advisory_xact_lock(hashtext(tenant_id))` al inicio de propose()
(serializa por-tenant: cierra la carrera del tope de 5 pendientes y la del dedup_key duplicado
que propagaba un 500 por UniqueViolation). Gate bp-db16/17 lo ejercitan con asyncio.gather.
Regla dura verificada sin fisuras: kind e is_procedural salen SIEMPRE del CATALOG (no del body),
generate_suggestions solo PROPONE (0 automatizaciones), accept() es el único creador vía sugerencia,
y la vigilancia solo lee fechas is_procedural con [VERIFICAR] (bp-db5 e2e). Notas:
1. **stale_matter NO se construyó**: la tabla matters no tiene timestamp de última actividad
   (solo created_at), así que una alerta de "asunto quieto" no es cableable sin un cambio mayor
   (añadir last_activity_at y actualizarlo en el flujo de turnos). Se reemplazó por
   calendar_heads_up (no procesal, cableada a la ventana de la vigilancia de calendario de CP-P3).
   Retomar stale_matter cuando exista la señal de actividad por asunto.
2. **Colisión de hash del advisory lock**: hashtext puede colisionar entre dos tenants → a lo
   sumo serialización innecesaria entre ellos en propose (inofensiva; correctness intacta).
3. **Frontend pendiente (Cursor, HANDOFF)**: pantalla de plantillas/automatizaciones + bandeja
   de sugerencias sobre /api/automations/* (catálogo, crear, aceptar/descartar).
4. **Solo 2 plantillas en el catálogo v1**: deadline_heads_up (procesal) y calendar_heads_up
   (no procesal). El marco soporta más; agregarlas es declarativo + cablear su consumidor.

## 🟢 Riesgo #43 — Valor entregado / ROI (CP-V1): límites declarados del estimado  [registrado 2026-07-02, revisión CP-V1]
CP-V1 abre la Ola 4 en verde (gate test_value_delivered.py 27/27; regresión 50/50; capa 2 APROBÓ
tras corregir A1/M1/M2/B1/B2 — la primera versión de la fórmula sobre-reportaba horas). La tubería
(tokens reales por llamada en turn_usage, RLS, tarifa por despacho) quedó sólida. Límites conocidos:
1. **El costo de IA NO incluye embeddings** (voyage-law-2 no pasa por call_llm): el panel
   SUBREPORTA el costo, nunca infla el valor. Ideal futuro: registrar embeddings también.
2. **DRAFT_MIN_CHARS=3000 es heurística declarada**: un análisis muy extenso (≥3000 chars) sin ser
   escrito cuenta 120 min — es la aproximación menos conservadora del conjunto. Refinar cuando el
   grafo etiquete el TIPO de turno (borrador vs diagnóstico vs consulta) en la traza.
3. **turn_usage sin autopoda**: crece ~1 fila por llamada LLM. Aceptable por años a escala actual;
   GRANT DELETE ya está listo para la poda futura (>12 meses).
4. **openrouter-sonnet se precia como el modelo base** ($3/$15): el fee de OpenRouter no se modela.
5. **Los eventos de compresión reales no traen `tokens`** (escriben tokens_antes/despues): el
   fallback legacy los cuenta 0 — coherente con el punto 1 (subreporta, no infla).

## 🟢 Riesgo #44 — Auto-diagnóstico prescriptivo (CP-V2): límites declarados  [registrado 2026-07-02, revisión CP-V2]
CP-V2 quedó verde (gate test_dreams.py 43/43; capa 2 APROBÓ tras re-verificar — los 4 mayores
CORREGIDOS antes del commit: H1 carrera cron×decisión del abogado → el upsert JAMÁS resetea una
fila decidida; solo el flag explícito de resurgimiento la reabre (cierra también el residual R1
de transacciones solapadas, sin comparar relojes); H2 la poda reseteaba la edad de tarjetas
vivas fuera del top → ahora se upserta toda señal viva y el panel filtra por `surfaced`; H3/H4 el
bucket de costo v1 recomendaba un swap por tarea arquitectónicamente imposible → rediseñado a
"gasto real pagado + selector Motor de IA del Panel de control", que existe y guarda; R2 el
texto de costo quedó neutro para no recomendar el motor ya elegido cuando el gasto viene de un
fallback del CLI a la API paga). El motor es DETERMINISTA (sin LLM): la anti-invención queda
garantizada por construcción — toda evidencia sale de conteos de datos reales y con <5 eventos
el bucket se salta. Límites conocidos:
1. **Heurísticas de minutos declaradas**: REWORK_MINUTES/WASTE_MINUTES = 15 min por corrección
   repetida / borrador rechazado. Son estimados de negocio (certeza 0.7/0.8 ya los descuenta en
   el ranking), no medición.
2. **H7 · ID de retrabajo frágil ante inputs variables**: el slug sale de los primeros 80
   caracteres de la solicitud; si el abogado antepone número de expediente/fecha, el mismo patrón
   se fragmenta en contextos distintos y puede no alcanzar el umbral de 3. Fail-safe (calla, no
   inventa). Refinar con normalización (quitar dígitos/fechas) si en uso real se queda corto.
3. **Las tarjetas reflejan la última consolidación semanal**: si una señal se resuelve a mitad de
   semana, la tarjeta sigue visible hasta la próxima corrida de Dreams (diseño semanal aceptado).
4. **bucket de costo solo dispara con motor 'nube' pagado por token**: con 'suscripción' o
   'soberano' el costo marginal registrado es 0 y no hay hallazgo (coherente: no hay nada que
   ahorrar). El texto condiciona la recomendación a que el despacho tenga la suscripción.
5. **Resurgimiento a 30 días sin historial de decisiones**: al resurgir, la fila pasa a
   'recurring' y pierde el registro de la decisión anterior (no hay tabla de historial). Aceptable
   v1; si se quiere auditoría, agregar un ledger de decisiones.
6. **Frontend pendiente (Cursor, HANDOFF)**: tarjetas de diagnóstico en el panel sobre
   GET /api/dreams/prescriptions + botones aceptar/descartar (POST .../decision).

## 🟢 Riesgo #45 — Dictado local (CP-Z1, Ola 3): límites declarados  [registrado 2026-07-03, revisión CP-Z1]
CP-Z1 quedó verde (gate test_speech_stt.py 41/41 con integración real: español correcto en es.wav,
audio de 76 s por el camino VAD, 70 s de silencio → 0 STT; regresión completa; probe de
concurrencia: 3 clips de 24.7 MB simultáneos con el loop latiendo <150 ms). Motor 100% LOCAL
(Silero VAD + Parakeet TDT v3 int8 vía sherpa-onnx), parámetros heredados de Lexter. Capa 2
(revisor adversarial) APROBÓ CON CORRECCIONES — verificó por código que la regla no negociable se
cumple (audio nunca sale del servidor, candado allow_cloud_audio fail-closed real, sin fugas en
logs). Los 2 MAYORES + 6 menores CORREGIDOS antes del commit:
- **[MAYOR, corregido] decodificación del WAV en el event loop**: numpy sobre hasta 32 MB corría
  en el loop ANTES del semáforo → N clips concurrentes congelaban los SSE de otros abogados.
  Movida a asyncio.to_thread DENTRO del semáforo; verificado con probe (gap del loop 46 ms).
- **[MAYOR, corregido] rate-limit por despacho castigaba firmas multi-abogado**: ahora la llave es
  (tenant, email) → cada abogado tiene su cupo (20 clips/5 min); gate r-06b lo cubre.
- **[menor, corregido] guardrail anti-traducción burlable con "no"** (palabra compartida ES/EN):
  ahora exige ≥2 stopwords españolas distintas Y rechaza si gana stopwords inglesas; gate c-02b.
- **[menor, corregido] >60 s de silencio se transcribía igual** (VAD lista vacía → 60 s al STT):
  lista vacía ahora devuelve 0 trozos; gate i-03.
- **[menor, corregido] curl sin -f** en el script de descarga (404 escribía HTML al .onnx): -fSL +
  verificación de tamaño mínimo del VAD.
- **[menor, corregido] jerga "tenant" en el 401** → "Tu sesión no es válida. Vuelve a iniciar sesión."
- **[menor, corregido] _clip_hits sin poda** → poda de claves con ventana vencida (patrón auth.py).
- **[menores de gate, corregidos] añadidos**: c-07 (resolve_fallback_chain('speech_cleanup',
  'mia-local')==['mia-local'] — delata un refactor futuro que rompa el "sin nube"), c-08
  (/api/speech/transcribe no es OPEN_PATH), a-04b (PCM 24 bits).
- **[robustez extra]** timeout de 240 s en la transcripción → 503 en llano si el motor se cuelga
  (evita que un clip zombi mate todo el dictado del proceso).
Límites conocidos que QUEDAN (aceptados v1):
1. **Clips <~0.7 s de voz cortada a media palabra pueden alucinar** (observación #11 del revisor:
   los primeros 0.5 s de un habla real → "Yeah, perhaps."). Parakeet v3 es multilingüe y no se le
   fija idioma. Silencio/ruido puros SÍ devuelven vacío (verificado). Bajo impacto: el abogado
   revisa el texto antes de usarlo. Mitigación futura: filtrar clips con <~0.7 s de voz por VAD.
2. **Sin GPU la latencia sube** en audios largos (Parakeet int8 es rápido en CPU; ~3 s por 5 s de
   audio en la laptop de prueba). Provider DirectML configurable (MIA_SPEECH_PROVIDER) para GPU
   Windows; degrada a CPU con aviso si el build de sherpa-onnx no lo trae.
3. **Sin checksum de integridad de los pesos**: el script verifica tamaño mínimo del VAD y que el
   tarball extraiga, pero no hay SHA256. Aceptable (fuente oficial de k2-fsa por HTTPS).
4. **Rate-limit y semáforo en memoria (Modo B, 1 worker)**: en Modo A multi-worker migrar a
   contador compartido (mismo apunte que auth.py).
5. **Timeout de STT deja el thread zombi**: el servicio responde 503 pero el thread colgado
   retiene el lock del motor hasta reiniciar el API (límite de asyncio.to_thread; declarado).
6. **Frontend pendiente (Cursor, HANDOFF)**: botón de micrófono (captura Web Audio → WAV PCM16
   16 kHz → POST /api/speech/transcribe). MediaRecorder produce webm/opus que el backend NO acepta.
7. **allow_cloud_audio sin UI**: el candado existe y es fail-closed, pero hoy el motor es local, así
   que no hay pantalla para encenderlo (no hace falta en v1; el frontend no debe ofrecerlo aún).

## Riesgo #46 — CP-Z1b (instalación de voz en el producto): residuales aceptados (2026-07-03)

Notas del revisor de capa 2 tras APROBAR — todas fail-closed, ninguna bloquea:
1. **Causa equivocada en un mensaje de error rarísimo**: si al publicar el modelo el directorio
   viejo está bloqueado por otro proceso (estado ya anómalo), os.replace falla y el estado dice
   "revisa la conexión a internet" (la causa real es el disco/bloqueo). Honesto y reintentable,
   solo impreciso.
2. **Staging huérfano**: si el proceso muere a mitad de la extracción quedan ~650 MB en
   `models/speech/*.staging` hasta el siguiente intento (se barre al reintentar). El estado
   sigue honesto ("no instalado").
3. **Disponibilidad del mic por-montaje**: el botón 🎤 consulta /api/speech/status al montar la
   página; si el despacho instala la voz en otra pestaña, hay que recargar la página del asunto
   (coherente con la caché de 60 s del wizard; el clic mientras tanto muestra el mensaje del
   Panel en llano).
4. **Modo A multi-worker**: el estado de la descarga vive en memoria del proceso (criterio de
   _clip_hits/_detect_cache); con >1 worker el polling puede caer en un worker sin la descarga.
   Mitigación futura: estado en Postgres (mismo apunte que Riesgo #45.4).
5. **Mensaje "~700 MB" del alertdialog del dashboard es fijo** (el caso "solo falta el detector"
   no es alcanzable desde el botón porque la tarjeta ya dice Instalado; por API el mensaje del
   backend SÍ diferencia).

## Riesgo #47 — CP-Z2 (voz de salida + notas de voz de Telegram): residuales aceptados (2026-07-03)
   1. **Voz por defecto es_MX-ald sin confirmación final de Pipe:** el checkpoint fija es_MX-ald-medium como voz por defecto (latinoamericana). Se le enviaron 3 muestras (es_MX + 2 castellanas) para que elija por el oído; cambiar la voz = cambiar 5 constantes en speech/tts.py + el nombre del modelo en install.py/ps1. Alto impacto (contenido que oye el cliente) → la elección de Pipe manda antes del merge.
   2. **Latencia de TTS en CPU sin GPU:** VITS es rápido en CPU pero una respuesta larga cerca de VOICE_REPLY_MAX_CHARS (1000 chars) puede tardar segundos; el semáforo serializa voz (1 op a la vez por proceso). Mitigación: DirectML (MIA_SPEECH_PROVIDER) o subir MIA_SPEECH_CONCURRENCY con costo de CPU.
   3. **Empate de timeouts al límite (cerrado, anotado):** acquire 45s + op 240s = 285s < 300s HTTP del puente. Margen 15s. Si se sube MIA_SPEECH_TIMEOUT hay que revisar MIA_SPEECH_ACQUIRE_TIMEOUT y HTTP_TIMEOUT_SECONDS del puente.
   4. **Estado de descarga en memoria (heredado de Riesgo #45.4/#46):** el TTS comparte el estado in-memory de install.py — en Modo A multi-worker el polling de progreso puede caer en un worker sin la descarga. Mitigación futura: estado en Postgres.
   5. **`on_voice` (glue de python-telegram-bot) no está cubierto por gates:** la guardia de file_size y la descarga viven en run_bot, que el bridge no ejercita en tests (se mockea sin PTB). Lógica trivial, verificada por inspección de capa 2.
   6. **Capa 3 pendiente:** dictar una nota de voz REAL (calidad de la transcripción de voz humana y naturalidad de la voz de salida) solo lo puede validar Pipe en vivo con el bot creado.

## Riesgo #48 — CP-E1 (auditoría + tope de gasto): residuales aceptados (2026-07-03)
   1. **Lag del tope por el buffer de metrics/usage:** el gasto se bufferiza y persiste en lotes (CP-V1), así que month_to_date_cost puede ir segundos/minutos atrasado → un turno puede colarse justo al cruzar el tope. Aceptable: es guardia blanda de costo, no facturación. Declarado en el docstring de budget.py.
   2. **FAIL-OPEN del tope (por diseño):** si no se puede leer el tope o el gasto (DB caída), se PERMITE el turno. Frenar el trabajo legítimo de un abogado por un hipo de infraestructura es peor que un sobregasto marginal. Distinto de los candados de confidencialidad (fail-closed).
   3. **Borde `||` con 'policy' escalar (no alcanzable):** si config['policy'] fuera un escalar/array en vez de objeto, el merge `||` concatenaría en array. budget.py es el ÚNICO escritor y siempre lo escribe como objeto → solo se dispararía con manipulación manual de la DB (fuera del modelo de amenaza). Blindaje opcional: CASE WHEN jsonb_typeof(...)='object'.
   4. **Auditoría genérica solo de métodos mutantes:** los GET (incluidas descargas de borrador) no se auditan salvo el turno del asunto (explícito). Login/register no se auditan (pre-tenant). Ampliable si un cliente exige rastro de lecturas.
   5. **Auditoría awaited en el middleware:** agrega una escritura a DB por request mutante (fail-open). Bajo carga alta se podría pasar a fire-and-forget; hoy el volumen de mutaciones es bajo.
   6. **Capa 3 pendiente:** control del tope en el Panel (Cursor).

## Riesgo #49 — CP-E2 (adjuntar pruebas por referencia @expediente/@carpeta): residuales aceptados (2026-07-03)
   1. **Tope de fetch = recursos, no completitud:** `MAX_FETCH_ROWS=2000` acota la memoria del
      fetch por referencia. Con chunks de tamaño normal cubre de sobra el techo de tokens; con
      chunks patológicamente diminutos podría adjuntarse de MENOS (fail-safe: jamás de más). Si
      algún día importa la completitud sobre expedientes enormes, subir el tope o paginar.
   2. **Valor multi-palabra sin comillas se corta:** `@carpeta:Pruebas Zurich` toma solo
      "Pruebas"; "Zurich" queda suelto en el mensaje/query. Es UX (el abogado debe entrecomillar
      valores con espacios). Sin implicación de seguridad. Documentado; un autocompletado futuro
      lo evitaría.
   3. **Referencias solo del turno actual (asistente):** el mensaje PERSISTIDO es el original con
      el `@` literal; los adjuntos NO se re-inyectan en turnos siguientes (como un resultado de
      herramienta, son por-turno). Si el abogado quiere la evidencia otra vez, re-referencia.
      Decisión de producto v1.
   4. **`@carpeta` = carpetas de trabajo (`local_folder_sources`), no Obsidian:** el vault de
      Obsidian (`source='obsidian'`) no es alcanzable por `@carpeta` hoy. Ampliable si se pide.
   5. **Título/etiqueta de matter que contenga literalmente `@carpeta:`** (auto-infligido, mismo
      tenant): al expandir sobre history[-1] aumentado en el asistente, un título así podría
      dispararse como referencia. Es intra-tenant (adjunta datos del PROPIO despacho) → sin fuga;
      solo un adjunto extra inesperado. Aceptado; sin impacto de seguridad.
   6. **A/B en vivo NO ejecutada:** CP-E2 es plomería de entrada (adjunta evidencia que el abogado
      pide explícitamente, sellada, opt-in por referencia); no cambia prompts ni la lógica de
      argumentos legales. Se juzgó que no exige la comparación A/B de alto impacto. Si Pipe quiere
      confirmarlo con un caso real antes de usarlo en producción, es trivial montarlo.
   7. **Capa 3:** NO APLICA (sin frontend); autocompletado de `@` en el chat es trabajo futuro
      opcional documentado en HANDOFF.


## Riesgo #50 — CP-E3 (personas jurídicas editables): residuales aceptados (2026-07-03)
   1. **Candado de motor por CONSTRUCCIÓN, no por posición:** una persona solo puede fijar
      `LOCAL_ALIAS` (motor local) o no fijar nada (`estandar`). `resolve_persona_alias('local')`
      devuelve `LOCAL_ALIAS` directamente (no `chain[-1]`), así que un reordenamiento futuro de
      `_POLICY_CHAINS` no puede filtrar a la nube. ÚNICO punto a mantener: si el despliegue
      renombra el alias del motor local, actualizar la constante `LOCAL_ALIAS` en personas.py
      (el peor caso de un desajuste es un turno que falla CERRADO por falta del modelo, jamás una
      fuga a la nube).
   2. **`role_prompt` NO va fenceado/sellado:** la voz de la persona se inyecta cruda (autoridad
      de estilo, como el SOUL.md del despacho), a diferencia de documentos/notas (contenido de
      terceros, sí sellados con CP-S1). El modelo de amenaza es "el admin del despacho contra sí
      mismo" (config autorizada). Mitigación en profundidad: L2/L3 (método/citación) preceden a la
      voz en el prompt y el guardrail de la voz reitera [VERIFICAR]. Aceptado como decisión.
   3. **Overhead por turno:** `resolve_for_turn` (asistente y asunto) hace 1-2 lecturas RLS por
      turno aun cuando el despacho no use personas (tras la 1ª siembra, es un SELECT del flag + un
      SELECT de las habilitadas). Es indexado y barato; si algún día pesa, cachear por proceso con
      invalidación por escritura.
   4. **Invocación solo por frase (v1):** no hay selector de persona en la UI ni autocompletado;
      el abogado nombra la persona en su mensaje (`explicit_id` existe en el servicio para cuando
      Cursor construya la pantalla). El grafo NO persiste una persona "por defecto del asunto":
      cada turno se resuelve de nuevo desde el mensaje. Decisión de producto v1.
   5. **A/B en vivo NO ejecutada:** sin invocación, CP-E3 es byte-idéntico (probado por gate y
      capa 2); la voz solo aplica cuando el abogado nombra la persona. No hay regresión de la
      calidad legal existente. Se ofreció a Pipe un A/B persona-on/off si quiere evaluar la calidad
      de las voces canónicas antes de confiar en ellas en producción.
   6. **Capa 3 PENDIENTE:** Cursor construye la pantalla de gestión de personas (endpoints
      `/api/personas` GET/POST/PUT/DELETE listos, ver HANDOFF).


## Riesgo #51 — CP-E4 (banco de pruebas de calidad / eval harness): residuales aceptados (2026-07-03)
   1. **Tenants `[eval]` huérfanos si el proceso se mata a mitad:** `run_eval.py` y el gate crean
      un despacho EFÍMERO de prueba y lo borran en `finally` (cascada limpia matters/documents/
      chunks; los checkpoints se borran por thread_id con conexión admin). Un Ctrl-C/SIGKILL entre
      la creación y el `finally` deja un tenant `[eval]` con datos SINTÉTICOS en la DB. Sin
      implicación de confidencialidad (nada real). Mitigación futura: barrido de tenants `[eval]`
      viejos al arrancar, o DB de test separada.
   2. **Marca `[VERIFICAR]` ANTEPUESTA no detectada (heredado de CP9):** `scan_citations` solo mira
      la ventana POSTERIOR a la cita; "[VERIFICAR] Ley 100 de 1993" cuenta como sin respaldo. El
      estilo de la casa pone la marca DESPUÉS, así que en la práctica no ocurre; pero si el modelo
      cambiara a marca-antepuesta, `compare_reports` podría leer una REGRESIÓN falsa (suben citas
      sin respaldo). Métrica acotada; documentado. Se cierra arreglando el escáner de CP9 (fuera
      de alcance de CP-E4).
   3. **El eval mide DISCIPLINA, no exactitud sustantiva:** las señales son deterministas
      (citas sin respaldo, cierre del diagnóstico, borrador) — NO juzgan si el derecho es correcto
      (eso exigiría un LLM-juez o casos con respuesta de oro anotada por un abogado, fuera de v1).
      Es un semáforo de regresión de FORMA/DISCIPLINA, no un juez de fondo. Declarado.
   4. **Casos de oro sintéticos, cobertura mínima (3):** cubren formas comunes (caducidad/
      prescripción/excepción de contrato) para ejercitar el pipeline y el verificador de citas; no
      pretenden cobertura jurídica amplia. Ampliar el set es trabajo incremental sin riesgo.
   5. **Datos reales de cliente = candado fail-closed:** correr el banco sobre expedientes reales
      exige `allow_eval_real_data` (default OFF). En v1 no hay pantalla ni caso que lea matters
      reales; el candado protege un camino futuro. Encenderlo para datos reales requiere aprobación
      explícita de Pipe (regla dura del plan de olas).


## Riesgo #52 — CP-E5 (delegación multi-agente + tablero de misión): residuales aceptados (2026-07-04)
   1. **Colisión silenciosa de `seq` en hitos (m2, capa 2):** `mission_milestones` no tiene
      `UNIQUE(mission_id, seq)`. Si el abogado edita el `seq` de un hito y luego añade/re-descompone,
      dos hitos pueden compartir `seq`. El orden queda determinista por el desempate
      `ORDER BY seq, created_at` (nunca aleatorio ni error) — el peor caso es un empate resuelto por
      antigüedad. No se añadió UNIQUE porque obligaría a reindexar en cada reordenamiento (más
      complejidad que valor). Aceptado por el revisor.
   2. **`matter_id` expuesto en `to_public` de la misión (m3, capa 2):** es un UUID de vínculo que
      el frontend necesita para ligar la misión a su expediente (como el `id` de la misión). NO es
      jerga §G y NO filtra `tenant_id` (`_MISSION_COLS` no lo incluye; sin cruce de despachos).
      Deliberado. Aceptado.
   3. **Tope de gasto por-turno vs. por-entrada (m4, capa 2 — MITIGADO):** `enforce_budget` es una
      guardia de ENTRADA de turno (CP-E1), no un límite por-llamada. El swarm añade N+1 llamadas a
      un turno ya admitido. Mitigación aplicada: `_research_swarm` consulta `budget_status` al inicio
      y si el despacho YA superó el tope del mes, degrada al camino simple (no amplifica). Residual:
      un despacho JUSTO por debajo del tope puede sobrepasarlo dentro de un solo turno
      multi-jurisdicción (acotado por `MAX_WORKERS=8` / concurrencia 4). Inerte para Lexia
      (mono-jurisdicción). Cierre futuro real = medir gasto acumulado del turno, fuera de alcance.
   4. **Verificación de citas del memo consolidado:** cada rama del swarm verifica sus citas
      (determinista) ANTES de sintetizar, pero el memo del SINTETIZADOR no se re-verifica. Es
      consistente con el camino simple (el memo de investigación tampoco se verifica ahí; la
      verificación de citas corre sobre el BORRADOR en verification_node, aguas abajo). Cualquier
      cita nueva introducida por el sintetizador se atrapa igual en la verificación del borrador.
      Declarado, no es regresión.
   5. **Investigación paralela GATILLADA por ≥2 jurisdicciones:** para un despacho mono-jurisdicción
      (Lexia hoy) el camino es byte-idéntico al previo a CP-E5 (cero costo/comportamiento extra). El
      valor de la delegación es latente hasta que exista corpus de una 2ª jurisdicción (pendiente de
      subir). A/B en vivo multi-jurisdicción no corrible aún por falta de ese corpus; evidencia del
      camino nuevo en `test_research_swarm.py`. Ver `docs/comparacion-cpe5.md`.
   6. **Carrera del compresor compartido en el swarm — CERRADA (M1, capa 2):** los workers pasan su
      propio `shrink` a `_llm` → nunca alcanzan `self._compressor` (stateful, compartido). Corregido
      y re-verificado antes del commit. Sin residual.

## Riesgo #53 — CP-E6 (canales relay + MCP seguro): residuales aceptados (2026-07-04)
   1. **Sellado de salida MCP cableado en la ACTIVACIÓN, no ahora (capa 2, MAYOR-andamiaje):**
      `mcp/security.py` expone `seal_tool_output` (CP-S1), `scan_tool_description` (aviso de
      inyección) y `write_token_file` (0600), TODOS probados por el gate, pero HOY sin llamador en
      una ruta viva: no existe aún el cliente JSON-RPC que ejecute una tool y reciba su salida. Es
      andamiaje honesto de la mitad "conexión en vivo diferida" (igual que el OAuth de correo en
      CP-P3 quedó listo y apagado). **Regla al activar:** el cliente MCP en vivo DEBE (a) sellar toda
      salida de servidor con `seal_tool_output` antes de que toque cualquier prompt, (b) pasar cada
      descripción de tool por `scan_tool_description`, y (c) escribir cualquier token en disco con
      `write_token_file`. Sin esos tres cableados, NO se enciende. Aceptado por el revisor como
      andamiaje documentado; no cerrar "salida sellada" como vivo hasta el cableado.
   2. **`build_safe_env` puede ser pisado por una env DECLARADA homónima de un secreto de sistema
      (capa 2, NOTA):** si una entrada del catálogo declarara una variable llamada, p. ej., `PATH` o
      `ANTHROPIC_API_KEY`, el merge la dejaría pasar al subproceso. Ninguna entrada curada lo hace
      (solo `DMS_*`/`PROCESOS_*`), y el catálogo es curado (no lo edita el usuario). Disciplina a
      mantener al agregar entradas: no declarar variables con nombre de credencial de la instalación.
   3. **Permisos 0600 del token no verificados en Windows (capa 2, menor):** el bit POSIX es
      informativo en Windows (plataforma real del proyecto); el aislamiento lo da la ACL del perfil
      del usuario donde vive `$MIA_HOME`. El gate lo declara explícito (no finge 0600 en Windows).
   BLOQUEANTE #1 (los `${VAR}` en `command`/`args` no se interpolaban ni se detectaban como
   colgantes → fail-closed roto) y MAYOR #2 (`disable` prometía un `forget` inexistente) fueron
   CORREGIDOS y re-verificados antes del commit: `resolve_server` ahora interpola y valida entorno +
   comando + args con un resolver único y aborta ante cualquier colgante; `forget_server` + endpoint
   borran las credenciales; `disable` pasó a jsonb_set atómico.

## Riesgo #54 — Fuentes remotas del expediente (Gmail + OneDrive vía Graph API): residuales aceptados (2026-07-09)
   **Contexto:** bloque 2 de la Fase 3 (`tenant_oauth_tokens` multi-proveedor, correos del caso →
   expediente, OneDrive remoto selectivo de solo lectura, UI de las 4 fases). Capa 2 tuvo dos
   revisores independientes: seguridad APROBÓ sin bloqueantes ni mayores; corrección encontró 3
   mayores + 6 menores, TODOS corregidos en el commit `c9f2a32` antes de cerrar la sesión (renombrar
   en OneDrive ya no borra el archivo del expediente; la UI espera a que la sync termine antes de
   refrescar; botón para agregar permiso de archivos a una cuenta Microsoft ya conectada; fallo
   por-correo no tumba el lote; `last_synced_at` por fuente; reset del diálogo al cerrar; uuid
   malformado → 404 en llano; embeddings fuera de la conexión pooled; `quote(safe='')` en ids de
   URLs; scopes base de Microsoft siempre incluidos — ver `progress.md` sesión 36 para el detalle
   completo). Quedan 6 residuales aceptados, ninguno de confidencialidad:

   1. 🟡 **Sin sincronización PROGRAMADA de OneDrive:** solo existe el botón manual "Sincronizar
      ahora". Archivos diferidos por el tope de una corrida (>2000) o que fallaron individualmente
      solo se retoman con un clic explícito del abogado. Deuda consciente — cierre futuro = job
      periódico igual al de `local_folder_sources`.
   2. 🟡 **`[VERIFICAR]` endpoints/scopes reales de Graph/Gmail:** los gates doblan el HTTP (nunca
      llaman a Microsoft/Google de verdad). Falta confirmar contra el proveedor real la primera vez
      que se conecte una cuenta — mismo criterio ya aplicado al mailbox de la Ola 2 (Riesgo
      documentado ahí).
   3. 🟢 **Colisión de ruta al renombrar (rarísimo, auto-sanable):** si un archivo se renombra a una
      ruta que YA ocupa otro archivo distinto en `knowledge_chunks`, podría perderse hasta el
      próximo cambio de contenido de ese archivo (que lo re-sincroniza). Caso extremo, se autocorrige
      solo.
   4. 🟢 **Avisos de correo/calendario podrían repetirse UNA vez tras el deploy:** el formato de las
      claves de debounce de vigilancia cambió a `provider:external_id`; un aviso ya notificado con la
      clave vieja podría notificarse otra vez con la clave nueva. Nunca en silencio, ocurre como
      máximo una vez por aviso.
   5. 🟡 **Candados/throttle de sync en memoria del proceso:** correcto para Modo B (un solo
      worker). Si algún día Mia corre multi-worker, hay que mover el candado a la DB o a un lock
      distribuido.
   6. 🔵 **Nota de negocio para Pipe (no es un bug):** Microsoft no ofrece un scope de "solo
      metadatos" — `Mail.Read` siempre permite leer el CUERPO del correo. Mia solo lee cuerpos
      cuando el abogado busca/vincula un correo explícitamente, pero el permiso técnico de leer
      cuerpos existe desde el momento en que se conecta la cuenta, no solo cuando se usa. Relevante
      para lo que Pipe le explique al cliente sobre el alcance del permiso que otorga.

## Riesgo #55 — OCR local + cron OneDrive (bloques 3a/3b): residuales aceptados (2026-07-09)

1. **Tope de OCR por documento:** 150 páginas / 10 minutos con corte ANOTADO — un expediente
   monstruo entra parcial pero con aviso honesto en el texto. Si en la práctica los expedientes
   de litigio superan esto con frecuencia, subir el tope (es un parámetro).
2. **Calidad dependiente del escaneo:** el OCR lee verbatim a calidad de escaneo normal (probado
   con texto jurídico en español); escaneos torcidos/manuscritos pueden salir con ruido — el
   marcador de lectura óptica por segmento le avisa al abogado qué partes vienen del OCR.
3. **Pin fuera de la vigilancia:** `rapidocr-onnxruntime~=1.4` está en el grupo `~=`, NO lo
   vigila `check_env_pins.py` (decisión consistente con el Riesgo #32 — solo pins críticos ahí).
4. **Reintento por diseño:** archivo sin cuerpo legible queda `omitted` SIN hash guardado → se
   re-procesa solo en la siguiente pasada cuando haya motor OCR; si un tenant tiene miles de
   escaneos y nunca instala el motor, cada sync los re-toca (costo menor, solo lectura local).
5. **Rasterización acotada:** páginas con MediaBox descomunal (>25 Mpx a 220 dpi, piso 72 dpi)
   se SALTAN con anotación — contenido de esas páginas no entra (caso rarísimo, honesto).
6. **Cron cada 6h + throttle 1h por fuente; locks en memoria del proceso** — igual que #54.5:
   correcto en Modo B single-worker; revisar si algún día hay multi-worker.
7. **Nota de tally:** `test_speech_tts` es 24/24 en el script actual (el 26/26 histórico era de
   otra versión); PASS con exit 0 — no es regresión.

## 🟡 Riesgo #56 — Navegador de carpetas (GET /api/folders/browse, Bloque A · A1) expone el árbol local del servidor (2026-07-09)

**Contexto:** para que el abogado elija una carpeta navegando (en vez de escribir la ruta a
mano), `browse_folder()`/`safe_browse_roots()` (connectors/local_folders.py) listan nombres
de subcarpetas de CUALQUIER punto del disco del equipo donde corre Mia, sin exigir que esa
ruta ya esté registrada — es la vía para ELEGIR qué registrar, así que necesariamente ve
más árbol que la allowlist.

**Riesgo:** en Modo B (nativo, un solo despacho por instalación) esto es aceptable —
el abogado navega SU PROPIO equipo. En Modo A (Docker, servidor compartido entre varios
despachos) un endpoint así en el servidor expondría la estructura de carpetas del HOST,
no la de cada cliente — no tiene sentido ahí y podría filtrar nombres de carpetas de otro
despacho si el aislamiento de proceso fallara.

**Mitigación:** (1) fail-closed — mismas reglas que registrar una fuente
(`_FORBIDDEN_PARTS`, `Path.resolve()`, existencia/tipo); solo devuelve NOMBRES de
subcarpetas, nunca archivos ni su contenido, tope de 500 con `truncated`. (2) flag
`MIA_DISABLE_FOLDER_BROWSE` para apagar el endpoint por completo en despliegues
compartidos (mismo patrón que la guarda de `POST /obsidian/install`, revisión CP-C2).
**Acción pendiente:** activar el flag por defecto en la plantilla de despliegue Docker
(Modo A) cuando exista — hoy el flag existe pero nadie lo enciende automáticamente.

## 🟢 Riesgo #57 — H11 CORREGIDO: poda cruzada de OneDrive entre carpetas hermanas del mismo expediente  [CERRADO 2026-07-09, Sesión 39]

**Contexto:** capa 2 (revisión adversarial del Bloque A) encontró que el fix de poda cruzada
que `LocalFolderSync` sí tenía (acotar la poda por `source_id`) NO se había espejado a
`RemoteDriveSync` (`connectors/graph_drive.py`). Con el `FuentesPanel.tsx` nuevo, un
expediente puede tener VARIAS carpetas de OneDrive vinculadas; `_prune_matter_docs` y el
borra-y-reinserta de `_ingest_matter_file` filtraban SOLO por `matter_id`, así que
sincronizar la carpeta B (manual o por el cron de 6h, `scheduler.py::sync_remote_drive_all_tenants`)
borraba en silencio los documentos que había traído la carpeta A — pérdida de datos real,
contradiciendo la promesa "los documentos se conservan".

**Corregido (espejo exacto del fix de `local_folders.py`):**
1. `documents.source_id` ahora se llena también para `origin='drive'` (`_ingest_matter_file`
   inserta con `source_id`, el DELETE previo queda acotado a `source_path=%s AND
   (source_id=%s::uuid OR source_id IS NULL)`).
2. `_prune_matter_docs` filtra SELECT y DELETE por `source_id` exacto — los huérfanos
   `source_id IS NULL` NUNCA se podan (mismo criterio conservador que local).
3. `_move_content` (renombre/movimiento remoto) también acotado por `source_id` para
   `kind='matters'`.
4. Backfill AL FINAL de la migración `028_projects_multifolder.sql`: los documentos
   `origin='drive'` con `source_id NULL` se asignan a la fuente `remote_drive_sources`
   `kind='matters'` de su expediente SOLO cuando hay EXACTAMENTE UNA (procedencia
   inequívoca); los expedientes con historial multi-carpeta quedan con `source_id NULL` a
   propósito (nunca se podan). Nota técnica: se usa `(array_agg(id))[1]` en vez de
   `min(id)` porque PostgreSQL no tiene agregado `min`/`max` nativo para `uuid`.
5. `matter_sources.py::_onedrive_sources` ahora cuenta documentos POR fuente exacta
   (`source_id`); los huérfanos `NULL` solo se suman al conteo cuando hay UNA sola carpeta
   activa (inequívoco) — con varias, no se le atribuyen a ninguna para no mentirle al
   abogado sobre qué carpeta trajo qué. Reemplaza el reparto anterior ("la primera se lleva
   el total, las demás 0").
6. Test nuevo en `execution/test_remote_drive.py` (anti-poda-cruzada): dos carpetas drive
   del mismo expediente, cada una ingiere su archivo, se borra un archivo de A y se
   re-sincroniza SOLO A → el documento de B queda intacto.

**RESUELTO en la misma sesión 39 (cierre del bloqueante residual):** el bloque de backfill
LOCAL de `028_projects_multifolder.sql` (el que asignaba `min(id)` sobre
`local_folder_sources.id`, uuid sin agregado `min`/`max` nativo en PostgreSQL 16) quedó
corregido con `(array_agg(id))[1]` — mismo patrón que el punto 4 de arriba. La migración
completa corre end-to-end sin reventar (verificado con `execution/init_projects_multifolder.py`)
y la regresión completa 74/74 ALL PASS lo confirma, incluyendo `test_matter_sources.py` 26/26
(ya actualizado al reparto honesto del punto 5) y `test_matter_folders_multi.py` 30/30 (con el
caso del backfill conservador). Sin residuales pendientes de este hallazgo.

**Límite consciente (deuda por diseño, no un bug):** los documentos con `source_id NULL`
(procedencia ambigua pre-028, expedientes con historial multi-carpeta) NUNCA se podan por
sync — es la mitad conservadora del backfill (mejor conservar de más que borrar por error).
Si el archivo físico que los originó desaparece, esos documentos quedan "fantasmas" en el
expediente indefinidamente; hoy solo se limpian manualmente. Revisar si en la práctica esto
ensucia expedientes viejos con muchas carpetas rotadas.

## Riesgo #58 — CERRADO (sesión 41, Bloque C): `kind='agente'` implementado (2026-07-10)

**Contexto:** el motor de entrevista stateless (`POST /api/guides/interview`, `guides.py`) ya
acepta `kind` ∈ {`'guia'`, `'agente'`} en el contrato, pero el Bloque B solo construyó el flujo
de guías de trabajo. Con `kind='agente'` el endpoint responde 422 en llano ("Los agentes se
crean con Mia próximamente.") en vez de tramitar la entrevista.

**Riesgo:** ninguno — es una deuda consciente de secuenciación, no un bug. `GuideInterviewWizard.tsx`
ya quedó construido de forma reusable (recibe `kind` como prop) para que el Bloque C (C1 —
"Agentes jurídicos con conocimiento") solo tenga que cablear el flujo de entrevista de agentes
sobre el mismo componente, sin rehacer la UI.

**Acción:** CERRADO en la sesión 41 — la entrevista `kind='agente'` quedó implementada
(interviewer parametrizado por kind + `suggested_playbook_ids` + `onDraftReady` en el wizard,
gate HITL verificado: la entrevista completa sin guardar deja 0 filas). Gate: `test_agent_playbooks.py`.

---

## Riesgo #59 — Verificaciones del instalador diferidas al E2E de Fase 4 (CASI CERRADO tras F4, sesión 45 — solo resta el E2E en frío en máquina 100% limpia, que es de Pipe)

**Qué:** el blindaje de la cáscara y el empaquetado (sesión 42) dejaron verificaciones que SOLO
pueden hacerse lanzando la cáscara/instalador de verdad, prohibidas en la sesión por el
incidente de ventanas en la máquina de Pipe (la cáscara vieja adoptó voicebox en 8000 y el
Next de "Intelligence Sura" en 3100 — evidencia de que la colisión de puertos es caso esperado):
1. Splash bajo la CSP nueva: confirmar VISUALMENTE que estilos y mensajes de error en llano se
   pintan (css/js ya externalizados — el riesgo residual es bajo, pero nadie lo ha VISTO).
2. Gating de IPC remoto: `window.__TAURI__ === undefined` desde localhost:3100 (paso exacto en
   desktop/README.md).
3. `console=True` del exe del backend: hoy abriría ventana de consola negra al abogado —
   decidir console=False al ensamblar el instalador (N9 de la capa 2).
4. E2E completo en frío: máquina sin Python/Node, LOCALAPPDATA virgen, primer arranque.

**Añadidos de la sesión 43 (F2) al mismo E2E de F4:**
5. Recompilar `mia-backend.exe` y compilar `mia-litellm.exe` DESPUÉS de F2/F3 y verificar en
   frío: el exe del backend actual en dist/ NO tiene el `--first-run` ni las datas .sql, y el
   de litellm NO tiene el Blindaje 6 (inyección default de `--host 127.0.0.1` en el entry) —
   hoy la protección de loopback vigente es el flag explícito en `orchestration.installer.json`
   (verificado en vivo: netstat 127.0.0.1, intento LAN rechazado).
6. Primer arranque interrumpido a mitad (cerrar la ventana durante el setup) y verificar que la
   reapertura auto-repara (gatillo triple: marcador `.mia-setup-complete` + PG_VERSION + .env).
   La lógica está cubierta por `test_first_run.py` 68/68; falta VERLO con la cáscara real.
7. `console=True` del exe de LiteLLM: misma decisión pendiente que el del backend (punto 3).

**Acción:** todas quedan como pasos OBLIGATORIOS del E2E de F4 (task_plan) — no cerrar el
bloque instalador sin ellas.

**Ampliado en sesión 44 (2026-07-11):** el E2E de F4 ahora también debe recompilar los exes
incluyendo `welcome.py` (rutas de activación), la migración `031_welcome_bootstrap.sql` y
`env_writer.py` — el `mia-backend.exe` actual en `dist/` no los trae.

**CERRADO en su mayoría (sesión 45, F4):**
- pt 1 (splash bajo CSP): css/js externalizados verificados por `test_shell_hardening` 77/77; la
  vista VISUAL sigue siendo de Pipe (capa 3).
- pt 3 y 7 (console=True/negra): RESUELTO por diseño — la cáscara lanza cada hijo con
  `CREATE_NO_WINDOW` (lib.rs), que oculta la ventana SIN volver el exe windowed. Se mantiene
  `console=True` a propósito: windowed vaciaría el stdout que `run_setup` muestra al abogado como
  motivo de error del primer arranque. (Hallazgo de capa 2: yo había puesto console=False y lo
  revertí.)
- pt 5 (recompilar exes con F2/F3 + placement): HECHO. Los dos exes recompilados (con welcome.py,
  migración 031, env_writer.py, Blindaje 6 loopback en litellm) y **la ubicación física
  verificada empíricamente**: instalación en frío aislada → payloads + `orchestration.json` caen
  DIRECTAMENTE junto al exe, NO bajo `resources/`. La incógnita central de F4 queda resuelta.
- **Resta SOLO:** pt 2 (IPC remoto `window.__TAURI__===undefined` empírico) y pt 4/6 (E2E completo
  en frío en máquina 100% limpia + primer arranque interrumpido con la cáscara real). Son físicos
  (esta máquina de dev tiene el entorno + colisión de puerto 55432) → **capa 3 de Pipe**.
- Además F4 halló y cerró en capa 2: frontend expuesto en 0.0.0.0 → atado a 127.0.0.1; pgAdmin 4
  (~700 MB) sacado del pgsql empaquetado; WebView2 `offlineInstaller` para instalar sin internet.

## 🟢 Riesgo #60 — El motor que depende del proxy LiteLLM no queda activo hasta reabrir MIA [RESUELTO 2026-07-12, sesión 46 — reinicio automático por IPC de Tauri implementado; resta solo la confirmación visual en la capa 3 de Pipe]

**Contexto:** F3 (wizard de bienvenida) añadió `POST /api/welcome/keys` para activar llaves
sin volver a la terminal. La clave de BÚSQUEDA (VOYAGE) se recarga EN CALIENTE porque
`embeddings.py` la consume in-process vía `config`. Pero la clave de RESPALDO (ANTHROPIC) y
OpenRouter alimentan al proxy `mia-litellm.exe`, que lee su `.env` SOLO al arrancar — F3 no
abre el IPC de Tauri necesario para reiniciar el proceso del proxy (mismo hueco que el punto 2
del Riesgo #59).

**Riesgo:** un abogado que elige la política "nube" (o "suscripción" sin el CLI de Claude Code
instalado, que cae de respaldo al proxy) escribe su clave en el wizard y el motor sigue sin
responder hasta que cierre y reabra MIA — sorpresa silenciosa si no se avisa. Para el equipo de
Lexia (suscripción con el CLI de Pipe ya instalado) el riesgo NO aplica.

**Mitigación aplicada en la sesión:** la pantalla `/activar` EXIGE la clave para la política
"nube" (no deja continuar sin ella) y muestra un AVISO FUERTE de que hay que reabrir MIA para
que el motor quede activo. La clave de búsqueda (Voyage) sí queda funcionando de inmediato, sin
aviso necesario.

**Acción (F4 o una ola futura):** el reinicio automático del proxy LiteLLM tras guardar la
clave requiere el mismo IPC remoto que el Riesgo #59 punto 2 deja pendiente de verificación
visual — cerrar ambos juntos cuando F4 monte la cáscara real con Tauri IPC probado en vivo.

**RESUELTO (sesión 46, 2026-07-12):** se implementó el reinicio automático en caliente.
- Cáscara Tauri (`desktop/src-tauri/src/lib.rs`): nuevo comando `#[tauri::command] restart_litellm`
  (registrado en `invoke_handler`), la config del proxy + `app_dir` se RETIENEN en `Shared`
  (`litellm: Mutex<Option<(LiteLlmCfg, Option<String>)>>`) para poder re-lanzarlo, un flag
  `restarting: AtomicBool` con guard que lo limpia en todos los caminos serializa el reinicio, y
  el arranque de litellm se factorizó a `spawn_litellm` (reutilizada por el arranque y el reinicio;
  re-asigna al Job Object anti-huérfanos, mata el proxy viejo con taskkill /T /F y espera a que el
  puerto quede libre antes de re-lanzar). Caminos NO-APLICA seguros: dev sin bloque litellm, litellm
  ADOPTADO (`litellm_pid=None`, no mata proceso ajeno) y cáscara cerrando.
- Frontend (`frontend/app/activar/page.tsx`): tras guardar la clave, si corre dentro de la cáscara
  (`window.__TAURI__`) invoca `restart_litellm`; solo si devuelve "reiniciado" quita el aviso de
  "cierra y reabre". En dev (navegador) `__TAURI__` es undefined → conserva el aviso, sin romper.
  Esto EJERCE el IPC remoto que el Riesgo #59 pt 2 dejaba pendiente (la confirmación VISUAL en vivo
  sigue siendo de la capa 3 de Pipe).
- Verificación: `cargo build` exit 0; `test_shell_hardening` 84/84 (7 checks nuevos del reinicio);
  `test_packaging` 23/23, `test_litellm_packaging` 60/60, `test_first_run` 68/68. Capa 2: revisor
  adversarial independiente de concurrencia/ciclo de vida — 0 bloqueantes, 0 mayores (sin deadlocks,
  ningún Mutex cruza `await`, flag sin fuga, Job re-asignado). `test_welcome_keys` y `test_rls` NO
  se re-corrieron esta sesión (la DB dev de mia no estaba encendida — puerto 55432); el único cambio
  en esa ruta (validación `\n`/`\r` en `env_writer.upsert_env_keys`) se micro-probó aparte. Correrlos
  en el próximo arranque con la DB arriba.
- Pre-flight resuelto de paso (era el punto MAYOR del bug-hunter): se lanzó el `mia-litellm.exe`
  empaquetado con CERO llaves de proveedor (estado del arranque en frío) → arrancó en ~1 s,
  `/health/liveliness` 200, `/v1/models` listó los 5 modelos. LiteLLM tolera `os.environ/X` ausente.

## 🟡 Riesgo #61 — Deuda consciente de la auditoría final pre-prueba (sesión 46, 2026-07-12)

Antes de la prueba en frío de Pipe se corrieron 3 auditorías adversariales independientes
(seguridad, corrección/E2E, y revisión del diff del #60): **0 bloqueantes en todo**. Se corrigió lo
barato (ver #60: validación anti-inyección en `env_writer`, ACL restrictiva del `.env` vía `icacls`
fail-soft en `first_run.py`). Estos 3 puntos se dejaron ANOTADOS como deuda a propósito — cambiarlos
justo antes del E2E en frío es más riesgoso que el problema que resuelven:

1. **Identidad de backend/frontend falsificable localmente (seguridad, MENOR).** La cáscara adopta un
   proceso en sus puertos si presenta señales públicas (claves en `/health`, cabeceras CSP). Un
   proceso local hostil que YA escuche en el puerto exacto ANTES de abrir MIA podría hacerse adoptar
   (phishing de la ventana). Precondición fuerte e irreal en una máquina mono-abogado recién
   instalada; el mecanismo está pensado para colisiones ACCIDENTALES (voicebox, "Intelligence Sura"),
   no para un atacante local decidido. Litellm SÍ exige firma con `LITELLM_MASTER_KEY` (fuerte). Si se
   quisiera cerrar del todo: firmar también la señal de backend/frontend con el secreto del `.env`.
   **Aceptado** para el modelo de amenaza local-first (un abogado = un equipo).
2. **Carpeta de datos = carpeta de programa (corrección, MENOR).** El instalador fija
   `INSTDIR = $LOCALAPPDATA\Mia` y `app_dir = ${local_app_data}/Mia` — los datos del abogado (pgdata,
   `.env`, logs) caen DENTRO de la carpeta del programa. Funciona en frío y el desinstalador usa
   `RMDir` NO recursivo → los datos SOBREVIVEN al desinstalar (bien). Es sucio pero no rompe nada;
   moverlo a `.../Mia/data` es cambio de layout con riesgo de regresión → **aplazado** (mejor con el
   E2E de Pipe como red).
3. **El setup nunca vuelve a correr tras el primer éxito (corrección, MENOR / deuda de "update").**
   El triple gatillo (marcador + PG_VERSION + `.env`) apaga el setup para siempre; las migraciones
   solo corren dentro del setup → en una ACTUALIZACIÓN futura de versión (032+) las migraciones nuevas
   NO se aplicarían solas. No afecta el E2E en frío de hoy; **es la historia de "actualizar una MIA ya
   instalada", pendiente para cuando se aborde el flujo de updates.**

## 🟡 Riesgo #62 — Banco de oro: residuales de anonimización + gate de confidencialidad antes de Fase 2 (sesión 46, 2026-07-12)

Fase 1 (backend) del banco de oro construida y verificada (`test_gold_cases` 37/37 offline; capa 2
adversarial de confidencialidad corrida: encontró 1 BLOQUEANTE —título con PII cruda— + 4 grietas,
TODAS corregidas y re-probadas con los ataques exactos del revisor en el gate). Ver diseño en
`memory/plan-banco-de-oro.md`. Arquitectura de no-fuga verificada sólida: el `anon_map` en claro nunca
se persiste (solo su hash), el juez solo ve texto anonimizado, la Pasada 2 (NER) fuerza modelo LOCAL
(nunca nube), `status='confirmed'` solo por el endpoint confirm (revisión humana), RLS FORCE patrón 015.

**Residuales ACEPTADOS (todos del lado seguro — ocultar de más o cubiertos por la revisión humana):**
1. **El NER local (nombres de personas/empresas) puede omitir entidades** — qwen-7B no es perfecto y
   puede no estar instalado. Mitigación: heurística de SOSPECHA (`scan_suspects`) marca candidatos sin
   ocultar + aviso SIEMPRE cauteloso cuando hay sospechas o el NER no corrió; `spans_pii_restantes`
   vacío = "nada detectado", NUNCA "garantizado limpio". La **revisión humana obligatoria** es la única
   red real contra reidentificación (apodos, hechos únicos que reidentifican por contexto).
2. **Número pelado de 10 díg que empiece en 3** y sea cuantía legítima podría enmascararse como teléfono
   (over-masking, lado seguro). Cédula pelada sin separador ni palabra clave NO se oculta a propósito
   (ambigüedad con cuantías) → cae como `sospecha_id` si no matchea un valor ya mapeado.
3. **Título explícito con un NOMBRE** (no PII estructurada) no lo bloquea `contains_pii` → queda a la
   revisión humana, igual que el cuerpo (decisión: rechazar título con PII estructurada, no anonimizar
   en silencio lo que el abogado escribió literal).

**GATE PENDIENTE (importante):** la Fase 1 NO tiene UI todavía → hoy NADIE puede guardar un caso real
(los endpoints existen pero no están cableados a pantalla). **ANTES de que la Fase 2 (botón "Guardar
como caso de oro" + pantalla) se pueda usar con datos reales, hacer una ÚLTIMA revisión de
confidencialidad end-to-end** (que la UI muestre los spans de sospecha resaltados y obligue la revisión
antes de confirmar). **VERIFICACIÓN DIFERIDA:** la parte RLS de `test_gold_cases` (sección 3) NO se
corrió (DB dev apagada, puerto 55432) — correr con la DB encendida; patrón idéntico a 015.
