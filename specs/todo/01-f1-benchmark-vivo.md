# F1 — Evidencia en vivo: el banco corre contra el modelo real

Fuente: plan maestro `C:\Users\USER\.claude\plans\fable-puedes-estructurar-un-sleepy-sifakis.md`,
sección "F1". Depende de F0 completo (tope de gasto + smoke vertical). Es además el frente A1 de la
auditoría competitiva (benchmark E2E versionado).

## Objetivo
Convertir la promesa central de MIA ("diagnóstico verificado sin afirmaciones sin respaldo") en
números medidos contra un modelo real, con disciplina anti-sobreajuste (holdout intocable).

## Entradas
- Tope de gasto fail-closed y smoke vertical de F0 ya operativos.
- `backend/mia/eval/scoring.py`, `backend/mia/eval/cases.py`, RISK_CASES existentes.
- DB portable en 55432 arriba; `.env` con política `nube` configurada.

## Pasos

1. **Antes de gastar un token: mutación del propio banco.** Respuestas enlatadas con violaciones
   plantadas (cita sin ancla, fuga de jurisdicción, procedencia falsa) contra
   `backend/mia/eval/scoring.py` — el scoring debe cazarlas al 100%. Un benchmark que no puede
   fallar no mide nada.
2. Corrida barata de plomería con política `suscripcion` (cli-claude, sin facturar).
3. Corrida real con política `nube`: `--case fuga-jurisdiccion-contrato-sin-pais --repeat 10`, los
   otros 2 RISK_CASES ×10, y `--agentic-compare` (lectura agéntica ON solo dentro del eval). N=10 por
   caso es el piso — "no reprodujo en 3 intentos" queda prohibido como evidencia.
4. Servicios lanzados por el harness con `run_in_background` (sobreviven la sesión); uvicorn NO
   recarga en caliente — reiniciar entre iteraciones.
5. **Tres grupos de evaluación** (corrección de Codex, contra el sobreajuste):
   - (a) regresión visible (los casos con los que se arregla),
   - (b) mutaciones de validación independiente (las planta el verificador, no el constructor),
   - (c) **holdout intocable** — casos que solo conoce el auditor, con hash registrado, que JAMÁS se
     usan para arreglar; si el guardián solo pasa la regresión visible, está entrenado, no
     endurecido.
6. **Comparador agéntico** solo bajo "nube", mismo modelo/prompt/parámetros en ambas ramas,
   presupuesto reservado — si no, el delta no es interpretable.
7. **Versionar el baseline**: resultados en `mia-data/eval-runs/` + números en `memory/findings.md`,
   con versión de modelo y prompts (el benchmark se re-corre ante cualquier cambio de modelo/prompt);
   cada falla descubierta se vuelve caso nuevo del banco (patrón del commit `3dc79a7`).
8. Workflow: ejecutor + auditor adversarial que verifica que los números del resumen coinciden con
   los crudos.

## Archivos críticos
`backend/mia/eval/scoring.py` (mutación), `backend/mia/eval/cases.py`, `mia-data/eval-runs/`.

## Salida medible (copiada del plan maestro)
1. 100% de violaciones plantadas cazadas por el scoring (y el holdout NI TOCADO).
2. ≥10 corridas por RISK_CASE con coste/duración bajo el tope.
3. Baseline publicado como **panel de métricas** (no 3 números): cobertura y precisión del
   respaldo, **falsos bloqueos** (marcas `[VERIFICAR]` sobre afirmaciones correctamente respaldadas
   — un guardián que marca todo es tan inútil como uno que no marca nada), tasa de detección
   determinista distinguiendo guardián-vs-modelo-obediente, frecuencia de fuga de jurisdicción, tasa
   de abstención, éxito de tarea, latencia p50/p95, coste por turno y variabilidad entre
   repeticiones.
4. Paquete de decisión para Sesión Pipe A (5-10 salidas curadas para que Pipe juzgue la calidad
   JURÍDICA, que ningún agente puede juzgar).

## Gates
HALT (`test_rls.py`, `check_env_pins.py`, `test_gates_no_ciegos.py`) + suites del área en verde +
mutación del scoring demostrada + verificador adversarial independiente que audita los números del
resumen contra los crudos.

## Modelos (matriz del plan)
Ejecución/corridas repetitivas: Sonnet (low-medium). Auditor de números: Codex u Opus (high).
