# PLAN — Principios del harness Lexia Litigio OS aplicados a MIA
# (memoria · verificación de citas · menos tokens · más rápido)

Fecha: 2026-08-07 · Estado: PROPUESTO (espera aprobación de Pipe)
Fuentes: destilado de principios de `lexia-litigio-os-harness` (66 mecanismos) × inventario de
gasto de MIA (llamadas LLM por turno, con archivo:línea). **Ningún código, texto de marca ni
color del harness se replica: solo principios.** El harness queda como sistema reservado de Pipe.

---

## El diagnóstico en una frase

Un turno de asunto en MIA hace **5-13 llamadas al modelo mayor**, re-enviando en CADA llamada
~2.400-3.600 tokens de prefijo idéntico **sin ningún caché** (la política `suscripcion` usa
`cli-claude`, que no recibe `cache_control`), pagando los documentos recuperados DOS veces
(facts y analysis), un gate LLM de citas con bucle de hasta 3 reintentos que duplica la llamada
más cara, y una cosecha (`harvest`) que corre síncrona dentro del clic de Aprobar **y cuyo
resultado hoy no se persiste ni se lee**. El harness de Lexia ya pagó estas lecciones: su
política de modelos por función ahorra ~40 % frente a todo-en-mayor, y su palanca compuesta
(sello + verificación incremental) hace que el sistema **se abarate a medida que madura**.

## Los 6 principios que se portan (sin replicar implementación)

1. **Sello como caché de verificación + verificación incremental**: lo ya auditado no se
   re-audita con LLM; solo se coteja por hash/verbatim. Cuanto más maduro el acervo, más barata
   cada corrida — y el gate no se degrada.
2. **Autenticidad no basta — tres preguntas de pertinencia**: ¿ratio o cita de segunda mano?
   ¿ramo/supuesto coinciden? ¿el contenido es compatible con la tesis? Si falla una, el
   argumento se sostiene solo en la norma.
3. **Determinismo antes del LLM**: extracción, triage, cotejo y todo lo mecánico por script;
   el modelo solo donde hay juicio. Los gates deterministas no consumen cupo.
4. **Cada función en el modelo más barato que la hace bien, con piso innegociable**: tabla
   función→nivel publicada como configuración auditable; se escala hacia arriba declarándolo,
   nunca se baja del piso (verificación adversarial y redacción de columna vertebral jamás en
   modelo menor). Log modelo≠política = corrida no apta.
5. **Divulgación progresiva con presupuesto por consulta**: mapa → índice → grep → ficha, con
   parada temprana; el peso en disco no es peso en contexto.
6. **«Lo que no tiene barrera, vuelve»**: cada optimización entra con su métrica y su gate de
   regresión (calidad primero: el alcance de lectura y el 0-sin-respaldo no pueden caer).

## Regla transversal del plan

**Toda palanca se mide antes y después** con la instrumentación que ya existe (`turn_usage`
con caché y costo real, `md["usage"]`, `latency_ms`, panel `hit_rate`, `alcance_lectura`), y
ninguna palanca pasa si degrada: 0 afirmaciones sin respaldo · alcance declarado sin caer ·
gates verdes. Los tokens brutos no son la vara: la vara es costo API-equivalente y latencia.

---

## FASE 0 — Poder medir (prerrequisito, ~½ sesión, riesgo nulo)

- **0.1 Atribución por nodo**: `metrics/usage.record()` ya recibe el alias; agregarle el
  `node` (facts/research/analysis/draft/gate/harvest) y una columna en `turn_usage`. Hoy todo
  se acumula en un solo `md["usage"]` y no se puede saber qué nodo gasta qué.
- **0.2 Baseline**: 3 turnos del caso de oro voluminoso con el desglose nuevo → tabla de
  referencia (tokens y segundos por nodo). Contra esa tabla se aprueba o se revierte cada
  palanca de las fases siguientes.

**Salida medible**: tabla baseline por nodo, versionada en `validation/`.

## FASE 1 — Ahorro determinista, riesgo nulo (1 sesión)

