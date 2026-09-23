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

ESTE MÓDULO NO DECIDE SI SE PUEDE DELEGAR — solo sabe ejecutar. El candado de
confidencialidad (política ≠ 'soberano' + opt-in del despacho) vive en `gateway/hub_gate.py`
y quien decide CUÁNDO es `agents/delegate_intent.py` + `agents/graph.py::_maybe_delegate`.
Nadie debe llamar a `invoke_result` sin haber pasado por `hub_gate.delegation_allowed`.

§G: el abogado ve un `display_name` funcional en español; el `slug` (id público
neutro) es lo que viaja en las URLs de settings. Excepción (decisión de Pipe
2026-08-24): los ayudantes del Agent Hub muestran su marca comercial (`marca`) en
letra pequeña bajo el nombre por función, para que el abogado sepa qué instalar
cuando la tarjeta dice «no instalado». El nombre principal sigue siendo funcional
y en español; ni `display_name` ni `slug` llevan la marca.

Los flags de invocación se confirman contra ``--help`` del binario SI está en PATH.
Si el binario no está, o el help no muestra el flag que usamos, el conector queda
``invocation_ready=False`` con una razón honesta — el mismo patrón que Codex cuando
no está en el equipo. Nunca se deja un ``[VERIFICAR]`` en el catálogo.
"""
from __future__ import annotations

import inspect
import logging
import os
import shutil
import subprocess
from dataclasses import dataclass
from typing import Callable, Optional

from ..agents import untrusted

logger = logging.getLogger("mia.gateway.agent_hub")

DEFAULT_TIMEOUT = 120  # segundos

# Estados del resultado de una invocación (contrato con el grafo y, vía metadata, con la UI).
STATUS_OK = "ok"                      # el CLI corrió y devolvió salida (ya SELLADA)
STATUS_NOT_INSTALLED = "no_instalado"  # habilitado pero el binario no está en el equipo
STATUS_ERROR = "error"                # exit≠0, timeout, excepción, conector desconocido


@dataclass(frozen=True)
class Connector:
    key: str                                  # id interno (hermes, claude_code, …)
    slug: str                                 # id público neutro (URLs; sin marca)
    display_name: str                         # nombre en español para el abogado (§G)
    bin_candidates: tuple[str, ...]           # nombres a buscar en PATH
    env_override: str                         # var de entorno con ruta explícita
    build_args: Callable[[str], list[str]]    # (prompt) -> args DESPUÉS del binario
    stdin_prompt: bool = False                # el prompt viaja por STDIN, nunca por argv
    marca: str = ""                           # marca comercial, en letra pequeña bajo el
                                              # nombre funcional (excepción §G, Pipe 2026-08-24)


def _prompt_flag(flag: str) -> Callable[[str], list[str]]:
    return lambda prompt: [flag, prompt]


def _claude_code_args(prompt: str) -> list[str]:
    """Args del conector `claude_code`: es el ÚNICO conector de este catálogo cuyo binario
    es el CLI real `claude`/`claude-code` (los demás son otros productos que también usan
    `-p`). `--no-session-persistence` confirmado con `claude --help` (2026-09-23): "Disable
    session persistence - sessions will not be saved to disk"; solo aplica con -p/--print,
    que es exactamente este modo. Esta invocación es de un solo turno (sin --resume ni
    --continue, y nadie relee el transcript después), así que apagar la persistencia no
    pierde nada y evita que cada delegación deje otro transcript de un mensaje bajo
    `~/.claude/projects/...` del equipo del despacho (mismo hallazgo que en
    `agent/subscription_llm.py`, ver su docstring)."""
    return ["-p", "--no-session-persistence", prompt]


# Flags que cada conector debe exhibir en `--help` para considerarse listo.
# Codex no usa -p: el prompt va por stdin (mismo aislamiento del proveedor productivo).
_HELP_NEEDLES: dict[str, tuple[str, ...]] = {
    "hermes": ("-p", "--print"),
    "claude_code": ("-p", "--print"),
    "antigravity": ("-p", "--print"),
    "openclaw": ("-p", "--print"),
    "codex": ("exec",),
}

CONNECTORS: dict[str, Connector] = {
    "hermes": Connector("hermes", "investigacion", "Asistente de investigación jurídica",
                        ("hermes",), "MIA_HERMES_BIN", _prompt_flag("-p"), marca="Hermes"),
    "claude_code": Connector("claude_code", "documentos", "Editor de documentos",
                             ("claude", "claude-code"), "MIA_CLAUDE_BIN", _claude_code_args,
                             marca="Claude Code"),
    # Codex con el MISMO aislamiento del proveedor productivo (codex_subscription_llm):
    # prompt por stdin (nunca argv), efímero, sin config/reglas del usuario, sandbox de
    # solo lectura y herramientas/red apagadas. Sin esto, el texto delegado (derivado del
    # expediente) corría con la config del usuario y una inyección podía activar
    # herramientas (auditoría 2026-08-14).
    "codex": Connector("codex", "automatizacion", "Asistente de automatización",
                       ("codex",), "MIA_CODEX_BIN",
                       lambda _prompt: [
                           "exec", "--ephemeral", "--ignore-user-config", "--ignore-rules",
                           "--skip-git-repo-check", "--sandbox", "read-only",
                           "--color", "never", "--strict-config",
                           "-c", 'web_search="disabled"',
                           "-c", "features.shell_tool=false",
                           "-c", "features.unified_exec=false",
                           "-c", "features.browser_use=false",
                           "-c", "features.computer_use=false",
                           "-c", "agents.enabled=false",
                           "-c", 'shell_environment_policy.inherit="none"',
                           "-c", 'approval_policy="never"',
                           "-c", "check_for_update_on_startup=false",
                           "-",
                       ], stdin_prompt=True, marca="Codex"),
    "antigravity": Connector("antigravity", "escritorio", "Asistente de escritorio",
                             ("antigravity",), "MIA_ANTIGRAVITY_BIN", _prompt_flag("-p"),
                             marca="Antigravity"),
    "openclaw": Connector("openclaw", "navegacion", "Asistente de navegación web",
                          ("openclaw",), "MIA_OPENCLAW_BIN", _prompt_flag("-p"),
                          marca="OpenClaw"),
}

@dataclass(frozen=True)
class InvokeResult:
    """Resultado ESTRUCTURADO de invocar un CLI. El caller decide por `status`, nunca
    olfateando el prefijo del string ("[error] …") — eso era frágil y se rompía en cuanto
    el CLI escupía un "[error]" propio en su stdout.

    · status = STATUS_OK        → `text` es la salida SELLADA (untrusted.wrap_untrusted).
    · status ≠ STATUS_OK        → `text` es un mensaje en llano para el abogado (§G) y
                                  `detail` la traza técnica (stderr recortado, excepción).
                                  `detail` NUNCA se le muestra al abogado: va al log.
    """
    status: str
    text: str
    detail: str = ""

    @property
    def ok(self) -> bool:
        return self.status == STATUS_OK


_SLUG_TO_KEY = {c.slug: c.key for c in CONNECTORS.values()}


def slug_to_key(slug: str) -> Optional[str]:
    """Traduce el id público (slug) al id interno del conector. None si no existe."""
    return _SLUG_TO_KEY.get(slug)


def _default_runner(args: list[str], *, cwd: Optional[str], timeout: int,
                    env: Optional[dict] = None,
                    stdin_input: Optional[str] = None) -> tuple[int, str, str]:
    """Corre el subproceso con `shell=False` (args en lista → espacios seguros)."""
    proc = subprocess.run(args, capture_output=True, text=True, timeout=timeout,
                          cwd=cwd, shell=False, env=env, input=stdin_input)
    return proc.returncode, proc.stdout, proc.stderr


# CP-S3: nombres de entorno que un CLI externo SÍ necesita para arrancar (rutas del
# SO, temp, config del usuario). Todo lo que NO esté aquí — en particular claves y
# credenciales de la instalación (ANTHROPIC_API_KEY, VOYAGE_API_KEY, PG_PASSWORD,
# DATABASE_URL, JWT_SECRET, TELEGRAM_BOT_TOKEN…) — NO se hereda al subproceso: un CLI
# de terceros comprometido no puede leer los secretos de Mia del entorno. Nombres en
# MAYÚSCULA; el match es case-insensitive (Windows usa 'SystemRoot', 'Path').
_ENV_ALLOWLIST = frozenset({
    "PATH", "PATHEXT", "SYSTEMROOT", "WINDIR", "SYSTEMDRIVE", "COMSPEC", "OS",
    "TEMP", "TMP", "TMPDIR", "HOME", "HOMEDRIVE", "HOMEPATH", "USERPROFILE",
    "USERNAME", "USER", "LOGNAME", "APPDATA", "LOCALAPPDATA", "PROGRAMDATA",
    "PROGRAMFILES", "PROGRAMFILES(X86)", "COMMONPROGRAMFILES", "NUMBER_OF_PROCESSORS",
    "PROCESSOR_ARCHITECTURE", "LANG", "LC_ALL", "TZ", "MIA_HOME", "PYTHONUNBUFFERED",
})


def sanitize_subprocess_env(env: dict) -> dict:
    """Entorno mínimo para el subproceso: solo la allowlist del SO + MIA_HOME.

    Excluye TODA credencial de la instalación (heredarlas al CLI de un tercero era el
    hueco de CP-S3). Fuerza PYTHONUNBUFFERED=1 para que el stdout llegue sin buffering."""
    out = {k: v for k, v in env.items() if k.upper() in _ENV_ALLOWLIST}
    out["PYTHONUNBUFFERED"] = "1"
    return out


class AgentHub:
    """Invoca CLIs externos como subprocesos aislados, con degradación con gracia.

    `runner` se inyecta en los tests (mock del subprocess). `env` permite override de
    las rutas de binarios (default `os.environ`). `cwd` es el directorio de trabajo
    del subproceso (puede contener espacios; va como parámetro, no como string).
    """

    def __init__(self, *, runner=None, env: Optional[dict] = None,
                 cwd: Optional[str] = None, timeout: int = DEFAULT_TIMEOUT,
                 help_prober: Optional[Callable[[str], str]] = None) -> None:
        self._runner = runner or _default_runner
        self._env = env if env is not None else os.environ
        self._cwd = cwd
        self._timeout = timeout
        self._help_prober = help_prober
        self._help_cache: dict[str, str] = {}
        # CP-S3: ¿el runner acepta `env`? Se decide UNA vez por la firma (no con un
        # except en caliente que confundiría un TypeError legítimo con "no soporta env").
        try:
            params = inspect.signature(self._runner).parameters
            self._runner_accepts_env = "env" in params
            self._runner_accepts_stdin = "stdin_input" in params
        except (ValueError, TypeError):
            self._runner_accepts_env = False
            self._runner_accepts_stdin = False

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

    def _read_help(self, binary: str) -> str:
        """`--help` del binario, cacheado por ruta. Vacío si no se puede leer."""
        cached = self._help_cache.get(binary)
        if cached is not None:
            return cached
        text = ""
        try:
            if self._help_prober is not None:
                text = self._help_prober(binary) or ""
            elif os.path.isfile(binary):
                proc = subprocess.run(
                    [binary, "--help"], capture_output=True, text=True, timeout=8,
                    shell=False)
                text = (proc.stdout or "") + "\n" + (proc.stderr or "")
        except Exception as e:  # noqa: BLE001 — un help fallido no tumba el catálogo
            logger.info("no se pudo leer --help de %s: %s", binary, e)
            text = ""
        self._help_cache[binary] = text
        return text

    def invocation_status(self, key: str, binary: Optional[str]) -> tuple[bool, str]:
        """(listo, razón). Sin binario o sin flag confirmado → no se habilita."""
        c = CONNECTORS[key]
        if not binary:
            return False, (
                f"«{c.display_name}» no está instalado en este equipo. Mia no confirma "
                "cómo invocarlo hasta que el programa exista aquí.")
        needles = _HELP_NEEDLES.get(key, ())
        help_text = self._read_help(binary)
        if not help_text.strip():
            return False, (
                f"«{c.display_name}» está en el equipo, pero Mia no pudo leer su "
                "ayuda (--help). No se habilita hasta confirmar la invocación.")
        blob = help_text.lower()
        if needles and not any(n.lower() in blob for n in needles):
            shown = ", ".join(needles)
            return False, (
                f"«{c.display_name}» está instalado, pero su ayuda no muestra los "
                f"parámetros que Mia usaría ({shown}). No se habilita a ciegas.")
        return True, ""

    def list_available(self) -> dict:
        """Estado de cada conector. NUNCA crashea (cada resolución va protegida)."""
        out: dict = {}
        for key, c in CONNECTORS.items():
            try:
                binary = self.resolve_binary(key)
            except Exception as e:  # noqa: BLE001
                logger.warning("resolver binario de %s falló: %s", key, e)
                binary = None
            try:
                ready, razon = self.invocation_status(key, binary)
            except Exception as e:  # noqa: BLE001
                logger.warning("confirmar invocación de %s falló: %s", key, e)
                ready, razon = False, (
                    f"«{c.display_name}» no se pudo confirmar en este equipo.")
            out[key] = {
                "key": key,
                "slug": c.slug,
                "display_name": c.display_name,
                # Excepción §G (Pipe 2026-08-24): la marca viaja en campo propio, en
                # letra pequeña en la UI; el display_name sigue limpio.
                "marca": c.marca,
                "installed": binary is not None,
                "binary": binary,
                "invocation_ready": ready,
                "razon": razon,
            }
        return out

    # -- invocación genérica ----------------------------------------------------
    def invoke(self, key: str, prompt: str, tenant_id: str) -> str:
        """Compat: solo el texto de `invoke_result` (salida sellada o mensaje en llano).

        Los llamadores nuevos usan `invoke_result`, que trae `status` y no obliga a
        adivinar el desenlace leyendo el prefijo del string."""
        return self.invoke_result(key, prompt, tenant_id).text

    def invoke_result(self, key: str, prompt: str, tenant_id: str) -> InvokeResult:
        """Invoca un conector y devuelve el resultado ESTRUCTURADO.
        NUNCA lanza excepción al caller (graceful degradation).

        Si un flag está mal, el CLI sale ≠ 0 y este camino termina en STATUS_ERROR;
        el turno del abogado no se rompe."""
        c = CONNECTORS.get(key)
        if c is None:
            logger.warning("conector desconocido: %s (tenant=%s)", key, tenant_id)
            return InvokeResult(STATUS_ERROR, "Ese asistente no existe.",
                                detail=f"conector desconocido: {key}")
        binary = self.resolve_binary(key)
        if binary is None:
            logger.info("conector %s no disponible (tenant=%s)", key, tenant_id)
            # §G: el abogado ve el nombre en español y una salida de acción, no un stacktrace.
            return InvokeResult(
                STATUS_NOT_INSTALLED,
                f"«{c.display_name}» no está instalado en este equipo. Puedes seguir sin él: "
                f"Mia responde igual con el expediente y el corpus del despacho.",
                detail=f"binario no encontrado: {c.bin_candidates} / {c.env_override}")

        # stdin_prompt: el prompt NUNCA entra al argv (visible en listados de procesos y
        # susceptible de trato como flags); viaja por stdin. Fail-closed: si el runner
        # inyectado no soporta stdin, el conector se reporta como error, no degrada a argv.
        args = [binary, *c.build_args("" if c.stdin_prompt else prompt)]
        if c.stdin_prompt and not self._runner_accepts_stdin:
            logger.warning("conector %s exige stdin y el runner no lo soporta (tenant=%s)",
                           key, tenant_id)
            return InvokeResult(STATUS_ERROR,
                                f"«{c.display_name}» no se pudo ejecutar en este equipo.",
                                detail="runner sin soporte stdin_input para stdin_prompt")
        # CP-S3: el subproceso recibe SOLO el entorno saneado (sin las claves de la
        # instalación). Se decide con la FIRMA del runner si acepta `env` (revisión
        # capa 2, H5: un `except TypeError` reintentaría el subprocess DOS veces si el
        # runner lanzara TypeError por otra razón — doble efecto para un CLI que actúa).
        env = sanitize_subprocess_env(dict(self._env))
        kwargs = {"cwd": self._cwd, "timeout": self._timeout}
        if self._runner_accepts_env:
            kwargs["env"] = env
        if c.stdin_prompt:
            kwargs["stdin_input"] = prompt
        try:
            code, stdout, stderr = self._runner(args, **kwargs)
        except subprocess.TimeoutExpired:
            logger.warning("conector %s: timeout %ss (tenant=%s)", key, self._timeout, tenant_id)
            return InvokeResult(
                STATUS_ERROR,
                f"«{c.display_name}» no respondió a tiempo ({self._timeout} s) y se detuvo.",
                detail=f"timeout {self._timeout}s")
        except Exception as e:  # noqa: BLE001 — graceful degradation: nunca propagar
            logger.warning("conector %s falló: %s (tenant=%s)", key, e, tenant_id)
            # El texto de la excepción NO va al abogado (puede traer rutas/jerga): al log.
            return InvokeResult(STATUS_ERROR,
                                f"«{c.display_name}» no se pudo ejecutar en este equipo.",
                                detail=f"{type(e).__name__}: {e}")

        if code != 0:
            # CP-S1: el stderr es salida EXTERNA — saneado antes de tocarlo siquiera
            # (un CLI comprometido no fabrica instrucciones dentro del mensaje).
            safe_err = untrusted.sanitize_field(stderr, 300)
            logger.warning("conector %s exit=%s stderr=%s (tenant=%s)",
                           key, code, safe_err, tenant_id)
            return InvokeResult(STATUS_ERROR,
                                f"«{c.display_name}» no pudo completar la tarea.",
                                detail=f"exit={code} stderr={safe_err}")
        # CP-S1 (cuarentena universal): la salida de un CLI externo es contenido
        # NO confiable — viaja sellada ("datos, no órdenes") hacia cualquier
        # prompt o metadata que la consuma (hoy md['delegation']; mañana lo que sea).
        return InvokeResult(STATUS_OK,
                            untrusted.wrap_untrusted(f"salida de '{c.display_name}'", stdout))

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
