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

# CIERRE — 2026-07-22 (2ª sesión) · F1 HECHA + F2 casi entera · EMPEZAR AQUÍ

## Arranque en una terminal nueva (prompt sugerido)

> Lee `HANDOFF.md` y `APRENDIZAJES.md` de `D:\Inteligencia Artificial\Mia-Super Agent\mia` y el plan
> maestro (`C:\Users\USER\.claude\plans\fable-puedes-estructurar-un-sleepy-sifakis.md`). Corre
> `scripts\sonda_salud.ps1` ANTES de nada (y relanza el segador si no está corriendo). Luego arranca la
> pieza grande restante de F2: la **especificación de seguridad de salida POR ORACIÓN** — toda afirmación
> jurídica → su fuente → un pasaje localizable → relación de soporte, o abstención explícita; capa
> determinista para ubicación y respaldo léxico; sondas adversariales de entailment en el banco para la
> implicación semántica; lo no verificable se marca, nunca se certifica. El patrón a seguir es el de la
> omisión de F2.1 (decisión en `graph._verify_draft`, mecánica agnóstica en `verification.py`, informe
> con trazabilidad, gates con mutación y señal positiva). Verificación adversarial independiente antes de
> dar nada por bueno, y cierre con benchmark en vivo N=10 bajo `suscripcion` (gratis, en trozos
> foreground — regla 45 de APRENDIZAJES.md).

Retrospectiva de esta sesión: `Pipe-OS\01-operacion\retrospectivas\retrospective-2026-07-22-007-…`.
Aprendizajes convertidos en regla: `APRENDIZAJES.md` 44-48 (persistencia antes de medir; trozos
foreground; cero-no-ciego; dirección segura según el dueño del texto; sonda de salud) — con sus barreras
ejecutables commiteadas (checks anti-descableado en `test_eval_harness.py`, `scripts/sonda_salud.ps1`).

Rama `feat/fase1-inc1-cleanup-scaffolding`. **F1 quedó ejecutada en su vía principal**: el benchmark vivo
corrió COMPLETO bajo la política `suscripcion` (el modo de venta), coste USD ~0 (solo centavos de
embeddings), y el baseline quedó versionado, AUDITADO contra los crudos por un verificador independiente
(veredicto: NÚMEROS FIELES, 10/10 chequeos) y publicado.

## Los números que importan (detalle en `memory/findings.md`, sección BASELINE F1)

- **La promesa central se sostuvo en las 33 corridas**: ninguna cita sin respaldo llegó al texto sin
  marca — las 3 no respaldadas (caso citas) las anotó el guardián DETERMINISTA (el modelo marcó 0).
  Falsos bloqueos: 0. Éxito de tarea: 33/33.
- **El defecto abierto es la fuga de jurisdicción: 40%** en el caso citas (4/10; la tanda descartada de
  la mañana dio 5/10 — intermitente confirmado con N=20, siempre «arts. 1740 y ss. del CCO»). Es
  exactamente lo que F2 endurece. Los otros dos casos de riesgo: 0/20.
- Latencia (informativa): p50 2,3-6,6 min según caso. Cuota consumida: ~1,6M tokens la tanda.
- Crudos y paneles: `mia-data/eval-runs/f1_susc_*` (agregados + partes + canónicos), prompt_hash
  `e0a4e15a39069bae`. Se re-corre ante cualquier cambio de modelo o prompt.

## Qué se construyó/arregló (commits de esta sesión)

- `ac5ce98` — fix(eval): `--repeat` PERSISTE los crudos y la versión del baseline (antes imprimía y
  tiraba los resultados; sin esto no había ni auditoría ni baseline).
- `8abb855` — feat(eval): `execution/aggregate_eval_runs.py` consolida trozos de `--repeat` en un run
  agregado recalculando panel y fuga DESDE los crudos (aborta si difiere el prompt_hash).
- (este cierre) — harness: `MIA_EVAL_PERSIST_FULL=1` persiste borrador/diagnóstico COMPLETOS (opt-in,
  para el paquete de decisión); `memory/findings.md` con el BASELINE F1; y
  **`docs/f1-paquete-decision-pipe.md`**: 6 salidas ÍNTEGRAS + los 4 ejemplares reales de fuga + las
  4 preguntas de la Sesión A. Ese archivo ES el insumo de la próxima sesión con Pipe.

## El asesino de procesos (léelo antes de correr nada largo)

