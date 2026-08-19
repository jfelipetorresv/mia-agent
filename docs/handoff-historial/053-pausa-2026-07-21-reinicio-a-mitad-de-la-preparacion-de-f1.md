# PAUSA — 2026-07-21 · reinicio de máquina a mitad de la preparación de F1

Rama `feat/fase1-inc1-cleanup-scaffolding`. **F0 está completa y PUSHEADA** (hasta `dad662e`). Esta pausa es
a mitad de la PREPARACIÓN de F1 (cerrar la deuda de dinero + demostrar que el banco puede fallar, ANTES de
gastar contra el modelo). Nada se ha gastado aún de forma seria.

## Cómo retomar (en orden)

1. **Reiniciar servicios** (el reinicio los mató; la DB portable 55432 puede volver sola o no):
   - LiteLLM :4000 → `scripts/start_litellm.ps1` **con `run_in_background` del harness** (si no, muere).
   - DB 55432: si no está, `pg_ctl` según `scripts/setup_db.ps1` (lee puerto del `.env`).
   - Verificar con `curl -s http://127.0.0.1:4000/health/liveliness` (debe dar 200) antes de gastar.
2. **Primera sonda ante cualquier lentitud rara: contar `node.exe`.** Los zombis de `statusline.js` ya
   tienen la causa raíz arreglada (ver cierre de F0), pero si reaparecen, matar solo los `statusline`.
3. **Retomar la ronda 2 de preparación de F1: solo falta VERIFICAR** (las correcciones ya están aplicadas).

## Qué quedó a medias (estado exacto)

**Preparación de F1 = 3 frentes.** Frente **B APROBADO Y COMMITEADO** (`b86b15a`: el banco demuestra que
sabe reprobar — 50 mutaciones plantadas + holdout intocable con manifiesto de hashes).

Frentes **A (dinero) y C (panel): ronda 1 rechazada, ronda 2 aplicada pero SIN VERIFICAR.** Las correcciones
de la ronda 2 están en el commit **WIP `f284bcf` (marcado, local, sin push)** — hay que RE-VERIFICARLAS
con un pase adversarial fresco + Codex xhigh ANTES de darlas por buenas. Los reportes de corrección de esa
ronda están guardados en el scratchpad de la sesión:
`…/scratchpad/f1prep_ronda2_fixes.json` (por si el scratchpad no sobrevive, el resumen está abajo).

**Defectos que la ronda 2 dice haber cerrado (verificar cada uno EJECUTANDO):**
- **A-BLOQ** (lo reprodujo Codex con un proxy local): el SDK reintenta por dentro (`max_retries=2`) y solo
  expone el error final; se devolvía la reserva de intentos que SÍ salieron al proveedor. Arreglo: los
  reintentos los hace MIA (`max_retries=0` en el cliente), cada uno reservado por separado. **Verificar con
  un proxy propio que reciba N POST y luego rechace.**
- **A-MAY1**: `metrics/usage.py` (PRODUCCIÓN) no tarifaba el caché (escritura 2x fuera de `prompt_tokens`,
  lectura 0.1x dentro). Arreglo: mismo desglose de tres cubos que `spend_guard.real_call_cost`. **Verificar
  que una fila SIN caché registra idéntico a antes, y `enforce_budget` sigue fail-open.**
- **A-MAY2** (tmp + ledger): el gate creaba temporales dentro del repo (81/83) y un call-site
  (`test_eval_harness.py:431`) filtraba al libro REAL con sesión `inapp-<fecha>`. **Verificar 83/83 y que el
  hash de `mia-data/eval-runs/spend_ledger.json` no cambia al correr los gates.**
- **A-MEN**: los embeddings cobran toda falla de red (dirección segura); declarado.
- **A-ABIERTO**: limpieza del residuo pre-existente del libro real (sesiones `default`/`smoke-f05`) y dos
  artefactos gitignoreados en la raíz (`.tmp/`, `mia-spend-guard-f478svfq`). Cosmético, no bloquea.
- **C-MAY1**: la frecuencia de fuga de jurisdicción se medía sobre 1.200 de ~15.656 caracteres (el 8% del
  borrador) → leería "cero fuga" por construcción. Arreglo: medir sobre el texto COMPLETO en `run_case`.
  **Verificar con un borrador >15k con la fuga después del carácter 1200.**
- **C-MAY2**: la métrica estrella (falsos bloqueos / `precision_respaldo`) no estaba protegida — mutar el
  denominador dejaba la suite verde. Arreglo: asertos con valores conocidos. **Verificar mutando el
  denominador → la suite debe ponerse ROJA.**
- **C-MEN**: `precision_respaldo` podía imprimir negativo; se le puso clamp.

**Verificación interrumpida**: de los 3 verificadores de la ronda 2, solo volvió 1 (parcial,
`EVIDENCIA_INSUFICIENTE` — NO es un veredicto, la corrida se cortó). Re-verificar los tres desde cero.

El workflow de la ronda 2 fue detenido a propósito (no se puede reanudar cross-sesión). El script vive en
`…/workflows/scripts/mia-f1-prep-ronda2-wf_4e096384-1d0.js`; su fase «Corregir» YA corrió (no re-correrla:
duplicaría ediciones), solo hace falta rehacer la fase «Verificar».

## Decisiones de Pipe de esta sesión (no reabrir)

- **La calidad manda sobre el reloj** (2026-07-21): los 10 minutos dejan de ser puerta; la latencia se mide
  y reporta, ningún gate falla por tiempo. Lo absoluto sigue siendo: cero afirmaciones sin respaldo.
- **El modo PRINCIPAL del producto es la SUSCRIPCIÓN del abogado** (Claude Code/Codex/Antigravity), no la
  nube. El baseline de F1 debe aprobar bajo `suscripcion` (coste USD 0 → el benchmark principal es GRATIS,
  N=10 sin tocar el tope); la nube es referencia. Verificado en esta sesión que el CLI `claude -p` anidado
  responde, así que el benchmark del modo primario es viable desde aquí. Consecuencia ascendida a defecto:
  bajo `cli-*` el bucle de lectura agéntica NO corre → capacidad que le falta al modo de venta; arreglar o
  declarar. El "USD 0,31/turno" de F0.5 era SOLO el modo nube.

## Pendiente de Pipe

- Nada bloqueante. Cuando retome: aprobar (o no) que las corridas de REFERENCIA en nube usen el tope de
  USD 30, aunque probablemente ni haga falta porque el modo principal es gratis.
