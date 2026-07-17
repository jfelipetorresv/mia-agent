"""Mia · mcp.catalog — catálogo curado de sistemas externos conectables vía MCP (CP-E6).

Espejo del patrón de Hermes (`hermes_cli/mcp_catalog.py`): cada entrada describe un
servidor MCP y NACE DESHABILITADA. El despacho la descubre en su pantalla, la habilita
con sus credenciales y solo entonces Mia puede hablar con ese sistema.

Política del catálogo (deliberadamente conservadora para un producto legal):
- Solo entradas CURADAS aquí (presencia en el catálogo = aprobación). No hay tier
  comunitario ni servidores arbitrarios definidos por el usuario en v1: reduce la
  superficie de una config hostil que ejecute comandos locales.
- Cada entrada declara sus secretos como placeholders ``${CLAVE}``; los valores los
  pone el despacho y viven bajo su scope (CP-S2), nunca en el código ni en el catálogo.
- §G: el abogado ve un nombre en español, sin marcas técnicas.
- Permisos MÍNIMOS: cada entrada recomienda el alcance del token (solo lectura, solo
  las carpetas del despacho…). Mia pide lo menos que necesita.

El `command`/`args` de cada entrada es una PLANTILLA de transporte que el admin
confirma al activar (igual que los flags de los CLIs externos quedan `[VERIFICAR]`
hasta ejecutarse en vivo). La maquinaria de seguridad que los procesa sí es real.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Mapping, Optional


@dataclass(frozen=True)
class MCPEnvSpec:
    """Una variable que el servidor necesita en su entorno. `secret_key` es la clave
    bajo la que el despacho guarda el valor en su scope (None = no es secreto, se
    guarda en claro en la config del despacho, p. ej. una URL base)."""
    env_var: str                 # nombre de la variable de entorno del servidor
    label: str                   # etiqueta en llano para la pantalla (§G)
    secret_key: Optional[str] = None  # clave en el scope de secretos del tenant (si es secreto)
    required: bool = True

    @property
    def is_secret(self) -> bool:
        return self.secret_key is not None


@dataclass(frozen=True)
class MCPServerDescriptor:
    slug: str                    # id público neutro (viaja en URLs; sin marca)
    display_name: str            # §G, español, sin marca
    description: str             # para qué le sirve al despacho, en llano
    command: str                 # plantilla de transporte (se confirma al activar)
    args: tuple[str, ...]
    env_specs: tuple[MCPEnvSpec, ...]
    permissions_note: str        # permisos mínimos recomendados del token
    env_template: Mapping[str, str] = field(default_factory=dict)

    def required_secret_keys(self) -> tuple[str, ...]:
        return tuple(s.secret_key for s in self.env_specs if s.is_secret and s.required)

    def secret_keys(self) -> tuple[str, ...]:
        return tuple(s.secret_key for s in self.env_specs if s.is_secret)

    def plain_env_keys(self) -> tuple[str, ...]:
        """Claves NO secretas (van en claro en la config del despacho: URLs, etc.)."""
        return tuple(s.env_var for s in self.env_specs if not s.is_secret)


def _descriptor(slug, display_name, description, command, args, env_specs,
                permissions_note) -> MCPServerDescriptor:
    # env_template: {ENV_VAR: "${secret_key}"} para los secretos; las no-secretas se
    # inyectan directo desde la config del despacho (no llevan placeholder).
    env_template = {s.env_var: "${" + s.secret_key + "}" for s in env_specs if s.is_secret}
    return MCPServerDescriptor(
        slug=slug, display_name=display_name, description=description,
        command=command, args=tuple(args), env_specs=tuple(env_specs),
        permissions_note=permissions_note, env_template=env_template,
    )


# ── entradas curadas (todas nacen deshabilitadas) ────────────────────────────
CATALOG: dict[str, MCPServerDescriptor] = {
    "gestion-documental": _descriptor(
        slug="gestion-documental",
        display_name="Gestión documental del despacho",
        description=("Deja que Mia consulte los documentos del despacho en tu sistema "
                     "de gestión documental para responder con base en ellos."),
        command="npx",
        args=("-y", "@modelcontextprotocol/server-filesystem", "${DMS_ROOT}"),
        env_specs=(
            MCPEnvSpec("DMS_ROOT", "Carpeta o URL base de la gestión documental",
                       secret_key=None, required=True),
            MCPEnvSpec("DMS_API_TOKEN", "Token de acceso (solo lectura)",
                       secret_key="dms_api_token", required=True),
        ),
        permissions_note=("Usa un token de SOLO LECTURA, limitado a las carpetas del "
                          "despacho. Mia nunca necesita permiso de escritura para consultar."),
    ),
    "consulta-procesos": _descriptor(
        slug="consulta-procesos",
        display_name="Consulta de estados de procesos judiciales",
        description=("Deja que Mia consulte el estado de un proceso en el sistema judicial "
                     "o el proveedor que uses, para traerte las novedades."),
        command="python",
        args=("-m", "mia_mcp_procesos"),
        env_specs=(
            MCPEnvSpec("PROCESOS_API_BASE", "URL del servicio de consulta",
                       secret_key=None, required=True),
            MCPEnvSpec("PROCESOS_API_TOKEN", "Token de consulta (solo lectura)",
                       secret_key="procesos_api_token", required=True),
        ),
        permissions_note=("Token de SOLO CONSULTA. Mia lee estados de procesos; nunca "
                          "radica, responde ni modifica nada en el sistema judicial."),
    ),
}


def list_catalog() -> list[MCPServerDescriptor]:
    return list(CATALOG.values())


def get_descriptor(slug: str) -> Optional[MCPServerDescriptor]:
    return CATALOG.get(slug)
