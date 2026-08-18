"""Tope por turno de asunto y medición honesta de costo.

Las pasadas caras (Sala / ``legal_verification``) admiten UNA por turno sin
autorización explícita. La segunda exige ``autorizar_pasada_cara``.

Los alias de suscripción/local NO se registran como cost=0 «gratis»: viajan
como ``no_medida`` para no fingir un precio que no tenemos.
"""
from __future__ import annotations

from typing import Any

from ..metrics import usage as usage_metrics

EXPENSIVE_TASKS = frozenset({"legal_verification", "legal_warroom"})
MAX_UNAUTH_EXPENSIVE = 1


class TurnBudgetExceeded(Exception):
    """Hace falta autorización explícita para una segunda pasada cara."""


def cost_status_for_alias(alias: str) -> str:
    """``medido`` | ``estimado`` | ``no_medida`` — nunca disfrazar suscripción como $0."""
    return usage_metrics.cost_status_for(alias)


def record_expensive_call(md: dict[str, Any], task: str) -> int:
    """Anota una pasada cara en metadata del turno. Devuelve el conteo acumulado."""
    calls = list(md.get("expensive_calls") or [])
    calls.append(task)
    md["expensive_calls"] = calls
    return len([c for c in calls if c in EXPENSIVE_TASKS])


def authorize_expensive(md: dict[str, Any] | None, task: str, *,
                        authorized: bool) -> None:
    """Fail-closed: la 2ª pasada cara del turno exige autorización explícita."""
    data = md if md is not None else {}
    count = len([c for c in (data.get("expensive_calls") or []) if c in EXPENSIVE_TASKS])
    if task not in EXPENSIVE_TASKS:
        return
    if count < MAX_UNAUTH_EXPENSIVE:
        return
    if authorized or data.get("authorize_expensive_pass") is True:
        return
    raise TurnBudgetExceeded(
        "Esta pasada (revisión independiente o Sala de estrategia) ya corrió en "
        "este turno. Confirma que quieres una segunda pasada cara para continuar."
    )
