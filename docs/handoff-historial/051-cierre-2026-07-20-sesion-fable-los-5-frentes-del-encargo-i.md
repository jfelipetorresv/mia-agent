# CIERRE — 2026-07-20 (sesión Fable) · Los 5 frentes del encargo, implementados y verificados

Rama `feat/fase1-inc1-cleanup-scaffolding`. **6 commits nuevos** (`2ecbbeb`…`3dc79a7` + este), **SIN push**
(Pipe aprueba; ojo: los 15 anteriores YA aparecen en el remoto — alguien los pushó entre sesiones).
**Esta entrada sustituye a la anterior como punto de partida.** El encargo de la entrada previa (§0) se
ejecutó completo; sus tres preguntas quedan respondidas abajo.

## 0 · Método (funcionó otra vez)

Un workflow, 13 agentes: un escritor por frente en archivos disjuntos (Opus en guardián y perfil, Sonnet en
lectura/riesgos/eval), **verificador adversarial Opus independiente por frente** — obligado a ejecutar sondas
y a repetir las mutaciones del implementador, no a leer — y validación combinada final. Un frente (D)
rechazado en primera ronda y corregido. Prueba de mutación exigida y cumplida en TODOS los checks nuevos
(~50): ninguno nació verde sin haberse visto rojo.

## 1 · Las tres preguntas del encargo, respondidas

1. **Lectura agéntica**: el traspaso anterior estaba DESACTUALIZADO — la reformulación de consulta ya
   funcionaba de punta a punta (la consulta nueva del modelo se re-embebe y busca con vector propio). Lo que
   no existía era un gate que la custodiara; ahora existe (h1, mutación demostrada). Se abarató el bucle:
   cada resultado viaja completo UNA vez y compacto después (~33% menos en ronda 3 con fragmentos reales).
   Bandera sigue APAGADA; nunca ha corrido contra modelo real.
2. **Guardián**: ahora opera sobre lo que el modelo AFIRMA, no solo sobre lo que escribe. Respaldo de
   expediente exige ancla `[doc n]` cercana Y que ESE documento contenga la cita (fronteras numéricas).
   Cita sin ancla → `[VERIFICAR]` siempre. Detecta las abreviadas (`arts. 1516 y ss. C.C.`) con siglas como
   DATOS del pack. **Decisión tomada que Pipe debe confirmar (§3.a): modelo DUAL** — el corpus curado
   (`<<<FUENTE n>>>`) respalda sin ancla como vía independiente, porque exigir `[doc n]` ahí marcaría toda
   norma investigada.
3. **Profundidad vs anchura**: sigue siendo decisión de Pipe (§3.d). Lo commiteado la deja honesta: selector
   honesto (`6e0cacc`, sesión anterior) + el banco de casos ahora mide la fuga de jurisdicción POR TASA.

## 2 · Los 6 commits

| Commit | Qué |
|---|---|
| `2ecbbeb` | **Guardián v2**: anclas obligatorias para respaldo de expediente + formas abreviadas + siglas por pack + instrucción de anclaje en analysis/draft/edit/work. Gate 38→53 checks |
| `6bc9ae9` | **Lectura agéntica**: blindaje de la reformulación (existía sin custodia) + rondas compactas (`MIA_AGENTIC_READING_COMPACT_WORDS=30`). Suite 75/75 |
| `151f4be` | **Perfil «## aprendido»** (paso 7, lo último del rediseño): se llena solo al aprobar un borrador; cada línea `[inferido]`+fecha+fuente por construcción; fail-soft absoluto. `test_aprendido` 32/32 nuevo |
| `753d798` | **5 riesgos menores**: comentario obsoleto de warroom, margen 0.15 del estimador de la Sala, piso citable medido (50→90, decoupled), `init_durable_jobs` con diagnóstico, `extendTailwindMerge` (defecto real en CardDescription) |
| `3dc79a7` | **Banco de casos**: 3 RISK_CASES (fuga por tasa, citas abreviadas, procedencia) + `run_eval.py --agentic-compare` |
| (este) | Traspaso |

## 3 · Decisiones pendientes de PIPE (no es código)

- **(a) Guardián dual o anclaje puro.** Hoy: ancla-de-documento O corpus-curado, vías independientes.
  El anclaje puro (todo exige `[doc n]`) obligaría a resellar el corpus como anclable — cambio mayor.
  Implementador y verificador recomiendan el dual; falta su confirmación.
- **(b) ¿RISK_CASES en el examen por defecto?** Hoy se piden con `--case/--repeat`; el examen canónico
  quedó intacto. Reversible.
- **(c) Aprobar el push** de los 6 commits nuevos (y aclarar quién pushó los 15 anteriores).
- **(d) Profundidad en un ordenamiento vs anchura verificable** — sigue abierta de la sesión anterior.
- Siguen pendientes: apps OAuth (Gmail/Outlook/OneDrive), archivos `Informe-Lucy-*.json` del escritorio.

## 4 · Verificación (estado final combinado)

**HALT**: `test_rls` 19/19 · `check_env_pins` 10/10 · `test_gates_no_ciegos` 9/9.
**Suites** (todas verdes): doc_citation_guard 53/53 · jurisdiction_agnostic 104/104 · lectura_agentica 75/75 ·
retrieval_adaptativa 59/59 · soul_guard 47/47 · profile_full 51/51 · warroom 84/84 · matter_folders_multi 31/31 ·
eval_harness 49/49 · eval_substance 42/42 · value_delivered 28/28 · e2e 58/58 · projects 59/59 ·
untrusted_content 28/28 · context_references 43/43 · aprendido 32/32 (nuevo) · context_recovery 52/52 · `tsc` limpio.
Aviso no bloqueante del meta-gate: 5 avisos de "clase visible" en `test_assistant.py` (preexistentes).

## 5 · NO VERIFICADO — honestidad

- **Nada corrió contra un modelo real.** El banco está LISTO para cerrarla:
  `run_eval.py --case fuga-jurisdiccion-contrato-sin-pais --repeat N` y `--agentic-compare`, con DB
  (55432, quedó ARRIBA) + LiteLLM (:4000, apagado). Ojo: bajo la política `suscripcion` (cadena `cli-*`)
  el bucle agéntico no corre aunque la bandera esté en True; el comparador lo reporta honesto.
- **Efecto end-to-end del anclaje** sobre un borrador real del modelo: sin probar en vivo (capa 3).
- **`## aprendido` con modelo real**: sin probar que el task `soul` devuelva JSON estricto; una frase corta
  podría colar un dato del caso — la red es formato+tope+descarte, no garantía semántica.
- **`next build` no se corrió** (regla del repo). Sí `tsc`.

## 6 · Menores abiertos (defectos listados por verificadores, ninguno rechaza)

1. Guardián no detecta `literal a del artículo 7` (subdivisión alfabética) ni `art. 5, C.C.` (coma) ni
   `art. 5 y el E.T.` — sub-detección, dirección segura.
2. `MIN_DOC_TOKENS=90` solo actúa en la rama degenerada (inalcanzable en producción); a presupuesto real
   la cita sobrevive por el reparto max-min (verificado con sonda a 70k). El gate cubre solo esa rama.
3. Señal de fuga no capta corporación/código nombrados SIN cita concreta ("según la Corte Constitucional") —
   límite heredado de reutilizar el guardián. `provenance_signal` es lista fija de frases (paráfrasis se escapa).
4. El path `decision=='editing'` del HITL no dispara `aprendido` (el módulo ya lo soporta, falta cablearlo).

---

