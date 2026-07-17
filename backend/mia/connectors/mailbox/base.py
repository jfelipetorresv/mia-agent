"""Mia · connectors.mailbox.base — tipos comunes y heurística de urgencia (CP-P3).

Estructuras neutrales al proveedor: Microsoft Graph y Google devuelven JSON con
formas distintas; cada conector las NORMALIZA a estos dataclasses, así las
vigilancias (watch_engine) no saben de qué proveedor vino cada evento/correo.
"""
from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Optional, Sequence

logger = logging.getLogger("mia.connectors.mailbox.base")

# Proveedores soportados. El orden no implica preferencia; cada tenant elige el suyo.
PROVIDERS = ("microsoft", "google")


def _norm_codes(jurisdictions: Optional[Sequence[str]]) -> Optional[tuple[str, ...]]:
    """Normaliza los códigos de jurisdicción a una tupla cacheable. `None`/vacío → `None`
    = todos los packs instalados."""
    if jurisdictions is None:
        return None
    codes = tuple(str(c).strip().lower() for c in jurisdictions if str(c or "").strip())
    return codes or None


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
# AGNÓSTICA DE JURISDICCIÓN: el léxico propio de un foro ("tutela", "desacato") y los
# dominios institucionales del país viven en `jurisdiction/packs/{code}/mail_signals.json`,
# no aquí. Este módulo solo trae la base PAN-HISPANA, que se aplica SIEMPRE: un pack puede
# AÑADIR señales, nunca quitarlas — sin pack el wake-gate nunca queda mudo.
#
# Deliberadamente amplia: un falso positivo solo agrega el correo al aviso; el abogado
# decide. NUNCA se lee el cuerpo para esto (regla de confidencialidad de CP-P3).
_URGENCY_TERMS_BASE = (
    "urgente", "inmediat[oa]", "hoy", "prioridad", "importante",
    "vence", "vencimiento", "plazo", "t[eé]rmino", "traslado", "requerimiento",
    "notificaci[oó]n", "audiencia", "juzgado", "tribunal",
    "demanda", "recurso", "apelaci[oó]n", "embargo",
    "medida\\s+cautelar", "sanci[oó]n", "multa",
)


def _pack_mail_signals(
        codes: Optional[tuple[str, ...]]) -> tuple[tuple[str, ...], tuple[str, ...], bool]:
    """(términos de urgencia, dominios institucionales, degradado) de los packs activos.

    A diferencia del ANONIMIZADOR —que enmascara con todos los packs siempre, porque su sesgo es
    la confidencialidad—, el wake-gate SÍ es por jurisdicción: 'tutela' o 'desacato' en el foro
    equivocado es solo ruido, y despertar de más tiene un coste real de atención. Aquí el error
    no filtra nada.

    `codes=None` = TODOS los packs instalados: ante la duda, MÁS señales. El sesgo correcto
    aquí es despertar de más (el abogado descarta un aviso) y nunca de menos (perder un
    término procesal). Fail-soft: si la capa de jurisdicción falla, se devuelve vacío +
    `degraded=True` y queda la base pan-hispana, sin que el bajón se cachee."""
    try:
        from ...jurisdiction.pack import list_packs, load_pack   # import diferido (evita ciclos)
    except Exception:  # noqa: BLE001
        return (), (), True
    if codes is None:
        try:
            codes = tuple(list_packs())
        except Exception:  # noqa: BLE001
            logger.exception("mailbox: no se pudieron listar los packs; solo el léxico base")
            return (), (), True
    degraded = False
    terms: list[str] = []
    domains: list[str] = []
    for code in codes:
        try:
            signals = load_pack(code).mail_signals or {}
        except Exception:  # noqa: BLE001 — un pack roto no puede callar la vigilancia
            logger.exception("mailbox: no se pudieron leer las señales del pack '%s'", code)
            degraded = True
            continue
        for t in signals.get("urgency_terms") or []:
            if isinstance(t, str) and t.strip():
                terms.append(t.strip())
        for d in signals.get("institutional_sender_domains") or []:
            if isinstance(d, str) and d.strip():
                domains.append(d.strip().lower())
    return tuple(terms), tuple(domains), degraded


