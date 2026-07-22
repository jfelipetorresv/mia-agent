## Checkpoint anterior: CP-Z2 — Conversación por voz en Telegram (2026-07-03)

### Qué cambió (lenguaje simple)

- **Mia ya habla.** Si el abogado le manda una NOTA DE VOZ a su bot privado de
  Telegram, Mia la transcribe (en el servidor del despacho, el audio nunca sale de
  ahí), responde, y le devuelve una NOTA DE VOZ hablada. Es el "asistente personal
  en el celular": le hablas y te contesta hablando.
- Regla de modalidad: **voz entra → voz sale; texto entra → texto sale** (el chat
  de texto por Telegram no cambia). Al recibir voz, Mia primero devuelve por
  escrito lo que ENTENDIÓ (para que el abogado verifique la transcripción) y luego
  la nota de voz de la respuesta.
- Respuestas largas (un borrador) siguen yendo por escrito; solo las respuestas
  conversacionales cortas se dicen habladas.

### Frontend (Cursor — capa 3): NO hay UI web nueva

- CP-Z2 vive 100% en el **canal de Telegram** (backend). No toca `frontend/`. El
  asistente conversacional de Mia no tiene pantalla web (es Telegram), así que no
  hay nada que construir ni revisar en la interfaz. El motor de voz de salida
  (`/api/speech/synthesize`, ver abajo) queda **reutilizable** para un futuro botón
  "Escuchar" en la web, pero eso NO es parte de este checkpoint.
- **La capa 3 de este checkpoint la hace Pipe en vivo:** crear el bot de Telegram
  (guía `docs/telegram-setup.md`), instalar la voz desde el Panel (botón "Instalar
  dictado por voz", que ahora también baja el modelo de voz de salida), y **dictar
  una nota de voz real** para oír a Mia responder hablando.

### Endpoint nuevo (por si la web lo usa después)

- **`POST /api/speech/synthesize`** (auth como todo /api/*): body `{"text": "..."}`
  → responde audio **OGG/Opus** (`audio/ogg`), 100% local. Errores en llano: 400
  (texto vacío), 413 (muy largo), 429 (rate-limit), 503 (voz no instalada u
  ocupada), 403 (motor de nube sin opt-in — hoy no aplica, es local).

### Resultado de verificación (3 capas)

- Capa 1: gate nuevo `test_speech_tts.py` **26/26** (síntesis local, códec Opus
  round-trip, candado de privacidad, 503 al estar ocupado, rate-limit);
  `test_telegram_bridge.py` extendido **37/37** (bucle de voz completo, modalidad,
  degradación a texto si el TTS falla, reply vacío, chat no autorizado);
  `test_speech_stt.py` **60/60** (instalación ahora incluye el modelo de voz);
  regresión completa **ALL PASS (52 suites)** (test_rls HALT). Sin `npm build`
  (no hay frontend web).
- Capa 2 (revisor adversarial independiente): confidencialidad, autorización,
  modalidad, instalación y concurrencia CONFIRMADOS; 1 MAYOR (espera del semáforo
  sin tope → 503 explícito) + 2 MENORES (reply vacío, guardia de tamaño) CERRADOS
  antes del commit. Ver memory/progress.md sesión 30.
- Capa 3: PENDIENTE — Pipe dicta una nota de voz real (lo único que la
  verificación automatizada no cubre).

---

