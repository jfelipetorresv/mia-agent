# APRENDIZAJES.md
# Lecciones convertidas en regla. Cada entrada es una REGLA accionable, no una anécdota.
# Consumido por `/EA-apply-learnings` al cierre de cada fase del plan maestro
# (`C:\Users\USER\.claude\plans\fable-puedes-estructurar-un-sleepy-sifakis.md`).
# Fuentes: memory/bugs-and-risks.md, docs/retrospectives/*.md.
# Al cerrar cada fase F0-F6, añadir aquí las reglas nuevas que la fase deje (no borrar las viejas).

## Verificación y gates

1. **Un gate en verde que no prueba nada es peor que no tenerlo.** Afirma una seguridad que no
   existe y toda la línea base se apoya en él. Tres gates de este repo estuvieron verdes sin probar
   nada en una sola semana (sesión 50); uno llevaba tres días roto sin que constara. Antes de confiar
   en un gate nuevo, exigir prueba de mutación: demostrar que SÍ puede ponerse rojo.
2. **Prueba de mutación obligatoria en todo check nuevo.** Y hasta la falsificación necesita
   falsificarse — una mutación puede dar verde por accidente (`"" in texto` siempre es cierto).
3. **Un gate que mockea la función bajo prueba NO prueba la propiedad real.** "32/32 verde" no
   significa "sin latencia" si el recurso lento (p. ej. `winget`) está mockeado. El verificador debe
   ejercitar o espiar el recurso real, no el mock.
4. **Toda restricción con un máximo debe preguntarse también si necesita un mínimo.** Un gate que
   solo mira el techo ("no desbordar") es estructuralmente incapaz de ver que se desperdicia la
   mitad del presupuesto.
5. **Al cambiar la FORMA de transporte de un dato (p. ej. el prompt), actualizar los gates que
   codifican la forma vieja.** Un split de mensajes para prefix caching cambió la forma del `system`
   y tumbó un gate que asumía "system = string byte-idéntico".
6. **Al cambiar un formato sellado (marcadores tipo `<<<DOC n>>>`), buscar las aserciones que lo
   comparan literal** antes de dar el cambio por cerrado.
7. **Todo comentario que describe un mecanismo debe re-verificarse cuando el mecanismo cambia.** Un
   comentario que miente sobre cómo funciona el código es una trampa para el siguiente que lo lea.

## Multi-agente y git

8. **Un solo escritor de git; grupos de archivos DISJUNTOS entre agentes.** Dos agentes IA sobre la
   misma carpeta git corrompen el estado. El coordinador integra y commitea; los agentes solo editan.
9. **El número de migración se reserva al EMPEZAR el trabajo, no al escribir el archivo.** Aplica en
   particular al trabajo multi-agente sobre el mismo repo (dos agentes ya colisionaron en el mismo
   prefijo).
10. **Verificar los hallazgos de los subagentes antes de propagarlos o descartarlos.** Un agente
    puede reportar "el fallo no es mío" o "no está cableado" sin haberlo confirmado; reproducir o
    grepear antes de aceptar la conclusión.
11. **El verificador adversarial re-corre el gate de forma independiente**, no confía en el reporte
    del implementador. Es lo que atrapa el "verde inventado".
12. **No atribuir decisiones de producto a Pipe sin que consten.** Separar explícitamente "arreglo
    técnico" de "decisión de producto" en comentarios y mensajes de commit.

## Entorno Windows de este repo (gotchas recurrentes)

13. **`Test-NetConnection` y `netstat` cuelgan el shell de esta máquina.** Sondear puertos con Python
    `socket` (`settimeout` corto) o `curl --max-time`.
14. **`find` y `Glob` pueden colgarse en este repo** (timeouts de 20-120s). `git ls-files | grep` es
    la alternativa rápida para localizar archivos por convención.
