"""Mia · memory.interviewer — motor de entrevista STATELESS para crear guías de trabajo
(Bloque B, evolución de producto: B1-B3).

Un abogado tiene una metodología en la cabeza pero nadie se la extrae. Este módulo hace
de entrevistador: dado el transcript completo de la conversación (el frontend lo manda
entero en cada turno — nada se guarda en memoria de servidor entre turnos), decide si
hace falta OTRA pregunta o si ya hay material para proponer un borrador de guía.

Contrato de salida (ver `routes/guides.py`):
  {"done": False, "question": str}
  {"done": True, "draft": {"title","summary","applies_when","content"}, "explanation": str}

Reglas duras (no las decide el LLM, las impone este módulo):
  - Menos de 3 preguntas ya hechas -> SIEMPRE se pregunta otra (aunque el LLM proponga
    un borrador, se ignora y se fuerza una pregunta).
  - 6 preguntas o más ya hechas -> SIEMPRE se fuerza el borrador (aunque el LLM proponga
    otra pregunta, se ignora y se construye/pide un borrador).
  - Entre 3 y 6 -> decide el LLM (task="curator").
  - El JSON del LLM puede venir inválido o incompleto: SIEMPRE hay una salida de
    respaldo determinista (pregunta o borrador) — este módulo JAMÁS deja escapar una
    excepción que termine en un 500 para el abogado.
  - Este módulo NUNCA escribe en la base de datos. El borrador vive solo en la
    respuesta HTTP hasta que el abogado pulsa "Guardar" en otro endpoint (gate HITL
    por construcción, no por permiso).

B3 (precarga de contexto de un asunto): si llega `matter_id` y el transcript está
vacío, se valida que el asunto sea del tenant (si no, `MatterNotFoundError`) y se
arma una primera pregunta de confirmación con el título/descripción del asunto y las
trazas APROBADAS (mismo patrón que `wiki_manager._approved_evidence`). En los turnos
siguientes de esa misma entrevista el `matter_id` se sigue mandando (el módulo es
stateless) y ese contexto se reinyecta en el prompt del LLM.
"""
from __future__ import annotations

import asyncio
import json
import logging
import uuid
from typing import Any

from psycopg.rows import dict_row

from ..agent import llm
from .trace_capture import TraceCapture

logger = logging.getLogger("mia.memory.interviewer")

MIN_QUESTIONS = 3
MAX_QUESTIONS = 6

_FIELD_MAX_CHARS = 200          # title/summary/applies_when recortados server-side
_MSG_BUDGET_CHARS = 4000        # cada mensaje del transcript, recortado antes del prompt
_EVIDENCE_BUDGET_CHARS = 12000  # evidencia aprobada del asunto (B3), recortada

_trace_capture = TraceCapture()

# Preguntas de respaldo, en orden — se usan cuando el JSON del LLM viene inválido o
# incompleto. Indexadas por cuántas preguntas van (0 = la primera).
_FALLBACK_QUESTIONS = [
    "¿Qué tipo de asunto o situación suele resolver esta guía? Cuéntamelo con tus "
    "palabras, como si me lo explicaras a mí.",
    "¿Cuáles son los pasos concretos que sigues, en orden, cuando trabajas este tipo "
    "de caso?",
    "¿Qué documentos o información necesitas tener a la mano antes de empezar?",
    "¿Hay algún error común que quieras evitar, o algo que SIEMPRE debas revisar antes "
    "de dar por bueno el trabajo?",
    "¿Cómo sabes que el resultado quedó bien hecho? ¿Cómo se ve un buen resultado aquí?",
    "¿Algo más que un abogado nuevo en el despacho debería saber para poder repetir tu "
    "método sin ti al lado?",
]


class MatterNotFoundError(ValueError):
    """El `matter_id` no existe o no es del tenant. El endpoint lo mapea a 404."""


def _is_uuid(s: str) -> bool:
    try:
        uuid.UUID(str(s))
        return True
    except Exception:
        return False


def _trim(text: str, limit: int) -> str:
    text = (text or "").strip()
    if len(text) <= limit:
        return text
    return text[: max(limit - 1, 0)].rstrip() + "…"


def _count_assistant_questions(messages: list[dict]) -> int:
    return sum(
        1 for m in messages
        if isinstance(m, dict) and m.get("role") == "assistant"
    )


def _fallback_question(already_asked: int) -> str:
    idx = min(max(already_asked, 0), len(_FALLBACK_QUESTIONS) - 1)
    return _FALLBACK_QUESTIONS[idx]


