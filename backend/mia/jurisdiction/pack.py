"""Mia · jurisdiction.pack — carga de paquetes de jurisdicción (Decisión #24).

Un `JurisdictionPack` agrupa los DATOS de referencia de una jurisdicción. Se compone de
archivos JSON opcionales bajo `packs/{code}/`:

  meta.json          {code, name, version, verified, verified_at, sources[], freshness?}
                     `freshness` (opcional) declara vigencia POR ARCHIVO del pack:
                     {archivo: {last_verified, freshness_window_days, freshness_category}}
  holidays.json      {"2025": ["2025-01-01", ...], ...}
  recess.json        [{"name", "start": "MM-DD", "end": "MM-DD"}]   (feria/vacancia judicial)
  id_formats.json    {"cedula": {"label", "regex", "marker", "role", "order", "flags"}, ...}
                     Consumido por `security/anonymize.py`. `marker` = TIPO del marcador
                     ([[CEDULA_1]]); `role` = qué cubre ("document"|"tax_id"|"phone"|
                     "case_number"|"account"), puramente DESCRIPTIVO; `order` = prioridad
                     (menor primero: lo más específico gana los dígitos).
                     OJO — un pack solo puede SUMAR cobertura, jamás restarla: `role` ya NO
                     suprime el respaldo pan-hispano equivalente (lo hacía, y era una fuga:
                     un `role` con un regex estrecho apagaba el respaldo entero). El
                     anonimizador aplica SIEMPRE su base + TODOS los packs instalados + sus
                     respaldos, sin mirar la jurisdicción del despacho.
  pii_hints.json     {"address_prefixes": [...], "stop_capitalized": [...]}
                     Pistas de la heurística de SOSPECHA de `anonymize.scan_suspects`
                     (solo MARCA para revisión humana; nunca oculta).
  doc_markers.json   {"norm": [...], "contract": [...], "ruling": [...]}  (LegalChunker)
  mail_signals.json  {"urgency_terms": [...], "institutional_sender_domains": [...]}
                     Consumido por `connectors/mailbox/base.py` (wake-gate metadata-only).
  term_catalog.json  {"<termino>": {"label", "days", "kind": "habil|calendario"}}
  citation_style.json

`load_pack(code)` tolera archivos faltantes E ILEGIBLES/CORRUPTOS (los trata como vacíos, con
log): un typo en un JSON no puede tumbar el pack entero ni quitarle cobertura a los consumidores
fail-closed (anonimizador, wake-gate de correo). Un `code` sin
carpeta → `GenericPack` (modo genérico): sin festivos, sin marcadores, formatos de ID
genéricos. NADA en el código conoce una jurisdicción concreta: el conocimiento vive en
los datos.

Cardinal: un pack con `verified=false` NO debe presentarse como autoridad verificada.
Los consumidores (calendario, investigación) deben marcar supuestos no verificados.
"""
from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path

logger = logging.getLogger("mia.jurisdiction.pack")

PACKS_DIR = Path(__file__).resolve().parent / "packs"
GENERIC_CODE = "generic"

# Archivos que componen un pack. `meta` aporta los campos de cabecera; el resto son datos.
_DATA_FILES = ("holidays", "recess", "id_formats", "doc_markers", "term_catalog",
               "citation_style", "pii_hints", "mail_signals")


