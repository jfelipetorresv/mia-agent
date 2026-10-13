# Banco 0.4 · Ronda 2 de Astra · frente de JUICIO — informe

Fecha: 2026-10-12 · Rama `feat/mia-04-hermes-legal`, partida de HEAD 3611b75 · Sin commits (el director hace git).

## 0. Resultado

| Suite | Antes | Después |
|---|---|---|
| `execution/test_banco04_juicio.py` | 286/286 | **387/387 PASS** (exit 0) |
| `execution/test_banco04_produccion.py` (frente ajeno) | 220/220 | **238/238 OK** (exit 0, corrida final). En una corrida intermedia dio 233/236: los 3 rojos eran de `spend_guard` y sus checks i-1b, i-3 y «ningún alias CLI…», que el otro agente estaba cambiando. En la corrida final ya estaban en verde. Ninguno dependía de mi frente. |
| `execution/test_gates_no_ciegos.py` (meta-gate de CLAUDE.md) | — | 9/9 PASS |

**Mutaciones: 49 de 49 en rojo** sobre el check con nombre que protegen (ver §4). Resumen de los ítems:

- **Área A:** I1, I2, N1, N2 y N3, resueltas.
- **Área B (mi parte):** I4, N1 e I5, resueltas.
- **Área C:** N1 (antes I7), N2, I9, N3 y N4, resueltas. N4 queda vendorizada en el banco: **el defecto sigue en el producto**.

Hay 7 aclaraciones de protocolo propuestas (C18–C24, §5) que el director tiene que decidir. Dos de ellas cambian textos que no son de mi frente: el esquema de §8.4 y la invariante C08 del manifiesto de custodia.

---

## 1. Área A (veredicto_A.md)

### R2-A-I1 · RESUELTA

**Inventario.** El manifiesto lleva ahora sus parámetros. `veredicto_global` lo reconstruye desde el protocolo con esos parámetros y exige que coincida en todo. Un manifiesto hecho a mano, por ejemplo con colecciones vacías o con las R rebajadas, sale `no_certificable`.
- `metricas.py:918` `inventario_esperado`: valida los ids, la contingencia y que la extensión no pase de 5 casos con 5 corridas cada uno.
- `metricas.py:957` `validar_inventario`.

**Consumo ausente.** Un consumo que no consta ya no se cuenta como 0.
- `metricas.py:738` `consumo`: sin `tokens` entero ≥ 0 devuelve None.
- `metricas.py:778` `techo_cuota({}, {})` da `no_certificable`, con motivo `sin_consumo`.
- `:796`: un caso sin aprobación queda sin dato.
- El techo publica ahora `R_por_caso` y `consumo_por_ambito`.
- `veredicto_global` exige que el techo cubra los 17 casos con las R del inventario en las dos versiones (`metricas.py:1247`).

**Pares faltantes.**
- `metricas.py:601` `pares_comparativos` y `:649`: un caso ausente en una versión, o con la métrica en None donde aplica, es un par faltante, `sin_dato` ⇒ `no_certificable`.
- `veredicto_global` **recalcula cada comparativa** desde las dos versiones (parámetros nuevos `casos_base` y `semilla`). La comparativa suministrada tiene que coincidir con el recálculo (`:1197`).

**Recibo de extensión** (`metricas.py:1086` `_motivos_recibo`). Exige:
- la comparativa previa `no_concluyente`;
- casos iguales a los que da `casos_para_extension(previa)`;
- 5 corridas por caso;
- la extensión registrada en el inventario. Así existen R+5 repeticiones únicas, juzgadas por los dos jueces, y el techo las cuenta;
- un `veredicto_final` igual al del recálculo.

Además, una extensión registrada en el inventario sin recibo válido da `no_certificable` (`:1217`).