def _fallback_draft(messages: list[dict]) -> dict:
    """Borrador determinista construido con las respuestas del transcript, para cuando
    el LLM debía redactar el borrador final (>=6 preguntas) y su JSON vino inválido."""
    answers = [
        str(m.get("content", "")).strip()
        for m in messages
        if isinstance(m, dict) and m.get("role") == "user" and str(m.get("content", "")).strip()
    ]
    if answers:
        content = "Respuestas recogidas durante la entrevista (edítalas y dales forma):\n\n"
        content += "\n\n".join(f"- {a}" for a in answers)
    else:
        content = "La entrevista no dejó respuestas para armar un borrador. Escribe la guía a mano."
    return {
        "title": "Guía sin título — edítalo antes de guardar",
        "summary": "Guía generada a partir de las respuestas de la entrevista; revísala.",
        "applies_when": "Ajusta esta condición a la situación real del despacho.",
        "content": content,
        "explanation": (
            "Mia no pudo redactar el borrador automáticamente esta vez, así que aquí "
            "quedan tus respuestas tal cual las diste. Edítalas antes de guardar la guía."
        ),
    }


async def _matter_context(tenant_id: str, matter_id: str, pool: Any) -> dict:
    """Título + descripción del asunto y evidencia aprobada (trazas con
    hitl_outcome='approved'). Lanza MatterNotFoundError si el asunto no es del tenant."""
    if pool is None or not _is_uuid(matter_id):
        # CP-S3 (mismo criterio que _common._is_uuid/require_uuid): un id mal formado se
        # rechaza ANTES de tocar SQL — si llegara crudo al `::uuid` de abajo, psycopg
        # lanzaría InvalidTextRepresentation sin capturar y el abogado vería un 500 en vez
        # del 404 en llano que promete este módulo (hallazgo del revisor).
        raise MatterNotFoundError("Ese asunto no existe")
    async with pool.tenant_connection(tenant_id) as conn:
        async with conn.cursor(row_factory=dict_row) as cur:
            await cur.execute(
                "SELECT title, description FROM matters WHERE id = %s::uuid", (matter_id,))
            row = await cur.fetchone()
    if not row:
        raise MatterNotFoundError("Ese asunto no existe")

    evidence: list[str] = []
    for rec in _trace_capture.read(tenant_id):
        if str(rec.get("matter_id")) != str(matter_id):
            continue
        if rec.get("hitl_outcome") != "approved":
            continue
        parts = [str(rec.get("input") or ""), str(rec.get("output") or ""),
                 str(rec.get("draft_final") or "")]
        text = "\n\n".join(p for p in parts if p.strip())
        if text.strip():
            evidence.append(text)

    evidence_text = _trim("\n\n---\n\n".join(evidence), _EVIDENCE_BUDGET_CHARS)
    return {
        "title": (row.get("title") or "").strip(),
        "description": (row.get("description") or "").strip(),
        "evidence": evidence_text,
    }


def _confirmation_question(ctx: dict) -> str:
    titulo = ctx["title"] or "este asunto"
    resumen = f"Trabajamos juntos en «{titulo}»"
    if ctx["description"]:
        resumen += f": {ctx['description']}"
    resumen = resumen.rstrip(".") + "."
    return (
        f"{resumen} ¿Quieres que la guía recoja ese método de trabajo? "
        "Cuéntame qué ajustarías o qué le falta antes de seguir."
    )


_SYSTEM_PROMPT = (
    "Eres Mia. Estás entrevistando a un abogado del despacho para extraer, paso a "
    "paso, una guía de trabajo escrita a partir de una metodología que hoy solo "
    "tiene en la cabeza. Haz UNA pregunta concreta a la vez, en español llano (nunca "
    "en jerga de abogados vacía ni en jerga técnica de software), que construya "
    "sobre las respuestas anteriores del abogado — no repitas preguntas ya "
    "respondidas. Cuando tengas material suficiente, propones un borrador de guía.\n\n"
    "Responde SIEMPRE con un JSON, sin texto adicional antes ni después, en una de "
    "estas dos formas:\n"
    '  {"action": "ask", "question": "..."}\n'
    '  {"action": "draft", "title": "...", "summary": "...", "applies_when": "...", '
    '"content": "...", "explanation": "..."}\n'
    "El \"content\" del borrador debe ser la guía completa, redactada en pasos claros "
    "que otro abogado del despacho pueda seguir sin ayuda."
)


