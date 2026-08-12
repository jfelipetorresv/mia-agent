# Matriz de cierre — robustecimiento inspirado en harness (2026-08)

Esta matriz prueba el estado del encargo sin exponer la implementación reservada. “Parcial”
significa que existe evidencia útil, pero no autoriza declarar terminado el frente.

| Requisito | Estado | Evidencia actual | Falta para cerrar |
|---|---|---|---|
| Investigación comparativa sin copia | Cumplido | `docs/auditoria-harness-aplicada-a-mia-2026-08.md` | — |
| Trazabilidad reservada separada | Cumplido | `docs/private/trazabilidad-harness-mia-2026-08.md` | Mantener fuera de distribución |
| Auditoría integral del árbol | Cumplido | Inventario del informe; worktree, herramientas y datos clasificados | — |
| Poda con evidencia | Cumplido en código versionado | Eliminados runtime `MiaAgent`/plugins/hooks y dependencia frontend sin imports | Los prototipos externos no versionados requieren respaldo antes de borrar |
| Hooks | Cumplido por simplificación | No existe subsistema de hooks productivo aparente; las extensiones reales son nodos, conectores o middleware | — |
| Agentes y subagentes | Cumplido | Grafo único; tareas jurídicas separadas; Agent Hub con consentimiento; gates de flujo | — |
| Skills/playbooks | Cumplido inicial | Fuente DB única, vínculo por persona, HITL para aprendizaje, máximo 3 activos y presupuesto de 8% | Health/freshness periódico queda como evolución |
| Gates y scripts | Cumplido inicial | `config/verification.json`, `scripts/verify.ps1`, preflight DB, UTF-8 y timeout por árbol | Regresión completa sigue roja por metodología jurídica |
| EF-3 enrutamiento | Cumplido | `LEGAL_TASKS`, pisos por política y `test_model_policy.py` | Calibración futura conserva IDs separados |
| EF-4 contexto progresivo | Cumplido | Índice, máximo 5 cuerpos, borradores no inyectados, presupuesto de playbooks | — |
| Migraciones reejecutables | Cumplido para fallos hallados | Vocabularios acumulativos en 010/027/040/049; suites de Dreams/correo verdes | — |
| Flujo jurídico núcleo | Parcial | HITL, RLS, pipeline y suites afectadas verdes | `test_argument_engine.py` 55/66 por prompt sobredimensionado |
| Seguridad frontend | Pendiente autorizado | `npm audit`: ocho vulnerabilidades altas | Migración mayor de Next.js + regresión visual |
| Regresión integral | Parcial | 16/18 fallos iniciales corregidos y repetidos verdes; quick 143/143 aserciones | Una suite jurídica roja; la pasada completa además excede 16 min |

## Decisiones de alto impacto pendientes

1. Condensar la metodología jurídica fija manteniendo sus invariantes ejecutables. Medición
   actual: metodología ≈1.744 tokens; system de borrador ≈3.255 (≈871 no cacheados).
2. Migrar Next.js 14 a una versión mantenida para corregir las vulnerabilidades altas.

No se puede afirmar “producto listo” hasta cerrar ambas decisiones y repetir la regresión.
