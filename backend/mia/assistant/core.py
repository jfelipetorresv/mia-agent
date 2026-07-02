"""Mia · assistant.core — MODO ASISTENTE (CP-B1, Pilar B): conversación libre.

Hasta CP-B1 Mia solo conversa DENTRO de un expediente (grafo matter-céntrico,
agents/graph.py). El modo asistente le da al abogado una conversación libre —
agenda, recordatorios, investigación, el despacho — con la MISMA alma y la misma
infraestructura:

  · Identidad: el SOUL.md del tenant (capa L1 del prompt_builder, cargado con
    soul_interview.load_soul_text) + las reglas de comunicación sin jerga (L5,
    prompt_builder.USER_COMMS) + una instrucción propia del asistente.
  · Motor: llm.call_llm(task="main") — la política de modelo del tenant
    (suscripcion/nube/soberano, CP2 · decisión #27) ya viene fijada por el
    middleware en el ContextVar; asyncio.to_thread propaga el contexto.
  · Historial: persistente en assistant_conversations / assistant_messages
    (015_assistant.sql), bajo RLS fail-closed vía pool.tenant_connection.
  · Compresión: si el historial estimado supera el umbral del ContextCompressor
    (55% de config.MIA_CONTEXT_WINDOW), se comprime ANTES de llamar al modelo —
    el propósito original del compresor (historial creciente), por fin cableado.

Herramienta v1 ACOTADA (sin framework de tools): si el mensaje pregunta por los
asuntos/borradores pendientes del despacho (keywords), se consulta `matters` bajo
RLS y se inyecta un bloque "=== ESTADO ACTUAL DE TUS ASUNTOS ===" en el mensaje
que VE el modelo (el mensaje persistido es el original del abogado). Las
herramientas reales (framework de tools, agenda, recordatorios) llegan con CP-B4.

Decisión #28 (memory/decisions.md): una sola Mia — mismo SOUL, mismos límites,
otra superficie de conversación.
"""
from __future__ import annotations

import asyncio
import logging
import re
import uuid
from types import SimpleNamespace

from .. import config
from ..agent import llm, prompt_builder
from ..agent.context_compressor import ContextCompressor
from ..db import pool
from ..onboarding.soul_interview import load_soul_text

logger = logging.getLogger("mia.assistant.core")

# Título de la conversación = primeras palabras del primer mensaje (cabe en varchar(200)).
_TITLE_MAX_WORDS = 8
_TITLE_MAX_CHARS = 120

# Herramienta v1: detección simple de "pregunta por el estado de mis asuntos".
# Con CP-B4 esto se reemplaza por un framework de tools de verdad.
_MATTERS_QUERY_RE = re.compile(
    r"\b(asuntos?|borrador(?:es)?|pendientes?|casos?)\b", re.IGNORECASE
)

MATTERS_BLOCK_HEADER = "=== ESTADO ACTUAL DE TUS ASUNTOS ==="

# Historial: cuántos mensajes persistidos se cargan por turno. Una conversación de años
# no puede cargarse entera (memoria + latencia + ventana); 200 mensajes ≈ semanas de uso
# y el compresor/truncado reduce desde ahí. Los más antiguos siguen en DB (list_messages
# no limita), solo dejan de viajar al modelo.
_HISTORY_MAX_MESSAGES = 200

# Fallback si la COMPRESIÓN falla (excepción del compresor o de su LLM): truncado duro
# SIN LLM — se conservan los primeros 2 y los últimos 30 mensajes (eco del patrón
# protect del compresor) con un marcador en medio, y el turno CONTINÚA (nunca 502 por
# no poder resumir).
_TRUNCATE_KEEP_FIRST = 2
_TRUNCATE_KEEP_LAST = 30
TRUNCATION_MARKER = "[... historial antiguo omitido ...]"

# Campos interpolados en bloques del sistema (p. ej. títulos de matters): máximo de chars.
_FIELD_MAX_CHARS = 150

# Instrucción propia del modo asistente (se suma a L1 identidad/SOUL y L5 comunicación).
ASSISTANT_INSTRUCTIONS = (
    "Eres Mia en su modo de ASISTENTE PERSONAL del abogado: en esta conversación no hay "
    "un expediente abierto y puedes conversar de lo que él necesite — su agenda, "
    "recordatorios, investigación, ideas, la operación del despacho o cualquier otro "
    "tema. Recuerdas el contexto del despacho (su identidad, su voz y sus límites) y lo "
    "usas para ayudar de verdad, no solo para responder. Regla inquebrantable: NUNCA "
    "des por definitivo un plazo procesal, un término judicial o una fecha límite legal "
    "— si mencionas uno, márcalo con [VERIFICAR] y dile al abogado que debe confirmarlo "
    "él mismo contra la fuente oficial antes de actuar."
)


