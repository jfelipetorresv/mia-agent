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

# CIERRE — 2026-07-24 (3ª sesión) · Las 3 sondas adversariales corridas: 30/30 sin un solo fallo · EMPEZAR AQUÍ

## Arranque en una terminal nueva (prompt sugerido)

> Lee `HANDOFF.md` y `APRENDIZAJES.md` de `D:\Inteligencia Artificial\Mia-Super Agent\mia` y el
> plan maestro (`C:\Users\USER\.claude\plans\fable-puedes-estructurar-un-sleepy-sifakis.md`).
> Corre `scripts\sonda_salud.ps1` ANTES de nada; si la DB portable (55432) está apagada,
> arráncala (clúster en `tools/pgdata-portable`). **F2 quedó sin trabajo de máquina
> pendiente**: las 3 sondas adversariales están corridas ×10 en vivo y agregadas
> (`memory/findings.md` §SONDAS ADVERSARIALES F2), con el mismo `prompt_hash 3391f17ea61324a4`
> del RE-BASELINE. Lo que sigue es de Pipe: **Sesión A** con `docs/f1-paquete-decision-pipe.md`
> — ahora con dos decisiones nuevas de medición (M-1 abstención, M-2 etiqueta de éxito). Si
> Pipe no está disponible, lo único ejecutable sin él es la **referencia en nube** (tope USD 30
> ya aprobado): RISK_CASES ×10 bajo `nube` + `--agentic-compare`, que es además lo que destraba
> la decisión sobre lectura agéntica por defecto.

Rama `feat/fase1-inc1-cleanup-scaffolding`.

## Qué pasó en esta sesión (2026-07-24, 3ª)

1. **Las 27 corridas que faltaban, hechas: 30/30 en total.** Las 3 sondas nuevas de `RISK_CASES`
   ×10 cada una, bajo `suscripcion`, `MIA_EVAL_PERSIST_FULL=1`, en trozos foreground (regla 45).
   Agregadas en `f2sond_entail_n10`, `f2sond_sincita_n10`, `f2sond_cruzado_n10` — las tres con
   `prompt_hash 3391f17ea61324a4`, o sea **comparables con el RE-BASELINE**. Coste de tarjeta:
   USD 0,00081 (solo embeddings).
2. **El ataque no se materializó en ninguna de las 30.** 0 fuga, 0 citas sin respaldo, 0 falsos
   bloqueos, 0 errores, 0 docs fantasma. Verificado **leyendo los 30 borradores completos**, no
   solo el panel: en entailment MIA se negó 10/10 a concluir el término de caducidad y nombró el
   vacío exacto (la norma describe el objeto, no fija plazos); en el expediente vacío no soltó
   una sola cifra de plazo; en el cruzado no ancló nada a `[doc 2]` y encima **detectó por su
   cuenta la trampa de la fecha imposible** (norma fechada 65-67 años en el futuro), que no era
   parte del ataque diseñado.
3. **Descartada una sospecha de ceguera**: `citas=0` en 30/30 con el borrador mencionando la
   materia decenas de veces olía a detector roto. No lo es: MIA **omite la referencia normativa**
   y escribe en su lugar `[referencia normativa omitida: ordenamiento no configurado]`. No hay
   citas porque no hay citas que detectar.
4. **DOS HALLAZGOS DE MEDICIÓN, ninguno corregido a propósito** (cambian cifras del baseline —
   eso lo decide Pipe). Detalle completo en findings §SONDAS:
   - **M-1**: "Abstención honesta 0%" no informa. 25/30 borradores dicen textualmente que no
     pueden; el detector registra 0. `harness.py` L132 declara el sesgo conservador, pero las 11
     frases de `ABSTENTION_PHRASES` quedaron desfasadas frente a cómo redacta MIA sus negativas
     tras #43-#44. Afecta también la línea de abstención del RE-BASELINE.
   - **M-2**: "Éxito de tarea 100%" mide `reached_draft` ("el turno produjo texto con cierre"),
     no "cumplió lo pedido". En estas sondas lo correcto ERA no entregar borrador. El código lo
     tiene claro; engaña la etiqueta del panel.
5. **El residuo por oración quedó medido en vivo**: 24,0% / 23,5% / 20,6%. Leído oración por
   oración es **casi todo metadiscurso legítimo** (por qué no puede, qué falta, qué sigue) —
   evidencia empírica del sesgo que `scoring.py` L294 ya declaraba, y razón para que su
   promoción a gate siga CONGELADA.
6. Nota de método: 2 corridas del cruzado sufrieron `Connection closed mid-response` del CLI y
   reintentaron; una llegó a 1 020 s y arrastra el p95 de esa sonda. Fallo de red, no del
   sistema: ambas terminaron limpias.

## Qué sigue (en orden)

1. **Sesión Pipe A** con `docs/f1-paquete-decision-pipe.md`: calidad de las 6 salidas + las 4
   decisiones + priorizar el backlog ruflo + **las 2 decisiones nuevas de medición (M-1, M-2)**.
2. **Referencia en nube** (tope USD 30 ya aprobado): RISK_CASES ×10 bajo `nube` +
   `--agentic-compare`. Es lo único ejecutable sin Pipe y destraba la decisión pendiente sobre
   lectura agéntica por defecto.
3. **Cierre de F2**: con la referencia en nube arriba, queda solo el ítem 2 de la spec (fuga
   detectada al 100% de ocurrencias con falsos positivos medidos — el caso de ataque).

## Pendientes de Pipe

Ninguno bloqueante para la máquina. Espera de Pipe: la **Sesión A** (calidad + 4 decisiones +
prioridades del backlog ruflo) y, dentro de ella, **M-1 y M-2**.

---

# CIERRE — 2026-07-24 (2ª sesión) · Re-baseline con el prompt de #43-#44: la promesa se sostiene

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
