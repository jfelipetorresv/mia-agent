"""Mia · connectors.notebooklm.gate — candado de confidencialidad de NotebookLM (CP-NLM).

NotebookLM es nube de Google. Cuando Mia le "consulta" un notebook, la PREGUNTA de Mia
(que puede llevar contexto del caso) VIAJA a Google. Hoy el muro de confidencialidad de
Mia es arquitectónico: todo el tráfico LLM sale por una sola puerta (`agent/llm.py`)
gobernada por la política de modelo del tenant. Una llamada a NotebookLM que NO pase por
un gate equivalente EVADIRÍA el muro — este módulo es ese gate, y es la única puerta por
la que puede salir una consulta a NotebookLM.

Regla (dos condiciones, ambas necesarias, ambas fail-closed):
  1. La política del tenant NO puede ser 'soberano'. 'soberano' = cero salida del equipo;
     ni con opt-in se consulta NotebookLM. Se lee con `model_policy_for_strict`, que LANZA
     si la DB falla (no cae al default) — un error de infraestructura JAMÁS abre la salida.
  2. El despacho debe haber dado el opt-in explícito `allow_notebooklm` (default False),
     igual que `allow_openrouter` / `allow_content_analysis`.

Ante CUALQUIER duda (error de DB, política indeterminada, opt-in ausente) → BLOQUEA.
"""
from __future__ import annotations

import logging

from ...agent import llm

logger = logging.getLogger("mia.connectors.notebooklm")

# Motivos de bloqueo (para traza/log; nunca jerga al abogado).
REASON_OK = "ok"
REASON_SOBERANO = "soberano"        # política sin salida a la nube
REASON_NO_OPTIN = "sin-opt-in"      # el despacho no autorizó consultar NotebookLM
REASON_ERROR = "error-gate"         # no se pudo determinar con certeza → fail-closed


async def query_allowed(tenant_id: str) -> tuple[bool, str]:
    """(permitido, motivo). True SOLO si la política ≠ 'soberano' Y el opt-in está activo.

    Fail-closed en todos los caminos: si `model_policy_for_strict` lanza (DB caída), se
    captura y se devuelve (False, REASON_ERROR) — nunca se asume que se puede salir a la
    nube por un fallo de infraestructura. El llamador debe tratar False como 'no consultar'
    y seguir el turno con el corpus local (degradación, no error)."""
    try:
        policy = await llm.model_policy_for_strict(tenant_id)
    except Exception:  # noqa: BLE001 — un error leyendo la política NO abre la salida
        logger.exception(
            "notebooklm.gate: no se pudo leer la política del tenant %s → BLOQUEA", tenant_id)
        return False, REASON_ERROR
    if policy == "soberano":
        return False, REASON_SOBERANO
    try:
        if not await llm.notebooklm_allowed_for(tenant_id):
            return False, REASON_NO_OPTIN
    except Exception:  # noqa: BLE001 — `notebooklm_allowed_for` ya es fail-closed, doble red
        logger.exception("notebooklm.gate: fallo leyendo el opt-in del tenant %s → BLOQUEA",
                         tenant_id)
        return False, REASON_ERROR
    return True, REASON_OK