# Caché de las tablas del wake-gate, POR jurisdicción. NO cachea una carga DEGRADADA: si un pack
# no se pudo leer por un hipo transitorio de I/O, un `lru_cache` normal habría congelado el léxico
# recortado para toda la vida del proceso y el despacho se habría perdido términos procesales de
# su propio foro durante la sesión entera. El caché es optimización, nunca fija una degradación.
_MAIL_TABLES_CACHE: dict = {}     # codes → (regex de urgencia, dominios institucionales)


def _mail_tables(codes: Optional[tuple[str, ...]]) -> tuple[re.Pattern, tuple[str, ...]]:
    """Tablas del wake-gate para `codes`. Base pan-hispana + señales de los packs. Un término mal
    escrito en el JSON de un pack se DESCARTA (fail-soft) sin tumbar el resto del léxico."""
    hit = _MAIL_TABLES_CACHE.get(codes)
    if hit is not None:
        return hit
    pack_terms, domains, degraded = _pack_mail_signals(codes)
    terms: list[str] = []
    for t in [*_URGENCY_TERMS_BASE, *pack_terms]:
        if t in terms:
            continue
        try:
            re.compile(t)
        except re.error:
            logger.warning("mailbox: término de urgencia inválido en un pack (%r); se descarta", t)
            continue
        terms.append(t)
    value = (re.compile(r"\b(" + "|".join(terms) + r")\b", re.IGNORECASE),
             tuple(dict.fromkeys(domains)))
    if not degraded:
        _MAIL_TABLES_CACHE[codes] = value
    return value


def _urgency_re(codes: Optional[tuple[str, ...]] = None) -> re.Pattern:
    """Regex de urgencia = base pan-hispana + términos del/los pack(s)."""
    return _mail_tables(codes)[0]


def _institutional_senders(codes: Optional[tuple[str, ...]] = None) -> tuple[str, ...]:
    """Dominios institucionales del/los pack(s). Sin pack → vacío: los dominios oficiales son
    propios de cada país y no hay base pan-hispana posible (el léxico sigue cubriendo)."""
    return _mail_tables(codes)[1]


# Contrato de `lru_cache` conservado para los tests, que reubican `PACKS_DIR` en caliente.
_urgency_re.cache_clear = _MAIL_TABLES_CACHE.clear          # type: ignore[attr-defined]
_institutional_senders.cache_clear = _MAIL_TABLES_CACHE.clear   # type: ignore[attr-defined]


def mail_looks_urgent(header: MailHeader,
                      jurisdictions: Optional[Sequence[str]] = None) -> bool:
    """True si el correo PARECE urgente por su metadata (bandera, asunto o remitente).

    Solo mira metadata — jamás el cuerpo. Es el wake-gate de la vigilancia de correo:
    barato y sin LLM. Un correo institucional (juzgado, procuraduría) o con importancia
    alta cuenta como urgente aunque el asunto no dispare palabra.

    `jurisdictions`: pack(s) del despacho; omitirlo = todos los instalados (más señales)."""
    codes = _norm_codes(jurisdictions)
    if (header.importance or "").lower() == "high":
        return True
    sender = (header.sender or "").lower()
    if any(sender.endswith(dom) or ("@" + dom) in sender
           for dom in _institutional_senders(codes)):
        return True
    hay = f"{header.subject or ''} {header.sender_name or ''}"
    return bool(_urgency_re(codes).search(hay))


def event_is_procedural(event: CalendarEvent) -> bool:
    """True si el TÍTULO del evento sugiere una actuación procesal (audiencia, plazo…).

    Reutiliza el detector de reminders (regla dura): si aplica, el aviso del evento
    viaja con [VERIFICAR]. Nunca calcula nada — solo etiqueta la advertencia."""
    from ...assistant.reminders import is_procedural_text
    return is_procedural_text(event.title or "")
