"""Mia · rag.corpus_factory — Data Factory del corpus jurídico (Módulo 3a+).

Motor de ingesta declarativa que reemplaza la semilla hardcodeada de `ingest_corpus.py`.
El QUÉ ingerir vive en datos (`packs/{jur}/corpus_sources.json`); el CÓMO extraerlo vive en
adaptadores, uno por portal oficial. Crecer el corpus = editar el JSON, no el código.

Diseño (imita `connectors/mailbox/providers.py`): una clase adaptador por fuente, con
cliente HTTP INYECTADO por constructor (permite fakes en tests, cero red), y una factory
`build_adapter` fail-soft. La orquestación (`ingest_catalog`) es fail-soft por entrada: una
norma caída no tumba la corrida.

Garantías jurídicas duras:
  · GATE ToS — una fuente con `tos_ok!=true` o `verified!=true` se SALTA entera.
  · VALIDACIÓN DE IDENTIDAD (fail-closed) — jamás se ingiere texto cuyo `norm_number`/número
    de sentencia esperado no aparezca en el documento descargado. El peor modo de falla es
    texto equivocado bajo una cita correcta; ante la duda se descarta.
  · SEGMENTACIÓN — normas gigantes (Código de Comercio) se parten en el límite de artículo
    para no reventar el tsvector de FTS (límite ~1MB en Postgres).

Los textos oficiales (leyes, decretos, providencias) son reproducibles fielmente sin
restricción (Ley 23 de 1982, art. 41): la ingesta NO marca `[VERIFICAR]` (es fuente real).
"""
from __future__ import annotations

import hashlib
import json
import logging
import re
import unicodedata
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any, Optional

from bs4 import BeautifulSoup

from ..jurisdiction.pack import GENERIC_CODE, PACKS_DIR
from .sat_graph import SATGraph

logger = logging.getLogger(__name__)

# Umbral de segmentación: por encima de ~500k chars el tsvector de FTS (config 'spanish')
# se acerca al límite de ~1MB de Postgres y el INSERT revienta. Se parte por artículo.
MAX_NORM_CHARS = 500_000

# Un documento de la Relatoría por debajo de esto es casi seguro el shell vacío de la SPA.
_MIN_RULING_BYTES = 20_000

_WS_RE = re.compile(r"\s+")
# Límite de corte de la segmentación: inicio de artículo ("ARTÍCULO 123", "ARTICULO 1").
_ART_RE = re.compile(r"\bART[IÍ]CULO\s+(\d+)", re.IGNORECASE)
# Magistrado/a ponente en providencias de la Corte: SOLO el patrón limpio "Magistrado(a)
# Ponente: NOMBRE" en línea propia — se abandona la forma abreviada "M.P." y cualquier
# captura no anclada porque, sobre el texto ya colapsado a espacio simple (_visible_text),
# arrastraban basura del párrafo siguiente hasta el límite de 69 caracteres (defecto
# verificado 2026-07-08: capturó "renden y justifican como transmisión instrumental...").
# El nombre real de un magistrado en la Relatoría va SIEMPRE en mayúsculas sostenidas, así
# que el corte natural y seguro es exigir palabras en mayúscula (deja de comer texto en
# minúscula del párrafo siguiente, p.ej. "Bogotá D.C., ...").
_MP_RE = re.compile(
    r"[Mm]agistrad[oa]\s+[Pp]onente\s*:\s*((?:[A-ZÁÉÍÓÚÑ]{2,}\s+){1,4}[A-ZÁÉÍÓÚÑ]{2,})"
)
_MESES = {
    "enero": 1, "febrero": 2, "marzo": 3, "abril": 4, "mayo": 5, "junio": 6,
    "julio": 7, "agosto": 8, "septiembre": 9, "setiembre": 9, "octubre": 10,
    "noviembre": 11, "diciembre": 12,
}
_DATE_RE = re.compile(
    r"(\d{1,2})\s+de\s+([a-záéíóúñ]+)\s+de\s+(?:[^\d]{0,20})?(\d{4})", re.IGNORECASE
)


