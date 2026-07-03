"""Mia · metrics.value — horas ahorradas ESTIMADAS a partir de las trazas (CP-V1, Ola 4).

Función pura y testeable (gate test_value_delivered.py) que clasifica las trazas
JSONL del despacho para la tarjeta "Valor entregado este mes". Reglas (capa 2 de
CP-V1, hallazgo A1 — sin esto el panel sobre-reportaba):

  - Solo trazas de TURNOS (schema mia.trace.v1/v2). Los EVENTOS técnicos
    (mia.trace.event.*: compresión de contexto, etc.) NO son trabajo del abogado.
  - Solo el mes pedido (prefijo YYYY-MM del timestamp UTC de la traza) — también
    para los tokens del fallback legacy (hallazgo M1: antes sumaba TODA la historia).
  - Un turno RECHAZADO no ahorró tiempo (conservador): no cuenta.
  - "Borrador" = el texto final es un ESCRITO sustancial (≥ DRAFT_MIN_CHARS).
    `hitl_outcome` no sirve para distinguirlo: el grafo lo escribe en TODOS los
    turnos (una pregunta aprobada también trae 'approved'). La longitud es una
    heurística declarada y conservadora; lo demás cuenta como consulta.

LIMITACIÓN CONOCIDA (hallazgo M3, declarada): el costo de IA del panel no incluye
los EMBEDDINGS (voyage-law-2 no pasa por call_llm) — subreporta algo el costo,
nunca lo infla. Anotado en bugs-and-risks.
"""
from __future__ import annotations

from typing import Iterable

# Un escrito jurídico real (contestación, memorial) supera con holgura este umbral;
# una respuesta de consulta rara vez lo alcanza. Heurística declarada de v1.
DRAFT_MIN_CHARS = 3000

_TURN_SCHEMAS_PREFIX = "mia.trace.v"   # v1/v2 = turnos; mia.trace.event.* = eventos


def summarize_traces(traces: Iterable[dict], month_prefix: str,
                     draft_min_chars: int = DRAFT_MIN_CHARS) -> dict:
    """Clasifica las trazas del mes: borradores vs consultas + tokens legacy del mes.

    `month_prefix` es "YYYY-MM" en UTC (los timestamps de TraceCapture son ISO UTC).
    Devuelve {"drafts": int, "turns": int, "legacy_tokens_month": int}.
    """
    drafts = 0
    turns = 0
    legacy_tokens_month = 0
    for t in traces:
        if not isinstance(t, dict):
            continue
        if not str(t.get("timestamp") or "").startswith(month_prefix):
            continue
        # Los TOKENS del mes cuentan para el costo legacy vengan de donde vengan
        # (un evento de compresión también gastó tokens); las HORAS no.
        tok = t.get("tokens")
        if isinstance(tok, dict):
            legacy_tokens_month += int(tok.get("total") or 0)
        elif isinstance(tok, (int, float)):
            legacy_tokens_month += int(tok)
        schema = str(t.get("schema") or _TURN_SCHEMAS_PREFIX)  # trazas viejas sin schema = turno
        if not schema.startswith(_TURN_SCHEMAS_PREFIX):
            continue
        if t.get("hitl_outcome") == "rejected":
            continue
        text = str(t.get("draft_final") or t.get("output") or "")
        if len(text) >= draft_min_chars:
            drafts += 1
        else:
            turns += 1
    return {"drafts": drafts, "turns": turns, "legacy_tokens_month": legacy_tokens_month}
