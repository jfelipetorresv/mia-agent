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
import os
import re
import uuid
from datetime import datetime
from types import SimpleNamespace

from .. import config
from ..agent import llm, prompt_builder
from ..agent.context_compressor import ContextCompressor
from ..agents import untrusted
from ..agents.context_references import (
    expand_context_references,
    parse_context_references,
)
from ..agents.personas import (
    Persona,
    persona_service,
    render_persona_voice,
    resolve_persona_alias,
)
from ..db import pool
from ..onboarding.soul_interview import load_soul_text
from . import reminders as reminders_mod

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

# CP-B3: pregunta por los recordatorios ("qué recordatorios tengo") → bloque de estado.
# (La CREACIÓN de recordatorios es determinista — parse_reminder — y no pasa por aquí.)
_REMINDERS_QUERY_RE = re.compile(r"\brecordatorios?\b", re.IGNORECASE)

# CP-C4: el abogado pide ayuda para configurar/conectar algo → el modelo ve el
# estado REAL del recorrido de configuración y guía con hechos, no de memoria.
# OJO (revisor CP-C4): "configurar"/"conectar" a secas son verbos del español
# JURÍDICO ("se configura la causal…") — el disparador exige un sustantivo del
# dominio de configuración o la frase dirigida a Mia; nunca el verbo solo.
_SETUP_QUERY_RE = re.compile(
    r"(\bobsidian\b|\btelegram\b|\bonedrive\b|google\s*drive|\bmis\s+carpetas\b|"
    r"\bconfig[uú]ra(?:r|me)?\s+a?\s*mia\b|\bconfiguraci[oó]n\s+de\s+mia\b)",
    re.IGNORECASE,
)

SETUP_BLOCK_HEADER = "=== ESTADO DE LA CONFIGURACIÓN DE MIA ==="

# CP-B3: cancelar por chat también es determinista ("cancela el recordatorio de la
# tutela") — el modelo JAMÁS confirma una cancelación que no ocurrió (hallazgo M4).
_REMINDER_CANCEL_RE = re.compile(
    r"\b(cancela(?:me|r)?|elimina(?:r)?|borra(?:r)?|quita(?:r)?)\b.*\brecordatorios?\b",
    re.IGNORECASE | re.DOTALL,
)
_CANCEL_FRAGMENT_RE = re.compile(
    r"\brecordatorios?\s+(?:de|del|de\s+la|para|sobre)\s+(.+)$",
    re.IGNORECASE | re.DOTALL,
)

REMINDERS_BLOCK_HEADER = "=== TUS RECORDATORIOS PENDIENTES ==="

# Respuestas deterministas del flujo de recordatorios (sin LLM: crear un recordatorio
# cambia estado y no puede depender de la interpretación de un modelo).
REMINDER_MISSING_DATE_REPLY = (
    "Con gusto te lo recuerdo, pero necesito saber cuándo. Dime por ejemplo: "
    "«mañana a las 9», «el viernes», «en 2 horas» o «el 15 de agosto»."
)

# "N días hábiles": Mia NO los calcula (festivos y calendario judicial cambian el
# resultado) — se pide la fecha exacta (hallazgo M1, coherente con la regla dura).
REMINDER_BUSINESS_DAYS_REPLY = (
    "Los días hábiles dependen de los festivos y del calendario judicial, y ese "
    "cálculo debe ser tuyo. Dime la fecha exacta (por ejemplo «el 15 de agosto») "
    "y te lo recuerdo ese día."
)

# El despacho aún no tiene canal de avisos (Telegram, opt-in de CP-B2): el
# recordatorio queda guardado y visible en Mia, pero nadie le va a "sonar" (M3).
REMINDER_NO_CHANNEL_WARNING = (
    "Ojo: todavía no tienes activado el canal de avisos por Telegram, así que no "
    "podré escribirte cuando llegue la hora — el recordatorio quedará visible en tu "
    "lista de recordatorios dentro de Mia. Activarlo toma 5 minutos: pídeme la guía "
    "cuando quieras."
)