# ── helpers ──────────────────────────────────────────────────────────────────
def _normalize(s: Optional[str]) -> str:
    """Minúsculas y sin tildes, para comparaciones de identidad robustas."""
    s = unicodedata.normalize("NFKD", s or "")
    s = "".join(c for c in s if not unicodedata.combining(c))
    return s.lower().strip()


def _sha256(raw: Any) -> str:
    if isinstance(raw, str):
        raw = raw.encode("utf-8", "replace")
    return hashlib.sha256(raw or b"").hexdigest()


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _decode_response(resp: Any, *, prefer_cp1252: bool = False) -> tuple[str, bytes]:
    """Devuelve (html_str, raw_bytes). `raw_bytes` es el HTML crudo tal cual llegó (para el
    sha256 de trazabilidad). Los HTML de la Corte son Word/charset windows-1252."""
    raw = getattr(resp, "content", None)
    if raw is None:
        text = getattr(resp, "text", "") or ""
        return text, text.encode("utf-8", "replace")
    if prefer_cp1252:
        for enc in ("cp1252", "utf-8"):
            try:
                return raw.decode(enc), raw
            except (UnicodeDecodeError, LookupError):
                continue
        return raw.decode("utf-8", "replace"), raw
    text = getattr(resp, "text", None)
    if text is None:
        text = raw.decode("utf-8", "replace")
    return text, raw


def _visible_text(soup: BeautifulSoup) -> str:
    """Texto legible: quita script/style/nav/header/footer y colapsa espacios."""
    for tag in soup(["script", "style", "nav", "header", "footer"]):
        tag.decompose()
    return _WS_RE.sub(" ", soup.get_text(separator=" ")).strip()


# ── segmentación de normas grandes ───────────────────────────────────────────
def segment_norm(norm: dict, max_chars: int = MAX_NORM_CHARS) -> list[dict]:
    """Parte una norma cuyo `full_text` supere `max_chars` en el límite de artículo más
    cercano al corte. Cada parte < max_chars y con `norm_number` = "{n} (parte i de N)"
    — SIN rango de artículos: la regex de corte agarra números de artículos CITADOS dentro
    del texto (referencias cruzadas), no encabezados reales, así que cualquier rango mostrado
    (p.ej. "arts. 370–292") podía salir invertido o falso (defecto verificado 2026-07-08). Un
    rango falso visible es peor que ninguno. El rango real vive solo en metadata
    (`segment`/`segments_total`), no en el texto que ve el abogado. Mismo effective_date/
    issuing_body; el norm_number base completo sigue dentro del label (el matcher de
    identidad usa inclusión normalizada). Una norma pequeña devuelve [norm] sin tocar."""
    text = norm.get("full_text") or ""
    if len(text) <= max_chars:
        return [dict(norm)]

    starts = [m.start() for m in _ART_RE.finditer(text)]
    cuts = [0]
    pos = 0
    n = len(text)
    while n - pos > max_chars:
        window_end = pos + max_chars
        candidate = None
        for s in starts:
            if pos < s <= window_end:
                candidate = s      # el último inicio de artículo dentro de la ventana
            elif s > window_end:
                break
        if candidate is None:      # sin límite de artículo: corte duro (evita reventar FTS)
            candidate = window_end
        cuts.append(candidate)
        pos = candidate
    cuts.append(n)

    base = norm.get("norm_number") or ""
    total = len(cuts) - 1
    out: list[dict] = []
    for i in range(total):
        seg_text = text[cuts[i]:cuts[i + 1]]
        seg = dict(norm)
        seg["full_text"] = seg_text
        seg["norm_number"] = f"{base} (parte {i + 1} de {total})"
        meta = dict(norm.get("metadata") or {})
        meta.update({"segment": i + 1, "segments_total": total, "parent_norm": base})
        seg["metadata"] = meta
        out.append(seg)
    return out