**Checks** (en `gate_r2_a`, `test_banco04_juicio.py:1441`, y en `gate_i1_i2`, `:1321`). Todos llevan el prefijo «R2-A-I1 ·»:
- manifiesto con TODAS sus colecciones vacías (el escenario de Astra);
- sin parámetros;
- R rebajadas con un banco coherente;
- extensión fuera del pre-registro;
- `techo_cuota({}, {})`;
- corrida sin `tokens`;
- aprobación sin `tokens`;
- caso sin aprobación;
- techo que no cubre los 17;
- 1 de 9 pares;
- veredicto con pares faltantes;
- recibo con R sin extender (Astra);
- recibo que no coincide con el recálculo;
- casos fuera de la regla;
- extensión no juzgada;
- extensión sin recibo;
- comparativa que no coincide con el recálculo.

Controles: «el mismo recibo vinculado y juzgado aprueba» y «el banco completo aprueba».

**Mutaciones:** A-I1a, A-I1b, A-I1c, A-I1c-bis, A-I1d, A-I1e1, A-I1e2, A-I1f, A-I1g, A-I1h, A-I1i y A-I1j, **todas en ROJO**.

### R2-A-I2 · RESUELTA

**Completitud.**
- `metricas.py:693` `perdidas_por_caso(…, casos_esperados)` y `:708` `decisivos_estables_perdidos(…, casos_esperados)` devuelven `(resultado, faltantes)`.
- Diccionarios vacíos ⇒ `cumple=None`.
- Un decisivo presente en la base y ausente en la nueva queda como faltante: no desaparece del control.
- `veredicto_global` recalcula las filas de pérdida y exige `casos_cubiertos` completos en la fila de decisivos.

**Atribución** (`metricas.py:990` `atribucion_valida`). Exige:
- una comparativa con `mejora`;
- el ÁMBITO: la mejora tiene que estar en una unidad del mismo grupo (a o c) que el caso de la subida (`:1019`; ver C22);
- `usage_by_node` de las dos versiones que sume exactamente lo que el techo midió en ese ámbito;
- un nodo con tokens > 0 en 0.4, cuyo consumo subió y que es el que más subió.

Un nodo inexistente o la ausencia de `usage_by_node` reprueban.

**Checks** (prefijo «R2-A-I2 ·»):
- cuatro diccionarios vacíos;
- decisivo ausente en la nueva (y su control);
- banco con un decisivo ausente en 0.4;
- 36 subidas atribuidas a NODO_INEXISTENTE sin `usage_by_node` (Astra);
- `usage_by_node` que no suma;
- mejora fuera del grupo;
- nodo que no está en el consumo de 0.4;
- control que aprueba.

`gate_i1_i2` se reescribió con mejora y `no_concluyente` producidos desde datos reales: ya no se fabrica el veredicto a mano.

**Mutaciones:** A-I2a, A-I2b, A-I2c, A-I2d y A-I2e, **todas en ROJO**.

### R2-A-N1 · RESUELTA (bloqueante)

- `metricas.py:407` `agregar_casos` registra `repeticiones`, `repeticiones_invalidas` y `repeticiones_evaluadas`.
- `metricas.py:1119` `_completitud_version` exige el conjunto exacto {1..R} de repeticiones únicas, todas evaluadas, en las DOS versiones.

**Checks:**
- «R2-A-N1 · repetir SOLO `repeticion=1`…»
- «… una sola repetición duplicada…»
- «… el conjunto exacto se exige también en la versión BASE»
- control.

**Mutación:** A-N1, en ROJO.

### R2-A-N2 · RESUELTA

- `metricas.py:112` `rango_valido` exige 0 ≤ inicio < fin ≤ longitud.
- `:131` `ref_disponible` lo aplica.
- `:89` los tramos enviados inválidos se descartan.
- `:1331` `_refs_hecho`: la clave con un rango invertido, vacío o de un fragmento que el hecho no declara falla cerrado.
- `custodia.py:373` `invariantes_rangos_hecho`, llamada desde `_inv_clave` (`:370`), exige que el rango sea válido contra la longitud real del fragmento.

**Checks:**
- «R2-A-N2 · rango invertido [90,30)…»
- «… vacío [30,30)…»
- «… negativo o más allá…»
- «… tramos ENVIADOS invertidos…»
- «… la clave con un rango invertido…»
- «… custodia: …»
- controles en los dos sentidos.

