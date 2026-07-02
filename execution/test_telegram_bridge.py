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
    def __init__(self, status_code: int, payload: dict | None = None) -> None:
        self.status_code = status_code
        self._payload = payload or {}

    def json(self) -> dict:
        return self._payload


class FakeHTTP:
    """Simula el API de Mia: login siempre entrega un token nuevo (tok-1, tok-2...);
    las respuestas de /api/assistant/chat salen de una cola guionada (o lanzan)."""

    def __init__(self) -> None:
        self.calls: list[dict] = []
        self.login_count = 0
        self.chat_queue: list = []

    async def post(self, url: str, json: dict | None = None, headers: dict | None = None):
        self.calls.append({"url": url, "json": json, "headers": headers or {}})
        if url.endswith("/api/auth/login"):
            self.login_count += 1
            return FakeResponse(200, {"token": f"tok-{self.login_count}", "tenant_id": "t"})
        if url.endswith("/api/assistant/chat"):
            assert self.chat_queue, "llamada a /assistant/chat no guionada"
            item = self.chat_queue.pop(0)
            if isinstance(item, Exception):
                raise item
            return item
        raise AssertionError(f"URL inesperada: {url}")

    def chat_calls(self) -> list[dict]:
        return [c for c in self.calls if c["url"].endswith("/api/assistant/chat")]


class Recorder:
    """Captura lo que el puente 'envía a Telegram' y las peticiones de apagado."""

    def __init__(self) -> None:
        self.texts: list[tuple[int, str]] = []
        self.docs: list[tuple[int, str, bytes]] = []
        self.stops = 0

    async def send_text(self, chat_id: int, text: str) -> None:
        self.texts.append((chat_id, text))

    async def send_document(self, chat_id: int, filename: str, content: bytes) -> None:
        self.docs.append((chat_id, filename, content))

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
