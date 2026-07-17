"""Mia · gateway.hub_gate — candado de confidencialidad del Agent Hub (CP-HUB).

Un "ayudante externo" del Hub es un BINARIO DE TERCEROS. Cuando Mia le delega algo, el
PROMPT (el mensaje que escribió el abogado, que puede llevar datos del expediente) SALE
del proceso de Mia hacia ese binario, y ese binario casi siempre habla con la nube por su
cuenta — con SUS credenciales y SU política, fuera del muro de Mia.

El muro de confidencialidad de Mia es arquitectónico: todo el tráfico LLM sale por una
sola puerta (`agent/llm.py`) gobernada por la política de modelo del despacho. Un
subprocess del Hub NO pasa por esa puerta: la EVADIRÍA por completo. Este módulo es el
gate equivalente, y es la ÚNICA puerta por la que puede salir una delegación — hermano
exacto de `connectors/notebooklm/gate.py::query_allowed`, mismo criterio y mismo orden.

Regla (dos condiciones, ambas necesarias, ambas fail-closed):
  1. La política del despacho NO puede ser 'soberano'. 'soberano' = "todo en mi equipo",
     cero salida. NI SIQUIERA con el ayudante habilitado se delega: el toggle del Hub no
     es una excepción a la política, es una opción DENTRO de ella. Se lee con
     `model_policy_for_strict`, que LANZA si la DB falla (no cae al default de la
     instalación) — un error de infraestructura JAMÁS abre la salida.
  2. El despacho debe haber HABILITADO ese ayudante (`hub_config.is_enabled`, default
     False). Es el opt-in por despacho, equivalente a `allow_notebooklm`.

Ante CUALQUIER duda (error de DB, política indeterminada, ayudante sin habilitar) → BLOQUEA.

POR QUÉ NO HAY UN TERCER INTERRUPTOR ("allow_agent_hub"):
El consentimiento de que el texto salga del equipo NO descansa solo en el toggle de
Configuración — descansa en que la delegación es de INVOCACIÓN EXPLÍCITA: solo ocurre si
el abogado NOMBRA al ayudante en su propio mensaje ("usa el asistente de navegación
para…", ver `agents/delegate_intent.py`). Eso es consentimiento POR MENSAJE y por turno,
más fuerte y más granular que una casilla global que se marca una vez y se olvida. El
toggle del Hub decide QUÉ ayudantes existen para el despacho; el mensaje del abogado
decide SI sale algo y QUÉ sale. Un tercer flag global sería una casilla que nadie lee y
daría la falsa sensación de que, marcada, ya todo puede salir sin pedirlo.
"""
from __future__ import annotations

import logging

from ..agent import llm
from . import hub_config

logger = logging.getLogger("mia.gateway.hub_gate")

# Motivos de bloqueo (para traza/log; nunca jerga al abogado).
REASON_OK = "ok"
REASON_SOBERANO = "soberano"        # política sin salida del equipo
REASON_NO_OPTIN = "sin-opt-in"      # el despacho no habilitó ese ayudante
REASON_ERROR = "error-gate"         # no se pudo determinar con certeza → fail-closed

# §G: motivos en llano para el abogado. La UI puede usarlos tal cual; NUNCA se le muestra
# el motivo interno ('soberano', 'sin-opt-in') ni se le habla de política/tenant/CLI.
REASON_TEXT: dict[str, str] = {
    REASON_SOBERANO: (
        "No se lo pedí a ningún ayudante externo: tu despacho está configurado en "
        "«Todo en mi equipo», así que nada de lo que escribes sale de este computador. "
        "Sigo con el expediente y el corpus del despacho."
    ),
    REASON_NO_OPTIN: (
        "Ese ayudante no está activado para tu despacho, así que no le envié nada. "
        "Puedes activarlo en Configuración › Asistentes."
    ),
    REASON_ERROR: (
        "No pude confirmar la configuración de confidencialidad de tu despacho, así que "
        "por precaución no envié nada fuera de este computador."
    ),
}

# Aviso que la UI DEBE mostrar junto al interruptor de cada ayudante en Configuración:
# es lo que vuelve "informado" al opt-in del despacho (restricción de consentimiento).
CONSENT_NOTICE = (
    "Al activarlo, podrás pedirle cosas nombrándolo en el chat. Cuando lo hagas, el texto "
    "de ESE mensaje sale de este computador hacia el ayudante, que es un programa de un "
    "tercero y puede consultar internet. Mia no le envía nada por su cuenta: solo cuando "
    "tú se lo pides en el mensaje."
)

# Aviso que acompaña a CADA delegación efectiva, en el turno, para que el abogado no se
# entere después de que su texto salió del equipo.
EXIT_NOTICE = (
    "Tu mensaje salió de este computador hacia este ayudante porque se lo pediste en el "
    "chat. Su respuesta viene de un programa externo: trátala como una pista sin verificar."
)


async def delegation_allowed(tenant_id: str, agent_key: str) -> tuple[bool, str]:
    """(permitido, motivo). True SOLO si la política ≠ 'soberano' Y el ayudante está habilitado.

    Fail-closed en todos los caminos: si `model_policy_for_strict` lanza (DB caída), se captura
    y se devuelve (False, REASON_ERROR) — nunca se asume que se puede salir del equipo por un
    fallo de infraestructura. El llamador debe tratar False como 'no delegar' y seguir el turno
    con el corpus local (degradación, no error).

    ORDEN DELIBERADO: la política se evalúa ANTES que el opt-in. En 'soberano' el resultado es
    el mismo aunque el ayudante esté habilitado — y así ni siquiera se consulta la config del
    Hub para decidir algo que ya está decidido."""
    try:
        policy = await llm.model_policy_for_strict(tenant_id)
    except Exception:  # noqa: BLE001 — un error leyendo la política NO abre la salida
        logger.exception(
            "hub_gate: no se pudo leer la política del tenant %s → BLOQUEA", tenant_id)
        return False, REASON_ERROR
    if policy == "soberano":
        logger.info("hub_gate: delegación a %s BLOQUEADA por política soberana (tenant=%s)",
                    agent_key, tenant_id)
        return False, REASON_SOBERANO
    try:
        if not await hub_config.is_enabled(tenant_id, agent_key):
            return False, REASON_NO_OPTIN
    except Exception:  # noqa: BLE001 — `is_enabled` no es fail-closed por sí solo: red aquí
        logger.exception("hub_gate: fallo leyendo el opt-in del tenant %s → BLOQUEA", tenant_id)
        return False, REASON_ERROR
    return True, REASON_OK
