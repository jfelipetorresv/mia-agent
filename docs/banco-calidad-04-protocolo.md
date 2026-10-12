# Banco de calidad 0.4 — Protocolo (fijado antes de correr)

Versión del protocolo: **banco04-v1.3** · Fecha: 2026-10-11 · Plan: `como-vamos-con-la-robust-llama.md`
(Bloque 0, contrato 11, respuestas a Astra rondas 1-2, objeciones N1 y O17). La v1.1 incorporó la
primera revisión de Codex Astra (NO APTO, 12 objeciones). La v1.2 incorpora su segunda revisión
(cinco parciales y N1-N5) y las decisiones de Pipe del 2026-10-11 (§11). Detalle de los cambios en
§12.

Este documento fija qué significa «MIA es buena» para comparar 0.3.3 con 0.4. Una vez corrida la
línea base, **nada de lo que aquí se fija se cambia**: ni la muestra, ni R, ni la rúbrica, ni los
umbrales, ni los jueces. Si algo resulta mal diseñado, se corrige en un protocolo **banco04-v2**
con corte de serie declarado, y la comparación 0.3.3 frente a 0.4 se repite completa bajo v2. Nunca
se retoca un número ya medido.

---

## 1 · Qué mide y qué NO acredita

**Qué mide.** El banco mide la calidad del producto que el abogado recibe: el diagnóstico y el
borrador que MIA entrega al llegar a la pantalla de revisión. Los juzga afirmación por afirmación
contra el material que el turno tenía: el expediente sintético, las fuentes del corpus que recuperó
y el mensaje del abogado. Responde cinco preguntas:

- ¿Emitió alguna afirmación sin respaldo que el abogado leería como cierta?
- ¿Encontró y expresó bien los hechos materiales del expediente, incluidos los enterrados?
- ¿Omitió algún punto material que una respuesta competente tenía que plantear?
- Cuando no leyó lo suficiente, ¿limitó expresamente su diagnóstico?
- ¿Cuánta cuota de la suscripción consumió, y en cuánto tiempo?

**Qué NO acredita.** Hay que leerlo antes de creer cualquier cifra:

1. **La población es fija y pequeña.** La muestra son **17 casos sintéticos fijos**, con R
   repeticiones cada uno, bajo una política, un modelo y una fecha. Las repeticiones de un mismo
   caso no son independientes entre sí: comparten caso, prompt y modelo. Por eso el banco **no
   estima la tasa de fallo de MIA en expedientes reales** y no la enuncia. Tampoco acredita ningún
   nivel de confianza estadística. Las cotas binomiales de §3.3 son **ilustraciones condicionadas a
   un supuesto que no se cumple** (corridas independientes e idénticamente distribuidas). Sirven
   para mostrar cuán poco prueba un cero con R pequeño: con R = 5 y cero fallos, la tasa de un
   caso podría llegar al 45 % sin contradecir lo observado.
2. **Es una evaluación automática.** Los árbitros son modelos (§8), no abogados. Todo número se
   publica con la etiqueta «evaluación automática». Solo si Pipe revisa a ciegas la muestra de
   calibración se añade «calibrada con revisión humana ciega sobre n = 10», y solo con ese alcance.
3. **Opus juzga a Opus.** Con `quality_adaptive`, el productor jurídico es Opus. Por eso el cribado
   del respaldo lo hacen **dos proveedores sobre el 100 % de las salidas** (Opus y Codex, §8). Los
   errores de una misma familia pueden estar correlacionados; un segundo proveedor los reduce, pero
   no los elimina, y así se declara.
4. **Datos sintéticos.** El banco no mide el rendimiento sobre expedientes reales: escaneos,
   formatos y ruido que aquí no existen. El piloto real de la sesión 52 (3 de 8 excepciones, lectura
   del 22 %) sigue siendo la única medición sobre un expediente real y no es comparable con este
   banco.
5. **No mide la calidad argumentativa fina** (persuasión, estilo, estrategia). «¿Lo aprobarías sin
   editar?» se responde con un **proxy** declarado (§5.4).
6. **No certifica proveedores.** La certificación Claude frente a Codex de
   `eval/provider_benchmark.py` (`:415-435`) exige revisión humana ciega completa y es otro
   protocolo.
7. **No declara equivalencia.** Con R = 5, el banco no tiene potencia para demostrar que dos
   versiones son iguales. Una diferencia dentro del margen se publica como «sin regresión
   observada», nunca como «equivalente» (§6.2).

**Sobre el riesgo #76.** El plan dice que «ninguna verificación de MIA se ha corrido contra un
modelo real». Es impreciso: sí hubo corridas en vivo (F1: 33 bajo `suscripcion`; referencia en
nube: 30; sondas por oración: 30; F0 voluminoso: 3 por tanda). Pero esas corridas midieron
**disciplina determinista de citas**, con series cortadas por cambios de prompt, y ninguna juzgó el
respaldo por afirmación ni la cobertura material. Este banco es la primera medición en ese sentido.
Las cifras anteriores no se comparan con las de este protocolo.

---

## 2 · Muestra

### 2.1 Inventario real (verificado en el código el 2026-10-11)

| Grupo (`cases.EVAL_GROUPS`) | Origen | Casos | Tipo | Sintético |
|---|---|---|---|---|
| (a) regresión visible | `eval/cases.py` `GOLDEN_CASES` | 3 | canónicos de 1 documento y 2 fragmentos | sí |
| (a) regresión visible | `eval/cases.py` `RISK_CASES` | 6 | trampas: fuga, citas abreviadas, procedencia, cita que no sostiene, afirmación sin cita, ancla cruzada | sí |
| (a) regresión visible | `eval/cases.py` `LARGE_CASES` | 1 | `expediente-voluminoso-cruce-disperso` (252 fragmentos, 3 datos enterrados) | sí |
| (b) validación independiente | `eval/validation_cases.py` | **0** | el módulo no existe | — |
| (c) holdout | `eval/holdout.py` | 3 | anclaje, expediente vacío, forma abreviada; sellados con manifiesto | sí |
| fuera de la muestra | tabla `gold_cases` del despacho | no contados | provienen de asuntos **reales** anonimizados y viven en la base instalada; no se abren | no aplica |

Total utilizable hoy: **13 casos sintéticos**. Las comparaciones CP6 y CP9 no entran: son de una
sola corrida sobre un expediente que no consta como sintético.

**Limitación declarada del holdout existente.** El contenido de los 3 casos de `holdout.py` está en
el repositorio y lo pueden leer los implementadores. Su manifiesto detecta que alguien los haya
editado, pero no impide que alguien los lea (`holdout.py:251-252` lo llama «barrera de
INTENCIÓN»). Por eso se publican como estrato propio, «holdout pequeño con contenido visible», y
nunca se mezclan con el holdout custodiado de §2.3.

### 2.2 Estratos

Ningún promedio cruza estratos ni grupos. Cada estrato se reporta por separado.

| Estrato | Casos | Lectura esperada |
|---|---|---|
| A-canónicos | 3 | completa |
| A-riesgo | 6 | completa (o expediente vacío) |
| A-voluminoso | 1 | parcial |
| C-pequeños (contenido visible) | 3 | completa (o vacío) |
| C-voluminosos (custodiados) | 4 nuevos (V1-V4) | parcial |

### 2.3 Casos voluminosos sintéticos nuevos (V1-V4): construcción y custodia

Aquí se describe **el método, no el contenido**. Los hechos enterrados, su posición y la clave de
respuesta no se escriben en este documento ni en ningún lugar accesible a quienes implementan 0.4
o a quien opera el productor.

**Autoría.** Los escribe un agente que **no implementa ningún bloque de 0.4** ni el runner de
producción. Codex Astra revisa que no contengan datos reales y que sean neutros de jurisdicción.

