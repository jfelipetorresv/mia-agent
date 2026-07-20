# HANDOFF — Mia (traspaso a Cursor)

---

# CIERRE — 2026-07-20 (final de sesión) · 15 commits, verificación adversarial y primera prueba en vivo

Rama `feat/fase1-inc1-cleanup-scaffolding`. **15 commits, NINGUNO pusheado** (Pipe aprueba el push).
**Esta entrada es la más reciente: empezar por aquí.** La entrada siguiente (« Ola 2 ») se escribió a mitad
de sesión y cubre solo los siete primeros commits; sigue siendo válida en el detalle, pero **esta la
sustituye como punto de partida**.

Retrospectivas de la sesión, en el vault (no en el repo):
`01-operacion\retrospectivas\retrospective-2026-07-20-003-*.md` (primera mitad) y `-005-*.md` (segunda mitad,
con los errores de método y su corrección).

---

## 0 · ENCARGO PARA FABLE — leer esto antes de ejecutar nada

Pipe quiere que **Fable revise el plan, busque mejoras y construya sobre él** en vez de limitarse a
ejecutarlo. Este es el encargo, y va primero a propósito.

**Lo que hay que revisar no es la lista de tareas: es la tesis del producto.** Tras esta sesión, la tesis
operativa de MIA quedó así:

> Un agente que lee el expediente entero, razona con el criterio del despacho, y **no puede afirmar nada que
> no pueda respaldar** — porque un guardián determinista, no la buena voluntad del modelo, marca lo que no
> está respaldado.

Las tres preguntas que Fable debería responder antes de tocar código:

1. **¿La lectura agéntica es el camino correcto, y hasta dónde?** Pipe lo propuso él mismo:
   *"no se puede establecer como funciona Claude code o codex? al fin y al cabo su motor será uno de ellos"*.
   Se construyó el andamiaje (apagado por defecto) y se midió: con un modelo que se conforma, ahorra 4,3×;
   con uno que amplía siempre, **cuesta 3,7× más**. La pregunta abierta no es técnica sino de diseño:
   ¿el bucle debe poder *reformular* la consulta al ver los primeros resultados —que es lo que hace valiosa
   la búsqueda agéntica en código— o solo pedir *más de lo mismo*? Hoy hace lo segundo. **Ahí puede estar
   la diferencia entre un truco de coste y una capacidad nueva.**
2. **¿El guardián de citas está en la capa correcta?** Hoy es un escáner de patrones sobre el texto final.
   Encontró 1 de 5 citas en la prueba en vivo; las otras cuatro las marcó el modelo obedeciendo la
   instrucción — justo aquello de lo que el guardián existe para no depender. Ampliar patrones es el arreglo
   obvio. **La pregunta mejor es si el guardián debería operar sobre lo que el modelo AFIRMA en vez de sobre
   lo que ESCRIBE** — por ejemplo exigiendo que toda cita venga acompañada de su ancla al material sellado,
   en vez de buscarla a posteriori con expresiones regulares.
3. **¿Qué significa "vendible a otro despacho" y qué falta de verdad?** Esta sesión destapó que el producto
   ofrece 21 países y tiene contenido jurídico real para uno. Antes de sumar features conviene decidir si el
   siguiente paso es **profundidad en un ordenamiento** o **anchura verificable en varios**. No es lo mismo,
   y hoy el producto insinúa lo segundo mientras entrega lo primero.

**Cómo debería trabajar Fable en esta sesión:** el método que funcionó fue *un escritor por archivo, frentes
disjuntos, y un verificador adversarial independiente al final de cada frente*. Unos 40 agentes, cinco
workflows, cero colisiones. **La fase de verificación adversarial fue, con diferencia, la de mayor
rendimiento**: encontró seis defectos graves en trabajo que sus propios autores daban por bueno, incluidos
dos frentes que hubo que rechazar y rehacer. No la recorte.

Y una regla que esta sesión compró cara: **prueba de mutación obligatoria**. Un check nuevo no vale hasta
que se demuestra que puede ponerse rojo. Aparecieron tres gates verdes que no probaban nada en una sola
semana, uno de ellos roto desde el 17 de julio sin que constara.

---

## 1 · Los 15 commits, en orden

| Commit | Qué |
|---|---|
| `aaa3d1a` | Los agentes del despacho vuelven a salir como chips (el corte a 6 guías los tapaba) |
| `96d3449` | Tres componentes que literalmente desaparecían en tema oscuro |
| `872a7ec` | Diseño del perfil del despacho + trampas del entorno Windows |
| `00c4c17` | **Lectura adaptativa**: muere el literal `top_k=8`; se deriva del material, el presupuesto y la pregunta |
| `9516833` | **Guardián de citas en proyectos** + el guardián deja de certificar en verde citas inventadas |
| `03d861f` | **Ordenamiento aplicable y procedencia** en el prompt |
| `444d3a1` | **Rediseño por capas**: tokens, primitivas, pantallas; Panel primero y Panel que sirve |
| `74ed135` | Traspaso de mitad de sesión |
| `fb30664` | `b5` de context_recovery llevaba roto desde el 17-jul (cambio de formato del system) |
| `479f78f` | La medida del prompt contaba el envoltorio, no el texto |
| `513a50b` | **Andamiaje de lectura agéntica**, APAGADO por defecto |
| `91bd2e0` | Causa raíz de las dos suites de carpetas + cobertura de carpeta-de-proyecto + presupuesto de la Sala |
| `c980704` | **Perfil del despacho** rediseñado (rechazado por un verificador y rehecho) |
| `3063df5` | **El recorte por presupuesto** dejaba de leer la mitad de lo recuperado |
| `f791596` | La lectura agéntica deja de leer un tercio y de vender ahorro que no tiene |

## 2 · Lo verificado EN VIVO contra el modelo real (lo único que cierra la brecha de fondo)

Es la primera vez en varias sesiones que se prueba con MIA encendida y un modelo de verdad.

| Escenario | Antes de la sesión | Después |
|---|---|---|
| Despacho **sin país**, expediente vacío, pregunta por requisitos de validez de un contrato | Citaba cinco artículos de un país concreto, transcribía verbatim, ofrecía consultar una base normativa nacional, y afirmaba que era *"conocimiento consolidado del despacho"* estando vacío | **Cero artículos, cero códigos, cero países.** Razona la institución jurídica y pide el ordenamiento para poder citar |
| Despacho **con país configurado**, misma pregunta | — | Cita su norma con normalidad, **cada cita con su marca**, y declara: *"salen de mi memoria jurídica general, no de un texto que me hayas cargado ni de una base verificada del despacho"* |

**Matiz honesto:** el guardián determinista detectó **1 de 5** citas; las otras cuatro las marcó el modelo
obedeciendo. El resultado fue correcto, pero por la razón equivocada. Ver el pendiente correspondiente.

**Matiz honesto 2:** la fuga original **no se pudo reproducir** en tres intentos con el código anterior. La
lectura correcta no es que no existiera —está capturada— sino que es **intermitente**, lo que la hace más
peligrosa, no menos.

## 3 · Los seis defectos graves que encontró la verificación adversarial

Ninguno lo vio su implementador. Este es el argumento entero a favor de esa fase.

1. **El guardián certificaba en verde citas inventadas.** Con "Decreto 1082 de 2015" en el expediente, un
   "Decreto 108" alucinado salía marcado **"Con respaldo"**, con visto verde y atribuido a archivo y folio
   reales. Cotejo bidireccional sin respetar fronteras numéricas. **Preexistente**: afectaba ya a los asuntos.
2. **El recorte por presupuesto desperdiciaba la mitad del cupo** (de 200.000 se quedaba en 35.000 teniendo
   70.000) porque no descontaba el peso del sellado y recortaba dos veces. Medido: utilización del **50 % al 99 %**.
3. **Y tiraba primero lo que el modelo pidió**: de 12 ampliaciones sobrevivían 2. La lectura agéntica se
   anulaba a sí misma. Ahora sobreviven 6.
4. **El Panel inventaba ceros** cuando fallaba la fuente de cifras. Un cero es una afirmación, no un dato ausente.
5. **La regla de movimiento reducido congelaba los indicadores de trabajo en curso**: MIA parecería colgada.
6. **El perfil del despacho dejaba fuera al propio dueño** con un error sin salida, y a cualquier despacho de
   un país no listado sin poder darse de alta. Frente **RECHAZADO** y rehecho.

## 4 · Estado del entorno (verificado al cerrar)

- **Base portable ARRIBA** en `127.0.0.1:55432`. Binarios `postgres16-portable` (NO el `-full`).
- **44 de 44 migraciones aplicadas.** Se descubrió que 044, 045 y 046 **no estaban en el registro** —la 044,
  salud de guías, **nunca había corrido**— y el blindaje del instalador habría frenado el arranque.
- **Cerebro** en `:8000` con TODO el código del día cargado (se reinició al final). **NO recarga en caliente.**
- **Motor** LiteLLM en `:4000`. **Pantalla** en `:3100` (sí recarga en caliente).
- **Los servicios SÍ sobreviven** lanzados con el mecanismo de fondo del harness (`run_in_background`). Lo que
  muere es `Start-Process` desde la sesión. Esto destrabó la verificación visual, dada por imposible durante
  sesiones. Para probar código nuevo sin reiniciar la instancia en uso: **levantar una segunda en otro puerto**.
- **Despachos de prueba** creados: `verificacion.visual@local.test` / `VerificaVisual2026` (con un asunto y un
  proyecto), `despacho.conpais@local.test` y `alta.nueva@local.test`. **Conviene borrarlos.**
- **Recorrido headless de las 11 rutas**: todas 200, cero errores de consola, cero peticiones fallidas.
  Script en el scratchpad (`visual/tour.mjs`, `visual/onb2.mjs`).

## 5 · Gates

**HALT verdes al cierre**: `test_rls` 19/19 · `check_env_pins` 10/10.

Verdes tras los cambios: `retrieval_adaptativa` 59/59 (nuevo) · `lectura_agentica` 66/66 (nuevo) ·
`carpeta_proyecto` 31/31 (nuevo) · `context_recovery` 52/52 · `warroom` 79/79 · `projects` 59/59 ·
`doc_citation_guard` 38/38 · `jurisdiction_agnostic` 104/104 · `argument_engine` 66/66 ·
`retrieval_knowledge` 36/36 · `document_pipeline` 45/45 · `untrusted_content` 28/28 ·
`context_references` 43/43 · `e2e` 58/58 · `soul_guard` 47/47 · `profile_full` 51/51 ·
`onboarding_horizontal` 13/13 (estaba 7/11) · `matter_folder` 37/37 · `matter_folders_multi` 30/30 · `tsc` limpio.

**NO se corrió la regresión completa** (no cabe): por tramos, las tocadas y sus adyacentes.

## 6 · NO VERIFICADO — honestidad

- **Ningún gate corre contra un modelo real.** La prueba en vivo de §2 fue manual y puntual, no un banco de
  casos. **Es la brecha de fondo del proyecto** y la señalaron todos los verificadores.
- **La lectura agéntica nunca ha corrido con un modelo real.** Si sabe decir "suficiente" en la pregunta
  puntual es exactamente lo que decide si sirve, y está sin probar. Por eso nace apagada.
- **Coste y latencia reales por turno**: no medidos. Las cifras del repo son estimaciones del propio gate.
- **El paso de país con campo libre**: verificado por código y por captura, **no recorrido a mano** por una
  persona.
- **`next build` no se corrió** (regla del repo). Sí `tsc`.

## 7 · Pendientes, por valor

1. **Ampliar el guardián a citas abreviadas.** Detectó 1 de 5 en vivo (`arts. 1516 y ss. C.C.`, siglas de
   código). Las formas `arts. N y ss.` son transversales al Civil Law hispano y van en el código; **las siglas
   concretas de cada código van en el pack, nunca en el código**.
2. **Selector de países honesto** — en curso al cerrar la sesión, en `frontend/app/_components/CountrySelector.tsx`
   (21 países cableados, un solo pack real). **Verificar si quedó y commitearlo.**
3. **Banco de casos + benchmark ciego** contra el modelo vivo. Cierra la brecha de §6.
4. **Segundo paso de la lectura agéntica**: que el bucle pueda reformular la consulta, no solo pedir más
   (ver §0.1). Y medir con modelo real antes de encender la bandera.
5. **Riesgos abiertos señalados por verificadores y no cerrados**: comentario obsoleto en `warroom.py:78-81`
   (afirma que el recorte parte por la mitad, ya no es cierto); margen cero del estimador de tokens de la Sala;
   `init_durable_jobs` aplicado dentro de un bloque de aserciones en `test_matter_folders_multi.py`;
   fragmentación del reparto (trozos de ~50 tokens, nadie ha medido si sostienen una cita).
6. **Sección `## aprendido` del perfil**: que se llene sola desde el trabajo real vía `update_soul`. Es la idea
   central del rediseño del perfil y es lo único que quedó sin implementar.
7. **`docs/diseno-soul-onboarding.md`** tiene el plan completo del perfil; los pasos 1-6 están hechos, el 7 no.

## 8 · Pendiente de Pipe (no es código)

- **Aprobar el push** de los 15 commits.
- **Registrar las apps OAuth** de Gmail/Outlook/OneDrive (sigue pendiente de sesiones anteriores).
- **Decidir** qué hacer con `C:\Users\USER\Desktop\Informe-Lucy-*.json` (son de `lexter-os`, no de MIA).
- **Decidir** entre profundidad en un ordenamiento o anchura verificable en varios (ver §0.3).

---

# CIERRE — 2026-07-20 · Ola 2: lectura del expediente, guardián de citas, jurisdicción y Panel

Rama `feat/fase1-inc1-cleanup-scaffolding`. **7 commits nuevos hoy, NINGUNO pusheado** (Pipe aprueba el push).
Esta entrada es la más reciente: **empezar por aquí.**

## 1 · Entorno: dos cosas que cambiaron de verdad

**(a) Por primera vez se logró mantener MIA viva desde la sesión del asistente.** Los servicios sobreviven
si se lanzan con el mecanismo de fondo del harness (`run_in_background`), a diferencia de `Start-Process`,
que muere al terminar el comando. Esto destrabó la **verificación visual**, que llevaba sesiones dándose por
imposible: hoy se recorrieron las 11 pantallas con navegador real, se tomaron capturas y se forzaron caídas
de servidor para ver cómo reacciona el producto. Documentado en `docs/trampas-entorno-windows.md` §3.

**(b) Se encontró y cerró un bloqueante silencioso en la base de datos.** Las migraciones **044, 045 y 046
no constaban en el ledger** `mia_schema_migrations`: la 045 y la 046 se habían aplicado a mano en la sesión
anterior sorteando el landmine de `setup_db.ps1`, y **la 044 (salud de guías) nunca había corrido**.
`/health` reportaba **41 de 44** y el blindaje del instalador habría frenado el arranque en una máquina
limpia. Se aplicaron por el runner real. Verificado hoy en vivo:

```
{"status":"ok","db":true,"pgvector":"0.8.2","migrations_expected":44,"migrations_applied":44,
 "checkpointer":true,"provenance_ready":true}
```

## 2 · Qué se commiteó hoy

| Commit | Qué |
|---|---|
| `00c4c17` | **Lectura adaptativa del expediente.** Muere el literal `top_k=8`. El tamaño de lectura se deriva en cada turno de tres señales: cuánto material hay indexado, cuánto cabe en el presupuesto real del nodo más estrecho, y qué tan exigente es la pregunta (heurística determinista, sin modelo). Piso inviolable en 8. **Trampa cerrada que habría arruinado el cambio en silencio:** `hnsw.ef_search` nunca se fijaba, y con el valor de fábrica de pgvector (40) subir los candidatos por encima de ~40 **degrada el recall sin avisar**; ahora se fija en la misma transacción. Además dedup, tope por documento y expansión a fragmentos contiguos (apagada por defecto). Suite nueva `test_retrieval_adaptativa` 59/59. |
| `9516833` | **Guardián de citas en PROYECTOS** (no lo tenía: un proyecto podía afirmar normas y jurisprudencia sin una sola marca `[VERIFICAR]`). **Detalle que hace que el arreglo sirva:** se movió el punto de emisión del evento SSE para que el texto salga DESPUÉS de verificarse — sin eso, el nodo nuevo habría sido decorativo. **Y el arreglo del defecto más grave de la sesión** (ver §4). Gates: `test_projects` 59/59 · `doc_citation_guard` 38/38. |
| `03d861f` | **Ordenamiento aplicable y procedencia.** L3 declara ahora bajo qué reglas trabaja el despacho, en dos ramas (sin ordenamiento declarado: prohibición de nombrar articulado, códigos, corporaciones o bases normativas de un país; con ordenamiento declarado: cita el suyo con normalidad). Más una política de procedencia: no se atribuye al expediente ni al despacho nada que no haya llegado sellado en ese turno. **Y se cableó la jurisdicción del despacho al estado en el primer nodo del turno** — antes solo llegaba por el nodo de investigación, que en proyectos nunca corre. `jurisdiction_agnostic` pasa de 75 a **104/104**. |
| `444d3a1` | **Rediseño por capas.** Capa 1 tokens (escala tipográfica semántica de seis roles, tres radios, dos elevaciones, escala de espaciado, contraste subido donde caía bajo el mínimo accesible — eran justo los avisos de responsabilidad — y regla global de movimiento reducido, que **no existía en ninguna parte del producto salvo la bienvenida**). Capa 2 primitivas (`Card` rescatada, `PageShell`, `SectionTitle`, `lib/motion.ts`). Capa 3 pantallas: **Panel primero en la navegación y aterrizaje del login**, consumiendo lo que ya existía construido y sin exponer (`/api/setup/status` con los 7 pasos en lenguaje llano, salud de guías, gasto del mes, tareas programadas). |
| `872a7ec` | `docs/diseno-soul-onboarding.md` (rediseño del perfil del despacho, **diseñado no implementado**) + `docs/trampas-entorno-windows.md`. |
| `96d3449` | **Tres componentes literalmente desaparecían en tema oscuro** (`MissionBoard`, `MicButton`, `MailboxSectionLoader`): usaban la paleta cruda de Tailwind sin un solo token, así que en oscuro eran una isla gris clara dentro del negro. Se renderizan en pantallas primarias. |
| `aaa3d1a` | Los agentes del despacho no salían nunca como chips en el chat vacío: el corte a 6 guías se aplicaba ANTES de anexar las personas. Capacidad construida que el abogado no podía ver. |

## 3 · La decisión de Pipe que redefine el siguiente bloque

Se le presentó que la lectura adaptativa, con los valores de fábrica, **multiplicaba el gasto de IA por
turno entre 11 y 20 veces**. Su respuesta, textual:

> *"no se puede establecer como funciona Claude code o codex? al fin y al cabo su motor será uno de ellos"*

Es superior a las tres opciones que se le ofrecieron. En vez de calcular de antemano cuánto leer, **exponer
la búsqueda como una herramienta y dejar que el modelo pida más material cuando le falte**, igual que hacen
las herramientas agénticas de código. Así una pregunta trivial cuesta poco, una difícil lee lo que necesite,
y nadie tiene que adivinar una proporción: el coste se ajusta solo.

**Queda como el rediseño pendiente de más valor — "lectura agéntica".** Mientras tanto la cobertura quedó
en `0.22` (≈7 veces más lectura que antes, en vez de ≈20), conservando la promesa que custodia el gate `a1`:
en un expediente grande Mia lee una fracción real del material, no una muestra simbólica. Se probó `0.15` y
rompía justo esa promesa. El valor es **provisional** y así está escrito en `backend/mia/config.py`.

## 4 · Los hallazgos graves (lo más valioso de la sesión)

**(a) El guardián certificaba en verde citas inventadas.** Defecto **PREEXISTENTE** —afectaba ya al flujo de
asuntos que el despacho usa— que el cambio de hoy agravaba al multiplicar las claves cosechadas. El cotejo de
respaldo era bidireccional y no respetaba fronteras numéricas: con *"Decreto 1082 de 2015"* en el expediente,
un *"Decreto 108"* alucinado salía marcado **"Con respaldo"**, con visto verde y **atribuido a un archivo y
un folio reales**. Igual con *"Ley 143"* dentro de *"Ley 1437 de 2011"* y *"Sentencia C-35"* dentro de
*"C-355 de 2006"*. Es la regla dura del producto al revés: marcar de más es inofensivo, respaldar de más
destruye la única razón por la que un abogado confiaría en esto. **Lo encontró un verificador adversarial
ejecutando una sonda, no leyendo.** El test que decía cubrirlo solo ejercitaba la dirección ya blindada.

**(b) Fuga de jurisdicción capturada en vivo.** Un despacho de prueba vacío y sin país configurado preguntó
qué exige la ley para que un contrato sea válido, y recibió derecho de un país concreto: cinco citas de
articulado, una transcripción verbatim entrecomillada y el ofrecimiento de consultar una base normativa
nacional. Remató afirmando que era *"conocimiento consolidado del despacho"* — con el despacho vacío.
**Matiz honesto:** el agente que endureció el prompt **no pudo reproducirla en tres intentos** con el código
anterior. La lectura correcta no es que no existiera, sino que **es intermitente** — lo que la hace más
peligrosa, no menos, porque una fuga que aparece una de cada varias veces es la que se cuela a un escrito.
Confirma que la instrucción sola no basta y que el guardián determinista es imprescindible.

**(c) El Panel inventaba ceros** cuando la fuente de cifras fallaba: con el servidor de cifras caído afirmaba
*"0 borradores aprobados · 0 horas ahorradas · USD 0.00"*, indistinguible de un dato real. **Un cero es una
afirmación, no un dato ausente.** Era además una regresión: el código anterior se quedaba en esqueleto —feo,
pero nunca mentía. Se arregló y se demostró en navegador forzando la caída de la fuente en cinco escenarios.

**(d) La regla de "reducir movimiento" congelaba los indicadores de trabajo en curso.** Con esa preferencia
activada (ajuste común de Windows), el abogado veía una rueda detenida y no podía distinguir *"analizando"*
de *"colgada"*. Habría reenviado la consulta creyendo que MIA se colgó.

**(e) El dedup borraba la fuente primaria** cuando un documento del expediente citaba a otro: la pieza
original desaparecía del prompt con su archivo y su folio, y Mia solo podía anclar al escrito que la citaba.

## 5 · NO verificado (honesto)

- **La regresión completa de suites NO se corrió.** No cabe en el tiempo disponible; se corrieron **por
  tramos** las suites tocadas y sus adyacentes. La revalidación final dejó 11 gates en verde, incluidos los
  dos HALT (`test_rls` 19/19, `check_env_pins` 10/10).
- **Ningún gate corre contra un modelo real.** Que la instrucción de ordenamiento **de verdad suprima el
  prior del modelo está SIN PROBAR**: exige un benchmark ciego en vivo. **Es la brecha más grande de la
  sesión.** Todo lo demás va con modelos dobles.
- Los conteos de tokens salen de una heurística del propio test, no de un tokenizador real: todas las
  conclusiones de presupuesto heredan ese error.
- **No se midió coste ni latencia reales** del cambio de lectura, ni el recall del HNSW con `ef_search` alto
  (se confirmó que el parámetro se fija, no que el ranking mejore).
- **La rama sigue sin push.** Pipe aprueba.
- El rediseño del perfil del despacho está **diseñado y documentado, no implementado**.

## 6 · Riesgos señalados por los verificadores y NO cerrados

1. **`backend/mia/agents/warroom.py`** renderiza documentos **sin presupuesto ni recorte**, y ahora puede
   recibir muchos más fragmentos que antes. Es el candidato más probable a desbordar la ventana.
2. **`context_recovery.py`** recorta por mitades fijas en vez de por presupuesto.
3. **La Sala de estrategia podría quedar en la rama restrictiva de jurisdicción**: llama a
   `build_graph_system` con un estado que no viene del grafo y puede no traer `jurisdictions`.
4. `cn()` usa `twMerge` sin configurar, así que toda la escala tipográfica nueva se clasifica como color y
   un token de tamaño combinado con uno de color **pierde el tamaño en silencio**. Arreglo de una línea
   (`extendTailwindMerge`), no aplicado.
5. En 3 de las 4 políticas de modelo soportadas **no hay prefix caching**, así que las capas nuevas de
   prompt se pagan enteras en cada llamada. La conclusión de coste sobrevive (419 tokens sobre 200.000),
   pero el mecanismo que se citó como justificación es falso para la mayoría de instalaciones.
6. Siguen abiertas las **2 suites rojas de carpetas** (`test_matter_folder`, `test_matter_folders_multi`) y
   **no existe ni un solo test de "carpeta vinculada a un PROYECTO"** — que es justo el escenario que falló
   en producción.

## 7 · Pendiente de Pipe (no es código)

- Decidir el **push** de la rama.
- **Lectura agéntica**: es su propia decisión de diseño y el bloque de más valor pendiente (§3).
- Aparecieron en su escritorio **dos archivos ajenos a MIA** (`Informe-Lucy-*.json`, del producto
  `lexter-os`): pendiente de que decida qué hacer con ellos.
- Sigue pendiente de sesiones anteriores: registrar las **apps OAuth** de Gmail/Outlook/OneDrive y verificar
  el inc. 3 en vivo.

---

# CIERRE — 2026-07-19 (2ª sesión) · Primer arranque en vivo + auditoría de usabilidad y RAG

Rama `feat/fase1-inc1-cleanup-scaffolding`. **14 commits, NINGUNO pusheado** (Pipe aprueba el push).
Esta entrada es la más reciente: **empezar por aquí.**

## 1 · Estado del entorno (verificado en vivo hoy)

- **Base de datos portable ARRIBA** en `127.0.0.1:55432` (binarios `postgres16-portable`, NO el `-full`, cuyos backends mueren con 0xC0000142). El `.env` ya apunta ahí (`PG_PORT=55432`).
- **Migraciones 045 y 046 APLICADAS a la base real** (se aplicaron directo, sorteando el landmine de `setup_db.ps1` — ya arreglado, ver §5). Verificado: `chunks.folio_ancla`, `documents.metadata_sugerida`, `tipo/parte/folio_radicado/fecha_documento` existen.
- **`test_rls` 19/19 PASS** contra esa base con las columnas nuevas. El gate crítico está verde.
- **Cuenta de Pipe:** su correo tenía un registro viejo y vacío del 20-jun (despacho "lexia", 0 asuntos/0 documentos) que **se borró** con su OK; se registró de nuevo → tenant **"Torres"** (`fddce561-25c0-451e-b281-18e646269042`).
- **Caso real de prueba:** proyecto **"Proceso 2"** (`a7645d60-…`) con la carpeta `D:\Jurisprudencia seguros\Cumplimiento` vinculada e **indexada correctamente**: 3 documentos, **622 fragmentos, ~743.600 caracteres** (≈370 páginas). NO eran escaneados.

## 2 · El hallazgo central (por qué "MIA no revisa bien la información")

Con 743.600 caracteres de jurisprudencia cargados, **MIA leía 8 fragmentos ≈ 9.600 caracteres por pregunta = el 1,3 %**. No es que analizara mal: es que casi no leía. Además, en proyectos, el conocimiento del despacho se recuperaba y se descartaba, y los fragmentos llegaban sin nombre de archivo. **Tres causas, todas verificadas en código y las tres ya corregidas** (commit `5d3ca3d`) salvo el volumen de lectura (ola 2).

## 3 · Qué se arregló y commiteó hoy

| Commit | Qué |
|---|---|
| `5d3ca3d` | **(a)** `work_node` (grafo de PROYECTO) ahora SÍ entrega el conocimiento del despacho al modelo — antes lo recuperaba, lo pagaba y lo tiraba, y encima L7 le *afirmaba* al modelo que lo tenía. **(b)** El sello pasa de `<<<DOC 1>>>` a `<<<DOC 1 · archivo.pdf · folio 12>>>` (`retrieval.py` ahora trae `filename` y `folio_ancla`): MIA puede citar por nombre y folio. Folio NULL nunca se inventa. **(c)** `GET /wiki/concepts/{n}` ya no devuelve el YAML crudo (nuevo `get_concept_view`). **(d)** Nuevo `frontend/components/MiaMarkdown.tsx`: parser propio, **cero dependencias**, cero `dangerouslySetInnerHTML`, tolerante a SSE; cableado en chat/asuntos/proyectos/memoria y **unifica el resaltado `[VERIFICAR]`** que estaba duplicado y divergente. |
| `1d34031` | **MIA agnóstica**: fuera el sesgo de país (Colombia ya no va primero; eliminada la insignia "Conocimiento jurídico profundo") y de área (ejemplos del onboarding ya no dicen "seguros"/"Aseguradoras (HDI, Zurich, SURA…)"). |
| `3ab3714`, `9c84682` | Arranque de dev: ventanas con `-NoProfile` y minimizadas + lanzador `Abrir Mia.cmd`. |
| `fdad1f1` | Retrospectiva `docs/retrospectives/retrospective-2026-07-19-001-*` + arreglo del chequeo de pgvector de `setup_db.ps1`. |
| `0d7bb6b`, `c447c8c`, `b99c2d0`, `06a4877`, `58ad4c6` | `docs/prueba-en-vivo-inc3.md`: guía de prueba en vivo + las trampas reales del entorno. |

Suites verificadas tras los cambios: `retrieval_knowledge` **36/36** (se corrigió una assertion que esperaba el sello viejo), `untrusted` 28/28, `projects` 33/33, `document_pipeline` 45/45, `citation_guard` 19/19, `context_references` 43/43.

## 4 · OLA 2 — lo siguiente, YA DECIDIDO por Pipe (arrancar por aquí)

1. **Lectura suficiente.** Decisión literal de Pipe: *"debe poder leer lo que se requiera para dar respuesta completa y suficiente; la información que esté en la carpeta o lo que se pida"*. NO es subir una constante: es **recuperación adaptativa**. Hoy `retrieve_rrf` usa `top_k=8, candidates=20` fijos (`agents/retrieval.py:80-81`) y nadie los sobreescribe; el llamador es `intake_node` (`graph.py:883`). El nodo YA tiene shrink por presupuesto (`graph.py:1446-1448`), así que subir es seguro: si no cabe, `context_recovery` recorta solo. Dimensionar contra el caso real (622 fragmentos disponibles).
2. **Guardián de citas también en PROYECTOS.** Hoy `verification_node` solo está cableado en `build()` (`graph.py:1600, 1616-1617`); `build_project` (`graph.py:1623-1645`) es START→intake→delegación→work→END: **un proyecto puede afirmar normas y jurisprudencia sin una sola marca `[VERIFICAR]`**. Pipe: *"debería poder confirmar las normas y jurisprudencia; es parte de la razón de ser de MIA"*. Requiere que `_verify_draft` opere sobre `state['reply']`, no solo `state['draft']` (`graph.py:1382-1387, 1397`).
3. **Panel primero — vía RÁPIDA** (elegida por Pipe): subir Panel al primer lugar en `frontend/app/_components/nav.ts` y que el login aterrice ahí (`login/page.tsx:33`). NO mover la ruta raíz todavía (eso es la vía completa, 9 archivos de enlaces).

## 5 · Trampas del entorno (documentadas en `docs/prueba-en-vivo-inc3.md`)

- **MIA NO se mantiene viva si la lanza el asistente**: los servicios mueren al terminar el comando (probado 3 veces, incluso desacoplando por WMI). **Pipe debe abrirla con `Abrir Mia.cmd`** (doble-clic) desde su sesión.
- **`statusline.js` zombis**: había **2.060 procesos node** huérfanos de Claude Code ahogando la máquina (terminal a 5736 ms, Next.js sin poder servir chunks). Limpieza: matar SOLO los `statusline.js` (2086 → 24; terminal a 1917 ms). **Causa raíz sin diagnosticar** — volverán.
- **`ChunkLoadError`**: tuvo TRES causas distintas en la sesión (saturación → recompilación de 50 s tras borrar `.next` → caché del navegador). Si el servidor devuelve 200 en los 6 chunks, el problema es del navegador: abrir **`http://127.0.0.1:3100`** (otro origen ⇒ caché limpio).
- **`setup_db.ps1` ARREGLADO** (`fdad1f1`): su chequeo de pgvector apuntaba al PostgreSQL del sistema (5432, ruta fija) en vez de la base del `.env`, y abortaba las migraciones con una falsa alarma.

## 6 · Auditoría de usabilidad — pendientes con diagnóstico hecho

Los 10 puntos que reportó Pipe fueron auditados (8 agentes + Codex). Lo ya diagnosticado y **no** implementado:

