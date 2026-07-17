"""Mia · memory.soul_manager — el único escritor del SOUL.md. Propone; no aplica.

EL PRINCIPIO
    "La identidad es sagrada: ningún agente la escribe solo."
    La capa de MÁXIMA autoridad es la de MENOR autonomía.

El SOUL.md es la capa 1 del prompt: `agent/prompt_builder.py` la inyecta ENTERA, sin
tope y con autoridad de sistema, en TODOS los turnos. Hasta hoy `dreams._append_soul_rule`
escribía reglas ahí solo, sin aprobación, sin tope y sin historial — el único escritor
automático sin freno sobre la capa más poderosa del sistema. Los playbooks, que importan
menos, sí tenían versiones (`playbook_versions`), `changed_by`, motivo en llano y
aprobación atómica. Este módulo invierte esa asimetría.

TRES FRENOS
  1. HITL — Mia PROPONE (`propose_soul_rule` → `feedback_proposals`, tipo 'soul_rule');
     el abogado aprueba desde el panel de sugerencias que YA usa (Pantalla 4) y solo
     entonces se escribe. No hay canal nuevo que aprender.
  2. VERSIONADO — todo cambio deja fila en `soul_versions`: el estado ANTERIOR completo,
     quién cambió ('abogado' | 'mia'), cuándo y el motivo EN LLANO (§G).
  3. TOPE CON RECHAZO, NO TRUNCADO — mismo patrón que `profile_manager` (600/900 tokens):
     un SOUL que se pasa del presupuesto se RECHAZA con un mensaje en llano. Truncar la
     identidad la cortaría por la mitad en silencio; el despacho debe recortar a conciencia.

EL MATIZ (regla dura del proyecto): lo que el abogado SUMINISTRA DIRECTO es fidedigno.
Una instrucción suya NO vuelve a pasar por el HITL — `apply_soul_rule(changed_by="abogado")`
aplica de una. El HITL es para lo que Mia DEDUCE sola, no para lo que el abogado MANDA.

FICHERO vs DB — DECISIÓN EXPLÍCITA
El SOUL vive en `$MIA_HOME/soul_{tenant}.md`: fuera de la DB y SIN RLS. Su aislamiento
entre despachos depende de `_safe_tenant`, que colapsa entradas distintas al mismo nombre
(con UUIDs no es explotable hoy, pero es estructural). El historial (`soul_versions`) sí
vive en DB con RLS. Se DESINCRONIZAN si un cambio escribe el fichero y no llega a
registrar la versión. La decisión:

  · El FICHERO es la fuente de verdad (es lo que el prompt lee). La DB es el LIBRO DE
    CUENTAS, no la fuente. NUNCA se reconstruye el SOUL desde la DB.
  · Orden: se registra la versión ANTES de tocar el fichero, dentro de la transacción del
    tenant. Si el fichero no se puede escribir → excepción → la transacción revierte → no
    queda versión fantasma. Si el fichero se escribe y el commit falla después, se pierde
    UN registro de historial pero el SOUL queda correcto: el sistema se reancla solo,
    porque el snapshot del cambio SIGUIENTE se toma leyendo el fichero REAL, no la tabla.
    Se prefirió ese fallo (perder una línea del libro) sobre el contrario (identidad
    corrompida o cambio invisible).
  · `_safe_tenant` NO se toca aquí: cambiarlo renombraría los SOUL de los despachos ya
    instalados. La mejora correcta (fichero por carpeta de tenant validado como UUID) es
    un cambio de layout de $MIA_HOME, no de este encargo. Queda dicho, no forzado.

NO SE REDISEÑA EL SOUL. Su generación es determinista y sin LLM por decisión de
2026-07-06 (`memory/decisions.md`). Aquí solo se AÑADEN reglas ya redactadas a una sección
propia — cero secciones interpretativas, cero "personalidad", cero LLM.
"""
from __future__ import annotations

import asyncio
import logging

from ..db import pool
from ..onboarding.soul_interview import soul_path
from .tokens import estimate_tokens

logger = logging.getLogger("mia.memory.soul")

