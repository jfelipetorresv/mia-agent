# F2 — Endurecer sobre evidencia: el guardián deja de depender de la obediencia

Fuente: plan maestro `C:\Users\USER\.claude\plans\fable-puedes-estructurar-un-sleepy-sifakis.md`,
sección "F2". Depende de F1 (baseline con números) + Sesión Pipe A (decisiones con evidencia). Es el
frente A2 de la auditoría competitiva (contrato afirmación→span).

## Objetivo
El guardián de citas deja de depender de que el modelo obedezca la instrucción del prompt: toda
afirmación jurídica debe llevar fuente + pasaje localizable + relación de soporte, verificado
deterministamente, o abstención explícita.

## Entradas
Baseline de F1 (panel de métricas), decisiones de Sesión Pipe A (guardián dual ya decidido — NO se
reabre; ver plan maestro §"Decisiones de Pipe").

## Pasos
Bucle: correr banco → analizar fallas → arreglar
(`backend/mia/agents/verification.py`, `backend/mia/agent/prompt_builder.py`) → reiniciar →
re-correr. Cada arreglo entra con su caso de regresión en `backend/mia/eval/cases.py`.

1. **Especificación de seguridad de salida POR ORACIÓN**: toda afirmación jurídica → su fuente → un
   pasaje localizable → relación de soporte, o abstención explícita. Honestidad sobre el límite: la
   capa determinista verifica ubicación y respaldo léxico; la implicación semántica (una cita real
   que NO sostiene lo afirmado) se ataca con sondas adversariales de entailment en el banco, no con
   regex — lo que no se pueda verificar se marca, nunca se certifica.
2. La fuga de jurisdicción se **bloquea o reescribe ANTES de mostrarse** (el punto de emisión ya es
   posterior a la verificación, commit `9516833`); el endurecimiento es que el detector la atrape en
   el 100% de sus ocurrencias, midiendo también sus falsos positivos con ataques y con respuestas
   legítimas (la intermitencia del modelo no se elimina; se atrapa antes de que el abogado la vea).
3. Cablear el path `decision=='editing'` de `## aprendido` en `backend/mia/api/routes/hitl.py` (el
   módulo `backend/mia/memory/aprendido.py` ya lo soporta).
4. Decidir con evidencia si la lectura agéntica se enciende por defecto (el delta on/off de F1
   manda).
5. Verificación adversarial en cada ciclo: un agente planta violaciones NUEVAS no vistas por el
   constructor (evita sobreajuste al banco).
6. Si el guardián determinista tiene un techo real (spans no anclables mecánicamente), la salida
   honesta es degradar la afirmación ("no puedo respaldar esto") — nunca relajar el umbral.
7. **Adelanto de F5 que corre aquí, no espera** (corrección de Codex): sonda de instalabilidad —
   compilar solo el backend (`packaging/build_backend.ps1`) y correr `--first-run` contra una DB de
   scratch en dev. Barato, evita descubrir al final que el flujo comprador está roto.

## Archivos críticos
`backend/mia/agents/verification.py`, `backend/mia/agent/prompt_builder.py`,
`backend/mia/api/routes/hitl.py`, `backend/mia/eval/cases.py`.

## Salida medible (copiada del plan maestro, textual — línea 134)
Re-corrida completa (N=10): 100% de afirmaciones sin respaldo plantadas bloqueadas por el guardián
(el harness distingue quién marcó: guardián vs modelo); fuga detectada en el 100% de sus ocurrencias
observadas; HALT + suites + tsc verdes.

**Añadido por esta spec (no es parte de la salida medible de F2 en el plan maestro; el plan la sitúa
"al cierre de F2" como adelanto del gate de instalabilidad de F5 — ver Paso 7 arriba)**: sonda de
instalabilidad corrida y documentada.

## Gates
HALT completo + suites del área + verificación adversarial por ciclo + `tsc` frontend 0 errores.

## Modelos (matriz del plan)
Diseño de endurecimiento: Opus (high) implementa, Opus distinto (high) verifica + Codex si
discrepan — refutación adversarial fue la fase de mayor rendimiento medido en este repo. Lógica
crítica (guardián/prompt): Opus (high) implementa, Codex (xhigh) verifica — cruce de proveedor.