- **Panel**: se siente vacío por una decisión escrita del 2026-07-09 (dejar solo lo accionable y mandar conexiones/salud a Configuración) — Pipe la revierte. **Casi todo ya existe mal expuesto**: `GET /api/setup/status` devuelve 7 pasos en lenguaje llano (perfil, motor de IA, notas, carpetas, guías, Telegram, voz) con estado/detalle/enlace y **solo lo consume `configurar/page.tsx`**. También sin usar: `/api/playbooks/health/summary`, `/api/matters/{id}/daily`, gasto del mes completo, `connectors.models`, `scheduler_jobs`. Además: las rejillas declaran `grid-cols-4` y pintan solo 2 tarjetas (media pantalla vacía).
- **Asunto vs Proyecto**: la diferencia REAL es *con aprobación* (asunto: siempre termina en borrador que Pipe aprueba) vs *sin aprobación* (proyecto: responde y ya). Todo lo demás es idéntico — **la pantalla de proyectos miente al sugerir que ahí "conectas las carpetas que quieras" como si fuera exclusivo: hay que borrarlo**. Asimetrías sin razón de negocio: en un asunto no se puede guardar lo que MIA produjo (3 candados); en un proyecto no se puede convocar la Sala de estrategia. Recomendación: **renombrar, no fusionar**.
- **Conexiones**: Gmail/Outlook/OneDrive están **construidos y muertos** hasta que Pipe registre las apps OAuth en Azure/Google (trámite suyo, no código). Decidir además: ¿una app por despacho o una app de Lexia compartida?
- **Modelos/OpenRouter por agente**: hoy un agente solo elige "motor del despacho" o "siempre local". Abrirlo permitiría evadir la política de gasto/privacidad del despacho — recomendación: **explicar mejor, no abrir**.
- **Bug de Hook**: `frontend/app/chat/page.tsx` invoca `useAtajo` dentro de un callback (viola las reglas de React). Sin diagnosticar si rompe el chat en runtime. Warnings de dependencias en dashboard, `ConnectedSystemsSection` y `FuentesPanel`.
- **Ctrl+K → "Nuevo asunto"** navega a `/?nuevo=1` y `page.tsx` nunca lee ese parámetro: el atajo no abre nada.
- **NO existe control de vencimientos procesales.** Solo recordatorios que pide Pipe por chat. No prometer plazos: sería inventar fechas.

## 7 · Carpetas: 5 fallos reales aún abiertos

La auditoría previa (`mia-cory-audit-worktree/research/cory-audit/`) dejó **2 suites rojas reproducidas**: `test_matter_folder.py` (conteo, throttle, conservación tras `unlink`) y `test_matter_folders_multi.py` (conteo, throttle). **Causa raíz sin identificar.** Son todas de *asuntos*: **no existe ni un solo test de "carpeta vinculada a un PROYECTO"**, que es justo el escenario que falló en producción. De los 11 FAIL de esa regresión, solo ~6 son reales; 4 eran ambientales del worktree (faltaba `PG_PASSWORD`).

## 8 · Pendiente de Pipe (no es código)

- Registrar las **apps OAuth** de Gmail/Outlook/OneDrive.
- **Verificar el inc. 3 en vivo** (nunca se probó con MIA corriendo): folio y procedencia al subir un documento, botones "Arrancar el día"/"Cerrar por hoy", y "Documentos por confirmar".
- Decidir el **push** de los 14 commits.
- Encargo para **Cursor** (rediseño visual de panel y conocimiento) — pendiente de redactar; su rol ya está definido como frontend/capa 3.
- **Rediseño del SOUL/perfil** con las skills de referencia que pasó (`perfil-personal-lexia`, `perfil-completo` — "no tan largo").

---

# CIERRE — 2026-07-19, Fase 1 · incremento 3 — procedencia+folio, ficha-loader/daily/cierre, clasificador de metadata (rama, sin push)

Rama `feat/fase1-inc1-cleanup-scaffolding`. Orquestado con workflows multi-agente (un escritor por archivo/fase; verificación independiente antes de cada commit). **4 commits, ninguno pusheado.**

## Commit `6b534d1` — limpieza de los 8 sucios pre-existentes
Se quitó SOLO la instrumentación de debug temporal (sesión 153429: log a `debug-153429.log` + imports huérfanos `_Path/_json/_time` en backend; `fetch` a `127.0.0.1:7610` con UUID de prueba en frontend), preservando intacto el trabajo legítimo (delegación CP-HUB2, refactor confidencialidad mensaje→POST body, fix jsonb footgun). 3 archivos ya eran 100% legítimos (`ux.py`, `AsistentesSection.tsx`, `api.ts`). Con esto `ux.py` quedó limpio y ya se puede commitear → desbloquea la nota de colisión del inc.2.

## Commit `1f16bd3` — P1+P2: procedencia diferida + folio_ancla real
- **P1 (`ux.py`)**, aplica la nota de colisión del inc.2: `create_matter()` scaffold del workspace (`scaffold_matter_workspace`, alias=UUID del asunto, threadpool no-fatal, solo `kind=='asunto'`); `upload_document()`→`procedencia='documento'`; `create_output()`→`procedencia='inferido'` (origin='mia', NUNCA 'documento').
- **P2 (folio real)**: `extract._assemble_body` devuelve `folio_map` (folio,ini,fin) contado sobre el cuerpo ensamblado real (evita desalineación por notas OCR/truncado); `ingest.chunk_text_with_folios()` NUEVA sin tocar la firma de `chunk_text` (la usan 5 llamadores); el chunk hereda el folio de su offset de inicio. Cableado en `ux.py::upload_document` + los 3 connectores. Fuentes sin páginas (.txt/.docx/.md, cuerpo de correo) → folio NULL (nunca inventa).

## Commit `a0bde00` — P4: ficha-loader + loops del día
- **ficha-loader** (`onboarding/ficha_loader.py`): lee ficha.md+HANDOFF.md+bitácora del expediente (alias=UUID, vía `workspace.py`), trunca por unidad semántica bajo presupuesto, fail-soft. Enganchado en `agents/graph.py::_matter_context_for` (tier CONTEXT no cacheado) → inyecta la memoria del caso a los 7 nodos sin alterar el orden de capas.
- **`/daily`** (`GET /api/matters/{id}/daily`, router `sessions.py`): briefing determinista sin LLM; "Requiere tu decisión" arriba, refs #N.
- **`/cierre`** (`POST .../cierre`): destila SOLO las intervenciones del abogado con cadena barata; escribe durables a `bitacora/cierre-*` y decisiones abiertas a bloque "Pendiente de tu decisión" separado en HANDOFF.md; si nada durable → `written:false` (no fabrica). Cierre automático: mismo endpoint `{auto:true}` gateado al ~65% de llenado, disparado por el frontend tras cada turno (una vez por sesión).
- **Frontend**: botones "Arrancar el día"/"Cerrar por hoy" + DiarioDialog/CierreDialog en lenguaje llano.
- **TODO documentado**: el cierre-auto backend-side no se cablea porque el checkpoint se borra al cerrar el turno (no hay medidor de llenado en backend); el frontend tiene el medidor real. Si el runner conserva transcript persistente en el futuro, invocar `session_briefing.maybe_auto_cierre`. NO se inventó cron (regla dura).

## Commit `f27aa1f` — P3: clasificador de metadata (infiere y marca la duda)
Decisión de Pipe: MIA infiere tipo/parte/folio_radicado/fecha y **marca la duda** en una **lista propia "Documentos por confirmar"** (no la Pantalla 4), confirmación **campo por campo**.
- **046** aditiva: `documents.metadata_sugerida jsonb` + índice parcial; la lista se deriva de `metadata_sugerida IS NOT NULL` (una sola verdad, sin flag extra).
- **`llm.py`**: task AUX nuevo `doc_classification` (cadena barata Haiku/mia-local), no locked, propagado a las 4 políticas por el spread.
- **`ingest/classify.py`**: `classify_document()` agnóstico de jurisdicción (tipo/parte texto libre, NUNCA vocabulario de un país), umbral por campo (env `MIA_CLASSIFY_MIN_CONFIANZA`, default 0.7), envuelto en la policy del tenant, fail-soft absoluto; no pisa fecha ya fijada.
- **`jobs/durable.py`**: handler recuperable `classify_document` + persistencia por lista blanca de columnas (jamás interpola claves del modelo); alta confianza→columna real, baja→`metadata_sugerida`; `fecha_documento` con COALESCE (no pisa el dato fidedigno del correo). Encolado fail-soft tras el INSERT en los 5 orígenes reales; EXCLUIDOS `create_output` (origin='mia') y el harness.
- **`api/routes/documents_review.py`**: GET pendientes + POST confirmar/editar un campo (mueve de sugerida a columna; NULL cuando no quedan dudas). **Frontend**: `DocumentosPorConfirmarDialog` (aceptar/corregir por campo).

## Verificación
- **PASÓ (capas 1–2, automática + independiente):** `ast.parse` OK en todos los .py de cada pieza; firma de `chunk_text` intacta; valores de procedencia correctos (`documento`/`inferido`); migración 046 sin colisión (max+1); grep sin vocabulario de país en el clasificador; exclusiones correctas (`create_output` no encola, count 0); los 5 orígenes encolan (1 c/u); router `documents_review` registrado; P1/P2/P4 y CP-HUB2 intactos entre piezas; `git grep` sin residuo de debug.
- **NO verificado (honesto) — capa 3 del dueño:** `test_rls` **no corrido** (requiere DB viva; columnas 045/046 heredan RLS, no se tocó lógica RLS). Migraciones **045+046 no aplicadas a DB real** (corren solas en bootstrap). Clasificador, `/daily`·`/cierre`, cierre-auto y encolado de jobs **no probados E2E en vivo** (necesitan Postgres + `DurableWorker` corriendo). **Frontend sin `next build`** (regla del repo: no correr build). El destilado de `/cierre` usa `task='session_search'` (AUX barato) como vehículo de la cadena Haiku — funcional, aunque semánticamente no es "destilar".

## Qué sigue
Capa 3 de Pipe (E2E en máquina con DB+worker+build): aplicar migraciones, correr `test_rls`, subir un doc por cada origen y verificar clasificación + "Documentos por confirmar", probar los botones del día y el cierre-auto al ~65%. Rama sin push (Pipe aprueba). Retomar leyendo esta entrada + `TRASPASO-MODELO.md`.

---

# CIERRE — 2026-07-18, Fase 1 · incremento 2 — Jarvis + cableado ingesta/onboarding (rama, sin push)

## Qué se hizo (un solo escritor; los 8 sucios pre-existentes NO se tocaron ni commitearon)
**A · Limpieza Jarvis (documental).** Removidas las **28 menciones** `jarvis`/`OpenJarvis` (revisión
independiente: **0 código derivado vivo**; la voz se construyó sobre Lexter/Handy MIT, no sobre OpenJarvis;
ninguna atribución Apache 2.0 era legalmente exigible). Edición mínima y quirúrgica en 8 docs: `CLAUDE.md`,
`TRASPASO-MODELO.md`, `HANDOFF.md`, `docs/{analisis-referencias-2026-07, plan-ejecucion-olas}.md`,
`memory/{findings, progress, session-summaries, task_plan}.md`. Se preservaron TODAS las atribuciones
`hermes`/MIT (código realmente incorporado — asunto distinto de Jarvis, no se tocó).

**B · Cableado inc2 (aditivo, en archivos NO-sucios).**
- **Onboarding despacho:** `auth.py::register()` llama `scaffold_despacho_workspace(tenant, despacho_nombre=
  firm_name)` vía `run_in_threadpool`, tras crear la fila del tenant, en `try/except` no-fatal (el disco es
  accesorio; jamás tumba el alta). Idempotente.
- **Procedencia en ingesta (4 de 5 sitios documentales):** `procedencia='documento'` explícito en el INSERT
  a `chunks` de `ingest/ingest.py`, `connectors/local_folders.py`, `connectors/graph_drive.py` y
  `api/routes/matter_mail.py`. (El 5.º — `ux.py::upload_document` — quedó DIFERIDO por colisión, ver abajo.)
- **Quick win metadata:** `matter_mail._ingest_document` puebla `documents.fecha_documento` con la fecha ISO
  del correo (`_parse_mail_date`: parsea YYYY-MM-DD; si no es inequívoca → NULL, **nunca inventa fecha**).
- **/health estructural:** `api/main.py::health()` añade `provenance_ready` (sonda a
  `information_schema.columns`, sin GRANT extra) que exige las 6 columnas de la 045 — el instalador puede
  sumarla al gate de 'ready'.
- **Migración 045:** NO requiere código de aplicación: `setup/paths.migration_paths()` la toma por glob; se
  aplica sola en `first_run` (instalación) y `maintenance.startup` (arranque). Aditiva/idempotente; ya en el bundle.

## COLISIÓN con los 8 sucios (regla "no forzar"): `ux.py`
`ux.py` es uno de los 8 sucios (trae el refactor vivo de delegación CP-HUB2 + POST `/stream`, sin commitear).
Dos cableados de inc2 caen en `ux.py` → **NO se forzaron**: se revirtieron a baseline y `ux.py` quedó EXACTO
como estaba (verificado por grep + py_compile). **Pendiente de aplicar por el dueño al cerrar/limpiar su batch
dirty:**
1. `create_matter()` (solo `kind=='asunto'`): tras el INSERT a `matters`, `await run_in_threadpool(
   scaffold_matter_workspace, tid, str(row[0]), titulo=body.name)` en try/except no-fatal. Imports:
   `from starlette.concurrency import run_in_threadpool` y `from ...onboarding.workspace import
   scaffold_matter_workspace`. alias=UUID; los proyectos ya tienen su propio multifolder.
2. `upload_document()` y `create_output()`: añadir `procedencia` al INSERT de `chunks` — `'documento'` en
   `upload_document` (subida manual, sitio PRINCIPAL) y `'inferido'` en `create_output` (origin='mia',
   contenido PRODUCIDO por Mia, sujeto al gate de citas — NUNCA 'documento').

## Verificación
- **PASÓ:** `test_workspace` **22/22**; HALT `check_env_pins` **10/10**; `py_compile` de los 7 archivos
  editados; import limpio de auth/matter_mail/connectors/ingest + `ux.py` revertido + `_parse_mail_date`
  (ISO→date, no-ISO→None). Grep: 0 menciones jarvis fuera de la nota de esta entrada; 0 marcadores inc2 en `ux.py`.
- **NO verificado (honesto):** `test_rls` **no corrido** (requiere DB viva; las columnas 045 heredan RLS, no
  se tocó lógica RLS) — re-correr en capa 3. 045 **no aplicada a DB viva** (corre sola en bootstrap = capa 3
  del dueño; no se levantó la DB portable). `/health provenance_ready`, `register`+`create_matter` y mail-link
  **no probados en vivo** (necesitan servidor+DB = capa 3). Sin frontend en inc2 → sin `next build`.

## Qué sigue — incremento 3
Aplicar la **nota de colisión de `ux.py`** (arriba) al limpiar los 8 sucios; **folio_ancla real** (mapa
chunk→página en `ingest/extract.py`; hoy NULL — nunca inventar folio); resto de metadata documental
(`tipo`/`parte`/`folio_radicado`) vía clasificador; ficha-loader; loops `/daily`+`/cierre`. Retomar leyendo
esta entrada + `TRASPASO-MODELO.md`. Rama `feat/fase1-inc1-cleanup-scaffolding`, sin push.

---

# CIERRE — 2026-07-18, Fase 1 · incremento 1 — limpieza + andamiaje (rama, sin push)

## Qué se hizo
Un solo escritor secuencial sobre rama nueva **`feat/fase1-inc1-cleanup-scaffolding`** (partió de
`feature/robustecimiento-sin-aws`; **sin push**). El árbol traía 8 archivos modificados pre-existentes
(mailbox/stream/ux/dreams + 4 de frontend) — se dejaron **intactos y sin commitear** (no eran de este
encargo). Dos bloques:

**A · Limpieza conservadora (solo evidencia positiva de código muerto).**
- Borradas 4 carpetas **huérfanas sólo-`__pycache__`** (sin `.py` fuente, 0 imports vivos, gitignored):
  `backend/mia/{voice,tools,tasks,audit}/` — reemplazadas hace tiempo por `speech/`, `jobs`+`missions`,
  `observability/audit.py`+`security/redact.py`. Cruft de disco; no tocan git ni runtime.
- Borrado `frontend/app/_components/MatterDriveFolder.tsx` (componente default-export con **0 imports**
  en todo el frontend; nunca se cableó). Único borrado que sí es cambio de git.
- **NO se borró** (queda para decisión del dueño): todas las referencias `hermes` (conector VIVO del
  Agent Hub + aserción de seguridad en `test_secret_scope` + ~30 docstrings de atribución MIT), y
  `rag/ingest_corpus.py` (deprecado pero fixture vivo de `test_sat_graph` + semilla opt-in de packs).
  Ninguno es código muerto. (Las menciones documentales `jarvis`/OpenJarvis se removieron en inc.2.)

**B · Andamiaje Fase 1 (aditivo e idempotente).**
- **Migración `045_fase1_document_provenance.sql`** — ADITIVA. Se descubrió que `documents`/`chunks`
  (Módulo 0) YA existen con `matter_id`, `embedding vector(1024)` y RLS. **Crear tablas `document`/`chunk`
  nuevas habría DUPLICADO** → en su lugar `ALTER TABLE ... ADD COLUMN IF NOT EXISTS`:
  documents += `tipo, folio_radicado, parte, fecha_documento`; chunks += `folio_ancla` + **`procedencia`**
  (`varchar(16)` CHECK `{fidedigno|documento|inferido}` default `documento`) + índice parcial. Campos ya
  existentes se MAPEARON (ruta_fuente→`source_path`, hash→`sha256`, texto_verbatim→`content`), no se
  re-crearon. `tipo`/`parte` texto libre (agnóstico de jurisdicción, sin dominio de país).