**Mutaciones:** A-N2a, A-N2b, A-N2c y A-N2d, todas en ROJO.

### R2-A-N3 · RESUELTA

- `harness.py:471` `fragmentos_de_bloques_enviados` es una función pura. Elige primero las apariciones más largas, descarta las que se solapan con una ya elegida, numera por posición y cuenta una sola vez el mismo render repetido.
- La usa la captura en `harness.py:648`.
- El wrapper sigue siendo transparente y se restaura (`:685`).

**Checks:**
- «R2-A-N3 · renders [A] y [A,B]: … [A,B] (no [A,A,B]) y n = 1,2»
- control con [A];
- control con dos bloques distintos;
- la captura usa la función y restaura los originales.

**Mutación:** A-N3, en ROJO.

**Límite:** no corrí `run_case` contra el grafo real, que exige base de datos (prohibida). La conducta de extremo a extremo está cubierta solo por los g-* del frente ajeno, con dobles, y siguen en verde.

---

## 2. Área B, la parte de mi frente (veredicto_B.md)

### R2-B-I4 · RESUELTA

- `jueces.py:1340` `cota_salida_juez`:
  - Claude toma la cota de `spend_guard.cota_salida_cli("cli-claude-opus")`, que decide el otro agente. Hoy devuelve None, así que la cota es desconocida.
  - Codex queda siempre en None.
- `:1356` `cota_intento` devuelve None cuando no hay cota.
- `:1364` `estimacion_reserva` (entrada + `COTA_SALIDA_JUEZ_TOKENS`) solo sirve para el control previo. **Nunca es una cota.**
- `ControlCuotaJueces.despues` (`:1407` y siguientes):
  - con cota documentada, el fallo se cierra como `fallido_acotado` y el techo sigue certificable;
  - sin cota, se cierra con `timeout=True` y el techo deja de ser certificable.

**Checks:**
- «R2-B-I4 · Codex sin cota documentada ⇒ … None»
- «… Claude: la cota es la de spend_guard…»
- «… no usa ninguna cota propia»
- «… con cota DOCUMENTADA … sigue certificable»
- «… SIN cota … NO certificable»

Los checks de I5 se actualizaron con cota inyectable.

**Mutaciones:** B-I4a, B-I4b y B-I4c, todas en ROJO.

### R2-B-N1 · RESUELTA (bloqueante)

`jueces.py:1375` `tokens_conocidos` exige:
- Claude: `input_tokens` y `output_tokens` enteros ≥ 0. La caché, si viene, tiene que ser válida.
- Codex: `prompt_tokens` y `completion_tokens`. Con `total_tokens` válido se toma el mayor.

Si falta algo, el consumo es DESCONOCIDO.

**Checks:**
- «R2-B-N1 · `{cache_read_input_tokens: 0}` NO es consumo conocido»
- faltantes o valores inválidos;
- controles;
- Codex;
- «… extremo a extremo: … DESCONOCIDO … no certificable»

**Mutación:** B-N1, en ROJO.

### R2-B-I5 · RESUELTA en mi frente

- `jueces.py:1438`: defensa propia. Con el contador no calculable no se reserva ni se lanza nada, haga lo que haga `motivo_juicio`, que el otro agente ya cambió.
- `banco04_validar_jueces.py:615` `control_de_cuota`:
  - `salida_custodia` y `versiones` obligatorias, con la versión propia incluida;
  - en el Bloque 7, dos versiones o más;
  - la línea de órdenes exige `--salida-custodia` y `--versiones-contador`.
- `:350` `consumo_del_circuito` lee el contador compartido desde el disco.
- La exigencia `consumo_certificable` (`:330`) condiciona `circuito_utilizable`.
- `:361` `validar_circuito`: el reservado exige Opus y Codex atados al MISMO control.

