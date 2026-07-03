# Diseño de integración de Lexter en Mia — base de CP-Z1 (voz-a-texto local)

_2026-07-02. Análisis del repo `github.com/jfelipetorresv/Lexter-Voice-Command` (HEAD 307fd9d),
el dictado local que Pipe desarrolló. Este documento es el diseño técnico del checkpoint CP-Z1
(Ola 3, voz). Decisión ya tomada: **voz 100% local**._

## Qué es Lexter
Fork de **Handy** (CJ Pais), **licencia MIT** → se puede reutilizar código, parámetros y prompts
citando el copyright. App de escritorio **Tauri 2 + Rust** (backend de voz) + React/TS (solo UI).
Todo el pipeline de voz vive en Rust; el frontend no toca el audio.

## Flujo del audio (captura → VAD → STT → limpieza)
1. **Captura** (`src-tauri/src/audio_toolkit/audio/recorder.rs`): `cpal` a tasa/formato nativo del
   micrófono, mezcla a mono.
2. **Resampleo** (`rubato`): baja a **16 kHz mono f32**, tramas de **30 ms (480 muestras)**.
3. **VAD** (`audio_toolkit/vad/silero.rs` + `smoothed.rs`): Silero VAD descarta el silencio; solo
   acumula tramas de voz. Push-to-talk (mantener tecla) + recorte de silencios internos.
4. **STT** (`managers/transcription.rs`): al soltar la tecla, el audio 16 kHz va al motor; audios
   largos se parten en trozos de ~60 s.
5. **Limpieza opcional** (`actions.rs::post_process_transcription` + `llm_client.rs`): manda el
   texto a un LLM local (Ollama) para pulirlo.

## Motor STT (lo más importante)
Usa la crate **`transcribe-rs` v0.3.8** con dos backends; catálogo y URLs en `managers/model.rs`
(descarga de `blob.handy.computer`, verificado por SHA256). Modelos con español:

| Modelo | Motor/formato | Control de español | Nota |
|---|---|---|---|
| **Parakeet TDT 0.6B v3** (`parakeet-tdt-0.6b-v3`) | ONNX int8, ~456 MB | **NO** fuerza idioma ni vocabulario (solo autodetecta) | **Es el DEFAULT** que la onboarding descarga y auto-selecciona. Rápido en CPU. |
| **Whisper Large v3** (`large`) | GGML .bin, ~1 GB | **SÍ**: `language="es"` + prompt de vocabulario + contexto | Mejor para español jurídico controlado. |
| Whisper Turbo (`turbo`) | GGML, ~1.5 GB | SÍ | Balance velocidad/calidad. |
| Canary 1B v2 | ONNX int8, ~691 MB | SÍ (25 idiomas) | Muy preciso multilingüe. |

**Toda la ingeniería de "español correcto"** (forzar `es`, glosario de hasta 40 términos, no
traducir ES→EN, contexto entre trozos) vive en `transcription.rs::build_whisper_initial_prompt()`
y aplica al **camino Whisper**. Aceleración Windows = **DirectML** (`Cargo.toml` feature
`ort-directml`). El VAD Silero (`silero_vad_v4.onnx`) es común a todos.

> **DECISIÓN RESUELTA por Pipe (2026-07-02, sesión 27): Parakeet v3.** Pipe confirmó que
> validó Lexter con el modelo POR DEFECTO — es decir, Parakeet v3 — y su español jurídico
> "va bien" en uso real. **CP-Z1 se construye con Parakeet v3** (vía `sherpa-onnx` +
> DirectML). **Whisper large-v3** (vía `faster-whisper`, con glosario del despacho y
> no-traducir) queda como opción configurable FUTURA, no v1. No re-preguntar.

## Parámetros que ya funcionan (reusar tal cual)
- STT: **16 000 Hz, mono, f32**. Trama VAD **30 ms / 480 muestras**.
- **Silero VAD umbral 0.3**; suavizado `SmoothedVad(15, 15, 2)` = pre-roll **450 ms**, hangover
  **450 ms**, onset **60 ms** (`managers/audio.rs:124-126`).
- Chunking STT objetivo **60 s** (±4 s buscando corte silencioso). Audios <1 s → pad a 1.25 s.

