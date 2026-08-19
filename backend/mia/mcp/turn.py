"""Mia · mcp.turn — orquesta UNA consulta a los servidores MCP habilitados del despacho (CP-E6b).

Hasta aquí `mcp.service` sabe RESOLVER un servidor de forma segura y `mcp.client` sabe
LANZARLO y hablar su protocolo — pero nadie los conectaba con un turno real. Este módulo es
ese cableado: para una pregunta del investigador (`agents/graph.py::_research_single`),
abre sesión con cada servidor MCP habilitado del despacho, le ofrece sus tools al LLM
(`agent/llm.py::call_llm(tools=...)`) y deja que decida si las usa, hasta un tope de rondas.

Fail-soft TOTAL, mismo contrato que `connectors.notebooklm.consult_notebook` /
`agents/graph.py::_notebooklm_context`:
  - política 'soberano' o error del gate → `[]` servidores → `consult` devuelve None de
    inmediato, CERO overhead para el despacho que no activó nada.
  - un servidor roto (config, arranque, tools) NO tumba a los demás — se omite y se sigue
    con el resto.
  - cualquier excepción durante el ida-y-vuelta con el LLM o las tools → log + None: el
    turno del abogado SIEMPRE continúa con el corpus local, jamás se cae por esto.

Toda salida de tool que entra al LLM llega YA SELLADA (`mcp.client.call_tool_sealed` →
`mcp.security.seal_tool_output`, CP-S1): dato de un tercero, nunca una instrucción.
"""
from __future__ import annotations

import asyncio
import json
import logging
from contextlib import AsyncExitStack
from typing import Any, Optional

from mcp import ClientSession

from ..agent import llm
from . import client, gate, security
from . import service as mcp_service
from .service import ResolvedMCPServer

logger = logging.getLogger("mia.mcp.turn")

_DEFAULT_MAX_ROUNDS = 3

_SYSTEM_PROMPT = (
    "Eres el investigador de Mia consultando sistemas externos que el despacho conectó. "
    "Usa las herramientas disponibles solo si ayudan a responder la pregunta del abogado. "
    "Responde en español, de forma breve y concreta, con lo que hayas encontrado."
)


async def enabled_resolved_servers(tenant_id: str) -> list[ResolvedMCPServer]:
    """Servidores MCP que HOY se pueden consultar para este despacho ([] si ninguno).

    Dos preguntas, cada una en su capa (mismo criterio que `hub_gate.allowed_agents`):
    primero el gate de confidencialidad (política del despacho); luego, solo si permite,
    el catálogo — filtrado a `enabled` Y `configured` (sin secretos faltantes). Un servidor
    que falle al RESOLVERSE (config a medias, forma peligrosa) se omite sin tumbar a los
    demás: nunca un servidor roto bloquea a los sanos."""
    allowed, reason = await gate.mcp_allowed(tenant_id)
    if not allowed:
        logger.info("mcp.turn: consulta MCP no autorizada (tenant=%s, motivo=%s)",
                    tenant_id, reason)
        return []
    try:
        statuses = await mcp_service.mcp_status(tenant_id)
    except Exception:  # noqa: BLE001 — fail-soft: sin estado legible, no hay servidores
        logger.warning("mcp.turn: no se pudo leer el estado de servidores MCP (tenant=%s)",
                       tenant_id, exc_info=True)
        return []

    resolved: list[ResolvedMCPServer] = []
    for st in statuses:
        if not (st.get("enabled") and st.get("configured")):
            continue
        slug = st["slug"]
        try:
            resolved.append(await mcp_service.resolve_server(tenant_id, slug))
        except Exception:  # noqa: BLE001 — un servidor roto no tumba a los demás
            logger.warning(
                "mcp.turn: no se pudo resolver el servidor MCP '%s' (tenant=%s); se omite",
                slug, tenant_id, exc_info=True)
    return resolved


