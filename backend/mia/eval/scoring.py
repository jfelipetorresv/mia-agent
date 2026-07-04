"""Mia · eval.scoring — señales OBJETIVAS de calidad de un turno (CP-E4).

Todo determinista, SIN LLM-juez (anti-invención por construcción, imprescindible en lo
legal): un LLM que puntúa a otro LLM introduce ruido y costo, y podría "premiar" un borrador
seguro-pero-vacío. Estas señales miden DISCIPLINA verificable, no exactitud sustantiva:

  · disciplina de citas (la más importante): del verificador determinista de CP9
    (`agents.verification`) — cuántas citas, cuántas SIN respaldo ni marca [VERIFICAR]
    (`anotadas`). Un borrador con citas sin respaldo es peor: obliga al abogado a rastrearlas.
  · estructura: ¿el diagnóstico trae el bloque de cierre problema/normas/riesgo
    (`prompt_builder.parse_diagnosis_closing`)? ¿el turno llegó a producir borrador?
  · forma: longitud del borrador (un borrador vacío o minúsculo es una señal de fallo).
  · costo/latencia: tokens y ms del turno (de la metadata del grafo).

`score_turn` es una función PURA sobre el resultado del turno: no toca DB, red ni reloj.
"""
from __future__ import annotations

from typing import Any

from ..agent import prompt_builder
from ..agents import verification
from ..memory.tokens import estimate_tokens

# Umbral mínimo de caracteres para considerar que hubo un borrador "real" (por debajo es
# un fallo de redacción, no un borrador). Conservador: un borrador jurídico serio supera
# de sobra este piso; sirve para atrapar vacíos/errores, no para calificar extensión.
MIN_DRAFT_CHARS = 200

# Banderas de calidad (problemas objetivos detectados en el turno).
FLAG_NO_DRAFT = "sin_borrador"
FLAG_TINY_DRAFT = "borrador_minusculo"
FLAG_UNSUPPORTED_CITATIONS = "citas_sin_respaldo"
FLAG_NO_DIAGNOSIS_CLOSING = "sin_cierre_diagnostico"


def _citation_signal(draft: str, sources: Any, extra_patterns: Any,
                     verification_report: Any = None) -> dict:
    """Disciplina de citas del borrador, vía el verificador determinista de CP9.

    Si el turno trae su `verification_report` (informe del grafo, calculado sobre el borrador
    ANTES de anotarlo), se usa TAL CUAL: es lo correcto, porque para cuando el turno llega al
    HITL el borrador YA fue anotado por el nodo de verificación (las citas sin marca recibieron
    su [VERIFICAR]) — re-escanear ese borrador anotado contaría 0 sin respaldo y borraría la
    señal. Sin informe (pruebas sobre un borrador crudo), se ESCANEA el borrador aquí.
    `anotadas` = citas sin marca [VERIFICAR] ni respaldo en el corpus = las riesgosas."""
    if isinstance(verification_report, dict) and "citas" in verification_report:
        report = verification_report
    else:
        src = sources if isinstance(sources, list) else None
        extra = extra_patterns if isinstance(extra_patterns, list) else None
        _annotated, report = verification.annotate_draft(
            draft or "", sources=src, extra_patterns=extra)
    citas = int(report.get("citas", 0))
    anotadas = int(report.get("anotadas", 0))
    respaldadas = int(report.get("respaldadas", 0))
    marcadas = int(report.get("marcadas", 0))
    return {
        "citas": citas,
        "citas_sin_respaldo": anotadas,       # las riesgosas (ni marca ni respaldo)
        "citas_respaldadas": respaldadas,
        "citas_marcadas": marcadas,
        # fracción de citas "en regla" (marcadas o respaldadas) sobre el total; 1.0 sin citas.
        "citas_en_regla_ratio": round((citas - anotadas) / citas, 4) if citas else 1.0,
    }


def score_turn(
    draft: str,
    diagnosis: str,
    metadata: dict | None = None,
    *,
    sources: Any = None,
    extra_patterns: Any = None,
    verification_report: Any = None,
) -> dict:
    """Señales objetivas de calidad de un turno. Pura y determinista.

    `draft` = borrador final del turno; `diagnosis` = diagnóstico (para el bloque de cierre);
    `metadata` = metadata del grafo (tokens/latencia/etapas); `sources` = fuentes recuperadas
    del corpus en el turno (para el respaldo de citas — las mismas que usó el grafo);
    `verification_report` = informe del verificador del grafo (preferido; ver `_citation_signal`).
    """
    md = metadata or {}
    draft = draft or ""
    draft_chars = len(draft)
    reached_draft = draft_chars > 0
    tiny_draft = 0 < draft_chars < MIN_DRAFT_CHARS

    cites = _citation_signal(draft, sources, extra_patterns, verification_report)
    has_closing = prompt_builder.parse_diagnosis_closing(diagnosis or "") is not None

    flags: list[str] = []
    if not reached_draft:
        flags.append(FLAG_NO_DRAFT)
    elif tiny_draft:
        flags.append(FLAG_TINY_DRAFT)
    if cites["citas_sin_respaldo"] > 0:
        flags.append(FLAG_UNSUPPORTED_CITATIONS)
    if not has_closing:
        flags.append(FLAG_NO_DIAGNOSIS_CLOSING)

    usage = md.get("usage") if isinstance(md.get("usage"), dict) else {}
    return {
        # forma / completitud
        "reached_draft": reached_draft,
        "draft_chars": draft_chars,
        "draft_tokens": estimate_tokens(draft),
        "has_diagnosis_closing": has_closing,
        "stage": str(md.get("stage") or ""),
        # disciplina de citas (lo central)
        **cites,
        # costo / latencia (informativo, no penaliza calidad por sí solo)
        "total_tokens": int(usage.get("total", 0) or 0),
        "latency_ms": round(float(md.get("latency_ms", 0.0) or 0.0), 1),
        # resumen de problemas objetivos detectados
        "flags": flags,
        "ok": len(flags) == 0,
    }
