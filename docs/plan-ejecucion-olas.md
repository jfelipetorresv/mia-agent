# Plan de ejecución — 5 olas de mejora de Mia (roadmap por checkpoints)

_Creado 2026-07-02 (fin sesión 24). Pipe aprobó ejecutar **las 5 olas completas** en el
orden recomendado. Este documento es el guion ejecutable; el "por qué" de cada pieza está
en `docs/analisis-referencias-2026-07.md`. Arrancar por **CP-S1**._

**Orden aprobado:** Ola 1 (confidencialidad) → Ola 2 (plazos) → Ola 4 (valor visible) →
Ola 3 (voz) → Ola 5 (escala). La voz va deliberadamente después de lo que protege al
cliente y de lo que da argumento comercial rápido.

**Protocolo por checkpoint (igual que todo el proyecto):** rama feature → construir →
gate nuevo + regresión completa (`test_rls` es HALT) → revisor independiente capa 2 (contexto
fresco) → corregir hallazgos ANTES del commit → HANDOFF.md si hay frontend → commit + merge a
main + push → resumen de negocio ≤4 líneas. Alto impacto (algo que cambie argumentos legales o
lo que ve el cliente de forma sustantiva) → comparación A/B en vivo antes de mergear. Usar
`git commit -F archivo` (el clasificador de permisos rompe con rutas tipo endpoint en el mensaje).

