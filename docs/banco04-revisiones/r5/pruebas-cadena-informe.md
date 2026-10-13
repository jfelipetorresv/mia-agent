# Pruebas de la cadena del banco 0.4: informe del autor independiente

Contrato: `docs/banco04-cadena-contrato.md` (banco04-cadena/v5, APTO de Astra). Protocolo: banco04-v1.3.
Rama `feat/mia-04-hermes-legal`, HEAD `6c26afc`. No se editó ningún archivo existente, no se usó git
salvo lecturas (`rev-parse`, `diff --name-only`), no se leyó la custodia real, el registro de uso,
`mia-data`, `.env` ni cifrados, y no se llamó a ningún proveedor.

## 1. Qué se entregó

| Archivo | Qué es |
|---|---|
| `execution/test_banco04_cadena.py` | La suite (estilo de `test_banco04_juicio.py`: `check`, «N/M PASS», exit 1 si algo falla). `--solo E2E-3,S` corre por tramos (nombre exacto, o prefijo con `*`). |
| `execution/fixtures_banco04_cadena/entorno.py` | Proceso hermético: `MIA_TEST_ENV_FILE` sintético (55448), `.env` del repo neutralizado, CLI sin sesión, claves vacías, `LITELLM_BASE_URL` a un puerto cerrado, `LOCALAPPDATA` y `MIA_BANCO04_CUSTODIA` temporales; precondición del clúster aislado. |
| `.../firmas.py` | Firma normalizada de comandos (§4.4) e instantáneas de acreditación de prueba. |
| `.../custodia_falsa.py` | Custodia de prueba (DPAPI real del usuario, AES-GCM, manifiesto propio): V1-V4, claves de los 17 casos, semilla, ajuste y reservado de prueba (34 defectos, 12 C12, 35 controles, las 4 clases v1.3), acreditación v1.3. |
| `.../dobles.py` | Dobles del CLI de Claude y de Codex, embeddings, cadena de política, jueces (interfaz `Runner`) y `mundo`. No importa `telemetria`. |
| `.../escenario.py` | Recorrido de las etapas desde sus `main` y lectura de disco. |
| `.../autocontrol.py` | Valida los fixtures contra el código determinista que ya existe. |
| `.../proceso_paralelo.py` | Proceso hijo con barreras para E2E-13 y E2E-15. |
| `.../evidencia/*` | Las dos evidencias estáticas que citan las instantáneas de prueba. |

## 2. Resultado de hoy

**`RESULTADO: 24/154 PASS`**, medido el 2026-10-12 en una corrida completa en primer plano: 419 s,
0 tracebacks, exit 1.

**El denominador va a crecer.** Hoy, cuando un escenario falla al montarse, su bloque colapsa en un
solo FAIL con el motivo. Pasa en E2E-10, 11, 13, 14 y 17, y cada S, I y R13 cae por «F17 no
disponible». Cuando la cadena exista, cada bloque emitirá todos sus checks y el total subirá
bastante. 154 no es el tamaño de la barrera.

**Perímetro verificado.** Después de la corrida, `git status --porcelain` muestra solo
`?? execution/fixtures_banco04_cadena/` y `?? execution/test_banco04_cadena.py`, y `git diff --stat`
está vacío: no hay ningún archivo rastreado modificado. `backend/mia/eval/banco04/telemetria_acreditada/`
no existe, así que la suite no escribió nada bajo `backend/`.

Los 130 rojos lo son porque la cadena no existe: módulos
ausentes (`telemetria`, `registros`, `reproduccion`, `puerta`, `banco04_juzgar`, `banco04_decidir`,
`banco04_medir_codex`), directorio `telemetria_acreditada/` ausente, `main` sin `proveedores=`/`mundo=`/
`runners=` (fallan con `TypeError` antes de ejecutar nada), funciones de `metricas.py` que el contrato
elimina, o el clúster 55448 no disponible.

**Los 24 verdes, uno por uno, y por qué son legítimos:**

