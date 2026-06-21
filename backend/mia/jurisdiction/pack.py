"""Mia · jurisdiction.pack — carga de paquetes de jurisdicción (Decisión #24).

Un `JurisdictionPack` agrupa los DATOS de referencia de una jurisdicción. Se compone de
archivos JSON opcionales bajo `packs/{code}/`:

  meta.json          {code, name, version, verified, verified_at, sources[]}
  holidays.json      {"2025": ["2025-01-01", ...], ...}
  recess.json        [{"name", "start": "MM-DD", "end": "MM-DD"}]   (feria/vacancia judicial)
  id_formats.json    {"cedula": {"label", "regex"}, ...}            (consumido por PII redactor)
  doc_markers.json   {"norm": [...], "contract": [...], "ruling": [...]}  (LegalChunker)
  term_catalog.json  {"<termino>": {"label", "days", "kind": "habil|calendario"}}
  citation_style.json

`load_pack(code)` tolera archivos faltantes (los trata como vacíos). Un `code` sin
carpeta → `GenericPack` (modo genérico): sin festivos, sin marcadores, formatos de ID
genéricos. NADA en el código conoce una jurisdicción concreta: el conocimiento vive en
los datos.

Cardinal: un pack con `verified=false` NO debe presentarse como autoridad verificada.
Los consumidores (calendario, investigación) deben marcar supuestos no verificados.
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

PACKS_DIR = Path(__file__).resolve().parent / "packs"
GENERIC_CODE = "generic"

# Archivos que componen un pack. `meta` aporta los campos de cabecera; el resto son datos.
_DATA_FILES = ("holidays", "recess", "id_formats", "doc_markers", "term_catalog", "citation_style")


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

    def holiday_dates(self, year: int) -> list[str]:
        """Fechas ISO de festivos del año dado (lista vacía si el pack no las trae)."""
        return list(self.holidays.get(str(year), []))


def _read_json(path: Path):
    if path.is_file():
        return json.loads(path.read_text(encoding="utf-8"))
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
        id_formats={
            "email": {"label": "Correo electrónico", "regex": r"[\w.+-]+@[\w-]+\.[\w.-]+"},
            "phone": {"label": "Teléfono", "regex": r"\+?\d[\d\s().-]{6,}\d"},
        },
        doc_markers={},
        term_catalog={},
        citation_style={},
        is_generic=True,
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
    )


def list_packs() -> list[str]:
    """Códigos de los packs instalados (carpetas con `meta.json`). NO incluye el genérico."""
    if not PACKS_DIR.is_dir():
        return []
    return sorted(
        p.name for p in PACKS_DIR.iterdir()
        if p.is_dir() and (p / "meta.json").is_file()
    )
