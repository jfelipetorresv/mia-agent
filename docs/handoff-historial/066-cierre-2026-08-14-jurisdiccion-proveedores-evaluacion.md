# CIERRE — 2026-08-14 · Jurisdicción, proveedores y evaluación: correcciones cerradas; API por instalador pendiente

## Resultado de esta sesión

Mia ya separa el dato aportado por el abogado de la evidencia que autoriza una cita
generada: sin jurisdicción configurada, una referencia repetida desde el mensaje se
omite del borrador y queda trazada, pero el mensaje original no se altera. La ruta
configurada conserva el marcado clásico. Gate: `execution/test_jurisdiction_omission.py`
29/29 y `execution/test_sentence_report.py` 47/47.

La selección de proveedor dejó de gastar o cambiar datos de asunto en silencio:
calidad estándar inicia Sonnet, Opus/Max solo entra por escalada excepcional y las
políticas de membresía fallan claro para `main` y tareas jurídicas. Codex es una
política explícita de membresía local: no es el alias de evaluación, no usa API ni
cae a Claude/local. Gate: `execution/test_model_policy.py` 55/55.

Codex por membresía está limitado a la app Tauri del titular: Tauri inyecta en cada
arranque/reinicio una marca efímera, host loopback y CORS local; el bootstrap no
persiste esas marcas. Un servidor o reverse-proxy ordinario queda apagado; esto NO
es una frontera contra el administrador del mismo host. Gate adversarial:
`execution/test_codex_production_provider.py` 15/15. Pasaron también compilación
Python, lint/typecheck frontend, `cargo check` Tauri y `git diff --check`.

Se eliminó el `.env` local con configuración personal. No se hicieron llamadas a
modelos ni se guardó una clave nueva. La corrida de benchmark `validation/provider-
benchmark-full-2026-08-14/` fue detenida por Pipe: es evidencia parcial, no una
comparación ni una certificación, y no debe borrarse ni usarse en comunicación comercial.

## Próximo bloque — no asumir, ejecutar en este orden

1. **API propia por instalación (decisión ya tomada por Pipe):** construir en el
   instalador el alta separada de Claude API y Codex/OpenAI API. Cada computador
   aporta y guarda su propia credencial local ignorada; no reutilizar claves de
   desarrollo. Antes de cualquier llamada OpenAI, aplicar el gate de credenciales
   seguro y pedir/recibir la clave de esa instalación.
2. **Cierre de instalación:** correr `execution/test_first_run.py` hasta obtener
   exit/result capturado y la colección rápida/CI desde entorno limpio. Esta sesión
   no cuenta ese gate como verde porque la ejecución larga terminó sin salida capturable.
3. **Benchmark solo por decisión de negocio:** definir qué afirmación se quiere
   demostrar, tiempo, presupuesto y criterio; entonces usar el runner durable en
   carriles separados. No reanudar la matriz actual automáticamente.
4. **Distribución:** no prometer aún la meta de instalador ≤335 MB; requiere build
   limpio medido. Mantener la variante Compact/Offline y sus gates existentes.

La retrospectiva técnica está en
`docs/retrospectives/retrospective-2026-08-14-proveedor-jurisdiccion-y-evaluacion.md`;
las reglas permanentes se absorbieron en `APRENDIZAJES.md`.
