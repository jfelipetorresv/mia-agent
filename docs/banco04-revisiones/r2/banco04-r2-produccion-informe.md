# Banco 0.4 · ronda 2 de Astra · frente PRODUCCIÓN (área B): informe

Repo `D:\Inteligencia Artificial\Mia-Super Agent\mia`, rama `feat/mia-04-hermes-legal`, HEAD 3611b75. Sin git (solo `git status/log/diff` de lectura al orientarme), sin DB, sin proveedores reales (solo `claude --version` y `claude --help`), sin custodia real, `mia-data` ni `.env`.

Archivos tocados (los cuatro del frente, nada más):
- `backend/mia/eval/spend_guard.py`
- `execution/run_banco04.py`
- `execution/test_banco04_produccion.py`
- `execution/test_eval_spend_guard.py` (solo el bloque de a-25)

Conservan sus finales de línea: CRLF en tres de ellos; `test_eval_spend_guard.py` ya los tenía mezclados (CRLF y LF) y sigue igual. Respaldo del estado previo: `scratchpad/r2prod/orig/`; estado final: `scratchpad/r2prod/post/` (el test de producción cambió después: 2 checks más, ver I10).

## Conteos finales (corridos al terminar)

| Suite | Resultado |
|---|---|
| `execution/test_banco04_produccion.py` | **238/238 OK** (antes 220/220) |
| `execution/test_eval_spend_guard.py` | **83/83 PASS** (antes 82/83: a-25 rojo) |
| `execution/test_gates_no_ciegos.py` (HALT del proyecto) | **9/9 PASS** |
| `execution/test_banco04_juicio.py` (frente ajeno) | **Inestable por obra del otro agente; ningún FAIL es mío.** Tres corridas, cada una con un FAIL distinto y un total distinto: 382/383 con FAIL R2-C-N1 (acreditación, área C); 370/371 con FAIL `gate_i9` FileExistsError; y la **A/B con mi `run_banco04` ORIGINAL** (cargado por `wrapper_rb.py`, repo intacto) 381/383 con FAIL R2-C-N3 ×2 (hash del validador). Ninguno de esos FAIL toca `run_banco04` ni `spend_guard`, y los checks I5/R2-B-I4 del juicio pasan en todas las corridas. |

Durante la sesión, la suite de juicio estuvo rota a ratos por obra del otro agente: abortaba en I9 con «LOCALAPPDATA no está definida». Para aislar mi cambio a `motivo_juicio` la corrí dos veces seguidas, con el cambio y sin él (A/B). El conjunto de FAIL fue idéntico en ambas corridas, y los checks `I5 …` de juicio pasaron.

---

## I4 · PARCIAL → RESUELTA por la vía (b): cota DESCONOCIDA para todo CLI

**Decisión: (b).** La vía (a) no se puede acreditar, por cinco razones con evidencia:

1. `claude --version` = **2.1.296**. `claude --help` **no lista `--max-turns`**, así que el supuesto de «un solo turno» no está documentado en el CLI instalado.
2. code.claude.com/docs/en/errors, sección «Tune retry behavior»:
   - el CLI reintenta hasta `CLAUDE_CODE_MAX_RETRIES` (10 por defecto);
   - `CLAUDE_CODE_RETRY_WATCHDOG` lo sube a 300;
   - un fallo de streaming se **reenvía sin streaming** (fallback activo por defecto);
   - los reenvíos por timeout (`CLAUDE_CODE_NONSTREAMING_TIMEOUT_RETRIES`) **no tienen default numérico documentado**.
3. code.claude.com/docs/en/costs, sección «Background token usage»: el CLI hace peticiones de fondo además del turno.
4. `agent/subscription_llm._sanitized_env` (`subscription_llm.py:133-145`) quita toda variable cuyo nombre contenga `TOKEN`. Por eso `CLAUDE_CODE_MAX_OUTPUT_TOKENS` no puede llegar al CLI sin tocar `agent/*`.
5. Fijar `CLAUDE_CODE_MAX_RETRIES=0` desde el banco cambiaría la conducta del producto que se mide: más fallos, otra cifra de `turnos_completados`.

Una invocación del CLI equivale, entonces, a un número **no acreditado** de peticiones a la API. La fórmula (reintentos+1)×(entrada+salida) no se puede calcular.

