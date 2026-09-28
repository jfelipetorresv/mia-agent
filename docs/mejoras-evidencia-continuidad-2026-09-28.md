# Evidencia, revisión incremental y continuidad de Mia

Encargo autorizado el 28 de septiembre de 2026. Dirección y revisión: Astra, esfuerzo medio. Implementación: Sol, esfuerzo medio. Base `9834c6b`; rama `codex/mia-evidencia-continuidad-20260928`.

## Alcance

Adaptar mecanismos de verificación del Harness al producto multidespacho. No trasladar identidad, criterios jurídicos ni fuentes privadas de Lexia. El Harness permanece en lectura. No añadir proveedores, cambiar políticas de modelos ni usar expedientes reales para probar.

## Matriz de aceptación

| Mejora | Conducta exigida | Prueba negativa |
|---|---|---|
| Evidencia original | El auditor independiente recibe texto de fuentes identificadas, localizadores y cobertura completa en ambas vías de revisión. | Fuente ausente, material excedido o cita posterior al antiguo recorte no obtiene cobertura completa ficticia. |
| Cobertura visible | Distingue fuente cotejada, defectuosa y no comprobable, incluso cuando no hay defectos adicionales. | Una fuente identificada sin contenido conserva aviso y cobertura pendiente. |
| Vigencia de aprobación | Texto, ejecución, fuentes, jurisdicción y versión de revisión corresponden; exportación comprueba fuentes locales vigentes. | Recibos mezclados, fuente usada cambiada/borrada, contexto ilegible o final legado no acreditable no habilitan final. |
| Corrección incremental | Reutiliza únicamente unidades auditadas con dependencias explícitas y vigentes; revisa cambios y dependientes. | Cambio global, dependencias incompletas o impacto no acreditable exige revisión completa o resultado inconcluso. |
| Recuperación de chat | Al reabrir consulta el envío por identidad autenticada y recupera respuesta registrada sin nueva inferencia. | Otro usuario/despacho no recupera el envío; estados inciertos no vencen ni se reenvían automáticamente. |

## Decisiones de implementación

- Reutilizar el registro de artefactos, recibos y solicitudes existente. Los nuevos módulos separan contratos puros; no se crea un segundo sistema de aprobación.
- La cobertura del auditor es estructurada. La ausencia de una dependencia no demuestra independencia; los casos ambiguos se revisan completos. El texto editado por el abogado se conserva literalmente.
- La procedencia conserva identidad del origen, huella del original y huella del pasaje presentado. Eliminar solapes no equivale a modificar la fuente original.
- El navegador conserva únicamente identificadores del envío y la conversación, separados por usuario y despacho. Los mensajes y respuestas permanecen en el almacenamiento autenticado existente.
- Las fuentes locales vigentes no acreditan por sí solas vigencia normativa externa. No se promete ahorro monetario ni de tokens sin medición.

## Validación y entrega

Pruebas conductuales positivas y negativas, mutaciones focales, aislamiento entre despachos, revisión independiente del diff integrado y recorrido visible del chat. Pruebas de base de datos en entorno sintético aislado. No conectar pruebas a la base instalada ni invocar modelos externos.

Las pruebas de desarrollo, la revisión de código y la aplicación instalada se informan separadamente. Implementación, comprobaciones focales y revisiones cerradas; Opus emitió APTO estático en la tercera pasada. El empaquetado queda pendiente en el checkpoint solicitado. Las secciones siguientes conservan la evolución y los fallos históricos.

## Evidencia parcial

- El director ejecutó `execution/test_rls.py` en un clúster nuevo y aislado, puerto 55448: 19/19 comprobaciones aprobadas, salida 0. No se usó la base instalada.
- La revisión independiente cerró los hallazgos de fuentes y unidades: impacto global perdido, aprobación textual ambigua y selección incompleta de citas y anclas. Dictamen Astra: APTO para ese frente; no acredita calidad jurídica de un modelo real.
- El registro y la exportación tienen pruebas positivas y negativas en la base sintética. La revisión independiente confirmó las correcciones de una huella recalculada sobre un fragmento ya recortado y un contexto no definido en el paso de aprobación. Dictamen Astra: APTO para el código del registro, condicionado a completar la integración HITL.
- Pipe pidió además revisión independiente con Claude Code, Opus 5.5 en esfuerzo alto. Está en ejecución, con acceso de lectura al código y sin permisos de edición.
- El arranque del navegador encontró un binario SWC incompleto en `node_modules`. Se restauró exclusivamente ese archivo desde el paquete de la misma versión 16.3.0, cotejado contra SHA-512 del lockfile. No cambiaron las dependencias declaradas ni el lockfile por esta reparación local.
- Chat: revisor Astra ejecutó `e2e/chat-recovery.mjs` en Chromium y aprobó 12/12 escenarios con APIs sintéticas. Se probaron pérdida de conexión y recarga con un solo POST, recarga durante animación, incertidumbre sin reenvío, aislamiento de usuario, dos ventanas, marcador dañado, almacenamiento no disponible y respuesta recuperada cuando falla el historial. El director cotejó el JSON de resultados e inspeccionó capturas de recuperación y envío pendiente. No hubo errores JavaScript; los errores de red fueron los inyectados por las pruebas.
- Una prueba adicional invalidó el cierre de aislamiento del chat: cambiar de cuenta en otra ventana permitía enviar el texto de la sesión anterior con el token nuevo. Reproducción roja: `MIA_RECOVERY_AUTH_SWITCH_ONLY=1`. Se requiere vincular identidad y envío al mismo token, invalidar el estado al cambiar de sesión y reverificar antes de entregar.

