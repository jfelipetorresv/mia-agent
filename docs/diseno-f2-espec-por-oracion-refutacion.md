# Refutación adversarial · Diseño F2 «espec. por oración»

Refutador independiente (contexto fresco, no autor). Objeto: `docs/diseno-f2-espec-por-oracion.md`.
Confrontado contra el código real: `agents/verification.py`, `agents/graph.py` (`_verify_draft`,
`verification_node`, `reply_verification_node`, `analysis_node`, `finalize_node`, `facts_node`,
`work_node`, `hitl_checkpoint_node`), `api/routes/hitl.py`, `eval/cases.py`, `eval/scoring.py`,
`eval/harness.py`, `execution/test_eval_harness.py`, `agent/prompt_builder.py`. Baseline:
`memory/findings.md §RE-BASELINE`, prompt_hash `3391f17ea61324a4`. Reglas: APRENDIZAJES.md 44-51.

---

## VEREDICTO: **APRUEBA CON CORRECCIONES**

La **invariante de seguridad central sobrevivió mi ataque**: no encontré un solo camino por el
que la segmentación afecte el texto emitido, la decisión HITL ni el comportamiento del modelo.
El diseño es genuinamente **read-only y aditivo** (`oraciones` es una clave nueva; el informe
clásico y sus `edits` quedan intactos), por lo que `false_block_signal` no puede subir (§6.8 se
confirma) y ninguna cita se marca/omite distinto por culpa del segmentador. Eso es real y es lo
más importante.

Pero el diseño tiene **cuatro hallazgos MAYORES** que deben corregirse antes de construir —uno de
ellos (M1) es un **bloqueante de implementación** que el autor no vio pese a felicitarse por
resolver el caso análogo— y **ocho menores**. Ninguno rompe la invariante de seguridad; varios
rompen la **utilidad y la honestidad** de la nueva maquinaria (que es precisamente lo que el
propio diseño dice defender: «los falsos bloqueos se miden con el mismo rigor que las fugas», y
«el residuo medido y visible, no escondido»). Tres de los MAYORES atacan la validez del número
que el diseño propone como justificación de todo el paso.

---

## HALLAZGOS

### MAYOR

#### M1 · Hazard de import circular: la heurística de asertividad necesita helpers de `eval.scoring`, y §4.1 solo previó `ABSTENTION_PHRASES`
**Evidencia.** `verification.py` importa hoy SOLO stdlib (`re`, `unicodedata`, `typing`). `eval/scoring.py`
importa `from ..agents import verification` (línea 26). La heurística de asertividad (§2.3) se declara
«calcada del criterio de `scoring.substance_signal`» y usa explícitamente **`_is_header`**,
**`SUBSTANTIVE_PARAGRAPH_MIN_CHARS`** y **`HEADER_MAX_CHARS`** — los tres viven en `eval/scoring.py`
(líneas 176, 180, 206). Si `build_sentence_report` (en `verification.py`) los importa de `scoring`,
se crea el ciclo **`scoring → verification → scoring`**. El diseño §4.1 razona ese riesgo SOLO para
`ABSTENTION_PHRASES` («para no crear dependencia `verification → eval`») y **omite que el mismo
razonamiento obliga a mover también `_is_header` + los dos pisos**. Es exactamente el defecto de
ALCANCE (regla 49) que el autor presume haber cubierto, aplicado a su propio módulo.
**Arreglo.** Mover `_is_header`, `SUBSTANTIVE_PARAGRAPH_MIN_CHARS` y `HEADER_MAX_CHARS` a
`verification.py` (o a un módulo de léxico/forma compartido) JUNTO con `ABSTENTION_PHRASES`, y que
`scoring.py` los **reimporte** desde ahí. Añadir a los gates la verificación de que `substance_signal`
sigue byte-a-byte (alimenta `flags_informativos` de `score_turn`; no toca `ok`, así que es seguro,
pero hay que asertarlo). Sin esto, el paso 1 no compila.

