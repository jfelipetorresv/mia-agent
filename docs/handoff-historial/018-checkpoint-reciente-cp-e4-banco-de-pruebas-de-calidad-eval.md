## Checkpoint reciente: CP-E4 — Banco de pruebas de calidad (eval harness) (2026-07-03)

### Qué es (lenguaje simple)

- Una herramienta INTERNA para medir si un cambio en Mia **mejora o empeora** la calidad de
  sus análisis, ANTES de confiar en él. Corre a Mia sobre un set de **casos de prueba
  sintéticos** (inventados, sin datos reales de cliente) y puntúa cada resultado con señales
  **objetivas** (sin que otra IA juzgue): cuántas citas quedaron sin respaldo, si el
  diagnóstico trae su cierre estructurado, si produjo borrador. Luego compara "antes vs
  después" y da un veredicto en llano: **mejora / sin cambio / regresión**.
- **No toca datos reales de cliente:** los casos son sintéticos por construcción; correr el
  banco sobre expedientes reales del despacho exige autorización explícita (candado
  fail-closed) — hoy no hay ni pantalla ni caso que lo haga.

### Frontend (Cursor — capa 3): NO aplica

- CP-E4 es una herramienta de **desarrollo/administración por línea de comandos**
  (`execution/run_eval.py`), no una función del producto para el abogado. **No hay UI que
  construir ni revisar.** Un panel de calidad para el despacho podría venir en un checkpoint
  futuro, pero no es parte de este.

### Resultado de verificación (3 capas)

- Capa 1: gate `test_eval_harness.py` **25/25** (scorer determinista; comparador detecta
  regresión/mejora con veredicto fail-safe; casos todos sintéticos; candado de datos reales
  fail-closed; end-to-end por el grafo real con LLM/embeddings stubbeados, incl. que intake
  recupera el expediente sembrado); regresión **ALL PASS (56 suites)** (test_rls HALT).
- Capa 2 (revisor adversarial independiente): candado de datos reales y determinismo de las
  métricas CONFIRMADOS. 1 MAYOR corregido y re-verificado ANTES del commit: el runner sembraba
  los documentos SIN embedding → intake los ignoraba y Mia redactaba "a ciegas" (el banco no
  ejercitaba la recuperación del expediente) → ahora se siembran con embedding como en
  producción y el gate exige que intake recupere el documento. 2 MENORES aceptados (ver
  memory/bugs-and-risks.md Riesgo #51).
- Capa 3: NO APLICA (sin frontend).

---

