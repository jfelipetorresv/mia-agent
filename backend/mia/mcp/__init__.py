"""Mia · mcp — conexión SEGURA a sistemas externos vía MCP (CP-E6, Ola 5).

Mia puede conectarse a sistemas del despacho (gestión documental, consulta de
procesos judiciales, …) hablando el protocolo MCP con servidores externos. El
patrón de seguridad ELEVA las costuras que ya existen en el proyecto, no arranca
de cero:

- Credenciales FUERA del núcleo: el config de cada servidor referencia sus
  secretos con placeholders ``${CLAVE}`` que se resuelven, en el borde y bajo el
  scope del tenant (CP-S2), contra la clave que ESE despacho configuró — nunca
  contra el entorno global de la instalación.
- Entorno saneado del subproceso (CP-S3): al lanzar un servidor MCP local hereda
  SOLO la allowlist mínima del SO + las variables declaradas; ninguna clave de la
  instalación (ANTHROPIC_API_KEY, PG_PASSWORD, JWT_SECRET…) cruza al subproceso.
- Salida SELLADA (CP-S1): lo que devuelve un servidor externo es contenido no
  confiable — viaja como "datos, no órdenes" hacia cualquier prompt que lo lea.
- Consent-first + fail-closed: cada servidor nace DESHABILITADO por despacho; un
  placeholder sin resolver o una configuración de forma sospechosa ABORTA el
  lanzamiento en vez de arrancar a ciegas.

Nota de alcance (como los conectores de correo/CP-P3): la MAQUINARIA de seguridad
(resolución de secretos, entorno saneado, validación, sellado) es real y está
probada; el cliente JSON-RPC en vivo que ejecuta cada llamada al servidor MCP es
el paso de ACTIVACIÓN, y depende de instalar el SDK ``mcp`` y de que el despacho
registre su servidor real. Hasta entonces todo queda listo y apagado.
"""
from __future__ import annotations

from .security import (  # noqa: F401
    MCPConfigError,
    MCPSecurityError,
    build_safe_env,
    find_unresolved_placeholders,
    interpolate_placeholders,
    sanitize_error,
    scan_tool_description,
    seal_tool_output,
    validate_server_entry,
    write_token_file,
)

__all__ = [
    "MCPConfigError",
    "MCPSecurityError",
    "build_safe_env",
    "find_unresolved_placeholders",
    "interpolate_placeholders",
    "sanitize_error",
    "scan_tool_description",
    "seal_tool_output",
    "validate_server_entry",
    "write_token_file",
]