- **1.1 `harvest` fuera del clic de Aprobar**: hoy corre síncrono dentro de
  `POST /draft/approve` (el abogado espera ~90 s) y su reporte **ni se persiste**. Pasarlo a
  background (como ya van wiki y `## aprendido`) y **persistir el reporte como propuesta**
  para aprobación del abogado (principio: cosecha sin escritura en caliente — nunca editar la
  memoria del despacho directo). Cierra además el pendiente #1 de lentitud de la sesión 54.
- **1.2 Prompt por rol (extractos, no manual completo)**: la capa de metodología (~1.743 tok)
  entra idéntica en las 5-13 llamadas, incluso donde no aplica (gate de citas, harvest,
  triage). Cada nodo recibe SOLO el extracto de metodología de su rol, generado desde la
  fuente única (una regla se escribe una vez; el extracto se genera, no se duplica; barrera de
  sincronía extracto↔fuente). Ahorro directo: miles de tokens × llamada.
- **1.3 Releer una vez por turno, no por nodo**: la ficha del expediente (≤1.200 tok) se relee
  de disco y re-renderiza en cada nodo; cachearla en el estado del turno. Ídem
  `citation_patterns_for` (se consulta dos veces) y el texto completo de documentos en
  `_check_negative_claims` (cachear por turno: hoy es una lectura íntegra por PAR
  afirmación×documento, en serie, dentro del camino crítico).
- **1.4 Caché de embeddings de consulta**: la misma pregunta se re-embebe cada turno (Voyage
  se paga 2-3 veces/turno). Caché por hash de texto (tabla pequeña o LRU en proceso).
- **1.5 Gate LLM de citas — quitar el bucle** *(sujeto a la decisión abierta de Pipe)*:
  mientras Pipe decide si el gate LLM se queda, caparlo a UNA pasada (sin las 3 vueltas
  draft↔gate, que duplican la llamada más cara) y recortarle el prompt (no necesita las 10
  capas ni la metodología completa: necesita el borrador y el informe del muro).

**Salida medible**: −25-40 % de tokens por turno y approve <10 s de espera, sin caída de
alcance ni de gates (comparado contra la baseline de F0).

## FASE 2 — Sello y verificación incremental (la palanca compuesta, 1-2 sesiones)

La joya del harness: **el sello convierte la verificación en un activo que se amortiza.**

- **2.1 Tabla de sellos en Postgres** (por tenant, RLS): cita normalizada + fuente + hash del
  pasaje + veredicto + fecha + origen del veredicto (gate aprobado por el abogado). El muro
  determinista ya resuelve citas contra corpus y anclas `[doc n]`; ahora una cita que YA pasó
  verificación con aprobación del abogado se resuelve `VERIFICADA_SELLO` **sin gastar LLM**:
  solo se coteja hash/verbatim. Excepciones mecánicas (como en el harness): hash roto, aviso
  de vigencia, u orden del abogado.
- **2.2 El gate LLM (si se queda) solo ve lo NO sellado**: en un despacho maduro, la mayoría
  de citas de un escrito recurrente ya están selladas → el gate audita 3 citas, no 47. KPI
  nuevo en el panel: **% de citas resueltas desde sello sin re-verificación** (baseline ~0 %,
  meta creciente).
- **2.3 Tres preguntas de pertinencia** como defectos tipificados del informe (segunda mano /
  ramo ajeno / doble filo contra la tesis): el muro ya segmenta por oración; estas tres
  entran como AVISO en el informe que ve el abogado (nacen como aviso, suben a muro solo si
  no dan falsos positivos — regla vigente de MIA).
- **2.4 Ya cumplido y se ratifica como contrato**: verificador independiente sin herramientas
  de red, cobertura 100 % sin muestreo, retirar-no-sustituir, y el informe acompaña siempre
  la entrega.

**Salida medible**: en el caso de oro corrido 2 veces, la segunda corrida gasta menos en
verificación que la primera (el sello amortiza), con 0 sin respaldo intacto.

## FASE 3 — Enrutamiento por función con piso innegociable (1 sesión)