## Post-proceso con Ollama (reusar)
- Proveedor `ollama`, base `http://localhost:11434/v1` (OpenAI-compatible), modelo default
  `llama3.1:8b` (`settings.rs`). Mia ya habla Ollama por su gateway → encaja directo.
- Prompts listos en `settings.rs`: **`clean_dictation`** (limpieza general, no-traducir) y
  **`spanish_polish`** (ya redactado en español — ideal para dictado jurídico). Hay un guardrail
  en `actions.rs` que rechaza si la salida parece traducción ES→EN accidental y reinyecta el glosario.

## Portabilidad a Python
- **Reusable tal cual:** pesos ONNX de los modelos, `silero_vad_v4.onnx`, vocab/tokens, y TODOS
  los parámetros y prompts.
- **Motor en Python:** ONNX (Parakeet/Canary) → **`sherpa-onnx`** con provider **DirectML** (mismo
  camino que Lexter). Whisper → **`faster-whisper`** (CTranslate2 int8, `large-v3`, `language="es"`
  + `initial_prompt` de glosario replicando `build_whisper_initial_prompt`).
- **VAD:** `silero_vad_v4.onnx` corre en Python con `onnxruntime`; el suavizado (~40 líneas de
  `smoothed.rs`) se reimplementa trivial.
- **Reimplementar en Python (hoy en Rust):** captura del navegador, resampleo a 16 kHz, mezcla
  mono, `SmoothedVad`, chunking 60 s, filtro de glosario. Lógica simple.
- **Licencia:** Lexter/Handy MIT. Los pesos de modelos tienen licencias propias (Whisper MIT;
  Parakeet/Canary NVIDIA/NeMo, típico CC-BY-4.0) → **descargarlos en instalación, no redistribuir
  en el repo**.

## Arquitectura de integración (botón de micrófono nativo, sin streaming para el MVP)
```
[Web Mia · botón 🎤]  Web Audio API captura → resamplea a 16 kHz mono f32
   → POST multipart  /api/speech/transcribe  (audio 16k + tenant + idioma + glosario)
        ▼
[FastAPI · backend/mia/speech/]
   1. Silero VAD (onnxruntime, 0.3 / 30 ms / pre-roll 450 ms)      ← reusado de Lexter
   2. STT Python (faster-whisper "es"  ó  sherpa-onnx Parakeet)    ← modelos reusados
   3. (opcional) limpieza con el Ollama local de Mia, prompt spanish_polish + guardrail ES→EN
        ▼
   { text, cleaned_text } → se inserta en el campo de Mia
```
Grabación por pulsación (no streaming en vivo) → **no hace falta WebSocket para el MVP**: se captura
el clip completo y se transcribe en el backend.

## Los 5 pasos de CP-Z1
1. `backend/mia/speech/`: pipeline VAD Silero + resampleo 16 kHz + chunking 60 s (portado de Lexter).
2. Motor STT elegido (faster-whisper `es` o sherpa-onnx Parakeet) en una clase `Transcriber`
   (`.transcribe(pcm16k) -> texto`); descargar pesos en instalación.
3. Endpoint FastAPI multi-tenant `POST /api/speech/transcribe` (validación de tamaño, rate-limit,
   tope de duración ~5 min, candado de privacidad `allow_cloud_audio=false`).
4. Post-proceso opcional con el Ollama local de Mia (`spanish_polish`/`clean_dictation` + guardrail).
5. Botón de micrófono en la web de Mia (captura → resamplea 16 kHz → envía; estados grabando/
   transcribiendo; inserta el texto). Frontend → HANDOFF para Cursor.

## Riesgos
- **Latencia sin GPU:** Whisper large-v3 en CPU va lento; mitigar con int8/`large-v3-turbo` o GPU
  en el servidor del despacho. Parakeet es más rápido en CPU pero menos controlable en español.
- **Privacidad:** audio y post-proceso 100% locales (Ollama de Mia), nunca nube. Ya es la decisión.
- **Tamaño de modelo:** descargar en instalación, no versionar los pesos.

## Referencias del repo (en el clon de trabajo)
`src-tauri/src/managers/{transcription.rs, model.rs, audio.rs}` · `audio_toolkit/vad/{silero.rs,
smoothed.rs}` · `audio_toolkit/audio/recorder.rs` · `actions.rs` · `llm_client.rs` · `settings.rs`
· `Cargo.toml` · `LICENSE` (MIT).