- **0.1-0.18, autocontrol (18).** No prueban la cadena: prueban que los fixtures son válidos para los
  validadores que ya existen (custodia real con DPAPI, `validar_pasada1`, `validar_pasada2`, tercer
  voto, `validar_conjunto`, `verificar_acreditacion`, `evaluar_exigencias`, `call_llm` real con los
  dobles). Sin ellos, el requisito «F17 da `aprueba`» podría ser inalcanzable por culpa del fixture y
  no de la implementación. Ninguno toca una pieza nueva.
- **A5 (1).** `metrics.usage._node` existe y es una `ContextVar`. El contrato (§4.2) pide una prueba
  que fije ese nombre y se ponga roja si cambia: hoy la propiedad se cumple.
- **V4, V5, V6, V8, V9 en la capa de la señal vendorizada (5).** La heurística actual ya resuelve
  esos cinco textos como pide §3.6. Son guardas de regresión: la regla nueva no puede romperlos. Los
  mismos nueve casos de punta a punta (mundo → juzgar → puerta) están en rojo. V1, V2, V3 y V7 en la
  capa de la señal están en rojo: son el defecto que §3.6 manda corregir.

No hay ningún otro verde. Toda aserción negativa o de igualdad va unida a una señal positiva de
alcanzabilidad: salida no vacía, fila que existe, `F17 aprueba` o un código presente. Así ninguna puede
quedar verde en vacío. Ejemplos: «sin puerta trasera» exige que `banco04_decidir.py --help` liste sus
tres subcomandos; «ninguna función nueva recibe conclusiones» exige además que exista
`falsos_bloqueos_corrida`; E2E-6.1 exige el `git diff` vacío **y** el R1 con su lista de rutas.
E2E-6.4 está en rojo hoy solo porque `test_rls` necesita el clúster. `test_gates_no_ciegos` y
`test_eval_spend_guard` corren dentro de la suite y salen verdes, y el meta-gate revisa este archivo
nuevo sin objeción.

## 3. Sección del contrato → pruebas que la cubren

