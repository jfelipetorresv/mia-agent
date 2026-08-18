"""Packs persistidos del turno jurídico (hechos / fuentes / tesis).

Porta la idea de Lexia (fact-pack / strategy-pack) SIN el corpus ni la vigencia
normativa. Un pack es un producto VERIFICADO: conteo declarado = real, cada hecho
lleva locator ``[doc n]``, cada tesis cita una fuente del pack. Si el preflight
falla, ``draft_node`` no llama al modelo.
"""
from __future__ import annotations

import hashlib
import json
import re
from typing import Any

from pydantic import BaseModel, Field, ValidationError, field_validator

_DOC_LOCATOR = re.compile(r"\[doc(?:umento)?s?\.?\s*(\d+)\]", re.IGNORECASE)
_PACK_FENCE = re.compile(
    r"===(FACT_PACK|SOURCE_PACK|STRATEGY_PACK)===\s*(\{.*?\})\s*===END===",
    re.DOTALL,
)


class PackError(ValueError):
    """El artefacto de la etapa no es un producto verificado."""


class Hecho(BaseModel):
    texto: str = Field(min_length=1)
    locator: str = Field(min_length=3)

    @field_validator("locator")
    @classmethod
    def _locator_doc(cls, value: str) -> str:
        if not _DOC_LOCATOR.search(value or ""):
            raise ValueError("cada hecho debe anclarse con [doc n]")
        return value.strip()


class FactPack(BaseModel):
    hechos: list[Hecho] = Field(min_length=1)
    conteo_declarado: int = Field(ge=1)


class Fuente(BaseModel):
    referencia: str = Field(min_length=1)
    chunk_hash: str = Field(min_length=16)
    tipo: str = ""
    titulo: str = ""


class SourcePack(BaseModel):
    fuentes: list[Fuente]
    conteo_declarado: int = Field(ge=0)


class Argumento(BaseModel):
    id: str = Field(min_length=1)
    tesis: str = Field(min_length=1)
    fuente_refs: list[str] = Field(min_length=1)
    seleccionado: bool = True
    contraparte: str = ""
    prueba: str = ""


class Descarte(BaseModel):
    tesis: str = Field(min_length=1)
    motivo: str = Field(min_length=1)


class StrategyPack(BaseModel):
    argumentos: list[Argumento] = Field(min_length=1)
    descartes: list[Descarte] = Field(default_factory=list)


def chunk_hash(text: str) -> str:
    return hashlib.sha256((text or "").encode("utf-8")).hexdigest()


def document_hash(doc: dict | str) -> str:
    if isinstance(doc, dict):
        raw = str(doc.get("content") or doc.get("id") or "")
    else:
        raw = str(doc or "")
    return chunk_hash(raw)


def _load_json_fence(text: str, kind: str) -> dict[str, Any] | None:
    blob = text or ""
    for match in _PACK_FENCE.finditer(blob):
        if match.group(1) == kind:
            try:
                parsed = json.loads(match.group(2))
            except (TypeError, ValueError, json.JSONDecodeError):
                raise PackError(f"el bloque {kind} no es JSON válido") from None
            if not isinstance(parsed, dict):
                raise PackError(f"el bloque {kind} debe ser un objeto JSON")
            return parsed
    # Fallback: último objeto JSON del texto (modelos que olvidan la valla).
    start = blob.rfind("{")
    end = blob.rfind("}")
    if start != -1 and end > start and kind.lower().replace("_", "") in blob.lower():
        try:
            parsed = json.loads(blob[start:end + 1])
        except (TypeError, ValueError, json.JSONDecodeError):
            return None
        return parsed if isinstance(parsed, dict) else None
    return None


def parse_fact_pack(prose: str, *, num_documents: int) -> FactPack:
    """Exige pack verificado. TypeError/JSON roto NO se tragan: levantan PackError."""
    raw = _load_json_fence(prose, "FACT_PACK")
    if raw is None:
        raw = _salvage_facts(prose)
    if not raw:
        raise PackError("la etapa de hechos no dejó un pack con locators [doc n]")
    try:
        pack = FactPack.model_validate(raw)
    except ValidationError as exc:
        raise PackError(f"pack de hechos inválido: {exc.errors()[0]['msg']}") from exc
    if pack.conteo_declarado != len(pack.hechos):
        raise PackError(
            f"conteo declarado ({pack.conteo_declarado}) ≠ hechos reales ({len(pack.hechos)})")
    max_n = max(1, int(num_documents or 0))
    for hecho in pack.hechos:
        nums = [int(n) for n in _DOC_LOCATOR.findall(hecho.locator)]
        if any(n < 1 or n > max_n for n in nums):
            raise PackError(f"locator fuera de rango: {hecho.locator}")
    return pack


def _salvage_facts(prose: str) -> dict[str, Any] | None:
    hechos: list[dict[str, str]] = []
    for line in (prose or "").splitlines():
        loc = _DOC_LOCATOR.search(line)
        texto = line.strip(" -*\t")
        if loc and len(texto) > 12:
            hechos.append({"texto": texto, "locator": loc.group(0)})
    if not hechos:
        return None
    return {"hechos": hechos, "conteo_declarado": len(hechos)}


