# TRASPASO-MODELO — Mia (continuidad entre modelos de IA)

_Creado 2026-07-02 por Claude Fable 5, a pedido de Pipe. Propósito: que cualquier modelo
que continúe este proyecto (Claude Opus u otro) arranque con la MISMA visión, la MISMA
ruta y el MISMO estándar de calidad con que se ha construido hasta hoy._

---

## Cómo usar este archivo

Léelo al iniciar sesión en una terminal nueva, DESPUÉS de `CLAUDE.md` y ANTES de tocar
código. Orden de lectura completo al retomar el proyecto:

1. `mia/CLAUDE.md` — constitución del proyecto (decisiones ya tomadas, no re-discutir).
2. La memoria persistente de Claude Code (se carga sola al abrir sesión en
   `D:\Inteligencia Artificial\Mia-Super Agent`) — estado por checkpoint y protocolo entre sesiones.
3. `mia/memory/session-summaries.md` — SOLO la última entrada.
4. `mia/HANDOFF.md` — el checkpoint más reciente y qué le falta al frontend (Cursor).
5. `mia/docs/plan-ejecucion-olas.md` — el roadmap ejecutable (5 olas, 16 checkpoints).
6. Este archivo — el estándar de calidad y las trampas del entorno.

Este documento APUNTA a las fuentes vivas; no las duplica. Si algo aquí contradice a
`memory/` o `HANDOFF.md`, ellas mandan (se actualizan cada checkpoint; esto no).
Matiz de precedencia: `session-summaries.md` solo se escribe con trigger de Pipe y
puede ir UNA SESIÓN atrás — la referencia de estado más confiable es la memoria
persistente de Claude Code + `git log` + `memory/progress.md`, en ese orden.

---

## La visión que no se negocia

- **Qué es Mia:** un agente legal cognitivo que aprende la metodología de CADA despacho,
  comercializable a firmas de CUALQUIER jurisdicción. "Terminado" = un abogado sin
  background técnico abre Mia, sube un expediente, pregunta, y recibe diagnóstico
  verificado + borrador para aprobar en 10 minutos.
- **Agnóstica de jurisdicción (REGLA DURA — para los tres agentes: Claude, Codex,
  Antigravity):** Mia NO es colombiana ni de ninguna jurisdicción fija. Se adapta a la
  persona/firma que la instala y a cómo quiera operarla: un despacho en México la adapta a
  México, uno en Colombia a Colombia, uno en España a España. La jurisdicción se resuelve
  POR DESPACHO (packs de `jurisdiction/`, default `generic`) — NUNCA se asume Colombia por
  defecto. Colombia es solo la jurisdicción con la que Pipe validará el diseño cuando el
  producto esté completo (un test, no el alcance). Todo default rígido a Colombia en código,
  SQL o prompts (p. ej. `COALESCE(jurisdiction,'colombia')`, "Español de Colombia",
  anonimizador o voz colombianos por defecto) es un BUG de framing a corregir hacia lo
  configurable/`generic`. No describir ni construir Mia como producto de una jurisdicción.
- **Conectores curados, adaptables por despacho:** Mia puede conectarse a distintos sistemas
  (NotebookLM del despacho, y a futuro fuentes judiciales/registrales de la jurisdicción que
  sea) CON reglas de juego claras y lista curada (estar en el catálogo = aprobado, patrón
  `mcp/`), no como puerta abierta a "conectar a lo que sea". Cada firma conecta SUS fuentes.
- **El usuario es un abogado, no un técnico.** Cero jerga en el frontend: no "HITL", no
  "vault", no "tenant", no "pgvector". El abogado ve "asunto", "revisar borrador",
  "Mia está investigando". Todo mensaje de error llega en lenguaje llano.
- **Reglas duras jurídicas (violarlas = defecto bloqueante, no detalle):**
  - Mia NUNCA calcula términos ni plazos procesales. Solo superficie fechas que el
    abogado YA fijó, y todo lo procesal viaja con la marca `[VERIFICAR]`.
  - Toda cita jurídica sin respaldo en el corpus queda marcada `[VERIFICAR]`
    automáticamente (verificador de CP9). Un borrador jamás sale "limpio" sin respaldo.
  - Nada se inventa: sin evidencia real contada, Mia calla (patrón CP-V2).
- **Confidencialidad fail-closed:** aislamiento por tenant con RLS
  (`execution/test_rls.py` es HALT — si falla, NO se avanza); secretos con scope por
  tenant que lanza excepción sin scope (CP-S2); todo contenido externo entra SELLADO
  como datos-no-órdenes (`agents/untrusted.py`, CP-S1); política de modelo del tenant
  se resuelve ANTES de llamar al LLM y ante duda se aborta (patrón
  `model_policy_for_strict`, CP-P4); logs con redacción de credenciales siempre
  encendida. Ante la duda entre fallar abierto o cerrado: SIEMPRE cerrado.
