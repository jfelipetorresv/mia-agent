"""Mia · channels.relay — cliente RELAY reusable para cualquier canal (CP-E6, Ola 5).

El patrón "relay" mantiene las CREDENCIALES FUERA DEL NÚCLEO: un proceso de canal
(Telegram hoy; WhatsApp, correo, … mañana) corre aparte, guarda SUS credenciales en
SU propio entorno, y habla con Mia SOLO por el API HTTP con un JWT que obtiene con
usuario/clave (POST /api/auth/login). Así RLS y la política de modelo del despacho
aplican igual que en la web, y el motor nunca toca las llaves del canal.

`RelayClient` es la parte reusable: login con JWT, re-login automático ante 401 y los
tres verbos que cualquier canal necesita — chat (texto), transcribe (voz→texto) y
synthesize (texto→voz), todos 100% locales en el servidor de Mia. Un canal nuevo es un
ADAPTADOR delgado (recibir mensaje del transporte → RelayClient → devolver la respuesta);
el puente de Telegram (`telegram_bridge.py`) es el primer adaptador y el molde a copiar.
Ver `docs/canales-y-mcp.md` para el paso a paso de "añadir un canal".
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Awaitable, Callable, Optional

import httpx

logger = logging.getLogger("mia.channels.relay")

DEFAULT_API_URL = "http://127.0.0.1:8000"

# El motor por suscripción (CLI de Claude Code) puede tardar 1-3 min por respuesta.
HTTP_TIMEOUT_SECONDS = 300.0


class RelayApiError(Exception):
    """El API de Mia no pudo responder (status inesperado o red caída)."""


@dataclass
class RelayConfig:
    """Config mínima de un relay: a dónde hablar y con qué identidad de despacho.

    Las credenciales viven en el ENTORNO del proceso de canal (no en el núcleo). Cada
    canal añade encima lo suyo (p. ej. el token del bot de Telegram), pero esto es lo
    común a todos."""
    api_url: str
    email: str
    password: str


class RelayClient:
    """Cliente HTTP hacia el API de Mia: login JWT + los verbos de canal, con re-login
    ante 401. `http` es inyectable (objeto con `post(url, json=/files=/data=, headers=)`
    async) para probar sin red. El default es httpx.AsyncClient con timeout de 300s (el
    motor por suscripción tarda 1-3 min por turno)."""

    def __init__(self, api_url: str, email: str, password: str, http=None) -> None:
        self.api_url = api_url.rstrip("/")
        self._email = email
        self._password = password
        self._http = http or httpx.AsyncClient(
            timeout=httpx.Timeout(HTTP_TIMEOUT_SECONDS, connect=30.0)
        )
        self._token: str | None = None

    async def login(self) -> None:
        resp = await self._http.post(
            f"{self.api_url}/api/auth/login",
            json={"email": self._email, "password": self._password},
        )
        if resp.status_code != 200:
            raise RelayApiError(f"login → status {resp.status_code}")
        self._token = resp.json()["token"]
        logger.info("Sesión con el API de Mia iniciada.")

    def _auth_headers(self) -> dict:
        return {"Authorization": f"Bearer {self._token}"}

    async def _authed(self, do_request: Callable[[], Awaitable], label: str):
        """Ejecuta `do_request()` con el JWT actual; ante 401 renueva la sesión y
        reintenta UNA vez (el JWT expira). Centraliza el patrón que cada verbo repetía."""
        if not self._token:
            await self.login()
        resp = await do_request()
        if resp.status_code == 401:
            logger.info("Token vencido — renovando sesión y reintentando (%s).", label)
            self._token = None
            await self.login()
            resp = await do_request()
        if resp.status_code != 200:
            raise RelayApiError(f"{label} → status {resp.status_code}")
        return resp

    async def chat(self, message: str, conversation_id: str | None = None) -> tuple[str, str]:
        """Un turno contra /api/assistant/chat → (conversation_id, reply)."""
        def _req():
            payload: dict = {"message": message}
            if conversation_id:
                payload["conversation_id"] = conversation_id
            return self._http.post(f"{self.api_url}/api/assistant/chat",
                                   json=payload, headers=self._auth_headers())

        resp = await self._authed(_req, "chat")
        data = resp.json()
        return data["conversation_id"], data["reply"]

    async def transcribe(self, audio: bytes) -> str:
        """Nota de voz (OGG/Opus) → texto, vía POST /api/speech/transcribe. El STT corre
        100% local en el servidor de Mia; el audio nunca sale de ahí. Devuelve texto
        (posiblemente vacío si no se escuchó voz — el llamador lo maneja)."""
        def _req():
            return self._http.post(
                f"{self.api_url}/api/speech/transcribe",
                files={"audio": ("nota-de-voz.ogg", audio, "audio/ogg")},
                data={"pulir": "false"}, headers=self._auth_headers())

        resp = await self._authed(_req, "transcribe")
        return (resp.json().get("text") or "").strip()

    async def synthesize(self, text: str) -> bytes:
        """Texto → nota de voz OGG/Opus, vía POST /api/speech/synthesize. Síntesis 100%
        local. Devuelve los bytes del audio (OGG/Opus)."""
        def _req():
            return self._http.post(f"{self.api_url}/api/speech/synthesize",
                                   json={"text": text}, headers=self._auth_headers())

        resp = await self._authed(_req, "synthesize")
        return resp.content

    async def aclose(self) -> None:
        close = getattr(self._http, "aclose", None)
        if close:
            await close()


def load_relay_config(env: dict[str, str], *, email_key: str, password_key: str,
                      api_url_key: str = "MIA_API_URL") -> Optional[RelayConfig]:
    """Arma un RelayConfig desde el entorno del proceso de canal. Devuelve None si falta
    correo o clave (el canal decide qué mensaje mostrar). Cada canal pasa los nombres de
    SUS variables — el núcleo nunca las ve."""
    email = (env.get(email_key) or "").strip()
    password = (env.get(password_key) or "").strip()
    if not email or not password:
        return None
    return RelayConfig(
        api_url=(env.get(api_url_key) or DEFAULT_API_URL).strip().rstrip("/"),
        email=email, password=password)
