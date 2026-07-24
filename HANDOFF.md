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

# CIERRE — 2026-07-24 (2ª sesión) · Re-baseline con el prompt de #43-#44: la promesa se sostiene · EMPEZAR AQUÍ

## Arranque en una terminal nueva (prompt sugerido)

> Lee `HANDOFF.md` y `APRENDIZAJES.md` de `D:\Inteligencia Artificial\Mia-Super Agent\mia` y el plan
> maestro (`C:\Users\USER\.claude\plans\fable-puedes-estructurar-un-sleepy-sifakis.md`). Corre
> `scripts\sonda_salud.ps1` ANTES de nada; venimos de un REINICIO de la máquina — si la DB
> portable (55432) no acepta conexiones, arráncala primero (clúster en `tools/pgdata-portable`,
> ver `memory` del repo / trampas de entorno). El re-baseline está PAGADO (`memory/findings.md`
> §RE-BASELINE, hash `3391f17ea61324a4`) y la especificación POR ORACIÓN está IMPLEMENTADA y
> verificada (`9fce76a`). Trabajo en curso INTERRUMPIDO por el reinicio: **las 3 sondas
> adversariales nuevas ×10 en vivo** bajo `suscripcion` con `MIA_EVAL_PERSIST_FULL=1`, en
> trozos foreground `--repeat 1` (regla 45; ~5-7 min por corrida). Estado exacto:
> `entailment-cita-real-no-sostiene` va 3/10 (partes `f2sond_entail_smoke` [sin persist-full],
> `_b`, `_c` — todas limpias, 0 fuga, éxito 1/1); faltan `_d.._j`. Después
> `afirmacion-juridica-sin-cita` ×10 (`f2sond_sincita_a..j`) y `soporte-cruzado-mal-anclado`
> ×10 (`f2sond_cruzado_a..j`), 0/10 ambas. Comando por trozo:
> `.venv\Scripts\python.exe execution\run_eval.py --case <id> --repeat 1 --run-id <parte>
> --session-id cli-<fecha>` con `$env:MIA_EVAL_PERSIST_FULL='1'`. Agregar con
> `aggregate_eval_runs.py` (`--out f2sond_<caso>_n10`), leer el residuo por oración
> (`verification.oraciones`) y las intercepciones de los crudos, publicar en findings +
> paquete de Sesión A (la sonda de entailment es de REVISIÓN HUMANA: sus borradores completos
> van al paquete). Si Pipe está disponible: Sesión Pipe A primero.

Rama `feat/fase1-inc1-cleanup-scaffolding`.

## Qué pasó en esta sesión (2026-07-24, 2ª)

1. **Re-baseline N=10 ×2 casos de riesgo bajo `suscripcion` (USD ~0,0004, solo embeddings)** —
   la deuda declarada de #43/#44. Resultado: **la promesa central se sostiene con el prompt
   nuevo**. Caso citas: 0 citas sin respaldo emitidas, cobertura de respaldo 100%, falsos
   bloqueos 0, éxito 10/10, fuga cruda 3/10 pero las 3 son el memo SELLADO referido con ancla
   `[doc 1]` (disciplina correcta, verificado crudo por crudo) → fuga real efectiva 0/10; p50
   371 s (levemente MEJOR que antes pese al prompt más grande). Caso fuga: 0/10 limpio, p50
   204 s. Números completos y comparación de tres líneas: `memory/findings.md` §RE-BASELINE.
2. **Hallazgo de método**: las 3 corridas en vivo del cierre anterior (`f2std_citas_a`/
   `f2std_fuga_a`) tenían prompt_hash intermedio `3c8cbd38` ≠ el del estado final de `bc90628`
   (`3391f17ea61324a4`) — quedaron FUERA del agregado; el re-baseline es 100 % fresco. Crudos:
   `mia-data/eval-runs/f2std_citas_n10` (partes b..k) + `f2std_fuga_n10` (partes b..f).
3. **Cero no ciego declarado (regla 46)**: el guardián ejecutó 0 omisiones porque no hubo qué
   interceptar; la señal positiva del mecanismo vive en el fake desobediente de las suites y en
   la interceptación en vivo del 2026-07-22.