def _tool_call_to_dict(tool_call: Any) -> dict:
    if hasattr(tool_call, "model_dump"):
        return tool_call.model_dump()
    return dict(tool_call)


async def _dispatch_tool_call(
    tool_call: Any, session_for_tool: dict[str, tuple[ClientSession, str]],
) -> str:
    """Ejecuta UNA tool call del LLM y devuelve su salida ya SELLADA (CP-S1)."""
    name = tool_call.function.name
    try:
        arguments = json.loads(tool_call.function.arguments or "{}")
        if not isinstance(arguments, dict):
            arguments = {}
    except (json.JSONDecodeError, TypeError):
        arguments = {}

    entry = session_for_tool.get(name)
    if entry is None:
        return security.seal_tool_output(name, "Esa herramienta ya no está disponible.")
    session, slug = entry
    tool_name = name.split("__", 1)[1] if "__" in name else name
    return await client.call_tool_sealed(session, slug, tool_name, arguments)


async def consult(
    tenant_id: str, question: str, *, max_rounds: int = _DEFAULT_MAX_ROUNDS,
) -> Optional[str]:
    """Consulta los servidores MCP habilitados del despacho y devuelve la respuesta final
    del LLM (texto plano, SIN sellar — el propio LLM la redacta a partir de tool outputs ya
    sellados), o None si no hay nada que consultar o algo falla.

    Devuelve None (sin lanzar) cuando: el gate bloquea, el despacho no habilitó ningún
    servidor, ninguno resuelve, ninguno ofrece tools, o cualquier paso del ida-y-vuelta con
    el LLM falla. En todos esos casos el turno del abogado sigue con el corpus local — esto
    es un ENRIQUECIMIENTO opcional, nunca un punto de fallo (mismo contrato que
    `connectors.notebooklm.consult_notebook`)."""
    q = str(question or "").strip()
    if not q:
        return None

    try:
        servers = await enabled_resolved_servers(tenant_id)
        if not servers:
            return None

        async with AsyncExitStack() as stack:
            tools: list[dict] = []
            session_for_tool: dict[str, tuple[ClientSession, str]] = {}

            for resolved in servers:
                try:
                    session = await stack.enter_async_context(
                        client.open_session(resolved, tenant_id))
                    server_tools = await client.list_tools_openai(session, resolved.slug)
                except Exception:  # noqa: BLE001 — un servidor que no arranca no tumba el turno
                    logger.warning(
                        "mcp.turn: no se pudo abrir/listar tools de '%s' (tenant=%s); se omite",
                        resolved.slug, tenant_id, exc_info=True)
                    continue
                for t in server_tools:
                    session_for_tool[t["function"]["name"]] = (session, resolved.slug)
                tools.extend(server_tools)

            if not tools:
                return None

            messages: list[dict] = [
                {"role": "system", "content": _SYSTEM_PROMPT},
                {"role": "user", "content": q},
            ]
            for _ in range(max_rounds):
                resp = await asyncio.to_thread(
                    llm.call_llm, messages, task="main", tools=tools)
                message = resp.choices[0].message
                tool_calls = getattr(message, "tool_calls", None)
                if not tool_calls:
                    content = str(message.content or "").strip()
                    return content or None

                messages.append({
                    "role": "assistant",
                    "content": message.content or "",
                    "tool_calls": [_tool_call_to_dict(tc) for tc in tool_calls],
                })
                for tc in tool_calls:
                    sealed = await _dispatch_tool_call(tc, session_for_tool)
                    messages.append({
                        "role": "tool", "tool_call_id": tc.id, "content": sealed,
                    })

            logger.info(
                "mcp.turn: %s rondas agotadas sin respuesta final (tenant=%s)",
                max_rounds, tenant_id)
            return None
    except Exception:  # noqa: BLE001 — fail-soft TOTAL: nunca tumba el turno del abogado
        logger.warning("mcp.turn: consulta MCP falló (tenant=%s); se sigue sin ella",
                       tenant_id, exc_info=True)
        return None