@dataclass(frozen=True)
class JurisdictionPack:
    """Datos de referencia de una jurisdicción. Inmutable; se carga una vez por código."""

    code: str
    name: str
    version: str
    verified: bool
    verified_at: str | None
    sources: list
    holidays: dict          # por año → lista de fechas ISO
    recess: list            # periodos de receso/feria judicial
    id_formats: dict        # nombre → {label, regex}
    doc_markers: dict       # tipo documental → lista de marcadores
    term_catalog: dict      # término → {label, days, kind}
    citation_style: dict
    is_generic: bool = False
    # Pistas de la heurística de SOSPECHA del anonimizador (prefijos de dirección, palabras
    # Capitalizadas genéricas del foro local). Vacío = solo la base pan-hispana del código.
    pii_hints: dict = field(default_factory=dict)
    # Señales del wake-gate de correo (léxico de urgencia + dominios institucionales).
    mail_signals: dict = field(default_factory=dict)
    # Opt-in EXPLÍCITO al corpus semilla de `rag/ingest_corpus.py` (viene de meta.json). Por
    # defecto False: un despacho de otra jurisdicción NO recibe corpus ajeno sembrado.
    baseline_corpus_seed: bool = False
    # Quick win §5.3 (docs/analisis-claude-for-legal.md): vigencia declarativa POR
    # ARCHIVO del pack (no solo el verified/verified_at global de meta.json) — un
    # festivo y un plazo procesal envejecen a velocidades muy distintas. Viene de
    # `meta.json → "freshness"` (aditivo; sin él, `{}` — ningún consumidor se rompe).
    # {archivo: {last_verified, freshness_window_days, freshness_category}}. Todavía
    # NO se conecta a ningún resolver/consumidor — es solo el dato disponible.
    freshness: dict = field(default_factory=dict)

    def data_is_provisional(self, file_key: str) -> bool:
        """¿Los datos del archivo `file_key` (p. ej. "holidays", "term_catalog") son
        PROVISIONALES y NO deben usarse como autoridad? True si el archivo se declaró a sí
        mismo `_complete: false`, o si el pack entero está sin verificar (`verified == false`).

        GUARDA DEFENSIVA (hallazgo de auditoría 2026-07-17). Hoy `holidays`/`term_catalog` del
        pack 'co' son PROVISIONALES (`_complete: false`, `verified: false`) y NO se consumen en
        cálculos de producción (solo tests; el resolver de plazos aún no está cableado a estos
        datos). Cuando un consumidor futuro los CABLEE a un cálculo con consecuencia procesal
        (festivos, términos), DEBE consultar esto ANTES y, si es True, marcar el resultado
        [VERIFICAR] o negarse a entregarlo — nunca presentar un plazo o un festivo provisional
        como firme. No completar aquí los datos: eso es trabajo de verificación contra la
        fuente oficial, no de inventiva."""
        data = getattr(self, file_key, None)
        if isinstance(data, dict) and data.get("_complete") is False:
            return True
        return not self.verified

    def holiday_dates(self, year: int) -> list[str]:
        """Fechas ISO de festivos del año dado (lista vacía si el pack no las trae).

        GUARDA (hallazgo de auditoría 2026-07-17): si los festivos son PROVISIONALES
        (`data_is_provisional('holidays')`) se emite un WARNING — el archivo está incompleto
        (p. ej. faltan los festivos trasladables a lunes y los de base pascual) y NO debe
        usarse para un cálculo de plazos con consecuencia procesal sin marcar [VERIFICAR].
        No se falla (para no romper a los consumidores actuales), pero queda el rastro."""
        if self.holidays and self.data_is_provisional("holidays"):
            logger.warning(
                "jurisdiction[%s]: festivos PROVISIONALES/sin verificar; el resultado debe "
                "marcarse [VERIFICAR] y no usarse como calendario firme de plazos", self.code)
        return list(self.holidays.get(str(year), []))

    def is_stale(self, file_key: str) -> bool | None:
        """¿El archivo `file_key` (p. ej. "term_catalog") superó su ventana de vigencia?

        `None` = no se puede evaluar (sin entrada de freshness, sin `last_verified`, o
        `freshness_window_days` es `None` = sin vencimiento declarado — p. ej. un dato
        casi estático como festivos históricos). Nunca lanza con datos mal formados
        (fail-soft: un pack mal editado no puede tumbar al consumidor)."""
        entry = self.freshness.get(file_key)
        if not isinstance(entry, dict):
            return None
        last_verified = entry.get("last_verified")
        window = entry.get("freshness_window_days")
        if not last_verified or window is None:
            return None
        try:
            verified_on = date.fromisoformat(str(last_verified))
            return (date.today() - verified_on).days > int(window)
        except (TypeError, ValueError):
            return None


