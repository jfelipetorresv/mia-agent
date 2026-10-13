**Veredicto: NO APTO.** El contrato corrige conceptualmente la confianza en conclusiones del llamador, pero conserva brechas de R3, deja cálculos sin recorrido definido y modifica reglas del protocolo congelado.

Revisión estática sobre HEAD `c827f57`, contrastada en dos contextos independientes. Referencias: **C** = [banco04-cadena-contrato.md](</D:/Inteligencia Artificial/Mia-Super Agent/mia/docs/banco04-cadena-contrato.md>); **P** = [banco-calidad-04-protocolo.md](</D:/Inteligencia Artificial/Mia-Super Agent/mia/docs/banco-calidad-04-protocolo.md>).

1. **K1 — BLOQUEANTE. Faltan productores de métricas comparativas.**  
   `C:425,777` promete recalcular todas, pero no define cómo obtener `falsos_bloqueos` y `cambio_de_motor`, entradas de [metricas.py:365](</D:/Inteligencia Artificial/Mia-Super Agent/mia/backend/mia/eval/banco04/metricas.py:365>). `harness.py:743` entrega `false_block` ya derivado; aceptarlo contradice IC-2 (`C:34`). `model_fallbacks` sí tiene productor (`harness.py:733`), pero falta su transformación contractual.  
   **Cambio:** especificar observaciones originales, función, conexión desde `main` y tratamiento de ausencia para cada métrica. Para `negativa_correcta`, Q8 identifica productor, pero todavía necesita semántica y validación, no únicamente un booleano nuevo.

2. **K2 — BLOQUEANTE. Q4 cambia la medición de fuga y deja desconectada su adjudicación.**  
   `C:408` conserva señal **o** fuga confirmada; `C:938-942` subordina la señal al juicio. `P:479-482,1351-1355` exige la señal vendorizada con negación vinculada a la cita. Además, la nueva adjudicación señal↔juez no tiene recorrido, esquema ni votos definidos en `C:88,176,219-225,379-385`. R3-C-N2 queda desplazada, no cerrada.  
   **Cambio:** conservar y corregir la regla congelada, o adoptar expresamente **v1.4**. Si se adopta Q4, definir productor, evidencia, reproducción y bloqueo por adjudicación pendiente.

3. **K3 — BLOQUEANTE. Sigue abierta la reutilización del reservado.**  
   `C:831-833` no corrige la raíz sustituible denunciada en R3-C:39-42. [banco04_validar_jueces.py:431](</D:/Inteligencia Artificial/Mia-Super Agent/mia/execution/banco04_validar_jueces.py:431>) sigue resolviéndola desde el entorno. Q12 (`C:960-962`) deduce «no usado» de «registro inexistente», inferencia insuficiente precisamente ante esa vulnerabilidad.  
   **Cambio:** vincular la raíz al perfil real de Windows independientemente del entorno sustituible, probar la reubicación conjunta y acreditar el historial. Un hash nuevo del evaluador no vuelve reservado material previamente expuesto.

4. **K4 — BLOQUEANTE. La telemetría cruda de Codex juez no tiene productor suficiente.**  
   `C:497` exige distinguir varios eventos `usage`, pero conserva los runners (`C:801`). [jueces.py:1689](</D:/Inteligencia Artificial/Mia-Super Agent/mia/backend/mia/eval/banco04/jueces.py:1689>) recibe de `_parse_events` valores colapsados; ese parser sobrescribe componentes (`codex_cli_adapter.py:318-328`). Los cambios de `C:528-541` no reparan ese camino del juez. Q9 permite además interpretar ausencia como cero mediante una acreditación sin registro ni enlace definidos.  
   **Cambio:** persistir todos los eventos del juez y definir un registro versionado de acreditación, ligado a comando, versión y evidencia, que la puerta valide. Añadir pruebas de múltiples eventos y acreditación ausente.

5. **K5 — MAYOR. Persiste el cero de la piloto Codex.**  
   `C:818-819` conserva expresamente vacía su estimación previa. [run_banco04.py:1095](</D:/Inteligencia Artificial/Mia-Super Agent/mia/execution/run_banco04.py:1095>) la convierte en cero. Recalcular R11 después de la piloto no protege su admisión inicial; el esqueleto tampoco ejerce Codex de producción (`C:623-626`).  
   **Cambio:** fijar productor y estimación previa acreditada; bloquear su ausencia cuando Codex pueda ejecutarse. Probarlo desde el montaje real del Bloque 7. R3-B-I5 permanece abierta.

