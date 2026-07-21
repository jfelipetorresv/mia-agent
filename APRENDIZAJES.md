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
    `statusline.js`, no todo `node`.
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