# Presupuesto del SOUL COMPLETO. Los SOUL reales de los despachos instalados van de ~50 a
# ~500 tokens; 1200 deja margen de sobra para crecer a conciencia y sigue siendo un freno
# real (la capa 1 se paga en TODOS los turnos). Mismo espíritu que los 600/900 de
# `profile_manager`: es un guardarraíl offline, el conteo exacto lo da el gateway.
SOUL_MAX_TOKENS = 1200

# Encabezado de la sección donde aterrizan las reglas aprendidas. Constante: es también la
# marca que usa el dedup y lo que el abogado reconoce en su archivo.
LEARNED_SECTION = "## Preferencias aprendidas por Mia"


class SoulTooLargeError(ValueError):
    """El cambio dejaría el SOUL por encima del presupuesto → se RECHAZA (no se trunca).

    `str(e)` es el mensaje EN LLANO que ve el abogado (§G): sin "tokens", sin "presupuesto",
    sin jerga. Hereda de ValueError para calzar con el patrón de `profile_manager`.
    """


def _plain_size_message(current_tokens: int) -> str:
    """Mensaje en llano para el abogado cuando la identidad ya no admite más texto.

    Se habla de PALABRAS (≈0.75 por token en la heurística), nunca de tokens: el abogado
    no lee jerga y 'token' no significa nada en su escritorio."""
    aprox_palabras = int(current_tokens * 0.75)
    limite_palabras = int(SOUL_MAX_TOKENS * 0.75)
    return (
        "No pude guardar esta regla: el texto que describe a tu despacho ya está en su "
        f"tamaño máximo (unas {aprox_palabras} palabras; el máximo son unas "
        f"{limite_palabras}). Mia lee ese texto completo en cada consulta, así que no "
        "puede crecer sin fin. Entra a «Mi despacho», quita lo que ya no aplique y vuelve "
        "a intentarlo. No recorté nada por mi cuenta: prefiero que decidas tú qué sobra."
    )


def read_soul(tenant_id: str) -> str:
    """Contenido actual del SOUL.md del despacho ('' si aún no existe)."""
    path = soul_path(tenant_id)
    return path.read_text(encoding="utf-8") if path.exists() else ""


def compose_with_rule(current: str, rule: str) -> str:
    """El SOUL que resultaría de añadir `rule` — PURA, no escribe nada.

    Determinista y sin LLM (decisión 2026-07-06). Réplica exacta de la composición que
    hacía `dreams._append_soul_rule`, extraída para poder VALIDARLA antes de escribir."""
    rule = (rule or "").strip()
    if not rule or rule in current:
        return current
    section = f"\n\n{LEARNED_SECTION}\n" if LEARNED_SECTION not in current else "\n"
    return current.rstrip() + section + f"- {rule}\n"


def check_soul_budget(content: str) -> None:
    """Rechaza (no trunca) un SOUL que excede el presupuesto. Patrón `profile_manager`."""
    n = estimate_tokens(content)
    if n > SOUL_MAX_TOKENS:
        raise SoulTooLargeError(_plain_size_message(n))


def rule_already_present(tenant_id: str, rule: str) -> bool:
    """¿La regla ya está en el SOUL del despacho? (dedup literal, como el original).

    Sirve también para las reglas que `dreams` YA escribió antes de este cambio: siguen
    ahí, se respetan y NO se vuelven a proponer. No se borra nada retroactivamente — son
    parte de la identidad que el despacho fundador viene usando."""
    return (rule or "").strip() in read_soul(tenant_id)


# ── Escritura: el ÚNICO camino que toca el fichero ──────────────────────────