def _read_json(path: Path):
    """Lee un archivo del pack. FAIL-SOFT: un archivo AUSENTE, ILEGIBLE o con JSON CORRUPTO se
    trata como vacío (`None`) y se registra — nunca revienta la carga del pack entero.

    Importa por seguridad: los consumidores fail-closed (el anonimizador, el wake-gate de correo)
    degradan a su base cuando un pack no aporta datos, pero solo si `load_pack` DEVUELVE. Si un
    `pii_hints.json` mal editado lanzara, se llevaría por delante los demás archivos VÁLIDOS del
    mismo pack (p. ej. los formatos de ID) y el despacho perdería cobertura por un typo."""
    if not path.is_file():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (ValueError, OSError, UnicodeDecodeError):
        logger.exception("jurisdiction: archivo de pack ilegible (%s); se trata como vacío y se "
                         "conserva el resto del pack", path)
        return None


def generic_pack() -> JurisdictionPack:
    """Modo genérico: sin conocimiento jurisdiccional. Permite operar en cualquier país
    de inmediato; el pack verificado es mejora progresiva (cuña de venta)."""
    return JurisdictionPack(
        code=GENERIC_CODE,
        name="Modo genérico",
        version="0",
        verified=False,
        verified_at=None,
        sources=[],
        holidays={},
        recess=[],
        # Formatos pan-hispanos: lo que es cierto en CUALQUIER jurisdicción hispanohablante.
        # `role` es DESCRIPTIVO: no desplaza ni suprime nada (ver la cabecera). `order` = lo más
        # específico primero, para que un patrón laxo no muerda los dígitos de uno preciso.
        id_formats={
            "url": {"label": "Dirección web", "marker": "URL", "role": "url", "order": 10,
                    "flags": "i",
                    "regex": r"\bhttps?://[^\s<>\"')]+|\bwww\.[^\s<>\"')]+"},
            "email": {"label": "Correo electrónico", "marker": "EMAIL", "role": "email",
                      "order": 20,
                      "regex": r"\b[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}\b"},
            # Documento de identidad por PALABRA CLAVE (pan-hispano: DNI/NIE/RUT/CURP/RFC/
            # cédula/pasaporte). Por palabra clave y no por forma: cada país numera distinto.
            "documento": {"label": "Documento de identidad", "marker": "DOCUMENTO",
                          "role": "document", "order": 55, "flags": "i",
                          "regex": (r"\b(?:c\.?\s?c\.?|c[eé]dula|documento\s+de\s+identidad|"
                                    r"identificaci[oó]n|D\.?N\.?I\.?|N\.?I\.?E\.?|R\.?U\.?T\.?|"
                                    r"C\.?U\.?R\.?P\.?|R\.?F\.?C\.?|pasaporte)\s*"
                                    r"(?:n[o°º]\.?\s*)?:?\s*[\dA-Z][\dA-Z.\-]{5,}\b")},
            "cuenta": {"label": "Cuenta bancaria", "marker": "CUENTA", "role": "account",
                       "order": 60, "flags": "i",
                       "regex": (r"\b(?:cuenta|cta)\.?\s*(?:de\s+ahorros|corriente|no\.?|"
                                 r"n[°º]\.?)?\s*:?\s*\d[\d\-]{6,}\d\b")},
            # Teléfono internacional: prefijo `+`, corrida pelada de 7-15 dígitos, o AGRUPADO
            # con separadores (`615 55 12 34` — la forma normal de escribirlo en España).
            # Espejo EXACTO de `security/anonymize._PHONE_FALLBACK_RE`: si tocas uno, toca el
            # otro. Allí están documentadas las guardas (fechas, 7-15 dígitos) y su razón.
            "phone": {"label": "Teléfono", "marker": "TELEFONO", "role": "phone", "order": 80,
                      "regex": (
                          r"\+\d[\d\s().-]{6,}\d"
                          r"|(?<!\d)\d{7,15}(?!\d)"
                          r"|(?<!\d)"
                          r"(?![0-3]?\d[\s.\-][01]?\d[\s.\-]\d{4}(?!\d))"
                          r"(?!(?:19|20)\d{2}[\s.\-][01]?\d[\s.\-][0-3]?\d(?!\d))"
                          r"(?=(?:\d[\s.\-]?){7,15}(?!\d))"
                          r"\d{2,4}(?:[\s.\-]\d{2,4}){1,4}(?!\d)"
                      )},
        },
        doc_markers={},
        term_catalog={},
        citation_style={},
        is_generic=True,
        # Pistas pan-hispanas de sospecha (solo marcan para revisión humana; no ocultan).
        pii_hints={
            "address_prefixes": ["Calle", "Cll", "Avenida", "Av", "Plaza", "Paseo",
                                 "Camino", "Autopista", "Carretera"],
            "stop_capitalized": [
                "constitución", "política", "ley", "corte", "suprema", "justicia", "consejo",
                "estado", "república", "código", "civil", "penal", "comercial", "laboral",
                "sala", "tribunal", "superior", "juzgado", "ministerio", "nación",
                "procuraduría", "fiscalía", "general", "nacional", "departamento",
                "municipio", "distrito", "sentencia", "auto", "decreto", "resolución",
                "artículo", "capítulo", "título", "libro", "administrativo", "contencioso",
                "procedimiento", "comercio", "sustantivo", "trabajo", "única", "único",
                "unificada",
            ],
        },
        # Sin dominios institucionales (son propios de cada país); léxico de urgencia
        # pan-hispano. El wake-gate del correo nunca queda mudo sin pack.
        mail_signals={
            "urgency_terms": [
                "urgente", "inmediat[oa]", "hoy", "prioridad", "importante", "vence",
                "vencimiento", "plazo", "t[eé]rmino", "traslado", "requerimiento",
                "notificaci[oó]n", "audiencia", "juzgado", "tribunal", "demanda", "recurso",
                "apelaci[oó]n", "embargo", "medida\\s+cautelar", "sanci[oó]n", "multa",
            ],
            "institutional_sender_domains": [],
        },
    )


