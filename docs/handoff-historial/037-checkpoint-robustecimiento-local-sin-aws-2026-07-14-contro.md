## Checkpoint: robustecimiento local sin AWS (2026-07-14) — control atómico de gasto

- Rama local `feature/robustecimiento-sin-aws`; todavía no se ha hecho push. Esta fase añade
  `035_atomic_ai_budget.sql`: cada llamada pagada reserva saldo en PostgreSQL antes de salir y
  liquida el costo real al terminar. Dos trabajos simultáneos ya no pueden atravesar juntos el tope.
- `turn_usage` conserva el detalle; `ai_budget_months` es el saldo mensual autoritativo desde la
  primera reserva, para no depender del buffer. Motores de suscripción/local no reservan; si un
  motor pagado no cabe y existe respaldo gratuito, Mia degrada a este sin detener el trabajo.
- Un corte incierto conserva la estimación por prudencia; una liberación con fallo transitorio de
  DB reintenta tres veces. RLS forzado mantiene las reservas aisladas por despacho.
- Gates: `test_atomic_ai_budget` 11/11, `test_observability` 22/22,
  `test_llm_fallback` 25/25 y `test_migration_ledger` PASS. Claude Code encontró el riesgo de
  liberación transitoria, se corrigió, y su segunda auditoría dio **PASS sin bloqueantes**.

---

