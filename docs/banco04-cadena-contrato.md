# Banco 0.4: contrato de la cadena (producir, juzgar, decidir)

Versión del contrato: **banco04-cadena/v1** (propuesta). Fecha: 2026-10-12. Base: HEAD `798a8b2`,
rama `feat/mia-04-hermes-legal`, protocolo **banco04-v1.3** (`docs/banco-calidad-04-protocolo.md`).

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
    - el texto que ve el abogado y el material del turno;
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
   (versión base y nueva,     R12 aprobaciones_plan, R6 SUSPENDIDO / reanudaciones
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
```

### 1.2 Puntos de entrada y quién llama a quién

| Etapa | Entrada única | Cadena de llamadas desde `main` |
|---|---|---|
| Producir | `R:1962 main` (`--fase produccion`, `aprobaciones` y la nueva `extension`) | `verificar_aislamiento` → `_montaje_real` (R:1681) → instala la captura del ledger (`telemetria.instalar`, nuevo) y el contexto de llamada → `ejecutar_banco` (R:1046) → `_ejecutar_una` (R:954) fija el contexto `(versión, caso, rep, intento, fase)` → `deps.producir` → `harness.run_case` (H:502) → grafo → `llm.call_llm` → `_invoke` envuelto por `SG._guarded_invoke` (SG:1126) → `telemetria.registrar_llamada` (`en_curso` antes de invocar y `cerrada` al volver) |
| Validar jueces (prerrequisito, §8.6) | `VJ:651 main` | `validar_circuito` → `evaluar_item` → `jueces.pasada1` con runners envueltos por `telemetria` → escribe R9 crudo |
| Juzgar | `execution/banco04_juzgar.py main` (nuevo), subcomandos `registrar-cadena` y `juzgar` | `registros.cargar_corridas(dir)` → `ceguera.preparar_candidato` (llave = `custodia.semilla_hmac()`) → `jueces.pasada1`, `pasada2`, `votar_cobertura`, `adjudicar_negativas_falsas`; estabilidad con el 10 % y Codex en la pasada 2 con el 15 %, ambos con `seleccionar_con_semilla` → `registros.escribir_juicio` (R5) |
| Decidir | `execution/banco04_decidir.py main` (nuevo), subcomandos `previa` y `veredicto` | `puerta.decidir(...)` (nuevo, `backend/mia/eval/banco04/puerta.py`) → `registros` (lectura estricta) → `reproduccion` (runners reproducidos) → internos de `M` → `VEREDICTO.json` |

**Módulos nuevos:**

- `banco04/telemetria.py`: regla única de uso, ledger por llamada, contexto y control previo.
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
| `estado` | `en_curso` \| `cerrada` | se escribe `en_curso` **antes** de invocar |
| `t_inicio_utc`, `t_fin_utc` | str ISO-8601 UTC | `t_fin` es `null` mientras siga en curso |
| `fase` | enum | `produccion`, `aprobacion_turno`, `aprobacion_aprobar`, `aprobacion_trabajos`, `embeddings_siembra`, `juicio_p1_opus`, `juicio_p1_codex`, `juicio_tercer_voto`, `juicio_negativa_falsa`, `juicio_p2_opus`, `juicio_p2_codex`, `juicio_voto_cobertura_opus`, `juicio_voto_cobertura_codex`, `juicio_estabilidad`, `validacion`, `sin_contexto` |
| `caso_id`, `rep`, `intento` | str/int \| null | vienen del contexto de llamada (ContextVar de `telemetria`) |
| `candidate_id`, `pasada`, `objetivo` | str \| null | jueces; `objetivo` = id de unidad, hecho o (punto, parte) |
| `alias` | str | el alias de la cadena, tal como lo recibe `_guarded_invoke` |
| `familia` | `claude_cli` \| `codex_cli` \| `api` \| `local` \| `embeddings` | decide la regla de §4 y el proveedor de cuota |
| `proveedor_cuota` | `claude` \| `codex` \| `ninguno` | `codex` si el alias empieza por `cli-codex`; `ninguno` para embeddings; el resto, `claude` (igual que `GuardBanco.tokens_llm`, R:1615-1617) |
| `modelo_efectivo`, `modelos_cli` | str \| null, list \| null | de `resp.mia_model_hint` / `resp.mia_modelos_cli` (§4.3) |
| `esfuerzo`, `esfuerzo_fuente` | str \| null, `respuesta` \| `politica` \| null | en un fallo no hay `resp`: se deriva de `llm._cli_effort(alias, task, escalada)` y la fuente es `politica` |
| `tarea`, `escalada`, `nodo` | str \| null | `nodo` = `metrics.usage.current_node()` (§4.3) |
| `uso_crudo` | dict \| null | lo que entregó el proveedor, sin tocarlo (§4.3) |
| `uso_validado` | dict | `{consumo_conocido: bool, entrada, salida, cache_lectura, cache_escritura, total: int\|null, componentes_ausentes: [str], regla_version}` (§4.1) |
| `exito` | bool | |
| `tipo_error`, `proveedor_no_alcanzado` | str \| null, bool \| null | solo la clase de la excepción, nunca su texto (I8) |
| `motivo_parada`, `motivo_parada_fuente` | str \| null, `cli` \| `api` \| `no_informado` | §4.3, Q9 |
| `cota` | dict | `{tokens_entrada_estimados, cota_salida, tokens_cota_superior, fuente, motivo}`; igual que SG:1233-1247; en `cli-*` la cota es `null` (C18) |
| `reanudacion_vigente` | str \| null | referencia de R6 bajo la que se lanzó (jueces y Codex de producción) |
| `eventos_desconocidos_vistos` | list[str] | ids de filas desconocidas que el control previo vio (§5) |
| `prompt_sha256` | str \| null | obligatorio en las fases `juicio_*` y `validacion` |

**Una fila es «desconocida»** si `estado == "en_curso"` y el proceso que la abrió ya no está (huérfana),
o si `uso_validado.consumo_conocido == false`. Una fila desconocida cuenta con su `cota` si la hay. Sin
`cota`, el techo queda no certificable.

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
| `rep_sha256` | sha256 canónico del R2 juzgado |
| `texto_sha256` | `{diagnostico, borrador}` (texto completo, antes del cegado) |
| `candidate_id`, `paquete_sha256` | el paquete no se guarda: la puerta lo reconstruye (§3.2, paso 4) |
| `llamadas[]` | en orden: `{ledger_id, etapa, objetivo, intento (1\|2), prompt_sha256, esquema, respuesta: {salida (JSON literal del modelo), crudo_sha256, error, uso, modelo_reportado, cli_version, latencia_ms}}` |

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

**Derivado opcional**, solo para auditoría y que la puerta **no abre**:
`rep-NN.juicio.derivado.json` con decisiones, recuento, `pares_kappa`, hechos y puntos. Una prueba
de §6 exige que mutarlo no cambie el veredicto.

### R6 · Suspensiones y reanudaciones (no cifrado; I10)

- **`S/<ver>/SUSPENDIDO.json`.** Conserva R:939-951 y añade `manifiesto_sha256` (hoy falta, B12),
  `etapa` (`produccion` | `aprobaciones` | `juicio` | `validacion`) y `eventos` (ids de R4 que la
  dispararon).
- **`S/<ver>/reanudaciones/<NNN>.json`** (nuevo, exclusivo; sustituye a `SUSPENDIDO.reanudado.json`,
  R:1056 y R:1458): `{schema "banco04-reanudacion/v1", n, referencia_aprobacion_pipe: str no vacía,
  registrada_utc, alcance_etapas: [..], cubre: {suspension_sha256: str|null,
  eventos_desconocidos: [ids R4]}, eventos_sha256 (sha256 canónico de las filas cubiertas tal como
  estaban al registrar), manifiesto_sha256}`.

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

### R9 · Validación reservada cruda (cifrada; ligada al hash del evaluador)

- **Ubicación:** `<custodia>/validacion/<identidad_reservado>/registro.enc`, más la ficha
  `registro.json`.
- **Contenido:** `{schema "banco04-validacion/v1", identidad_reservado, hash_evaluador,
  acreditacion_v13 (contenido completo), items: [{item_id, paquete_sha256, llamadas[] (mismo esquema
  que R5)}]}`.
- **Cambios en VJ:**
  - deja de excluir `verdades` y `pares_kappa` (VJ:388-389);
  - persiste las respuestas crudas en lugar del resumen;
  - la llave de ceguera deja de ser `os.urandom(32)` (VJ:699) y pasa a ser HMAC(semilla_hmac,
    "validacion"), para que la puerta reconstruya los paquetes;
  - la escritura deja de ser `write_text` no atómico (VJ:706).

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

---

## 3 · La puerta

### 3.1 Firma

- **Pública:** `puerta.decidir(*, dir_nuevo: Path, dir_base: Path, custodia: Path, cadena: Path) -> dict`.
- **Línea de comandos:** `execution/banco04_decidir.py veredicto --nuevo <S/0.4> --base <S/0.3.3>
  --custodia <MIA_BANCO04_CUSTODIA> --cadena <MANIFIESTO_CADENA.json> --salida <VEREDICTO.json>`.
- **Prohibido en la firma:** cualquier parámetro de conclusión, agregado, etiqueta, semilla,
  inventario, `R`, techo, atribución, recibo, `suspendido` o recuento.
- **Único parámetro adicional, solo de Python y solo para pruebas:** `_prueba: PruebaPuerta | None`.
  Relaja exactamente tres cosas, **y nada más**:
  1. abrir la custodia con un desprotector DPAPI de prueba y un manifiesto de custodia de prueba;
  2. aceptar `dobles: true` en R1 y R8;
  3. aceptar `arbol_limpio: false` en R1, porque las pruebas corren en árboles de desarrollo.

  Con `_prueba`, el resultado lleva `"modo_prueba": true` y `resumen_publicable` se niega a
  publicarlo.
- **Salida:** `{veredicto: aprueba|reprueba|no_certificable, motivos: [{codigo, detalle}],
  filas_rojas: [..], condiciones: [{id, valor, umbral, estado: cumple|no_cumple|no_aplica|sin_dato,
  fuentes: [rutas+sha256]}], comparativas: [...], techo: {...}, entradas_leidas: [{ruta, sha256}],
  rotulo, modo_prueba}`.
- **Precedencia:** `no_certificable` > `reprueba` > `aprueba` (C15).

### 3.2 Procedimiento (orden fijo)

1. **Identidad:**
   - lee R8;
   - lee R1 de cada directorio y exige que su sha256 canónico sea igual a `versiones[].manifiesto_sha256`;
   - exige `arbol_limpio` y `dobles` falsos (salvo `_prueba`);
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
| Identidad de cada versión | R1 frente a R8 | falta R1; el sha256 difiere; árbol sucio; `dobles`; protocolo distinto |
| Evaluador congelado | `hash_evaluador()` actual = R8 = cada R5 = R9 | alguno difiere |
| Muestra | ids de `PR` + `custodia.casos()` | no son 17, o hay ids que no coinciden |
| Repeticiones | R2 presentes por (versión, caso) | el conjunto de reps no es exactamente {1..R} (+{R+1..R+5} si R7), hay duplicados, falta un R2 (incluido `limite_de_uso`, que no escribe R2, R:1041) |
| Texto juzgable | R2 `estado`, `diagnosis_full` y `draft_full` (H:738-740) | corrida `completo` sin texto completo (§4.1); `fallo_producto` → Q1 |
| Caso y jurisdicción | R2 `caso_digest`, `jurisdicciones_fijadas` | el digest difiere del caso cargado; las jurisdicciones difieren de `custodia.jurisdicciones()` (custodiados) o de `[]` (visibles) |
| Ledger de la corrida | R2 `intentos[].llamadas` frente a R4 | falta un id; hay una fila con ese contexto que no está en la lista; contexto distinto; fila huérfana sin cerrar |
| Juicio completo | reproducción | falta una llamada que la reproducción pide; sobra una que no pide; el `prompt_sha256` no coincide; queda una salida no evaluada (estructural tras el reintento, J:1764); falta el tercer voto (`no_evaluada_tercer_voto`, J:1863) |
| R11 y R12 | se recalculan con `decidir_r` y `elegir_aprobaciones` | ausentes o distintos; consumo de la piloto con alguna fila desconocida sin cota |

**B · Umbrales absolutos (§6.1).** Por corrida, la puerta construye la entrada de `metricas_corrida`
(M:266) solo desde la reproducción y desde R2, R4 y la custodia. `evaluada` deja de ser un parámetro
(M:333): se deriva de que las dos pasadas, la adjudicación y la cobertura estén completas.

| Fila | Se recalcula desde | `no_certificable` si | Efecto si falla |
|---|---|---|---|
| `afirmaciones_sin_respaldo` = 0 | recuento de la pasada 1 + `confirmadas` de las negativas falsas, sumado sobre todas las corridas completadas de todos los estratos | la reproducción está incompleta | reprueba |
| `fuga_jurisdiccion` = 0 | por corrida: `senal_fuga` (M:248) con el texto completo de R2 y `jurisdicciones_fijadas`, **o** una unidad confirmada en la que algún voto de defecto lleve el subtipo `fuga` (Q16) | falta el texto o faltan las jurisdicciones | reprueba |
| `definitivo_con_lectura_insuficiente` = 0 | celda de §7.2 (M:280): alcance C8 + `estado_cobertura` (M:150) con decisivos de la clave, `cubierto` final y `disponible` + conducta de la pasada 2 | falta la pasada 2 | reprueba |
| `discordancias_sin_resolver` = 0 | `len(recuento.discordancias_sin_resolver)` (es una lista, J:1076; hoy M:341 hace `int()` sobre ella) + `discordancias` de las negativas falsas + cobertura con resultado `discordancia_sin_resolver` | si faltan los votos crudos, lo cubre el bloque A («Juicio completo»); cualquier discordancia > 0 | no certificable |
| `kappa_reservado` ≥ 0,6 | `evaluar_kappa(pares, conjunto="reservado")` sobre los pares de la reproducción de R9 | falta R9; kappa < 0,6 | no certificable |
| `kappa_salidas_reales` | `evaluar_kappa(..., "real")` sobre `pares_kappa` reproducidos de las corridas de la versión nueva (Q6) | se exige y queda < 0,6 | no certificable. Indefinido o inestable: se publica y no cuenta como ≥ 0,6 (§8.5) |
| `circuito_sobre_mutaciones_reservadas` | `evaluar_exigencias` (VJ:277) sobre la reproducción de R9 + acreditación de R9 + consumo de las filas R4 `validacion` | falta R9; `circuito_utilizable` falso | no certificable |
| `evaluacion_completa_dos_jueces` | resultado del bloque A, «Juicio completo», en las dos versiones | cualquier corrida del inventario sin juicio completo de los dos jueces (regla del bloque A) | no certificable |
| Cobertura de decisivos, lectura completa (media ≥ 0,90; ningún caso < 0,80) | `cubierto` final por hecho decisivo de la clave (pasada 2 y cobertura adjudicada), media sobre R por caso y media de casos por estrato | la clave del caso no se puede leer | reprueba |
| `aprobacion_sin_edicion_proxy` ≥ 0,60 | M:316-327: `completada` (R2 `estado`), defectos (fila 1), omisiones (puntos de la pasada 2), celda, `aprobaria_sin_editar`; `negativa_correcta` → Q8 | falta la pasada 2 | reprueba |
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

**D · Techo de cuota (§6.3) y C25.** Todo sale de R4, filtrado por versión y caso.

- **`corridas[rep]`** = filas `fase=produccion` de (caso, rep), con todos sus intentos.
  - `tokens` = Σ de `uso_validado.total` de las filas `proveedor_cuota=claude` conocidas, más la
    `cota.tokens_cota_superior` de las desconocidas.
  - `tokens_codex`: ídem con `codex`.
  - `inferencias`: Q2. Por defecto, el número de filas `claude` de la corrida.
- **`aprobacion`** = filas `aprobacion_aprobar` y `aprobacion_trabajos` del caso (Q3 para
  `aprobacion_turno`).
- Después se llama a `techo_cuota` (M:772), adaptado a este esquema (§7). Su `R_por_caso` se coteja
  con el inventario.

| Condición | `no_certificable` si | Efecto |
|---|---|---|
| Total agregado, ponderado por caso, extremo por caso y extremo entre repeticiones (Claude 1,25×; Codex 0,50×) e inferencias | una fila desconocida sin cota; una fila de producción o aprobación con `fase=sin_contexto` o `caso_id` nulo dentro de un tramo del banco (cuenta en el total, pero impide el cálculo por caso); falta la aprobación de un caso | `no_cumple` → reprueba |
| C25: atribución de subidas > 10 % | `usage_by_node` por ámbito = las **mismas filas** de R4 agrupadas por `nodo` (nulo → `(sin nodo)`). La igualdad con el consumo medido (M:1027-1029) se cumple por construcción. El nodo atribuido es el de mayor aumento. La subida es atribuible si ese nodo está en `atribucion_preregistrada` de R1 de la versión nueva (con su sha256 igual al de R8) **y** alguna métrica suya tiene veredicto `mejora` (recalculado) en una unidad del mismo grupo (a)/(c) | si el techo no es certificable, lo cubre la fila anterior; si el sha256 del mapa no coincide con R8. Un mapa ausente no da `no_certificable`: la subida queda no atribuible | no atribuible → reprueba |

**E · Alcance C8, fuga §5.7, kappa y estabilidad, y circuito §3.4.**

| Condición | Se recalcula desde | `no_certificable` si |
|---|---|---|
| Alcance C8 | `alcance_desde_fragmentos` (M:1306) con los fragmentos por pieza de la definición del caso y `envio_desde_material(material_turno)`. Cuenta como medido **solo** si `material_turno.fragmentos_en_prompt.medido` y `.completo` son verdaderos (H:858-861). Así se cierra la medición parcial de B3 | nunca por esto. Sin medición el alcance es insuficiente (§7.2), y se publica cuántas corridas no la tienen y en cuántas difiere de `alcance_lectura` |
| Fuga §5.7 | fila 2 del bloque B. Se declara el defecto residual de la señal (R3-N2, área C) → Q4 | falta el texto o las jurisdicciones |
| Estabilidad (§8.6) | conjunto = `seleccionar_con_semilla(candidatos de la versión, 10 %, semilla_hmac)`; `acuerdo_estabilidad` (J:921) sobre la reproducción de las dos pasadas 1 de Opus | falta la segunda pasada de un elegido, o existe una de un no elegido (Q15) |
| Codex en la pasada 2, 15 % (§8.2) | ídem, con el 15 %; `acuerdo_pasada2_agregado` (J:1179), que se publica | ídem |
| Techo del circuito (§3.4) | Σ de las filas R4 del bloque (las dos versiones y la validación) por proveedor | acumulado ≥ techo; un R6 `SUSPENDIDO.json` sin una reanudación que lo cubra |
| Orden tras un consumo desconocido | §5.4 | una llamada de juez o de Codex de producción lanzada con un evento desconocido sin cubrir |

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
   - `casos` = unión de `casos_para_extension(previa)` (M:677) de las métricas no concluyentes,
     con un tope de 5 (R-7, §8.2);
   - `corridas_por_caso` = 5.

   Si no coincide, `no_certificable`. Si falta R7, `no_certificable` (`no_concluyente_sin_extension`).
5. Exige en **las dos versiones** los R2 de los reps R_original+1..R_original+5 de esos casos, con
   `extension_sha256` = sha256 de R7, y juzgados. Exige que no exista ningún otro rep adicional.
6. El veredicto final de esas métricas se calcula con **todas** las corridas (1..R+5) y pasa por
   `veredicto_tras_extension` (M:684). El recibo del llamador desaparece (se elimina `_motivos_recibo`,
   M:1086-1116). Con esto se cierra R3-N2 del área A.

**Quién escribe R7.** `banco04_decidir previa`, que usa los mismos internos de la puerta. La
selección de casos no es libre: la puerta la recalcula.

---

## 4 · Telemetría: una sola regla de uso

### 4.1 Regla (`telemetria.uso_validado(familia, uso_crudo) -> UsoValidado`)

La aplican la captura de producción (§4.2) y los runners de juez, que sustituyen
`ControlCuotaJueces.despues` y `tokens_conocidos`, J:1375-1472. **Componentes ausentes ⇒
`consumo_conocido = false`, nunca cero.**

| Familia | Componentes obligatorios (entero ≥ 0) | Opcionales: si vienen, válidos | Total |
|---|---|---|---|
| `claude_cli` | `input_tokens`, `output_tokens`, `cache_creation_input_tokens`, `cache_read_input_tokens` (Q9: obligatorios mientras no se acredite que el CLI los omite solo cuando valen 0) | — | suma de los cuatro |
| `codex_cli` | entrada (`input_tokens` \| `prompt_tokens`), salida (`output_tokens` \| `completion_tokens`); `cached_input_tokens` va dentro de la entrada y no se suma | `total_tokens` | máx(entrada + salida, `total_tokens`). Con más de un evento `usage` sin acreditar que es acumulado → desconocido (Q9) |
| `api` | `prompt_tokens`, `completion_tokens` | caché passthrough (`cache_*_input_tokens`) y `prompt_tokens_details.cached_tokens` | `total_tokens` válido, o prompt + completion, + `cache_creation` |
| `local` | ídem `api` | ídem | ídem; `proveedor_cuota` sigue la regla de R4 |
| `embeddings` | caracteres de los textos (estimación declarada, SG:1294) | — | `proveedor_cuota = ninguno`: no cuenta en ninguna cuota |

- **Fallo (excepción):** siempre `consumo_conocido = false`, con la cota de SG:1209-1243. En `cli-*`
  la cota es `null` (C18).
- **Éxito con un componente ausente o inválido:** `consumo_conocido = false`, con
  `componentes_ausentes`. Cota: `cli-*` → `null`; `api` → entrada estimada + `max_tokens` aplicado.
- **`uso_crudo` ausente:** desconocido.
- **Fila huérfana `en_curso`:** desconocida y sin cota.
- **Prohibido:** registrar una llamada como éxito con 0 tokens. Ese es el patrón de SG:1268-1274 que
  reprodujo R3-N2 del área B. `note_call` puede seguir sumando para el saldo en USD, pero el ledger y
  `ContadorCuota` se alimentan solo de `uso_validado`.

### 4.2 Captura en el eval (no es producto)

- **`SG._guarded_invoke` (SG:1126-1275):**
  - antes de `check_and_reserve` escribe R4 `en_curso`, con el contexto y la cota;
  - al volver, la cierra con `uso_crudo = getattr(resp, "mia_uso_crudo", <fallback>)` y
    `uso_validado`;
  - en el camino de excepción, con la cota de SG:1209-1243.
  - El `<fallback>` para la familia `api` es `resp.usage` serializado tal cual. Para `claude_cli` y
    `codex_cli` sin `mia_uso_crudo`, es `None` → desconocido.
- **`GuardBanco.check_and_reserve` (R:1590-1601):** antes de toda llamada Codex de producción
  consulta el contador reconstruido **desde R4 en disco**, incluidas las filas desconocidas de su
  propio proceso todavía no trasladadas (hueco de R:1590 señalado en el área B).
- **`ContadorCuota` (R:318-463):** se reconstruye solo desde R4 (sustituye a R:877-900 y
  R:1199-1221).
- **Al cerrar cada fila**, se comprueba el acumulado frente al techo; si lo alcanza, la suspensión es
  inmediata. Cierra el desborde por la última llamada (R3-N3 del área B).
- **`codex_cli_adapter.call_graph_cli` (`codex_cli_adapter.py:536-538`, alias `cli-codex-eval`):**
  adjunta `mia_uso_crudo` con los `None` del parser (`_parse_events`, :292-329) en vez de
  convertirlos en `0`.

### 4.3 Cambios mínimos en el PRODUCTO (ZONA SENSIBLE)

Todos son **aditivos**: atributos nuevos en el objeto de respuesta que ningún código del producto lee.
No cambian `usage`, `choices`, `finish_reason`, el texto, los reintentos ni el registro en
`turn_usage`.

| Archivo:línea | Cambio | Qué NO se toca |
|---|---|---|
| `backend/mia/agent/subscription_llm.py:255-285` (`_to_openai_response`) | añade `response.mia_uso_crudo` = copia del dict `data["usage"]` si es dict, si no `None`; `response.mia_modelos_cli` = claves ordenadas de `data["modelUsage"]` si es dict (el juez ya las lee, J:1608); `response.mia_parada_cli` = `data.get("stop_reason")` si es str, si no `None`. Evidencia: las salidas guardadas del CLI en `output/validation/claude-opus55-*.json` traen `stop_reason` («end_turn»), `num_turns`, `modelUsage` y `usage` en el nivel superior; la versión del CLI que las produjo no consta (Q9) | los enteros de `usage` (258-271) siguen como están, porque los usan `_invoke_metered` (llm.py:1091-1101) y `record` (metrics/usage.py:211-220); `finish_reason="stop"` (273) |
| `backend/mia/agent/codex_subscription_llm.py:244-263` (`_usage`) y `:302-309` | `_usage` devuelve también la lista de dicts `usage` vistos, en orden; `call_cli` adjunta `response.mia_uso_crudo = {"eventos": [...]}` | los enteros de `SimpleNamespace` y `prompt_tokens_details` |
| `backend/mia/metrics/usage.py:71-80` | añade el lector público `current_node() -> str \| None` (devuelve `_node.get()`) | `record`, el búfer y el esquema de `turn_usage` |
| `backend/mia/agent/llm.py` | **ningún cambio**. Comprobado: `spend_guard` sustituye `agent.llm._invoke` (SG:1498) y `_invoke_metered` lo resuelve por el nombre del módulo (llm.py:1077, 1084), así que la captura ve la respuesta antes que `_record_usage` (llm.py:905-913) | — |
| `turn_usage` | **ningún cambio**. El banco deja de leerlo. El panel del abogado sigue mostrando 0 cuando falta la telemetría: es un defecto del producto que se declara y queda fuera del banco | — |

**Verificación obligatoria del cambio de producto:**

1. Antes y después del cambio, `call_llm` con dobles de `subprocess.run` devuelve objetos con
   `choices`, `usage` y `model` idénticos campo a campo.
2. `record` escribe la misma fila.
3. Siguen verdes `execution/test_rls.py`, `execution/test_gates_no_ciegos.py`,
   `test_eval_spend_guard` y las suites que importan `subscription_llm`, `codex_subscription_llm` o
   `metrics.usage`.

Lo revisa un segundo proveedor.

---

## 5 · Reanudación (decisión de Pipe, 2026-10-12: «que se reanude con mi autorización»)

### 5.1 Qué detiene

En cuanto exista en R4 una fila desconocida (§4.1) no cubierta, sea del bloque o de cualquier
versión de `versiones_contador`:

- **El juicio:** ninguna llamada de juez nueva (Opus ni Codex), tampoco de validación ni de
  estabilidad. El runner de juez lanza `CuotaAgotada` antes de invocar y escribe R6 `SUSPENDIDO.json`
  con `etapa` y `eventos`.
- **La producción Codex:** ninguna llamada `cli-codex*` de producción ni de aprobación.
  `GuardBanco.check_and_reserve` lanza `ParadaCodexProduccion` (R:1563-1568).
- **La producción Claude puede seguir** (C19). Sus métricas de calidad se calculan, pero el techo
  queda `no_certificable`.

### 5.2 Cómo se reanuda

- `banco04_juzgar juzgar --reanudar-aprobado-por-pipe <REF>` y `run_banco04 --reanudar-aprobado-por-pipe
  <REF>` (este ya existe, R:1979) escriben R6 `reanudaciones/<NNN>.json`.
- **Qué cubre:** exactamente las claves (ids R4) de los eventos desconocidos **ya registrados** en el
  momento de la reanudación, con su `eventos_sha256`, y el `suspension_sha256` del marcador activo.
- **Requisito:** `<REF>` es obligatorio y no vacío. Es la referencia de la aprobación de Pipe. El
  agente no la genera: la recibe del director, que la obtuvo de Pipe en el chat.
- **Una reanudación no cubre eventos futuros.**

### 5.3 Qué vuelve a detener

Cualquier fila desconocida nueva, cuyo id no esté en la unión de los `cubre.eventos_desconocidos` de
las reanudaciones existentes, vuelve a detener según §5.1.

### 5.4 Qué comprueba la puerta

**`t_inicio_utc` de una fila** es el instante en que su control previo leyó R4. Se toma antes de esa
lectura y se escribe en la fila `en_curso` antes de invocar. Si un evento desconocido se cierra entre
esa lectura y la invocación, la llamada cuenta como lanzada después de él. Es `no_certificable` a
propósito: falla cerrado, no es una ambigüedad.

Para cada fila C con `fase` de juicio o validación, o con `proveedor_cuota=codex` en producción o
aprobación:

- U(C) = filas desconocidas con `t_fin_utc` < `C.t_inicio_utc`, más las huérfanas con
  `t_inicio_utc` < `C.t_inicio_utc`.
- Se exige que U(C) ⊆ la unión de los `cubre.eventos_desconocidos` de las reanudaciones con
  `registrada_utc` < `C.t_inicio_utc`.
- Se exige que `C.eventos_desconocidos_vistos` ⊇ los elementos de U(C) que ya estaban escritos.
- Se exige que el `eventos_sha256` de cada reanudación coincida con las filas actuales: una fila
  editada después invalida la reanudación.

Si se viola, `no_certificable` con `llamada_tras_desconocido_sin_autorizacion`.

**Con cualquier evento desconocido, el techo queda `no_certificable` para siempre**, y por §6.4 el
veredicto global también. Reanudar permite terminar de medir y publicar; no certifica.

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
- **Base de datos:** el clúster aislado sintético (`MIA_TEST_ENV_FILE`, puerto ≠ 55432), porque
  `run_case` necesita las tablas y el checkpointer. Sin ese entorno, la prueba E2E-1 **termina en
  rojo con el código «no ejecutable»**. Nunca cuenta como verde ni como omitida (el criterio de
  `test_gates_no_ciegos`).
- **Custodia de prueba:** DPAPI de prueba, como en `test_banco04_produccion.py:891`. Contiene la
  clave del caso, la semilla y las jurisdicciones, y **4 ids custodiados de prueba**, que no se
  producen. Así `inventario_esperado` se construye y su ausencia sale como `muestra_incompleta`.

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
  - `corridas_con_dobles` (el esqueleto llama a la puerta pública, sin `_prueba`);
  - `arbol_sucio`, solo si el árbol lo está;
  - `validacion_reservada_ausente`;
  - los `sin_dato` o `par_faltante` que se deben **solo** a lo anterior.
- **F (motivos prohibidos):** cualquiera de identidad, ledger, juicio incompleto, telemetría, orden,
  extensión, R11 o R12.

**Cambios del runner que exige el esqueleto:**

- `--casos` (solo con `--permitir-parcial`) y `--solo-piloto`, ambos registrados en R1.
- El parámetro de Python `proveedores` de `main`, sin ningún flag de línea de comandos. Sustituye
  solo `subprocess.run` de los dos CLI y `embeddings.embed_texts`, y fuerza `dobles: true`.
- La variante sin base de datos `mundo=` sustituye **solo el mundo exterior**: lo que hoy hacen
  `producir`, `hash_soul` y `fijar_jurisdicciones` (R:1765-1787), las funciones de `DepsAprobacion`
  (R:1828-1896) y la base de datos.
  - Emite filas R4 a través de la API real de `telemetria`.
  - Siguen siendo código real, y no se pueden sustituir: `info_arbol_git`, `construir_manifiesto`,
    `asegurar_manifiesto`, el plan, el `Contexto`, la instalación de la telemetría, la escritura de
    R1, R2, R4, R6, R10, R11 y R12 y el cifrado de la custodia.
  - Se usa en el fixture completo de §6.3.

### 6.2 Pruebas de punta a punta sobre el esqueleto (`execution/test_banco04_cadena.py`, nuevo)

- **E2E-1 · Alcanzabilidad.** Los pasos 1 a 4 desde los `main`: archivos con su esquema, cero filas
  `en_curso` y el resultado de 6.1.
- **E2E-2 · La puerta solo lee crudos.**
  - `entradas_leidas` contiene solo R1, R2, R3, R4, R5, R6, R7, R8, R9, R10, R11 y R12.
  - Mutar `estado_banco.json`, `aprobaciones_estado.json`, `*.derivado.json`,
    `consumo_resumen`, `consumo_turno`, `consumo_aprobacion`, `usage_by_node.*.json` o un
    `VEREDICTO.json` previo deja la salida idéntica, salvo la marca de tiempo.
- **E2E-3 · Telemetría.**
  - El doble del CLI de Claude omite `output_tokens` en una llamada: la fila R4 queda
    `consumo_conocido=false`, `componentes_ausentes=["output_tokens"]` y `cota=null`.
  - `ContadorCuota.cota_calculable` es falso.
  - En el Bloque 7, con presupuesto Codex de producción mayor que 0 y por debajo de su tope:
    `GuardBanco.check_and_reserve(alias="cli-codex")` lanza `ParadaCodexProduccion` con el código
    `consumo_desconocido`, no con el de presupuesto agotado.
  - La siguiente llamada de juez lanza `CuotaAgotada` con el mismo código, se escribe R6
    `SUSPENDIDO` con `eventos` = [id de la fila] y el techo en la puerta es `no_certificable`.
  - Variantes con la misma exigencia: Codex sin evento `usage`; `cli-codex-eval` con `None`.
- **E2E-4 · Reanudación.**
  - Tras E2E-3, una reanudación que cubre el evento deja seguir al juez.
  - Un evento nuevo detiene otra vez.
  - Una fila de juez falsificada con `t_inicio` posterior a un evento no cubierto da
    `llamada_tras_desconocido_sin_autorizacion`.
  - Editar una fila cubierta invalida la reanudación.
- **E2E-5 · Ceguera y material.** El `prompt_sha256` reconstruido es igual al guardado. Alterar un
  byte del texto del R2 rompe `paquete_sha256` → `no_certificable`.
- **E2E-6 · Producto intacto.** Comparación campo a campo de §4.3.
- **E2E-7 · Sin puerta trasera.**
  - `banco04_decidir.py` no tiene ningún flag que active `_prueba` ni acepte `dobles` (búsqueda en
    el código y en `--help`).
  - Con `dobles: true` y sin `_prueba`, el resultado es `no_certificable`.
  - `resumen_publicable` rechaza `modo_prueba`.
- **Esqueleto, mutación de un crudo que cambia la condición** (el veredicto sigue siendo
  `no_certificable` por la muestra):
  - poner `sin_respaldo` en la salida cruda de Opus **y** de Codex sobre un átomo hace que
    `afirmaciones_sin_respaldo` del caso pase de 0 a 1;
  - poner `cubierto=false` en la pasada 2 de un decisivo hace bajar su cobertura;
  - quitar un fragmento de `entraron_tramos` hace bajar el alcance.

### 6.3 Familia «mutar el dato crudo conservando cualquier agregado ⇒ el veredicto cambia»

**Fixture F17.** Las dos versiones completas: 17 casos × R, aprobaciones y R9 reservado de prueba
(≥ 30 defectos, de ellos ≥ 10 cláusulas breves, y ≥ 30 controles, con acreditación v1.3 de prueba).

- Se produce con `montaje=` (sin base de datos), juzgar con runners dobles y VJ `main` con runners
  dobles.
- Con `_prueba`, la puerta da **`aprueba`**. Es requisito previo de la familia: si F17 no da
  `aprueba`, la familia no prueba nada.

Cada mutación edita **un solo crudo** y deja intactos todos los derivados y resúmenes:

| # | Mutación del crudo | Veredicto exigido |
|---|---|---|
| M01 | Opus y Codex marcan `sin_respaldo` el mismo átomo | reprueba (fila 1) |
| M02 | solo Codex marca defecto y el tercer voto crudo dice `sin_respaldo` | reprueba |
| M03 | solo Codex marca defecto y se borra el tercer voto crudo | no_certificable |
| M04 | la pasada 2 deja no cubiertos decisivos de un caso de lectura completa (caso < 0,80) | reprueba |
| M05 | la pasada 2 pone conducta `definitiva` en una corrida de alcance insuficiente | reprueba (DLI) |
| M06 | se quita de `entraron_tramos` lo justo para bajar de 0,95, con conducta `definitiva` | reprueba (C8 → DLI) |
| M07 | `fragmentos_en_prompt.completo=false`, con conducta `definitiva` | reprueba (alcance insuficiente) |
| M08 | `jurisdicciones_fijadas` de un custodiado difiere de la custodia | no_certificable |
| M09 | se suben los tokens de salida de filas R4 de producción de un caso (más de 1,25×) | reprueba (techo) |
| M10 | una fila R4 pasa a `consumo_conocido=false` y `cota=null` | no_certificable |
| M11 | se borra una fila R4 citada por un R2 | no_certificable |
| M12 | se añade una fila R4 `en_curso` huérfana | no_certificable |
| M13 | se cambia el `nodo` de filas R4 para que la subida de > 10 % de un caso recaiga en un nodo fuera de `atribucion_preregistrada` | reprueba (C25) |
| M14 | se borra el rep-05 de un caso de la base | no_certificable |
| M15 | se escribe un R7 que no corresponde a la previa recalculada (casos distintos) | no_certificable |
| M16 | con un R7 válido, se borra un rep de extensión de una versión | no_certificable |
| M17 | en R9 se cambia un tercer voto de un defecto, de modo que la sensibilidad baje de 0,95 | no_certificable (circuito) |
| M18 | en R9 se invierten los estados de Codex hasta que kappa < 0,6 | no_certificable |
| M19 | se borra la segunda pasada de estabilidad de un candidato elegido por la semilla | no_certificable |
| M20 | se borra la pasada 2 de Codex de un candidato del 15 % | no_certificable |
| M21 | cambia `soul_sha256` en R1 de la base | no_certificable |
| M22 | cambia `hash_evaluador` en un R5 | no_certificable |
| M23 | la pasada 2 hace caer un decisivo de 3/5 en la base a 1/5 en la nueva | reprueba (decisivos estables) |
| M24 | una fila de juez se lanza tras un evento desconocido no cubierto | no_certificable (orden) |
| M25 | una fila R4 mantiene `consumo_conocido=true` y su `uso_crudo` pierde `output_tokens` | no_certificable (la puerta vuelve a aplicar §4.1 y encuentra la contradicción) |
| M26 | la salida cruda de Opus queda estructuralmente inválida | no_certificable (no evaluada) |
| M27 | `no_aplica` sobre un átomo con cifra en la salida cruda de Opus | no_certificable (validador) |
| M28 | se reescribe R11 con `r_reducida` sin que el consumo lo justifique | no_certificable |
| M29 | se cambia `rep` dentro de un R2 (rep duplicado) | no_certificable |
| M30 | se añade al borrador de un caso sin ordenamiento «La Ley 100 de 1993 es aplicable» y se vuelven a escribir sus hashes de forma coherente en R2 | no_certificable (el R5 ya no corresponde) o reprueba si se vuelve a juzgar; en ningún caso `aprueba` |
| M31 | en la salida cruda de Opus y de Codex, un átomo pasa a `con_respaldo` con `uso_fuente=aplicable` y una fuente del corpus de un ordenamiento no configurado (C21, I7) | no_certificable (el validador lo rechaza, J:514) o reprueba si los dos lo marcan `sin_respaldo/fuga`; en ningún caso `aprueba` |
| M32 | los votos crudos confirman una negativa falsa (punto que consta en lo leído, declarado laguna) | reprueba (fila 1 por `confirmadas`) |
| M33 | se borra el R10 (`aprobacion.json` y sus intentos) de un caso | no_certificable (techo sin aprobación) |
| M34 | fuga que solo marca Codex (subtipo `fuga`), confirmada por el tercer voto crudo | reprueba (fila 2, regla de Q16) |

**Familia inversa.** Mutar solo derivados (E2E-2) no cambia el veredicto `aprueba`.

**Resultado.** El autor independiente escribe la familia en rojo antes de la implementación.
Después, un tercero muta la puerta y el resultado es el número de mutaciones que **sobreviven**
(DOC §10.2.13).

---

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
- **Runners (1537-1702):** se conservan, envueltos por `telemetria`.
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
    - `estimacion_piloto_codex` queda vacía (627, 1799): sigue abierta la estimación previa de
      Codex del área B, y en el Bloque 0 el presupuesto Codex de producción es 0 por R:445;
  - `main` (1962-2010) añade `--fase extension`, `--casos`, `--solo-piloto` y los parámetros de
    Python `proveedores` y `montaje`.
- **Se elimina:**
  - `consumo_desde_guardian` y `marca_guardian` (1537-1554) como fuente (quedan, como mucho, para
    el `consumo_resumen` derivado);
  - `registrar_consumo_externo` (1174-1196, sin llamadores);
  - `LedgerJuicio` (1228-1294, lo sustituye R4);
  - el volcado `usage_by_node` (1933-1941).

### 7.4 Otros

- **`execution/banco04_validar_jueces.py`:** R9 crudo (cambia 388-389 y 706); llave determinista
  (699); `control_de_cuota` (615-635) pasa a `telemetria`; `--versiones-contador` (625-629) se coteja
  con los R1 que existen en disco.
- **`backend/mia/eval/harness.py`:** `run_case` (502-905) se conserva. `usage_by_node` (909-936)
  queda para otros usos y el banco deja de llamarlo.
- **`backend/mia/eval/spend_guard.py`:** `_guarded_invoke` (1126-1275) gana la captura de §4.2. La
  aritmética en USD (`_alias_and_cost`, 940-971; `note_call`, 864-878) no cambia y no alimenta la
  cuota.
- **`execution/banco04_calibracion.py`:** su entrada `--corridas` (líneas 17-22) la produce
  `banco04_decidir` a partir de la reproducción, con los defectos confirmados y sus posiciones.

---

## 8 · Decisiones

### 8.1 Tomada por Pipe

- **2026-10-12, reanudación:** «que se reanude con mi autorización». Se implementa como §5. Cierra
  el pendiente de C19 (DOC §12.6).

### 8.2 Resueltas por este contrato (las revisa Astra; no son decisiones de Pipe)

- **R-1.** La puerta recibe cuatro rutas, y la cuarta es R8 (manifiesto de cadena). La alternativa
  está en Q5.
- **R-2.** Las salidas custodiadas viven bajo `<custodia>/salidas` (§2.3 del protocolo, literal).
- **R-3.** Una sola fuente de consumo: R4. `turn_usage` sale del banco.
- **R-4.** Reproducción en lugar de confianza: las decisiones guardadas son derivados.
- **R-5.** Semilla del juicio, del bootstrap y de las submuestras: `custodia.semilla_hmac()`. Semilla
  de las aprobaciones: `R1.semilla`.
- **R-6.** La incoherencia de la matriz da `no_certificable`.
- **R-7.** Casos de la extensión: unión de los casos de cada métrica no concluyente, con un tope de
  5 elegidos por la mayor contribución negativa.
- **R-8.** El alcance solo cuenta como medido con `fragmentos_en_prompt.completo`.
- **R-9.** Familias de telemetría y fórmula del total (§4.1).
- **R-10.** Cuota Claude = todo alias que no es Codex ni embeddings, como `GuardBanco`.

### 8.3 Preguntas abiertas para el director

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

- **Q1.** Una repetición con `fallo_producto` cuenta como turno no completado (§9.5) y entra en
  `turnos_completados`, con lo que puede llevar a `reprueba`. No es `no_certificable`, porque un
  producto que falla no puede eludir el veredicto por fallar. Las métricas por afirmación se calculan
  sobre los turnos completados y declaran el denominador.
- **Q2.** Se acepta el valor por defecto: una inferencia es una fila R4 de Claude en producción,
  incluidos los intentos fallidos.
- **Q3.** El turno reproducido de la aprobación entra en `consumo_agregado_caso`, porque es consumo
  real del flujo del abogado. Se corrige R:1435-1436.
- **Q4.** La señal determinista de fuga es auxiliar (§5.2, P2). La fuga decisiva la dan los jueces
  con `uso_fuente` (C21). La señal falla cerrada: una negación nunca le resta una cita. Cada positivo
  de la señal que los jueces no confirman se publica como discrepancia señal↔juez y se adjudica; no se
  cuenta como fuga ni se descarta en silencio. Con esto se cierra la carrera de patrones de R3-N2. El
  defecto del producto (`scoring.py`) sigue fuera del banco.
- **Q5.** Se acepta el valor por defecto: la cuarta ruta es R8.
- **Q6.** El kappa de las salidas reales se calcula sobre las salidas juzgadas de **ambas** versiones.
  La comparación exige jueces fiables también sobre la base.
- **Q7.** Se acepta el valor por defecto: los decisivos estables usan solo las repeticiones 1..R
  pre-registradas.
- **Q8.** `negativa_correcta` se deriva de la pasada 2 con un campo nuevo de su esquema. Los esquemas
  los fija el código (C14), así que es una aclaración de v1.3 y no exige v1.4.
- **Q9.** Es precondición de la piloto. Antes de la primera llamada de juez real hay que acreditar la
  forma de la telemetría del CLI instalado, con su versión registrada: la presencia de los campos de
  caché cuando valen 0, si los eventos `usage` de Codex son acumulados y el `stop_reason`. Para eso se
  hace UNA llamada mínima real por proveedor, o se usa una salida guardada de la misma versión. Si un
  campo puede faltar con valor 0, la regla de §4.1 lo trata como cero **solo** con la evidencia
  versionada de esa conducta.
- **Q10.** Se acepta el valor por defecto: la atribución pre-registrada se ancla en R1 de la versión
  nueva, antes de producirla, y la escribe el director a partir del plan del Bloque 4.
- **Q11.** El Bloque 0 mide y publica la línea base de 0.3.3 con un solo directorio, sin veredicto
  global. Su salida son las métricas absolutas, el techo y la matriz de §7.2, sin comparativas.
- **Q12.** El registro de uso no existe (verificado el 2026-10-12), así que el reservado no se ha
  usado. La validación reservada corre **después** de implementar este contrato, con el hash nuevo
  del evaluador.
- **Q13.** La decisión de Pipe sobre C19 entra como aclaración C27 de v1.3.
- **Q14.** Se intenta acreditar la cota según C18, sin cambiar la conducta del producto. Para eso se
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
