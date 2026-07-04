"""Mia · channels.telegram_bridge — CP-B2 (Pilar B): Mia en el celular por Telegram.

Puente standalone (``python -m mia.channels.telegram_bridge``) estilo ClaudeClaw:
un bot PRIVADO de Telegram bloqueado a UN solo chat autorizado, que reenvía cada
mensaje del abogado al modo asistente del backend (POST /api/assistant/chat, CP-B1)
y devuelve la respuesta al chat. El puente NO toca la DB ni el motor: habla solo
con el API con un JWT obtenido vía POST /api/auth/login (MIA_BRIDGE_EMAIL /
MIA_BRIDGE_PASSWORD), así RLS y la política de modelo aplican igual que en el web.

Seguridad (bot privado single-chat):
  · Cualquier update de un chat_id distinto de TELEGRAM_ALLOWED_CHAT_ID se IGNORA
    por completo — ni siquiera se responde; solo se loguea el chat_id (métrica).
  · ``/apagar`` desde el chat autorizado detiene el puente (frase de emergencia).
  · ``/nueva`` inicia una conversación nueva (el conversation_id vive en memoria).
  · §G / regla de negocio: NUNCA se loguea el contenido de los mensajes del
    abogado ni de las respuestas — solo ids y longitudes.

Resiliencia:
  · Timeout HTTP generoso (300s): el motor por suscripción tarda 1-3 min por turno.
  · 401 del API → re-login automático y UN reintento (el JWT expira).
  · Error de red/API → mensaje amable al chat y el loop SIGUE (nunca se cae por
    una excepción de un turno); el polling de Telegram reintenta con backoff.
  · Respuestas > ~3900 chars (límite de Telegram ~4096) → se envían como archivo
    .md adjunto en lugar de texto.

Testabilidad (execution/test_telegram_bridge.py, TODO mockeado): la lógica vive en
``MiaClient`` (HTTP inyectable) y ``TelegramBridge`` (send_text / send_document /
on_stop inyectables); python-telegram-bot solo se importa dentro de ``run_bot``.
"""
from __future__ import annotations

import asyncio
import io
import logging
import os
import sys
from dataclasses import dataclass
from typing import Awaitable, Callable

from .relay import RelayApiError, RelayClient

logger = logging.getLogger("mia.channels.telegram")

DEFAULT_API_URL = "http://127.0.0.1:8000"

# Límite práctico de un mensaje de texto de Telegram (~4096); margen para no partir.
TELEGRAM_TEXT_LIMIT = 3900

# El motor por suscripción (CLI de Claude Code) puede tardar 1-3 min por respuesta.
HTTP_TIMEOUT_SECONDS = 300.0

SHUTDOWN_COMMAND = "/apagar"
NEW_CONVERSATION_COMMAND = "/nueva"

FRIENDLY_ERROR = "Mia está teniendo un problema técnico, intenta en un momento."
SHUTDOWN_REPLY = "Listo, apago el puente de Telegram. Para reactivarlo, ejecuta scripts/start_telegram.ps1."
NEW_CONVERSATION_REPLY = "Listo, empezamos una conversación nueva. Cuéntame."
ATTACHMENT_FILENAME = "respuesta-de-mia.md"

# CP-Z2: si el abogado manda una NOTA DE VOZ, Mia responde HABLANDO (voz entra →
# voz sale). Respuestas más largas que esto se dejan por escrito (una nota de voz
# de varios minutos leyendo un borrador es mala experiencia).
VOICE_REPLY_MAX_CHARS = 1000
VOICE_NOT_UNDERSTOOD = "No entendí bien la nota de voz. ¿Puedes repetirla, por favor?"
# Al recibir voz, Mia devuelve primero lo que ENTENDIÓ, para que el abogado
# verifique la transcripción (la voz-a-texto puede errar — criterio [VERIFICAR]).
VOICE_HEARD_PREFIX = "Entendí: "
VOICE_TOO_LONG_NOTE = "La respuesta es larga, te la dejo por escrito:"
VOICE_EMPTY_REPLY = "No obtuve una respuesta esta vez. Intenta de nuevo."
# Techo de tamaño de una nota de voz entrante antes de siquiera descargarla
# (defensa en profundidad; la Bot API ya limita descargas de bots y el backend
# rechaza > 32 MB al decodificar).
MAX_VOICE_BYTES = 20 * 1024 * 1024