| Sección | Pruebas |
|---|---|
| IC-1 (un `main` por etapa) | A1, E2E-1, E2E-1m (todos los pasos desde `main`); `juzgar` sin R8 se niega |
| IC-2 (crudo frente a derivado) | E2E-2, INV; E2E-1m (todas las filas `origen: captura`) |
| IC-3 (ausencia ⇒ `no_certificable`) | E2E-3, §4.4-1/4/6, S09, S22, S23, I06 |
| IC-4 (una sola fuente de consumo) | E2E-3, S08, S09, S10, E2E-12, R13 |
| IC-5 (identidad) | I04, I05, I14, E2E-17 |
| IC-6 (reproducción) | E2E-5, I10, I11, S01-S04, S17, S18 |
| IC-7 (dobles) | E2E-7, E2E-1m (`corridas_con_dobles` sin `_prueba`) |
| §1.2 módulos y huella | A1, A7 |
| R1 | E2E-1m (campos nuevos), E2E-6.1, E2E-8, E2E-9, E2E-16 |
| R2 | E2E-1m (`caso_digest`, `prompt_version_hash`, `jurisdicciones_fijadas`, `intentos[].llamadas`), I01, I08, I11 |
| R3 | F17 (crudos de V1-V4 cifrados en `<custodia>/salidas`, marca sintética ausente del árbol S) |
| R4 | E2E-1m, E2E-3, E2E-15, E2E-16, I02, I03, I06 |
| R5 | E2E-1m, E2E-5, §4.4-2/3 (todas las líneas JSONL), I05, I10, I13 |
| R6 | E2E-3, E2E-4, E2E-14 |
| R7 | EXT, I12 |
| R8 | E2E-1m, E2E-11, E2E-17 |
| R9 | F17, E2E-4 (reanudación de VJ), E2E-10, E2E-17, S12, S13 |
| R10 | E2E-1, S20, INV |
| R11 y R12 | E2E-1, I07, S19, S21 |
| R13 | E2E-8, E2E-9, E2E-12, bloque R13 (10 + 1.000 ⇒ 1.263; 1→2, 4→5, 5→7, 0→0) |
| R14 | E2E-12 (directorio propio, sin `resultado`, recibos, k preregistrado, variantes) |
| §3.1 firma de la puerta | A2, E2E-7 |
| §3.2 procedimiento | F17, E2E-1m, todas las I |
| §3.3 A identidad y completitud | I01-I11, I14, E2E-9, E2E-18, S19, S21 |
| §3.3 B absolutos | S01-S07, S12-S18 |
| §3.3 C comparativas y K1 | S11, S21-S23, EXT |
| §3.3 D techo y C25 | S08, S09, S10, S20, E2E-8 |
| §3.3 E alcance, fuga, estabilidad y circuito | S05-S07, S15, I13, E2E-14 |
| §3.4 extensión | EXT (positivo), I12, `extension_incompleta`, `extension_sin_causa` |
| §3.5 Bloque 0 | E2E-11 |
| §3.6 negación vinculada (V1-V9) | bloque V (señal y de punta a punta), S15 |
| §3.7 submuestras | EXT (las originales no cambian), I13 |
| §3.8 vocabulario cerrado | `vocab_ok` en cada veredicto que se inspecciona; cada prueba aserta el **código**, nunca el texto |
| §3.9 inventario de lecturas | E2E-2 |
| §4.1 regla de uso | E2E-3, §4.4-1 a 8 |
| §4.2 compromiso irrevocable y `no_enviado` | E2E-3, E2E-13, E2E-15 |
| §4.3 producto intacto | E2E-6.1-6.4 |
| §4.4 instantáneas y firma | §4.4-1 a 8, E2E-16, E2E-17, I15 |
| §5 reanudación | E2E-4, E2E-13, E2E-14, S09 |
| §6.1 esqueleto | E2E-1 (con base), E2E-1m (con `mundo=`) |
| §6.2 E2E-1 … E2E-18 | todas, con el número en el nombre del check |
| §6.3 familia S | S01-S23, cada una con su condición concreta y el **cierre de dependencias** (falla si cambia una condición fuera del cierre) |
| §6.3 familia I | I01-I15, con el código exacto, una lista cerrada de motivos concomitantes por prueba y ningún motivo de calidad |
| §6.3 inversa | INV y E2E-2 |
| §6.3 F17-ext | EXT |
| §7.1 `metricas.py` | A3 |

## 4. Interfaces que fijan las pruebas, porque el contrato las deja abiertas

El director debería confirmarlas antes de que empiece la implementación. Quien implemente no puede
cambiarlas.

1. **`proveedores`** es un dict cuyas claves son literalmente los nombres que enumera §6.1:
   `subscription_llm.subprocess.run`, `codex_subscription_llm.subprocess.run`,
   `subscription_llm._resolve_exe`, `codex_subscription_llm._resolve_exe`, `embeddings.embed_texts` y,
   como opcionales, `codex_subscription_llm._local_membership_allowed` y `llm.resolve_fallback_chain`.
2. **`mundo`** es un objeto con `async producir(caso, rep)`, `hash_soul()`,
   `fijar_jurisdicciones(codigos, tenant=None)`, `async abrir_despacho`, `producir_hasta_revision`,
   `aprobar` y `cerrar_despacho`. Su `producir` llama a `llm.call_llm` real con el nodo fijado por
   `set_node`.
3. **`runners`** (de juzgar y de VJ) es `{"opus": Runner, "codex": Runner}`. Cada runner atiende todas
   las etapas según el `schema` de su esquema.