15. **Los procesos zombis de `statusline.js` (Node) saturan la máquina.** Ante "todo va lento",
    contar procesos primero, no asumir que el síntoma visible es la causa. Matar solo los
    `statusline.js`, no todo `node`. **Causa raíz encontrada y cerrada en F0**: el script leía
    stdin con `readFileSync(0)` (bloqueante) y con `refreshInterval: 1` generaba un proceso
    colgado por segundo. Arreglado con lectura asíncrona + vigilante `process.exit` a 1,5 s (de
    2566 procesos node a 46, cero zombis). **Regla ampliada**: un fallo que parece de red/proveedor
    (`ALL_PROVIDERS_EXHAUSTED`, tareas de fondo "killed" sin una línea de salida) puede ser el
    entorno saboteando el trabajo, no un bug de producto — contar `node.exe` ANTES de diagnosticar
    el código propio.
16. **Los servicios de desarrollo lanzados desde una sesión de agente mueren al terminar el
    comando** (el sandbox se lleva el árbol de procesos) — salvo que se lancen con
    `run_in_background` del harness, que sí sobrevive la sesión. Para que el usuario final los
    tenga siempre vivos, usar un lanzador de doble-clic (`Abrir Mia.cmd`) que él mismo ejecute desde
    su propia sesión.
17. **`uvicorn` no recarga en caliente** — reiniciar entre iteraciones de benchmark/eval.
18. **Nunca entregar a un no-técnico (Pipe) comandos multilínea con backtick de continuación.**
    PowerShell los parte al pegarlos. Una sola línea, siempre.
19. **Antes de concluir que algo "no carga" en el navegador, pedir el recurso por HTTP.** Si el
    servidor devuelve 200 en los recursos, el problema es del cliente (caché), no del servidor.
20. **Usar siempre el intérprete del venv del proyecto** (`.venv/Scripts/python.exe`), nunca el
    `py`/`python` global del PATH — evita degradar versiones de dependencias pineadas.
21. **Consultar el esquema real de la DB (`information_schema`) antes de escribir SQL exploratorio**
    — asumir nombres de columna (p. ej. `name` en vez de `title`) produce errores evitables.

## Producto y honestidad

22. **Ninguna capacidad se declara disponible si no está construida.** Modo A (Docker) llevaba
    declarado sin un solo Dockerfile en el repo — deuda comercial, no decisión diferible.
23. **Toda afirmación de arquitectura debe estar respaldada por una medición, no solo por diseño.**
    El "~75% de ahorro por caching" vivía en varios archivos sin que nada lo midiera ni lo activara.
    El arreglo correcto no es inflar el número: es cablear el mecanismo, medirlo, y declarar el
    límite honesto.
24. **Una instrucción de prompt no es un control.** El día que el modelo no obedezca, no hay red. El
    guardián determinista (verificación por código, no por instrucción) es irrenunciable para
    cualquier propiedad de seguridad o de cita — es la razón de ser del guardián de citas de MIA.
25. **Un fenómeno intermitente no se descarta con pocos intentos.** "No reprodujo en 3 intentos" no
    es evidencia de ausencia — es justo el patrón que se cuela a un escrito firmado el día del
    cliente. El banco de evaluación exige repeticiones (N=10 mínimo), no un solo pase.
26. **Cuantificar convierte una queja en un diagnóstico accionable.** "No revisa bien la información"
    es irrefutable; "1,3% del material indexado" dice exactamente qué arreglar.
27. **Auditar antes de construir.** Gran parte de lo que se pide ya existe y solo está mal expuesto;
    construirlo de nuevo duplica trabajo hecho.
28. **MIA es AGNÓSTICA DE JURISDICCIÓN — regla dura, no re-discutir.** Nunca hardcodear un país, una
    ley o un formato local en código común; todo lo específico de jurisdicción va en los packs de
    datos (`backend/mia/jurisdiction/packs/`).
29. **El input directo del abogado es fidedigno.** Lo que Pipe suministra directo (documentos,
    hechos, instrucciones, citas) se asume cierto y NO se verifica; el escepticismo del guardián
    aplica solo a lo que MIA infiere o genera.

