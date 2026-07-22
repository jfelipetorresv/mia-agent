# HANDOFF — Mia (traspaso a Cursor)

> **PLAN MAESTRO VIGENTE (aprobado por Pipe 2026-07-21):**
> `C:\Users\USER\.claude\plans\fable-puedes-estructurar-un-sleepy-sifakis.md` — "Dejar MIA funcionando
> en los términos de la visión". Fases F0→F6 + 2 sesiones de Pipe; dynamic workflows con matriz
> Opus/Sonnet/Haiku/Codex; refutado por Codex en xhigh. El prompt de arranque está en su sección
> «Arranque en una terminal nueva». Toda sesión de implementación empieza leyendo ese plan + la
> entrada más reciente de este archivo.

---

## Cómo usar este archivo (regla de mantenimiento)

Aquí viven SOLO la entrada vigente («EMPEZAR AQUÍ») y la inmediatamente anterior.
Al escribir una entrada nueva: mover la más vieja de las dos a `docs/handoff-historial/`
con el siguiente número (`NNN-titulo.md`) y agregarla arriba del todo en su `INDICE.md`.
El historial completo está en `docs/handoff-historial/INDICE.md`. Nada se borra.

---

# PAUSA — 2026-07-21 · reinicio de máquina a mitad de la preparación de F1 · EMPEZAR AQUÍ

Rama `feat/fase1-inc1-cleanup-scaffolding`. **F0 está completa y PUSHEADA** (hasta `dad662e`). Esta pausa es
a mitad de la PREPARACIÓN de F1 (cerrar la deuda de dinero + demostrar que el banco puede fallar, ANTES de
gastar contra el modelo). Nada se ha gastado aún de forma seria.

## Cómo retomar (en orden)

1. **Reiniciar servicios** (el reinicio los mató; la DB portable 55432 puede volver sola o no):
   - LiteLLM :4000 → `scripts/start_litellm.ps1` **con `run_in_background` del harness** (si no, muere).
   - DB 55432: si no está, `pg_ctl` según `scripts/setup_db.ps1` (lee puerto del `.env`).
   - Verificar con `curl -s http://127.0.0.1:4000/health/liveliness` (debe dar 200) antes de gastar.
2. **Primera sonda ante cualquier lentitud rara: contar `node.exe`.** Los zombis de `statusline.js` ya
   tienen la causa raíz arreglada (ver cierre de F0), pero si reaparecen, matar solo los `statusline`.
3. **Retomar la ronda 2 de preparación de F1: solo falta VERIFICAR** (las correcciones ya están aplicadas).

## Qué quedó a medias (estado exacto)

**Preparación de F1 = 3 frentes.** Frente **B APROBADO Y COMMITEADO** (`b86b15a`: el banco demuestra que
sabe reprobar — 50 mutaciones plantadas + holdout intocable con manifiesto de hashes).

Frentes **A (dinero) y C (panel): ronda 1 rechazada, ronda 2 aplicada pero SIN VERIFICAR.** Las correcciones
de la ronda 2 están en el commit **WIP `f284bcf` (marcado, local, sin push)** — hay que RE-VERIFICARLAS
con un pase adversarial fresco + Codex xhigh ANTES de darlas por buenas. Los reportes de corrección de esa
ronda están guardados en el scratchpad de la sesión:
`…/scratchpad/f1prep_ronda2_fixes.json` (por si el scratchpad no sobrevive, el resumen está abajo).

**Defectos que la ronda 2 dice haber cerrado (verificar cada uno EJECUTANDO):**
- **A-BLOQ** (lo reprodujo Codex con un proxy local): el SDK reintenta por dentro (`max_retries=2`) y solo
  expone el error final; se devolvía la reserva de intentos que SÍ salieron al proveedor. Arreglo: los
  reintentos los hace MIA (`max_retries=0` en el cliente), cada uno reservado por separado. **Verificar con
  un proxy propio que reciba N POST y luego rechace.**
- **A-MAY1**: `metrics/usage.py` (PRODUCCIÓN) no tarifaba el caché (escritura 2x fuera de `prompt_tokens`,
  lectura 0.1x dentro). Arreglo: mismo desglose de tres cubos que `spend_guard.real_call_cost`. **Verificar
  que una fila SIN caché registra idéntico a antes, y `enforce_budget` sigue fail-open.**
- **A-MAY2** (tmp + ledger): el gate creaba temporales dentro del repo (81/83) y un call-site
  (`test_eval_harness.py:431`) filtraba al libro REAL con sesión `inapp-<fecha>`. **Verificar 83/83 y que el
  hash de `mia-data/eval-runs/spend_ledger.json` no cambia al correr los gates.**