**Tres tandas largas fueron matadas hoy** (2 lanzadas desacopladas vía WMI, 1 como tarea del harness):
árboles COMPLETOS (powershell+cmd+python) terminados sin rastro en Event Log; no fue Defender, ni el
segador, ni OOM; LiteLLM (python, vivo desde la víspera) sobrevivió — no es un barrido general y la causa
sigue SIN identificar. **La defensa que funcionó** (y es ahora el método estándar): trabajo largo en
TROZOS foreground (`--repeat 1..2`, <10 min por comando — el foreground completó el 100% de las veces),
persistencia por trozo, y agregación posterior. Además: los zombis de statusline REAPARECIERON (3.346,
CPU 100%, 1,3 GB RAM libre — el segador de 8 h se había apagado solo); matarlos y relanzar el segador es
lo primero ante cualquier lentitud.

## F2.1 HECHO en esta misma sesión: la fuga pasó de sugerencia a control (`e0c1634`+`e743c63`)

Bajo jurisdicción desconocida, toda cita sin respaldo (ni corpus, ni ancla, ni el MENSAJE del abogado —
carve-out del principio «input fidedigno», hallazgo MAYOR de la revisión adversarial independiente) se
OMITE del texto ANTES de emitirse; el DIAGNÓSTICO también pasa por el guardián (estaba fuera y F1 midió
fugas en él); el informe de omisiones viaja al abogado (payload HITL). **Re-corrida en vivo N=10 del caso
citas (mismo prompt_hash): citas sin respaldo emitidas 3→0; el guardián interceptó EN VIVO 2 extrapolaciones
del modelo (corrida 6); cobertura de respaldo 50%→100%; falsos bloqueos 0; sin costo de latencia.** La fuga
"cruda" bajó 40%→20% y el 20% restante es el memo SELLADO referido con ancla (disciplina correcta). Detalle
en `memory/findings.md` §F2.1. Suites: 26/26 nueva + 53/53 + 57/57 + 59/59 + 104/104 + 50/50.

## También en esta sesión: dos ítems más de F2 CERRADOS

- **`## aprendido` aprende de las CORRECCIONES** (`d5bcc51`): el path `decision=='editing'` de hitl.py
  quedó cableado con `SOURCE_CORREGIDO` (estaba sin conectar aunque el módulo lo soportaba). Gate H nuevo
  en test_aprendido (34/34); test_hitl_flow 21/21.
- **Sonda de instalabilidad PASÓ** (adelanto de F5 que el plan manda correr al cierre de F2): backend
  re-compilado (466,5 MB, smoke OCR OK) y `--first-run` contra clúster scratch desde cero → initdb + rol +
  44 migraciones + checkpointer + «Mia puede arrancar», y la SEGUNDA corrida es idempotente (0
  actualizaciones, .env con secretos byte a byte intacto; apaga su postgres al salir). El hueco que F5
  documentaba («el exe actual NO trae --first-run ni las migraciones») quedó cerrado por este build.
- Lectura agéntica bajo `cli-*`: DECLARADA como limitación conocida (el código la detecta con
  `agentic_reading_available()` y no cobra de más); «arreglar» espera el delta on/off de la corrida de
  referencia en nube.

## Qué sigue (en orden)

1. **Sesión Pipe A** con `docs/f1-paquete-decision-pipe.md`: juzgar la calidad jurídica de las 6
   salidas + las 4 decisiones (RISK_CASES por defecto; prioridades restantes de F2; disparar OAuth/Trusted
   Signing; desdeclarar Modo A). Nota: las salidas del paquete son PRE-F2.1 (el endurecimiento no las
   invalida: ninguna tenía citas sin respaldo).
2. **Resto de F2** (plan maestro): la pieza grande que queda es la especificación de seguridad de salida
   POR ORACIÓN (toda afirmación jurídica → fuente → pasaje localizable → soporte, o abstención); su banco
   de sondas adversariales de entailment.
3. **Referencia en nube** (opcional, espera el OK de Pipe al tope de USD 30): RISK_CASES ×10 bajo `nube`
   + `--agentic-compare`.

## Pendientes de Pipe (acumulados)

1. Aprobar el borrado de 7 ramas remotas ya fusionadas (verificado commit a commit, sesión anterior).
2. Aprobar la tarea programada permanente del segador de statusline (hoy volvió a hacer falta).
3. Decidir si se conserva `origin/claude/arranque-fptz34` (2 commits de docs de la sesión 45).
4. Aprobar (o no) el tope de USD 30 para las corridas de REFERENCIA en nube (el baseline principal ya
   está hecho y fue gratis).

---

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