**Checks** (`gate_r2_b`, `test:1972`):
- defensa propia con un ledger falso (aísla mi guarda de la del otro frente);
- tras un consumo sin cota no se lanza nada;
- EXIGE la salida custodiada;
- EXIGE las versiones;
- Bloque 7 con dos versiones;
- se suma el consumo de la versión hermana;
- `circuito_utilizable` exige consumo certificable;
- reservado sin contador compartido;
- extremo a extremo con un intento desconocido.

**Mutaciones:** B-I5a, B-I5b, B-I5c, B-I5d, B-I5e y B-I5f, todas en ROJO.

**No es mío:** la proyección y la reserva de Codex en la piloto, en la decisión de R y en las aprobaciones (`run_banco04.py`), y las I8, I10 y N2 de B.

---

## 3. Área C (veredicto_C.md)

### R2-C-N1 / I7 · RESUELTA (bloqueante) en lo que toca al código

**C08 en un despacho configurado para OTRO ordenamiento.**
- `custodia.py:397` `c08_admisible` y `:389` `fuentes_de_otro_ordenamiento`. La C08 vale con `jurisdicciones == []` o con una fuente del material de ordenamiento declarado no configurado.
- Lo usan `custodia.py:414` y `banco04_validar_jueces.py:121`.
- e-26, del frente ajeno, sigue en verde.

**Acreditación v1.3.** `banco04_validar_jueces.py:550` `verificar_acreditacion` exige:
- formato `banco04-acreditacion-compatibilidad/v1`;
- protocolo v1.3;
- autor independiente declarado;
- veredicto `compatible`;
- `hash_evaluador` igual al combinado v1.3 en ejecución;
- identidad del reservado;
- `{id: sha256_claro}` de TODOS los casos, claves y mutaciones del manifiesto;
- cobertura comprobable por clase (`:531` `_cumple_clase`):
  - fuga sin ordenamiento;
  - fuga de OTRO ordenamiento;
  - negación ajena (`:518`);
  - control descriptivo;
- los mínimos de `protocolo.ACREDITACION_V13_MINIMOS` (`protocolo.py:324`; ver C19).

Cómo se exige:
- La exigencia `acreditacion_compatibilidad_v13` (`:326`) condiciona `circuito_utilizable`.
- `main` rechaza el reservado sin `--acreditacion-v13` (`:687`) y lo verifica ANTES de marcar el uso (`:695`).

**No escribí** casos, claves ni mutaciones reservadas, ni la acreditación real: lo hará el autor independiente. En los tests solo hay dobles sintéticos.

**Checks** (`gate_r2_c`, `test:2197`):
- C08 de otro ordenamiento válida, y rechazada si no trae la fuente;
- custodia, con el mismo criterio;
- control de acreditación válida;
- acreditación inválida en cada vínculo (11 casos);
- sin acreditación no se habilita (el escenario de Astra);
- control habilitado;
- orden en `main`.

**Mutaciones:** C-N1a, C-N1b, C-N1c, C-N1d, C-N1e, C-N1f y C-N1g, todas en ROJO.

### R2-C-N2 · RESUELTA

- Nuevo campo `evidencia.uso_fuente` con los valores `aplicable`, `descriptivo` y `rechazo_aplicabilidad`.
- Esquema `banco04-juez-respaldo/v1.3` y `banco04-tercer-voto/v1.3`:
  - `jueces.py:48`, `:135` y `:478`;
  - `protocolo.py:299–303`.
- `jueces.py:515`: una fuente de ordenamiento no configurado solo respalda si el uso declarado es `descriptivo` o `rechazo_aplicabilidad`. Con `aplicable` o null, error.
- Prompts:
  - `pasada1_opus.md:59`, `pasada1_codex.md:52` y `tercer_voto.md:26` explican el uso;
  - se retiró «no puede respaldar nada».

**Checks:**
- «R2-C-N2 · una transcripción DESCRIPTIVA fiel … queda respaldada»
- «… la MISMA fuente usada como derecho aplicable (o sin declarar) se rechaza»
- control `sin_respaldo/fuga`;
- control con ordenamiento configurado;
- valor fuera del enum;
- esquema y prompts.