**Corrección (`spend_guard.py:1079-1121`):**
- `CLI_SALIDA_MAXIMA` (los 131 072 tokens) se sustituye por `CLI_COTA_ACREDITADA`, que registra versión, evidencia y `claude: None` / `codex: None`.
- `cota_salida_cli(alias)` conserva su firma `(máximo|None, motivo)`, pero **cambió su semántica**: devuelve `(None, motivo R2-B-I4)` para **todo** `cli-*`. Se retiró el nombre público `CLI_SALIDA_MAXIMA`.
- **Cambio de contrato para el otro agente:** `jueces.cota_salida_juez` (`jueces.py:1340-1353`) consume `cota_salida_cli`. Grep hecho al cierre: maneja bien el `None`, que es exactamente lo que hace ahora. Consecuencia: la cota del juez Claude pasa a ser DESCONOCIDA, su reserva cae a `estimacion_reserva`, y un timeout de juez Claude deja el contador no calculable. Ningún otro consumidor usa `CLI_SALIDA_MAXIMA`. Su check `R2-B-I4 · Claude: …` (`test_banco04_juicio.py:1949-1957`) dobla la función y sigue verde.
- `_guarded_invoke` (`:1225`) registra entonces `cota_salida=None` y `tokens_cota_superior=None`; con eso el techo queda no certificable (P10).
- La API de otros alias no cambia: `max_tokens` aplicado sigue dando cota (i-2).

**Checks** (`test_banco04_produccion.py`, `bloque_i`):

| Check | Línea | Qué cambió |
|---|---|---|
| i-1 | :2035 | Invertido: Opus por CLI de un turno → sin cota, con motivo |
| i-1b | :2043 | Codex sin cota |
| i-1c | :2046 | Acreditación versionada, sin tabla de máximos |
| **R2-B-I4 · ningún alias CLI de MIA … declara cota** | :2068 | Nuevo. Recorre 6 alias CLI (las 4 claves de `_CLI_MODEL_HINTS` más `cli-codex` y `cli-codex-eval`) con `MIA_CLI_MODEL` = opus/sonnet/haiku, por el `_guarded_invoke` real. Es el check que se pone rojo si alguien vuelve a declarar cota |
| i-2 | (sin cambio) | API acotada, sentido bueno |
| i-3 | :2082 | Ambos sentidos: CLI no certificable, API certificable |

Se retiraron i-1d e i-1e: probaban la lógica de «un turno» de la tabla, que ya no existe.

**Mutaciones:**

| Mutación | Resultado |
|---|---|
| I4a: `cli-claude*` devuelve 131 072 | ROJO (i-1, R2-B-I4, i-3) |
| I4b: solo `cli-claude` (modelo por defecto) devuelve 131 072 | ROJO (R2-B-I4; i-1 no lo ve, por eso existe el check nuevo) |
| I4c: Codex devuelve 64 000 | ROJO (i-1b, R2-B-I4) |

**Consecuencia que el director tiene que ver: decisión de Pipe.** Con (b) más I5:
- **un solo timeout de CLI** en producción o en un juez deja el contador no calculable;
- desde ese momento, **no se lanza ningún juez más**;
- en modo suscripción los timeouts de Opus xhigh/max en voluminosos son recurrentes según la memoria del proyecto.

En la práctica, **el banco difícilmente llegará a juzgarse completo**. Lo que dice el protocolo (P10: «no certificable») queda cumplido. El coste es que se pierde la medición de calidad del resto. Ver C19.

**Riesgo residual que no corregí (frente producto):** en las llamadas CLI **exitosas**, `subscription_llm._to_openai_response` lee solo `usage` del JSON del CLI. No lee `modelUsage` ni las peticiones de fondo o los reintentos internos. El consumo «conocido» de una llamada exitosa puede subestimar, y corregirlo exige tocar `agent/*`.

**C18 propuesta (texto exacto):**
> **C18 (cota de los intentos por CLI).** El máximo de salida que la API documenta para un modelo no acredita la cota de una ejecución del CLI de suscripción. Una invocación del CLI puede emitir varias peticiones a la API (reintentos internos, reenvío sin streaming, peticiones de fondo) que el banco no puede fijar sin cambiar el producto. Por eso todo intento fallido bajo un alias `cli-*` (Claude o Codex) se registra con `consumo_conocido = false` y **sin cota**, y el techo de §3.4 y §6.3 queda no certificable (P10). Declarar una cota para un CLI exige acreditar dos cosas, leídas del comando y del entorno reales con que el banco lo invoca y de la documentación oficial de la versión instalada: el número máximo de peticiones a la API por invocación y la salida máxima por petición. La cota es entonces peticiones × (entrada estimada + salida máxima). Sin esa acreditación no hay cota.

