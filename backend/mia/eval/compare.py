"""Mia · eval.compare — comparar dos corridas del banco de pruebas (CP-E4).

El valor del harness: correr los MISMOS casos de oro ANTES y DESPUÉS de un cambio y decir en
lenguaje llano si la calidad MEJORÓ, se mantuvo o EMPEORÓ — para que Pipe decida con datos,
no con el diff. Todo determinista.

Criterios de REGRESIÓN (duros — bajan la calidad jurídica verificable):
  · aparecen citas sin respaldo que antes no estaban (o aumentan);
  · el diagnóstico pierde su bloque de cierre estructurado;
  · un caso que antes llegaba a borrador ahora no;
  · el borrador se encoge drásticamente (< mitad) — señal de contenido perdido.
Criterios de MEJORA: los inversos (menos citas sin respaldo, gana cierre/borrador).
"""
from __future__ import annotations

# Fracción por debajo de la cual un borrador que se encoge cuenta como posible pérdida.
DRAFT_SHRINK_REGRESSION_FRACTION = 0.5


def _index_by_case(report: dict) -> dict[str, dict]:
    out: dict[str, dict] = {}
    for c in report.get("cases", []) or []:
        cid = c.get("case_id")
        if cid:
            out[cid] = c
    return out


def _compare_case(before: dict, after: dict) -> dict:
    """Delta y veredicto de UN caso presente en ambas corridas."""
    b = before.get("score", {}) or {}
    a = after.get("score", {}) or {}
    regressions: list[str] = []
    improvements: list[str] = []

    b_unsup = int(b.get("citas_sin_respaldo", 0) or 0)
    a_unsup = int(a.get("citas_sin_respaldo", 0) or 0)
    if a_unsup > b_unsup:
        regressions.append("aumentaron las citas sin respaldo")
    elif a_unsup < b_unsup:
        improvements.append("bajaron las citas sin respaldo")

    if b.get("has_diagnosis_closing") and not a.get("has_diagnosis_closing"):
        regressions.append("se perdió el cierre estructurado del diagnóstico")
    elif not b.get("has_diagnosis_closing") and a.get("has_diagnosis_closing"):
        improvements.append("se ganó el cierre estructurado del diagnóstico")

    if b.get("reached_draft") and not a.get("reached_draft"):
        regressions.append("dejó de producir borrador")
    elif not b.get("reached_draft") and a.get("reached_draft"):
        improvements.append("ahora produce borrador")

    b_chars = int(b.get("draft_chars", 0) or 0)
    a_chars = int(a.get("draft_chars", 0) or 0)
    if b_chars > 0 and a_chars < b_chars * DRAFT_SHRINK_REGRESSION_FRACTION:
        regressions.append("el borrador se encogió a menos de la mitad")

    if regressions:
        verdict = "regresion"
    elif improvements:
        verdict = "mejora"
    else:
        verdict = "sin_cambio"

    return {
        "case_id": after.get("case_id"),
        "verdict": verdict,
        "regressions": regressions,
        "improvements": improvements,
        "deltas": {
            "citas_sin_respaldo": a_unsup - b_unsup,
            "draft_chars": a_chars - b_chars,
            "total_tokens": int(a.get("total_tokens", 0) or 0) - int(b.get("total_tokens", 0) or 0),
        },
    }


def compare_reports(before: dict, after: dict) -> dict:
    """Compara dos corridas (dicts de `harness.build_report`). Devuelve el veredicto por
    caso + un veredicto AGREGADO. Casos que solo están en una corrida se listan aparte
    (no se comparan). Determinista y puro."""
    b_idx = _index_by_case(before)
    a_idx = _index_by_case(after)
    common = [cid for cid in a_idx if cid in b_idx]
    only_before = sorted(cid for cid in b_idx if cid not in a_idx)
    only_after = sorted(cid for cid in a_idx if cid not in b_idx)

    per_case = [_compare_case(b_idx[cid], a_idx[cid]) for cid in sorted(common)]
    n_reg = sum(1 for c in per_case if c["verdict"] == "regresion")
    n_imp = sum(1 for c in per_case if c["verdict"] == "mejora")

    # Veredicto agregado: una sola regresión manda (fail-safe: no declarar "mejora" si algo
    # empeoró). Sin regresiones y con al menos una mejora → mejora; si no, sin cambio.
    if n_reg > 0:
        overall = "regresion"
    elif n_imp > 0:
        overall = "mejora"
    else:
        overall = "sin_cambio"

    return {
        "overall": overall,
        "n_regresiones": n_reg,
        "n_mejoras": n_imp,
        "n_sin_cambio": len(per_case) - n_reg - n_imp,
        "cases": per_case,
        "only_before": only_before,
        "only_after": only_after,
    }