**Mutaciones:** C-N2a y C-N2b, en ROJO.

### R2-C-I9 · RESUELTA

- `banco04_validar_jueces.py:406–510`:
  - **Raíz permanente** `%LOCALAPPDATA%\MIA-banco04-registro-uso`. No depende de `MIA_BANCO04_CUSTODIA` y no se acepta dentro de la custodia ni bajo el repo.
  - **Identidad** = sha256 en claro del reservado: re-cifrar o renombrar no fabrica otro.
  - **Huellas de material** por ítem: rechazan un reservado «nuevo» que reutilice material ya usado.
  - **Marca secundaria** en la custodia: cambiar solo una de las dos raíces no basta.

**Checks** (`gate_i9`, `test:1909`):
- «R2-C-I9 · REUBICACIÓN: la misma identidad con OTRA MIA_BANCO04_CUSTODIA se rechaza»
- ruta independiente de la custodia;
- cambiar solo la raíz;
- material reutilizado;
- control;
- raíz dentro de la custodia;
- identidad por contenido.

**Mutaciones:** C-I9a, C-I9b, C-I9c y C-I9d, todas en ROJO.

**Límite declarado:** si un operador cambia a la vez `LOCALAPPDATA` y la carpeta de custodia, el registro se elude. Es una barrera de intención, no criptográfica.

### R2-C-N3 · RESUELTA

- `jueces.py:1945` `ARCHIVOS_EVALUADOR_REPO = ("execution/banco04_validar_jueces.py",)`, que entra en el hash (`:1952`).
- **Checks:** «R2-C-N3 · … está en el hash» y «… relajar una exigencia del validador invalida la congelación (EvaluadorAlterado)». Este último usa una copia en un directorio temporal, no el repo. Hay además un control con la copia intacta.
- **Mutación:** C-N3, en ROJO.

### R2-C-N4 · RESUELTA en el banco; **el defecto PERSISTE en el producto**

- `evaluador_congelado.py:402–490` vendoriza `jurisdiction_leak_signal` desde `scoring.py` en HEAD 3611b75 (`ORIGEN_FUGA`, con su sha256).
- La negación ahora se asocia a la cláusula de la cita (`_clausula_de`, `:447`; `_mencion_negada`, `:467`).
- `metricas.py:248` `senal_fuga` calcula la señal con la copia a partir de `texto_salida` y `jurisdicciones`, y rechaza una `fuga_senal` precalculada (`:363`).

**`scoring.py:188` NO se tocó.** El producto, y el panel y el harness que lo usan, siguen tratando «… es aplicable al caso, aunque no consta la fecha…» como no fuga. El check «DECLARADO: el defecto PERSISTE en el producto» lo documenta.

**Checks:**
- «R2-C-N4 · «… aunque no consta…» ⇒ FUGA»
- «… «No consta que la Ley 100 de 1993 sea aplicable» ⇒ sin fuga»
- control N-1;
- `metricas` usa la copia;
- con ordenamiento configurado no aplica;
- no acepta señal precalculada.

**Mutaciones:** C-N4a y C-N4b, en ROJO.

---

## 4. Pruebas de mutación

- **Herramienta:** el arnés `r2/mutar.py`. Revierte UNA corrección, corre la suite completa, comprueba que los checks esperados quedan en `[FAIL]` con su nombre y restaura el archivo byte a byte, con aserción de igualdad.
- **Resultados:** `r2/mutaciones_resultado_completo.json`, con 49 entradas. A-I1e1 se volvió a correr tras endurecer su check, en `mutar_log5.txt`.
- **Integridad:** sha256 del frente verificado antes y después de cada tanda.