# REGLA DURA (plan CP-B3 · regla 5 del propietario): un recordatorio que menciona un
# plazo o actuación procesal SIEMPRE se confirma con el abogado — Mia no calcula
# términos legales; la fecha la puso él y debe verificarla contra la fuente oficial.
REMINDER_PROCEDURAL_WARNING = (
    "[VERIFICAR] Esto menciona un plazo o actuación procesal: la fecha me la diste tú "
    "y debes confirmarla contra el expediente o la fuente oficial antes de actuar — "
    "yo no calculo términos legales por mi cuenta."
)

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
    "él mismo contra la fuente oficial antes de actuar. Sobre los RECORDATORIOS: tú NO "
    "puedes crearlos, cancelarlos ni moverlos — eso lo hace el sistema de Mia solo "
    "cuando el abogado lo pide con frases directas como «recuérdame … mañana a las 9» "
    "o «cancela el recordatorio de …», y el sistema siempre responde confirmándolo. "
    "JAMÁS afirmes que un recordatorio quedó creado, cancelado o cambiado: si el "
    "abogado te lo pide y no ves esa confirmación del sistema, dile la frase exacta "
    "que debe escribir para lograrlo."
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


def _sanitize_title(value, max_chars: int = _FIELD_MAX_CHARS) -> str:
    """Sanea un campo que se interpola en un bloque del sistema (defensa de prompt).

    Un título hostil con saltos de línea o '===' podría "cerrar" el bloque
    === ESTADO ACTUAL DE TUS ASUNTOS === y fabricar instrucciones con autoridad del
    sistema. Se colapsa TODO el whitespace (incluidos \\n \\r) a espacios simples, se
    eliminan secuencias de 3+ '=' y se trunca a `max_chars`.

    CP-C4b (revisión capa 2, L1): el tope por defecto (150) está pensado para campos
    cortos de entrada de usuario (títulos de asuntos). El contenido editorial del
    servidor (guía del recorrido) es constante y confiable — se pasa `max_chars`
    amplio para no entregarlo cortado a mitad de oración en el chat.

    CP-S1: delega en la cuarentena central (untrusted.sanitize_field), que suma la
    neutralización de marcadores de sello `<<<`/`>>>` al saneo que ya existía.
    """
    return untrusted.sanitize_field(value, max_chars)


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