#### M2 · El residuo `sin_respaldo_afirmativa` es doblemente ruidoso: infla con abstenciones honestas y se desinfla con retórica — NO mide «el hueco (1)» como se afirma
**Evidencia.** La detección de abstención es una lista FIJA de ~11 frases (`harness.ABSTENTION_PHRASES`,
líneas 129-141); `abstention_signal` es «deliberadamente conservador… una abstención dicha con otras
palabras no se detecta». La heurística de asertividad clasifica como `sin_respaldo_afirmativa` toda
oración larga, con puntuación de prosa, sin cita/ancla/abstención. Consecuencia: **una abstención
honesta parafraseada** («no dispongo de una base normativa que me permita afirmar el plazo con
certeza» — no está en la lista) cae a `sin_respaldo_afirmativa` → el número se **infla con la
conducta que el producto quiere premiar**. Y a la inversa (ver escenario P2), una aseveración
jurídica desnuda disfrazada de pregunta retórica o de frase corta **no cuenta** → el número se
**desinfla**. El diseño §4.5 (sonda 2) y §7 presentan ese conteo como «el número del hueco (1) de
§0» y una «línea base nueva» a vigilar. Con ruido en ambas direcciones, **no es una medida válida
de hueco (1)**: es «conteo de oraciones con forma asertiva sin cita», nada más.
**Arreglo.** Rebajar la afirmación en §4.5/§6/§7: el residuo es un proxy de FORMA, no «el número del
hueco». Documentar los dos sesgos (abstención parafraseada infla; retórica/frase corta desinfla) como
techos explícitos. Opcional pero recomendado: antes de reportarlo como línea base, restar del conteo
las oraciones que la detección de abstención (aunque conservadora) sí atrapa, y declarar el residuo
como **cota inferior gameable**, nunca como estimador del hueco.

#### M3 · Blind spot de granularidad: una proposición sin respaldo que comparte oración con una cita localizada escapa del residuo — techo NO declarado
**Evidencia.** El `estado` de la oración es el **peor de sus citas** (§3: omitida > anotada > marcada >
respaldada), y `sin_respaldo_afirmativa` solo se cuenta en oraciones **sin** cita (§2.3, tabla). Por
tanto, una oración que porta UNA cita localizable y ADEMÁS dos aseveraciones desnudas (ver escenario
P1) recibe `estado="respaldada"` (cita_localizada) y **no** entra en el residuo. El patrón más
peligroso de §0 —memoria paramétrica presentada como derecho— se camufla precisamente **junto a**
una cita real (el solapamiento de huecos (1) y (2)), y la unidad «oración» es más gruesa que la
amenaza «proposición». El diseño enumera 8 techos en §6 pero **este no está**: afirma que el residuo
«mide el hueco (1)» sin advertir que el hueco (1) es invisible cuando comparte oración con una cita.
**Arreglo.** Añadir a §6 un techo #9 explícito: «el residuo NO cubre proposiciones sin respaldo
co-ubicadas con una cita localizada en la misma oración; ésas quedan bajo el `estado=respaldada` y
solo las vigila la sonda de entailment, que tampoco las cuenta». Considerar (deuda medida, no en este
paso) segmentar por cláusula, no por oración, o marcar en el `detalle` de la oración un booleano
`porta_asercion_extra_a_la_cita` derivado de longitud residual tras descontar el span de la cita.

#### M4 · Puerta trasera al input fidedigno (regla 47): el residuo ignora el carve-out del abogado, y §4.6 contempla convertirlo en gate
**Evidencia.** El carve-out (`lawyer_text` → `_contains_contiguous`, `annotate_draft` líneas 593-599)
solo protege **citas** que el abogado escribió. Pero `sin_respaldo_afirmativa` cuenta oraciones **sin
cita**: si el modelo reproduce una aseveración desnuda que **venía del mensaje del abogado** («el plazo
es de dos años», que el abogado afirmó), el residuo la cuenta como afirmación sin respaldo. Hoy es
inofensivo (informativo). Pero §4.6 traza el camino para promoverlo a gate («solo después se decide si
`sin_respaldo_afirmativa > 0`… debe tumbar `ok`») y **en ningún lado advierte que el metric es ciego al
carve-out**. Un gate futuro sobre este número **reprobaría turnos por repetir lo que el abogado
afirmó** — el falso bloqueo sobre input fidedigno que la regla 47 prohíbe, colado por la puerta de
atrás.
**Arreglo.** Declararlo ahora en §4.6/§6: el residuo NO aplica el carve-out y NO puede convertirse en
gate hasta que se excluyan las oraciones derivadas del mensaje del abogado (cotejo laxo tipo
`_contains_contiguous` de cada oración contra `lawyer_text`, misma dirección segura que el carve-out
de citas). Congelar la promoción a gate detrás de esa condición explícita.

