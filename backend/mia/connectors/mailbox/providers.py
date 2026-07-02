"""Mia · connectors.mailbox.providers — lectura de calendario y correo (CP-P3).

Un conector por proveedor. Ambos exponen la MISMA interfaz (metadata-only):
  · ``upcoming_events(within_hours)`` -> list[CalendarEvent]
  · ``recent_mail(max_results, unread_only)`` -> list[MailHeader]  (SIN cuerpo)

Solo lectura. `http` (get async estilo httpx) se inyecta para probar sin red. Ante
cualquier error de API se lanza `MailboxAPIError`; la vigilancia de arriba degrada."""
from __future__ import annotations

import base64
import html as _html
import logging
import re
from datetime import datetime, timedelta, timezone
from typing import Optional
from urllib.parse import quote

from .base import CalendarEvent, MailHeader, OAuthCreds, parse_dt

logger = logging.getLogger("mia.connectors.mailbox")

GRAPH_BASE = "https://graph.microsoft.com/v1.0"
GOOGLE_CAL_BASE = "https://www.googleapis.com/calendar/v3"
GOOGLE_GMAIL_BASE = "https://gmail.googleapis.com/gmail/v1"


class MailboxAPIError(RuntimeError):
    """Fallo al leer calendario/correo de la API (se degrada con gracia arriba)."""


async def _get(http, url: str, *, token: str, params: Optional[dict] = None,
               headers: Optional[dict] = None) -> dict:
    h = {"Authorization": f"Bearer {token}", "Accept": "application/json"}
    if headers:
        h.update(headers)
    resp = await http.get(url, params=params or {}, headers=h)
    status = getattr(resp, "status_code", 0)
    if status != 200:
        raise MailboxAPIError(f"GET {url.split('?')[0]} devolvió status {status}")
    return resp.json()


class MicrosoftMailbox:
    """Calendario y correo vía Microsoft Graph (Outlook / Microsoft 365)."""

    provider = "microsoft"

    def __init__(self, creds: OAuthCreds, *, http, base: str = GRAPH_BASE) -> None:
        self._creds = creds
        self._http = http
        self._base = base

    async def upcoming_events(self, within_hours: int,
                              now: Optional[datetime] = None) -> list[CalendarEvent]:
        now = now or datetime.now(timezone.utc)
        end = now + timedelta(hours=within_hours)
        # calendarView expande recurrencias; pedimos tiempos en UTC con el header Prefer.
        params = {
            "startDateTime": now.strftime("%Y-%m-%dT%H:%M:%SZ"),
            "endDateTime": end.strftime("%Y-%m-%dT%H:%M:%SZ"),
            "$select": "id,subject,start,end,location,isAllDay",
            "$orderby": "start/dateTime",
            "$top": "50",
        }
        data = await _get(self._http, f"{self._base}/me/calendarView", token=self._creds.access_token,
                          params=params, headers={"Prefer": 'outlook.timezone="UTC"'})
        out: list[CalendarEvent] = []
        for ev in data.get("value", []) or []:
            loc = ((ev.get("location") or {}).get("displayName")) or ""
            out.append(CalendarEvent(
                provider=self.provider,
                external_id=str(ev.get("id") or ""),
                title=str(ev.get("subject") or "(sin título)"),
                start=parse_dt((ev.get("start") or {}).get("dateTime")),
                end=parse_dt((ev.get("end") or {}).get("dateTime")),
                location=str(loc),
                is_all_day=bool(ev.get("isAllDay")),
            ))
        return out

    async def fetch_body(self, external_id: str) -> str:
        """Cuerpo de UN correo en texto plano (CP-P4, solo si el despacho lo autorizó).

        Graph devuelve body.content en HTML o text según contentType; si es HTML se
        despoja a texto. Es contenido NO confiable: quien lo consuma (analyze.py) lo
        SELLA antes de dárselo a un LLM."""
        data = await _get(self._http, f"{self._base}/me/messages/{quote(external_id)}",
                          token=self._creds.access_token, params={"$select": "body"})
        body = data.get("body") or {}
        content = str(body.get("content") or "")
        if str(body.get("contentType") or "").lower() == "html":
            content = strip_html(content)
        return content.strip()

    async def recent_mail(self, max_results: int = 25,
                          unread_only: bool = True) -> list[MailHeader]:
        # CP-P3 metadata-only: NO se pide bodyPreview (es una porción del cuerpo). La
        # vigilancia decide urgencia por remitente/asunto/bandera; el cuerpo solo se
        # trae con fetch_body cuando el despacho autorizó el análisis con IA (CP-P4).
        params = {
            "$select": "id,subject,from,receivedDateTime,isRead,importance,hasAttachments",
            "$orderby": "receivedDateTime desc",
            "$top": str(max_results),
        }
        if unread_only:
            params["$filter"] = "isRead eq false"
        data = await _get(self._http, f"{self._base}/me/messages", token=self._creds.access_token,
                          params=params)
        out: list[MailHeader] = []
        for m in data.get("value", []) or []:
            frm = ((m.get("from") or {}).get("emailAddress")) or {}
            out.append(MailHeader(
                provider=self.provider,
                external_id=str(m.get("id") or ""),
                subject=str(m.get("subject") or "(sin asunto)"),
                sender=str(frm.get("address") or ""),
                sender_name=str(frm.get("name") or ""),
                received_at=parse_dt(m.get("receivedDateTime")),
                is_unread=not bool(m.get("isRead")),
                importance=str(m.get("importance") or "normal").lower(),
                has_attachments=bool(m.get("hasAttachments")),
                snippet="",   # metadata-only: no se trae vista previa del cuerpo
            ))
        return out


