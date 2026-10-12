# Banco de calidad 0.4 — Resultados

Protocolo: **banco04-v1.2** (`docs/banco-calidad-04-protocolo.md`). Plantilla creada **antes** de
correr (§9.7). Se rellena sin excluir corridas; las anuladas se listan con su motivo. No se vuelve a
correr para mejorar un número.

> **Rótulo de todo número de este documento:** «Evaluación automática (Opus high y Codex en cribado
> doble, adjudicación por mayoría)». Solo si Pipe completa la revisión ciega de §8.7: «… calibrada
> con revisión humana ciega (n = 10)». Nunca «validado por abogado» ni «certificado».

## 0 · Primera línea

| Campo | Valor |
|---|---|
| Incumplimientos de 0.3.3 (primera línea, §9.7) | _pendiente_ |
| Veredicto de 0.4 (`aprueba` / `reprueba` / `no_certificable`) | _pendiente_ |
| Estado del banco (completo / «incompleto — no certificable») | _pendiente_ |
| Filas rojas | _pendiente_ |
| Motivos de no certificación | _pendiente_ |

## 1 · Identificación y congelación

| Campo | Bloque 0 (0.3.3) | Bloque 7 (0.4) |
|---|---|---|
| SHA de la versión | | |
| `prompt_version_hash` | | |
| Política (`quality_adaptive`) | | |
| Versión del CLI de Claude / modelo efectivo del productor | | |
| Hash del protocolo (`protocolo.hash_protocolo()`) | | |
| Hash del evaluador (`jueces.hash_evaluador()["combinado"]`) | | |
| Modelo reportado por el juez Opus / por Codex | | |
| Manifiesto de custodia (sha256) | | |
| Fecha | | |

## 2 · Validación de los jueces (§8.6) — antes de juzgar la línea base

| Exigencia | Umbral | Ajuste | Reservado (un solo uso) |
|---|---|---|---|
| Sensibilidad final del circuito | ≥ 0,95 | | |
| Falsos positivos finales del circuito | ≤ 0,10 | | |
| Sensibilidad Opus / Codex | ≥ 0,90 | | |
| Falsos positivos Opus / Codex | ≤ 0,10 | | |
| Kappa (unidades comunes) | ≥ 0,6 | | |
| Sensibilidad en cláusula falsa breve | ≥ 0,90 | | |
| Defectos vistos solo por Codex descartados por la mayoría | ≤ 0,20 | | |
| Salidas sin evaluar | 0 | | |
| **Circuito utilizable** | sí | (no aplica) | |

Estabilidad (Opus repite la pasada 1 sobre el 10 % elegido con la semilla): acuerdo por afirmación
= _pendiente_.

## 3 · Corridas

| Estrato | Casos | R | Corridas previstas | Completadas | Anuladas (motivo) | Cambio de motor |
|---|---|---|---|---|---|---|
| A-canónicos | 3 | 5 | 15 | | | |
| A-riesgo | 6 | 5 / 10 | 35 | | | |
| A-voluminoso | 1 | 5 | 5 | | | |
| C-pequeños (contenido visible) | 3 | 5 / 10 | 20 | | | |
| C-voluminosos (custodia DPAPI, mismo usuario) | 4 | 5 | 20 | | | |

Contingencia de la tanda piloto (§3.4): _sin aplicar / aplicada con la cifra de consumo que la disparó_.

## 4 · Absolutos de 0.4 (§6.1) — y los mismos medidos a 0.3.3

| Métrica | Umbral | 0.4 | 0.3.3 | Cumple 0.4 |
|---|---|---|---|---|
| `afirmaciones_sin_respaldo` (confirmadas) | 0 | | | |
| `fuga_jurisdiccion` | 0 | | | |
| `definitivo_con_lectura_insuficiente` | 0 | | | |
| Discordancias materiales sin resolver | 0 | | | |
| Kappa reservado / kappa en salidas reales (o «indefinido (clase única)» / «inestable (n < 10)») | ≥ 0,6 | | | |
| Evaluación completa (100 % por los dos jueces) | sí | | | |
| `cobertura_hechos_decisivos`, lectura completa (media; mínimo por caso) | ≥ 0,90; ≥ 0,80 | | | |
| `cobertura_decisivos_en_lo_leido`, voluminosos (media) | ≥ 0,90 | | | |
| `cobertura_hechos_decisivos`, voluminosos (media) | ≥ 0,34 | | | |
| Tasa de corridas con omisión material de lo leído (por estrato) | ≤ 0,20 | | | |
| `utilidad_resultado_limitado` (por estrato donde aplique) | ≥ 0,80 | | | |
| `aprobacion_sin_edicion_proxy`, lectura completa (proxy) | ≥ 0,60 | | | |