async def apply_soul_rule(tenant_id: str, rule: str, *, changed_by: str,
                          reason: str) -> dict:
    """Añade `rule` al SOUL del despacho, versionando el estado anterior.

    ES EL ÚNICO ESCRITOR. `changed_by`:
      · 'abogado' — instrucción DIRECTA del abogado. Se aplica de una: lo que él suministra
        es fidedigno y no se le re-pregunta lo que acaba de ordenar.
      · 'mia'     — texto que originó Mia. Solo debe llegar aquí DESPUÉS de que el abogado
        aprobó la propuesta (ver `apply_soul_rule_proposal`).
    `reason` va al historial en LLANO (§G).

    Levanta `SoulTooLargeError` (mensaje en llano) si el cambio no cabe → nada se escribe.
    Devuelve {"applied": bool, "reason": str} — applied=False si la regla ya estaba
    (idempotente: no duplica ni versiona de más).
    """
    if changed_by not in ("abogado", "mia"):
        raise ValueError("changed_by debe ser 'abogado' o 'mia'")
    rule = (rule or "").strip()
    if not rule:
        return {"applied": False, "reason": "regla vacía"}

    current = read_soul(tenant_id)
    new_content = compose_with_rule(current, rule)
    if new_content == current:
        return {"applied": False, "reason": "la regla ya estaba en la identidad"}

    # Tope ANTES de tocar nada: rechaza, no trunca.
    check_soul_budget(new_content)

    path = soul_path(tenant_id)
    async with pool.tenant_connection(tenant_id) as conn:
        # 1) El libro de cuentas primero: el estado ANTERIOR, tomado del fichero REAL.
        await conn.execute(
            "INSERT INTO soul_versions (tenant_id, content, changed_by, reason) "
            "VALUES (%s::uuid, %s, %s, %s)",
            (tenant_id, current, changed_by, reason or ""))
        # 2) El fichero después, DENTRO de la transacción: si el disco falla, la excepción
        #    revierte la versión y no queda historial de un cambio que no ocurrió.
        def _write() -> None:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(new_content, encoding="utf-8")

        await asyncio.to_thread(_write)   # E/S de disco fuera del event loop
    return {"applied": True, "reason": reason or ""}


async def soul_versions(tenant_id: str, limit: int = 20) -> list[dict]:
    """Historial de la identidad del despacho (más reciente primero). Bajo RLS."""
    from psycopg.rows import dict_row
    async with pool.tenant_connection(tenant_id) as conn:
        async with conn.cursor(row_factory=dict_row) as cur:
            await cur.execute(
                "SELECT id::text, content, changed_by, reason, created_at "
                "FROM soul_versions ORDER BY created_at DESC, id DESC LIMIT %s", (limit,))
            return await cur.fetchall()


# ── Propuesta: lo que Mia DEDUCE sola pasa por aquí ─────────────────────────

async def propose_soul_rule(tenant_id: str, rule: str, *, reason: str,
                            signal_count: int = 1,
                            trace_ids: list[str] | None = None) -> str | None:
    """Deja una regla PROPUESTA para que el abogado la apruebe. NO escribe el SOUL.

    Reusa `feedback_proposals` (tipo 'soul_rule'), el mecanismo que ya usan el Curator y el
    feedback_processor y que el abogado ya sabe revisar (Pantalla 4 → POST
    /proposals/{id}/apply). `reason` es lo que él leerá como porqué: SIEMPRE en llano.

    Devuelve el id de la propuesta, o None si no había nada que proponer (regla vacía, ya
    presente en el SOUL, o ya propuesta y pendiente → no se acosa al abogado con la misma
    sugerencia cada semana).
    """
    rule = (rule or "").strip()
    if not rule or rule_already_present(tenant_id, rule):
        return None
    async with pool.tenant_connection(tenant_id) as conn:
        dup = await (await conn.execute(
            "SELECT 1 FROM feedback_proposals WHERE proposal_type='soul_rule' "
            "AND status='pending' AND suggested_content=%s LIMIT 1", (rule,))).fetchone()
        if dup:
            return None
        row = await (await conn.execute(
            "INSERT INTO feedback_proposals "
            "  (tenant_id, proposal_type, suggested_content, rationale, signal_count, trace_ids) "
            "VALUES (%s::uuid, 'soul_rule', %s, %s, %s, %s) RETURNING id::text",
            (tenant_id, rule, reason, max(1, signal_count), trace_ids or None))).fetchone()
    return row[0]


async def apply_soul_rule_proposal(tenant_id: str, rule: str, *,
                                   reason: str | None = None) -> dict:
    """Aplica una propuesta 'soul_rule' YA APROBADA por el abogado (la llama la ruta de
    aprobación). Queda como `changed_by='mia'` porque el TEXTO lo originó Mia — igual que
    `playbook_versions` marca 'mia' las mejoras aplicadas desde una propuesta.

    El abogado puede haber editado la regla antes de aprobar: se aplica lo que él aprobó."""
    return await apply_soul_rule(
        tenant_id, rule, changed_by="mia",
        reason=reason or "El abogado aprobó una preferencia que Mia aprendió de su trabajo.")