# ── identidad + armado del dict de norma, compartido entre adaptadores de norma
# (revisión capa 2: FuncionPublica y SuinJuriscol duplicaban esta lógica letra por
# letra; una corrección al fail-closed de identidad aplicada a un adaptador y olvidada
# en el otro dejaría esa fuente con una garantía distinta — ahora hay un solo lugar).
def _identity_confirmed(source_label: str, entry: dict, page_title: str, full_text: str, url: str) -> bool:
    """VALIDACIÓN DE IDENTIDAD (fail-closed): el `norm_number` esperado debe aparecer en
    el título o en el arranque del texto; si no, se descarta y se loggea. Nunca lanza —
    el llamador decide qué hacer con `entry` cuando devuelve False."""
    expected = _normalize(entry.get("norm_number"))
    haystack = _normalize(page_title) + " " + _normalize(full_text[:2000])
    if not expected or expected not in haystack:
        logger.warning(
            "%s: identidad no confirmada para %s (%s) — se descarta",
            source_label, entry.get("norm_number"), url,
        )
        return False
    return True


def _build_norm_record(entry: dict, *, full_text: str, source: str, url: str, raw: bytes,
                       jurisdiction: str = GENERIC_CODE) -> dict:
    """Dict listo para `add_norm`, compartido entre adaptadores de norma (solo cambia
    `metadata.source` y la URL/bytes de origen).

    `jurisdiction` = la del PACK que se está ingiriendo (la sabe `ingest_catalog`; la
    inyecta `build_adapter`). Antes era `entry.get("jurisdiction", "co")`: ingerir el
    catálogo del pack español marcaba sus normas como COLOMBIANAS. Una entrada del catálogo
    puede seguir declarando la suya (un pack puede catalogar derecho comunitario)."""
    eff = entry.get("effective_date")
    if isinstance(eff, str):
        eff = date.fromisoformat(eff)
    summary = entry.get("summary") or full_text[:600].strip()
    return {
        "norm_type": entry.get("norm_type"),
        "norm_number": entry.get("norm_number"),
        "issuing_body": entry.get("issuing_body"),
        "title": entry.get("title"),
        "summary": summary,
        "full_text": full_text,
        "effective_date": eff,
        "expiry_date": entry.get("expiry_date"),
        "jurisdiction": entry.get("jurisdiction") or jurisdiction,
        "practice_areas": entry.get("practice_areas"),
        "metadata": {
            "source": source,
            "source_url": url,
            "fetched_at": _now_iso(),
            "content_sha256": _sha256(raw),
            "ingesta": "corpus_factory",
            "verified_source": True,
        },
    }


# ── adaptadores (uno por portal) ─────────────────────────────────────────────
class FuncionPublicaAdapter:
    """Gestor Normativo de Función Pública: leyes y decretos (texto oficial)."""

    def __init__(self, cfg: dict, *, http, jurisdiction: str = GENERIC_CODE) -> None:
        self._cfg = cfg
        self._http = http
        self._base = cfg.get("base_url", "")
        self._jurisdiction = jurisdiction

    async def fetch_norm(self, entry: dict) -> Optional[dict]:
        """Descarga y parsea una norma. Devuelve el dict listo para `add_norm`, o None si la
        identidad no se confirma (fail-closed: nunca texto equivocado bajo cita correcta)."""
        url = f"{self._base}?i={entry.get('source_id')}"
        resp = await self._http.get(url, timeout=30.0, follow_redirects=True)
        status = getattr(resp, "status_code", 0)
        if status != 200:
            logger.warning("funcionpublica: %s devolvió status %s", url, status)
            return None

        html_str, raw = _decode_response(resp)
        soup = BeautifulSoup(html_str, "html.parser")
        page_title = soup.title.get_text(strip=True) if soup.title else ""
        full_text = _visible_text(soup)

        if not _identity_confirmed("funcionpublica", entry, page_title, full_text, url):
            return None
        return _build_norm_record(entry, full_text=full_text, source="funcionpublica", url=url,
                                  raw=raw, jurisdiction=self._jurisdiction)


