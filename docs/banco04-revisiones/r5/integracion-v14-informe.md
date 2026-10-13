# Integración v1.4 en docs/banco-calidad-04-protocolo.md

Solo se tocó ese archivo (CRLF conservado). VERSION_PROTOCOLO y todo lo demás, intactos. Sin git add/commit.

## Cambio -> estado (líneas en el protocolo resultante)

| Cambio | Estado | Línea |
|---|---|---|
| 4.1 cabecera: versión v1.4 y fecha 2026-10-12 | aplicado | 3 |
| 4.1 frase de motivo (remite a §12.7) | aplicado | 6-8 |
| 4.2 «una CALIDAD incompleta nunca se certifica» | aplicado | 291 |
| 4.2 «Se miden acumulados…» (cota / estimación inicial congelada) | aplicado | 261 |
| 4.2 piloto («repetición 1…») | aplicado | 271 |
| 4.2 suspensión «incompleto — no certificable» | aplicado | 288 |
| 4.3 «El techo de §6 se evalúa con esa cota superior…» (+ bullets de intento sin cota, estimación congelada) | **NO aplicado**: Actual 0 coincidencias | 481-482 (línea más parecida; difiere la sangría: el protocolo trae 4 espacios de continuación y la cita de la propuesta ninguno) |
| 4.3 consumo_agregado_caso como intervalo | aplicado | 466 |
| 4.3 Segundo proveedor (Codex) | aplicado | 483 |
| 4.4 final del primer párrafo de §6.3 | aplicado | 597 |
| 4.4 bloque «Veredicto de cuota, por intervalo» tras «Una subida…» | aplicado | 616 |
| 4.5 §6.4 Veredictos de calidad y de cuota | aplicado | 644 |
| 4.6 §9.7 dos viñetas añadidas | aplicado | 1103 |
| 4.7 C15 revisada | aplicado | 1329 |
| 4.8 C18 frase central | **NO aplicado**: Actual 0 coincidencias | 1371-1372 (en el protocolo la frase empieza a mitad de línea tras «…sin cambiar el producto.»; la cita de la propuesta la pone al inicio de línea) |
| 4.8 «Se añade al final de C18» (Acotar y medir revocada) | aplicado | 1379 |
| 4.9 C19 revisada | aplicado | 1383 |
| 4.11 §4.1 «bloquea la certificación de calidad» | aplicado | 304 |
| 4.12 §8.8 rotulación | aplicado | 990 |
| 4.13 §10.2.10 | aplicado | 1157 |
| 4.14 P9 | aplicado | 1178 |
| 4.14 P10 y P11 | aplicado | 1192, 1196 |
| 4.15 nota a P10 de §12.1 | aplicado (al final de la celda de descripción, antes de la columna de secciones, para no romper la tabla) | 1254 |
| 4.16 C24 | aplicado | 1436 |
| 4.17 final de C19 (habilitación jueces) | aplicado | 1392 |
| 4.10 §12.7 nueva (con C27) | aplicado, al final del archivo | 1457 |

Las aclaraciones «Aplicación por intervalo» ya vienen dentro de los textos Nuevo (§6.3, C15, C18, C19, P10, §12.7) y entraron con ellos, salvo las que dependen de los dos cambios no aplicados.

## Barrido («no certificable», «no_certificable», «techo», «certific»)

Apariciones que TODAVIA hacen no certificable el techo por un intento sin cota (no corregidas; son consecuencia directa de los dos cambios no aplicados):
- 481-482 (§5.5): «Si un intento fallido no permite calcularla, el techo queda no certificable y 0.4 no aprueba esa fila.»
- 1371-1372 (C18): «…sin cota, y el techo de §3.4 y §6.3 queda no certificable.»

Históricas, no tocadas por la propuesta (registro de ronda 1, §12.1):
- 1254 (P10): «sin cota el techo no es certificable» (lleva ya la nota v1.4 añadida).
- 1255 (P11): «prohibición de certificar resultados incompletos» (histórico; coherente con calidad).

Ninguna aparición declara la cuota «estimada» sin pasar por el intervalo; las demás (54, 231-233, 264, 266, 280-285, 574, 591-642, 652-657, 685, 885, 939, 986, 995-1000, 1101-1107, 1131, 1147, 1215-1219, 1253, 1267, 1282, 1287, 1330-1332, 1353, 1365, 1388-1393, 1404, 1436, 1466-1478) son cifras, calidad de jueces o ya revisadas.

## diff --stat
 docs/banco-calidad-04-protocolo.md | 208 ++++++++++++++++++++++++++++++-------
 1 file changed, 170 insertions(+), 38 deletions(-)
