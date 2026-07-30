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