def build_assistant_system(tenant_id: str, persona: Persona | None = None) -> str:
    """System del modo asistente: capas del prompt_builder que aplican SIN matter.

    Reutiliza L1 (identidad/SOUL del tenant, vía _identity_layer sobre un estado
    duck-typed) y L5 (comunicación sin jerga, USER_COMMS) y les suma la instrucción
    propia del asistente. Sin SOUL.md (onboarding incompleto) la identidad va vacía
    y el asistente funciona igual (no bloquea).

    CP-E3 (personas): si el abogado invocó una persona, su voz se AÑADE (no reemplaza:
    la identidad del despacho persiste) entre las reglas duras y la instrucción del
    asistente. Se incluye L3 (citación) para que la regla dura anti-invención ([VERIFICAR])
    PRECEDA a la voz de la persona: una persona jamás la relaja (hallazgo capa 2 · el rol
    colorea el tono, no la verificación). Sin persona, la voz va vacía.
    """
    state = SimpleNamespace(identity=load_soul_text(tenant_id) or "")
    parts = [
        prompt_builder._identity_layer(state),      # L1 · identidad / SOUL del tenant
        prompt_builder._citation_layer(state),      # L3 · citación / [VERIFICAR] (regla dura)
        prompt_builder._user_comms_layer(state),    # L5 · comunicación sin jerga (§G)
        render_persona_voice(persona) if persona else "",   # CP-E3 · voz de la persona
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

        # CP-B3 · CREAR o CANCELAR un recordatorio es un flujo DETERMINISTA (sin LLM):
        # cambia estado y no puede depender de que un modelo "entienda". Si el parser
        # reconoce la intención, se ejecuta, se persiste el turno y se responde ya.
        parsed = reminders_mod.parse_reminder(text)
        if parsed is None:
            # Turno de seguimiento (hallazgo B2): Mia acaba de preguntar "¿cuándo?"
            # y el abogado responde solo con la fecha ("mañana a las 9") — se retoma
            # el QUÉ del mensaje anterior; jamás se deja que el modelo "confirme".
            parsed = self._reminder_followup(text, history_rows)
        if parsed is not None:
            reply = await self._handle_reminder_request(tenant_id, user_id, parsed)
            await self._persist_turn(tenant_id, conversation_id, text, reply)
            return conversation_id, reply
        if _REMINDER_CANCEL_RE.search(text):
            reply = await self._handle_reminder_cancel(tenant_id, text)
            await self._persist_turn(tenant_id, conversation_id, text, reply)
            return conversation_id, reply

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

        # CP-B3: pregunta por sus recordatorios → el modelo ve el estado real bajo RLS
        # (mismo patrón que el bloque de asuntos: solo en el mensaje que viaja al modelo).
        if _REMINDERS_QUERY_RE.search(text):
            reminders_block = await self._reminders_block(tenant_id)
            if reminders_block:
                history[-1] = {
                    "role": "user",
                    "content": f"{history[-1]['content']}\n\n{reminders_block}",
                }

        # CP-C4: pide ayuda para configurar/conectar → el modelo ve el estado real
        # del recorrido de configuración (qué está listo y qué falta) y guía con
        # hechos. Solo en el mensaje que viaja al modelo, nunca en el persistido.
        if _SETUP_QUERY_RE.search(text):
            setup_block = await self._setup_block(tenant_id)
            if setup_block:
                history[-1] = {
                    "role": "user",
                    "content": f"{history[-1]['content']}\n\n{setup_block}",
                }

        # CP-E2: adjuntar pruebas por referencia (@expediente:"..."/@carpeta:"..."). En el
        # asistente NO hay recuperación automática, así que la referencia es la única forma
        # de traer evidencia del despacho a la conversación libre. El asistente no tiene
        # asunto en curso → @expediente suelto pide un nombre (matter_id=None). El adjunto va
        # SELLADO (CP-S1) y SOLO en el mensaje que viaja al modelo, nunca en el persistido.
        # Fail-open: si la expansión falla, el turno sigue con el mensaje tal cual.
        # Se expande sobre el contenido ACTUAL de history[-1] (que ya puede traer el
        # bloque de asuntos/recordatorios/configuración) para no pisar esa augmentación:
        # las referencias viven en la parte del abogado; el adjunto se anexa al final.
        if parse_context_references(text):
            try:
                ref_result = await expand_context_references(
                    tenant_id, history[-1]["content"], matter_id=None,
                    context_length=config.MIA_CONTEXT_WINDOW)
                if ref_result.expanded:
                    history[-1] = {"role": "user", "content": ref_result.message}
            except Exception:  # noqa: BLE001 — adjuntar por referencia nunca tumba el turno
                logger.warning("asistente: la expansión de referencias falló conv=%s",
                               conversation_id, exc_info=True)

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

        # CP-E3: persona jurídica invocada por frase en el mensaje del abogado. Se detecta
        # sobre el mensaje ORIGINAL (`text`), no sobre la versión aumentada con bloques de
        # estado/adjuntos. El alias de motor se acota BAJO la política activa del despacho
        # (ContextVar del middleware) → nunca escala a la nube. FAIL-OPEN (simétrico a
        # stream.py): si algo falla resolviendo o acotando la persona, el turno sigue SIN
        # persona (system y motor idénticos a hoy) — aplicar una persona nunca tumba el turno.
        persona = None
        persona_alias = None
        try:
            persona = await persona_service.resolve_for_turn(tenant_id, text)
            persona_alias = resolve_persona_alias(persona.model_tier) if persona else None
        except Exception:  # noqa: BLE001 — §G: aplicar una persona jamás tumba el turno
            logger.warning("chat: no se pudo aplicar la persona (conv=%s)", conversation_id,
                           exc_info=True)
            persona = None
            persona_alias = None

        # (c) + (e) system (sin matter) + historial → task='main'. La política de modelo
        # del tenant ya está en el ContextVar (middleware CP2); to_thread la propaga.
        messages = [{"role": "system", "content": build_assistant_system(tenant_id, persona)},
                    *history]
        resp = await asyncio.to_thread(llm.call_llm, messages, task="main", model=persona_alias)
        reply = (resp.choices[0].message.content or "").strip()

        # (f) persistir user + assistant JUNTOS tras el éxito del modelo.
        await self._persist_turn(tenant_id, conversation_id, text, reply)

        # TODO(CP-C2): escritura fire-and-forget de lo aprendido a la wiki del despacho (WikiManager).
        return conversation_id, reply

    async def _persist_turn(
        self, tenant_id: str, conversation_id: str, user_text: str, reply: str
    ) -> None:
        """Persiste user + assistant JUNTOS y refresca updated_at — una sola
        transacción tras el éxito del turno. clock_timestamp() (no now()): dentro de
        una misma transacción now() es constante y el orden (created_at, id) con ids
        uuid aleatorios sería ambiguo; clock_timestamp() avanza entre inserts."""
        async with pool.tenant_connection(tenant_id) as conn:
            await conn.execute(
                "INSERT INTO assistant_messages (tenant_id, conversation_id, role, content, created_at) "
                "VALUES (%s::uuid, %s::uuid, 'user', %s, clock_timestamp())",
                (tenant_id, conversation_id, user_text),
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

    def _reminder_followup(
        self, text: str, history_rows: list
    ) -> reminders_mod.ParsedReminder | None:
        """Retoma el recordatorio cuando el abogado responde SOLO la fecha (B2).

        Aplica únicamente si el último mensaje de la conversación fue la pregunta
        determinista de Mia ("¿cuándo?" / "días hábiles") y el texto actual trae
        una fecha reconocible; el QUÉ sale del mensaje anterior del abogado."""
        if len(history_rows) < 2:
            return None
        last_role, last_content = history_rows[-1][0], history_rows[-1][1]
        prev_role, prev_content = history_rows[-2][0], history_rows[-2][1]
        if last_role != "assistant" or last_content not in (
            REMINDER_MISSING_DATE_REPLY, REMINDER_BUSINESS_DAYS_REPLY
        ) or prev_role != "user":
            return None
        due = reminders_mod.parse_when(text)
        if due is None:
            return None
        prev_parsed = reminders_mod.parse_reminder(prev_content)
        subject = prev_parsed.subject if prev_parsed else _sanitize_title(prev_content)
        procedural = (prev_parsed.is_procedural if prev_parsed else
                      reminders_mod.is_procedural_text(prev_content))
        return reminders_mod.ParsedReminder(
            subject, due, procedural or reminders_mod.is_procedural_text(text)
        )

    async def _owns_notify_channel(self, tenant_id: str) -> bool:
        """True si ESTE despacho recibirá los avisos: Telegram configurado y el
        usuario del puente (MIA_BRIDGE_EMAIL) pertenece al tenant — se verifica bajo
        RLS: si el correo es de otro despacho, aquí no existe (hallazgo M3)."""
        from ..channels import notify

        bridge_email = (os.getenv("MIA_BRIDGE_EMAIL") or "").strip()
        if not bridge_email or not notify.telegram_configured():
            return False
        try:
            async with pool.tenant_connection(tenant_id) as conn:
                row = await (await conn.execute(
                    "SELECT 1 FROM users WHERE lower(email) = lower(%s) LIMIT 1",
                    (bridge_email,),
                )).fetchone()
            return row is not None
        except Exception:  # noqa: BLE001 — ante la duda, avisar que no hay canal
            logger.exception("no se pudo verificar el canal de avisos (tenant=%s)", tenant_id)
            return False

    async def _handle_reminder_request(
        self, tenant_id: str, user_id: str | None, parsed: reminders_mod.ParsedReminder
    ) -> str:
        """Crea el recordatorio (o pide la fecha) y arma la confirmación determinista.

        REGLA DURA: si menciona un plazo/actuación procesal, la confirmación lleva
        [VERIFICAR] — la fecha la puso el abogado y la confirma él (Mia nunca
        calcula términos legales; "días hábiles" no se calculan, se pide la fecha)."""
        if parsed.due_at is None:
            return (REMINDER_BUSINESS_DAYS_REPLY if parsed.business_days
                    else REMINDER_MISSING_DATE_REPLY)
        await reminders_mod.ReminderService().create(
            tenant_id, user_id, parsed.subject, parsed.due_at, parsed.is_procedural
        )
        reply = (
            f"Listo. Te lo recordaré el {reminders_mod.format_due(parsed.due_at)}: "
            f"«{parsed.subject}»."
        )
        if parsed.is_procedural:
            reply += f"\n\n{REMINDER_PROCEDURAL_WARNING}"
        if not await self._owns_notify_channel(tenant_id):
            # Promesa honesta (M3): sin canal de avisos, el recordatorio no "suena".
            reply += f"\n\n{REMINDER_NO_CHANNEL_WARNING}"
        return reply

    async def _handle_reminder_cancel(self, tenant_id: str, text: str) -> str:
        """Cancela por chat, de forma determinista (M4): por fragmento («cancela el
        recordatorio de la tutela»), o directo si solo hay uno; si es ambiguo, lista
        los pendientes y pide precisión — nunca adivina ni deja confirmar al modelo."""
        service = reminders_mod.ReminderService()
        try:
            pending = await service.list_pending(tenant_id)
        except Exception:  # noqa: BLE001
            logger.exception("asistente: no se pudieron leer los recordatorios (cancel)")
            return "No pude consultar tus recordatorios en este momento. Intenta de nuevo."
        if not pending:
            return "No tienes recordatorios pendientes, así que no hay nada que cancelar."

        frag_m = _CANCEL_FRAGMENT_RE.search(text)
        fragment = (frag_m.group(1).strip(" ,.;:¿?¡!«»\"'") if frag_m else "")
        matches = [r for r in pending if fragment and fragment.lower() in r["text"].lower()]
        target = None
        if len(matches) == 1:
            target = matches[0]
        elif not fragment and len(pending) == 1:
            target = pending[0]
        if target is not None:
            cancelled = await service.cancel(tenant_id, target["id"])
            if cancelled:
                return f"Listo, cancelé el recordatorio: «{target['text']}»."
            return "Ese recordatorio ya no estaba pendiente."
        lines = [
            "Tengo estos recordatorios pendientes y no estoy segura de cuál cancelar:"
        ]
        lines += [
            f"- «{r['text']}» (para el "
            f"{reminders_mod.format_due(datetime.fromisoformat(r['due_at']))})"
            for r in pending
        ]
        lines.append("Dime, por ejemplo: «cancela el recordatorio de "
                     f"{pending[0]['text'][:40]}».")
        return "\n".join(lines)

    async def _setup_block(self, tenant_id: str) -> str:
        """Bloque factual con el estado de configuración de Mia (CP-C4, bajo RLS)."""
        try:
            # Import perezoso: evita acoplar el módulo del asistente a la capa API
            # en tiempo de import (la capa API sí importa al asistente).
            from ..api.routes.setup import collect_setup_status

            status = await collect_setup_status(tenant_id)
        except Exception:  # noqa: BLE001 — la herramienta v1 no debe tumbar el turno
            logger.exception("asistente: no se pudo leer el estado de configuración")
            return ""
        lines = [SETUP_BLOCK_HEADER, _sanitize_title(status.get("mensaje"))]
        for paso in status.get("pasos", []):
            lines.append(
                f"- {_sanitize_title(paso.get('titulo'))} · {paso.get('estado')} · "
                f"{_sanitize_title(paso.get('detalle'))}"
            )
        # CP-C4b: la guía COMPLETA del siguiente paso pendiente (qué es, para qué,
        # cómo) para que el asistente acompañe como un onboarding, no solo enumere.
        siguiente = status.get("siguiente")
        guia = next((p.get("guia") for p in status.get("pasos", [])
                     if p.get("id") == siguiente), None) if siguiente else None
        if guia:
            # L1: contenido editorial del servidor (confiable) → sin truncar a 150,
            # pero igual saneado contra '===' y saltos de línea (defensa de prompt).
            lines.append("Guía del siguiente paso pendiente:")
            lines.append(f"  Qué es: {_sanitize_title(guia.get('que_es'), 400)}")
            lines.append(f"  Para qué sirve: {_sanitize_title(guia.get('para_que'), 400)}")
            for i, paso_como in enumerate(guia.get("como") or [], start=1):
                lines.append(f"  Cómo, paso {i}: {_sanitize_title(paso_como, 400)}")
        lines.append("=== FIN DEL ESTADO DE CONFIGURACIÓN ===")
        lines.append(
            "(Bloque generado por el sistema con el estado real de la configuración; "
            "acompaña al abogado como un onboarding: explica qué es cada pieza, para "
            "qué le sirve al despacho y el paso a paso, con estos hechos. Los pasos "
            "se hacen desde las pantallas de Mia; el bot de Telegram se crea con la "
            "guía integrada.)"
        )
        return "\n".join(lines)

    async def _reminders_block(self, tenant_id: str) -> str:
        """Bloque factual con los recordatorios pendientes del despacho (bajo RLS)."""
        try:
            pending = await reminders_mod.ReminderService().list_pending(tenant_id)
        except Exception:  # noqa: BLE001 — la herramienta v1 no debe tumbar el turno
            logger.exception("asistente: no se pudieron leer los recordatorios")
            return ""
        if not pending:
            return (f"{REMINDERS_BLOCK_HEADER}\n(No hay recordatorios pendientes.)\n"
                    "=== FIN DE LOS RECORDATORIOS ===")
        lines = [REMINDERS_BLOCK_HEADER]
        for r in pending:
            due = reminders_mod.format_due(datetime.fromisoformat(r["due_at"]))
            marca = " · [VERIFICAR] plazo procesal (la fecha la confirma el abogado)" \
                if r["is_procedural"] else ""
            lines.append(f"- {_sanitize_title(r['text'])} · para el {due}{marca}")
        lines.append("=== FIN DE LOS RECORDATORIOS ===")
        lines.append(
            "(Bloque generado por el sistema con los recordatorios reales del despacho; "
            "úsalo para responder con hechos, no lo inventes ni lo contradigas.)"
        )
        return "\n".join(lines)

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