def source_pack_from_research(sources: list[dict] | None) -> SourcePack:
    """El pack de fuentes sale de las fichas recuperadas, no de la prosa del LLM."""
    fuentes: list[Fuente] = []
    for src in sources or []:
        if not isinstance(src, dict):
            continue
        ref = str(src.get("referencia") or "").strip()
        if not ref:
            continue
        passage = str(src.get("pasaje") or src.get("texto") or src.get("content") or ref)
        digest = str(src.get("source_passage_hash") or "") or chunk_hash(passage)
        fuentes.append(Fuente(
            referencia=ref,
            chunk_hash=digest,
            tipo=str(src.get("tipo") or ""),
            titulo=str(src.get("titulo") or ""),
        ))
    return SourcePack(fuentes=fuentes, conteo_declarado=len(fuentes))


def parse_strategy_pack(prose: str, *, source_pack: SourcePack | None) -> StrategyPack:
    raw = _load_json_fence(prose, "STRATEGY_PACK")
    if raw is None:
        raise PackError("la etapa de análisis no dejó matriz de argumentos + descartes")
    try:
        pack = StrategyPack.model_validate(raw)
    except ValidationError as exc:
        raise PackError(f"pack de tesis inválido: {exc.errors()[0]['msg']}") from exc
    known = {f.referencia.lower() for f in (source_pack.fuentes if source_pack else [])}
    if known:
        for arg in pack.argumentos:
            if not any(ref.lower() in known or any(ref.lower() in k for k in known)
                       for ref in arg.fuente_refs):
                raise PackError(
                    f"la tesis «{arg.id}» no cita ninguna fuente del pack de investigación")
    return pack


def seleccionados(pack: StrategyPack | None, *, overrides: dict[str, bool] | None = None) -> list[Argumento]:
    chosen: list[Argumento] = []
    for arg in (pack.argumentos if pack else []):
        flag = (overrides or {}).get(arg.id, arg.seleccionado)
        if flag:
            chosen.append(arg)
    return chosen


def preflight_draft(*, fact_pack: FactPack | None, source_pack: SourcePack | None,
                    strategy_pack: StrategyPack | None,
                    selection: dict[str, bool] | None = None) -> None:
    """Aborto de redacción si falta un producto verificado aguas arriba."""
    if fact_pack is None:
        raise PackError("no hay pack de hechos verificado")
    if fact_pack.conteo_declarado != len(fact_pack.hechos):
        raise PackError("el pack de hechos no cierra: conteo declarado ≠ real")
    if source_pack is None:
        raise PackError("no hay pack de fuentes verificado")
    if source_pack.conteo_declarado != len(source_pack.fuentes):
        raise PackError("el pack de fuentes no cierra: conteo declarado ≠ real")
    if strategy_pack is None:
        raise PackError("no hay matriz de argumentos verificada")
    chosen = seleccionados(strategy_pack, overrides=selection)
    if not chosen:
        raise PackError("no quedó ningún argumento seleccionado para redactar")
    known = {f.referencia.lower() for f in source_pack.fuentes}
    if known:
        for arg in chosen:
            if not any(ref.lower() in known or any(ref.lower() in k for k in known)
                       for ref in arg.fuente_refs):
                raise PackError(
                    f"la tesis seleccionada «{arg.id}» no cita una fuente del pack")


def compact_source_pack(pack: SourcePack | None) -> list[dict[str, str]]:
    """Lo que ve el gate LLM: referencia + hash, sin prosa de análisis ni draft."""
    if pack is None:
        return []
    return [{"referencia": f.referencia, "chunk_hash": f.chunk_hash, "tipo": f.tipo}
            for f in pack.fuentes]


FACT_PACK_INSTRUCTION = (
    "Cierra SIEMPRE con este bloque, JSON estricto, sin markdown:\n"
    "===FACT_PACK===\n"
    '{"hechos": [{"texto": "...", "locator": "[doc 1]"}], "conteo_declarado": 1}\n'
    "===END===\n"
    "conteo_declarado DEBE igualar el número de hechos. Cada hecho lleva [doc n]."
)

STRATEGY_PACK_INSTRUCTION = (
    "Cierra SIEMPRE, ANTES del bloque === de diagnóstico, con este JSON:\n"
    "===STRATEGY_PACK===\n"
    '{"argumentos": [{"id": "A1", "tesis": "...", "fuente_refs": ["Ley 1"], '
    '"seleccionado": true, "contraparte": "...", "prueba": "[doc 1]"}], '
    '"descartes": [{"tesis": "...", "motivo": "..."}]}\n'
    "===END===\n"
    "Toda tesis seleccionada cita una referencia del pack de investigación. "
    "Los descartes son argumentos considerados y rechazados, cada uno con motivo."
)


def example_metadata_packs() -> dict[str, object]:
    """Packs mínimos válidos para tests de nodos posteriores (p. ej. recorte de draft)."""
    digest = "a" * 64
    facts = FactPack(
        hechos=[Hecho(texto="El accidente ocurrió el 14 de marzo.", locator="[doc 1]")],
        conteo_declarado=1)
    sources = SourcePack(
        fuentes=[Fuente(referencia="Ley 1", chunk_hash=digest, tipo="norma")],
        conteo_declarado=1)
    strategy = StrategyPack(
        argumentos=[Argumento(id="A1", tesis="Hay caducidad.", fuente_refs=["Ley 1"],
                              seleccionado=True, prueba="[doc 1]")],
        descartes=[Descarte(tesis="Culpa exclusiva", motivo="El expediente no la acredita.")])
    return {
        "facts_pack": facts.model_dump(), "facts_pack_ok": True,
        "source_pack": sources.model_dump(), "source_pack_ok": True,
        "strategy_pack": strategy.model_dump(), "strategy_pack_ok": True,
    }
