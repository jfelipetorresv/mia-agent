"""Mia · connectors.notebooklm.client — envoltura del CLI `notebooklm-py` (CP-NLM).

Corre el CLI NO oficial `notebooklm` (proyecto `notebooklm-py`) como subproceso AISLADO,
con los mismos principios de seguridad que `gateway/agent_hub.py`:

- `shell=False` + argumentos EN LISTA: una pregunta con comillas/espacios/`;` NO se
  interpreta como shell ni necesita entrecomillado manual (evita inyección de shell).
- Entorno SANEADO (`agent_hub.sanitize_subprocess_env`): el subproceso recibe solo la
  allowlist del SO + MIA_HOME; NUNCA hereda las claves de la instalación (ANTHROPIC,
  VOYAGE, PG_PASSWORD, JWT…). La auth de NotebookLM vive aparte, en el perfil del usuario
  (`~/.notebooklm/storage_state.json`), que el CLI lee por su cuenta.
- Timeout. Ante CUALQUIER fallo (binario ausente, exit≠0, timeout, excepción) devuelve
  None y loguea; NUNCA propaga (degradación con gracia — el turno sigue con corpus local).

Devuelve stdout CRUDO (sin sellar): el sellado anti-inyección (`untrusted.wrap_untrusted`)
lo aplica UNA sola vez el punto de entrada del módulo (`__init__.consult_notebook`).

NOTA [VERIFICAR] (misma convención que agent_hub · decisión D3): los flags de invocación
(`use <id>`, `ask <q> --json`) están SIN confirmar contra el `--help` real del CLI; el
gate de tests mockea el runner, así que no se ejercitan en vivo. Confirmar contra el CLI
instalado antes de la prueba E2E.
"""
from __future__ import annotations

import json
import logging
import os
import shutil
import subprocess
from typing import Callable, Optional

from ...gateway.agent_hub import sanitize_subprocess_env

logger = logging.getLogger("mia.connectors.notebooklm")

DEFAULT_TIMEOUT = 120  # segundos (una consulta RAG de NotebookLM responde rápido)
_BIN_CANDIDATES = ("notebooklm",)
_ENV_OVERRIDE = "MIA_NOTEBOOKLM_BIN"

# runner(args, timeout, env) -> (returncode, stdout, stderr). Inyectable en tests.
Runner = Callable[..., tuple[int, str, str]]


def resolve_binary(env: Optional[dict] = None) -> Optional[str]:
    """Ruta del CLI `notebooklm`: override por env > venv instalado por MIA (setup) > PATH.
    None si falta."""
    env = env if env is not None else os.environ
    override = env.get(_ENV_OVERRIDE)
    if override and os.path.isfile(override):
        return override
    # Binario instalado in-app por connectors.notebooklm.setup (venv aislado bajo MIA_HOME).
    try:
        from . import setup  # import diferido (evita ciclos al cargar el paquete)

        installed = setup.bin_path()
        if installed is not None:
            return str(installed)
    except Exception:  # noqa: BLE001 — si setup no está disponible, se sigue con PATH
        pass
    for name in _BIN_CANDIDATES:
        found = shutil.which(name)
        if found:
            return found
    return None


def _default_runner(args: list[str], *, timeout: int,
                    env: Optional[dict] = None) -> tuple[int, str, str]:
    proc = subprocess.run(args, capture_output=True, text=True, timeout=timeout,
                          shell=False, env=env)
    return proc.returncode, proc.stdout, proc.stderr


def _run(binary: str, cli_args: list[str], *, timeout: int, runner: Runner,
         env: Optional[dict]) -> Optional[tuple[int, str, str]]:
    """Corre `binary cli_args` con entorno saneado. None ante timeout/excepción."""
    args = [binary, *cli_args]  # ruta intacta como primer arg (espacios OK)
    safe_env = sanitize_subprocess_env(dict(env if env is not None else os.environ))
    try:
        return runner(args, timeout=timeout, env=safe_env)
    except subprocess.TimeoutExpired:
        logger.warning("notebooklm: timeout %ss en %s", timeout, cli_args[:1])
        return None
    except Exception as e:  # noqa: BLE001 — degradación con gracia: nunca propagar
        logger.warning("notebooklm: fallo en %s: %s", cli_args[:1], e)
        return None


def ask(notebook_id: str, question: str, *, timeout: int = DEFAULT_TIMEOUT,
        runner: Optional[Runner] = None, env: Optional[dict] = None) -> Optional[str]:
    """Consulta RAG a un notebook: fija el contexto (`use <id>`) y pregunta (`ask <q> --json`).

    Devuelve el TEXTO de la respuesta (crudo, sin sellar), o None si el CLI no está
    disponible o algo falla. Función SINCRÓNICA (subprocess): el llamador async debe
    envolverla en `asyncio.to_thread`."""
    runner = runner or _default_runner
    binary = resolve_binary(env)
    if binary is None:
        logger.info("notebooklm: CLI no instalado en este equipo (nada que consultar)")
        return None

    # 1) Fijar el notebook activo. `use` es estado global del CLI — para un instalador
    #    de un solo usuario (Pipe) no hay carrera; en multi-tenant sería un hazard a
    #    resolver (p. ej. un flag `--notebook` por llamada). [VERIFICAR] contra el CLI.
    used = _run(binary, ["use", notebook_id], timeout=timeout, runner=runner, env=env)
    if used is None:
        return None
    code, _out, stderr = used
    if code != 0:
        logger.warning("notebooklm: 'use %s' exit=%s stderr=%s",
                       notebook_id, code, (stderr or "")[:200])
        return None

    # 2) Preguntar en JSON para parsear la respuesta sin adivinar formato de texto.
    # [VERIFICAR] (revisión capa 2, MENOR-2): `question` va como arg posicional sin
    # separador `--`; un valor que empiece con `-` el CLI podría leerlo como flag. El
    # input del abogado es fidedigno (regla de MIA), así que el riesgo es funcional, no de
    # confidencialidad. Endurecer con `["ask", "--", question, "--json"]` SI el CLI lo
    # soporta — confirmar junto con los flags al validar el `--help` real.
    asked = _run(binary, ["ask", question, "--json"], timeout=timeout, runner=runner, env=env)
    if asked is None:
        return None
    code, stdout, stderr = asked
    if code != 0:
        logger.warning("notebooklm: 'ask' exit=%s stderr=%s", code, (stderr or "")[:200])
        return None
    return _parse_answer(stdout)


def _parse_answer(stdout: str) -> Optional[str]:
    """Extrae el texto de la respuesta del `--json` del CLI. Fail-soft: si no es JSON o no
    trae un campo conocido, devuelve el stdout crudo recortado (mejor algo que nada); vacío → None."""
    raw = str(stdout or "").strip()
    if not raw:
        return None
    try:
        data = json.loads(raw)
    except (ValueError, TypeError):
        return raw  # el CLI no devolvió JSON válido: pasar el texto crudo tal cual
    if isinstance(data, dict):
        for key in ("answer", "response", "text", "content", "message"):
            val = data.get(key)
            if isinstance(val, str) and val.strip():
                return val.strip()
    return raw