- **A-MEN**: los embeddings cobran toda falla de red (dirección segura); declarado.
- **A-ABIERTO**: limpieza del residuo pre-existente del libro real (sesiones `default`/`smoke-f05`) y dos
  artefactos gitignoreados en la raíz (`.tmp/`, `mia-spend-guard-f478svfq`). Cosmético, no bloquea.
- **C-MAY1**: la frecuencia de fuga de jurisdicción se medía sobre 1.200 de ~15.656 caracteres (el 8% del
  borrador) → leería "cero fuga" por construcción. Arreglo: medir sobre el texto COMPLETO en `run_case`.
  **Verificar con un borrador >15k con la fuga después del carácter 1200.**
- **C-MAY2**: la métrica estrella (falsos bloqueos / `precision_respaldo`) no estaba protegida — mutar el
  denominador dejaba la suite verde. Arreglo: asertos con valores conocidos. **Verificar mutando el
  denominador → la suite debe ponerse ROJA.**
- **C-MEN**: `precision_respaldo` podía imprimir negativo; se le puso clamp.

**Verificación interrumpida**: de los 3 verificadores de la ronda 2, solo volvió 1 (parcial,
`EVIDENCIA_INSUFICIENTE` — NO es un veredicto, la corrida se cortó). Re-verificar los tres desde cero.

El workflow de la ronda 2 fue detenido a propósito (no se puede reanudar cross-sesión). El script vive en
`…/workflows/scripts/mia-f1-prep-ronda2-wf_4e096384-1d0.js`; su fase «Corregir» YA corrió (no re-correrla:
duplicaría ediciones), solo hace falta rehacer la fase «Verificar».

## Decisiones de Pipe de esta sesión (no reabrir)

- **La calidad manda sobre el reloj** (2026-07-21): los 10 minutos dejan de ser puerta; la latencia se mide
  y reporta, ningún gate falla por tiempo. Lo absoluto sigue siendo: cero afirmaciones sin respaldo.
- **El modo PRINCIPAL del producto es la SUSCRIPCIÓN del abogado** (Claude Code/Codex/Antigravity), no la
  nube. El baseline de F1 debe aprobar bajo `suscripcion` (coste USD 0 → el benchmark principal es GRATIS,
  N=10 sin tocar el tope); la nube es referencia. Verificado en esta sesión que el CLI `claude -p` anidado
  responde, así que el benchmark del modo primario es viable desde aquí. Consecuencia ascendida a defecto:
  bajo `cli-*` el bucle de lectura agéntica NO corre → capacidad que le falta al modo de venta; arreglar o
  declarar. El "USD 0,31/turno" de F0.5 era SOLO el modo nube.

## Pendiente de Pipe

- Nada bloqueante. Cuando retome: aprobar (o no) que las corridas de REFERENCIA en nube usen el tope de
  USD 30, aunque probablemente ni haga falta porque el modo principal es gratis.

---

# CIERRE — 2026-07-21 · F0 COMPLETA · MIA corrió por primera vez contra un modelo real

Rama `feat/fase1-inc1-cleanup-scaffolding`. **Esta entrada sustituye a la anterior como punto de partida.**
Push de los 7 commits pendientes: **APROBADO POR PIPE Y HECHO** (`5163ba1..c19c680`). Los 15 anteriores los
había subido su propia cuenta (`jfelipetorresv`), no un tercero: pregunta cerrada.

**La fase siguiente es F1** (`specs/todo/01-f1-benchmark-vivo.md`). Antes de empezarla, leer la sección
«Deuda declarada que entra a F1» de abajo: no es opcional, son huecos de dinero conocidos.

## 0 · Lo que cambió de la promesa del producto (DECISIÓN DE PIPE, 2026-07-21)

> «no tienen que ser 10 minutos. puede ser más si el resultado es brutal y de calidad»

Los 10 minutos DEJAN DE SER UNA PUERTA. La latencia se mide y se reporta (p50/p95); ningún gate falla por
tiempo. El criterio de salida pasa a ser de CALIDAD: **cero afirmaciones sin respaldo** (esa mitad sigue
siendo absoluta) y un resultado que a Pipe le parezca valioso. Con presupuesto de tiempo, se puede gastar
más cómputo en calidad; el límite real pasa a ser el **coste por turno**, no el reloj. No se invierte al
revés: lentitud sin ganancia de calidad sigue siendo defecto.
Aplicado en `CLAUDE.md` §B, `TRASPASO-MODELO.md`, y la spec de F3 (renombrada a
`specs/todo/03-f3-recorrido-completo.md` para que el umbral no viva ni en el nombre del archivo).
**A una sesión futura: esto NO es un error que haya que restaurar.**

