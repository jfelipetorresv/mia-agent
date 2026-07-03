"""
Mia · test_telegram_bridge.py — gate de CP-B2 (puente de Telegram, Pilar B).

Verifica el puente COMPLETAMENTE OFFLINE (sin red, sin Telegram real, sin DB:
HTTP falso inyectado en MiaClient y callbacks falsos en TelegramBridge):

  (a) sin TELEGRAM_BOT_TOKEN → main() sale con 1 e imprime instrucciones amables
      (sin jerga técnica ni traceback).
  (b) update de un chat_id NO autorizado → ignorado por completo: ningún POST al
      API y ninguna respuesta al chat.
  (c) chat autorizado → POST correcto a /api/assistant/chat con el texto y el
      Bearer token del login; la reply vuelve como mensaje; el conversation_id
      se mantiene entre turnos y /nueva lo resetea. Además: el contenido del
      abogado NO aparece en los logs (solo métricas/ids).
  (d) reply gigante (> 4000 chars) → se envía como documento .md, no como texto.
  (e) 401 del API (JWT vencido) → re-login y reintento UNA vez, con el token nuevo.
  (f) /apagar desde el chat autorizado → el puente se detiene (on_stop); desde
      otro chat → ignorado.
  (g) error de red del API → mensaje amable al chat y el loop SIGUE (el turno
      siguiente funciona).

Exit 0 = PASS · 1 = FAIL. HALT si falla (CLAUDE.md §G).
    .venv\\Scripts\\python.exe execution\\test_telegram_bridge.py
"""
from __future__ import annotations

import asyncio
import io
import logging
import os
import sys
from contextlib import redirect_stdout
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

from mia.channels import telegram_bridge as tb  # noqa: E402

_results: list[tuple[str, bool]] = []

ALLOWED = 111
INTRUDER = 999


def check(name: str, ok: bool) -> None:
    _results.append((name, bool(ok)))
    print(("  [OK]   " if ok else "  [FAIL] ") + name)


# ── dobles de prueba: HTTP falso (MiaClient) y transporte falso (TelegramBridge) ──
class FakeResponse:
    def __init__(self, status_code: int, payload: dict | None = None,
                 content: bytes | None = None) -> None:
        self.status_code = status_code
        self._payload = payload or {}
        self.content = content or b""

    def json(self) -> dict:
        return self._payload


class FakeHTTP:
    """Simula el API de Mia: login siempre entrega un token nuevo (tok-1, tok-2...);
    las respuestas de /api/assistant/chat, /api/speech/transcribe y
    /api/speech/synthesize salen de colas guionadas (o lanzan)."""

    def __init__(self) -> None:
        self.calls: list[dict] = []
        self.login_count = 0
        self.chat_queue: list = []
        self.transcribe_queue: list = []
        self.synth_queue: list = []

    async def post(self, url: str, json: dict | None = None, headers: dict | None = None,
                   files: dict | None = None, data: dict | None = None):
        self.calls.append({"url": url, "json": json, "headers": headers or {},
                           "files": files, "data": data})
        if url.endswith("/api/auth/login"):
            self.login_count += 1
            return FakeResponse(200, {"token": f"tok-{self.login_count}", "tenant_id": "t"})
        if url.endswith("/api/assistant/chat"):
            return self._pop(self.chat_queue, "/assistant/chat")
        if url.endswith("/api/speech/transcribe"):
            return self._pop(self.transcribe_queue, "/speech/transcribe")
        if url.endswith("/api/speech/synthesize"):
            return self._pop(self.synth_queue, "/speech/synthesize")
        raise AssertionError(f"URL inesperada: {url}")

    @staticmethod
    def _pop(queue: list, name: str):
        assert queue, f"llamada a {name} no guionada"
        item = queue.pop(0)
        if isinstance(item, Exception):
            raise item
        return item

    def chat_calls(self) -> list[dict]:
        return [c for c in self.calls if c["url"].endswith("/api/assistant/chat")]

    def calls_to(self, suffix: str) -> list[dict]:
        return [c for c in self.calls if c["url"].endswith(suffix)]