class SuinJuriscolAdapter:
    """SUIN-Juriscol (Ministerio de Justicia): normas no cubiertas por el Gestor Normativo
    de Función Pública (p.ej. el Código Civil — Ley 84 de 1873, que solo vive aquí).

    Gotcha verificado (2026-07-08, curl): el <meta> del HTML declara `charset=utf-16`, pero
    los bytes reales que sirve el portal son UTF-8 — decodificar SIEMPRE como utf-8 con
    errors='replace'; NUNCA confiar en el charset declarado por el propio documento.

    La cadena de certificados TLS de este portal está incompleta (verificado 2026-07-08),
    por lo que la fuente se declara con `ssl_verify: false` en el catálogo y el cliente HTTP
    inyectado se crea sin verificación TLS para este `source` específicamente (ver
    `ingest_catalog`). Esto es aceptable porque la integridad de lo ingerido no depende del
    transporte: se sigue aplicando la misma validación de identidad fail-closed sobre el
    CONTENIDO (el `norm_number` esperado debe aparecer en título/arranque del texto) y se
    conserva el sha256 de trazabilidad de los bytes crudos — un MITM que alterara el
    contenido sería detectado por el mismatch de identidad, no por TLS.
    """

    def __init__(self, cfg: dict, *, http, jurisdiction: str = GENERIC_CODE) -> None:
        self._cfg = cfg
        self._http = http
        self._base = cfg.get("base_url", "")
        self._jurisdiction = jurisdiction

    async def fetch_norm(self, entry: dict) -> Optional[dict]:
        """Descarga y parsea una norma. Devuelve el dict listo para `add_norm`, o None si la
        identidad no se confirma (fail-closed: nunca texto equivocado bajo cita correcta)."""
        url = f"{self._base}?id={entry.get('source_id')}"
        resp = await self._http.get(url, timeout=30.0, follow_redirects=True)
        status = getattr(resp, "status_code", 0)
        if status != 200:
            logger.warning("suin: %s devolvió status %s", url, status)
            return None

        raw = getattr(resp, "content", None)
        if raw is None:
            raw = (getattr(resp, "text", "") or "").encode("utf-8", "replace")
        # El charset declarado en el <meta> del HTML es utf-16, pero es una mentira del
        # documento: los bytes reales son utf-8. Se ignora el charset declarado a propósito.
        html_str = raw.decode("utf-8", "replace")
        soup = BeautifulSoup(html_str, "html.parser")
        page_title = soup.title.get_text(strip=True) if soup.title else ""
        full_text = _visible_text(soup)

        if not _identity_confirmed("suin", entry, page_title, full_text, url):
            return None
        return _build_norm_record(entry, full_text=full_text, source="suin", url=url, raw=raw,
                                  jurisdiction=self._jurisdiction)