Repos de referencia en `D:\Codex\Mia-Super Agent\`: `hermes-ref/`, `claudeos-ref/`,
`jarvis-ref/OpenJarvis-main/`.

---

## OLA 1 — Blindaje de confidencialidad

### CP-S1 · Cuarentena universal de contenido no confiable
- **Qué:** generalizar el sellado "esto son datos, no órdenes" a TODO lo que entra a un
  prompt desde fuera: documentos subidos, correos, carpetas/nube, web, resultados de MCP. Hoy
  Mia solo lo hace puntual (knowledge de CP3 en `graph.py::KNOWLEDGE_HEADER`, fuentes de CP9 en
  `research.py`). Crear un helper único `wrap_untrusted(source, content)` y pasar por él toda
  fuente externa antes de inyectarla.
- **Referencia Hermes:** `hermes-ref/agent/tool_dispatch_helpers.py` (`_maybe_wrap_untrusted`,
  `make_tool_result_message`), `agent/tool_guardrails.py` (detección de bucles: misma
  herramienta+args fallando, o lectura sin progreso).
- **Dónde en Mia:** `backend/mia/agents/` (un módulo nuevo `untrusted.py`), y cablearlo en
  `intake`/`research`/conectores/asistente.
- **Gate:** `test_untrusted_content.py` — verifica que cada fuente externa va sellada y que el
  sello es consistente; regresión sin cambios de comportamiento en las rutas ya fenceadas.
- **Valor máximo · esfuerzo bajo. Empezar por aquí.**

### CP-S2 · Aislamiento fail-closed de secretos + redacción de logs
- **Qué:** (a) scoping de secretos/credenciales por tenant en memoria que, sin scope activo,
  **lanza excepción** en vez de leer del entorno (nunca "por si acaso"); (b) formateador de
  logs que **redacta ~40 patrones de credenciales**, "congelado" en import para que el modelo
  no pueda apagarlo a mitad de sesión.
- **Referencia Hermes:** `agent/secret_scope.py` (`set_secret_scope`, `UnscopedSecretError`),
  `agent/redact.py` (`RedactingFormatter`, snapshot en import), `agent/file_safety.py`,
  `agent/credential_pool.py`.
- **Dónde en Mia:** `backend/mia/security/` (nuevo), cablear en `logging` global y en el
  acceso a claves por tenant.
- **Gate:** `test_secret_scope.py` — sin scope → excepción; logs con claves → redactados;
  el redactor no se puede desactivar en runtime.
- **Valor muy alto · esfuerzo bajo-medio.**

### CP-S3 · Endurecimiento de conectores y streaming
- **Qué:** ejecución por lista de argumentos (nunca shell), validación estricta de IDs
  (regex), tripwire que impide persistir una clave por error en config de tenant, latido en
  SSE y cierre/kill al desconectar el navegador.
- **Referencia ClaudeOS:** patrones del puente local en `claudeos-ref/.../vite.config.ts`
  (argv-exec ~525-661, gating por token ~211-235, tripwire de secretos ~1642-1647, heartbeat +
  kill-on-disconnect ~581-684).
- **Dónde en Mia:** `agent_hub.py` (spawn de CLIs), `api/routes/stream.py` (SSE), conectores.
- **Gate:** `test_connector_hardening.py`.
- **Valor medio-alto · esfuerzo bajo por pieza.**

---

## OLA 2 — Proactividad sobre plazos

### CP-P1 · Motor de vigilancia programada
- **Qué:** elevar los recordatorios de CP-B3 a un motor que vigila condiciones en el tiempo
  (vencimientos, correo urgente de autoridad, revisión semanal de expediente), con abstracción
  de scheduler, ejecución at-most-once, **wake-gate** (un chequeo barato decide si vale la pena
  despertar al agente) y jobs `no_agent` (script puro sin gasto de LLM).
- **Referencia Hermes:** `cron/scheduler.py` (`tick`, `run_one_job`), `cron/jobs.py`
  (locking + claim CAS), `cron/scheduler_provider.py`, `cron/scripts/classify_items.py`
  (monitor fetch→score→surface sobre umbral).
- **Dónde en Mia:** `backend/mia/cron/` (ya existe `build_scheduler`); extender.
- **Gate:** `test_watch_engine.py`.
- **Valor máximo · esfuerzo medio-alto.**

### CP-P2 · Plantillas de automatización (blueprints) + sugerencias consent-first
- **Qué:** plantillas rellenables sin jerga ("avísame N días antes de un vencimiento") y
  sugerencias que Mia propone y el abogado acepta/descarta (nunca auto-activa; máx. 5
  pendientes). **Regla dura:** toda automatización que toque un **plazo procesal** es
  sugerencia con confirmación humana — Mia jamás calcula ni agenda un término sola.
- **Referencia Hermes:** `cron/blueprint_catalog.py`, `cron/suggestions.py`,
  `cron/suggestion_catalog.py`.
- **Gate:** `test_blueprints.py` (incluye check duro: ningún blueprint de plazo procesal
  auto-ejecuta).
- **Valor máximo · esfuerzo medio.** Frontend → HANDOFF para Cursor.

---

## OLA 4 — Valor visible + auto-mejora rigurosa

### CP-V1 · "Valor entregado" en lenguaje de negocio (ROI)
- **Qué:** por cada asunto/skill, calcular **horas ahorradas × tarifa − costo de tokens** y
  mostrarlo como "valor neto" en el panel. Tarifa configurable por despacho.
- **Referencia ClaudeOS:** `src/lib/time-saved.ts`, `src/components/usage-panel.tsx`,
  `src/routes/setup.tsx` (paso "Time value").
- **Dónde en Mia:** backend de métricas + Panel de control (frontend → HANDOFF).
- **Gate:** `test_value_delivered.py`.
- **Valor alto de producto · esfuerzo bajo. Es rápido y da argumento comercial ya.**

### CP-V2 · Auto-diagnóstico prescriptivo riguroso
- **Qué:** evolucionar "Dreams semanal" a un motor que puntúa hallazgos por
  **gravedad × impacto económico × certeza** y propone las mejoras de mayor impacto, con dos
  cosas nuevas: **IDs estables + memoria de recomendaciones** (no repite lo aceptado/descartado
  salvo que reaparezca) y **guardas anti-invención** (nada sin evidencia real y verificable —
  imprescindible en lo legal; si un bucket tiene &lt;5 eventos, se salta).
- **Referencia ClaudeOS:** `skills/dream/SKILL.md` (spec de 289 líneas), `state.json` de dreams.
- **Dónde en Mia:** `backend/mia/memory/dreams*` (ya existe).
- **Gate:** `test_dreams.py` extendido.
- **Valor alto · esfuerzo bajo-medio.**

---

## OLA 3 — Voz _(DECISIÓN TOMADA por Pipe 2026-07-02: VOZ 100% LOCAL)_

> **Decisión: voz LOCAL** (privacidad total; el audio nunca sale de la infraestructura del
> despacho). Candado `allow_cloud_audio=false` por defecto; nube solo si algún tenant lo
> habilita explícitamente. Regla 2 satisfecha.
>
> **Activo aportado por Pipe: LEXTER** (`C:\Users\jfeli\Downloads\lexter-x86_64-pc-windows-msvc.zip`)
> — dictado local de escritorio que Pipe desarrolló, basado en **Handy** (open source). Empaquetado
> Tauri (Rust). Contenido confirmado: push-to-talk global (ctrl+space), VAD **Silero**
> (`silero_vad_v4.onnx`), aceleración local **DirectML** (GPU Windows), modelo STT descargado en
> primer uso (vocab **GigaAM** presente; probablemente soporta Whisper/otros on-demand),
> multi-idioma (`selected_language: auto`), y **post-proceso local con Ollama** (`clean_dictation`).
> Escribe el texto dictado en la app activa a nivel de SO. **Cubre el STT de CP-Z1.** NO trae TTS
> (voz de salida) → CP-Z2 sigue necesitando un TTS local (Kokoro/Piper).
>
> **Respuestas de Pipe (2026-07-02):** (a) CÓDIGO FUENTE disponible en
> `https://github.com/jfelipetorresv/Lexter-Voice-Command.git` (repo propio, acceso concedido).
> (b) Español jurídico: **probado, va bien** — no hace falta cambiar el modelo STT. (c) Integración
> **NATIVA dentro de Mia** (botón de micrófono propio), no como app aparte.
>
> **Consecuencia de diseño (CP-Z1):** el objetivo es un botón de micrófono en la web de Mia
> (Web Audio en Next.js) → endpoint FastAPI → motor STT en Python que **reusa los MISMOS modelos y
> parámetros que Lexter ya validó en español** (Silero VAD + modelo STT ONNX vía onnxruntime, con
> `onnxruntime-directml` para GPU Windows). El código Rust de Lexter es la REFERENCIA de qué modelos,
> sample rate y preproceso usar (los que ya funcionan), no código a copiar literal. El post-proceso
> "clean_dictation" con Ollama local de Lexter encaja con el gateway de Mia (que ya habla Ollama).
> **DISEÑO TÉCNICO COMPLETO en `docs/analisis-lexter.md`** (arquitectura, modelo exacto, parámetros
> 16kHz/umbral 0.3/tramas 30ms, prompts de limpieza, portabilidad a Python, 5 pasos). **Decisión del
> modelo STT RESUELTA por Pipe (2026-07-02, sesión 27): Parakeet v3** — confirmó que validó Lexter
> con el modelo por defecto (Parakeet v3) y su español jurídico va bien en uso real. CP-Z1 se
> construye con Parakeet v3 (sherpa-onnx + DirectML); Whisper large-v3 queda como opción
> configurable futura, no v1. No re-preguntar.

