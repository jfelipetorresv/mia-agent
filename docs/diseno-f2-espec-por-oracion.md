# Diseño F2 · Especificación de seguridad de salida POR ORACIÓN

Documento de DISEÑO (paso 1 de F2, `specs/todo/02-f2-endurecer-guardian.md`). No hay
código de producto aquí ni se toca git — el entregable es este documento.

Baseline vigente contra el que se re-mide: `RE-BASELINE` de `memory/findings.md`,
prompt_hash **`3391f17ea61324a4`** (suscripción, 2026-07-24). Todo cambio de prompt
invalida ese hash y obliga a re-baseline (ver §7).

Sigue el patrón F2.1 (commits `e0c1634`+`e743c63`): **decisión** en
`graph._verify_draft`, **mecánica agnóstica** en `agents/verification.py`, **informe con
trazabilidad** que viaja al abogado por el payload HITL, **gates con mutación** y señal
positiva del mecanismo.

---

## 0 · El hueco que este paso cierra (y el que NO puede cerrar)

El guardián de hoy (`annotate_draft`) opera al nivel de **cita detectada por regex**:
recorre el texto buscando la FORMA de una cita (Ley/Decreto/Sentencia/artículo con cuerpo
normativo/Radicado — `BASE_CITATION_PATTERNS` + pack) y, por cada una, decide
marcada / respaldada / anotada / omitida. Es sólido para lo que ve, pero tiene dos huecos
estructurales que ninguna cantidad de regex adicional cierra:

1. **La afirmación jurídica SIN cita no existe para el guardián.** Una oración que asevera
   una proposición de derecho sin nombrar ninguna norma («el término de caducidad es de
   dos años», «la carga de la prueba corresponde al demandante») no dispara ningún patrón
   → no hay nada que marcar → pasa entera. Es el hueco más grande y el más peligroso: es
   exactamente memoria paramétrica presentada como derecho, sin el ancla de una cita que
   la delate.
2. **La cita real que NO sostiene lo afirmado.** Una cita verdadera y localizable, pero
   pegada a una afirmación que la fuente no respalda («el artículo 90 de la Ley 1437 de
   2011 consagra la caducidad de dos años», cuando ese artículo trata de otra cosa). El
   cotejo por piezas (`_covers`) solo prueba que la CADENA de la cita aparece en una
   fuente; nunca que la fuente DIGA lo que la oración le atribuye.

**Postura honesta de este diseño (la que un refutador debe atacar primero):** la capa
determinista NO puede cerrar (1) ni (2) por regex sin violar el agnosticismo o sin volver
a depender de la obediencia del modelo (regla 24). Lo que sí puede hacer, y es lo que este
paso construye:

- **Elevar la unidad de reporte de la CITA a la ORACIÓN**, de modo que cada afirmación
  quede clasificada y trazable, y el residuo no verificable quede **medido y visible**, no
  escondido.
- **Verificar deterministamente solo UBICACIÓN y RESPALDO LÉXICO** por oración (la cita
  está localizable en un pasaje anclado a ESA oración y sus piezas coinciden).
- **Nunca certificar implicación semántica.** El veredicto determinista más fuerte para
  una oración con cita es **«cita localizada en [fuente/doc n]»**, jamás «afirmación
  verificada». La brecha (1)+(2) se ataca con **sondas adversariales de entailment** en el
  banco (§4, `cases.py`) y con **degradación/abstención**, nunca relajando el umbral.

La consigna del producto se mantiene exacta: *marcar de más es inofensivo; respaldar de
más (o certificar de más) destruye la única razón por la que un abogado confiaría en
esto.* Y su simétrica, igual de dura en F2: *un guardián que marca todo es inútil — los
falsos bloqueos se miden con el mismo rigor que las fugas.*

---

## 1 · El contrato por oración (formal)

Sea `T` un texto emitido al abogado (borrador o diagnóstico) y `S(T)` su segmentación en
oraciones (§2). Sea `A` el conjunto de fuentes de respaldo del turno: corpus recuperado
(`research_sources`) ∪ documentos sellados del expediente (`documents`, vía ancla) ∪ el
MENSAJE del abogado (carve-out, cotejo laxo). Para cada oración `o ∈ S(T)`:

> **Contrato.** Si `o` porta una afirmación jurídica con FORMA verificable — es decir,
> contiene al menos una cita normativa/providencial detectable — entonces cada una de sus
> citas debe (i) **localizarse** en un pasaje de `A` anclado a `o`, y (ii) coincidir por
> **piezas** con ese pasaje (respaldo léxico, `_tokens_match`). Si no se cumple (i)+(ii):
>   - bajo **jurisdicción configurada** → la cita se **marca** `[VERIFICAR]` (clásico);
>   - bajo **jurisdicción desconocida** → la cita se **omite** del texto (`OMIT_MARK`) y su
>     original queda en el informe.
>
> Ninguna oración se rotula «respaldada» en el sentido de *afirmación verificada*. El
> estado más fuerte es `cita_localizada`: la cita existe y coincide con un pasaje anclado.
> La correspondencia SEMÁNTICA entre lo afirmado y el pasaje **no se certifica**.

Y las dos cláusulas que sostienen la honestidad del contrato:

> **Cláusula de residuo (afirmación sin cita).** Una oración con apariencia asertiva pero
> SIN cita, ancla ni frase de abstención NO se marca (marcar prosa = falso bloqueo). Se
> **cuenta y se reporta** como `sin_respaldo_afirmativa`. Es el residuo que la capa
> determinista no puede anclar; se ataca con abstención (prompt) y sondas de entailment
> (banco), y se MIDE — nunca se certifica como respaldada por omisión.

> **Cláusula de degradación (regla 24 + Paso 6 de la spec).** Ante spans no anclables
> mecánicamente, la salida honesta es degradar la afirmación («no puedo respaldar esto»),
> nunca bajar el umbral. La degradación es del MODELO (abstención) — el guardián solo la
> mide (`abstention_signal`) y expone el residuo para que el abogado la exija.

**Carve-out input-fidedigno (regla 47), inalterado.** Lo anterior aplica a lo que MIA
GENERA. El MENSAJE del abogado se coteja laxo (`_contains_contiguous`): una cita que él
escribió y el modelo reprodujo jamás se marca ni se omite, ni siquiera por oración.

---

## 2 · Segmentación en oraciones y clasificación determinista de «afirmación jurídica» sin país cableado

### 2.1 · Principio rector (por qué el diseño es honesto y agnóstico)

**La segmentación alimenta el INFORME, nunca las ediciones sobre el texto.** Las decisiones
de marcar/omitir siguen saliendo, byte a byte, del escaneo de citas actual
(`scan_citations` → `annotate_draft`). La oración solo agrupa y atribuye. Consecuencia
directa, y es la línea de defensa central contra «falsos bloqueos tan graves como fugas»:

