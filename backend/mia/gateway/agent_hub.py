"""Mia · gateway.agent_hub — invocación de CLIs de agentes externos (1e · PASO 1).

El hub corre CADA CLI como subproceso AISLADO. Principios (riesgo #1 de
bugs-and-risks.md + spec 1e):

- NUNCA hardcodea rutas de binarios: los detecta en PATH (`shutil.which`) o los lee
  de una variable de entorno de override. Si no los encuentra → "no disponible".
- Subprocess con ARGUMENTOS EN LISTA y `shell=False`: Python pasa cada argumento
  intacto, así que una ruta con espacio ("Mia-Super Agent") NO se rompe ni necesita
  comillas manuales (que son frágiles y propensas a inyección). Es la mitigación
  robusta del riesgo #1 — mejor que entrecomillar a mano (decisión D2).
- `timeout=120s`. Captura stdout/stderr. Ante CUALQUIER fallo (binario ausente,
  exit ≠ 0, timeout, excepción) → loguea y DEVUELVE un string de error descriptivo;
  NUNCA propaga una excepción al caller (graceful degradation).
- Los CLIs son OPCIONALES por tenant; por defecto todos deshabilitados (hub_config).

§G: el abogado nunca ve marcas ("Hermes", "Claude Code"); ve un `display_name` en
español. El `slug` (id público neutro) es lo que viaja en las URLs de settings.

NOTA [VERIFICAR]: los flags de invocación de cada CLI (`build_args`) están SIN
confirmar contra el `--help` real de cada herramienta; el gate mockea el subprocess,
así que no se ejercitan. Confirmar antes de invocar en vivo (decisión D3).
"""
from __future__ import annotations

import logging
import os
import shutil
import subprocess
from dataclasses import dataclass
from typing import Callable, Optional

logger = logging.getLogger("mia.gateway.agent_hub")

DEFAULT_TIMEOUT = 120  # segundos


@dataclass(frozen=True)
class Connector:
    key: str                                  # id interno (hermes, claude_code, …)
    slug: str                                 # id público neutro (URLs; sin marca)
    display_name: str                         # nombre en español para el abogado (§G)
    bin_candidates: tuple[str, ...]           # nombres a buscar en PATH
    env_override: str                         # var de entorno con ruta explícita
    build_args: Callable[[str], list[str]]    # (prompt) -> args DESPUÉS del binario


def _prompt_flag(flag: str) -> Callable[[str], list[str]]:
    return lambda prompt: [flag, prompt]


def _subcmd(subcmd: str) -> Callable[[str], list[str]]:
    return lambda prompt: [subcmd, prompt]


# Los 5 conectores del spec. build_args = [VERIFICAR] (no se ejercita en el gate).
CONNECTORS: dict[str, Connector] = {
    "hermes": Connector("hermes", "investigacion", "Asistente de investigación jurídica",
                        ("hermes",), "MIA_HERMES_BIN", _prompt_flag("-p")),
    "claude_code": Connector("claude_code", "documentos", "Editor de documentos",
                             ("claude", "claude-code"), "MIA_CLAUDE_BIN", _prompt_flag("-p")),
    "codex": Connector("codex", "automatizacion", "Asistente de automatización",
                       ("codex",), "MIA_CODEX_BIN", _subcmd("exec")),
    "antigravity": Connector("antigravity", "escritorio", "Asistente de escritorio",
                             ("antigravity",), "MIA_ANTIGRAVITY_BIN", _prompt_flag("-p")),
    "openclaw": Connector("openclaw", "navegacion", "Asistente de navegación web",
                          ("openclaw",), "MIA_OPENCLAW_BIN", _prompt_flag("-p")),
}

_SLUG_TO_KEY = {c.slug: c.key for c in CONNECTORS.values()}


def slug_to_key(slug: str) -> Optional[str]:
    """Traduce el id público (slug) al id interno del conector. None si no existe."""
    return _SLUG_TO_KEY.get(slug)


