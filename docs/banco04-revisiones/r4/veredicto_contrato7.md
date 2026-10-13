**Veredicto: NO APTO.** La separación decidida por Pipe es coherente, pero v7 y la propuesta v1.4 aún permiten una certificación de cuota injustificada y conservan contradicciones operativas. HEAD confirmado: `b89e4e8`.

**(a) CALIDAD: no encontré una vía nueva para aprobar ocultando una salida mala o una muestra incompleta.** Permanecen las exigencias de inventario, repeticiones, texto completo —también ante `fallo_producto`—, conciliación de llamadas y juicio completo. Un consumo desconocido puede coexistir con evidencia suficiente de calidad; una salida faltante sigue bloqueándola. [Contrato:708–713](</D:/Inteligencia Artificial/Mia-Super Agent/mia/docs/banco04-cadena-contrato.md:708>).

Sin embargo, persisten dos caminos que **invalidan CALIDAD por consumo**, contrariando la separación:

- La piloto todavía da `no_certificable` ante cualquier fila desconocida sin cota. Debe precisarse cómo se recalcula R con estimaciones, conservando la selección reproducible y todas las repeticiones exigidas. [Contrato:714](</D:/Inteligencia Artificial/Mia-Super Agent/mia/docs/banco04-cadena-contrato.md:714>).
- La estimación guardada usa el máximo observado del bloque, pero después se recalcula y exige igualdad. Si el máximo aumenta de 100 a 200 en una llamada posterior, aparece `telemetria_contradictoria` sin manipulación. Hay que fijar el conjunto de observaciones utilizado —por ejemplo, mediante un corte de secuencia— o distinguir estimación inicial y actualización final. [Contrato:1284–1291](</D:/Inteligencia Artificial/Mia-Super Agent/mia/docs/banco04-cadena-contrato.md:1284>).

**(b) CUOTA: el aviso de «estimada» es claro; la certificación no está completamente justificada.** La regla «conocido ya excede» es correcta cuando compara el mínimo del numerador contra el máximo del denominador. El problema es el caso 3: **no tener intentos sin cota no convierte las cotas finitas en consumos exactos**. [Propuesta:149–165](</D:/Inteligencia Artificial/Mia-Super Agent/mia/docs/banco-calidad-04-protocolo-v1.4-propuesta.md:149>), [contrato:773](</D:/Inteligencia Artificial/Mia-Super Agent/mia/docs/banco04-cadena-contrato.md:773>).

Contraejemplo: nueva = 100 conocidos; base = 10 conocidos + intento con cota 90, cuyo consumo real fue 1. Comparar 100/100 permite «certificada · cumple»; el cociente real es 100/11 y excede 1,25. Inversamente, una cota sobredimensionada del numerador puede producir un falso «excede».

**Corrección necesaria:** certificar cumplimiento únicamente cuando el máximo posible del cociente cumple; certificar exceso cuando su mínimo excede. Debe definirse qué estado corresponde al intervalo que cruza el umbral, incluso con cotas finitas. La ausencia de intentos sin cota no basta. Este punto impide aprobar el contrato.

**(c) Envoltorio: resuelto contractualmente, pendiente de prueba ejecutada.** La v7 exige devolver exactamente el entorno saneado original, sin añadir, quitar ni modificar variables, y probar valores de reintentos 0, 15 y ausente. Eso elimina la normalización objetada en v6. No acredita todavía comportamiento implementado. [Contrato:1112](</D:/Inteligencia Artificial/Mia-Super Agent/mia/docs/banco04-cadena-contrato.md:1112>), [prueba exigida:1144](</D:/Inteligencia Artificial/Mia-Super Agent/mia/docs/banco04-cadena-contrato.md:1144>).

**(d) La propuesta v1.4 no es completa.** Además de lo anterior, deja textos operativos incompatibles:

- El gate P10 aún exige que un intento sin cota vuelva el techo «no certificable». [Protocolo:1126](</D:/Inteligencia Artificial/Mia-Super Agent/mia/docs/banco-calidad-04-protocolo.md:1126>).
- §8.8 prohíbe publicar cualquier número como «certificado»; debe delimitarse a CALIDAD y distinguir expresamente CUOTA. [Protocolo:937–942](</D:/Inteligencia Artificial/Mia-Super Agent/mia/docs/banco-calidad-04-protocolo.md:937>).
- S08 y S10 siguen esperando `reprueba` por exceso o atribución de cuota. Deben exigir el resultado separado de CUOTA y conservar CALIDAD. [Contrato:1775–1777](</D:/Inteligencia Artificial/Mia-Super Agent/mia/docs/banco04-cadena-contrato.md:1775>).

**(e) Sí procede retirar `consumo_certificable` de la habilitación de VJ**, exclusivamente ese predicado. Deben conservarse el contador compartido, la suspensión/reanudación C27, cero salidas sin evaluar, cero discordancias y la acreditación del reservado. Esos controles mantienen la evidencia necesaria para habilitar el circuito. Conviene hacerlo explícito en §8.6. [VJ:321–332](</D:/Inteligencia Artificial/Mia-Super Agent/mia/execution/banco04_validar_jueces.py:321>), [VJ:365–374](</D:/Inteligencia Artificial/Mia-Super Agent/mia/execution/banco04_validar_jueces.py:365>).

Revisión documental, con contraste independiente de CALIDAD/VJ y cotejo de sus fuentes. Sin modificaciones, acceso a recursos excluidos ni ejecución de proveedores, bases o pruebas.