## Revisión externa y decisiones

Claude Code terminó con modelo confirmado `claude-opus-5-5` y esfuerzo `high`.
Dictamen inicial: **NO APTO**, por lectura de código; no ejecutó pruebas. Informe
íntegro local: `output/validation/claude-opus55-review.md`.

| Hallazgo | Decisión del director |
|---|---|
| Investigación derivada ajena bloquea originales utilizables | Confirmado en casos concretos por sonda independiente de Astra. No está demostrada la frecuencia general afirmada por Opus. Corregir selección y exigir al auditor declarar dependencias y exclusiones; mantener bloqueo de fuentes necesarias sin original y de contextos vacíos. |
| Pruebas antiguas omiten cobertura/versión del revisor | Actualizar fixtures al contrato vigente sin rebajar el gate; conservar evidencia de la corrida roja y las correcciones focales. |
| JSON válido envuelto en Markdown es rechazado | Admitir únicamente una envoltura completa de JSON, conservando validación estricta y rechazo de texto adicional. |
| Resumen de norma comparado como cita literal | Usar pasaje del original y conservar el resumen como información derivada separada. |
| Rechazo anterior a ejecutar deja pendiente falso | Retirar marcador y recuperar input solo ante respuestas del protocolo que acreditan que no se inició ejecución; conservarlo ante incertidumbre. |
| Ancla documental fuera de rango | Registrar original faltante explícito; no sustituirlo por todos los documentos disponibles. |
| Límite de pasadas pierde motivo | Conservar el motivo específico del presupuesto. |
| Pruebas sin normas reales del recolector o resolución por email | Añadir estos recorridos sintéticos; no sustituir el mecanismo que se prueba. |
| Fixture puede caer a configuración local | Exigir entorno aislado explícito o configuración del servicio efímero de CI; no leer `.env` del repositorio como respaldo. |

Estas decisiones están en implementación y requieren reverificación; el dictamen inicial
no equivale a aprobación de las correcciones.

## Segundo dictamen de Opus

Modelo confirmado nuevamente `claude-opus-5-5`, esfuerzo `high`, solo lectura.
Informe: `output/validation/claude-opus55-recheck.md`. Cerró los hallazgos iniciales,
pero emitió **NO APTO** por tres omisiones adicionales confirmadas por Astra:
el índice documental de un sello pertenece al turno anterior; la selección final
no puede omitir referencias explícitas por una declaración incompleta del auditor;
las fuentes derivadas deben seguir ante el auditor aunque otra cita sea inequívoca.

Correcciones ordenadas: resolver sello por identidad/huella o revisar todos ante
ambigüedad; unir dependencias explícitas comprobadas con las semánticas; conservar
inventario derivado y exigir motivo de exclusión. No convertir todos los documentos
ambiguos en dependencias obligatorias ni bloquear automáticamente derivados ajenos.
También se corrigen pérdida de avisos, recuperación tras invalidación de selección,
manifestación de huella de origen, rechazo local previo al envío, datos SAT de los
fixtures y precheck del entorno de pruebas. Se requieren regresiones focales y
dictamen nuevo; las pruebas aprobadas anteriormente no cierran estos hallazgos.

## Cierre de comprobaciones focales

Las correcciones anteriores están implementadas. Sol registró los resultados en
`output/validation/sol-final-validation.json`: fuentes 15, unidades 6, contexto 4,
HITL 4, contenido 30, integración 56 y chat backend 9, todos aprobados; TypeScript
y lint focal terminaron con salida 0. La corrida rápida inicial conserva sus
38 suites aprobadas, cuatro fallos y dos tiempos agotados; cada fallo o tiempo
agotado tiene reparación o repetición focal documentada. No se reescribe ese rojo
histórico como si hubiera sido una corrida completamente verde.

La prueba integrada usa PostgreSQL real con datos sintéticos y recorre revisión,
edición humana, aprobación, final y exportación DOCX. Cambiar una fuente o su
identidad impide presentar el final anterior como vigente. Los proveedores están
sustituidos: esto no acredita calidad jurídica de modelos reales. La prueba MCP
aprobó 40 comprobaciones; su conexión a un gateway real quedó omitida por ausencia.