class CorteConstitucionalAdapter:
    """Relatoría de la Corte Constitucional: providencias (C, T, SU, A)."""

    _RELATORIA = "https://www.corteconstitucional.gov.co/relatoria"

    def __init__(self, cfg: dict, *, http, jurisdiction: str = GENERIC_CODE) -> None:
        self._cfg = cfg
        self._http = http
        self._base = cfg.get("base_url") or self._RELATORIA
        self._jurisdiction = jurisdiction

    def _build_url(self, tipo: str, numero: str, anio: int) -> str:
        aa = f"{anio % 100:02d}"
        # Las SU van SIN guion tras "SU" (p.ej. SU070-13.htm); el resto lleva guion.
        if tipo == "su":
            fname = f"SU{numero}-{aa}.htm"
        else:
            fname = f"{tipo.upper()}-{numero}-{aa}.htm"
        return f"{self._base}/{anio}/{fname}"

    def _number_variants(self, tipo: str, numero: str, anio: int) -> list[str]:
        aa = f"{anio % 100:02d}"
        t = tipo.upper()
        raw = [
            f"{t}-{numero}/{aa}", f"{t}-{numero} de {anio}", f"{t}-{numero}-{aa}",
            f"{t}{numero}/{aa}", f"{t}{numero}-{aa}", f"{t}.{numero}/{aa}",
        ]
        return [_normalize(v) for v in raw]

    async def fetch_ruling(self, entry: dict) -> Optional[dict]:
        """Descarga y parsea una providencia. None si es el shell vacío de la SPA o si el
        número no aparece (fail-closed)."""
        tipo = str(entry.get("tipo", "")).lower()
        numero = str(entry.get("numero", ""))
        anio = int(entry.get("anio"))
        url = self._build_url(tipo, numero, anio)

        resp = await self._http.get(url, timeout=30.0, follow_redirects=True)
        status = getattr(resp, "status_code", 0)
        if status != 200:
            logger.warning("corteconstitucional: %s devolvió status %s", url, status)
            return None

        html_str, raw = _decode_response(resp, prefer_cp1252=True)
        # Shell vacío de la SPA: HTML minúsculo o sin el número de la sentencia.
        variants = self._number_variants(tipo, numero, anio)
        norm_html = _normalize(html_str)
        if len(raw) < _MIN_RULING_BYTES or not any(v in norm_html for v in variants):
            logger.warning(
                "corteconstitucional: documento vacío o sin el número esperado (%s) — se descarta",
                url,
            )
            return None

        soup = BeautifulSoup(html_str, "html.parser")
        text = _visible_text(soup)
        norm_text = _normalize(text)

        # magistrado_ponente: el catálogo se verifica a mano contra la relatoría, pero
        # (hallazgo de auditoría) un TYPO en el catálogo aparecería como dato jurídico real.
        # Por eso NO se presenta el MP del catálogo sin CORROBORARLO por inclusión contra el
        # texto oficial descargado — mismo criterio fail-closed que `_identity_confirmed` con
        # el norm_number. Si el MP del catálogo aparece en el texto → confirmado, se usa. Si
        # NO aparece → se descarta y se cae a la extracción limpia del HTML (y si esa tampoco
        # da un patrón limpio, queda VACÍO: mejor vacío que un dato sin respaldo en la fuente).
        catalog_mp = entry.get("magistrado_ponente") or None
        mp_confirmed = bool(catalog_mp) and _normalize(catalog_mp) in norm_text
        if catalog_mp and mp_confirmed:
            mp = catalog_mp
        else:
            m = _MP_RE.search(text)
            mp = m.group(1).strip() if m else None
            if catalog_mp and not mp_confirmed:
                logger.warning(
                    "corteconstitucional: MP de catálogo '%s' NO aparece en el texto oficial "
                    "(%s) — no se da por confirmado; se usa la extracción del HTML (%s)",
                    catalog_mp, url, mp,
                )

        # decision_date: mismo criterio. La fecha del catálogo solo se presenta como firme si
        # aparece (como fecha real "D de MES de AAAA") en el texto oficial; si no se corrobora,
        # se conserva el valor pero se marca `decision_date_approx` (no se presenta como
        # confirmada). Sin fecha en catálogo, se parsea del HTML (aproximada si no se encuentra).
        entry_date = entry.get("decision_date")
        approx = False
        if entry_date:
            decision_date = (date.fromisoformat(entry_date)
                             if isinstance(entry_date, str) else entry_date)
            if not self._date_in_text(text, decision_date):
                approx = True
                logger.warning(
                    "corteconstitucional: fecha de catálogo %s NO corroborada en el texto "
                    "oficial (%s) — se marca aproximada (decision_date_approx)",
                    decision_date.isoformat(), url,
                )
        else:
            decision_date, approx = self._parse_date(text, anio)

        topic = self._extract_topic(text)

        cons = re.search(r"considerac", text, re.IGNORECASE)
        ratio = text[cons.start():cons.start() + 4000].strip() if cons else None

        metadata = {
            "source": "corteconstitucional",
            "source_url": url,
            "fetched_at": _now_iso(),
            "content_sha256": _sha256(raw),
            "ingesta": "corpus_factory",
            "verified_source": True,
            "full_text_omitted": True,
        }
        if approx:
            metadata["decision_date_approx"] = True

        return {
            # Igual que en `_build_norm_record`: la del pack que se ingiere, no un país
            # supuesto. La entrada del catálogo puede declarar la suya.
            "jurisdiction": entry.get("jurisdiction") or self._jurisdiction,
            "court": "Corte Constitucional",
            "sala": entry.get("sala"),
            "decision_number": f"{tipo.upper()}-{numero} de {anio}",
            "radicado": entry.get("radicado"),
            "magistrado_ponente": mp,
            "decision_date": decision_date,
            "topic": topic,
            "ratio_decidendi": ratio,
            "obiter_dicta": None,
            "keywords": entry.get("keywords"),
            "metadata": metadata,
        }

    @staticmethod
    def _date_in_text(text: str, target: date) -> bool:
        """True si `target` aparece como fecha real ('D de MES de AAAA') en el texto oficial.
        Corrobora una fecha traída del catálogo antes de presentarla como confirmada
        (hallazgo de auditoría: una fecha de catálogo equivocada no puede pasar como firme)."""
        for m in _DATE_RE.finditer(text):
            mes = _MESES.get(_normalize(m.group(2)))
            if not mes:
                continue
            try:
                d = date(int(m.group(3)), mes, int(m.group(1)))
            except ValueError:
                continue
            if d == target:
                return True
        return False

    @staticmethod
    def _parse_date(text: str, anio: int) -> tuple[date, bool]:
        """(fecha, es_aproximada). Si no se puede parsear, date(anio, 1, 1) aproximada."""
        for m in _DATE_RE.finditer(text):
            mes = _MESES.get(_normalize(m.group(2)))
            if not mes:
                continue
            try:
                d = date(int(m.group(3)), mes, int(m.group(1)))
            except ValueError:
                continue
            if d.year == anio:
                return d, False
        return date(anio, 1, 1), True

    @staticmethod
    def _extract_topic(text: str) -> Optional[str]:
        m = re.search(r"(?:referencia|asunto)\s*:?\s*(.{20,300})", text, re.IGNORECASE)
        if m:
            return m.group(1).strip()
        stripped = text.strip()
        return stripped[:300] or None