def _default_runner(args: list[str], *, cwd: Optional[str], timeout: int) -> tuple[int, str, str]:
    """Corre el subproceso con `shell=False` (args en lista → espacios seguros)."""
    proc = subprocess.run(args, capture_output=True, text=True, timeout=timeout,
                          cwd=cwd, shell=False)
    return proc.returncode, proc.stdout, proc.stderr


class AgentHub:
    """Invoca CLIs externos como subprocesos aislados, con degradación con gracia.

    `runner` se inyecta en los tests (mock del subprocess). `env` permite override de
    las rutas de binarios (default `os.environ`). `cwd` es el directorio de trabajo
    del subproceso (puede contener espacios; va como parámetro, no como string).
    """

    def __init__(self, *, runner=None, env: Optional[dict] = None,
                 cwd: Optional[str] = None, timeout: int = DEFAULT_TIMEOUT) -> None:
        self._runner = runner or _default_runner
        self._env = env if env is not None else os.environ
        self._cwd = cwd
        self._timeout = timeout

    # -- detección de binarios --------------------------------------------------
    def resolve_binary(self, key: str) -> Optional[str]:
        """Ruta del binario: override por env (si el archivo existe) > PATH. None si falta."""
        c = CONNECTORS[key]
        override = self._env.get(c.env_override)
        if override and os.path.isfile(override):
            return override
        for name in c.bin_candidates:
            found = shutil.which(name)
            if found:
                return found
        return None

    def list_available(self) -> dict:
        """Estado de cada conector. NUNCA crashea (cada resolución va protegida)."""
        out: dict = {}
        for key, c in CONNECTORS.items():
            try:
                binary = self.resolve_binary(key)
            except Exception as e:  # noqa: BLE001
                logger.warning("resolver binario de %s falló: %s", key, e)
                binary = None
            out[key] = {
                "key": key,
                "slug": c.slug,
                "display_name": c.display_name,
                "installed": binary is not None,
                "binary": binary,
            }
        return out

    # -- invocación genérica ----------------------------------------------------
    def invoke(self, key: str, prompt: str, tenant_id: str) -> str:
        """Invoca un conector. Devuelve stdout, o un string de error descriptivo.
        NUNCA lanza excepción al caller (graceful degradation)."""
        c = CONNECTORS.get(key)
        if c is None:
            return f"[error] Conector desconocido: {key}"
        binary = self.resolve_binary(key)
        if binary is None:
            logger.info("conector %s no disponible (tenant=%s)", key, tenant_id)
            return f"[no disponible] '{c.display_name}' no está instalado en este equipo."

        args = [binary, *c.build_args(prompt)]  # ruta intacta como primer arg (espacios OK)
        try:
            code, stdout, stderr = self._runner(args, cwd=self._cwd, timeout=self._timeout)
        except subprocess.TimeoutExpired:
            logger.warning("conector %s: timeout %ss (tenant=%s)", key, self._timeout, tenant_id)
            return f"[error] '{c.display_name}' no respondió en {self._timeout}s."
        except Exception as e:  # noqa: BLE001 — graceful degradation: nunca propagar
            logger.warning("conector %s falló: %s (tenant=%s)", key, e, tenant_id)
            return f"[error] '{c.display_name}' falló: {e}"

        if code != 0:
            logger.warning("conector %s exit=%s stderr=%s", key, code, (stderr or "")[:300])
            return f"[error] '{c.display_name}' terminó con código {code}: {(stderr or '').strip()[:300]}"
        return stdout

    # -- métodos nombrados (los 5 del spec) -------------------------------------
    def invoke_hermes(self, prompt: str, tenant_id: str) -> str:
        return self.invoke("hermes", prompt, tenant_id)

    def invoke_claude_code(self, prompt: str, tenant_id: str) -> str:
        return self.invoke("claude_code", prompt, tenant_id)

    def invoke_codex(self, prompt: str, tenant_id: str) -> str:
        return self.invoke("codex", prompt, tenant_id)

    def invoke_antigravity(self, prompt: str, tenant_id: str) -> str:
        return self.invoke("antigravity", prompt, tenant_id)

    def invoke_openclaw(self, prompt: str, tenant_id: str) -> str:
        return self.invoke("openclaw", prompt, tenant_id)