- **Consent-first:** Mia propone, el abogado decide. Nada se auto-activa, nada se
  instala sin confirmación explícita, todo aviso es opt-in.

---

## El estándar de calidad (protocolo por checkpoint — OBLIGATORIO)

Así se ha construido TODO el proyecto. No es aspiracional: es lo mínimo para cerrar
cualquier checkpoint.

1. **Rama feature** por checkpoint.
2. **Construir leyendo los repos de referencia EN DISCO** (`hermes-ref/`,
   `claudeos-ref/`, `jarvis-ref/`, en `D:\Inteligencia Artificial\Mia-Super Agent\`), no de memoria del
   modelo. Cada checkpoint del plan de olas trae sus archivos de referencia exactos.
3. **Capa 1 — automatizada:** gate nuevo del checkpoint + regresión COMPLETA
   (`scripts/run_tests.ps1`; `test_rls` es HALT). Si hay frontend, `npm run build` verde.
4. **Capa 2 — revisor adversarial independiente con contexto fresco** (subagente que no
   vio la implementación). Su trabajo es REFUTAR. Corregir TODOS los hallazgos ANTES del
   commit y re-verificar con el revisor. Dato de calibración: CP-S2, CP-S3, CP-P4 y
   CP-V1 fueron RECHAZADOS en v1 y se corrigieron — el rechazo de capa 2 es el estándar
   funcionando, no un fracaso. Un checkpoint sin hallazgos de capa 2 es sospechoso.
5. **Capa 3 — visual (si hay frontend):** HANDOFF.md actualizado para Cursor con
   endpoints, comportamiento esperado y qué revisar. Verificar la entrega de Cursor al
   integrarla (ya se le corrigieron defectos de exactitud — no asumir que está bien).
6. **Alto impacto** (prompts, argumentos legales, algo sustantivo que ve el cliente):
   comparación **A/B en vivo** antes de mergear. El método (probado en CP6 y CP9; el
   script `ab_run.py` que lo corrió fue efímero y NO está versionado — reconstruirlo es
   trivial siguiendo esto): `git worktree` de main = ANTES, la rama feature = DESPUÉS;
   MISMO expediente de prueba (el de `docs/comparacion-cp6.md`); MISMOS servicios vivos
   (Postgres + LiteLLM en :4000 + claude CLI, política "suscripcion"); correr el mismo
   turno en ambos y documentar el veredicto lado a lado en un `docs/comparacion-*.md`
   nuevo (ejemplos del formato: `docs/comparacion-cp6.md` y `docs/comparacion-cp9.md`).
   Pipe decide con esa comparación, no con el diff.
7. **Commit + merge + push:** rama feature autónomo; **push a main requiere aprobación
   de Pipe en el diálogo**. Nunca mezclar trabajo de dos frentes en un commit (lección
   de la "deuda de árbol" de CP-P3).
8. **Reporte a Pipe ≤4 líneas en lenguaje de negocio:** qué cambió, por qué, riesgo si
   algo sale mal, suposiciones hechas.
9. Al cerrar: registrar riesgos residuales en `memory/bugs-and-risks.md` (numerados),
   actualizar `memory/progress.md`, y session-summary solo con trigger de Pipe.

---

## Cómo trabajar con Pipe

Su perfil completo se carga solo (`~/.claude/CLAUDE.md` y `~/.claude/perfil/`). Lo
esencial: es abogado y director de la firma — decide negocio y producto, NO revisa
código ni diffs. Autonomía total en git y cambios menores reversibles (reportar
después); aprobación PREVIA solo en alto impacto (lógica de negocio, contenido legal,
push a main). NUNCA asumir un dato procesal, plazo o criterio jurídico — preguntar
siempre. NUNCA pedirle ejecutar comandos ni resolver detalles técnicos. Usa voz a
texto: interpretar la intención, no el término mal transcrito. Regla de sesión (pedida
por Pipe): al llegar el contexto a ~65%, preparar el traspaso y continuar en terminal
nueva — no arrancar checkpoints grandes con el contexto alto; las sesiones se encadenan
por la memoria del repo, no por el contexto. OJO: puede haber OTRA terminal activa
sobre el mismo repo — antes de commitear, verificar con `git log`/`git status` que el
estado sigue siendo el que conoces.

---

## Estado actual y ruta por delante (al 2026-07-02)

- **Olas 1 (confidencialidad), 2 (plazos) y 4 (valor visible) CERRADAS** — CP-S1..S3,
  CP-P1..P4, CP-V1, CP-V2 en `origin/main`, cada uno con sus 3 capas. Detalle fino en
  la memoria persistente y `memory/progress.md`.
- **SIGUE (orden aprobado por Pipe): OLA 3 — voz 100% local**, luego Ola 5 (escala).
  - **CP-Z1** (voz-a-texto): integración NATIVA en Mia reusando los modelos que LEXTER
    (dictado local de Pipe, fork de Handy) ya validó en español jurídico. Diseño técnico
    completo en `docs/analisis-lexter.md`; código fuente en
    `https://github.com/jfelipetorresv/Lexter-Voice-Command.git` (repo privado de Pipe,
    NO está clonado en disco — los parámetros ya están extraídos en el análisis; clonar
    solo si hay que verificar contra el código). **Modelo STT DECIDIDO
    por Pipe (2026-07-02): Parakeet v3** (el default de Lexter, validado por su uso real
    en español jurídico); Whisper queda como opción configurable futura, no v1.
    Candado `allow_cloud_audio=false` por tenant.
  - **CP-Z2** (respuesta hablada): falta elegir TTS local (Kokoro/Piper, validar español).
  - **CP-Z3** (overlay de escritorio): opcional, al final de la ola.
  - **Ola 5:** CP-E1..E6 según `docs/plan-ejecucion-olas.md`.