def build_adapter(source_cfg: dict, *, http, jurisdiction: str = GENERIC_CODE):
    """Fabrica el adaptador de una fuente por su `code`. None (con warning) si no se reconoce.

    `jurisdiction`: la del pack que se ingiere; el adaptador marca con ella lo que produce
    (ver `_build_norm_record`). Por defecto 'generic' — nunca un país supuesto."""
    code = source_cfg.get("code")
    if code == "funcionpublica":
        return FuncionPublicaAdapter(source_cfg, http=http, jurisdiction=jurisdiction)
    if code == "corteconstitucional":
        return CorteConstitucionalAdapter(source_cfg, http=http, jurisdiction=jurisdiction)
    if code == "suin":
        return SuinJuriscolAdapter(source_cfg, http=http, jurisdiction=jurisdiction)
    logger.warning("fuente de corpus desconocida: %s", code)
    return None


# ── orquestación ─────────────────────────────────────────────────────────────
def _tos_ok(src: Optional[dict]) -> bool:
    return bool(src) and src.get("tos_ok") is True and src.get("verified") is True


def _load_sources(jurisdiction: str) -> dict:
    """Carga `corpus_sources.json` del pack de la jurisdicción (vacío si no existe)."""
    path = PACKS_DIR / jurisdiction / "corpus_sources.json"
    if not path.is_file():
        logger.warning("no hay corpus_sources.json para la jurisdicción %s", jurisdiction)
        return {"sources": [], "catalog": {}}
    return json.loads(path.read_text(encoding="utf-8"))


