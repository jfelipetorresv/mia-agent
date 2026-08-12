# Auditoría de robustecimiento y poda de Mia — agosto de 2026

## Veredicto

Mia conserva una visión integral, pero su primera frontera verificable es el flujo jurídico
núcleo: asunto → expediente → análisis → verificación → borrador → aprobación → exportación.
El núcleo existe y está cableado. Antes de declarar el producto listo para pruebas faltan una
señal automática confiable, cerrar la eficiencia pendiente y retirar capacidades aparentes
que no participan en el runtime.

Este informe contiene únicamente principios generales y evidencia propia de Mia. La
trazabilidad hacia el sistema reservado de Lexia vive en un anexo privado separado.

## Hallazgos prioritarios

1. **Regresión no confiable.** El gate HITL esperaba el nombre anterior del nodo y depende de
   infraestructura local sin diagnóstico temprano. Tampoco existía CI versionada.
2. **Enrutamiento por función pendiente.** Los especialistas jurídicos usan mayoritariamente
   `task="main"`; falta una política función→nivel con pisos verificables.
3. **Contexto progresivo incompleto.** El conocimiento usa un presupuesto global, pero no un
   índice ligero seguido de fichas justificadas; las guías limitan cantidad, no peso.
4. **Hooks aparentes fuera del runtime — retirados.** `MiaAgent` y sus seis hooks solo tenían
   consumidores de prueba; se eliminó ese runtime paralelo y el constructor de prompts quedó
   probado mediante su contrato mínimo real.
5. **Complejidad concentrada.** El grafo y algunas rutas mezclan demasiadas responsabilidades.
   La separación debe seguir a contratos y gates, no precederlos.
6. **Fases ambiguas.** F3/F4 significan cosas distintas en dos planes. En adelante la
   eficiencia se identifica como `EF-3` y `EF-4`.
7. **Dependencias vulnerables.** `npm audit` reporta ocho vulnerabilidades altas, incluidas
   dependencias directas de Next.js y PostCSS. La solución sugerida exige migrar a Next.js 16;
   debe ejecutarse como cambio mayor separado, con regresión y revisión visual.

## Principios incorporables

- Separar productor, verificador y sellador; el verificador no modifica el artefacto auditado.
- Convertir reglas críticas en contratos, estados o barreras ejecutables, no solo prosa.
- Validar cada hook por registro, ruta, evento, matcher y tiempo máximo.
- Mantener un grafo de alcanzabilidad; una definición sin invocación real es candidata a poda.
- Usar contratos versionados con `run_id`, procedencia y estado durable entre etapas.
- Exigir prueba positiva, negativa y mutación a cada gate.
- Dar a cada rol solo el contexto necesario y medir relecturas y relanzamientos.
- Mantener una sola fuente canónica para skills o adaptadores y generar sus copias.
- Considerar aplicado un aprendizaje solo cuando exista una defensa ejecutable.

## Secuencia de implementación

1. Base confiable: contratos actualizados, CI y entrada única de verificación.
2. Poda demostrada: retirar scaffolding y artefactos sin consumidores reales.
3. EF-3: funciones jurídicas separadas en el router y la telemetría, conservando el piso de
   razonamiento principal; después se calibran niveles distintos sin mezclar métricas.
4. EF-4: índice ligero, fichas progresivas, estados y presupuestos duros para guías.
5. Contratos de corrida: manifiesto durable, huellas y reconciliación de huérfanos.
6. Prueba del núcleo con caso ficticio o anonimizado; luego capacidades integrales por capas.

## Criterio de eliminación

No se elimina por tamaño ni por pocas referencias. Se exige ausencia de consumidores reales,
declaración de reemplazo o imposibilidad de alcanzar el componente desde el producto. Cada
retiro debe dejar pruebas verdes y recuperación por Git.

## Inventario de la carpeta superior

- **Conservar:** repo `mia`, `tools` (PostgreSQL portable), `Lexia-Vault`, `.agents` y el
  worktree `mia-cory-audit-worktree`, que contiene una línea divergente no integrada.
- **Mover fuera del workspace al terminar la investigación:** repositorios de referencia;
  no son runtime, pero todavía sirven como evidencia técnica.
- **Eliminar después de respaldo:** `spike-fase4*`, cerca de 2 GB. No están versionados y no
  se borran hasta preservar sus README o resultados útiles.
- **Regenerables pero necesarios durante el robustecimiento:** entornos virtuales,
  `node_modules` y `desktop/src-tauri/target`, cerca de 4,4 GB.
- **Retiro aplicado:** log diagnóstico de la raíz y dependencia frontend sin imports.