- **Conectores de correo/calendario (CP-P3/P4): código LISTO, activación APLAZADA** por
  decisión de Pipe hasta el producto final. NO pedirle las llaves OAuth ni insistir.

## Pendientes que dependen de Pipe (no bloquean el código)

Lista viva en la memoria persistente; al escribir esto: (1) conectores aplazados —
no insistir; (2) encender `allow_content_analysis` por despacho (regla dura si es nube);
(3) OpenRouter: cuenta + API key + tope de gasto + opt-in (Riesgo #38); (4) frontend
pendiente con Cursor vía HANDOFF.md: pantallas de CP-P2 (automatizaciones), CP-P3
(conectar Microsoft 365/Google) y CP-V2 (tarjetas de diagnóstico); (5) bot de Telegram,
subir sus guías de trabajo reales, corpus jurídico real (activa las citas "respaldadas").

---

## Trampas conocidas de este entorno (te van a morder si no las sabes)

- **Windows-first, Modo B nativo.** PowerShell, no bash de Linux. La ruta del proyecto
  tiene ESPACIOS: siempre `"D:\Inteligencia Artificial\Mia-Super Agent\mia"` entre comillas.
- **`git commit -F archivo`** siempre: el clasificador de permisos rompe con mensajes de
  commit que contienen rutas tipo endpoint (`/api/...`) o heredocs.
- **`npm run build` con el dev server corriendo PISA la caché `.next`** (página en
  blanco, chunks 404). Reiniciar el dev server después de cada build.
- **Arranque Modo B:** 3 procesos (`scripts/start_litellm.ps1`, `start_api.ps1`,
  `npm run dev` en frontend/). Regresión: `scripts/run_tests.ps1` (aborta si los pins
  del venv fueron alterados — Riesgo #32).
- **El .env NUNCA se commitea.** Las claves por tenant van en `tenant_settings` con
  scope, no en el entorno global.
- **Deudas menores conocidas** (anotadas, no urgentes): jerga "Pinecone"/"second brain"
  en el dashboard (§G); la página de memoria usa `.includes("409")` sobre un mensaje que
  ya no trae el código; detector de citas no cubre artículos con numerales intercalados;
  entradas VIEJAS de `memory/session-summaries.md` y `memory/progress.md` tienen
  mojibake (UTF-8 leído como Windows-1252) — el contenido reciente está sano, pero un
  grep sobre el histórico puede fallar por eso.
- **`call_llm(task="compression")` está BLOQUEADA** a la cadena barata/local de la
  política activa del despacho — ningún call-site la puede cambiar (un `model=` explícito
  se ignora, `_LOCKED_TASKS` en `agent/llm.py`). El modelo concreto lo fija la política:
  'suscripcion' = `cli-claude-haiku`, 'nube' = `claude-haiku`, 'soberano' = `mia-local`.
  No "mejorar" a sonnet ni tocar el bloqueo sin documentar en `memory/decisions.md`.

---

_Si este archivo queda desactualizado respecto a `memory/` o `HANDOFF.md`, actualízalo
en el mismo commit de docs del checkpoint que lo desactualizó._
