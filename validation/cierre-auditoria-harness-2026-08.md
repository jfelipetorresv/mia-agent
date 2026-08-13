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
| Gates y scripts | Cumplido | `config/verification.json`, `scripts/verify.ps1`, preflight DB, UTF-8 y timeout por árbol | — |
| EF-3 enrutamiento | Cumplido | `LEGAL_TASKS`, pisos por política y `test_model_policy.py` | Calibración futura conserva IDs separados |
| EF-4 contexto progresivo | Cumplido | Índice, máximo 5 cuerpos, borradores no inyectados, presupuesto de playbooks | — |
| Migraciones reejecutables | Cumplido para fallos hallados | Vocabularios acumulativos en 010/027/040/049; suites de Dreams/correo verdes | — |
| Flujo jurídico núcleo | Cumplido | HITL, RLS, pipeline; motor argumental 66/66; prompt builder 51/51 | — |
| Seguridad frontend | Cumplido | Next 16.3.0, React 19.2.8, build de 14 rutas y `npm audit` con 0 vulnerabilidades | 11 avisos de lint heredados, no bloqueantes |
| Regresión integral | Cumplido | 142 suites recorridas; seis contratos desactualizados reparados y repetidos verdes; quick verde | La pasada completa tarda ~10,5 min; optimizar el runner es evolución |

## Decisiones de alto impacto cerradas

1. Metodología fija: 1.744 → 363 tokens; system de borrador: 3.255 → 1.171;
   franja no cacheada: 871 → 167. Los invariantes quedaron fijados por 66 gates.
2. Next.js 14 → 16.3.0 y React 18 → 19.2.8; build, navegación Login→Registro,
   empaquetado, autenticación y auditoría de dependencias verificados.

El núcleo queda apto para comenzar pruebas controladas. Esto no equivale a certificar la
calidad jurídica de un caso real: esa validación conserva sus gates independientes y HITL.
