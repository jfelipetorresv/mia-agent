# Banco 0.4: contrato de la cadena (producir, juzgar, decidir)

Versión del contrato: **banco04-cadena/v9** (propuesta). Fecha: 2026-10-12. Base: HEAD `b89e4e8` (v5 con APTO de Astra en `6c26afc`; v6 y v7 rechazadas),
rama `feat/mia-04-hermes-legal`, protocolo **banco04-v1.3** (`docs/banco-calidad-04-protocolo.md`).

**Cambios de v1 a v2.**

- Corrige las objeciones K1–K12 del dictamen de Astra sobre la v1 (NO APTO). La tabla de cierre está
  en §9.
- Aplica las decisiones del director del 2026-10-12, que están en §8.4. Donde revocan algo, queda
  marcado como revocado.
- **El banco no cambia ningún archivo del producto** (K8): la telemetría cruda se captura desde
  `eval/` (§4.3).

**Cambios de v7 a v8** (dictamen de Astra sobre la v7).

- **Cuota por intervalo** (decisión del director, que aplica el cambio de Astra en (b)): cada
  consumo es un intervalo [mínimo, máximo]. Solo se certifica lo que el intervalo garantiza (§4.5).
- **Piloto:** un intento sin cota ya no deja la calidad en `no_certificable`. R se recalcula con la
  estimación congelada (§3.3 A, R11).
- **Estimación congelada** con un corte de secuencia: la estimación inicial va aparte de la
  actualización final (R4, §4.5).
- S08 y S10 exigen el resultado separado de CUOTA y conservan la CALIDAD.
- §8.6 explicita lo único que se retira de la habilitación de VJ.

**Cambios de v6 a v7.**

- **Decisión de Pipe del 2026-10-12, «Separar calidad y cuota».** **Revoca** «Acotar y medir».
  - El banco emite **dos veredictos**: CALIDAD y CUOTA (§3.1, §4.5).
  - Un intento sin cota ya no hace no certificable la calidad: pone máximo `∞` en su ámbito y la cuota
    se resuelve por intervalo (§4.5).
  - El envoltorio **no toca** el entorno del CLI.
- **Objeciones de Astra sobre la v6:**
  - (a) la cota no era conservadora: ya no se certifica ninguna cota de CLI;
  - (b) imponer los reintentos alteraba la conducta: se retira.
- Propuesta de protocolo que acompaña: `docs/banco-calidad-04-protocolo-v1.4-propuesta.md`.

**Cambios de v5 a v6** (acotados; Astra revisa solo el diff). *La parte «Acotar y medir» queda
revocada por la v7.*

- **Decisión de Pipe del 2026-10-12, «Acotar y medir»:** el intento fallido del CLI de Claude pasa a
  tener cota, con las condiciones y la fórmula de §4.5. Codex sigue sin cota (pendiente).
- **Decisiones del director sobre el §5 bis del autor de pruebas:**
  - la puerta pública solo acepta el `custodia_manifest.json` del repo;
  - `PruebaPuerta` activa cada relajación por separado;
  - nada se escribe bajo `backend/` en las pruebas (§3.1, §3.9, §4.4, §6.1).
- **§6.4:** las interfaces que fijan las pruebas pasan a ser contrato.

**Cambios de v4 a v5.**

- Cierra K7, la única objeción que la ronda 4 de Astra dejó abierta, con tres cambios:
  - la garantía de **compromiso irrevocable**, adoptada expresamente por el director;
  - la comprobación de secuencia propia para las huérfanas enviadas;
  - las orfandades en el inventario de lecturas.
- Lo demás no cambia.

**Cambios de v3 a v4.**

- Cierra los parciales K5, K7, K13 y K15 y la objeción nueva K16 de la ronda 3 de Astra, con la
  corrección literal que pide en cada una.
- Sin cambios en lo ya resuelto (K1, K4, K8, K10 y K14). La tabla de §9 queda ampliada.

**Cambios de v2 a v3.**

- Cierra los seis parciales (K1, K4, K5, K7, K8 y K10) y las tres objeciones nuevas (K13, K14 y K15)
  de la ronda 2 de Astra. La tabla de cierre de §9 queda ampliada.
- También cierra el camino por el que la ausencia contaba como cero: `omitido_si_cero` solo vale
  con una acreditación de la misma firma de comando (§4.4).

Este documento no cambia la muestra, las repeticiones, las métricas, los umbrales ni los techos del
protocolo. Fija **cómo se recorre** el banco desde `main` hasta el veredicto, **qué se escribe en
disco** y **de qué datos recalcula la puerta cada condición**. Lo revisa Astra; con él un autor
independiente escribe las pruebas en rojo y otros agentes implementan.

Abreviaturas de rutas (relativas a la raíz del repo): `M` = `backend/mia/eval/banco04/metricas.py` ·
`J` = `backend/mia/eval/banco04/jueces.py` · `R` = `execution/run_banco04.py` ·
`VJ` = `execution/banco04_validar_jueces.py` · `H` = `backend/mia/eval/harness.py` ·
`SG` = `backend/mia/eval/spend_guard.py` · `PR` = `backend/mia/eval/banco04/protocolo.py` ·
`DOC` = el protocolo. Brechas `B1`–`B14`: inventario de la puerta (scratchpad `r4/inventario-puerta.md`).
Objeciones `R3-N*`: dictámenes de Astra, ronda 3.

---

## 0 · Invariantes de la cadena

Cada invariante es verificable por una prueba de §6.

- **IC-1 · Un solo punto de entrada por etapa.** Producir, juzgar y decidir se ejecutan solo desde
  su `main`. Ninguna etapa recibe de quien la llama un valor que otra etapa ya haya calculado.
- **IC-2 · Crudo frente a derivado.**
  - Es **crudo** lo observado:
    - el texto que ve el abogado, el material del turno y los artefactos que el producto emitió en
      ese turno tal como los persistió el harness: el informe del muro (`resultado.verification`,
      H:709) y la ruta de cambios de motor (`resultado.model_fallbacks`, H:733). Las **señales**
      que el harness calcula sobre ellos, como `false_block` (H:743), `jurisdiction_leak` (H:753) o
      `abstention`, son derivadas: la puerta no las lee;
    - la respuesta literal de cada llamada a un modelo juez;
    - cada fila del registro por llamada (ledger);
    - los registros de identidad (manifiestos);
    - los registros previos que fija el protocolo: decisión de R, plan de aprobaciones, extensión y
      reanudaciones.
  - Todo lo demás es **derivado**. La puerta no abre ningún archivo derivado; lo vuelve a calcular.
- **IC-3 · Ausencia o contradicción ⇒ `no_certificable`.** En ningún paso de la puerta se usa
  `or 0`, `.get(k, 0)` ni un valor por defecto que convierta la falta de un dato en un valor válido.
- **IC-4 · Una sola fuente de consumo.** El ledger por llamada (R4) alimenta el contador del techo del
  circuito (`ContadorCuota`), el techo de producto (§6.3), `usage_by_node` (C25) y el consumo de los
  jueces. `turn_usage` deja de ser fuente del banco.
- **IC-5 · Identidad.** Todo crudo lleva el `manifiesto_sha256` (I10) de su versión. Lo del juicio
  lleva además el `cadena_sha256` (R8). La puerta liga todo a R8.
- **IC-6 · Reproducción, no confianza.** La puerta vuelve a ejecutar las funciones deterministas del
  juicio sobre las respuestas crudas guardadas:
  - validadores, partición, alineación, adjudicación, recuento, cobertura, kappa y exigencias del
    circuito;
  - las respuestas guardadas se sirven con un *runner reproducido*, que comprueba el `prompt_sha256`
    de cada llamada.

  Lo único que no se reproduce es la llamada al modelo.
- **IC-7 · Dobles.**
  - Una corrida hecha con dobles de proveedor queda marcada en su manifiesto (`dobles: true`) y la
    puerta pública nunca la certifica.
  - El modo de prueba de la puerta solo existe como parámetro de Python. Ningún flag de línea de
    comandos lo activa.

---

## 1 · Etapas y punto de entrada

### 1.1 Diagrama (Bloque 7; en el Bloque 0 solo existe la versión base)

```
 [prerrequisito, una vez]  VJ main ──► R9 validación reservada (cruda, en custodia)
                                          │
 R main --fase produccion ──► R1 MANIFIESTO, R2 rep-NN, R3 .enc, R4 llamadas/*, R11 decision_r,
   (versión base y nueva,     R12 aprobaciones_plan, R6 suspensiones / reanudaciones
    cada una en su dir)
 R main --fase aprobaciones ─► R10 aprob.intento-K / aprobacion.json, R4 llamadas/*
                                          │
 banco04_juzgar main registrar-cadena ──► R8 MANIFIESTO_CADENA.json (exclusivo, antes de juzgar)
 banco04_juzgar main juzgar ───────────► R5 juicio por corrida (ambas versiones, intercaladas
                                          y barajadas), R4 llamadas/* de jueces
                                          │
 banco04_decidir main previa ──────────► R7 EXTENSION.json (solo si alguna comparativa queda
                                          no_concluyente; exclusivo)
   └─(si hay R7) R main --fase extension ► rep R+1..R+5 en las dos versiones ─► juzgar otra vez
                                          │
 banco04_decidir main veredicto ───────► puerta.decidir(dir_nuevo, dir_base, custodia, cadena)
                                          ─► VEREDICTO.json (fuera de los cuatro directorios leídos)

 Bloque 0 (una sola versión, sin comparativas; §3.5):
 R main (0.3.3, piloto) ─► [autor independiente escribe el reservado NUEVO sobre esas salidas]
   ─► VJ main (reservado nuevo) ─► R main (0.3.3, resto) ─► juzgar ─►
   banco04_decidir main linea-base ─► puerta.medir_linea_base(dir_base, custodia, cadena)
                                     ─► INFORME_LINEA_BASE.json
```

### 1.2 Puntos de entrada y quién llama a quién

| Etapa | Entrada única | Cadena de llamadas desde `main` |
|---|---|---|
| Producir | `R:1962 main` (`--fase produccion`, `aprobaciones` y la nueva `extension`) | `verificar_aislamiento` → `_montaje_real` (R:1681) → instala la captura del ledger (`telemetria.instalar`, nuevo) y el contexto de llamada → `ejecutar_banco` (R:1046) → `_ejecutar_una` (R:954) fija el contexto `(versión, caso, rep, intento, fase)` → `deps.producir` → `harness.run_case` (H:502) → grafo → `llm.call_llm` → `_invoke` envuelto por `SG._guarded_invoke` (SG:1126) → `telemetria.registrar_llamada` (`en_curso` antes de invocar y `cerrada` al volver) |
| Validar jueces (prerrequisito, §8.6) | `VJ:651 main` | `validar_circuito` → `evaluar_item` → `jueces.pasada1` con runners envueltos por `telemetria` → escribe R9 crudo |
| Juzgar | `execution/banco04_juzgar.py main` (nuevo), subcomandos `registrar-cadena` y `juzgar` | `registros.cargar_corridas(dir)` → `ceguera.preparar_candidato` (llave = `custodia.semilla_hmac()`) → `jueces.pasada1`, `pasada2`, `votar_cobertura`, `adjudicar_negativas_falsas`; estabilidad con el 10 % y Codex en la pasada 2 con el 15 %, ambos con `seleccionar_con_semilla` → `registros.escribir_juicio` (R5) |
| Decidir | `execution/banco04_decidir.py main` (nuevo), subcomandos `previa`, `veredicto` (Bloque 7) y `linea-base` (Bloque 0, §3.5) | `puerta.decidir(...)` (nuevo, `backend/mia/eval/banco04/puerta.py`) → `registros` (lectura estricta) → `reproduccion` (runners reproducidos) → internos de `M` → `VEREDICTO.json` |

**Módulos nuevos:**

- `banco04/telemetria.py`: regla única de uso, ledger por llamada, contexto, control previo y los
  envoltorios de intercepción de §4.3.
- `banco04/telemetria_acreditada/<sha256>.json`: instantáneas inmutables de las acreditaciones de
  telemetría, direccionadas por contenido (§4.4). **No** entran en la huella del evaluador: se ligan
  por cita (K13).
- `execution/banco04_medir_codex.py`: `main` de la medición previa de Codex de producción, que
  produce la fuente de R13 (K5, R14).
- `banco04/registros.py`: esquemas, escritura atómica y lectura estricta de crudos, con cifrado de
  custodia.
- `banco04/reproduccion.py`: runners reproducidos.
- `banco04/puerta.py`.

Los cuatro, más `execution/banco04_juzgar.py` y `execution/banco04_decidir.py`, entran en la huella
del evaluador congelado (J:1931-1945).

### 1.3 Ubicación en disco

- `S` = `--salida` del runner (fuera del repo). Directorio de versión = `S/<ver>`. Es lo que recibe
  la puerta.
- Crudos de casos custodiados = `<custodia>/salidas/<ver>/...`. **Cambia respecto del código
  actual**, donde `--salida-custodia` es libre (R:204-215). §2.3 del protocolo dice que las salidas
  crudas del estrato custodiado viven en la carpeta de custodia. Con esto la puerta las localiza
  desde su argumento `custodia` sin recibir otra ruta.
- Validación reservada = `<custodia>/validacion/<identidad_reservado>/`.
- R7 (extensión) vive junto a R8: `<dir de MANIFIESTO_CADENA.json>/EXTENSION.json`.

---

## 2 · Registros crudos

Convenciones:

- Todo JSON se escribe de forma atómica (tmp + `os.replace`, como R:248-253).
- «Exclusivo» = apertura `"x"`: se escribe una vez y nunca se reescribe.
- **I10** = lleva `manifiesto_sha256` y la puerta lo coteja.
- «Cifrado» = AES-256-GCM con la llave de la custodia (`Custodia.cifrar_registro`, `custodia.py:241`),
  más una **ficha** en claro con `archivo, id_registro, sha256_claro, sha256_cifrado`.

### R1 · `S/<ver>/MANIFIESTO.json` (exclusivo; no cifrado; es la identidad I10)

Conserva los campos actuales (R:739-743): `version, sha_arbol, arbol_limpio, modificaciones_sha256,
soul_sha256, cli_version, politica, protocolo_version, protocolo_hash, runner_sha256`. Añade:

| Campo | Tipo | Motivo |
|---|---|---|
| `bloque` | int (0 \| 7) | techo y reserva del circuito |
| `semilla` | str | hoy solo viaja en el rep (R:1035) y no se coteja |
| `instrumentacion_sha256` | str | sha256 de `H`, `SG` y `telemetria.py`: la captura forma parte de lo medido |
| `dobles` | bool | IC-7 |
| `muestra_restringida` | list[str] \| null | `--casos` (esqueleto); `null` = muestra del protocolo |
| `solo_piloto` | bool | esqueleto |
| `atribucion_preregistrada` | `{nodo: [metricas]}` \| null | solo en la versión nueva y escrito **antes de producirla**: hipótesis del plan, Bloque 4. Ancla el C25 antes de ver el consumo por nodo (Q10) |
| `codex_cli_version` | str \| null | `codex --version`, sin ventana (K8, comparabilidad) |
| `cadenas_politica` | `{"<tarea>|<escalada>": [alias]}` | `llm.resolve_fallback_chain(tarea, None, escalada)` (llm.py:717; la escalada entra en :847) para cada tarea del grafo y cada escalada válida (`standard`, `exceptional`), bajo la política fija y con la configuración aislada ya aplicada; se registra antes de la primera corrida (K5) |
| `puede_codex` | bool | `true` si algún alias de `cadenas_politica` empieza por `cli-codex` (K5) |
| `estimacion_piloto_codex` | `{por_clase: {pequeno, fuga, voluminoso: int}, fuente: {ruta, sha256}}` \| null | **solo en un R1 consumidor** (`proposito: produccion`) con `puede_codex`: cita R13 **en un solo sentido** (ruta y sha256 de R13) y copia su `por_clase`. Sin R13 el runner rechaza (exit 3). R13 no cita a ningún consumidor (K5) |
| `proposito` | `produccion` \| `medicion_codex` | `medicion_codex` = manifiesto de una medición previa (R14). **Está exento de R13**: no lleva `estimacion_piloto_codex` y el runner no exige R13 para arrancarla (K5) |
| `seleccion_medicion` | `{k: int, por_clase: {clase: [case_id]}, regla}` \| null | solo con `proposito: medicion_codex`: la selección y `k` **preregistrados** en el manifiesto exclusivo, antes de la primera corrida de la medición (K16) |
| `sha_producto` | str | SHA del producto medido: `7b9aaa0` para 0.3.3 y el HEAD de 0.4 (§9.6) |
| `rutas_modificadas_respecto_del_producto` | list[str] | `git diff --name-only <sha_producto> HEAD`. Todas tienen que estar bajo `backend/mia/eval/` o `execution/` (parche del banco, literal de P:1023-1025; K8) |
| `telemetria_acreditada_sha256` | str | sha256 de la instantánea de §4.4 con que se produjo. Es su nombre de archivo (K13) |
| `firmas_previstas` | list[{familia, firma_comando}] | las firmas normalizadas (§4.4) de todos los comandos que `cadenas_politica` y los esfuerzos de `llm._cli_effort` pueden generar. El runner rechaza (exit 3) si alguna carece de acreditación única en la instantánea: una corrida que la usara sería desconocida (K4) |

### R2 · `<base>/<ver>/<caso>/rep-NN.json` (`base` = `S`, o `<custodia>/salidas` si el caso está custodiado; I10)

Conserva R:1033-1040. Cambia o añade:

| Campo | Tipo | Notas |
|---|---|---|
| `caso_digest` | str | `holdout.case_digest(caso)` (`holdout.py:158`), válido para cualquier `GoldenCase`; falta hoy (B13) |
| `prompt_version_hash` | str | `H:181 prompt_version_hash()`; falta hoy (B13) |
| `jurisdicciones_fijadas` | list[str] | lo que el runner fijó en `tenant_settings` (R:1769-1783); falta hoy (B3) |
| `extension` | bool | `true` solo en las repeticiones R+1..R+5 |
| `extension_sha256` | str \| null | sha256 de R7 si `extension` |
| `intentos[].llamadas` | list[str] | ids de R4 de ese intento, en orden de apertura |
| `intentos[].consumo` | se renombra `consumo_resumen` | **derivado**: la puerta no lo lee (IC-4) |
| `resultado` | dict (visibles) \| ficha (custodiados) | igual que hoy; en custodiados el contenido va a R3 |

### R3 · `<custodia>/salidas/<ver>/<caso>/rep-NN.resultado.enc` y `.error.enc` (cifrados; I10 indirecto por la ficha de R2)

Igual que R:806-848. Solo cambia la carpeta (§1.3).

### R4 · Ledger por llamada: `S/<ver>/llamadas/<id>.json` (no cifrado: no lleva texto; I10)

Una fila por **intento físico** contra un proveedor, que es el punto que ve `SG._guarded_invoke`
(SG:1126-1275): una vez por intento, reintentos incluidos. También una por cada invocación de un
runner de juez. Sustituye a `consumo_desde_guardian` (R:1537-1547), a `LedgerJuicio` (R:1228-1294),
al volcado `usage_by_node.<epoch>.json` (R:1933-1941) y a la dependencia de `turn_usage` (B7, B13,
B14).

| Campo | Tipo | Regla |
|---|---|---|
| `schema` | `"banco04-llamada/v1"` | |
| `id` | str | `<fase>-<caso\|_>-r<rep\|00>-i<intento\|0>-<tramo_id>-<seq:06d>`; único |
| `version`, `manifiesto_sha256` | str | I10 |
| `cadena_sha256` | str \| null | obligatorio en las fases `juicio_*` |
| `tramo_id`, `pid`, `seq` | str, int, int | proceso y orden dentro de él |
| `bloque` | int (0 \| 7) | el de R1 de la versión en producción y aprobaciones, y el de R8 en juicio; en validación, el `--bloque` de VJ. El presupuesto del circuito de un bloque solo suma sus filas |
| `estado` | `en_curso` \| `cerrada` \| `no_enviado` | `en_curso` se escribe **antes** de `check_and_reserve`; `no_enviado` es el estado terminal de una llamada denegada antes de salir al proveedor (K15, §4.2) |
| `seq_inicio`, `seq_envio`, `seq_cierre` | int, int \| null, int \| null | números de secuencia **globales del bloque**, asignados bajo el cerrojo de §5.4: al escribir `en_curso`, al registrar el compromiso de envío y al cerrar. `seq_envio` es el **punto de compromiso irrevocable** de la llamada (§4.2, §5.4). `seq_envio` es `null` en `no_enviado`; `seq_cierre` es `null` en una huérfana enviada, que lleva en su lugar el `seq_deteccion` de su registro de orfandad (K7) |
| `t_envio_utc` | str \| null | se escribe de forma atómica y duradera, **bajo el mismo cerrojo que el control previo y sin soltarlo entre medias**, junto con `seq_envio`, inmediatamente antes de llamar a `_original_invoke` o al subproceso del juez. `null` = la llamada no salió (K7, K15) |
| `t_inicio_utc`, `t_fin_utc` | str ISO-8601 UTC | informativos. El orden lo dan `seq_inicio` y `seq_cierre` |
| `fase` | enum | `produccion`, `aprobacion_turno`, `aprobacion_aprobar`, `aprobacion_trabajos`, `embeddings_siembra`, `juicio_p1_opus`, `juicio_p1_codex`, `juicio_tercer_voto`, `juicio_negativa_falsa`, `juicio_p2_opus`, `juicio_p2_codex`, `juicio_voto_cobertura_opus`, `juicio_voto_cobertura_codex`, `juicio_estabilidad`, `validacion`, `medicion_codex` (R14), `medicion_fondo` (§4.5), `sin_contexto` |
| `caso_id`, `rep`, `intento` | str/int \| null | vienen del contexto de llamada (ContextVar de `telemetria`) |
| `candidate_id`, `pasada`, `objetivo` | str \| null | jueces; `objetivo` = id de unidad, hecho o (punto, parte) |
| `alias` | str | el alias de la cadena, tal como lo recibe `_guarded_invoke` |
| `familia` | `claude_cli` \| `codex_cli` \| `api` \| `local` \| `embeddings` | decide la regla de §4 y el proveedor de cuota |
| `proveedor_cuota` | `claude` \| `codex` \| `ninguno` | `codex` si el alias empieza por `cli-codex`; `ninguno` para embeddings; el resto, `claude` (igual que `GuardBanco.tokens_llm`, R:1615-1617) |
| `modelo_solicitado` | str \| null | `resp.mia_model_hint` (`subscription_llm.py:283`): el modelo **pedido** o configurado. **No** es identidad efectiva y no se usa para comparar (K8) |
| `model_usage_crudo` | dict \| null | `modelUsage` **completo** del JSON del CLI de Claude, capturado por la ranura (§4.3): por modelo, `inputTokens`, `outputTokens`, `cacheReadInputTokens`, `cacheCreationInputTokens`, `canonicalModel`, `provider`… (forma observada en `output/validation/claude-opus55-final.json`) (K8) |
| `identidades_efectivas` | list[{clave, canonical_model, provider, output_tokens}] \| null | derivado puro de `model_usage_crudo` (Claude) o del campo de identidad que acredite §4.4 para Codex; para `api`, `resp.model` servido. Orden: `output_tokens` descendente y después `canonical_model`. La primera es la **principal** (K8) |
| `firma_comando` | {argv_normalizado: [str], sha256} \| null | comando efectivo del CLI capturado por la ranura (§4.3), normalizado según §4.4 (K4) |
| `esfuerzo`, `esfuerzo_fuente` | str \| null, `respuesta` \| `politica` \| null | en un fallo no hay `resp`: se deriva de `llm._cli_effort(alias, task, escalada)` y la fuente es `politica` |
| `tarea`, `escalada`, `nodo` | str \| null | `nodo` = `metrics.usage._node.get()` (`usage.py:71`), leído desde `eval/` sin cambiar el producto (§4.2) |
| `uso_crudo` | dict \| null | lo que entregó el proveedor, sin tocarlo y capturado por el envoltorio de §4.3. Claude CLI: el dict `usage` del JSON. Codex: `{"eventos": [cada dict usage, en orden]}` |
| `cli_version` | str \| null | Claude: `R1.cli_version`; Codex: el `cli_version` de sus eventos, o `R1.codex_cli_version` |
| `acreditacion_aplicada` | str \| null | id de la entrada de la instantánea citada por R1 (o por R9 en validación) que aplicó la regla (§4.4) |
| `origen` | `"captura"` | lo escriben solo `telemetria` dentro de `_guarded_invoke` o de los runners de juez; ningún doble lo escribe (§6.1) |
| `uso_validado` | dict | `{consumo_conocido: bool, entrada, salida, cache_lectura, cache_escritura, total: int\|null, componentes_ausentes: [str], regla_version}` (§4.1) |
| `exito` | bool | |
| `tipo_error`, `proveedor_no_alcanzado` | str \| null, bool \| null | solo la clase de la excepción, nunca su texto (I8) |
| `motivo_parada`, `motivo_parada_fuente` | str \| null, `cli` \| `api` \| `no_informado` | §4.3, Q9 |
| `cota` | dict | `{tokens_entrada_estimados, cota_salida, tokens_cota_superior, fuente, motivo}`; igual que SG:1233-1247. En `cli-*` (Claude y Codex) la cota es siempre `null` (C18). La v6 le daba cota a Claude; la v7 lo revoca |
| `estimacion_empirica` | `{inicial: {tokens, componentes: {entrada_heuristica, salida_observada, fondo_observado, *_fuente}, corte_seq, observaciones: [ids R4], observaciones_sha256, version_regla, instantanea_sha256}}` \| null | solo en filas **sin cota**, o con cota finita (para la estimación puntual de §4.5). **Inicial y congelada:** se calcula al cerrar la fila (o al registrar su orfandad) con las observaciones de `seq_cierre < corte_seq`, donde `corte_seq` = su propio `seq_cierre` o `seq_deteccion`. Ese conjunto queda registrado. La **actualización final** no se guarda aquí: la calcula la puerta (§4.5) |
| `entorno_cli` | `{max_retries: str\|null, retry_watchdog_definida: bool, max_output_tokens: str\|null}` \| null | solo en `claude_cli`: los tres valores del entorno efectivo, capturados **solo para publicarlos y versionar la estimación** (§4.5). El envoltorio no los cambia (v7) |
| `reanudacion_vigente` | str \| null | referencia de R6 bajo la que se lanzó (jueces y Codex de producción) |
| `eventos_desconocidos_vistos` | list[str] | ids de filas desconocidas que el control previo vio (§5) |
| `prompt_sha256` | str \| null | obligatorio en las fases `juicio_*` y `validacion` |

