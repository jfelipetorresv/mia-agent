**Veredicto: APTO.**

Revisión estática de `banco04-cadena/v5`, HEAD `6c26afc`, y del diff contra `315a127`, limitada a K7 y sus posibles regresiones.

**(a) Los tres puntos de K7 quedan RESUELTOS como contrato.**

1. **Compromiso frente a invocación.** La garantía expresamente adoptada fija `seq_envio` bajo el cerrojo como punto irrevocable. Declara que B puede invocar después del cierre de A si se comprometió antes, contabilizando su consumo. §5.1 ahora exige detener los compromisos nuevos. E2E-13 incorpora la barrera entre compromiso e invocación y exige rechazar el compromiso posterior no autorizado. Desaparece la contradicción señalada en ronda 4. [§4.2, líneas 972–1003](</D:/Inteligencia Artificial/Mia-Super Agent/mia/docs/banco04-cadena-contrato.md:972>); [E2E-13, líneas 1291–1307](</D:/Inteligencia Artificial/Mia-Super Agent/mia/docs/banco04-cadena-contrato.md:1291>).

2. **Huérfana enviada.** La comprobación distingue las filas cerradas de las huérfanas: estas conservan `seq_cierre == null` y exigen `seq_inicio < seq_envio < seq_deteccion`. La prueba de orfandad tardía exige expresamente que ese caso no produzca `seq_incoherente`. [§5.4, líneas 1269–1282 y 1309–1316](</D:/Inteligencia Artificial/Mia-Super Agent/mia/docs/banco04-cadena-contrato.md:1269>).

3. **Lectura de orfandades.** El inventario cerrado las incorpora como complemento de R4, con ruta, identidad y SHA-256; exige correspondencia con una fila existente y prohíbe duplicados por fila. [§3.9, líneas 925–934](</D:/Inteligencia Artificial/Mia-Super Agent/mia/docs/banco04-cadena-contrato.md:925>).

**(b) No identifico regresiones ni contradicciones del diff que alteren lo anteriormente resuelto.** La garantía cambia expresamente el momento hasta el que puede detenerse una llamada; no elimina su contabilización ni los controles de autorización.

**(c) La garantía no abre una vía contractual para aprobar o certificar sin acreditar.** Admitir B por su compromiso previo solo valida su orden. La reanudación nunca acredita consumo, y cualquier evento sin cota mantiene **el techo y el veredicto global** en `no_certificable`, estado que prevalece sobre `aprueba`. [Líneas 1205–1207](</D:/Inteligencia Artificial/Mia-Super Agent/mia/docs/banco04-cadena-contrato.md:1205>), [1331–1333](</D:/Inteligencia Artificial/Mia-Super Agent/mia/docs/banco04-cadena-contrato.md:1331>) y [585](</D:/Inteligencia Artificial/Mia-Super Agent/mia/docs/banco04-cadena-contrato.md:585>).

El contraste independiente coincidió. Este APTO acredita la especificación revisada; no acredita implementación ni pruebas ejecutadas. No modifiqué archivos ni accedí a los recursos prohibidos; no ejecuté proveedores ni bases.