### CP-Z1 · Voz-a-texto local (base: Lexter/Handy)
- **Qué:** dictado local para el abogado. Dos caminos según respuesta de Pipe:
  - **Rápido (recomendado para arrancar):** usar Lexter como app de dictado a nivel de SO — el
    abogado dicta en el chat/campos de Mia hoy mismo, sin desarrollo. Se documenta y se prueba.
  - **Integrado:** portar el motor de Lexter (Silero VAD + STT ONNX + DirectML) o el patrón
    registry de OpenJarvis a `backend/mia/speech/` con endpoint FastAPI + botón de micrófono en
    Next.js. Motor local; candado de privacidad por tenant.
- **Referencia:** Lexter (activo de Pipe, base Handy) + OpenJarvis `src/openjarvis/speech/`
  (registry + `_discovery.py` local-first + `SpeechConfig`), endpoint `/v1/speech/transcribe`
  (`server/api_routes.py` ~L748), frontend `hooks/useSpeech.ts` + `components/Chat/MicButton.tsx`.
- **Gate:** `test_speech_stt.py` (incluye candado de privacidad por tenant).
- **Valor alto · esfuerzo bajo** (Lexter ya resuelve el motor).

### CP-Z2 · Respuesta hablada (TTS local) + streaming incremental
- **Qué:** voz de salida local (Kokoro/Piper, validar español) y sintetizar por frases
  conforme Mia genera el texto (sensación de tiempo real). Barge-in básico = cancelar stream +
  parar audio cuando el micrófono detecta voz.
- **Referencia OpenJarvis:** `speech/tts.py`, `kokoro_tts.py`, `server/stream_bridge.py`
  (EventBus→cola→SSE — LangGraph ya es async, más fácil), `tools/text_to_speech.py`.
- **Gate:** `test_speech_tts.py`.
- **Valor medio-alto · esfuerzo medio.**

