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

---

# DESPUÉS — Fase 1 aplicada (2026-08-07, corrida `f1-despues-nodo`)

Palancas medidas (commit `ad5a6fc`): gate de citas en UNA pasada sin reescritura y con
prompt magro · cosecha fuera del clic de Aprobar (background, solo aprobaciones, persistida
como propuesta) · texto completo de documento leído una vez por pasada · caché de embeddings
de consulta. Mismo caso, mismas condiciones, ×3.

| Nodo | Llamadas | Total F0 | Total F1 | Δ |
|---|---|---|---|---|
| draft | 3 (era 9) | 302.513 | 75.737 | **−75 %** |
| verificador_citas | 3 (era 9) | 257.190 | 54.826 | **−79 %** |
| analysis | 3 | 132.162 | 120.217 | −9 % |
| facts | 3 | 93.281 | 109.612 | +18 % (varianza de completions) |
| research | 3 | 65.886 | 70.501 | +7 % (varianza) |
| **Total corrida** | **30** (era 42) | **1.006.506** | **586.368** | **−42 %** |

Latencia: p50 **569,7 s** (era 1.179,5) · p95 573,8 s (era 1.526,5) → **−52 % — el turno del
caso voluminoso baja de ~20 min a ~9,5 min.**

Calidad (el contrapeso): 0 afirmaciones sin respaldo (3/3) · fuga 0/3 · turnos completados
3/3 · precisión [VERIFICAR] 100 %. **Un matiz a vigilar**: «abstención honesta» dio 2/3
(baseline: 3/3) — una corrida no formuló la declaración de abstención con la señal que el
panel busca. No es el gate absoluto (que es el respaldo, y quedó 3/3 limpio), pero queda
anotado: si se repite en la próxima tanda, se investiga antes de seguir con F2.

**Veredicto: F1 PASA** — −42 % de tokens y −52 % de latencia con el muro intacto, contra la
misma tabla y con derecho a reversa por commit.

---

# DESPUÉS — Fase 2 aplicada: el sello (2026-08-07, corrida `f2-despues-nodo`)

Palanca medida (commit `9d077e7`): el gate LLM de citas se SALTA entero cuando el borrador
no trae nada nuevo que auditar (cero citas, o todas selladas sin avisos). Mecánica del sello
completa probada en `test_citation_seals` (14/14): sellar al aprobar, resolver por sello,
quemada gana, revocación.

| Métrica | F0 | F1 | F2 | Δ vs F0 |
|---|---|---|---|---|
| Tokens/tanda | 1.006.506 | 586.368 | **530.009** | **−47 %** |
| Llamadas | 42 | 30 | **27** | −36 % |
| verificador_citas | 9 llamadas / 257.190 | 3 / 54.826 | **0 / 0 (salto por sello)** | −100 % |
| Latencia p50 | 1.179,5 s | 569,7 s | **533,3 s** | **−55 %** |

Calidad: 0 sin respaldo 3/3 · fuga 0/3 · turnos 3/3 · **abstención honesta 3/3** (el 2/3 de
la tanda F1 fue varianza — con la misma configuración volvió a 3/3; se sigue observando).

Nota de alcance: este caso no trae citas, así que mide el SALTO del gate. La amortización
del sello con citas reales (primera aprobación sella → siguiente turno resuelve sin gate)
queda probada en mecánica (14/14) y se verá en el uso vivo — KPI pendiente en el panel.

**Veredicto: F2 PASA.** Acumulado del plan a hoy: **−47 % de tokens y −55 % de latencia
(20 min → 8,9 min) con los gates absolutos intactos**, y el sistema queda con la propiedad
del harness: cada expediente recurrente será más barato que el anterior.

## Residuos anotados (no bloquean)
- KPI «% de citas resueltas por sello» en el panel del despacho (hoy vive en el informe).
- F1.2b: extractos de metodología por rol para los nodos que SÍ redactan (medir con cuidado).
- Caché de la ficha del expediente por turno (hoy se relee por nodo; es I/O, no tokens).
- F3 (función→nivel con piso) y F4 (memoria progresiva) del plan, pendientes de arrancar.