class ConversationNotFound(Exception):
    """La conversación no existe PARA ESTE TENANT (RLS: la de otro despacho es invisible)."""


def _make_title(message: str) -> str:
    """Título = primeras palabras del mensaje, acotado a varchar(200)."""
    words = (message or "").split()
    title = " ".join(words[:_TITLE_MAX_WORDS]).strip()
    if len(title) > _TITLE_MAX_CHARS:
        title = title[:_TITLE_MAX_CHARS].rstrip()
    return title or "Conversación"


def _asks_about_matters(message: str) -> bool:
    return bool(_MATTERS_QUERY_RE.search(message or ""))


def _sanitize_title(value) -> str:
    """Sanea un campo que se interpola en un bloque del sistema (defensa de prompt).

    Un título hostil con saltos de línea o '===' podría "cerrar" el bloque
    === ESTADO ACTUAL DE TUS ASUNTOS === y fabricar instrucciones con autoridad del
    sistema. Se colapsa TODO el whitespace (incluidos \\n \\r) a espacios simples, se
    eliminan secuencias de 3+ '=' y se trunca a un largo razonable.
    """
    text = re.sub(r"={3,}", "", str(value or ""))
    text = re.sub(r"\s+", " ", text).strip()
    return text[:_FIELD_MAX_CHARS].strip()


def _truncate_history(history: list[dict]) -> list[dict]:
    """Truncado duro SIN LLM del historial (fallback cuando la compresión falla)."""
    if len(history) <= _TRUNCATE_KEEP_FIRST + _TRUNCATE_KEEP_LAST:
        return history
    return [
        *history[:_TRUNCATE_KEEP_FIRST],
        {"role": "user", "content": TRUNCATION_MARKER},
        *history[-_TRUNCATE_KEEP_LAST:],
    ]


def _require_uuid(conversation_id: str) -> str:
    """Un id mal formado equivale a 'no existe' (404), nunca a un error técnico (500)."""
    try:
        return str(uuid.UUID(str(conversation_id)))
    except (ValueError, AttributeError, TypeError):
        raise ConversationNotFound(conversation_id)


def build_assistant_system(tenant_id: str) -> str:
    """System del modo asistente: capas del prompt_builder que aplican SIN matter.

    Reutiliza L1 (identidad/SOUL del tenant, vía _identity_layer sobre un estado
    duck-typed) y L5 (comunicación sin jerga, USER_COMMS) y les suma la instrucción
    propia del asistente. Sin SOUL.md (onboarding incompleto) la identidad va vacía
    y el asistente funciona igual (no bloquea).
    """
    state = SimpleNamespace(identity=load_soul_text(tenant_id) or "")
    parts = [
        prompt_builder._identity_layer(state),      # L1 · identidad / SOUL del tenant
        prompt_builder._user_comms_layer(state),    # L5 · comunicación sin jerga (§G)
        ASSISTANT_INSTRUCTIONS,                     # instrucción propia del modo asistente
    ]
    return "\n\n".join(p.strip() for p in parts if p and p.strip())


