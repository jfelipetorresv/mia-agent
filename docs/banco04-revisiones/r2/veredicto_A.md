**Veredicto del área A: NO APTO.** Las correcciones cierran los ejemplos originales, pero persisten aprobaciones sin evidencia suficiente. Ejecuté **24/24 checks existentes de I1–I3** mediante extracción AST y Python `-B`; las sondas adversariales adicionales reproducen los defectos siguientes.

**I1 — PARCIAL.** Se incorporaron inventario, recuento de evaluaciones y presencia de filas en [metricas.py:765](</D:/Inteligencia Artificial/Mia-Super Agent/mia/backend/mia/eval/banco04/metricas.py:765>) y [metricas.py:829](</D:/Inteligencia Artificial/Mia-Super Agent/mia/backend/mia/eval/banco04/metricas.py:829>). Lo cubre `gate_i1_i2`, incluidos los checks «entradas vacías NO aprueban», «falta un caso» y «no_concluyente sin recibo».

Sin embargo, reproduje `aprueba` en cuatro situaciones:

- Manifiesto con todas sus colecciones vacías: la puerta confía en el inventario suministrado.
- Banco de 17 casos con `techo_cuota({}, {})`: el consumo ausente se convierte en `cumple`.
- Comparación A-pequeños con solo **1 de 9 pares**: [metricas.py:535](</D:/Inteligencia Artificial/Mia-Super Agent/mia/backend/mia/eval/banco04/metricas.py:535>) omite los faltantes y termina como `descriptivo_sin_inferencia`.
- Recibo que declara cinco corridas adicionales, mientras `R` permanece en cinco: [metricas.py:818](</D:/Inteligencia Artificial/Mia-Super Agent/mia/backend/mia/eval/banco04/metricas.py:818>) comprueba campos, pero no acredita la extensión. El propio check «con recibo válido… aprueba» acepta ese supuesto.

**Cambio concreto:** validar el inventario contra el protocolo; exigir cobertura de casos, repeticiones y consumo en ambas versiones; vincular el recibo a las cinco ejecuciones adicionales efectivamente juzgadas, su consumo y el recálculo del resultado.

**I2 — PARCIAL.** Las condiciones ahora generan filas obligatorias en [metricas.py:786](</D:/Inteligencia Artificial/Mia-Super Agent/mia/backend/mia/eval/banco04/metricas.py:786>) y llegan al veredicto en `:884`. Pasan los checks de `gate_i1_i2` «cuota 100 → 120 sin mejora atribuida → reprueba» y «el veredicto global las incorpora».

Pero esas filas aceptan **cuatro diccionarios vacíos** como ausencia de pérdidas y permiten `aprueba`. Además, un decisivo presente en la base y ausente del resultado nuevo desaparece del control: [metricas.py:602](</D:/Inteligencia Artificial/Mia-Super Agent/mia/backend/mia/eval/banco04/metricas.py:602>) exige que exista su valor nuevo.

La atribución tampoco acredita causalidad: `:807–812` solo exige una comparación etiquetada `mejora` y un nombre de nodo no vacío. Reproduje aprobación de **36 subidas** con `nodo="NODO_INEXISTENTE"`, sin `usage_by_node`, atribuidas todas a A-pequeños.

**Cambio concreto:** comprobar completitud de casos y hechos antes de calcular pérdidas; ausencia ⇒ `no_certificable`. Exigir evidencia de consumo y mejora correspondiente al nodo y al ámbito de cada subida.

**I3 / C8 — PARCIAL.** El defecto original está corregido: [harness.py:594](</D:/Inteligencia Artificial/Mia-Super Agent/mia/backend/mia/eval/harness.py:594>) descuenta el marcador de truncamiento; [metricas.py:99](</D:/Inteligencia Artificial/Mia-Super Agent/mia/backend/mia/eval/banco04/metricas.py:99>) coteja disponibilidad por tramos y `:956` cuenta únicamente fragmentos completos. Ejecutados los diez checks de `gate_i3`; inspeccionados `g-1`, `g-2` y `g-2b` de producción. Queda pendiente corregir N2.

**Objeciones nuevas**

**N1 — BLOQUEANTE. Repeticiones duplicadas cuentan como ejecuciones independientes.** [metricas.py:356](</D:/Inteligencia Artificial/Mia-Super Agent/mia/backend/mia/eval/banco04/metricas.py:356>) usa `len(ms)` y `:365` suma etiquetas `evaluada`, sin verificar identidad de repetición. Reproduje `aprueba` repitiendo exclusivamente `repeticion=1` hasta completar cada R. **Cambio:** validar identificadores únicos y el conjunto exacto de repeticiones esperado por versión y caso. Añadir check de duplicación.

**N2 — MAYOR. Los nuevos rangos aceptan intervalos invertidos o vacíos.** [metricas.py:110](</D:/Inteligencia Artificial/Mia-Super Agent/mia/backend/mia/eval/banco04/metricas.py:110>) devuelve disponible para `[90,30)` y `[30,30)` aunque solo se envió `[0,40)` de cien caracteres. Reproducido independientemente. [custodia.py:364](</D:/Inteligencia Artificial/Mia-Super Agent/mia/backend/mia/eval/banco04/custodia.py:364>) tampoco valida esos rangos. **Cambio:** exigir `0 ≤ inicio < fin ≤ longitud_original` y coherencia con el fragmento; agregar checks negativos.

**N3 — MENOR. La captura duplica fragmentos al coincidir renders históricos.** [harness.py:617](</D:/Inteligencia Artificial/Mia-Super Agent/mia/backend/mia/eval/harness.py:617>) concatena todas las coincidencias. Tras renders `[A]` y `[A,B]`, registra la segunda llamada como `[A,A,B]`, con numeración incorrecta. Reproducido; el agregado deduplica, por lo que no infla `entraron`. **Cambio:** identificar el bloque efectivamente enviado sin sumar coincidencias históricas superpuestas.

La revisión independiente de los wrappers conservó render, mensajes, argumentos, retorno y excepción originales. **No encontré alteración de la conducta del producto en esas sondas secuenciales.** La restauración está en `harness.py:653–656`, cubierta por `g-4`, inspeccionado pero no ejecutado. No acredita un recorrido integral.

No modifiqué archivos ni leí datos prohibidos. No ejecuté suites completas, proveedores ni conexiones a bases.