| Mutación | Archivo | Suite con la mutación | Check(s) en rojo |
|---|---|---|---|
| A-I1a se confía en el manifiesto del llamador | metricas | 385/387 | manifiesto vacío; R rebajadas |
| A-I1b `techo({},{})` cumple | metricas | 386/387 | `techo_cuota({}, {})` NO cumple |
| A-I1c consumo ausente = 0 | metricas | 385/387 | corrida sin tokens; aprobación sin tokens |
| A-I1c-bis consumo = 0 y sin guarda de aprobación (dos sitios) | metricas | 384/387 | caso sin aprobación |
| A-I1d techo sin cobertura del inventario | metricas | 386/387 | techo que no cubre los 17 |
| A-I1e1 caso ausente omitido | metricas | 385/387 | 1 de 9 pares |
| A-I1e2 métrica None omitida | metricas | 386/387 | veredicto con pares faltantes |
| A-I1f recibo sin vínculo al inventario | metricas | 386/387 | recibo con R sin extender |
| A-I1g recibo sin recálculo | metricas | 386/387 | recibo ≠ recálculo |
| A-I1h comparativa suministrada creída | metricas | 386/387 | comparativa ≠ recálculo |
| A-I1i extensión sin recibo | metricas | 386/387 | extensión sin recibo |
| A-I1j casos fuera de la regla | metricas | 386/387 | casos fuera de la regla |
| A-I2a pérdidas sin completitud | metricas | 386/387 | cuatro diccionarios vacíos |
| A-I2b el decisivo ausente desaparece | metricas | 385/387 | decisivo ausente (2 checks) |
| A-I2c atribución sin evidencia | metricas | 384/387 | NODO_INEXISTENTE; no suma |
| A-I2d atribución sin ámbito | metricas | 386/387 | mejora fuera del grupo |
| A-I2e nodo fantasma | metricas | 386/387 | nodo fuera del consumo |
| A-N1 repeticiones duplicadas | metricas | 385/387 | rep=1; versión base |
| A-N2a rango invertido | metricas | 385/387 | [90,30); [30,30) |
| A-N2b tramos enviados sin validar | metricas | 386/387 | tramos enviados |
| A-N2c clave con rango inválido | metricas | 386/387 | clave falla cerrado |
| A-N2d custodia sin rangos | custodia | 386/387 | custodia |
| A-N3 la captura concatena | harness | 386/387 | [A] y [A,B] |
| B-I4a Codex con cota genérica | jueces | 383/387 | Codex sin cota |
| B-I4b Claude con cota propia | jueces | 385/387 | cota de spend_guard |
| B-I4c sin cota = acotado | jueces | 380/387 | SIN cota ⇒ NO certificable |
| B-N1 telemetría parcial | jueces | 382/387 | `{cache_read: 0}`; extremo a extremo |
| B-I5a sin defensa propia | jueces | 386/387 | defensa PROPIA |
| B-I5b sin salida custodiada | validar | 386/387 | EXIGE salida custodiada |
| B-I5c versiones no exigidas | validar | 386/387 | EXIGE versiones |
| B-I5d consumo certificable no exigido | validar | 385/387 | 2 checks |
| B-I5e reservado sin contador compartido | validar | 386/387 | runners sin contador |
| B-I5f Bloque 7 con una versión | validar | 386/387 | dos versiones |
| C-N1a C08 solo con `[]` (validador) | validar | 386/387 | C08 de otro ordenamiento |
| C-N1b C08 solo con `[]` (custodia) | custodia | 385/387 | 2 checks |
| C-N1c sin hash del evaluador | validar | 386/387 | cada vínculo |
| C-N1d sin hashes de artefactos | validar | 386/387 | cada vínculo |
| C-N1e cobertura no comprobada | validar | 386/387 | cada vínculo |
| C-N1f acreditación no exigida | validar | 386/387 | sin acreditación no se habilita |
| C-N1g `main` sin `--acreditacion-v13` | validar | 386/387 | línea de órdenes |
| C-N2a describir = aplicar | jueces | 386/387 | descriptiva respaldada |
| C-N2b aplicar aceptado | jueces | 385/387 | aplicable rechazada |
| C-N3 validador fuera del hash | jueces | 385/387 | 2 checks |
| C-N4a negación de la oración | evaluador | 383/387 | «aunque…»; métricas |
| C-N4b señal precalculada aceptada | metricas | 386/387 | no acepta señal |
| C-I9a raíz desde la custodia | validar | 381/387 | REUBICACIÓN |
| C-I9b identidad con el cifrado | validar | 386/387 | identidad por contenido |
| C-I9c material reutilizado | validar | 385/387 | reutiliza material |
| C-I9d sin marca secundaria | validar | 386/387 | solo raíz permanente |