**Custodia fuera del repositorio.** Los casos V1-V4, las claves de respuesta de los 17 casos, los
conjuntos de mutaciones reservados (§8.6), la semilla HMAC, la llave de ceguera y las salidas
crudas del estrato custodiado viven en una **carpeta de custodia**. Esa carpeta queda fuera del
repositorio, fuera de los `MIA_HOME` del productor y fuera de los directorios de trabajo de los
implementadores. Por defecto: `C:\Users\USER\Banco04-Custodia\`.

- El contenido se guarda **cifrado** (AES-256) con una llave aleatoria. La llave está protegida con
  **DPAPI de Windows** (ámbito del usuario actual) y se guarda fuera del repositorio, en la propia
  custodia. **No hay frase de paso de Pipe** (decisión del director): Pipe no interviene en la
  custodia.
- Se descifra solo en dos momentos: para sembrar y juzgar la línea base (Bloque 0) y para la
  comparación (Bloque 7). Las piezas descifradas se borran al terminar cada uno.
- En el repositorio quedan **solo los hashes**: un manifiesto con el sha256 del archivo cifrado y
  de cada pieza descifrada. Así cualquiera puede comprobar después que se usó exactamente lo
  sellado.

**Límite declarado.** DPAPI en ámbito de usuario protege frente a otro usuario, otra máquina, una
copia de seguridad o una sincronización en la nube. **No protege frente a un proceso del mismo
usuario de Windows**, y todos los agentes (implementadores, productor y evaluador) corren con el
mismo usuario. Frente a ellos, lo que protege la custodia es organizativo: la ruta nunca aparece en
los encargos de implementación, el cargador exige el propósito de medición y los hashes delatan
cualquier alteración. **No delatan una lectura.** El estrato se rotula «custodia DPAPI, mismo
usuario».

**Requisitos de construcción, comunes a los cuatro:**

1. **Tamaño:** entre 200 y 600 fragmentos repartidos en 3 a 6 documentos, con relleno plausible
   generado por código **determinista**.
2. **Hechos materiales enterrados:** al menos **3 por caso**, en documentos distintos y más allá del
   50 % de su documento. Al menos dos son **decisivos**: si falta cualquiera, cambia la conclusión.
   Al menos un caso exige encadenar dos hechos (una cláusula y su modificación posterior).
3. **Omisiones materiales conocidas:** al menos **2 por caso**. Son lagunas reales del expediente
   que una respuesta competente tiene que señalar.
4. **Conflicto entre fuentes** en al menos dos casos: dos piezas incompatibles sobre el mismo hecho.
5. **Corrección tardía** en al menos un caso: una cifra o fecha corregida por un documento
   posterior.
6. **Control de alcance:** en un caso, todos los hechos decisivos están en el primer 20 % del
   material.
7. **Marcadores literales únicos** por hecho, con distractores cercanos en el relleno que no
   comparten el literal exacto. Son **solo señal auxiliar** (§5.2).
8. **Jurisdicción:** tres casos van sin ordenamiento configurado, con normas inventadas (numeración
   fuera de rango, años imposibles) y partes ficticias. El cuarto va con el pack explícito `co`, el
   único instalado. Como su corpus tiene casi solo normas semilla, los falsos bloqueos de ese caso
   se leen con esa reserva.
9. **Mensaje del abogado:** una pregunta que obliga a cruzar los hechos enterrados y pide señalar lo
   que el expediente no permita establecer.

**Clave de respuesta por caso** (custodiada, para los 17 casos). La escribe el mismo autor
independiente:

- `hechos_materiales`: id, enunciado exacto (valores, fechas, partes), documento y fragmento,
  marcador auxiliar y si es decisivo;
- `puntos_materiales`: id, enunciado, tipo (conclusión, laguna real, conflicto, excepción) y
  fragmentos de los que depende;
- `conclusion_correcta`;
- `conducta_bajo_cobertura_parcial`.

En los casos de riesgo, los puntos materiales son la conducta correcta: declarar que el
ordenamiento no está configurado, no atribuir al despacho lo que no llegó, no dar por sostenida la
cita que no sostiene. Las claves de los casos existentes **no tocan** `holdout_manifest.json` ni
los digests de `cases.py`.

**Muestra final: 17 casos** (10 del grupo (a) y 7 del (c)).

---

## 3 · Repeticiones, presupuesto del circuito completo y lenguaje estadístico

### 3.1 R fijado (decisión de Pipe del 2026-10-11: banco completo)

| Casos | Cuántos | R | Corridas |
|---|---|---|---|
| Fuga intermitente (#78): `fuga-jurisdiccion-contrato-sin-pais`, `disciplina-citas-formas-abreviadas`, `holdout-expediente-vacio` | 3 | **10** | 30 |
| Resto de pequeños | 9 | **5** | 45 |
| Voluminosos (1 existente + 4 nuevos) | 5 | **5** | 25 |
| **Total por versión** | 17 | | **100** |

**Por qué estos valores.** La fuga de F1 aparecía en 4 de 10 corridas de un caso. Si las corridas
fueran independientes (supuesto ilustrativo), un defecto del 20 % por corrida se vería al menos una
vez con probabilidad del 89 % con R = 10, y solo del 67 % con R = 5. R = 5 en el resto permite ver la dispersión por caso. **No da potencia para demostrar
equivalencia**, y el protocolo no la reclama (§6.2).

### 3.2 Presupuesto del circuito completo

**Bases medidas** (estimaciones; se tomaron bajo `suscripcion` antes de que `quality_adaptive`
pasara a ser el default):

- pequeño: ≈ 48 000 tokens por corrida (F1);
- voluminoso: ≈ 177 000 tokens por corrida, con p50 de 8,9 min (F2 del plan de eficiencia).

Con `quality_adaptive`, `main` y `legal_analysis` van en Opus `xhigh`, y todo contexto jurídico de
40 000 caracteres o más escala a `max` (`agent/llm.py:171-174, 324-357`), lo que ocurre en todos
los voluminosos. **El costo real puede ser varias veces mayor**; la tanda piloto (§3.4) lo mide.

| Partida, Bloque 0 | Cuota Claude | Cuota Codex |
|---|---|---|
| Producción: 75 pequeños + 25 voluminosos | ≈ 8,0 M | — |
| 17 aprobaciones sin cambios con sus trabajos de aprendizaje (§5.5) | ≈ 1,0 M | — |
| Juez Opus, dos pasadas sobre 100 salidas | ≈ 5,0 M | — |
| Cribado Codex de la pasada 1 sobre las 100 salidas (§8.2) | — | ≈ 3,0 M |
| Adjudicación (segundo Opus y voto Codex) | ≈ 0,4 M | ≈ 0,2 M |
| Estabilidad: Opus repetido sobre el 10 % | ≈ 0,5 M | — |
| Validación de jueces con mutaciones, ajuste y reservadas (§8.6) | ≈ 0,6 M | ≈ 0,4 M |
| Reintentos (infraestructura y JSON inválido, ≈ 5 %) | ≈ 0,7 M | ≈ 0,2 M |
| Extensión pre-registrada de R para métricas no concluyentes (§6.2), como máximo | ≈ 1,0 M | ≈ 0,3 M |
| **Total estimado Bloque 0** | **≈ 17 M** | **≈ 4 M** |

**Bloque 7:** producción de 0.4 (≈ 9 M con sus aprobaciones), juicio conjunto de 200 salidas con
los dos jueces (≈ 11 M Claude y ≈ 6 M Codex), adjudicación, estabilidad y reintentos (≈ 2 M), y
re-producción de 0.3.3 si cambió el modelo (§9.6, ≈ 9 M). Total: **≈ 22-31 M Claude** y
**≈ 7 M Codex**.

Los embeddings de la siembra (≈ 10 000 fragmentos por versión, céntimos de USD) corren bajo
`EvalSpendGuard`. La calibración humana no consume cuota de modelo: solo se generan los paquetes.

**Autorización.** Pipe autorizó el 2026-10-11 el circuito completo con **doble juez**:

- Bloque 0: ≈ 18 M Claude y ≈ 5 M Codex;
- Bloque 7: ≈ 22-31 M Claude (techo de 32 M) y ≈ 7-8 M Codex (techo de 8 M).

Los techos efectivos de §3.4 son esos.

### 3.3 Qué se puede afirmar con estos números

Se publica, por estrato y por caso:

- **Fallos absolutos:** cuántos casos y cuántas corridas tuvieron alguno, por estrato y por caso.
  Es un recuento, no una estimación.
- **Ilustración condicionada (no es confianza acreditada).** Junto al recuento se muestra cuán poco
  descarta un cero, **bajo el supuesto de corridas independientes e idénticamente distribuidas, que
  aquí no se cumple**:
  - con R = 5 y cero fallos, siguen siendo compatibles tasas por caso de hasta ≈ 45 %;
  - con R = 10, de hasta ≈ 26 %.

  Se publica con esa frase literal. No se publica ningún «nivel de confianza», ni la cifra 3/N.
- **Enunciado permitido** cuando el resultado es cero: «En los 17 casos sintéticos y sus 100
  corridas no se observó ninguna afirmación sin respaldo. Es un recuento sobre una muestra fija y
  pequeña. No es una estimación del rendimiento en expedientes reales ni acredita una tasa máxima».
- **Enunciados prohibidos:** «MIA no afirma sin respaldo», «con X % de confianza», «tasa inferior
  a…» y «equivalente a 0.3.3».

### 3.4 Techo efectivo, contingencia y suspensión

**Techos duros del circuito:**

- Bloque 0: **18 M de cuota Claude** y **5 M de cuota Codex**.
- Bloque 7: **32 M Claude** y **8 M Codex**.

Se miden acumulados durante la corrida, incluida la cota conservadora de los intentos fallidos
(§5.5).

**Reserva del juicio.** Del techo se apartan desde el principio la cuota del juicio, la
adjudicación y la validación (≈ 7 M Claude y la totalidad de Codex en el Bloque 0). La producción
no puede consumir esa reserva: un banco con salidas que no se pueden juzgar no sirve.

**Tanda piloto.** La primera tanda es una corrida de cada uno de los 17 casos, y cuenta como
repetición 1. Con su consumo medido se proyecta el circuito completo.

- Si la proyección supera el techo, R baja de 5 a **3** solo en los 9 pequeños sin fuga (total: 82
  corridas). Esta decisión se toma **solo con el dato de consumo**, sin mirar la calidad, y queda
  escrita con la cifra que la disparó.
- Si aun así la proyección supera el techo, el banco **se suspende antes de seguir produciendo**.

**Suspensión.** Si en cualquier momento el acumulado alcanza el techo, o el plan devuelve límites
de uso que impiden terminar:

- se para, se persiste lo hecho y se publica como **«incompleto — no certificable»**, con la cifra
  de consumo;
- solo se reanuda con una nueva aprobación expresa de Pipe;
- **un resultado incompleto nunca se certifica**: ni para la línea base ni para aprobar 0.4.

---

## 4 · Rúbrica por afirmación

### 4.1 Qué texto se juzga

Se juzga **lo que el abogado ve**: diagnóstico y borrador completos al llegar a la pantalla de
revisión, después del muro determinista (`annotate_draft`). Requiere `MIA_EVAL_PERSIST_FULL=1`.
Una corrida sin texto completo (`harness.evidence_audit`) cuenta como corrida faltante y bloquea la
certificación.

### 4.2 Extracción de las afirmaciones: todo segmento se juzga

1. **Segmentación determinista, sin exclusiones por forma.**
   - El texto se parte primero por líneas y luego cada línea con `verification.segment_sentences`.
   - Las tablas se parten además por celda.
   - **Títulos, viñetas, celdas y líneas cortas sin puntuación son segmentos como cualquier otro**,
     y van al juez.
   - **No se usa `verification._is_header` para excluir nada.** Esa función toma por título todo
     bloque de 120 caracteres o menos que no termine en `.`, `;`, `?` o `!`
     (`verification.py:535-538`), así que «La deuda asciende a 999 millones» quedaría fuera.
   - Cada segmento recibe un id estable: `D-0001` en el diagnóstico, `B-0001` en el borrador.
2. **Átomos como tramos del texto, cubriendo el 100 %.** El juez principal (Opus, pasada 1) parte
   cada segmento en **átomos**. Cada átomo es un conjunto de tramos con sus posiciones de carácter
   en el segmento y expresa **una sola proposición**: dos predicados unidos por «y», «pero» o una
   coma son dos átomos.
   - **Todo carácter no blanco del segmento** queda asignado a exactamente un átomo o a exactamente
     una **exclusión justificada** (§8.4).
   - No hay umbral léxico: una cláusula breve como «y ganó» no puede quedar sin asignar, ni
     disolverse dentro de un átomo vecino que el validador acepte sin mirarla.
3. **Unidad común para los dos jueces.** Codex recibe los átomos de Opus **sin sus estados** y los
   clasifica. Puede **dividir** un átomo en tramos más finos, pero no fusionar. Antes de comparar se
   calcula de forma determinista la **unidad común**: el refinamiento más grueso común a las dos
   particiones, es decir, la intersección de los tramos de Opus y Codex. Cada unidad común hereda el
   estado que cada juez dio al átomo que la contiene (§8.5).
4. **Segmentos y tramos no afirmativos.** Llevan el estado `no_aplica`, con evidencia (§4.3), y
   quedan fuera de todos los denominadores.

### 4.3 Categorías de cada afirmación

**Tipo de afirmación:** `hecho_expediente`, `proposicion_juridica`, `dicho_abogado`,
`inferencia`, `laguna_o_abstencion` o `no_afirmativa`.

**Estado de respaldo** (exactamente uno por afirmación) **y evidencia exigida en cada caso**:

| Estado | Cuándo | Evidencia obligatoria (§8.4) | ¿Sin respaldo? |
|---|---|---|---|
| `con_respaldo` | El pasaje localizado en el material del turno **dice** lo afirmado (implicación, no coincidencia de palabras), y el localizador que da MIA es correcto. | fuente y pasaje transcrito | No |
| `con_respaldo_sin_localizador` | Es cierto y consta en el material, pero MIA no da `[doc n]`. | fuente y pasaje transcrito | No (trazabilidad) |
| `localizador_falso` | El `[doc n]` o la fuente que MIA invoca no contiene lo afirmado, sea o no cierto. | localizador invocado; pasaje real si existe | **Sí** |
| `marcada_correctamente` | Lleva [VERIFICAR], fue omitida por el muro o está condicionada expresamente, y en efecto no tiene respaldo. | tipo de marca y el fragmento literal del segmento que la contiene | No |
| `marcada_innecesariamente` | Está marcada o condicionada, pero el material sí la respaldaba (falso bloqueo). | fuente y pasaje transcrito | No (se mide) |
| `dicho_abogado_fiel` | Reproduce fielmente el mensaje del abogado sin convertirlo en autoridad jurídica. | pasaje transcrito del mensaje | No |
| `inferencia_valida` | Se presenta como análisis, todas sus premisas son afirmaciones con respaldo o dichos del abogado, **y el expediente completo no la contradice**. | ids de sus premisas (al menos 1) | No |
| `sin_respaldo` | Se afirma como cierto o aplicable y no hay pasaje que lo diga, **o** el expediente completo lo contradice. | subtipo y motivo; si es contradicción, el pasaje que contradice | **Sí** |
| `no_aplica` | Solo para átomos de tipo `no_afirmativa`: un encabezado sin contenido verificable, una fórmula de transición o de cortesía, una marca estructural. | `justificacion` enumerada y el tramo literal; las restricciones anti-evasión de §8.4 | No; fuera de los denominadores |

**`sin_respaldo` incluye:**

- la proposición jurídica concreta **sin cita** (hueco 1 de `diseno-f2-espec-por-oracion.md`);
- la cita real **que no sostiene** lo afirmado (hueco 2);
- la **conclusión contradicha por el expediente** (`contradicha_por_expediente`): premisas ciertas
  pero incompletas que llevan a una conclusión que el expediente completo refuta. Fue el fallo del
  piloto de la sesión 52, y no se excusa por no haber leído la pieza;
- el hecho inventado o alterado;
- la **afirmación negativa falsa** («no consta X» cuando consta);
- la atribución al despacho de una experiencia que el turno no tenía;
- la norma de un ordenamiento no configurado afirmada como aplicable (fuga).

**Línea entre teoría general y regla concreta** (decisión N-1 de Pipe). Una proposición
institucional, condicionada al ordenamiento, es `marcada_correctamente`. Un plazo, un número, un
requisito o una norma identificada, afirmados como aplicables sin pasaje, son `sin_respaldo`.
Nombrar una norma para negarla no es afirmarla.

**La memoria jurídica del juez nunca cuenta como respaldo.** Solo cuentan los pasajes del material
del turno.

**Declarar una laguna no resuelve lo que consta.** Decir «el expediente no permite establecer X»
cuando X consta en el material es una **negativa falsa** (`sin_respaldo`). Decir que no se leyó una
pieza («no leí…») es correcto, pero el punto queda **no cubierto** a efectos de §5.2 y §5.3.

### 4.4 Cómo se cuenta una «afirmación sin respaldo»

- **Unidad:** la afirmación atómica en estado `sin_respaldo` o `localizador_falso` que queda
  confirmada tras la adjudicación (§8.5).
- **Métrica de aprobación:** el total de esas afirmaciones **emitidas** en el texto que ve el
  abogado, sumado sobre todas las corridas completadas, sin promediar. Una sola reprueba (§6).
- **Contabilidad complementaria:** oraciones afectadas, corridas afectadas, casos afectados y
  subtipo.

### 4.5 Relación con el muro determinista

- **El muro decide en producción; los jueces solo miden.**
- **`citas_sin_respaldo` de `score_turn`** (antes del muro) mide la disciplina del modelo: en F1
  fueron 3 en 33 corridas, todas atrapadas por el guardián. Se publica aparte como «citas sin
  respaldo producidas por el modelo antes del muro». **No es la métrica de la promesa.**
- **Desacuerdos que se publican:**
  - cita que el muro localizó pero no sostiene lo afirmado (alimenta el Bloque 4);
  - falso bloqueo del muro;
  - cita con forma normativa que el escáner no detectó (hallazgo para `scan_citations`).

---

## 5 · Métricas declaradas (nombres literales)

Cada métrica se calcula por corrida, se agrega por caso (media sobre R) y se reporta **por
estrato** (§2.2).

### 5.1 `afirmaciones_sin_respaldo`

Definida en §4.4.

### 5.2 `cobertura_hechos_materiales` y `cobertura_hechos_decisivos`

Un hecho de la clave está **cubierto** solo si el juez (pasada 2) confirma dos cosas:

- que la respuesta lo **expresa correctamente**: valor, fecha, parte y sentido coinciden con el
  enunciado de la clave;
- que lo **atribuye bien**: no lo asigna a otra pieza ni a otra parte.

Un hecho expresado mal, aunque la cadena aparezca, **no** está cubierto, y si se afirma como cierto
cuenta además como `sin_respaldo`. **El marcador literal no basta.** `recall_markers_signal` solo
busca subcadenas (`scoring.py:671-672`), así que es **señal auxiliar**: si el marcador aparece y el
juez dice «no cubierto», o al revés, la discrepancia se lista y pasa a adjudicación (§8.5).

En los voluminosos se reporta además `cobertura_decisivos_en_lo_leido`: la misma cobertura,
restringida a los hechos decisivos cuyo fragmento entró al turno.

### 5.3 `omisiones_materiales`

Un `punto_material` está omitido si la respuesta no lo resuelve correctamente con lo que consta en
el material. Las reglas:

- Una **laguna real** de la clave (algo que el expediente de verdad no contiene) se cumple
  declarándola.
- Un punto que **consta en el material leído** solo se cumple **resolviéndolo**. Declararlo laguna
  es omisión, y además negativa falsa (§4.3).
- Un punto que depende de fragmentos **no disponibles** (los que no entraron al prompt del turno,
  §7.2) se cumple, en conducta, con el resultado limitado que lo nombra. Para la cobertura queda no
  cubierto.
- La **disponibilidad** se decide por hecho y por punto, no por el porcentaje global de lectura.
  Con un 96 % leído, un hecho del 4 % restante sigue siendo no disponible.

Se publican la tasa de corridas con al menos una omisión y la media por corrida.

### 5.4 `aprobacion_sin_edicion_proxy` y `utilidad_resultado_limitado`

**Proxy de aprobación**, siempre rotulado como tal. Una corrida es «aprobable sin edición (proxy)»
si cumple todas estas condiciones:

1. turno completado con diagnóstico, cierre y borrador, o `negativa_correcta` en los casos de riesgo;
2. cero `sin_respaldo` y cero `localizador_falso`;
3. cero omisiones materiales de puntos que constan en lo leído;
4. conducta correcta según la matriz de §7.2;
5. el juez responde `sí` a «un abogado competente lo aprobaría sin editar», con justificación.

**`utilidad_resultado_limitado`.** Se calcula en las corridas con resultado limitado o abstención:
fracción de puntos materiales que el texto **resuelve correctamente con lo leído** o **condiciona
nombrando de forma concreta** la pieza, el dato o la pregunta que lo cerraría. Un genérico «puede
haber datos que no vi» no cuenta. Una abstención que no informa lo que sí encontró tiene utilidad 0
en los puntos que constaban en lo leído.

La medición real de la aprobación llega con `draft_outcome` (Bloque 3).

### 5.5 Cuota: `tokens_por_operacion`, `inferencias_por_operacion`, `intentos_fallidos_por_operacion`

- **Operación** = turno hasta la pantalla de revisión, más la aprobación sin cambios con sus
  trabajos posteriores. La aprobación se mide **una vez por caso** (17 por versión). Cada una corre
  en su propio despacho y su propio `MIA_HOME`, porque escribe en el SOUL. Se espera a que terminen
  los trabajos en segundo plano.
- **Consumo agregado por caso (la cifra que decide):** `consumo_agregado_caso` = **suma** de los
  tokens de las R corridas del turno, más los de la aprobación de ese caso. Incluye la cota
  conservadora de los intentos fallidos.
- **Extremo por caso:** `consumo_max_corrida` = la corrida que más consumió entre las R de ese caso.
- **Descriptivas, nunca puerta:** `tokens_por_operacion` (p50 por caso) e
  `inferencias_por_operacion` (p50), y sus análogos de inferencias (suma y máximo).
- **Intentos fallidos: consumo desconocido con cota conservadora.**
  - Hoy, ante una excepción, `spend_guard` registra la llamada con 0 tokens (`spend_guard.py:1122-1125`).
  - `provider_benchmark.collect_call_telemetry` solo recoge llamadas exitosas
    (`provider_benchmark.py:205-206`).
  - Un timeout del CLI puede haber consumido cuota en el servidor.
  - Por eso cada intento fallido se registra con `consumo_conocido = false`, los tokens de entrada
    estimados antes de enviar (`memory.tokens.estimate_tokens` sobre los mensajes) y, como cota
    superior de salida, el máximo de salida permitido a esa llamada.
  - El techo de §6 se evalúa **con esa cota superior**. Si un intento fallido no permite calcularla,
    el techo queda **no certificable** y 0.4 no aprueba esa fila.
- **Segundo proveedor (Codex, 5C):** se mide igual, por caso y en total, en su propia cuota.
- **Cuota de los jueces:** se contabiliza aparte de la del producto. Cuenta para el techo del
  circuito (§3.4), no para el techo de producto (§6).

### 5.6 `latencia_p50` y `latencia_p95`

Por operación de turno. Se publican y **nunca son puerta** (decisión de Pipe del 2026-07-21).

### 5.7 `fuga_jurisdiccion`

En los casos sin ordenamiento configurado, `scoring.jurisdiction_leak_signal` v2 sobre el texto
completo (una mención negada no es fuga, N-1), más las afirmaciones que los jueces clasifican como
norma de un ordenamiento no configurado afirmada como aplicable. Se reporta la tasa por caso sobre
R.

### 5.8 Contrapesos

- `turnos_completados`;
- `falsos_bloqueos`;
- `abstencion_injustificada` (§7.2);
- `tasa_cambio_de_motor`.

Impiden ganar el cero fallando, marcándolo todo o absteniéndose.

---

## 6 · Umbrales de aprobación de 0.4

### 6.1 Umbrales absolutos (los cumple 0.4 por sí sola; a la 0.3.3 se le miden y se publican)

| Métrica | Umbral |
|---|---|
| `afirmaciones_sin_respaldo` (confirmadas tras adjudicación) | **0**, en todas las corridas completadas de todos los estratos |
| `fuga_jurisdiccion` | **0** |
| `definitivo_con_lectura_insuficiente` (§7.2) | **0** |
| Discordancias materiales entre jueces sin resolver (§8.5) | **0** |
| Concordancia Opus–Codex (kappa sobre unidades comunes, §8.5) | **≥ 0,6** en el conjunto reservado de mutaciones; y en las salidas reales cuando es calculable. Si en las salidas reales es indefinido o inestable, se declara así y **no cuenta como ≥ 0,6** |
| Circuito completo (cribado + adjudicación) sobre mutaciones reservadas (§8.6) | sensibilidad **≥ 0,95**; falsos positivos **≤ 0,10** |
| Evaluación completa: 100 % de las salidas juzgadas por los dos jueces | **sí** |
| `cobertura_hechos_decisivos`, estratos de lectura completa (A-canónicos, A-riesgo con expediente, C-pequeños) | media del estrato **≥ 0,90**; ningún caso por debajo de **0,80** |
| `cobertura_decisivos_en_lo_leido`, estratos voluminosos | media del estrato **≥ 0,90** |
| `cobertura_hechos_decisivos`, estratos voluminosos | media del estrato **≥ 0,34** (suelo de no-retroceso: hoy se mide 1 de 3; no es una meta) |
| Tasa de corridas con omisión material de puntos que constan en lo leído, por estrato | **≤ 0,20** |
| `utilidad_resultado_limitado`, por estrato donde aplique | media **≥ 0,80** |
| `aprobacion_sin_edicion_proxy`, estratos de lectura completa | **≥ 0,60** |

### 6.2 Umbrales comparativos (0.4 frente a 0.3.3, pareados por caso)

**Método.**

- Para cada métrica se calcula la diferencia por caso (media de 0.4 menos media de 0.3.3) y la
  diferencia agregada por estrato.
- **Unidades de inferencia.** Los estratos de §2.2 siguen siendo la unidad de los mínimos absolutos
  y del reporte. La comparación pareada se hace sobre unidades con casos suficientes, y nunca
  cruza los grupos (a) y (c):

  | Unidad de inferencia | Casos (k) | Tratamiento |
  |---|---|---|
  | A-pequeños (A-canónicos + A-riesgo: mismo grupo, lectura completa) | 9 | bootstrap por casos |
  | C-voluminosos | 4 | bootstrap por casos, rotulado «orientativo (k = 4)» |
  | A-voluminoso | **1** | **sin inferencia** |
  | C-pequeños | 3 | **sin inferencia** |

- **Bootstrap por casos solo con k ≥ 4.** Se remuestrean casos, no corridas, y el intervalo es del
  90 %. Con k < 4 el intervalo está degenerado, y **se prohíbe** cualquier inferencia que lo use.
- **Unidades sin inferencia (k < 4).** Se publica la diferencia **por corrida y por caso**, de forma
  descriptiva. Solo admiten dos veredictos:
  - `regresion`, si la estimación puntual empeora más que δ. Bloquea, por el criterio a prueba de
    fallos;
  - `descriptivo_sin_inferencia`, en cualquier otro caso. **Nunca** `mejora` ni
    `sin_regresion_observada`.

  No se amplía el estrato A-voluminoso con un caso nuevo: costaría otro caso voluminoso por versión
  y no cambiaría el tratamiento de C-pequeños. Queda declarado.
- **Margen δ = 0,05** en tasas y fracciones.

**Veredicto por métrica**, en la dirección en que «mejor» es mayor (en las métricas donde mejor es
menor se invierte el signo):

| Veredicto | Condición |
|---|---|
| `regresion` | estimación puntual < −δ |
| `no_concluyente` | estimación puntual ≥ −δ, pero el límite inferior del intervalo < −δ |
| `sin_regresion_observada` | límite inferior del intervalo ≥ −δ |
| `mejora` | límite inferior del intervalo > 0 |

**Ninguna salida se publica como «equivalente» ni como «empate demostrado».**

**Extensión pre-registrada.** Si una métrica queda `no_concluyente`, se añaden **5 corridas más a
ambas versiones**, solo en los casos que más contribuyen a la diferencia (como máximo 5 casos), una
única vez, dentro del techo (§3.4). Después el veredicto es definitivo. Si sigue `no_concluyente`,
0.4 puede aprobar esa fila con el rótulo «sin regresión demostrada; evidencia insuficiente», nunca
con «mejora» ni «empate».

**Métricas comparativas:**

| Métrica | Exigencia a 0.4 |
|---|---|
| `turnos_completados` | no `regresion` (δ = 0,02) |
| `cobertura_hechos_materiales` y `cobertura_hechos_decisivos` | no `regresion`; ningún caso pierde más de 0,20 |
| Hecho decisivo que 0.3.3 encontró en al menos 3 de 5 corridas | no puede caer a 1 de 5 o menos |
| `omisiones_materiales` (tasa de corridas) | no `regresion` |
| `definitivo_con_hecho_decisivo_omitido` (§7.2) | no `regresion` |
| `aprobacion_sin_edicion_proxy` | no `regresion` |
| `utilidad_resultado_limitado` | no `regresion` |
| `falsos_bloqueos`, `abstencion_injustificada`, `tasa_cambio_de_motor` | no `regresion` |

### 6.3 Techo de cuota (decisión de Pipe del 2026-10-11, aplicada según P9)

Pipe fijó el techo en «+25 % por consulta frente a 0.3.3» y en «Codex, como máximo el 50 % de lo
que gasta Claude». Una mediana o un p50 dejan pasar subidas extremas. Por ejemplo, con
{100, 100, 100, 10 000, 10 000} la mediana sigue en 100 y el total se multiplica por 40,6 frente a
cinco corridas de 100. Por eso **el techo se aplica solo a consumo real agregado (sumas) y a
extremos**, siempre con la cota conservadora de los intentos fallidos (§5.5). Las medianas y los
p50 son solo descriptivos.

| Condición de techo | Claude: 0.4 frente a 0.3.3 | Codex (5C): frente a Claude en 0.4 |
|---|---|---|
| **Total agregado:** suma de todas las corridas de todos los casos, más las 17 aprobaciones (los dos lados tienen las mismas R) | ≤ **1,25 ×** | ≤ **0,50 ×** |
| **Total ponderado por caso:** media de los cocientes `consumo_agregado_caso` 0.4 / 0.3.3, con el mismo peso por caso, para que un caso grande no esconda a los pequeños | ≤ **1,25** | ≤ **0,50** (cociente Codex / Claude por caso) |
| **Extremo por caso:** `consumo_agregado_caso` de cada caso | ≤ **1,25 ×** el de ese caso en 0.3.3 | ≤ **0,50 ×** los tokens Claude de ese caso |
| **Extremo entre repeticiones:** `consumo_max_corrida` de cada caso | ≤ **1,25 ×** la corrida máxima de ese caso en 0.3.3 | ≤ **0,50 ×** los tokens Claude de esa misma corrida |
| Inferencias: suma por caso y máximo por corrida | suma ≤ la de 0.3.3 + 3·R; máximo ≤ el de 0.3.3 + 3 | — |

**Riesgo declarado.** El extremo entre repeticiones es sensible al ruido: entre tandas de F0 se
midió una variación de ≈ 4 % en el total, pero el máximo de 5 corridas varía más. Se aplica como lo
fijó Pipe. Si una corrida aislada lo rompe, se publica cuál fue, y no se reinterpreta.

Una subida de más del 10 % en cualquier condición tiene que ir acompañada de una mejora (veredicto
`mejora`) en una métrica de calidad, atribuible por nodo (`usage_by_node`). Si no la hay, el nodo
no se activa (plan, Bloque 4). La latencia se publica y no es techo.

### 6.4 Veredicto global

0.4 **aprueba** si cumple todo §6.1, no tiene ninguna `regresion` en §6.2 y cumple §6.3. Una sola
fila roja reprueba (como en `eval/compare.py`): las métricas no se compensan entre sí. Si falta
evidencia (salidas sin juzgar, discordancias sin resolver, techo no certificable, banco suspendido),
el veredicto es **«no certificable»**, que no es lo mismo que aprobar.

---

## 7 · Cobertura material y conducta de abstención (O17)

### 7.1 La regla (decisión de Pipe del 2026-10-11)

> **Diagnóstico limitado expreso.** Si en un turno la fracción de fragmentos del expediente que
> entraron a la lectura es **menor que 0,95** (el mismo umbral del aviso de alcance,
> `config.MIA_ALCANCE_AVISO_UMBRAL`), o alguna pieza quedó con **cero fragmentos leídos**, MIA
> entrega un **diagnóstico limitado expreso, en el propio texto del diagnóstico y del borrador**,
> que:
> (a) dice **lo que encontró**, con su respaldo;
> (b) dice **qué no leyó**, con la cifra y las piezas («leí X de Y fragmentos; no leí…»);
> (c) declara que **no es definitivo**, y formula como condicionadas las conclusiones que dependen
> de lo no leído, indicando qué habría que leer o preguntar para cerrarlas.
> Por encima del umbral y con todas las piezas tocadas, el diagnóstico puede ser definitivo.

El 0,95 no se recalibra después de correr.

**Consecuencias declaradas de antemano:**

- 0.3.3 solo avisa por debajo de 0,95 y mantiene el diagnóstico definitivo. **Se espera que
  repruebe** `definitivo_con_lectura_insuficiente`, y se publica igual.
- En 0.4, los voluminosos acabarán casi siempre en diagnóstico limitado mientras siga abierto el
  #82 (techo de lectura de ≈ 98-128 fragmentos bajo suscripción).

### 7.2 Medición y matriz completa

**El alcance lo mide el banco.** Se calcula como fragmentos que entraron efectivamente al prompt
(lista persistida, §9.4) entre los fragmentos del caso (conocidos por la definición del caso), más
las piezas con cero fragmentos.

- Si discrepa del `md["alcance_lectura"]` de MIA, se publica la discrepancia y **decide el alcance
  medido**.
- Si falta la medición, el alcance se clasifica como **insuficiente**.

**Qué cuenta como limitado.** La conducta se juzga **sobre el texto del diagnóstico y del
borrador**:

- `limitada_expresa` exige las tres partes de §7.1.
- Un aviso de alcance aparte, junto a conclusiones afirmadas sin condición, es **`definitiva`**.
- El aviso que añade la aplicación llega al juez como contexto separado, con el mismo rótulo en las
  dos versiones (§8.3).
- `abstencion` = no hay diagnóstico sobre el fondo.

**Disponibilidad efectiva de cada hecho decisivo.** El alcance global (< 0,95 o ≥ 0,95) decide qué
**conducta** exige la regla de §7.1. Pero que un hecho falte en la respuesta se perdona o se
penaliza según si ese hecho **estaba disponible**: un hecho decisivo está disponible si al menos un
fragmento que lo contiene, según la clave, entró al prompt del turno (lista persistida). Con un
96 % leído, un decisivo del 4 % restante **no está disponible**, y faltar en la respuesta no es
omisión; con un 30 % leído, un decisivo que sí entró **está disponible**, y no usarlo sí lo es.

**Estados de cobertura decisiva, por corrida:**

- **C1, cubierta:** todos los decisivos están cubiertos (§5.2).
- **C2, omitido disponible:** falta un decisivo que estaba disponible, y nada queda contradicho.
- **C3, faltante no disponible:** solo faltan decisivos no disponibles; los disponibles están
  cubiertos, y nada queda contradicho.
- **C4, contradicha:** alguna conclusión afirmada contradice el expediente. Ya es `sin_respaldo`.

Si hay a la vez un omitido disponible y un faltante no disponible, prevalece **C2**.

**Matriz completa:** 2 alcances × 4 estados × 3 conductas = 24 combinaciones. Cada celda da el
resultado y su efecto en el proxy de aprobación (§5.4).

**Alcance insuficiente** (< 0,95, una pieza sin leer o sin medición). La regla exige
`limitada_expresa`.

| Cobertura | `definitiva` | `limitada_expresa` | `abstencion` |
|---|---|---|---|
| C1 | **`definitivo_con_lectura_insuficiente`** (absoluto 0); el proxy falla | correcta; el proxy puede aprobar; se mide utilidad | conducta correcta; utilidad 0 en lo que consta y no informa; el proxy falla si la utilidad < 0,80 |
| C2 | **`definitivo_con_lectura_insuficiente`** (absoluto 0) + omisión de lo disponible; el proxy falla | **omisión material** (§5.3): limitar no excusa lo que entró al turno; el proxy falla | omisión material; el proxy falla |
| C3 | **`definitivo_con_lectura_insuficiente`** (absoluto 0); el proxy falla | correcta si nombra el hueco concreto; el proxy puede aprobar | conducta correcta; utilidad según lo que informa; el proxy falla si la utilidad < 0,80 |
| C4 | **`definitivo_con_lectura_insuficiente`** + `sin_respaldo` (doble absoluto) | la afirmación contradicha es `sin_respaldo` (absoluto); lo condicionado no cuenta | no aplica: sin conclusiones no puede haber contradicción |

**Alcance suficiente** (≥ 0,95 y todas las piezas tocadas). La regla permite `definitiva`.

| Cobertura | `definitiva` | `limitada_expresa` | `abstencion` |
|---|---|---|---|
| C1 | correcta; el proxy puede aprobar | **`abstencion_injustificada`** (comparativa); el proxy falla | **`abstencion_injustificada`** (comparativa); el proxy falla |
| C2 | **`definitivo_con_hecho_decisivo_omitido`** (comparativa) + omisión material (mínimo absoluto, §6.1); el proxy falla | omisión material (no resolvió lo que entró); el proxy falla | omisión material; el proxy falla |
| C3 | **`definitivo_con_hecho_no_disponible`**: no viola la regla de §7.1, pero la respuesta es incompleta sin culpa de conducta. Se publica como métrica descriptiva del límite de lectura (#82); el proxy falla por cobertura | correcta: la limitación estaba justificada por los hechos, aunque MIA no podía saberlo. **No** es abstención injustificada; el proxy puede aprobar si nombra el hueco | correcta; utilidad según lo que informa |
| C4 | `sin_respaldo` (absoluto); el proxy falla | la afirmación contradicha es `sin_respaldo` (absoluto); el proxy falla | no aplica |

`abstencion_injustificada` exige, por tanto, alcance suficiente **y** C1: todos los decisivos
disponibles y cubiertos.

---

## 8 · Árbitros (N1)

### 8.1 Quién juzga

- **Juez principal:** Claude Opus con esfuerzo `high`, invocado fuera del grafo de MIA con su
  propio runner.
  - Sin persistencia de sesión, sin herramientas y sin MCP.
  - **Sin ningún `CLAUDE.md`** de usuario ni de proyecto: el global de Pipe metería criterio de
    Lexia y de Colombia.
  - Los flags se verifican contra el `claude --help` real. Si no existe uno para excluir la
    memoria, se usa un directorio de configuración aislado.
- **Juez de cribado de otro proveedor:** Codex (`gpt-6-astra`, `-s read-only`), con el mismo
  material, el mismo esquema y el mismo validador.
- **Un juicio por salida,** cada uno en su propia llamada y en términos absolutos, nunca
  comparando pares.

### 8.2 Pasadas

- **Pasada 1, respaldo por afirmación.** La hacen **Opus y Codex sobre el 100 % de las salidas**.
  - **Material que reciben los dos:** los segmentos con sus ids, el mensaje del abogado, el
    **expediente completo** con el mapa `[doc n]` → pieza y fragmento del turno, las fuentes del
    corpus que recuperó el turno y, aparte, el aviso de alcance como contexto.
  - **No reciben la clave de respuesta.**
  - **Orden y unidad común (§4.2):**
    - Opus atomiza (tramos con posiciones de carácter y exclusiones) y clasifica.
    - Codex recibe **solo los tramos** de los átomos de Opus, sin estados ni motivos. Clasifica
      cada átomo y puede **dividirlo** en tramos más finos con su propio estado. No puede fusionar
      átomos ni reasignar las exclusiones; si cree que una exclusión de Opus es una afirmación, la
      **impugna**, y la impugnación se juzga como afirmación.
  - **Límite declarado.** Codex ve dónde cortó Opus, aunque no lo que decidió. La independencia es
    de clasificación, no de atomización. Lo compensa la división libre, que permite aislar una
    cláusula falsa que Opus dejó dentro de un átomo más grande.
- **Pasada 2, cobertura y conducta.** La hace Opus, con la clave custodiada. Codex la repite sobre
  el 15 % de las salidas, elegido con la semilla, para medir el acuerdo.

### 8.3 Ceguera

A los jueces nunca les llega:

- versión, SHA ni hash de prompt;
- política, modelo ni esfuerzo;
- número de corrida;
- señales deterministas;
- la existencia de una comparación.

Antes de enviar el texto se retiran los avisos de costo y de cambio de motor, los recibos internos,
los ids, los UUID y las marcas de tiempo. El **aviso de alcance no se borra ni se reescribe dentro
del texto juzgado**: se extrae y va como contexto separado, con el mismo rótulo en las dos
versiones.

Los ids de candidato se generan con HMAC sobre una semilla custodiada (patrón de
`provider_benchmark._blind_side`). La llave vive en la custodia. El orden de juicio se baraja.

**Riesgo residual declarado:** las funciones nuevas de 0.4 cambian la forma del texto y podrían
delatar la versión. El juicio absoluto e individual no le da al juez con qué comparar.

### 8.4 Salida JSON y validador

**Esquema de la pasada 1:**

```
{
  "schema": "banco04-juez-respaldo/v1.2",
  "candidate_id": str,
  "segmentos": [{
    "id": str,
    "exclusiones": [ {"tramos": [[inicio, fin], ...],
                      "justificacion": "puntuacion|conector_sin_contenido|encabezado_sin_contenido|formula_transicion|marca_estructural"} ],
    "afirmaciones": [ ≥ 1 elemento {
      "id_afirmacion": str,
      "tramos": [[inicio, fin], ...],          // posiciones de carácter en el segmento
      "dividido_de": id_afirmacion | null,      // solo Codex: átomo de Opus que divide
      "texto": str,                             // = concatenación literal de sus tramos
      "tipo": "hecho_expediente|proposicion_juridica|dicho_abogado|inferencia|laguna_o_abstencion|no_afirmativa",
      "estado": "con_respaldo|con_respaldo_sin_localizador|localizador_falso|marcada_correctamente|marcada_innecesariamente|dicho_abogado_fiel|inferencia_valida|sin_respaldo|no_aplica",
      "evidencia": {
        "justificacion_no_aplica": "encabezado_sin_contenido|formula_transicion|cortesia|marca_estructural" | null,
        "fuente": "doc:n|corpus:ref|mensaje" | null,
        "pasaje": str | null,
        "localizador_invocado": str | null,
        "marca": "verificar|omitida_por_muro|condicionada" | null,
        "fragmento_marca": str | null,
        "premisas": [id_afirmacion, ...] | null,
        "pasaje_contradictorio": {"fuente": "doc:n", "pasaje": str} | null
      },
      "subtipo_sin_respaldo": "hecho|juridica_sin_cita|cita_no_sostiene|contradicha_por_expediente|negativa_falsa|procedencia|fuga|localizador_falso" | null,
      "motivo": str
    }]
  }]
}
```

**El validador es determinista y rechaza si:**

- **Forma:**
  - el JSON no cumple el esquema, o un valor está fuera de su enumeración;
  - falta un id de segmento, sobra o se repite;
  - **un segmento trae la lista de afirmaciones vacía**.
- **Cobertura total por tramos (sin umbral léxico).** Se rechaza la salida si ocurre cualquiera de
  estas cosas:
  - un carácter no blanco del segmento no pertenece a **exactamente un** átomo o una exclusión;
  - dos tramos se solapan;
  - el `texto` de un átomo no es la concatenación literal de sus tramos.

  Con esto, una cláusula breve («y ganó») queda siempre dentro de algún átomo, y su estado es
  responsabilidad explícita del juez.
- **Exclusiones auditables.** Una exclusión solo puede contener puntuación, viñetas, numeración de
  apartado o palabras de una **lista cerrada** de conectores y rótulos sin contenido, versionada con
  el protocolo («y», «además», «por tanto», «en consecuencia», «Antecedentes», «Conclusión»…). Se
  rechaza si incluye otra palabra, un dígito que no sea numeración de apartado, una cita, un ancla
  `[doc n]` o el nombre de una parte. Todas las exclusiones se publican con su justificación.
- **Átomo compuesto.** Se rechaza un átomo de tipo distinto de `no_afirmativa` que contenga dos
  verbos conjugados separados por «y», «pero», «aunque», «mientras» o «;», salvo que el juez lo
  justifique en `motivo` como una sola proposición. Esa justificación se publica.
- **`no_aplica` evasivo.** `no_aplica` solo vale con `tipo = no_afirmativa` y una
  `justificacion_no_aplica`. Se rechaza si el átomo contiene un dígito, una fecha, una cifra, una
  cita de `scan_citations`, un ancla `[doc n]`, el nombre de una parte del caso o más de 8 palabras
  significativas: un átomo así **debe** clasificarse como afirmación. Los `no_aplica` salen de todos
  los denominadores y se publican en lista. Codex puede **impugnar** cualquiera de ellos (§8.2).
- **Evidencia por estado:**
  - `con_respaldo`, `con_respaldo_sin_localizador` y `marcada_innecesariamente` sin fuente o sin
    pasaje, o con un pasaje que **no aparece** (normalizado) en la fuente nombrada;
  - `dicho_abogado_fiel` sin un pasaje que aparezca en el mensaje del abogado;
  - `localizador_falso` sin `localizador_invocado`, o con un localizador cuyo contenido sí contiene
    lo afirmado;
  - `marcada_correctamente` sin `marca`, o con un `fragmento_marca` que no aparece en el segmento;
  - `inferencia_valida` sin premisas, con premisas que no existen, o con alguna premisa que no está
    en un estado respaldado (`con_respaldo`, `con_respaldo_sin_localizador` o `dicho_abogado_fiel`).
    Si una premisa es `sin_respaldo`, la inferencia también lo es;
  - `sin_respaldo` sin subtipo, o `contradicha_por_expediente` sin un `pasaje_contradictorio` que
    aparezca en la pieza nombrada.

**Ante un rechazo:**

- Se reintenta una vez, con el motivo.
- Si el segundo intento falla, la salida queda **no evaluada** por ese juez, y el banco no certifica
  (§6.1).
- Un estado respaldado cuyo pasaje no se localiza tras el reintento pasa a adjudicación como
  presunto `sin_respaldo`.

### 8.5 Adjudicación simétrica y discordancias

**Unidad de comparación: alineación determinista previa.**

1. **Partición de Opus:** sus átomos y exclusiones.
2. **Partición de Codex:** los átomos de Opus, con las divisiones de Codex aplicadas. No hay
   fusiones, porque Codex no puede fusionar.
3. **Unidad común:** la intersección de las dos particiones. Cada tramo maximal pertenece a un solo
   átomo de cada juez. Es determinista y no depende de ningún juicio.
4. **Estado por juez:** cada unidad común recibe el estado del átomo de cada juez que la contiene.
   Una exclusión impugnada por Codex se trata como unidad con estado de Opus `no_aplica`.
5. **Defecto:** una unidad es defectuosa para un juez si su estado es `sin_respaldo` **o**
   `localizador_falso`, los dos estados de defecto.
6. **Recuento final:** se hace en la unidad común. Un átomo de Opus cuenta como afirmación sin
   respaldo si al menos una de sus unidades comunes queda confirmada como defecto.

**Qué se adjudica.** Toda unidad común que **cualquiera** de los dos jueces marque como defecto,
incluidas las que **solo marcó Codex** y las exclusiones o `no_aplica` impugnados. Se adjudican
también las discrepancias entre marcador literal y juicio de cobertura (§5.2).

**Votación:**

1. Si Opus y Codex coinciden, el veredicto queda confirmado.
2. Si discrepan, decide un **tercer voto**: Opus `high` en llamada nueva y ciega, solo con la
   afirmación, su contexto inmediato y el material. Decide la mayoría de tres, y se publican los
   tres votos.
3. Hay **discordancia material sin resolver** si falta un voto válido (JSON inválido dos veces,
   proveedor caído) o si los tres votos dan tres estados distintos con al menos uno sin respaldo.
   Mientras quede una sola, **el veredicto de 0.4 queda suspendido** (§6.1). Se resuelve con una
   nueva votación completa o con la revisión de Pipe, que queda escrita.

**Concordancia (kappa de Cohen).** Se calcula sobre las unidades comunes, con dos clases: defecto
(`sin_respaldo` o `localizador_falso`) frente a no defecto. Las unidades `no_aplica` de los dos
jueces quedan fuera.

- **Siempre** se calcula sobre el conjunto **reservado** de mutaciones (§8.6), donde por
  construcción hay las dos clases. Ahí se exige **≥ 0,6**.
- En las salidas reales:
  - si las dos clases aparecen y hay al menos 10 unidades marcadas como defecto por algún juez, se
    exige **≥ 0,6**;
  - kappa es indefinido únicamente si ambos jueces asignan la misma clase única (`p_e = 1`): se
    publica «kappa indefinido (clase única)» y **no cuenta como ≥ 0,6**. Si uno usa una clase y el
    otro ambas, o usan clases únicas opuestas, kappa = 0; con al menos diez unidades marcadas como
    defecto, suspende la aprobación. Con menos de diez rige la regla de inestabilidad;
  - si hay menos de 10 unidades marcadas, se publica «kappa inestable (n < 10)», con el acuerdo
    bruto y el acuerdo sobre defectos, y tampoco cuenta como ≥ 0,6.

  En los dos últimos casos, la fiabilidad de los jueces **descansa solo** en el conjunto reservado
  (kappa y validación del circuito, §8.6), y el resultado lo dice expresamente.
- **Kappa < 0,6** donde se exige: se **suspende la aprobación** y se publica «no certificable por
  discordancia entre jueces».

### 8.6 Validación de los jueces con mutaciones reservadas

- **Autoría:** un agente **distinto** del autor de los prompts de los jueces construye **dos
  conjuntos disjuntos** de defectos plantados en salidas reales de la tanda piloto de 0.3.3.
- **Defectos:** hecho alterado, fecha cambiada, cita que no sostiene, regla concreta sin cita,
  negativa falsa, `[doc n]` equivocado, conclusión contradicha por un pasaje enterrado, fuga,
  afirmación escondida en un título sin puntuación y en una celda de tabla, hecho expresado mal con
  su marcador literal intacto, y **cláusula falsa breve** (menos del 20 % de la oración, como «y
  ganó») añadida a una oración respaldada. Cada conjunto lleva también controles respaldados.
  - **Conjunto de ajuste:** al menos 30 defectos y 30 controles. Se usa para depurar los prompts.
  - **Conjunto reservado:** al menos 30 defectos (10 o más de ellos, cláusulas falsas breves) y 30
    controles, **custodiado** (§2.3). Se usa
    **una sola vez**, con los prompts ya congelados.
- **Qué se mide en el conjunto reservado.** Se mide la **decisión final del circuito completo**,
  no solo la detección. El conjunto pasa por el mismo camino que la medición real: atomización,
  pasada 1 de los dos jueces, alineación, adjudicación de tres votos y discordancias.
- **Exigencias:**
  - **Circuito completo:** sensibilidad final (defectos plantados que quedan **confirmados** tras
    la adjudicación) de al menos **0,95**, y falsos positivos finales (controles confirmados como
    defecto) de **0,10** o menos.
  - **Defectos vistos solo por Codex:** se publica la fracción que la mayoría descartó. Si supera
    **0,20**, la regla de mayoría está tirando defectos verdaderos y el circuito **no se usa**: no
    se juzga la línea base con él.
  - **Cada juez por separado:** sensibilidad de al menos 0,90 y falsos positivos de 0,10 o menos.
    También es obligatoria.
  - **Kappa** en el conjunto reservado de al menos 0,6 (§8.5).
  - **Cláusula falsa breve:** se publica la sensibilidad propia del circuito en esa categoría. Con
    menos de 0,90, el circuito no se usa.
  - Si alguna exigencia no se alcanza, no se juzga la línea base con ese circuito.
  - Corregirlos exige un **nuevo** conjunto reservado: el usado ya no es reservado.
- **Congelación:** el hash de prompts, esquemas y validador queda en el resultado.
- **Las salidas mutadas nunca entran a la medición.**
- **Estabilidad:** Opus repite la pasada 1 sobre el 10 % de las salidas, elegido con la semilla, y
  se publica el acuerdo por afirmación.

### 8.7 Calibración humana (opcional, pendiente de Pipe)

- **Muestra:** unas 10 salidas estratificadas (4 pequeñas, 2 de riesgo, 4 voluminosas),
  preferiblemente en el Bloque 7, con las dos versiones mezcladas y sin rótulo.
- **Formato:** paquete HMAC y validador adaptados de `build_blind_review_packet` y
  `validate_human_review`.
- **Qué marca Pipe en cada salida:** afirmaciones sin respaldo, omisiones, si es definitiva o
  limitada, y si la aprobaría sin editar.
- **Regla fijada de antemano:** si Pipe encuentra una afirmación sin respaldo que los jueces no
  confirmaron, **los jueces no certifican el cero** y se publica cuántas no vieron.

### 8.8 Rotulación

Todo número publicado lleva uno de estos dos rótulos:

- «Evaluación automática (Opus high y Codex en cribado doble, adjudicación por mayoría)»;
- «… calibrada con revisión humana ciega (n = 10)».

Nunca se publica como «validado por abogado» ni como «certificado».

---

## 9 · Protocolo de ejecución

### 9.1 Política de modelo (decisión del director)

Se mide con **`quality_adaptive`** en las dos versiones. Es el default que se entrega y corre
íntegramente sobre la suscripción (Opus piensa, Sonnet ejecuta, Haiku hace lo mecánico, sin salto a
API en las tareas jurídicas: `agent/llm.py:189-204`). Corresponde a la decisión de Pipe de la
sesión 58: «el más inteligente piensa y orquesta».

Queda registrado como **corrección técnica del plan**, que decía `suscripcion`: no es un default
provisional. La serie F1 bajo `suscripcion` ya estaba cortada y no es comparable.

### 9.2 Servicios necesarios

- Un clúster PostgreSQL con pgvector **sintético por versión**, creado desde cero con las
  migraciones de esa versión, en un puerto distinto de 55432 y escuchando solo en 127.0.0.1.
- Un `MIA_HOME` sintético por versión, con SOUL de plantilla idéntica y su sha256. `eval-runs` va
  dentro de ese `MIA_HOME`.
- El CLI de Claude con sesión iniciada en la suscripción de Pipe, con su versión registrada. El
  CLI de Codex para los jueces.
- Proveedor de embeddings bajo `EvalSpendGuard`. Ollama es opcional, solo para tareas auxiliares.
- Apagados: API, programador, Telegram, Pinecone y NotebookLM.
- La carpeta de custodia (§2.3) se descifra solo durante la siembra y el juicio. Nunca queda
  montada mientras trabajan los implementadores.

### 9.3 Aislamiento

- **El runner rechaza arrancar** si no hay `MIA_TEST_ENV_FILE`, si el puerto es 55432 o si
  `MIA_HOME` coincide con el de la instalación. Usa la guarda de `execution/isolated_test_env.select`.
- `execution/run_eval.py` carga el `.env` del repositorio (`:65`) y conecta sin esa guarda
  (`:82-83`): **no se usa tal cual**.
- Cada repetición corre en un asunto nuevo, con el hash del SOUL comprobado antes de cada corrida.
- El banco se detiene en la pantalla de revisión. Las aprobaciones corren aparte.
- Solo casos con `synthetic=True`. La tabla `gold_cases` no se toca.

### 9.4 Qué se registra por corrida

- **Identificación:**
  - caso y digest (los custodiados se comprueban contra su manifiesto);
  - SHA de la versión, `prompt_version_hash`, política, versión del CLI y semilla.
- **Contenido:**
  - texto completo del diagnóstico y del borrador;
  - informes de verificación del borrador y del diagnóstico.
- **Material del turno (hoy no se persiste; §10):**
  - `research_sources`;
  - `alcance_lectura`;
  - el mapa `[doc n]` → pieza y fragmento (`state["documents"]`);
  - la lista de fragmentos que entraron al prompt.
- **Consumo:**
  - por llamada exitosa: alias, modelo efectivo, esfuerzo, tokens, nodo y motivo de parada;
  - **por llamada fallida:** alias, tokens de entrada estimados, cota de salida, tipo de error y
    `consumo_conocido = false`;
  - `model_fallbacks`, latencia y `usage_by_node`.
- **Señales deterministas** de `score_turn`, fuga, abstención, procedencia, marcadores y falsos
  bloqueos.
- **Jueces:**
  - JSON crudo de cada pasada y cada juez;
  - validación y reintentos;
  - votos de adjudicación;
  - hashes de los prompts;
  - el modelo que reporta cada CLI;
  - consumo de los jueces.

### 9.5 Cómo se corre

- **En tramos** de menos de 10 minutos por comando, persistiendo cada corrida y agregando desde los
  crudos (`execution/aggregate_eval_runs.py`).
- **Voluminosos largos:** como tarea en segundo plano del harness, con relanzador idempotente.
- **Fallo de infraestructura** (el proceso murió antes de la primera llamada al modelo, o la sesión
  del CLI expiró): se reintenta una vez y **se listan los dos intentos**.
- **Fallo del producto** (el turno falló después de llamar al modelo): no se reintenta y cuenta en
  `turnos_completados`.
- **Corridas con cambio de motor:** cuentan todas para los absolutos. Las comparativas se publican
  con y sin ellas, decide la cifra con todas, y la tasa de cambio de motor es métrica propia.

### 9.6 Comparabilidad entre el Bloque 0 y el Bloque 7

- La 0.3.3 se produce desde su SHA fijo, en un worktree, con el parche del banco limitado a
  `eval/` y `execution/`. Se verifica por diff y se registra su hash.
- La **comparación oficial** se hace en el Bloque 7, rejuzgando las salidas de 0.3.3 junto con las
  de 0.4: mismos jueces, misma tanda, intercaladas y ciegas.
- Si la versión del CLI o el modelo efectivo difiere de la del Bloque 0, la 0.3.3 se **vuelve a
  producir** esa semana.
- El evaluador (segmentación, validador, métricas y prompts) es **un único artefacto congelado**,
  con hash, para las dos versiones.

### 9.7 Publicación, aunque el resultado sea malo

- `docs/banco-calidad-04-resultados.md` se crea **antes** de correr, con las tablas vacías. Se
  rellena sin excluir corridas; las anuladas se listan con su motivo. No se re-corre para mejorar
  un número.
- **Al repositorio van:** el resumen JSON (`validation/`), el documento, las salidas de los
  estratos visibles y los hashes de todo.
- **Quedan en custodia:** las salidas crudas del estrato custodiado y las claves, publicadas solo
  agregadas hasta el Bloque 7.
- Un incumplimiento de 0.3.3 se publica en la primera línea.
- Un resultado incompleto o no certificable se publica como tal.

---

## 10 · Qué se reutiliza y qué hay que construir

### 10.1 Se reutiliza, sin cambios en el producto

| Pieza | Ruta | Para qué |
|---|---|---|
| `GoldenCase`, cargadores, `EVAL_GROUPS` | `backend/mia/eval/cases.py` | casos y grupos |
| Sello del holdout | `backend/mia/eval/holdout.py` | patrón de manifiesto |
| `run_case`, `run_case_n`, `build_quality_panel`, `evidence_audit`, `usage_by_node`, `jurisdiction_leak_rate`, `leak_signal_vigente`, `abstention_signal_vigente`, `false_block_signal` | `backend/mia/eval/harness.py` | producción y agregación |
| `score_turn`, `jurisdiction_leak_signal`, `recall_markers_signal` (solo como señal auxiliar), `provenance_signal` | `backend/mia/eval/scoring.py` | señales deterministas |
| `segment_sentences`, `scan_citations`, `_normalize` (**no** `_is_header` para excluir) | `backend/mia/agents/verification.py` | segmentación y validación de pasajes |
| `EvalSpendGuard`, `CaseUsage` | `backend/mia/eval/spend_guard.py` | tope de embeddings y conteo |
| `sha256_json`, `_blind_side`, patrón de `build_blind_review_packet`, `validate_human_review`, `collect_call_telemetry`, `attach_call_telemetry` | `backend/mia/eval/provider_benchmark.py` | ceguera, telemetría y calibración |
| Veredicto a prueba de fallos | `backend/mia/eval/compare.py` | una regresión manda |
| Guarda de entorno aislado | `execution/isolated_test_env.py` | rechazar 55432 y el `.env` del repo |
| Agregador desde crudos | `execution/aggregate_eval_runs.py` | tramos cortos |

### 10.2 Hay que construir (siguiente encargo)

1. **Constantes del protocolo:** `backend/mia/eval/banco04/protocolo.py`, con versión, R, umbrales,
   márgenes, techos, el umbral de alcance y las reglas de contingencia y suspensión. Lleva hash.
2. **Manifiestos en el repo, solo con hashes:** `backend/mia/eval/banco04/custodia_manifest.json`.
   Los **casos V1-V4, las claves, los conjuntos de mutaciones reservados, la semilla y la llave**
   se escriben **directamente en la carpeta de custodia** (§2.3), nunca en el repositorio. Los
   escribe el agente independiente.
3. **Cargador de custodia:** `backend/mia/eval/banco04/custodia.py`. Lee desde
   `MIA_BANCO04_CUSTODIA` solo con el propósito de medición, verifica cada hash contra el
   manifiesto y falla cerrado si falta algo o no coincide.
4. **Instrumentación en `harness.run_case`** (`harness.py:598-629`): persistir `research_sources`,
   `alcance_lectura`, `state["documents"]`, la lista de fragmentos que entraron, el hash del SOUL y
   la versión del CLI.
5. **Contabilidad de intentos fallidos** (`spend_guard.py:1113-1125`): registrar los tokens de
   entrada estimados, la cota de salida y `consumo_conocido = false` en vez de 0. Es un cambio de
   telemetría del eval, no del producto. Va también al parche de 0.3.3.
6. **Runner de producción:** `execution/run_banco04.py`. Incluye la guarda de aislamiento, la
   política fija, el despacho efímero, la persistencia idempotente, la clasificación de fallos, la
   submuestra de aprobaciones, la tanda piloto, el **contador acumulado contra el techo con reserva
   del juicio** y la suspensión.
7. **Segmentación del banco:** `backend/mia/eval/banco04/segmentos.py`. Parte por línea, por celda y
   por oración, sin exclusiones por forma.
8. **Ceguera:** `backend/mia/eval/banco04/ceguera.py`. Retira los rastros, separa el aviso de alcance
   como contexto, genera los HMAC y baraja.
9. **Jueces:** `backend/mia/eval/banco04/jueces.py` y `prompts/`. Opus y Codex con invocación
   limpia, dos pasadas, esquemas, validador con evidencia por estado y reglas anti-evasión,
   reintento, adjudicación simétrica de tres votos, detección de discordancias, kappa y estabilidad.
10. **Métricas y veredicto:** `backend/mia/eval/banco04/metricas.py`. Cubre §5, §6.1, el bootstrap
    por casos de §6.2, el techo en tres niveles de §6.3, la matriz de §7.2, las cotas de §3.3 y el
    veredicto «aprueba / reprueba / no certificable».
11. **Validación de jueces:** `execution/banco04_validar_jueces.py`, con el conjunto de ajuste y el
    reservado de un solo uso (§8.6).
12. **Paquete de calibración:** `execution/banco04_calibracion.py`.
13. **Gates con mutación hecha por un tercero:** `execution/test_banco04_*.py`. Cubren:
    - **cambiar la puntuación o convertir una oración en título, viñeta o celda no reduce las
      afirmaciones juzgadas** ni oculta un `sin_respaldo` (P1);
    - un hecho mal expresado con su marcador intacto no cuenta como cubierto (P2);
    - una laguna declarada sobre algo que consta en lo leído es omisión y negativa falsa (P3);
    - un defecto que solo detecta Codex llega a adjudicación; una discordancia sin resolver o un
      kappa < 0,6 suspenden el veredicto (P4);
    - el validador rechaza listas vacías, `no_afirmativa` sobre un segmento con cifra o ancla,
      `inferencia_valida` sin premisas o con una premisa sin respaldo, `dicho_abogado_fiel` sin
      pasaje en el mensaje, y `con_respaldo_sin_localizador` sin pasaje (P5);
    - el cargador de custodia falla cerrado con un hash alterado o una carpeta ausente, y ningún
      archivo de custodia aparece bajo el repositorio (P6);
    - el reporte nunca emite «equivalente» y aplica la tabla de veredictos de §6.2 (P7);
    - la matriz de §7.2 clasifica bien sus 24 celdas, incluido un decisivo en el 4 % no leído con
      alcance de 0,96 (P8);
    - los ejemplos {100 ×4, 10 000 ×3} y {100, 100, 100, 10 000, 10 000} reprueban el techo aunque
      la mediana no cambie (P9);
    - **alineación:** una división de Codex produce la unidad común esperada; un defecto que solo
      marca Codex sobre una unidad dividida llega a adjudicación; `localizador_falso` cuenta como
      defecto en el kappa; ambos asignan la misma clase: indefinido, sin acreditar ≥0,6; rige la
      validación reservada. Uno marca diez defectos y el otro ninguno: kappa = 0 y suspensión (N2);
    - **cobertura por tramos:** quitar la cláusula «y ganó» de todo átomo, o meterla en una
      exclusión, hace rechazar la salida; un átomo compuesto sin justificación se rechaza (N1);
    - una unidad con k < 4 casos nunca emite `mejora` ni `sin_regresion_observada` (N3);
    - `no_aplica` sobre un átomo con cifra o ancla se rechaza, y los `no_aplica` válidos salen de
      los denominadores (N4);
    - si la mayoría descarta más del 20 % de los defectos vistos solo por Codex, o la sensibilidad
      final del circuito es menor que 0,95, el circuito no se usa (N5);
    - la llave de la custodia está protegida con DPAPI y no aparece bajo el repositorio (P6);
    - un intento fallido sin cota hace el techo no certificable (P10);
    - el contador alcanza el techo, suspende y publica «incompleto — no certificable» (P11);
    - el runner rechaza el puerto 55432 y el `.env` del repo.

    Lo que cuenta como resultado es el número de mutaciones que sobreviven.
14. **Plantilla de resultados:** `docs/banco-calidad-04-resultados.md`, creada vacía antes de
    correr.

---

## 11 · Decisiones

**Tomadas por Pipe el 2026-10-11:**

1. **Banco completo:** unas 100 corridas por versión, ≈ 13 M tokens ahora y ≈ 18-26 M al final,
   12-19 h por versión (§3).
2. **Por debajo de 0,95 de lectura, o con una pieza sin leer:** diagnóstico limitado expreso en el
   propio texto: lo que encontró, qué no leyó, y que no es definitivo (§7.1).
3. **Techo de cuota:** hasta +25 % frente a 0.3.3 por consulta, y la segunda IA (Codex, 5C) como
   máximo el 50 % de lo que gasta Claude. Por P9, se aplica al consumo real agregado (total y por
   caso) y a los extremos entre repeticiones; la mediana y el p50 son solo descriptivos (§6.3).
4. **Circuito completo con doble juez:** Bloque 0, ≈ 18 M Claude y ≈ 5 M Codex; Bloque 7, ≈ 22-31 M
   Claude (techo de 32 M) y ≈ 7-8 M Codex (techo de 8 M) (§3.2, §3.4).

**Tomadas por el director:**

- **Política del banco:** `quality_adaptive`, como corrección técnica del plan (§9.1).
- **Custodia:** llave protegida con DPAPI fuera del repositorio, sin frase de paso de Pipe, con el
  límite «mismo usuario de Windows» declarado (§2.3).
- **Estrato A-voluminoso de un solo caso:** se reporta sin inferencia, en lugar de ampliarlo (§6.2).

**Pendiente de Pipe (opcional):**

5. **Calibración humana:** si revisa a ciegas unas 10 salidas, y cuándo. Sin ella, todo se rotula
   «evaluación automática».

---

## 12 · Cambios tras la revisión de Astra (P1-P12)

### 12.1 Ronda 1 (v1.1)

Las evidencias citadas se comprobaron en la fuente antes de aceptar cada objeción. Las doce se
aceptan; ninguna evidencia resultó falsa. En las filas P4 a P9 y P11, lo que se cambió después en
la v1.2 queda indicado en §12.2.

| Objeción | Veredicto | Dónde |
|---|---|---|
| **P1** | Aceptada. `verification.py:535-538` confirma que un texto de 120 caracteres o menos sin puntuación final es «título». Se juzgan títulos, viñetas y celdas; `_is_header` no excluye nada; hay mutación de puntuación y formato. | §4.2; §8.4 (`no_afirmativa` evasiva); §8.6; §10.2.7 y .13 |
| **P2** | Aceptada. `scoring.py:671-672` confirma que solo busca subcadenas normalizadas. La cobertura exige expresión y atribución correctas; el marcador es señal auxiliar. | §5.2; §8.5; §10.2.13 |
| **P3** | Aceptada. Hay mínimos absolutos de cobertura, omisión, utilidad y proxy por estrato, y una laguna declarada sobre lo que consta es omisión y negativa falsa. | §4.3; §5.3; §5.4; §6.1 |
| **P4** | Aceptada. Cribado doble Opus–Codex sobre el 100 %, adjudicación simétrica de tres votos, suspensión por discordancia sin resolver o kappa < 0,6, y validación sobre mutaciones reservadas y custodiadas. | §8.2; §8.5; §8.6; §6.1 |
| **P5** | Aceptada. Evidencia obligatoria por estado, premisas en las inferencias, lista no vacía, cobertura atómica (el 80 % léxico de la v1.1 lo sustituye la cobertura por tramos de la v1.2, N1) y pruebas de clasificaciones evasivas. | §4.3; §8.4; §10.2.13 |
| **P6** | Aceptada. `holdout.py:251-252` confirma que es una «barrera de INTENCIÓN». Casos, claves, mutaciones reservadas, semilla y llave van cifrados fuera del repo, con solo hashes en el repo. Se declara la limitación del holdout pequeño existente y la de un solo usuario de Windows. | §2.1; §2.3; §9.2; §10.2.2-3 |
| **P7** | Aceptada. 1 − 0,05^(1/5) ≈ 0,45, como afirma Astra. Se delimitan la población (17 casos fijos) y la dependencia, se dan cotas por caso y por estrato, bootstrap por casos, y se prohíbe declarar equivalencia. | §1; §3.3; §6.2 |
| **P8** | Aceptada. La matriz pasa a 18 combinaciones (2 × 3 × 3), con su efecto en la aprobación. | §7.2 |
| **P9** | Aceptada. Mediana de {100 ×4, 10 000 ×3} = 100 y total ×43 frente a 700, como afirma Astra. El techo se aplica al total ponderado, a la mediana de estrato y a los extremos por caso, también para Codex. | §6.3; §10.2.13 |
| **P10** | Aceptada. `spend_guard.py:1122-1125` registra 0 tokens ante una excepción y `provider_benchmark.py:205-206` lee solo llamadas exitosas. Se registra el consumo desconocido con cota conservadora, y sin cota el techo no es certificable. | §5.5; §9.4; §10.2.5 |
| **P11** | Aceptada. Presupuesto del circuito completo, techo efectivo con reserva del juicio, suspensión, y prohibición de certificar resultados incompletos. Pipe autorizó el circuito el 2026-10-11 (decisión 4). | §3.2; §3.4; §6.4; §11 |
| **P12** | Aceptada como decisión del director: `quality_adaptive`, registrada como corrección técnica del plan, no como default provisional. | §9.1; §11 |

### 12.2 Ronda 2 (v1.2): parciales y nuevas

Astra dio por resueltas P1, P2, P3, P5, P6, P10, P11 y P12. Antes de aceptar, cada evidencia de
esta ronda se comprobó contra el texto de la v1.1:

- la v1.1 dejaba que cada juez creara sus átomos y luego los comparaba como si coincidieran;
- la frase de paso de §2.3 contradecía la decisión de custodia;
- las cotas decían «95 % de confianza»;
- la fila «suficiente / limitada / incompleta» chocaba con la disponibilidad real del hecho;
- los techos usaban p50 (con {100, 100, 100, 10 000, 10 000} la mediana sigue en 100 y el total
  sube ×40,6);
- había un umbral léxico del 80 %;
- A-voluminoso tenía k = 1;
- no existía un estado para lo no afirmativo;
- la validación medía la detección, no la decisión final.

**Ninguna evidencia resultó falsa; todas se aceptan.**

| Objeción | Veredicto | Dónde |
|---|---|---|
| **P4 / N2** (alineación y kappa) | Aceptada. Codex clasifica los átomos de Opus y solo puede dividirlos. La unidad común es la intersección determinista de las dos particiones. El defecto incluye `sin_respaldo` y `localizador_falso`. El kappa se exige en el conjunto reservado y, en las salidas reales, «indefinido (clase única)» o «inestable (n < 10)» **no cuentan como ≥ 0,6**. | §4.2.2-3; §8.2; §8.5; §6.1 |
| **P6** (custodia) | Aceptada. Llave protegida con DPAPI fuera del repositorio, sin frase de paso de Pipe (decisión del director). Límite «mismo usuario de Windows» declarado: DPAPI no protege frente a procesos de ese usuario, y los hashes delatan alteraciones, no lecturas. | §2.3; §11 |
| **P7** (lenguaje estadístico) | Aceptada. Se retira «95 % de confianza». Las cotas binomiales pasan a ser ilustraciones condicionadas a una independencia que no se cumple. Se prohíbe publicar niveles de confianza y la cifra 3/N. | §1.1; §3.1; §3.3 |
| **P8** (disponibilidad) | Aceptada. Disponibilidad efectiva por hecho decisivo (su fragmento entró o no al prompt). Matriz de 24 celdas con C1-C4. `abstencion_injustificada` exige alcance suficiente y C1, y la limitación con un decisivo no disponible deja de penalizarse. | §5.3; §7.2 |
| **P9** (techo) | Aceptada. El techo se aplica a sumas (total agregado, total ponderado por caso, por caso) y al extremo entre repeticiones. El p50 queda descriptivo. | §5.5; §6.3 |
| **N1** (umbral léxico) | Aceptada. Átomos como tramos con posiciones, que cubren el 100 % de los caracteres no blancos. Exclusiones de lista cerrada y auditables, rechazo de átomos compuestos, y mutaciones reservadas con cláusulas falsas breves (menos del 20 %, al menos 10 casos), con sensibilidad propia de al menos 0,90. | §4.2.2; §8.4; §8.6; §10.2.13 |
| **N3** (estrato de un caso) | Aceptada. Bootstrap solo con k ≥ 4 (A-pequeños, k = 9, y C-voluminosos, k = 4, este último «orientativo»). A-voluminoso y C-pequeños van por corrida, sin inferencia: solo `regresion` o `descriptivo_sin_inferencia`. Se decidió no ampliar el estrato. | §6.2; §11 |
| **N4** (estado no afirmativo) | Aceptada. Estado `no_aplica`, solo para tipo `no_afirmativa`, con justificación enumerada, restricciones anti-evasión, exclusión de los denominadores y posibilidad de impugnación por Codex. | §4.2.4; §4.3; §8.4 |
| **N5** (decisión final) | Aceptada. Se valida el circuito completo (cribado, alineación y adjudicación) sobre las mutaciones reservadas: sensibilidad final de al menos 0,95 y falsos positivos de 0,10 o menos. Si la mayoría descarta más del 20 % de los defectos vistos solo por Codex, el circuito no se usa. | §8.6; §6.1 |
| **Registro** | La autorización de Pipe del circuito completo con doble juez (Bloque 0: ≈ 18 M Claude y ≈ 5 M Codex; Bloque 7: ≈ 22-31 M Claude con techo de 32 M y ≈ 7-8 M Codex con techo de 8 M) queda registrada como decisión 4. | §3.2; §11 |

**Sin pendientes de Pipe derivados de esta ronda.** Solo sigue opcional la calibración humana
(§11.5).

### 12.3 Ronda 3 de Codex Astra y congelamiento

Astra emitió APTO CON CAMBIOS en la ronda 3 (2026-10-11), condicionado a dos correcciones literales
sobre el kappa con clase única (N2): §8.5 y la prueba de §10.2.13. El director las aplicó textualmente.
Con ellas, **banco04-v1.2 queda congelado**. Cualquier cambio posterior abre una versión nueva con su
propia revisión, antes de correr el banco, nunca después.

### 12.4 Aclaraciones de interpretación durante la implementación (2026-10-12)

No cambian umbrales, muestra ni métricas; fijan la lectura del texto congelado donde era ambiguo.
Las decide el director y quedan sujetas a la revisión de Astra sobre el código.

- **C2.** `pasaje_contradictorio.fuente` admite también `expediente:<pieza_id>` para las piezas no
  leídas.
- **C3.** Si tras el reintento solo quedan errores de pasaje, manda la regla específica: esos átomos
  pasan a presunto `sin_respaldo` y la presunción se propaga a las inferencias que dependen de ellos.
  Cualquier error estructural deja la salida no evaluada.
- **C3-bis.** La negativa falsa que solo detecta la pasada 2 se resuelve por ubicación y voto ciego.
- **C4.** Tres estados distintos con al menos un defecto cuentan como discordancia. En cualquier otro
  caso decide la mayoría binaria (defecto / no defecto).
- **C5.** Un átomo sale del kappa solo si los dos jueces lo marcaron `no_aplica`.
- **C6.** En las celdas de §7.2 sin efecto declarado sobre el proxy se aplica el efecto de la celda
  homóloga, con la marca `proxy_inferido`.
- **C7.** Un punto está disponible si entraron todos sus fragmentos, o todos sus hechos cuando no
  lista fragmentos. Una laguna real siempre cuenta como disponible.
- **C9.** Sin lista de partes, se rechazan los nombres propios que el material escribe con mayúscula
  a mitad de frase. La lista cerrada de exclusiones se completa con ordinales y rótulos procesales
  (`protocolo.ROLES_Y_ROTULOS`).
- **C10.** Un átomo es compuesto según la heurística versionada en `protocolo.py`; para declararlo
  una sola proposición se usa el prefijo `UNA_PROPOSICION:`.
- **C11.** El evaluador usa una copia congelada de las funciones de segmentación de
  `agents/verification.py` en 7b9aaa0 (`eval/banco04/evaluador_congelado.py`), para que los Bloques 0
  y 7 sigan siendo comparables.
- **C13 (REVOCADA el 2026-10-12 por I7 de Astra; ver §12.5).** La primera lectura excluía del
  material la configuración de jurisdicción. Era errónea: tener pasaje no prueba que la norma sea
  aplicable al ordenamiento configurado.
- **C14.** Los esquemas de la pasada 2, del tercer voto y del voto de cobertura los fija el código.
- **C15.** Precedencia de veredictos: `no_certificable` > `reprueba` > `aprueba`.
- **C16.** La regla de cifras de P5 se aplica por átomo.
- **C8 y C12 quedan abiertas.**
  - C8: el alcance se mide con la lista real de fragmentos que entraron al prompt.
  - C12: si la tanda piloto muestra que la reserva del juicio no alcanza, se lleva a Pipe antes de la
    línea base.
- **C17 (reserva del juicio del Bloque 7).** Se reservan unos 13 M de cuota Claude y 6 M de Codex,
  derivados de las partidas del Bloque 7 en §3.2. En Codex la reserva no es «total», como sí lo es en el
  Bloque 0, porque 0.4 usa Codex en producción (revisión 5C encendida por defecto).

### 12.5 Versión banco04-v1.3 (2026-10-12): jurisdicción en el material del juez

Motivo: la objeción I7 de Astra a la implementación. Una norma puede tener pasaje en el corpus y
aun así pertenecer a un ordenamiento que el despacho no tiene configurado. Sin conocer esa
configuración, el juez no puede medir la fuga de §5.7.

Cambio único: el material del juez de §8.2 incluye las **jurisdicciones configuradas del despacho**
como contexto permitido, tanto en la validación de los jueces (§8.6) como en la medición real. La
norma respaldada pero no habilitada cuenta como `fuga`. No cambian ni la muestra, ni las
repeticiones, ni las métricas, ni los umbrales, ni los techos. La versión se fija antes de cualquier
corrida; v1.2 no llegó a ejecutarse.

Versión de la custodia: el formato y los artefactos custodiados siguen en `banco04-v1.2`
(`protocolo.PROTOCOLO_CUSTODIA`), con su AAD ligada a esa versión. La v1.3 no cambia ningún artefacto
custodiado, así que la versión del protocolo (`VERSION_PROTOCOLO`) y la de la custodia se versionan por
separado.
