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

