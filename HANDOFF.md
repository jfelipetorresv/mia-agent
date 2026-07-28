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

# CIERRE — 2026-07-27/28 (4ª sesión) · SESIÓN PIPE A EJECUTADA: F2 cerrada + 4 barreras del harness · EMPEZAR AQUÍ

## Arranque en una terminal nueva (prompt sugerido)

> Lee `HANDOFF.md` y `APRENDIZAJES.md` de `D:\Inteligencia Artificial\Mia-Super Agent\mia` y el
> plan maestro (`C:\Users\USER\.claude\plans\fable-puedes-estructurar-un-sleepy-sifakis.md`).
> Corre `scripts\sonda_salud.ps1` ANTES de nada; si la DB portable (55432) está apagada,
> arráncala: `tools\postgres16-portable\pgsql\bin\pg_ctl.exe -D tools\pgdata-portable -l
> tools\pg_start.log -o "-p 55432" start` (el `pg_ctl` no devuelve el prompt pero el motor
> arranca — comprobar con `pg_isready` o conectando). **La Sesión Pipe A YA SE HIZO**: las 7
> decisiones están en `memory/decisions.md` #45/#46/#47 y **F2 está CERRADA** (`memory/findings.md`
> §CIERRE DE F2). **Antes de comparar cualquier cifra con el pasado, leer los TRES CORTES DE SERIE
> de esa sección**: fuga (N-1), abstención (M-1) y `prompt_hash` (`3391f17ea61324a4` →
> `8388c516a2156de2`), más el cambio de composición del examen (los casos de RIESGO entran por
> defecto: 3 → 9). Lo que sigue está en «Qué sigue» abajo; lo único que espera a Pipe es la
> lectura de calidad de las 6 salidas y los dos trámites de terceros
> (`docs/tramites-terceros-pipe.md`).

Rama `feat/fase1-inc1-cleanup-scaffolding`. Pusheado hasta el commit de esta entrada.

## Qué pasó en esta sesión (2026-07-27/28, 4ª)

1. **La Sesión Pipe A se ejecutó completa** (salvo la lectura de calidad, que es juicio suyo).
   Siete decisiones tomadas en vivo, registradas en `memory/decisions.md` #45, #46 y #47.
2. **Las tres decisiones de medición, aplicadas y verificadas** (`656dc20`):
   - **N-1**: la regla del muro es «no afirmar una norma como aplicable sin respaldo», NO «no
     escribir jamás el número». Mención + negación explícita en la misma oración ya no es fuga.
     **Fuga real 0/63** recalculando los crudos guardados; el falso positivo de «Ley 4137»
     desaparece y ninguna cita realmente usada se escapa (checks G1-G9).
   - **M-1**: `ABSTENTION_PHRASES` recalibrado MIDIENDO los 62 borradores (11 → 46 formas).
     Cobertura 29/29 en suscripción (antes 0/30), 30/33 en nube. **Corte de serie declarado** —
     Pipe eligió declararlo en vez de pagar un re-baseline.
   - **M-2**: fuera «Éxito de tarea»; ahora «Turnos completados» + «Se negó correctamente» en los
     casos de RIESGO (10/10 nube, 9/9 suscripción sobre las sondas ya corridas).
3. **Las CUATRO barreras del harness de litigio de Pipe, portadas** (`99fb4a2`, `ba1fbde`,
   `ae42b96`). Decisión de dureza suya: **nacen como AVISO y solo suben a muro si se mide que no
   bloquean trabajo bueno**; el banco de citas quemadas es la única excepción (muro día uno).
   - **Afirmaciones negativas** verificadas contra el documento COMPLETO (no el fragmento ni el
     resumen de un extractor) + `retrieval.document_full_text` + regla y corolario en el prompt.
   - **Banco de citas quemadas** (migración **047**, tabla `burned_citations` con RLS): la cita
     que el abogado marca como falsa no vuelve a emitirse **ni con respaldo del corpus** — el muro
     va antes de toda vía de respaldo, que es como se coló el defecto original.
   - **Contaminación entre expedientes**: partes de OTRO asunto nombradas en el escrito. Catálogo
     DERIVADO de `documents.parte` del propio despacho — cero listas cableadas, agnóstico.
   - **Ninguna lección sin barrera**: regla de trabajo (reglas 55-61 de `APRENDIZAJES.md`).
