# CIERRE — 2026-07-24 · El criterio de Pipe entró a MIA: decisiones #43-#44 + backlog ruflo

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
   declarada de #43/#44). → HECHO en la sesión siguiente (entrada de arriba).
2. **Sesión Pipe A** con `docs/f1-paquete-decision-pipe.md`: calidad de las 6 salidas + las 4
   decisiones + AHORA TAMBIÉN priorizar el backlog ruflo dentro de F2.
3. **Resto de F2**: especificación de seguridad de salida POR ORACIÓN + banco de sondas
   adversariales de entailment (la pieza grande del plan maestro).
4. Referencia en nube (tope USD 30 ya aprobado): RISK_CASES ×10 bajo `nube` + `--agentic-compare`.

## Pendientes de Pipe

Ninguno bloqueante. Lo único que espera de Pipe es la **Sesión A** (juzgar calidad + 4 decisiones +
prioridades del backlog ruflo).

---