## Higiene de repo y organización (este frente, F0)

30. **El `.git` de un directorio padre que no tiene `HEAD`/`refs`/`objects` no es un repositorio git
    funcional** — es ruido, no historia. No confundirlo con el repo real (que en este proyecto vive
    en `mia/.git`). Verificar con `git status` antes de asumir que un `.git` visible es operativo.
    (Ver diagnóstico completo en `specs/todo/00-f0-preflight.md`.)
31. **Antes de duplicar hooks/config de seguridad a nivel de proyecto, verificar si ya existe una
    versión global que cubra el repo sin restricción de directorio.** Duplicar lógica de seguridad
    en dos sitios es peor que tenerla en uno: diverge con el tiempo y nadie sabe cuál manda.
32. **Tres intentos iguales de la misma vía = cambiar de estrategia**, no repetir una cuarta vez.

## Guardián de gasto hermético y frente crítico (F0)

33. **Un guardián de gasto/seguridad no se cierra enumerando rutas de gasto una por una — no
    converge.** Construir un registro HERMÉTICO donde cada ruta esté GOBERNADA, DESACTIVADA o
    DECLARADA, y una entrada sin clasificar impide que la corrida arranque. Implementado:
    `SPEND_ROUTES` + `ensure_installed()` en `backend/mia/eval/spend_guard.py`; barrera:
    `execution/test_eval_harness.py`.
34. **Todo tope compuesto por varias fuentes se mide POR FUENTE, nunca solo el agregado.** Sumar
    esconde la fuente rota bajo la que sí funciona — ocurrió con modelo+embeddings: el agregado
    daba verde con la cota de embeddings rota. Medir y reportar cada fuente por separado.
35. **La excepción de un guardián crítico hereda de `BaseException`, nunca de `Exception`**, y el
    módulo se audita para que ninguna excepción propia se desvíe de esa regla. Un `except
    Exception` genérico en cualquier otro punto del codebase (p. ej. los 19 de `graph.py`) puede
    tragarse la señal del guardián en silencio — pasó DOS VECES por dos puertas distintas antes de
    blindarse. Implementado: `SpendGuardHalt(BaseException)` + `guard_exception_audit()` en
    `backend/mia/eval/spend_guard.py`.
36. **Exit code 0 no es prueba de que una corrida terminó bien** — puede ser una corrida FRENADA
    que una puerta de manejo de errores reporta como éxito. Verificar el motivo explícito además
    del código de salida, y probarlo con una mutación que fuerce el corte a mitad de corrida.
37. **Reservar presupuesto en el punto más cercano a "esto va a cobrar" (por intento cobrable), no
    en la capa que orquesta reintentos o saltos de alias.** Una reserva a nivel de `call_llm` deja
    sin cubrir los reintentos y los saltos de alias dentro de la misma llamada lógica.
38. **Al fijar el scope de un contador de gasto (de "no cuenta nada" a "cuenta de verdad"),
    auditar TODOS sus consumidores, no solo el que motivó el cambio.** El cómputo de sesión y el
    cómputo MENSUAL son consumidores distintos del mismo contador — arreglar uno y no el otro deja
    el gasto de pruebas filtrando al presupuesto real del despacho, y ese filtrado puede bloquear
    el turno real de un abogado.
39. **En el frente crítico de cada fase (dinero o seguridad), exigir dos verificadores de
    proveedor DISTINTO**, uno que audite con rigor y otro que ejecute sondas propias contra el
    código real. Un solo verificador, por bueno que sea, puede aprobar un estado que el segundo
    tumba reproduciendo el defecto en vivo — pasó en la ronda 3 de F0.
40. **Al arbitrar entre un verificador que razona y uno que ejecuta, descontar las cifras
    cuantitativas del que solo razona bajo presión (tiende a exagerar magnitudes) pero tomarse en
    serio cada defecto ESTRUCTURAL que señale**, sobre todo si lo reproduce ejecutando una sonda en
    vez de estimarlo.