4. **F2 CERRADA y alcance de la v1 ajustado** (#47): los casos de RIESGO entran al examen por
   defecto (`load_golden_cases` los incluye; el examen pasa de 3 a 9 casos y
   `test_gold_cases_influence_eval` ya deriva el número en vez de cablearlo), el «Modo A»
   (Docker/servidor) queda FUERA de la v1, y **los USD 22,6 del tope de nube quedan sin gastar**.
5. **Riesgo #81 CERRADO** con criterio + barrera (las tres partes: N-1, M-1, M-2).
6. Verificación en tres capas en cada bloque: unitaria (4 barreras nuevas: 27/27, 20/20, 17/17,
   18/18), independiente (`test_eval_harness` 67/67 con DB, panel 50/50, substance 51/51,
   sentence_report 47/47, mutación 50/50, omission 26/26, agnostic 104/104, META C 11/11) y en
   vivo (recálculo de los 63 crudos; ciclo real del muro contra la base con RLS entre dos
   despachos: `execution/test_citas_quemadas_db.py`). Gates HALT verdes: `test_rls` 19/19,
   `test_gates_no_ciegos` 9/9.

## Qué sigue (en orden)

1. **Helper de siembra para verificación visual** (`execution/seed_despacho_demo.py`, no existe):
   un despacho de prueba CON PERFIL, para poder capturar pantallas sin correr la entrevista.
   Motivo: el gate de bienvenida no se salta con `setup/steps/perfil/skip` (devuelve 200 pero
   mira si el perfil existe), así que hoy toda captura de UI cuesta 20 minutos de andamiaje y
   quedó SIN verificación visual el botón de marcar cita falsa y los dos avisos nuevos de la
   pantalla de revisión (regla 62 de `APRENDIZAJES.md`). El andamiaje que sí quedó listo: venv
   con Playwright y script de captura en el scratchpad de la sesión.
2. ~~Alta del banco de citas quemadas desde la interfaz~~ **HECHA** (`2c7ff04`): endpoint
   `/api/citas-quemadas` (POST/GET/DELETE, 18/18 con RLS por HTTP) + enlace «Esta cita no existe
   o no dice eso» en el diálogo de cada cita, y los avisos de afirmaciones negativas y
   contaminación entre expedientes ya se pintan.
2. **Caso de oro con expediente GRANDE** (cientos de fragmentos): sigue siendo el prerrequisito
   para decidir «lectura agéntica por defecto» (N-2). No requiere aprobación.
3. **Mostrar los avisos nuevos en la pantalla**: `afirmaciones_negativas` y
   `contaminacion_expediente` viajan en el informe de verificación y todavía no se pintan.
4. Producto (plan maestro): instalador y bienvenida de F3.

## Pendientes de Pipe

- **Lectura de calidad** de las 6 salidas de `docs/f1-paquete-decision-pipe.md` y del ejemplar
  `f2sond_entail_g`. Ningún agente lo sustituye.
- **Los dos trámites de terceros**, que decidió disparar: Azure Trusted Signing (firma de Windows)
  y registro de apps OAuth (Google/Microsoft). Pasos en `docs/tramites-terceros-pipe.md`.

---

# CIERRE — 2026-07-24/25 (3ª sesión) · Sondas 30/30 + referencia en nube: el modo de venta empata

## Arranque en una terminal nueva (prompt sugerido)

> Lee `HANDOFF.md` y `APRENDIZAJES.md` de `D:\Inteligencia Artificial\Mia-Super Agent\mia` y el
> plan maestro (`C:\Users\USER\.claude\plans\fable-puedes-estructurar-un-sleepy-sifakis.md`).
> Corre `scripts\sonda_salud.ps1` ANTES de nada; si la DB portable (55432) está apagada,
> arráncala (clúster en `tools/pgdata-portable`). **F2 quedó sin trabajo de máquina
> pendiente**: las 3 sondas adversariales están corridas ×10 en vivo y agregadas
> (`memory/findings.md` §SONDAS ADVERSARIALES F2) y **la referencia en nube TAMBIÉN está hecha**
> (§REFERENCIA EN NUBE, USD 7,38 de 30). Todo con `prompt_hash 3391f17ea61324a4`. Lo que sigue
> es de Pipe: **Sesión A** con `docs/f1-paquete-decision-pipe.md` — ahora con **tres** decisiones
> nuevas (M-1 abstención, M-2 etiqueta de éxito, **N-1 mención vs uso en el detector de fuga**,
> que es la importante porque toca la métrica central). Sin Pipe, lo ejecutable es **construir un
> caso de oro con expediente GRANDE**: sin él, `--agentic-compare` no puede decidir nada (ver
> punto 11). **Al agregar cualquier serie, usa `--exige-evidencia`** (barrera de esta sesión: sin
> texto releíble el agregado reprueba). Para correr en nube hay que **encender LiteLLM primero**
> (`.venv-litellm\Scripts\litellm.exe --config litellm_config.yaml --port 4000`); la sonda de
> salud NO lo verifica.

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
7. **Retrospectiva y aprendizajes aplicados CON BARRERA (`e05d9fa`).** El defecto propio que
   destapó la retrospectiva: el agregado `f2sond_entail_n10` incluyó la corrida `_smoke`,
   guardada sin `MIA_EVAL_PERSIST_FULL=1` (borrador truncado a 1 200 chars), y **nada lo
   advirtió** — justo en la sonda declarada de REVISIÓN HUMANA. Construido:
   `harness.evidence_audit` + `--exige-evidencia` en `execution/aggregate_eval_runs.py` (avisa
   siempre; reprueba cuando se le exige). Verificado en tres capas: 6 checks nuevos en
   `test_eval_harness.py` (**67/67**, eran 61); reprobación real de `entail_n10` señalando el
   índice 0; aprobación de `sincita`/`cruzado` con 10/10 releíbles. Ojo al matiz: los **números
   del agregado no estaban comprometidos** (fuga y abstención se calculan sobre el texto entero
   en `run_case` y viajan persistidas) — lo que faltaba era poder RELEER.
8. **Cierre de sesión completo**: reglas 52-54 en `APRENDIZAJES.md`; **riesgo #81** en
   `bugs-and-risks.md` (M-1/M-2, pariente del #80: métrica correcta con etiqueta que induce
   lectura falsa); `findings.md` con el límite declarado de la evidencia; `progress.md`,
   `session-summaries.md` (sesión 49) y `task_plan.md` (hito + puntero al plan maestro vigente,
   porque su lista interna de 2026-07-01 quedó superada). Retrospectiva de método en el vault:
   `01-operacion\retrospectivas\retrospective-2026-07-24-005-mia-sondas-adversariales-f2.md`.
   Gates HALT en verde (19/19, 9/9, 12/12) + `test_sentence_report` 47/47. Repo limpio y
   pusheado hasta `e05d9fa`.

9. **REFERENCIA EN NUBE HECHA (2026-07-25) — USD 7,38 del tope de 30.** Los mismos 3 casos ×10
   bajo `MIA_MODEL_POLICY=nube` (claude-sonnet vía LiteLLM), mismo `prompt_hash`, evidencia
   10/10 en las tres (la barrera nueva en verde). Resultado para el modo de venta: **empate en
   lo que importa** — 0 citas sin respaldo y 0 falsos bloqueos en las 60 corridas (30+30). La
   nube escribe casi el doble (8,7k-11,4k vs 4,2k-7,6k), gasta MENOS tokens (33-36k vs 58-76k:
   el exceso de la suscripción es andamiaje del CLI, no trabajo jurídico), es más predecible en
   latencia y cuesta USD ~0,20 por consulta. Tabla completa en findings §REFERENCIA EN NUBE.
10. **N-1 · hallazgo más grave que M-1/M-2**: la única «fuga» de las 60 corridas es un **falso
   positivo verificado** — MIA nombró `Ley 4137` para decir que NO la reconoce, y el detector
   cuenta la aparición sin distinguir mención de uso. La fuga SÍ es métrica que decide. Va como
   **decisión 7** al paquete, con el pasaje completo. Riesgo #81 ampliado.
11. **N-2 · lectura agéntica medida**: encendida cuesta ×4,6, tarda ×2 y trajo **0 fragmentos
   nuevos** (3 ampliaciones insistiendo en un dato que el caso no contiene). Pero el límite es
   honesto: los RISK_CASES tienen 0-2 fragmentos y la función es para expedientes de cientos, así
   que «0 nuevos» es cierto POR CONSTRUCCIÓN. **Se paró el comparador ahí en vez de gastar el
   tope en más casos pequeños**: la conclusión accionable es que el banco necesita un caso de oro
   con expediente GRANDE antes de poder decidir «agéntica por defecto». Eso es más barato que
   seguir comprando corridas.

## Qué sigue (en orden)

1. **Sesión Pipe A** con `docs/f1-paquete-decision-pipe.md`: calidad de las 6 salidas + las 4
   decisiones + priorizar el backlog ruflo + **las 3 decisiones nuevas: M-1, M-2 y N-1** (esta
   última es la importante: toca la métrica central).
2. **Caso de oro con expediente GRANDE** (cientos de fragmentos) — es el prerrequisito para
   decidir lectura agéntica por defecto; sin él, el `--agentic-compare` no puede concluir nada.
   No requiere aprobación de Pipe: es construcción de banco.
3. **Cierre de F2**: queda el ítem 2 de la spec (fuga detectada al 100% de ocurrencias con
   falsos positivos medidos — que ahora tiene un falso positivo REAL documentado, N-1, como
   primer caso de prueba).
4. Sobra presupuesto de nube: **USD 22,6 de los 30** por si se quiere ampliar la referencia a
   los otros 3 RISK_CASES (`fuga`, `disciplina-citas`, `procedencia`), a ~USD 0,20 por corrida.

## Pendientes de Pipe

Ninguno bloqueante para la máquina. Espera de Pipe: la **Sesión A** (calidad + 4 decisiones +
prioridades del backlog ruflo) y, dentro de ella, **M-1 y M-2**.
