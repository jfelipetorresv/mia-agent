# Baseline F0 — gasto por nodo del grafo (plan de eficiencia)

Fecha: 2026-08-07 · Corrida: `baseline-f0-nodo-v2` (crudos en `mia-data/eval-runs/baseline-f0-nodo-v2/`)
Condiciones: caso de oro `expediente-voluminoso-cruce-disperso` (3 documentos, 252 fragmentos),
×3 corridas consecutivas, política `suscripcion` (aliases `cli-*`, coste USD marginal 0 — se mide
cuota en tokens), máquina del proyecto, `MIA_AGENTIC_READING` apagada, instrumentación de la
migración 048 (`turn_usage.node`). El desglose por nodo se captura dentro del reporte del eval
ANTES de que el tenant de eval se borre (las filas de `turn_usage` se van con él).

## La tabla contra la que se mide toda palanca de F1-F4

Suma de las 3 corridas (turno de asunto; sin approve → sin harvest/edit):

| Nodo | Llamadas | Prompt | Completion | Total | % del atribuido |
|---|---|---|---|---|---|
| draft | **9** (3/turno) | 179.996 | 122.517 | 302.513 | 35,5 % |
| verificador_citas | **9** (3/turno) | 143.577 | 113.613 | 257.190 | 30,2 % |
| analysis | 3 (1/turno) | 88.490 | 43.672 | 132.162 | 15,5 % |
| facts | 3 (1/turno) | 63.945 | 29.336 | 93.281 | 11,0 % |
| research | 3 (1/turno) | 39.884 | 26.002 | 65.886 | 7,7 % |
| **Atribuido al grafo** | **27** | | | **851.032** | 100 % |
| Fuera del grafo (aux: triage, clasificación, etc.) | 15 | | | ~155.474 | — |
| **Total de la corrida** | **42** | | | **1.006.506** | — |

Latencia (informativa, nunca gate): p50 = 1.179,5 s · p95 = 1.526,5 s · rango [1.168–1.565 s].
Calidad (el contrapeso que ninguna palanca puede degradar): 0 afirmaciones sin respaldo,
abstención honesta 3/3, fuga 0/3, turnos completados 3/3.
Referencia de la primera pasada (mismo caso, sin captura por nodo, `baseline-f0-nodo`):
1.047.015 tokens / 42 llamadas / p50 1.495 s — variabilidad entre tandas ~4 %.

## Lo que la tabla ya demuestra (hipótesis del plan, ahora con dato)

1. **El bucle del gate de citas es real y es el gasto #1**: draft y verificador_citas corren
   3 veces por turno (el gate rebota el borrador 2 veces). Entre ambos: **559.703 tokens, el
   66 % de lo atribuido**. La palanca F1.5 (capar el bucle) y la decisión de Pipe sobre el
   gate atacan directamente esta línea.
2. **El prefijo se paga íntegro en cada llamada**: 27 llamadas de grafo × ~2.400-3.600 tok de
   capas estables sin caché bajo `suscripcion` ≈ 65.000-97.000 tok/tanda solo de prefijo
   repetido (6-10 % del total). Palanca F1.2 (extractos por rol) lo reduce sin tocar caché.
3. **Las llamadas auxiliares no son gratis**: 15 llamadas / ~155k tokens (15 %) fuera del
   grafo — clasificación de documentos al subir y triage. Candidatas a nivel ligero explícito
   (F3) — hoy ya van por cadena AUX, falta atribuirlas con nombre (`node` para aux).
4. **research es el nodo más barato (7,7 %)** — el fan-out por jurisdicciones (N+1) solo
   dolería con despachos multi-jurisdicción; no es prioridad.

## Regla de uso

Toda palanca de F1-F4 se aprueba comparando contra ESTA tabla (misma semilla, mismo caso,
×3), con la calidad como gate: 0 sin respaldo, abstención honesta y alcance declarado no
pueden caer. La tabla se regenera con:

    .venv\Scripts\python.exe execution\run_eval.py --case expediente-voluminoso-cruce-disperso --repeat 3 --run-id <id>

y el desglose queda impreso y persistido en el JSON del run (`uso_por_nodo`).
