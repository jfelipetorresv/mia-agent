# CP-E5 — Comparación: investigación en paralelo (alto impacto) y por qué NO cambia tu trabajo hoy

**Qué es esto:** CP-E5 trae dos cosas. El **tablero de misión** es superficie nueva
(no toca cómo Mia analiza) y no necesita comparación A/B. La **investigación
delegada en paralelo** SÍ toca el motor de análisis, así que aquí queda la lectura
honesta de qué cambia y qué no.

## La decisión de diseño que baja el riesgo a casi cero para Lexia

La investigación en paralelo **solo se activa cuando el despacho tiene DOS O MÁS
jurisdicciones configuradas**. Con una sola jurisdicción —el caso de Lexia hoy, que
litiga en Colombia— Mia toma **exactamente el mismo camino de investigación de
siempre**: una sola pasada, byte por byte igual a antes de CP-E5. Cero costo extra,
cero cambio en el borrador, cero cambio en el diagnóstico.

Esto no es una promesa: es cómo está escrito el código. El turno pregunta cuántas
jurisdicciones tiene el despacho; si es una, ni siquiera entra a la lógica nueva.

## Qué pasa cuando SÍ hay dos o más jurisdicciones (despachos futuros)

| | ANTES (CP9, hoy en producción) | DESPUÉS (CP-E5) |
|---|---|---|
| Cómo investiga con varias jurisdicciones | UNA búsqueda que mezcla todas las jurisdicciones y UN investigador que redacta la memoria | UN investigador **por jurisdicción**, en paralelo, cada uno ceñido a su ordenamiento + un **sintetizador** que consolida |
| Verificación de citas de la investigación | El borrador final se verifica (igual) | Además, **cada rama verifica sus citas** antes de consolidar (control extra) |
| Costo por turno (multi-jurisdicción) | 1 llamada de investigación | N investigadores + 1 sintetizador (más caro; por eso solo se activa cuando aporta) |
| Costo por turno (una jurisdicción) | 1 llamada | **1 llamada (idéntico)** |
| Si un investigador falla | — | Los demás siguen; si fallan todos, cae al camino simple (nunca tumba el turno) |

**La ganancia:** un despacho que litiga en varios países deja de mezclar normas de
distintos ordenamientos en una sola búsqueda; cada jurisdicción se investiga por
separado y luego se cruzan las coincidencias y diferencias. Para Lexia esto es
capacidad **latente**: se enciende sola el día que trabajes un segundo país.

## Por qué no hay una corrida en vivo lado a lado en este documento

Para mostrar el camino nuevo haría falta un **corpus jurídico de una segunda
jurisdicción** cargado, que hoy no existe (el corpus real sigue pendiente de subir).
Con una sola jurisdicción, una corrida A/B daría **el mismo resultado en ambos
lados** —que es justamente la garantía de seguridad—. La evidencia de que el camino
nuevo funciona está en las pruebas automáticas (`test_research_swarm.py`): con una
jurisdicción corre el camino simple; con dos, delega un investigador por
jurisdicción, verifica cada rama y sintetiza; si todos fallan, cae al camino simple.

## Topes y guardas (para que nunca se dispare el gasto)

- Máximo de investigadores en paralelo por turno: **4 a la vez**, tope duro **8**.
- Cada llamada del turno sigue midiéndose contra el **tope de gasto del despacho**
  (CP-E1): si el mes se pasó del límite, el siguiente turno se frena como siempre.
- Toda la investigación respeta la **política de motor del despacho** (en modo
  soberano, todo local; nada del expediente sale fuera de la política).
