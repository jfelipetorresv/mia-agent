"""Mia · mcp.gate — candado de confidencialidad para CONSULTAR servidores MCP (CP-E6b).

Hermano exacto de ``gateway.hub_gate.delegation_allowed`` / ``connectors.notebooklm.gate.
query_allowed``: mismo criterio, mismo orden, fail-closed ante cualquier duda. Un servidor
MCP es un subproceso de terceros — cuando Mia lo consulta, la PREGUNTA (que puede llevar
contexto del caso) sale del proceso de Mia hacia ese subproceso. Sin este gate, `mcp.turn`
evadiría el muro de confidencialidad exactamente igual que un CLI del Hub sin `hub_gate`.

Regla (una sola condición aquí — ver por qué no hay una segunda más abajo):
  La política del despacho NO puede ser 'soberano'. 'soberano' = "todo en mi equipo", cero
  salida — ni siquiera a un servidor MCP local (muchos hablan con la nube por su cuenta, y
  los que no, igual son un binario de terceros fuera del gateway). Se lee con
  `model_policy_for_strict`, que LANZA si la DB falla (no cae al default de la instalación)
  — un error de infraestructura JAMÁS abre la salida.

POR QUÉ NO HAY UN SEGUNDO INTERRUPTOR DE OPT-IN AQUÍ:
El opt-in por servidor YA existe y es más granular que un toggle genérico: el flag
`enabled` de cada entrada en `tenant_settings.config['mcp']['servers'][slug]`
(`mcp.service.enable_server`, acto explícito del despacho con sus credenciales). Repetirlo
aquí sería una casilla redundante sobre otra casilla. Este gate decide SI el despacho puede
consultar servidores MCP en absoluto (según su política); `mcp.turn.enabled_resolved_servers`
decide CUÁLES, filtrando por ese `enabled` de catálogo — dos preguntas distintas, cada una
en su capa, igual que hub_gate separa política de catálogo del Hub.

Ante CUALQUIER duda (error de DB, política indeterminada) → BLOQUEA.
"""
from __future__ import annotations

import logging

from ..agent import llm

logger = logging.getLogger("mia.mcp.gate")

# Motivos de bloqueo (para traza/log; nunca jerga al abogado — §G).
REASON_OK = "ok"
REASON_SOBERANO = "soberano"        # política sin salida del equipo
REASON_ERROR = "error-gate"         # no se pudo determinar con certeza → fail-closed


async def mcp_allowed(tenant_id: str) -> tuple[bool, str]:
    """(permitido, motivo). True SOLO si la política del despacho ≠ 'soberano'.

    Fail-closed en todos los caminos: si `model_policy_for_strict` lanza (DB caída), se
    captura y se devuelve (False, REASON_ERROR) — nunca se asume que se puede consultar un
    servidor MCP por un fallo de infraestructura. El llamador (`mcp.turn`) debe tratar False
    como 'no consultar' y seguir el turno con el corpus local (degradación, no error)."""
    try:
        policy = await llm.model_policy_for_strict(tenant_id)
    except Exception:  # noqa: BLE001 — un error leyendo la política NO abre la salida
        logger.exception(
            "mcp.gate: no se pudo leer la política del tenant %s → BLOQUEA", tenant_id)
        return False, REASON_ERROR
    if policy == "soberano":
        logger.info("mcp.gate: consulta MCP BLOQUEADA por política soberana (tenant=%s)",
                    tenant_id)
        return False, REASON_SOBERANO
    return True, REASON_OK
