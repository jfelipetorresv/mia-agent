## Checkpoint anterior: CP-B3 — Mia te avisa y recuerda (2026-07-01)

### Qué cambió (lenguaje simple)

- Mia ahora es proactiva: el abogado le pide recordatorios escribiéndole
  normal ("recuérdame radicar la tutela mañana a las 9") y Mia le avisa por
  Telegram a la hora pactada; también avisa cuando un borrador queda
  esperando su revisión (máximo un aviso al día por asunto) y envía el
  reporte semanal de lo aprendido.
- Regla de negocio dura: si el recordatorio menciona un plazo o actuación
  procesal, SIEMPRE va con [VERIFICAR] — la fecha la pone el abogado y la
  confirma él; Mia no calcula términos legales, y "días hábiles" ni se
  agendan: se pide la fecha exacta.
- Todo es opt-in: sin el bot de Telegram configurado, nada suena y Mia lo
  dice honestamente al confirmar ("quedará visible en tu lista de
  recordatorios").

### Frontend a revisar (Cursor — capa 3)

- CP-B3 NO trae pantalla nueva (la UI de recordatorios llega con CP7; ya
  existen los endpoints GET /api/assistant/reminders y POST
  /api/assistant/reminders/{id}/cancel). Siguen PENDIENTES de capa 3 los 2
  archivos de CP5 listados en el checkpoint anterior.

### Resultado de verificación (3 capas)

- Capa 1: regresión completa **41/41 suites PASS** (test_rls 12/12 HALT);
  gate nuevo `test_reminders` **64/64**.
- Capa 2 (revisor independiente, contexto fresco): APROBADO CON
  CORRECCIONES — 2 bloqueantes y 5 mayores, TODOS corregidos antes del
  commit y convertidos en checks del gate (detalle en memory/progress.md,
  sesión 22). Residuales aceptados en memory/bugs-and-risks.md (Riesgo #35).
  Revisión por lectura de patrones conocidos, no auditoría con herramientas.
- Capa 3 (Cursor): NO APLICA (sin frontend en este checkpoint).

---