4. **Argumentos de línea de comandos:**
   - `run_banco04` añade `--casos`, `--solo-piloto`, `--fase extension`,
     `--telemetria-acreditada <sha>` y `--atribucion-preregistrada <ruta>`;
   - sin `--salida-custodia`, los crudos custodiados van a `<MIA_BANCO04_CUSTODIA>/salidas`;
   - `banco04_juzgar registrar-cadena --base --nuevo --custodia --salida --bloque [--linea-base]`;
   - `banco04_juzgar juzgar --cadena --custodia [--reanudar-aprobado-por-pipe --etapas --versiones]`;
   - `banco04_decidir previa | veredicto | linea-base` con `--base`, `--nuevo`, `--custodia`,
     `--cadena` y `--salida`;
   - `VJ main(argv, runners=, carpeta_local_appdata=)` con `--telemetria-acreditada`;
   - `banco04_medir_codex` con el argv de R14 más `--telemetria-acreditada`, `--permitir-arbol-sucio`,
     `--incluir-custodiados` y `--versiones-contador`.
5. **`PruebaPuerta(manifiesto_custodia=, desproteger=)`.**
6. **Manifiesto de custodia (PENDIENTE DE DECISIÓN DEL DIRECTOR, ver §5 bis).** La cadena lo
   localiza en tiempo de llamada por `custodia.cargar_manifiesto()` / `custodia._MANIFEST_PATH`, y las
   pruebas lo apuntan al de la custodia de prueba.
7. **Identificación de condiciones:** el `id` de cada condición contiene el nombre literal de su
   métrica. Por ejemplo `afirmaciones_sin_respaldo`, `fuga_jurisdiccion`,
   `cobertura_hechos_decisivos`, `claude_extremo_por_caso`, `decisivos_estables`, `alcance`, y
   `atribu` o `C25`. El cierre de dependencias de la familia S se calcula sobre esos nombres.
8. **`etiqueta_version` del candidato** es la etiqueta de la versión. Solo lo usan S11 y EXT, que
   necesitan guionizar la cobertura por repetición.
9. **`IDENTIDADES_RESERVADO_RETIRADAS`** se consulta en tiempo de llamada, como atributo del módulo
   VJ.
10. **Claves de los 13 casos visibles:** van en la custodia de prueba, porque §6.1 pone allí «la clave
    del caso». La custodia real **solo** declara claves de V1-V4 (es un pendiente fuera de este
    frente). Para los casos sin expediente, el esquema exige ≥ 1 hecho: se fija un hecho no decisivo
    del mensaje y un punto `laguna_real`.

## 5. Lo que el contrato no permitió probar, o solo de forma aproximada

- **E2E-1 y las tres mutaciones del esqueleto con base de datos.** Necesitan el clúster 55448, que no
  está disponible. Quedan escritas en un proceso hijo con el `MIA_TEST_ENV_FILE` real y están en rojo
  con «clúster aislado no disponible». Que el grafo real acepte el contenido de los dobles del CLI no
  se pudo comprobar aquí. La mutación «material recortado» usa embeddings degenerados, porque el
  contrato no dice qué doble reduce el material.
- **`cli-codex-eval` con `None` (variante de E2E-3).** No es ejecutable con dobles: exige el override
  del harness y su `subprocess` (`codex_cli_adapter`) no está en la lista de §6.1, así que llamaría al
  CLI real. Queda como un check en rojo declarado.
- **E2E-15, muerte entre `en_curso` y `t_envio_utc`.** Ese instante ocurre dentro del cerrojo y no es
  alcanzable con dobles. Se fabrica la fila que dejaría ese proceso muerto (PID real ya terminado) y
  se prueba la detección y la clasificación reales. La muerte **después** de `t_envio_utc` sí es real:
  se mata el proceso hijo.
- **E2E-13, «la variante que suelta el cerrojo entre el control y el compromiso tiene que dar rojo».**
  Es una mutación de la implementación, no una prueba: la tiene que hacer el tercero que mute. La
  serialización se comprueba por la coherencia de los `seq` en R4.
- **§4.4 «sin entrada» para firmas de producción.** El runner exige una acreditación única de todas
  las `firmas_previstas`, así que «sin entrada» solo existe para las firmas de los jueces. Por eso las
  variantes 1, 4 y 6 usan el juez. La ambigüedad sobre una firma prevista se prueba como rechazo
  (exit 3) del runner, y sobre una firma de juez como `acreditacion_ambigua`.
