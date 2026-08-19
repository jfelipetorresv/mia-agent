# Smoke 1×2 — no concluido

Este directorio contiene el plan, el preflight y una salida parcial de un solo caso del
brazo Claude. No contiene el brazo Codex ni un resultado comparable; por tanto no puede
usarse para escoger proveedor ni para afirmar la meta 25/30/25.

Primer intento: se detuvo antes del modelo por un `ProactorEventLoop` incompatible con el pool
asíncrono de Psycopg. El runner quedó corregido para usar `WindowsSelectorEventLoopPolicy`.

Segundo intento: reveló que la envoltura del tope de gasto no aceptaba el quinto parámetro
`quality_escalation` del router. Se corrigió manteniendo compatibilidad con las llamadas de
cuatro parámetros; el gate completo del guardián quedó en 83/83.

El reintento posterior terminó un caso Claude antes de ser cancelado. Esa salida parcial se
conserva como `arm-claude.json` para no ocultar consumo ni evidencia, pero no se asignó un
ganador porque falta el brazo Codex equivalente. La matriz completa de 180 turnos no se
ejecutó.
