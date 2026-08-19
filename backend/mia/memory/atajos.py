"""Mia · memory.atajos — atajos de despacho para la conversación vacía (Meta E · Mitad 2).

QUÉ ES: un texto reproducible y determinista, listo para PRE-LLENAR el cuadro de mensaje del
abogado (consent-first — NUNCA se auto-envía; el abogado siempre revisa y pulsa enviar). Hay
dos tipos:

  · Atajo de GUÍA: reproduce el título y el "cuándo aplica" de una guía activa del despacho.
  · Atajo de AGENTE (persona): EMBEBE literalmente una de las `summon_phrases` existentes de
    la persona, así que `agents.personas.detect_persona()` la reconoce SIN que este módulo
    toque un solo bit de esa resolución (misma función ya gateada de siempre).

Este módulo es PURO donde puede serlo (`build_playbook_shortcut` / `build_persona_shortcut`
no tocan la DB ni tienen efectos: mismo input → mismo texto, byte a byte). Solo
`list_shortcuts` toca la DB, y lo hace de solo LECTURA — no crea ninguna tabla nueva.

FAIL-OPEN: `list_shortcuts` nunca lanza; ante cualquier error de DB devuelve lista vacía
(mostrar atajos es una ayuda, no un candado — patrón agents.personas.PersonaService).
"""
from __future__ import annotations

import logging
from typing import Optional

from ..db import pool

logger = logging.getLogger("mia.memory.atajos")

# Cuántos atajos como máximo se ofrecen en la conversación vacía (frontend: hasta 6 chips).
MAX_SHORTCUTS = 6

# Cupo GARANTIZADO para los agentes del despacho dentro de `MAX_SHORTCUTS`.
# Por qué: antes se anexaban las guías primero y se cortaba al final, así que con 6 o más guías
# activas los agentes NO salían NUNCA — el despacho los configuraba en su pantalla y no volvía a
# verlos en la conversación vacía, que es justo donde más los usaría. Este cupo se reserva ANTES
# del corte. No agranda la lista: si no hay agentes, las guías se quedan con los 6 cupos.
RESERVED_FOR_AGENTS = 2


def build_playbook_shortcut(row: dict) -> str:
    """Texto reproducible de una guía: 'Aplica la guía del despacho "X": <cuándo aplica>.
    Marca [VERIFICAR] lo que no puedas confirmar.' Puro y determinista (mismo `row` → mismo
    texto, byte a byte)."""
    title = str(row.get("title") or "").strip()
    applies_when = str(row.get("applies_when") or "").strip()
    texto = f'Aplica la guía del despacho "{title}"'
    if applies_when:
        texto += f": {applies_when}"
    texto += ". Marca [VERIFICAR] lo que no puedas confirmar."
    return texto


def build_persona_shortcut(persona: dict) -> Optional[str]:
    """Texto reproducible de un agente (persona): EMBEBE literalmente una de sus
    `summon_phrases` (la más larga — mismo criterio de especificidad que
    `agents.personas.detect_persona`) para que esa función la reconozca sin ningún cambio en
    su resolución. None si la persona no tiene ninguna frase de invocación utilizable.

    Puro y determinista (mismo `persona` → mismo texto, byte a byte)."""
    phrases = [str(p).strip() for p in (persona.get("summon_phrases") or []) if str(p).strip()]
    if not phrases:
        return None
    phrase = max(phrases, key=len)  # la más larga: la más específica, igual que detect_persona
    description = str(persona.get("description") or "").strip()
    texto = f"Quiero que trabajes {phrase} en este asunto."
    if description:
        texto += f" {description}"
    return texto


async def list_shortcuts(tenant_id: str, limit: int = MAX_SHORTCUTS) -> list[dict]:
    """Atajos del despacho para la conversación vacía: guías activas (por `usage_count`, mismo
    orden que GET /api/playbooks) + agentes habilitados (mismo orden que GET /api/personas —
    esa tabla no lleva contador de uso), cada uno con un `texto` reproducible listo para
    pre-llenar el cuadro de mensaje. Nunca más de `limit` atajos en total.

    REPARTO: los agentes tienen `RESERVED_FOR_AGENTS` cupos garantizados, que se descuentan
    ANTES de cortar las guías; si sobran cupos (pocas guías o pocos agentes) el otro grupo los
    absorbe, así que la lista siempre llega a `limit` mientras haya material.

    Determinista: para el mismo estado de la base de datos, el mismo orden y el mismo texto
    siempre. FAIL-OPEN: cualquier error de lectura → lista vacía (nunca rompe la pantalla).
    """
    try:
        async with pool.tenant_connection(tenant_id) as conn:
            pb_rows = await (await conn.execute(
                "SELECT id, title, applies_when FROM playbooks WHERE status = 'active' "
                "ORDER BY usage_count DESC, created_at LIMIT %s", (limit,),
            )).fetchall()
            persona_rows = await (await conn.execute(
                "SELECT id, name, description, summon_phrases FROM personas "
                "WHERE enabled = true ORDER BY lower(name)"
            )).fetchall()
    except Exception:  # noqa: BLE001 — mostrar atajos es una ayuda, no un candado
        logger.warning("atajos: no se pudieron cargar (tenant=%s)", tenant_id, exc_info=True)
        return []

    guias: list[dict] = []
    for r in pb_rows:
        texto = build_playbook_shortcut({"title": r[1], "applies_when": r[2]})
        guias.append({"kind": "guia", "id": str(r[0]), "label": r[1], "texto": texto})

    agentes: list[dict] = []
    for r in persona_rows:
        texto = build_persona_shortcut(
            {"name": r[1], "description": r[2], "summon_phrases": r[3]})
        if texto:
            agentes.append({"kind": "agente", "id": str(r[0]), "label": r[1], "texto": texto})

    # Reparto de los `limit` cupos: primero se aparta la reserva de los agentes (solo la que de
    # verdad se puede usar), se cortan las guías con lo que queda, y el remanente vuelve a los
    # agentes. Sin reserva, 6 guías activas dejaban la lista llena y ningún agente entraba.
    reserva = max(0, min(RESERVED_FOR_AGENTS, len(agentes), limit))
    n_guias = max(0, min(len(guias), limit - reserva))
    n_agentes = max(0, min(len(agentes), limit - n_guias))
    return guias[:n_guias] + agentes[:n_agentes]