# Backoff del polling ante caídas de red (segundos): 5 → 10 → 20 → ... → tope 300.
_BACKOFF_INITIAL = 5.0
_BACKOFF_MAX = 300.0


class BridgeConfigError(Exception):
    """Configuración incompleta — el mensaje va dirigido al abogado, sin jerga."""


# El puente reusa el cliente de relay común (CP-E6): credenciales fuera del núcleo,
# login JWT y re-login ante 401. `MiaApiError`/`MiaClient` se conservan como nombres
# locales por compatibilidad (el gate y start_telegram.ps1 los usan).
MiaApiError = RelayApiError


@dataclass
class BridgeSettings:
    bot_token: str
    allowed_chat_id: int
    api_url: str
    email: str
    password: str


_MISSING_CONFIG_MESSAGE = """\
Mia todavía no puede conectarse a Telegram: falta completar la configuración.

Qué falta: {missing}

Cómo completarla (5 minutos, guía completa en docs/telegram-setup.md):
  1. En Telegram, habla con @BotFather y crea tu bot con /newbot.
  2. Copia la clave secreta que te entrega BotFather.
  3. Abre el archivo de configuración .env (en la carpeta principal de Mia)
     y completa estas líneas (quítales el # del inicio):
        TELEGRAM_BOT_TOKEN=la clave de BotFather
        TELEGRAM_ALLOWED_CHAT_ID=tu número de chat (la guía explica cómo obtenerlo)
        MIA_BRIDGE_EMAIL=tu correo de inicio de sesión en Mia
        MIA_BRIDGE_PASSWORD=tu contraseña de Mia
  4. Guarda el archivo y vuelve a ejecutar scripts/start_telegram.ps1.
"""


def load_settings(env: dict[str, str] | None = None) -> BridgeSettings:
    """Lee la configuración del entorno. Si falta algo, explica QUÉ y CÓMO — sin jerga."""
    env = env if env is not None else dict(os.environ)
    labels = {
        "TELEGRAM_BOT_TOKEN": "la clave del bot (TELEGRAM_BOT_TOKEN)",
        "TELEGRAM_ALLOWED_CHAT_ID": "tu número de chat autorizado (TELEGRAM_ALLOWED_CHAT_ID)",
        "MIA_BRIDGE_EMAIL": "tu correo de Mia (MIA_BRIDGE_EMAIL)",
        "MIA_BRIDGE_PASSWORD": "tu contraseña de Mia (MIA_BRIDGE_PASSWORD)",
    }
    missing = [label for key, label in labels.items() if not (env.get(key) or "").strip()]
    if missing:
        raise BridgeConfigError(_MISSING_CONFIG_MESSAGE.format(missing="; ".join(missing)))

    raw_chat_id = env["TELEGRAM_ALLOWED_CHAT_ID"].strip()
    try:
        allowed_chat_id = int(raw_chat_id)
    except ValueError:
        raise BridgeConfigError(
            "El número de chat (TELEGRAM_ALLOWED_CHAT_ID) debe ser solo dígitos "
            "(puede empezar con un signo menos). Revisa el paso 4 de docs/telegram-setup.md."
        ) from None

    return BridgeSettings(
        bot_token=env["TELEGRAM_BOT_TOKEN"].strip(),
        allowed_chat_id=allowed_chat_id,
        api_url=(env.get("MIA_API_URL") or DEFAULT_API_URL).strip().rstrip("/"),
        email=env["MIA_BRIDGE_EMAIL"].strip(),
        password=env["MIA_BRIDGE_PASSWORD"].strip(),
    )


class MiaClient(RelayClient):
    """Cliente del puente de Telegram hacia el API de Mia. Toda la lógica (login JWT,
    re-login ante 401, chat/transcribe/synthesize) vive en `RelayClient` (channels.relay),
    reusable por cualquier canal. Se conserva la subclase como punto de extensión y por
    el nombre que el gate y el runner ya usan."""