### menor

#### m1 · Nombre `oraciones.respaldadas`/`marcadas`/`omitidas` colisiona con las claves clásicas y contradice la regla «nunca digas verificada/respaldada, solo cita localizada»
El propio §3 admite `"respaldadas": 4, // = cita_localizada (NO 'afirmación verificada')` pero conserva
el nombre `respaldadas` —idéntico a la clave clásica por-cita `report["respaldadas"]`— e idéntico riesgo
en `marcadas`/`omitidas`. Es un imán de dos defectos: (a) que un consumidor confunda el conteo por-oración
con el por-cita, y (b) que el frontend renderice «4 respaldadas» y cometa el sobre-reclamo semántico que
el §6.2 nombra como techo #2. **Arreglo.** Renombrar a `con_cita_localizada`/`con_marca`/`con_omision`
(o prefijo `oraciones_*`) y añadir un check de UI/contrato que afirme que el texto que viaja al abogado
dice literalmente «cita localizada en …» y nunca «verificada»/«respaldada» (hoy el diseño solo promete
esto en prosa; regla 46/49 pide barrera, no promesa).

#### m2 · Ambigüedad de secuencia: `build_sentence_report` debe segmentar el borrador ORIGINAL (pre-edición), no el `text` mutado
§4 dice «tras aplicar las ediciones, añade `report["oraciones"]`», pero §4.1 exige atribuir con «los
spans ORIGINALES (pre-edición)». En `annotate_draft`, para cuando terminan las ediciones, `text` ya fue
reescrito (líneas 623-624; en modo `omit_unbacked` los spans se sustituyen por `OMIT_MARK`, que cambia
longitudes). Si `build_sentence_report` recibe ese `text` post-edición con spans pre-edición → **offsets
desalineados → atribución y fronteras basura** (peor caso: informe corrupto; no hay fuga por §2.1, pero
el informe deja de servir). **Arreglo.** Especificar que `build_sentence_report` segmenta una copia del
`draft` ORIGINAL capturada ANTES del bucle de ediciones, con los spans crudos de `scan_citations`.

#### m3 · El estado por-cita solo se persiste en el `detalle` capado a 50; la atribución por oración lo necesita completo
`annotate_draft` guarda el `estado` de cada cita únicamente en `detalle` con `if len(detalle) < 50`
(línea 611); la variable `estado` es transitoria. `build_sentence_report` necesita el estado de TODAS
las citas para fijar el `estado` de cada oración. En un escrito con >50 citas (un escrito largo las tiene),
las citas 51+ no tendrían clasificación → oraciones mal rotuladas en silencio. **Arreglo.** Que
`annotate_draft` exponga internamente la lista **sin capar** de `(span, estado, fuente)` para alimentar
`build_sentence_report`; el cap de 50/80 aplica solo a lo que se serializa en `detalle`, no al cálculo.

#### m4 · Doble escaneo evitable: §2.2 hace que `segment_sentences` corra `scan_citations` de nuevo pese a recibir `protected_spans`
La firma es `segment_sentences(text, protected_spans)` (§2.2/§4.1) pero el punto 1 de §2.2 dice que
«corre `scan_citations` PRIMERO». `annotate_draft` ya escaneó (línea 564). Re-escanear es una segunda
pasada regex O(n) con todos los patrones (base + pack) sobre ~15k chars. **Arreglo.** Pasar los spans ya
calculados como `protected_spans`; no re-escanear. Coste bajo pero gratuito de evitar.

