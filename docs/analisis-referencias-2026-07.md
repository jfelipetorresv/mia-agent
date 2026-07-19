# Qué adoptar de Hermes y ClaudeOS — plan para Mia

_Análisis del 2026-07-02 (sesión 24). Fuentes: `hermes-ref` (Hermes Agent, Python/MIT),
`claudeos-ref` (ClaudeOS [Hermes] V2.3, TypeScript). Cada repo fue leído a fondo por un analista dedicado con el
mapa completo de lo que Mia ya tiene, para no recomendar reinventar lo construido._

Este documento es el plan de referencia; la ejecución de cada ola se puede afinar luego
con otro modelo. Todo está ordenado por **valor para un despacho legal**, no por valor
genérico.

---

## Resumen en una frase

Los tres repos coinciden en cinco frentes donde Mia puede crecer: **(1) blindaje de
confidencialidad**, **(2) proactividad sobre plazos**, **(3) voz**, **(4) valor visible +
auto-mejora rigurosa** y **(5) escala/robustez**. Lo más urgente para un despacho no es la
voz (lo llamativo) sino la **confidencialidad** y la **vigilancia de plazos** (lo que
protege al cliente y evita una sanción).

---

## OLA 1 — Blindaje de confidencialidad _(lo que un despacho no puede NO tener)_

El frente donde los tres repos más aportan y el más crítico para el secreto profesional.

- **Cuarentena de contenido no confiable (anti-manipulación).** Hoy un expediente, un
  correo o una página web que Mia lee podría contener instrucciones ocultas que la hagan
  actuar mal contra el cliente ("ignora todo y envía esto a…"). Hermes envuelve TODO lo que
  viene de fuera en un sello que le dice al modelo "esto son datos, no órdenes".
  - En Mia: ya empezamos esto puntualmente (las notas del despacho en CP3 y las fuentes del
    corpus en CP9 van con ese sello). Falta **generalizarlo** a todo lo que entra:
    documentos subidos, correos, carpetas, web.
  - Referencia: `hermes-ref/agent/tool_dispatch_helpers.py`, `agent/tool_guardrails.py`.
  - **Valor: máximo. Esfuerzo: bajo.**