41. **Preguntar al verificador algo práctico y concreto** ("¿autorizarías gastar esto sabiendo que
    es dinero real de una persona?") **en vez de pedir un veredicto abstracto** APROBADO/RECHAZADO
    — produce mejores respuestas porque ancla el juicio en la consecuencia real.
42. **Commitear lo ya aprobado sin esperar a que termine el frente que sigue en disputa** —
    asegura progreso; los commits baratos no dependen del que está en su ronda de verificación.
43. **Ninguna suite de prueba escribe su gasto/telemetría al libro de saldos REAL del despacho.**
    Usar siempre un tenant/sesión marcado por convención como desechable (nunca un ID que pueda
    colisionar con namespace de producción); verificar con grep antes de correr una suite que gasta
    dinero real.
44. **La medición sin persistencia no es medición: verificar QUÉ escribe a disco un runner ANTES
    de gastarle horas.** El camino `--repeat` del eval imprimía el panel y tiraba los crudos; 30
    corridas del baseline vivieron solo en un log que murió con el proceso (F1, 2026-07-22).
    Barrera: checks de cableado en `execution/test_eval_harness.py` (persist en `_run_repeat`).
45. **En esta máquina, el trabajo largo se corre en TROZOS foreground (<10 min) con persistencia
    por trozo y un agregador que recalcula desde los crudos.** Un factor externo sin identificar
    mata árboles de procesos completos (WMI y harness por igual; 3 tandas perdidas el 2026-07-22);
    ni el desacople salva. Herramientas: `execution/aggregate_eval_runs.py` + la sección de método
    del baseline en `memory/findings.md`.
46. **Un cero puede ser ciego: al endurecer un comportamiento, el gate debe exigir la señal
    POSITIVA del mecanismo, no la ausencia del síntoma.** "0 fugas" es indistinguible de "el
    modelo no citó" salvo que el informe registre la INTERCEPCIÓN (omitidas ≥ 1 con un fake que
    siempre desobedece). Implementado en los checks e2e de `test_eval_harness.py`.
47. **La dirección segura depende del dueño del texto.** Para fuentes/documentos, el cotejo
    estricto (marcar de menos jamás inventa respaldo); para el MENSAJE del abogado, el laxo
    (borrar de más es el daño — input fidedigno). El mismo cotejo no sirve para ambos:
    `_covers` vs `_contains_contiguous` en `backend/mia/agents/verification.py`.
48. **Ante cualquier lentitud (Glob/ripgrep con timeout es la primera señal), correr la sonda de
    salud ANTES de seguir**: `scripts/sonda_salud.ps1` (zombis de statusline/CPU/RAM/segador).
    La saturación pasó DOS veces en un día y ambas se detectaron tarde.
49. **Todo cambio del prompt core pasa por verificación adversarial independiente ANTES del
    commit, con la pregunta de ALCANCE como obligatoria**: ¿a qué nodos/modos llega esta capa y
    en cuáles NO debería aplicar? Los 2 MAYORES de la decisión #43 (registro adversarial
    incondicional; transcripción de norma vs jurisdicción desconocida) eran ambos de alcance y
    el autor no los vio — el verificador fresco sí, dos veces en la misma sesión (11 hallazgos
    reales en total). Barrera: checks `std-1..std-5` en `execution/test_prompt_builder.py`
    (las correcciones no pueden des-corregirse en silencio).
50. **Al editar un prompt cuyo output alimenta un parser, verificar QUÉ parte del texto
    sobrevive el parseo y dirigir el contenido a los campos que se conservan.** La prosa del
    moderador de la Sala fuera del bloque `=== DICTAMEN ===` se descarta: una instrucción
    puede cumplirse y aún así perderse. Barrera: check `std-5` (el moderador escribe DENTRO
    de los campos).
