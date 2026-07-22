## Checkpoint anterior: CP-Z1 — Dictado local (voz a texto) (2026-07-02)

### Qué cambió (lenguaje simple)

- Mia ya puede transcribir la voz del abogado SIN que el audio salga de su
  servidor: un nuevo servicio de dictado 100% local (mismo motor y parámetros
  que Lexter, el dictado que Pipe ya usa y validó en español jurídico).
- El backend está completo y probado; falta el botón de micrófono en la web
  (este HANDOFF). Opcionalmente, Mia puede "pulir" la puntuación del dictado
  con su modelo local (si Ollama está corriendo); si no, entrega el texto crudo.
- Si el servidor no tiene el modelo de voz descargado, el botón debe explicar
  en llano lo que el backend responde (503 con instrucción para el administrador).

### Frontend a construir (Cursor — capa 3): botón de micrófono

- **`POST /api/speech/transcribe`** (multipart/form-data, requiere Authorization
  como todo /api/*):
  - campo `audio`: archivo WAV PCM16 **16 kHz mono** (el navegador debe
    re-muestrear antes de enviar — ver nota técnica), máx. 5 minutos / 32 MB.
  - campo opcional `pulir`: `"true"` para pedir la corrección de puntuación con
    el modelo local (fail-soft: puede volver null).
  - Respuesta: `{text, cleaned_text, duration_seconds, message}` — `text` es la
    transcripción cruda; `cleaned_text` la versión pulida o null; `message`
    solo viene cuando no se escuchó voz ("No se escuchó voz en la grabación.").
  - Errores en llano listos para pantalla: 400 (audio ilegible), 413 (muy
    grande), 429 (demasiados clips seguidos), 503 (dictado no instalado en el
    servidor) — mostrar el `detail` tal cual (lib/api.ts ya lo propaga).
- **Nota técnica de captura:** `MediaRecorder` produce webm/opus, que el backend
  NO acepta. Capturar con Web Audio API (`AudioContext` + `MediaStreamSource`),
  acumular Float32, re-muestrear a 16 kHz mono (p. ej. `OfflineAudioContext`) y
  empaquetar WAV PCM16 en el cliente (~30 líneas; sin librerías externas).
- **UI sugerida:** botón 🎤 junto al campo de texto del asunto y del asistente;
  estados: inactivo → grabando (pulso rojo + "Dictando… toca para terminar") →
  transcribiendo (spinner "Mia está escribiendo tu dictado…") → texto insertado
  en el campo (usar `cleaned_text ?? text`). Si `message` viene, mostrarlo en
  ámbar. Accesibilidad: `aria-pressed` en el botón, estado comunicado con texto
  además del color. Pedir permiso de micrófono solo al primer clic.
- Referencia de diseño (en disco): `frontend/hooks/useSpeech.ts` y
  `components/Chat/MicButton.tsx`.

### Comportamiento esperado

- Dictar un clip corto en español → el texto aparece en el campo en ~1-3 s
  (motor local, sin GPU). Clips largos (hasta 5 min) tardan más y llegan
  completos. Un clip en silencio → aviso honesto, no texto inventado.
- El audio JAMÁS sale del servidor: no hay que pedir consentimiento de nube.

### Resultado de verificación (3 capas)

- Capa 1: gate nuevo `test_speech_stt.py` 35/35 (incluye integración real con
  el modelo descargado: español correcto y audio de 76 s por el camino VAD);
  regresión completa en verde (test_rls HALT).
- Capa 2 (revisor adversarial independiente): ver memory/progress.md sesión 28.
- Capa 3 (Cursor): PENDIENTE — construir el botón descrito arriba.

---