- **3.1 Tabla función→nivel como configuración** (no convención): hoy TODOS los nodos usan
  `task="main"` con el mismo alias. Propuesta inicial (a calibrar con la baseline de F0):
  triage/clasificación → ligero (ya) · facts/research → nivel medio · analysis/draft →
  **mayor (piso)** · verificación adversarial → **mayor (piso)** · harvest/formateo → ligero.
  El piso se enumera explícito y nunca se baja; ante ambigüedad real se ESCALA y se declara.
- **3.2 Barrera de política**: si el log registra que una función del piso corrió en modelo
  menor, el turno se marca no apto (mismo principio del router enforceado del harness). En
  `suscripcion` no hay dólares sino cuota: racionamiento (esperar/derivar), jamás degradar
  el gate.
- **3.3 Documentos una sola vez**: los 128 fragmentos entran enteros a facts Y a analysis.
  Palanca con riesgo (calidad primero): analysis recibe hechos + solo los fragmentos que
  facts citó como relevantes + acceso de relectura dirigida. SOLO se aplica si la baseline
  demuestra que el recall de datos enterrados (hoy 1/3) no cae; si cae, se revierte.

**Salida medible**: reparto por nivel visible en el panel (hoy imposible); costo por turno
−15-25 % adicional sin tocar el piso.

## FASE 4 — Memoria con divulgación progresiva (1 sesión, después de las anteriores)

- **4.1 Knowledge por escalones**: hoy el knowledge entra hasta 30.000 tok (15 % de ventana)
  por turno. Pasar a: índice ligero (títulos+resúmenes de 1 línea) siempre + ficha completa
  solo de las 3-5 notas que el ranking justifica + presupuesto explícito por consulta (si va
  a superar unos pocos KB, se re-plantea la búsqueda en vez de leer más).
- **4.2 Estado de la nota como control de flujo**: verificada / pendiente / obsoleta en el
  knowledge del despacho, y el prompt lo declara — lo pendiente se cita con marcador, lo
  obsoleto nunca se propone (hoy todo entra igual).
- **4.3 Playbooks con tope**: el contenido completo de los activos entra al draft sin tope
  duro; ponerle presupuesto y parada temprana como al knowledge.

**Salida medible**: tokens de knowledge/turno ↓ con calidad de respuestas estable (mismo
gate ciego del baseline).

## Decisiones que son de Pipe (no se implementa sin su palabra)

1. **El gate LLM de citas de `f264b1e`**: ¿muro solo, o muro + gate LLM acotado a lo no
   sellado (F2.2)? — ya estaba pendiente desde la sesión 55.
2. **F3.3 (documentos una vez)**: toca la calidad de lectura; se hace solo con la medición
   delante y con derecho a reversa.
3. El orden de las fases si algún caso real lo cruza.

## Qué NO se hace (aprendido del harness, para no repetir sus errores)

- No portar etapas a otra familia de modelos por ahorro (fragmenta el pipeline y duplica
  calibración — antipatrón registrado allá).
- No optimizar nada sin baseline por nodo (F0 va primero, siempre).
- No bajar del piso de calidad jamás: el ahorro se hace en lo mecánico, nunca en el
  razonamiento ni en los gates.
- No replicar del harness ni código, ni identidad, ni colores: es sistema reservado de Lexia.

## Estimación de conjunto

| Fase | Esfuerzo | Ahorro estimado | Riesgo de calidad |
|---|---|---|---|
| F0 medición | ½ sesión | — (habilita todo) | nulo |
| F1 determinista | 1 sesión | 25-40 % tokens/turno + approve <10 s | nulo |
| F2 sello incremental | 1-2 sesiones | creciente con la madurez (la verificación fue el 37 % del gasto en el harness) | nulo (el sello endurece, no relaja) |
| F3 enrutamiento | 1 sesión | 15-25 % adicional | bajo (piso explícito + barrera) |
| F4 memoria progresiva | 1 sesión | knowledge/turno ↓ | bajo (gate ciego) |

Referencia del harness: política por función ya activa ≈ 40 % de ahorro frente a
todo-en-mayor; escalones de costo por escrito allá: 40-60 USD → 18-30 → 8-18 → **6-14 con
acervo verificado maduro**. La meta de MIA es la misma curva: **que cada expediente
recurrente sea más barato que el anterior sin aflojar un solo gate.**
