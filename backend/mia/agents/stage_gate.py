"""Fail-closed de etapas: un nodo caro no corre sobre un artefacto inválido.

Contrato: etapa cierra = producto verificado (pack), no «el LLM respondió».
Un TypeError o un JSON roto NO se tragan: la etapa queda incompleta y el
borrador no se redacta.
"""
from __future__ import annotations

from typing import Any

from . import packs


class StageIncomplete(Exception):
    """La etapa aguas arriba no dejó un producto verificado."""

    def __init__(self, stage: str, detail: str) -> None:
        self.stage = stage
        self.detail = detail
        super().__init__(detail)


def lawyer_abort(stage: str, detail: str) -> str:
    """Texto en llano para el abogado: el turno se detiene, no se finge un borrador."""
    labels = {
        "facts": "hechos",
        "research": "investigación",
        "analysis": "análisis",
        "packs": "los packs del turno",
    }
    nombre = labels.get(stage, stage)
    return (
        f"No pude seguir con el escrito: la etapa de {nombre} no dejó un producto "
        f"verificado. {detail} Revisa el expediente o vuelve a lanzar el turno."
    )


def facts_ok(md: dict[str, Any] | None) -> bool:
    return bool((md or {}).get("facts_pack_ok")) and isinstance((md or {}).get("facts_pack"), dict)


def research_ok(md: dict[str, Any] | None) -> bool:
    return bool((md or {}).get("source_pack_ok")) and isinstance((md or {}).get("source_pack"), dict)


def analysis_ok(md: dict[str, Any] | None) -> bool:
    return bool((md or {}).get("strategy_pack_ok")) and isinstance((md or {}).get("strategy_pack"), dict)


def load_fact_pack(md: dict[str, Any] | None) -> packs.FactPack | None:
    raw = (md or {}).get("facts_pack")
    if not isinstance(raw, dict):
        return None
    try:
        return packs.FactPack.model_validate(raw)
    except (TypeError, ValueError):
        return None


def load_source_pack(md: dict[str, Any] | None) -> packs.SourcePack | None:
    raw = (md or {}).get("source_pack")
    if not isinstance(raw, dict):
        return None
    try:
        return packs.SourcePack.model_validate(raw)
    except (TypeError, ValueError):
        return None


def load_strategy_pack(md: dict[str, Any] | None) -> packs.StrategyPack | None:
    raw = (md or {}).get("strategy_pack")
    if not isinstance(raw, dict):
        return None
    try:
        return packs.StrategyPack.model_validate(raw)
    except (TypeError, ValueError):
        return None


def require_upstream_for_draft(md: dict[str, Any] | None) -> None:
    """Levanta StageIncomplete si facts/research/analysis no cerraron con pack."""
    if not facts_ok(md):
        raise StageIncomplete("facts", str((md or {}).get("facts_pack_error")
                                           or "faltó el pack de hechos."))
    if not research_ok(md):
        raise StageIncomplete("research", str((md or {}).get("source_pack_error")
                                             or "faltó el pack de fuentes."))
    if not analysis_ok(md):
        raise StageIncomplete("analysis", str((md or {}).get("strategy_pack_error")
                                             or "faltó la matriz de argumentos."))
    try:
        packs.preflight_draft(
            fact_pack=load_fact_pack(md),
            source_pack=load_source_pack(md),
            strategy_pack=load_strategy_pack(md),
            selection=(md or {}).get("argument_selection") if isinstance(
                (md or {}).get("argument_selection"), dict) else None,
        )
    except packs.PackError as exc:
        raise StageIncomplete("packs", str(exc)) from exc
