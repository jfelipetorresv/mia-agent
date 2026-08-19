## Checkpoint anterior: CP-C3 — El circuito de aprendizaje quedó cerrado (2026-07-01)

### Qué cambió (lenguaje simple)

- Cuando el abogado rechaza o corrige un borrador, la sugerencia de mejora
  que Mia genera ahora apunta al procedimiento que DE VERDAD participó en
  ese trabajo (antes podía proponer mejorar uno cualquiera), se redacta
  viendo el contenido real de ese procedimiento, y al aplicarla queda
  guardada la versión anterior (se puede volver atrás).
- El listado de sugerencias ahora dice QUÉ procedimiento se va a modificar.
- Para ver el ciclo completo en vivo falta UN insumo de negocio: que Pipe
  suba sus primeras guías de trabajo (botón/endpoint de importar guías).

### Frontend a revisar (Cursor — capa 3)

- Sin pantalla nueva. NOTA para CP7: `GET /api/proposals` ahora devuelve un
  campo `target` (título del procedimiento a modificar) — la Pantalla 4
  (memoria) debería mostrarlo junto a cada sugerencia. Siguen PENDIENTES de
  capa 3 los 2 archivos de CP5.

### Resultado de verificación (3 capas)

- Capa 1: regresión completa **41/41 suites PASS** (test_rls 12/12 HALT);
  gates extendidos: test_feedback_processor 26/26, test_gepa 18/18,
  test_trace_capture 23/23, test_ux 29/29.
- Capa 2 (revisor independiente): **APROBADO** sin bloqueantes; sus 2
  hallazgos mayores (del flujo pre-existente de aplicar sugerencias,
  agravados por este checkpoint) se corrigieron antes del commit.
  Revisión por lectura de patrones conocidos, no auditoría con herramientas.
- Capa 3 (Cursor): NO APLICA (sin frontend; ver nota para CP7 arriba).

---