## I5 · PARCIAL → RESUELTA (con la consecuencia de arriba)

### 1. `motivo_juicio` con consumo desconocido (`run_banco04.py:391-402`)
Si `cota_calculable` es False, devuelve un motivo y no se lanza otro intento. La API no cambia.

El agente de juicio añadió su propio control equivalente en `ControlCuotaJueces.antes` (`jueces.py:1438`). Ambos son coherentes.

- **Check** `R2-B-I5 · motivo_juicio NIEGA …` (:2333). Cubre los dos proveedores. Por el ledger: tras un timeout, `iniciar` lanza `PresupuestoAgotado` sin dejar rastro; tras un cierre conocido, sí lanza.
- **Mutación I5a** (quitar el bloque): ROJO.

### 2. Cero llamadas Codex de producción en el Bloque 0
El control por corrida no puede dar cero: 0+0>0 es falso. Hice un control **por llamada** en `GuardBanco.check_and_reserve` (`run_banco04.py:1563-1600`):
- `_guarded_invoke` lo invoca **antes** de `_original_invoke`, también para los alias gratuitos.
- Para `cli-codex*` consulta `ContadorCuota.motivo_llamada_codex` (`:436-452`). El presupuesto es techo − reserva: 0 en el Bloque 0 y 2 M en el Bloque 7. El consumo usado incluye la base del contador y el Codex en vuelo de este proceso.
- Si no hay presupuesto, levanta `ParadaCodexProduccion`, una subclase de `SpendLimitExceeded`, es decir `BaseException`: ningún `except Exception` del grafo puede tragársela.
- El guardián queda parado (sticky).
- El montaje lo conecta en `guard.vincular_contador(contador)` (`:1751`).
- La parada lleva `motivo_banco`. `_ejecutar_una` y las aprobaciones la guardan como `motivo_parada` (texto fijo), y `paso` suspende con ese motivo (`:1084`) y no con «límites de uso».

Verificado por grep: a HEAD, toda llamada Codex de producción pasa por `llm._invoke`. En `quality_adaptive`, de hecho, ninguna cadena incluye `cli-codex`: la revisión 5C todavía no está cableada en el grafo. `settings.py` y `welcome.py` solo usan `detect_status`.

| Check | Línea | Mutación | Resultado |
|---|---|---|---|
| `R2-B-I5 · Bloque 0 …` (constantes reales de `protocolo.py`): 0 invocaciones y 0 tokens en el Bloque 0; en el Bloque 7 la llamada sí ocurre | :2385 | I5b: anular el override | ROJO (3 checks) |
| | | I5c: quitar solo `tope <= 0` | **SOBREVIVE, equivalente**: la rama `usado >= tope` (0 ≥ 0) cubre lo mismo |
| | | I5c2: quitar las dos ramas | ROJO |
| `R2-B-I5 · con presupuesto Codex 100 …`: 2 llamadas, la 3.ª se para | :2394 | I5d: no contar el Codex en vuelo | ROJO |
| `R2-B-I5 · de punta a punta (Bloque 0)`: suspende con 0 llamadas Codex y `SUSPENDIDO.json` dice «Codex» | :2421 | I5e: ignorar `motivo_parada` | ROJO |

### 3. Decisión de R con Codex (`decidir_r`, `:515-563`; llamada en `ejecutar_banco`, `:1106-1125`)
- Proyecta Codex (piloto × R + Codex estimado de las aprobaciones = Σ piloto) contra su presupuesto.
- Registra `proveedor_disparador` y la cifra.
- c-38 se amplió **solo** con nombres de consumo Codex.

| Check | Línea | Mutación | Resultado |
|---|---|---|---|
| `R2-B-I5 · decidir_r proyecta Codex …`: R plena, reducida y suspender, y Bloque 0 con Codex 0 | :2442 | I5f: ignorar Codex en `_excede` | ROJO |
| `R2-B-I5 · de punta a punta: Claude cabe pero la proyección Codex …` | :2475 | I5g: no pasar Codex | ROJO |