class Recorder:
    """Captura lo que el puente 'envía a Telegram' y las peticiones de apagado."""

    def __init__(self) -> None:
        self.texts: list[tuple[int, str]] = []
        self.docs: list[tuple[int, str, bytes]] = []
        self.voices: list[tuple[int, bytes]] = []
        self.stops = 0

    async def send_text(self, chat_id: int, text: str) -> None:
        self.texts.append((chat_id, text))

    async def send_document(self, chat_id: int, filename: str, content: bytes) -> None:
        self.docs.append((chat_id, filename, content))

    async def send_voice(self, chat_id: int, ogg: bytes) -> None:
        self.voices.append((chat_id, ogg))

    async def on_stop(self) -> None:
        self.stops += 1


def make_bridge() -> tuple[tb.TelegramBridge, FakeHTTP, Recorder]:
    fake = FakeHTTP()
    rec = Recorder()
    client = tb.MiaClient("http://mia.test", "pipe@lexia.co", "secreta", http=fake)
    bridge = tb.TelegramBridge(
        allowed_chat_id=ALLOWED,
        client=client,
        send_text=rec.send_text,
        send_document=rec.send_document,
        on_stop=rec.on_stop,
        send_voice=rec.send_voice,
    )
    return bridge, fake, rec


# ── (a) sin TELEGRAM_BOT_TOKEN → exit 1 con instrucciones amables ──────────────
def check_missing_config() -> None:
    for var in ("TELEGRAM_BOT_TOKEN", "TELEGRAM_ALLOWED_CHAT_ID",
                "MIA_BRIDGE_EMAIL", "MIA_BRIDGE_PASSWORD"):
        os.environ.pop(var, None)
    buf = io.StringIO()
    with redirect_stdout(buf):
        rc = tb.main()
    out = buf.getvalue()
    check("a1 · sin TELEGRAM_BOT_TOKEN → main() sale con código 1", rc == 1)
    check("a2 · imprime instrucciones amables (BotFather + guía + .env)",
          "@BotFather" in out and "docs/telegram-setup.md" in out and ".env" in out)
    check("a3 · sin jerga técnica ni traceback en el mensaje",
          "Traceback" not in out and "Exception" not in out and "None" not in out)
    # chat_id no numérico → también mensaje amable (no un ValueError crudo)
    env = {"TELEGRAM_BOT_TOKEN": "t", "TELEGRAM_ALLOWED_CHAT_ID": "abc",
           "MIA_BRIDGE_EMAIL": "e@x.co", "MIA_BRIDGE_PASSWORD": "p"}
    try:
        tb.load_settings(env)
        friendly = False
    except tb.BridgeConfigError as exc:
        friendly = "dígitos" in str(exc) and "docs/telegram-setup.md" in str(exc)
    check("a4 · chat_id no numérico → explicación amable, no error técnico", friendly)


