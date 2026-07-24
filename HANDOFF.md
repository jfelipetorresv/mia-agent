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

# CIERRE — 2026-07-24 · El criterio de Pipe entró a MIA: decisiones #43-#44 + backlog ruflo · EMPEZAR AQUÍ

## Arranque en una terminal nueva (prompt sugerido)

> Lee `HANDOFF.md` y `APRENDIZAJES.md` (reglas nuevas 49-51) de
> `D:\Inteligencia Artificial\Mia-Super Agent\mia` y el plan maestro
> (`C:\Users\USER\.claude\plans\fable-puedes-estructurar-un-sleepy-sifakis.md`). Corre
> `scripts\sonda_salud.ps1` ANTES de nada (ahora también chequea la DB portable; la tarea programada
> del segador ya es permanente). Primer trabajo: **re-medir el baseline con el prompt nuevo** —
> el prompt_hash cambió con las decisiones #43-#44 (`memory/decisions.md`), así que la línea base
> `e0a4e15a39069bae` quedó desactualizada: correr `disciplina-citas-formas-abreviadas` ×10 y
> `fuga-jurisdiccion-contrato-sin-pais` ×10 bajo `suscripcion` (gratis), en TROZOS foreground
> `--repeat 1..2` <10 min (regla 45), agregando con `execution/aggregate_eval_runs.py`, y comparar
> contra el baseline F1 (`memory/findings.md` §BASELINE F1). OJO al leer el panel: en el caso citas,
> la mención del memo sellado CON ancla es disciplina correcta aunque el escáner crudo la cuente
> (regla del 20% residual). Después: el resto de F2 (especificación de seguridad de salida POR
> ORACIÓN) o la Sesión Pipe A si Pipe está disponible.

Retrospectiva de esta sesión: `Pipe-OS\01-operacion\retrospectivas\retrospective-2026-07-24-001-mia-destilacion-principios.md`.
Aprendizajes convertidos en regla: `APRENDIZAJES.md` 49-51 (alcance en destilaciones + verificación
adversarial obligatoria para prompt core; prompts que alimentan parsers; MSYS_NO_PATHCONV para `!`)
— con barreras: checks `std-1..std-5` en `test_prompt_builder.py` (51/51) y sonda de salud ampliada.

Rama `feat/fase1-inc1-cleanup-scaffolding`, pusheada hasta este cierre.

## Qué pasó en esta sesión (2026-07-23 → 24)

1. **Los 4 pendientes de Pipe: APROBADOS Y EJECUTADOS.** Ramas remotas prescindibles borradas (solo
   quedan `main` y esta rama; los 2 docs únicos de arranque-fptz34 rescatados en `abd1a25`), tarea
   programada permanente del segador creada y verificada, tope USD 30 de referencia en nube
   APROBADO (habilita RISK_CASES ×10 bajo `nube` + `--agentic-compare`).
2. **Decisión #43 (`48d0ed5`)**: el manual de litigio de Pipe (metodologia-fable, 56 reglas) entró
   DESTILADO al prompt core — L2 pasa a SEIS elementos con postura de litigio, catálogo de
   confrontación, arquitectura del escrito, exhaustividad→selección y pasada del adversario; L8
   facts/analysis/draft con lo operativo. Cero identidad, cero país (gate 104/104). La verificación
   adversarial independiente encontró 2 MAYORES de ALCANCE que se corrigieron (adversarial
   condicionado a encargos adversariales; transcripción de norma condicionada a ordenamiento
   declarado).
3. **Decisión #44 (`bc90628`)**: 5 skills más como PRINCIPIOS — Sala de estrategia (franqueza,
   vacíos-como-preguntas, moderador que RESUELVE sin promediar y escribe DENTRO de los campos del
   dictamen), `## aprendido` con vectores Funciona/Evitar/Lección + dedup ciego al vector,
   pasada final de auto-verificación en draft, ficha de ESTÁNDAR DE CALIDAD por despacho en la
   entrevista de guías (calidad = estructura + defectos, no puntaje), y convo-review resuelto:
   ya está cubierto por `traces` FTS cross-asunto (candidato declarado: consulta espontánea).
4. **Análisis ruflo (`c6c9665`, `memory/findings.md` §RUFLO)**: claude-flow renombrado; VETO de
   instalación (telemetría+monetización sin disclosure, historial de fachadas); 5 ideas
   destilables al backlog — decaimiento de confianza en lo aprendido (ALTA), consolidación
   post-turno en cola presupuestada (ALTA), manifiesto sellado por entregable (MEDIA-ALTA,
   candidata comercial), routing justificado (MEDIA), promoción explícita de memoria (MEDIA).
   Valida el modo suscripción como modelo de negocio.
5. **Verificación**: 2 rondas adversariales (11 hallazgos reales corregidos), 12 corridas de suites
   en verde, 3 corridas EN VIVO con el prompt nuevo (fuga ×2 limpias; citas ×1 con disciplina
   correcta — 2/2 respaldadas con ancla al memo sellado), USD 0.

## Qué sigue (en orden)

1. **Re-medir el baseline** N=10 con el prompt nuevo (ver prompt de arranque — es la deuda
   declarada de #43/#44).
2. **Sesión Pipe A** con `docs/f1-paquete-decision-pipe.md`: calidad de las 6 salidas + las 4
   decisiones + AHORA TAMBIÉN priorizar el backlog ruflo dentro de F2.
3. **Resto de F2**: especificación de seguridad de salida POR ORACIÓN + banco de sondas
   adversariales de entailment (la pieza grande del plan maestro).
4. Referencia en nube (tope USD 30 ya aprobado): RISK_CASES ×10 bajo `nube` + `--agentic-compare`.

## Pendientes de Pipe

Ninguno bloqueante. Lo único que espera de Pipe es la **Sesión A** (juzgar calidad + 4 decisiones +
prioridades del backlog ruflo).

---

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

---

