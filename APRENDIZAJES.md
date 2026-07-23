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