class TelegramBridge:
    """Lógica del puente, independiente de python-telegram-bot (testeable).

    ``send_text(chat_id, text)``, ``send_document(chat_id, filename, content)`` y
    ``on_stop()`` son callbacks async inyectados por el runner real (o por el gate).
    """

    def __init__(
        self,
        allowed_chat_id: int,
        client: MiaClient,
        send_text: Callable[[int, str], Awaitable[None]],
        send_document: Callable[[int, str, bytes], Awaitable[None]],
        on_stop: Callable[[], Awaitable[None]],
        send_voice: Callable[[int, bytes], Awaitable[None]] | None = None,
    ) -> None:
        self.allowed_chat_id = allowed_chat_id
        self.client = client
        self._send_text = send_text
        self._send_document = send_document
        self._on_stop = on_stop
        self._send_voice = send_voice
        self.stopped = False
        # conversation_id por chat, en memoria (un solo chat autorizado; /nueva resetea).
        self.conversations: dict[int, str] = {}

    async def handle_message(self, chat_id: int, text: str | None) -> None:
        """Procesa un mensaje entrante. NUNCA lanza: un turno fallido no tumba el loop."""
        try:
            await self._handle(chat_id, text)
        except Exception:  # noqa: BLE001 — resiliencia: el loop sigue pase lo que pase
            logger.exception("Turno de Telegram falló (chat_id=%s)", chat_id)
            await self._safe_send_text(chat_id, FRIENDLY_ERROR)

    async def _handle(self, chat_id: int, text: str | None) -> None:
        # SEGURIDAD: bot privado — cualquier otro chat se ignora POR COMPLETO
        # (ni respuesta ni eco del contenido; solo el chat_id, que no es contenido).
        if chat_id != self.allowed_chat_id:
            logger.warning("Mensaje IGNORADO de chat no autorizado (chat_id=%s)", chat_id)
            return
        if self.stopped:
            return
        text = (text or "").strip()
        if not text:
            return

        command = text.split()[0].lower()
        if command == SHUTDOWN_COMMAND:
            logger.info("Frase de emergencia recibida — deteniendo el puente.")
            self.stopped = True
            await self._safe_send_text(chat_id, SHUTDOWN_REPLY)
            await self._on_stop()
            return
        if command == NEW_CONVERSATION_COMMAND:
            self.conversations.pop(chat_id, None)
            await self._send_text(chat_id, NEW_CONVERSATION_REPLY)
            return

        logger.info("Turno entrante (chat_id=%s, %d chars)", chat_id, len(text))
        try:
            conversation_id, reply = await self.client.chat(
                text, self.conversations.get(chat_id)
            )
        except Exception:  # noqa: BLE001 — red caída, API caído, 5xx: mensaje amable
            logger.exception("El API de Mia no respondió (chat_id=%s)", chat_id)
            await self._safe_send_text(chat_id, FRIENDLY_ERROR)
            return
        self.conversations[chat_id] = conversation_id
        await self._deliver_reply(chat_id, reply)

    async def _deliver_reply(self, chat_id: int, reply: str) -> None:
        """Respuesta al chat; si excede el límite de Telegram, va como .md adjunto."""
        logger.info("Respuesta lista (chat_id=%s, %d chars)", chat_id, len(reply))
        if len(reply) > TELEGRAM_TEXT_LIMIT:
            await self._send_document(chat_id, ATTACHMENT_FILENAME, reply.encode("utf-8"))
        else:
            await self._send_text(chat_id, reply)

    async def handle_voice(self, chat_id: int, audio: bytes) -> None:
        """Procesa una NOTA DE VOZ entrante. NUNCA lanza: un turno fallido no tumba
        el loop (mismo contrato que handle_message)."""
        try:
            await self._handle_voice(chat_id, audio)
        except Exception:  # noqa: BLE001 — resiliencia: el loop sigue pase lo que pase
            logger.exception("Nota de voz de Telegram falló (chat_id=%s)", chat_id)
            await self._safe_send_text(chat_id, FRIENDLY_ERROR)

    async def _handle_voice(self, chat_id: int, audio: bytes) -> None:
        # SEGURIDAD: idéntico a _handle — cualquier otro chat se ignora POR COMPLETO
        # (el runner ya no debería ni descargar el audio de un chat ajeno).
        if chat_id != self.allowed_chat_id:
            logger.warning("Nota de voz IGNORADA de chat no autorizado (chat_id=%s)", chat_id)
            return
        if self.stopped:
            return
        if not audio:
            await self._safe_send_text(chat_id, VOICE_NOT_UNDERSTOOD)
            return

        # 1) Voz → texto (STT local en el servidor de Mia; el audio no sale de ahí).
        logger.info("Nota de voz entrante (chat_id=%s, %d bytes)", chat_id, len(audio))
        try:
            heard = await self.client.transcribe(audio)
        except Exception:  # noqa: BLE001 — API/STT caído: mensaje amable, loop sigue
            logger.exception("No se pudo transcribir la nota de voz (chat_id=%s)", chat_id)
            await self._safe_send_text(chat_id, FRIENDLY_ERROR)
            return
        if not heard:
            await self._safe_send_text(chat_id, VOICE_NOT_UNDERSTOOD)
            return

        # Transparencia: devolver lo que Mia entendió para que el abogado verifique.
        await self._safe_send_text(chat_id, f"{VOICE_HEARD_PREFIX}“{heard}”")

        # 2) Turno normal del asistente con ese texto.
        try:
            conversation_id, reply = await self.client.chat(
                heard, self.conversations.get(chat_id)
            )
        except Exception:  # noqa: BLE001
            logger.exception("El API de Mia no respondió a la voz (chat_id=%s)", chat_id)
            await self._safe_send_text(chat_id, FRIENDLY_ERROR)
            return
        self.conversations[chat_id] = conversation_id

        # 3) Voz entra → voz sale: si la respuesta es corta, Mia contesta hablando.
        await self._deliver_voice_reply(chat_id, reply)

    async def _deliver_voice_reply(self, chat_id: int, reply: str) -> None:
        """Respuesta hablada a una nota de voz. Corta → nota de voz sintetizada;
        larga o si la síntesis falla → texto/adjunto (degrada, nunca se cae)."""
        reply = reply or ""
        if not reply.strip():
            # Reply vacío del asistente: un texto vacío lo rechaza Telegram (400) y
            # el abogado vería "problema técnico" — mejor un aviso honesto (capa 2).
            await self._safe_send_text(chat_id, VOICE_EMPTY_REPLY)
            return
        can_voice = self._send_voice is not None and len(reply) <= VOICE_REPLY_MAX_CHARS
        if not can_voice:
            if reply and len(reply) > VOICE_REPLY_MAX_CHARS:
                await self._safe_send_text(chat_id, VOICE_TOO_LONG_NOTE)
            await self._deliver_reply(chat_id, reply)
            return
        try:
            ogg = await self.client.synthesize(reply)
        except Exception:  # noqa: BLE001 — TTS/API falló: degrada a texto
            logger.exception("No se pudo sintetizar la voz (chat_id=%s); va texto", chat_id)
            await self._deliver_reply(chat_id, reply)
            return
        if not ogg:
            await self._deliver_reply(chat_id, reply)
            return
        try:
            await self._send_voice(chat_id, ogg)
            logger.info("Respuesta de voz enviada (chat_id=%s, %d bytes)", chat_id, len(ogg))
        except Exception:  # noqa: BLE001 — envío de la nota falló: cae a texto
            logger.exception("No se pudo enviar la nota de voz (chat_id=%s); va texto", chat_id)
            await self._deliver_reply(chat_id, reply)

    async def _safe_send_text(self, chat_id: int, text: str) -> None:
        try:
            await self._send_text(chat_id, text)
        except Exception:  # noqa: BLE001
            logger.exception("No se pudo enviar el mensaje al chat (chat_id=%s)", chat_id)