### CP-Z3 · (Opcional) Overlay de escritorio omnipresente
- **Qué:** ventana flotante con atajo global desde cualquier app (el "ClaudeClaw" real), como
  **cliente delgado** que apunta al backend de Mia por HTTPS + token de tenant (NO el
  localhost-sin-auth de OpenJarvis).
- **Referencia OpenJarvis:** `frontend/src-tauri/src/lib.rs` (`native_overlay`, `global_shortcut`),
  `src/overlay.html`. Nota: overlay nativo pulido solo en macOS; en Windows viable con Tauri
  estándar.
- **Valor medio · esfuerzo medio-alto. Opcional / al final de la ola.**

---

## OLA 5 — Escala y robustez

### CP-E1 · Trazabilidad (observer hooks) + políticas por tenant (middleware)
- Auditoría read-only de cada acción (cumplimiento) + capa que aplica reglas por cliente
  (redacción extra, tope de gasto, routing de modelo) sin tocar el core.
- **Ref Hermes:** `docs/observability/README.md`, `docs/middleware/README.md`,
  `hermes_cli/plugins.py` (contratos `hermes.observer.v1` / `hermes.middleware.v1`).
- **Gate:** `test_observability.py`. Valor alto para escalar · esfuerzo medio-alto.

### CP-E2 · Adjuntar pruebas por referencia (`@expediente`, `@carpeta`)
- Menciones que Mia expande con confinamiento al workspace, denylist de rutas sensibles y
  techo de tokens. **Ref Hermes:** `agent/context_references.py`. Valor alto · esfuerzo bajo-medio.

### CP-E3 · Personas jurídicas especializadas (editables por el despacho)
- Registro en archivos (YAML) de "quién habla" (litigante, tributarista, revisor de citas),
  cada una con su modelo/estilo/skills/frases de invocación; complementa el equipo de nodos de
  CP9 ("quién habla" vs "cómo trabaja"). **Ref ClaudeOS:** Pantheon/Personas
  (`vite.config.ts::PANTHEON_SEEDS`, `skills/personas/SKILL.md`). Valor medio-alto · esfuerzo medio.

### CP-E4 · Banco de pruebas de calidad (eval harness)
- Correr Mia sobre un set de "casos de oro" y medir si cada cambio mejora/empeora la calidad
  jurídica. **Ref Hermes:** `batch_runner.py`, `trajectory_compressor.py`. Valor medio-alto ·
  esfuerzo medio. **Regla 2: datos reales de cliente para esto requieren aprobación de Pipe.**

### CP-E5 · Delegación multi-agente + tablero de misión por expediente
- Investigación paralela (fuentes/jurisdicciones) con verificador+sintetizador; tablero que
  descompone "preparar la demanda" en hitos visibles. **Ref:** `hermes-ref/tools/delegate_tool.py`,
  `hermes_cli/kanban*`, ClaudeOS Missions. Valor medio · esfuerzo medio-alto.

### CP-E6 · Más canales (relay) + más sistemas (MCP) con seguridad
- WhatsApp/correo con credenciales fuera del núcleo (patrón relay); conectar a gestión
  documental/tribunales con permisos mínimos. **Ref Hermes:** `gateway/relay/`, `tools/mcp_tool.py`
  (`_build_safe_env`, placeholders `${VAR}`, tokens 0600), `hermes_cli/mcp_catalog.py`. Valor
  medio-alto cuando se necesite · esfuerzo medio-alto.

---

## Decisiones de Pipe
1. **Voz local vs. nube → RESUELTO 2026-07-02: LOCAL.** Activo: Lexter (ver Ola 3). Pendiente solo
   caracterizar Lexter (código fuente / modelo / modo de integración) al llegar a CP-Z1.
2. Plazos procesales = siempre sugerencia con confirmación (ya es política; se mantiene).
3. Datos reales de cliente para eval (CP-E4) = requieren su aprobación.

## Cómo arranca la terminal nueva
1. Leer `mia/CLAUDE.md`, `mia/HANDOFF.md`, la última entrada de `mia/memory/session-summaries.md`,
   este archivo y `docs/analisis-referencias-2026-07.md`.
2. Empezar por **CP-S1**. Un checkpoint a la vez, con su protocolo completo.
3. Los repos de referencia están en disco; leerlos al implementar cada checkpoint (no de memoria).
