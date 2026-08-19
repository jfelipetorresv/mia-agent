# Anexo privado — trazabilidad de principios del harness hacia Mia

> Reservado. No distribuir con el producto ni convertir rutas, prompts o reglas jurídicas del
> harness en documentación pública de Mia.

| Evidencia reservada | Principio abstraído | Aplicación en Mia |
|---|---|---|
| Configuración y comprobador de hooks | Un hook solo existe si está registrado y resoluble | Gate de evento, matcher, ruta y timeout |
| Guardas por herramienta y pruebas adversariales | Prevenir daño y validar también la salida | Casos permitidos/bloqueados por guarda |
| Guardas de corrida y aislamiento | Una corrida no mezcla artefactos con otra | `run_id` y workspace obligatorios |
| Comprobación de huella | El auditor no altera el objeto auditado | Hash antes/después y salida separada |
| Manifiesto y espejo de agentes | Definición única fuera de discovery duplicado | Registro de roles, herramientas y deriva |
| Contratos JSON entre etapas | Reducir contexto y ambigüedad | Envelopes versionados con procedencia |
| Ledger y gestor de gates | Estado durable, no conversación | Reanudación idempotente y reconciliación |
| Catálogo de barreras | Ningún gate se omite silenciosamente | Comando único y skips visibles |
| Fixtures, claves y sabotajes | Calibrar falsos verdes | Oracle separado y mutación por barrera |
| Presupuestos por rol | El costo es un contrato medible | Límites por etapa y excedentes declarados |
| Sincronización de skills | Una fuente canónica | Hashes y detección de duplicados obsoletos |
| Manifiesto de release | Distribución reproducible y limpia | Allowlist y escaneo de secretos/PII |
| Retrospectivas comprobables | Aprender exige defensa ejecutable | Estado documentado/aplicado/verificado |

La matriz detallada permanece en el registro reservado de auditoría. Este anexo conserva el
mínimo necesario para justificar decisiones sin copiar la implementación protegida.
