# Smoke 1×2 — no concluido

Este directorio contiene únicamente el plan y el preflight. No contiene un resultado de
benchmark ni puede usarse para comparar proveedores.

Primer intento: se detuvo antes del modelo por un `ProactorEventLoop` incompatible con el pool
asíncrono de Psycopg. El runner quedó corregido para usar `WindowsSelectorEventLoopPolicy`.

Segundo intento: reveló que la envoltura del tope de gasto no aceptaba el quinto parámetro
`quality_escalation` del router. Se corrigió manteniendo compatibilidad con las llamadas de
cuatro parámetros; el gate completo del guardián quedó en 83/83.

El reintento posterior fue cancelado por instrucción del coordinador antes de producir un
reporte. No se conservaron respuestas parciales, no se asignaron puntajes y no hay ganador.
La matriz completa de 180 turnos no se ejecutó.
