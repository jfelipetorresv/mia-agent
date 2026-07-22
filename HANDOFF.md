# HANDOFF — Mia (traspaso a Cursor)

> **PLAN MAESTRO VIGENTE (aprobado por Pipe 2026-07-21):**
> `C:\Users\USER\.claude\plans\fable-puedes-estructurar-un-sleepy-sifakis.md` — "Dejar MIA funcionando
> en los términos de la visión". Fases F0→F6 + 2 sesiones de Pipe; dynamic workflows con matriz
> Opus/Sonnet/Haiku/Codex; refutado por Codex en xhigh. El prompt de arranque está en su sección
> «Arranque en una terminal nueva». Toda sesión de implementación empieza leyendo ese plan + la
> entrada más reciente de este archivo.

---

## Cómo usar este archivo (regla de mantenimiento)

Aquí viven SOLO la entrada vigente («EMPEZAR AQUÍ») y la inmediatamente anterior.
Al escribir una entrada nueva: mover la más vieja de las dos a `docs/handoff-historial/`
con el siguiente número (`NNN-titulo.md`) y agregarla arriba del todo en su `INDICE.md`.
El historial completo está en `docs/handoff-historial/INDICE.md`. Nada se borra.

---

# CIERRE — 2026-07-22 · Preparación de F1 COMPLETA: dinero hermético en 5 rondas + limpieza · EMPEZAR AQUÍ

Rama `feat/fase1-inc1-cleanup-scaffolding`, pusheada hasta `bfb9123`. **La preparación de F1 terminó**: el
banco sabe reprobar (frente B, `b86b15a`), el panel es confiable (43/43) y el control de dinero quedó
hermético y CERTIFICADO POR EJECUCIÓN tras 5 rondas de corrección↔verificación adversarial cruzada
(Opus verifica, Codex xhigh refuta — dos veces encontró huecos críticos que Opus había aprobado).

## Lo que quedó cerrado (commits de esta sesión)

- `f284bcf`+`34f77e1` — caché tarifado en producción (6,15 vs 6,00), reintentos del SDK y del PROXY
  apagados (`router_settings.num_retries: 0` en ambas configs, pin anti-deriva en `check_env_pins` 12/12),
  gate vivo `test_litellm_proxy_retries.py`: una invocación = exactamente 1 POST (control con reintentos
  = 3 POST). Temporales del harness migrados al helper común `execution/_tmp_desechable.py` (HALT antes de
  crear dentro del repo). Panel: fuga de jurisdicción medida sobre el texto COMPLETO y métrica estrella
  protegida por valores exactos.
- `bfb9123` — el crítico final de Codex: el presupuesto MENSUAL del despacho ahora reserva y liquida POR
  INTENTO dentro de `_invoke_metered` (antes: 4 fallos reales = USD 0 contabilizados; ahora 4 estimaciones;
  éxito sin `usage` cobra estimación, nunca 0; solo lo demostrable-no-enviado se devuelve). Suscripción
  `cli-*` intacta (coste 0, sin reserva). Gate 12/12 con vía del cliente REAL (mutar `max_retries` → ROJO)
  y `test_model_policy` 43/43 con los 3 checks de regresión no-ciegos.
- `643f1df` — este HANDOFF quedó liviano (15 KB): solo vigente + anterior; historial completo en
  `docs/handoff-historial/INDICE.md` (regla de mantenimiento arriba).
- `cd4df62` — limpieza fase B: 11 menciones de "Modo A" reescritas como hipótesis futura (nunca existió);
  3 planes ejecutados a `memory/archivo/` (plan-f2 se queda: un test lo cita).
- Limpieza fase A (sin commit, artefactos fuera de git): ~14 GB de builds regenerables borrados
  (`target/`, `packaging/dist|build`, `.next`, `.tmp/`), rama local `feature/robustecimiento-sin-aws`
  eliminada (0 commits únicos). El inventario completo concluyó: **no hay código muerto** en backend,
  frontend ni configs.

## Estado del veredicto de Codex (la garantía y su alcance)

La sesión de eval en nube con tope USD 30 quedó con techo efectivo **USD 29,87712** garantizado
(reproducido ejecutando). Su crítico restante (presupuesto mensual por alias) se cerró en `bfb9123` y un
verificador adversarial fresco lo aprobó ejecutando las sondas exactas de Codex. El modo PRINCIPAL sigue
siendo la suscripción del abogado (coste 0, cuota) — el tope USD protege solo las corridas de referencia.

## Próximo paso: F1 propiamente (specs/todo/01-f1-benchmark-vivo.md)

Benchmark vivo bajo `suscripcion` (N=10 GRATIS con `cli-claude`), nube como referencia con el tope ya
certificado. La latencia se MIDE, nunca reprueba (decisión de Pipe). Antes de gastar en nube: releer la
sección de deuda del cierre de F0 (archivo `052` del historial).

## Entorno (léelo antes de arrancar servicios)

- **LiteLLM :4000**: `scripts/start_litellm.ps1` con `run_in_background`; su config runtime vive en
  `%TEMP%\mia-litellm-runtime\` (ya NO en `.tmp/`). Corre con `num_retries: 0`.
- **Los zombis de statusline NO están resueltos**: el vigilante interno del script no alcanza a correr
  (node se cuelga antes del event loop); 573 acumulados en 2,5 h saturaron la máquina y tumbaron a Codex.
  Mitigación de sesión: `C:\Users\USER\.claude\statusline-reaper-loop.ps1` lanzado desacoplado (WMI,
  se apaga solo a las 8 h). La tarea programada permanente espera aprobación de Pipe.
- **Algo mata las tareas de fondo del harness en bloque** (ocurrió 4+ veces esta sesión, causa sin
  identificar): los procesos largos críticos (LiteLLM, Codex) se lanzan desacoplados vía
  `Invoke-CimMethod Win32_Process Create` y se vigilan con un bucle relanzable — el patrón está probado.
- Residuo conocido: `mia-spend-guard-f478svfq/` y `mia-harness-ledger-j2c3gbkl/` (vacías, ACL de otro
  contexto, exigen admin para borrarse; invisibles para git).

## Pendientes de Pipe

1. Aprobar el borrado de 7 ramas remotas ya fusionadas y sin trabajo único (verificado commit a commit).
2. Aprobar la tarea programada permanente del segador de statusline (cada 5 min, mata solo >30 s de vida).
3. La rama `origin/claude/arranque-fptz34` tiene 2 commits de docs de la sesión 45: decidir si se conserva.
4. Sin nada bloqueante: F1 puede arrancar bajo suscripción sin gastar un dólar.

---

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

---

