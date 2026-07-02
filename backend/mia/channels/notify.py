"""Mia · channels.notify — notificaciones SALIENTES proactivas (CP-B3, Pilar B).

Módulo común y minimalista para que los jobs del scheduler (recordatorios vencidos,
borradores esperando revisión, reporte semanal de Dreams) le avisen al abogado sin
que él pregunte. Canal v1: el MISMO bot privado de Telegram del puente CP-B2
(TELEGRAM_BOT_TOKEN + TELEGRAM_ALLOWED_CHAT_ID en .env) — extensible a otros
canales cuando existan (correo, WhatsApp).

Diseño:
  · OPT-IN y fail-soft: sin token o chat configurado → no-op silencioso (False).
    Un despacho sin Telegram funciona exactamente igual que antes de CP-B3.
  · Llama la Bot API de Telegram por HTTPS directo (sendMessage) — NO usa
    python-telegram-bot: no hay polling ni estado, es un POST puntual.
  · NUNCA lanza: cualquier fallo de red/API se loguea y devuelve False; el que
    llama decide si reintenta (los jobs dejan el recordatorio 'pending' y el
    siguiente ciclo lo reintenta solo).
  · §G y hallazgo de CP-B2: JAMÁS se loguea el token (va en la URL) ni el
    contenido del mensaje — solo longitudes y status.
  · UN solo chat de salida (el del puente CP-B2): los jobs deben notificar SOLO
    al tenant dueño de ese chat (scheduler._resolve_notify_tenant) — nunca
    contenido de otros despachos por este canal.

``http`` es inyectable (objeto con ``post(url, json=...)`` async) para que el gate
pruebe todo sin red — mismo patrón que MiaClient (telegram_bridge.py).
"""
from __future__ import annotations

import logging
import os

logger = logging.getLogger("mia.channels.notify")

TELEGRAM_API_BASE = "https://api.telegram.org"

# Límite práctico de un mensaje de texto de Telegram (~4096); margen para no partir.
_TEXT_LIMIT = 3900

_TRUNCATION_SUFFIX = "\n\n(… mensaje recortado; el detalle completo está en Mia.)"


def telegram_configured(env: dict[str, str] | None = None) -> bool:
    """True si el canal de Telegram tiene token y chat autorizado en el entorno."""
    env = env if env is not None else dict(os.environ)
    return bool((env.get("TELEGRAM_BOT_TOKEN") or "").strip()) and bool(
        (env.get("TELEGRAM_ALLOWED_CHAT_ID") or "").strip()
    )


async def send_telegram(
    text: str,
    env: dict[str, str] | None = None,
    http=None,
) -> bool:
    """Envía un mensaje proactivo al chat autorizado. True si Telegram lo aceptó.

    Sin configuración (opt-in pendiente de crear el bot) o ante cualquier error →
    False, sin lanzar. El contenido y el token NUNCA se loguean.
    """
    env = env if env is not None else dict(os.environ)
    token = (env.get("TELEGRAM_BOT_TOKEN") or "").strip()
    raw_chat = (env.get("TELEGRAM_ALLOWED_CHAT_ID") or "").strip()
    if not token or not raw_chat:
        logger.debug("Telegram sin configurar — notificación omitida (opt-in pendiente).")
        return False
    try:
        chat_id = int(raw_chat)
    except ValueError:
        logger.warning("TELEGRAM_ALLOWED_CHAT_ID no es numérico — notificación omitida.")
        return False

    text = (text or "").strip()
    if not text:
        return False
    if len(text) > _TEXT_LIMIT:
        text = text[: _TEXT_LIMIT - len(_TRUNCATION_SUFFIX)].rstrip() + _TRUNCATION_SUFFIX

    close_after = False
    if http is None:
        import httpx

        http = httpx.AsyncClient(timeout=httpx.Timeout(30.0, connect=10.0))
        close_after = True
    try:
        resp = await http.post(
            f"{TELEGRAM_API_BASE}/bot{token}/sendMessage",
            json={"chat_id": chat_id, "text": text},
        )
        if resp.status_code != 200:
            # Solo status y longitud — nunca la URL (lleva el token) ni el contenido.
            logger.warning(
                "Telegram no aceptó la notificación (status=%s, %d chars).",
                resp.status_code, len(text),
            )
            return False
        logger.info("Notificación enviada por Telegram (%d chars).", len(text))
        return True
    except Exception as exc:  # noqa: BLE001 — una notificación caída nunca tumba un job
        # Sin exc_info: algunas excepciones de httpx incluyen la URL del request,
        # que lleva el TOKEN del bot (mismo hallazgo que en CP-B2). Solo el tipo.
        logger.warning("No se pudo enviar la notificación por Telegram (%s).",
                       type(exc).__name__)
        return False
    finally:
        if close_after:
            try:
                await http.aclose()
            except Exception:  # noqa: BLE001
                pass
