**Veredicto: NO APTO.** K5, K13, K15 y K16 quedan resueltas como diseño. K7 permanece parcial: el cerrojo ordena el registro del envío, pero todavía permite la intercalación cuestionada antes de la invocación real.

Revisión estática de HEAD `315a127`, del diff contra `56e25d0` y del dictamen anterior. Las referencias corresponden al [contrato v4](</D:/Inteligencia Artificial/Mia-Super Agent/mia/docs/banco04-cadena-contrato.md>). «RESUELTA» acredita la especificación, no su implementación.

| Objeción | Estado | Evidencia |
|---|---|---|
| **K5** | **RESUELTA** | **R1:180–182; R13:464–472; R14:512–514, 540–550.** El manifiesto de medición está expresamente exento de R13. La dependencia queda unidireccional: manifiesto de medición → llamadas y recibos → R13 → manifiesto consumidor. Se exige probar tanto el arranque de la medición sin R13 como el rechazo del consumidor sin él. |
| **K7** | **PARCIAL** | **§4.2:954–968; §5.4:1184–1228, 1237–1250.** Mejora la serialización y fecha la detección de orfandad, pero subsisten la carrera de invocación y dos incompatibilidades nuevas, detalladas abajo. |
| **K13** | **RESUELTA** | **§4.4:1104–1115; E2E-17:1442–1444.** Se separan integridad de todas las instantáneas e igualdad exclusivamente entre R1/R8. R9 se interpreta con su propia referencia, que puede ser distinta. Desaparece la contradicción anterior. |
| **K15** | **RESUELTA** | **R4:264–273; §4.2:971–979; §5.4:1202–1209; E2E-15:1425–1436.** Las llamadas no enviadas quedan expresamente fuera del requisito de autorización. La clasificación de huérfanas es única y las otras secciones remiten a ella. Una denegación correcta ya no constituye infracción. |
| **K16** | **RESUELTA** | **R1:182; R13:476–500; R14:517–550; §3.9:903–904; §3.3 E:724.** Selección y `k` quedan preregistrados. La puerta abre todas las R4 y todos los recibos, exige igualdad con la selección y las referencias, y suma todos los intentos de cada corrida. El cero exige corridas completas. La prueba obligatoria rechaza citar solo 10 y exige **1.263** para 10 + 1.000. Las filas de medición cuentan en el presupuesto del circuito. |

**Pendientes de K7 y regresiones del texto nuevo:**

1. **El registro no serializa la invocación real.** En **§4.2:964–968**, B escribe `seq_envio` y libera el cerrojo antes de `_original_invoke`. Sigue siendo posible: **B registra → libera → el sistema pausa B → A cierra sin cota → B invoca**. La prohibición de tomar decisiones o leer estado entre esos pasos no impide que otro proceso avance. E2E-13, **§5.4:1237–1241**, solo comprueba el orden entre marcas y acepta esa ejecución, aunque **§5.1:1142–1150** exige detener antes de invocar. **Corrección:** serializar el inicio efectivo y exigir una prueba con barrera entre registro e invocación. Tratar la marca como compromiso irrevocable sería una garantía distinta, que debe aceptarse expresamente.

2. **La huérfana enviada incumple obligatoriamente la nueva desigualdad.** **R4:224, 266–271** permite que permanezca `en_curso`, con `seq_cierre=null`. Pero **§5.4:1228** exige `seq_inicio < seq_envio < seq_cierre` para **cada** fila enviada. El caso de orfandad tardía de **§5.4:1246–1250** termina marcado como `seq_incoherente`. **Corrección:** distinguir filas cerradas y huérfanas; para estas últimas comprobar `seq_inicio < seq_envio < seq_deteccion`, conservando el cierre nulo.

3. **La puerta no tiene autorización para leer la nueva evidencia de orfandad.** **§5.4:1190–1196** introduce `orfandades/<seq_deteccion>.json`, necesario para reconstruir U(C). El inventario cerrado de **§3.9:897–916** no lo incorpora ni lo adscribe a R1–R13. Leerlo produce `entrada_no_permitida`; omitirlo impide comprobar la detección. **Corrección:** incorporarlo expresamente con identidad, ruta y huella.

Mantengo las demás objeciones previamente resueltas. No añado IDs nuevos: estos defectos pertenecen a K7. El contraste independiente coincidió con los hallazgos, cotejados contra el texto original.

No modifiqué archivos ni accedí a los recursos prohibidos. No ejecuté proveedores, bases ni pruebas.

