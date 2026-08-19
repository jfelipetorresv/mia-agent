# CIERRE — 2026-07-22 (2ª sesión) · F1 HECHA + F2 casi entera

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

## Pendientes de Pipe — TODOS APROBADOS Y EJECUTADOS el 2026-07-23

1. **Ramas remotas BORRADAS** (Pipe ejecutó el push --delete con `!`; el clasificador lo bloquea al
   agente). Solo quedaban 3 prescindibles: `claude/arranque-fptz34` (sus 2 docs únicos RESCATADOS a
   esta rama en `abd1a25` — runbook F4 + capa 3 pendiente de sesión 45),
   `claude/cory-legal-analysis-comparison-4f064p` (efecto neto cero: 2 análisis + 2 reverts) y
   `feature/robustecimiento-sin-aws` (0 commits únicos vs esta rama, verificado). Quedan solo `main` y
   esta rama.
2. **Segador de statusline: tarea programada PERMANENTE creada y verificada** (`statusline-reaper`,
   cada 5 min, estado "Listo"). También la creó Pipe con `!` — gotcha: en Git Bash anteponer
   `MSYS_NO_PATHCONV=1` o los `/Flags` de schtasks se convierten en rutas.
3. **Tope USD 30 para corridas de referencia en nube: APROBADO.** La referencia RISK_CASES ×10 bajo
   `nube` + `--agentic-compare` queda habilitada (techo certificado USD 29,88).
