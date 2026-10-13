**Veredicto del área A: NO APTO.** En `f5d678b` siguen existiendo vías para obtener `aprueba` sin acreditar requisitos obligatorios.

Leí los tres dictámenes de R2, las correcciones del área y el protocolo completo. Ejecuté **55/55 checks focales satisfactorios**, extraídos por AST, y ocho sondas adversariales. Otro contexto verificó las conclusiones principales y ejecutó **12/12 sondas** de rangos y captura. Los checks existentes no detectan los bloqueantes siguientes.

**Estado de cada ítem de R2**

- **I1 — PARCIAL.** Se reconstruye el inventario, se exigen ambas versiones y se recalculan comparativas: [metricas.py:957](</D:/Inteligencia Artificial/Mia-Super Agent/mia/backend/mia/eval/banco04/metricas.py:957>) y `:1181`. Los checks **R2-A-I1**, [test_banco04_juicio.py:1453](</D:/Inteligencia Artificial/Mia-Super Agent/mia/execution/test_banco04_juicio.py:1453>), cubren inventario vacío, consumo ausente, pares incompletos y extensión sin corridas. Persisten la aceptación de resultados precalculados y una comparación previa no acreditada. **Cambio:** recalcular las decisiones desde evidencia vinculada y reconstruir la comparación anterior a la extensión; véanse R3-N1/N2.

- **I2 — PARCIAL.** Los diccionarios completamente vacíos y el decisivo ausente únicamente en la versión nueva ya bloquean: [metricas.py:708](</D:/Inteligencia Artificial/Mia-Super Agent/mia/backend/mia/eval/banco04/metricas.py:708>). Cobertura: **R2-A-I2**, [test_banco04_juicio.py:1542](</D:/Inteligencia Artificial/Mia-Super Agent/mia/execution/test_banco04_juicio.py:1542>). Sin embargo, **17 casos presentes con `{}` como inventario de decisivos en ambas versiones permiten aprobar**, aunque sus agregados declaren decisivos. La atribución tampoco queda vinculada a telemetría original. **Cambio:** cotejar los hechos esperados contra la clave y reconstruir decisivos y atribuciones desde sus registros.

- **I3/C8 — RESUELTA respecto del pendiente de R2.** Se conserva el descuento del marcador de truncamiento y ahora se rechazan los rangos inválidos: [harness.py:624](</D:/Inteligencia Artificial/Mia-Super Agent/mia/backend/mia/eval/harness.py:624>) y [metricas.py:112](</D:/Inteligencia Artificial/Mia-Super Agent/mia/backend/mia/eval/banco04/metricas.py:112>). Cubren `gate_i3` y **R2-A-N2**.

- **N1 — RESUELTA.** Las repeticiones conservan su identidad y se exige exactamente `1..R`, también en la base: [metricas.py:410](</D:/Inteligencia Artificial/Mia-Super Agent/mia/backend/mia/eval/banco04/metricas.py:410>) y `:1134`. Checks **R2-A-N1**, [test_banco04_juicio.py:1578](</D:/Inteligencia Artificial/Mia-Super Agent/mia/execution/test_banco04_juicio.py:1578>).

- **N2 — RESUELTA.** Se exige `0 ≤ inicio < fin ≤ longitud_original` y pertenencia al fragmento declarado: [custodia.py:380](</D:/Inteligencia Artificial/Mia-Super Agent/mia/backend/mia/eval/banco04/custodia.py:380>). Checks **R2-A-N2**, [test_banco04_juicio.py:1597](</D:/Inteligencia Artificial/Mia-Super Agent/mia/execution/test_banco04_juicio.py:1597>).

- **N3 — RESUELTA.** Las coincidencias históricas solapadas se descartan; `[A]` y `[A,B]` producen `[A,B]`: [harness.py:486](</D:/Inteligencia Artificial/Mia-Super Agent/mia/backend/mia/eval/harness.py:486>). Checks **R2-A-N3**, [test_banco04_juicio.py:1636](</D:/Inteligencia Artificial/Mia-Super Agent/mia/execution/test_banco04_juicio.py:1636>). El check de integración `:1647` solo inspecciona cadenas; no acredita ejecución integral.

**Objeciones de R3**

**R3-N1 — BLOQUEANTE. Los resultados declarados todavía sustituyen la evidencia.**  
[metricas.py:1175](</D:/Inteligencia Artificial/Mia-Super Agent/mia/backend/mia/eval/banco04/metricas.py:1175>) consume `cumple` de absolutos; `:1231–1237`, de decisivos y atribución; `:1238–1249`, la etiqueta del techo y sus recuentos.

Reproduje `aprueba`:

1. Añadiendo una afirmación sin respaldo a los casos, conservando las filas absolutas anteriores.
2. Cambiando únicamente `cumple=True` en una fila que registra un decisivo perdido.
3. Haciendo lo mismo con 36 subidas sin atribución.
4. Entregando como techo únicamente `resultado="cumple"` y `R_por_caso`, **sin consumos ni condiciones**.

El [límite declarado de §12.6:1357](</D:/Inteligencia Artificial/Mia-Super Agent/mia/docs/banco-calidad-04-protocolo.md:1357>) reconoce parte de estas vías. Declararlas no satisface §6.4. **Cambio:** recalcular o comprobar obligatoriamente la correspondencia con evidencia original completa; ausencia o contradicción ⇒ `no_certificable`.

**R3-N2 — BLOQUEANTE. El recibo acepta una comparación previa imposible.**  
[metricas.py:1100](</D:/Inteligencia Artificial/Mia-Super Agent/mia/backend/mia/eval/banco04/metricas.py:1100>) comprueba una etiqueta y un subconjunto de casos, pero no recalcula el antecedente. Una previa `no_concluyente` con **un solo par y diferencia −1** permitió `aprueba`; ese dato no acredita tal clasificación. **Cambio:** reconstruir la previa con las repeticiones originales completas y verificar desde ella la selección de casos. **R2-A-I1 no cubre este supuesto.**

**R3-N3 — BLOQUEANTE. C25 acepta atribución fabricada.**  
[metricas.py:1020](</D:/Inteligencia Artificial/Mia-Super Agent/mia/backend/mia/eval/banco04/metricas.py:1020>) coteja sumas del desglose aportado, sin vincularlo a llamadas observadas. Reproduje `aprueba` atribuyendo las subidas a `NODO_INEXISTENTE` mediante un desglose inventado que suma correctamente. **Cambio:** obtener `usage_by_node` de registros identificados y acreditar la relación de la mejora con el nodo. No basta hacerlo coincidir aritméticamente.

**C18–C26 y regresiones.** No reproduje regresiones nuevas en captura o rangos. C24 endurece el contrato, pero su implementación queda incompleta. C25 permite aprobar sin acreditar atribución; no objetó exigir mejora del mismo caso, requisito que §6.3 no formula literalmente. No identifico otra contradicción textual autónoma en C18–C23/C26 dentro de A. La falta de conexión del runner con `metricas_corrida` sigue siendo una integración pendiente; no acredita por sí sola un recorrido certificable.

No modifiqué archivos, accedí a datos prohibidos ni ejecuté proveedores, bases o suites completas.

