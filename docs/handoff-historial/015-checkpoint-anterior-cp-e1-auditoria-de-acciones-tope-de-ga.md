## Checkpoint anterior: CP-E1 — Auditoría de acciones + tope de gasto de IA (2026-07-03)

### Qué cambió (lenguaje simple)

- **Registro de auditoría:** Mia ahora deja rastro de cada acción del despacho
  (quién hizo qué y cuándo) en un registro interno append-only, por despacho. Es
  invisible y no cambia nada de la experiencia; sirve para cumplimiento/confianza
  al vender a firmas grandes. Guarda solo metadatos (acción, ruta, ids, resultado)
  — NUNCA el texto de la consulta ni el contenido del expediente.
- **Tope de gasto de IA:** el despacho puede fijar un presupuesto MENSUAL en dólares.
  Al alcanzarlo, los turnos nuevos se pausan con un aviso en llano hasta que el
  abogado suba el tope o llegue el mes siguiente. Antes solo se MEDÍA el gasto
  (tarjeta "Valor entregado"); ahora se puede LIMITAR.

### Frontend a construir (Cursor — capa 3): control del tope en el Panel

- **`GET /api/policy/budget`** → `{monthly_budget_usd, spent_this_month_usd,
  remaining_usd, over_budget, unlimited}`. `monthly_budget_usd`/`remaining_usd` son
  null cuando es ilimitado (`unlimited: true`).
- **`PUT /api/policy/budget`** body `{"monthly_budget_usd": 100}` (o `null`/0 para
  quitar el tope) → devuelve el estado ya actualizado.
- Sugerencia de UI: en el Panel de control, junto a "Valor entregado este mes",
  un control "Tope de gasto de IA este mes" — input en USD + "Sin límite"; mostrar
  gasto del mes y restante; si `over_budget`, un aviso ámbar "Se alcanzó el tope;
  los turnos están en pausa". Estado vacío/ilimitado en llano.
- El REGISTRO de auditoría es backend-only por ahora (no requiere pantalla); una
  vista "Registro de actividad" es trabajo futuro opcional.

### Comportamiento esperado

- Con tope fijado y gasto por debajo: todo igual. Al superarlo, un asunto o el
  asistente responden **402** con el aviso en llano (mostrar el `detail` tal cual).
- El dictado por voz NO cuenta como "acción" en el registro (alta frecuencia).

### Resultado de verificación (3 capas)

- Capa 1: gate nuevo `test_observability.py` **22/22** (auditoría RLS + fail-open +
  recorte de campos; tope: roundtrip incl. rama de producción, suma del mes UTC,
  bloqueo/permiso, fail-open); regresión **ALL PASS (53 suites)** (test_rls HALT).
  Sin frontend web tocado → sin npm build.
- Capa 2 (revisor adversarial): confidencialidad (sin fuga del mensaje a
  audit_logs — se guarda solo el path, no el query string), aislamiento RLS,
  fail-open y no-regresión del curador CONFIRMADOS. 1 BLOQUEANTE (el tope no
  persistía sobre la fila tenant_settings que todo tenant ya tiene → jsonb_set
  corregido) + 1 MENOR (borde de mes corrido 5h por la zona del servidor)
  corregidos ANTES del commit y re-verificados. Ver memory/progress.md sesión 30.
- Capa 3: COMPLETADO — ver "Hallazgos de Cursor (capa 3)" · 2026-07-04 (CP-E1).

---