### 4. Piloto con estimación previa
- `Contexto.estimacion_piloto` (`:624`) y `EST_PILOTO_TOKENS = {pequeño 48 000, fuga 48 000, voluminoso 177 000}` (`:1651-1655`), tomados de la prosa de §3.2. `protocolo.py` es frente ajeno: conviene mover ahí la constante.
- En los dobles, el valor por defecto es `{}`, para no cambiar los checks viejos.
- Codex a priori es 0, porque §3.2 no da base por corrida. Lo gobierna el control por llamada.

| Check | Línea | Mutación | Resultado |
|---|---|---|---|
| `R2-B-I5 · la piloto usa la estimación A PRIORI …` | :2491 | I5h: volver a 0 | ROJO |
| (inspección del código de `_montaje_real`) | | I5j: quitar `vincular_contador` del montaje | ROJO |

### 5. Aprobaciones (`ejecutar_aprobaciones`, `:1470-1480`)
- La proyección suma el turno **reproducido** (Claude y Codex de la corrida elegida) a la estimación de aprobar.
- Codex se mira contra su presupuesto.

| Check | Línea | Mutación | Resultado |
|---|---|---|---|
| `R2-B-I5 · cada aprobación se proyecta …` | :2533 | I5i: volver a `proximo_estimado=por_aprobacion` | ROJO |

**Ajuste de un check viejo:** h-24 (:1928). Su techo pasó de 700 a 800 porque la proyección ahora es más conservadora (600 + 100 + 100). El check sigue probando que corre exactamente una aprobación.

**Lo que NO hice en I5:**
- **`motivo_suspension` (producción Claude) no se detiene ante consumo desconocido.** El encargo lo pedía solo para el juicio. Detener la producción con el primer timeout de CLI pararía el banco entero. El techo ya queda no certificable. Hay una consecuencia que el director tiene que pesar: un intento fallido sin cota suma **0** al acumulado. Desde ese momento, el control del techo duro Claude (18 M en el Bloque 0, 32 M en el Bloque 7) trabaja sobre una cota **inferior** y el techo podría rebasarse sin detectarse. Decisión pendiente; ver C19.
- No toqué `banco04_validar_jueces.py:414` (`versiones=()`, custodia opcional) ni `circuito_utilizable` sin condición de certificabilidad. Son frente ajeno. Ver «Defectos del frente ajeno».

**C19 propuesta:**
> **C19 (consumo desconocido durante el circuito).** Con un intento de consumo desconocido y sin cota, el acumulado es solo una cota inferior. No se lanza ningún intento más de juez ni ninguna llamada Codex de producción. La producción Claude puede seguir, pero el techo queda no certificable. Continuar el juicio exige una nueva aprobación expresa de Pipe, registrada igual que la reanudación de §3.4. Las métricas de calidad que se obtengan se publican; la fila del techo queda «no certificable».

Nota: el mecanismo de reanudación del juicio con aprobación de Pipe **no existe hoy**. Lo propongo, no lo implementé.

**C20 propuesta:**
> **C20 (piloto y Codex en el Bloque 0).** Cada corrida de la tanda piloto se controla antes de lanzarse con la base de §3.2 de su clase: 48 000 tokens si es pequeña, 177 000 si es voluminosa. En el Bloque 0 el presupuesto Codex de producción es cero: el banco impide antes de enviarla cualquier llamada Codex de producción y suspende con ese motivo.

## I8 · PARCIAL → RESUELTA

`error_persistible` (`run_banco04.py:824-850`):
- En un caso **custodiado**, el texto de la excepción se cifra con la llave de la custodia. El id es **propio**: `<versión>/<caso>/<rep>/<etapa>-intento-<n>/error`, distinto del id del resultado, así que los dos blobs no son intercambiables.
- El cifrado va a `rep-NN.<etapa>-intento-N.error.enc`.
- En claro quedan solo `error_tipo`, `error_status`, `clase`, `estado` y la ficha con su hash.
- Un caso visible sigue en claro.

Se usa en producción (`:1011-1013`) y en aprobaciones (`:1407-1409`). Además:
- Las aprobaciones de un custodiado sin cifrador **no corren** (`:1342`); antes sí corrían.
- El `AVISO` de stderr imprime solo el tipo cuando el caso es custodiado (`:1386`).

