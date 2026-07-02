"""Mia · connectors.mailbox.base — tipos comunes y heurística de urgencia (CP-P3).

Estructuras neutrales al proveedor: Microsoft Graph y Google devuelven JSON con
formas distintas; cada conector las NORMALIZA a estos dataclasses, así las
vigilancias (watch_engine) no saben de qué proveedor vino cada evento/correo.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Optional

# Proveedores soportados. El orden no implica preferencia; cada tenant elige el suyo.
PROVIDERS = ("microsoft", "google")


def parse_dt(raw: Optional[str]) -> Optional[datetime]:
    """Parsea un ISO-8601 de la API a datetime con tz. Naive → se asume UTC.

    Graph devuelve tiempos sin offset cuando se pide `Prefer: outlook.timezone="UTC"`;
    Google devuelve con offset ('Z' o ±hh:mm). Sin fecha reconocible → None (el
    llamador decide; una vigilancia jamás revienta por una fecha rara)."""
    if not raw:
        return None
    s = str(raw).strip()
    if s.endswith("Z"):
        s = s[:-1] + "+00:00"
    try:
        dt = datetime.fromisoformat(s)
    except ValueError:
        # Google 'date' de eventos de todo el día viene como 'YYYY-MM-DD'.
        try:
            dt = datetime.strptime(s[:10], "%Y-%m-%d")
        except ValueError:
            return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt


@dataclass(frozen=True)
class OAuthCreds:
    """Credenciales OAuth de UN tenant para UN proveedor. `access_token` es de vida
    corta; `refresh_token` se canjea por uno nuevo cuando expira (oauth.refresh)."""
    provider: str
    access_token: str
    refresh_token: str = ""
    expires_at: Optional[datetime] = None     # UTC; None = desconocido → refrescar
    scopes: tuple[str, ...] = ()


@dataclass(frozen=True)
class CalendarEvent:
    """Un evento del calendario, normalizado. `external_id` es estable por proveedor
    (para el debounce de avisos)."""
    provider: str
    external_id: str
    title: str
    start: Optional[datetime]
    end: Optional[datetime] = None
    location: str = ""
    is_all_day: bool = False


@dataclass(frozen=True)
class MailHeader:
    """CABECERA de un correo (metadata) — NUNCA el cuerpo. Es lo único que la
    vigilancia metadata-only de CP-P3 lee: remitente, asunto, fecha, banderas."""
    provider: str
    external_id: str
    subject: str
    sender: str = ""
    sender_name: str = ""
    received_at: Optional[datetime] = None
    is_unread: bool = True
    importance: str = "normal"        # "high" | "normal" | "low"
    has_attachments: bool = False
    snippet: str = ""                 # vista previa corta que da la API (metadata)


# ── heurística de urgencia (metadata-only, SIN LLM) ──────────────────────────────
# Palabras que, en el ASUNTO o remitente, sugieren que un correo merece atención hoy.
# Deliberadamente amplia: un falso positivo solo agrega el correo al aviso; el abogado
# decide. NUNCA se lee el cuerpo para esto (regla de confidencialidad de CP-P3).
_URGENCY_RE = re.compile(
    r"\b(urgente|inmediat[oa]|hoy|prioridad|importante|"
    r"vence|vencimiento|plazo|t[eé]rmino|traslado|requerimiento|"
    r"notificaci[oó]n|audiencia|juzgado|tribunal|despacho\s+judicial|"
    r"demanda|tutela|recurso|apelaci[oó]n|desacato|embargo|"
    r"acci[oó]n\s+de\s+tutela|medida\s+cautelar|sanci[oó]n|multa)\b",
    re.IGNORECASE,
)

# Dominios típicos de la rama judicial colombiana (remitente institucional = señal
# fuerte). Se compara por sufijo, case-insensitive.
_INSTITUTIONAL_SENDERS = (
    "ramajudicial.gov.co",
    "cendoj.ramajudicial.gov.co",
    "procuraduria.gov.co",
    "fiscalia.gov.co",
    "supersociedades.gov.co",
    "superfinanciera.gov.co",
)


def mail_looks_urgent(header: MailHeader) -> bool:
    """True si el correo PARECE urgente por su metadata (bandera, asunto o remitente).

    Solo mira metadata — jamás el cuerpo. Es el wake-gate de la vigilancia de correo:
    barato y sin LLM. Un correo institucional (juzgado, procuraduría) o con importancia
    alta cuenta como urgente aunque el asunto no dispare palabra."""
    if (header.importance or "").lower() == "high":
        return True
    sender = (header.sender or "").lower()
    if any(sender.endswith(dom) or ("@" + dom) in sender for dom in _INSTITUTIONAL_SENDERS):
        return True
    hay = f"{header.subject or ''} {header.sender_name or ''}"
    return bool(_URGENCY_RE.search(hay))


def event_is_procedural(event: CalendarEvent) -> bool:
    """True si el TÍTULO del evento sugiere una actuación procesal (audiencia, plazo…).

    Reutiliza el detector de reminders (regla dura): si aplica, el aviso del evento
    viaja con [VERIFICAR]. Nunca calcula nada — solo etiqueta la advertencia."""
    from ...assistant.reminders import is_procedural_text
    return is_procedural_text(event.title or "")