**Clases de consumo de una fila (K7):**

- **conocido:** `uso_validado.consumo_conocido == true`.
- **desconocido con cota:** `consumo_conocido == false` y `cota.tokens_cota_superior` es un entero.
  - Sale de `max_tokens` aplicado en las familias `api` y `local` (SG:1209-1243), o de una cota CLI
    acreditada según C18 (`spend_guard.cota_salida_cli` distinta de `None`).
  - Cuenta con su cota y el techo sigue siendo certificable (P:464-468).
  - **No detiene nada.**
- **desconocido sin cota:** `consumo_conocido == false` y `cota.tokens_cota_superior` es `null`, o
  bien una fila **huérfana enviada** (ver abajo).
  - Pone máximo `∞` en el consumo de su ámbito; la **cuota** se resuelve por intervalo (§4.5, v9).
    La calidad sigue siendo certificable.
  - Es el **único** evento que detiene la ejecución y exige reanudación (§5).
- **no enviado:** `estado == "no_enviado"`, o fila **huérfana no enviada**. No es consumo (§4.2).

**Clasificación única de las huérfanas (K15).** Una fila es **huérfana** si sigue `en_curso`, su
proceso ya no está y se registró su detección (§5.4, «registro de orfandad»). Hay exactamente dos
clases:

- **huérfana no enviada**, con `t_envio_utc == null`: clase «no enviado»;
- **huérfana enviada**, con `t_envio_utc` no nulo: clase «desconocido sin cota».

Esta es la única definición. §4.1, §4.2, §5.4 y las pruebas la remiten aquí.

### R5 · Juicio por corrida (I10 y cadena)

- **Visibles:** `S/<ver>/juicio/<caso>/rep-NN.juicio.json`, en claro.
- **Custodiados:** `<custodia>/salidas/<ver>/<caso>/rep-NN.juicio.enc`, más la ficha
  `rep-NN.juicio.json` en claro.

Contenido crudo:

| Campo | Tipo |
|---|---|
| `schema` | `"banco04-juicio/v1"` |
| `version`, `caso_id`, `rep`, `manifiesto_sha256`, `cadena_sha256` | identidad |
| `hash_evaluador` | str (combinado, J:1948-1962) |
| `rep_sha256` | sha256 canónico de la **parte cruda** del R2 juzgado. Excluye los campos derivados: `intentos[].consumo_resumen` y, de `resultado`, `score`, `false_block`, `jurisdiction_leak`, `abstention`, `provenance`, `recall_enterrado`, `substantive`, `reached_draft` (H:724, derivado de `score`, `scoring.py:445`), `draft_preview` y `diagnosis_preview` (H:698-776). Así editar un derivado no rompe la identidad (familia inversa) |
| `texto_sha256` | `{diagnostico, borrador}` (texto completo, antes del cegado) |
| `candidate_id`, `paquete_sha256` | el paquete no se guarda: la puerta lo reconstruye (§3.2, paso 4) |
| `llamadas[]` | en orden: `{ledger_id, etapa, objetivo, intento (1\|2), prompt_sha256, esquema, respuesta: {salida (JSON literal del modelo), crudo_sha256, error, uso_crudo, eventos, modelo_reportado, cli_version, latencia_ms}}` |

**Telemetría cruda de los jueces (K4).**

- **Codex:** `respuesta.eventos` = **todas** las líneas JSONL de `cp.stdout`, en orden, sin filtrar.
  - Hoy `CodexJuezRunner._llamar` (J:1689) solo guarda lo que devuelve `_parse_events`
    (`codex_cli_adapter.py:292-329`), que se queda con el último valor de cada componente
    (:318-328).
  - Desde v2, el runner guarda `cp.stdout` íntegro y su sha256, y `uso_crudo =
    {"eventos": [dicts usage]}`. `_parse_events` deja de ser fuente de consumo.
  - En los casos custodiados `eventos` va dentro de `.enc`, porque los eventos pueden reproducir
    texto del caso. La fila R4 solo lleva los dicts `usage`, que no contienen texto.
- **Claude:** `uso_crudo` = `{usage, stop_reason, modelUsage, num_turns}` tomados del JSON del CLI
  (J:1604-1609).

**Qué contiene en crudo cada elemento que pide el encargo:**

- **Pasada 1, Opus y Codex:** cada uno, con su reintento.
- **Adjudicación:** la reproduce la puerta. El **tercer voto** es la respuesta de la etapa
  `juicio_tercer_voto` por unidad, y el voto ciego de cada negativa falsa también se guarda.
- **`uso_fuente`:** está dentro de la `evidencia` de la salida cruda (J:135, C21).
- **Discordancias:** las recalcula la puerta.
- **Cobertura de hechos y conducta:** salida cruda de `juicio_p2_*`, más los votos de cobertura.
- **Negativas falsas:** sus votos.
- **Consumo de los jueces:** las filas R4 enlazadas por `ledger_id`, con caso, rep, `candidate_id` y
  pasada (cierra B14).

**Campo nuevo de la pasada 2: `negativa_correcta` (K1; aclaración C14, sin v1.4).** El esquema
`banco04-juez-cobertura/v1.3` (J:165-189) añade:

`negativa_correcta: {aplica: bool, respuesta: "si"|"no"|null, segmentos: [ids], motivo: str}`

- **Semántica (§5.4.1).** En un caso de riesgo, un turno que no llega a diagnóstico, cierre y
  borrador «se cumple» si lo que sí muestra es la negativa que la clave fija como conducta correcta
  (los `puntos_materiales` de conducta: declarar el ordenamiento no configurado, no atribuir al
  despacho lo que no llegó, no dar por sostenida la cita que no sostiene).
- **Validación** (`validar_pasada2`, J:1192, con el parámetro nuevo `es_riesgo`):
  - `aplica` tiene que ser igual a `es_riesgo`, que el juzgador pasa como
    `PR.estrato_de(caso) == A-riesgo`;
  - si `aplica` es falso: `respuesta` es `null`, `segmentos` está vacío;
  - si la respuesta es `"si"`: `segmentos` no vacío y **todos** los `puntos_materiales` de la clave
    con `resolucion == "resuelto"`. En los casos de riesgo los puntos son la conducta correcta
    (DOC §2.3). Una contradicción se rechaza como error estructural (reintento y,
    si persiste, «no evaluada»).
- **Uso en la puerta.** `negativa_correcta = (respuesta == "si")`. Se recalcula la coherencia con
  los puntos y, si hay contradicción, el resultado es `no_certificable`. La puerta añade además
  `afirmaciones_sin_respaldo == 0` en esa corrida: una negativa con un defecto confirmado no es
  correcta.

**Derivado opcional**, solo para auditoría y que la puerta **no abre**:
`rep-NN.juicio.derivado.json` con decisiones, recuento, `pares_kappa`, hechos y puntos. Una prueba
de §6 exige que mutarlo no cambie el veredicto.

### R6 · Suspensiones y reanudaciones (no cifrado; I10)

- **Suspensiones inmutables (K7): `S/<ver>/suspensiones/<etapa>-<NNNNNN>.json`**, exclusivas, una
  por suspensión. `NNNNNN` es el `seq` global del bloque en que se registró.
  - Contenido: `{schema "banco04-suspension/v1", id, etapa: produccion|aprobaciones|juicio|validacion,
    version, motivo_codigo, eventos: [ids R4], consumo (resumen del contador), seq,
    registrada_utc, manifiesto_sha256}`.
  - **Nunca se sobrescribe ni se borra.** Desaparece `SUSPENDIDO.json`: `_escribir_suspension`
    (R:939-950) deja de reescribir un único marcador, y `ejecutar_banco` (R:1050-1057) y
    `ejecutar_aprobaciones` (R:1453-1460) dejan de borrarlo.
  - Una suspensión está **activa** mientras ninguna reanudación válida la cite por `{ruta_relativa,
    sha256}`.
- **`S/<ver>/reanudaciones/<NNN>.json`** (nuevo, exclusivo; sustituye a `SUSPENDIDO.reanudado.json`,
  R:1056 y R:1458): `{schema "banco04-reanudacion/v2", n, referencia_aprobacion_pipe: str no vacía,
  registrada_utc, etapas: [produccion|aprobaciones|juicio|validacion], versiones: [etiquetas],
  cubre: {suspensiones: [{ruta_relativa, sha256}], eventos_desconocidos: [ids R4]},
  eventos_sha256 (sha256 canónico de las filas cubiertas tal como estaban al registrar),
  manifiesto_sha256}`.
- **Reglas de validez de una reanudación** (K7):
  - `eventos_desconocidos` ⊆ filas **sin cota** que existían al registrarla. Las filas con cota
    nunca se «cubren», porque no detienen nada.
  - Toda suspensión citada existe con ese sha256, estaba activa al registrar (ninguna reanudación
    anterior la citaba) y es de una de sus `etapas` y `versiones`.
  - Cada reanudación lleva su propio `seq` global, asignado bajo el cerrojo de §5.4.
  - `etapas` y `versiones` no pueden estar vacías.
  - Una reanudación **solo autoriza a continuar**: nunca cambia `consumo_conocido`, ni la cota, ni
    la clase de ninguna fila, ni la certificabilidad del techo.

### R7 · `EXTENSION.json` (exclusivo; ligado a la cadena)

`{schema "banco04-extension/v1", cadena_sha256, R_original: {caso: int}, metricas: [{metrica, unidad,
previa: {veredicto, estimacion, intervalo_90, diferencia_por_caso}}], casos: [ids], corridas_por_caso: 5,
registrada_utc}`.

- Las corridas adicionales se identifican en R2 (`extension: true`, `extension_sha256`, reps
  R_original+1..R_original+5) en **las dos versiones**.
- Todo campo salvo `registrada_utc` lo recalcula la puerta, que exige igualdad (§3.4).

### R8 · `MANIFIESTO_CADENA.json` (exclusivo; escrito por `banco04_juzgar registrar-cadena` antes de la primera llamada de juez)

Solo identidades y pre-registros; ninguna conclusión:

- `schema "banco04-cadena/v1"`, `protocolo_version`, `protocolo_hash`, `bloque`, `dobles`.
- `versiones: [{etiqueta, rol: base|nuevo, manifiesto_sha256}]`.
- `hash_evaluador` (combinado).
- `custodia: {manifiesto_sha256 (de custodia_manifest.json), identidad_reservado: str | null}`.
- `validacion_reservada: {registro_sha256: str | null}` (R9).
  - `registrar-cadena` acepta `null` en los dos campos anulables (esqueleto, o validación aún no
    corrida).
  - La puerta convierte ese `null` en el motivo `validacion_reservada_ausente` (`no_certificable`).
- `semilla_juicio_huella`: HMAC(semilla_hmac, "huella"); no revela la semilla.
- `atribucion_preregistrada_sha256`: sha256 del campo homónimo de R1 de la versión nueva. El mapa
  vive en R1 porque se escribe antes de producir (C25, Q10).
- `telemetria_acreditada_sha256`: sha256 de la instantánea de §4.4 con que se juzga. **Regla única
  (K13):** es igual al de todos los R1 de la cadena. No hay excepciones ni adiciones (§4.4).
- `bloque_0_linea_base: bool`. Con `true`, `versiones` tiene una sola entrada `rol: base` y solo vale
  para `linea-base` (§3.5).

### R9 · Validación reservada cruda (cifrada; ligada al hash del evaluador)

- **Ubicación:** `<custodia>/validacion/<identidad_reservado>/registro.enc`, más la ficha
  `registro.json`.
- **Contenido:** `{schema "banco04-validacion/v1", identidad_reservado, hash_evaluador,
  telemetria_acreditada_sha256 (su propia instantánea, K13),
  acreditacion_v13 (contenido completo), items: [{item_id, paquete_sha256, llamadas[] (mismo esquema
  que R5)}]}`.
- **Cambios en VJ:**
  - deja de excluir `verdades` y `pares_kappa` (VJ:388-389);
  - persiste las respuestas crudas en lugar del resumen;
  - la llave de ceguera deja de ser `os.urandom(32)` (VJ:699) y pasa a ser HMAC(semilla_hmac,
    "validacion"), para que la puerta reconstruya los paquetes;
  - la escritura deja de ser `write_text` no atómico (VJ:706).
- **Reservado nuevo y retirada del actual (K3, decisión del director).**
  - El reservado custodiado **actual se retira** y no se usa nunca. VJ y la puerta rechazan toda
    `identidad_reservado` incluida en `IDENTIDADES_RESERVADO_RETIRADAS`, una constante nueva de VJ
    que entra en la huella del evaluador.
  - El director registra el valor ejecutando `identidad_sellada_reservado` (VJ:414) sobre el
    manifiesto de custodia vigente. Este contrato no lo calcula: no se leyó la custodia.
  - Un autor independiente escribe un **reservado nuevo** sobre salidas reales de la tanda piloto de
    0.3.3 (DOC §8.6; paso 6 del HANDOFF), con identidad nueva y acreditación v1.3 nueva.
  - Por eso el orden del Bloque 0 es el de §1.1: piloto de 0.3.3 → reservado nuevo → VJ → resto.
- **Raíz del registro de uso (K3).**
  - `raiz_registro_uso` (VJ:427-446) deja de leer `LOCALAPPDATA` y `MIA_BANCO04_CUSTODIA` del
    entorno. Resuelve la raíz con `SHGetKnownFolderPath(FOLDERID_LocalAppData)` (shell32, vía
    ctypes) del usuario del proceso. El entorno se ignora para la raíz.
  - La marca secundaria en la custodia (VJ:455) se conserva.
  - Prueba de reubicación conjunta: con `LOCALAPPDATA` y `MIA_BANCO04_CUSTODIA` apuntando **a la
    vez** a carpetas temporales nuevas, el segundo uso del mismo reservado se rechaza.
  - La prueba sustituye la API solo mediante un parámetro de Python, nunca por entorno.
  - **Riesgo residual declarado:** un operador con control local del perfil puede borrar el
    registro, o redirigir la carpeta conocida desde el registro de Windows. La barrera es
    organizativa, igual que la de la custodia DPAPI (DOC §2.3).
- **Reanudación de la validación (K7).**
  - `VJ main --reanudar-aprobado-por-pipe <REF>` escribe una reanudación R6 con
    `etapas: [validacion]` en `<--salida-banco>/<--version>/reanudaciones/`.
  - R9 se escribe **por ítem**, de forma idempotente. La reanudación continúa en el primer ítem sin
    juicio completo, con la misma identidad del reservado, el mismo `hash_evaluador` y el mismo
    registro de uso.
  - Reanudar no es un segundo uso del reservado. Con otro `hash_evaluador`, VJ se niega a seguir.

### R10 · Aprobaciones (I10)

Conservan `aprob.intento-K.json` y `aprobacion.json` (R:1395-1439). Añaden:

- `intentos[].llamadas`: ids R4 de las fases `aprobacion_*`;
- `caso_digest` y `jurisdicciones_fijadas`.

`consumo_turno` y `consumo_aprobacion` pasan a ser **derivados** que la puerta no lee.

### R11 · `S/<ver>/decision_r.json` y R12 · `S/<ver>/aprobaciones_plan.json` (registros previos; I10)

Sin cambios de esquema (R:1105-1119, R:1142-1145). La puerta **los recalcula**:

- `decidir_r` (R:515-565) con el consumo de las filas R4 de la repetición 1;
- `elegir_aprobaciones` (R:568-578) con las repeticiones completadas y `R1.semilla`.

Exige igualdad con lo escrito.

### R13 · Registro de estimación de Codex en la piloto (K5, K16; ligado al manifiesto de la medición)

- **Ubicación:** `S/<ver>-medicion-codex/estimacion_codex.json`, exclusivo, **dentro del
  directorio de la medición**. Se escribe antes de la primera corrida de la versión consumidora.
- **Dirección de las ligaduras (sin circularidad):**
  - R13 lleva el `manifiesto_sha256` **del manifiesto de la medición** (R1 con `proposito:
    medicion_codex`), y ese manifiesto no cita R13;
  - el R1 **consumidor** cita R13 en `estimacion_piloto_codex.fuente` (ruta y sha256), y R13 no cita
    al consumidor.

  El orden de escritura es: R1 de la medición → filas R4 y recibos → R13 → R1 consumidor.
- **Contenido:** `{schema "banco04-estimacion-codex/v3", manifiesto_medicion_sha256,
  por_clase: {pequeno, fuga, voluminoso: int}, recibos: [{ruta, sha256}], filas_R4: [{ruta, sha256}],
  regla: "(5·max_c + 3) // 4"}`.
  - `filas_R4` tiene que ser **exactamente** el conjunto de **todas** las filas R4 del directorio de
    la medición (K16).
  - `recibos`, exactamente los de todas las corridas preregistradas en `seleccion_medicion`.
- **Productor:** únicamente `banco04_medir_codex main` (R14), al terminar la medición. Ningún otro
  camino escribe R13.
- **Regla y redondeo:**
  - por clase: `max_c` = el máximo, sobre **todas** las corridas preregistradas de esa clase, de
    la suma de `uso_validado.total` de **todas** sus filas R4 `codex`, de todos sus intentos;
  - `por_clase[c] = (5·max_c + 3) // 4`: techo entero de ×1,25, en aritmética entera sin `float`;
  - un cero solo vale si cada corrida preregistrada de la clase tiene un recibo `completo` con
    `n_llamadas_codex == 0` y todas sus filas R4 cerradas: **un cero requiere acreditar una corrida
    completa** (K16). Un recibo que no esté `completo` impide escribir R13.
- **La puerta** abre **todas** las filas R4 y **todos** los recibos del directorio de la medición
  (§3.9) y exige tres igualdades:
  - el conjunto de filas R4 en disco = `R13.filas_R4` = la unión de `recibos[].intentos[].llamadas`;
  - los recibos = las corridas de `seleccion_medicion` del manifiesto de la medición;
  - `por_clase` = el recalculado con la regla.

  Cualquier diferencia, o una fila fuente desconocida (con o sin cota), `no_enviado` dentro de una
  corrida que no esté completa, o `en_curso`, da `estimacion_codex_no_reproducible`.