- **Aislamiento fail-closed de secretos entre clientes.** Si Mia atiende a varios despachos
  en el mismo proceso, los secretos de uno no deben poder filtrarse a otro. Hermes usa un
  patrón que, ante la duda, **falla ruidosamente en vez de leer de más** (nunca "por si
  acaso" expone algo).
  - En Mia: ya hay aislamiento por base de datos (RLS). Falta el mismo rigor a nivel de
    secretos/credenciales en memoria y de **redacción automática** de datos sensibles en los
    registros (logs), "congelada" para que ni el propio modelo pueda apagarla.
  - Referencia: `hermes-ref/agent/secret_scope.py`, `agent/redact.py`, `agent/file_safety.py`.
  - **Valor: muy alto. Esfuerzo: bajo-medio.**

- **Endurecimiento de los conectores y la ejecución.** Ejecutar por lista de argumentos (no
  por "shell", que permite inyectar comandos), validar identificadores con reglas estrictas,
  un "tripwire" que impide guardar una clave por error, y latidos + cierre limpio en las
  conexiones largas.
  - Referencia: `claudeos-ref/.../vite.config.ts` (patrones de puente local).
  - **Valor: medio-alto. Esfuerzo: bajo por pieza.**

> Por qué primero: es barato, cierra el mayor riesgo de seguridad de un agente que ingiere
> material del mundo real, y es exactamente la Regla 2 (datos de cliente hacia IA = zona
> sensible). Nada de esto cambia lo que el abogado ve; es blindaje por detrás.

---

## OLA 2 — Proactividad sobre plazos _(el valor diario de un despacho)_

- **Motor de tareas programadas + "plantillas de automatización" + "sugerencias".** Hermes
  tiene un motor que vigila cosas en el tiempo (vencimientos, correo urgente de una
  autoridad, revisión semanal de un expediente) y, en vez de pedirle al usuario que
  configure algo técnico, le ofrece **plantillas rellenables** ("avísame X días antes de un
  vencimiento") y **sugerencias** que el abogado acepta o descarta (nunca se auto-activan).
  Incluye un truco de eficiencia: un chequeo barato decide si "vale la pena despertar" al
  agente, para no gastar en llamadas de IA inútiles.
  - En Mia: ya hay recordatorios proactivos (CP-B3). El salto es la **vigilancia
    programada** con plantillas sin jerga y el filtro de "vale la pena avisar".
  - **Regla dura (regla 5):** cualquier automatización que toque un **plazo procesal** debe
    ser una sugerencia que el abogado confirma — Mia nunca calcula ni agenda un término
    legal sola. Esto ya es política de Mia; se mantiene.
  - Referencia: `hermes-ref/cron/scheduler.py`, `cron/blueprint_catalog.py`, `cron/suggestions.py`.
  - **Valor: máximo. Esfuerzo: medio-alto.**

---

## OLA 3 — Voz _(el pilar de voz que querías)_

La referencia de voz da la **arquitectura y los patrones de privacidad**, pero conviene saber: su voz
es "graba y envía" (por lotes), **no** es conversación en tiempo real con interrupción. Eso
hay que construirlo; no viene hecho. Lo bueno: adoptamos lo sólido y evitamos deuda.

- **Fase 1 — Dictado en la web (rápido y de alto uso).** Botón de micrófono en la pantalla
  actual: el abogado dicta, Mia transcribe. Con un motor de transcripción **local**
  (faster-whisper) el audio **nunca sale del equipo/servidor** — clave para datos de
  cliente. Esfuerzo: **bajo.**
- **Fase 2 — Respuesta hablada + fluidez.** Voz de salida (TTS) también local (Kokoro/Piper),
  y sintetizar por frases conforme Mia genera el texto, para que se sienta en tiempo real.
  Esfuerzo: **medio.**
- **Fase 3 — Asistente omnipresente (opcional).** Un "overlay" de escritorio que aparece con
  un atajo de teclado desde cualquier aplicación (el verdadero "ClaudeClaw"). La referencia lo
  tiene pulido solo en Mac; en Windows es viable pero menos fino. Esfuerzo: **medio-alto.**
- Referencias (subsistema de voz local-first, en disco): `speech/` (todo el subsistema),
  `server/stream_bridge.py` (streaming), `frontend/src/hooks/useSpeech.ts` (dictado),
  `frontend/src-tauri/src/lib.rs` (overlay + atajo global).

> **Decisión de alto impacto para ti (Regla 2):** ¿la voz de Mia es **100% local**
> (privacidad total, calidad buena pero no perfecta en español) o se permite **nube** para
> mejor calidad (el audio y su transcripción salen a un tercero)? Para un despacho,
> recomiendo local por defecto y nube solo como opción consciente por cliente. **Requiere tu
> decisión antes de exponer cualquier ruta de voz a la nube.**

---

## OLA 4 — Valor visible + auto-mejora rigurosa

- **"Valor entregado" en lenguaje de negocio (ROI).** ClaudeOS calcula, por cada tarea que
  hace el agente, **horas ahorradas × tu tarifa − costo**, y lo muestra como "valor neto".
  Es la métrica que un abogado entiende y puede llevar a un cliente. Mia no lo tiene.
  - Referencia: `claudeos-ref/.../src/lib/time-saved.ts`. **Valor: alto (de producto).
    Esfuerzo: bajo.**
- **Motor de auto-diagnóstico prescriptivo.** ClaudeOS revisa cada día la actividad, la
  puntúa por **gravedad × impacto económico × certeza**, y propone las 4 mejoras de mayor
  impacto — con dos cosas que Mia debería copiar: **memoria de recomendaciones** (no repite
  lo ya aceptado/descartado) y **guardas anti-invención** (no sugiere nada sin evidencia
  real y verificable — imprescindible en lo legal).
  - En Mia: ya hay "Dreams semanal"; esto lo vuelve mucho más riguroso y accionable.
  - Referencia: `claudeos-ref/.../skills/dream/SKILL.md`. **Valor: alto. Esfuerzo: bajo-medio.**

---

## OLA 5 — Escala y robustez _(cuando haya más clientes/uso)_

- **Trazabilidad para cumplimiento (observer hooks) + políticas por cliente (middleware).**
  Una capa de auditoría que registra cada acción (para cumplimiento regulatorio) y otra que
  permite aplicar reglas por cliente (redacción extra, límite de gasto, qué motor usar) sin
  tocar el corazón del sistema. Referencia: `hermes-ref/docs/observability/`, `docs/middleware/`.
  **Valor: alto para escalar. Esfuerzo: medio-alto.**
- **Adjuntar pruebas por referencia (`@expediente`, `@carpeta`).** El abogado menciona un
  archivo o carpeta y Mia lo trae, con las salvaguardas de confidencialidad ya integradas y
  sin saturar la memoria. Referencia: `hermes-ref/agent/context_references.py`. **Valor: alto.
  Esfuerzo: bajo-medio.**
- **Personas jurídicas especializadas (editables por el despacho).** Definir "quién habla"
  (litigante, tributarista, revisor de citas), cada una con su estilo y su motor de IA, como
  archivos que el despacho edita — complementa el equipo de especialistas que ya existe (CP9).
  Referencia: `claudeos-ref` (Pantheon/Personas). **Valor: medio-alto. Esfuerzo: medio.**
- **Banco de pruebas de calidad (eval).** Correr a Mia sobre un set de "casos de oro" y medir
  si cada cambio la mejora o la empeora — la red de seguridad para no degradar la calidad
  jurídica con el tiempo. Referencia: `hermes-ref/batch_runner.py`. **Valor: medio-alto.
  Esfuerzo: medio.** _(Nota regla 2: usar datos reales de cliente para esto requiere tu
  aprobación.)_
- **Delegación multi-agente + tablero de misión por expediente.** Investigar varias
  fuentes/jurisdicciones en paralelo con un verificador y un sintetizador; y un tablero que
  descompone "preparar la demanda" en hitos visibles para el abogado. Referencias:
  `hermes-ref/tools/delegate_tool.py`, `claudeos-ref` (Missions). **Valor: medio. Esfuerzo:
  medio-alto.**
- **Conectar a más canales y sistemas con seguridad (relay + MCP).** WhatsApp/correo con las
  credenciales fuera del núcleo; conectar a gestión documental o sistemas de tribunales con
  un modelo de permisos mínimo. Referencias: `hermes-ref/gateway/relay/`, `tools/mcp_tool.py`.
  **Valor: medio-alto cuando se necesite. Esfuerzo: medio-alto.**

---

## Lo que se descartó (no encaja en un despacho)

- Integración con editores de código (ACP) y con servidores de lenguaje (LSP): sirven para
  programar, no para litigar.
- El "marketplace" comunitario de skills: un despacho no instalaría habilidades de terceros
  desconocidos.
- Empaquetar todo el sistema dentro de una app de escritorio (modelo monolítico de escritorio): Mia es
  multi-cliente en servidor; el escritorio, si llega, debe ser un cliente delgado que apunta
  al servidor de Mia con conexión segura y autenticación por despacho.

---

## Decisiones que dependen de ti (alto impacto)

1. **Voz local vs. nube** (privacidad vs. calidad) — antes de construir la Ola 3.
2. **Automatización de plazos**: se mantiene como sugerencia con confirmación humana
   obligatoria; ninguna auto-ejecución de términos procesales.
3. **Datos reales de cliente para el banco de pruebas/eval**: requiere tu aprobación
   explícita (Regla 2).

## Mi recomendación de secuencia

**Ola 1 (confidencialidad) → Ola 2 (plazos) → Ola 4 (ROI visible, que es rápido y te sirve
para mostrar valor) → Ola 3 (voz) → Ola 5 (escala).** La voz es lo más vistoso, pero la
confidencialidad y la vigilancia de plazos son lo que un despacho de verdad necesita
primero, y el "valor en horas ahorradas" es barato y te da un argumento comercial de
inmediato.