async def ingest_catalog(jurisdiction: str, *, http=None, pool=None,
                         only: Optional[str] = None, limit: Optional[int] = None,
                         dry_run: bool = False, pause: float = 1.0) -> dict:
    """Recorre el catálogo declarativo y lo ingiere al SAT-Graph. Fail-soft por entrada.

    `jurisdiction` es OBLIGATORIA (antes: `= "co"`). Dice de qué pack se lee el catálogo Y
    con qué jurisdicción se marca lo ingerido: llamar sin decirlo no puede significar
    "Colombia" en un producto agnóstico de jurisdicción.

    `http`: cliente async con `get(url, ...)` (se inyecta para tests sin red; si es None se
    crea un httpx.AsyncClient POR FUENTE, respetando `ssl_verify` de cada una — algunos
    portales estatales, p.ej. SUIN-Juriscol, sirven con cadena de certificados incompleta;
    la identidad del contenido se sigue validando fail-closed en cada adaptador). `only`:
    'norms' | 'jurisprudence' | None (ambos). `limit`: tope de entradas efectivamente
    descargadas. `dry_run`: no escribe. `pause`: cortesía entre requests (somos huéspedes de
    portales estatales; en tests se pasa 0).

    Devuelve stats: {norms, jurisprudence, segments, rejected_identity, skipped_tos, errors}.
    """
    import asyncio

    # Código canónico del pack: es lo que se le inyecta a cada adaptador para marcar lo que
    # ingiere. Vacío → 'generic' (neutro), nunca un país supuesto.
    jur = str(jurisdiction or "").strip().lower() or GENERIC_CODE

    cfg = _load_sources(jur)
    sources_by_code = {s.get("code"): s for s in cfg.get("sources", [])}
    catalog = cfg.get("catalog", {}) or {}

    own_http = http is None
    owned_clients: list[Any] = []
    if own_http:
        import httpx
        # Un AsyncClient por fuente: `ssl_verify` es un flag por fuente (no global), así
        # que cada portal recibe su propio cliente con el `verify` que le corresponde.
        adapters = {}
        for code, s in sources_by_code.items():
            if not _tos_ok(s):
                continue
            client = httpx.AsyncClient(timeout=httpx.Timeout(30.0, connect=10.0),
                                       verify=s.get("ssl_verify", True))
            owned_clients.append(client)
            a = build_adapter(s, http=client, jurisdiction=jur)
            if a is not None:
                adapters[code] = a
    else:
        # Adaptadores solo para fuentes que pasan el GATE ToS.
        adapters = {code: build_adapter(s, http=http, jurisdiction=jur)
                    for code, s in sources_by_code.items() if _tos_ok(s)}
        adapters = {code: a for code, a in adapters.items() if a is not None}

    sat = SATGraph()
    stats: dict[str, Any] = {"norms": 0, "jurisprudence": 0, "segments": 0,
                             "rejected_identity": 0, "skipped_tos": 0, "errors": []}
    processed = 0

    def _reached_limit() -> bool:
        return limit is not None and processed >= limit

    try:
        # ── normas ──
        if only in (None, "norms"):
            for entry in catalog.get("norms", []) or []:
                if _reached_limit():
                    break
                src = sources_by_code.get(entry.get("source"))
                if src is None:
                    stats["errors"].append({"entry": entry.get("norm_number"),
                                            "error": "fuente no declarada"})
                    continue
                if not _tos_ok(src):
                    stats["skipped_tos"] += 1
                    continue
                adapter = adapters.get(entry.get("source"))
                if adapter is None:
                    stats["errors"].append({"entry": entry.get("norm_number"),
                                            "error": "sin adaptador"})
                    continue
                processed += 1
                try:
                    norm = await adapter.fetch_norm(entry)
                except Exception as e:  # noqa: BLE001 — fail-soft por entrada
                    stats["errors"].append({"entry": entry.get("norm_number"), "error": str(e)})
                    continue
                if norm is None:
                    stats["rejected_identity"] += 1
                    continue
                segs = segment_norm(norm)
                if len(segs) > 1:
                    stats["segments"] += len(segs)
                for s in segs:
                    if not dry_run:
                        await sat.add_norm(s)
                    stats["norms"] += 1
                if pause:
                    await asyncio.sleep(pause)

        # ── jurisprudencia ──
        if only in (None, "jurisprudence"):
            for entry in catalog.get("jurisprudence", []) or []:
                if _reached_limit():
                    break
                src = sources_by_code.get(entry.get("source"))
                if src is None:
                    stats["errors"].append({"entry": entry.get("numero"),
                                            "error": "fuente no declarada"})
                    continue
                if not _tos_ok(src):
                    stats["skipped_tos"] += 1
                    continue
                adapter = adapters.get(entry.get("source"))
                if adapter is None:
                    stats["errors"].append({"entry": entry.get("numero"),
                                            "error": "sin adaptador"})
                    continue
                processed += 1
                try:
                    ruling = await adapter.fetch_ruling(entry)
                except Exception as e:  # noqa: BLE001 — fail-soft por entrada
                    stats["errors"].append({"entry": entry.get("numero"), "error": str(e)})
                    continue
                if ruling is None:
                    stats["rejected_identity"] += 1
                    continue
                if not dry_run:
                    await sat.add_jurisprudence(ruling)
                stats["jurisprudence"] += 1
                if pause:
                    await asyncio.sleep(pause)
    finally:
        if own_http:
            for client in owned_clients:
                await client.aclose()

    return stats