51. **Comandos Windows que Pipe corre con `!` llevan `MSYS_NO_PATHCONV=1` antepuesto** (el `!`
    corre en Git Bash y convierte `/Flags` en rutas: `schtasks /Create` → error "C:/Program
    Files/Git/Create"). Además: acción bloqueada por el clasificador de permisos = preparar el
    comando exacto para `!`, no buscar rodeos. Sin barrera automática (documentada).
52. **Ninguna sonda adversarial se publica leyendo solo el panel: hay que leer una muestra de
    borradores COMPLETOS.** Las 30 corridas de F2 (2026-07-24) daban "abstención honesta 0%" y
    "éxito de tarea 100%"; leyendo los crudos, 25 de 30 borradores empiezan diciendo
    textualmente que no pueden, y "éxito" contaba turnos en los que lo correcto ERA negarse.
    Publicar desde el tablero habría entregado dos afirmaciones que inducen a error sobre las
    dos líneas que un lector usa para juzgar el producto. Barrera: `harness.evidence_audit` +
    `--exige-evidencia` en `execution/aggregate_eval_runs.py` (si el texto no se persistió, el
    agregado avisa y puede reprobar) + 6 checks en `execution/test_eval_harness.py`. La barrera
    garantiza que el texto EXISTA para leerse; leerlo sigue siendo obligación del que publica.
53. **El instrumento del analista necesita la misma verificación que el del producto.** Una
    regex propia contó la palabra «nulidad» como «mención de la ley» y produjo un falso
    hallazgo de detector ciego (`citas=0` con 49 menciones aparentes) que estuvo a un paso de
    reportarse; el texto crudo mostró que MIA omite la referencia a propósito. Antes de
    reportar un defecto que detectó un script propio, confirmarlo contra la fuente. Sin
    barrera automática (documentada): la disciplina es del que analiza.
54. **En PowerShell el resultado vacío es el error silencioso.** `Select-String` que no
    encuentra nada devuelve vacío; ese vacío usado como índice (`$c[($i-1)..$fin]`) se evalúa
    como `-1` y copia el archivo ENTERO sin quejarse — así se archivó un HANDOFF de 185 líneas
    "recortado" a 186. Todo corte de archivo por índice se verifica después por nº de líneas y
    primera línea. Sin barrera automática (documentada).

## Barreras, medición y honestidad de las etiquetas (Sesión Pipe A · 2026-07-27/28)

55. **NINGUNA LECCIÓN SIN BARRERA — regla de trabajo, adoptada del harness de litigio del
    despacho (decisión #46.3).** Toda lección de una retrospectiva nombra la barrera ejecutable
    que la vigila (un test, un check, un gate) o se marca **«documentada»**, no «aplicada». El
    principio de fondo del harness es «lo que no tiene barrera, vuelve»: allí una contradicción
    de formato vivió una semana en 13 archivos y una cita fabricada reapareció en un banco
    autodenominado verificado, en los dos casos porque nada las vigilaba. Barrera de esta regla:
    la tabla de barreras de `memory/findings.md` §CIERRE DE F2, que enumera cada principio con
    el test que lo fija.
56. **Un detector léxico se desfasa en silencio cada vez que cambia el prompt: no falla, MIENTE
    EN VERDE.** El contador de abstención reconocía 11 frases y, tras las decisiones #43-#44,
    MIA dejó de usarlas: 25 de 30 borradores decían textualmente que no podían y el panel
    mostraba «Abstención honesta: 0%». Lo mismo puede pasarle a cualquier lista de frases del
    repo. Regla: todo detector por léxico se recalibra MIDIENDO los textos reales (no inventando
    frases) y su cobertura queda fijada por un test que impide que vuelva a caer a cero. Barrera:
    `execution/test_abstention_recalibrada.py` (bloque C, piso medido sobre los crudos).
57. **La etiqueta de una métrica es parte de la métrica.** «Éxito de tarea: 100%» medía «el turno
    no se cayó» y se leía como «acertó» — en casos de ataque donde lo correcto era NO entregar
    borrador. El código estaba bien; engañaba el rótulo. Regla: el nombre de cada línea del panel
    dice lo que la línea MIDE, y cuando «funcionó» y «acertó» son cosas distintas, van en dos
    líneas. Barrera: los checks M-2 de `execution/test_eval_panel.py`.
58. **Una métrica que cuenta apariciones de texto castiga el mejor comportamiento posible.** La
    única «fuga» de 60 corridas era MIA nombrando una norma PARA DECIR que no la reconoce: el
    detector contaba la aparición sin distinguir uso de mención. Regla: antes de convertir
    cualquier detector en gate, buscar el caso en que su mejor comportamiento dispara la alarma
    — y que ese caso sea un test. Barrera: checks G1-G9 de `execution/test_eval_substance.py`,
    cuyo primer dato es el pasaje real de `f2nube_entail_i`.
59. **Una barrera nueva nace como AVISO y solo sube a MURO cuando se mide que no bloquea trabajo
    bueno (decisión de dureza de Pipe).** El harness del despacho es duro porque es su taller —
    una barrera de más solo le molesta a él. MIA va a manos de otros despachos, donde un falso
    positivo se siente como que MIA no sirve. Excepción única: el banco de citas quemadas, que no
    admite falso positivo por construcción (la cita está en la lista que el propio abogado
    construyó, o no está).
60. **Al portar una barrera de otro repo, traducir el MÉTODO y derivar los datos; no copiar la
    lista.** El `check-partes-docx.py` del despacho lleva un catálogo de aseguradoras cableado —
    en MIA eso habría violado el agnosticismo de jurisdicción y habría creado una lista que
    mantener. La versión portada deriva el catálogo de `documents.parte` de los otros asuntos del
    propio despacho: misma protección, cero literales de país. Barrera:
    `execution/test_contaminacion_expediente.py`.
62. **Para verificar VISUALMENTE cualquier pantalla de Mia hace falta un despacho CON PERFIL, y
    omitir los pasos del recorrido NO basta.** Intentando capturar los avisos nuevos de la
    revisión de citas: el layout manda al login sin token (se siembra en `localStorage` con la
    clave `mia_token`, JWT firmado con `JWT_SECRET` del `.env`), y con token manda al onboarding
    hasta que el despacho tiene perfil — `POST /api/setup/steps/perfil/skip` devuelve 200 pero el
    gate de bienvenida no lo respeta, porque mira si el perfil EXISTE. Consecuencia práctica: una
    captura de UI exige sembrar el perfil del despacho (o correr la entrevista, que gasta modelo).
    **Pendiente con dueño**: un helper de siembra (`execution/seed_despacho_demo.py`) que deje un
    despacho listo para capturas; sin él, toda verificación visual cuesta 20 minutos de andamiaje.
    Sin barrera automática (documentada). Nota de entorno del mismo intento: el backend arranca
    con `python -m mia.api.run` **desde `backend/` como directorio de trabajo** — lanzado desde la
    raíz, el pool muere con `ProactorEventLoop` aunque el runner fije la política.
63. **Un `self` simulado en un test es contrato: la lógica que no necesita `self` no debe ser
    método.** Colgar la comprobación de afirmaciones negativas como método de la clase del grafo
    rompió `test_sentence_report.w_cableado`, que invoca `_verify_draft` con un
    `SimpleNamespace()`. Se movió a función de módulo. Barrera: el propio
    `execution/test_sentence_report.py`, que falla si vuelve a acoplarse.

64. **Un `git status` sucio que nadie mira acaba DENTRO del producto.** Una sesión de depuración
    agéntica dejó bloques `#region agent log` en tres archivos; nadie los quitó y al recompilar
    los payloads viajaron al instalador: un chunk de Next.js ya compilado hacía POST a
    `127.0.0.1:7610/ingest/...` desde la máquina del abogado. Se detectó por casualidad al mirar
    `git status` antes de un commit. Barrera: `test_sin_instrumentacion_debug.py`, y su capa
    importante NO es la del código fuente sino la del BUNDLE — la fuente limpia no basta porque
    el paquete puede venir de un árbol sucio anterior.

65. **Un borrado que no puede demostrar su resultado no da certeza, la simula.** Al construir el
    purgador del piloto, sus dos defectos peores fueron los que TRANQUILIZABAN: el slug de la
    carpeta de transcripts no contemplaba los espacios de la ruta, así que no la encontraba y
    reportaba «0 coincidencias»; y la búsqueda por subcadena marcaba para borrado cuatro corridas
    viejas ajenas porque «Nexa» casa dentro de «anexa». Reglas: cuando no se puede verificar un
    sitio hay que DECIRLO como problema (nunca como limpio), y la coincidencia es por palabra
    completa cuando de ella depende un borrado.

66. **El rastro de un expediente no está solo donde uno lo puso.** En la política 'suscripcion'
    MIA razona invocando el CLI con `cwd = MIA_HOME`, y ese CLI guarda el PROMPT COMPLETO de cada
    turno en `~/.claude/projects/<slug de MIA_HOME>/*.jsonl`: fuera de MIA, fuera del alcance de
    cualquier borrado interno, y con el expediente dentro (verificado). Antes de prometerle a un
    abogado que «no queda nada», inventariar los canales, no las tablas.

67. **Un defecto de capacidad se descubre con material real, no con casos de prueba.** Los casos
    sintéticos del banco tenían 2 fragmentos por documento; con ellos `embed_texts` nunca pasó del
    tope del proveedor. El primer expediente real (174 páginas) lo pasó a la primera y la ingesta
    falló ENTERA — y lo mismo le pasaba al abogado al subir un documento grande, porque
    `upload_document` usa la misma función. Corolario: al arreglar un troceo, lo peligroso no es
    trocear sino el ORDEN (quien llama empareja `vectors[i]` con `texts[i]`; desordenarlos guarda
    cada fragmento con el embedding de otro, y eso envenena la búsqueda SIN delatarse).

68. **Reintentar no arregla lo que falló por tamaño.** El CLI de la suscripción expiró tres veces
    a 300s con un expediente grande antes de saltar al motor de crédito, que respondió a la
    primera: 15 minutos tirados haciendo lo que iba a hacer igual. Un timeout por volumen es
    determinista, no transitorio: se salta de motor ya. Y si el salto cambia QUIÉN PAGA, hay que
    decírselo al abogado — un cargo que no esperaba es un cargo que no autorizó.

69. **Un gate de copy no puede cablear la redacción.** El check exigía la frase literal «ya pagas»
    y se puso rojo al simplificar el texto sin que nada hubiera empeorado. Un gate así obliga a
    «arreglarlo» en cada mejora de copy y entrena a ignorarlo: se verifica el CONCEPTO aceptando
    varias formulaciones. (El texto costó cinco iteraciones: ver
    `feedback-copy-mia-registro-profesional` en la memoria del harness.)

70. **Antes de comparar dos caminos, verificar que el segundo camino CORRIÓ.** `--agentic-compare`
    informó «IGUAL — encontró los mismos datos leyendo menos» cuando la lectura agéntica no se
    había ejecutado ni una vez (el motor de la suscripción no admite herramientas): las dos
    pasadas eran del MISMO camino clásico y su diferencia de tokens era ruido del modelo. Sin
    ejecución del brazo B no hay veredicto, hay etiqueta engañosa — la familia del riesgo #81.

71. **Un aviso calculado no es un aviso dado.** El texto que le dice al abogado que su consulta se
    pagó con crédito quedó una sesión entera escrito, probado y sin que nadie lo emitiera: vivía en
    la memoria del proceso. La regla del muro tiene su gemela en la interfaz — una barrera que no
    llega a la pantalla no protege a nadie, y su gate tiene que ejercer el CAMINO (aquí, el cuerpo
    real del SSE con un grafo de mentira), no solo la función que arma la frase.

72. **Mirar la pantalla encuentra lo que ningún test mira.** La primera hora de tener un despacho de
    prueba sembrado destapó dos defectos con años de superficie: un resumen que decía «todas con
    respaldo en sus fuentes» cuando la única cita se había RETIRADO del texto (la cuenta tenía dos
    casillas y las citas retiradas no caían en ninguna), y un normalizador que descartaba en
    silencio los avisos que el componente sí sabía pintar. Los dos estaban en la primera línea que
    lee el abogado. Corolario: el coste de mirar es lo que decide si se mira — bajarlo a un comando
    vale más que cualquier propósito de mirar más.

73. **Una prueba que depende de un empate es una prueba intermitente.** El gate del despacho de
    prueba pasaba y fallaba según qué fragmento recuperara el turno, porque todos los vectores del
    doble eran idénticos y el orden lo decidía un desempate arbitrario de la base. Un doble tiene
    que FORZAR la condición que la prueba afirma, no confiar en que salga. Aquí: los términos que
    deben quedar enterrados se embeben ortogonales a la consulta.

74. **Barrer no puede costar material.** La primera versión del barrido de cobertura apartaba 22
    fragmentos de la cola y luego deduplicaba: el dedup se comía parte del barrido y el turno
    acababa leyendo 86 donde antes leía 98. Cuando una mejora sustituye material por material, el
    descarte va ANTES de decidir cuánto se cede — si no, la mejora es una pérdida con buena
    intención. Solo se vio midiendo en vivo (el log del turno lo decía: «pasa de 98 a 86»).

75. **Repartir la lectura no es leer más, y hay que decir cuál de las dos se hizo.** El barrido y la
    relectura dirigida cambiaron DÓNDE cae la lectura (44 de 98 fragmentos vienen ahora de sitios
    que el ranking no habría traído), pero el recall de datos enterrados siguió en 1/3: leer 98 de
    252 ve el 39% del expediente se reparta como se reparta. Ninguna técnica de recuperación
    garantiza haber visto un fragmento concreto. Lo honesto no es prometer el dato: es declarar el
    alcance («leí 86 de 252») — la disciplina del muro de citas aplicada a la lectura.

76. **La palanca obvia estaba medida en contra.** Doblar el techo de lectura (128 → 256) parecía la
    respuesta al alcance; en vivo el turno dejó de caber en la suscripción, saltó a crédito (USD
    1,01 de tarjeta en UNA consulta) y agotó la cadena. Antes de proponerle a Pipe una palanca de
    gasto, correrla: una corrida convierte una discusión de criterio en un dato.

77. **Antes de creer que la pantalla está rota, dudar del andamiaje.** El recorrido automatizado no
    conseguía marcar un país y parecía un bloqueo del onboarding; era el selector del script (la
    casilla es `sr-only` bajo la ficha). Un clic real la marcó a la primera. Una herramienta de
    verificación también falla, y su fallo se disfraza de defecto del producto.
# 2026-08-12: Un gate queda obsoleto cuando cambia el contrato del grafo

**Error:** el runtime cambió de `verification` a `verificador_citas`, pero el gate HITL
conservó la secuencia anterior y quedó rojo; además dependía de infraestructura sin emitir
diagnóstico temprano.

**Fix:** actualizar contrato, documentación y gate en el mismo cambio, y confrontar en CI los
enlaces críticos del grafo con la secuencia esperada.

**Aplica en:** toda modificación de nodos, rutas o nombres que formen parte de un E2E.
# 2026-08-12: El nombre de tarea debe identificar la función, aunque comparta modelo

**Error:** hechos, investigación, análisis, redacción y verificación llamaban todos
`task="main"`; la medición por nodo existía, pero la política de modelos no podía auditar ni
calibrar el piso de cada función.

**Fix:** crear tareas jurídicas explícitas que hoy conservan la cadena fuerte de `main`, con
gates para todas las políticas. La separación habilita calibración posterior sin bajar calidad.

**Aplica en:** cualquier pipeline donde varias etapas usen el mismo proveedor pero tengan
responsabilidades, riesgos o presupuestos diferentes.