def run_bot(settings: BridgeSettings) -> int:
    """Arranca el bot real (python-telegram-bot v21, long-polling) con reconexión.

    Import LAZY de ``telegram`` para que la lógica de arriba sea testeable sin el bot.
    """
    from telegram import Update
    from telegram.ext import Application, MessageHandler, filters

    application = Application.builder().token(settings.bot_token).build()
    client = MiaClient(settings.api_url, settings.email, settings.password)

    async def send_text(chat_id: int, text: str) -> None:
        await application.bot.send_message(chat_id=chat_id, text=text)

    async def send_document(chat_id: int, filename: str, content: bytes) -> None:
        await application.bot.send_document(
            chat_id=chat_id, document=io.BytesIO(content), filename=filename
        )

    async def send_voice(chat_id: int, ogg: bytes) -> None:
        buf = io.BytesIO(ogg)
        buf.name = "mia.ogg"
        await application.bot.send_voice(chat_id=chat_id, voice=buf)

    async def on_stop() -> None:
        application.stop_running()

    bridge = TelegramBridge(
        allowed_chat_id=settings.allowed_chat_id,
        client=client,
        send_text=send_text,
        send_document=send_document,
        on_stop=on_stop,
        send_voice=send_voice,
    )

    async def on_message(update: Update, _context) -> None:
        message = update.effective_message
        chat = update.effective_chat
        if message is None or chat is None:
            return
        await bridge.handle_message(chat.id, message.text)

    async def on_voice(update: Update, _context) -> None:
        message = update.effective_message
        chat = update.effective_chat
        if message is None or chat is None or message.voice is None:
            return
        # SEGURIDAD: no descargar audio de un chat no autorizado (defensa antes de
        # tocar la red; el bridge lo re-verifica igual).
        if chat.id != settings.allowed_chat_id:
            logger.warning("Nota de voz IGNORADA de chat no autorizado (chat_id=%s)", chat.id)
            return
        # Defensa en profundidad: rechazar una nota enorme ANTES de bajarla a RAM
        # (hallazgo capa 2). El backend igual acota al decodificar.
        size = getattr(message.voice, "file_size", None)
        if size and size > MAX_VOICE_BYTES:
            await bridge._safe_send_text(
                chat.id, "Esa nota de voz es muy larga. Envíala en fragmentos más cortos."
            )
            return
        try:
            tg_file = await message.voice.get_file()
            audio = bytes(await tg_file.download_as_bytearray())
        except Exception:  # noqa: BLE001 — fallo al bajar el audio: mensaje amable
            logger.exception("No se pudo descargar la nota de voz (chat_id=%s)", chat.id)
            await bridge._safe_send_text(chat.id, FRIENDLY_ERROR)
            return
        await bridge.handle_voice(chat.id, audio)

    application.add_handler(MessageHandler(filters.TEXT, on_message))
    application.add_handler(MessageHandler(filters.VOICE, on_voice))

    # Reconexión con backoff: PTB ya reintenta dentro del polling; este loop cubre
    # además caídas del arranque (p. ej. sin internet al iniciar). /apagar sale limpio.
    backoff = _BACKOFF_INITIAL
    while not bridge.stopped:
        try:
            print("Puente de Telegram activo. Escríbele a tu bot; /apagar lo detiene.")
            application.run_polling(
                allowed_updates=[Update.MESSAGE],
                bootstrap_retries=-1,       # reintenta el arranque indefinidamente
                close_loop=False,
            )
            if not bridge.stopped:
                # run_polling terminó sin /apagar (p. ej. señal externa) → salir limpio.
                break
            backoff = _BACKOFF_INITIAL
        except Exception:  # noqa: BLE001 — red caída u otro fallo: esperar y reintentar
            logger.exception("El puente perdió la conexión; reintentando en %.0fs", backoff)
            print(f"Se perdió la conexión con Telegram. Reintento en {backoff:.0f} segundos...")
            import time

            time.sleep(backoff)
            backoff = min(backoff * 2, _BACKOFF_MAX)

    try:
        asyncio.run(client.aclose())
    except Exception:  # noqa: BLE001
        pass
    print("Puente de Telegram detenido.")
    return 0


def main() -> int:
    logging.basicConfig(
        level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s"
    )
    # CP-S2: el redactor envuelve el handler del basicConfig — aunque el token
    # del bot acabe en un traceback (httpx lo lleva EN LA URL), sale enmascarado.
    from ..security import install_redacting_logging
    install_redacting_logging()
    # httpx loguea a INFO la URL completa de cada request de polling, que incluye
    # el TOKEN del bot (…api.telegram.org/bot<TOKEN>/getUpdates) — silenciarlo
    # (hallazgo mayor de la revisión CP-B2; CP-S2 añade la redacción como segunda
    # capa, pero no loguear de más sigue siendo la primera).
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("httpcore").setLevel(logging.WARNING)
    # Carga .env del proyecto (mismo patrón que el resto del backend).
    try:
        from .. import config  # noqa: F401 — su import ejecuta load_dotenv(.env)
    except Exception:  # noqa: BLE001 — sin config igual se puede leer el entorno
        pass
    try:
        settings = load_settings()
    except BridgeConfigError as exc:
        print(str(exc))
        return 1
    return run_bot(settings)


if __name__ == "__main__":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:  # noqa: BLE001
        pass
    raise SystemExit(main())