- **Prueba obligatoria del contraejemplo de Astra (K16):** una corrida de medición con dos llamadas
  Codex de 10 y 1.000 tokens.
  - Un R13 que cita solo la primera fila (`por_clase` = (5·10+3)//4 = 13) →
    `estimacion_codex_no_reproducible`, porque las filas citadas ≠ todas las filas.
  - El R13 correcto da (5·1.010+3)//4 = **1.263** y valida.
- **Sin R13 no hay estimación,** y una versión con `puede_codex` no se produce: el runner rechaza
  (exit 3).

### R14 · Medición previa de Codex de producción (K5)

- **Entrada:** `execution/banco04_medir_codex.py main --version <ver> --sha <sha> --bloque 7
  --salida <S> --soul-plantilla <...> --max-tokens-codex <N> --max-tokens-claude <M>
  --corridas-por-clase <k=1>`.
  - Mismos aislamiento, manifiesto, `mundo`, `proveedores` y telemetría que `run_banco04` (reutiliza
    `_montaje_real`).
  - Exige `puede_codex == true`; si no, rechaza (exit 3).
- **Directorio propio:** `S/<ver>-medicion-codex/`, con su R1 (`proposito: medicion_codex`,
  **exento de R13**) y sus filas R4 (`fase: medicion_codex`). `_montaje_real` no exige R13 cuando
  `proposito == medicion_codex` (K5).
  - **No** escribe `resultado`: ni diagnóstico, ni borrador, ni material. Escribe solo R1, R4,
    suspensiones, recibos y R13. Nadie ve la calidad de esas corridas, y no se juzgan.
- **Asignación por clase, preregistrada (K16):**
  - para cada clase (`pequeno`, `fuga`, `voluminoso`), los `k` primeros casos de la clase en el
    orden `HMAC(semilla_hmac, "medicion_codex:" + case_id)`, repetición 1;
  - `k` y la lista resultante se escriben en `seleccion_medicion` del R1 de la medición, que es
    exclusivo y anterior a la primera corrida;
  - la puerta recalcula la lista desde `k` y la semilla y exige igualdad;
  - los casos custodiados entran con su cifrador, igual que en producción.
- **Recibos de completitud sin texto jurídico (K16):**
  - por corrida, `S/<ver>-medicion-codex/<caso>/rep-01.recibo.json`, exclusivo, escrito al
    terminar la corrida;
  - contenido: `{caso_id, clase, rep, estado: completo|fallo_producto|fallo_infraestructura|
    limite_de_uso, intentos: [{n, llamadas: [ids R4 en orden]}], n_llamadas_codex, n_llamadas_total,
    seq_primera, seq_ultima, manifiesto_sha256}`;
  - sin texto, sin error en claro y sin material; los casos custodiados solo llevan ids.
- **Presupuesto y control propios:**
  - `--max-tokens-codex` y `--max-tokens-claude` son techos de la medición, y el `ContadorCuota` de
    la medición los aplica con el control previo de §5.4;
  - además, sus filas llevan `bloque: 7` y cuentan en el presupuesto del circuito del Bloque 7
    (§3.3 E), dentro del tope de producción Codex (C20: 8 M − 6 M);
  - un evento sin cota detiene la medición (§5.1) y R13 no se escribe.
- **Salida:** solo si todas las corridas preregistradas tienen recibo `completo` y no hay filas
  desconocidas ni `en_curso`, escribe de forma exclusiva `S/<ver>-medicion-codex/estimacion_codex.json`
  (R13).
- **Orden:** R1 de la medición → corridas, R4 y recibos → R13 → R1 consumidor (que cita R13) →
  `run_banco04` de la versión.
- **Pruebas:**
  - E2E-12: recorrido positivo con `mundo=` y Codex enrutado;
  - redondeo: `max_c` = 1 → 2; 4 → 5; 5 → 7; 0 → 0 (este solo con recibo `completo`);
  - contraejemplo obligatorio 10 + 1.000 → 1.263, y el R13 que cita solo la fila de 10 →
    `estimacion_codex_no_reproducible`;
  - una fila R4 de la medición que no esté en `R13.filas_R4`, o un recibo que falte →
    `estimacion_codex_no_reproducible`;
  - una corrida con `fallo_infraestructura` → sin R13;
  - el R1 de la medición se escribe y arranca sin R13, y el R1 consumidor no arranca sin él;
  - una fila desconocida → sin R13;
  - el presupuesto de la medición alcanzado → suspensión y sin R13.

---

## 3 · La puerta

### 3.1 Firma

- **Pública:** `puerta.decidir(*, dir_nuevo: Path, dir_base: Path, custodia: Path, cadena: Path) -> dict`.
- **Línea de comandos:** `execution/banco04_decidir.py veredicto --nuevo <S/0.4> --base <S/0.3.3>
  --custodia <MIA_BANCO04_CUSTODIA> --cadena <MANIFIESTO_CADENA.json> --salida <VEREDICTO.json>`.
- **Prohibido en la firma:** cualquier parámetro de conclusión, agregado, etiqueta, semilla,
  inventario, `R`, techo, atribución, recibo, `suspendido` o recuento.
- **Manifiesto de custodia (decisión del director, v6).**
  - La puerta **pública** solo acepta el `custodia_manifest.json` del repo.
  - Lo pasa de forma explícita a `custodia.abrir(manifest_path=RUTA_MANIFIESTO_REPO)`, con una
    constante de `puerta.py` calculada desde la raíz del repo. **Ninguna ruta se redirige en tiempo
    de llamada:** sustituir `custodia._MANIFEST_PATH` o `custodia.cargar_manifiesto` no tiene efecto
    en la puerta.
- **Único parámetro adicional, solo de Python y solo para pruebas:** `_prueba: PruebaPuerta | None`.
  - Firma: `PruebaPuerta(manifiesto_custodia: Path | None = None, desproteger: Callable | None =
    None, directorio_instantaneas: Path | None = None, aceptar_dobles: bool = False,
    aceptar_arbol_sucio: bool = False)`.
  - Cada relajación se activa **por separado** y no hay ninguna más:
    1. `manifiesto_custodia` y `desproteger`: abrir una custodia de prueba con su manifiesto y su
       desprotector DPAPI de prueba;
    2. `directorio_instantaneas`: leer las instantáneas de acreditación de un directorio de prueba
       en lugar de `backend/mia/eval/banco04/telemetria_acreditada/` (§4.4);
    3. `aceptar_dobles`: aceptar `dobles: true` en R1 y R8;
    4. `aceptar_arbol_sucio`: aceptar `arbol_limpio: false` en R1.
  - Con **cualquier** relajación activa, el resultado lleva `"modo_prueba": true` y
    `resumen_publicable` se niega a publicarlo.
  - **El veredicto se calcula igual**, para que el esqueleto o F17 puedan mostrar `aprueba` con
    `modo_prueba: true`.
  - `banco04_decidir.main(argv, *, _prueba=None)` acepta el mismo objeto **solo como parámetro de
    Python**; la línea de comandos no lo expone (E2E-7).
- **Salida: dos veredictos separados** (decisión de Pipe «Separar calidad y cuota»):
  `{veredicto: aprueba|reprueba|no_certificable, motivos: [{codigo, detalle}], filas_rojas: [..],
  condiciones: [{id, valor, umbral, estado: cumple|no_cumple|no_aplica|sin_dato, fuentes:
  [rutas+sha256]}], comparativas: [...], cuota: {estado: certificada|estimada, resultado:
  cumple|excede|null, condiciones: [{id, intervalo: [min, max], umbral, estado:
  certificada_cumple|certificada_excede|estimada, estimacion_puntual_inicial,
  estimacion_puntual_final}], consumo: {conocido, cotas_finitas, n_sin_cota}, aviso: str|null,
  intentos_sin_cota: [ids R4]}, entradas_leidas: [{ruta, sha256}], rotulo, modo_prueba}`.
  - `veredicto` es el **veredicto de CALIDAD**. No lee ninguna condición de cuota: solo las de
    calidad e identidad de §3.3 A, B, C y E (salvo el techo), y §3.4.
  - `cuota` es el **veredicto de CUOTA** de §3.3 D y §4.5. Las condiciones de cuota no entran nunca en
    `veredicto`, ni las de calidad en `cuota`.
- **Precedencia, por veredicto (C15 en v1.4):**
  - calidad: `no_certificable` > `reprueba` > `aprueba`;
  - cuota, **por intervalo** (§4.5):
    1. si alguna condición tiene su **mínimo** posible por encima del umbral → `certificada ·
       excede`, aunque otras sean inciertas;
    2. si no, y alguna condición tiene un intervalo que **cruza** el umbral → `estimada`
       (`resultado: null`), con los intervalos, las estimaciones puntuales y el aviso. Vale también
       con solo cotas finitas, sin ningún intento sin cota;
    3. si no, todas tienen su **máximo** posible dentro del umbral → `certificada · cumple`.

### 3.2 Procedimiento (orden fijo)

1. **Identidad:**
   - lee R8;
   - lee R1 de cada directorio y exige que su sha256 canónico sea igual a `versiones[].manifiesto_sha256`;
   - exige `arbol_limpio == true` y `dobles == false` (salvo `_prueba`, §3.1) (K12);
   - exige la **comparabilidad** de §3.3 A (K8);
   - exige `protocolo_version` y `protocolo_hash` iguales a los de `PR`;
   - `jueces.verificar_congelado(R8.hash_evaluador)` (J:1969).
2. **Custodia:** `custodia.abrir(PROPOSITO_MEDICION)` sobre el argumento `custodia`; el sha256 del
   manifiesto de custodia debe ser igual a `R8.custodia.manifiesto_sha256`. De ahí salen:
   - ids custodiados, casos, claves, jurisdicciones y semilla;
   - fragmentos por pieza: para los casos visibles, de `eval/cases.py` y `eval/holdout.py`; para los
     custodiados, de `custodia.casos()`.
3. **Inventario:** lo construye la puerta, nunca lo recibe:
   - `contingencia` sale de recalcular R11;
   - `extension` sale de recalcular R7 (§3.4);
   - después llama a `inventario_esperado` (M:918-954).
4. **Corridas:** para cada (versión, caso, rep) del inventario:
   - lee R2 (y R3 descifrado si el caso está custodiado);
   - valida su identidad;
   - reconstruye el paquete con `ceguera.preparar_candidato` (llave = `semilla_hmac`) y exige
     `paquete_sha256` y `candidate_id` iguales a los de R5;
   - reproduce el juicio (§3.3).
5. **Agregación interna** con las funciones de M (§7): `metricas_corrida` → `agregar_casos` →
   `agregar_estratos` → filas, comparativas y techo.
6. **Circuito:** reproduce R9 (§3.3, E).
7. **Orden de las llamadas y reanudaciones** (§5.4), techo del circuito (§3.4 del protocolo) y
   suspensiones.
8. **Veredicto.**

**Acumulación de motivos.** Ningún paso corta el cálculo. Cada fallo se añade como motivo y la
puerta sigue con todo lo que se pueda calcular, para que la salida exponga cada condición
recalculada. Hay dos excepciones, porque sin ellas no queda nada con qué calcular:

- no poder abrir la custodia;
- no poder leer R8.

`inventario_esperado` (M:929-930) lanza `ValueError` si no hay exactamente 4 ids custodiados. La
puerta lo convierte en `muestra_incompleta` y construye el inventario con los ids presentes.

### 3.3 Condiciones: de qué se recalcula cada una y qué da `no_certificable`

«Reproducir pasada 1» quiere decir, para una corrida:

1. `validar_pasada1` (J:576) sobre la salida cruda de Opus y de Codex, con el reintento tal como
   está guardado;
2. `particion` (J:798);
3. `alinear` (J:890);
4. `adjudicar` (J:1030) con un votante reproducido que devuelve el tercer voto guardado para esa
   unidad;
5. `recuento` (J:1068).

«Reproducir pasada 2» quiere decir:

1. `validar_pasada2` (J:1192);
2. `hechos_y_puntos_desde_clave` (M:1341) con el envío de la corrida;
3. `discrepancias_marcador` (M:1283) recalculadas sobre el texto completo;
4. `adjudicar_cobertura` (J:1143) con los votos guardados;
5. `adjudicar_negativas_falsas` (J:1087) con los votos guardados.

**A · Identidad y completitud.** Cualquier fallo de este bloque da `no_certificable`.

| Condición | Se recalcula desde | `no_certificable` si |
|---|---|---|
| Identidad de cada versión | R1 frente a R8 | falta R1; el sha256 difiere; `arbol_limpio != true`; `dobles != false`; protocolo distinto |
| **Comparabilidad entre versiones** (P:1023-1030, K8) | R1 de las dos versiones y R4 de las dos versiones | `cli_version` distinto entre base y nueva; `codex_cli_version` distinto si las dos tienen filas Codex; el **modelo principal** de un alias presente en las dos versiones es distinto entre ellas. Se comparan **identidades efectivas** (R4 `identidades_efectivas`, derivadas de `modelUsage` completo), nunca `modelo_solicitado`/`mia_model_hint`. Por alias presente en las dos versiones, el conjunto de identidades **principales** (`canonical_model`, `provider`) de sus filas cerradas con éxito tiene que coincidir. Las identidades auxiliares se publican y no se comparan. Si una fila cerrada con éxito de `claude_cli` o `codex_cli` no tiene identidad efectiva (sin `modelUsage`, sin `outputTokens` enteros, o Codex sin el campo de identidad acreditado en §4.4), su corrida da `no_certificable` (`identidad_efectiva_ausente`) (K8). El motivo es `base_no_comparable_reproducir`: §9.6 obliga a **volver a producir la 0.3.3** con el CLI y el modelo de la 0.4. **El R1 de la base puede ser del Bloque 0** (`bloque: 0`), con `R8.bloque = 7`: las salidas de 0.3.3 del Bloque 0 se rejuzgan en el Bloque 7 y solo se reproducen si cambió el CLI o el modelo (P:1026-1028) |
| Perímetro del parche del banco (K8) | R1.`rutas_modificadas_respecto_del_producto` de las dos versiones | en la base, alguna ruta fuera de `backend/mia/eval/` o `execution/`, literal de P:1023-1025; `docs/` **no** se admite. En la nueva, `sha_producto` = HEAD, así que la lista tiene que estar vacía; si no lo está, `no_certificable` |
| Evaluador congelado | `hash_evaluador()` actual = R8 = cada R5 = R9 | alguno difiere |
| Muestra | ids de `PR` + `custodia.casos()` | no son 17, o hay ids que no coinciden |
| Repeticiones | R2 presentes por (versión, caso) | el conjunto de reps no es exactamente {1..R} (+{R+1..R+5} si R7), hay duplicados, falta un R2 (incluido `limite_de_uso`, que no escribe R2, R:1041) |
| Texto juzgable | R2 `estado`, `diagnosis_full` y `draft_full` (H:738-740) | toda repetición del inventario sin texto completo: `completo` sin texto, **y también `fallo_producto`** (§4.1, K6). Las dos reglas rigen **a la vez**: el `fallo_producto` además cuenta como turno no completado en `turnos_completados` (§9.5), que se recalcula y se publica; el veredicto es `no_certificable` por precedencia (C15) |
| Caso y jurisdicción | R2 `caso_digest`, `jurisdicciones_fijadas` | el digest difiere del caso cargado; las jurisdicciones difieren de `custodia.jurisdicciones()` (custodiados) o de `[]` (visibles) |
| Ledger de la corrida | R2 `intentos[].llamadas` frente a R4 | falta un id; hay una fila con ese contexto que no está en la lista; contexto distinto; fila huérfana sin cerrar |
| Juicio completo | reproducción | falta una llamada que la reproducción pide; sobra una que no pide; el `prompt_sha256` no coincide; queda una salida no evaluada (estructural tras el reintento, J:1764); falta el tercer voto (`no_evaluada_tercer_voto`, J:1863) |
| R11 y R12 | se recalculan con `decidir_r` y `elegir_aprobaciones`. El consumo de la piloto que entra a `decidir_r` es, por corrida, **conocido + cotas finitas + estimación empírica inicial** de sus filas sin cota (§4.5), y R11 registra `estimaciones_usadas: [{fila, tokens, corte_seq, observaciones_sha256}]` y `corte_decision_seq` | ausentes o distintos del recálculo con esas mismas estimaciones congeladas. **Un intento sin cota en la piloto no da `no_certificable`** (v8): la decisión de R se reproduce con la estimación registrada, la selección de aprobaciones sigue siendo la de `elegir_aprobaciones` con `R1.semilla`, y el inventario sigue exigiendo **todas** las repeticiones 1..R de la R decidida |
| Codex en la piloto (K5) | R1.`puede_codex` y `cadenas_politica`, R13 y R4 | `puede_codex` sin R13, o un R13 que no se reproduce desde su fuente; filas R4 Codex de producción con `puede_codex == false`; una fila R4 de producción cuyo `alias` no está en `cadenas_politica["<tarea>|<escalada>"]` de su `tarea` y su `escalada`, lo que prueba que las cadenas registradas no eran las reales |

**B · Umbrales absolutos (§6.1).** Por corrida, la puerta construye la entrada de `metricas_corrida`
(M:266) solo desde la reproducción y desde R2, R4 y la custodia. `evaluada` deja de ser un parámetro
(M:333): se deriva de que las dos pasadas, la adjudicación y la cobertura estén completas.

| Fila | Se recalcula desde | `no_certificable` si | Efecto si falla |
|---|---|---|---|
| `afirmaciones_sin_respaldo` = 0 | recuento de la pasada 1 + `confirmadas` de las negativas falsas, sumado sobre todas las corridas completadas de todos los estratos | la reproducción está incompleta | reprueba |
| `fuga_jurisdiccion` = 0 | por corrida: `senal_fuga` (M:248) con el texto completo de R2 y `jurisdicciones_fijadas`, usando la copia vendorizada con la **regla de vinculación de §3.6** (P:479-482, C26), **o** una unidad confirmada en la que algún voto de defecto lleve el subtipo `fuga` (Q16). Es la regla congelada (señal **o** jueces); no hay adjudicación entre la señal y el juez (K2) | falta el texto o faltan las jurisdicciones | reprueba |
| `definitivo_con_lectura_insuficiente` = 0 | celda de §7.2 (M:280): alcance C8 + `estado_cobertura` (M:150) con decisivos de la clave, `cubierto` final y `disponible` + conducta de la pasada 2 | falta la pasada 2 | reprueba |
| `discordancias_sin_resolver` = 0 | `len(recuento.discordancias_sin_resolver)` (es una lista, J:1076; hoy M:341 hace `int()` sobre ella) + `discordancias` de las negativas falsas + cobertura con resultado `discordancia_sin_resolver` | si faltan los votos crudos, lo cubre el bloque A («Juicio completo»); cualquier discordancia > 0 | no certificable |
| `kappa_reservado` ≥ 0,6 | `evaluar_kappa(pares, conjunto="reservado")` sobre los pares de la reproducción de R9 | falta R9; kappa < 0,6 | no certificable |
| `kappa_salidas_reales` | `evaluar_kappa(..., "real")` sobre `pares_kappa` reproducidos de las corridas juzgadas de **las dos versiones** (§8.4, Q6) | se exige y queda < 0,6 | no certificable. Indefinido o inestable: se publica y no cuenta como ≥ 0,6 (§8.5) |
| `circuito_sobre_mutaciones_reservadas` | `evaluar_exigencias` (VJ:277) sobre la reproducción de R9 y la acreditación de R9. **v7:** la exigencia `consumo_certificable` (VJ:329-332) sale del circuito y pasa a la cuota: un intento sin cota en la validación pone máximo `∞` en su ámbito y va a la cuota por intervalo, no deja el circuito inutilizable | falta R9; `circuito_utilizable` falso por una exigencia de calidad | no certificable |
| `evaluacion_completa_dos_jueces` | resultado del bloque A, «Juicio completo», en las dos versiones | cualquier corrida del inventario sin juicio completo de los dos jueces (regla del bloque A) | no certificable |
| Cobertura de decisivos, lectura completa (media ≥ 0,90; ningún caso < 0,80) | `cubierto` final por hecho decisivo de la clave (pasada 2 y cobertura adjudicada), media sobre R por caso y media de casos por estrato | la clave del caso no se puede leer | reprueba |
| `aprobacion_sin_edicion_proxy` ≥ 0,60 | M:316-327: `completada` (R2 `estado`), defectos (fila 1), omisiones (puntos de la pasada 2), celda, `aprobaria_sin_editar`; `negativa_correcta` de la pasada 2 (R5, campo nuevo, con su validación) | falta la pasada 2; `negativa_correcta` contradice los puntos o los defectos de la corrida | reprueba |
| Cobertura de decisivos en lo leído (voluminosos ≥ 0,90) y suelo (≥ 0,34) | `disponible` (`envio_desde_material` sobre `material_turno.entraron_tramos`, M:78) + `cubierto` | si falta la pasada 2, lo cubre el bloque A. Sin medición del envío **no** se da `no_certificable`: nada está disponible (§7.2, M:124-125). La fila «en lo leído» no aplica si ningún decisivo del estrato está disponible (M:525), y se publica cuántas corridas no tienen medición | reprueba |
| Tasa de omisión en lo leído ≤ 0,20; utilidad ≥ 0,80 | puntos y resoluciones de la pasada 2 y su disponibilidad (M:282-307) | si falta la pasada 2, lo cubre el bloque A. La utilidad no aplica sin corridas limitadas (M:537). Un punto de la clave sin resolución en la pasada 2 lo rechaza el validador (J:1231), así que lo cubre el bloque A | reprueba |
| Incoherencia de la matriz (C4 con abstención) | `celda.aplica` (M:203, M:223) | alguna corrida cae en ella (decisión de este contrato: datos contradictorios) | no certificable |

**C · Comparativas (§6.2).**

| Condición | Se recalcula desde | `no_certificable` si | Efecto |
|---|---|---|---|
| Cada métrica en cada unidad | `comparar_metrica` (M:629) sobre los agregados recalculados, con `base_corridas` y `nuevo_corridas` por corrida en las unidades sin inferencia. Semilla del bootstrap: `custodia.semilla_hmac()` | falta un par (M:648); no hay datos donde la métrica aplica; `no_concluyente` sin R7 | `regresion` → reprueba |
| Pérdida por caso (materiales y decisivos) | `perdidas_por_caso` (M:693) | falta un par | reprueba |
| Decisivos estables | por (caso, hecho decisivo de la clave): fracción de corridas de la base (reps 1..R, Q7) con `cubierto` final; ídem en la nueva; luego `decisivos_estables_perdidos` (M:708). El inventario de hechos lo da la clave, nunca la entrada: un `{}` es imposible salvo un caso sin decisivos en la clave, que no aplica | falta la pasada 2 de alguna corrida | reprueba |
| Extensión | §3.4 | ver §3.4 | — |

**Entradas por corrida de las métricas comparativas sin productor en la v1 (K1).** Cada una se
calcula en la puerta, desde `puerta.decidir` → `registros.cargar_corrida` → la función indicada →
la entrada de `metricas_corrida` (M:266).

| Métrica (`metricas_corrida`) | Observación cruda (R2) | Función de la puerta | Ausencia o contradicción |
|---|---|---|---|
| `falsos_bloqueos` (M:365) | `resultado.verification` (informe del muro, H:709) y `resultado.material_turno.research_sources` (H:880) | `metricas.falsos_bloqueos_corrida(informe, fuentes)` = copia congelada de `harness.false_block_signal` (H:85-128) y de `verification.source_index`, `_tokenize_index` y `_backing_source_tokenized` (`agents/verification.py:286`, `:300`, `:307`) en `evaluador_congelado.py` (patrón C11, origen 7b9aaa0 con su sha256). Valor = `falsos_bloqueos > 0` | H:709 escribe `md.get("verification") or {}`, así que la clave siempre existe. Reglas:<br>(a) un informe no vacío sin `detalle` en forma de lista → `no_certificable`;<br>**Presencia de borrador (K1):** `hay_borrador` = `draft_full` es `str` (validado: si falta o no es `str`, la corrida ya es `texto_ausente`, §3.3 A) **y** `draft_full.strip() != ""`. Se recalcula desde el crudo; `reached_draft` (H:724) es derivado y no se lee.<br>(b) `{}` con `hay_borrador == false` → 0: sin borrador no hay marcas que juzgar;<br>(c) `{}` con `hay_borrador == true` → `no_certificable` (`informe_del_muro_ausente`): el muro tenía que correr.<br>Falta `research_sources`, o no es lista → `no_certificable`. La copia **no** trata un no-dict como `{}` (H:109). `resultado.false_block` (H:743) es derivado y no se lee. **Por verificar antes de implementar:** que todas las rutas que llegan al borrador en `agents/graph.py:2284-2458` escriban `md["verification"]`; `annotate_draft` devuelve `detalle` también sin citas (`agents/verification.py:1332`) |
| `cambio_de_motor` (M:366) | `resultado.model_fallbacks` (H:733), lista de `{task, desde, hacia, motivo}` (llm.py:478-484) | `metricas.cambio_de_motor_corrida(fallbacks, filas_R4)` = `len(fallbacks) > 0`. Cotejo: cada `hacia` aparece como `alias` de alguna fila R4 del intento final de la corrida | falta la clave; no es una lista de dicts con esas cuatro claves de texto; un `hacia` sin fila R4 |
| `turnos_completados` (M:364) | R2 `estado`, más `negativa_correcta` en los casos de riesgo | sin cambio de fórmula (M:316-317) | el `fallo_producto` cuenta como no completado **y** deja la corrida no certificable (bloque A) |
| `abstencion_injustificada` (M:361) | celda de §7.2 | ya definida (bloque B) | ya definida |

**D · Techo de cuota (§6.3) y C25.** Todo sale de R4, filtrado por versión y caso.

- **`corridas[rep]`** = filas `fase=produccion` de (caso, rep), con todos sus intentos.
  - `tokens` = Σ de `uso_validado.total` de las filas `proveedor_cuota=claude` conocidas, más la
    `cota.tokens_cota_superior` de las desconocidas.
  - `tokens_codex`: ídem con `codex`.
  - `inferencias`: Q2. Por defecto, el número de filas `claude` de la corrida.
- **`aprobacion`** = filas `aprobacion_aprobar` y `aprobacion_trabajos` del caso. Las filas
  `aprobacion_turno` (el turno reproducido) **no** entran en el consumo decisorio: rige «R turnos más
  aprobación» (P:453-455, P:587; §8.4, Q3 revocada). Sí cuentan en el presupuesto del circuito
  (§3.4 del protocolo) a través de R4, en el bloque E.
- Después se llama a `techo_cuota` (M:772), adaptado a este esquema (§7). Su `R_por_caso` se coteja
  con el inventario.

| Condición | `no_certificable` si | Efecto |
|---|---|---|
| Total agregado, ponderado por caso, extremo por caso y extremo entre repeticiones (Claude 1,25×; Codex 0,50×) e inferencias | **ninguna: es veredicto de CUOTA, no de calidad.** Cada condición se evalúa **por intervalo** (§4.5): `certificada_cumple` si su máximo posible cumple, `certificada_excede` si su mínimo posible excede, y `estimada` si cruza el umbral, también con solo cotas finitas. Una fila con `fase=sin_contexto` o `caso_id` nulo suma a los intervalos de todos los casos posibles (al mínimo de ninguno y al máximo de todos). Las inferencias son recuentos de intentos, y su intervalo es degenerado | cuota según el intervalo |
| C25: atribución de subidas > 10 % | `usage_by_node` por ámbito = las **mismas filas** de R4 agrupadas por `nodo` (nulo → `(sin nodo)`). La igualdad con el consumo medido (M:1027-1029) se cumple por construcción. El nodo atribuido es el de mayor aumento. La subida es atribuible si ese nodo está en `atribucion_preregistrada` de R1 de la versión nueva (con su sha256 igual al de R8) **y** alguna métrica suya tiene veredicto `mejora` (recalculado) en una unidad del mismo grupo (a)/(c) | CUOTA. Si la subida solo resulta de la estimación, la atribución se publica como estimada. Si el sha256 del mapa no coincide con R8, **calidad** `no_certificable` (identidad, `atribucion_mapa_no_coincide`). Un mapa ausente deja la subida no atribuible | cuota: `excede` (no atribuible) |

**E · Alcance C8, fuga §5.7, kappa y estabilidad, y circuito §3.4.**

| Condición | Se recalcula desde | `no_certificable` si |
|---|---|---|
| Alcance C8 | `alcance_desde_fragmentos` (M:1306) con los fragmentos por pieza de la definición del caso y `envio_desde_material(material_turno)`. Cuenta como medido **solo** si `material_turno.fragmentos_en_prompt.medido` y `.completo` son verdaderos (H:858-861). Así se cierra la medición parcial de B3 | nunca por esto. Sin medición el alcance es insuficiente (§7.2), y se publica cuántas corridas no la tienen y en cuántas difiere de `alcance_lectura` |
| Fuga §5.7 | fila 2 del bloque B, con la regla de vinculación de §3.6. Sus pruebas obligatorias cierran R3-N2 del área C | falta el texto o las jurisdicciones |
| Estabilidad (§8.6) | conjuntos de §3.7: población original y población de la extensión, por separado y por versión; etiqueta `estabilidad`; `acuerdo_estabilidad` (J:921) sobre la reproducción de las dos pasadas 1 de Opus | falta la segunda pasada de un elegido, o existe una de un no elegido de su población (Q15) |
| Codex en la pasada 2, 15 % (§8.2) | ídem con el 15 % y la etiqueta `codex_p2`; `acuerdo_pasada2_agregado` (J:1179), que se publica | ídem |
| Techo del circuito (§3.4) | Σ de **todas** las filas R4 con `bloque == R8.bloque` (incluidas las de los directorios de medición R14, las dos versiones, aprobaciones con su turno reproducido, juicio y validación) por proveedor. Las filas del Bloque 0 de una base reutilizada no cuentan en el Bloque 7, cada una con su clase de consumo. **Para suspender durante la corrida** se usa conocido + cotas + estimación empírica de las filas sin cota, para detener antes (§4.5); **nunca para certificar** | calidad `no_certificable` (incompleta) si queda una suspensión R6 activa sin una reanudación válida que la cite. El acumulado del circuito se publica en `cuota` |
| Orden tras un consumo desconocido sin cota | §5.4 | una llamada de juez, de validación o de Codex de producción lanzada con un evento sin cota no autorizado para su etapa y versión |

### 3.4 Comparativa previa y extensión

1. La puerta toma `R_original` por caso de `PR.repeticiones(caso, ids, contingencia)`, con la
   contingencia recalculada desde R11.
2. Con las corridas **de reps 1..R_original** de las dos versiones, y solo con ellas, recalcula los
   agregados por caso y `comparar_metrica` para cada métrica y unidad. Esa es la **previa**.
3. Si ninguna previa es `no_concluyente`:
   - la existencia de R7 da `no_certificable` (`extension_sin_causa`);
   - la existencia de un R2 con rep > R_original da `no_certificable`.
4. Si alguna es `no_concluyente`, exige R7 y que, campo a campo, sea igual a lo recalculado:
   - `metricas` (métrica, unidad y previa completa, con `diferencia_por_caso` comparada con
     tolerancia 1e-9);
   - `casos` = la selección determinista de abajo (K9; sustituye a R-7);
   - `corridas_por_caso` = 5.

   **Selección de casos con orden total reproducible (K9):**
   - Sea N el conjunto de pares (métrica, unidad) con previa `no_concluyente`.
   - Para cada caso c de las unidades de N:
     - d_m(c) = `sentido` × (media nueva − media base) sobre las reps 1..R_original, calculado en
       **`Fraction` exacta** desde los valores por corrida, nunca desde los `float` de
       `diferencia_por_caso`;
     - contribución(c) = Σ_{(m,u)∈N, c∈u} max(0, −d_m(c)).
   - Se toman los casos con contribución > 0.
   - Orden: contribución descendente; a igualdad, número de métricas de N con d_m(c) < 0,
     descendente; a igualdad, `case_id` ascendente en orden de código Unicode.
   - Se quedan los primeros min(5, n).
   - `casos_para_extension` (M:677) se sustituye por esta función (`metricas.casos_extension`), que
     recibe los valores por corrida y no la comparativa.

   Si no coincide, `no_certificable`. Si falta R7, `no_certificable` (`no_concluyente_sin_extension`).
5. Exige en **las dos versiones** los R2 de los reps R_original+1..R_original+5 de esos casos, con
   `extension_sha256` = sha256 de R7, y juzgados. Exige que no exista ningún otro rep adicional.
6. El veredicto final de esas métricas se calcula con **todas** las corridas (1..R+5) y pasa por
   `veredicto_tras_extension` (M:684). El recibo del llamador desaparece (se elimina `_motivos_recibo`,
   M:1086-1116). Con esto se cierra R3-N2 del área A.

**Quién escribe R7.** `banco04_decidir previa`, que usa los mismos internos de la puerta. La
selección de casos no es libre: la puerta la recalcula.

### 3.5 Informe del Bloque 0: línea base de una sola versión (K11)

- **Comando:** `execution/banco04_decidir.py linea-base --base <S/0.3.3> --custodia
  <MIA_BANCO04_CUSTODIA> --cadena <MANIFIESTO_CADENA.json> --salida <INFORME_LINEA_BASE.json>`.
- **Firma:** `puerta.medir_linea_base(*, dir_base: Path, custodia: Path, cadena: Path) -> dict`.
  - Mismas prohibiciones y el mismo `_prueba` de §3.1.
  - Exige `R8.bloque == 0`, `R8.bloque_0_linea_base == true` y una sola versión `rol: base`.
- **Productor:** los mismos pasos 1–7 de §3.2 sobre una versión. No calcula comparativas (§6.2),
  pérdidas por caso, decisivos estables, extensión ni el techo comparativo de §6.3: los cinco
  necesitan las dos versiones.
- **Esquema** `banco04-linea-base/v1`: `{schema, version, rotulo, modo_prueba, estado:
  "medicion_completa" | "incompleta_no_certificable", motivos: [{codigo, detalle}], absolutos:
  [filas de §6.1 por estrato con valor, umbral y cumple], matriz_7_2: {celda: n_corridas},
  por_caso: {caso: {metricas de METRICAS_MEDIA (M:374), R, repeticiones}}, consumo: {por_caso:
  {consumo_agregado_caso, consumo_max_corrida, inferencias_suma, inferencias_max, codex},
  total_claude, total_codex, clases_de_consumo: {conocido, con_cota, sin_cota}}, circuito_bloque0:
  {acumulado_claude, acumulado_codex, techo_claude: 18000000, techo_codex: 5000000, reserva_juicio,
  suspendido: bool}, jueces: {kappa_real, estabilidad, acuerdo_codex_p2, circuito_reservado},
  cotas_ilustrativas, cuota: {estado: certificada|estimada, consumo_conocido, estimacion_empirica,
  aviso, circuito: cumple|excede}, entradas_leidas}`.
  - **No lleva el campo `veredicto`** de calidad comparativa.
  - **Sí lleva el veredicto de cuota separado** (`cuota`, §4.5) del consumo del Bloque 0 frente al
    techo del circuito (18 M / 5 M), **por intervalo** (§4.5): `certificada · cumple` si el máximo
    posible ≤ techo; `certificada · excede` si el mínimo (lo conocido) > techo; `estimada` si el
    intervalo cruza el techo.
  - Un incumplimiento de 0.3.3 se publica en la primera línea del resumen (DOC §9.7).
- **Separación:** el consumo del informe es **descriptivo**. El techo de §6.3 solo existe en
  `decidir`, con las dos versiones. El presupuesto del circuito del Bloque 0 (§3.4 del protocolo)
  es una condición de completitud: si se alcanza, `incompleta_no_certificable`.

### 3.6 Regla de vinculación de la negación en la señal de fuga (K2; regla congelada P:479-482 y C26)

Sustituye `_clausula_de` y `_mencion_negada` en `evaluador_congelado.py:437-472`. Es determinista y
entra en la huella del evaluador. Para cada cita que detecta `scan_citations` en el texto completo:

1. **Oración:** la de `_SENTENCE_SPLIT` (`evaluador_congelado.py:419`) que contiene la cita.
2. **Incisos:** se retira todo tramo entre dos comas consecutivas de la oración que no contenga
   ninguna cita, y toda subordinada que empieza por `que`, `cuyo`, `el cual`, `quien` o `donde`
   después de una coma, hasta la siguiente coma o el final de la oración, si no contiene la cita.
   - Las posiciones de la cita se conservan.
   - Una coma dentro de la cita no cuenta.
3. **Proposiciones:** sobre lo que queda, se corta en `;`, en `,` y en los conectores
   `y|e|o|pero|aunque|mientras|sino|porque|pues|ya que|dado que|puesto que|si bien|no obstante|sin
   embargo|pese a que|a pesar de que` **solo** si el tramo que sigue hasta el corte siguiente
   empieza por «no» o contiene un verbo conjugado según `jueces._tiene_verbo` (J:248; heurística
   versionada C10). Un conector seguido de un sintagma nominal no corta, así que la negación
   alcanza a los objetos coordinados.
4. **Negación vinculada:** la cita está negada si se cumplen las tres condiciones:
   - su proposición contiene una expresión de `_NEGATION_NEAR_CITATION`
     (`evaluador_congelado.py:405-416`);
   - ninguna proposición posterior de la misma oración que empiece por verbo conjugado (sujeto
     elíptico: hereda el de la proposición de la cita) carece de negación;
   - ningún **inciso retirado en el paso 2** que sigue a la cita, o la modifica, contiene un verbo
     conjugado (`jueces._tiene_verbo`) sin una expresión de negación. Un inciso así predica algo
     afirmativo de la cita y anula la negación de la proposición principal.

   Un inciso sin verbo conjugado, como «por falta de fuentes» en V3, es neutro.
   - Ejemplos: «La Ley X no consta pero es aplicable» no está negada; «La Ley X, que es aplicable,
     no consta en el expediente» tampoco.
5. **Fuga:** hay fuga si queda al menos una cita no negada y `jurisdicciones_fijadas == []`.

**Pruebas obligatorias** (sobre `jurisdiction_leak_signal` vendorizada y hasta `metricas_corrida`;
todas en rojo antes de implementar):

| # | Texto | Exigido |
|---|---|---|
| V1 (R3-C-N2) | «La Ley 100 de 1993 es aplicable al caso y no consta la fecha del contrato» | fuga |
| V2 (R3-C-N2) | «La Ley 100 de 1993, que no consta en el expediente, es aplicable al caso» | fuga |
| V3 (R3-C-N2) | «No puedo verificar, por falta de fuentes, la Ley 100 de 1993» | sin fuga |
| V4 (R2-C-N4) | «La Ley 100 de 1993 es aplicable al caso, aunque no consta la fecha del contrato» | fuga |
| V5 (R2-C-N4) | «No consta que la Ley 100 de 1993 sea aplicable» | sin fuga |
| V6 (control N-1, test_banco04_juicio.py:2320) | «la numeración Ley 4137 no corresponde a ninguna ley…» | sin fuga |
| V7 (sujeto elíptico) | «La Ley 100 de 1993 no consta en el expediente pero es aplicable» | fuga |
| V8 (coordinación nominal) | «No puedo verificar la Ley 100 de 1993 ni la Ley 200 de 1995» | sin fuga |
| V9 (inciso afirmativo) | «La Ley 100 de 1993, que es aplicable al caso, no consta en el expediente» | fuga |

**Residual declarado.** Es una heurística sintáctica del español. Lo que la señal no vea lo
cuentan los jueces en la misma fila 2 (señal **o** jueces), y cada corrida publica `detalle` y
`detalle_negadas` (`evaluador_congelado.py:474-500`). El defecto de `scoring.py` en el producto
sigue fuera del banco.

### 3.7 Poblaciones de las submuestras (K9)

- **Por versión y por población** se aplica `seleccionar_con_semilla` (J:1919), con dos cambios:
  - un parámetro nuevo `etiqueta`, que sustituye el prefijo fijo `"submuestra:"` (J:1922), para
    que la estabilidad y la pasada 2 de Codex no compartan el mismo orden;
  - la población es una lista cerrada de `candidate_id`.
- **Población original:** candidatos de las reps 1..R_original de la versión. Se selecciona una
  sola vez, antes de cualquier extensión, y **no cambia** después.
- **Población de extensión:** candidatos de las reps R_original+1..R_original+5. Tiene su propia
  selección (⌈10 %⌉ y ⌈15 %⌉ sobre esa población) con las etiquetas `estabilidad-ext` y
  `codex_p2-ext`.
- Las pasadas ya hechas de la población original nunca se vuelven «sobrantes».
- Etiquetas: `estabilidad`, `codex_p2`, `estabilidad-ext` y `codex_p2-ext`. La puerta recalcula los
  cuatro conjuntos y exige exactamente esos registros.

### 3.8 Vocabulario cerrado de códigos de motivo de `no_certificable`

- La puerta (y `medir_linea_base`) solo emite estos códigos. `detalle` es libre, con caso, rep,
  ids y rutas.
- Un código fuera de la lista es un error de implementación, con su prueba.
- Las pruebas de §6 asertan el código, nunca el texto.

| Código | Condición (sección) |
|---|---|
| `cadena_ilegible` | falta R8 o no valida su esquema (§3.2) |
| `custodia_no_coincide` | no se abre, o el sha256 de su manifiesto difiere de R8 (§3.2) |
| `identidad_version` | R1 ausente, sha256 distinto de R8 o protocolo distinto (§3.3 A) |
| `arbol_sucio` · `corridas_con_dobles` | `arbol_limpio != true` · `dobles != false` (§3.3 A) |
| `evaluador_no_congelado` | huella del evaluador distinta en el código, R8, R5 o R9 (§3.3 A) |
| `base_no_comparable_reproducir` · `perimetro_parche` | §3.3 A, comparabilidad · perímetro |
| `muestra_incompleta` | casos o repeticiones que faltan respecto del inventario (§3.3 A, §6.1) |
| `repeticiones` | duplicado o identidad de rep incoherente (§3.3 A) |
| `texto_ausente` | corrida sin texto completo, incluido `fallo_producto` (§3.3 A) |
| `caso_digest_no_coincide` · `jurisdiccion_no_coincide` | §3.3 A |
| `ledger_incompleto` · `ledger_sin_contexto` | §3.3 A · §3.3 D |
| `juicio_incompleto` · `juicio_contradictorio` · `paquete_no_coincide` · `rep_sha256_no_coincide` | §3.3 A, reproducción |
| `decision_r_no_coincide` · `plan_aprobaciones_no_coincide` | R11 · R12 (§3.3 A) |
| `codex_piloto_sin_estimacion` · `codex_sin_permiso` · `cadenas_no_coinciden` | §3.3 A, «Codex en la piloto» |
| `discordancias_sin_resolver` · `incoherencia_matriz` · `negativa_correcta_contradictoria` | §3.3 B |
| `kappa_reservado` · `kappa_real` · `circuito_no_utilizable` · `validacion_reservada_ausente` · `reservado_retirado` | §3.3 B, R9 |
| `falsos_bloqueos_sin_dato` · `informe_del_muro_ausente` · `cambio_de_motor_contradictorio` | §3.3 C (K1) |
| `sin_dato` · `par_faltante` | métrica sin dato donde aplica; par de versiones faltante (§3.3 B y C) |
| `no_concluyente_sin_extension` · `extension_sin_causa` · `extension_no_coincide` · `extension_incompleta` | §3.4 |
| `submuestra_incompleta` | §3.3 E, §3.7 |
| `techo_sin_aprobacion` · `atribucion_mapa_no_coincide` | calidad: completitud e identidad (§3.3 D) |
| `consumo_desconocido_sin_cota` | **solo** código de parada en tiempo de ejecución (`CuotaAgotada`, `ParadaCodexProduccion`) y causa del máximo `∞` del ámbito en la cuota (que se resuelve por intervalo, §4.5). **Nunca** es motivo de calidad `no_certificable` (v7) |
| `telemetria_contradictoria` · `telemetria_acreditada_no_coincide` | §4.1, §4.4 |
| `circuito_suspendido` · `llamada_tras_desconocido_sin_autorizacion` · `reanudacion_invalida` | §3.3 E, §5.4, R6 |
| `identidad_efectiva_ausente` | §3.3 A, comparabilidad (K8) |
| `acreditacion_ambigua` · `acreditacion_snapshot_distinto` | §4.4 (K4, K13) |
| `no_enviado_contradictorio` · `seq_incoherente` | §4.2, §5.4 (K15, K7) |
| `estimacion_codex_no_reproducible` | R13, R14 (K5) |
| `entrada_no_permitida` · `entrada_inaccesible` | §3.9 (K14) |
| `instantaneas_de_prueba` | R1 o R9 escritos con `instantaneas_dir=` y leídos sin `PruebaPuerta.directorio_instantaneas` (§4.4, v6) |

### 3.9 Inventario cerrado de `entradas_leidas` (K14)

La puerta registra en `entradas_leidas` **todo** lo que abre, con ruta y sha256, y **solo** puede
abrir lo siguiente. Abrir algo fuera de la lista da `no_certificable` (`entrada_no_permitida`), y no
poder abrir algo obligatorio, `entrada_inaccesible`.

1. **Crudos R1–R13**, y los registros de orfandad del punto 8, de los dos directorios de versión, de `<custodia>/salidas/<ver>/` y de
   `<custodia>/validacion/<identidad>/`.
2. **Fuentes de R13:** el directorio de medición `S/<ver>-medicion-codex/`, con su R1, **todas**
   sus filas R4, todos sus recibos y R13, cada uno con su sha256 cotejado (K16).
3. **Instantáneas de acreditación** citadas por R1, R8 y R9
   (`backend/mia/eval/banco04/telemetria_acreditada/<sha256>.json`, o
   `PruebaPuerta.directorio_instantaneas/<sha256>.json` con esa relajación), incluidas las entradas
   `fondo_cli` (§4.5), y **cada archivo de su `evidencia`**.
4. **Artefactos de custodia** que abre `custodia.abrir`: la llave DPAPI, los cifrados del
   manifiesto, `custodia_manifest.json` y los casos, claves, semilla, jurisdicciones y mutaciones
   del reservado vigente. Se registran por id de artefacto y `sha256_cifrado`.
5. **Definiciones de los casos visibles:** `backend/mia/eval/cases.py` y `holdout.py`, con su sha256
   y el `case_digest` de cada caso.
6. **Archivos del evaluador congelado** (`ARCHIVOS_EVALUADOR`, J:1931-1945, más los módulos nuevos
   de §1.2) y los prompts de los jueces (J:1954-1955), para `verificar_congelado`.
7. **`telemetria_acreditada/`** (el índice del directorio) y `protocolo.py`, para la versión y la
   huella del protocolo.
8. **Registros de orfandad** (K7). Se adscriben a **R4**, como complemento de la fila que declaran
   huérfana:
   - **ruta:** `S/<ver>/orfandades/<seq_deteccion>.json` de cada directorio de versión y de medición
     (R14);
   - **identidad:** `id_fila` (id de la fila R4) y `seq_deteccion`, único en el bloque;
   - **huella:** sha256 del archivo, que se registra en `entradas_leidas`.

   La puerta exige que cada uno cite una fila R4 existente con `estado == en_curso` y
   `seq_cierre == null`, y que no haya dos registros de orfandad para la misma fila. Si no,
   `seq_incoherente`.

No se abren derivados (`*.derivado.json`, `estado_banco.json`, `aprobaciones_estado.json`,
`usage_by_node.*.json` ni los `VEREDICTO.json` o `INFORME_LINEA_BASE.json` previos). Abrirlos da
`entrada_no_permitida`.

---

## 4 · Telemetría: una sola regla de uso

### 4.1 Regla (`telemetria.uso_validado(familia, uso_crudo) -> UsoValidado`)

La aplican la captura de producción (§4.2) y los runners de juez, que sustituyen
`ControlCuotaJueces.despues` y `tokens_conocidos`, J:1375-1472. **Componentes ausentes ⇒
`consumo_conocido = false`, nunca cero.**

| Familia | Componentes obligatorios (entero ≥ 0) | Opcionales: si vienen, válidos | Total |
|---|---|---|---|
| `claude_cli` | `input_tokens`, `output_tokens`, `cache_creation_input_tokens`, `cache_read_input_tokens`. Un componente de caché ausente vale 0 **solo** si una entrada única de §4.4 para esa `cli_version` exacta **y esa `firma_comando`** acredita `omitido_si_cero` para ese campo; si no, la llamada es desconocida | — | suma de los cuatro |
| `codex_cli` | por evento `usage`: entrada (`input_tokens` \| `prompt_tokens`) y salida (`output_tokens` \| `completion_tokens`); `cached_input_tokens` va dentro de la entrada y no se suma | `total_tokens` | **un evento:** máx(entrada + salida, `total_tokens`). **Varios eventos:** según la entrada única de §4.4 para esa `cli_version` y esa `firma_comando`: `acumulado` → el del último evento; `incremental` → la suma. Sin entrada → desconocido |
| `api` | `prompt_tokens`, `completion_tokens` | caché passthrough (`cache_*_input_tokens`) y `prompt_tokens_details.cached_tokens` | `total_tokens` válido, o prompt + completion, + `cache_creation` |
| `local` | ídem `api` | ídem | ídem; `proveedor_cuota` sigue la regla de R4 |
| `embeddings` | caracteres de los textos (estimación declarada, SG:1294) | — | `proveedor_cuota = ninguno`: no cuenta en ninguna cuota |

- **Fallo (excepción):** siempre `consumo_conocido = false`, con la cota de SG:1209-1243.
  - En `cli-*` (Claude y Codex) la cota es siempre `null`: desconocido sin cota. La fila lleva su
    `estimacion_empirica` (§4.5).
- **Éxito con un componente ausente o inválido:** `consumo_conocido = false`, con
  `componentes_ausentes`. Cota: `cli-*` → `null`, con su `estimacion_empirica`; `api` → entrada
  estimada + `max_tokens` aplicado.
- **`uso_crudo` ausente:** desconocido.
- **Fila huérfana:** se clasifica según R4, «clasificación única de las huérfanas»: si fue enviada, desconocida sin cota; si no, no enviada.
- **Prohibido:** registrar una llamada como éxito con 0 tokens. Ese es el patrón de SG:1268-1274 que
  reprodujo R3-N2 del área B. `note_call` puede seguir sumando para el saldo en USD, pero el ledger y
  `ContadorCuota` se alimentan solo de `uso_validado`.

### 4.2 Captura en el eval (no es producto)

- **`SG._guarded_invoke` (SG:1126-1275):**
  - **Garantía de compromiso irrevocable (K7; decisión expresa del director, 2026-10-12; se recoge
    en la aclaración C27 del protocolo, junto con la decisión de Pipe sobre la reanudación, §8.4 Q13):**
    - el punto de compromiso de una llamada es su `seq_envio`, escrito bajo el cerrojo;
    - una llamada B con `B.seq_envio < A.seq_cierre`, siendo A una llamada cerrada sin cota (o
      `< A.seq_deteccion` si A es una huérfana enviada), es **legítima** aunque B invoque físicamente
      al proveedor después de que A cierre;
    - lo prohibido es **registrar un `seq_envio` posterior** a ese cierre o a esa detección sin una
      reanudación válida que lo cubra.
    - **Residual declarado:** B puede consumir cuota después de que se produzca el evento
      desconocido de A. Quedó comprometida antes de que se conociera, y su consumo cuenta en el techo
      como cualquier otro, con su clase.
    - La garantía **no** es «nada se invoca después de un evento desconocido», sino «nada se
      **compromete** después de un evento desconocido no autorizado».
  - **Orden fijo de una llamada (K7, K15):**
    1. **toma el cerrojo de §5.4 y no lo suelta hasta el paso 4:**
       - registra las orfandades que detecte (§5.4);
       - hace el control previo (lee R4, R6 y los registros de orfandad);
       - asigna `seq_inicio` y escribe R4 `en_curso` con `t_envio_utc = null`, el contexto y la cota;
    2. **bajo el mismo cerrojo**, `check_and_reserve` (SG:1150-1151; en el banco,
       `GuardBanco.check_and_reserve`, R:1590-1601), que no hace E/S de red. Si deniega
       (`SpendLimitExceeded`, `ParadaCodexProduccion` o `SpendControlUnavailable`), cierra la fila
       con `estado: no_enviado`, `motivo_codigo` y `seq_cierre`, suelta el cerrojo y la excepción
       sigue su curso;
    3. **bajo el mismo cerrojo**, abre la ranura de captura (§4.3) y escribe de forma atómica
       `t_envio_utc` y `seq_envio`. Ese es el **compromiso irrevocable**: desde ahí la llamada queda
       comprometida y ordenada frente a todo cierre y toda detección de orfandad;
    4. suelta el cerrojo y llama a `_original_invoke`. **La invocación real no se serializa:**
       sostener el cerrojo durante la llamada al modelo serializaría todo el circuito (decisión del
       director, 2026-10-12). Entre soltar y llamar no se toma ninguna decisión ni se lee ningún
       estado, pero otro proceso sí puede avanzar;
    5. toma el cerrojo y cierra con `seq_cierre`, `uso_crudo` = lo que dejó la ranura y
       `uso_validado`; en el camino de excepción, con la cota de SG:1209-1243.
  - **`no_enviado` (K15)** es un estado terminal comprobable: exige `t_envio_utc == null`, ranura
    vacía y `uso_crudo == null`.
    - No es consumo (ni conocido, ni con cota, ni sin cota), no es inferencia, no entra en U(C) ni
      en ningún techo, y no detiene nada.
    - Una fila `no_enviado` con `t_envio_utc` no nulo da `no_certificable` (`no_enviado_contradictorio`).
    - Huérfanas: se aplica la clasificación única de R4. `t_envio_utc` se escribe de forma
      duradera antes del envío, así que una huérfana con `t_envio_utc == null` no salió.
    - Los runners de juez siguen el mismo orden: el control de `ControlCuotaJueces.antes`
      (J:1432-1453) es el paso 1, y `CuotaAgotada` cierra la fila como `no_enviado`.
  - Para la familia `api`, `uso_crudo` es `resp.usage` serializado tal cual (lo devuelve el cliente
    OpenAI; el producto no lo colapsa). Para `claude_cli` y `codex_cli` con la ranura vacía,
    `uso_crudo` es `None` → desconocido.
  - El modelo efectivo, el esfuerzo y la parada salen de `resp.mia_model_hint` y `resp.mia_effort`
    (ya existen, `subscription_llm.py:283-284`, `codex_subscription_llm.py:308-309`) y de la ranura
    (`stop_reason`, `modelUsage`).
  - El nodo sale de `metrics.usage._node.get()` (`usage.py:71`). Es una lectura de un atributo
    privado desde `eval/`; idéntico en 7b9aaa0. Una prueba fija el nombre y falla en rojo si cambia.
- **`GuardBanco.check_and_reserve` (R:1590-1601):** antes de toda llamada Codex de producción
  consulta el contador reconstruido **desde R4 en disco**, incluidas las filas desconocidas de su
  propio proceso todavía no trasladadas (hueco de R:1590 señalado en el área B).
- **`ContadorCuota` (R:318-463):** se reconstruye solo desde R4 (sustituye a R:877-900 y
  R:1199-1221).
- **Al cerrar cada fila**, se comprueba el acumulado frente al techo; si lo alcanza, la suspensión es
  inmediata. Cierra el desborde por la última llamada (R3-N3 del área B).
- **`codex_cli_adapter` (alias `cli-codex-eval`; es código de `eval/`, se modifica directamente):**
  - `invoke_codex` (:384) deposita en la ranura **todas** las líneas de `completed.stdout` antes de
    `_parse_events` (:424);
  - `call_graph_cli` (:536-538) deja de convertir en `0` los `None` del parser.

### 4.3 Perímetro: el banco no cambia el producto. Intercepción desde `eval/` (K8)

**Decisión del director.** El banco no modifica ningún archivo del producto. La telemetría cruda se
captura con un envoltorio de instrumentación en `backend/mia/eval/banco04/telemetria.py`. El
envoltorio intercepta la salida cruda del CLI **antes** de que el producto la colapse en enteros, y
es transparente y restaurable, igual que los envoltorios de `harness.run_case` (H:609-687: se
instalan, se restauran siempre en un `finally` y no cambian lo que devuelve la función envuelta).

**Puntos de intercepción.** Son idénticos en 7b9aaa0 (0.3.3) y en HEAD (0.4): `git diff 7b9aaa0
HEAD` está vacío en los tres archivos. **El mismo envoltorio vale para las dos versiones.**

| Punto (archivo:línea) | Qué se envuelve | Qué captura | Por qué ahí |
|---|---|---|---|
| `backend/mia/agent/subscription_llm.py:255` (`_to_openai_response`), llamada en `:356` | se sustituye el atributo de módulo `subscription_llm._to_openai_response` por una función que guarda en la ranura `data` (el JSON completo del CLI: `usage`, `stop_reason`, `modelUsage`, `num_turns`) y devuelve **exactamente** el resultado de la original | `usage` sin colapsar, motivo de parada y modelos efectivos | es el único punto donde `call_cli` tiene el dict crudo; `call_cli` resuelve el nombre al llamar, así que el envoltorio lo ve. El colapso a enteros (`_n`, :260-262) ocurre dentro de la original, después de la captura |
| `backend/mia/agent/codex_subscription_llm.py:244` (`_usage`), llamada en `:302` | se sustituye `codex_subscription_llm._usage` por una función que guarda en la ranura `events` (todo el `stdout` JSONL) y devuelve el resultado de la original | todos los eventos `usage` en orden y la versión del CLI | la sobrescritura por evento (:254-256) ocurre dentro de la original |
| `backend/mia/eval/codex_cli_adapter.py:424` | es código de `eval/`: se modifica (§4.2) | ídem | — |
| `backend/mia/agent/subscription_llm.py:231` (`_build_command`), llamada en `:304` | se sustituye el atributo de módulo por una función que guarda en la ranura el `argv` que devuelve la original y lo devuelve sin cambios | comando efectivo de Claude, para `firma_comando` (K4) | es el único punto donde existe el `argv` real con `--model` y `--effort` |
| `backend/mia/agent/codex_subscription_llm.py:235` (`_command`), llamada en `:285` | ídem | comando efectivo de Codex (K4) | ídem |
| runners de juez (J:1571-1582 `ClaudeJuezRunner.comando`; J:1655-1665 `CodexJuezRunner.comando`) | código de `eval/`: guardan el `cmd` | comando efectivo del juez (K4) | — |
| `backend/mia/agent/subscription_llm.py:140` (`_sanitized_env`), llamada en `:326` | se sustituye el atributo de módulo por una función que llama a la original, guarda en la ranura los tres valores de `entorno_cli` y **devuelve exactamente** el mismo dict. **No añade, no quita y no cambia ninguna variable** (v7: se retira el fijado de reintentos de la v6; Astra, v6 (b)) | entorno efectivo del CLI, solo para publicarlo y versionar la estimación | es el único punto donde existe el entorno real del subproceso |
| `entorno_juez_claude` (J:1501-1512), código de `eval/` | sin cambios de conducta: el runner registra los tres valores de `entorno_cli` del dict que ya devuelve | ídem, para el juez | — |

**Ranura.** Una `ContextVar` de `telemetria` que abre `_guarded_invoke` antes de llamar a
`_original_invoke` y lee al volver. `call_llm` corre en un hilo con `asyncio.to_thread` y
`_guarded_invoke` llama a `_invoke` en el mismo hilo (llm.py:1077-1084), así que la ranura es
la de esa llamada.

**Instalación y restauración.** `telemetria.instalar()` como gestor de contexto dentro de
`_montaje_real`, igual que `spend_guard.install()` (R:1929):

- guarda los originales;
- comprueba con `is` que el atributo sustituido es el envoltorio (patrón de SG:1619-1625);
- los restaura en `finally`.

Fuera del proceso del banco nada cambia: el abogado nunca corre con el envoltorio.

**Pendiente del producto, fuera del banco (Bloque 1).**

- El colapso de `subscription_llm.py:258-271` y `codex_subscription_llm.py:244-263` hace que el
  panel del abogado (`turn_usage`, vía `_record_usage`, llm.py:905-913) muestre **0** cuando falta
  la telemetría.
- Se declara como defecto del producto, a corregir en el Bloque 1. El banco no lo corrige y no
  depende de él.

**Verificación obligatoria de la transparencia** (E2E-6):

1. `git diff` vacío en `backend/mia/agent/` y `backend/mia/metrics/` respecto del `sha_producto`.
   Además, `rutas_modificadas_respecto_del_producto` de R1 (§2) no contiene ninguna ruta de producto.
2. Con dobles de `subprocess.run`, `call_llm` devuelve, con el envoltorio instalado y sin él,
   objetos con `choices`, `usage`, `model`, `mia_model_hint` y `mia_effort` idénticos campo a
   campo, y `metrics.usage.record` bufferiza la misma fila.
   - El `env` que recibe el doble de `subprocess.run` es **idéntico**, sin excepciones (v7), y lo
     es también con `CLAUDE_CODE_MAX_RETRIES` igual a `0`, a `15` o ausente en el entorno de
     partida.
3. Al salir de `telemetria.instalar()`, incluso por excepción, todos los atributos de módulo sustituidos vuelven
   a ser los originales (`is`).
4. Siguen verdes `execution/test_rls.py`, `execution/test_gates_no_ciegos.py` y
   `test_eval_spend_guard`.

**Evidencia sobre la forma del JSON del CLI** (no acredita nada por sí sola; ver §4.4):
`output/validation/claude-opus55-{final,review}.json` traen en el nivel superior `stop_reason`
(«end_turn»), `num_turns`, `modelUsage` y `usage`, con los campos de caché distintos de cero. No
registran la versión del CLI.

### 4.4 Instantáneas inmutables de acreditaciones de telemetría (K4, K13; §8.4, Q9)

**Regla única de congelamiento (K13).**

- Una acreditación vive en una **instantánea inmutable** direccionada por contenido:
  `backend/mia/eval/banco04/telemetria_acreditada/<sha256>.json`, donde el nombre es el sha256 de los
  bytes. Editarla cambia su nombre: es otra instantánea.
- **En las pruebas no se escribe nada bajo `backend/`** (decisión del director, v6).
  - Los `main` (`run_banco04`, `banco04_juzgar`, VJ, `banco04_medir_codex` y
    `banco04_medir_fondo_cli`) aceptan el parámetro de Python `instantaneas_dir=`, nunca un flag de
    línea de comandos.
  - Con él, el R1 o el R9 que escriben llevan `instantaneas_de_prueba: true`.
  - La puerta solo los acepta con `PruebaPuerta.directorio_instantaneas`. Sin ella, el resultado es
    `no_certificable` (`instantaneas_de_prueba`).
- No hay adiciones a una instantánea existente.
- **Todos** los R1 de la cadena y R8 citan **la misma** instantánea; si no, `no_certificable`
  (`acreditacion_snapshot_distinto`).
- Queda fijada desde el primer R1 que la cita.
- Si hace falta acreditar otro CLI, se crea otra instantánea, y eso exige R1 nuevos para todas las
  versiones de la cadena. Es lo mismo que ya exige la comparabilidad si cambia el CLI (§3.3 A).
- **R9** cita su propia instantánea. Sus filas de validación se interpretan con ella, y nada más.
- Las instantáneas **no** entran en la huella del evaluador (J:1931-1945): se ligan por cita. Así una
  acreditación nueva no invalida R9 ni el congelamiento de los jueces.

**Esquema** `banco04-acreditacion-telemetria/v2`: `{entradas: [{id, familia: claude_cli|codex_cli,
cli_version (exacta), firma_comando: {argv_normalizado, sha256}, conducta: {<campo de usage>:
"presente_siempre" | "omitido_si_cero"} | {eventos_usage: "acumulado" | "incremental"},
campo_identidad (solo Codex: ruta del campo del evento que lleva el modelo efectivo, o null),
evidencia: [{archivo, sha256, descripcion}], autor, fecha}]}`.

**Firma normalizada del comando (K4).** Parte del `argv` efectivo capturado por la ranura (§4.3):

- el ejecutable pasa a su nombre de archivo en minúsculas;
- las rutas temporales de `--output-schema` y `--output-last-message` (Codex) pasan a `<schema>` y
  `<salida>`;
- el `argv` del juez, igual;
- se conservan el orden y todos los demás tokens: modelo, esfuerzo, `-c` y `--safe-mode`.

`sha256` = sha256 del JSON canónico de `argv_normalizado`.

**Selección (la aplica §4.1):**

- candidatas = entradas con la misma `familia`, la misma `cli_version` exacta **y** el mismo
  `firma_comando.sha256` que la fila R4;
- 0 candidatas → todo componente ausente es **desconocido**;
- más de una candidata con conductas distintas → `no_certificable` (`acreditacion_ambigua`);
- varias con la misma conducta valen como una sola, con la `id` menor;
- una acreditación de **otro comando** de la misma versión nunca se aplica. Esto cierra el camino de
  ausencia→cero que señaló Astra: `omitido_si_cero` solo vale para la firma exacta acreditada.

**Validación en la puerta:**

- **integridad (todas las instantáneas citadas, por R1, R8 o R9):** el nombre de cada instantánea
  es igual al sha256 de sus bytes; si no, `telemetria_acreditada_no_coincide`;
- **igualdad (solo entre referencias R1 y R8):** `R8.telemetria_acreditada_sha256` es igual al de
  cada R1 de la cadena; si no, `acreditacion_snapshot_distinto`;
- **R9 se coteja solo con su propia referencia:** sus filas de validación se interpretan con la
  instantánea que cita `R9.telemetria_acreditada_sha256`, que puede ser distinta de la de R8 y R1
  sin ningún motivo (E2E-17) (K13);
- cada `evidencia.sha256` se comprueba contra su archivo, que entra en `entradas_leidas` (§3.9); si
  falta, la entrada no vale;
- la puerta recalcula la firma de cada fila desde el `argv_normalizado` y vuelve a aplicar la
  selección y la regla de §4.1. Exige el mismo `uso_validado` y la misma `acreditacion_aplicada`; si
  no, `telemetria_contradictoria`.

**Quién la produce:** el director, con UNA llamada mínima real por proveedor y por firma prevista
(R1 `firmas_previstas`), o con una salida guardada de la misma versión y la misma firma. Es
precondición de la piloto. **Este contrato no llama a proveedores.**

**Pruebas** (E2E-3 y E2E-16):

- varios eventos `usage` de Codex sin entrada → desconocido; entrada `incremental` → suma; entrada
  `acumulado` → último;
- caché ausente sin entrada → desconocido; con `omitido_si_cero` de la misma versión y la misma
  firma → 0 conocido; de otra versión → desconocido;
- **misma versión, comandos distintos:** una entrada `omitido_si_cero` para la firma A no se aplica
  a una fila con la firma B (otro `--effort`) → desconocido;
- dos entradas con la misma firma y conductas distintas → `acreditacion_ambigua`;
- instantánea con un nombre que no coincide con su sha256, o R1 que citan instantáneas distintas →
  `no_certificable`;
- Codex sin `campo_identidad` acreditado → `identidad_efectiva_ausente`.
---

### 4.5 Veredicto de cuota separado y estimación empírica (decisión de Pipe del 2026-10-12, «Separar calidad y cuota»)

**Revoca «Acotar y medir»** (v6). Motivo: Astra mostró que la cota de la v6 no era conservadora.

- la entrada se estimaba con una heurística (`memory/tokens.py`, caracteres/4; el juez,
  caracteres/3);
- la salida máxima depende del modelo, y 128 000 solo es el tope de los modelos que el CLI no
  reconoce;
- los diez reintentos son de **peticiones fallidas**;
- una muestra del fondo no fija un máximo;
- imponer `CLAUDE_CODE_MAX_RETRIES=10` alteraba la conducta si el entorno traía otro valor.

**Dos veredictos (§3.1).**

- **CALIDAD:** `aprueba` / `reprueba` / `no_certificable`, por las causas de calidad e identidad que
  ya existen.
  - **Sigue siendo certificable aunque haya intentos fallidos sin cota.**
  - Un fallo de una consulta solo cuenta para la calidad por sus efectos propios: turno no
    completado, fallo sin texto (`texto_ausente`), juicio incompleto, etc., como hasta ahora.
- **CUOTA, por intervalo** (decisión del director en la v8, que aplica el cambio (b) de Astra
  sobre la v7):
  - **Consumo como intervalo.** Todo consumo agregado (por corrida, por caso, total, por proveedor)
    es un intervalo `[mín, máx]`:
    - `mín` = la suma de lo **conocido**: una fila fallida, con o sin cota, puede no haber
      consumido nada;
    - `máx` = lo conocido + la suma de las **cotas finitas**, o `∞` si en el ámbito hay algún
      intento sin cota.
  - **Cociente** `r = A/B` de dos intervalos: `r_mín = A.mín / B.máx` (0 si `B.máx = ∞`) y
    `r_máx = A.máx / B.mín` (`∞` si `B.mín = 0` y `A.máx > 0`; 0 si `A.máx = 0`). El total
    ponderado por caso usa la media de los `r_mín` y la de los `r_máx` de los casos. Una condición
    absoluta (el techo del circuito) usa el intervalo directamente.
  - **Estado de una condición con umbral `u`** (la condición es `≤ u`):
    - `certificada_cumple` solo si `máx ≤ u`;
    - `certificada_excede` solo si `mín > u`;
    - `estimada` si `mín ≤ u < máx`: el intervalo cruza el umbral. **Vale también con solo cotas
      finitas y ningún intento sin cota.**
  - **Publicación de una condición `estimada`:** el intervalo, la estimación puntual (inicial y
    final, abajo) y el aviso literal: «Cuota estimada: el consumo real está en el intervalo
    publicado y cruza el umbral; la cifra puntual es una estimación empírica no garantizada y no
    certifica el techo».
  - **Estimación puntual** de un consumo = lo conocido + Σ `min(cota, estimación empírica)` de las
    filas con cota finita + Σ estimación empírica de las filas sin cota.
  - **Veredicto de cuota:** §3.1 (precedencia).

**El techo sigue gobernando la suspensión** durante la corrida (§3.4 del protocolo).

- El control previo y `ContadorCuota` suman conocido + cotas + **estimación empírica inicial**
  (congelada) de las filas sin cota, de forma conservadora, para detener antes.
- Esa suma nunca certifica nada.
- La parada por evento sin cota de §5.1 y la reanudación con autorización de Pipe **siguen
  iguales**, y C27 se mantiene.

**Estimación empírica de un intento sin cota (versionada, no garantizada):**

`estimacion = entrada_heuristica + salida_observada + fondo_observado`

- `entrada_heuristica`: la misma de SG:1209 (`estimate_tokens`), o `jueces.entrada_estimada`
  (J:1335) en los jueces. Se declara heurística.
- `salida_observada`: el máximo de `uso_validado.salida` de las filas **conocidas** del bloque con la
  misma familia, `cli_version` y `firma_comando`. Si no hay ninguna, el máximo observado de la
  familia, con `componentes.salida_observada_fuente = "familia"`.
- `fondo_observado`: el `fondo_max` de la entrada `fondo_cli` de la instantánea citada (misma
  familia, versión y firma). Sin entrada, `0`, con `fondo_observado_fuente = "no_medido"`.
- **Estimación inicial congelada (v8).**
  - Cada fila guarda `estimacion_empirica.inicial`, con su `corte_seq` (su propio `seq_cierre`, o
    `seq_deteccion` si es huérfana) y el conjunto exacto de observaciones usado.
  - Las observaciones son los ids de las filas conocidas con `seq_cierre < corte_seq` y la misma
    familia, versión y firma. Se registran con su sha256.
  - La puerta recalcula la inicial con **ese** conjunto y **ese** corte, y exige igualdad: con otro
    conjunto u otro resultado, `telemetria_contradictoria`. Un máximo observado **posterior** al
    corte no entra en la inicial y **nunca** produce contradicción.
- **Actualización final.** La calcula la puerta al decidir, con todas las observaciones conocidas
  del bloque. Se publica junto a la inicial (`estimacion_puntual_final`) y no se compara con nada
  guardado.
- **Uso de cada una:**
  - la **inicial** se usa para suspender (§3.4) y para la decisión de R (R11);
  - las dos se publican en la cuota;
  - ninguna certifica.

**Medición del fondo: se conserva como estimación empírica versionada.**

- Sigue la entrada `fondo_cli` de la v6: `banco04_medir_fondo_cli main`, paso 0 de la piloto, con
  instrumento `--debug-file` o proxy local, filas R4 `fase: medicion_fondo` y la entrada en una
  instantánea nueva con firma, versión del CLI, evidencia y sha256.
- Cambian dos cosas:
  - ya **no** hay factor de seguridad ni pretensión de máximo;
  - su ausencia no bloquea nada: solo marca `fondo_observado_fuente = "no_medido"`.

**Entorno del CLI.** Se **retira** el fijado de reintentos de la v6. El envoltorio **no toca** el
entorno: solo lo lee y lo registra (`entorno_cli`, §4.3). Si el entorno trae
`CLAUDE_CODE_RETRY_WATCHDOG` o unos reintentos distintos de los de fábrica, se publica junto a la
cuota. No cambia nada más.

**Codex.** Sus intentos sin cota caen en la misma regla (máximo `∞` en su ámbito, cuota por
intervalo), con su estimación
empírica (`fondo_observado` = 0, `no_medido`, mientras no exista una medición equivalente).

**Cambios de código respecto de la v6:**

- `telemetria.cota_intento_cli` se sustituye por `telemetria.estimacion_intento_sin_cota(fila,
  instantanea)`;
- `spend_guard.cota_salida_cli` vuelve a devolver `(None, motivo)` para todo `cli-*` (SG:1109-1123,
  como en HEAD);
- `ControlCuotaJueces.antes` reserva la estimación empírica cuando no hay cota (sustituye a
  `estimacion_reserva`, J:1364-1368, solo para suspender).

**Pruebas (E2E-19, obligatorias, sustituyen a las de la v6):**

1. **Calidad certificable con intentos sin cota.** F17 con un intento sin cota (un doble de Claude
   que omite `output_tokens`, y otro que agota el tiempo) → `veredicto: aprueba` y `cuota.estado:
   estimada`, con `consumo_conocido`, `estimacion_empirica` por intento, el aviso literal y la lista
   `intentos_sin_cota`.
2. **El mínimo excede.** Hay intentos sin cota en la nueva, y en un caso de la base sin filas sin
   cota el conocido de la nueva es > 1,25 × (conocido + cotas) de la base → `cuota: certificada ·
   excede`.
3. **Sin incertidumbre.** Sin cotas ni intentos sin cota: `certificada · cumple`, y en otra
   variante `certificada · excede`.
3b. **Contraejemplo de Astra (obligatorio).** Nueva = 100 conocidos; base = 10 conocidos + un intento
   con cota 90 (consumo real 1). Intervalo de la base [10, 100]; cociente [100/100, 100/10] =
   [1, 10], que cruza 1,25 → `estimada`. **Nunca `certificada · cumple`.**
3c. **Inverso (obligatorio).** Nueva = 100 conocidos + un intento con cota 1 000 (numerador
   sobredimensionado); base = 100 exactos. Cociente [1, 11] → `estimada`. **Nunca un falso
   `certificada · excede`.**
3e. **Evento sin cota solo en el denominador (obligatorio, Astra v8).** Nueva = 100 exactos; base =
   100 conocidos + un intento sin cota → base [100, ∞]; cociente [0, 1] ≤ 1,25 → `certificada ·
   cumple`. Su variante con el evento en el numerador da `estimada`.
3d. **Solo cotas finitas que no cruzan.** Nueva 100; base 92 + una cota de 5 → [100/97, 100/92] =
   [1,03; 1,09] ≤ 1,25 → `certificada · cumple`. (Base 92 y no 90: con 90 el máximo, 1,11, pasa el
   10 % de C25 y la subida exigiría atribución; ajuste del autor de pruebas aceptado por el director.)
4. **Suspensión conservadora.** Un acumulado conocido por debajo del tope, pero que con la
   estimación empírica lo supera → suspensión **antes** de la siguiente corrida. La misma corrida
   publica la cuota por intervalo; con los datos fijados (el evento está en la versión NUEVA (numerador) y el mínimo del cociente no supera el umbral, por lo que el intervalo lo cruza), `estimada`.
5. **El envoltorio no toca el entorno.** Con `CLAUDE_CODE_MAX_RETRIES` igual a `0`, a `15` o ausente,
   y con `CLAUDE_CODE_RETRY_WATCHDOG=1`, el `env` que recibe `subprocess.run` es idéntico al de la
   original, y `entorno_cli` registra esos valores.
6. **Codex sin cota** → `cuota: estimada` (datos fijados: el evento está en el numerador y el mínimo del cociente no supera el umbral, por lo que el intervalo lo cruza), `fondo_observado_fuente = "no_medido"`, calidad intacta.
7. **Estimación congelada.**
   - Editar `estimacion_empirica.inicial` de una fila o su conjunto de observaciones → calidad
     `no_certificable` (`telemetria_contradictoria`).
   - En cambio, una llamada **posterior** con una salida mayor (100 → 200) **no** produce
     contradicción: cambia solo la `estimacion_puntual_final`.
7b. **Piloto con un intento sin cota.** La corrida piloto de un caso tiene una fila sin cota.
   - `decision_r.json` se reproduce con la estimación inicial registrada, sin `no_certificable`.
   - El inventario exige las R decididas.
   - La calidad se certifica si lo demás está completo.
8. **Separación estricta.** Ninguna condición de cuota aparece en `veredicto.motivos`, y ninguna de
   calidad en `cuota.condiciones`.

## 5 · Reanudación (decisión de Pipe, 2026-10-12: «que se reanude con mi autorización»)

### 5.1 Qué detiene

**Solo detiene un evento desconocido SIN cota** (R4, «clases de consumo»; K7). Un desconocido con
cota acreditada no detiene nada: cuenta con su cota (P:464-468, P:1297-1300).

«Detener» quiere decir **no registrar ningún compromiso nuevo** (`seq_envio`, §4.2). Las llamadas
ya comprometidas antes del evento terminan y se contabilizan: es la garantía de compromiso
irrevocable, con su residual declarado en §4.2.

En cuanto exista en R4 una fila sin cota (cerrada, o huérfana enviada ya detectada) que **no esté
autorizada** para la etapa y la versión de la llamada siguiente (§5.4), sea del bloque o de
cualquier versión de `versiones_contador`:

- **El juicio:** ningún compromiso de juez nuevo (Opus ni Codex), incluida la estabilidad. El runner
  de juez lanza `CuotaAgotada` (código `consumo_desconocido_sin_cota`) en la sección crítica de
  §4.2, antes de registrar `seq_envio`. La fila queda `no_enviado` y se escribe una suspensión
  **nueva** R6 `suspensiones/juicio-<seq>.json` con `eventos`, aunque ya haya otras.
- **La validación (VJ):** igual, con `etapa: validacion`.
- **La producción Codex:** ningún compromiso `cli-codex*` nuevo de producción ni de aprobación.
  `GuardBanco.check_and_reserve` lanza `ParadaCodexProduccion` (R:1563-1568) con el mismo código.
- **La producción Claude puede seguir** (C19). Sus métricas de calidad se calculan y son
  certificables. La cuota se resuelve por intervalo (§4.5): `estimada` solo si su intervalo cruza el
  umbral.

### 5.2 Cómo se reanuda

- **Comandos** que escriben R6 `reanudaciones/<NNN>.json`, cada uno con `--reanudar-aprobado-por-pipe
  <REF> --etapas <lista> --versiones <lista>`:
  - `banco04_juzgar juzgar` (etapa `juicio`);
  - `run_banco04` (ya existe, R:1979; etapas `produccion` y `aprobaciones`);
  - `banco04_validar_jueces` (etapa `validacion`, R9).
- **Qué cubre:** exactamente las claves (ids R4) de los eventos **sin cota ya registrados** en el
  momento de la reanudación, con su `eventos_sha256`, y las suspensiones activas de esas etapas y
  versiones. Lo cubierto queda limitado a las `etapas` y `versiones` declaradas.
- **Requisito:** `<REF>` es obligatorio y no vacío. Es la referencia de la aprobación de Pipe. El
  agente no la genera: la recibe del director, que la obtuvo de Pipe en el chat.
- **Una reanudación no cubre eventos futuros ni otras etapas o versiones.**
- **Una reanudación nunca acredita consumo:** el evento sigue siendo sin cota y el techo sigue
  `no_certificable`.

### 5.3 Qué vuelve a detener

Cualquier fila sin cota nueva vuelve a detener según §5.1. También la detiene una fila ya existente
que no esté autorizada para la etapa y la versión de la llamada siguiente.

### 5.4 Qué comprueba la puerta

**Serialización del control y del envío frente al cierre (K7).**

- Hay un **cerrojo por bloque**: `S/.cerrojo-bloque<n>`, en la raíz común de los directorios de
  versión, con el patrón de `spend_guard._ledger_lock` (SG:481-546: archivo exclusivo y detección
  de cerrojo abandonado por PID, SG:430).
- Hay un contador `S/.seq-bloque<n>` de enteros crecientes que solo se lee y se escribe bajo el
  cerrojo.
- Bajo el cerrojo, y solo bajo él, ocurren:
  - (a) en **una sola sección crítica**: el control previo de una llamada, su `en_curso`
    (`seq_inicio`), `check_and_reserve` y el compromiso irrevocable (`t_envio_utc`, `seq_envio`), o su
    cierre `no_enviado`. El cerrojo **no se libera antes del compromiso** (K7); la invocación real queda fuera de la sección (§4.2);
  - (b) todo cierre de fila (`seq_cierre`);
  - (c) el registro de una suspensión o de una reanudación (su `seq`);
  - (d) el **registro de orfandad**: `S/<ver>/orfandades/<seq_deteccion>.json`, exclusivo, con
    `{id_fila, pid, t_envio_utc, seq_deteccion, detectada_por: id de la fila o proceso que la
    detectó}`.
    - Lo escribe cualquier sección (a) que encuentre una fila `en_curso` cuyo proceso ya no está
      (`spend_guard._pid_alive`, SG:430), y también la recuperación del arranque
      (`_recuperar_huerfanas`, R:851-874).
    - Una fila es huérfana **solo desde su `seq_deteccion`** (K7).
- Con eso, cada cierre y cada detección de orfandad ocurren **estrictamente antes o estrictamente
  después** del **compromiso** (`seq_envio`) de cualquier otra llamada.
  - «B controla, A cierra, B se compromete» es imposible: A no puede cerrar mientras B tiene el
    cerrojo entre el control y el compromiso.
  - «B se compromete, A cierra, B invoca» es posible y **legítimo** según la garantía de compromiso
    irrevocable (§4.2). No se serializa la invocación real.

**Llamadas comprobadas (K15).** Para cada fila C **enviada** (`t_envio_utc` y `seq_envio` no
nulos) con `fase` de juicio, validación o `medicion_codex`, o con `proveedor_cuota=codex` en
producción o aprobación.

- **Las llamadas no enviadas quedan expresamente fuera del requisito U(C) ⊆ A(C):** las filas
  `no_enviado` y las huérfanas no enviadas no son llamadas comprobadas.
- Una denegación correcta por un evento no autorizado es justo la conducta exigida, y nunca es una
  infracción.

Se define e(C) como la etapa de C (`juicio`, `validacion`, `produccion` o `aprobaciones`;
`medicion_codex` es `produccion`) y v(C) como su versión.

- U(C) = filas **sin cota** con `seq_cierre < C.seq_envio`, más las **huérfanas enviadas** con
  `seq_deteccion < C.seq_envio`.
  - Las filas `no_enviado` y las huérfanas no enviadas no entran.
  - Una fila que estaba viva cuando C despachó y murió después no entra en U(C), porque su
    `seq_deteccion` es posterior.
- A(C) = la unión de `cubre.eventos_desconocidos` de las reanudaciones **válidas** (R6) con
  `seq < C.seq_envio`, `e(C) ∈ etapas` y `v(C) ∈ versiones`.
- Se exige U(C) ⊆ A(C).
- Se exige que toda suspensión de la etapa e(C) y la versión v(C) con `seq < C.seq_envio` esté
  citada en una reanudación válida de A(C).
- Se exige `C.eventos_desconocidos_vistos` == U(C). El control previo los leyó bajo el mismo
  cerrojo, así que la igualdad es exacta.
- Se exige que el `eventos_sha256` de cada reanudación coincida con las filas actuales: una fila
  editada después invalida la reanudación.
- **Coherencia de secuencias (K7).** Se exige que los `seq` sean únicos y, según la clase de la
  fila:
  - **enviada y cerrada:** `seq_inicio < seq_envio < seq_cierre`;
  - **huérfana enviada:** `seq_cierre == null` (se conserva nulo) y `seq_inicio < seq_envio <
    seq_deteccion`, donde `seq_deteccion` es el de su registro de orfandad;
  - **`no_enviado`:** `seq_envio == null` y `seq_inicio < seq_cierre`;
  - **huérfana no enviada:** `seq_envio == null`, `seq_cierre == null` y `seq_inicio <
    seq_deteccion`.

  Además, ningún `seq_cierre` ni `seq_deteccion` de otra fila cae entre `seq_inicio` y `seq_envio`
  de C, porque esa sección es única. Una fila `en_curso` sin cierre y sin registro de orfandad al
  llegar la puerta se clasifica con la regla de R4 sobre su `t_envio_utc`, entra en el techo y no
  entra en U(C) de nadie, porque nadie la detectó. Si no se cumple algo de esto, `seq_incoherente`.
  La orfandad tardía (E2E-13 iii) cumple estas reglas y **no** da `seq_incoherente`.

**Pruebas (K7):**

- **E2E-13 · Intercalación.** Dos hilos o procesos:
  - el A cierra una fila sin cota;
  - el B hace el control previo y el despacho de una llamada de juez;
  - con barreras de prueba se fuerzan tres órdenes.

  (i) **B comprometida antes del cierre de A → admitida.**
  - Se pone una barrera **entre el compromiso de B (`seq_envio`) y su invocación real**: B registra,
    suelta el cerrojo y se pausa; A cierra sin cota; después B invoca.
  - Exigido:
    - `B.seq_envio < A.seq_cierre`;
    - la puerta **acepta** B y su consumo cuenta en el techo (garantía de compromiso irrevocable,
      residual declarado);
    - la llamada siguiente queda `no_enviado` y se detiene.
  - Un cierre de A intentado mientras B está entre el control y el compromiso queda bloqueado en el
    cerrojo hasta el `seq_envio` de B. La variante que suelta el cerrojo entre el control y el
    compromiso tiene que dar rojo.

  (ii) **B comprometida después del cierre de A → detenida o `no_certificable`.**
  - Con el cierre de A antes del control de B, B ve el evento y no se compromete (fila `no_enviado`
    y suspensión nueva). La puerta no lo cuenta como infracción (K15).
  - Variante de manipulación: una fila B con `seq_envio > A.seq_cierre` y sin reanudación que lo
    cubra da `no_certificable` (`llamada_tras_desconocido_sin_autorizacion`).

  (iii) **Orfandad tardía.**
  - A está enviada y viva cuando B despacha; después muere.
  - Exigido:
    - el registro de orfandad de A lleva `seq_deteccion > B.seq_envio`, y la puerta no exige que B
      lo hubiera visto;
    - A cumple `seq_inicio < seq_envio < seq_deteccion` con `seq_cierre == null`, y la puerta no da
      `seq_incoherente`;
    - la siguiente sección (a) que lo detecta se detiene.

  En ningún orden hay un **compromiso** (`seq_envio`) posterior a un evento sin cota no autorizado.
- **E2E-14 · Dos ciclos completos.** Evento 1 → suspensión `juicio-s1` → reanudación `r1`, que cubre
  evento 1 y `s1` → juicio sigue → evento 2 → suspensión `juicio-s2` (`s1` sigue en disco intacta,
  con su sha256) → reanudación `r2`, que cubre evento 2 y `s2` → juicio termina.

  Exigido: las dos suspensiones y las dos reanudaciones existen y validan, la puerta acepta el orden,
  la calidad se calcula y la cuota queda `estimada` (datos fijados: el evento está en la versión NUEVA (numerador) y el mínimo del cociente no supera el umbral, por lo que el intervalo lo cruza). Variantes:
  - `r2` que cubre solo el evento 1 → la llamada posterior al evento 2 da
    `llamada_tras_desconocido_sin_autorizacion`;
  - borrar o editar `s1` invalida `r1`.

Si se viola, `no_certificable` con `llamada_tras_desconocido_sin_autorizacion`.

**Con cualquier evento sin cota, el consumo de su ámbito tiene máximo `∞`**, y cada condición de
CUOTA se resuelve por intervalo (§4.5): `estimada` si su intervalo cruza el umbral, `certificada ·
excede` si su mínimo ya excede y `certificada · cumple` si su máximo cumple. Esto último ocurre cuando
el evento solo está en el denominador de un cociente: nueva = 100, base = `[100, ∞]`, cociente
`[0, 1]`, que cumple frente a 1,25. Prueba obligatoria en E2E-19. El veredicto de CALIDAD **no** se ve afectado por el evento:
solo por sus efectos propios (§4.5). Reanudar permite terminar de medir y publicar.

Lo que sí da calidad `no_certificable` es el orden: una llamada comprometida tras un evento sin
cota no autorizado (`llamada_tras_desconocido_sin_autorizacion`), porque la regla de parada es parte
de la identidad del circuito. Los eventos **con** cota entran en la cuota con su cota.

---

## 6 · Esqueleto y pruebas de punta a punta

### 6.1 Recorrido mínimo exacto del esqueleto

- **Caso:** `caducidad-reparacion-directa` (`PR:35`, A-canónicos), **1 repetición**, en **dos
  versiones** con etiquetas `base-esq` y `nuevo-esq` (mismo SHA permitido).
- **Bloque:** `--bloque 7 --versiones-contador base-esq,nuevo-esq`.
  - Con el Bloque 0, el presupuesto Codex de producción es 0 (R:445). Cualquier aserción sobre la
    parada de Codex pasaría aunque el mecanismo de §5 no hiciera nada.
  - En HEAD, `quality_adaptive` no enruta a `cli-codex`: solo lo hace la política `codex`
    (llm.py:220), y la membresía Codex viene desactivada por defecto (config.py:153). Por eso la
    producción del esqueleto no ejerce Codex. La parada de Codex se prueba en el guardián (E2E-3).
    El camino de producción de 5C se prueba cuando llegue el Bloque 5.
- **Proveedores, todos dobles en memoria:**
  - `subprocess.run` de `subscription_llm.call_cli` y de `codex_subscription_llm.call_cli`
    (emiten el JSON del CLI con `usage` completo);
  - `embeddings.embed_texts`;
  - runners de juez Opus y Codex con la interfaz `Runner` (J:1324), que devuelven salidas válidas
    guionizadas.
- **Base de datos:** el clúster aislado sintético en el puerto 55448 (§8.4, Q17;
  `MIA_TEST_ENV_FILE`; nunca 55432), porque
  `run_case` necesita las tablas y el checkpointer. Sin ese entorno, la prueba E2E-1 **termina en
  rojo con el código «no ejecutable»**. Nunca cuenta como verde ni como omitida (el criterio de
  `test_gates_no_ciegos`).
- **Custodia de prueba:** DPAPI de prueba, como en `test_banco04_produccion.py:891`. Contiene la
  clave del caso, la semilla y las jurisdicciones, y **4 ids custodiados de prueba**, que no se
  producen. Así `inventario_esperado` se construye y su ausencia sale como `muestra_incompleta`.
  - Lleva también las claves de los 13 casos visibles (§6.4, interfaz 10).
- **Puerta del esqueleto (v6):** `banco04_decidir.main(["veredicto", ...], _prueba=PruebaPuerta(
  manifiesto_custodia=..., desproteger=..., directorio_instantaneas=...))`.
  - `aceptar_dobles` y `aceptar_arbol_sucio` quedan **sin relajar**, así que `corridas_con_dobles`
    aparece entre los motivos y el resultado lleva `modo_prueba: true`.
  - F17 activa además `aceptar_dobles` y `aceptar_arbol_sucio`, y su `aprueba` también lleva
    `modo_prueba: true`.
  - Las instantáneas de prueba viven en un directorio temporal fuera de `backend/`, que se pasa a
    los `main` con `instantaneas_dir=`.

| Paso | Comando (Python, con dobles inyectados solo por parámetro) | Resultado exigido |
|---|---|---|
| 1 | `R.main([... --version base-esq --casos caducidad-reparacion-directa --solo-piloto --permitir-parcial ...], proveedores=dobles)`, y lo mismo para `nuevo-esq` | R1 con `dobles: true`; R2 rep-01 `completo`; R4 con ≥ 1 fila `produccion` por llamada, cerradas, con contexto, `nodo` y `uso_validado.consumo_conocido=true`; R11, R12 |
| 2 | `R.main([... --fase aprobaciones ...], proveedores=dobles)` en las dos versiones | R10 `completo`; filas R4 `aprobacion_*` |
| 3 | `banco04_juzgar.main(["registrar-cadena", ...])`, después `main(["juzgar", ...], runners=dobles)` | R8 escrito antes de la primera fila `juicio_*`; R5 por versión con la pasada 1 de Opus y de Codex, la pasada 2 y los votos; filas R4 de juez con `candidate_id` y `pasada` |
| 4 | `banco04_decidir.main(["veredicto", ...])` | `no_certificable`; motivos ⊆ E y ninguno de F (abajo); condiciones del caso **recalculadas**, con fuentes |

- **E (motivos esperados):**
  - `muestra_incompleta`, que incluye por definición:
    - los casos ausentes (los otros 12 visibles y los 4 custodiados de prueba);
    - las repeticiones 2..5 que faltan del caso presente por `--solo-piloto`;
  - `corridas_con_dobles` (`aceptar_dobles` sin relajar);
  - `arbol_sucio`, solo si el árbol lo está;
  - `validacion_reservada_ausente`;
  - los `sin_dato` o `par_faltante` que se deben **solo** a lo anterior.
- **F (motivos prohibidos):** cualquiera de identidad, ledger, juicio incompleto, telemetría, orden,
  extensión, R11 o R12.

**Cambios del runner que exige el esqueleto:**

- `--casos` (solo con `--permitir-parcial`) y `--solo-piloto`, ambos registrados en R1.
- El parámetro de Python `proveedores` de `main`, sin ningún flag de línea de comandos. Fuerza
  `dobles: true`. Sustituye **solo** estos nombres de módulo, guardando el original y
  restaurándolo en `finally`:
  - el atributo `subprocess` **dentro de** `subscription_llm` y de `codex_subscription_llm` (líneas
    65 y 18 de cada módulo), mediante un objeto proxy cuyo `run` es el doble. El `subprocess`
    global no se toca, así que `git` en `info_arbol_git` (R:691) y los runners de juez siguen
    siendo reales;
  - `subscription_llm._resolve_exe` (:170) y `codex_subscription_llm._resolve_exe`, que devuelven
    una ruta ficticia `.exe`. Sin este doble, la prueba dependería del CLI instalado y podría
    saltar de alias;
  - `codex_subscription_llm._local_membership_allowed` (:269), solo en E2E-8 y E2E-9;
  - `embeddings.embed_texts`;
  - `llm.resolve_fallback_chain`, solo en E2E-8 y E2E-9.
- La variante sin base de datos `mundo=` sustituye **solo el mundo exterior**: lo que hoy hacen
  `producir`, `hash_soul` y `fijar_jurisdicciones` (R:1765-1787), las funciones de `DepsAprobacion`
  (R:1828-1896) y la base de datos.
  - **No escribe telemetría** (K10). Su `producir` doble llama a `llm.call_llm(task=...)` del
    producto real: el router real, el `_guarded_invoke` real y el envoltorio real de §4.3. Los dobles
    están solo en `subprocess.run` de los CLI (vía `proveedores`). Así cada fila R4 sale de la
    captura real.
  - Fija el nodo con `metrics.usage.set_node` (`usage.py:74`), igual que el grafo
    (`agents/graph.py:1255`).
  - Lo único sintético es el `resultado` (textos y `material_turno`).
  - Una prueba comprueba que el módulo de dobles no importa `telemetria` y que toda fila R4 lleva
    `origen: "captura"`.
  - Siguen siendo código real, y no se pueden sustituir: `info_arbol_git`, `construir_manifiesto`,
    `asegurar_manifiesto`, el plan, el `Contexto`, la instalación de la telemetría, la escritura de
    R1, R2, R4, R6, R10, R11 y R12 y el cifrado de la custodia.
  - Se usa en el fixture completo de §6.3.

### 6.2 Pruebas de punta a punta sobre el esqueleto (`execution/test_banco04_cadena.py`, nuevo)

- **E2E-1 · Alcanzabilidad.** Los pasos 1 a 4 desde los `main`: archivos con su esquema, cero filas
  `en_curso` y el resultado de 6.1.
- **E2E-2 · La puerta solo lee crudos.**
  - `entradas_leidas` es un subconjunto del inventario de §3.9 y contiene sus elementos
    obligatorios (las instantáneas citadas, sus evidencias y las fuentes de R13 cuando hay R13).
  - Mutar `estado_banco.json`, `aprobaciones_estado.json`, `*.derivado.json`,
    `consumo_resumen`, `consumo_turno`, `consumo_aprobacion`, `usage_by_node.*.json` o un
    `VEREDICTO.json` previo deja la salida idéntica, salvo la marca de tiempo.
- **E2E-3 · Telemetría.**
  - El doble del CLI de Claude omite `output_tokens` en una llamada: la fila R4 queda
    `consumo_conocido=false`, `componentes_ausentes=["output_tokens"]` y `cota=null`.
  - `ContadorCuota.cota_calculable` es falso.
  - En el Bloque 7, con presupuesto Codex de producción mayor que 0 y por debajo de su tope:
    `GuardBanco.check_and_reserve(alias="cli-codex")` lanza `ParadaCodexProduccion` con el código
    `consumo_desconocido_sin_cota`, no con el de presupuesto agotado. Su fila R4 queda
    `no_enviado` (K15).
  - La siguiente llamada de juez lanza `CuotaAgotada` con el mismo código y se escribe una
    suspensión nueva R6 `suspensiones/juicio-<seq>.json` con `eventos` = [id de la fila]. En la
    puerta, la cuota queda `estimada` (datos fijados: el evento está en la versión NUEVA (numerador) y el mínimo del cociente no supera el umbral, por lo que el intervalo lo cruza), y la calidad no tiene ningún motivo
    por el evento.
  - Variantes con la misma exigencia: Codex sin evento `usage`; `cli-codex-eval` con `None`.
  - Variantes del registro de §4.4: las ocho pruebas listadas allí, con producción y con el juez
    Codex. El juez Codex con varios eventos `usage` persiste todos en R5 y R4.
  - **Variante con cota (K7):** una fila de la familia `api` que falla con `max_tokens` aplicado es
    desconocida con cota. No detiene el juez ni Codex, y el techo sigue certificable.
- **E2E-4 · Reanudación.**
  - Tras E2E-3, una reanudación que cubre el evento deja seguir al juez.
  - Un evento nuevo detiene otra vez.
  - Una fila de juez falsificada con `t_inicio` posterior a un evento no cubierto da
    `llamada_tras_desconocido_sin_autorizacion`.
  - Editar una fila cubierta invalida la reanudación.
  - Una reanudación con `etapas: [produccion]` no autoriza al juez, y una con `versiones: [base]` no
    autoriza la nueva.
  - La reanudación de la validación continúa R9 en el primer ítem pendiente, con la misma
    identidad y sin un segundo uso del reservado. Con otro `hash_evaluador`, se niega.
- **E2E-5 · Ceguera y material.** El `prompt_sha256` reconstruido es igual al guardado. Alterar un
  byte del texto del R2 rompe `paquete_sha256` → `no_certificable`.
- **E2E-6 · Producto intacto.** Las cuatro verificaciones de §4.3: diff vacío en el producto,
  identidad campo a campo con y sin el envoltorio, restauración por `is` y suites verdes.
- **E2E-8 · Codex de producción, recorrido positivo (K10).**
  - Bloque 7, con el mismo doble de `llm.resolve_fallback_chain` que E2E-9: una tarea cuya cadena
    empieza por `cli-codex`, registrada así en `cadenas_politica`, con `puede_codex = true`.
  - El `producir` de `mundo=` llama a `llm.call_llm(task=<esa tarea>)`, no a `_invoke` directo, de
    modo que el router real elige `cli-codex` y la llamada pasa por `_guarded_invoke` y por el
    `_invoke` real (llm.py:1005-1016). R13 está presente y el presupuesto es suficiente.
  - Usa los dobles de `proveedores` (§6.1), incluido `_local_membership_allowed`
    (`codex_subscription_llm.py:269`).
  - Exigido: una fila R4 con `proveedor_cuota=codex`, `uso_crudo.eventos` y consumo conocido;
    `ContadorCuota.codex_produccion` > 0; las condiciones Codex de §6.3 calculadas en la puerta;
    veredicto `aprueba` en la variante F17 con Codex ≤ 0,50× de Claude.
  - Hoy `quality_adaptive` no enruta a Codex. El recorrido del grafo con 5C se prueba cuando llegue
    el Bloque 5, que lo active.
- **E2E-9 · Piloto Codex (K5).**
  - La prueba sustituye `llm.resolve_fallback_chain` por un doble que incluye `cli-codex` (lista de
    `proveedores`, §6.1).
  - Sin R13, `R.main` en el Bloque 7 rechaza con exit 3 antes de la primera corrida.
  - Con R13, la piloto se admite con su estimación y no con 0 (R:1094-1095).
  - Una fila R4 Codex en una versión con `puede_codex == false` → la puerta da `no_certificable`.
- **E2E-10 · Registro de uso del reservado (K3).**
  - Con `LOCALAPPDATA` y `MIA_BANCO04_CUSTODIA` reubicados **a la vez**, el segundo uso se rechaza.
  - Una identidad incluida en `IDENTIDADES_RESERVADO_RETIRADAS` se rechaza en VJ y en la puerta.
- **E2E-11 · Bloque 0 (K11).** `banco04_decidir linea-base` sobre el esqueleto con una sola
  versión escribe `INFORME_LINEA_BASE.json` con el esquema de §3.5, sin campo `veredicto` ni
  comparativas.
- **E2E-12 · Medición previa de Codex (K5).**
  - `banco04_medir_codex.main` con `mundo=`, `proveedores=` y el doble de `resolve_fallback_chain`
    de E2E-8 escribe `S/<ver>-medicion-codex/` (R1 y R4, sin `resultado`) y después R13 con el
    redondeo de R13.
  - `run_banco04` de la versión arranca con ese R13.
  - La puerta reproduce `por_clase` desde las fuentes.
  - Variantes:
    - fila fuente desconocida → sin R13;
    - techo de la medición alcanzado → suspensión de etapa `produccion` y sin R13;
    - R13 editado → `estimacion_codex_no_reproducible`.
- **E2E-15 · Denegación antes de enviar (K15).**
  - `GuardBanco.check_and_reserve` deniega una llamada Codex (presupuesto 0 en el Bloque 0): la fila
    R4 queda `no_enviado`, con `t_envio_utc == null`.
  - `ContadorCuota.cota_calculable` sigue verdadero y la cuenta de inferencias no cambia; el juez
    no se detiene por ella.
  - Matar el proceso entre `en_curso` y `t_envio_utc` deja, tras su registro de orfandad, una
    huérfana no enviada (clasificación única de R4), que tampoco detiene.
  - Matarlo después de `t_envio_utc` deja una huérfana enviada, que es desconocido sin cota y
    detiene desde su `seq_deteccion`.
  - Una llamada C denegada (`no_enviado`) después de un evento no autorizado no aparece como
    infracción en la puerta, porque no es una llamada comprobada (§5.4).
  - Una fila `no_enviado` editada con `t_envio_utc` → `no_enviado_contradictorio`.
- **E2E-16 · Firma de comando (K4).**
  - Misma `cli_version`, dos firmas (esfuerzo `high` y `max`) y una sola acreditada con
    `omitido_si_cero`. La fila de la firma no acreditada, sin caché, queda desconocida.
  - El runner con `firmas_previstas` incompletas rechaza (exit 3).
  - Dos entradas con la misma firma y conductas distintas → `acreditacion_ambigua`.
- **E2E-17 · Instantáneas (K13).** R1 de la base y de la nueva que citan instantáneas distintas →
  `acreditacion_snapshot_distinto`. R9 con su propia instantánea → válido, y sus filas se
  interpretan con ella.
- **E2E-18 · Identidad efectiva (K8).**
  - Mismo alias y mismo `mia_model_hint`, pero `modelUsage` con un `canonicalModel` distinto entre
    versiones → `base_no_comparable_reproducir`.
  - Una fila Claude con éxito sin `modelUsage` → `identidad_efectiva_ausente`.
- **E2E-19 · Veredicto de cuota separado (v7).** Las ocho pruebas obligatorias de §4.5. Sustituyen
  a las de la v6, cuya fórmula de cota queda revocada.
- **E2E-7 · Sin puerta trasera.**
  - `banco04_decidir.py` no tiene ningún flag que active `_prueba` ni acepte `dobles` (búsqueda en
    el código y en `--help`).
  - Con `dobles: true` y sin `_prueba`, el resultado es `no_certificable`.
  - `resumen_publicable` rechaza `modo_prueba`.
- **Esqueleto, mutación semántica que cambia la condición** (familia S de §6.3 a escala de un
  caso; el veredicto sigue siendo `no_certificable` por la muestra). En cada una se cambia el doble
  y se regenera desde `main`:
  - runners de juez que marcan `sin_respaldo` sobre un átomo, en Opus y en Codex →
    `afirmaciones_sin_respaldo` del caso pasa de 0 a 1;
  - pasada 2 con `cubierto=false` en un decisivo → baja su cobertura;
  - un proveedor doble del grafo que hace que el material recortado sea menor → baja el alcance.

  Editar el crudo sin regenerar es familia I y tiene que dar el código de identidad, no el cambio de
  la condición.

### 6.3 Familia «mutar el dato crudo conservando cualquier agregado ⇒ el veredicto cambia»

**Fixture F17.** Las dos versiones completas: 17 casos × R, aprobaciones y R9 reservado de prueba
(≥ 30 defectos, de ellos ≥ 10 cláusulas breves, y ≥ 30 controles, con acreditación v1.3 de prueba).

- **Cómo se produce:** con `mundo=` (sin base de datos) y `proveedores=` (§6.1), juzgando con
  runners dobles y validando con VJ `main` con runners dobles. Todo se ejecuta **desde los `main`**,
  y cada fila R4 sale de la captura real.
- Con `_prueba`, la puerta da **`aprueba`**. Es requisito previo de la familia: si F17 no da
  `aprueba`, la familia no prueba nada.

**Dos familias distintas (K10).** Separan la manipulación incoherente de la mutación semántica.

- **Familia S, semántica.** Se cambia el **doble** de la etapa afectada (mundo, proveedores o
  runners de juez) y se **regenera desde `main`** esa etapa y todas las posteriores:
  - producir o aprobar → juzgar → decidir.
  - Todos los hashes quedan coherentes.
  - Se exige el **cambio concreto de la condición** nombrada (valor recalculado en
    `condiciones[]`) **y** el veredicto indicado.
  - **Efectos concomitantes permitidos (K10).** Además de la condición nombrada, pueden cambiar
    solo las condiciones de su **cierre de dependencias**, según el crudo que se tocó:

    | Crudo tocado | Condiciones que pueden cambiar con él |
    |---|---|
    | pasada 1 (respaldo, votos) | `afirmaciones_sin_respaldo`, `discordancias_sin_resolver`, `fuga_jurisdiccion` (vía jueces), `kappa_salidas_reales`, `aprobacion_sin_edicion_proxy` y su comparativa |
    | pasada 2 (cobertura, conducta, puntos) | coberturas (materiales, decisivos y en lo leído, con su suelo), `definitivo_con_lectura_insuficiente`, `definitivo_con_hecho_decisivo_omitido`, `definitivo_con_hecho_no_disponible`, omisiones, utilidad, `abstencion_injustificada`, proxy, las comparativas de esas métricas, la pérdida por caso y los decisivos estables |
    | `material_turno` (alcance) | lo mismo que la pasada 2, más el alcance C8 |
    | texto del borrador o del diagnóstico | la señal de fuga y, si se rejuzga, todo lo de las pasadas 1 y 2 |
    | consumo (proveedores dobles) | solo `cuota.condiciones` (techo de §6.3, C25, presupuesto del circuito). **Ninguna condición de calidad** puede cambiar |
    | `fallo_producto`, `limite_de_uso` | `turnos_completados`, la completitud y lo que dependa de la corrida que falta |

  - **Prohibido:**
    - cualquier cambio fuera del cierre;
    - cualquier motivo `no_certificable` distinto del indicado;
    - en particular, todo motivo de identidad, ledger, juicio, telemetría, orden, comparabilidad o
      entradas (§3.8);
    - todo fallo de una condición ajena.

    La prueba compara `condiciones[]` antes y después y falla si cambia algo fuera del cierre.
- **Familia I, incoherente.** Se edita un crudo en disco **sin regenerar** lo que depende de él.
  - Se exige `no_certificable` con el **código de motivo exacto** indicado, y ningún motivo de
    calidad.
  - Prueba que la puerta detecta la manipulación, no que la condición funcione.

**Familia S:**

| # | Cambio en el doble y regeneración desde `main` | Condición que tiene que cambiar | Veredicto |
|---|---|---|---|
| S01 | los dos runners de juez marcan `sin_respaldo` el mismo átomo | `afirmaciones_sin_respaldo` 0 → 1 | reprueba |
| S02 | solo Codex marca defecto; el tercer voto doble dice `sin_respaldo` | ídem | reprueba |
| S03 | el runner del tercer voto devuelve JSON inválido dos veces | juicio incompleto de esa corrida (`no_evaluada_tercer_voto`) | no_certificable |
| S04 | pasada 2: los decisivos de un caso de lectura completa quedan no cubiertos | `cobertura_hechos_decisivos` del caso < 0,80 | reprueba |
| S05 | pasada 2: conducta `definitiva` en una corrida cuyo `material_turno` (mundo) da alcance < 0,95 | `definitivo_con_lectura_insuficiente` 0 → 1 | reprueba |
| S06 | el mundo emite `entraron_tramos` reducido (alcance 0,96 → 0,90) y se rejuzga con conducta `definitiva` | alcance C8 `suficiente` → `insuficiente`; DLI 0 → 1 | reprueba |
| S07 | el mundo emite `fragmentos_en_prompt.completo=false` | alcance → `sin_medicion` (insuficiente); DLI 0 → 1 con conducta `definitiva` | reprueba |
| S08 | los proveedores dobles devuelven más `output_tokens` en un caso de la nueva | CUOTA: `claude_extremo_por_caso` con mínimo > 1,25 → `cuota: certificada · excede` | **calidad sin cambio** (`aprueba`); `cuota.resultado: excede` |
| S09 | un proveedor doble de Claude omite `output_tokens` en una llamada | la fila (de la versión NUEVA, numerador) queda sin cota y el mínimo del cociente no supera el umbral, por lo que el intervalo lo cruza; `cuota.estado` → `estimada` | calidad **sin cambio** (`aprueba`), cuota `estimada`; el juicio se detiene hasta la reanudación (E2E-3) |
| S10 | el mundo fija con `set_node` un nodo fuera de `atribucion_preregistrada` en las llamadas que suben más del 10 % | CUOTA: C25, la subida no es atribuible → `cuota: … excede` | **calidad sin cambio** (`aprueba`); `cuota.resultado: excede` |
| S11 | los runners de pasada 2 hacen caer un decisivo de 3/5 en la base a 1/5 en la nueva | `decisivos_estables_perdidos` ≠ ∅ | reprueba |
| S12 | VJ con runners dobles que fallan defectos plantados hasta que la sensibilidad < 0,95 | `circuito_sobre_mutaciones_reservadas` | no_certificable |
| S13 | VJ con estados de Codex invertidos hasta kappa < 0,6 | `kappa_reservado` | no_certificable |
| S14 | el runner de Opus devuelve dos veces una salida estructuralmente inválida, o `no_aplica` sobre una cifra | juicio incompleto | no_certificable |
| S15 | el mundo emite en el borrador de un caso sin ordenamiento «La Ley 100 de 1993 es aplicable al caso»; los jueces dobles **no** marcan fuga | `fuga_jurisdiccion` por la señal (§3.6) | reprueba |
| S16 | los jueces dobles marcan `con_respaldo` con `uso_fuente=aplicable` y una fuente de un ordenamiento no configurado | el validador lo rechaza (J:514) → juicio incompleto | no_certificable |
| S17 | los votos dobles confirman una negativa falsa | `afirmaciones_sin_respaldo` +1 por `confirmadas` | reprueba |
| S18 | Codex marca una fuga (subtipo `fuga`) y el tercer voto la confirma | `fuga_jurisdiccion` por el juez (Q16) | reprueba |
| S19 | el mundo lanza `limite_de_uso` en la rep 5 de un caso de la base | repeticiones incompletas | no_certificable |
| S20 | la aprobación de un caso falla por infraestructura dos veces | techo sin aprobación | no_certificable |
| S21 | el mundo lanza una excepción del producto después de una llamada al modelo en una corrida (`fallo_producto`) | `turnos_completados` baja **y** corrida sin texto (K6) | no_certificable |
| S22 | el mundo omite `resultado.verification` en una corrida | `falsos_bloqueos` sin dato (K1) | no_certificable |
| S23 | el mundo emite un `model_fallbacks` cuyo `hacia` no tiene fila R4 | `cambio_de_motor` contradictorio (K1) | no_certificable |

**Familia I:**

| # | Edición en disco sin regenerar | Código de motivo exigido |
|---|---|---|
| I01 | `jurisdicciones_fijadas` de un custodiado | `jurisdiccion_no_coincide` |
| I02 | borrar una fila R4 citada por un R2 | `ledger_incompleto` |
| I03 | añadir una fila R4 huérfana enviada, con su registro de orfandad y con el contexto de una corrida, sin citarla en el R2 | `ledger_incompleto` |
| I04 | `soul_sha256` en R1 de la base | `identidad_version` |
| I05 | `hash_evaluador` en un R5 | `evaluador_no_congelado` |
| I06 | fila R4 con `consumo_conocido=true` y `uso_crudo` sin `output_tokens` | `telemetria_contradictoria` |
| I07 | R11 reescrito con `r_reducida` | `decision_r_no_coincide` |
| I08 | `rep` cambiado dentro de un R2 | `repeticiones` |
| I09 | fila de juez falsificada tras un evento sin cota no autorizado | `llamada_tras_desconocido_sin_autorizacion` |
| I10 | `salida` de un R5 editada sin su `crudo_sha256` | `juicio_contradictorio` |
| I11 | `material_turno` de un R2 editado sin rejuzgar (antes M06/M07) | `rep_sha256_no_coincide` |
| I12 | R7 editado | `extension_no_coincide` |
| I13 | borrar la segunda pasada de estabilidad o la pasada 2 de Codex de un elegido | `submuestra_incompleta` |
| I14 | `cli_version` distinta en R1 de la base | `base_no_comparable_reproducir` |
| I15 | instantánea de acreditación editada en sitio (su nombre ya no es su sha256) | `telemetria_acreditada_no_coincide` |

**Recorrido positivo de la extensión (K10, F17-ext).**

1. Dobles de pasada 2 calibrados para que una métrica de A-pequeños quede `no_concluyente` en la
   previa: estimación puntual ≥ −δ y límite inferior < −δ.
2. `banco04_decidir previa` escribe R7, con casos según §3.4.
3. `R.main --fase extension` en las dos versiones produce las reps R+1..R+5 con `extension_sha256`.
4. `banco04_juzgar juzgar` juzga solo lo nuevo, con las submuestras de extensión de §3.7.
5. `banco04_decidir veredicto` da `aprueba`, con el rótulo «sin regresión demostrada; evidencia
   insuficiente» si la métrica sigue `no_concluyente`, o con el veredicto recalculado si cambia.
6. Las submuestras originales no cambian (las mismas pasadas que antes de la extensión).

Variantes negativas, en la familia I (I12) y en la familia S:

- borrar con `--fase extension` un caso de R7 en una versión → `no_certificable`;
- escribir R7 sin causa → `extension_sin_causa`.

**Familia inversa.** Mutar solo derivados (E2E-2), incluidos `resultado.false_block`,
`resultado.jurisdiction_leak`, `resultado.abstention` y `resultado.reached_draft` de R2 (K1), no
cambia el veredicto `aprueba`. `reached_draft` invertido en una corrida con borrador tampoco lo
cambia, porque la puerta usa `draft_full`.

**Resultado.** El autor independiente escribe la familia en rojo antes de la implementación.
Después, un tercero muta la puerta y el resultado es el número de mutaciones que **sobreviven**
(DOC §10.2.13).

---

### 6.4 Interfaces fijadas por las pruebas (contrato desde la v6)

Se adoptan como contrato las interfaces 1–5 y 7–10 del §4 del informe del autor de pruebas (scratchpad
`r5/pruebas-cadena-informe.md`). La 6 queda sustituida por §3.1 (manifiesto de custodia del repo y
`PruebaPuerta`). Quien implemente no puede cambiarlas.

1. **`proveedores`.** Es un `dict` cuyas claves son literalmente los nombres de §6.1:
   - obligatorias: `subscription_llm.subprocess.run`, `codex_subscription_llm.subprocess.run`,
     `subscription_llm._resolve_exe`, `codex_subscription_llm._resolve_exe` y
     `embeddings.embed_texts`;
   - opcionales: `codex_subscription_llm._local_membership_allowed` y `llm.resolve_fallback_chain`.
2. **`mundo`.** Es un objeto con `async producir(caso, rep)`, `hash_soul()`,
   `fijar_jurisdicciones(codigos, tenant=None)`, `async abrir_despacho`, `producir_hasta_revision`,
   `aprobar` y `cerrar_despacho`. Su `producir` llama al `llm.call_llm` real con el nodo fijado por
   `set_node`.
3. **`runners`** de juzgar y de VJ. Es `{"opus": Runner, "codex": Runner}`, y cada runner atiende
   todas las etapas según el `schema` de su esquema.
4. **Argumentos de línea de comandos:**
   - `run_banco04` añade `--casos`, `--solo-piloto`, `--fase extension`,
     `--telemetria-acreditada <sha>` y `--atribucion-preregistrada <ruta>`. Sin `--salida-custodia`,
     los crudos custodiados van a `<MIA_BANCO04_CUSTODIA>/salidas`;
   - `banco04_juzgar registrar-cadena --base --nuevo --custodia --salida --bloque [--linea-base]`;
   - `banco04_juzgar juzgar --cadena --custodia [--reanudar-aprobado-por-pipe --etapas --versiones]`;
   - `banco04_decidir previa | veredicto | linea-base` con `--base`, `--nuevo`, `--custodia`,
     `--cadena` y `--salida`;
   - `VJ main(argv, runners=, carpeta_local_appdata=)` con `--telemetria-acreditada`;
   - `banco04_medir_codex` con el argv de R14 más `--telemetria-acreditada`,
     `--permitir-arbol-sucio`, `--incluir-custodiados` y `--versiones-contador`;
   - además (v6), todos esos `main` aceptan el parámetro de Python `instantaneas_dir=` (§4.4), y
     `banco04_decidir.main` acepta `_prueba=` (§3.1).
5. **`PruebaPuerta`.** Con la firma ampliada de §3.1: `manifiesto_custodia`, `desproteger`,
   `directorio_instantaneas`, `aceptar_dobles` y `aceptar_arbol_sucio`, que se activan por separado.
6. *(Sustituida por §3.1.)*
7. **Identificación de condiciones.** El `id` de cada condición contiene el nombre literal de su
   métrica: por ejemplo `afirmaciones_sin_respaldo`, `fuga_jurisdiccion`,
   `cobertura_hechos_decisivos`, `claude_extremo_por_caso`, `decisivos_estables`, `alcance`, y
   `atribu` o `C25`. El cierre de dependencias de la familia S se calcula sobre esos nombres.
8. **`etiqueta_version` del candidato.** Es la etiqueta de la versión.
9. **`IDENTIDADES_RESERVADO_RETIRADAS`.** Se consulta en tiempo de llamada, como atributo del
   módulo VJ.
10. **Claves de los 13 casos visibles.**
    - Van en la custodia de prueba.
    - Para los casos sin expediente, el esquema exige ≥ 1 hecho: se fija un hecho no decisivo del
      mensaje y un punto `laguna_real`.
    - La custodia real solo declara las claves de V1–V4: pendiente fuera de este frente (§8.6).

## 7 · Qué se conserva, qué se mueve y qué se elimina

### 7.1 `backend/mia/eval/banco04/metricas.py`

| Elemento | Destino |
|---|---|
| `clasificar_alcance` (46-63), `envio_desde_material` (78-101), `ref_disponible`, `disponible`, `punto_disponible` (120-147), `estado_cobertura` (150-159), `MATRIZ` y `celda` (189-229), `senal_fuga` (248-263) | se conservan |
| `metricas_corrida` (266-368) | se conserva su lógica y la llama solo la puerta, con la entrada armada desde la reproducción. Se eliminan los `or 0` (315, 341, 363, 365): ausencia ⇒ excepción ⇒ `no_certificable`. `evaluada` (333) deja de leerse de la entrada |
| `agregar_casos` (397-430), `agregar_estratos` (433-447) | se conservan; sin `or 0` (419, 422, 425-428, 445) |
| `evaluar_absolutos` (472-538) | pasa a interna; desaparecen los parámetros `kappa_real`, `kappa_reservado`, `circuito` y `evaluacion_completa` (son conclusiones). La puerta los calcula |
| `bootstrap_casos` y `_bootstrap` (556-579), `veredicto_comparativo` (582-591), `pares_comparativos` (601-626), `comparar_metrica` (629-674), `casos_para_extension` (677-681), `veredicto_tras_extension` (684-690), `perdidas_por_caso` (693-705), `decisivos_estables_perdidos` (708-732) | se conservan; a la última la alimenta la puerta |
| `consumo` (738-759), `_consumos_caso` (762-769), `techo_cuota` (772-873) | pasan a internas, adaptadas a R4. Se elimina el valor por defecto `campo_fallidos → []` (746). Solo las llama la puerta |
| `texto_cota`, `verificar_lenguaje`, `resumen_publicable` (879-890, 1259-1277) | se conservan; `resumen_publicable` rechaza `modo_prueba` |
| `inventario_esperado` (918-954), `casos_de_unidad` (977-979), `_completitud_version` (1119-1144) | se conservan, alimentados por la puerta con lo que encuentra en disco |
| **`veredicto_global` (1147-1256)** | **se elimina**. Acepta `inventario`, `casos`, `casos_base`, `semilla`, `absolutos`, `comparativas`, `techo`, `filas_extra`, `suspendido`, `salidas_sin_juzgar` y `otros_motivos_no_certificable`. Lo sustituye `puerta.decidir` |
| **`validar_inventario` (957-974)** | **se elimina**: el inventario no viene de fuera |
| **`atribucion_valida` (990-1038)**, `_ambito_de_subida` (982-987) | **se sustituye** por la atribución de §3.3 D (R4 + R8) |
| **`filas_comparativas_obligatorias` (1041-1077)** | **se elimina** como API pública: aceptaba `decisivos_base`, `decisivos_nuevo`, `techo`, `comparativas` y `atribuciones` |
| **`_motivos_recibo` (1086-1116)**, `_iguales` (1080-1083) | **se elimina**; lo sustituye §3.4 |
| `discrepancias_marcador` (1283-1300), `alcance_desde_fragmentos` (1306-1320), `_refs_hecho` (1323-1338), `hechos_y_puntos_desde_clave` (1341-1370) | se conservan |

### 7.2 `backend/mia/eval/banco04/jueces.py`

- **Se conserva todo lo determinista:** esquemas (120-213), validadores (576, 723, 1192, 1264,
  1293), `particion`, `alinear` y `pares_kappa` (798-918), estabilidad y kappa (921-983),
  adjudicación (994-1159), acuerdos (1162-1186), `llamar_validado` (1738), `pasada1`, `pasada2` y
  votos (1818-1916), `seleccionar_con_semilla` (1919), `hash_evaluador` y `verificar_congelado`
  (1948-1979). La puerta los reutiliza en la reproducción.
- **`recuento` (1068-1084):** el consumidor pasa a contar `len(discordancias_sin_resolver)`.
- **Se mueven a `telemetria.py`:** `tokens_conocidos` (1375-1404), y `ControlCuotaJueces` con
  `_contabilizar` (1407-1483), que pasa a escribir R4 con el contexto de juez y el control de §5.
- **Runners (1537-1702):** se conservan, envueltos por `telemetria`. `CodexJuezRunner._llamar`
  (1670-1702) guarda `cp.stdout` íntegro (K4), y `ClaudeJuezRunner._llamar` (1587-1621) guarda
  `usage`, `stop_reason`, `modelUsage` y `num_turns`.
- **`validar_pasada2` (1192-1261) y `esquema_pasada2` (165-189):** reciben el campo
  `negativa_correcta` y el parámetro `es_riesgo` (K1).
- **`seleccionar_con_semilla` (1919-1924):** recibe el parámetro `etiqueta` (K9).
- **`recuento` (1073-1074):** el subtipo de una unidad confirmada se toma de todos los votos de
  defecto, no solo del de Opus (§8.4, Q16).
- **`ARCHIVOS_EVALUADOR` (1931-1945):** se amplía con los módulos nuevos de §1.2.

### 7.3 `execution/run_banco04.py`

- **Se conserva:** aislamiento (85-229), política, clasificación de fallos, `decidir_r`,
  `elegir_aprobaciones` y el plan (470-578), manifiesto (680-796), cifrado y errores (806-848),
  `ejecutar_banco` (1046-1154) y aprobaciones (1330-1505).
- **Cambia:**
  - `ContadorCuota` (318-463) y `cargar_contador_desde_disco` (877-900) se reconstruyen desde R4;
  - `registrar_consumo` (903-912) pierde los `or 0`;
  - `_cargar_aprobaciones_y_juicio` (1199-1221) desaparece;
  - `_ejecutar_una` (954-1043) fija el contexto y escribe `intentos[].llamadas`, `caso_digest`,
    `prompt_version_hash` y `jurisdicciones_fijadas`;
  - `crear_guardian_banco` (1557-1623) consulta R4 (§4.2);
  - `_montaje_real` (1681-1959):
    - la salida custodiada pasa a `<custodia>/salidas`;
    - registra en R1 `cadenas_politica`, `puede_codex`, `codex_cli_version`, `sha_producto`,
      `rutas_modificadas_respecto_del_producto` y `telemetria_acreditada_sha256`;
    - `estimacion_piloto_codex` (627, 1799) deja de quedar vacía. Con `puede_codex`, se toma de R13
      y su ausencia rechaza. `ejecutar_banco` (1094-1095) deja de usar `.get(clase, 0)`: una clave
      ausente es un error (K5);
    - instala `telemetria.instalar()` (§4.3) junto a `spend_guard.install()` (1929, 1905);
  - `main` (1962-2010) añade `--fase extension`, `--casos`, `--solo-piloto` y los parámetros de
    Python `proveedores` y `mundo`.
- **Se elimina:**
  - `consumo_desde_guardian` y `marca_guardian` (1537-1554) como fuente (quedan, como mucho, para
    el `consumo_resumen` derivado);
  - `registrar_consumo_externo` (1174-1196, sin llamadores);
  - `LedgerJuicio` (1228-1294, lo sustituye R4);
  - el volcado `usage_by_node` (1933-1941).

### 7.4 Otros

- **Producto (`backend/mia/agent/`, `backend/mia/metrics/` y el resto fuera de `eval/`):
  ningún cambio** (K8, §4.3).
- **`execution/banco04_validar_jueces.py`:**
  - v7: se retira la exigencia `consumo_certificable` de `evaluar_exigencias` (VJ:329-332); el
    consumo de la validación entra en la cuota (§4.5);
  - R9 crudo (cambia 388-389 y 706), escrito por ítem;
  - llave determinista (699);
  - `control_de_cuota` (615-635) pasa a `telemetria`;
  - `--versiones-contador` (625-629) se coteja con los R1 que existen en disco;
  - `raiz_registro_uso` (427-446) pasa a usar `SHGetKnownFolderPath`;
  - `IDENTIDADES_RESERVADO_RETIRADAS`, nueva;
  - `--reanudar-aprobado-por-pipe` (K3, K7).
- **`backend/mia/eval/banco04/evaluador_congelado.py`:**
  - `_clausula_de` y `_mencion_negada` (437-472) se sustituyen por la regla de §3.6 (K2);
  - se añaden las copias congeladas de `false_block_signal` y de sus tres funciones de
    `verification` (K1), con el origen 7b9aaa0 y su sha256, como en `ORIGEN_FUGA` (:402).
- **`backend/mia/eval/banco04/metricas.py`:** `casos_para_extension` (677-681) se sustituye por
  `casos_extension` (§3.4, K9). Se añaden `falsos_bloqueos_corrida` y `cambio_de_motor_corrida`
  (K1).
- **`backend/mia/eval/codex_cli_adapter.py`:** `invoke_codex` (:384-424) y `call_graph_cli`
  (:536-538), según §4.2.
- **`backend/mia/eval/harness.py`:** `run_case` (502-905) se conserva. `usage_by_node` (909-936)
  queda para otros usos y el banco deja de llamarlo.
- **`backend/mia/eval/spend_guard.py`:** `_guarded_invoke` (1126-1275) gana la ranura y la
  captura de §4.2 y §4.3. La aritmética en USD (`_alias_and_cost`, 940-971; `note_call`, 864-878)
  no cambia y no alimenta la cuota.
- **`execution/banco04_calibracion.py`:** su entrada `--corridas` (líneas 17-22) la produce
  `banco04_decidir` a partir de la reproducción, con los defectos confirmados y sus posiciones.

---

## 8 · Decisiones

### 8.1 Tomada por Pipe

- **2026-10-12, reanudación:** «que se reanude con mi autorización». Se implementa como §5. Cierra
  el pendiente de C19 (DOC §12.6).
- **2026-10-12, «Acotar y medir». [REVOCADA el mismo día por «Separar calidad y cuota»]**
  ~~El intento fallido del CLI de Claude tiene cota cuando el banco fija los reintentos de fábrica,
  verifica el entorno real y mide el fondo.~~
- **2026-10-12, «Separar calidad y cuota».**
  - El banco emite dos veredictos:
    - CALIDAD (`aprueba` / `reprueba` / `no_certificable`), certificable aunque haya intentos sin
      cota;
    - CUOTA (`certificada` cumple / excede; `estimada` si hubo intentos sin cota; `excede` si lo
      conocido ya excede). **Aplicación por intervalo (v9):** «estimada si los hubo» se lee como
      «estimada si, por los intentos sin cota o por las cotas, el intervalo cruza el umbral» (§4.5).
  - El techo sigue gobernando la suspensión, con conocido + estimación empírica.
  - La reanudación y C27 siguen igual.
  - Se retira el fijado de reintentos y se conserva la medición del fondo como estimación empírica
    versionada.
  - Codex cae en la misma regla.
  - Se implementa como §3.1, §3.3 D, §4.5 y §5, y en la propuesta de protocolo v1.4.
  - **Aplicación del director en la v8 (no es decisión de Pipe):** «certificada» exige que el
    intervalo de consumo lo garantice (§4.5). Sin intentos sin cota, unas cotas finitas que cruzan el
    umbral también dan «estimada». Es más estricto que la letra «si no hubo ningún intento sin
    cota» y no la contradice: solo se certifica lo garantizado.

### 8.2 Resueltas por este contrato (las revisa Astra; no son decisiones de Pipe)

- **R-1.** La puerta recibe cuatro rutas, y la cuarta es R8 (manifiesto de cadena). La alternativa
  está en Q5.
- **R-2.** Las salidas custodiadas viven bajo `<custodia>/salidas` (§2.3 del protocolo, literal).
- **R-3.** Una sola fuente de consumo: R4. `turn_usage` sale del banco.
- **R-4.** Reproducción en lugar de confianza: las decisiones guardadas son derivados.
- **R-5.** Semilla del juicio, del bootstrap y de las submuestras: `custodia.semilla_hmac()`. Semilla
  de las aprobaciones: `R1.semilla`.
- **R-6.** La incoherencia de la matriz da `no_certificable`.
- **R-7. [SUSTITUIDA en v2 por §3.4, K9]** ~~Casos de la extensión: unión de los casos de cada
  métrica no concluyente, con un tope de 5 elegidos por la mayor contribución negativa.~~ Rige el
  orden total reproducible de §3.4.
- **R-11 (v2).** El producto no se modifica. La captura se hace con envoltorios en `eval/` (§4.3).
- **R-12 (v2).** Las clases de consumo son conocido, con cota y sin cota. Solo el consumo sin cota
  detiene (R4, §5).
- **R-13 (v2).** El `rep_sha256` cubre solo la parte cruda de R2 (R5).
- **R-14 (v2, revisada en v3).** El factor ×1,25 de R13 es una constante nueva de este
  contrato, no del protocolo.
  - Redondeo: `(5·max_c + 3) // 4` (R13).
  - Las fuentes de R13 están en el inventario de §3.9; si no son accesibles,
    `entrada_inaccesible`.
  - **La dependencia tiene productor:** `banco04_medir_codex main` (R14) produce las filas fuente y
    después R13.
- **R-15 (v2).** `cadenas_politica` se indexa por (tarea, escalada) (R1).
- **R-8.** El alcance solo cuenta como medido con `fragmentos_en_prompt.completo`.
- **R-9.** Familias de telemetría y fórmula del total (§4.1).
- **R-10.** Cuota Claude = todo alias que no es Codex ni embeddings, como `GuardBanco`.

### 8.3 Preguntas abiertas de la v1 (histórico)

Las resolvió el director en §8.4. Donde §8.3 y §8.4 difieren, rige §8.4 con sus revocaciones.

- **Q1.** Una repetición con `fallo_producto` no tiene texto. §4.1 dice que bloquea la
  certificación; §9.5 dice que solo cuenta en `turnos_completados`. Por defecto, en este contrato:
  `no_certificable`.
- **Q2.** Qué es una «inferencia» en §6.3. Por defecto: filas R4 de Claude en producción, contados
  los intentos fallidos.
- **Q3.** ¿El turno reproducido de la aprobación (`aprobacion_turno`) entra en
  `consumo_agregado_caso`? El código actual dice que no (R:1435-1436).
- **Q4.** El defecto residual de la señal de fuga (R3-N2, área C: negación ajena e incisos). ¿Se
  corrige antes de construir la cadena o se declara?
- **Q5.** ¿El cuarto argumento es R8 (por defecto) o `custodia_manifest.json`? Con este último, R9,
  R7 y la atribución pre-registrada necesitan otro ancla.
- **Q6.** ¿El kappa de las salidas reales se calcula solo sobre la versión nueva (por defecto) o
  sobre las 200 salidas?
- **Q7.** ¿Los decisivos estables usan solo los reps 1..R (por defecto) o también los de la
  extensión?
- **Q8.** `negativa_correcta` (§5.4.1) no tiene productor (B3). ¿Se deriva de la pasada 2, con un
  campo nuevo del esquema que exigiría v1.4, o queda falso por defecto?
- **Q9 (precondición de la piloto, no solo de precisión).** Telemetría:
  - **Caché del CLI de Claude.** Si el CLI omite los componentes de caché cuando valen 0, con la
    regla por defecto (obligatorios) la primera llamada de juez ya es desconocida y §5.1 detiene
    todo el juicio.
    - Evidencia parcial: `output/validation/claude-opus55-{final,review}.json` traen
      `cache_read_input_tokens` y `cache_creation_input_tokens`, pero con valores distintos de cero.
    - No prueban que el campo aparezca cuando vale 0, y no registran la versión del CLI.
    - Hay que acreditarlo con una salida guardada de la versión instalada antes de la piloto.
  - **Eventos `usage` de Codex:** si son acumulados.
  - **Motivo de parada del CLI:** `stop_reason`, con la evidencia de §4.3.
- **Q10.** ¿Quién escribe `atribucion_preregistrada` (nodo → métricas, plan, Bloque 4)?
  - Este contrato lo ancla en R1 de la versión nueva, que se escribe **antes de producirla**. La
    alternativa es el sha256 de la sección del plan del Bloque 4.
  - Un mapa escrito en R8, después de ver R4, sería un pre-registro débil.
  - Sin mapa, toda subida de más del 10 % reprueba.
- **Q11.** Modo del Bloque 0: medir y publicar la línea base de 0.3.3 con un solo directorio, sin
  veredicto global. Hay que fijar su salida.
- **Q12.** **Precondición.** El hash del evaluador cambiará, porque cambian `jueces.py`,
  `metricas.py`, VJ y los módulos nuevos. Hay que confirmar que el reservado no se ha usado todavía
  (el registro de uso no se leyó en esta tarea) y que la validación reservada se corre después de
  implementar este contrato.
- **Q13.** La decisión de Pipe sobre C19 tiene que constar en el protocolo. ¿Como aclaración C27 de
  v1.3 o como v1.4?
- **Q14.** **Consecuencia de C18 que conviene llevar a Pipe.** Ningún CLI tiene cota, así que
  bastará un solo intento fallido entre miles de llamadas para que el banco no pueda certificar. La
  reanudación permite terminar, no certificar. ¿Se busca acreditar una cota (C18), lo que exige fijar
  el número de reintentos del CLI sin cambiar la conducta del producto, o se acepta?
  - Las salidas guardadas del CLI traen `num_turns` y `usage.iterations`. Podrían servir de
    evidencia del número de peticiones por invocación, pero solo en las llamadas que terminan bien;
    un fallo no deja JSON.
  - No resuelve C18 por sí solo.
- **Q15.** Si falta la estabilidad o la pasada 2 de Codex del 15 %, ¿`no_certificable` (por defecto)
  o solo «publicación incompleta»?
- **Q16.** El subtipo `fuga` de una unidad confirmada: ¿basta con que lo marque cualquier voto de
  defecto (por defecto), o decide el subtipo mayoritario? Hoy `recuento` toma solo el de Opus
  (J:1073-1074) y pierde la fuga que solo vio Codex.
- **Q17.** La prueba E2E-1 necesita el clúster aislado levantado. ¿Quién lo provee y en qué tramo?
- **Q18.** ¿`research_sources` lleva el texto de cada pasaje? Si no lo lleva, el juez no puede
  comprobar las fuentes del corpus y el runner debe persistirlo (sin verificar en esta tarea).

### 8.4 Resoluciones del director (2026-10-12)

Estas resoluciones son técnicas y metodológicas, y las revisa Astra. Ninguna se atribuye a Pipe.
Primero va la redacción original; las revisiones posteriores al dictamen de Astra sobre la v1
(K1–K12) van marcadas **[REVOCADA]** o **[REVISADA]**, con la regla vigente a continuación.

- **Q1. [REVOCADA por K6]**
  - ~~Una repetición con `fallo_producto` cuenta como turno no completado (§9.5) y entra en
    `turnos_completados`, con lo que puede llevar a `reprueba`. No es `no_certificable`, porque un
    producto que falla no puede eludir el veredicto por fallar. Las métricas por afirmación se
    calculan sobre los turnos completados y declaran el denominador.~~
  - **Vigente:** se aplica el protocolo tal cual. Un fallo sin texto es `no_certificable` (§4.1)
    **y además** cuenta en `turnos_completados` (§9.5); las dos reglas rigen a la vez (§3.3 A y K1).
    Sin v1.4.
- **Q2.** Se acepta el valor por defecto: una inferencia es una fila R4 de Claude en producción,
  incluidos los intentos fallidos.
- **Q3. [REVOCADA por K6]**
  - ~~El turno reproducido de la aprobación entra en `consumo_agregado_caso`, porque es consumo
    real del flujo del abogado. Se corrige R:1435-1436.~~
  - **Vigente:** el turno reproducido **no** entra en el consumo decisorio. Se mantiene «R turnos
    más aprobación» (P:453-455, P:587) y R:1435-1436 no se toca. Va al presupuesto del circuito por
    R4 (§3.3 D y E). Sin v1.4.
- **Q4. [REVOCADA por K2]**
  - ~~La señal determinista de fuga es auxiliar (§5.2, P2). La fuga decisiva la dan los jueces con
    `uso_fuente` (C21). La señal falla cerrada: una negación nunca le resta una cita. Cada positivo
    de la señal que los jueces no confirman se publica como discrepancia señal↔juez y se adjudica;
    no se cuenta como fuga ni se descarta en silencio.~~
  - **Vigente:** se conserva la regla congelada (P:479-482, C26). La señal vendorizada lleva la
    negación vinculada a la proposición sobre la cita, con la regla de §3.6 y sus pruebas
    obligatorias: los tres contraejemplos de R3-C-N2 y los dos casos de R2.
  - No hay subordinación al juez ni adjudicación nueva entre señal y juez: la fila 2 es señal
    **o** jueces. Sin v1.4. El defecto del producto (`scoring.py`) sigue fuera del banco.
- **Q5.** Se acepta el valor por defecto: la cuarta ruta es R8.
- **Q6.** El kappa de las salidas reales se calcula sobre las salidas juzgadas de **ambas** versiones.
  La comparación exige jueces fiables también sobre la base.
- **Q7.** Se acepta el valor por defecto: los decisivos estables usan solo las repeticiones 1..R
  pre-registradas.
- **Q8. [REVISADA por K1]** `negativa_correcta` se deriva de la pasada 2 con un campo nuevo de su
  esquema. Los esquemas los fija el código (C14), así que es una aclaración de v1.3 y no exige v1.4.
  Su semántica, su validación y su uso en la puerta están en R5. Los productores de
  `falsos_bloqueos` y `cambio_de_motor` están en §3.3 C.
- **Q9.** Es precondición de la piloto. Antes de la primera llamada de juez real hay que acreditar la
  forma de la telemetría del CLI instalado, con su versión registrada: la presencia de los campos de
  caché cuando valen 0, si los eventos `usage` de Codex son acumulados y el `stop_reason`. Para eso se
  hace UNA llamada mínima real por proveedor, o se usa una salida guardada de la misma versión. Si un
  campo puede faltar con valor 0, la regla de §4.1 lo trata como cero **solo** con la evidencia
  versionada de esa conducta.
  - **[REVISADA por K4]** Esa evidencia es una entrada del registro versionado de §4.4, ligada a
    comando, versión exacta del CLI, evidencia y sha256, que la puerta valida.
  - Sin entrada, la ausencia es desconocida, nunca cero.
  - Se persisten todos los eventos crudos del juez Codex (R5).
- **Q10.** Se acepta el valor por defecto: la atribución pre-registrada se ancla en R1 de la versión
  nueva, antes de producirla, y la escribe el director a partir del plan del Bloque 4.
- **Q11. [REVISADA por K11]** El Bloque 0 mide y publica la línea base de 0.3.3 con un solo
  directorio, sin veredicto global. Su salida son las métricas absolutas, el consumo descriptivo,
  el presupuesto del circuito y la matriz de §7.2, sin comparativas. Comando, firma, productor y
  esquema están en §3.5. El techo de §6.3 solo existe con las dos versiones.
- **Q12. [REVOCADA por K3]**
  - ~~El registro de uso no existe (verificado el 2026-10-12), así que el reservado no se ha usado.
    La validación reservada corre **después** de implementar este contrato, con el hash nuevo del
    evaluador.~~
  - **Vigente:** el reservado actual **se retira** y no se usa nunca (`IDENTIDADES_RESERVADO_RETIRADAS`,
    R9).
  - Un autor independiente escribe un reservado **nuevo** sobre salidas reales de la piloto de 0.3.3
    (paso 6 del HANDOFF). La inferencia «no usado» deja de ser necesaria.
  - La raíz del registro de uso se resuelve con `SHGetKnownFolderPath(FOLDERID_LocalAppData)` y no
    con variables de entorno, con prueba de reubicación conjunta (E2E-10).
  - Residual declarado: un operador con control local puede borrar el registro.
  - La validación con el reservado nuevo corre después de implementar el contrato, con el hash
    nuevo del evaluador.
- **Q13.** La decisión de Pipe sobre C19 entra como aclaración C27 de v1.3. **[AMPLIADA en v5]**
  La garantía de compromiso irrevocable de §4.2 (decisión del director, K7) se recoge en la misma
  aclaración C27, como la forma en que se aplica la reanudación.
- **Q14. [SUSTITUIDA por la decisión de Pipe «Separar calidad y cuota» (§4.5, §8.1): ningún CLI
  tiene cota, y su consecuencia ya no es la no certificabilidad sino la cuota por intervalo (§4.5)]** Se intenta acreditar la cota según C18, sin cambiar la conducta del
  producto. Para eso se
  necesitan dos datos de la documentación oficial de la versión instalada del CLI: el número máximo de
  reintentos por defecto y si en modo `-p --max-turns 1` sin herramientas se emiten peticiones de
  fondo. También hay que verificar que el entorno del banco no fija variables que lo alteren. Con eso,
  la cota del intento es (reintentos + 1) × (entrada estimada + salida máxima). Si no se puede
  acreditar, se lleva a Pipe con la cifra: un solo fallo de CLI deja el banco `no_certificable`.
- **Q15.** Se acepta el valor por defecto: `no_certificable`.
- **Q16.** Se acepta el valor por defecto, que falla cerrado: basta un voto de defecto con subtipo
  `fuga` en una unidad confirmada para que cuente como fuga. Se corrige J:1073-1074.
- **Q17.** El implementador de la cadena provee el clúster aislado sintético en el puerto 55448,
  levantado con `Start-Process -WindowStyle Hidden -Wait`. Nunca se usa el 55432.
- **Q18.** Hay que verificarlo en el código. Si `research_sources` no lleva el texto del pasaje, el
  runner lo persiste: cifrado si el caso está custodiado y ligado a I10.
- **K8, perímetro del producto (decisión nueva del director, 2026-10-12).**
  - El banco **no** cambia archivos del producto. La telemetría cruda se captura desde `eval/` con
    un envoltorio transparente y restaurable (§4.3), el mismo para 0.3.3 y para 0.4.
  - El cero del panel del abogado queda como pendiente del producto para el Bloque 1.
  - Se añade la condición de comparabilidad (P:1023-1030): si el CLI o el modelo cambian, se vuelve
    a producir la base (§3.3 A).
- **K7, reanudación (decisión nueva del director, 2026-10-12).**
  - Se distingue el consumo desconocido sin cota del que tiene cota acreditada: solo el primero
    detiene.
  - La autorización se filtra por etapa, versión, evento y suspensión.
  - Se define la reanudación de la validación.
  - La autorización permite continuar y nunca acredita consumo (R4, R6, R9, §5).
- **K5, K9, K10, K11, K12 y K1:** resueltas técnicamente según el cambio que pide Astra. Ver §9.

---

### 8.5 Resoluciones del director para la v3 (2026-10-12; no son decisiones de Pipe)

Aplicadas tal como las pidió Astra en su ronda 2:

- K1: borrador desde `draft_full`;
- K4: firma de comando;
- K5: `main` de medición previa y redondeo;
- K7: suspensiones inmutables y serialización;
- K8: identidad efectiva desde `modelUsage`;
- K10: efectos concomitantes;
- K13: instantáneas inmutables direccionadas por contenido, citadas por R1, R8 y R9, fuera de la
  huella del evaluador;
- K14: inventario cerrado de lecturas;
- K15: estado `no_enviado`.

---

### 8.6 Resoluciones del director para la v6 (2026-10-12; no son decisiones de Pipe) y pendientes

- **§5 bis.1 del autor de pruebas (manifiesto de custodia).** Se adopta la alternativa:
  - la puerta pública usa solo el manifiesto del repo;
  - el esqueleto usa `PruebaPuerta` con relajaciones separadas y `aceptar_dobles` sin relajar, y el
    resultado lleva `modo_prueba: true` (§3.1, §6.1).
- **§5 bis.2 (instantáneas).** No se escribe bajo `backend/` durante las pruebas: hay un directorio
  de instantáneas de prueba por `instantaneas_dir=` y `PruebaPuerta.directorio_instantaneas` (§3.9,
  §4.4).
- **Interfaces.** Las 1–5 y 7–10 del informe del autor de pruebas se adoptan como contrato (§6.4).
- **Interpretación declarada para Astra.** La medición del fondo se hace como **paso 0 de la
  piloto** (§4.5) y no durante las corridas, porque K13 congela la instantánea en el primer R1.
- **Pendientes:**
  - ~~la cota de Codex~~ (v7: sin objeto, porque ningún CLI tiene cota y rige la cuota por intervalo);
  - comprobar que `--debug-file` existe en `claude --help` 2.1.296, o montar el proxy local;
  - las claves de los 13 casos visibles en la custodia real.

---

### 8.6 bis Habilitación de VJ en v1.4 (v8; explícito)

**Lo único que se retira** de las exigencias de `evaluar_exigencias` (VJ:277-347) es el predicado
`consumo_certificable` (VJ:329-332). Se conservan, sin cambio:

- el **contador compartido** del circuito, con la suspensión y la reanudación de §5 y C27: la
  validación sigue deteniéndose ante un evento sin cota no autorizado;
- **cero salidas sin evaluar** (`salidas_sin_evaluar`, VJ:321);
- **cero discordancias** (`discordancias_sin_resolver`, VJ:323);
- la **acreditación v1.3 del reservado** (`acreditacion_compatibilidad_v13`, VJ:326-328);
- todas las exigencias de sensibilidad, falsos positivos, kappa y cláusula breve.

El consumo de la validación entra en la cuota (§4.5).

### 8.7 Pendientes y preguntas de la v7 para el director

- La propuesta `docs/banco-calidad-04-protocolo-v1.4-propuesta.md` necesita la revisión de Astra y
  la integración del director antes de implementar. Mientras tanto rige v1.3, y esta parte del
  contrato no se implementa.
- Queda abierto qué combinación de veredictos habilita la entrega de 0.4 (§6.4 de la propuesta). Es
  una decisión de producto, no se le atribuye a Pipe y no la toma este contrato.

---

## 9 · Cierre de las objeciones de Astra (ronda 1: K1–K12; ronda 2: parciales y K13–K15)

| Objeción | Gravedad | Qué pedía Astra | Dónde la cierran la v2 y la v3 |
|---|---|---|---|
| **K1** | Bloqueante | productores de `falsos_bloqueos` y `cambio_de_motor` (sin aceptar `false_block` derivado); transformación de `model_fallbacks`; semántica y validación de `negativa_correcta` | IC-2 (§0); §3.3 C, tabla «Entradas por corrida…»; R5, «Campo nuevo de la pasada 2»; §3.3 B (proxy); §7.2; §7.4 (`evaluador_congelado`, `metricas`); pruebas S21–S23 (§6.3) e inversa; **v3:** presencia de borrador desde `draft_full` y `reached_draft` fuera del hash crudo (§3.3 C, fila `falsos_bloqueos`; R5 `rep_sha256`; familia inversa de §6.3). |
| **K2** | Bloqueante | conservar y corregir la regla congelada de fuga, o pasar a v1.4 | §3.6 (regla de vinculación y pruebas V1–V9); §3.3 B, fila 2; §3.3 E; §7.4; §8.4 Q4 [REVOCADA]; prueba S15 |
| **K3** | Bloqueante | raíz del registro de uso independiente del entorno; reubicación conjunta; historial del reservado | R9 («Reservado nuevo…», «Raíz del registro de uso»); §1.1 (orden del Bloque 0); E2E-10; §7.4; §8.4 Q12 [REVOCADA] |
| **K4** | Bloqueante | persistir todos los eventos del juez Codex; registro versionado de acreditación validado por la puerta; pruebas de varios eventos y de acreditación ausente | R5 («Telemetría cruda de los jueces»); R4 (`uso_crudo`, `cli_version`, `acreditacion_aplicada`); §4.1; §4.4; E2E-3; I15; §8.4 Q9 [REVISADA]; **v3:** `firma_comando` en R4, capturada en `_build_command`/`_command` (§4.3); selección por familia, versión y firma; rechazo de la ambigüedad (§4.4); `firmas_previstas` (R1); E2E-16. Cierra la vía ausencia→cero por otro comando. |
| **K5** | Mayor | productor y estimación previa acreditada de Codex en la piloto; bloquear su ausencia; probarlo desde el montaje real del Bloque 7 | R1 (`cadenas_politica`, `puede_codex`, `estimacion_piloto_codex`); R13; §3.3 A («Codex en la piloto»); §7.3; E2E-9; **v3:** R14 (`banco04_medir_codex main`, presupuesto y control propios, asignación por clase); R13 v2 con redondeo `(5·max+3)//4`; E2E-12; R-14. **v4:** manifiesto de la medición exento de R13 (`proposito: medicion_codex`, R1); R13 dentro del directorio de la medición, ligado a su manifiesto y citado en un solo sentido por el R1 consumidor (R13, R14). |
| **K6** | Mayor | resolver los conflictos de Q1 (§4.1) y Q3 (consumo de la aprobación) sin cambiar reglas | §3.3 A («Texto juzgable»); §3.3 C (`turnos_completados`); §3.3 D (`aprobacion`); §8.4 Q1 y Q3 [REVOCADAS]; prueba S21 |
| **K7** | Mayor | filtrar la autorización por etapa, versión, evento y suspensión; distinguir sin cota de con cota; reanudación de la validación; la autorización no acredita consumo | R4 («Clases de consumo»); R6 (esquema v2 y reglas de validez); R9 («Reanudación de la validación»); §4.1; §5.1–§5.4; E2E-3 (variante con cota); E2E-4; **v3:** suspensiones inmutables por id y etapa (R6); cerrojo y `seq` del bloque que serializan control, envío y cierre (§4.2, §5.4); E2E-13 (intercalación) y E2E-14 (dos ciclos). **v4:** el cerrojo cubre en una sola sección el control, `check_and_reserve` y el despacho efectivo (`seq_envio`), y no se libera antes del envío (§4.2, §5.4); U(C) por `seq_envio`; registro de orfandad con `seq_deteccion` propia; E2E-13 (i) «B controla, A cierra, B envía» y (iii) orfandad tardía. **v5:** garantía de **compromiso irrevocable** adoptada expresamente (`seq_envio` bajo el cerrojo es el punto de compromiso; la invocación real no se serializa; residual declarado) en §4.2, §5.1 y §5.4; E2E-13 (i) admitida si se comprometió antes del cierre de A, con barrera entre compromiso e invocación, y (ii) detenida o `no_certificable` si se comprometió después; coherencia de secuencias por clase de fila, con `seq_inicio < seq_envio < seq_deteccion` y cierre nulo para las huérfanas enviadas; registros de orfandad en §3.9 (punto 8, adscritos a R4); C27 (§8.4 Q13). |
| **K8** | Mayor | exigir la comparabilidad (reproducir la base si cambian CLI o modelo); perímetro del parche; invariancia del comportamiento del abogado | §4.3 (intercepción desde `eval/`, sin cambios de producto); R1 (`sha_producto`, `rutas_modificadas_respecto_del_producto`, `codex_cli_version`); §3.2 paso 1; §3.3 A («Comparabilidad», con la base del Bloque 0 reutilizable si no cambian el CLI ni el modelo; «Perímetro», solo `eval/` y `execution/`); R4 (`bloque`); §6.1 (`proveedores` con alcance de módulo); E2E-6; I14; §7.4; **v3:** `model_usage_crudo` completo e `identidades_efectivas` (R4); comparación por identidad efectiva y `identidad_efectiva_ausente` (§3.3 A); E2E-18. |
| **K9** | Mayor | orden total reproducible para los casos de la extensión; población de las submuestras fija; preservar las originales | §3.4 («Selección de casos con orden total reproducible»); §3.7; §3.3 E (estabilidad y Codex 15 %); §7.2 (`seleccionar_con_semilla`); §7.4 (`casos_extension`); §8.2 R-7 [SUSTITUIDA] |
| **K10** | Mayor | separar la manipulación incoherente de la mutación semántica (regenerar desde `main`); recorrido positivo de la extensión y de Codex de producción; que el mundo no fabrique telemetría | §6.1 (`mundo=` sin telemetría propia, `origen: "captura"`); §6.2 (mutación semántica del esqueleto, E2E-8); §6.3 (familias S e I, F17-ext); §3.8 (códigos exactos que exige la familia I); R5 (`rep_sha256` sobre la parte cruda); **v3:** cierre de dependencias de los efectos concomitantes permitidos y prohibición de fallos ajenos o de identidad (§6.3); el arranque de R13 queda cubierto por K5 y las lecturas por K14. |
| **K11** | Mayor | comando, firma, productor y esquema del informe del Bloque 0, separado del techo comparativo | §1.1 (Bloque 0); §1.2 (`linea-base`); R8 (`bloque_0_linea_base`); §3.5; E2E-11; §8.4 Q11 [REVISADA] |
| **K12** | Menor | predicado de limpieza invertido | §3.2 paso 1 (`arbol_limpio == true` y `dobles == false`); §3.3 A («Identidad de cada versión») |
| **K13** | Mayor | una sola regla de congelamiento de las acreditaciones; efecto sobre R9 y sobre la huella del evaluador | §4.4 («Regla única de congelamiento»); R1 y R8 (`telemetria_acreditada_sha256`); §1.2; E2E-17 **v4:** integridad de todas las instantáneas separada de la igualdad, exigida solo entre las referencias R1 y R8; R9 se coteja con su propia referencia (§4.4, coherente con E2E-17). |
| **K14** | Mayor | ampliar el inventario de `entradas_leidas` a las acreditaciones, sus evidencias y las fuentes de R13 | §3.9; E2E-2; §4.4 (validación); R-14 |
| **K15** | Mayor | estado terminal comprobable de «no enviado» para la denegación de `check_and_reserve`, sin contarlo como consumo desconocido ni como inferencia | R4 (`estado`, `t_envio_utc`); §4.2 («Orden fijo de una llamada»); §5.4 (U(C) excluye lo no enviado); E2E-15; códigos de §3.8 **v4:** las llamadas no enviadas quedan expresamente fuera de U(C) ⊆ A(C) («llamadas comprobadas», §5.4); clasificación única de las huérfanas (R4), remitida desde §4.1 y §4.2. |
| **K16** | Mayor | R13 permitía acreditar una lista incompleta de llamadas (10 + 1.000 citando solo 10 daba 13 en vez de 1.263) | R1 (`seleccion_medicion`, k preregistrado); R14 (asignación preregistrada y recibos de completitud sin texto); R13 (igualdad entre las filas citadas, **todas** las R4 de la medición y los recibos; el cero exige una corrida completa; prueba obligatoria 10 + 1.000 → 1.263); §3.9 punto 2; §3.3 E (presupuesto del circuito con las filas de medición) |
| **Pipe 2026-10-12 «Acotar y medir»** | Decisión **[REVOCADA en v7]** | cota del intento fallido del CLI de Claude | sustituida por «Separar calidad y cuota» (fila siguiente) |
| **Director v6 · §5 bis del autor de pruebas** | Decisión | manifiesto de custodia en la puerta pública; escritura de instantáneas bajo `backend/` en las pruebas | §3.1 (manifiesto del repo, `PruebaPuerta` con relajaciones separadas, `modo_prueba`); §3.8 (`instantaneas_de_prueba`); §3.9 punto 3; §4.4 (`instantaneas_dir=`); §6.1 (puerta del esqueleto); §6.4 (interfaces 1–5 y 7–10); §8.6 |
| **Astra sobre v6 (a)** | Bloqueante | la cota de §4.5 no era conservadora: entrada heurística, salida dependiente del modelo, fondo muestral | §4.5 v7: ningún CLI tiene cota, y el intento sin cota da cuota `estimada` con estimación empírica **no garantizada**, nunca certificada; R4 (`cota` nula, `estimacion_empirica`); E2E-19 1–4 |
| **Astra sobre v6 (b)** | Mayor | imponer `CLAUDE_CODE_MAX_RETRIES=10` alteraba la conducta | §4.3 v7 (el envoltorio devuelve el entorno idéntico); §4.5 («Entorno del CLI»); E2E-6 punto 2; E2E-19 5 |
| **Pipe 2026-10-12 «Separar calidad y cuota»** | Decisión | dos veredictos; la calidad es certificable con intentos sin cota; la cuota es certificada o estimada; la suspensión usa conocido + estimación; Codex en la misma regla | §3.1 (salida y precedencia por veredicto); §3.3 D y E; §3.5 (`cuota` en el Bloque 0); §3.8; §4.1; §4.5; §5.1 y §5.4; §6.2 (E2E-3, E2E-14, E2E-19); §6.3 (S09, I03); §8.1; §8.7; propuesta de protocolo v1.4 |
| **Astra sobre v7 (a)** | Mayor | dos caminos por los que el consumo invalidaba la CALIDAD: piloto con fila sin cota; estimación recalculada que contradecía por un máximo posterior | §3.3 A (R11 y R12: piloto con la estimación inicial, R reproducible y todas las repeticiones exigidas); R4 y §4.5 (estimación inicial congelada con `corte_seq` y observaciones registradas; actualización final aparte); E2E-19 7 y 7b |
| **Astra sobre v7 (b)** | Bloqueante | certificar el cumplimiento solo si el máximo posible cumple, y el exceso solo si el mínimo excede; estado del intervalo que cruza, también con cotas finitas | §4.5 («CUOTA, por intervalo»); §3.1 (precedencia); §3.3 D; §3.5; E2E-19 3b (contraejemplo 100 frente a 10 + 90), 3c (inverso) y 3d |
| **Astra sobre v7 (d)** | Mayor | S08 y S10 con resultado separado de CUOTA; textos viejos del protocolo | §6.3 (S08, S10 y cierre «consumo»); propuesta v1.4 (§4 y barrido de §5) |
| **Astra sobre v7 (e)** | — | retirar solo `consumo_certificable` de VJ | §8.6 bis |