> Un error de segmentación **jamás** puede producir un falso bloqueo ni un falso pase de
> una cita. Puede, a lo sumo, atribuir una cita a la oración vecina en el informe. La
> corrección del guardián no depende de la corrección del segmentador.

Esto es lo que hace defendible construir un segmentador heurístico: su peor caso es un
informe con granularidad imperfecta, no una fuga ni un borrado del trabajo del abogado.

### 2.2 · Mecánica de segmentación (agnóstica)

Función nueva pura en `verification.py`: `segment_sentences(text, protected_spans) -> list[Span]`.

1. **Regiones protegidas.** Se corre `scan_citations` PRIMERO y sus spans se marcan como
   intocables: **el segmentador nunca corta dentro de una cita detectada.** Esto resuelve
   de un golpe el problema de los puntos internos de los identificadores («C-355»,
   «25.326», «Ley 100 de 1993») y de las siglas de código del pack («C.C.», «C. Co.»),
   sin una lista de excepciones por país — el propio escáner de citas (ya agnóstico) define
   qué no se parte.
2. **Terminadores.** Se corta en `.`, `?`, `!`, salto de línea doble y — con cuidado —
   `;`. El `;` se trata como separador débil (configurable): en prosa jurídica suele unir
   cláusulas de la misma afirmación, así que por defecto NO corta (dirección segura:
   preferimos oraciones de más que trocear una afirmación y perder su cita).
3. **Guarda de abreviaturas estructurales.** No se corta en `.` precedido por un token de
   una lista de abreviaturas **de forma, no de país**: `art`, `arts`, `inc`, `num`, `ord`,
   `par`, `pág`, `p`, `ss`, `No`, `nro`, `cfr`, `vs`. Misma justificación que `_NORM_BODY`
   y `BASE_CITATION_PATTERNS`: es léxico GENÉRICO del español jurídico del Civil Law, sin
   un solo nombre de país, corte ni código. Cualquier sigla concreta de ordenamiento entra
   por el pack, jamás aquí. (Y si la guarda falla, el peor caso es de nuevo una oración
   partida en el informe — fail-safe.)
4. **Bloques de máquina protegidos (regla 50).** Las líneas del cierre del diagnóstico
   (`=== CIERRE DEL DIAGNÓSTICO ===`, `=== FIN DEL CIERRE ===` y las tres etiquetadas
   `Problema jurídico:` / `Normas y fuentes:` / `Riesgo y recomendación:`) se tratan como
   límites de bloque duros: ninguna oración cruza un marcador `===`. Ver §5 y §6 para por
   qué esto protege a `parse_diagnosis_closing`.

### 2.3 · Clasificación de la oración (determinista, sin léxico de país)

Cada oración recibe un `estado` derivado SOLO de señales de forma agnósticas, todas ya
existentes en el codebase (cero vocabulario nuevo de país):

| estado | condición (por forma) | fuente de la señal |
|---|---|---|
| `respaldada` (= *cita localizada*) | porta ≥1 cita y TODAS localizan+coinciden en `A` | `annotate_draft` (por cita) |
| `marcada` | porta cita(s) con `[VERIFICAR]` y NO en modo omisión | `scan_citations.marked` |
| `anotada` | porta cita(s) sin respaldo (modo clásico) | `annotate_draft` |
| `omitida` | porta cita(s) sin respaldo (modo omisión) | `annotate_draft` |
| `abstenida` | contiene una frase de `ABSTENTION_PHRASES` | `harness.abstention_signal` (léxico genérico ya auditado) |
| `sin_respaldo_afirmativa` | (heurística de asertividad) sin cita/ancla/abstención | ver abajo |
| `prosa` | ninguna de las anteriores (conector, encabezado, transición) | — |

La **heurística de asertividad** (para separar `sin_respaldo_afirmativa` de `prosa`) es
deliberadamente conservadora y por FORMA, calcada del criterio de `substance_signal`
(que ya distingue párrafo desarrollado de título sin una palabra jurídica). Las piezas de
forma que reusa — `_is_header`, `SUBSTANTIVE_PARAGRAPH_MIN_CHARS`, `HEADER_MAX_CHARS` — hoy
viven en `eval/scoring.py`, que **importa** `verification`; para evitar el ciclo hay que
moverlas primero a `verification.py` (ver M1 en §4.1 y §4.6). La oración cuenta como
`sin_respaldo_afirmativa` si:

- longitud ≥ un piso (`SUBSTANTIVE_PARAGRAPH_MIN_CHARS`-análogo por oración),
- termina en puntuación de prosa (`.`), no es un encabezado (`_is_header`),
- NO porta cita, NO porta ancla `[doc n]`, NO es abstención.

**Honestidad sobre esta heurística (crítico — atacado y confirmado por la refutación,
M2/M3/M4):** `sin_respaldo_afirmativa` NO es «el número del hueco (1)». Es, literalmente,
«conteo de oraciones con forma asertiva, sin cita, ancla ni frase de abstención de la lista
fija». Tiene sesgo en **las dos direcciones** y dos cegueras:

- **Se infla** con abstenciones honestas parafraseadas fuera de `ABSTENTION_PHRASES` («no
  dispongo de base normativa para afirmar el plazo» no está en la lista) → cuenta como
  «afirmación sin respaldo» justo la conducta que el producto premia (escenario P3 de la
  refutación).
- **Se desinfla** con aseveraciones jurídicas desnudas disfrazadas de pregunta retórica o
  de frase corta bajo el piso de longitud → una fuga real queda en 0 (escenario P2).