6. **K6 — MAYOR. Q1 y Q3 cambian reglas, aunque el contrato diga que no.**  
   Q1 (`C:930-933`) elimina la no certificabilidad del fallo sin texto, frente a `P:289-292`; §9.5 obliga a contar el fallo, pero no revoca expresamente aquella condición. Q3 (`C:936-937`) añade el turno reproducido de aprobación al consumo decisorio, frente a **R turnos más aprobación** de `P:453-455,587`.  
   **Cambio:** resolver explícitamente ambos conflictos. Mantener el replay adicional en el presupuesto del circuito, o revisar la fórmula bajo **v1.4**. La excepción de Q1 también requiere nueva versión si permite certificar donde §4.1 lo prohibía.

7. **K7 — MAYOR. Reanudación contradictoria e incompleta.**  
   R6 registra `alcance_etapas` (`C:240`), pero `C:599-605` acepta la unión de autorizaciones sin filtrar ese alcance. Además, `C:609-610` invalida cualquier consumo desconocido para siempre, contradiciendo las cotas admitidas en `C:196-197,433-434` y `P:464-468,1297-1300`.  
   **Cambio:** comprobar etapa, versión, evento y suspensión; distinguir desconocido **sin cota** de desconocido con cota acreditada. Definir también la reanudación de validación: `C:576-577` solo ofrece comandos de producción y juicio. Una autorización debe permitir continuar, nunca acreditar consumo.

8. **K8 — MAYOR. Comparabilidad registrada, pero no exigida.**  
   `C:127-134,182` guarda SHA, CLI y modelo, pero las comprobaciones de `C:329-355,389-399` no ejecutan la obligación de reproducir la base cuando cambia CLI/modelo (`P:1023-1030`). Además, los cambios de producto de `C:540-542` exceden el parche de base limitado a `eval/` y `execution/`.  
   **Cambio:** incorporar una condición explícita de comparabilidad y revisar el perímetro autorizado del parche. Las pruebas aditivas propuestas son pertinentes; todavía no demuestran invariancia del comportamiento del abogado.

9. **K9 — MAYOR. Extensión y submuestras no tienen selección completamente determinada.**  
   `C:470-471,861-862` limita a cinco la unión de casos de varias métricas sin fijar cómo combinar contribuciones ni desempatar. `C:453-454` selecciona estabilidad y segunda pasada sobre los candidatos de la versión: al añadir extensión puede cambiar la selección y convertir una pasada anterior válida en una «sobrante» prohibida.  
   **Cambio:** fijar orden total reproducible y población de selección; preservar explícitamente las submuestras originales y definir las adicionales.

10. **K10 — MAYOR. Varias mutaciones no alcanzan la condición pretendida.**  
    M06/M07 (`C:732-733`) alteran R2 y exigen `reprueba` por C8, pero conservan R5, cuyo `rep_sha256` y paquete quedan incoherentes (`C:212-214,347-348`). Correspondería `no_certificable` por identidad. La caída global no demuestra que C8 funcione.  
    **Cambio:** separar manipulación incoherente de mutación semántica: producir el material alterado, rejuzgar desde `main` y exigir el cambio concreto de condición con hashes coherentes. Añadir recorrido positivo completo de extensión y Codex de producción; F17 puede pasar usando un mundo que emite telemetría artificialmente (`C:664-671`).

11. **K11 — MAYOR. Q11 no tiene entrada ejecutable definida.**  
    `C:958-959` dispone una línea base con un directorio, pero `C:308-310` exige dos y `C:89` solo ofrece `previa/veredicto`.  
    **Cambio:** definir comando, firma, productor y esquema del informe del Bloque 0; separar sus métricas y presupuesto del techo comparativo, que necesita ambas versiones.

12. **K12 — MENOR. Predicado de limpieza invertido.**  
    `C:332` exige `arbol_limpio` y `dobles` falsos, mientras `C:391` rechaza árbol sucio.  
    **Cambio:** exigir `arbol_limpio=true` y `dobles=false`.

Sí quedan abordadas de raíz, **como diseño**, las conclusiones externas, los decisivos vacíos y la atribución aritmética fabricada: reproducción, claves y R4 sustituyen esas entradas. Kappa y estabilidad tienen productores previstos. Q8 puede desarrollar el esquema bajo C14 sin cambiar por sí misma la métrica; Q13 recoge una decisión expresamente pendiente.

El panel del abogado seguirá mostrando cero ante consumo ausente (`C:544`): es un límite declarado del producto. No modifiqué archivos ni accedí a datos prohibidos; no ejecuté proveedores, bases ni pruebas.