class AssistantService:
    """Conversación libre del asistente: crea/continúa conversaciones y llama al modelo.

    v1 SIN streaming (SSE): el proveedor por suscripción (CLI de Claude Code, CP2)
    responde en bloque, así que el endpoint devuelve la respuesta completa.

    SIN estado compartido entre requests: el ContextCompressor se crea POR TURNO dentro
    de chat() (mismo patrón que graph.py). Un compresor compartido arrastraría en memoria
    el `_previous_summary` de la última compresión — de CUALQUIER despacho — y su prompt
    iterativo se lo entregaría al modelo del siguiente ("PRESERVA toda la información
    previa"): fuga de información confidencial entre tenants, por fuera del RLS.
    """

    # ── consultas de solo lectura (las usa el router) ────────────────────────
    async def list_conversations(self, tenant_id: str, user_id: str | None) -> list[dict]:
        """Conversaciones del tenant (+ del usuario, si se resolvió), recientes primero."""
        async with pool.tenant_connection(tenant_id) as conn:
            if user_id:
                cur = await conn.execute(
                    "SELECT id, title, created_at, updated_at FROM assistant_conversations "
                    "WHERE user_id = %s::uuid ORDER BY updated_at DESC",
                    (user_id,),
                )
            else:
                cur = await conn.execute(
                    "SELECT id, title, created_at, updated_at FROM assistant_conversations "
                    "ORDER BY updated_at DESC"
                )
            rows = await cur.fetchall()
        return [
            {"id": str(r[0]), "title": r[1],
             "created_at": r[2].isoformat(), "updated_at": r[3].isoformat()}
            for r in rows
        ]

    async def list_messages(self, tenant_id: str, conversation_id: str) -> list[dict]:
        """Mensajes de una conversación del tenant. Ajena/inexistente → ConversationNotFound."""
        conversation_id = _require_uuid(conversation_id)
        async with pool.tenant_connection(tenant_id) as conn:
            owned = await (await conn.execute(
                "SELECT 1 FROM assistant_conversations WHERE id = %s::uuid",
                (conversation_id,),
            )).fetchone()
            if not owned:
                raise ConversationNotFound(conversation_id)
            rows = await (await conn.execute(
                "SELECT id, role, content, created_at FROM assistant_messages "
                "WHERE conversation_id = %s::uuid ORDER BY created_at, id",
                (conversation_id,),
            )).fetchall()
        return [
            {"id": str(r[0]), "role": r[1], "content": r[2], "created_at": r[3].isoformat()}
            for r in rows
        ]

    async def resolve_user_id(self, tenant_id: str, email: str | None) -> str | None:
        """user_id del despacho a partir del email del JWT (bajo RLS). None si no resuelve."""
        if not email:
            return None
        async with pool.tenant_connection(tenant_id) as conn:
            row = await (await conn.execute(
                "SELECT id FROM users WHERE lower(email) = lower(%s) LIMIT 1", (email,),
            )).fetchone()
        return str(row[0]) if row else None

    # ── el turno del asistente ────────────────────────────────────────────────
    async def chat(
        self,
        tenant_id: str,
        user_id: str | None,
        conversation_id: str | None,
        message: str,
    ) -> tuple[str, str]:
        """Un turno de conversación libre. Devuelve (conversation_id, respuesta).

        (a) crea la conversación si no existe (título = primeras palabras);
        (b) carga el historial PREVIO (últimos _HISTORY_MAX_MESSAGES) y añade el
            mensaje del abogado EN MEMORIA — no se persiste todavía: si el modelo
            falla, no queda un turno 'user' huérfano que se duplique al reintentar;
        (c) arma system (SOUL + comunicación + instrucción del asistente) + historial;
        (d) comprime el historial si supera el umbral (55% de la ventana); si la
            compresión falla, trunca SIN LLM y el turno continúa;
        (e) llama call_llm(task='main') en un thread (política del tenant ya fijada);
        (f) persiste user + assistant JUNTOS (misma transacción) tras el éxito.
        """
        text = (message or "").strip()
        if not text:
            raise ValueError("El mensaje está vacío.")

        # (a) + (b) validación/creación de la conversación + lectura del historial
        # previo — una sola transacción bajo RLS. Solo los últimos N mensajes viajan
        # al modelo (subquery DESC LIMIT, reordenada ASC para el orden cronológico);
        # los más antiguos siguen en DB.
        if conversation_id:
            conversation_id = _require_uuid(conversation_id)
        async with pool.tenant_connection(tenant_id) as conn:
            if conversation_id:
                owned = await (await conn.execute(
                    "SELECT 1 FROM assistant_conversations WHERE id = %s::uuid",
                    (conversation_id,),
                )).fetchone()
                if not owned:
                    # Fail-closed: la conversación de otro tenant es invisible → no existe.
                    raise ConversationNotFound(conversation_id)
            else:
                row = await (await conn.execute(
                    "INSERT INTO assistant_conversations (tenant_id, user_id, title) "
                    "VALUES (%s::uuid, %s::uuid, %s) RETURNING id",
                    (tenant_id, user_id, _make_title(text)),
                )).fetchone()
                conversation_id = str(row[0])

            history_rows = await (await conn.execute(
                "SELECT role, content FROM ("
                "  SELECT role, content, created_at, id FROM assistant_messages"
                "  WHERE conversation_id = %s::uuid"
                "  ORDER BY created_at DESC, id DESC LIMIT %s"
                ") ultimos ORDER BY created_at, id",
                (conversation_id, _HISTORY_MAX_MESSAGES),
            )).fetchall()

        # El mensaje del turno actual va EN MEMORIA al final del historial (se persiste
        # en (f), junto con la respuesta).
        history = [{"role": r[0], "content": r[1]} for r in history_rows]
        history.append({"role": "user", "content": text})

        # Herramienta v1 (acotada, sin framework — reales en CP-B4): si el abogado
        # pregunta por sus asuntos/borradores, el modelo ve el estado real bajo RLS.
        # Se inyecta SOLO en el mensaje que viaja al modelo, no en el persistido.
        if _asks_about_matters(text):
            matters_block = await self._matters_block(tenant_id)
            if matters_block:
                history[-1] = {
                    "role": "user",
                    "content": f"{history[-1]['content']}\n\n{matters_block}",
                }

        # (d) compresión ANTES de llamar: compresor NUEVO por turno (nunca compartido
        # entre requests/tenants — ver docstring de la clase). Decide con su umbral
        # (55% de la ventana) y devuelve el historial intacto si no aplica. Corre en
        # thread porque su resumen usa call_llm síncrono (task='compression'). Si la
        # compresión falla (excepción del compresor o de su LLM), NO se propaga 502:
        # truncado duro sin LLM y el turno sigue.
        # TODO: persistir el resumen comprimido por conversación (evita recomprimir cada turno) — CP futuro.
        compressor = ContextCompressor()
        try:
            history = await asyncio.to_thread(
                compressor.compress, history, config.MIA_CONTEXT_WINDOW,
                tenant_id=tenant_id,
            )
            if compressor.last_compressed:
                logger.info(
                    "asistente: historial comprimido (%d → %d tokens) conv=%s",
                    compressor.last_tokens_before, compressor.last_tokens_after,
                    conversation_id,
                )
        except Exception:  # noqa: BLE001 — no poder resumir nunca tumba el turno
            logger.warning(
                "asistente: la compresión falló; se aplica truncado duro sin LLM conv=%s",
                conversation_id, exc_info=True,
            )
            history = _truncate_history(history)

        # (c) + (e) system (sin matter) + historial → task='main'. La política de modelo
        # del tenant ya está en el ContextVar (middleware CP2); to_thread la propaga.
        messages = [{"role": "system", "content": build_assistant_system(tenant_id)}, *history]
        resp = await asyncio.to_thread(llm.call_llm, messages, task="main")
        reply = (resp.choices[0].message.content or "").strip()

        # (f) persistir user + assistant JUNTOS y refrescar updated_at — una sola
        # transacción tras el éxito del modelo. clock_timestamp() (no now()): dentro de
        # una misma transacción now() es constante y el orden (created_at, id) con ids
        # uuid aleatorios sería ambiguo; clock_timestamp() avanza entre inserts.
        async with pool.tenant_connection(tenant_id) as conn:
            await conn.execute(
                "INSERT INTO assistant_messages (tenant_id, conversation_id, role, content, created_at) "
                "VALUES (%s::uuid, %s::uuid, 'user', %s, clock_timestamp())",
                (tenant_id, conversation_id, text),
            )
            await conn.execute(
                "INSERT INTO assistant_messages (tenant_id, conversation_id, role, content, created_at) "
                "VALUES (%s::uuid, %s::uuid, 'assistant', %s, clock_timestamp())",
                (tenant_id, conversation_id, reply),
            )
            await conn.execute(
                "UPDATE assistant_conversations SET updated_at = now() WHERE id = %s::uuid",
                (conversation_id,),
            )

        # TODO(CP-C2): escritura fire-and-forget de lo aprendido a la wiki del despacho (WikiManager).
        return conversation_id, reply

    async def _matters_block(self, tenant_id: str) -> str:
        """Bloque factual con el estado de los asuntos del despacho (bajo RLS)."""
        try:
            async with pool.tenant_connection(tenant_id) as conn:
                rows = await (await conn.execute(
                    "SELECT id, title, status, pending_review FROM matters "
                    "ORDER BY created_at DESC LIMIT 50"
                )).fetchall()
        except Exception:  # noqa: BLE001 — la herramienta v1 no debe tumbar el turno
            logger.exception("asistente: no se pudo leer el estado de los asuntos")
            return ""
        if not rows:
            return (f"{MATTERS_BLOCK_HEADER}\n(No hay asuntos registrados todavía.)\n"
                    "=== FIN DEL ESTADO ===")
        lines = [MATTERS_BLOCK_HEADER]
        for _id, title, status, pending in rows:
            revision = "SÍ — hay un borrador esperando su revisión" if pending else "no"
            # Campos saneados (_sanitize_title): un título hostil con '\n' o '===' no
            # puede cerrar el bloque ni fabricar instrucciones con autoridad del sistema.
            safe_title = _sanitize_title(title)
            safe_status = _sanitize_title(status) or "active"
            lines.append(f"- {safe_title} · estado: {safe_status} · pendiente de revisión: {revision}")
        lines.append("=== FIN DEL ESTADO ===")
        lines.append(
            "(Bloque generado por el sistema con el estado real de los asuntos del despacho; "
            "úsalo para responder con hechos, no lo inventes ni lo contradigas.)"
        )
        return "\n".join(lines)