async def run_async_checks() -> None:
    # ── (b) chat NO autorizado → ignorado por completo ─────────────────────────
    bridge, fake, rec = make_bridge()
    await bridge.handle_message(INTRUDER, "hola Mia, soy un intruso")
    check("b1 · chat no autorizado → NINGÚN POST al API (ni login ni chat)",
          fake.calls == [])
    check("b2 · chat no autorizado → NINGUNA respuesta al chat",
          rec.texts == [] and rec.docs == [] and rec.stops == 0)

    # ── (c) chat autorizado → POST correcto, reply al chat, hilo persistente ───
    bridge, fake, rec = make_bridge()
    log_buf = io.StringIO()
    handler = logging.StreamHandler(log_buf)
    logging.getLogger("mia.channels.telegram").setLevel(logging.DEBUG)
    logging.getLogger("mia.channels.telegram").addHandler(handler)
    try:
        fake.chat_queue = [FakeResponse(200, {"conversation_id": "conv-1",
                                              "reply": "Hola Pipe, aquí estoy."})]
        await bridge.handle_message(ALLOWED, "Hola Mia, ¿cómo va todo?")
    finally:
        logging.getLogger("mia.channels.telegram").removeHandler(handler)
    calls = fake.chat_calls()
    check("c1 · un mensaje autorizado → UN POST a /api/assistant/chat con el texto",
          len(calls) == 1 and calls[0]["json"] == {"message": "Hola Mia, ¿cómo va todo?"})
    check("c2 · el POST lleva el Bearer token obtenido en el login",
          fake.login_count == 1
          and calls[0]["headers"].get("Authorization") == "Bearer tok-1")
    check("c3 · la reply del API llega al chat como mensaje de texto",
          rec.texts == [(ALLOWED, "Hola Pipe, aquí estoy.")])
    logged = log_buf.getvalue()
    check("c4 · el contenido del abogado y la reply NO se loguean (solo métricas)",
          "Hola Mia, ¿cómo va todo?" not in logged
          and "Hola Pipe, aquí estoy." not in logged)

    fake.chat_queue = [FakeResponse(200, {"conversation_id": "conv-1", "reply": "Sigo aquí."})]
    await bridge.handle_message(ALLOWED, "Segunda vuelta")
    check("c5 · el segundo turno reutiliza el conversation_id del hilo",
          fake.chat_calls()[-1]["json"] == {"message": "Segunda vuelta",
                                            "conversation_id": "conv-1"})
    await bridge.handle_message(ALLOWED, "/nueva")
    fake.chat_queue = [FakeResponse(200, {"conversation_id": "conv-2", "reply": "De cero."})]
    await bridge.handle_message(ALLOWED, "Empecemos de nuevo")
    check("c6 · /nueva resetea el hilo (el POST siguiente va SIN conversation_id)",
          fake.chat_calls()[-1]["json"] == {"message": "Empecemos de nuevo"}
          and any(t == (ALLOWED, tb.NEW_CONVERSATION_REPLY) for t in rec.texts))

    # ── (d) reply gigante → documento .md adjunto ──────────────────────────────
    bridge, fake, rec = make_bridge()
    giant = "análisis jurídico extenso " * 200          # ~5.200 chars > 3.900
    fake.chat_queue = [FakeResponse(200, {"conversation_id": "conv-3", "reply": giant})]
    await bridge.handle_message(ALLOWED, "Dame el análisis completo")
    check("d1 · reply > límite de Telegram → llega como documento, no como texto",
          rec.texts == [] and len(rec.docs) == 1)
    check("d2 · el documento es un .md con el contenido completo",
          rec.docs and rec.docs[0][1].endswith(".md")
          and rec.docs[0][2].decode("utf-8") == giant)

    # ── (e) 401 del API → re-login y reintento UNA vez ─────────────────────────
    bridge, fake, rec = make_bridge()
    fake.chat_queue = [
        FakeResponse(401, {"detail": "token vencido"}),
        FakeResponse(200, {"conversation_id": "conv-4", "reply": "De vuelta."}),
    ]
    await bridge.handle_message(ALLOWED, "¿Sigues ahí?")
    calls = fake.chat_calls()
    check("e1 · 401 del API → re-login (dos logins) y reintento UNA vez (dos POST)",
          fake.login_count == 2 and len(calls) == 2)
    check("e2 · el reintento va con el token RENOVADO y la reply llega al chat",
          calls[1]["headers"].get("Authorization") == "Bearer tok-2"
          and rec.texts == [(ALLOWED, "De vuelta.")])

    # ── (f) /apagar: emergencia desde el chat autorizado; ignorado desde otro ──
    bridge, fake, rec = make_bridge()
    await bridge.handle_message(INTRUDER, "/apagar")
    check("f1 · /apagar desde un chat NO autorizado → ignorado (el puente sigue)",
          bridge.stopped is False and rec.stops == 0 and fake.calls == [])
    await bridge.handle_message(ALLOWED, "/apagar")
    check("f2 · /apagar desde el chat autorizado → el puente se detiene",
          bridge.stopped is True and rec.stops == 1
          and any(cid == ALLOWED for cid, _ in rec.texts))
    fake.chat_queue = []
    await bridge.handle_message(ALLOWED, "¿hola?")
    check("f3 · tras /apagar no se procesan más turnos (ningún POST nuevo)",
          fake.chat_calls() == [])

    # ── (g) error de red → mensaje amable y el loop sigue ──────────────────────
    bridge, fake, rec = make_bridge()
    fake.chat_queue = [ConnectionError("red caída (simulada)")]
    await bridge.handle_message(ALLOWED, "Hola Mia")
    check("g1 · error de red del API → mensaje amable al chat (sin jerga)",
          rec.texts == [(ALLOWED, tb.FRIENDLY_ERROR)]
          and "problema técnico" in tb.FRIENDLY_ERROR)
    fake.chat_queue = [FakeResponse(200, {"conversation_id": "conv-5", "reply": "Ya volví."})]
    await bridge.handle_message(ALLOWED, "¿Y ahora?")
    check("g2 · el loop SIGUE: el turno siguiente funciona normal",
          rec.texts[-1] == (ALLOWED, "Ya volví."))
    # ni siquiera el envío del mensaje amable puede tumbar el loop
    async def boom_send(_cid: int, _txt: str) -> None:
        raise RuntimeError("Telegram caído (simulado)")
    bridge2, fake2, _ = make_bridge()
    bridge2._send_text = boom_send  # noqa: SLF001 — a propósito: peor escenario
    fake2.chat_queue = [ConnectionError("red caída")]
    await bridge2.handle_message(ALLOWED, "hola")   # no debe lanzar
    check("g3 · falla API + falla Telegram al avisar → el handler NO lanza",
          True)

    # ── (h) NOTA DE VOZ: voz entra → voz sale (CP-Z2) ──────────────────────────
    # h1 · bucle completo: transcribe (local) → chat → synthesize (local) → nota de voz
    bridge, fake, rec = make_bridge()
    audio_in = b"OggS" + b"\x00" * 64                    # una "nota de voz" entrante
    fake.transcribe_queue = [FakeResponse(200, {"text": "cómo va el caso Zurich"})]
    fake.chat_queue = [FakeResponse(200, {"conversation_id": "cv-v1",
                                          "reply": "Va bien, el borrador está listo."})]
    fake.synth_queue = [FakeResponse(200, content=b"OggS-voz-de-mia")]
    await bridge.handle_voice(ALLOWED, audio_in)
    tcalls = fake.calls_to("/api/speech/transcribe")
    scalls = fake.calls_to("/api/speech/synthesize")
    check("h1a · nota de voz → UN POST a /speech/transcribe con el audio y el Bearer",
          len(tcalls) == 1
          and tcalls[0]["files"]["audio"][1] == audio_in
          and tcalls[0]["headers"].get("Authorization") == "Bearer tok-1")
    check("h1b · el texto entendido va al asistente (POST a /assistant/chat)",
          fake.chat_calls() and fake.chat_calls()[0]["json"]["message"]
          == "cómo va el caso Zurich")
    check("h1c · la respuesta se sintetiza (POST a /speech/synthesize con el texto)",
          len(scalls) == 1 and scalls[0]["json"] == {"text": "Va bien, el borrador está listo."})
    check("h1d · Mia responde con NOTA DE VOZ (el audio del synth), no como texto",
          rec.voices == [(ALLOWED, b"OggS-voz-de-mia")]
          and (ALLOWED, "Va bien, el borrador está listo.") not in rec.texts)
    check("h1e · transparencia: Mia devuelve lo que ENTENDIÓ para verificación",
          any(cid == ALLOWED and tb.VOICE_HEARD_PREFIX in txt
              and "cómo va el caso Zurich" in txt for cid, txt in rec.texts))
    check("h1f · un solo login reutilizado para transcribe + chat + synthesize",
          fake.login_count == 1)

    # h2 · nota de voz de chat NO autorizado → ignorada por completo
    bridge, fake, rec = make_bridge()
    await bridge.handle_voice(INTRUDER, audio_in)
    check("h2 · nota de voz de chat no autorizado → ningún POST y ninguna respuesta",
          fake.calls == [] and rec.texts == [] and rec.voices == [])

    # h3 · nota de voz vacía → aviso amable, sin llamar al API
    bridge, fake, rec = make_bridge()
    await bridge.handle_voice(ALLOWED, b"")
    check("h3 · nota de voz vacía → aviso amable (no entendí), sin tocar el API",
          fake.calls == [] and rec.texts == [(ALLOWED, tb.VOICE_NOT_UNDERSTOOD)])

    # h4 · transcripción vacía (no se escuchó voz) → aviso, sin turno de chat
    bridge, fake, rec = make_bridge()
    fake.transcribe_queue = [FakeResponse(200, {"text": ""})]
    await bridge.handle_voice(ALLOWED, audio_in)
    check("h4 · no se escuchó voz → aviso amable y NO se llama al asistente",
          fake.chat_calls() == [] and rec.voices == []
          and (ALLOWED, tb.VOICE_NOT_UNDERSTOOD) in rec.texts)

    # h5 · respuesta larga → va por escrito (no una nota de voz eterna)
    bridge, fake, rec = make_bridge()
    long_reply = "detalle jurídico " * 100              # > VOICE_REPLY_MAX_CHARS
    fake.transcribe_queue = [FakeResponse(200, {"text": "resúmeme el expediente"})]
    fake.chat_queue = [FakeResponse(200, {"conversation_id": "cv-v5", "reply": long_reply})]
    await bridge.handle_voice(ALLOWED, audio_in)
    check("h5 · respuesta larga → texto (o adjunto), NO nota de voz; sin synth",
          rec.voices == [] and fake.calls_to("/api/speech/synthesize") == []
          and (len(long_reply) <= tb.TELEGRAM_TEXT_LIMIT and rec.texts
               or rec.docs))

    # h6 · la síntesis falla → degrada a texto (nunca se cae ni se queda muda)
    bridge, fake, rec = make_bridge()
    fake.transcribe_queue = [FakeResponse(200, {"text": "hola Mia"})]
    fake.chat_queue = [FakeResponse(200, {"conversation_id": "cv-v6", "reply": "Hola, Pipe."})]
    fake.synth_queue = [ConnectionError("TTS caído (simulado)")]
    await bridge.handle_voice(ALLOWED, audio_in)
    check("h6 · si el TTS falla → la respuesta llega como TEXTO (degradación)",
          rec.voices == [] and (ALLOWED, "Hola, Pipe.") in rec.texts)

    # h7 · el envío de la nota de voz falla → también degrada a texto
    bridge, fake, rec = make_bridge()
    fake.transcribe_queue = [FakeResponse(200, {"text": "hola"})]
    fake.chat_queue = [FakeResponse(200, {"conversation_id": "cv-v7", "reply": "Aquí estoy."})]
    fake.synth_queue = [FakeResponse(200, content=b"OggS-audio")]

    async def _boom_voice(_cid, _ogg):
        raise RuntimeError("Telegram rechazó la nota de voz")

    bridge._send_voice = _boom_voice  # noqa: SLF001 — peor escenario del envío
    await bridge.handle_voice(ALLOWED, audio_in)
    check("h7 · si enviar la nota de voz falla → la respuesta cae a TEXTO",
          (ALLOWED, "Aquí estoy.") in rec.texts)

    # h8 · modalidad: un mensaje de TEXTO NO dispara síntesis (voz solo si entra voz)
    bridge, fake, rec = make_bridge()
    fake.chat_queue = [FakeResponse(200, {"conversation_id": "cv-t", "reply": "Respuesta."})]
    await bridge.handle_message(ALLOWED, "pregunta escrita")
    check("h8 · texto entra → texto sale: NUNCA se llama a /speech/synthesize",
          fake.calls_to("/api/speech/synthesize") == []
          and rec.voices == [] and (ALLOWED, "Respuesta.") in rec.texts)

    # h9 · error de red del STT → mensaje amable, loop sigue (sin chat ni voz)
    bridge, fake, rec = make_bridge()
    fake.transcribe_queue = [ConnectionError("STT/API caído")]
    await bridge.handle_voice(ALLOWED, audio_in)
    check("h9 · STT/API caído en la voz → mensaje amable, sin turno ni nota de voz",
          rec.texts == [(ALLOWED, tb.FRIENDLY_ERROR)]
          and fake.chat_calls() == [] and rec.voices == [])

    # h10 · reply vacío del asistente → aviso honesto, NO un texto vacío ni synth
    bridge, fake, rec = make_bridge()
    fake.transcribe_queue = [FakeResponse(200, {"text": "hola"})]
    fake.chat_queue = [FakeResponse(200, {"conversation_id": "cv-v10", "reply": "   "})]
    await bridge.handle_voice(ALLOWED, audio_in)
    check("h10 · reply vacío → aviso honesto (sin texto vacío ni intento de voz)",
          (ALLOWED, tb.VOICE_EMPTY_REPLY) in rec.texts and rec.voices == []
          and fake.calls_to("/api/speech/synthesize") == []
          and not any(t == "" for _, t in rec.texts))


def main() -> int:
    print("== CP-B2 · puente de Telegram (bot privado single-chat → /api/assistant/chat) ==")
    check_missing_config()
    asyncio.run(run_async_checks())

    passed = sum(1 for _, ok in _results if ok)
    total = len(_results)
    print(f"\nRESULT: {passed}/{total} checks PASS")
    if passed == total:
        print("Puente de Telegram OK — CP-B2 verificado (auth, single-chat, adjuntos, resiliencia).")
        return 0
    print("Puente de Telegram FAIL — HALT: no avanzar (CLAUDE.md §G).")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