class GoogleMailbox:
    """Calendario y correo vía Google Calendar / Gmail (Google Workspace)."""

    provider = "google"

    def __init__(self, creds: OAuthCreds, *, http,
                 cal_base: str = GOOGLE_CAL_BASE, gmail_base: str = GOOGLE_GMAIL_BASE) -> None:
        self._creds = creds
        self._http = http
        self._cal_base = cal_base
        self._gmail_base = gmail_base

    async def upcoming_events(self, within_hours: int,
                              now: Optional[datetime] = None) -> list[CalendarEvent]:
        now = now or datetime.now(timezone.utc)
        end = now + timedelta(hours=within_hours)
        params = {
            "timeMin": now.strftime("%Y-%m-%dT%H:%M:%SZ"),
            "timeMax": end.strftime("%Y-%m-%dT%H:%M:%SZ"),
            "singleEvents": "true",       # expande recurrencias
            "orderBy": "startTime",
            "maxResults": "50",
        }
        data = await _get(self._http, f"{self._cal_base}/calendars/primary/events",
                          token=self._creds.access_token, params=params)
        out: list[CalendarEvent] = []
        for ev in data.get("items", []) or []:
            start = ev.get("start") or {}
            endd = ev.get("end") or {}
            is_all_day = "date" in start and "dateTime" not in start
            out.append(CalendarEvent(
                provider=self.provider,
                external_id=str(ev.get("id") or ""),
                title=str(ev.get("summary") or "(sin título)"),
                start=parse_dt(start.get("dateTime") or start.get("date")),
                end=parse_dt(endd.get("dateTime") or endd.get("date")),
                location=str(ev.get("location") or ""),
                is_all_day=is_all_day,
            ))
        return out

    async def fetch_body(self, external_id: str) -> str:
        """Cuerpo de UN correo en texto plano (CP-P4). Gmail `format=full` trae el árbol
        MIME; se prefiere text/plain, con fallback a text/html despojado. Contenido NO
        confiable — analyze.py lo SELLA antes del LLM."""
        data = await _get(self._http, f"{self._gmail_base}/users/me/messages/{quote(external_id)}",
                          token=self._creds.access_token, params={"format": "full"})
        return _extract_gmail_body(data.get("payload") or {})

    async def recent_mail(self, max_results: int = 25,
                          unread_only: bool = True) -> list[MailHeader]:
        # Gmail API en dos pasos: listar ids (con query) → traer metadata de cada uno.
        q = "is:unread" if unread_only else ""
        listing = await _get(self._http, f"{self._gmail_base}/users/me/messages",
                             token=self._creds.access_token,
                             params={"q": q, "maxResults": str(max_results)})
        out: list[MailHeader] = []
        for ref in listing.get("messages", []) or []:
            mid = str(ref.get("id") or "")
            if not mid:
                continue
            try:
                msg = await _get(
                    self._http, f"{self._gmail_base}/users/me/messages/{quote(mid)}",
                    token=self._creds.access_token,
                    params={"format": "metadata",
                            "metadataHeaders": ["From", "Subject", "Date"]},
                )
            except MailboxAPIError:
                logger.warning("gmail: no se pudo leer metadata de un mensaje; se omite")
                continue
            out.append(_gmail_header(mid, msg))
        return out