def _build_llm_messages(
    messages: list[dict], ctx: dict | None, forced_action: str | None
) -> list[dict]:
    system = _SYSTEM_PROMPT
    if forced_action == "ask":
        system += (
            "\n\nTodavía no se han hecho las 3 preguntas mínimas. Debes responder "
            'SIEMPRE con {"action": "ask", ...} — no puedes proponer el borrador aún.'
        )
    elif forced_action == "draft":
        system += (
            "\n\nYa se hicieron suficientes preguntas (6 o más). Debes responder "
            'SIEMPRE con {"action": "draft", ...} con el borrador final — no hagas '
            "más preguntas."
        )
    if ctx is not None:
        bloque = (
            f"\n\nContexto del asunto ya trabajado con este abogado:\n"
            f"Título: {ctx['title'] or '(sin título)'}\n"
            f"Descripción: {ctx['description'] or '(sin descripción)'}"
        )
        if ctx["evidence"]:
            bloque += f"\n\nFragmentos aprobados relevantes de ese asunto:\n{ctx['evidence']}"
        system += bloque

    out: list[dict] = [{"role": "system", "content": system}]
    for m in messages:
        if not isinstance(m, dict):
            continue
        role = m.get("role")
        if role not in ("assistant", "user"):
            continue
        out.append({"role": role, "content": _trim(str(m.get("content", "")), _MSG_BUDGET_CHARS)})
    return out


def _clip_draft_fields(draft: dict) -> dict:
    return {
        "title": _trim(str(draft.get("title", "")), _FIELD_MAX_CHARS),
        "summary": _trim(str(draft.get("summary", "")), _FIELD_MAX_CHARS),
        "applies_when": _trim(str(draft.get("applies_when", "")), _FIELD_MAX_CHARS),
        "content": str(draft.get("content", "")).strip(),
    }


def _parse_llm_decision(raw: str) -> dict | None:
    """Devuelve {"action":..., ...} válido, o None si el JSON vino inválido/incompleto.
    JAMÁS lanza — cualquier problema de parseo cae a None (fallback determinista)."""
    try:
        parsed = json.loads(raw)
    except Exception:
        return None
    if not isinstance(parsed, dict):
        return None
    action = parsed.get("action")
    if action == "ask":
        if not isinstance(parsed.get("question"), str) or not parsed["question"].strip():
            return None
        return parsed
    if action == "draft":
        required = ("title", "summary", "applies_when", "content")
        if any(not isinstance(parsed.get(f), str) for f in required):
            return None
        return parsed
    return None


async def _ask_llm(llm_messages: list[dict]) -> dict | None:
    try:
        resp = await asyncio.to_thread(llm.call_llm, llm_messages, task="curator")
        raw = resp.choices[0].message.content or ""
    except Exception:
        logger.exception("interviewer: call_llm falló; se usa la pregunta/borrador de respaldo")
        return None
    return _parse_llm_decision(raw)


async def interview(
    kind: str,
    messages: list[dict],
    tenant_id: str,
    matter_id: str | None = None,
    pool: Any = None,
) -> dict:
    """Motor de entrevista stateless. Ver docstring del módulo para el contrato completo."""
    ctx: dict | None = None
    if matter_id:
        ctx = await _matter_context(tenant_id, matter_id, pool)
        if not messages:
            # B3: primer turno con matter_id y transcript vacío -> resumen de
            # confirmación, sin tocar el LLM (no hay nada que decidir todavía).
            return {"done": False, "question": _confirmation_question(ctx)}

    already_asked = _count_assistant_questions(messages)
    if already_asked < MIN_QUESTIONS:
        forced: str | None = "ask"
    elif already_asked >= MAX_QUESTIONS:
        forced = "draft"
    else:
        forced = None

    llm_messages = _build_llm_messages(messages, ctx, forced)
    decision = await _ask_llm(llm_messages)

    if forced == "ask":
        if decision is None or decision.get("action") != "ask":
            return {"done": False, "question": _fallback_question(already_asked)}
        return {"done": False, "question": decision["question"]}

    if forced == "draft":
        if decision is None or decision.get("action") != "draft":
            draft = _fallback_draft(messages)
            return {
                "done": True,
                "draft": _clip_draft_fields(draft),
                "explanation": draft["explanation"],
            }
        draft = _clip_draft_fields(decision)
        return {
            "done": True,
            "draft": draft,
            "explanation": str(decision.get("explanation", "")).strip(),
        }

    # Entre MIN_QUESTIONS y MAX_QUESTIONS: decide el LLM.
    if decision is None:
        return {"done": False, "question": _fallback_question(already_asked)}
    if decision.get("action") == "ask":
        return {"done": False, "question": decision["question"]}
    draft = _clip_draft_fields(decision)
    return {
        "done": True,
        "draft": draft,
        "explanation": str(decision.get("explanation", "")).strip(),
    }