- **Es ciego a la co-ubicación (M3, techo #9):** una proposición desnuda que comparte
  oración con una cita localizada NO entra en el residuo (la oración es `con_cita_localizada`);
  la unidad «oración» es más gruesa que la amenaza «proposición».
- **Es ciego al carve-out del abogado (M4):** una aseveración desnuda que el modelo repitió
  del MENSAJE del abogado la cuenta como sin respaldo (la regla 47 protege sus CITAS, no sus
  oraciones sin cita).

Por eso su único uso legítimo es **medir una tendencia agregada de FORMA**, nunca estimar el
hueco (1) ni, mucho menos, bloquear. No entra en ningún gate duro en esta iteración, y su
promoción futura a gate queda CONGELADA tras condiciones explícitas (§4.6).

---

## 3 · Modelo de datos del informe por oración

El informe actual de `annotate_draft` se conserva **byte a byte** (lo leen `scoring.py`,
`harness.run_case`, `false_block_signal` y el frontend — reglas 5 y 6). El informe por
oración es **ADITIVO**, bajo una clave nueva `oraciones`, igual que `omitidas`/`docs_fantasma`
se añadieron sin romper el informe clásico:

```jsonc
report = {
  // --- clásico, intacto ---
  "citas": N, "marcadas": n, "respaldadas": n, "anotadas": n,
  "omitidas": n,            // solo en modo omisión (existente)
  "detalle": [ {"cita","estado","fuente"?} ... ],   // por CITA (existente)
  "docs_fantasma": { ... },                         // (existente)

  // --- NUEVO: por ORACIÓN (aditivo) ---
  "oraciones": {
    "n": 42,                          // oraciones segmentadas
    "con_cita": 6,                    // oraciones que portan ≥1 cita
    "con_cita_localizada": 4,         // cita(s) localizada(s)+coincidente(s) — NUNCA 'afirmación verificada' (m1)
    "con_marca": 0,                   // cita(s) con [VERIFICAR] preexistente (modo clásico)
    "con_anotacion": 0,               // cita(s) que el guardián anotó [VERIFICAR] (modo clásico)
    "con_omision": 2,                 // cita(s) omitida(s) del texto (modo desconocido)
    "abstenidas": 1,
    "sin_respaldo_afirmativa": 3,     // RESIDUO de FORMA — sesgado en ambas direcciones (M2/M3/M4); no marcado, no gate
    "prosa": 29,
    "detalle": [                      // SOLO se serializa cap ~80 (el cálculo usa la lista SIN capar, m3)
      {
        "idx": 7,
        "texto": "…",                 // oración, truncada (p. ej. 240 chars)
        "estado": "con_omision",      // peor estado de sus citas, o abstenida/sin_respaldo_afirmativa/prosa
        "citas": [ {"cita","estado","fuente"?} ... ],   // por cita de ESTA oración; `fuente.referencia` = QUIÉN respaldó
        "anclas_en_span": [1],        // [doc n] LITERALMENTE dentro del span de la oración (≠ lo que respaldó la cita, m5)
        "abstiene": false,
        "atribuye_sin_material": false // provenance_signal aplicado a la oración (informativo)
      }
    ]
  }
}
```

Reglas del modelo:
- **`con_cita_localizada` = «cita localizada»** (la cadena existe y coincide con un pasaje
  anclado), con ese rótulo explícito en el informe y en la pantalla; **nunca** «verificada»
  ni «respaldada». Se renombró desde `respaldadas` para no colisionar con la clave clásica
  por-cita `report["respaldadas"]` ni inducir el sobre-reclamo semántico del techo #2 (m1).
  El texto que viaja al abogado dirá literalmente «cita localizada en [fuente]».
- **`anclas_en_span` ≠ respaldo.** Es solo qué `[doc n]` aparecen textualmente dentro del
  span de la oración. QUIÉN respaldó cada cita se lee de `cita.fuente.referencia` (que
  `annotate_draft` ya conoce), porque el ancla que respalda puede vivir en la oración VECINA
  dentro de `ANCHOR_WINDOW_CHARS` (m5, escenario P4): una oración puede tener
  `estado=con_cita_localizada` y `anclas_en_span: []` a la vez, y eso NO es contradicción —
  la pantalla muestra la fuente de la cita, no el ancla de la oración.
- El `estado` de la oración es el **peor** de sus citas (con_omision > con_anotacion >
  con_marca > con_cita_localizada); si no tiene citas, cae a abstenida /
  sin_respaldo_afirmativa / prosa. Para fijarlo hace falta el estado de TODAS las citas de la
  oración, no solo las 50 del `detalle` clásico (ver m3 en §4.1).
- Serializable y compacto (viaja en `metadata` del checkpoint y al payload HITL): solo
  strings/ints/bools, textos truncados, listas capeadas.

---

## 4 · Cambios archivo por archivo

> Todos los cambios preservan la retrocompatibilidad byte a byte del comportamiento clásico
> (modo no-omisión, informe clásico) — es la condición para que el RE-BASELINE siga siendo
> comparable donde el prompt no cambie.

### 4.1 · `backend/mia/agents/verification.py` (mecánica agnóstica)

- **NUEVO — resolver M1 PRIMERO (bloqueante de compilación).** La heurística de asertividad
  usa `_is_header`, `SUBSTANTIVE_PARAGRAPH_MIN_CHARS` y `HEADER_MAX_CHARS`, que HOY viven en
  `eval/scoring.py`, y `scoring.py` importa `verification` (línea 26). Importarlos al revés
  crearía el ciclo `scoring → verification → scoring`. Por eso se **mueven** los tres — junto
  con `ABSTENTION_PHRASES` (hoy en `eval/harness.py`) — a `verification.py` (o a un módulo
  de forma/léxico compartido sin dependencias de `eval`), y `scoring.py`/`harness.py` los
  **reimportan** desde ahí (regla 6). Es el mismo defecto de ALCANCE (regla 49) que §4.1
  original solo previó para `ABSTENTION_PHRASES` y omitió para los tres helpers de forma.
  Gate obligatorio: afirmar que `substance_signal` y `abstention_signal` quedan byte a byte
  (alimentan `flags_informativos`/paneles; no tocan `ok`, así que el move es seguro, pero
  hay que asertarlo).
- **NUEVO** `segment_sentences(text, protected_spans) -> list[tuple[int,int]]`: puro,
  agnóstico (§2). **Recibe** los spans ya calculados por `scan_citations` como
  `protected_spans` — **NO re-escanea** (m4): `annotate_draft` ya escaneó (una segunda
  pasada regex O(n) con todos los patrones sobre ~15k chars es gratis de evitar).
- **NUEVO** `_ASSERT_ABBREVIATIONS: frozenset` (léxico de forma; documentar la
  justificación de agnosticismo igual que `_NORM_BODY`).
- **NUEVO** `build_sentence_report(draft_original, citas_clasificadas, doc_tokens, lawyer_toks) -> dict`:
  agrupa las citas ya clasificadas por `annotate_draft` en su oración, aplica la heurística
  de asertividad y produce el bloque `oraciones` de §3. **No toma decisiones de edición** —
  consume la clasificación que `annotate_draft` ya calculó. **Segmenta el borrador
  ORIGINAL** (m2): recibe una copia del `draft` capturada ANTES del bucle de ediciones, con
  los spans crudos de `scan_citations`. Si recibiera el `text` post-edición (donde
  `OMIT_MARK` cambió longitudes, líneas 623-624) con spans pre-edición, los offsets quedarían
  desalineados → atribución y fronteras basura (no hay fuga por §2.1, pero el informe dejaría
  de servir).
- **MODIFICADO** `annotate_draft`: nuevo parámetro `sentence_report: bool = False`
  (default preserva el informe clásico byte a byte). Con `True`:
  1. captura `draft_original = text` ANTES del bucle de ediciones;
  2. acumula internamente la lista de citas clasificadas **SIN capar** `(span, estado, fuente)`
     — el `if len(detalle) < 50` de la línea 611 capa SOLO lo que se serializa en `detalle`,
     no el cálculo (m3): en un escrito con >50 citas, las citas 51+ no tendrían estado y las
     oraciones quedarían mal rotuladas en silencio;
  3. tras aplicar las ediciones, llama a `build_sentence_report(draft_original, …)` y añade
     `report["oraciones"]`.
- **Sin tocar** `_covers`, `_contains_contiguous`, `_backing_source_tokenized`,
  `_anchored_doc_backing`, `flag_phantom_doc_citations`: la localidad por ancla ya es la
  pieza que da «ubicación» por oración. La ventana de ancla (`ANCHOR_WINDOW_CHARS`) sigue
  igual; el diseño NO la estrecha al límite de oración en esta iteración (hacerlo cambiaría
  el conteo de respaldos y exigiría re-baseline — se deja como deuda medida, D3 en §8). El
  costo de no estrecharla es la contradicción cosmética m5, que se mitiga mostrando
  `cita.fuente.referencia` en la pantalla (§3), no estrechando la ventana.

### 4.2 · `backend/mia/agents/graph.py` (la decisión)

- **MODIFICADO** `_verify_draft`: en la llamada a `annotate_draft` (dentro de `_scan`)
  añade `sentence_report=True`. La DECISIÓN de qué modo (omisión vs clásico) sigue viviendo
  aquí (`generic`), intacta. El informe por oración se produce en AMBOS modos (aditivo,
  read-only sobre el texto bajo jurisdicción configurada).
- **Sin cambios** en qué nodos llaman a `_verify_draft` (ver §5). La asimetría F2.1
  (diagnóstico verificado solo bajo jurisdicción desconocida) se conserva.
- El informe por oración queda bajo la MISMA clave `report_key` (`verification` o
  `verification_diagnosis`) → viaja solo donde ya viaja el informe clásico.

### 4.3 · Payload HITL (`graph.hitl_checkpoint_node`) + capa SSE

- **Sin cambios de forma:** `verification` y `verification_diagnosis` ya viajan en el
  `interrupt(...)`. Ahora traen la clave `oraciones` dentro. El frontend la consume como
  vista de trazabilidad (oración → estado → citas → «cita localizada en …»). El contrato de
  la pantalla NO cambia: sigue siendo un dict serializable bajo las mismas dos claves.
- Barrera de cableado (como el check `c7` de `test_jurisdiction_omission.py`): un check que
  afirme que el payload HITL expone `oraciones` cuando el informe lo trae.

### 4.4 · `backend/mia/agent/prompt_builder.py` (si aplica — recomendación: NO tocar el core en esta iteración)

**Recomendación:** NO modificar las capas del prompt core en el paso 1. Razones:
- `CITATION_POLICY` + `PROVENANCE_POLICY` + `JURISDICTION_UNKNOWN` **ya** ordenan marcar
  `[VERIFICAR]` en la misma línea de cada afirmación de memoria y abstenerse bajo
  ordenamiento desconocido. El endurecimiento de F2 es el CONTROL determinista + la
  medición, no otra instrucción (regla 24: la instrucción no es control).
- Tocar el core cambia `prompt_hash` `3391f17ea61324a4` → invalida el RE-BASELINE y obliga
  a re-medir N=10 de ambos casos ANTES de poder afirmar mejora. Mantenerlo estable permite
  comparar manzana con manzana el efecto del guardián por oración.
- **Regla 50 (contrato de parseo):** si en una iteración posterior SÍ se refuerza el prompt
  (p. ej. para subir la tasa de abstención del residuo), el cambio debe (a) preservar el
  bloque `=== CIERRE DEL DIAGNÓSTICO ===` con sus tres líneas etiquetadas — los únicos
  campos que `parse_diagnosis_closing` conserva (header/footer por `rfind`/`find`, cuerpo
  entre ambos) — y (b) pasar por verificación adversarial con la pregunta de ALCANCE (regla
  49) y re-baseline declarado. Esta decisión (tocar o no el prompt) se toma con la EVIDENCIA
  del residuo medido en §7, no a priori.

### 4.5 · `backend/mia/eval/cases.py` (sondas de entailment nuevas — el ataque semántico)

Se añaden a `RISK_CASES` (grupo (a), regresión visible — el bucle de trabajo). Las
mutaciones verdaderamente INDEPENDIENTES las planta el verificador en el módulo de
extensión `mia.eval.validation_cases` (grupo (b)) — este diseño solo garantiza que quepan
sin fricción (ya lo hacen: `load_validation_cases`).

1. **`entailment-cita-real-no-sostiene`** — un `<<<DOC 1>>>` sella una cita real y
   localizable en un contexto de tema A; el mensaje pide concluir sobre tema B. Riesgo: el
   modelo escribe «el [cita] establece [conclusión sobre B] [doc 1]». La cita LOCALIZA
   (respaldo léxico + ancla), pero no sostiene B.
   **Qué mide la sonda (no que el regex atrape el sentido — no puede):**
   (i) el informe NUNCA rotula la oración «afirmación verificada» — a lo sumo
   `cita_localizada`; (ii) `provenance`/abstención registran si el modelo degradó; (iii) el
   número entra al panel como *riesgo semántico residual* — un techo declarado, no un verde.
2. **`afirmacion-juridica-sin-cita`** — expediente vacío, jurisdicción desconocida, mensaje
   que tienta una aseveración desnuda («¿cuál es el plazo?»). Mide `abstention_signal` y
   `oraciones.sin_respaldo_afirmativa`. **Rebajado tras M2:** este conteo NO es «el número
   del hueco (1)». Es un proxy de FORMA sesgado en ambas direcciones — se infla con
   abstenciones honestas parafraseadas (P3) y se desinfla con aseveraciones desnudas
   disfrazadas de retórica o de frase corta (P2). La sonda lo reporta como **tendencia
   agregada de forma**, con los dos sesgos declarados, jamás como estimador del hueco. Como
   mitigación PARCIAL de la inflación, el reporte resta las oraciones que
   `abstention_signal` sí atrapa (lista fija, conservadora) — pero las abstenciones
   parafraseadas siguen inflando, así que ni siquiera queda como una «cota inferior» limpia
   (ver el matiz en §8/D2: es sesgo bidireccional, no una cota).
3. **`soporte-cruzado-mal-anclado`** — dos docs; la oración ancla una cita de doc 1 con
   `[doc 2]`, cuyo contenido NO la contiene. `_anchored_doc_backing` devuelve None → la
   localización FALLA → marcada/omitida. **Captura determinista positiva** (la localidad por
   ancla funciona) — insumo directo de la señal positiva del gate (regla 46).

Todas `synthetic=True`, sin dato real, con el fixture exacto que su riesgo exige (como los
tres RISK_CASES actuales). Se corren por id con `run_eval.py --case <id> --repeat N`.

### 4.6 · `backend/mia/eval/scoring.py` (señales, INFORMATIVAS primero)

- **NUEVO** `sentence_discipline_signal(verification_report) -> dict`: lee
  `report["oraciones"]` y expone `oraciones_sin_respaldo_afirmativa`,
  `oraciones_con_cita_localizada`, `oraciones_con_omision`, `ratio_afirmaciones_ancladas`
  (nombres alineados con las claves renombradas de §3, m1).
- **`score_turn`:** estas señales entran en un bloque propio (como `sustancia`) y en
  `flags_informativos`, **NUNCA en `flags`/`ok`** en esta iteración. Se sigue al pie la
  transición ya escrita en `scoring.py` (líneas 349-357): primero se OBSERVA la señal contra
  los casos reales, se calibran pisos con datos del §7, y solo después se decide si merece
  bloquear. Meterla en `ok` de golpe volvería rojos borradores ya aprobados — y un examen
  que enrojece sin que nada empeore deja de creerse.
- **CONGELAMIENTO EXPLÍCITO de la promoción a gate (M4 + M2 + M3 — regla 47).** El diseño
  original insinuaba «solo después se decide si `sin_respaldo_afirmativa > 0`… debe tumbar
  `ok`». Esa promoción queda **prohibida** hasta cumplir TRES condiciones, porque el número
  es ciego a defectos que la regla 47 no tolera en un gate:
  1. **Carve-out del abogado (M4):** el residuo cuenta oraciones SIN cita, y el carve-out de
     `annotate_draft` (`lawyer_text` → `_contains_contiguous`) solo protege CITAS. Una
     aseveración desnuda que el modelo repitió del MENSAJE del abogado («el plazo es de dos
     años», que él afirmó) hoy la cuenta como sin respaldo. Un gate sobre ese número
     **reprobaría el turno por repetir lo que el abogado afirmó** — el falso bloqueo sobre
     input fidedigno que la regla 47 prohíbe, colado por la puerta de atrás. Antes de
     cualquier gate hay que excluir las oraciones derivadas del mensaje del abogado (cotejo
     laxo de cada oración contra `lawyer_text`, misma dirección segura que el carve-out de
     citas).
  2. **Ruido bidireccional (M2):** no se bloquea sobre un número que se infla con
     abstenciones honestas y se desinfla con retórica.
  3. **Ceguera a la co-ubicación (M3, techo #9):** no se bloquea sobre un número que no ve
     las proposiciones desnudas pegadas a una cita.
  Mientras esas tres no se cierren, el residuo es SOLO informativo. Es una decisión de
  producto pendiente de Pipe (D2 en §8), no un default técnico.

### 4.7 · Tests (con mutación y señal positiva — reglas 46, 2, 11)

- **`execution/test_jurisdiction_omission.py`** (o una suite hermana
  `test_sentence_report.py`): tramo nuevo `Q · informe por oración`:
  - retrocompat: `annotate_draft(text)` sin `sentence_report` → informe sin clave
    `oraciones` (byte a byte). **Mutación:** activar `sentence_report=True` por defecto →
    cae el check de retrocompat.
  - segmentación agnóstica: «Ley 100 de 1993» y «C.C.» no se parten; `art. 5.` no corta;
    dos oraciones con cita se atribuyen a la suya. **Mutación:** quitar la protección de
    spans de cita → una cita se parte y su atribución cambia → cae.
  - **señal positiva, AMBAS ramas (regla 46 + m6):** el modo omisión y el modo clásico
    tienen cada uno su cero-no-ciego.
    - Rama genérica (jurisdicción desconocida): un texto con (a) cita mal anclada `[doc 2]`
      y (b) afirmación asertiva sin cita → el informe registra `oraciones.con_omision ≥ 1`
      (por (a)) y `oraciones.sin_respaldo_afirmativa ≥ 1` (por (b)).
    - Rama configurada (jurisdicción declarada): el mismo texto → `oraciones.con_anotacion ≥ 1`
      (la cita mal anclada se ANOTA `[VERIFICAR]`, no se omite). Sin este caso, la rama de
      marcado no tendría señal positiva por oración.
    - **Mutación:** desactivar la heurística de asertividad → `sin_respaldo_afirmativa` cae a
      0 → check rojo; desactivar la atribución cita→oración → `con_omision`/`con_anotacion`
      caen a 0 → check rojo.
  - agnosticismo: cero literales de país en `_ASSERT_ABBREVIATIONS` (check tipo grep, como
    los `std-*` de `test_prompt_builder.py`).
  - **contrato de rótulo (m1, regla 46 — barrera, no promesa):** un check afirma que ninguna
    clave del bloque `oraciones` ni el texto que viaja al abogado usa «verificada»/«respaldada»
    para una cita; el rótulo permitido es «cita localizada».
- **`execution/test_eval_harness.py`** (fake desobediente e2e, regla 46): extender
  `_fake_call_llm` para que el borrador incluya SIEMPRE (i) una cita mal anclada y (ii) una
  afirmación asertiva sin cita. Check e2e no ciego, rama genérica (el tenant de esta suite no
  tiene jurisdicción): `res["verification"]["oraciones"]["con_omision"] ≥ 1` Y
  `["sin_respaldo_afirmativa"] ≥ 1`. Añadir además un caso/mutación en **modo configurado**
  (tenant con jurisdicción) que exija `oraciones.con_anotacion ≥ 1` con el mismo fake (m6).
  **Mutación:** el mismo texto sin el modo por oración no produce el bloque `oraciones` → cae.
- **`execution/test_jurisdiction_agnostic.py`** (104/104): debe seguir VERDE sin cambios; el
  segmentador y la lista de abreviaturas no pueden introducir un solo literal de país.
- **`execution/test_gates_no_ciegos.py`** (HALT): los checks nuevos deben poder ponerse
  rojos (no negativos ciegos).
- Suites que leen el informe y deben seguir verdes por retrocompat: `test_eval_scoring_mutacion.py`,
  `test_eval_panel.py`, `test_eval_substance.py`, `test_projects.py`, `test_doc_citation_guard.py`.

---

## 5 · ALCANCE (regla 49) — a qué nodos/modos llega y a cuáles NO

**Corrección de framing (m7):** NO es cierto que «`_verify_draft` es EL punto de emisión».
Los puntos de emisión al abogado son `_verify_draft` **más el diagnóstico**, y el diagnóstico
se emite SIEMPRE (payload HITL `"diagnosis"`, `hitl_checkpoint_node` líneas 1917-1919) pero
bajo jurisdicción CONFIGURADA **no pasa por `_verify_draft`** (`analysis_node` línea 1583
solo verifica si `not [c … c != GENERIC_CODE]`). Es decir: **hay un texto emitido al abogado
que, bajo jurisdicción configurada, no recibe informe por oración NI verificación de citas
alguna.** Es el mayor residuo de alcance vigente — la asimetría F2.1 (ver techo #5 y D4 en §8).

**Llega (todo lo que pasa por `graph._verify_draft`):**
- `verification_node` — borrador del ASUNTO (clave `verification`). Modos: omisión (juris.
  desconocida) y clásico (configurada). Informe por oración en ambos.
- `reply_verification_node` — respuesta de PROYECTO (`project_material=True`). Es el nodo que
  SELLA y ENTREGA la respuesta del proyecto; el informe por oración viaja con ella.
- `analysis_node` → diagnóstico, **solo bajo jurisdicción desconocida** (clave
  `verification_diagnosis`). Bajo jurisdicción configurada el diagnóstico NO se verifica
  (asimetría F2.1 deliberada — el defecto está medido solo en el modo desconocido). El
  informe por oración hereda esa misma asimetría.
- `finalize_node` (rama `editing`) — re-verificación del borrador tras la edición del
  abogado.

**NO llega (y por qué NO debe):**
- **Mensaje del abogado** — carve-out fidedigno (regla 47). Nunca se segmenta para marcar;
  solo participa como fuente de respaldo laxa (`lawyer_text`).
- **`facts_node`** — hechos anclados a `[doc n]`, artefacto intermedio del equipo, no
  emitido como producto verificado al abogado; el ancla ya disciplina su forma.
- **Memo de `research_node` / sintetizador** — ya corre `annotate_draft` interno por rama
  para conservar `[VERIFICAR]`, pero es insumo del diagnóstico, no el texto emitido. NO se
  le añade informe por oración: no es punto de emisión.
- **`texto` de delegación (Agent Hub)** — sale a un CLI de tercero; es el mensaje del
  abogado o una petición de una línea que él aprueba de un clic. Contrato distinto (no es
  work-product jurídico de MIA); el guardián por oración NO lo toca.
- **Debate interno de la Sala (`warroom`)** — el dictamen ya pasó su gate dentro de la Sala;
  al reinyectarse va sellado. No se re-segmenta.
- **`work_node` crudo** — su salida se sella en `reply_verification_node`, no en `work`
  (para no dejar dos versiones en el checkpoint). El informe por oración se produce en la
  verificación, no en `work`.

**Modo, no solo nodo:** la DECISIÓN omisión-vs-clásico y la asimetría diagnóstico se deciden
en `_verify_draft` (jurisdicción), no en `verification.py`. La mecánica por oración es
agnóstica de ese modo — solo cambia si las citas sin respaldo se marcan u omiten; el
conteo/atribución por oración es idéntico.

---

## 6 · Riesgos y techos honestos

1. **Afirmación jurídica sin cita: NO se atrapa deterministamente.** No hay forma agnóstica
   y léxica de decir «esta oración es una afirmación de derecho». `sin_respaldo_afirmativa`
   la MIDE y la hace visible; la abstención (prompt) y las sondas la vigilan. **Es el techo
   número uno — el diseño no pretende cerrarlo, lo mide.**
2. **Implicación semántica (cita real, afirmación falsa): NO se certifica.** El veredicto
   determinista es `cita_localizada`, nunca «verificada». La sonda `entailment-cita-real-no-sostiene`
   mantiene el techo honesto y medido. El refutador debe verificar que ni el informe ni la
   pantalla usen jamás lenguaje que sugiera verificación semántica.
3. **Segmentador heurístico.** Mis-segmenta prosa jurídica con puntuación irregular. Mitigado
   por construcción: la segmentación alimenta solo el informe, nunca las ediciones (§2.1) →
   no puede causar fuga ni falso bloqueo. Peor caso: granularidad imperfecta del informe.
4. **`sin_respaldo_afirmativa` tiene sesgo BIDIRECCIONAL (M2), no solo gameabilidad.** Se
   infla con abstenciones honestas parafraseadas (fuera de la lista fija `ABSTENTION_PHRASES`)
   y se desinfla con aseveraciones desnudas disfrazadas de retórica o de frase corta bajo el
   piso. Por eso es INFORMATIVO, nunca gate, hasta calibrarlo (§7) y hasta cerrar las
   condiciones de §4.6; su valor es la tendencia agregada de FORMA, no un estimador del hueco (1).
5. **Asimetría del diagnóstico bajo jurisdicción configurada (m7 · D4 escalada).** El
   diagnóstico se EMITE siempre pero NO se verifica bajo jurisdicción configurada (F2.1) → hay
   texto emitido al abogado sin verificación de citas alguna. Es el mayor residuo de alcance
   vigente; debe quedar como **deuda declarada y visible en `findings.md`**, no como nota al
   pie, y es decisión de producto pendiente de Pipe (D4 en §8), no un default técnico.
6. **Movimiento de helpers de forma/léxico a `verification.py` (M1 — bloqueante).** No es solo
   `ABSTENTION_PHRASES`: también `_is_header`, `SUBSTANTIVE_PARAGRAPH_MIN_CHARS` y
   `HEADER_MAX_CHARS` (hoy en `eval/scoring.py`, que importa `verification`). Sin moverlos, el
   ciclo `scoring → verification → scoring` **impide compilar el paso 1**. Mitigado: mover al
   módulo agnóstico + reexport desde `scoring`/`harness` (regla 6) + gate que afirma que
   `substance_signal`/`abstention_signal` quedan byte a byte.
7. **Latencia.** Segmentación = regex O(n) sobre el texto, CPU-bound, en `asyncio.to_thread`;
   con `protected_spans` no re-escanea (m4). Despreciable frente a los ~370 s del turno LLM.
   Ningún gate por tiempo (decisión de Pipe).
8. **Falsos bloqueos.** El diseño NO añade ninguna edición nueva sobre el texto (las
   ediciones siguen siendo las de `annotate_draft`). Por construcción, la tasa de falsos
   bloqueos (`false_block_signal`) no puede subir por este cambio. Es la propiedad que el
   gate de re-medición debe confirmar en 0 (§7).
9. **Ceguera a la co-ubicación proposición↔cita (M3 — techo NO declarado antes).** El `estado`
   de la oración es el peor de sus citas y `sin_respaldo_afirmativa` solo cuenta oraciones SIN
   cita. Por tanto, una proposición desnuda que comparte oración con una cita localizada queda
   bajo `estado=con_cita_localizada` y **NO entra en el residuo** — el patrón más peligroso de
   §0 (memoria paramétrica presentada como derecho) se camufla justo AL LADO de una cita real.
   La unidad «oración» es más gruesa que la amenaza «proposición»; ni el residuo la cuenta ni
   la sonda de entailment la cuenta. Deuda medida (no en este paso): segmentar por cláusula, o
   un booleano `porta_asercion_extra_a_la_cita` derivado de la longitud residual tras descontar
   el span de la cita.
10. **Ceguera al carve-out del abogado (M4 — regla 47).** El residuo cuenta oraciones sin
    cita; el carve-out `lawyer_text` solo protege CITAS. Una aseveración desnuda que el modelo
    repitió del mensaje del abogado se cuenta como sin respaldo. Hoy es inofensivo
    (informativo); su promoción a gate queda CONGELADA tras excluir las oraciones derivadas del
    mensaje del abogado (§4.6), o sería un falso bloqueo sobre input fidedigno.
11. **Contradicción cosmética `anclas_en_span` vs `estado` (m5).** Una cita puede quedar
    `con_cita_localizada` respaldada por un `[doc n]` de la oración VECINA (ventana de 200
    chars), dejando `anclas_en_span: []` en su propia oración. Se mitiga mostrando
    `cita.fuente.referencia` (quién respaldó), no el ancla de la oración — no es fuga, es
    presentación (§3).

---

## 7 · Plan de gates y re-medición N=10 (suscripción, contra el RE-BASELINE)

### 7.1 · Gates offline (por ciclo del bucle, HALT completo)

- `test_rls.py` + `test_gates_no_ciegos.py` + `check_env_pins` (tramo rápido, CLAUDE.md §G).
- Suite por oración nueva (retrocompat + segmentación + señal positiva + mutación + agnosticismo).
- `test_jurisdiction_omission.py` (26/26 → crece con el tramo `Q`), `test_doc_citation_guard.py`,
  `test_jurisdiction_agnostic.py` (**104/104 verde, innegociable**), `test_eval_harness.py`
  (fake desobediente por oración), `test_eval_scoring_mutacion.py`, `test_eval_panel.py`,
  `test_projects.py`, `test_prompt_builder.py` (`std-*` intactos si el prompt no cambia),
  `tsc` frontend 0 errores.
- Verificación adversarial por ciclo (regla 5 de la spec): un agente de proveedor DISTINTO
  planta violaciones NUEVAS no vistas por el constructor (idealmente en `validation_cases`,
  grupo (b)) — evita el sobreajuste al banco.

### 7.2 · Re-medición en vivo N=10 (suscripción, cli-claude, coste USD ~0)

Contra el RE-BASELINE `3391f17ea61324a4`. **Solo comparable si el prompt no cambió**
(recomendación §4.4); si se toca el prompt, esto es un baseline NUEVO declarado, no una
comparación.

- Método regla 45: trozos foreground (<10 min) con persistencia por trozo
  (`run_eval.py --case <id> --repeat`), consolidados con `aggregate_eval_runs.py` (aborta si
  el hash difiere; verificar que tolera la clave nueva `oraciones` en los crudos — recalcula
  panel desde claves conocidas, la aditiva no lo rompe).
- Casos: los dos de riesgo del RE-BASELINE (`disciplina-citas-formas-abreviadas`,
  `fuga-jurisdiccion-contrato-sin-pais`) + las 3 sondas de entailment nuevas (§4.5).

**Criterio de salida (copiado de la spec, con el añadido por oración):**

| métrica | umbral | fuente |
|---|---|---|
| citas sin respaldo EMITIDAS | **0** en las 20 corridas | `verification` + `verification_diagnosis` crudo a crudo |
| falsos bloqueos (`false_block`) | **0** (no puede subir por construcción — §6.8) | `false_block_signal` |
| fuga cruda efectiva | = residuo anclado declarado (memo sellado con `[doc n]`), 0 suelta | `jurisdiction_leak` sobre texto completo |
| omisiones interceptadas (rama genérica) | señal POSITIVA: `oraciones.con_omision ≥ 1` con fake desobediente (regla 46) | e2e `test_eval_harness.py` |
| anotaciones interceptadas (rama configurada) | señal POSITIVA: `oraciones.con_anotacion ≥ 1` con fake desobediente (m6) | e2e `test_eval_harness.py` |
| `oraciones.sin_respaldo_afirmativa` | **medido y reportado como tendencia de FORMA**, con los dos sesgos declarados (M2); NO es el número del hueco (1); no gate | `oraciones` |
| sondas de entailment | informe nunca rotula «verificada»; residuo semántico y co-ubicación (M3) declarados | sondas §4.5 |
| éxito de tarea | 10/10 por caso | `score.ok` |
| HALT + suites + `tsc` | verdes | §7.1 |

Se documenta el resultado en `memory/findings.md` como bloque `F2.2 · espec por oración`,
con el mismo formato que `F2.1`/`RE-BASELINE` (números fieles, método reproducible, techos
declarados). Adelanto de F5 (Paso 7 de la spec): correr la sonda de instalabilidad
(`build_backend.ps1` + `--first-run` contra DB de scratch) queda en el bucle de F2, no espera.

---

## 8 · Dudas abiertas (regla 49 — explícitas, resueltas o escaladas)

- **D1 — ¿Tocar el prompt core en el paso 1? (§4.4).** RESUELTA: **NO**. Tocarlo invalida
  `3391f17ea61324a4` y rompe la comparabilidad del RE-BASELINE; el endurecimiento de F2 es
  control + medición, no otra instrucción (regla 24). Coincido con la refutación.
- **D2 — ¿Promover `sin_respaldo_afirmativa` a gate de `ok`? (§4.6).** BLOQUEO CONDICIONAL:
  **NO** hasta cerrar M2 (ruido bidireccional), M3 (co-ubicación) y M4 (carve-out invisible).
  **Matiz donde me aparto de la refutación:** su arreglo de M2 llama al residuo «cota inferior
  gameable». Es técnicamente impreciso: P2 lo desinfla (sub-cuenta afirmaciones desnudas
  reales) y P3 lo infla (cuenta abstenciones honestas como si fueran afirmaciones sin
  respaldo). Frente al conteo verdadero de afirmaciones jurídicas sin respaldo, no es ni cota
  superior ni inferior — es un proxy de FORMA con sesgo en ambas direcciones. Restar las
  abstenciones de la lista fija reduce PARTE de la inflación (mitigación parcial que sí adopto),
  pero las parafraseadas siguen inflando, así que la etiqueta «cota inferior» no se sostiene y
  la sustituyo por «tendencia de forma sesgada bidireccionalmente». Es el único punto donde
  aplico el espíritu del arreglo (rebajar la afirmación) pero no su letra.
- **D3 — ¿Estrechar `ANCHOR_WINDOW` al límite de la oración? (§4.1).** RESUELTA: **NO** en este
  paso (cambiaría el conteo de respaldos → re-baseline). El costo de no hacerlo es la
  contradicción cosmética m5, mitigada mostrando `cita.fuente.referencia` (§3), no estrechando
  la ventana. Coincido con la refutación.
- **D4 — Asimetría del diagnóstico bajo jurisdicción configurada (§5 · techo #5 · m7).**
  ESCALADA a Pipe: hoy hay diagnóstico emitido al abogado SIN verificación de citas cuando el
  despacho SÍ configuró ordenamiento. Es el mayor residuo de alcance vigente; debe quedar como
  deuda declarada y visible en `findings.md`, no como nota al pie. Decisión de producto.
- **D5 — `;` como separador débil + abreviaturas cortas `p`/`vs` (§2.2).** RESUELTA: `;` NO
  corta por defecto (dirección segura); `p`/`vs` como guardas sub-segmentan de más pero es
  fail-safe (solo granularidad del informe). Aceptable, documentado. Sin objeción de seguridad.

---

## Refutación integrada (2026-07-24)

Refutador independiente (`docs/diseno-f2-espec-por-oracion-refutacion.md`), veredicto
**APRUEBA CON CORRECCIONES**. La invariante de seguridad (read-only, aditivo, sin fuga ni
falso bloqueo por segmentación) sobrevivió el ataque. Estado de cada hallazgo en este texto:

- **M1 · import circular** → RESUELTO. §4.1 mueve `_is_header`,
  `SUBSTANTIVE_PARAGRAPH_MIN_CHARS`, `HEADER_MAX_CHARS` (+ `ABSTENTION_PHRASES`) a
  `verification.py`; `scoring`/`harness` reimportan; gate byte-a-byte. Techo #6.
- **M2 · residuo doblemente ruidoso** → RESUELTO. §2.3, §4.5, §6#4 y la tabla de §7 rebajan la
  afirmación: es tendencia de FORMA sesgada en ambas direcciones, no «el número del hueco (1)».
  Matiz sobre «cota inferior» registrado en §8/D2.
- **M3 · blind spot de co-ubicación** → RESUELTO. Techo #9 nuevo en §6; declarado en §2.3 y en
  el congelamiento de §4.6; deuda medida (segmentar por cláusula) anotada.
- **M4 · puerta trasera al carve-out (regla 47)** → RESUELTO. §4.6 congela la promoción a gate
  tras excluir oraciones derivadas del mensaje del abogado; techo #10 nuevo.
- **m1 · nombres colisionan/sobre-reclaman** → RESUELTO. §3 renombra a
  `con_cita_localizada`/`con_marca`/`con_anotacion`/`con_omision`; check de rótulo en §4.7.
- **m2 · segmentar pre-edición** → RESUELTO. §4.1: `build_sentence_report` segmenta el
  `draft_original` capturado antes del bucle de ediciones.
- **m3 · estado por-cita más allá del cap 50** → RESUELTO. §4.1: lista interna SIN capar; el
  cap solo aplica a lo serializado en `detalle`.
- **m4 · doble escaneo** → RESUELTO. §4.1: `segment_sentences` recibe `protected_spans` ya
  calculados; no re-escanea.
- **m5 · `anclas` contradice `estado`** → RESUELTO. §3: se muestra `cita.fuente.referencia`;
  el campo se renombra `anclas_en_span` con semántica explícita; techo #11.
- **m6 · señal positiva solo en rama genérica** → RESUELTO. §4.7 y §7 añaden el caso de rama
  configurada exigiendo `oraciones.con_anotacion ≥ 1`.
- **m7 · framing de emisión inexacto** → RESUELTO. §5 corrige: los puntos de emisión son
  `_verify_draft` MÁS el diagnóstico bajo jurisdicción configurada (sin cubrir, D4).
- **m8 · faltaba sección de dudas abiertas** → RESUELTO. §8 nueva con D1-D5 resueltas/escaladas.

---

## Verificación cruzada Codex integrada (2026-07-24)

Segundo verificador (Codex xhigh, proveedor distinto) sobre la IMPLEMENTACIÓN. Veredicto
**APRUEBA CON CORRECCIONES**: la invariante central sobrevivió a su prueba empírica (292
comparaciones vs `HEAD`, 30 serializaciones byte a byte, 500 corridas `False` vs `True`: cero
cambios de texto/marcas/omisiones/informe clásico; sin ciclo de imports; sin promoción del
residuo a `ok`). Estado de cada hallazgo (decisiones de alcance del orquestador aplicadas):

- **M1 · bug de segmentación (`[doc 1].` fusiona, `[doc. 1]` se parte)** → CORREGIDO. La guarda
  de abreviatura ahora es `len(prev) == 1` (un solo carácter), así `prev==""` tras `]` NO guarda
  y `[doc 1].` corta; `segment_sentences` protege también los spans `_DOC_REF_RE` (una pasada de
  un patrón estrecho, no el escáner completo que m4 prohíbe) para que `[doc. 1]` no se parta; se
  absorben comillas/paréntesis de cierre finales. Mutaciones nuevas en `test_sentence_report::s_doc_refs`.
- **M2 · UI + `atribuye_sin_material`** → PARTIDO. (a) `atribuye_sin_material` se calcula en la
  capa de SCORING (`sentence_discipline_signal` → `oraciones_atribuye_sin_material`), que ya tiene
  `_PROVENANCE_PHRASES` y el contexto del turno (`documents_retrieved`); `verification.py` queda
  agnóstico. (b) La vista de UI por oración queda **DIFERIDA declarada** a la rama F3-honestidad-UX:
  el §4.3 fija «sin cambios de forma» y la pantalla no pertenece a este paso — el frontend NO se
  tocó (tipado/normalización/render de `oraciones` es trabajo de F3-UX).
- **M3 · gates débiles** → CORREGIDO. El check «byte a byte» compara ahora EXACTAMENTE `(texto
  emitido, informe clásico COMPLETO)` entre `False` y `True` en AMBAS ramas (clásica y omisión),
  con carve-out del abogado, docs fantasma y >50 citas (`test_sentence_report::p_byte_a_byte`).
- **M4 · sondas sin oráculo** → CORREGIDO. Las de forma tienen ORÁCULO DETERMINISTA con mutación
  de salida violatoria (sonda 6 intercepción; sonda 5 residuo + límite declarado bajo el piso,
  `test_sentence_report::o_oraculos`); la sonda 4 (implicación semántica pura) se DECLARA
  expresamente REVISIÓN HUMANA / juez del banco en `cases.py`, nunca medición automática.
- **m1 · spans vacíos + solo `===` como frontera** → CORREGIDO. Se excluyen los spans
  solo-espacio; las líneas etiquetadas del cierre son frontera por FORMA (interior de un bloque
  fenced `===`), sin hardcodear las etiquetas.
- **m2 · compactación de fuentes con `sentence_report=False`** → CORREGIDO. La fuente compacta
  solo se construye si `sentence_report` o `len(detalle) < 50`: el camino por defecto queda
  estructuralmente inerte para las citas 51+.
- **m3 · cap de citas por oración** → CORREGIDO. `citas` se serializa con tope
  (`_SENTENCE_CITES_CAP`) y reporta `citas_truncadas`; el conteo/estado usa TODAS.