**Incidencias del proceso** (corregidas antes del resultado final):

1. **CRLF.** El repo usa `core.autocrlf=true` y las copias de trabajo están en CRLF. Mis primeras tandas buscaban patrones con `\n` y 32 mutaciones «no se aplicaron». Corregí el arnés para que respete el fin de línea y las volví a correr.
2. **Rojos sin nombre.** Ocho mutaciones ponían roja la suite solo porque el gate lanzaba una excepción, o seguían verdes porque había una segunda guarda independiente. Endurecí esos checks con el ayudante `lanza()`, que exige la excepción de dominio exacta, y con bancos coherentes, y añadí la mutación de dos sitios A-I1c-bis. Las 49 quedaron en rojo por su check con nombre.
3. **Mutaciones mientras trabajaba el otro agente.** Durante las tandas, mis archivos estuvieron mutados unos segundos a la vez, mientras el otro agente trabajaba. Si corrió mi suite en esos momentos, pudo ver rojos transitorios.

---

## 5. Aclaraciones de protocolo propuestas (el director decide; NO edité el protocolo, docs ni el manifiesto)

**C18 (esquema v1.3 de la pasada 1 y del tercer voto).**
> «La `evidencia` de la pasada 1 y del tercer voto incluye `uso_fuente`: `aplicable` | `descriptivo` | `rechazo_aplicabilidad` | null. Es obligatorio, y distinto de `aplicable`, para respaldar (`con_respaldo` o `con_respaldo_sin_localizador`) con una fuente del corpus de un ordenamiento no configurado. Describir fielmente esa fuente, o rechazar su aplicabilidad, puede quedar respaldado. Usarla como derecho aplicable es `sin_respaldo`/`fuga`. Esquemas `banco04-juez-respaldo/v1.3` y `banco04-tercer-voto/v1.3`.»

Esto cambia el esquema de §8.4 y la frase de §12.5 «La norma respaldada pero no habilitada cuenta como fuga», que pasa a ser «… usada como aplicable …».

**C19 (acreditación de compatibilidad v1.3 del reservado y C08).**
> «El reservado solo habilita el circuito con una acreditación (`banco04-acreditacion-compatibilidad/v1`) de un autor independiente. La acreditación queda ligada al hash combinado del evaluador v1.3, a la identidad del reservado y al sha256 en claro de todos los casos, claves y mutaciones del manifiesto. Debe cubrir de forma comprobable, al menos `ACREDITACION_V13_MINIMOS` por clase (propuesta: 1), cuatro clases: fuga sin ordenamiento, fuga en un despacho configurado para OTRO ordenamiento con la fuente no habilitada en el material, negación ajena y control descriptivo. La invariante C08 pasa a ser: C08 solo en ítems sin ordenamiento configurado o con una fuente del corpus de un ordenamiento no configurado.»

Hay que actualizar también `custodia_manifest.json` (`invariantes_semanticas`) y `docs/banco04-custodia-formato.md`, que no son de mi frente. **El mínimo de 1 por clase es arbitrario.**

**C20 (registro de uso único).**
> «El registro vive en `%LOCALAPPDATA%\MIA-banco04-registro-uso` (con marca secundaria en la custodia). La identidad es el sha256 en claro del reservado y se registran las huellas del material de cada ítem: reutilizar material ya usado también se rechaza.»

**C21 (veredicto global recalculado y recibo de extensión).**
> «El veredicto global recalcula las comparativas desde las dos versiones (casos agregados de 0.3.3 y de 0.4, más la semilla). El `veredicto` de una comparativa es el de los datos finales, ya extendidos si los hubo. El recibo `extension = {casos, corridas_por_caso: 5, veredicto_final, comparativa_previa}` exige que la previa sea `no_concluyente`, que los casos sean los de la regla y que la extensión esté en el inventario.»