## 1 · F0.5 — la primera evidencia real (el número que no existía)

`run_eval.py --case caducidad-reparacion-directa --max-usd 5` con política `nube`, contra el modelo real:

| | |
|---|---|
| Resultado | llegó a borrador · 0 errores · `[ok]` |
| Coste del turno | **USD 0,3126** |
| Tokens | 37.341 en 6 llamadas |
| Duración | 353,6 s (350 s dentro del modelo) |
| Borrador | 15.656 caracteres |
| Citas | 0 (el guardián no tuvo nada que marcar) |

Corrida guardada en `mia-data/eval-runs/smoke_f05b_20260721/`. **El borrador de 15k caracteres con CERO
citas es material para la Sesión A**: que eso sea bueno o alarmante es juicio jurídico de Pipe, no de un
agente. Esto NO cierra el riesgo #76 (sigue abierto: es UN caso, N=1, sin holdout); cierra la parte de
plomería y da el primer coste real por turno.

## 2 · Los 3 commits

| Commit | Qué |
|---|---|
| `94aa68e` | **Docs honestos**: Modo A (Docker) desdeclarado — 0 Dockerfiles en el repo, verificado. Y tres docs que mandaban en dirección falsa: soul-onboarding decía «no implementado» de algo ya construido, e2e_runbook describía 19 preguntas/puerto 3000 (real: 7 pasos/3100), trampas-entorno-windows denunciaba una landmine de `setup_db.ps1` que `fdad1f1` ya había arreglado. #75/#79 cerrados; **#76 y #78 siguen abiertos a propósito** |
| `c7b991a` | **Organización**: el plan maestro pasa a ser 8 specs ejecutables en `specs/todo/` (rutas verificadas una por una), `APRENDIZAJES.md`, `.mcp.json` con Playwright, hooks damage-control de proyecto + la excepción en `.gitignore` que hacía falta para que se versionaran |
| `b05b58b` | **El guardián de gasto** (abajo) |

## 3 · El guardián de gasto — 4 rondas, y por qué costó tanto

El banco podía hacer llamadas reales **sin registrar un centavo y sin ningún tope**: nunca fijaba el scope
de uso, así que el registro de coste era un no-op. La infraestructura ya existía y estaba probada en
producción; faltaba que el banco la usara.

**MODO HERMÉTICO** (`SPEND_ROUTES` en `backend/mia/eval/spend_guard.py`): cada ruta capaz de gastar está
GOBERNADA, DESACTIVADA o DECLARADA, y si una entrada no se puede aplicar **la corrida no arranca**. Se llegó
ahí porque enumerar huecos uno por uno NO CONVERGÍA: tres rondas cerrando rutas (juez, Pinecone, NotebookLM,
MCP, subprocesos) y en cada una aparecía otra.

**La cota es CERO y está medida**: la reserva no estima, acota (1 token por CARÁCTER, salida tope 8192,
tarifa la más cara del catálogo) y se reserva por INTENTO cobrable, no por llamada. Medir modelo y
embeddings JUNTOS escondía el error — el modelo tapaba al embedding y daba verde con la cota rota.

**No puede mentir sobre sí mismo**: toda excepción del guardián deriva de `SpendGuardHalt(BaseException)`,
así que los `except Exception` del grafo no pueden tragársela, y una corrida frenada sale con código 2 o 3,
nunca 0. `guard_exception_audit()` delata cualquier excepción nueva que no derive de ahí. Este defecto
—corrida FRENADA reportándose como COMPLETA— apareció **dos veces por puertas distintas**; la segunda la
reprodujo Codex ejecutando, después de que un verificador Opus ya había aprobado.

Regresión propia detectada y cerrada: al fijar el scope, el gasto de pruebas empezó a consumir el
**presupuesto mensual del despacho** y podía bloquear el turno real de un abogado. El primer arreglo fue
incompleto (arreglamos la reserva, no el cálculo del mes). `enforce_budget` sigue fail-open a propósito.

73 checks nuevos, **todos vistos rojos por mutación** antes de darse por buenos.

## 4 · Verificación

**HALT**: `test_rls` 19/19 · `check_env_pins` 10/10 · `test_gates_no_ciegos` 9/9 (corridos por el
orquestador, no solo reportados).
**Suites**: `test_eval_spend_guard` 73/73 (nuevo) · `test_eval_harness` 57/57 · más las vecinas del área.
**Hooks**: bloquearon un `rm -rf` REAL durante la sesión, no simulado.
**OJO con el intérprete**: hay que usar `./.venv/Scripts/python.exe`. El `python` del PATH no tiene
psycopg y los tres gates HALT revientan con `ModuleNotFoundError`.