Astra verificó en contexto independiente fuentes, dependencias, registro y
selección auditada. La selección se copia profundamente y su huella invalida
cambios de contenido, identidad, localizador u origen; una huella de texto sola
no bastaba. Las exclusiones de investigación derivada exigen motivo del auditor,
y los recibos conservados participan en la unión de dependencias. Un contexto
vacío o una fuente necesaria sin original sigue sin habilitar el final.

La revisión visible final del chat aprobó 21 escenarios únicos, con Chromium y
Edge y APIs sintéticas. Incluye tres cambios de sesión, respuestas 401/402/422
frente a 409/502 y callbacks tardíos. El fallo de aislamiento inicial quedó
corregido y conserva evidencia roja. Resultados y huellas finales:
`output/playwright/chat-recovery-final-summary.json`. No se probó una instalación
nativa ni proveedores reales. El servidor de desarrollo propio quedó detenido.

El timeout final de integración se diagnosticó con traza en el constructor de
MuPDF; la repetición sin búfer aprobó 56/56 dentro del plazo original de 180 s.
No se atribuye el incidente a una causa ambiental no demostrada. El fixture MCP
que sobrescribía el entorno aislado fue corregido; no se acreditó acceso ni
escritura en una base instalada durante el intento anterior.

## Correcciones del segundo dictamen

Delta de código congelado. Sol aprobó fuentes 18/18, unidades 6/6, contexto real
4/4, tipos y lint focal. Evidencia: `output/validation/sol-delta-validation.json`.
La regresión reproduce la omisión de una norma explícita por el auditor: MIA
conserva la norma y el documento, niega el DOCX al cambiar `full_text`, lo habilita
al restaurar los bytes y vuelve a negarlo al cambiar la identidad de la norma.

Astra emitió **APTO para el delta core**, tras cinco pruebas puras y una sonda
propia de la unión determinista. Confirmó sellos reordenados, inventario derivado
con exclusión motivada y revisión nueva cuando la selección o procedencia cambian.
El precheck de `quick` usa el mismo helper que los fixtures y explica el entorno
aislado faltante antes de ejecutar suites. Conserva la aceptación específica de CI.

El rechazo local por cambio de token ahora ejecuta el callback que elimina solo
el marcador capturado. Su lectura independiente pasó; los dos escenarios nuevos
del navegador siguen pendientes de que el servidor de desarrollo sirva `/chat`.
Los 21 escenarios anteriores no se presentan como prueba de este último delta.

Pipe pidió checkpoint documentado al terminar el arreglo. El cierre de código y
revisiones se conservará en Git; el build completo 0.3.3 queda como siguiente paso
de entrega, no como artefacto ya producido ni instalación verificada.

## Dictamen final de Opus

Tercera pasada terminada, modelo confirmado `claude-opus-5-5`, esfuerzo `high`:
**APTO por revisión estática**. Cerró los ocho hallazgos del segundo informe y no
encontró regresiones bloqueantes. Informe conservado completo en
`output/validation/claude-opus55-final.md`. Su dictamen no acredita ejecución de
pruebas, migración 067, compilación ni navegador. Dejó pendiente la evidencia de
los dos casos prefetch; las pruebas sintéticas y revisión Astra se informan aparte.
Con candidatos a exclusión se vuelve a revisar el texto completo: no hay ahorro
incremental garantizado en ese caso. El driver `full` conserva su configuración
anterior y no debe confundirse con el precheck aislado añadido a `quick`.

## Checkpoint final

La reserva de navegador quedó cerrada: **23 escenarios únicos aprobados**, 12 en
Chromium y 11 focales en Edge. Los dos últimos comprueban cero POST/GET, eliminación
del marcador propio y conservación del renovado. Una inspección detectó un estado
«Mia está pensando…» residual; Sol añadió únicamente `setStatus("")` al invalidar
la identidad. Tipos y lint pasaron; Astra repitió los dos focales con aserción y
revisión visual de ambas capturas. El director inspeccionó la captura final propia.
Resumen y huellas: `output/playwright/chat-recovery-final-summary.json`.

El APTO estático de Opus precede a esa única línea visual, que tiene revisión
independiente posterior. Se conservan timeout de navegador y éxito funcional previo
a la limpieza visual. La compilación fría de `/chat` tardó 166 s según la traza;
no se demostró una causa interna más específica. No se cambiaron dependencias para
resolverla. La prueba final usó el servidor ya compilado y luego se cerró.

Todos los procesos propios concluyeron; Next/depurador 3111/9229 cerrados y clúster
sintético 55448 detenido. El entorno temporal se conserva para reproducción.
Código versionado para 0.3.3; **sin build ni instalación nuevos**, sin push. El
procedimiento de siguiente entrega y el entorno de pruebas están en `HANDOFF.md`.
El estado final de esta sección prevalece sobre los pendientes históricos anteriores.