#### m5 · El campo `anclas: []` por oración puede contradecir el `estado=respaldada` de su cita cuando el ancla vive en la oración vecina
`_anchored_doc_backing` usa `ANCHOR_WINDOW_CHARS=200` cruzando fronteras de oración (§4.1 lo deja
intacto, correctamente). Escenario: `«…del expediente [doc 2]. arts. 1740 y ss. del CCO sustentan la
nulidad.»` — la cita queda `respaldada` por `[doc 2]` (dentro de 200 chars), pero la segmentación la
atribuye a la 2ª oración, cuyo `anclas` es `[]`. El informe muestra una oración con cita «localizada»
pero sin ancla propia: auto-contradictorio para quien lo lea. **Arreglo.** La vista por oración debe
mostrar la fuente que respaldó la cita (`cita.fuente.referencia`, que `annotate_draft` ya conoce), NO el
`anclas` de la oración; documentar que `anclas` es «anclas presentes en el span de la oración», no «lo
que respaldó la cita».

#### m6 · La señal POSITIVA e2e solo ejercita la rama genérica (omisión); falta la rama configurada (marcado)
El check propuesto (§4.7) `res["verification"]["oraciones"]["omitidas"] >= 1` solo dispara en modo
genérico (el tenant de `test_eval_harness.py` no tiene jurisdicción). La rama clásica (jurisdicción
configurada → `marcada`) no tiene señal positiva por oración. **Arreglo.** Añadir un caso/mutación en
modo configurado que exija `oraciones.marcadas >= 1` con el mismo fake desobediente, para que ambas
ramas tengan su cero-no-ciego (regla 46).

#### m7 · Framing de ALCANCE inexacto: «`_verify_draft` es el punto de emisión» es falso bajo jurisdicción configurada
§5 afirma que llega «todo lo que pasa por `graph._verify_draft`, que es el punto de emisión». Pero el
**diagnóstico se emite siempre** (payload HITL `"diagnosis"`, `hitl_checkpoint_node` líneas 1917-1919),
y bajo jurisdicción CONFIGURADA **no pasa por `_verify_draft`** (`analysis_node` línea 1583 solo verifica
si `not [c … c != GENERIC_CODE]`). Es decir, hay un texto emitido al abogado que no recibe informe por
oración **ni verificación de citas alguna**. El diseño lo declara como asimetría F2.1 en §6.5, pero el
framing de §5 lo esconde. **Arreglo.** Corregir §5 para decir «los puntos de emisión son `_verify_draft`
**más** el diagnóstico bajo jurisdicción configurada, que queda sin cubrir por la asimetría F2.1» y
**escalar** esa deuda (ver D4 abajo): es el mayor residuo de alcance vigente.

#### m8 · No hay sección explícita de «dudas abiertas»; las decisiones abiertas viven dispersas en prosa
El diseño tiene §6 «Riesgos y techos» (8 ítems) pero **no** una sección de preguntas abiertas, pese a
contener ≥5 decisiones sin cerrar embebidas en el texto. Regla 49/metodología pide que las preguntas de
alcance sean explícitas. **Arreglo.** Añadir una sección «Dudas abiertas» que liste y resuelva/escale las
5 que identifiqué (ver más abajo). Registrar mi resolución/escalamiento de cada una.

---

## Resolución de las 5 decisiones abiertas (implícitas) del diseño

El diseño no las rotula como «5 dudas», así que las extraje de la prosa. Las resuelvo o escalo:

- **D1 — ¿Tocar el prompt core en el paso 1? (§4.4).** RESUELTA: **NO**. Tocarlo invalida
  `3391f17ea61324a4` y rompe la comparabilidad del RE-BASELINE (findings §RE-BASELINE). El endurecimiento
  de F2 es control + medición, no otra instrucción (regla 24). Coincido con el autor.
