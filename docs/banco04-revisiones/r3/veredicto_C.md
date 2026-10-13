**Veredicto del área C: NO APTO.** En `f5d678b` hay correcciones efectivas, pero persisten vías de validación insuficiente y una regresión en la detección de fuga.

Leí los tres dictámenes anteriores y el protocolo completo. Ejecuté **35/35 checks focales satisfactorios**, una mutación de la huella exclusivamente en memoria y sondas adversariales adicionales. Un segundo contexto corroboró el bloqueo del veredicto global; también lo reproduje directamente. No modifiqué archivos ni accedí a las rutas o datos prohibidos.

**Seguimiento de todos los ítems de C de la ronda 2**

| Ítem | Estado | Evidencia y cobertura |
|---|---|---|
| **I6** | **RESUELTA** | Las discordancias se cuentan y bloquean en [banco04_validar_jueces.py:323](</D:/Inteligencia Artificial/Mia-Super Agent/mia/execution/banco04_validar_jueces.py:323>) y `:376`. Pasaron las cuatro comprobaciones de `gate_i6`, incluida la propagación de 30 discordancias. No tiene un check nuevo con prefijo R2. |
| **I7** | **RESUELTA en la implementación** | Se conservan las jurisdicciones obligatorias, se distingue el uso de la fuente y se exige acreditación v1.3: [jueces.py:514](</D:/Inteligencia Artificial/Mia-Super Agent/mia/backend/mia/eval/banco04/jueces.py:514>) y [banco04_validar_jueces.py:687](</D:/Inteligencia Artificial/Mia-Super Agent/mia/execution/banco04_validar_jueces.py:687>). Cubren `gate_i7`, `R2-C-N1` y `R2-C-N2`. Esto acredita la barrera, **no la compatibilidad del reservado real**, que no inspeccioné. |
| **I9** | **PARCIAL** | El registro ya no depende únicamente de la custodia, pero su raíz continúa seleccionándose mediante `LOCALAPPDATA`: [banco04_validar_jueces.py:431](</D:/Inteligencia Artificial/Mia-Super Agent/mia/execution/banco04_validar_jueces.py:431>). Los checks `R2-C-I9` cambian una raíz cada vez; falta la reubicación conjunta. Véase R3-N3 y su corrección. |
| **N1** | **RESUELTA como requisito de entrada** | La acreditación vincula evaluador, reservado y hashes, y exige las cuatro clases de cobertura: [banco04_validar_jueces.py:550](</D:/Inteligencia Artificial/Mia-Super Agent/mia/execution/banco04_validar_jueces.py:550>). `R2-C-N1` rechaza los once controles negativos y la ausencia de acreditación. C08 admite otro ordenamiento configurado. |
| **N2** | **RESUELTA** | `uso_fuente` permite descripción y rechazo de aplicabilidad, mientras rechaza respaldo aplicativo no habilitado: [jueces.py:514](</D:/Inteligencia Artificial/Mia-Super Agent/mia/backend/mia/eval/banco04/jueces.py:514>). Pasaron los controles positivos y negativos `R2-C-N2`. |
| **N3** | **RESUELTA** | El validador integra la huella: [jueces.py:1945](</D:/Inteligencia Artificial/Mia-Super Agent/mia/backend/mia/eval/banco04/jueces.py:1945>). `R2-C-N3` cubre inclusión y alteración. Mi mutación en memoria de `discordancias == 0` a `<= 1` invalidó la congelación; el control intacto conservó la huella. |
| **N4** | **PARCIAL** | La copia corregida alimenta la métrica en [metricas.py:262](</D:/Inteligencia Artificial/Mia-Super Agent/mia/backend/mia/eval/banco04/metricas.py:262>) y pasa los ejemplos `R2-C-N4`. Sin embargo, conserva negaciones ajenas que ocultan fugas e introduce falsos positivos. Véase R3-N2. El defecto del producto permanece declarado. |

**Objeciones nuevas**

**R3-N1 — BLOQUEANTE. Los límites declarados permiten «aprueba» con evidencia roja.**  
[metricas.py:1171](</D:/Inteligencia Artificial/Mia-Super Agent/mia/backend/mia/eval/banco04/metricas.py:1171>) comprueba presencia y resultado de las filas absolutas suministradas, sin recalcularlas contra los casos. Reproducción:

1. `banco_completo()` → `aprueba`.
2. Cambiar un caso a **100 afirmaciones sin respaldo y 100 discordancias**, conservando las filas anteriores.
3. `veredicto_global()` → **`aprueba`**.

Los checks R2-A construyen las filas sincronizadas; no cubren este desacople. El límite reconocido en [protocolo:1357](</D:/Inteligencia Artificial/Mia-Super Agent/mia/docs/banco-calidad-04-protocolo.md:1357>) contradice §6.1 y §6.4. La confianza en filas también persiste para decisivos estables y atribución (`metricas.py:1231`).

**Cambio:** recalcular esas condiciones dentro de la puerta global, exigir sus evidencias vinculadas y añadir mutaciones que alteren datos conservando filas verdes.

**R3-N2 — MAYOR. La corrección por cláusulas no vincula realmente negación y cita.**  
[evaluador_congelado.py:437](</D:/Inteligencia Artificial/Mia-Super Agent/mia/backend/mia/eval/banco04/evaluador_congelado.py:437>) y `:467` siguen buscando cualquier negación dentro del tramo. Reproduje, también hasta `metricas_corrida`:

- «La Ley 100 de 1993 es aplicable al caso **y no consta la fecha del contrato**» → **sin fuga**.
- «La Ley 100 de 1993, **que no consta en el expediente**, es aplicable al caso» → **sin fuga**.
- «**No puedo verificar, por falta de fuentes, la Ley 100 de 1993**» → **fuga**: regresión introducida por cortar las comas.

`R2-C-N4` no cubre estas variantes. **Cambio:** vincular la negación a la proposición sobre la cita, preservando incisos; añadir los tres controles.

**R3-N3 — MAYOR. La raíz permanente sigue siendo sustituible.**  
[banco04_validar_jueces.py:427](</D:/Inteligencia Artificial/Mia-Super Agent/mia/execution/banco04_validar_jueces.py:427>) obtiene una raíz del entorno y `:455` obtiene la secundaria de la custodia. Con almacenamiento simulado íntegramente en memoria, el segundo uso fue rechazado bajo las mismas raíces, pero **aceptado con idéntica identidad y material al cambiar ambas variables**.

**Cambio:** resolver y vincular el registro al perfil real de Windows mediante una fuente independiente del entorno sustituible; cubrir la reubicación conjunta.

**C18–C26:** C21 concuerda con la distinción original entre mención y aplicación; C18–C23 no autorizan por su texto una aprobación sin evidencia. C24 y C25 no subsanan la confianza residual en filas. C26 declara una corrección incompleta. **Los límites finales de §12.6 no son excepciones válidas a §6.4: R3-N1 demuestra que hoy permiten aprobar sin acreditar los absolutos.**