def _gmail_header(mid: str, msg: dict) -> MailHeader:
    """Normaliza un mensaje de Gmail (format=metadata) a MailHeader."""
    headers = {h.get("name", "").lower(): h.get("value", "")
               for h in ((msg.get("payload") or {}).get("headers") or [])}
    label_ids = set(msg.get("labelIds") or [])
    sender_name, sender = _split_from(headers.get("from", ""))
    return MailHeader(
        provider="google",
        external_id=mid,
        subject=headers.get("subject", "(sin asunto)"),
        sender=sender,
        sender_name=sender_name,
        received_at=parse_dt(_epoch_ms_to_iso(msg.get("internalDate"))),
        is_unread="UNREAD" in label_ids,
        importance="high" if "IMPORTANT" in label_ids else "normal",
        has_attachments=False,   # metadata no lo trae de forma barata; se omite en v1
        snippet=str(msg.get("snippet") or "")[:200],
    )


def _split_from(raw: str) -> tuple[str, str]:
    """'Juan Pérez <juan@x.co>' -> ('Juan Pérez', 'juan@x.co'). Sin '<>' → todo es email."""
    raw = (raw or "").strip()
    if "<" in raw and ">" in raw:
        name = raw.split("<", 1)[0].strip().strip('"')
        email = raw.split("<", 1)[1].split(">", 1)[0].strip()
        return name, email
    return "", raw


def _epoch_ms_to_iso(ms: Optional[str]) -> Optional[str]:
    if not ms:
        return None
    try:
        return datetime.fromtimestamp(int(ms) / 1000, tz=timezone.utc).isoformat()
    except (TypeError, ValueError):
        return None


_TAG_RE = re.compile(r"(?s)<[^>]+>")
_SCRIPT_STYLE_RE = re.compile(r"(?is)<(script|style)\b.*?</\1>")
_WS_RE = re.compile(r"\s+")


def strip_html(s: str) -> str:
    """HTML → texto plano legible: quita script/style, etiquetas, desescapa entidades."""
    s = _SCRIPT_STYLE_RE.sub(" ", s or "")
    s = _TAG_RE.sub(" ", s)
    s = _html.unescape(s)
    return _WS_RE.sub(" ", s).strip()


def _b64url_decode(data: str) -> str:
    try:
        pad = "=" * (-len(data) % 4)
        return base64.urlsafe_b64decode(data + pad).decode("utf-8", "replace")
    except Exception:  # noqa: BLE001 — cuerpo ilegible: mejor vacío que reventar
        return ""


def _find_part(payload: dict, mime: str) -> Optional[str]:
    """Busca (recursivo) el `body.data` del primer part con este mimeType."""
    if payload.get("mimeType") == mime:
        data = (payload.get("body") or {}).get("data")
        if data:
            return data
    for part in payload.get("parts") or []:
        found = _find_part(part, mime)
        if found:
            return found
    return None


def _extract_gmail_body(payload: dict) -> str:
    """Texto del cuerpo desde el árbol MIME de Gmail: prefiere text/plain; si no, HTML."""
    plain = _find_part(payload, "text/plain")
    if plain:
        return _b64url_decode(plain).strip()
    html_data = _find_part(payload, "text/html")
    if html_data:
        return strip_html(_b64url_decode(html_data)).strip()
    # cuerpo simple (sin parts): el data está en el propio payload
    data = (payload.get("body") or {}).get("data")
    if data:
        text = _b64url_decode(data)
        if payload.get("mimeType") == "text/html":
            text = strip_html(text)
        return text.strip()
    return ""


def build_connector(creds: OAuthCreds, *, http):
    """Fabrica el conector del proveedor de las credenciales. None si no se reconoce."""
    if creds.provider == "microsoft":
        return MicrosoftMailbox(creds, http=http)
    if creds.provider == "google":
        return GoogleMailbox(creds, http=http)
    logger.warning("proveedor de mailbox desconocido: %s", creds.provider)
    return None