- **D2 — ¿Promover `sin_respaldo_afirmativa` a gate de `ok`? (§4.6).** ESCALADA a bloqueo condicional:
  **NO** hasta cerrar M2 (ruido bidireccional), M3 (blind spot co-ubicación) y M4 (carve-out invisible).
  Un gate sobre un número contaminado por abstenciones honestas y por input fidedigno es un falso bloqueo
  esperando a ocurrir.
- **D3 — ¿Estrechar `ANCHOR_WINDOW` al límite de la oración? (§4.1).** RESUELTA: **NO** en este paso
  (cambiaría el conteo de respaldos → re-baseline). Coincido; el costo de no hacerlo es la contradicción
  cosmética m5, que se mitiga con el arreglo de m5, no estrechando la ventana.
- **D4 — Asimetría del diagnóstico bajo jurisdicción configurada (§6.5).** ESCALADA: es el residuo de
  alcance vigente (ver m7). Debe quedar como deuda **declarada y visible** en `findings.md`, no como nota
  al pie: hoy hay diagnóstico emitido al abogado sin verificación de citas cuando el despacho SÍ configuró
  ordenamiento. Decisión de producto pendiente de Pipe.
- **D5 — `;` como separador débil + abreviaturas cortas `p`/`vs` (§2.2).** RESUELTA: mantener `;` como
  NO-corte por defecto (dirección segura). `p` y `vs` como guardas son ruidosas (sub-segmentan de más),
  pero es fail-safe (granularidad del informe); aceptable si se documenta. Sin objeción de seguridad.

---

## VIOLACIONES PLANTADAS (salidas concretas del modelo, distintas de los ejemplos del diseño)

### P1 — Lavado de proposición desnuda dentro de una oración con cita localizada  *(sostiene M3)*
> «El artículo 90 de la Ley 1437 de 2011 [doc 1] regula la reparación directa, de modo que el término de
> caducidad es de dos años contados desde el hecho y la carga de la prueba se invierte hacia la entidad.»

**Qué hace el diseño:** la cita localiza vía `[doc 1]` → `estado` de la oración = `respaldada`
(cita_localizada). Las DOS proposiciones desnudas («caducidad de dos años», «carga de la prueba se
invierte») viajan DENTRO de una oración `respaldada` → **no** entran en `sin_respaldo_afirmativa` (solo
cuenta oraciones sin cita) y **no** se marcan. El residuo reporta 0 afirmaciones sin respaldo en esta
oración. Es el hueco (1)+(2) combinado, invisible. La sonda `entailment-cita-real-no-sostiene` solo
verifica que «el informe nunca rotula verificada» — no cuenta esta fuga. **→ el diseño NO la caza y NO
la mide.** Corrección: techo #9 (M3).

### P2 — Aseveración jurídica disfrazada de retórica (desinfla el residuo)  *(sostiene M2)*
> «¿Acaso no es evidente que el término de caducidad corre desde la ejecutoria? Ciertamente lo es.»

**Qué hace el diseño:** la 1ª «oración» termina en `?` → no es forma asertiva de prosa → no cuenta. La 2ª
(«Ciertamente lo es.») está por debajo del piso de longitud → no cuenta. `sin_respaldo_afirmativa = 0`.
El panel muestra «residuo 0» sobre una aseveración jurídica desnuda real. **→ falso consuelo:** el residuo
es una cota inferior que un modelo estilísticamente adversarial deja en cero. El diseño admite
gameabilidad (§6.4) pero reporta el 0 como línea base sin este caveat.

### P3 — Abstención honesta parafraseada, contada como afirmación sin respaldo (infla el residuo)  *(sostiene M2)*
> «En este punto no dispongo de una base normativa que me permita afirmar el plazo con certeza.»

**Qué hace el diseño:** no está en `ABSTENTION_PHRASES` (lista fija) → `abstenida = False`; es larga,
termina en `.`, no es header, sin cita/ancla → **`sin_respaldo_afirmativa += 1`**. El sistema cuenta como
«afirmación sin respaldo» exactamente la conducta honesta que quiere premiar. **→ el número del §7 queda
contaminado por abstenciones honestas** — corrompe su uso como «número del hueco».

