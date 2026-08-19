"""Mia · mcp.client — lanzamiento y consumo del cliente JSON-RPC de un servidor MCP (CP-E6b).

Hoy `mcp.service.resolve_server` deja un ``ResolvedMCPServer`` (comando + args + entorno ya
saneados y verificados) sin consumidor: nadie lo lanza ni ofrece sus tools. Este módulo es
ese consumidor — el SDK oficial ``mcp`` habla el protocolo por stdio; aquí solo se cablea
con el mismo cuidado de seguridad que el resto de CP-E6:

  - El subproceso corre en una carpeta SANDBOX propia del despacho (``sandbox_dir``), nunca
    en el cwd del proceso de Mia — un servidor hostil que liste "el directorio actual" no
    ve el código ni los datos de la instalación.
  - `initialize()` lleva un timeout duro: un servidor colgado no cuelga el turno del abogado.
  - El subproceso se cierra SIEMPRE (context managers del SDK), incluso si algo lanza a
    mitad de una llamada — nunca queda un `npx`/`python` huérfano.
  - Cada tool listada pasa por `security.scan_tool_description` (aviso, no bloqueo) y viaja
    con su nombre NAMESPACED (`{slug}__{tool}`) para no chocar entre servidores.
  - Toda salida de una tool sale SELLADA (`security.seal_tool_output`, CP-S1): contenido no
    confiable, jamás instrucciones — mismo contrato que `_notebooklm_context`.
"""
from __future__ import annotations

import asyncio
import logging
from contextlib import asynccontextmanager
from datetime import timedelta
from pathlib import Path
from typing import Any, AsyncIterator

from mcp import ClientSession, StdioServerParameters, types
from mcp.client.stdio import stdio_client

from .. import config
from . import security
from .service import ResolvedMCPServer

logger = logging.getLogger("mia.mcp.client")

# Un servidor colgado en el handshake no debe colgar el turno del abogado.
_INIT_TIMEOUT_S = 20
# Ídem para una llamada a tool individual (puede pegarle a red/disco de terceros).
_CALL_TIMEOUT_S = 60


def sandbox_dir(tenant_id: str) -> Path:
    """Carpeta SANDBOX del subproceso de un servidor MCP para ESTE despacho.

    Nunca el cwd de Mia: un servidor MCP hostil (o simplemente mal escrito) que liste
    "el directorio actual" no debe ver ni el código fuente ni los datos de otros despachos.
    Vive bajo $MIA_HOME (por instalación), particionada por tenant (aislamiento entre
    despachos, mismo espíritu que el resto de rutas de datos por tenant)."""
    d = config.MIA_HOME / "mcp_sandbox" / str(tenant_id)
    d.mkdir(parents=True, exist_ok=True)
    return d


@asynccontextmanager
async def open_session(
    resolved: ResolvedMCPServer, tenant_id: str,
) -> AsyncIterator[ClientSession]:
    """Lanza el subproceso del servidor MCP y entrega una `ClientSession` YA inicializada.

    Cierra SIEMPRE el subproceso al salir del `with` (incluida una excepción a mitad de
    turno): son los context managers anidados del SDK (`stdio_client` + `ClientSession`)
    los que garantizan eso — no hay un `try/finally` propio que pueda olvidarse."""
    params = StdioServerParameters(
        command=resolved.command,
        args=list(resolved.args),
        env=dict(resolved.env),
        cwd=str(sandbox_dir(tenant_id)),
    )
    async with stdio_client(params) as (read_stream, write_stream):
        async with ClientSession(read_stream, write_stream) as session:
            await asyncio.wait_for(session.initialize(), timeout=_INIT_TIMEOUT_S)
            yield session


def _namespaced(slug: str, tool_name: str) -> str:
    return f"{slug}__{tool_name}"


async def list_tools_openai(session: ClientSession, slug: str) -> list[dict]:
    """Tools de la sesión, en formato function-calling de OpenAI, con nombre NAMESPACED
    (``{slug}__{tool}``) para que dos servidores no choquen si declaran el mismo nombre.

    Cada descripción pasa por `security.scan_tool_description`: SOLO deja un WARNING en el
    log si tiene forma de inyección de prompt — no bloquea (un falso positivo no debe
    tumbar un servidor legítimo; la defensa dura es el sellado de la SALIDA, no de la
    descripción de entrada)."""
    result = await session.list_tools()
    out: list[dict] = []
    for tool in result.tools:
        description = tool.description or ""
        security.scan_tool_description(slug, tool.name, description)
        out.append({
            "type": "function",
            "function": {
                "name": _namespaced(slug, tool.name),
                "description": description,
                "parameters": tool.inputSchema or {"type": "object", "properties": {}},
            },
        })
    return out


def _extract_text(result: types.CallToolResult) -> str:
    parts = [block.text for block in result.content if isinstance(block, types.TextContent)]
    return "\n".join(parts)


async def call_tool_sealed(
    session: ClientSession, server_label: str, name: str, arguments: dict[str, Any] | None,
) -> str:
    """Llama la tool y devuelve su salida YA SELLADA (CP-S1): contenido no confiable, nunca
    instrucciones para el modelo que la lea. Un error del servidor (`isError`) se redacta
    con `sanitize_error` antes de sellarse — el texto de error de un tercero puede llevar
    fragmentos de credenciales o rutas internas suyas."""
    result = await session.call_tool(
        name, arguments or {}, read_timeout_seconds=timedelta(seconds=_CALL_TIMEOUT_S))
    text = _extract_text(result)
    if result.isError:
        text = security.sanitize_error(text or "La herramienta devolvió un error.")
    return security.seal_tool_output(server_label, text)
