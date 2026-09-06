# Auditoría de Mia — 6 de septiembre de 2026

Actualización posterior: la versión 0.3.1 incorpora memoria durable del chat además
de idempotencia. Las menciones siguientes a resumen pendiente describen el primer
cierre; el comportamiento vigente está en `docs/chat-continuidad-idempotencia.md`
y la entrega e instalación se registran en el cierre más reciente de `HANDOFF.md`.

## Propósito y alcance comprobable

Mia debe permitir que un abogado abra un asunto, aporte documentos, converse sobre ellos,
revise un diagnóstico respaldado y apruebe una versión concreta. La metodología y la
jurisdicción pertenecen a cada despacho. Esta auditoría revisa implementación y recorridos
sintéticos; no certifica la calidad jurídica de respuestas de modelos reales ni ausencia
universal de errores.

Base de trabajo: `8a5ac10`, árbol inicialmente limpio. Los planes y cierres históricos se
cotejaron contra código vigente. La referencia del HANDOFF a un plan externo de julio ya
no existe en esta máquina; se usaron `CLAUDE.md`, `TRASPASO-MODELO.md`, arquitectura y código.

## Hallazgos reparados

1. La compresión aceptaba un resumen mayor o igual al historial. Ahora conserva el original,
   registra el intento improductivo y no emite una falsa señal de ahorro. Conserva intactos
   los mensajes protegidos y las advertencias `[VERIFICAR]`.
2. La actualización iterativa enviaba el checkpoint propio también como turno nuevo. Ahora
   lo incorpora una sola vez, sin excluir otros mensajes por su parecido con un resumen.
3. Aprobar con otra selección podía regenerar el borrador y volver a revisión, mientras el
   recibo decía `approved` y la pantalla mantenía el texto viejo. Ahora el recibo consulta
   el estado persistido y entrega texto, huella e informe nuevos; la pantalla renueva las
   constancias y conserva la selección aplicada. No habilita el documento final.
4. La revisión independiente encontró edición concurrente: el usuario podía escribir o
   cambiar notas mientras llegaba una nueva versión, perdiendo ese trabajo. Matriz, editor,
   comentarios y constancias quedan bloqueados durante la operación.
5. Ante contexto excesivo, el grafo reintentaba aunque la compresión devolviera el mismo
   prompt o uno mayor. Ahora conserva el error original sin repetir la llamada ni gastar
   el cupo de recuperación. En los tres negativos sintéticos las llamadas pasan de 2 a 1.
6. El adaptador Codex descartaba `cached_input_tokens`. Ahora lo traduce al contador de
   caché existente, sin sumarlo de nuevo a la entrada ni convertir cuota en precio medido.

Medición reproducible del fixture iterativo: 2.371 → 2.295 tokens estimados de entrada al
resumidor (76 evitados). Conserva originales cuando no ahorra, advertencias y protección de
cabeza/cola. Es una medición sintética; no una promesa de ahorro monetario en expedientes.

## Adaptación genérica de las reglas de Lexia Litigio

| Principio transferido | Aplicación en Mia | Evidencia / límite |
|---|---|---|
| Medir antes de optimizar | Rechazar compresión sin ahorro real de tokens estimados | `test_context_compressor.py`; no equivale a ahorro monetario medido |
| Evitar reprocesar el mismo insumo | Checkpoint propio una sola vez | Prueba iterativa con resumen propio y mensajes distintos |
| La decisión no sustituye evidencia de cierre | Estado de revisión obtenido del checkpoint | `test_hitl_resume_state.py` y recorrido UI |
| Una corrección invalida aprobaciones anteriores | Texto/huella/informe nuevos, nueva constancia humana | Navegador con respuesta sintética; hash nuevo en segundo envío |
| Revisor independiente y pruebas adversariales | Revisión de rutas, 76 sondas de compresión y mutaciones | Se encontró y corrigió la edición concurrente; no es auditoría especializada |
| Una sola verificación por versión y alcance consolidado | Reglas de construcción en `AGENTS.md`, reutilización de comprobaciones exitosas | Los controles de sellos/delta ya existían; no se duplicaron |
| Ahorro y calidad se miden juntos | Conservar fuentes, avisos y controles; distinguir estimación/no medición | No se cambiaron modelos, precios, doctrina ni pisos de razonamiento |

Fuentes de adaptación: `rules/always.md` §§6, 8 y 9 y los cierres de agosto/septiembre de
Lexia Litigio OS. Solo se incorporan mecanismos operativos; no identidad, expedientes,
argumentos, estándares de ramos ni formato de una firma particular.

## Verificación

El primer tramo rápido dio 31/35 suites verdes: tres fallos ocurrieron mientras PostgreSQL
recuperaba un cierre anterior y MCP agotó el tiempo. Se conserva ese resultado original en
`validation/audit-2026-09-06-quick.json`; las repeticiones justificadas y la regresión ampliada
se registran en `validation/audit-2026-09-06-system.json`. No se sustituye un rojo histórico
por un verde sin explicar su causa.