# ── CLI ──────────────────────────────────────────────────────────────────────
async def _run(jurisdiction: str, only: Optional[str], limit: Optional[int],
               dry_run: bool) -> None:
    """La jurisdicción es EXPLÍCITA (antes se caía al default 'co' de `ingest_catalog`):
    ingerir el corpus de un país es una decisión, no un efecto colateral de correr un
    script — mismo criterio que el CLI de `ingest_corpus`."""
    from ..db import pool
    await pool.open_pool()
    try:
        stats = await ingest_catalog(jurisdiction, only=only, limit=limit, dry_run=dry_run)
    finally:
        await pool.close_pool()

    print(f"== Data Factory del corpus jurídico · jurisdicción '{jurisdiction}' ==")
    print(f"Normas ingeridas:        {stats['norms']}  (segmentos: {stats['segments']})")
    print(f"Providencias ingeridas:  {stats['jurisprudence']}")
    print(f"Descartadas por identidad no confirmada: {stats['rejected_identity']}")
    print(f"Saltadas por permisos/ToS:               {stats['skipped_tos']}")
    if stats["errors"]:
        print(f"Errores ({len(stats['errors'])}):")
        for e in stats["errors"]:
            print(f"  - {e}")
    if dry_run:
        print("(dry-run: no se escribió nada en la base)")


if __name__ == "__main__":
    # Ejecutar como módulo:
    #   python -m mia.rag.corpus_factory <jurisdiccion> [--only ...] [--limit N] [--dry-run]
    import argparse
    import asyncio
    import sys

    # psycopg async no corre sobre ProactorEventLoop (Windows nativo, Modo B).
    if sys.platform == "win32":
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass

    parser = argparse.ArgumentParser(description="Data Factory del corpus jurídico de Mia.")
    parser.add_argument("jurisdiction",
                        help="código del pack cuyo catálogo se ingiere (p. ej. 'co'). "
                             "Obligatorio: marca la jurisdicción de lo ingerido y MIA no "
                             "supone un país.")
    parser.add_argument("--only", choices=["norms", "jurisprudence"], default=None,
                        help="ingerir solo normas o solo jurisprudencia (por defecto ambos)")
    parser.add_argument("--limit", type=int, default=None,
                        help="tope de entradas a descargar")
    parser.add_argument("--dry-run", action="store_true",
                        help="no escribe en la base; solo reporta lo que haría")
    args = parser.parse_args()
    asyncio.run(_run(args.jurisdiction, args.only, args.limit, args.dry_run))