def load_pack(code: str | None) -> JurisdictionPack:
    """Carga el pack `code` desde `packs/{code}/`. Si no existe o `code` es vacío/genérico,
    devuelve `generic_pack()`. Tolera archivos JSON faltantes (los trata como vacíos)."""
    code = (code or "").strip().lower()
    if not code or code == GENERIC_CODE:
        return generic_pack()
    pack_dir = PACKS_DIR / code
    if not pack_dir.is_dir():
        return generic_pack()

    meta = _read_json(pack_dir / "meta.json") or {}
    data = {name: _read_json(pack_dir / f"{name}.json") for name in _DATA_FILES}
    # fail-soft (revisión capa 2): un meta.json mal editado con "freshness" NO-dict
    # (lista/string) no debe tumbar is_stale() más adelante — se descarta, no se lanza.
    raw_freshness = meta.get("freshness")
    freshness = raw_freshness if isinstance(raw_freshness, dict) else {}

    return JurisdictionPack(
        code=code,
        name=meta.get("name", code),
        version=str(meta.get("version", "0")),
        verified=bool(meta.get("verified", False)),
        verified_at=meta.get("verified_at"),
        sources=meta.get("sources", []),
        holidays=data["holidays"] or {},
        recess=data["recess"] or [],
        id_formats=data["id_formats"] or {},
        doc_markers=data["doc_markers"] or {},
        term_catalog=data["term_catalog"] or {},
        citation_style=data["citation_style"] or {},
        freshness=freshness,
        pii_hints=data["pii_hints"] or {},
        mail_signals=data["mail_signals"] or {},
        baseline_corpus_seed=bool(meta.get("baseline_corpus_seed", False)),
    )


def list_packs() -> list[str]:
    """Códigos de los packs instalados (carpetas con `meta.json`). NO incluye el genérico."""
    if not PACKS_DIR.is_dir():
        return []
    return sorted(
        p.name for p in PACKS_DIR.iterdir()
        if p.is_dir() and (p / "meta.json").is_file()
    )