- **Instantáneas en el repo.** §4.4 fija el directorio `backend/mia/eval/banco04/telemetria_acreditada/`
  y exige acreditar la `cli_version` exacta, que es la real (`claude --version`). Por eso la suite
  escribe ahí instantáneas de prueba, direccionadas por contenido, y las borra al terminar. Solo lo
  hace si el directorio ya existe; hoy no existe, así que no escribió nada. Eso deja el árbol sucio
  mientras corre, lo que el esqueleto admite (`arbol_sucio` ∈ E) y F17 relaja con `_prueba`. I15
  edita una instantánea en sitio y la restaura siempre.
- **E2E-17.** Si `registrar-cadena` se niega ante instantáneas distintas, también se acepta (la cadena
  no se registra). El contrato pone la comprobación en la puerta, pero las dos salidas impiden
  certificar.
- **S05** necesita una referencia propia: la misma producción con alcance < 0,95, juzgada con
  `limitada_expresa`. La mutación cambia solo la conducta de la pasada 2.
- **S14** solo prueba la salida estructuralmente inválida. Los textos sintéticos no llevan cifras, así
  que la variante «`no_aplica` sobre una cifra» no se guioniza.
- **Familia I, motivos concomitantes.** El contrato pide el código exacto, pero algunas ediciones
  rompen además otra identidad: por ejemplo, editar R1 cambia su sha frente a R8. Cada I declara una
  lista **cerrada** de concomitantes admitidos, y nunca admite un motivo de calidad ni una condición
  `no_cumple`.
- **E2E-2 e INV: «salida idéntica».** Se comparan con las horas excluidas. También se excluye el sha256
  de `entradas_leidas` de los crudos que la prueba editó en un campo derivado, porque sus bytes cambian
  de forma legítima.

## 5 bis. Dos decisiones que necesita el director (contradicciones o límites del contrato)

1. **El manifiesto de custodia en la puerta pública.**
   - §6.1, paso 4, llama a la puerta pública **sin** `_prueba` (de ahí sale `corridas_con_dobles`)
     sobre una **custodia de prueba**. Con el `custodia_manifest.json` del repo eso es imposible: la
     puerta no podría abrirla.
   - La suite lo resuelve apuntando `custodia._MANIFEST_PATH` al manifiesto de prueba durante el
     escenario. Eso **obliga** a la implementación a leer el manifiesto en tiempo de llamada, por
     `custodia.cargar_manifiesto()`. No es una interfaz neutra: es una interpretación del contrato.
   - Alternativa: que el esqueleto use `_prueba` solo con la relajación 1 de §3.1 y sin relajar
     `dobles`. Para eso `PruebaPuerta` tendría que permitir activar sus relajaciones por separado, y
     el resultado llevaría `modo_prueba`.
   - **Se pide aprobación expresa de una de las dos.**
2. **Escritura transitoria de instantáneas bajo `backend/`.**
   - §4.4 fija la ubicación (`backend/mia/eval/banco04/telemetria_acreditada/<sha256>.json`) y exige
     que cada R1 cite una instantánea que acredite **todas** sus `firmas_previstas` con la
     `cli_version` real. Por eso la suite tiene que escribir instantáneas de prueba en ese
     directorio mientras corre y borrarlas al terminar.
   - La alternativa, un directorio de pruebas que la puerta admita, exige cambiar §4.4 y §3.9. La
     suite no la toma porque el contrato no la permite.
   - **Se pide aprobación de la escritura transitoria, o una enmienda del contrato.**

## 6. Riesgos para quien implemente

- La suite completa con la cadena implementada producirá F17 (200 corridas juzgadas) y unas 30
  regeneraciones. Hay que correrla por tramos (`--solo F17,S01`) y fijar `timeout` amplios.
- Los dobles validan hoy contra los validadores v1.2/v1.3 existentes (autocontrol). La pasada 2 añade
  `negativa_correcta` solo si el esquema la declara.
- `BANCO04_CADENA_CONSERVAR=1` conserva la carpeta temporal para depurar.