| Check | Línea | Mutación | Resultado |
|---|---|---|---|
| `R2-B-I8 · una excepción de un caso CUSTODIADO …`: centinela con hecho del caso en ningún archivo de salida o custodia; descifra con su id; el id del resultado no lo descifra; un caso visible queda en claro | :2568 | I8a: siempre en claro | ROJO (3 checks) |
| `R2-B-I8 · un «usage limit» … SIGUE suspendiendo` | :2581 | | |
| `R2-B-I8 · aprobaciones: …` | :2615 | I8b: quitar el fail-closed sin cifrador | ROJO |
| | | I8c: error de aprobación en claro | ROJO |

**Ajuste de un check viejo:** h-25 (:1984) ahora pasa el cifrador, que es lo exigido.

## I10 · PARCIAL → RESUELTA

**Correcciones:**
- Todo registro reutilizable lleva `manifiesto_sha256`: marcador `.en_curso`, intento, huérfano (hereda la huella del marcador), `aprobacion.json`, `aprob.intento-*`, marcador de aprobación, `decision_r.json`, `aprobaciones_plan.json`, `estado_banco.json` y `aprobaciones_estado.json`.
- El cotejo ocurre en dos capas:
  - **Al arrancar:** `PATRONES_REUTILIZABLES` (`:765-794`), 8 patrones.
  - **Por registro, antes de reutilizar:**
    - intentos parciales: `:978`;
    - aprobación terminal (el `:1150` de Astra): `:1337`;
    - intentos de aprobación: `:1349`;
    - `decision_r`: `:1108`;
    - plan de aprobaciones: `:1465`.
- Rechazar significa abortar (`BancoAbortado`). El consumo de otro manifiesto **no se salta** al cargar el contador: se gastó y cuenta.
- **Fuera de I10:** el **ledger del juicio**. Es consumo, no resultado reutilizable, y su API es del otro agente.

| Check | Línea | Mutación | Resultado |
|---|---|---|---|
| `R2-B-I10 · una APROBACIÓN terminal con la huella antigua bajo un contexto NUEVO se RECHAZA …` (el pedido) | :2643 | I10a | ROJO |
| `R2-B-I10 · un INTENTO parcial con otra huella …` | :2664 | I10b | ROJO |
| `R2-B-I10 · un intento parcial de APROBACIÓN …` | :2686 | I10f | ROJO tras añadir el check; en la primera pasada **sobrevivió** porque lo tapaba el escaneo de arranque |
| `R2-B-I10 · una decision_r.json de OTRA ejecución …` | :2701 | I10g | ROJO; misma historia que I10f |
| `R2-B-I10 · al arrancar … los 8 tipos` | :2725 | I10c (quitar `aprobacion.json`) | ROJO |
| | | I10d (quitar `decision_r.json`) | ROJO |
| `R2-B-I10 · el marcador .en_curso y el huérfano llevan la huella` | :2736 | I10e (marcador sin huella) | ROJO por excepción: la suite revienta con el `BancoAbortado` esperado («None ≠ …») |

**Ajustes:**
- Helper de test `_ctx`: ahora usa por defecto un manifiesto **limpio** de prueba, `MANIFIESTO_PRUEBA` (:554). Sin manifiesto el banco ya no termina «terminado» (ver N2).
- d-6: su marcador lleva la huella, como lo escribe el runner.

## N2 · MAYOR → RESUELTA

**Estado final:**
- `motivos_identidad` (`:746-755`) entra en los motivos de `estado_banco.json` (`:1148`) y de `aprobaciones_estado.json`.
- Árbol sucio da «no certificable» con el motivo y la huella.
- **Sin manifiesto, también** «no certificable». Es un endurecimiento propio: sin identidad acreditada no se certifica.

**Identidad:**
- `info_arbol_git` (`:680-727`) añade `modificaciones_sha256`: sha256 de `git diff HEAD --binary` más ruta y `git hash-object` (sin `-w`) de cada no rastreado no ignorado. Los ignorados (`.env`, `mia-data`) no se leen.
- `construir_manifiesto` (`:730-743`) incluye la huella y **rechaza un árbol sucio sin huella**.
- El montaje la pasa (`:1739`).

| Check | Línea | Mutación | Resultado |
|---|---|---|---|
| `R2-B-N2 · un árbol SUCIO … termina «no certificable» …` (producción y aprobaciones; limpio sigue «terminado»; sin manifiesto, no certificable) | :2754 | N2a (producción) | ROJO |
| | | N2b (aprobaciones) | ROJO |
| `R2-B-N2 · la identidad distingue las modificaciones locales …` | :2806 | N2c (no hashear el diff) | ROJO |
| | | N2d (no hashear el contenido de no rastreados) | ROJO |
| | | N2e (sucio sin huella aceptado) | ROJO |
| | | N2f (montaje sin huella) | ROJO |

