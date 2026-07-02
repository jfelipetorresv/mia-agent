"""Mia · assistant.reminders — recordatorios en lenguaje natural (CP-B3, Pilar B).

El abogado le pide a Mia un recordatorio desde el chat del asistente ("recuérdame
radicar la tutela mañana a las 9") y Mia lo agenda; el scheduler lo despacha por
Telegram cuando vence (cron/scheduler.py + channels/notify.py).

Dos piezas:

  · ``parse_reminder(text, now)`` — parser DETERMINISTA (sin LLM) de la intención
    y la fecha en español: "mañana", "el viernes", "en 2 horas", "el 15 de agosto",
    "a las 3 pm", combinaciones. Determinista a propósito: crear un recordatorio
    cambia estado y no puede depender de que un modelo "entienda" — si la fecha no
    se reconoce, el asistente PREGUNTA en vez de adivinar. ``parse_when`` expone la
    fecha sola (para el turno de seguimiento: "¿cuándo?" → "mañana a las 9").

  · ``ReminderService`` — CRUD y despacho bajo ``pool.tenant_connection`` (RLS
    fail-closed, como todo lo por-tenant).

REGLA DURA del plan (regla 5 del propietario): los recordatorios que mencionan
plazos o actuaciones PROCESALES (``is_procedural``) se confirman siempre con el
abogado — Mia NUNCA calcula un término legal por su cuenta: la fecha la puso el
abogado y tanto la confirmación como el aviso llevan [VERIFICAR]. En la misma
línea, "N días HÁBILES" no se calcula jamás (depende de festivos y del calendario
judicial): se pide la fecha exacta (``business_days``).
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime, timedelta

from ..db import pool

# Hora por defecto cuando el abogado da un día sin hora ("mañana", "el viernes").
_DEFAULT_HOUR = 8

# ── detección de intención ────────────────────────────────────────────────────
# Disparadores FUERTES: pedir un recordatorio de forma inequívoca — siempre se
# atienden. NO se incluye "recuerda(s)" a secas: "¿recuerdas el caso HDI?" es una
# pregunta de memoria, no un recordatorio.
_STRONG_TRIGGER_RE = re.compile(
    r"\b(recu[eé]rdame|recordarme|recuerdame|"
    r"ponme\s+un\s+recordatorio|crea(?:me)?\s+un\s+recordatorio|"
    r"agenda(?:me)?\s+un\s+recordatorio)\b",
    re.IGNORECASE,
)

# Disparadores DÉBILES: lenguaje cotidiano que solo es un recordatorio si trae
# fecha/hora. "Revisa el contrato y avísame qué opinas" NO debe interceptarse
# (hallazgo M5 del revisor): sin fecha, el turno sigue su camino normal al modelo.
_WEAK_TRIGGER_RE = re.compile(r"\bav[ií]same\b", re.IGNORECASE)

# Plazos / actuaciones procesales → el recordatorio SIEMPRE va con [VERIFICAR].
# Lista AMPLIA a propósito (hallazgo B1 del revisor): un falso positivo solo añade
# la advertencia; un falso negativo dejaría un término legal sin verificar.
_PROCEDURAL_RE = re.compile(
    r"\b(plazos?|t[eé]rminos?|audiencias?|radicar|radicaci[oó]n|"
    r"contestar|contestaci[oó]n|demandas?|tutelas?|recursos?|apelar|"
    r"apelaci[oó]n|impugnar|impugnaci[oó]n|traslados?|vencimientos?|vence|"
    r"alegatos?|subsanar|desacatos?|notificaci[oó]n(?:es)?|juzgados?|"
    r"despacho\s+judicial|procesos?|sentencias?|fallos?|emplazamientos?|"
    r"requerimientos?|diligencias?|fiscal[ií]as?|casaci[oó]n|querellas?|"
    r"expedientes?|jueces|juez|magistrad[oa]s?|tribunal(?:es)?|corte|"
    r"oficios?|memoriales?|incidentes?|embargos?|remates?|"
    r"liquidaci[oó]n|conciliaci[oó]n|interponer|sustentaci[oó]n|"
    r"actuaci[oó]n(?:es)?|medidas?\s+cautelar(?:es)?|h[aá]bil(?:es)?)\b",
    re.IGNORECASE,
)

_WEEKDAYS = {
    "lunes": 0, "martes": 1, "miercoles": 2, "miércoles": 2,
    "jueves": 3, "viernes": 4, "sabado": 5, "sábado": 5, "domingo": 6,
}

_MONTHS = {
    "enero": 1, "febrero": 2, "marzo": 3, "abril": 4, "mayo": 5, "junio": 6,
    "julio": 7, "agosto": 8, "septiembre": 9, "octubre": 10,
    "noviembre": 11, "diciembre": 12,
}

_MONTH_NAMES = {v: k for k, v in _MONTHS.items()}

_NUMBER_WORDS = {
    "un": 1, "una": 1, "uno": 1, "dos": 2, "tres": 3, "cuatro": 4, "cinco": 5,
    "seis": 6, "siete": 7, "ocho": 8, "nueve": 9, "diez": 10,
}

# "en 2 horas", "en media hora", "en tres días", "en 45 minutos", "en una semana"
_IN_RE = re.compile(
    r"\ben\s+(\d+|una?|uno|dos|tres|cuatro|cinco|seis|siete|ocho|nueve|diez|media)\s+"
    r"(minutos?|horas?|d[ií]as?|semanas?|hora|min)\b",
    re.IGNORECASE,
)

# "N días hábiles": Mia NO los calcula (festivos + calendario judicial) — pide la
# fecha exacta. Se detecta cerca de la expresión "en N días" (hallazgo M1).
_BUSINESS_DAYS_RE = re.compile(r"\bh[aá]bil(?:es)?\b", re.IGNORECASE)

# "el viernes", "este viernes", "el próximo viernes"
_WEEKDAY_RE = re.compile(
    r"\b(?:el|este|pr[oó]ximo|el\s+pr[oó]ximo)\s+"
    r"(lunes|martes|mi[eé]rcoles|jueves|viernes|s[aá]bado|domingo)\b",
    re.IGNORECASE,
)

# "el 15 de agosto", "el 3 de enero de 2027" (año opcional — hallazgo M2)
_DATE_RE = re.compile(
    r"\bel\s+(\d{1,2})\s+de\s+"
    r"(enero|febrero|marzo|abril|mayo|junio|julio|agosto|septiembre|octubre|noviembre|diciembre)"
    r"(?:\s+(?:de|del)\s+(\d{4}))?\b",
    re.IGNORECASE,
)

# "a las 3", "a las 3:30", "a la 1 pm", "a las 9 de la mañana", "a las 8 de la noche"
_TIME_RE = re.compile(
    r"\ba\s+las?\s+(\d{1,2})(?::(\d{2}))?\s*"
    r"(am|pm|a\.m\.|p\.m\.|de\s+la\s+ma[ñn]ana|de\s+la\s+tarde|de\s+la\s+noche)?\b",
    re.IGNORECASE,
)

_TODAY_RE = re.compile(r"\bhoy\b", re.IGNORECASE)
# Lookbehind "de la ": que "a las 9 de la mañana" (hora) no se lea como el día "mañana".
_TOMORROW_RE = re.compile(r"(?<!de\sla\s)\bma[ñn]ana\b", re.IGNORECASE)
_AFTER_TOMORROW_RE = re.compile(r"\bpasado\s+ma[ñn]ana\b", re.IGNORECASE)


@dataclass
class ParsedReminder:
    """Resultado del parser: qué recordar, cuándo (None = falta la fecha), si es
    procesal y si pidió "días hábiles" (que Mia no calcula — pide fecha exacta)."""

    subject: str
    due_at: datetime | None
    is_procedural: bool
    business_days: bool = False


def is_procedural_text(text: str) -> bool:
    """True si el texto menciona un plazo o actuación procesal (regla dura)."""
    return bool(_PROCEDURAL_RE.search(text or ""))


def _apply_time(base: datetime, match: re.Match | None) -> datetime:
    """Fija la hora sobre una fecha base; sin hora explícita → _DEFAULT_HOUR."""
    if match is None:
        return base.replace(hour=_DEFAULT_HOUR, minute=0, second=0, microsecond=0)
    hour = int(match.group(1))
    minute = int(match.group(2) or 0)
    suffix = (match.group(3) or "").lower().replace(".", "").replace(" ", "")
    if suffix in {"pm", "delatarde", "delanoche"} and hour < 12:
        hour += 12
    if suffix in {"am", "delamañana", "delamanana"} and hour == 12:
        hour = 0
    if hour > 23 or minute > 59:
        return base.replace(hour=_DEFAULT_HOUR, minute=0, second=0, microsecond=0)
    return base.replace(hour=hour, minute=minute, second=0, microsecond=0)


def _when(text: str, now: datetime) -> tuple[datetime | None, list[re.Match], bool]:
    """Extrae el CUÁNDO del texto → (due, expresiones consumidas, pidió_hábiles).

    due None + pidió_hábiles=False = no hay fecha reconocible (se pregunta).
    due None + pidió_hábiles=True  = "N días hábiles": Mia no los calcula (festivos
    y calendario judicial) — se pide la fecha exacta."""
    time_m = _TIME_RE.search(text)

    # 1 · relativo: "en N minutos/horas/días/semanas" (la hora explícita no aplica).
    in_m = _IN_RE.search(text)
    if in_m:
        consumed = [in_m]
        raw_n, unit = in_m.group(1).lower(), in_m.group(2).lower()
        if _BUSINESS_DAYS_RE.search(text):
            return None, consumed, True  # días hábiles: pedir fecha exacta (M1)
        if raw_n == "media":
            if unit.startswith("hora"):
                return now + timedelta(minutes=30), consumed, False
            return None, consumed, False  # "media semana" y similares: preguntar
        n = int(raw_n) if raw_n.isdigit() else _NUMBER_WORDS.get(raw_n, 1)
        if unit.startswith("min"):
            return now + timedelta(minutes=n), consumed, False
        if unit.startswith("hora"):
            return now + timedelta(hours=n), consumed, False
        if unit.startswith("semana"):
            return now + timedelta(weeks=n), consumed, False
        return now + timedelta(days=n), consumed, False

    # 2 · fecha absoluta: "el 15 de agosto (de 2027)" — año explícito se respeta (M2).
    date_m = _DATE_RE.search(text)
    if date_m:
        consumed = [date_m] + ([time_m] if time_m else [])
        day, month = int(date_m.group(1)), _MONTHS[date_m.group(2).lower()]
        year = int(date_m.group(3)) if date_m.group(3) else None
        try:
            due = _apply_time(now.replace(year=year or now.year, month=month, day=day),
                              time_m)
        except ValueError:  # 31 de febrero y similares → que el abogado la corrija
            return None, consumed, False
        if year is not None:
            if due <= now:  # fecha explícita ya pasada → preguntar, nunca adivinar
                return None, consumed, False
            return due, consumed, False
        if due <= now:  # sin año → próxima ocurrencia
            try:
                due = due.replace(year=due.year + 1)
            except ValueError:  # 29 de febrero → el año siguiente no existe
                return None, consumed, False
        return due, consumed, False

    # 3 · día de la semana: "el viernes" (próxima ocurrencia; hoy mismo → +7).
    week_m = _WEEKDAY_RE.search(text)
    if week_m:
        consumed = [week_m] + ([time_m] if time_m else [])
        target = _WEEKDAYS[week_m.group(1).lower()]
        ahead = (target - now.weekday()) % 7
        due = _apply_time(now + timedelta(days=ahead), time_m)
        if due <= now:
            due += timedelta(days=7)
        return due, consumed, False

    # 4 · "pasado mañana" / "mañana" / "hoy" (+ hora opcional).
    #     OJO: probar "pasado mañana" ANTES que "mañana" (subcadena).
    after_m = _AFTER_TOMORROW_RE.search(text)
    if after_m:
        consumed = [after_m] + ([time_m] if time_m else [])
        return _apply_time(now + timedelta(days=2), time_m), consumed, False

    tomorrow_m = _TOMORROW_RE.search(text)
    if tomorrow_m:
        consumed = [tomorrow_m] + ([time_m] if time_m else [])
        return _apply_time(now + timedelta(days=1), time_m), consumed, False

    today_m = _TODAY_RE.search(text)
    if today_m:
        consumed = [today_m] + ([time_m] if time_m else [])
        due = _apply_time(now, time_m)
        if due <= now:  # "hoy a las 7" pero ya son las 9 → mañana a esa hora
            due += timedelta(days=1)
        return due, consumed, False

    # 5 · hora suelta: "a las 4" → hoy a esa hora (o mañana si ya pasó).
    if time_m:
        due = _apply_time(now, time_m)
        if due <= now:
            due += timedelta(days=1)
        return due, [time_m], False

    return None, [], False


def _clean_subject(text: str, consumed: list[re.Match]) -> str:
    """Quita del mensaje el disparador y las expresiones de fecha/hora → el QUÉ."""
    spans = sorted((m.start(), m.end()) for m in consumed if m)
    out, prev = [], 0
    for start, end in spans:
        out.append(text[prev:start])
        prev = max(prev, end)
    out.append(text[prev:])
    subject = " ".join("".join(out).split())
    subject = re.sub(r"^(que|de|para|:|,)\s+", "", subject, flags=re.IGNORECASE).strip(" ,.;:")
    return subject or "Recordatorio"


def parse_reminder(text: str, now: datetime | None = None) -> ParsedReminder | None:
    """Detecta y parsea la petición de recordatorio. None = no es un recordatorio.

    ``due_at=None`` = es un recordatorio pero falta la fecha (el asistente pregunta;
    si ``business_days`` es True, pidió "días hábiles" y se pide la fecha exacta).
    Un disparador DÉBIL ("avísame") sin fecha NO se intercepta: es conversación.
    ``now`` inyectable para tests deterministas; default: hora local con tz.
    """
    text = (text or "").strip()
    strong = _STRONG_TRIGGER_RE.search(text)
    weak = None if strong else _WEAK_TRIGGER_RE.search(text)
    if not strong and not weak:
        return None
    now = now if now is not None else datetime.now().astimezone()

    due, consumed, business = _when(text, now)
    if weak and due is None:
        # "avísame" sin fecha = frase conversacional ("avísame qué opinas") — el
        # turno sigue su camino normal al modelo (hallazgo M5).
        return None

    is_procedural = is_procedural_text(text)
    subject = _clean_subject(text, [strong or weak, *consumed])
    return ParsedReminder(subject, due, is_procedural, business_days=business)


def parse_when(text: str, now: datetime | None = None) -> datetime | None:
    """Solo el CUÁNDO, sin exigir disparador — para el turno de seguimiento:
    Mia preguntó "¿cuándo?" y el abogado responde "mañana a las 9"."""
    now = now if now is not None else datetime.now().astimezone()
    due, _consumed, _business = _when((text or "").strip(), now)
    return due


def format_due(due: datetime) -> str:
    """Fecha legible en español, sin depender del locale. Incluye el año cuando
    no es el año en curso (que "15 de agosto" de otro año no se lea como próximo)."""
    local = due.astimezone()
    base = f"{local.day} de {_MONTH_NAMES[local.month]}"
    if local.year != datetime.now().astimezone().year:
        base += f" de {local.year}"
    return f"{base} a las {local:%H:%M}"


class ReminderService:
    """CRUD y despacho de recordatorios, todo bajo RLS (pool.tenant_connection)."""

    async def create(
        self,
        tenant_id: str,
        user_id: str | None,
        text: str,
        due_at: datetime,
        is_procedural: bool,
    ) -> str:
        async with pool.tenant_connection(tenant_id) as conn:
            row = await (await conn.execute(
                "INSERT INTO reminders (tenant_id, user_id, text, due_at, is_procedural) "
                "VALUES (%s::uuid, %s::uuid, %s, %s, %s) RETURNING id",
                (tenant_id, user_id, text, due_at, is_procedural),
            )).fetchone()
        return str(row[0])

    async def list_pending(self, tenant_id: str) -> list[dict]:
        """Recordatorios pendientes del despacho, el más próximo primero."""
        async with pool.tenant_connection(tenant_id) as conn:
            rows = await (await conn.execute(
                "SELECT id, text, due_at, is_procedural FROM reminders "
                "WHERE status = 'pending' ORDER BY due_at",
            )).fetchall()
        return [
            {"id": str(r[0]), "text": r[1], "due_at": r[2].isoformat(),
             "is_procedural": r[3]}
            for r in rows
        ]

    async def cancel(self, tenant_id: str, reminder_id: str) -> bool:
        """Cancela un recordatorio pendiente del tenant. False si no existe (RLS incluido)."""
        async with pool.tenant_connection(tenant_id) as conn:
            cur = await conn.execute(
                "UPDATE reminders SET status = 'cancelled' "
                "WHERE id = %s::uuid AND status = 'pending'",
                (reminder_id,),
            )
        return cur.rowcount > 0

    async def due(self, tenant_id: str) -> list[dict]:
        """Pendientes ya vencidos (due_at <= now) — lo que el job debe despachar."""
        async with pool.tenant_connection(tenant_id) as conn:
            rows = await (await conn.execute(
                "SELECT id, text, due_at, is_procedural FROM reminders "
                "WHERE status = 'pending' AND due_at <= now() ORDER BY due_at",
            )).fetchall()
        return [
            {"id": str(r[0]), "text": r[1], "due_at": r[2], "is_procedural": r[3]}
            for r in rows
        ]

    async def mark_sent(self, tenant_id: str, reminder_id: str) -> None:
        # Guarda de estado: si el abogado canceló entre due() y el envío, la
        # cancelación GANA (un 'cancelled' jamás pasa a 'sent').
        async with pool.tenant_connection(tenant_id) as conn:
            await conn.execute(
                "UPDATE reminders SET status = 'sent', sent_at = now() "
                "WHERE id = %s::uuid AND status = 'pending'",
                (reminder_id,),
            )