## 5 · EL ENTORNO SABOTEÓ LA SESIÓN (leer antes de diagnosticar cualquier cosa)

La primera corrida en vivo falló con `ALL_PROVIDERS_EXHAUSTED (network)`. Parecía un bug de MIA. **No lo
era**: había **2.512 procesos zombi de `statusline.js`** de Claude Code (de 2.566 node) ahogando Windows.
Mataban LiteLLM, la API, y las tareas de fondo del harness —que salían «killed» SIN UNA LÍNEA de salida,
lo cual despista muchísimo— y un `ls` tardaba dos minutos.

**Causa raíz encontrada y arreglada** (llevaba sesiones pendiente): `~/.claude/statusline.js` leía stdin con
`readFileSync(0)`, que es BLOQUEANTE; si el padre no cierra stdin el proceso cuelga para siempre, y con
`refreshInterval: 1` eso son ~3.600 colgados por hora. Arreglado con lectura asíncrona (800 ms) +
`process.exit` vigilante a 1,5 s. Respaldo en `statusline.js.bak-20260721`. De 2.566 node a 46, **cero
zombis**.
**Regla operativa: ante lentitud rara o tareas de fondo que mueren sin salida, contar `node.exe` ANTES de
sospechar del código propio.**

## 6 · Deuda declarada que entra a F1 (huecos de dinero conocidos, NO opcionales)

1. **La escritura de caché de prompt de 1 h se factura al DOBLE y no está tarifada.** El campo
   `cache_creation_input_tokens` viene en la respuesta real del proveedor (confirmado) y ni `spend_guard`
   ni `metrics/usage.py` lo contabilizan. Es el único motivo por el que Codex no certifica el tope de
   USD 30 en general (sí autorizó la corrida de USD 5). **Cerrar antes de las sesiones grandes de F1.**
2. **El registro hermético detecta rutas que CAMBIAN, no rutas NUEVAS** que alguien añada sin declarar. No
   hay bloqueo a nivel de socket.
3. **`api/routes/ux.py` (~L1729) suma el gasto del banco al panel de coste del abogado** como si fuera su
   gasto real del mes. Honestidad de producto, no solo contabilidad.
4. **Las llamadas que fallan por RED se cobran por lo estimado**: la corrida fallida cobró USD 0,5785 sin
   gastar nada real — más que la corrida exitosa (USD 0,31). Fail-safe, pero quema presupuesto de sesión
   por nada. Distinguir «no conectó» (devolver) de «final incierto» (cobrar).
5. **LiteLLM no sobrevive** a que su tarea contenedora del harness sea detenida. Arrancarlo de forma
   durable ANTES de las corridas largas de F1, o se pierden a mitad.
6. **Higiene de pruebas**: dos suites filtraron gasto al libro de saldos REAL (`inapp-20260721`,
   `sonda-mundo-20260721`, USD 0,0022) en vez de usar uno desechable, y otras dejan directorios
   temporales en la raíz del repo (ya ignorados, pero el defecto sigue).

## 7 · Método — lo que rindió y lo que no

**Rindió**: la prueba de mutación como requisito innegociable (ningún check nació verde); exigir al
verificador que EJECUTE sondas propias DISTINTAS con derecho a decir «evidencia insuficiente»; el cruce de
proveedor (Claude implementa, GPT refuta) exactamente donde el plan lo predijo; commitear lo aprobado sin
esperar al frente en disputa; y sobre todo **preguntarle al verificador algo práctico** («¿autorizarías
gastar USD 5 sabiendo que el dinero es de una persona?») en vez de un APROBADO/RECHAZADO abstracto — eso
produjo veredictos mucho mejores.

**No rindió**: enumerar huecos uno por uno (hubo que cambiar a cerrar el mundo). Y **un solo verificador no
basta en el frente crítico**: Opus aprobó un estado en el que Codex después reprodujo un exit code 0.
**Sobre Codex**: exagera en lo cuantitativo (dio USD 238, USD 89 e «infinito»; el número real medido fue
menos de USD 1, y al final 0) pero acertó en CADA defecto estructural. Al arbitrar: descontar sus cifras,
tomarse en serio sus mecanismos.

Retrospectiva completa en el vault:
`01-operacion\retrospectivas\retrospective-2026-07-21-004-f0-preflight-cierre.md`.
Reglas aplicadas en `APRENDIZAJES.md` (33-43).

---