La pasada ampliada terminó con **95/95 suites seleccionadas en verde**, 2.963 comprobaciones
contabilizadas y 932,162 segundos acumulados; no se cuentan como aserciones únicas. RLS
pasó 19/19 aparte. El recorrido E2E pasó 60/60 y aprobación 21/21. MCP offline+DB pasó 40/40;
la porción live se omitió expresamente. Hay 57 suites omitidas con razón en la evidencia.
La compilación de escritorio se detuvo durante copia lenta de recursos y queda inconclusa;
no se interpreta como fallo de Rust ni como compilación aprobada.

La regresión de pantalla está en `e2e/revision_regenerada.mjs`: usa el frontend real con
respuestas API sintéticas, prueba ambos temas y comprueba segunda aprobación con nueva
huella. Sus capturas y resultados viven en `output/playwright/`.

Resultado de pantalla: ambos temas pasaron; axe (WCAG A/AA) sin incidencias y cero errores
de página. Lint, TypeScript y build de producción pasaron. `npm audit` informó cero
vulnerabilidades conocidas en 544 dependencias. La primera ejecución del fixture UI
omitió campos obligatorios de verificación (`detalle` y `respaldadas`); se corrigió el
fixture antes de interpretar su timeout como fallo de producto.

## Límites que siguen siendo relevantes

- El asistente crea un compresor por turno: aún no persiste checkpoints de resumen por
  conversación. Hacerlo exige invalidación y aislamiento; no se añadió caché global.
- Las pruebas con proveedores sustituidos acreditan cableado y contratos, no profundidad
  jurídica ni precio real. Falta comparación de calidad con modelos reales y evaluación
  humana ciega para afirmar ahorro monetario sin pérdida de calidad.
- El navegador no acredita el puente Tauri instalado. La instalación del NSIS en equipo
  limpio y las integraciones opt-in requieren sus propias pruebas.
- Los checks de formato de Word no sustituyen la validación visual del documento final.
- No se cambiaron credenciales, datos de clientes, políticas de modelos ni precios.

El resultado actualizado y los procesos que permanezcan activos se consignan en el cierre
más reciente de `HANDOFF.md`.

## GrokRouter y Grokky: comparación solicitada

Archivos entregados por el usuario, inspeccionados dentro de los ZIP sin ejecutarlos:

- `grokrouter-main.zip`: 95 entradas, SHA-256
  `b71f660f797c6ecd4d5ebe1a59dc28e9094617c3d5dab660cab243b69baafcc4`.
- `grokky-main.zip`: 104 entradas, SHA-256
  `a1978d1263db317de407105a6573bbf94ce99cf4cf32e096eb6bb2391a74b449`.

Las licencias incluidas restringen incorporar código a otro producto. Se compararon
capacidades y se escribió una adaptación propia para Mia; no se incorporaron dependencias,
código, prompts, marcas ni activos de esos proyectos.

| Observación | Comparación con Mia | Decisión |
|---|---|---|
| Métrica de caché del proveedor (`grokky/src/main/providers/codex-provider.ts`, `grokrouter/runtime/run-provider.mjs`) | Mia ya almacenaba esa métrica, pero su adaptador Codex la perdía | Implementada la traducción propia; 31 checks, recorrido hasta recorder y revisión independiente |
| Control de turnos concurrentes y huella de petición | El chat libre de Mia persiste historial pero no tiene idempotencia por envío | Implementada en continuación: clave por despacho/usuario/envío y respuesta durable; un reenvío no ejecuta otro turno. No serializa claves distintas entre dispositivos |
| Continuidad de hilos del proveedor | Mia usa Codex efímero deliberadamente y arma contexto explícito | Mantener aislamiento; no importar hilos duraderos del proveedor automáticamente |
| Continuidad de conversación | El asistente de Mia solo carga 200 mensajes y crea compresor por turno | Propuesta propia: resumen persistido más cursor de cobertura y originales conservados; no es función encontrada en los ZIP |
| Historial local, enrutamiento, actividad de ayudantes | Mia ya tiene PostgreSQL/RLS, políticas por despacho, telemetría y búsqueda de trazas | No duplicar infraestructura ni confundir historial con memoria semántica nueva |

Para resumen persistido e idempotencia, los criterios de aceptación serían: aislamiento
entre despachos; reintento de un mismo envío sin segunda inferencia; preguntas iguales con
identificadores distintos permitidas; resumen invalidado al cambiar su alcance; ninguna
advertencia perdida; recuperación tras reinicio; medición conjunta de costo y calidad.
En el primer cierre no se implantaron. Tras la instrucción de continuar se incorporó
idempotencia propia del chat: clave por despacho/usuario/envío, reserva durable,
recuperación de respuestas completadas y reintento desde la pantalla. Los estados
inciertos no se ejecutan de nuevo automáticamente. El resumen persistido sigue pendiente.
Los contratos, límites de recuperación y diseño de continuidad constan en
`docs/chat-continuidad-idempotencia.md`; el cierre más reciente de `HANDOFF.md` registra
la verificación de esta continuación.