Recuento de afirmaciones sin respaldo por estrato, caso, corrida y subtipo: _pendiente_.

Ilustración condicionada (§3.3), con la frase literal: «Con R = 5 y cero fallos, siguen siendo
compatibles tasas por caso de hasta ≈ 45 %, bajo el supuesto de corridas independientes e
idénticamente distribuidas, que aquí no se cumple.» (R = 10: ≈ 26 %).

## 5 · Comparación pareada 0.4 frente a 0.3.3 (§6.2)

Veredictos posibles: `regresion`, `no_concluyente`, `sin_regresion_observada`, `mejora` (solo con
bootstrap, k ≥ 4) y `descriptivo_sin_inferencia` (k < 4). Bootstrap por casos, 90 %, 10 000
remuestreos, δ = 0,05 (0,02 en turnos completados).

| Métrica | A-pequeños (k = 9) | C-voluminosos (k = 4, orientativo) | A-voluminoso (k = 1) | C-pequeños (k = 3) |
|---|---|---|---|---|
| `turnos_completados` | | | | |
| `cobertura_hechos_materiales` | | | | |
| `cobertura_hechos_decisivos` | | | | |
| `omisiones_materiales` (tasa de corridas) | | | | |
| `definitivo_con_hecho_decisivo_omitido` | | | | |
| `aprobacion_sin_edicion_proxy` | | | | |
| `utilidad_resultado_limitado` | | | | |
| `falsos_bloqueos` | | | | |
| `abstencion_injustificada` | | | | |
| `tasa_cambio_de_motor` | | | | |

Casos que pierden más de 0,20 de cobertura: _pendiente_. Hechos decisivos hallados por 0.3.3 en
≥ 3/5 que caen a ≤ 1/5: _pendiente_. Extensión pre-registrada (si hubo): casos, corridas y
veredicto final.

## 6 · Techo de cuota (§6.3) — sumas y extremos, con cota de los intentos fallidos

| Condición | Claude 0.4 / 0.3.3 (≤ 1,25) | Codex 5C / Claude 0.4 (≤ 0,50) |
|---|---|---|
| Total agregado | | |
| Total ponderado por caso | | |
| Extremo por caso (peor caso) | | |
| Extremo entre repeticiones (peor corrida) | | |
| Inferencias: suma por caso / máximo por corrida | | — |

Descriptivas (nunca puerta): `tokens_por_operacion` p50, `inferencias_por_operacion` p50,
`latencia_p50`, `latencia_p95`. Subidas de más del 10 % y su mejora atribuible por nodo:
_pendiente_. Intentos fallidos sin cota (techo no certificable): _pendiente_.

## 7 · Matriz de conducta (§7.2)

Recuento de corridas por celda (alcance × cobertura C1-C4 × conducta) y por versión: _pendiente_.
Discrepancias entre el alcance medido y `md["alcance_lectura"]`: _pendiente_.

## 8 · Listas publicadas

- Exclusiones y `no_aplica` (con su justificación): _pendiente_.
- Átomos compuestos justificados como una proposición (`UNA_PROPOSICION:`): _pendiente_.
- Tres votos de cada adjudicación: _pendiente_.
- Discrepancias marcador literal ↔ juicio de cobertura y su adjudicación: _pendiente_.
- Desacuerdos con el muro (cita localizada que no sostiene, falso bloqueo, cita no detectada por
  `scan_citations`): _pendiente_.
- «Citas sin respaldo producidas por el modelo antes del muro» (`score_turn`), aparte: _pendiente_.

## 9 · Calibración humana ciega (§8.7, opcional)

| Campo | Valor |
|---|---|
| ¿Se hizo? | _pendiente de Pipe_ |
| Salidas revisadas | |
| Afirmaciones sin respaldo marcadas por Pipe que los jueces no confirmaron | |
| ¿Los jueces certifican el cero? | |