- **`backend/mia/onboarding/workspace.py`** — genera en disco (bajo `$MIA_HOME/despachos/<tenant>/`,
  reusando `_safe_tenant`) el árbol que SEPARA estado-de-Mia de fuente: `.mia/` (despacho.md,
  baseline-<fecha>.md, aprendizajes.md PINNED, memoria/INDICE.md) y `expedientes/<alias>/` (ficha.md,
  HANDOFF.md, bitacora/ inbox/ **fuente/** [verbatim inmutable, con LEEME] fichas/ _archivo/). Puro
  (config+stdlib), idempotente, no-destructivo. `extra_carpetas` deja al pack del despacho inyectar
  carpetas jurídicas propias sin hardcodear ningún país.
- **`execution/test_workspace.py`** — gate offline del andamiaje.

## Decisiones del dueño aplicadas (2026-07-18)
Caso demo cerrado/didáctico; cross-matter proactivo (solo argumento abstraído, jamás hechos de cliente,
logueado+HITL); auto solo lo trivial al destilar; allowlist permissive. (El grueso de estas decisiones
aterriza en el **incremento 2** — pipeline de ingesta; el inc.1 dejó el andamiaje que las soporta.)

## Verificación
- **PASÓ:** `test_workspace` **22/22**; HALT `check_env_pins` **10/10**; import de `mia.onboarding.workspace`
  limpio; cleanup verificado por grep (0 imports de los 4 paquetes borrados y de `MatterDriveFolder`).
- **NO verificado (honesto):** migración 045 **no aplicada a DB viva** (idempotente; se aplica sola en el
  próximo `db_bootstrap`/arranque — es capa 3 del dueño; no se levantó la DB portable a propósito).
  `test_rls` **no corrido** (requiere DB viva; el cambio no toca superficie RLS). `tsc`/`next build` del
  frontend **no corridos** (repo pesado, riesgo de cuelgue; el borrado es un archivo sin referencias →
  probado por grep). Regresión completa NO corrida (regla: por tramos).

## Qué sigue — incremento 2
Pipeline de **ingesta → ficha → loops**: cablear `scaffold_despacho_workspace` en el onboarding y
`scaffold_matter_workspace` al crear un asunto; poblar `procedencia`/`folio_ancla`/`tipo` en la ingesta;
aplicar la 045 en vivo y añadir su check al gate del instalador (`/health` migraciones esperadas). Retomar
leyendo esta entrada + `TRASPASO-MODELO.md`; la rama `feat/fase1-inc1-cleanup-scaffolding` está sin push.

---

# CIERRE — 2026-07-17 (tarde), sesión 49 — las 3 features inertes + instalador + atajos: CABLEADAS

## Qué se hizo esta sesión
Se ejecutó, con orquestación multi-agente dinámica (Opus coordina, Sonnet implementa,
Opus verifica adversarial), **todo el backlog de metas del handoff de la mañana**: las tres
capacidades que el abogado veía "activas" pero por dentro no hacían nada (Banco de oro, Pinecone,
MCP), el blindaje del instalador, la limpieza trivial y — por decisión de Pipe — los atajos de
despacho con salud de guías. **6 commits, uno por meta, repo con 6 commits nuevos sobre `fe1ecab`.**

Método: 1 workflow de recon read-only (6 scouts) + 4 olas de implementación en grupos de archivos
DISJUNTOS; el coordinador (esta terminal) fue el único que tocó git y preparó los archivos
compartidos (`pyproject.toml`, numeración de migraciones). Cada meta con su gate verde y un
verificador Opus independiente que RE-CORRIÓ el gate antes de aprobar.

## Las 6 metas (commit · gate)
- **C — Banco de oro al examen** (`e4e921b`): `run_full_suite()` suma los casos confirmados del
  despacho a los sintéticos; `POST /gold-cases:evaluate` gated por `allow_eval_real_data`. Gate
  `test_gold_cases_influence_eval` 11/11 + regresión eval 25/25, gold_cases_api 57/57.
- **F — limpieza** (`9be48e9`): borrada `gepa_run_all_tenants()` huérfana. Gates gepa/dreams/curator/feedback verdes.
- **A — Pinecone store secundario** (`e5c9cfe`): espejo `upsert/delete/query` opt-in por despacho,
  aislado por namespace de tenant, **fail-soft total** (si falla, sigue pgvector), solo espeja
  conocimiento del despacho, **nunca el expediente**. Gate `test_pinecone_wiring` 23/23 + connector 16/16.
- **B — MCP consumidor real** (`75a59bd`): `mcp/client.py` (stdio en sandbox por tenant) +
  `mcp/turn.py` (sub-turno de tools) + `graph._mcp_context` (salida SELLADA `[VERIFICAR]`). Muro:
  `soberano` BLOQUEA antes de lanzar el subproceso. Fail-soft en 5 capas. Gate `test_mcp` 39/39.
- **D — blindaje instalador** (`062adc3`): `/health` reporta migraciones aplicadas vs esperadas +
  checkpointer (migración **043**); la cáscara Tauri frena con mensaje en llano si la base no terminó
  de actualizarse; backups rotan a 3. Gate `test_first_run` 71/71, backup/maintenance/config_anchor verdes, `cargo check` exit 0.
- **E — atajos + salud de guías** (`c0df832`, decisión de Pipe = "las dos completas"): chips de un
  clic en el chat vacío que **pre-llenan** el mensaje (consent-first, nunca auto-envían) reusando
  guías/personas del despacho; badge sana/revisar por guía (migración **044**, fail-open). §G
  validado string por string. Gates `test_playbook_health` 29/29, `test_despacho_atajos` 17/17, `tsc` exit 0.

## Estado de verificación
- **Capa 1:** cada meta con su gate verde (arriba). **HALT re-corridos al cierre sobre el estado
  final acumulado: `test_rls` 19/19, `check_env_pins` 10/10.** NO se corrió la regresión completa (no cabe).
- **Capa 2:** un verificador Opus adversarial independiente por meta, que re-corrió cada gate. 0 bloqueantes.
- **Capa 3 (en vivo): PENDIENTE — de Pipe.** Nada probado con MIA encendida.

## Pendientes y próximo paso (capa 3 de Pipe)
1. **MCP de punta a punta EN VIVO** (lo más importante): la sección `stdio-live` de `test_mcp`
   (ida-y-vuelta real, guard de soberano sin subproceso, sin proceso huérfano) hizo **SKIP honesto**
   porque LiteLLM `:4000` no estaba arriba. Node/npx SÍ están. Falta: arrancar Modo B y re-correr
   `test_mcp.py` para ejercitar e6b-01/02/03.
2. **Pinecone en vivo:** las llaves reales del despacho + un índice dim 1024 coseno; hoy verificado
   con índice falso (FakeIndex). El opt-in y el fail-soft ya están; falta la escritura/lectura real.
3. **Banco de oro de punta a punta** y **delegación D3** (Riesgo #66) siguen pendientes de vivo.
4. **Ajuste opcional (no bloqueante, decisión de Pipe):** `memory/atajos.py::list_shortcuts` corta a
   6 guías por uso ANTES de anexar personas → con ≥6 guías activas los agentes del despacho no salen
   como chips. Si Pipe quiere cupo garantizado para 1-2 agentes, es un ajuste de una línea.

## Decisiones tomadas
- **Pipe — meta E completa** (atajos + salud de guías), elegido en sesión sobre "solo salud" o "diferir".
- **Coordinación de archivos compartidos por el coordinador** (no por los agentes): `pyproject.toml`
  (declara `pinecone>=3` y `mcp>=1.10,<2`), y la numeración de migración (D=043, E=044) para evitar
  el choque del `038` de la sesión 48. Un solo escritor de git.
- **Pinecone NO externaliza el expediente** (solo `knowledge_chunks`): elección de confidencialidad,
  no se mandan documentos de casos a un cloud sin que nadie lo pida.

---

# CIERRE — 2026-07-17, sesión 48

## Qué se hizo esta sesión
Se cerró el backlog de las tres auditorías (Cursor, Antigravity, Claude) y se le quitó a MIA
el sesgo colombiano que llevaba por dentro. Se hicieron reales dos capacidades que tenían API
pero estaban muertas (Agent Hub y Banco de oro) y se les hizo pantalla. Se le dio criterio
jurídico con 8 principios destilados de los skills y el vault de Pipe, sin clonar nada suyo.
De paso volvió a arrancar la DB portable (llevaba sesiones caída) y aparecieron **cuatro fugas
de confidencialidad que nadie buscaba** y **dos gates que llevaban sesiones en rojo sin que
constara**. 17 commits, repo limpio.

## Estado de verificación
- **Capa 1 (tests/build/lint):** PASÓ. `test_rls` 19/19 (HALT) · `jurisdiction_agnostic` 75/75 ·
  `delegation_decide` 103/103 · `argument_engine` 65/65 · `soul_guard` 47/47 ·
  `curator_conflicts` 38/38 · `wiki_reading` 36/36 · `obsidian_sync` 73/73 ·
  `eval_substance` 37/37 · `gold_cases_api` 55/55 · `e2e` 32/32 · `prompt_builder` 46/46 ·
  `migration_ledger` PASS · `config_tabs` 21/21 · tsc limpio · lint 0 errores ·
  `next build` 15 rutas · `cargo check` exit 0.
  **NO se corrió la regresión completa** (103 suites; no cabe): se corrieron las tocadas y sus
  adyacentes.
- **Capa 2 (revisor independiente):** HECHO en los dos frentes de riesgo — revisión adversarial
  del frontend (6 hallazgos, todos corregidos: dos invalidaban objetivos que se daban por
  cerrados) y del anonimizador (encontró la fuga del `role`, corregida). El resto de frentes
  los verificó Claude releyendo y ejecutando, no un revisor aparte.
- **Capa 3 (visual/en vivo):** **PENDIENTE — es de Pipe.** Nada de esto se ha probado en vivo.

## Pendientes y próximo paso
1. **Capa 3 de Pipe** (lo que Claude no puede hacer): E2E del instalador en máquina limpia,
   recorrido visual, login real de NotebookLM y, nuevos: **probar la delegación en vivo**
   (Riesgo #66 · D3: los flags de los CLI nunca se han probado contra un `--help` real; la
   primera invocación puede fallar — degrada limpio, pero "funciona" está sin verificar) y el
   **banco de oro de punta a punta**.
2. **El diagnóstico del turno se tira cada turno** (Riesgo #68): es el razonamiento que llevó a
   la conclusión y hoy se pierde (vive en el checkpoint y se borra). Por eso las conclusiones
   clave del banco de oro llegan vacías. Es el hilo abierto de más valor.
3. **El juez de conflictos del Curator** (Riesgo #67) está probado en cableado, no en puntería.
   El paso honesto: un set etiquetado de pares reales de la firma contra el modelo vivo.
4. Riesgos #69-#74 en `memory/bugs-and-risks.md` (hilo del asunto que no sobrevive a un F5,
   ficheros sin RLS, `index_trace` best-effort, "Patrones rechazados" que no llega al modelo).

## Trabajo en background sin leer
**Ninguno.** Todos los agentes cerraron y sus informes se leyeron y verificaron.
**Ojo — un proceso vivo:** la **DB portable quedó ENCENDIDA** en `127.0.0.1:55432` (se levantó
esta sesión). Colgaba de la sesión y ya se cayó una vez al terminar un comando: **si mañana no
responde, arráncala** con `tools/postgres16-portable/pgsql/bin/pg_ctl.exe -D tools/pgdata-portable
-o "-p 55432" start`. Trampas documentadas abajo y en `memory/progress.md`: el clúster es
`tools/pgdata-portable`; a la copia mínima le faltaba `share/*` (se copió del `-full` SIN
machacar `share/extension/`, donde vive **pgvector 0.8.2**, que el `-full` no trae); y arrancar
con los binarios del `-full` levanta el postmaster pero **sus backends mueren con 0xC0000142**
(el puerto responde y engaña: solo se ve como ConnectionTimeout).

## Decisiones tomadas / suposiciones hechas
- **Pipe — anonimizador: "enmascarar todo, siempre".** Todos los packs, sin mirar el país del
  despacho. Secreto profesional > precisión. Efecto aceptado: `artículos 1494-1495` se enmascara
  como teléfono.
- **Pipe — delegación: "MIA decide y me pregunta".** Rechazó que MIA no pudiera decidir
  (*"parte del encanto de MIA es que puede determinar si necesita agentes o subagentes"*), y
  tenía razón: sus subagentes PROPIOS ya eran autónomos y siguen sin candado.
- **Pipe — todo en dólares.** Corrigió su idea inicial (moneda por jurisdicción) al ver que la
  tarifa en pesos + el gasto en USD obligaba a mentir en el "valor neto" o a inventar una tasa.
  **No se tocó nada**: el trabajo se paró a tiempo.
- **Pipe — los 8 principios** de sus skills y su vault, sin clonar nada suyo.
- **Suposición de Claude (decidida, no consultada):** los indicios de sustancia entran como
  informativos y NO en `ok` — meterlos en el contrato volvería rojos de golpe los casos de oro
  ya aprobados, y un examen que se pone rojo sin que nada empeore deja de creerse.
- **Renumeración:** `038_soul_versions` → `040`. Dos agentes crearon el mismo 038. Regla nueva:
  el número de migración se reserva al EMPEZAR, no al escribir el archivo (Riesgo #73).

---

## Cómo usar este archivo

Cursor lee este archivo al iniciar sesión en el repositorio. Aquí queda
registrado el checkpoint más reciente del trabajo hecho en Claude Code:
qué cambió, qué debe revisarse en el frontend y qué comportamiento se
espera. Al terminar su revisión visual (capa 3), Cursor escribe sus
hallazgos en la sección final "Hallazgos de Cursor (capa 3)" para que
quede trazabilidad de ambas revisiones.

---

## Checkpoint MÁS RECIENTE: sesión 48 (2026-07-16) — backlog de las tres auditorías CERRADO

**Rama:** `feature/robustecimiento-sin-aws`, repo limpio, sin push. Commits: `ca7cd74`
(ruta del motor), `960553b` (frontend), `902bd90` (agnosticismo backend), `c4b57f5`
(ejemplos del onboarding), `16e9eec` + `9a93341` (dos gates en rojo), `09d00c7`
(defaults del grafo).

**LA DB PORTABLE YA ARRANCA** (llevaba sesiones caída, lo que mantenía gates diferidos).
Cómo: `tools/postgres16-portable/pgsql/bin/pg_ctl.exe -D tools/pgdata-portable -o "-p 55432"`.
Trampas: el clúster es `tools/pgdata-portable`; a la copia mínima le faltaba `share/*` (se
copió del `-full` SIN machacar `share/extension/`, que es donde vive **pgvector 0.8.2**, que
el `-full` no trae); arrancar el clúster con los binarios del `-full` levanta el postmaster
pero **sus backends mueren con `0xC0000142`** (parece vivo y da ConnectionTimeout). El 5432
lo ocupa un PostgreSQL de sistema SIN pgvector — no confundirlos.

**Gates que estaban diferidos y hoy están VERDES:** `test_rls` 19/19 (HALT), `test_welcome_keys`
41/41, `test_setup_wizard` 28/28, `test_second_brain_ui` 27/27.

### A · Frontend (`960553b`) — confianza, agnosticismo, legibilidad
Cerrado TODO el backlog de Cursor + los 6 arreglos que Antigravity nunca llegó a implementar.
Deep-link al borrador (`/asuntos/{id}/revisar`) desde panel y lista; se consumen
`?sin_borrador`/`?confirmed` (antes se escribían y nadie los leía); fin de los fallos
silenciosos en `memoria` (drift por `status===409`, no por buscar "409" en el texto);
`AuthGate` con loader; fechas con el locale del abogado (cero `es-CO`); placeholders y
ejemplos sin sesgo de país; detonador de cuantía con UVT/UIT/UMA/IPREM/SMI/€ conservando
SMLMV; "Notas del despacho" ya no miente con "Próximamente"; Telegram avisa de sus pasos
guiados; token `--cta-strong` medido sobre el fondo REAL (`bg-cta/15`, no blanco): 5.10:1
reposo / 4.91:1 hover. Verificado: `tsc` limpio + `next build` completo (14 rutas).
**Revisión adversarial: 6 hallazgos, todos corregidos** — dos invalidaban objetivos que se
daban por cerrados (el botón "Revisar borrador" no funcionaba con TECLADO; el contraste se
había medido contra blanco y daba 4.46).

### B · Agnosticismo de jurisdicción (`902bd90`, `c4b57f5`, `09d00c7`) — REGLA DURA aplicada
La raíz estaba bien diagnosticada: el pack tenía `id_formats`/`doc_markers` **sin cablear**.
Movido al pack: formatos de ID (cédula/NIT/radicado/+57), pistas de dirección y stop-words
(`pii_hints.json`), léxico del buzón (`mail_signals.json`), seed de corpus como opt-in
(`baseline_corpus_seed`). Los 7 patrones CO se movieron a JSON **sin alterar un carácter**
(verificado contra HEAD): cero regresión para el fundador.

**DECISIÓN DE PIPE — anonimizador: "enmascarar todo, siempre".** Aplica TODOS los packs
instalados + base universal + respaldos por rol, **sin mirar la jurisdicción del despacho**;
por eso `jurisdictions` **desapareció de su API pública** (un llamador viejo revienta con
TypeError, no se le ignora en silencio). Sobre-enmascarar es aceptable; filtrar un dato por
ser de otro país, no. **Efecto conocido y aceptado:** `artículos 1494-1495` se enmascara como
teléfono y las cuantías las muerde el patrón de cédula (preexistente). Si el ruido pesa, ese
es el hilo — NO reintroducir una perilla por jurisdicción.

**Cuatro fugas de confidencialidad cerradas** (todas confirmadas ejecutando):
1. Un pack podía APAGAR la red pan-hispana con solo declarar un `role` → salían cédulas y DNI
   en crudo. Bastaba un typo, sin malicia. (La encontró la revisión adversarial; el test del
   agente probaba el camino que SÍ funcionaba: regex inválido.)
2. Preexistente: un despacho colombiano dejaba salir el DNI de un cliente español.
3. El respaldo de teléfono no cubría separadores: `615 55 12 34` salía crudo.
4. `resolve_jurisdictions` no distingue "eligió generic" de "nunca lo configuró" → un despacho
   sin configurar habría perdido cédula/NIT.

**El conocimiento ya no nace colombiano** (`09d00c7`): la jurisdicción al escribir se decide
en Python (explícita → pack del tenant → `'generic'`, nunca `'co'`); migración **036** deja el
DEFAULT en `'generic'` para `legal_norms`, `jurisprudence` y `firm_profiles`. Sin un solo
UPDATE: el material del fundador no se re-marca (verificado: co=26, co=13, colombia=6,
idénticos). **El peor defecto no estaba en el inventario:** `firm_profiles` tenía DEFAULT
`'colombia'` y `auth.py` inserta sin jurisdicción → **todo despacho nuevo nacía colombiano**.
También `corpus_factory` marcaba como colombiano el catálogo del pack español.

### C · DOS GATES LLEVABAN SESIONES EN ROJO sin que constara (`16e9eec`, `9a93341`)
Ambos sobre DINERO, y en ambos el código era correcto: el test se quedó con una regla anterior.
La línea base de "84 suites ALL PASS" **no era cierta**; conviene desconfiar de ella.
- `test_connector_hardening` (35/36 desde la sesión 47): exigía que 'suscripcion' NUNCA usara
  OpenRouter, pero `b582541` extendió el overflow por decisión de Pipe ("Ambas"). Se conserva
  lo que sí protege ('soberano' jamás) y se añade el caso que faltaba (sin opt-in tampoco).
- `test_value_delivered` (26/27 desde `f147fb9`): exigía costo 0 para un alias sin precio, pero
  el control atómico del gasto lo cambió a tarifa conservadora de Sonnet — correcto: con 0 el
  tope mensual no frena y el abogado cree que no gastó.

### D · Agent Hub y Banco de oro: CONSTRUIDOS (`65e521d` backend, `84a059b` UI)
Pipe pidió pantalla para ambos. **Las dos tenían API pero estaban muertas por dentro**;
montar la UI encima habría sido prometer lo que no se cumple, así que se cablearon primero
(decisión de Pipe: "cablearlo de verdad y luego la pantalla").

**Agent Hub — la delegación no existía.** `graph.py` leía `metadata['delegate']` y NADIE lo
escribía. Ahora MIA delega SOLO si el abogado nombra al ayudante en su mensaje con un verbo
de orden (`agents/delegate_intent.py`, determinista, sin LLM). **Se descartó el tool-calling
a propósito:** darle el gatillo al modelo convierte una inyección indirecta desde un
documento del propio expediente en una fuga. Candado en `gateway/hub_gate.py` (hermano de
`notebooklm/gate.py`): con `soberano` NO se delega aunque esté habilitado; la política se lee
con `model_policy_for_strict`, que LANZA si la DB falla — un error de infra jamás abre la
salida. Verificado a mano: soberano→bloquea, nube→permite, DB caída→bloquea. Sale solo el
mensaje del abogado (ni documentos, ni hechos, ni perfil, ni historial). **No pasa por
`anonymize` a propósito** (rompería el encargo — "busca el radicado RADICADO_1" no se puede
buscar — y daría falsa seguridad sobre prosa libre). Bug de raíz cerrado: `set_enabled` hacía
read-modify-write y activar un ayudante podía **revertir un cambio simultáneo de
`model_policy`, resucitando una política que el despacho acababa de endurecer**.

**Banco de oro — tenía TRES bloqueos, no uno:**
1. `allow_eval_real_data` solo se LEÍA: no había forma de concederlo y el 403 mandaba "a
   Configuración", donde no había nada → `GET|PUT /settings/eval-consent`, fail-closed. Ojo:
   el merge `||` de jsonb es superficial y habría borrado el resto de `config['eval']`.
2. No se podía releer un caso → `GET /api/gold-cases/{id}`. Nunca devuelve `anon_map`.
3. **La UI no podía armar el caso:** los documentos solo exponen metadatos y el borrador se
   borra del checkpoint al terminar el turno, justo cuando se captura. Ahora `:draft` lo arma
   **server-side** desde el `matter_id` → el material sin anonimizar NUNCA pasa por el
   navegador. Fuentes: `traces.input/output` del último turno approved|edited (rejected
   fuera); `chunks ⋈ documents`. Topes explícitos (20 docs / 60 fragmentos) avisados con
   números, nunca recorte silencioso.

**Deuda conocida de esto:** (a) **D3 sigue abierto** — los flags de los CLI nunca se han
confirmado contra un `--help` real, así que la salida del ayudante va a `metadata` y NO entra
en la cadena de razonamiento jurídico; la primera invocación real puede fallar (degrada
limpio y avisa, pero "funciona" está SIN verificar en vivo). (b) **El diagnóstico del turno
no se persiste en ninguna parte** (vive en el checkpoint y se borra): por eso las
conclusiones clave llegan vacías y las escribe el abogado. Es dato de valor que se tira cada
turno — hilo abierto si Pipe quiere conservarlo. (c) `index_trace` es best-effort: si esa
fila falla, el asunto queda incapturable y el 409 dirá "aprueba el borrador primero" a quien
sí lo aprobó.

### D2 · Moneda: CERRADO — todo en dólares (decisión de Pipe)
Pipe primero dijo "lo lógico es el peso de cada jurisdicción" y, al ver el nudo, corrigió a
**todo en dólares**. El nudo era real: con la tarifa en pesos y el gasto de IA en USD, el
"valor neto" (`ux.py:1581`, `gross - cost`) mezclaba monedas → o mentía o exigía inventar una
tasa de cambio. **No se tocó nada** (el trabajo se paró a tiempo, solo se había leído código).
Si algún día un despacho pide su moneda, hay que resolver la conversión de verdad.

### E2 · CP-HUB2 + los 8 principios (`65e521d`, `84a059b`, `aa8ac3a`, `9019ee6`, `47f5578`)
**Delegación — decisión de Pipe: "MIA decide y me pregunta".** Rechazó la invocación explícita
como única vía: *"parte del encanto de MIA es que puede determinar si necesita agentes o
subagentes"*. Tenía razón, y además **MIA ya orquesta subagentes PROPIOS sin candado y así debe
seguir** (`agents/delegation.py`: swarm interno por `call_llm` → no sale nada del equipo). El
debate era solo con los 5 ayudantes EXTERNOS. Modos: `preguntar` (default) / `autonomo` /
`solo_si_lo_pido` (`GET|PUT /settings/delegation-mode`).
- **La trampa que casi lo rompe:** LangGraph re-ejecuta el nodo al reanudar. Un nodo que
  decidiera-y-preguntara volvería a llamar al modelo al aprobar y podría sacar **otro texto**:
  la pantalla sería teatro. Por eso está partido — `intake` **planifica** y persiste el plan;
  `delegation_node` solo interrumpe y lee del estado. Hay test que cambia lo que el modelo
  respondería entre proponer y aprobar y exige que salga el texto viejo.
- **Dos pausas que no se pueden confundir:** aprobar el BORRADOR no puede reanudar la pausa del
  AYUDANTE (el texto saldría sin verse). Separadas por nodo y por payload.
- **FUGA PREEXISTENTE CERRADA:** `_maybe_delegate` leía `_last_user_message`, que con
  `@expediente` lleva **pegado el contenido de los documentos** (CP-E2): **el expediente entero
  salía al CLI de un tercero**, contra el contrato escrito en el propio módulo. Ahora
  `retrieval_query`.

**Los 8 principios** (destilados de los skills y el vault de Pipe, sin clonar nada suyo; lo
colombiano y el estilo Lexia se descartaron por diseño). El hallazgo que los ordenó: **MIA está
construida para no mentir, no para argumentar bien** — y **aprendía de Pipe sin volver a leer
jamás lo aprendido**.
- **La Sala de estrategia existía y el redactor NUNCA la consultaba.** Ahora su dictamen (ya
  pagado y persistido) se inyecta sellado en el borrador. Se descartó correrla por turno: ~9
  llamadas contra las 4 del turno → triplica la factura. Coste: 0 llamadas nuevas.
- **Anatomía del argumento** en la capa 2 (cacheada, +238 tokens una vez) + jerarquía 80/20 +
  `facts` que explota las inconsistencias en vez de describirlas.
- **El examen mide sustancia** (`aa8ac3a`): 3 señales deterministas; se RECHAZARON 3 que no se
  podían medir sin mentir (confrontación → solo por léxico, gameable con una palabra;
  consecuencia → depende de fórmulas de un país; 80/20 → probado, NO discrimina). Van como
  **indicios informativos**, no en `ok`: meterlas en el contrato volvería rojos de golpe los
  casos de oro ya aprobados.
- **El wiki era de SOLO ESCRITURA:** `search_wiki()` sin un solo llamador. Cableado, fenceado
  como inferido y NO citable. Antes hubo que arreglar la confianza, que era un **trinquete**
  (solo subía; 9 toques → 1.0; nunca bajaba ante un rechazo).
- **`dreams` escribía SOUL sin permiso, sin tope y sin versión** — y estaba **PROTEGIDO POR UN
  TEST** que exigía ese comportamiento ("Nudges actualiza SOUL"): hubo que invertirlo. Ahora
  propone; el tope RECHAZA (no trunca). La instrucción directa de Pipe se aplica sin
  re-preguntar.
- **El Curator fusionaba contradicciones** (coseno >0.85): "siempre X" y "nunca X" acababan en
  un texto que no dice ninguna. Ahora juez barato + umbral 0.85 y **fail-soft a duplicado** (un
  falso positivo interroga al abogado, deja de aprobar, y la memoria deja de aprender).
- **Obsidian:** el frontmatter entraba como basura y los `[[wikilinks]]` no se parseaban — MIA
  leía el segundo cerebro del despacho como un PDF.
- **Otra fuga cerrada:** `wiki_dir()` interpolaba el `tenant_id` en la ruta **sin sanear** —
  inofensivo mientras solo se escribía; primitiva de lectura al wiki de OTRO despacho en cuanto
  se cableara la lectura.
- **Y otra:** el prompt del NER decía *"anonimizar un texto jurídico colombiano"* (`47f5578`).
  Se le escapó a TRES auditorías del mismo archivo el mismo día: todas miraban los patrones,
  ninguna leyó el prompt.

**Deuda de esto (leer antes de tocar):** (a) **D3 abierto** — los flags de los CLI nunca se han
probado contra un `--help` real; la salida del ayudante va a `metadata` y NO al razonamiento; la
primera invocación en vivo puede fallar (degrada limpio, pero "funciona" está SIN verificar).
(b) El **juez de conflictos** está probado en cableado, **no en puntería** (los gates corren sin
red). El siguiente paso honesto es un set etiquetado de pares reales contra el modelo vivo.
(c) **El diagnóstico del turno no se persiste** (checkpoint → se borra): las conclusiones clave
del banco de oro llegan vacías y se tira dato de valor cada turno. (d) El archivo **"Patrones
rechazados"** de `dreams` sigue sin llegar al modelo (confidence hardcodeada). (e) **El hilo de
mensajes del asunto no sobrevive a un F5** (no hay endpoint de historial; los turnos están en
`traces` y nadie los muestra). (f) **SOUL/wiki/trazas viven en ficheros SIN RLS**: el
aislamiento depende de sanear el nombre de fichero. (g) **El número de migración se reserva al
EMPEZAR, no al escribir**: dos agentes crearon el mismo `038` y hubo que renumerar (soul → 040).

### E · Pendiente técnico (reportado, no tocado — con su razón)
- **FTS `'spanish'`**: vive en columnas `GENERATED ALWAYS AS ... STORED` + triggers (003/004/013
  + schema.sql); cambiarlo exige migración de índices y reindexado. No es cosmético.
- **Voz TTS `es_MX`**: el asset lo eligió Pipe de oído y lo baja `install.py`; voz por despacho
  exige empaquetar una voz por variante.
- **Capa 3 de Pipe (lo que él pidió reservarse):** E2E del instalador en máquina limpia y el
  recorrido visual; login/registro reales del NotebookLM.

---

## Checkpoint: conector NotebookLM + regla de agnosticismo de jurisdicción (2026-07-15)

**Rama:** `feature/robustecimiento-sin-aws` (sin commitear a `main`). **Entorno de la sesión:**
Postgres apagado → los tests que dependen de DB no se corrieron aquí (dan PoolTimeout, NO es
regresión); los tests-script sin DB sí corrieron y pasan.

### A · Conector NotebookLM (CP-NLM) — nuevo
Cada despacho puede conectar SU propio NotebookLM como fuente (jurisdiction-neutral). Piezas:
- **Consulta viva gated** (`backend/mia/connectors/notebooklm/{__init__,gate,client}.py`): MIA
  consulta el NotebookLM del abogado durante la investigación (`agents/graph.py::_notebooklm_context`
  en `_research_single`). Pasa por candado de confidencialidad `gate.query_allowed` (bloquea en
  política `soberano`, exige opt-in `allow_notebooklm`, fail-closed). La respuesta entra SELLADA
  como contexto no confiable con `[VERIFICAR]`, NUNCA como cita respaldada.
- **Instalador in-app** (`connectors/notebooklm/setup.py` + `api/routes/notebooklm.py`, registrado
  en `api/main.py`): instalar (venv aislado 3.12/3.11 + `notebooklm-py[browser]` + chromium),
  conectar (login de Google, navegador visible) y selector de notebooks. Verificación REAL de
  sesión con `notebooklm auth check` analizando el TEXTO (no el exit code) + `list --json`.
- **UI** (`frontend/app/_components/ConexionesSection.tsx`): tarjeta "Consultar mi NotebookLM"
  multi-estado (instalar → conectar → elegir notebook → activar) con aviso "cada pregunta viaja a
  Google" y bloqueo en modo soberano.
- **Verificación:** `execution/test_notebooklm_gate.py` **33/33** (gate + client + instalador +
  auth por texto). Frontend `tsc --noEmit` limpio. Dos revisiones independientes (consulta viva +
  instalador): 0 bloqueantes; 2 MAYORES del instalador YA corregidos (instalación parcial disfrazada
  de "instalado" → marcador `installed.ok`; subprocess del CLI de terceros heredaba secretos → saneado).
- **PENDIENTE:** (1) capa 3 de Pipe = E2E en vivo en su Windows (instalar/login reales + confirmar
  flags `[VERIFICAR]` del CLII contra el `--help`). (2) **Siguiente terminal:** capacidades restantes
  del spec (sources_list, notebook_create, source_add con COMPUERTA de confidencialidad para datos de
  cliente, artifacts_list, generate, download a carpeta segura) + gobernanza + auditoría (solo
  acción/fecha/tipo/cuaderno, sin contenido). Se acordó construir el envoltorio MCP stdio SOLO cuando
  exista el consumidor (el chat/agente principal), que está diferido.

### B · MIA es AGNÓSTICA DE JURISDICCIÓN (regla dura — los tres agentes)
Corrección de Pipe: MIA NO es colombiana; se adapta al despacho que la instala (Colombia, México,
España…). La jurisdicción se resuelve por despacho (packs de `jurisdiction/`, default `generic`).
Regla propagada a `TRASPASO-MODELO.md` (visión) para Claude/Codex/Antigravity.
- **Hecho (seguro):** `memory/profile_manager.py:150` y `missions/decompose.py:58` — quitado el
  default `'colombia'` y el "Español de Colombia".
- **BACKLOG "des-colombianizar" (necesita DB viva; NO tocar a ciegas):** raíz = el pack tiene
  `id_formats`/`doc_markers`/`holidays` diseñados pero SIN cablear. Puntos: defaults `'co'` en
  `rag/sat_graph.py:171,209` + migración para `DEFAULT` de columna (`003/007/011`); anonimizador
  `security/anonymize.py` (cédula/NIT/teléfono/dirección CO → riesgo de confidencialidad, mover al
  pack); remitentes `.gov.co` y léxico "tutela/desacato" en `connectors/mailbox/base.py`; seed de
  corpus CO en `rag/ingest_corpus.py` → opt-in del pack; cosméticos (`es-CO`, voz TTS, `SMLMV`, FTS
  `spanish`). Inventario completo en la auditoría de Claude de esta sesión.
- **Auditorías:** Claude entregó inventario completo; **Codex** corre en su runtime (task
  `task-mrmuhgo0-3utkp8`) — su cross-check se folará la próxima sesión (sacar con `/codex:result`).

### C · Revisiones pendientes (read-only, correr DESPUÉS de este commit, sin escribir el repo a la vez)
- **Cursor:** revisión frontend/UX + jurisdicción-neutral + jerga (instrucción entregada a Pipe).
- **Antigravity:** revisión estética/visual del producto renderizado (instrucción entregada a Pipe).

### NOTA PARA ANTIGRAVITY — implementación de diseño (frontend)
Antigravity ya entregó su auditoría estética; ESTOS son los 6 arreglos que debe **implementar**
(su ventaja: puede renderizar y VERIFICAR visualmente). **Reglas:** trabaja sobre el commit más
reciente y LIMPIO (no edites si otro agente está escribiendo el repo — un escritor a la vez);
NO toques el backend; verifica en tema CLARO y OSCURO; mantén todo jurisdiction-neutral y sin
jerga técnica; commitea al terminar. Los items de config por-despacho (moneda USD, "tarjeta
profesional") NO son tuyos — los lleva Claude en el backend.

1. **Contraste del CTA en modo claro (Alta · WCAG).** `frontend/app/globals.css:29` (`--cta: 160 100% 42%`);
   usos `app/page.tsx:142`, `app/dashboard/page.tsx:182` (`bg-cta/15 text-cta`). En claro, `text-cta`
   sobre fondo claro da ~1.90:1 (ilegible). Arreglo: en tema CLARO usa un verde oscuro para
   texto/bordes (p. ej. `hsl(160 100% 25%)` / `#008050`) — idealmente un token aparte
   (`--cta-strong`/foreground) para no dañar `bg-cta/15`; reserva el neón para fondos oscuros.
   **Resultado esperado:** texto/insignias CTA ≥ 4.5:1 en claro; modo oscuro intacto.
2. **Tildes faltantes (Media · pulido).** `frontend/app/asuntos/[id]/page.tsx` líneas 229, 243, 297, 347:
   "Mia esta analizando/redactando/preparando" → "está"; "revision" → "revisión"; etc. **Resultado:**
   mismos textos de streaming con ortografía correcta, como ya lo hace `proyectos/[id]/page.tsx`.
3. **Locale `es-CO` → neutro (Media · agnosticismo).** `app/page.tsx:34`, `app/asuntos/[id]/page.tsx:51`,
   `app/memoria/page.tsx:258`, `app/proyectos/page.tsx:37`, `app/proyectos/[id]/page.tsx:43`,
   `_components/MailSearchDialog.tsx:43`, `_components/PanelUI.tsx:12,22`. Reemplaza `"es-CO"` por
   `undefined` en `toLocale*String(...)` para usar el locale del navegador. **Resultado:** fechas
   según el equipo del abogado; sin literal `es-CO`.
4. **Ejemplo con jerga colombiana (Baja · agnosticismo).** `app/dashboard/page.tsx:259`: «recuérdame
   radicar la tutela mañana a las 9» → ejemplo pan-hispano neutro, p. ej. «recuérdame presentar la
   contestación mañana a las 9». **Resultado:** sin modismos procesales de un solo país.
5. **Animación del menú móvil (Baja · premium).** `_components/Sidebar.tsx:113` (`DialogContent`).
   Añade deslizamiento: `data-[state=open]:animate-in data-[state=closed]:animate-out
   data-[state=open]:slide-in-from-left data-[state=closed]:slide-out-to-left duration-250`.
   **Resultado:** el drawer entra/sale deslizando, coherente con la bienvenida.
6. **Errores sin estilo en `FuentesPanel` (Baja · estados).** `_components/FuentesPanel.tsx:158`.
   Envuelve el error de carga en un contenedor con estilo de alerta suave (borde sutil, fondo
   desaturado, ícono de aviso pequeño), coherente con las tarjetas del sistema. **Resultado:** el
   error se ve cuidado, no texto plano.

Cierre: `npx tsc --noEmit` limpio y revisión visual en claro+oscuro antes de commitear.

### HALLAZGOS DE CURSOR (capa 3, 2026-07-15) — backlog para la terminal nueva
Cursor hizo revisión read-only de frontend/UX. Los 3 audits (Cursor, Antigravity, Claude)
COINCIDEN en el sesgo de jurisdicción. Prioridad:

**CRÍTICO — ✅ RESUELTO (2026-07-16, commit `ca7cd74`).** Ruta corregida a `/settings/model-policy`
y el fallo dejó de ser silencioso: si la elección de motor no se persiste, la bienvenida se detiene
con un motivo en llano en vez de decir "listo". Test de regresión en `test_second_brain_ui.py`
(frontend 14/14); `tsc --noEmit` limpio. Descripción original abajo:
- `frontend/app/activar/page.tsx` hace `PUT /api/settings/model-policy`, pero el backend expone
  `PUT /settings/model-policy` (SIN `/api`; `ConexionesSection.tsx` sí usa la ruta buena). En el
  viaje de bienvenida, elegir motor / opt-in OpenRouter **falla en silencio** (catch vacío) → el
  abogado cree que quedó "Todo en tu equipo"/OpenRouter y Mia sigue con otra política. OJO: es el
  MISMO endpoint que extendí para `allow_notebooklm` → desde Activar tampoco se podría fijar el
  opt-in de NotebookLM (Configuración sí). Arreglo: corregir la ruta + no tragar el error.

**ALTO — promesas/UX que dañan confianza:**
- Promesas contradictorias: "Notas del despacho" marcado *Próximamente* en onboarding pero Obsidian
  YA se instala/sincroniza en Conexiones; Telegram ofrecido como checkbox "normal" pero su activación
  real es un wizard @BotFather + `.env`, no OAuth. Alinear expectativa.
- Deep-links de borrador: "Para tu decisión" y el badge llevan a `/asuntos/{id}`, no a
  `/asuntos/{id}/revisar`; y `?sin_borrador=true` no se consume (el abogado vuelve al chat sin
  explicación). Añadir CTA "Revisar borrador" + leer el query.
- Fallos tragados: `memoria/page.tsx::act()` con `.catch(()=>{})`; detección de drift del curator por
  `message.includes("409")` es frágil → usar `err.status === 409`.

**MEDIO — sesgo de jurisdicción en frontend (se suma al backlog de "des-colombianizar"):**
- Placeholders CO: "Fajardo & Asociados S.A.S." (forma societaria), "tarjeta profesional",
  "Lexia Abogados" (register). Empty state "radicar la tutela". Detonador `SMLMV/SMMLV`
  (`revisar/page.tsx`). Copy "Rama Judicial" en el MCP de consulta de procesos. `es-CO` en fechas
  (ya listado). Moneda fija USD (Panel/Configuración) → moneda por despacho. CountrySelector pone
  Colombia primero (deliberado, no bug). Solo el pack `co` instalado en backend.
- Jerga técnica que se filtra: placeholder "Nombre del índice" (Pinecone) — el abogado no sabe qué
  es; fallback de automatizaciones muestra `clave: valor` crudo.
- Capacidades muertas: `/settings/agents` (Agent Hub) y `gold-cases` tienen backend pero NO UI →
  orquestar o esconder hasta que haya pantalla.
- `AuthGate` renderiza `null` mientras valida el token → pantalla en blanco (poner un loader).

Nota: Cursor confirma que §G se cumple en general (no hay "MCP/HITL/tenant/pgvector" en el copy).

---

## Checkpoint: instalador de aceptación del robustecimiento (2026-07-14)

- Se reconstruyó desde cero el instalador NSIS de la rama
  `feature/robustecimiento-sin-aws`: backend, LiteLLM, frontend, PostgreSQL
  portátil y la cáscara Tauri. Artefacto local:
  `desktop/src-tauri/target/release/bundle/nsis/Mia_0.1.0_x64-setup.exe`
  (452.488.052 bytes; SHA-256
  `A9E80ACEE007D5A2407107F101F751D4160964C665305749416CEC8535F4FF33`).
- Gates posteriores al build: installer 30/30, backend packaging 23/23,
  LiteLLM packaging 66/66, frontend packaging 24/24, shell hardening 84/84,
  first run real 68/68 y supervisor PASS. Se actualizó el gate antiguo que
  contaba exactamente tres usos de `child_died`: ahora protege los tres
  bucles de arranque sin rechazar los usos adicionales del supervisor.
- Claude Code repitió controles y verificó el hash. Veredicto: **PASS
  condicionado para prueba de aceptación local; no producción**. El siguiente
  gate es instalar y arrancar el NSIS real, recorrer visualmente la app y
  comprobar LiteLLM/backend/frontend de punta a punta.
- El instalador no tiene firma de código. Es válido para prueba local, pero la
  firma y la aceptación visual son requisitos antes de distribuirlo a terceros.

---

## Checkpoint: robustecimiento local sin AWS (2026-07-14) — supervisor autorreparable

- La cáscara Tauri vigila cada 5 segundos backend, frontend y LiteLLM después del arranque.
  Exige 3 fallos consecutivos, reinicia únicamente hijos propios y se detiene tras 3 recaídas
  por hora. Los servicios adoptados se observan y avisan, pero nunca se matan ni reemplazan.
- El reinicio automático del motor comparte exclusión con el reinicio manual y revalida salud
  después de tomarla; así no actúa sobre un PID nuevo usando un sondeo viejo. `shutdown()` sigue
  gobernando el cierre y `register_child()` mata cualquier hijo creado después de cerrar.
- `RuntimeHealthBanner` muestra recuperación/error en lenguaje llano dentro de la app; en navegador
  normal no aparece. Gates: `cargo check` PASS, tests Rust 3/3, gate estático PASS, `tsc` PASS y
  build Next 15/15. Claude Code re-auditó la carrera y dio **PASS sin bloqueantes**.

---

## Checkpoint: robustecimiento local sin AWS (2026-07-14) — control atómico de gasto

- Rama local `feature/robustecimiento-sin-aws`; todavía no se ha hecho push. Esta fase añade
  `035_atomic_ai_budget.sql`: cada llamada pagada reserva saldo en PostgreSQL antes de salir y
  liquida el costo real al terminar. Dos trabajos simultáneos ya no pueden atravesar juntos el tope.
- `turn_usage` conserva el detalle; `ai_budget_months` es el saldo mensual autoritativo desde la
  primera reserva, para no depender del buffer. Motores de suscripción/local no reservan; si un
  motor pagado no cabe y existe respaldo gratuito, Mia degrada a este sin detener el trabajo.
- Un corte incierto conserva la estimación por prudencia; una liberación con fallo transitorio de
  DB reintenta tres veces. RLS forzado mantiene las reservas aisladas por despacho.
- Gates: `test_atomic_ai_budget` 11/11, `test_observability` 22/22,
  `test_llm_fallback` 25/25 y `test_migration_ledger` PASS. Claude Code encontró el riesgo de
  liberación transitoria, se corrigió, y su segunda auditoría dio **PASS sin bloqueantes**.

---

## Checkpoint más reciente: Sesión 47 (2026-07-13/14) — Sala de estrategia (War Room) + OpenRouter como motor propio/respaldo

> Sesión que RETOMÓ tras un "error del computador". Diagnóstico: NO se dañó el repo de MIA
> (`mia/.git` intacto y sincronizado); lo dañado fue un `.git` fantasma y vacío en la carpeta
> contenedora `Mia-Super Agent/` (un `git init` viejo, sin remoto), que se limpió. Regla para el
> futuro: el repo de trabajo es `mia/`, no la raíz — usar `git -C mia`.

### Qué se hizo esta sesión (lenguaje simple)

Dos features nuevas, en paralelo, con orquestación multi-agente (recon → ejecución → auditoría
adversarial → corrección), ambas pusheadas a `main`:

- **Sala de estrategia (commit `e8bcc51`)** — pivote de la apuesta #2 de NotebookLM (era un
  podcast de audio; Pipe lo giró a un **debate ESCRITO** tipo "War Room"). En un ASUNTO con
  expediente, el abogado convoca un panel de 3-4 counsel con posturas OPUESTAS (defiende tu tesis
  / contraparte / juez escéptico / especialista); cada uno analiza el caso citando el expediente
  `[doc n]`, se contrastan en una ronda de réplicas, y un moderador sintetiza un dictamen
  (fortalezas / riesgos / puntos ciegos / estrategia / próximo paso). **Decisiones de Pipe:** MIA
  propone el panel y el abogado lo ajusta; salida = conclusiones arriba + debate desplegable
  abajo; cierre = dictamen + botón "convertir en borrador" (pasa por el gate de citas y HITL
  normales); solo ASUNTOS; nombre de cara al abogado = "Sala de estrategia" (§G, nunca "agente").
  Reutiliza personas.Persona, delegation.run_parallel (patrón research_swarm),
  untrusted.render_documents y verification.annotate_draft en CADA intervención y la síntesis.
- **OpenRouter como motor propio + respaldo (commit `b582541`)** — el abogado conecta su propia
  cuenta de OpenRouter (y la carga de crédito) para usar MIA (1) como MOTOR PRINCIPAL (política
  nueva "openrouter", para despachos sin la suscripción del equipo) y (2) como RESPALDO/overflow
  (en "suscripción"/"nube", con opt-in `allow_openrouter`). Validación en vivo de la clave en
  `/activar` (4ª opción de motor) + activación en caliente.

### Frontend a revisar (Cursor/Pipe — capa 3)

- **Sala de estrategia (TODO NUEVO):** `frontend/app/asuntos/[id]/page.tsx` (botón "Convocar Sala
  de estrategia" en la barra de acciones + estado del stream) y `frontend/app/asuntos/[id]/
  _components/SalaEstrategia{Dialog,Result}.tsx` + `warroom-types.ts`. Recorrido: en un asunto CON
  expediente, convocar la sala → ajustar el panel → ver el debate en vivo (rondas) → dictamen con
  conclusiones + debate colapsable → "Descargar en Word" y "Convertir en borrador". Sin expediente
  debe mostrar aviso en llano (no error mudo).
- **OpenRouter:** `frontend/app/activar/page.tsx` — la 4ª tarjeta de motor "Tu cuenta de
  OpenRouter" con su campo de clave (✓ en vivo) y, en otras políticas, el campo opcional "más uso".

### Resultado de verificación (3 capas)

- **Capa 1 (regresión, DB dev en 55432):** test_warroom **52/52**, `test_rls` **19/19** (HALT,
  +7 checks nuevos de `warroom_results` con RLS fail-closed), `check_env_pins` **9/9** (HALT),
  test_doc_citation_guard **19/19**, CP9 test_document_pipeline **45/45**, test_openrouter_policy
  **16/16**, test_welcome_keys **41/41**, test_litellm_packaging **66/66**, test_model_policy
  **40/40**, test_llm_fallback **25/25**, test_agent_core **26/26**. `tsc --noEmit` verde; `npm run
  build` compila 15/15 páginas (queda un flake ambiental de Windows al generar `500.html`, ajeno
  al código — se reproduce en árbol pristine).
- **Capa 2 (DOS auditorías adversariales independientes):** 0 BLOQUEANTES. **Sala:** aislamiento
  entre despachos y gate de citas OK; 2 mayores + 5 menores corregidos (réplicas desalineadas ante
  fallo parcial de un panelista; error invisible sin expediente; inyección de 2º orden entre
  intervenciones ahora SELLADA con `untrusted.fence_block`; degradación por presupuesto funcional
  a 0.85 del tope; clamp del tamaño de panel en el SSE; agentes reales sin clonar "defensor";
  cobertura RLS de la tabla nueva). **OpenRouter:** la **muralla de confidencialidad SE SOSTIENE**
  ("soberano" jamás enruta a la nube por ningún fallback; la clave nunca se filtra); 1 mayor + 3
  menores corregidos (overflow inerte tras reinicio en caliente → helper `_openrouter_key_present`
  con cache 5s lee el `.env`; auto-omisión del wizard sin la clave del motor; landmine de
  `AgentCore.model` → default None).
- **Capa 3: PENDIENTE — de Pipe** (recorrido visual en vivo de ambas features).

### Pendientes y próximo paso

1. **Capa 3 de Pipe:** recorrer la Sala de estrategia y la nueva opción de OpenRouter en vivo
   (encender MIA Modo B; la DB dev ya quedó arriba en 55432).
2. **ACCIÓN DE PIPE (deuda de OpenRouter):** confirmar los slugs EXACTOS de los modelos en
   openrouter.ai/models (`anthropic/claude-sonnet-4.6`, `anthropic/claude-haiku-4.5`). Un slug
   errado degrada a `mia-local` sin romper, pero pierde el motor OpenRouter en silencio.
3. Acciones de Pipe sin cambio: firma digital (Azure Trusted Signing) + apps OAuth; capa 3 en
   frío del instalador (bloque instalador). Apuesta #3 de NotebookLM (transformaciones al ingerir)
   sigue diferida.

### Trabajo en background sin leer

Nada — 2 recon iniciales (ClaudeClaw, sistema de motor), 3 recon de MIA, 5 ejecutores, 2 auditores
adversariales y 2 correctores: todo leído y reflejado aquí. La regresión la corrió esta terminal.

### Decisiones tomadas y suposiciones declaradas

- **El "War Room" de ClaudeClaw NO existe** (se verificó el zip): ClaudeClaw solo tiene delegación
  1-a-1 + hive mind, no un panel que debate. La Sala de estrategia es diseño propio de MIA.
- **Panelistas sintéticos de código** (`WARROOM_STANCES`, 4 posturas) reemplazables por Agentes
  del despacho — no depende de que el despacho haya creado personas.
- **Política "openrouter" = consentimiento por selección** (no depende de `allow_openrouter`); el
  overflow en "suscripción"/"nube" SÍ exige el opt-in (gate de confidencialidad CP-S3).
- Las dos features tocan archivos DISJUNTOS (Sala: warroom/ux/asuntos/033; OpenRouter:
  llm/config/welcome/settings/activar/yaml) → paralelo seguro sin colisión ni migración compartida.

---

## Nota paralela (2026-07-12, sesión Fable) — Refuerzo del gate de citas: guardián de referencias [doc n] fantasma

> Vía SEPARADA del bloque instalador (no lo toca). Registrada aquí a pedido de Pipe porque él estaba
> corriendo otra sesión al mismo tiempo. Backend Python puro, sin dependencias nuevas, sin cambios en
> `packaging/`/`desktop/` → no afecta el instalador ni el build en caliente.

### Qué se hizo (lenguaje simple)
Punto de partida: se analizó el repo externo `earlyaidopters/notebooklmreimagined` para sacar ideas
para MIA. De ahí salieron 3 apuestas; se implementó la #1 (la de mayor impacto y menor riesgo).

**El hueco que cierra:** cuando MIA redacta y "cita" un documento del expediente (ej. "según el poder
[doc 9]"), nadie comprobaba que ese documento existiera. Si solo se recuperaron 5 documentos y el
modelo inventaba un `[doc 9]`, esa cita pasaba **como si estuviera respaldada**. Ahora un guardián
determinista detecta toda referencia `[doc n]` fuera del rango real y le añade `[VERIFICAR]` — igual
que cualquier cita sin respaldo (nunca borra ni bloquea; solo avisa). Es el análogo de la técnica de
"lista blanca de IDs" de NotebookLM/open-notebook, aplicada al diferenciador #1 de MIA.

### Archivos (commit `ec1aa15` en `main`, ya pusheado a GitHub)
- `backend/mia/agents/verification.py`: `flag_phantom_doc_citations()` + `highest_sealed_doc_index()`
  (el rango válido sube al mayor `<<<DOC n>>>` que vio el modelo, incluyendo adjuntos por `@expediente`,
  para no marcar como fantasma una cita legítima a un adjunto). `annotate_draft` gana el parámetro
  opcional `num_documents` (retrocompatible; corre el guardián DESPUÉS del escáner legal).
- `backend/mia/agents/graph.py` (`_verify_draft`): cablea el rango = max(docs RRF, adjuntos sellados).
- `execution/test_doc_citation_guard.py`: gate nuevo, **19/19**, sin DB/red.

### Verificación (3 capas)
- **Capa 1:** test 19/19; AST OK; firma retrocompatible (el nodo research y `eval/scoring.py` no cambian).
- **Capa 2:** revisor independiente con contexto fresco → halló 1 falso positivo real (cita legítima a
  adjunto `@expediente`) → **corregido + test**. Demás hallazgos van en dirección segura (documentados).
- **Capa 3 (visual):** N/A — no se tocó frontend. El informe de verificación solo gana una clave
  aditiva `docs_fantasma` (no rompe render). *Opcional a futuro:* la Pantalla 2/3 podría mostrar el
  conteo de referencias fantasma detectadas.

### Alcance y pendientes
- **Cubre el flujo de ASUNTO** (verification_node). **El flujo de PROYECTO (work_node) NO pasa por
  verificación** — hoy su respuesta llega sin red de `[VERIFICAR]`. Decisión de diseño a **confirmar
  con Pipe** si quiere extenderlo.
- **Apuestas #2 y #3 DIFERIDAS** (en memoria `mia-notebooklm-apuestas`): #2 audio del expediente en
  modo debate/crítica (necesita voz multi-locutor = pesos nuevos, zona sensible del instalador →
  retomar al cerrar el instalador); #3 transformaciones al ingerir (extraer pretensiones/hechos/
  cronología al subir; toca la ruta de upload, riesgo medio).

### ⚠️ Incidente de sesiones concurrentes (resuelto, sin pérdida)
Había otra sesión corriendo sobre el mismo repo; las operaciones de git chocaron. **Desenlace limpio:**
el commit del banco de oro quedó en `bfa7d07`, este trabajo en `ec1aa15`, historia lineal, nada perdido.
La carrera dejó un conflicto de `git stash pop` (autostash) en `memory/session-summaries.md` que se
resolvió conservando TODO el contenido (lo stasheado era una entrada vieja ya presente en el archivo);
el autostash ya se descartó tras confirmar que no aportaba nada. **Recomendación: no correr dos sesiones
que hagan git sobre el mismo repo a la vez.** (Confirmado en vivo por la sesión de Claude que desenredó
el choque; guardián verificado a fondo en capa 2 — sin falsos positivos, CP9 45/45 sin regresión.)

---

## Checkpoint más reciente: Sesión 46 (2026-07-12) — PULIDO PRE-PRUEBA: Riesgo #60 cerrado + auditoría final de seguridad/bugs + pre-flight del motor sin llaves

### Qué se hizo esta sesión (lenguaje simple)

Pipe pidió, antes de instalar en frío, "dejarlo listo para pruebas": mejorar lo que quedaba, revisar
seguridad y bugs, y solucionar lo que saliera. Se corrieron **tres auditorías adversariales
independientes** (seguridad, corrección/E2E en frío, y revisión del diff) — **0 bloqueantes en todo**.

- **Se cerró el Riesgo #60 (mejora que Pipe pidió expresamente):** el motor de modelos ahora se
  **reinicia solo, en caliente**, cuando el abogado guarda su clave en la pantalla de bienvenida —
  ya NO hay que cerrar y reabrir MIA. Se implementó vía un comando interno de la cáscara Tauri
  (`restart_litellm`): el frontend, que corre dentro de la cáscara, lo invoca tras guardar la clave;
  la cáscara mata el motor viejo, espera a que libere el puerto y lo re-lanza leyendo la clave nueva,
  re-asignándolo al Job Object anti-huérfanos. En modo desarrollo (navegador) degrada solo al aviso
  de "reabre Mia", sin romper nada.
- **Se eliminó la única incógnita real de tu prueba (pre-flight del motor sin llaves):** nadie había
  encendido `mia-litellm.exe` con CERO llaves de proveedor, que es exactamente el estado del arranque
  en frío cuando el abogado difiere las claves. Se probó: arranca en ~1 s, responde salud y lista los
  5 modelos. Ya no es un riesgo.
- **Dos endurecimientos de seguridad baratos:** validación anti-inyección extra al escribir el `.env`
  y permisos restrictivos (solo el dueño) sobre el archivo de claves.

### Frontend a revisar (Cursor — capa 3): un cambio mínimo
`frontend/app/activar/page.tsx` (`finish()`): tras guardar la clave, si corre dentro de la cáscara,
invoca `restart_litellm` y, solo si el motor se reinició, quita el aviso "cierra y reabre". En
navegador (dev) el aviso se conserva. Cubierto por gate + revisión; falta el recorrido visual en vivo.

### Resultado de verificación (3 capas)
- **Capa 1:** `cargo build` exit 0; `test_shell_hardening` **84/84** (sube de 77 con 7 checks nuevos
  del reinicio), `test_packaging` 23/23, `test_litellm_packaging` 60/60, `test_first_run` 68/68.
  **NO se re-corrieron `test_welcome_keys` ni `test_rls`** porque la DB dev de mia no estaba encendida
  (puerto 55432); el único cambio en esa ruta (validación `\n`/`\r` en `env_writer`) se micro-probó
  aparte. **Pendiente: correrlos en el próximo arranque con la DB arriba.**
- **Capa 2:** revisor adversarial independiente de concurrencia/ciclo de vida sobre el diff de la
  cáscara — **0 bloqueantes, 0 mayores** (sin deadlocks, ningún Mutex cruza `await`, el flag de
  reinicio no se fuga, el proceso re-lanzado se re-asigna al Job, caminos "no-aplica" seguros para
  dev/adoptado/cerrando). 3 menores cosméticos/pre-existentes, ninguno rompe la prueba.
- **Capa 3: PENDIENTE — de Pipe (sin cambio respecto a F4):** el E2E en frío en máquina 100% limpia
  sigue siendo el único pendiente para cerrar el bloque instalador. Ahora, al guardar la clave de
  respaldo en `/activar`, el motor debe quedar activo SIN reabrir (antes obligaba a reabrir).

### Pendientes y próximo paso
1. **Capa 3 de Pipe:** E2E en frío (doble clic → primer arranque → viaje de bienvenida → guardar clave
   y ver que el motor queda activo sin reabrir). En `desktop/src-tauri/target/release/bundle/nsis/`.
   Nota: el `.exe` en el bundle es de la sesión 45; si se quiere probar el reinicio en caliente del
   #60 hay que RE-ENSAMBLAR el instalador (`packaging/build_installer.ps1`) para incluir la cáscara
   recompilada de esta sesión.
2. **Correr `test_welcome_keys` + `test_rls`** con la DB dev encendida (verificación diferida de capa 1).
3. **Deuda consciente nueva (Riesgo #61), NO bloquea la prueba:** identidad de cáscara falsificable
   solo por un atacante local (aceptado en modelo mono-abogado); carpeta de datos = carpeta de
   programa (aplazado); el setup no re-corre migraciones en una actualización futura (deuda de
   "update").
4. **Acciones de Pipe sin cambio:** firma digital (Azure Trusted Signing) + registrar apps OAuth.

### Trabajo en background sin leer
Nada — 3 auditores (seguridad/bugs/diff), 1 ejecutor y 1 recon de diseño: todo leído y reflejado aquí.

### Decisiones tomadas y suposiciones declaradas
- **El reinicio del motor lo dispara el frontend, no el backend:** el frontend ya vive dentro de la
  cáscara Tauri (`withGlobalTauri`), así que invoca el comando directo; el backend Python no tiene
  canal hacia la cáscara. Más limpio y sin dependencias nuevas.
- **El aviso "cierra y reabre" solo se borra si el motor confirma que se reinició** (no incondicional):
  si el motor fue adoptado o hay un reinicio en curso, se conserva el aviso — más honesto.
- **Se corrigió lo barato y se DOCUMENTÓ lo riesgoso** (Riesgo #61): cambiar el layout de carpetas o
  la firma de identidad justo antes del E2E en frío es más peligroso que el problema que resuelven;
  mejor con la prueba de Pipe como red.
- Los comandos de app de Tauri v2 no requieren ACL de capabilities (la CSP ya permite `ipc:`).

---

## Checkpoint anterior: Sesión 45 (2026-07-11) — BLOQUE INSTALADOR: Fase 4 (instalador de doble clic) ENSAMBLADA — falta SOLO el E2E en frío de Pipe

### Qué se hizo esta sesión (lenguaje simple)

Se armó el **instalador de doble clic** que un abogado usa para instalar MIA sin tener Python,
Node ni base de datos en su computador. La cáscara de escritorio no empaqueta sola los motores,
así que se cableó cómo se colocan todos junto al programa y se incluyó una **base de datos
portable con el buscador vectorial adentro**. Resultado real y probado: `Mia_0.1.0_x64-setup.exe`
(~452 MB), que instala sin pedir permisos de administrador y **funciona sin internet**.

- **Ensamblaje (`packaging/build_installer.ps1` + `tauri.conf.json`):** recompila los tres motores,
  copia el PostgreSQL portable (con pgvector) y arma el instalador NSIS. Cada motor + el archivo
  de arranque quedan **directamente junto al programa** (verificado instalando en una carpeta
  aislada: nada queda mal ubicado — era la duda central de esta fase).
- **La incógnita crítica se resolvió a favor:** la cáscara busca los motores en rutas fijas junto
  a su exe, y ahí quedan exactamente. Instalación de prueba: 804 MB en disco, todo en su sitio.

### Frontend a revisar (Cursor — capa 3): NO APLICA
Esta sesión fue empaquetado + cáscara (Rust) + scripts. No hay UI nueva. La capa 3 pendiente es
de **Pipe**, no de Cursor (ver abajo).

### Resultado de verificación (3 capas)

- **Capa 1:** gates del instalador verdes — `test_installer_bundle` 30/30 (NUEVO), `test_packaging`
  23/23, `test_litellm_packaging` 60/60, `test_frontend_packaging` 24/24, `test_shell_hardening`
  77/77, `test_first_run` 68/68 — + HALT `test_rls` 12/12 y `check_env_pins` 9/9 + `test_welcome_keys`
  39/39. Línea base sube de 85 a 86 suites. Instalador producido y verificado por instalación
  aislada (payloads junto al exe, sin subcarpeta `resources/`, pgvector presente, pgAdmin ausente).
- **Capa 2:** TRES revisores adversariales independientes (seguridad, corrección/build, coherencia
  cáscara/§G). **0 BLOQUEANTES**, ningún secreto de Pipe viaja en el instalador, DB bien endurecida.
  **5 correcciones aplicadas y re-verificadas:** (1) **console REVERTIDO a True** — la cáscara ya
  oculta la ventana con CREATE_NO_WINDOW; el `console=False` que se había puesto vaciaba el stdout
  con el que el primer arranque le dice al abogado *por qué* falló (regresión introducida y
  corregida en la misma sesión); (2) **frontend atado a 127.0.0.1** — estaba en 0.0.0.0, visible
  para toda la red del despacho; (3) **pgAdmin fuera** del paquete de base de datos (−736 MB:
  860→124 MB, y menos superficie de ataque); (4) **WebView2 `offlineInstaller`** para instalar sin
  internet; (5) gate endurecido. Detalle en `memory/session-summaries.md` sesión 45 y Riesgo #59.
- **Capa 3: PENDIENTE — de Pipe (ÚNICO pendiente de F4):** instalar el `.exe` en una **máquina
  100% limpia** (sin Python/Node/Postgres, estado virgen) con doble clic y confirmar el primer
  arranque en frío + el viaje de bienvenida. Es física: no se puede hacer en la máquina de dev
  (tiene el entorno + colisión de puerto 55432). El instalador está en
  `desktop/src-tauri/target/release/bundle/nsis/Mia_0.1.0_x64-setup.exe`.

### Pendientes y próximo paso

1. **Capa 3 de Pipe:** el E2E en frío en máquina limpia (arriba) — cierra el bloque instalador.
2. **Riesgo #60 (ola futura):** el reinicio automático del motor de modelos tras guardar la clave
   en el wizard NO se hizo en F4 (requiere IPC de Tauri); la mitigación de F3 (clave obligatoria +
   aviso de reabrir) sigue vigente.
3. **ACCIÓN DE PIPE (sin cambio):** firma digital (Azure Trusted Signing) para vender sin la
   advertencia de "editor desconocido" de Windows, y registrar las apps OAuth.

### Trabajo en background sin leer
Nada — 1 recon, 2 builds delegados y 3 revisores de capa 2: todo leído y reflejado aquí. La
instalación de prueba del build corregido la corrió y verificó la propia terminal (804 MB, layout
correcto) y se limpió (carpeta + clave de registro).

### Decisiones tomadas y suposiciones declaradas

- **console=True (no False):** la ventana negra la elimina la cáscara con CREATE_NO_WINDOW, no el
  spec; windowed rompía el diagnóstico del primer arranque. Cierra Riesgo #59 pt 3/7 por diseño.
- **installMode currentUser:** instala sin pedir administrador (más fácil para el abogado, §B);
  si algún día se quisiera "para todos los usuarios" cambia a perMachine (implica UAC).
- **WebView2 offlineInstaller** (+~130 MB al instalador) elegido sobre el descargador para que el
  E2E en frío/offline no falle — coherente con local-first. Reversible en `tauri.conf.json`.
- **pgAdmin/StackBuilder excluidos** del pgsql: MIA nunca los usa (conecta por psycopg + initdb).
- El Postgres portable se toma de `..\tools\postgres16-portable-full\pgsql` (fuera del repo);
  `build_installer.ps1` lo autodetecta y exige pgvector antes de empaquetar.

---

## Checkpoint anterior: Sesión 44 (2026-07-11) — BLOQUE INSTALADOR: Fase 3 (bienvenida cinematográfica + activación de llaves) COMPLETA

### Qué se hizo esta sesión (lenguaje simple)

Pipe fijó como meta cerrar la **Fase 3 del instalador** y, al ver el onboarding actual, pidió algo
más grande: que **toda la primera vez que un abogado abre MIA se sienta premium** ("cinematográfico,
con wow factor, más amigable"). Se rediseñó la experiencia completa de bienvenida como un solo viaje:

- **Crear despacho → Activar → Conocer tu despacho → Entrar**, todo con el mismo diseño: fondo negro
  con una aurora teal que se mueve sola, la marca MIA que respira, una pregunta a la vez con
  transiciones suaves, una barra de progreso tipo constelación y una celebración al final. (Se
  estrenó la librería de animaciones que ya estaba instalada sin usar.)
- **Paso nuevo "Activar":** el abogado confirma el motor de Mia (su suscripción, ya viene elegida)
  y pega la **clave de búsqueda en sus documentos**, que se comprueba en vivo con un ✓. Todo en
  lenguaje llano, sin una sola palabra técnica, y siempre con la opción de "hacerlo después".
- **La clave de búsqueda queda activa al instante** (Mia ya puede leer y buscar en documentos sin
  reiniciar). La clave de respaldo del motor, si la pega, se activa la próxima vez que abra Mia —
  y ahora se lo decimos claramente.

### Frontend a revisar (Cursor — capa 3): TODO NUEVO

Esta sesión es sobre todo frontend. Pantallas rediseñadas/nuevas: `frontend/app/register/page.tsx`
("Crear tu despacho"), `login/page.tsx`, `activar/page.tsx` (NUEVA), `onboarding/page.tsx`
(rediseño preservando el guardado automático y el resumen final), e infraestructura visual nueva en
`frontend/app/_welcome/`. El Sidebar se oculta en `/activar` y `/onboarding` (pantalla completa).

### Resultado de verificación (3 capas)

- **Capa 1: línea base sube de 84 a 85 suites** con `test_welcome_keys` 39/39. Verdes (por tramos):
  `test_rls` 12/12 y `check_env_pins` 9/9 (HALT), `test_first_run` 68/68 (con la migración 031 nueva),
  `test_setup_wizard` 28/28, `test_onboarding_draft` 15/15, `test_hitl_flow` 21/21. `npm run build`
  verde (15 páginas; `/activar` nueva). La migración 031 entra sola al bundle del instalador.
- **Capa 2: CUATRO revisiones adversariales independientes** (seguridad, corrección backend,
  corrección frontend, §G/visual/accesibilidad). 0 BLOQUEANTES. Seguridad SIN mayores explotables
  (el ataque de inyección al `.env` para pisar secretos de instalación está bloqueado). §G LIMPIO
  (cero jerga visible al abogado). Se corrigieron y re-verificaron: el caso "motor en la nube"
  (ahora exige la clave y avisa fuerte de reabrir), dos claves opcionales tratadas de forma
  inconsistente, una doble llamada de validación al pulsar Enter, dos hallazgos de accesibilidad
  (campos y etiquetas sin nombre accesible), y varios menores de robustez de la escritura del `.env`.
  Detalle en `memory/progress.md` sesión 44.
- **Capa 3: PENDIENTE — de Pipe:** recorrer en vivo el nuevo viaje de bienvenida (crear despacho →
  activar → conocer el despacho → celebración) y confirmar que se siente premium.

### Pendientes y próximo paso

1. **PRÓXIMA SESIÓN → F4 (la ÚLTIMA fase):** instalador NSIS/MSI + prueba en frío en máquina limpia,
   con los 7 puntos acumulados del Riesgo #59 (recompilar los dos ejecutables ahora incluye
   `welcome.py` + migración 031 + `env_writer.py`) y el nuevo Riesgo #60.
2. **Riesgo #60 (nuevo):** el motor que depende del motor de modelos (opción "nube", o el respaldo
   de la suscripción cuando el abogado NO tiene el CLI de Claude Code) no queda activo hasta cerrar
   y reabrir MIA una vez. La pantalla de activación ya lo advierte con fuerza; el reinicio automático
   es trabajo de F4. Para el equipo de Pipe (suscripción con su CLI) no aplica.
3. **ACCIÓN DE PIPE (sin cambio):** registrar la firma digital (Azure Trusted Signing) para vender
   sin la advertencia de Windows, y las apps OAuth (guía en `docs/guia-conectar-correo-y-nube.md`).

### Trabajo en background sin leer

Nada — 4 recon, 4 ejecutores, 4 revisores adversariales, 2 correctores y 2 verificaciones: todo
leído y reflejado aquí.

### Decisiones tomadas y suposiciones declaradas

- **La clave de búsqueda (Voyage) se activa en caliente** porque el backend la usa directamente;
  la de respaldo del motor (Anthropic) la lee el motor de modelos solo al arrancar → se difiere
  con aviso claro. No se abrió ningún puente nuevo hacia la cáscara de escritorio (se respeta el
  blindaje de F2 y el Riesgo #59).
- **Se pide la clave con opción de diferir.** De dónde sale la llave (Pipe la provee vs. cada
  despacho la suya) es una decisión de negocio futura, fuera de F3.
- **Confianza mono-despacho:** cualquier usuario ya autenticado puede configurar las llaves de su
  instalación; si MIA pasa a multi-despacho hará falta un rol de "administrador de la instalación".
- La política de motor "suscripción" ya era la de fábrica: el wizard solo la confirma en llano.

---

## Checkpoint anterior: Sesión 43 (2026-07-11) — BLOQUE INSTALADOR: Fase 2 (primer arranque automático) COMPLETA

### Qué se hizo esta sesión (lenguaje simple)

Se completó la **Fase 2 del instalador** (meta que Pipe fijó para la sesión): en una máquina
limpia, MIA ahora **se prepara sola la primera vez que se abre**:

- **Primer arranque automático:** la cáscara detecta que MIA no está preparada y dispara un
  paso de preparación que crea la carpeta de datos del abogado, genera las llaves de seguridad
  solas (una sola vez, jamás se pisan), crea la base de datos desde cero —cerrada al mundo:
  solo escucha dentro del computador— aplica las 28 migraciones y deja la memoria conversacional
  lista. Si el abogado cierra la ventana a mitad de la preparación, la próxima apertura **se
  auto-repara** (esto salió de la revisión adversarial: antes quedaba rota para siempre).
- **El motor de modelos (LiteLLM) ya es un ejecutable propio** (108 MB, sin Python): la cáscara
  lo enciende y lo vigila como 4º servicio, con la misma regla de identidad de siempre (nada
  se adopta por solo responder — exige la llave y los nombres de modelos de MIA).
- **Hallazgo de seguridad corregido y verificado en vivo:** el motor de modelos quedaba
  escuchando hacia toda la red del despacho (cualquier equipo de la oficina podía usar las
  llaves de la firma); ahora solo escucha dentro del computador — se probó con un intento real
  desde la red, rechazado.

### Resultado de verificación (3 capas)

- **Capa 1: regresión completa 84/84 suites ALL PASS** (línea base sube de 82 a 84 con
  `test_first_run` 68/68 —initdb y login reales— y `test_litellm_packaging` 60/60;
  `test_shell_hardening` sube de 69 a 77 checks). `test_rls` 12/12 y `check_env_pins` 9/9
  (HALT) intactos. cargo build exit 0. Cero reintentos.
- **Capa 2: TRES revisiones adversariales independientes** (bootstrap, cáscara, LiteLLM):
  **6 MAYORES + 5 menores, TODOS corregidos y re-verificados** antes del commit. Los más
  importantes: preparación interrumpida quedaba rota para siempre (ahora marcador de
  finalización + gatillo triple); archivo de llaves podía quedar a medias (ahora escritura
  atómica); el motor de modelos expuesto a la red local (ahora solo loopback, verificado
  en vivo); el gate no probaba un login real (ahora sí). Detalle en `memory/progress.md`
  sesión 43.
- **Capa 3: PENDIENTE — de Pipe** (sin UI nueva esta sesión; sigue la lista acumulada abajo).

### Capa 3 para Pipe (cuando retome)

1. Sin cambios visuales nuevos esta sesión (todo fue motor, cáscara y empaquetado). Sigue
   pendiente lo acumulado: abrir la cáscara y ver el splash (sesión 42) + recorrido de
   producto de las sesiones 39-41.

### Pendientes y próximo paso

1. **PRÓXIMA SESIÓN → F3 (wizard de bienvenida):** la primera pantalla que ve el abogado al
   abrir MIA instalada — pedirle solo las llaves mínimas y dejar la política de motor
   "suscripción" lista, todo en llano (§G). Luego F4 (instalador NSIS + E2E en frío en máquina
   limpia, con los 7 puntos acumulados del Riesgo #59 — incluye recompilar los dos ejecutables
   con lo de esta sesión).
2. **ACCIÓN DE PIPE (sin cambio):** registrar la firma digital (Azure Trusted Signing) para
   vender sin la advertencia de Windows, y las apps OAuth (guía en
   `docs/guia-conectar-correo-y-nube.md`).
3. Deuda consciente (Riesgo #59): los ejecutables ya compilados en dist/ se recompilan en F4
   (el del backend aún no trae el paso de preparación; el del motor de modelos no trae la
   inyección default de loopback — la protección vigente es la configuración del instalador,
   verificada en vivo).

### Trabajo en background sin leer

Nada — 3 recon, 3 ejecutores, 3 revisores, 3 correctores y la regresión: todo leído y
reflejado aquí.

### Decisiones tomadas y suposiciones declaradas

- **Bootstrap en Python, no en Rust:** la cáscara solo decide CUÁNDO prepararse y muestra el
  progreso; toda la lógica vive en `mia.setup.first_run` (testeable con initdb real).
- **Marcador `.mia-setup-complete` como fuente de verdad** de "preparación completa" — existir
  la base y las llaves NO basta (pueden ser de una preparación interrumpida).
- **Loopback para todo servicio empaquetado** (la base ya lo hacía; el motor de modelos
  bindeaba 0.0.0.0 por default del CLI — corregido en instalador, dev y entry).
- **El modo desarrollo no cambia:** LiteLLM sigue manual (3 terminales); el 4º servicio es
  exclusivo del modo instalado. `litellm_config.yaml` de dev intacto.
- MIA_ENV=prod en el `.env` semilla (verificado contra los 5 usos reales de IS_PRODUCTION —
  no rompe login ni CORS).

---

## Checkpoint anterior: Sesión 42 (2026-07-10) — BLOQUE INSTALADOR: Fase 1 (empaquetado) COMPLETA + cáscara blindada

### Qué se hizo esta sesión (lenguaje simple)

Arrancó el **bloque del instalador** (nuevo objetivo aprobado por Pipe): que cualquier abogado
instale MIA con doble clic, sin saber de tecnología. Plan de 4 fases; esta sesión cerró la
Fase 1 y adelantó el blindaje de la Fase 2:

- **El motor de MIA ya corre empaquetado** (sin Python ni nada instalado): 459 MB verificados
  en vivo — salud OK, seguridad exige credenciales, y el lector de PDFs escaneados responde.
  La voz queda como descarga posterior (decisión de Pipe); los escaneados van incluidos.
- **La pantalla ya corre autocontenida** (sin Node instalado): 103 MB con su propio motor
  portable, probada en un puerto libre con sus protecciones de seguridad intactas.
- **La cáscara de escritorio quedó blindada** contra el mundo real: no pueden abrirse dos MIA
  a la vez, y ya NO adopta cualquier cosa que responda en sus puertos — exige que el proceso
  demuestre ser MIA. Motivo: en la máquina de Pipe pasó de verdad (la cáscara vieja adoptó
  una app ajena llamada Voicebox como "motor" y mostró el proyecto "Intelligence Sura" como
  "pantalla" — Pipe lo vio). Ahora ese caso termina en un aviso en llano.

### Resultado de verificación (3 capas)

- **Capa 1: regresión completa 82/82 suites ALL PASS** (línea base sube de 79 a 82 con
  `test_packaging` 23/23, `test_frontend_packaging` 24/24, `test_shell_hardening` 42/42).
  `test_rls` 12/12 y `check_env_pins` 9/9 (HALT) intactos. cargo build exit 0. `test_ux`
  recalibrado de raíz (timeout de build 300→600s: el modo autocontenido alarga la compilación;
  el check sigue validando que compile) y re-verificado 41/41.
- **Capa 2: DOS revisiones adversariales independientes** (empaquetado y cáscara): 1 BLOQUEANTE
  (la política de seguridad nueva rompía la pantalla de arranque — corregido externalizando sus
  estilos/lógica) + 4 MAYORES (el motor "llamaba a casa" por internet en cada arranque —
  violaba la promesa local-first; compresión que podía corromper el lector de escaneados en
  silencio; prueba de humo con "verde falso" si el puerto estaba ocupado; gate que validaba
  comentarios en vez de código) + 5 menores — **TODOS corregidos y re-verificados** antes del
  commit. Detalle en `memory/progress.md` sesión 42.
- **Capa 3: PENDIENTE — de Pipe** (ver abajo).

### Capa 3 para Pipe (cuando retome)

1. **NUEVO:** abrir la cáscara de escritorio y confirmar que la pantalla de arranque SE VE con
   su diseño (fondo oscuro, marca) y que, si un puerto está ocupado por otra app, el mensaje
   en llano aparece.
2. Sigue pendiente el recorrido de producto de las sesiones 39-41 (Proyectos, guías con Mia,
   agentes jurídicos, perfil, Configuración en pestañas) — nada de eso cambió hoy.

### Pendientes y próximo paso

1. **PRÓXIMA SESIÓN → F2 (primer arranque automático):** carpeta de datos en
   `%LOCALAPPDATA%\Mia`, llaves de seguridad generadas solas, base de datos inicializada con
   sus 30 migraciones, configuración de instalador para la cáscara, y **LiteLLM como segundo
   ejecutable empaquetado** (decisión declarada de la sesión 42: sin él, dos de los tres modos
   de motor quedan rotos en la máquina del abogado). Luego F3 (wizard de bienvenida) y F4
   (instalador final + prueba en frío en máquina limpia).
2. **ACCIÓN DE PIPE (para VENDER, no para el equipo):** registrar la cuenta de firma digital
   (Azure Trusted Signing) — sin ella el instalador funciona pero Windows muestra advertencia
   de "editor desconocido". También siguen pendientes las apps OAuth (guía en
   `docs/guia-conectar-correo-y-nube.md`).
3. Deuda consciente: verificaciones que exigen lanzar la app de verdad quedaron como pasos
   OBLIGATORIOS del E2E de F4 (Riesgo #59): splash visual bajo la política de seguridad,
   ventana de consola del motor (hoy visible — se apaga al ensamblar el instalador), prueba
   empírica del aislamiento de la página remota, y el arranque en frío completo.

### Trabajo en background sin leer

Nada — todos los ejecutores, revisores y regresiones se leyeron y quedaron reflejados aquí.

### Decisiones tomadas y suposiciones declaradas

- **Pipe (2026-07-10):** instalador con lector de escaneados INCLUIDO y voz como descarga
  posterior; plan de 4 fases aprobado; instalador sin firma suficiente para el equipo Lexia.
- **Fable (declarada):** LiteLLM entra como segundo ejecutable (~150-300 MB más) porque sin él
  los modos "nube" y "soberano" quedan completamente rotos y el modo "suscripción" pierde su
  red de respaldo — se prefirió peso sobre abogados con MIA muda. La consolidación elegante
  (Riesgo #4) queda como refactor futuro.
- La colisión de puertos en máquinas reales es caso ESPERADO del producto (demostrado en vivo
  en la máquina del fundador) — toda adopción exige identidad, nunca un simple "responde".

---

## Checkpoint anterior: Sesión 41 (2026-07-10) — BLOQUE C COMPLETO: agentes jurídicos + perfil unificado + Configuración en subtabs — PLAN A/B/C TERMINADO

### Qué se hizo esta sesión (lenguaje simple)

Se ejecutó COMPLETO el Bloque C — el último del plan de evolución de producto aprobado por Pipe —
con la misma orquestación multi-agente autorizada desde la sesión 38:

- **Agentes jurídicos con conocimiento propio:** las "personas" pasan a llamarse **Agentes
  jurídicos** y ahora cada agente puede tener hasta 8 guías del despacho vinculadas. Cuando el
  abogado invoca un agente, Mia prioriza ESAS guías al trabajar (en el chat del asunto y en el
  asistente). Además, "Crear con Mia" también sirve para agentes: una entrevista corta arma el
  borrador del agente (con guías sugeridas ya pre-marcadas) y NADA se guarda hasta que el abogado
  pulsa Guardar en el formulario.
- **Perfil del despacho editable y unificado:** lo que el abogado respondió al conocer a Mia ya
  se puede editar en "Mi despacho" sin repetir la entrevista (identidad, países con el mismo
  selector del inicio, áreas de práctica, tarjeta profesional, herramientas). Antes había DOS
  copias desconectadas del perfil que se desincronizaban en silencio — ahora hay UNA fuente de
  verdad y la otra se deriva sola.
- **Configuración en pestañas:** la pantalla de Configuración dejó de ser un scroll largo — ahora
  son 5 pestañas (Primeros pasos con contador, Conexiones, Carpetas, Automatizaciones, Valor y
  gasto). Todos los enlaces viejos ("Ir al paso", avisos del Panel) siguen llegando a la pestaña
  correcta.

### Resultado de verificación (3 capas)

- **Capa 1: regresión completa ALL PASS (79 suites)** — línea base sube de 76 a 79:
  `test_agent_playbooks` 55/55, `test_profile_full` 51/51, `test_config_tabs` 14/14.
  `test_rls` 12/12 y `check_env_pins` 9/9 (HALT) intactos. `npm run build` verde (14 páginas).
- **Capa 2: revisión adversarial con 4 revisores independientes + refutación por hallazgo** —
  5 hallazgos MENORES confirmados (0 mayores, 0 bloqueantes; seguridad/RLS sin hallazgos), TODOS
  corregidos y re-verificados antes del commit: el presupuesto del material de guías podía
  pasarse por unos caracteres; guardar el perfil podía borrar en silencio datos guardados por la
  pantalla vieja; una guía archivada ocupaba cupo invisible en el formulario del agente; un error
  crudo del servidor podía mostrársele al abogado; código muerto. Detalle en `memory/progress.md`
  sesión 41. (De paso, el ejecutor del perfil atrapó un bug latente que habría borrado ajustes
  del despacho en cada guardado.)
- **Capa 3: PENDIENTE — recorrido en vivo de Pipe** (ver lista abajo).

### Capa 3 para Pipe (recorrido sugerido en http://localhost:3100)

1. En **Agentes jurídicos** (antes "Personas"): abrir un agente, vincularle 2-3 guías en
   "Guías vinculadas" (ver el contador "N de 8"), guardar; luego en un asunto invocarlo
   ("actúa como litigante...") y confirmar que trabaja normal.
2. **"Crear con Mia"** en Agentes jurídicos: responder la entrevista (3-6 preguntas), ver que el
   formulario queda precargado (con guías sugeridas marcadas), CANCELAR a mitad de camino y
   verificar que NO quedó ningún agente creado; repetir y esta vez Guardar.
3. En **Conocimiento → Mi despacho**: editar el perfil (países con el selector, áreas,
   herramientas), Guardar y leer el resumen "Así entendí a tu despacho".
4. En **Configuración**: navegar las 5 pestañas; desde el Panel usar un enlace de "tope de gasto"
   (debe abrir directo la pestaña "Valor y gasto") y un "Ir al paso" del recorrido (pestaña
   correcta). Probar entrar directo a `http://localhost:3100/configurar#carpetas`.
5. Sigue pendiente la capa 3 arrastrada de los Bloques A y B (sesiones 39-40) — nada de eso
   cambió en esta sesión.

### Pendientes y próximo paso

1. **El plan A/B/C quedó COMPLETO.** La próxima sesión arranca definiendo con Pipe el siguiente
   objetivo de producto (candidatos naturales: capa 3 acumulada, activación OAuth, o el
   siguiente frente que Pipe priorice).
2. **ACCIÓN DE PIPE (sin cambio):** registrar las apps OAuth (guía en
   `docs/guia-conectar-correo-y-nube.md`).
3. Deuda consciente: carpetas vinculadas POR AGENTE pospuesto a v2; las 3 personas canónicas de
   fábrica vienen sin guías pre-vinculadas; crear un agente con guías inválidas lo crea SIN
   vínculos y avisa en llano (decisión documentada).

### Trabajo en background sin leer

Nada — los 3 workflows (recon, ejecución, capa 2) y las 2 regresiones se leyeron y quedaron
reflejados aquí.

### Decisiones tomadas y suposiciones declaradas

- **"soul_responses" es un nombre lógico, no una tabla nueva:** la fuente canónica del perfil
  sigue siendo el archivo por despacho en disco (diseño local-first existente); la tabla
  `firm_profiles` pasa a ser derivada y ya no puede pisar en silencio lo canónico.
- El material de las guías de un agente entra al prompt como REFERENCIA después de las reglas
  duras (método y citación) y de la voz — nunca dentro del rol; el presupuesto es duro (≤16k)
  y la regla [VERIFICAR] manda siempre.
- "Modo profundo" (p19) NO se muestra en el perfil editable (coherente con el onboarding, que
  también la oculta — Riesgo #27).
- El renombre "Personas jurídicas" → "Agentes jurídicos" es SOLO visible: la ruta `/personas` y
  la API no cambian (cero riesgo de romper enlaces o integraciones).

---

## Checkpoint anterior: Sesión 40 (2026-07-10) — BLOQUE B COMPLETO: guías asistidas + gobernanza de lo aprendido

### Qué se hizo esta sesión (lenguaje simple)

Se ejecutó COMPLETO el Bloque B del plan de evolución de producto (aprobado por Pipe), con la
misma orquestación multi-agente autorizada desde la sesión 38:

- **"Crear con Mia" (nuevo):** el abogado ya no tiene que redactar una guía de trabajo desde
  cero — le abre una entrevista corta (3 a 6 preguntas), Mia arma un borrador, el abogado lo edita
  libremente y SOLO se guarda cuando él pulsa Guardar (nada toca la base de datos antes de eso).
  Disponible desde Conocimiento y también desde un asunto ya resuelto ("Convertir en guía"),
  donde precarga lo que se hizo en ese caso.
- **Gobernanza completa de guías:** historial de versiones con restaurar, archivar/reactivar,
  editar aunque la guía esté protegida (protegida solo bloquea que Mia la cambie sola), y las
  sugerencias de mejora de Mia ahora se pueden editar antes de aplicarlas (antes era solo
  aprobar o rechazar tal cual).
- **Una sola pantalla para "lo que Mia sabe hacer":** se fusionaron dos pestañas que mostraban
  la misma información partida en dos vistas (guías y habilidades) en una sola, con el origen de
  cada guía en lenguaje llano (manual, importada, con Mia, aprendida) y de dónde viene cada
  sugerencia ("Aprendí esto trabajando en...").
- **Corrección importante de comportamiento:** crear una guía con un nombre que ya existe ya NO
  la sobrescribe en silencio — avisa en llano que ya existe una guía con ese nombre.

### Resultado de verificación (3 capas)

- **Capa 1: regresión completa ALL PASS (76 suites)** — línea base sube de 74 a 76:
  `test_playbook_versions` 59/59 (48 iniciales, sube tras la capa 2), `test_guide_interview` 25/25.
  `test_rls` 12/12 y `check_env_pins` 9/9 (HALT) intactos. `test_ux` sube a 37/37,
  `test_second_brain_ui` 26/26. `npm run build` verde (14 páginas). Hubo 1 ciclo de corrección en
  el gate (un test buscaba el nombre viejo de una pestaña; se actualizó al nuevo copy sin
  debilitar la aserción).
- **Capa 2: revisión adversarial con 4 agentes independientes (contexto fresco)** — 10 hallazgos
  CONFIRMADOS, todos corregidos y re-verificados antes del commit:
  3 MAYORES (restaurar una versión con un título repetido daba un error técnico en vez de un
  aviso en llano; crear una guía con nombre repetido sobrescribía en silencio la existente sin
  dejar rastro; "Editar antes de aplicar" descartaba la corrección que el abogado acababa de
  escribir), 7 menores (varios casos de identificadores mal escritos que daban error técnico en
  vez de aviso en llano; una guía nueva creada por Mia no quedaba indexada para búsquedas
  futuras; el botón "Convertir en guía" aparecía en casos donde no debía). Detalle completo en
  `memory/progress.md` sesión 40.
- **Capa 3: PENDIENTE — recorrido en vivo de Pipe** (ver lista abajo).

### Capa 3 para Pipe (recorrido sugerido en http://localhost:3100)

1. En **Conocimiento → "Guías y habilidades"**: pulsar "Crear con Mia", responder la entrevista
   (mínimo 3 preguntas), revisar que el borrador es editable y que cancelar a mitad de camino NO
   deja ninguna guía creada; guardarla y verla aparecer con el sello "Creada con Mia".
2. Editar una guía existente, ver su Historial y restaurar una versión anterior.
3. Desactivar y reactivar una guía.
4. En Sugerencias: usar "Editar antes de aplicar" sobre una propuesta.
5. En un asunto con borrador APROBADO: usar el botón "Convertir en guía" (y verificar que NO
   aparece si el borrador fue rechazado o aprobado con cambios).

### Pendientes y próximo paso

1. **PRÓXIMA SESIÓN: Bloque C** del plan (agentes jurídicos con conocimiento propio + perfil del
   despacho editable y unificado + Configuración reorganizada en subtabs). El plan vive en
   `memory/plan-evolucion-producto.md` (Bloques A y B ya marcados completados).
2. **ACCIÓN DE PIPE (sin cambio):** registrar las apps OAuth (guía en
   `docs/guia-conectar-correo-y-nube.md`).
3. Deuda consciente nueva: el endpoint de entrevista para crear agentes (`kind='agente'`) responde
   "próximamente" hasta el Bloque C — el componente de entrevista ya quedó reusable para ese caso
   (Riesgo #58).

### Trabajo en background sin leer

Nada.

### Decisiones tomadas y suposiciones declaradas

- Crear una guía (por el wizard o manualmente) ya NO sobrescribe en silencio una guía con el
  mismo nombre — avisa en llano y el abogado decide. Antes de esta sesión, un nombre repetido
  podía hacer "desaparecer" una guía existente sin que nadie se diera cuenta.
- El resultado de la revisión de un borrador ("aprobado" vs. "aprobado con cambios" vs.
  "rechazado") ahora es visible para la pantalla del asunto, no solo para el backend — es lo que
  decide si aparece el botón "Convertir en guía". Un borrador "aprobado con cambios" NO cuenta
  como evidencia suficiente (mismo criterio que usa la entrevista para decidir qué mostrarle a
  Mia).
- Crear agentes jurídicos con "Crear con Mia" queda para el Bloque C a propósito — el wizard de
  entrevista de esta sesión ya se construyó pensando en reusarse para ese caso.

---

## Checkpoint anterior: Sesión 39 (2026-07-09) — BLOQUE A COMPLETO: Proyectos + carpetas sin fricción

### Qué se hizo esta sesión (lenguaje simple)

Se ejecutó COMPLETO el Bloque A del plan de evolución de producto (aprobado por Pipe), con
orquestación multi-agente según su autorización expresa de la sesión 38:

- **Pestaña "Proyectos" (nueva):** espacio de trabajo libre estilo Claude Cowork — el abogado
  crea un proyecto en 2 pasos, conecta carpetas, chatea con Mia sobre esas fuentes (con memoria
  de la conversación) y guarda los documentos que Mia produce, con descarga en Word. Sin
  diagnóstico ni aprobación de borrador (eso sigue siendo de los Asuntos, separados como pidió Pipe).
- **Fin de las rutas pegadas a mano:** selector visual de carpetas del equipo (navegable, seguro,
  fail-closed) en los 3 sitios donde antes se pegaba la ruta (carpetas de trabajo, carpeta del
  expediente, vault de Obsidian).
- **Varias carpetas por asunto/proyecto** — y de paso se corrigió DE RAÍZ el bug latente de poda
  cruzada (documentado en el plan): con 2 carpetas, el sync de una ya no puede borrar los
  documentos de la otra (ni en carpetas del equipo NI en OneDrive, donde también existía).
- **Panel "Fuentes" unificado** en la pantalla del asunto y del proyecto: carpetas del equipo +
  OneDrive + correos en una sola lista con estados en llano y "+ Conectar fuente".

### Resultado de verificación (3 capas)

- **Capa 1: regresión completa ALL PASS (74 suites)** — línea base sube de 70 a 74:
  `test_matter_folders_multi` 30/30 (el caso del bug de poda cruzada + concurrencia + backfill
  conservador), `test_folder_browse` 15/15, `test_projects` 33/33, `test_matter_sources` 26/26.
  `test_rls` 12/12 y `check_env_pins` 9/9 (HALT) intactos. `npm run build` verde (14 páginas).
- **Capa 2: revisión adversarial multi-agente (contexto fresco)** — 12 hallazgos CONFIRMADOS,
  todos corregidos y re-verificados antes del commit salvo 2 notas aceptadas como deuda:
  2 BLOQUEANTES (el backfill de la migración podía fusionar procedencias y provocar borrado de
  documentos conservados; la poda de OneDrive seguía sin distinguir fuente → borrado cruzado
  con multi-carpeta), 2 MAYORES (carrera de sincronización sin candado en el motor → documentos
  duplicados; el chat de proyecto no recordaba los turnos anteriores), 6 menores (proyectos
  contados como "asuntos" en asistente/dashboard/endpoint legacy, burbuja "pensando" infinita
  en error, doble Enter creaba proyectos duplicados, mensaje con la palabra equivocada).
  Detalle completo en `memory/progress.md` sesión 39.
- **Capa 3: PENDIENTE — recorrido en vivo de Pipe** (ver lista abajo).

### Capa 3 para Pipe (recorrido sugerido en http://localhost:3100)

1. **Proyectos:** crear un proyecto (nombre → conectar carpeta con el selector visual → entrar),
   chatear sobre los documentos, verificar que un segundo mensaje recuerda el anterior, guardar
   una respuesta larga con "Guardar en el proyecto" y descargarla en Word.
2. **Selector de carpetas:** en Configuración → Carpetas y en un asunto ("Conectar fuente →
   Carpeta del equipo"), navegar y elegir sin pegar rutas.
3. **Panel Fuentes del asunto:** vincular 2 carpetas al mismo asunto, "Revisar ahora" en una,
   confirmar que los documentos de la otra no se tocan; el botón de correos sigue ahí.
4. Sigue pendiente la capa 3 arrastrada de sesiones 35-38 (onboarding/panel/rebrand + los 5
   puntos de fuentes remotas) — nada de eso cambió en esta sesión.

### Pendientes y próximo paso

1. **PRÓXIMA SESIÓN: Bloque B** del plan (guías de trabajo asistidas — "Crear guía con Mia" con
   gate HITL por construcción + CRUD/versiones de playbooks + gobernanza de lo aprendido).
   El plan vive en `memory/plan-evolucion-producto.md` (Bloque A ya marcado completado).
2. **ACCIÓN DE PIPE (sin cambio):** registrar las apps OAuth (guía en `docs/guia-conectar-correo-y-nube.md`).
3. Deuda consciente nueva: el navegador de carpetas queda deshabilitable por flag para el futuro
   Modo A/Docker (Riesgo #56); documentos con procedencia ambigua pre-migración nunca se podan
   solos (protección anti-pérdida, Riesgo #57); `MatterDriveFolder.tsx` quedó sin uso (borrar
   en una limpieza futura).

### Trabajo en background sin leer

Nada — todos los workflows y la regresión final se leyeron y quedaron reflejados aquí.

### Decisiones tomadas / suposiciones declaradas

- `documents.body` (texto íntegro) para los archivos que Mia produce: los fragmentos indexados
  llevan traslape y no se pueden reconstruir para el Word. Suposición razonable no prevista en
  el plan, declarada aquí.
- `GET /api/matters` sin parámetro devuelve SOLO asuntos (compatibilidad de la lista actual);
  `?kind=proyecto` y `?kind=todos` para lo demás. Asistente, dashboard y endpoint legacy también
  filtran proyectos.
- Los endpoints singulares `/folder` quedan como wrappers deprecados (sin el 409); el frontend
  ya usa la superficie plural vía FuentesPanel.
- Memoria conversacional del proyecto: corta y presupuestada (últimos 6 turnos / 8.000
  caracteres), solo en proyectos — el flujo de asuntos quedó byte a byte intacto (gate HITL 21/21).

---

## Checkpoint anterior: Sesión 38 (2026-07-09) — Cáscara de escritorio + rediseño onboarding/panel + rebrand visual + PLAN APROBADO de evolución de producto

### Qué se hizo esta sesión (retoma post-apagón, todo en `origin/main`)

- **Cáscara de escritorio Tauri (Fase 4 · bloque 2)** — `35b3a96`: la app que el abogado abre
  y enciende/apaga todo (DB→backend→frontend). E2E de 5 ciclos + Job Object anti-huérfanos
  verificado con crash simulado. Revisión adversarial: 2 mayores + 5 menores corregidos.
- **Onboarding rediseñado** — `46db38c`: 8 preguntas (fuera estilo/límites/ritmo — el estilo
  se aprende del flywheel), UNA pregunta de país con 21 países multi-select, ejemplos sin
  Lexia. e2e 32/32, second_brain_ui 26/26.
- **Panel/Configuración reestructurados** — `0d5e826`: el Panel solo con lo accionable
  (Para tu decisión + recordatorios + recomendaciones + Este mes); Configuración absorbe
  conexiones/carpetas/automatizaciones/valor. Guía OAuth en `docs/guia-conectar-correo-y-nube.md`.
- **Rebrand visual completo** — `13f0d55`: paleta Lexia (teal/negro/degradé verde), sidebar
  negra con wordmark MIA (I en teal), Archivo+Hind, aurora teal, card-depth. Pipe lo vio en
  vivo y le gustó ("me gusta lo que estoy viendo").

### PRÓXIMA SESIÓN: ejecutar el plan de evolución de producto (APROBADO por Pipe)

> **AUTORIZACIÓN EXPRESA DE PIPE (2026-07-09, en sus palabras):** ejecutar el plan
> **usando workflows de orquestación multi-agente desde el arranque, a velocidad
> máxima**. Es decir: al retomar con /arranque, usar el tool Workflow (fan-out de
> ejecutores en paralelo sobre partes disjuntas del Bloque A + verificación
> adversarial multi-agente) sin volver a pedirle permiso. Los límites NO cambian:
> verificación de 3 capas antes del cierre, gate HITL innegociable, HALT si
> test_rls falla, y capa 3 visual sigue siendo de Pipe.

**El plan completo vive en `memory/plan-evolucion-producto.md`** (misma copia en
`C:\Users\USER\.claude\plans\chad-me-gusta-lo-memoized-token.md`). Resumen:
- **Bloque A (EMPEZAR AQUÍ):** pestaña "Proyectos" estilo Claude Cowork (reusa `matters`
  con `kind`), selector visual de carpetas del equipo (fin de rutas pegadas a mano),
  multi-carpeta por asunto (⚠️ PRIMERO `documents.source_id` — hay bug latente de poda
  cruzada documentado en el plan), panel "Fuentes" unificado.
- **Bloque B:** "Crear guía con Mia" (entrevista stateless con gate HITL por construcción),
  CRUD+versiones de playbooks, gobernanza de skills aprendidas (fusionar subtabs).
- **Bloque C:** Personas → "Agentes jurídicos" con conocimiento vinculado, perfil del
  despacho editable (SOUL como fuente canónica, `/api/profile/full`), Configuración en subtabs.
- Decisiones de Pipe: todo en orden A→B→C, un bloque por sesión; Proyectos y Asuntos como
  pestañas SEPARADAS. Verificación 3 capas por bloque; gate HITL innegociable.

**Pendientes de Pipe (sin cambio):** registrar apps OAuth (guía en docs/), capa 3 en vivo
de sesiones 35-36 y del onboarding/panel/rebrand nuevos.

---

## Checkpoint anterior: Sesión 37 (2026-07-09) — OCR local para PDFs escaneados + sincronización automática de OneDrive

### Qué se hizo esta sesión

> Nota: la sesión se interrumpió por un corte de luz tras el último commit; el cierre (regresión
> completa + esta memoria) se completó en la retoma del mismo día. No se perdió trabajo.

- **Bloque 3a — Mia ya lee PDFs escaneados (OCR local):** en litigio la mayoría de expedientes
  son escaneos sin capa de texto; antes Mia quedaba ciega SIN AVISAR. Ahora los lee con un motor
  de lectura óptica que corre 100% en el servidor del despacho (el documento nunca sale de ahí),
  página por página, marcando con honestidad qué partes vienen de lectura óptica. Fail-soft:
  tope de 150 páginas / 10 minutos con corte anotado; una página corrupta no tumba el documento;
  un archivo sin cuerpo legible NO entra como documento válido (se reporta y se reintenta luego).
- **Bloque 3b — las carpetas de OneDrive se mantienen al día solas:** job programado cada 6 horas
  (misma cadencia que Obsidian) que sincroniza las fuentes de OneDrive remoto de cada despacho;
  comparte el candado con el botón manual (nunca corren dobles) y una carpeta rota no tumba las
  demás. Cierra la deuda #1 de la sesión 36.
- **Revisión adversarial (capa 2) corrida y cerrada:** 3 mayores + 4 menores, TODOS corregidos
  antes del cierre (`ea28423` + `315dbd1`): el OCR ya no congela el servidor (async), RAM acotada
  ante PDFs con páginas descomunales, "solo nota sin cuerpo" ya no entra como documento, gate de
  no-egress que PRUEBA que el OCR no hace ninguna llamada de red, y la guarda de cuerpo legible
  replicada también en carpetas locales.

### Frontend a revisar (Cursor — capa 3): NO APLICA

Los 4 commits son backend + tests puros — no hay UI nueva. Sigue pendiente la capa 3 de la
sesión 36 (fuentes remotas) y la del botón "Revisar ahora" (sesión 35) — ver checkpoint anterior.

### Resultado de verificación (3 capas)

- **Capa 1: regresión completa 70/70 suites ALL PASS** (corrida en la retoma post-apagón) —
  `test_rls` 12/12 y `check_env_pins` 9/9 (HALT) intactos; línea base sube de 69 a 70 con
  `test_ocr_ingest` 26/26. Sin frontend tocado → sin `npm run build`. (Nota de tally:
  `test_speech_tts` es 24/24 en el script actual; el 26/26 histórico era de otra versión.)
- **Capa 2:** revisor adversarial independiente — 3 mayores + 4 menores, TODOS corregidos y
  re-verificados; detalle en `memory/progress.md` sesión 37 y Riesgo #55.
- **Capa 3: NO APLICA** (sin UI nueva en esta sesión).

**Commits de esta sesión en `main`, SIN PUSH todavía:** `ad16a64` (OCR bloque 3a), `10788c2`
(cron OneDrive bloque 3b), `ea28423` (correcciones capa 2), `315dbd1` (guarda has_body en
carpetas locales) + el commit de cierre de esta memoria. Los commits de la sesión 36 ya están
en `origin/main`.

**Pendiente real para la próxima sesión:**
1. Capa 3 EN VIVO de Pipe/Cursor — los 5 puntos de la sesión 36 (abajo) + botón "Revisar ahora".
2. **ACCIÓN DE PIPE:** registrar las apps OAuth (Azure AD y Google Cloud) y poner las llaves en
   `.env` — hasta entonces las fuentes remotas responden 503 en llano (por diseño).
3. Quick win #5 (checklist de pre-entrega en el gate de aprobación) espera aprobación de Pipe.
4. Decidir push a `origin/main` de los commits de esta sesión.

---

## Checkpoint anterior: Sesión 36 (2026-07-09) — Fuentes remotas del expediente (Gmail + OneDrive vía la nube)

### Qué se hizo esta sesión

Bloque 2 de la Fase 3 (el que quedó pendiente en el HANDOFF de la sesión 35): el abogado ya puede
traer correos (Microsoft/Google) y carpetas de OneDrive al expediente, con OAuth multi-proveedor de
base (un despacho puede tener Microsoft Y Google conectados a la vez). Construido en 4 fases:

- **Fase 1 — cimientos OAuth multi-proveedor:** `tenant_oauth_tokens` con PK `(tenant_id, provider)`;
  migración `027_remote_sources.sql` (+ `remote_drive_sources`, `remote_file_hashes`, RLS FORCE);
  `documents.origin` gana `'mail'`/`'drive'`. `GET /api/mailbox/status` ahora reporta POR PROVEEDOR.
- **Fase 2 — correos del caso → expediente:** buscar y vincular correos (cuerpo + adjuntos se
  vuelven documentos, dedupe por sha256, máx 20 por lote).
- **Fase 3 — OneDrive remoto SELECTIVO de solo lectura:** navegar carpetas, registrar una fuente,
  sincronizar (incremental por eTag→sha256, tope 20MB por archivo, fail-soft por archivo, tope 20
  fuentes por despacho).
- **Fase 4 — UI:** navegador modal de carpetas, diálogo de búsqueda de correos, tarjetas del Panel
  de control por proveedor con checkbox de OneDrive.

Detalle completo (piezas de código, los 3 mayores + 6 menores corregidos en `c9f2a32`) en
`memory/progress.md` sesión 36 y `memory/bugs-and-risks.md` Riesgo #54.

### Frontend a revisar (Cursor — capa 3, PENDIENTE)

Toda la UI de esta sesión (`OneDriveFolderPicker`, `OneDriveSourcesSection`, `MatterDriveFolder`,
`MailSearchDialog`, `MailboxSection`) pasó `npm run build` verde y está cubierta por gates de API,
pero **nadie la recorrió en un navegador real todavía.** Pendiente:

1. **Conectar Microsoft con "Incluir mis archivos de OneDrive"** y verificar el flujo real de
   consentimiento OAuth (requiere que Pipe haya puesto las llaves en `.env` primero — ver más abajo).
2. **Navegador de carpetas:** entrar 2-3 niveles y elegir una carpeta para sincronizar.
3. **Probar el 503** cuando no hay conexión configurada, y el botón nuevo **"Añadir permiso de
   archivos"** sobre una cuenta Microsoft que solo tenía correo conectado.
4. **Buscar y vincular 2-3 correos reales** desde el diálogo del asunto y verlos aparecer como
   documentos del expediente.
5. **Responsive** de los dos modales nuevos (buscador de correos, navegador de carpetas).

También sigue pendiente la capa 3 del botón "Revisar ahora" (deuda arrastrada de la sesión 35).

**Contratos de los endpoints nuevos (por si Cursor los necesita):**
- `GET /api/mailbox/status` → `{conectado, conexiones:[{proveedor, proveedor_nombre, conectado,
  funciones:[...], archivos:bool}], analisis_contenido, proveedor?, proveedor_nombre?, proveedores?}`
  — `archivos` indica si esa conexión YA tiene permiso de OneDrive (para ofrecer "Añadir permiso").
- `GET /api/matters/{id}/mail/search?q=&provider=` → `{resultados:[{...,provider}]}`; sin `provider`
  busca en todas las cuentas conectadas; sin cuenta conectada → 503 en llano.
- `POST /api/matters/{id}/mail/link` con `{items:[{provider, message_id}]}` (máx 20) →
  `{added:[...], already:[...], skipped:[{name, reason}]}` — un fallo individual nunca tumba el lote.
- `GET /api/drive/browse?item_id=` → `{items:[...]}` (un nivel de OneDrive; sin `item_id` = raíz);
  503 sin cuenta/permiso, 502 si Graph falla.
- `GET /api/drive/sources` / `POST /api/drive/sources` (`{remote_item_id, label?, kind, matter_id?}`)
  / `DELETE /api/drive/sources/{id}` / `POST /api/drive/sources/{id}/sync` (throttle 60s + lock de
  corrida en vuelo, ambos con mensaje en llano).

### Resultado de verificación (3 capas)

- **Capa 1:** regresión completa **69/69 suites ALL PASS** (dos corridas, antes y después de las
  correcciones de capa 2) — `test_rls` 12/12 y `check_env_pins` 9/9 (HALT) intactos; `npm run build`
  verde. Gates nuevos: `test_mailbox_multi.py` 21/21, `test_mail_to_matter.py` 24/24,
  `test_remote_drive.py` 35/35. (Nota de tally: `test_setup_wizard` es 28/28, no el 30/30 que quedó
  anotado en HANDOFFs anteriores — correspondía a otra versión del script.)
- **Capa 2 — dos revisores adversariales independientes (contexto fresco):** seguridad **APROBADO
  sin bloqueantes ni mayores** (RLS, OAuth state con nonce+cookie anti-CSRF, sin fuga de tokens/
  contenido, SQL parametrizado, límites verificados); corrección encontró **3 mayores + 6 menores,
  TODOS corregidos** antes del commit `c9f2a32` (renombrar en OneDrive ya no borra el archivo del
  expediente; la UI espera a que la sync termine; botón para agregar permiso de archivos a una
  cuenta ya conectada; fallo por-correo no tumba el lote; `last_synced_at` por fuente; reset del
  diálogo al cerrar; uuid malformado → 404; embeddings fuera de la conexión pooled; ids de URL
  escapados; scopes base de Microsoft siempre incluidos).
- **Capa 3: PENDIENTE** — sin navegador conectado en esta sesión; ver la lista de 5 puntos arriba.

**5 commits en `main`, SIN PUSH todavía:** `7ccab33` (Fase 1 OAuth), `8c2c28a` (Fase 2 correos),
`a84088a` (Fase 3 OneDrive), `b989e39` (Fase 4 UI), `c9f2a32` (correcciones de capa 2).

**Pendiente real para la próxima sesión:**
1. Capa 3 EN VIVO de Pipe/Cursor (los 5 puntos de arriba) + la capa 3 pendiente del botón "Revisar
   ahora" (sesión 35).
2. **ACCIÓN DE PIPE:** registrar las apps OAuth (Azure AD y Google Cloud) y poner las llaves en
   `.env` (`MS_OAUTH_CLIENT_ID/SECRET`, `GOOGLE_OAUTH_CLIENT_ID/SECRET`) — hasta entonces todo
   responde 503 en llano (activación diferida, por diseño).
3. Quick win #5 (checklist de pre-entrega en el gate de aprobación) sigue esperando aprobación de Pipe.
4. Deuda consciente: sincronización PROGRAMADA de fuentes OneDrive (hoy solo botón manual).
5. Decidir si se hace push a `origin/main` de estos 5 commits.

---

## Checkpoint anterior: Sesión 35 (2026-07-08) — Frentes B/C + Data Factory del corpus + bugfix FTS

### Qué se hizo esta sesión

Sesión de retoma: había ~5h de trabajo de una sesión previa sin commitear ni documentar (nunca corrió
`/cierre`). Se reconstruyó por lectura de código, se verificó y se corrigió antes de commitear:

- **Bugfix** `agents/research.py`: la consulta FTS de investigación mandaba el mensaje completo del
  abogado (0 resultados casi siempre) → ahora usa términos clave + citas exactas en OR.
- **Frente B (aprendizaje):** motivo del rechazo en la traza (B1), botón "Revisar ahora" en
  Conocimiento → `POST /api/learning/run` (B2), aprobar una corrección de wiki ya la aplica de verdad
  al archivo del concepto (B4).
- **Fase 3 · frente C + Data Factory del corpus:** `rag/corpus_factory.py` (motor único, jurisdicción
  por pack JSON — nada de Colombia hardcodeado, ver decisión de Pipe en `memory/progress.md` sesión
  35) + `connectors/vault_export.py` (backfill de playbooks y fichas del corpus al vault de Obsidian).

Detalle completo, con los 5 hallazgos de capa 2 y sus correcciones, en `memory/progress.md` (sesión 35).

### Frontend a revisar (Cursor — capa 3)

- `frontend/app/memoria/page.tsx` (pestaña Sugerencias): botón nuevo **"Revisar ahora"** sobre la
  lista de propuestas — dispara `POST /api/learning/run`, muestra spinner mientras corre y un mensaje
  de resultado ("Mia propuso N mejoras nuevas" / "no encontró nada nuevo"). `npm run build` verde y
  cubierto por gate de API; falta el recorrido visual en vivo (clic real, estados de carga/error).
- Nada más cambió en `frontend/`; el resto de esta sesión fue backend puro (Data Factory, vault export,
  bugfix de investigación) sin superficie nueva para el abogado más allá del botón de arriba.

### Resultado de verificación (3 capas)

- Capa 1: regresión completa **66/66 suites verdes** (dos corridas — antes y después de aplicar las
  correcciones de capa 2), `test_rls`/`check_env_pins` HALT intactos. Gates nuevos: `test_research_query`
  11/11, `test_corpus_factory` 12/12, `test_vault_export` 38/38.
- Capa 2 (revisor adversarial independiente, workflow multi-agente): 5 hallazgos CONFIRMADOS, los 5
  corregidos y RE-VERIFICADOS antes del commit (colisión de slug al exportar playbooks; parseo frágil
  del concepto de una wiki_correction → columna dedicada; conexión pooled sostenida durante E/S de
  disco; lógica de identidad duplicada entre adaptadores del corpus; fetches secuenciales evitables).
- Capa 3: **PENDIENTE** — sin navegador conectado en esta sesión para el recorrido en vivo del botón.

**6 commits en `main`, YA PUSHEADOS a `origin/main`:** `9f62b4e`, `4ea4126`, `cb32ebb`, `00728c8`,
`8376726`, `c11fb71` (el último añade 3 de los 5 quick wins de
`docs/analisis-claude-for-legal.md` — detalle en `memory/progress.md`, regresión 66/66 y capa 2
con 3 hallazgos corregidos antes del commit).

**Pendiente real para la próxima sesión (ya no queda nada "chico" en la cola):**
1. Capa 3 visual en vivo (botón "Revisar ahora" en Conocimiento + los quick wins de prompt no
   tienen UI que revisar, son solo texto de sistema).
2. **Gmail/OneDrive vía Graph API** (bloque 2 de la Fase 3, `mia-decisiones-pipe-fase3` en
   memoria) — es la siguiente pieza grande. Antes de construirla a ciegas, vale la pena que Pipe
   confirme alcance: ¿Gmail primero (correos+adjuntos del caso como parte del expediente) o
   OneDrive vía Graph API primero (la sincronización LOCAL de OneDrive/Google Drive Desktop ya la
   cubre `local_folder_sources`/F3.1 para quien tenga el cliente de escritorio instalado — el
   Graph API solo aporta valor si el abogado NO usa el cliente de escritorio)? Necesita también
   que Pipe registre la app OAuth (mismo patrón "activación diferida" que Microsoft 365/Google ya
   tienen: backend/UI listos, 503 hasta que lleguen las llaves).
3. Quick win #5 (checklist de pre-entrega ejecutado en el gate de aprobación) — requiere
   aprobación previa de Pipe por tocar `hitl_checkpoint`.

---

## ⭐ Trabajo de frontend PENDIENTE para Cursor (consolidado · priorizado · 2026-07-03)

El backend de estos puntos ya está en `origin/main`; falta SOLO la UI. Cada uno tiene su
sección detallada más abajo con endpoints y comportamiento. Orden sugerido:

1. **Control del tope de gasto de IA (CP-E1)** — `GET/PUT /api/policy/budget`. **COMPLETADO** (commit `7030e5e`). Detalle en la sección "CP-E1 · control del tope en el Panel".
2. **Pantalla de gestión de Personas jurídicas (CP-E3, lo más nuevo)** — CRUD
   `GET/POST/PUT/DELETE /api/personas`. **COMPLETADO** (commit `557478c`). Detalle en la sección "CP-E3" arriba de todo.
3. **Tarjetas de "Recomendaciones de Mia" (CP-V2)** — `GET /api/dreams/prescriptions` +
   `POST .../{id}/decision`. **COMPLETADO** (commit `c61912f`). Detalle en la sección "CP-V2".
4. **Automatizaciones (CP-P2)** — plantillas + sugerencias consent-first (`/api/automations/*`). **COMPLETADO** (commit `5642a73`).
5. **Conectar Microsoft 365 / Google (CP-P3)** — botón "Conectar" (`/api/mailbox/*`). **COMPLETADO** (commit `70ac8e7`). OJO:
   la ACTIVACIÓN real (llaves OAuth en `.env`) sigue APLAZADA por decisión de Pipe hasta el producto
   final; la UI está lista y muestra el aviso 503 si el servidor aún no tiene las llaves.

**Reglas para Cursor (recordatorio):** §G sin jerga técnica al abogado (nada de "tenant",
"LangGraph", "modelo", "pgvector"); errores del backend llegan en llano — mostrarlos tal cual;
tras `npm run build` reinicia el dev server (pisa la caché `.next`). Escribe tus hallazgos de
capa 3 al final del archivo.

---

## ✅ Rediseño del onboarding — COMPLETADO (backend + frontend en `origin/main`, 2026-07-06)

**Backend** (merge `de6c797`) y **frontend de Cursor** (commit `1487ba6`) ya están en
`origin/main` y verificados (tsc limpio; 3100 sirve 200 sin ChunkError; SummaryMarkdown
calza con `build_summary`). Cursor entregó: resumen llano + detalle técnico plegable,
7 días (con fin de semana), herramientas con descripción, y "Conocimiento" de-jergada.
**Único pendiente = capa 3 EN VIVO de Pipe:** hacer el recorrido de punta a punta en
`http://localhost:3100` y confirmar que el resumen refleja sus respuestas. La spec
original se conserva abajo por trazabilidad; NO rehacer.

<details><summary>Spec original (histórica — ya implementada)</summary>

Pipe probó el onboarding real y pidió arreglos. **El backend ya cambió** (rama
`feat/onboarding-soul-claro`); falta la parte visual. Contexto: el "Configura a Mia"
debe sentirse fácil para un abogado (cero jerga de agentes), estilo wizard de Hermes.

**COMPLETADO** (Cursor capa 3 · 2026-07-06). Detalle en "Hallazgos de Cursor (capa 3)" al final.

**Ya hecho en backend (no tocar, solo consumir):**
- La entrevista ahora trae **13 preguntas** (`GET /api/onboarding/questions`); se
  QUITARON las de "objetivo del año" y "los 3 pilares" (eran confusas). Los `id`
  `p15`/`p16` ya no llegan — si el frontend tiene lógica por-id para ellos, quítala.
- El SOUL.md se genera **determinista y sin placeholders** (nunca más `[CORCHETES]`).
- `POST /api/onboarding/complete` ahora devuelve, además de `soul_content`, un campo
  **`summary`**: un resumen en **lenguaje llano** en Markdown ("### Así entendí a tu
  despacho" + viñetas). ESO es lo que debe ver el abogado al terminar.
- El recorrido "Configura a Mia" ya **no incluye Obsidian** (`GET /api/setup/status`
  devuelve 6 pasos). No lo repongas.

**Frontend a construir (`frontend/app/onboarding/page.tsx` salvo que se indique):**

1. **Pantalla final = el resumen, no el .md crudo.** Hoy se muestra `soul_content` en
   un `<pre>`. Cámbialo por render del campo **`summary`** (Markdown → texto con
   viñetas y negritas, legible). El `soul_content` técnico puede quedar oculto o en un
   "Ver detalle técnico" plegable (opcional, para power users). Encabezado tipo tarjeta.

2. **Días de la semana — agregar SÁBADO y DOMINGO.** La pregunta de ritmo (`p17`) hoy
   muestra checkboxes Lunes–Viernes; hay abogados que trabajan fin de semana. Deja los
   **7 días** (Lunes, Martes, Miércoles, Jueves, Viernes, Sábado, Domingo).

3. **Herramientas (`p18`) — lista curada CON descripción, no texto libre.** Reemplaza
   los chips libres por una lista de opciones (checklist) donde cada una explique qué
   hace Mia con ella. Los valores seleccionados se envían igual (lista de textos) en la
   respuesta del field `memory.tools_that_survived`. Opciones sugeridas + descripción:
   - **Correo** — "Mia vigila tus correos urgentes y te avisa."
   - **Calendario** — "Mia te recuerda tus eventos y audiencias próximas."
   - **Gestor documental** — "Mia consulta los documentos del despacho para responder."
   - **Mensajería (Telegram)** — "Habla con Mia desde tu celular, por texto o por voz."
   - **Carpetas en la nube (OneDrive/Google Drive)** — "Mia conoce las carpetas donde
     guardas tu trabajo."
   - **Notas (Obsidian)** — "Mia guarda y consulta tus notas." *(marcar "próximamente"
     si se quiere, ya que Obsidian está pospuesto)*
   Deja además un campo "otra…" para añadir libremente si el abogado quiere.

4. **De-jergar la pantalla "Conocimiento"** (`frontend/app/memoria/page.tsx`, pestañas
   línea ~14-18). Nombres nuevos (confirmados con Pipe):
   - "Wiki del despacho" → **"Temas que Mia va aprendiendo"**
   - "Lo que Mia sabe" → **"Documentos y fuentes"**
   - "Habilidades" → **"Lo que Mia sabe hacer"**
   - "Sugerencias de Mia" → **"Mejoras que Mia propone"**
   - "Mi despacho" → se queda igual (ya es claro).

**Reglas:** §G sin jerga ("SOUL", "tenant", "playbook", "wiki" no van); textos cálidos
y explicativos (estilo Hermes: cada opción con su descripción, un default sensato); tras
`npm run build` reinicia el dev server. **OJO — puerto:** Mia ahora corre en **3100**
(no 3000; el 3000 es de otro proyecto del equipo). Escribe tus hallazgos abajo.

</details>

---

## Checkpoint actual: CP-E6 — Más canales (relay) + conectar sistemas vía MCP (2026-07-04)

### Qué cambió (lenguaje simple)

- **Conectar sistemas del despacho (lo nuevo para el abogado):** Mia ahora puede conectarse
  a sistemas externos —**gestión documental** del despacho y **consulta de estados de
  procesos judiciales**— para trabajar con esa información. Todo nace **apagado**: el
  despacho lo enciende con sus credenciales cuando quiere, y lo apaga (o borra las
  credenciales) cuando quiere.
- **Seguridad primero:** las credenciales viven **fuera** del cerebro de Mia; se piden
  tokens de **solo lectura**; y al conectar, ningún secreto interno de Mia se filtra.
- **Más canales:** se preparó el patrón "relay" para que sumar canales (WhatsApp, correo…)
  sea un adaptador delgado, con las llaves del canal fuera del núcleo. El puente de
  Telegram ya usa ese patrón común.

### Frontend PENDIENTE para Cursor — pantalla "Sistemas conectados"

**COMPLETADO** (Cursor capa 3 · 2026-07-12). Detalle en "Hallazgos de Cursor (capa 3)" al final.

En Configuración → Conexiones, sección "Sistemas conectados". Endpoints (`/api/mcp/*`):

- `GET /api/mcp/status` → lista de sistemas. Cada uno trae: `slug`, `display_name`
  (mostrar ESTE, en llano), `description`, `permissions_note` (nota de permisos mínimos —
  mostrarla para tranquilidad del abogado), `fields` (cada uno: `env_var`, `label`,
  `is_secret`, `required`), `enabled`, `configured`, `missing` (etiquetas de lo que falta).
- `POST /api/mcp/{slug}/enable` con body `{ "env": {…}, "secrets": {…} }` → guarda las
  credenciales y habilita. `env` = campos NO secretos (URLs), `secrets` = tokens. Las
  claves van por `env_var`/`secret_key` que da `fields`. Devuelve el status actualizado.
- `POST /api/mcp/{slug}/disable` → apaga sin borrar credenciales. Devuelve status.
- `POST /api/mcp/{slug}/forget` → borra la conexión y sus credenciales. Devuelve status.

Comportamiento esperado en la UI:
- Por cada sistema: nombre + descripción + nota de permisos; un formulario con los
  `fields` (los `is_secret:true` como campo tipo contraseña). Botón "Conectar" (enable),
  y si `enabled`: "Desconectar" (disable) y "Borrar credenciales" (forget).
- El backend **nunca** devuelve el valor de un secreto — no intentes precargarlo; usa
  `configured`/`missing` para mostrar si ya está puesto.
- Errores del backend llegan en llano (§G) — mostrarlos tal cual. Nada de "MCP",
  "servidor", "tenant": el abogado ve "Gestión documental del despacho".
- **No urgente / activación diferida:** igual que "Conectar Microsoft 365", la conexión
  EN VIVO con estos sistemas depende de registrar el servidor real; la UI puede quedar
  lista sin que haya un sistema conectado todavía.

Detalle técnico completo en `docs/canales-y-mcp.md`.

---

## Checkpoint anterior: CP-E5 — Delegación multi-agente + tablero de misión por expediente (2026-07-04)

### Qué cambió (lenguaje simple)

- **Tablero de misión por expediente (lo que ve el abogado):** el abogado puede tomar un
  objetivo grande de un asunto —"preparar la contestación", "alistar la audiencia"— y Mia lo
  **descompone en hitos concretos y ordenados** que se ven como un tablero. Cada hito dice
  qué es, quién lo hace (**Mia lo prepara** o **lo haces tú**) y en qué estado va
  (**pendiente / en curso / hecho**). El abogado **aprueba, edita, reordena y marca avance a
  mano**: nada se ejecuta solo (consent-first).
- **Regla dura respetada:** el tablero **no maneja fechas ni plazos**. Si un hito toca un
  término procesal, queda **marcado para que el abogado lo verifique** (Mia nunca calcula
  plazos). No hay ninguna casilla de fecha en el tablero.
- **Investigación en paralelo (por dentro, no lo ve el abogado):** cuando un despacho trabaja
  en **dos o más jurisdicciones**, Mia ahora investiga cada una **por separado y a la vez**, y
  luego consolida. Para Lexia (solo Colombia) **no cambia nada** hoy: sigue el camino de
  siempre, mismo costo. Detalle en `docs/comparacion-cpe5.md`.

### Frontend a construir (Cursor — capa 3): el tablero de misión

Backend listo en `origin/main` (tras aprobación de Pipe). Falta la **pantalla del tablero**,
idealmente dentro de la vista de un asunto (una pestaña "Plan" o "Misión"). Endpoints (todos
bajo `/api`, auth como el resto; todos devuelven la **misión completa** salvo el DELETE de
misión):

- **`GET /api/missions?matter_id={id}`** → `{missions: [Mission]}`. Misiones del asunto.
- **`POST /api/missions`** body `{matter_id, title, objective, outcome?, auto_decompose?}`
  → `Mission`. Con `auto_decompose` (default true) Mia **propone los hitos** al crear.
- **`POST /api/missions/{id}/decompose`** body `{replace?}` → `Mission`. Re-propone hitos
  (`replace:true` sustituye los actuales; `false` los añade al final).
- **`PUT /api/missions/{id}`** body `{title?, objective?, outcome?, status?}` → `Mission`.
  `status` ∈ `"active"` | `"archived"`.
- **`DELETE /api/missions/{id}`** → `{ok:true}`.
- **`POST /api/missions/{id}/milestones`** body `{title, detail?, actor?, is_procedural?}`
  → `Mission`. Añade un hito manual.
- **`PUT /api/missions/{id}/milestones/{milestoneId}`** body cualquiera de
  `{title?, detail?, actor?, status?, seq?, is_procedural?}` → `Mission`. Avanzar un hito =
  `status:"done"`; reordenar = `seq`.
- **`DELETE /api/missions/{id}/milestones/{milestoneId}`** → `Mission`.

Forma de `Mission`:
```
{ id, matter_id, title, objective, outcome, status,
  progress: { done, total },
  milestones: [ { id, seq, title, detail, actor, status, is_procedural } ] }
```

- **Sin jerga (§G) — traducciones para pantalla:**
  - `actor`: `"mia"` → **"Mia lo prepara"**; `"abogado"` → **"Lo haces tú"**.
  - `status` (hito): `"queued"` → **"Pendiente"**, `"active"` → **"En curso"**, `"done"` → **"Hecho"**.
  - `is_procedural: true` → mostrar un aviso claro tipo **"Toca un plazo — confírmalo tú
    [VERIFICAR]"**. NUNCA calcular ni sugerir una fecha.
  - `progress` → barra "X de Y hitos".
  - `matter_id` es un identificador interno para ligar la misión al asunto (como el id de la
    misión); no mostrarlo como texto al abogado.
- Errores de validación llegan **422** con `detail` en llano (mostrarlo tal cual): título
  vacío, tope de misiones/hitos, misión/hito inexistente, etc. Errores de servicio **502** en
  llano. **404** si la misión no existe.

### Comportamiento esperado

- Crear misión "Preparar la contestación" con objetivo → Mia devuelve 3-8 hitos propuestos
  (pendientes), algunos marcados "Mia lo prepara". El abogado los edita/aprueba y va marcando
  "Hecho"; la barra de progreso sube.
- Si Mia no logra proponer (modelo caído) → devuelve una **lista genérica de planeación**
  editable (el tablero nunca queda vacío). Consent-first: nada se ejecuta solo.
- El objetivo con palabras de plazo ("contestar dentro del término") → el hito correspondiente
  llega **marcado como procesal** para que el abogado confirme el plazo.

### Resultado de verificación (3 capas)

- Capa 1: 3 gates nuevos — `test_delegation.py` **11/11** (concurrencia acotada, orden
  estable, fail-soft, tope duro), `test_missions.py` **40/40** (descomposición con guarda
  procesal fail-closed; CRUD y topes bajo RLS; AISLAMIENTO entre despachos; propiedad del
  expediente), `test_research_swarm.py` **21/21** (1 jurisdicción = camino simple sin costo
  extra; ≥2 = swarm con verificación por rama + síntesis; fail-soft; degradación por tope;
  dedup). Regresión **ALL PASS (59 suites)** con `test_rls` HALT.
- Capa 2 (revisor adversarial independiente): confirmó correctos RLS/aislamiento, regla de
  plazos, §G, fail-soft y concurrencia de uso. 1 MAYOR (carrera sobre el compresor compartido
  en el swarm) + 2 MENORES (dedup de jurisdicciones; degradación por tope) **corregidos y
  re-verificados ANTES del commit**; 2 residuales aceptados (orden de hitos por desempate;
  `matter_id` expuesto a propósito). Ver `memory/progress.md` sesión 33.
- Capa 3: **COMPLETADO** — ver "Hallazgos de Cursor (capa 3)" · 2026-07-04 (CP-E5, commit `f47f143`).

---

## Checkpoint reciente: CP-E4 — Banco de pruebas de calidad (eval harness) (2026-07-03)

### Qué es (lenguaje simple)

- Una herramienta INTERNA para medir si un cambio en Mia **mejora o empeora** la calidad de
  sus análisis, ANTES de confiar en él. Corre a Mia sobre un set de **casos de prueba
  sintéticos** (inventados, sin datos reales de cliente) y puntúa cada resultado con señales
  **objetivas** (sin que otra IA juzgue): cuántas citas quedaron sin respaldo, si el
  diagnóstico trae su cierre estructurado, si produjo borrador. Luego compara "antes vs
  después" y da un veredicto en llano: **mejora / sin cambio / regresión**.
- **No toca datos reales de cliente:** los casos son sintéticos por construcción; correr el
  banco sobre expedientes reales del despacho exige autorización explícita (candado
  fail-closed) — hoy no hay ni pantalla ni caso que lo haga.

### Frontend (Cursor — capa 3): NO aplica

- CP-E4 es una herramienta de **desarrollo/administración por línea de comandos**
  (`execution/run_eval.py`), no una función del producto para el abogado. **No hay UI que
  construir ni revisar.** Un panel de calidad para el despacho podría venir en un checkpoint
  futuro, pero no es parte de este.

### Resultado de verificación (3 capas)

- Capa 1: gate `test_eval_harness.py` **25/25** (scorer determinista; comparador detecta
  regresión/mejora con veredicto fail-safe; casos todos sintéticos; candado de datos reales
  fail-closed; end-to-end por el grafo real con LLM/embeddings stubbeados, incl. que intake
  recupera el expediente sembrado); regresión **ALL PASS (56 suites)** (test_rls HALT).
- Capa 2 (revisor adversarial independiente): candado de datos reales y determinismo de las
  métricas CONFIRMADOS. 1 MAYOR corregido y re-verificado ANTES del commit: el runner sembraba
  los documentos SIN embedding → intake los ignoraba y Mia redactaba "a ciegas" (el banco no
  ejercitaba la recuperación del expediente) → ahora se siembran con embedding como en
  producción y el gate exige que intake recupere el documento. 2 MENORES aceptados (ver
  memory/bugs-and-risks.md Riesgo #51).
- Capa 3: NO APLICA (sin frontend).

---

## Checkpoint reciente: CP-E3 — Personas jurídicas especializadas y editables (2026-07-03)

### Qué cambió (lenguaje simple)

- Mia ahora tiene **personas jurídicas** que el despacho **edita a su gusto**: un
  **litigante** (estratega procesal), un **tributarista** y un **revisor de citas**
  vienen listos de fábrica, y el despacho puede cambiarlos, deshabilitarlos, borrarlos
  o crear los suyos. Cada persona tiene su **voz** (cómo razona y con qué tono), sus
  **áreas de énfasis**, un **nivel de motor** y sus **frases de invocación**.
- El abogado **invoca** una persona escribiéndola en su propio mensaje — "actúa **como
  litigante** y analiza este asunto", "dame la **perspectiva tributaria**", "**revisa las
  citas** de este borrador" — en el chat de un asunto o hablando con Mia (Telegram). Mia
  adopta esa voz solo para ese turno. **Nada se auto-activa**: sin invocación, Mia trabaja
  exactamente como hoy.
- **Privacidad blindada:** una persona NUNCA puede mandar el trabajo del despacho a un
  motor de nube que su política no permita. Solo puede elegir entre "el motor del despacho"
  (respeta la política) o "siempre el motor local" (más privado y económico) — jamás al
  revés. El revisor de citas usa el motor local de fábrica.
- **La voz no relaja las reglas:** una persona colorea el tono, pero **nunca** puede hacer
  que Mia invente una norma o una cita — la regla de marcar con [VERIFICAR] lo no
  verificable manda siempre, por encima de cualquier persona.

### Frontend a construir (Cursor — capa 3): pantalla de personas en el Panel

- CP-E3 es **backend**; el abogado hoy invoca personas por frase en el chat (que ya
  existe). Falta la pantalla para **gestionarlas**. Endpoints listos (todos bajo `/api`,
  auth como el resto):
  - **`GET /api/personas`** → `{personas: [...]}`. Cada persona: `{id, name, title,
    role_prompt, tone, focus_areas[], model_tier, summon_phrases[], description, enabled}`.
    La primera llamada **siembra** las 3 canónicas del despacho.
  - **`POST /api/personas`** body con los mismos campos (name y role_prompt obligatorios)
    → la persona creada. `model_tier` ∈ `"estandar"` | `"local"`.
  - **`PUT /api/personas/{id}`** → la persona actualizada.
  - **`DELETE /api/personas/{id}`** → `{ok: true}`.
  - Errores de validación llegan **422** con `detail` en llano (mostrarlo tal cual):
    nombre duplicado, nivel inválido, tope alcanzado, etc.
- **Sin jerga (§G):** para `model_tier`, mostrar al abogado dos opciones en llano —
  "El motor del despacho" (`estandar`) y "Siempre el motor local — más privado" (`local`).
  Nunca nombres de modelo. `role_prompt` es "cómo debe razonar y hablar esta persona";
  `summon_phrases` es "frases con las que la llamas en el chat".
- Trabajo FUTURO opcional (no de este checkpoint): autocompletar las frases de invocación
  al teclear en el chat; un selector de persona en el asunto (hoy la invocación es por frase).

### Comportamiento esperado

- En un asunto: "Analiza esto **como litigante**" → Mia razona con voz de litigante en los
  5 especialistas del turno (hechos→investigación→cruce→borrador→corrección), sin cambiar
  el método ni la verificación de citas. Sin frase de persona → turno idéntico a hoy.
- Con Mia libre (Telegram): "**revisa las citas** de este texto: …" → Mia adopta la voz del
  revisor (motor local de fábrica) y marca lo no respaldado con [VERIFICAR].
- Nombre/persona deshabilitada o inexistente → Mia trabaja sin persona (no falla el turno).

### Resultado de verificación (3 capas)

- Capa 1: gate nuevo `test_personas.py` **52/52** (candado de motor fail-closed en las 3
  políticas incl. soberano; voz con guardrail [VERIFICAR] y sin jerga; detección por frase;
  validación; CRUD bajo RLS; AISLAMIENTO entre despachos; siembra idempotente que respeta el
  borrado); regresión **ALL PASS (55 suites)** (test_rls 12/12 HALT). Sin frontend web → sin
  npm build.
- Capa 2 (revisor adversarial independiente): los 7 invariantes SE SOSTIENEN
  (confidencialidad del motor, RLS, la voz no anula la citación, fail-open, comportamiento
  sin cambios, recursos/concurrencia, logs). Sin bloqueantes ni mayores. 2 MENORES
  (fail-open del asistente simétrico a stream; L3 citación añadida al system del asistente
  para que la regla dura preceda a la voz) + 1 NOTA (el candado 'local' devuelve el motor
  local por CONSTRUCCIÓN, no por posición de la cadena) corregidos y re-verificados ANTES
  del commit. Ver memory/progress.md sesión 32.
- Capa 3: COMPLETADO — ver "Hallazgos de Cursor (capa 3)" · 2026-07-04 (CP-E3).

---

## Checkpoint anterior: CP-E2 — Adjuntar pruebas por referencia (@expediente / @carpeta) (2026-07-03)

### Qué cambió (lenguaje simple)

- El abogado ya puede **traer evidencia a la conversación escribiéndola con `@`**: en el
  chat de un asunto o con Mia (Telegram/asistente) puede escribir `@expediente` (los
  documentos del asunto en curso), `@expediente:"Banco Popular vs Zurich"` (otro asunto
  del despacho, por su nombre) o `@carpeta:"Pruebas Zurich"` (una carpeta de trabajo
  registrada). Mia **expande la mención** e incorpora esa evidencia a su análisis del
  turno, sin que el abogado copie y pegue nada.
- Es donde más sirve **hablando con Mia libremente** (por Telegram o el asistente), que
  antes no traía documentos sola: ahora `@expediente:"..."` mete el expediente a la charla.
- **Privacidad primero:** una mención SOLO resuelve a expedientes y carpetas **del propio
  despacho** (nunca de otro), y **nunca abre un archivo del disco** — lee lo que Mia ya
  tiene indexado. Si el nombre no existe, está deshabilitado, o parece una ruta de
  computador, Mia lo dice en llano y no adjunta nada. Toda la evidencia entra **sellada**
  (Mia la trata como datos del caso, no como órdenes). Si el material referenciado es muy
  grande, se adjunta **recortado con aviso honesto** (nunca finge tener la prueba completa).

### Frontend (Cursor — capa 3): NO hay UI nueva

- CP-E2 es **sintaxis de mensaje** — el abogado escribe `@expediente`/`@carpeta` en el campo
  de chat que YA existe (asunto y, sobre todo, Telegram). No toca `frontend/`. **No hay nada
  que construir ni revisar** en la interfaz para este checkpoint.
- Trabajo FUTURO opcional (no de este checkpoint): un autocompletado que sugiera nombres de
  expedientes/carpetas al teclear `@` en el chat del asunto. Los datos ya existen
  (`GET /api/matters`, `GET /api/folders`). No es necesario para que la función trabaje hoy.
- Nota: sigue pendiente de Cursor el control del tope de gasto de **CP-E1** (ver abajo);
  ese trabajo NO se mezcló con CP-E2.

### Comportamiento esperado

- En un asunto: "Analiza @expediente a fondo" → Mia trabaja con los documentos del asunto
  (igual que antes, pero ahora explícito); "compara con @expediente:\"Otro caso\"" cruza con
  otro expediente del despacho. La búsqueda interna del turno usa el texto SIN la mención
  (no se ensucia con el documento adjunto).
- Con Mia libre (Telegram): "Según @expediente:\"Zurich\" ¿qué defensa tengo?" trae ese
  expediente a la respuesta. Nombre ambiguo o inexistente → aviso en llano, sin adjuntar.

### Resultado de verificación (3 capas)

- Capa 1: gate nuevo `test_context_references.py` **43/43** (parseo + denylist de rutas +
  resolución por título/etiqueta con RLS + AISLAMIENTO entre despachos + sellado
  anti-inyección + techo de tokens con recorte marcado + query de recuperación limpia);
  regresión **ALL PASS (54 suites)** (test_rls 12/12 HALT). Sin frontend web → sin npm build.
- Capa 2 (revisor adversarial independiente): confidencialidad/RLS, confinamiento a las
  filas del despacho (nunca disco), anti-inyección (CP-S1), escape LIKE y fail-open/closed
  CONFIRMADOS. 2 MAYORES (fetch sin LIMIT en SQL → tope de recursos; techo de tokens en el
  listado de carpeta → presupuestado por archivo) + 2 MENORES (`@expedientes` plural;
  query solo-referencia) corregidos y RE-VERIFICADOS CERRADOS antes del commit. Ver
  memory/progress.md sesión 31.
- Capa 3: NO APLICA (sin frontend en este checkpoint).

---

## Checkpoint anterior: CP-E1 — Auditoría de acciones + tope de gasto de IA (2026-07-03)

### Qué cambió (lenguaje simple)

- **Registro de auditoría:** Mia ahora deja rastro de cada acción del despacho
  (quién hizo qué y cuándo) en un registro interno append-only, por despacho. Es
  invisible y no cambia nada de la experiencia; sirve para cumplimiento/confianza
  al vender a firmas grandes. Guarda solo metadatos (acción, ruta, ids, resultado)
  — NUNCA el texto de la consulta ni el contenido del expediente.
- **Tope de gasto de IA:** el despacho puede fijar un presupuesto MENSUAL en dólares.
  Al alcanzarlo, los turnos nuevos se pausan con un aviso en llano hasta que el
  abogado suba el tope o llegue el mes siguiente. Antes solo se MEDÍA el gasto
  (tarjeta "Valor entregado"); ahora se puede LIMITAR.

### Frontend a construir (Cursor — capa 3): control del tope en el Panel

- **`GET /api/policy/budget`** → `{monthly_budget_usd, spent_this_month_usd,
  remaining_usd, over_budget, unlimited}`. `monthly_budget_usd`/`remaining_usd` son
  null cuando es ilimitado (`unlimited: true`).
- **`PUT /api/policy/budget`** body `{"monthly_budget_usd": 100}` (o `null`/0 para
  quitar el tope) → devuelve el estado ya actualizado.
- Sugerencia de UI: en el Panel de control, junto a "Valor entregado este mes",
  un control "Tope de gasto de IA este mes" — input en USD + "Sin límite"; mostrar
  gasto del mes y restante; si `over_budget`, un aviso ámbar "Se alcanzó el tope;
  los turnos están en pausa". Estado vacío/ilimitado en llano.
- El REGISTRO de auditoría es backend-only por ahora (no requiere pantalla); una
  vista "Registro de actividad" es trabajo futuro opcional.

### Comportamiento esperado

- Con tope fijado y gasto por debajo: todo igual. Al superarlo, un asunto o el
  asistente responden **402** con el aviso en llano (mostrar el `detail` tal cual).
- El dictado por voz NO cuenta como "acción" en el registro (alta frecuencia).

### Resultado de verificación (3 capas)

- Capa 1: gate nuevo `test_observability.py` **22/22** (auditoría RLS + fail-open +
  recorte de campos; tope: roundtrip incl. rama de producción, suma del mes UTC,
  bloqueo/permiso, fail-open); regresión **ALL PASS (53 suites)** (test_rls HALT).
  Sin frontend web tocado → sin npm build.
- Capa 2 (revisor adversarial): confidencialidad (sin fuga del mensaje a
  audit_logs — se guarda solo el path, no el query string), aislamiento RLS,
  fail-open y no-regresión del curador CONFIRMADOS. 1 BLOQUEANTE (el tope no
  persistía sobre la fila tenant_settings que todo tenant ya tiene → jsonb_set
  corregido) + 1 MENOR (borde de mes corrido 5h por la zona del servidor)
  corregidos ANTES del commit y re-verificados. Ver memory/progress.md sesión 30.
- Capa 3: COMPLETADO — ver "Hallazgos de Cursor (capa 3)" · 2026-07-04 (CP-E1).

---

## Checkpoint anterior: CP-Z2 — Conversación por voz en Telegram (2026-07-03)

### Qué cambió (lenguaje simple)

- **Mia ya habla.** Si el abogado le manda una NOTA DE VOZ a su bot privado de
  Telegram, Mia la transcribe (en el servidor del despacho, el audio nunca sale de
  ahí), responde, y le devuelve una NOTA DE VOZ hablada. Es el "asistente personal
  en el celular": le hablas y te contesta hablando.
- Regla de modalidad: **voz entra → voz sale; texto entra → texto sale** (el chat
  de texto por Telegram no cambia). Al recibir voz, Mia primero devuelve por
  escrito lo que ENTENDIÓ (para que el abogado verifique la transcripción) y luego
  la nota de voz de la respuesta.
- Respuestas largas (un borrador) siguen yendo por escrito; solo las respuestas
  conversacionales cortas se dicen habladas.

### Frontend (Cursor — capa 3): NO hay UI web nueva

- CP-Z2 vive 100% en el **canal de Telegram** (backend). No toca `frontend/`. El
  asistente conversacional de Mia no tiene pantalla web (es Telegram), así que no
  hay nada que construir ni revisar en la interfaz. El motor de voz de salida
  (`/api/speech/synthesize`, ver abajo) queda **reutilizable** para un futuro botón
  "Escuchar" en la web, pero eso NO es parte de este checkpoint.
- **La capa 3 de este checkpoint la hace Pipe en vivo:** crear el bot de Telegram
  (guía `docs/telegram-setup.md`), instalar la voz desde el Panel (botón "Instalar
  dictado por voz", que ahora también baja el modelo de voz de salida), y **dictar
  una nota de voz real** para oír a Mia responder hablando.

### Endpoint nuevo (por si la web lo usa después)

- **`POST /api/speech/synthesize`** (auth como todo /api/*): body `{"text": "..."}`
  → responde audio **OGG/Opus** (`audio/ogg`), 100% local. Errores en llano: 400
  (texto vacío), 413 (muy largo), 429 (rate-limit), 503 (voz no instalada u
  ocupada), 403 (motor de nube sin opt-in — hoy no aplica, es local).

### Resultado de verificación (3 capas)

- Capa 1: gate nuevo `test_speech_tts.py` **26/26** (síntesis local, códec Opus
  round-trip, candado de privacidad, 503 al estar ocupado, rate-limit);
  `test_telegram_bridge.py` extendido **37/37** (bucle de voz completo, modalidad,
  degradación a texto si el TTS falla, reply vacío, chat no autorizado);
  `test_speech_stt.py` **60/60** (instalación ahora incluye el modelo de voz);
  regresión completa **ALL PASS (52 suites)** (test_rls HALT). Sin `npm build`
  (no hay frontend web).
- Capa 2 (revisor adversarial independiente): confidencialidad, autorización,
  modalidad, instalación y concurrencia CONFIRMADOS; 1 MAYOR (espera del semáforo
  sin tope → 503 explícito) + 2 MENORES (reply vacío, guardia de tamaño) CERRADOS
  antes del commit. Ver memory/progress.md sesión 30.
- Capa 3: PENDIENTE — Pipe dicta una nota de voz real (lo único que la
  verificación automatizada no cubre).

---

## Checkpoint anterior: CP-Z1b — La voz instalada en el producto (2026-07-03)

### Qué cambió (lenguaje simple)

- El dictado por voz ya se instala DESDE LA PANTALLA: tarjeta nueva "Dictado
  por voz" en el Panel de control (sección Conectores) con botón "Instalar
  dictado por voz", confirmación explícita en ámbar, barra de avance de la
  descarga (~700 MB) y mensajes del servidor en llano. Ya no hace falta que un
  administrador corra un script.
- El recorrido "Configura a Mia" tiene el paso 7 "Dictado por voz" (detección
  automática + guía explicativa; "Ir al paso" lleva al Panel).
- El chat del asunto ya tiene el BOTÓN DE MICRÓFONO: dictas, Mia transcribe en
  el servidor del despacho (la voz nunca sale de ahí) e inserta el texto en el
  campo sin borrar lo escrito. Este botón lo construyó Claude Code — Cursor
  hace la revisión visual (capa 3), no la construcción.

### Endpoints para la UI (ya construida — revisar, no construir)

- **`GET /api/speech/status`** → `{estado, listo, mensaje, progreso}` donde
  `estado` ∈ instalado | no_instalado | descargando | error; `progreso` (solo
  descargando) = `{fase, descargado_mb, total_mb, porcentaje}` (total/porcentaje
  pueden ser null si el servidor de descarga no anuncia el tamaño).
- **`POST /api/speech/install`** body `{"confirmar": true}` → `{status, message}`.
  Sin confirmación → 400 con `detail` en llano (mostrarlo tal cual).
- **`POST /api/speech/transcribe`** (de CP-Z1): multipart `audio` WAV PCM16 16k
  + `pulir`; responde `{text, cleaned_text, duration_seconds, message}`.

### Qué revisar visualmente (Cursor — capa 3)

1. **`frontend/app/dashboard/page.tsx` · tarjeta "Dictado por voz"**: estados
   Inactivo / Instalando… (barra `role="progressbar"` con MB) / Instalado;
   confirmación `role="alertdialog"` antes de descargar; Cancelar no descarga;
   tras un error el botón reaparece con el mensaje en ámbar; el refresco es
   automático cada 2 s SOLO mientras descarga.
2. **`frontend/app/configurar/page.tsx`**: el paso 7 "Dictado por voz" se pinta
   con su guía expandible (el contenido viene del servidor — no requirió cambios
   en esta página; verificar que el acordeón y el progreso "N de 7" se vean bien).
3. **Micrófono** (`frontend/app/_components/MicButton.tsx`,
   `frontend/lib/useDictation.ts`, `frontend/lib/wav.ts`, integrado en
   `frontend/app/asuntos/[id]/page.tsx`): estados inactivo → grabando (pulso
   rojo + "Dictando… toca para terminar") → transcribiendo (spinner "Mia está
   escribiendo tu dictado…"); `aria-pressed` alterna; el permiso de micrófono se
   pide solo al primer clic; los errores del backend (400/413/429/503) y el
   aviso "No se escuchó voz en la grabación." salen en ámbar bajo el campo;
   PROBAR CON MICRÓFONO REAL dictando en español (lo único que la verificación
   automatizada no pudo cubrir).

### Comportamiento esperado

- Instalar desde la tarjeta: confirmar → "Empecé a descargar…" → barra avanza →
  la tarjeta pasa sola a "Instalado" (verificado en vivo con descarga real).
- Dictar un clip corto → el texto aparece en el campo en ~1-3 s, agregado al
  final de lo ya escrito. Un clip en silencio → aviso honesto en ámbar.
- Ningún texto visible trae jerga técnica.

### Resultado de verificación (3 capas)

- Capa 1: gate `test_speech_stt.py` extendido 41 → **57/57** (instalador:
  consent-first, single-flight, progreso, retry limpio, tar malicioso rechazado,
  idempotencia — sin descargar los pesos reales); `test_setup_wizard.py`
  **30/30** (7 pasos); regresión completa **ALL PASS (51 suites)**; `npm run
  build` verde ×2; verificación EN VIVO por navegador: tarjeta en sus 3 estados,
  confirmación/cancelar, instalación real (descarga del detector de voz desde
  internet), paso 7 del wizard, botón de micrófono con aria correcta, y POST
  multipart navegador→API con WAV real (CORS OK).
- Capa 2 (revisor adversarial independiente): ver memory/progress.md sesión 29.
- Capa 3 (Cursor): PENDIENTE — revisar lo listado arriba (en especial dictar
  con micrófono real).

---

## Checkpoint anterior: CP-Z1 — Dictado local (voz a texto) (2026-07-02)

### Qué cambió (lenguaje simple)

- Mia ya puede transcribir la voz del abogado SIN que el audio salga de su
  servidor: un nuevo servicio de dictado 100% local (mismo motor y parámetros
  que Lexter, el dictado que Pipe ya usa y validó en español jurídico).
- El backend está completo y probado; falta el botón de micrófono en la web
  (este HANDOFF). Opcionalmente, Mia puede "pulir" la puntuación del dictado
  con su modelo local (si Ollama está corriendo); si no, entrega el texto crudo.
- Si el servidor no tiene el modelo de voz descargado, el botón debe explicar
  en llano lo que el backend responde (503 con instrucción para el administrador).

### Frontend a construir (Cursor — capa 3): botón de micrófono

- **`POST /api/speech/transcribe`** (multipart/form-data, requiere Authorization
  como todo /api/*):
  - campo `audio`: archivo WAV PCM16 **16 kHz mono** (el navegador debe
    re-muestrear antes de enviar — ver nota técnica), máx. 5 minutos / 32 MB.
  - campo opcional `pulir`: `"true"` para pedir la corrección de puntuación con
    el modelo local (fail-soft: puede volver null).
  - Respuesta: `{text, cleaned_text, duration_seconds, message}` — `text` es la
    transcripción cruda; `cleaned_text` la versión pulida o null; `message`
    solo viene cuando no se escuchó voz ("No se escuchó voz en la grabación.").
  - Errores en llano listos para pantalla: 400 (audio ilegible), 413 (muy
    grande), 429 (demasiados clips seguidos), 503 (dictado no instalado en el
    servidor) — mostrar el `detail` tal cual (lib/api.ts ya lo propaga).
- **Nota técnica de captura:** `MediaRecorder` produce webm/opus, que el backend
  NO acepta. Capturar con Web Audio API (`AudioContext` + `MediaStreamSource`),
  acumular Float32, re-muestrear a 16 kHz mono (p. ej. `OfflineAudioContext`) y
  empaquetar WAV PCM16 en el cliente (~30 líneas; sin librerías externas).
- **UI sugerida:** botón 🎤 junto al campo de texto del asunto y del asistente;
  estados: inactivo → grabando (pulso rojo + "Dictando… toca para terminar") →
  transcribiendo (spinner "Mia está escribiendo tu dictado…") → texto insertado
  en el campo (usar `cleaned_text ?? text`). Si `message` viene, mostrarlo en
  ámbar. Accesibilidad: `aria-pressed` en el botón, estado comunicado con texto
  además del color. Pedir permiso de micrófono solo al primer clic.
- Referencia de diseño (en disco): `frontend/hooks/useSpeech.ts` y
  `components/Chat/MicButton.tsx`.

### Comportamiento esperado

- Dictar un clip corto en español → el texto aparece en el campo en ~1-3 s
  (motor local, sin GPU). Clips largos (hasta 5 min) tardan más y llegan
  completos. Un clip en silencio → aviso honesto, no texto inventado.
- El audio JAMÁS sale del servidor: no hay que pedir consentimiento de nube.

### Resultado de verificación (3 capas)

- Capa 1: gate nuevo `test_speech_stt.py` 35/35 (incluye integración real con
  el modelo descargado: español correcto y audio de 76 s por el camino VAD);
  regresión completa en verde (test_rls HALT).
- Capa 2 (revisor adversarial independiente): ver memory/progress.md sesión 28.
- Capa 3 (Cursor): PENDIENTE — construir el botón descrito arriba.

---

## Checkpoint anterior: CP-V2 — Auto-diagnóstico prescriptivo (2026-07-02)

### Qué cambió (lenguaje simple)

- La consolidación semanal de Mia ahora produce un DIAGNÓSTICO con hasta 4
  recomendaciones concretas para el despacho ("Ha corregido 6 veces respuestas
  del mismo tipo — suba su guía de trabajo y desaparecen"), cada una con
  evidencia real contada de la actividad (nunca inventada: con menos de 5
  eventos de señal, Mia calla), impacto en dólares según la tarifa del
  despacho, y puntaje que las ordena.
- Lo que el abogado acepta o descarta NO se le vuelve a mostrar, salvo que el
  problema siga vivo pasados 30 días (entonces vuelve marcado como recurrente).
- El reporte semanal menciona cuántas recomendaciones hay y la principal.

### Frontend a construir (Cursor — capa 3): tarjetas de diagnóstico en el panel

- **`GET /api/dreams/prescriptions`** → `{prescriptions: [...]}` ordenadas por
  impacto (máx. 4). Campos por tarjeta: `id`, `category` (retrabajo | rechazos |
  conocimiento | costo | guias | valor), `headline` (título en llano),
  `prescription` (la receta, 3-4 frases), `evidence` (lista de 3 pruebas con
  números reales), `dollar_impact` (USD/mes o null), `time_impact_mins` (o
  null), `status` (`new` | `recurring`), `age_days`.
- **`POST /api/dreams/prescriptions/{id}/decision`** con body
  `{"action": "accept"}` o `{"action": "dismiss"}` → la tarjeta desaparece.
  404 si ya fue decidida (refrescar la lista).
- Sugerencia de UI: sección "Recomendaciones de Mia" en el Panel de control
  (encima o junto a "Valor entregado"); tarjeta con headline + impacto,
  evidencia expandible, botones "Lo haré" (accept) y "Descartar" (dismiss).
  `recurring` con `age_days` alto merece un matiz visual ("lleva N días").
- Estado vacío en llano: "Mia aún no tiene recomendaciones — necesita más
  actividad para hablar con evidencia."
- OJO: las tarjetas reflejan la última consolidación semanal (no tiempo real).

### Resultado de verificación (3 capas)

- Capa 1: gate `test_dreams.py` extendido 16 → **43/43**; regresión completa
  **50/50 suites × 3 corridas** (test_rls 12/12 HALT); migración 022 aplicada
  e idempotente.
- Capa 2 (revisor adversarial independiente): APROBAR tras re-verificación —
  los 4 MAYORES corregidos antes del commit: (H1) una decisión del abogado
  tomada mientras corría el cron semanal podía perderse → el guardado ya nunca
  resetea una fila decidida (solo el resurgimiento explícito a los 30 días);
  (H2) la poda borraba la edad de problemas vivos que solo salieron del top
  por diversidad → ahora se conserva toda señal viva y el panel filtra;
  (H3/H4) la recomendación de costo v1 era imposible de ejecutar (proponía
  mover tareas que YA corren en el modelo económico, hacia una pantalla sin
  ese control) → rediseñada al gasto real pagado + el selector "Motor de IA"
  del Panel de control, verificado que existe y guarda. Menores H5-H7 y
  residuales R1/R2 también cerrados (Riesgo #44).
- Capa 3: COMPLETADO — ver "Hallazgos de Cursor (capa 3)" · 2026-07-04 (CP-V2).

---

## Checkpoint anterior: CP-C4b — "Configura a Mia" como onboarding explicativo (2026-07-02)

### Qué cambió (lenguaje simple)

- El recorrido "Configura a Mia" ya no solo detecta qué falta: ahora EXPLICA cada
  paso como un onboarding. Cada tarjeta tiene un botón "¿Qué es esto?" que despliega
  qué es la herramienta, para qué le sirve al despacho y cómo se hace paso a paso.
- Se agregó al final el mapa "¿Qué hace cada sección de Mia?" (Asuntos, Revisión de
  borradores, Conocimiento, Panel de control, este recorrido y Telegram).
- Mia también explica el siguiente paso completo cuando se le pregunta por la
  configuración (por Telegram): antes solo enumeraba, ahora acompaña.

### Frontend a revisar (Cursor — capa 3) + UI PENDIENTE de construir

- `frontend/app/configurar/page.tsx` — guía expandible por paso (contenido del
  servidor, `GET /api/setup/status` → `pasos[].guia` y `secciones`), sección del
  mapa de secciones, accesibilidad de la barra de progreso (`role="progressbar"`
  + aria) y del botón (`aria-expanded`). Foco de capa 3: legibilidad del texto
  largo, jerarquía visual del acordeón, contraste.
- **UI que el backend ya soporta pero el frontend AÚN NO tiene** (hallazgos del
  revisor de capa 2 — las guías se redactaron para no mentir mientras tanto, pero
  la experiencia queda a medias hasta que existan):
  1. **Panel de control · sección "Carpetas de trabajo"** — no existe. Backend
     listo: `GET /api/folders/detected`, `POST /api/folders`, `DELETE
     /api/folders/{id}`, `POST /api/folders/sync`. Debe listar carpetas
     registradas + nubes detectadas, permitir registrar por ruta y quitar.
  2. **Panel de control · tarjeta Obsidian: botón "Instalar Obsidian"** — hoy solo
     hay "Sincronizar" + input "Ruta del vault" (con jerga "vault"). Backend listo:
     `GET /api/obsidian/status`, `POST /api/obsidian/install` (body
     `{"confirmar": true}`), `POST /api/obsidian/bootstrap`. Falta el botón de
     instalar (con confirmación) y suavizar el texto "Ruta del vault" → "espacio de
     notas".
  3. **Pantalla de revisión de borrador · botón "Descargar en Word" + informe de
     verificación de citas** (pendiente de CP9, ver ese checkpoint abajo). Las
     guías de CP-C4b se escribieron asumiendo que ESTO existirá pronto.

### Resultado de verificación (3 capas)

- Capa 1: `test_setup_wizard` extendido **30/30**; regresión completa **43 suites
  verdes** (test_rls 12/12 HALT); `npm run build` verde.
- Capa 2 (revisor independiente): APROBADO CON CORRECCIONES — CORREGIDAS antes del
  commit: (L1) la guía llegaba cortada a 150 caracteres en el chat → ahora completa
  (check a4); (U1/U2/U4/U5/U8) las guías describían pantallas o un chat web que no
  existen → reescritas para decir la verdad del producto HOY y sin referencias
  circulares; (U3) la promesa de Word/verificación se suavizó hasta que Cursor la
  entregue. La UI faltante (carpetas, instalar Obsidian) quedó documentada arriba
  como trabajo pendiente en vez de fingir que existe. Revisión por lectura de
  patrones, no auditoría con herramientas.
- Capa 3 (Cursor): PENDIENTE — revisar la página y, sobre todo, construir la UI
  pendiente de los 3 puntos de arriba.

---

## Checkpoint anterior: CP9 — Equipo de especialistas para producir documentos (2026-07-02)

> Estado: APROBADO por Pipe y mergeado a `main` (2026-07-02). Falta la UI del
> frontend (botón Word + informe de verificación) — ver abajo.

### Qué cambió (lenguaje simple)

- Al preguntar en un asunto, Mia ya no trabaja "de un solo envión": ahora un
  equipo de especialistas hace el trabajo por etapas, cada uno con el estilo
  del despacho — uno establece los HECHOS del expediente, otro INVESTIGA las
  normas y sentencias aplicables según el país del despacho (usando primero el
  corpus jurídico interno del sistema), otro CRUZA hechos con derecho y emite
  el diagnóstico, otro REDACTA el borrador, y un VERIFICADOR revisa cita por
  cita: toda cita sin respaldo queda marcada [VERIFICAR] automáticamente
  (antes se nos escapaban sentencias sin marca — el riesgo detectado en la
  comparación de CP6).
- El avance se ve en vivo en el chat: "estableciendo los hechos…",
  "investigando normas…", "cruzando los hechos con el derecho…",
  "verificando las citas…".
- Botón nuevo posible: **descargar el borrador como documento Word** con
  formato de escrito judicial (el backend ya lo sirve).

### Frontend a revisar (Cursor — capa 3)

- NO se tocó ningún archivo del frontend en este checkpoint: el backend emite
  datos nuevos que la UI puede aprovechar. Trabajo sugerido para la
  Pantalla 2/3 (`frontend/app/asuntos/[id]/page.tsx`):
  1. Botón "Descargar en Word" → `GET /api/matters/{id}/draft.docx`
     (descarga directa; 404 si no hay borrador).
  2. Mostrar el informe del verificador de citas: el SSE `awaiting_review` y
     `GET /api/matters/{id}/draft` ahora traen `verification`:
     `{citas, marcadas, respaldadas, anotadas, detalle:[{cita, estado}]}`.
     Sugerencia: una línea sobria bajo el borrador ("Mia revisó N citas; M
     quedaron marcadas para tu verificación") con detalle expandible.
  3. Los mensajes nuevos del avance ya llegan por el evento `thinking`
     existente — no requiere cambio, solo verificar que se vean bien.

### Comportamiento esperado

- Al preguntar en un asunto: los mensajes de avance cambian por etapa (5
  frases distintas antes de "Borrador listo"); el turno tarda MÁS que antes
  (son 4 pasos de razonamiento en vez de 2 — calidad sobre velocidad).
- El borrador llega con TODAS las citas específicas o marcadas [VERIFICAR] o
  respaldadas en el corpus del sistema; el diagnóstico conserva el resumen en
  3 líneas (problema/normas/riesgo) de CP6.
- El Word descarga con encabezados, viñetas y el pie "no radicar sin
  verificar las citas marcadas".

### Bugs conocidos / fuera de alcance

- El detector de citas es conservador: puede marcar de más (inofensivo — el
  abogado revisa algo que estaba bien), y no detecta una marca escrita ANTES
  de la cita. Artículos con numerales intercalados ("artículo 164, numeral 2,
  literal i del CPACA") pueden escapar al detector — deuda anotada.
- El costo por turno aproximadamente se duplica (4 llamadas de razonamiento
  en vez de 2). Decisión consciente: calidad del documento sobre costo.

### Resultado de verificación (3 capas)

- Capa 1: gate nuevo `test_document_pipeline` **41/41**; regresión completa
  del repo en verde (43 suites; test_rls 12/12 HALT); `test_hitl_flow`
  actualizado al orden nuevo del equipo (19/19).
- Capa 2 (revisor independiente): APROBADO CON CORRECCIONES — 2 mayores
  CORREGIDOS antes del commit: (M1) los expedientes grandes recuperaban su
  turno solo una vez por conversación y ahora cada etapa tiene su propio
  rescate; (M2) un patrón del verificador podía congelar el servidor con
  texto malicioso (confirmado con medición) — reescrito y movido fuera del
  hilo principal; ambos con checks de regresión (cp9-37..41). Menores
  corregidos: nombre de archivo Word con caracteres especiales, contexto
  impreciso al especialista de hechos, color/limpieza del Word. Revisión por
  lectura de patrones conocidos, no auditoría con herramientas de escaneo.
- Capa 3 (Cursor): NO APLICA aún (sin cambios de frontend en este
  checkpoint); queda el trabajo sugerido arriba para cuando se apruebe CP9.

---

## Checkpoint anterior: CP-C4 — "Configura a Mia": el recorrido guiado (2026-07-02)

### Qué cambió (lenguaje simple)

- Página nueva **"Configura a Mia"** (enlace en la barra lateral): un checklist
  de 6 pasos que detecta solo qué está listo y qué falta (perfil, motor de IA,
  Obsidian, carpetas de trabajo, guías, Telegram), con barra de progreso,
  "Ir al paso", guía de Telegram integrada, y "Dejar para después"/"Retomar"
  (el recorrido se recuerda entre sesiones).
- Mia también guía por chat: si le pides "ayúdame a conectar mi Google Drive",
  responde con el estado real de la configuración, no de memoria.
- Detectar NUNCA instala ni registra nada: las acciones viven en sus pantallas
  con sus propias confirmaciones.

### Frontend a revisar (Cursor — capa 3)

- `frontend/app/configurar/page.tsx` (NUEVA) — checklist, progreso, guía de
  Telegram inline, mensajes de error en ámbar. Hallazgo del revisor de capa 2
  DIFERIDO a esta capa: la barra de progreso necesita `role="progressbar"` +
  aria; los estados del paso se comunican en parte solo por color/símbolo
  (accesibilidad).
- `frontend/app/_components/Sidebar.tsx` — enlace nuevo "Configura a Mia".
- Siguen pendientes los 4 archivos de CP7 (sección siguiente) — puede
  revisarse todo junto.

### Resultado de verificación (3 capas)

- Capa 1: regresión **42/42 suites PASS** (test_rls 12/12 HALT); gate nuevo
  `test_setup_wizard` **21/21**; `npm run build` verde.
- Capa 2 (revisor independiente): APROBADO CON CORRECCIONES — 3 mayores
  (disparador del chat confundía verbos jurídicos "se configura la causal";
  detección con winget de hasta 60 s en el camino del request → caché 60 s;
  I/O de disco bloqueando el event loop → threads) y 3 menores: corregidos
  antes del commit. Residual aceptado: carrera menor en "dejar para después"
  con dos clics simultáneos (se autocorrige). Revisión por lectura de
  patrones, no auditoría con herramientas.
- Capa 3 (Cursor): PENDIENTE — archivos listados arriba.

---

## Checkpoint anterior: CP7 — El abogado gobierna todo desde la pantalla (2026-07-02)

### Qué cambió (lenguaje simple)

- Pantalla "Conocimiento": pestaña nueva **Habilidades** (qué tan bien le va a
  Mia con cada procedimiento, con % de aprobación); botón **Importar guías**
  (sube las guías de trabajo del despacho en .md/.txt/Word, con detalle en
  llano de lo que se importó/omitió); cada sugerencia ahora dice **qué
  procedimiento se modificaría**; sección nueva **"Orden del conocimiento"**
  (propuestas de Mia para unir guías repetidas o archivar las sin uso, con
  Aprobar/Rechazar).
- Panel de control: el selector de modelos técnicos se reemplazó por **"Motor
  de IA"** en español llano (Mi suscripción / Nube / Todo en mi equipo) y
  ahora SÍ guarda el cambio; sección nueva **Recordatorios** (ver y cancelar,
  con fecha Y HORA); la clave de Pinecone ya se escribe oculta (••••).
- Onboarding: se retiró la pregunta del "modo profundo" (era una función no
  implementada — no se ofrece lo que no existe).
- Pantalla del asunto: el panel Diagnóstico mostrará el resumen en 3 líneas
  (problema/normas/riesgo) cuando el backend lo emita (llega con CP6, hoy
  pendiente de aprobación de Pipe; sin él, todo se ve como antes).

### Frontend a revisar (Cursor — capa 3) — TODOS los archivos de este checkpoint

- `frontend/app/memoria/page.tsx` — pestaña Habilidades, Importar guías,
  target en sugerencias, sección Orden del conocimiento.
- `frontend/app/dashboard/page.tsx` — Motor de IA, Recordatorios, input de
  clave oculto.
- `frontend/app/onboarding/page.tsx` — pregunta p19 retirada (verificar que la
  navegación entre preguntas no se sienta rota).
- `frontend/app/asuntos/[id]/page.tsx` — resumen estructurado condicional en
  el panel Diagnóstico (los 2 pendientes de CP5 sobre este archivo y
  `frontend/app/page.tsx` siguen abiertos — puede cerrarse todo junto).
- Foco de la capa 3: diseño de interfaz, accesibilidad (labels, foco,
  contraste), consistencia de UX entre secciones nuevas y viejas, y
  superficies de seguridad visibles (ninguna clave/dato sensible en claro).

### Comportamiento esperado

- Con datos: Habilidades lista procedimientos con barra de % aprobado;
  Importar guías muestra "Se importaron N guías…" con detalle por archivo;
  el selector de Motor de IA persiste tras recargar; cancelar un recordatorio
  lo quita SOLO si el servidor confirmó (si falla, aviso en ámbar).
- Sin datos: cada sección nueva tiene su estado vacío en español llano.

### Resultado de verificación (3 capas)

- Capa 1: regresión **41/41 suites PASS** (test_rls 12/12 HALT);
  `test_second_brain_ui` extendido **26/26**; `npm run build` verde.
- Capa 2 (revisor independiente): APROBADO CON CORRECCIONES — 1 mayor
  (cancelar recordatorio mostraba éxito aunque fallara) + 1 mayor
  preexistente (clave de Pinecone visible) + 5 menores: TODOS corregidos
  antes del commit. Revisión por lectura de patrones, no auditoría con
  herramientas. Deuda §G anotada fuera de alcance: textos "second brain",
  "vault", "Pinecone" del dashboard viejo.
- Capa 3 (Cursor): PENDIENTE — revisar los 4 archivos listados arriba y
  devolver hallazgos en la sección final de este documento.

---

## Checkpoint anterior: CP-C3 — El circuito de aprendizaje quedó cerrado (2026-07-01)

### Qué cambió (lenguaje simple)

- Cuando el abogado rechaza o corrige un borrador, la sugerencia de mejora
  que Mia genera ahora apunta al procedimiento que DE VERDAD participó en
  ese trabajo (antes podía proponer mejorar uno cualquiera), se redacta
  viendo el contenido real de ese procedimiento, y al aplicarla queda
  guardada la versión anterior (se puede volver atrás).
- El listado de sugerencias ahora dice QUÉ procedimiento se va a modificar.
- Para ver el ciclo completo en vivo falta UN insumo de negocio: que Pipe
  suba sus primeras guías de trabajo (botón/endpoint de importar guías).

### Frontend a revisar (Cursor — capa 3)

- Sin pantalla nueva. NOTA para CP7: `GET /api/proposals` ahora devuelve un
  campo `target` (título del procedimiento a modificar) — la Pantalla 4
  (memoria) debería mostrarlo junto a cada sugerencia. Siguen PENDIENTES de
  capa 3 los 2 archivos de CP5.

### Resultado de verificación (3 capas)

- Capa 1: regresión completa **41/41 suites PASS** (test_rls 12/12 HALT);
  gates extendidos: test_feedback_processor 26/26, test_gepa 18/18,
  test_trace_capture 23/23, test_ux 29/29.
- Capa 2 (revisor independiente): **APROBADO** sin bloqueantes; sus 2
  hallazgos mayores (del flujo pre-existente de aplicar sugerencias,
  agravados por este checkpoint) se corrigieron antes del commit.
  Revisión por lectura de patrones conocidos, no auditoría con herramientas.
- Capa 3 (Cursor): NO APLICA (sin frontend; ver nota para CP7 arriba).

---

## Checkpoint anterior: CP-B3 — Mia te avisa y recuerda (2026-07-01)

### Qué cambió (lenguaje simple)

- Mia ahora es proactiva: el abogado le pide recordatorios escribiéndole
  normal ("recuérdame radicar la tutela mañana a las 9") y Mia le avisa por
  Telegram a la hora pactada; también avisa cuando un borrador queda
  esperando su revisión (máximo un aviso al día por asunto) y envía el
  reporte semanal de lo aprendido.
- Regla de negocio dura: si el recordatorio menciona un plazo o actuación
  procesal, SIEMPRE va con [VERIFICAR] — la fecha la pone el abogado y la
  confirma él; Mia no calcula términos legales, y "días hábiles" ni se
  agendan: se pide la fecha exacta.
- Todo es opt-in: sin el bot de Telegram configurado, nada suena y Mia lo
  dice honestamente al confirmar ("quedará visible en tu lista de
  recordatorios").

### Frontend a revisar (Cursor — capa 3)

- CP-B3 NO trae pantalla nueva (la UI de recordatorios llega con CP7; ya
  existen los endpoints GET /api/assistant/reminders y POST
  /api/assistant/reminders/{id}/cancel). Siguen PENDIENTES de capa 3 los 2
  archivos de CP5 listados en el checkpoint anterior.

### Resultado de verificación (3 capas)

- Capa 1: regresión completa **41/41 suites PASS** (test_rls 12/12 HALT);
  gate nuevo `test_reminders` **64/64**.
- Capa 2 (revisor independiente, contexto fresco): APROBADO CON
  CORRECCIONES — 2 bloqueantes y 5 mayores, TODOS corregidos antes del
  commit y convertidos en checks del gate (detalle en memory/progress.md,
  sesión 22). Residuales aceptados en memory/bugs-and-risks.md (Riesgo #35).
  Revisión por lectura de patrones conocidos, no auditoría con herramientas.
- Capa 3 (Cursor): NO APLICA (sin frontend en este checkpoint).

---

## Checkpoint anterior: CP3 + CP-C2 — Conocimiento del despacho y vault de Obsidian (2026-07-01)

### Qué cambió (lenguaje simple)

- CP3: Mia ya analiza con el MÉTODO DEL DESPACHO — al diagnosticar un
  asunto usa las notas y criterios internos del despacho (lo indexado
  desde Obsidian y las carpetas de trabajo), siempre como orientación
  de método, nunca en reemplazo de la norma o la sentencia. APROBADO
  por Pipe con una comparación en vivo (mismo caso, con y sin el
  conocimiento del despacho).
- CP-C2: Mia escribe su memoria donde el abogado la ve — su vault de
  Obsidian. Los conceptos que aprende y los reportes semanales quedan
  como notas normales bajo la carpeta `Mia/` del vault; Mia JAMÁS toca
  las notas del abogado. Incluye instalación guiada de Obsidian para
  quien no lo tenga (con confirmación explícita).

### Frontend a revisar (Cursor — capa 3)

- CP3 y CP-C2 no traen pantalla nueva (la UI de conectores llega en
  CP7). Siguen PENDIENTES de la capa 3 los 2 archivos de CP5:
- `frontend/app/page.tsx`: punto naranja en la lista de asuntos cuando
  hay borrador pendiente (title="Borrador esperando tu revisión").
- `frontend/app/asuntos/[id]/page.tsx`: panel "Diagnóstico" (texto con
  scroll interno; estado vacío: "Mia aún no ha analizado este asunto.").

### Comportamiento esperado

- Con notas del despacho indexadas, al preguntar en un asunto el
  análisis refleja el método interno (y sigue marcando [VERIFICAR] lo
  que corresponda). Si el despacho no tiene notas indexadas, todo se
  comporta EXACTAMENTE igual que antes.
- Al consolidarse un concepto o generarse el reporte semanal, aparece
  una nota nueva en `{vault}/Mia/conceptos/` o `{vault}/Mia/reportes/`
  visible en Obsidian; las notas del abogado quedan intactas.

### Bugs conocidos / fuera de alcance

- Menores anotados por los revisores: el presupuesto del 15% para las
  notas usa un estimador de tokens aproximado (podría quedarse corto o
  largo en casos límite); si el disco/OneDrive del vault no está
  disponible, la nota espejo no se escribe (queda solo en el registro
  interno — no se pierde nada, se reintenta en el siguiente ciclo).
- Decisiones de producto pendientes de Pipe (ver bugs-and-risks.md):
  privacidad de las conversaciones del asistente, diagnóstico visible
  tras aprobar, y deshabilitar la instalación de Obsidian en Modo A.

### Resultado de verificación (3 capas)

- Capa 1 (automatizada): regresión completa **40/40 suites PASS**
  (test_rls 12/12 HALT PASS); gates nuevos: test_retrieval_knowledge
  **35/35** y test_vault_write **34/34**.
- Capa 2 (revisores independientes con contexto fresco): CP3 aprobado
  con 1 mayor CORREGIDO (las notas del despacho entran al prompt
  delimitadas y con orden de no obedecer instrucciones embebidas —
  anti-inyección — más margen de recorte y limpieza de metadatos).
  CP-C2 aprobado con 2 mayores CORREGIDOS (escape por junction/symlink
  de Windows hacia fuera del vault BLOQUEADO fail-closed — reproducido
  con mklink /J; escritura al vault ya no congela el servidor con
  discos lentos). Revisión por lectura de patrones conocidos, no
  auditoría con herramientas de escaneo.
- Capa 3 (Cursor): PENDIENTE — revisar los 2 archivos de CP5 listados
  arriba y devolver hallazgos en la sección final.

### Checkpoint anterior: CP-B2 + CP-C1 — Telegram y carpetas del abogado (2026-07-01)

Mia atiende por Telegram (bot privado single-chat, opt-in hasta que
Pipe cree su bot — guía docs/telegram-setup.md) y conoce las carpetas
de trabajo autorizadas (disco, OneDrive, Google Drive); carpetas de
sistema excluidas SIEMPRE. Gates: test_telegram_bridge 22/22 y
test_local_folders 39/39; test_obsidian_sync 22/22 sin regresión.
Revisores: CP-B2 con 2 mayores corregidos (token del bot filtrado a
logs; instructivo roto por espacios de la ruta); CP-C1 con 2 mayores
de privacidad corregidos (subcarpetas de sistema excluidas también en
el descenso recursivo; carpetas >2000 archivos sin pérdida de
conocimiento). Sin frontend (capa 3 no aplica).

### Checkpoint anterior: CP5 + CP-B1 — Diagnóstico visible y modo asistente (2026-07-01)

CP5: panel "Diagnóstico" en la pantalla del asunto + punto naranja de
borrador pendiente en la lista (gate test_ux 29/29 con npm run build);
2 ventanas de carrera de milisegundos anotadas (se autocorrigen solas).
CP-B1: modo asistente — conversación libre con memoria por tenant y
usuario (test_assistant 32/32); el revisor encontró 1 BLOQUEANTE de
confidencialidad entre despachos (compresor compartido) + 2 mayores —
LOS 4 hallazgos corregidos y cubiertos con checks antes del commit.
Capa 3 de Cursor PENDIENTE sobre sus 2 archivos de frontend (los
mismos listados en el checkpoint actual).

---

## Hallazgos de Cursor (capa 3)

### 2026-07-02 — CP9 + CP-C4b: UI pendiente construida + revisión visual

**Qué se construyó (las 3 piezas pendientes):**

1. **Pantalla de revisión de borrador** (`frontend/app/asuntos/[id]/revisar/page.tsx`):
   - Botón "Descargar en Word" en la cabecera → `GET /api/matters/{id}/draft.docx`.
     Nota técnica: la descarga NO puede ser un enlace directo porque el endpoint
     exige el header Authorization — se añadió `apiDownload()` en `lib/api.ts`
     (fetch → Blob → descarga). El error se muestra inline en ámbar, sin jerga.
   - Informe de verificación de citas bajo el borrador: línea sobria ("Mia revisó
     N citas; M quedaron marcadas para tu verificación") con detalle expandible
     cita por cita (`aria-expanded` en el botón). Cada estado se comunica con
     texto + color (no solo color): "Verifícala tú" / "Con respaldo" / "Anotada".
     Si `verification` es null (borradores previos a CP9) no se muestra nada.

2. **Panel de control · sección "Carpetas de trabajo"** (`frontend/app/dashboard/page.tsx`):
   - Lista las nubes detectadas (OneDrive/Google Drive) con botón "Registrar"
     (o sello "Registrada"), las carpetas registradas con "Quitar", y un
     formulario para registrar por ruta (con nombre opcional).
   - "Quitar" pide confirmación explícita porque borra el conocimiento indexado
     de esa carpeta ("Mia… olvidará lo que leyó de ella") — acción destructiva.
   - Botón "Revisar carpetas ahora" → `POST /api/folders/sync`; el mensaje del
     servidor (en lenguaje llano) se muestra tal cual.
   - Texto de privacidad visible: "Mia solo lee las carpetas que tú registres
     aquí. Nunca revisa nada fuera de ellas."

3. **Panel de control · tarjeta Obsidian** (`frontend/app/dashboard/page.tsx`):
   - Botón "Instalar Obsidian" (solo aparece si `GET /api/obsidian/status`
     reporta que NO está instalado) con confirmación explícita en un panel
     ámbar (`role="alertdialog"`) antes de llamar `POST /api/obsidian/install`
     con `{"confirmar": true}`. Cancelar no instala nada.
   - Se muestra el `message` del status en lenguaje llano bajo el título.
   - Jerga corregida (§G): "Ruta del vault" → label "Ubicación de tu espacio de
     notas"; el error de sync "No se pudo sincronizar el vault." → "…tu espacio
     de notas."

**Hallazgo transversal corregido:** `lib/api.ts` descartaba el `detail` que el
backend redacta en lenguaje llano — todo error llegaba al abogado como
"Error 400". Ahora `checkResponse` lee el `detail` del cuerpo JSON y lo usa
como mensaje, así los textos cuidados del backend (p. ej. por qué una carpeta
no es segura, o la confirmación que exige instalar) por fin se ven en pantalla.

**Deuda §G que sigue abierta (ya anotada en CP7, no se tocó aquí):** la tarjeta
"Pinecone" (con "vectores", "Index") y la sección "Salud del second brain"
("Skills activos/archivados") del panel de control siguen con jerga técnica.

**Consistencia pendiente (menor):** la pantalla de revisión usa `alert()` del
navegador para errores de Aprobar/Rechazar (patrón pre-existente); el resto de
la app usa mensajes inline en ámbar. Unificar cuando se retoque esa pantalla.

**Verificación:** `npm run build` verde (11/11 páginas, sin errores de tipos).

### 2026-07-04 — CP-E1 + CP-E3 + CP-V2: UI pendiente construida (capa 3)

**Qué se construyó (3 commits separados, ya en `origin/main`):**

1. **CP-E1 · Tope de gasto de IA** (`frontend/app/dashboard/page.tsx`):
   - Tarjeta "Tope de gasto de IA este mes" junto a "Valor entregado este mes" (grid de 2 columnas en pantallas grandes).
   - `GET/PUT /api/policy/budget`: input USD + checkbox "Sin límite"; muestra gasto del mes y restante cuando hay tope.
   - Aviso ámbar con `role="alert"` cuando `over_budget`: "Se alcanzó el tope; los turnos están en pausa."
   - Errores del backend (`detail` vía `ApiError`) se muestran tal cual en ámbar.
   - Verificado en vivo: registro de usuario de prueba → PUT tope 100 USD → respuesta coherente (`unlimited=false`, `monthly_budget_usd=100`).

2. **CP-E3 · Personas jurídicas** (`frontend/app/personas/page.tsx`, enlace en `Sidebar.tsx`):
   - Pantalla CRUD completa: lista las 3 personas de fábrica en la primera carga (`GET /api/personas` siembra).
   - Crear, editar (formulario inline), eliminar (con confirmación).
   - §G: `model_tier` como selector "El motor del despacho" / "Siempre el motor local — más privado" — sin nombres de modelo.
   - Etiquetas en llano: `role_prompt` → "Cómo debe razonar y hablar esta persona"; `summon_phrases` → "Frases con las que la llamas en el chat".
   - Errores 422 del backend se propagan tal cual (`ApiError.detail`).
   - Verificado en vivo: API devuelve Litigante, Tributarista, Revisor de citas tras registro.

3. **CP-V2 · Recomendaciones de Mia** (`frontend/app/dashboard/page.tsx`):
   - Sección "Recomendaciones de Mia" en el Panel (encima de valor/tope).
   - `GET /api/dreams/prescriptions` + `POST .../{id}/decision` con botones "Lo haré" / "Descartar".
   - Evidencia expandible (`aria-expanded`); matiz ámbar para `recurring` con `age_days`.
   - Estado vacío en llano: "Mia aún no tiene recomendaciones — necesita más actividad para hablar con evidencia."
   - Verificado en vivo: tenant nuevo → lista vacía (0 recomendaciones); rutas `/dashboard` y `/personas` responden 200.

**Build:** `npm run build` verde tras cada frente (12/12 páginas al final, sin errores de tipos).

**Deuda §G sin tocar (pre-existente):** tarjeta "Pinecone" (vectores, Index) y sección "Salud del second brain" (Skills) siguen con jerga técnica — anotado en CP7.

**Pendiente de Pipe (capa 3 en vivo, no automatizable aquí):** probar aceptar/descartar una recomendación real cuando el cron semanal haya generado tarjetas; invocar una persona editada en el chat de un asunto.

### 2026-07-04 — CP-E5: tablero de misión por expediente (capa 3)

**Qué se construyó** (commit `f47f143`, ya en `origin/main`):

- **`frontend/app/_components/MissionBoard.tsx`** + pestaña **Plan** en `frontend/app/asuntos/[id]/page.tsx` (junto a Consulta).
- CRUD completo vía `/api/missions/*`: crear misión con propuesta automática de hitos, editar título/objetivo, archivar/eliminar, re-proponer hitos (añadir o reemplazar).
- Hitos: editar título, actor, estado, reordenar (↑↓), añadir manual, quitar. Barra de progreso "X de Y hitos" con `role="progressbar"`.
- §G: `mia` → "Mia lo prepara"; `abogado` → "Lo haces tú"; estados → Pendiente / En curso / Hecho; `is_procedural` → aviso "Toca un plazo — confírmalo tú [VERIFICAR]". Sin campos de fecha.
- Errores 422/502 del backend mostrados tal cual (`ApiError.detail`).
- **`npm run build` verde** (12/12 páginas).

**Pendiente de Pipe (capa 3 en vivo):** crear una misión real ("Preparar la contestación"), editar hitos propuestos y marcar avance en un asunto con documentos.

### 2026-07-04 — CP-P2: automatizaciones consent-first (capa 3)

**Qué se construyó** (commit `5642a73`, ya en `origin/main`):

- Sección **Automatizaciones** en el Panel (`AutomationsSection.tsx` + `dashboard/page.tsx`).
- **Sugerencias de Mia:** `GET /api/automations/suggestions` con botones Activar / Descartar; aviso ámbar en plantillas que tocan plazos procesales.
- **Automatizaciones activas:** lista con resumen en llano (p. ej. "3 días de anticipación") y Quitar (`DELETE`).
- **Crear automatización:** catálogo de plantillas (`GET /api/automations/blueprints`) con formularios expandibles por campo (`entero`/`texto`/`opcion`); `POST` con `plantilla` + `valores`. Errores 422 mostrados tal cual.
- §G: sin "blueprint", "cron" ni "job" en pantalla.
- **`npm run build` verde** (12/12 páginas).

**Pendiente de Pipe (capa 3 en vivo):** tener un recordatorio procesal pendiente para que Mia proponga el aviso anticipado; aceptar/descartar en pantalla y verificar que queda activa.

### 2026-07-04 — CP-P3: calendario y correo (Microsoft 365 / Google) (capa 3)

**Qué se construyó** (commit `70ac8e7`, ya en `origin/main`):

- **`MailboxSection.tsx`** + **`MailboxSectionLoader.tsx`** (Suspense para query OAuth).
- **Panel de control · Conectores** y **Configura a Mia**: tarjeta "Calendario y correo".
- `GET /api/mailbox/status` — muestra conectado / proveedor o botones Conectar Microsoft 365 / Google Workspace.
- `POST /api/mailbox/connect/{provider}` → redirige a la URL de consentimiento; opción «Incluir contenido de correos» (`?content=1`).
- `DELETE /api/mailbox/disconnect`; `PUT /api/mailbox/content-analysis` — opt-in de resumen con IA (checkbox).
- Tras OAuth, el backend redirige a `/configurar?mailbox=conectado|error` — la UI muestra el mensaje.
- §G: sin "OAuth", "token" ni "Graph"; errores 503/422 del backend tal cual.
- **`npm run build` verde** (12/12 páginas).

**Pendiente de Pipe:** registrar la app en Azure/Google, pegar llaves en `.env`, y probar el flujo completo de conexión en vivo.

### 2026-07-06 — Rediseño del onboarding + de-jerga de Conocimiento (capa 3)

**Qué se construyó:**

1. **Pantalla final del onboarding** (`frontend/app/onboarding/page.tsx`):
   - Consume `summary` de `POST /api/onboarding/complete` y lo muestra en tarjeta con Markdown legible (viñetas y negritas).
   - El `soul_content` técnico quedó en `<details>` plegable "Ver detalle técnico".
   - Eliminada lógica de preguntas `p15`/`p16` (objetivo del año y pilares) que el backend ya no envía.

2. **Días de la semana (p17):** checkboxes ahora incluyen los 7 días (añadidos Sábado y Domingo).

3. **Herramientas (p18):** reemplazados chips libres por checklist curada con descripción por opción (Correo, Calendario, Gestor documental, Mensajería, Carpetas en la nube, Notas/Obsidian marcada "Próximamente") + campo "Otra herramienta" para texto libre. Los valores se envían como lista de textos en `memory.tools_that_survived`.

4. **Conocimiento** (`frontend/app/memoria/page.tsx`): pestañas renombradas — "Temas que Mia va aprendiendo", "Documentos y fuentes", "Lo que Mia sabe hacer", "Mejoras que Mia propone" (Mi despacho sin cambio).

**Build:** `npm run build` verde (12/12 páginas).

**Pendiente de Pipe (capa 3 en vivo):** completar el onboarding de punta a punta y verificar que el resumen final refleja las respuestas; probar selección de herramientas y días de fin de semana.

### 2026-07-12 — CP-E6: Sistemas conectados (capa 3)

**Qué se construyó:**

- **`frontend/app/_components/ConnectedSystemsSection.tsx`** — UI consent-first sobre `/api/mcp/*`.
- Integrado en **Configuración → Conexiones** (`ConexionesSection.tsx`), alineado al design system actual (`ConnectorCard`, `Button`, `Input`, `Label`).

**Comportamiento:**

- `GET /api/mcp/status` → una tarjeta por sistema (`display_name`, descripción, nota de permisos).
- Formulario con campos `fields` (secretos como password); **Conectar** → `POST .../enable` con `{ env, secrets }`.
- Si habilitado: **Desconectar** (`disable`) y **Borrar credenciales** (`forget`, con confirmación).
- Secretos nunca se precargan; errores del backend en llano (`ApiError.detail`).
- §G: sin "MCP" / "servidor" / "tenant" en pantalla.

**Build:** `npm run build` verde (warnings preexistentes de `useReducedMotion` en `_welcome/`, no bloquean).

**Pendiente de Pipe:** conectar un sistema real cuando el cliente MCP esté activo; OAuth/correo siguen con activación diferida.

### Corrección post-Cursor (Claude Code · verificación de la entrega integrada)

- **Exactitud del resumen del verificador (corregido):** la línea sobria contaba
  solo `marcadas` para decir cuántas citas verificar, pero el abogado debe
  verificar TODA cita con la marca [VERIFICAR] en el texto final = `marcadas`
  (las que ya venían marcadas del redactor) **+ `anotadas`** (las que el
  verificador añadió por no tener respaldo). Con el conteo anterior, un caso real
  (5 citas: 3 marcadas + 2 anotadas + 0 respaldadas) mostraba "3 quedaron
  marcadas" cuando en el borrador hay 5 con marca; y peor, un caso de 0 marcadas
  + 2 anotadas decía "todas quedaron con respaldo" (falso — 2 sin respaldo). Eso
  subrepresentaba justo el riesgo que CP9 existe para evitar. Corregido en
  `revisar/page.tsx` (`porVerificar = marcadas + anotadas`). Build verde,
  regresión 43/43 tras el cambio.

---

## 2026-07-17 — HANDOFF: cablear 3 features inertes + mejoras 2/3 del análisis claudeclaw

**Para quien retome (terminal fresca).** Rama `feature/robustecimiento-sin-aws`. Repo git en `D:\Inteligencia Artificial\Mia-Super Agent\mia`. Intérprete `.venv\Scripts\python.exe`. DB portable en 127.0.0.1:55432 (encender con pg_ctl si no escucha, ver memoria "mia-arranque-entorno-local"). Los tests son scripts: `.venv\Scripts\python.exe execution\test_X.py`. **HALT si `test_rls.py` falla.**

### Contexto: qué se hizo hoy (commits en la rama)
- `8cdc7a3` — cerró 6 de 8 riesgos de la sesión 48 (#68/#69/#70/#71/#72/#73).
- `ac7ed31` — fix contraste del control "Apariencia" (validación visual de las 13 pantallas: todas OK).
- `e8ce3b3` — **caching medido y CABLEADO** (antes el "~75%" era falso: ni medido ni activado) + arreglos de integridad de una auditoría de 4 frentes (datos jurídicos fabricados neutralizados, métricas del panel honestas, afirmaciones de docs corregidas).
- Análisis de referencia: `docs/analisis-claudeclaw-os.md` (de dónde salen las mejoras 2/3).

### REGLAS DE EJECUCIÓN (respetar)
- Si usas equipo de agentes: **grupos de archivos DISJUNTOS**, ningún agente hace git (el coordinador commitea), y **reservar el número de migración al EMPEZAR** (última usada = `042`; siguiente libre = `043`). El migrador ya bloquea prefijos duplicados (Riesgo #73).
- Cada cambio con su gate VERDE. §G: el abogado nunca ve jerga técnica.
- No degradar lo que ya es superior (migrador con ledger, personas en RLS, política de modelo).

### TRABAJO PENDIENTE (metas claras)

**A. Cablear Pinecone (hoy captura la clave de nube y muestra "activo" sin usarla).**
- Meta: que los vectores se escriban/consulten en Pinecone como store SECUNDARIO, detrás del opt-in por tenant que YA existe (`tenant_settings.config['pinecone']`).
- Archivos: `backend/mia/connectors/pinecone_connector.py` (interfaz `upsert/query/delete` + `get_pinecone_connector()`, hoy CERO llamadores en producción). Cablear `.upsert()` en el pipeline de ingesta (`backend/mia/ingest/`, `connectors/local_folders.py`, `connectors/obsidian_sync.py` — hoy solo escriben pgvector) y `.query()` en `agents/retrieval.py` como store secundario. Corregir el indicador "external_store: active" de `api/routes/ux.py` (~1676) para que refleje uso real.
- Nota: `pip install "pinecone>=3"` + pinnear en `pyproject` (Riesgo #18); crear índice dim 1024 coseno. Gate: extender `test_pinecone*` si existe; verificar aislamiento por namespace `{prefix}_{tenant_id}` (Riesgo #17).

**B. Cablear MCP (hoy guarda secretos y dice "conectado" sin lanzar nada).**
- Meta: un ejecutor que, para los servidores MCP habilitados del tenant, los levante y exponga sus tools al turno.
- Archivos: `backend/mia/mcp/service.py` (`resolve_server()` → `ResolvedMCPServer`, hoy sin consumidor), `mcp/catalog.py`, `mcp/security.py`, ruta `api/routes/mcp.py`. Falta el punto en `agents/graph.py` (o `agents/research.py`) que resuelva el server habilitado, lo levante como subproceso (cliente MCP stdio) y ofrezca sus tools durante el turno. Gate: `test_mcp.py` + uno nuevo de invocación real.
- Seguridad: los subprocesos MCP corren fuera del RLS (Riesgo #10) — acotar cwd/entorno como hace `agent_hub.sanitize_subprocess_env`.

**C. Conectar el Banco de oro al examen (hoy el abogado aprueba casos que no alimentan nada).**
- Meta: que `eval/cases.py::load_tenant_gold_cases()` (hoy CERO llamadores) alimente `eval/harness.py::run_suite` (hoy usa los casos SINTÉTICOS `GOLDEN_CASES`).
- Entrega: un endpoint "evaluar contra mi banco" o un job periódico, gated por `allow_eval_real_data` (ya existe). Correr `run_eval.py` deja de ser solo-dev. Gate: `test_gold_cases_api` + nuevo de que el banco confirmado influye en el examen.

**D. Mejora 2 — blindaje del instalador (antes de la prueba en vivo de Pipe).** Detalle en `docs/analisis-claudeclaw-os.md` §2.
- **Preservar secretos en upgrade (ALTO):** verificar que `backend/mia/setup/first_run.py`/`env_writer.py` NUNCA regeneran `DB_ENCRYPTION_KEY` ni el `.env` semilla si ya existen (leer-existente-o-generar). Un fallo aquí = datos cifrados irrecuperables al reinstalar.
- **Smoke-test post-first-run (ALTO):** al final del first-run, health-check real (FastAPI `/health`, LiteLLM.exe vivo, nº migraciones aplicadas == esperadas, checkpointer OK) y reportar. "Instaló" → "instaló y arranca".
- **Backup pre-migración (MEDIO-ALTO):** `pg_dump` a `app_dir/backups/pre-{ver}.dump` con rotación (3) ANTES de aplicar migraciones; enganchar `backend/mia/setup/backup.py` a `db_bootstrap.apply_migrations`.
- **Root de config canónico (ALTO/S):** auditar que TODO derive de `paths.py`/`app_dir`; nada hardcodee `%APPDATA%`/`expanduser` en paralelo.

**E. Mejora 3 — atajos de despacho + health-check de playbooks.** Detalle en `docs/analisis-claudeclaw-os.md` §5.
- **Atajos:** comando del abogado → PROMPT CANÓNICO reproducible que dispara un playbook/persona (capitaliza `playbooks`+`personas` que ya existen). Reservar migración si hace falta tabla.
- **Health-check de playbooks:** check que valida que cada playbook sigue "sano" (referencias resuelven, citas verificables), persistiendo estado. Alineado con la cultura [VERIFICAR].

**F. Limpieza trivial:** borrar `cron/scheduler.py::gepa_run_all_tenants()` (función huérfana, nunca registrada; Dreams ya llama GEPA internamente).

### VERIFICACIÓN PENDIENTE (capa 3 de Pipe, en vivo)
- **Caching:** confirmar el hit-rate REAL con API de Anthropic y un `SOUL.md` representativo (el prefijo estable debe superar el mínimo de ~1024 tok; sin SOUL real, la medición lee 0 — correcto pero da falsa impresión de "no funciona").
- **`test_ux.py`** (hace `next build`, ~10 min): confirma el panel nuevo (bloque "En el despacho" + caché) end-to-end.
- E2E del instalador en máquina limpia + delegación D3 (Riesgo #66) + banco de oro de punta a punta.

### Hallazgos de la auditoría NO críticos que quedaron anotados (no bloquean)
- Precios LLM hardcodeados con fecha (`metrics/usage.py:37`) — externalizar a config con `last_verified` algún día.
- Slugs de OpenRouter sin confirmar (Riesgo #62) — validar contra openrouter.ai/models antes de vender.
- Metadatos jurídicos del catálogo: cross-check ya añadido (corpus_factory); completar festivos trasladables/pascuales de `holidays.json` es trabajo de verificación jurídica (no inventar).

---

## 2026-07-17 — HANDOFF (adenda): principios del diagnóstico del harness jurídico (LLOS) → MIA

Fuente: diagnóstico "Del texto que se recuerda a la barrera que bloquea" (Codex + panel red-team) sobre el sistema de skills PERSONAL de Lexia (LLOS). No es MIA, pero su principio de arquitectura es universal y varios temas aplican al producto. Conecta directo con el trabajo de hoy (el "75% caching" era una garantía confiada a prosa; los datos jurídicos fabricados de `ingest_corpus` son el mismo "corpus contaminado" que el red-team describe).

### La regla que ordena todo (adoptarla como criterio de diseño de MIA)
**Si algo DEBE cumplirse, no puede ser una directriz.** Tres niveles con garantías distintas:
- **Orden** (script con código de salida, determinista) → garantía FUERTE.
- **Directriz** (prompt/prosa que sube la probabilidad) → garantía DÉBIL.
- **Restricción** (gate/supervisor que NIEGA, no que pide) → garantía FUERTE.
Las directrices solo hacen más probable pasar el gate; NUNCA son la barrera. Auditar toda "garantía dura" de MIA y clasificarla: la que sea solo prosa, convertir a orden o restricción.

### Temas a EVALUAR/implementar en MIA (con veredicto honesto)
1. **Auditar garantías prosa-vs-código (ALTO).** Recorrer las reglas duras de MIA (verificación de citas, §G, HALT de gates, política de modelo) y confirmar que cada una la hace cumplir CÓDIGO, no solo el prompt. El caching de hoy fue el caso ejemplar: afirmado, nunca ejecutado. MIA ya tiene gates reales (test_rls, especialista de citas) — falta el barrido sistemático.
2. **Gate de citas a nivel de PASAJE + cuarentena de fichas contaminadas (ALTO).** El red-team es duro: verificar que "el radicado existe" APRUEBA el error de mala atribución (el incidente real de 10 citas). La verificación debe confrontar el PASAJE textual contra el texto completo de la providencia en disco; ficha sin fuente almacenada = no apta, en cuarentena. Conecta con lo de hoy (corpus con datos fabricados ya neutralizados en `ingest_corpus`, pero el gate de MIA `agents/verification.py` marca/escanea — revisar si confronta a nivel de pasaje o solo de existencia).
3. **Veredicto de 4 estados, no binario (MEDIO-ALTO).** Hoy MIA aprueba/rechaza. Adoptar: APTO_TÉCNICO ("citas presentes y localizables; el juicio jurídico sigue siendo tuyo" — NUNCA "seguro para firmar") · REQUIERE_JUICIO · NO_APTO · EXCEPCIÓN_AUTORIZADA (override que expira, deja riesgo residual registrado y escala). Evita la falsa seguridad del semáforo verde.
4. **Gate de calidad que fuerza ESTRUCTURA, no puntaje (MEDIO-ALTO).** MIA ya mide "sustancia" (eval_substance, s48). Revisar que NO sea un juez 1-10 (premia "basura elocuente") sino que obligue la cadena completa: mejor tesis contraria → regla → hecho probado con evidencia → inferencia → objeción → respuesta → efecto pedido. Calibrar el umbral contra escritos ya radicados de la firma.
5. **Contrato de escrito con capa probatoria ANTES de redactar (MEDIO).** Estructura canónica por tipo de caso; cada argumento con ≥1 prueba mapeada como REQUISITO previo a redactar, no control posterior.
6. **Aprobación atada al HASH de sus insumos (MEDIO).** Si cambia una cita o una prueba tras aprobar, la verificación se invalida sola. Alinea con el estado transaccional; MIA tiene checkpointer LangGraph — evaluar atar la aprobación HITL al hash de documentos/citas.
7. **Meta corregida (filosofía de producto, ALTO como norte).** NO "el abogado solo aprueba" (o relee todo = cero ahorro, o firma a ciegas = riesgo disciplinario). SÍ "el socio decide derecho; el sistema verifica lo mecanizable; vista de auditoría para aprobar en minutos". El harness DETECTA los detonadores de escalamiento y FRENA — no los evita. MIA ya tiene detonadores; alinear el discurso de producto.
8. **Nombrar los modos de auto-engaño con su freno (MEDIO).** Verificador que lava el error (→ confronta el texto fuente, no la ficha); automatización complaciente (→ la vista resalta conflictos/riesgo, no un sello; registrar tiempo de aprobación); calidad como casillas (→ medir correcciones sustantivas reales); override como bypass (→ expira y escala).

### Lo que MIA YA cubre (no re-implementar, solo verificar que sigue firme)
HITL de borradores · detonadores de escalamiento · RLS fail-closed por tenant · muro de confidencialidad/anonimización · política de modelo (suscripción/nube/soberano) · medición de sustancia (parcial) · gate/especialista de citas (parcial — ver punto 2).

### Advertencia transferible del documento
"Verificado no es verdadero; verdadero no es bueno." El harness industrializa lo chequeable (citas localizables, formato) y deja intacto lo decisivo (calidad del argumento, responsabilidad profesional). El peligro real: que funcione lo bastante bien como para que el abogado deje de mirar. El diseño de MIA debe atacar esto de frente, no esconderlo tras un verde.
