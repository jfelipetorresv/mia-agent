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

import re
from typing import Any, Callable, Optional

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


# ── Calificación SUSTANTIVA (Banco de oro, Fase 1) ────────────────────────────
# score_turn (arriba) mide DISCIPLINA y es PURO. substantive_score mide si la respuesta nueva
# CUBRE las claves que el abogado confirmó (rúbrica). El DETERMINISTA manda pasa/no-pasa; el
# juez LLM es solo ADVISORY (callback opcional, efecto de red fuera de la ruta pura).

FLAG_MISSING_KEY_CITATION = "falta_cita_clave"
FLAG_MISSING_KEY_CONCLUSION = "falta_conclusion_clave"

# Fracción de palabras significativas de una conclusión clave que deben aparecer para darla por
# cubierta (match por conjunto de términos, no exacto: tolera reformulaciones del modelo).
CONCLUSION_KEYWORD_THRESHOLD = 0.7

# Palabras vacías (no aportan a la cobertura de una conclusión): conectores/artículos comunes.
_STOPWORDS = frozenset((
    "de", "la", "el", "los", "las", "un", "una", "unos", "unas", "y", "o", "u", "e", "en",
    "con", "sin", "por", "para", "del", "al", "se", "su", "sus", "que", "como", "es", "son",
    "lo", "le", "les", "ha", "han", "no", "si", "mas", "pero", "the", "a", "ante", "sobre",
))


def _normalize_cita(text: str) -> str:
    """Normaliza una cita para comparar (minúsculas, sin tildes, sin puntuación) y unifica la
    abreviatura 'art.' con 'artículo' — así 'art. 90' casa con 'artículo 90'."""
    s = verification._normalize(text)          # minúsculas · sin tildes · separadores colapsados
    return re.sub(r"\bart\b", "articulo", s)


def _cita_cubierta(cita_clave: str, halladas_norm: list[str]) -> bool:
    """La cita clave está cubierta si casa (inclusión normalizada, en ambos sentidos) con alguna
    de las citas que el escáner detectó en la respuesta nueva."""
    kn = _normalize_cita(cita_clave)
    if not kn:
        return False
    return any(kn in hn or hn in kn for hn in halladas_norm if hn)


def _keywords(text: str) -> list[str]:
    """Palabras significativas de una conclusión (normalizadas, sin stopwords ni de ≤2 letras)."""
    toks = _normalize_cita(text).split()
    return [t for t in toks if len(t) > 2 and t not in _STOPWORDS]


def _conclusion_cubierta(conclusion_clave: str, texto_norm: str) -> bool:
    """La conclusión clave está cubierta si ≥ umbral de sus palabras significativas aparecen en
    la respuesta nueva (diagnóstico + borrador). Conjunto de términos, no coincidencia literal."""
    kws = _keywords(conclusion_clave)
    if not kws:
        return False
    presentes = sum(1 for w in set(kws) if w in texto_norm)
    return (presentes / len(set(kws))) >= CONCLUSION_KEYWORD_THRESHOLD


def substantive_score(
    draft: str,
    diagnosis: str,
    rubric: Optional[dict],
    *,
    judge: Optional[Callable[[str, str, dict], dict]] = None,
) -> dict:
    """Calificación SUSTANTIVA de una respuesta nueva contra la rúbrica confirmada.

    (a) DETERMINISTA — AUTORITATIVO: cobertura de `citas_clave` (match robusto vía scan_citations)
        y de `conclusiones_clave` (umbral de keywords). `ok = len(flags) == 0`.
    (b) JUEZ LLM — ADVISORY (opcional): `judge(draft, diagnosis, rubric)` debe devolver
        {"veredicto": "solido|debilitado", "explicacion_llana": str}. NUNCA bloquea solo: solo
        adjunta señal. Se pasa como CALLBACK (efecto de red) para mantener esta función pura por
        defecto (judge=None → sin red, determinista, testeable). El juez ve SOLO texto anonimizado.
    """
    rubric = rubric or {}
    citas_clave = [str(c) for c in (rubric.get("citas_clave") or []) if str(c).strip()]
    conclusiones_clave = [str(c) for c in (rubric.get("conclusiones_clave") or []) if str(c).strip()]

    # (a) Determinista.
    halladas = verification.scan_citations(draft or "")
    halladas_norm = [_normalize_cita(h["citation"]) for h in halladas]
    citas_cubiertas = [c for c in citas_clave if _cita_cubierta(c, halladas_norm)]
    citas_faltantes = [c for c in citas_clave if c not in citas_cubiertas]

    texto_norm = _normalize_cita((diagnosis or "") + " \n " + (draft or ""))
    concl_cubiertas = [c for c in conclusiones_clave if _conclusion_cubierta(c, texto_norm)]
    concl_faltantes = [c for c in conclusiones_clave if c not in concl_cubiertas]

    flags: list[str] = []
    if citas_faltantes:
        flags.append(FLAG_MISSING_KEY_CITATION)
    if concl_faltantes:
        flags.append(FLAG_MISSING_KEY_CONCLUSION)

    result = {
        "cobertura_citas": round(len(citas_cubiertas) / len(citas_clave), 4) if citas_clave else 1.0,
        "cobertura_conclusiones": (round(len(concl_cubiertas) / len(conclusiones_clave), 4)
                                   if conclusiones_clave else 1.0),
        "citas_cubiertas": citas_cubiertas,
        "citas_faltantes": citas_faltantes,
        "conclusiones_cubiertas": concl_cubiertas,
        "conclusiones_faltantes": concl_faltantes,
        "faltantes": citas_faltantes + concl_faltantes,
        "n_faltantes_clave": len(citas_faltantes) + len(concl_faltantes),
        "flags": flags,
        "ok": len(flags) == 0,
        "judge": None,
        "judge_flags": [],
    }

    # (b) Juez advisory — nunca bloquea; cualquier fallo de red NO tumba la calificación dura.
    if judge is not None:
        try:
            veredicto = judge(draft or "", diagnosis or "", rubric)
            if isinstance(veredicto, dict):
                result["judge"] = {
                    "veredicto": str(veredicto.get("veredicto") or ""),
                    "explicacion_llana": str(veredicto.get("explicacion_llana") or ""),
                }
                if result["judge"]["veredicto"] == "debilitado":
                    result["judge_flags"] = ["juez_señala_debilitado"]
        except Exception:  # noqa: BLE001 — el juez es advisory: su fallo no altera pasa/no-pasa
            result["judge"] = {"veredicto": "", "explicacion_llana": "El juez no pudo opinar."}

    return result