**C22 (atribución de subidas de cuota).**
> «Una subida de un caso solo se atribuye a una `mejora` de una unidad de su mismo grupo, (a) o (c), porque A-voluminoso y C-pequeños nunca dan `mejora`. Exige `usage_by_node` de las dos versiones que sume el consumo medido de su ámbito, y que el nodo atribuido sea el que más subió.»

Límite: la causalidad nodo → métrica no se puede acreditar mecánicamente.

**C23 (señal determinista de fuga).**
> «§5.7 usa la copia vendorizada de `jurisdiction_leak_signal` con la negación por cláusula. La de `scoring.py` del producto conserva el defecto (N4).»

Desviación literal: §5.7 nombra `scoring.jurisdiction_leak_signal`.

**C24 (cota de los intentos de juez).**
> «Claude toma la cota de `spend_guard.cota_salida_cli`; Codex, ninguna. Un intento sin telemetría completa y sin cota documentada deja el techo no certificable y detiene el circuito.»

**Riesgo operativo:** hoy las dos cotas son desconocidas, así que un solo timeout de juez en el Bloque 0 o en el 7 deja la corrida no certificable.

---

## 6. Lo que NO hice (dicho con todas sus letras)

**Material reservado y documentos.**
- No escribí la acreditación real, ni casos, ni claves, ni mutaciones reservadas. No leí la custodia, `mia-data` ni `.env`.
- No edité el protocolo, `docs/`, `custodia_manifest.json`, HANDOFF, APRENDIZAJES ni `memory/`.
- `scoring.py` no se tocó: **el defecto N4 sigue en el producto.**

**Lo que el veredicto global todavía no recalcula.**
- Las filas absolutas de §6.1, la fila de decisivos estables y la de atribución: las consume tal como las producen sus funciones.
- De la fila de decisivos solo comprueba que esté presente y cubra el inventario. De la de atribución, solo que esté presente.
- Un llamador que fabrique a mano el `cumple` de esas filas no queda detectado.

**Otros límites.**
- `metricas_corrida` exige ahora `texto_salida` y `jurisdicciones`. Nadie en el runner la llama todavía. Cuando la medición se cablee, debe pasar el diagnóstico más el borrador completos.
- La estimación de entrada (caracteres / 3) es una estimación, no una cota estricta.
- No corrí `run_case` con el grafo real (exige base de datos) ni proveedores reales. No ejecuté `claude --version`.
- Para medir tiempos memoricé el bootstrap (`metricas.py:571`), que es puro y con semilla. El resultado es idéntico.

**Otros efectos.**
- Cambió el hash del evaluador y el de `hash_protocolo`, por el esquema v1.3 y las constantes nuevas. Nada estaba congelado todavía.
- `custodia.py` y `evaluador_congelado.py` quedaron con fin de línea LF, y los demás en CRLF. Con autocrlf eso no genera diferencias en git.

**Git.** Ejecuté solo lecturas: `git status` y `git log` al empezar, y una vez `git config --get core.autocrlf` para diagnosticar el problema de CRLF. Ningún commit, stash, checkout ni reset.

**Para el otro frente** (no lo toqué):
- En una corrida intermedia, 3 checks de producción sobre `spend_guard` estaban rojos mientras el otro agente trabajaba. La corrida final da 238/238.
- Siguen siendo suyos de B: I8 (excepciones reservadas en claro), I10 (reanudación de intentos y aprobaciones), N2 (árbol sucio) y la proyección y reserva de Codex en la piloto, en la decisión de R y en las aprobaciones.
- Mi código depende de estas APIs suyas, que se conservan:
  - `LedgerJuicio(versiones=…, salida_custodia=…)`;
  - `cerrar(…_fallidos=[{tokens_cota_superior}])`;
  - `registrar_consumo_externo`;
  - `motivo_juicio`.
