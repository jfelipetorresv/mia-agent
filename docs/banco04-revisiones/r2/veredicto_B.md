**Veredicto del área B: NO APTO.** Las cuatro objeciones tienen correcciones reales, pero conservan caminos que incumplen el control exigido. Revisé los tres dictámenes anteriores y el código en HEAD `3611b75`.

**I4 — PARCIAL.** La vía «cota desconocida» funciona cuando recibe `None`: llega al techo, al veredicto y al resumen publicable mediante [metricas.py:625](</D:/Inteligencia Artificial/Mia-Super Agent/mia/backend/mia/eval/banco04/metricas.py:625>), `:894` y `:915`. Ejecuté satisfactoriamente el check **«P10 (métricas) un intento fallido sin cota hace el techo no certificable»**, además de una sonda de propagación hasta el informe.

Sin embargo, **la implementación contradice la solución declarada**: [spend_guard.py:1083](</D:/Inteligencia Artificial/Mia-Super Agent/mia/backend/mia/eval/spend_guard.py:1083>) introduce una tabla de máximos para alias flotantes de Claude; `:1242` vuelve a marcar la cota como aplicada. La sonda devolvió **131.072** para Opus. Los checks de producción **`i-1` e `i-3` exigen expresamente que ese timeout sea certificable**. La tabla sobre máximos de API no acredita por sí misma el límite efectivo de esa ejecución CLI. Además, [jueces.py:1321](</D:/Inteligencia Artificial/Mia-Super Agent/mia/backend/mia/eval/banco04/jueces.py:1321>) sigue fabricando una cota genérica, incluso para Codex.

**Cambio:** aplicar consistentemente la vía declarada —cota desconocida— o acreditar otra solución efectiva por invocación; modificar los checks que hoy consolidan la contradicción.

**I5 — PARCIAL.** Hay registro anterior a cada intento y control de ambos proveedores en [run_banco04.py:1074](</D:/Inteligencia Artificial/Mia-Super Agent/mia/execution/run_banco04.py:1074>) y `:391`; los runners lo invocan mediante [jueces.py:1397](</D:/Inteligencia Artificial/Mia-Super Agent/mia/backend/mia/eval/banco04/jueces.py:1397>). Cobertura declarada: **producción `i-4`–`i-14` y juicio `gate_i5`**. Reproduje correctamente la suspensión de **7 M de producción frente a techo 8 M y reserva 6 M**.

Persisten cuatro huecos:

- `motivo_juicio` ignora `cota_calculable=False`: la sonda permitió otra llamada después de consumo desconocido.
- [banco04_validar_jueces.py:414](</D:/Inteligencia Artificial/Mia-Super Agent/mia/execution/banco04_validar_jueces.py:414>) construye el contador con `versiones=()` y custodia opcional; no asegura sumar las dos versiones del Bloque 7 ni sus salidas custodiadas.
- `:464` agrega el consumo al informe, pero no condiciona `circuito_utilizable` a su certificabilidad.
- **Pendiente lateral: NO cumplido integralmente.** Los topes nominales son 2 M y cero, pero [run_banco04.py:935](</D:/Inteligencia Artificial/Mia-Super Agent/mia/execution/run_banco04.py:935>) decide R solo con Claude; `:1271` omite la proyección Codex de las aprobaciones. La piloto también entra con estimación cero (`:922`). Reproduje **una llamada y un token Codex consumido en Bloque 0 antes de suspender**.

**Cambio:** detener ante consumo sin cota, vincular obligatoriamente todo el circuito al mismo contador y aplicar proyección/reserva Codex también a piloto, decisión de R y aprobaciones.

**I8 — PARCIAL.** El resultado exitoso reservado se cifra antes de persistir en [run_banco04.py:689](</D:/Inteligencia Artificial/Mia-Super Agent/mia/execution/run_banco04.py:689>) y `:869`; lo cubre **`f-7`**, con autenticación por identidad en **`f-7b`**.

Pero `:847` incorpora el texto íntegro de la excepción y `:858` lo escribe en JSON claro. Reproduje una excepción sintética con un hecho reservado: apareció en el intento y en el registro terminal. Las aprobaciones repiten ese patrón en `:1212`.

**Cambio:** cifrar también los detalles de error reservados y persistir fuera del cifrado únicamente códigos y metadatos permitidos. Añadir un check negativo con una excepción que reproduzca contenido del caso.

**I10 — PARCIAL.** El SHA real y el manifiesto mejoran la reanudación en [run_banco04.py:616](</D:/Inteligencia Artificial/Mia-Super Agent/mia/execution/run_banco04.py:616>), `:658` y `:805`; cobertura: **`i-17`–`i-23`**.

La comprobación recorre únicamente `rep-??.json`. No cubre intentos parciales ni aprobaciones: [run_banco04.py:1150](</D:/Inteligencia Artificial/Mia-Super Agent/mia/execution/run_banco04.py:1150>) devuelve directamente una aprobación terminal. La sonda reutilizó una con huella **ANTIGUA** bajo contexto nuevo.

**Cambio:** vincular y cotejar manifiesto en todos los registros reutilizables, incluidos intentos, aprobaciones y decisiones de planificación.

**Objeciones nuevas sobre las correcciones:**

- **N1 — BLOQUEANTE. Telemetría parcial se convierte en consumo conocido.** [jueces.py:1333](</D:/Inteligencia Artificial/Mia-Super Agent/mia/backend/mia/eval/banco04/jueces.py:1333>) acepta cualquier componente entero de uso. Reproduje `{"cache_read_input_tokens": 0}` → **0 tokens conocidos**, aunque falten entrada y salida; `:1386` cierra el intento como conocido. **Cambio:** exigir los componentes necesarios, validar valores y conservar consumo desconocido cuando falten.
- **N2 — MAYOR. El nuevo permiso de árbol sucio no impide certificar.** [run_banco04.py:1486](</D:/Inteligencia Artificial/Mia-Super Agent/mia/execution/run_banco04.py:1486>) admite el ensayo, pero `:962` no incorpora esa limitación al estado. La sonda devolvió **`terminado` con `arbol_limpio=False`**. **Cambio:** propagar obligatoriamente «no certificable» y distinguir las modificaciones locales en la identidad.

Verificación realizada: **9/9 checks P9/P10**, extraídos por AST, y sondas adicionales exclusivamente en memoria. No ejecuté las suites completas, proveedores ni bases; no modifiqué archivos ni leí contenido prohibido.