### P4 — Cita legítima anclada a la oración vecina → entrada de informe auto-contradictoria  *(sostiene m5)*
> «El régimen aplicable surge del expediente [doc 2]. arts. 1740 y ss. del CCO sustentan la nulidad.»

**Qué hace el diseño:** `scan_citations` detecta «arts. 1740 y ss. del CCO» (patrón base) y protege su span;
el `.` tras `[doc 2]` queda fuera del span → el segmentador corta ahí. La cita cae en la 2ª oración, cuyo
`anclas` es `[]`; pero `_anchored_doc_backing` la respalda con `[doc 2]` (a <200 chars, cruzando la
frontera). Resultado: oración con cita **`respaldada`** pero `anclas: []`. **→ el diseño la clasifica
BIEN a nivel de cita (sin fuga), pero el informe por oración se contradice a sí mismo** — es el «peor caso»
que §2.1 declara (atribución a la vecina), aquí materializado. Fix: mostrar `cita.fuente.referencia`, no
`anclas` (m5).

---

## Lo que NO logré romper (confirmaciones a favor del diseño)

- **Sin camino a fuga ni falso bloqueo.** `build_sentence_report` es read-only; `annotate_draft` devuelve
  el mismo `text`; los `edits` no dependen de la segmentación. `false_block_signal` lee el `detalle`
  clásico (por cita), que no cambia → §6.8 se sostiene.
- **Sin camino a la decisión HITL ni al modelo.** El bloque `oraciones` viaja en `metadata`/payload HITL
  pero **ningún prompt** lo reinyecta (verificado en `finalize_node` editing y en el flujo de proyecto:
  `history`/`messages` llevan el texto anotado, no el informe). `score_turn` (donde entraría el residuo)
  **no corre en el turno vivo** — solo en `eval/harness`; aunque tocara `ok`, no afectaría a un abogado.
- **Regla 50 intacta.** Al ser read-only, `parse_diagnosis_closing` opera sobre el mismo texto de siempre;
  el bloque `=== CIERRE ===` sobrevive por construcción (§2.2.4 es defensa redundante pero inofensiva).
- **Agnosticismo / 104-104.** La lista de abreviaturas (art/arts/inc/num/ord/par/pág/p/ss/No/nro/cfr/vs)
  no trae literal de país; alimenta solo segmentación (fail-safe). Sin tocar el prompt, los `std-*` y las
  104 asserciones de `test_jurisdiction_agnostic.py` quedan verdes. El nuevo grep sobre
  `_ASSERT_ABBREVIATIONS` pasa.
- **Aditividad retrocompatible.** Con `sentence_report=False` (default) el informe es idéntico; los
  consumidores (`_citation_signal`, `false_block_signal`, harness, frontend) ignoran la clave extra. Único
  pendiente real: `aggregate_eval_runs.py` (el diseño ya lo flagea en §7) y el tipo TS del frontend.
- **Coste.** Cero llamadas LLM; regex O(n) en `to_thread`, despreciable frente a ~371 s (RE-BASELINE). No
  amenaza el presupuesto del recorrido. Único gasto evitable: el doble `scan_citations` de m4 y el bulto de
  JSON del bloque `oraciones` (cap 80 × ~240 chars, ×2 si viaja en `verification` y `verification_diagnosis`).

---

## Cierre

El diseño es **seguro** (no rompe la invariante) y **barato**, y su honestidad declarada es superior a la
media. Pero su **razón de ser** —medir el residuo para que las sondas tengan «un número que vigilar»— se
apoya en un contador (`sin_respaldo_afirmativa`) que M2/M3/M4 muestran **doblemente ruidoso, ciego a la
co-ubicación con citas y ciego al carve-out del abogado**. Corregidos esos cuatro MAYORES (empezando por el
bloqueante M1) y aterrizados los ocho menores, apruébese. Sin M1 no compila; sin M2-M4 el número que
justifica el paso no significa lo que el diseño dice que significa.