4. Limpieza quirúrgica en `memory/findings.md`: los ítems 5-7 + síntesis de la sección Hermes
   (skills self-improving) estaban huérfanos tras §F2.1 por un accidente de inserción;
   reubicados dentro de su sección.
5. Sonda de salud en verde toda la sesión (0 zombis de statusline, DB portable arriba, tarea
   del segador "Ready").
6. **El DISEÑO de la especificación por oración quedó HECHO y refutado** (misma sesión, más
   tarde): `docs/diseno-f2-espec-por-oracion.md` (diseñador Opus) + refutación adversarial
   independiente en `docs/diseno-f2-espec-por-oracion-refutacion.md` (veredicto: APRUEBA CON
   CORRECCIONES — 4 MAYORES incl. un import circular bloqueante + 8 menores, TODOS integrados
   al diseño con una discrepancia razonada registrada en §8/D2). Idea central que sobrevivió a
   la refutación: la segmentación alimenta SOLO el informe — por construcción no puede causar
   ni fuga ni falso bloqueo; las decisiones de marcar/omitir siguen saliendo de
   `annotate_draft`. El diseño NO toca `prompt_builder.py` (el hash `3391f17ea61324a4` se
   mantiene).

7. **La especificación por oración quedó IMPLEMENTADA y commiteada (`9fce76a`)**, con la
   cadena completa de verificación: implementación Opus → verificación cruzada Codex xhigh
   (APRUEBA CON CORRECCIONES: 4 MAYORES + 3 menores, TODOS integrados — incluida su prueba
   empírica de 292 comparaciones vs HEAD y 500 corridas on/off sin un byte de diferencia) →
   re-corrida independiente del orquestador. Suites: 47/47 nueva (`test_sentence_report`),
   61/61 harness, 104/104 agnosticismo, HALT completo. `prompt_builder.py` INTACTO (hash
   `3391f17ea61324a4` — el RE-BASELINE sigue vigente). 3 sondas adversariales nuevas en
   RISK_CASES (la de implicación semántica pura declarada REVISIÓN HUMANA; las otras dos con
   oráculo determinista). Smoke ×1 de `entailment-cita-real-no-sostiene` EN VIVO: corre de
   punta a punta y el informe `oraciones` viaja en el crudo (79 oraciones, residuo
   informativo 17 — la señal no está ciega). Decisiones de alcance del orquestador: vista UI
   por oración DIFERIDA declarada a F3-honestidad-UX; procedencia por oración vive en scoring
   (donde existe el contexto del turno), verification.py queda agnóstico.

## Qué sigue (en orden)

1. **Correr las 3 sondas nuevas EN VIVO ×10** (`entailment-cita-real-no-sostiene`,
   `afirmacion-juridica-sin-cita`, `soporte-cruzado-mal-anclado`) bajo `suscripcion`, en
   trozos foreground (regla 45; el smoke dio ~6,6 min/corrida), agregando con
   `aggregate_eval_runs.py`; leer el residuo por oración de los crudos y llevar los
   resultados (junto con la sonda de implicación, que es de REVISIÓN HUMANA) al paquete de
   la Sesión Pipe A.
2. **Lo que queda de F2** tras esto: decisión con evidencia sobre lectura agéntica por
   defecto (espera el delta on/off de la referencia en nube) y el ítem 2 de la spec (fuga
   detectada al 100% de ocurrencias — el RE-BASELINE ya muestra fuga real 0, falta el caso
   de ataque con falsos positivos medidos).
2. **Sesión Pipe A** con `docs/f1-paquete-decision-pipe.md`: calidad de las 6 salidas + las 4
   decisiones + priorizar el backlog ruflo dentro de F2.
3. **Referencia en nube** (tope USD 30 ya aprobado): RISK_CASES ×10 bajo `nube` +
   `--agentic-compare`.

## Pendientes de Pipe

Ninguno bloqueante. Lo único que espera de Pipe es la **Sesión A** (juzgar calidad + 4
decisiones + prioridades del backlog ruflo).

---

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
