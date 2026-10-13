**Veredicto: NO APTO.** Revisión acotada al delta `6c26afc → 5b142b5`, con sus soportes directos. Dos objeciones cambian el veredicto.

**(a) La fórmula no acredita una cota superior conservadora. Bloqueante.**

[§4.5, líneas 1233–1244](</D:/Inteligencia Artificial/Mia-Super Agent/mia/docs/banco04-cadena-contrato.md:1233>) permite certificar el techo mediante:

`11 × (entrada_estimada + 128000) + 2 × fondo_max`

Sus términos no garantizan ese límite:

- **Fondo:** duplicar el máximo de tres invocaciones sintéticas no limita las peticiones laterales de otra invocación, con contenido diferente o errores. Si la piloto observa cero, el margen también es cero. La instantánea y sus hashes acreditan lo observado; no demuestran que ninguna ejecución pueda superarlo. La fórmula permite certificar sin resolver esa diferencia.
- **Entrada:** `estimate_tokens` calcula caracteres/4 y declara expresamente que es una heurística, no el tokenizer de Anthropic. El juez utiliza caracteres/3. Tampoco esos cálculos acreditan toda la entrada finalmente enviada por el CLI. Incorporarlos a una fórmula no los convierte en máximos. [Estimador](</D:/Inteligencia Artificial/Mia-Super Agent/mia/backend/mia/memory/tokens.py:1>), [juez](</D:/Inteligencia Artificial/Mia-Super Agent/mia/backend/mia/eval/banco04/jueces.py:1335>).
- **Salida y reintentos:** la fuente oficial describe diez reintentos de **peticiones fallidas**, no once peticiones totales por invocación. Además, los máximos de salida dependen del modelo; 128 000 es el límite descrito para modelos que el CLI no reconoce. Aceptar `max_output_tokens == null` no demuestra un máximo universal de 128 000. [Documentación oficial](https://code.claude.com/docs/en/env-vars).

La existencia de `--debug-file` resuelve la disponibilidad del instrumento, pero no prueba su exhaustividad ante fallos ni transforma una muestra en límite superior.

**Corrección necesaria:** conservar `desconocido sin cota` mientras falte un límite acreditado para **todas** las peticiones, sus entradas y salidas. La medición propuesta puede servir como estimación empírica versionada; no como fundamento suficiente de `techo certificable`. E2E-19 comprueba la aritmética elegida, no su carácter conservador.

**(b) Imponer diez reintentos sí puede alterar la conducta medida. Mayor.**

[§4.3, línea 1082](</D:/Inteligencia Artificial/Mia-Super Agent/mia/docs/banco04-cadena-contrato.md:1082>) afirma que imponer el valor de fábrica no cambia la conducta. Eso solo resulta válido cuando el producto ya utilizaría efectivamente diez.

El producto conserva `CLAUDE_CODE_MAX_RETRIES` del entorno. Si recibe `0` o `15`, el envoltorio lo sustituye por `10`: cambia recuperación ante errores, tiempo y consumo, aunque ningún archivo del producto cambie. [Saneamiento original](</D:/Inteligencia Artificial/Mia-Super Agent/mia/backend/mia/agent/subscription_llm.py:125>).

**Corrección necesaria:** comprobar la equivalencia antes de intervenir; si no existe, conservar la configuración y negar la cota, o declarar expresamente que se mide una configuración normalizada distinta. La comparación con respuestas simuladas idénticas no demuestra equivalencia de reintentos reales.

**(c) No identifico una nueva vía contractual de publicación mediante `PruebaPuerta`.** Cualquier relajación exige `modo_prueba`, el publicador lo rechaza y las instantáneas de prueba quedan bloqueadas fuera de ese modo. Un `aprueba` de prueba conserva esa marca. El contraste independiente coincide. [§3.1](</D:/Inteligencia Artificial/Mia-Super Agent/mia/docs/banco04-cadena-contrato.md:590>).

**(d) K7 permanece resuelto.** La regresión relevante afecta la garantía de certificación: v6 permite convertir incertidumbre no acotada en techo certificable. También debilita la transparencia de K8 al confundir ausencia de cambios en archivos con ausencia de cambios de conducta.

Dictamen documental: sin modificaciones, acceso a recursos prohibidos ni ejecución de proveedores, bases o pruebas.

