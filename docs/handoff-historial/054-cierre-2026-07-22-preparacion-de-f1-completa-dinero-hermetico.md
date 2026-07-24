# CIERRE — 2026-07-22 · Preparación de F1 COMPLETA: dinero hermético en 5 rondas + limpieza

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