Se adaptó i-23 a la forma nueva (:2279).

## a-25 (`test_eval_spend_guard.py`) · RESUELTO, 83/83

**Contrato confirmado en `agent/llm.py:189-211`:**
- `quality_adaptive.curator = [cli-claude-sonnet, mia-local]`.
- `suscripcion` no cae a API facturada.
- `nube` empieza ya pagado.

Ninguna política estándar tiene hoy un salto gratis→pagado, así que la expectativa del gate era obsoleta.

**Alineación** (bloque de :383-413):
- Se conserva lo que protegía: la reserva por intento con el alias que cobra.
- Para eso se inyecta una tarea no estándar `[cli-claude-sonnet, claude-sonnet]` en `_TASK_FALLBACK_CHAINS`, que es el gancho documentado en `_active_chains`, y se restaura en un `finally`.
- El contrato de `curator` queda como condición del check.

**Mutaciones:**

| Mutación | Resultado |
|---|---|
| a25: la documentada, envolver `call_llm` en vez de `_invoke` | ROJO |
| a25b: reservar con el precio del alias gratis | ROJO |

## Resumen de mutaciones

- **32 mutaciones distintas, 34 corridas:** las 32 en la primera pasada, más I10f e I10g otra vez tras su check nuevo.
- **31 ROJO** en su estado final. Una de ellas, I10e, por excepción.
- **1 sobrevive, equivalente:** I5c, cubierta por `usado >= tope`; quitando las dos ramas (I5c2) sale ROJO.
- I10f e I10g sobrevivieron en la primera pasada; se cerraron con checks nuevos.

**Método:** script `scratchpad/r2prod/mut.py`, resultados en `mut_resultados.jsonl`.
- Las mutaciones de `run_banco04.py` se corrieron sobre una **copia temporal** cargada por `wrapper_rb.py`, sin tocar el archivo del repo, para que el otro agente nunca importara una versión mutada.
- Las de `spend_guard.py` (5) fueron en el sitio, con restauración por bytes y sha256 verificado. Hashes finales iguales a `post/`.

## Defectos observados en el FRENTE AJENO (no tocados)

- **N1 (área B):** `jueces.py:1333`, telemetría parcial tomada como consumo conocido. No lo toqué. El código cambió durante la sesión (otro agente).
- `jueces.py:1321`: la cota genérica de `cota_intento` contradice C18 si se aplica a un juez por CLI. Ya la están reescribiendo (`cota_intento(prompt, proveedor, cota_salida)`).
- `banco04_validar_jueces.py:414`: `LedgerJuicio(..., versiones=())` y custodia opcional. En el Bloque 7 no suma 0.4 y 0.3.3 contra un solo techo. Además, `circuito_utilizable` (`:464`) no depende de `cota_calculable`.
- La suite de juicio termina con un FAIL propio (R2-C-N1, 9/11).

## Lo que NO hice, dicho con todas sus letras

1. **No acredité cota para ningún CLI**: elegí (b). En consecuencia, en modo suscripción **cualquier** fallo de CLI deja el techo no certificable y **bloquea el resto del juicio**. Es decisión de Pipe si eso es aceptable o si se aprueba C19.
2. No implementé la reanudación del juicio con aprobación de Pipe (C19).
3. La producción Claude no se detiene ante consumo desconocido. Desde ese momento el techo duro Claude se controla sobre una cota inferior y podría rebasarse sin detectarse.
4. No corregí la posible subestimación del consumo de llamadas CLI **exitosas** (`modelUsage` y reintentos internos), que está en `agent/subscription_llm.py`, fuera del banco.
5. `EST_PILOTO_TOKENS` y `APROBACIONES_EST_TOKENS` siguen en el runner y no en `protocolo.py` (frente ajeno).
6. No toqué el protocolo `.md`, ni HANDOFF, APRENDIZAJES ni memory. C18, C19 y C20 quedan como propuestas.
7. No ejecuté `_montaje_real` (requiere DB y CLI). El cableado del montaje se verifica solo por inspección del código fuente en los checks. Es un check débil y está declarado.
8. La revisión 5C (Codex en producción) no está cableada a HEAD. El control por llamada queda probado con dobles por el `_guarded_invoke` real; no con el grafo.
