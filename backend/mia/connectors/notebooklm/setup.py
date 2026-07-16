"""Mia · connectors.notebooklm.setup — instalación y conexión del CLI de NotebookLM (CP-NLM).

Antes de esto, usar NotebookLM exigía que alguien instalara a mano el CLI `notebooklm-py`
y corriera un login por terminal — inaceptable para el abogado objetivo. Este módulo lo
vuelve un flujo de dos botones en Configuración (patrón "Instalar dictado por voz" /
"Instalar Obsidian"):

  1. INSTALAR (background, single-flight, con progreso por fase): crea un venv AISLADO
     bajo MIA_HOME, instala `notebooklm-py[browser]` y el navegador de Playwright. No toca
     el venv del backend (evita conflictos de dependencias). Solo Modo B (Windows nativo):
     el login abre una ventana de navegador en el escritorio del abogado.
  2. CONECTAR (login guiado): abre un navegador donde el abogado inicia sesión en Google;
     al confirmar "ya inicié sesión", se captura la sesión (`~/.notebooklm/storage_state.json`,
     el default del CLI) y queda conectado.

El DISCO es la fuente de verdad (`installed()` mira el binario; `authenticated()` mira el
archivo de sesión). La memoria del proceso solo guarda lo transitorio (instalación/login en
curso), que muere con el proceso — persistirlo mentiría tras un reinicio. Mismo criterio que
`speech/install.py`. Limitación declarada Modo A multi-worker: el polling puede caer en un
worker sin el trabajo en curso.

NOTA [VERIFICAR] (misma convención que agent_hub/client · D3): los comandos exactos del CLI
(`notebooklm-py` en pip, `notebooklm` como entry-point, `auth check`, `list --json`) y el
guion de login (Playwright) están SIN confirmar contra la herramienta real — el gate mockea
el runner. Confirmar en la prueba E2E en la máquina de Pipe.
"""
from __future__ import annotations

import json
import logging
import os
import subprocess
import sys
import threading
import time
from pathlib import Path
from typing import Callable, Optional

from ...config import MIA_HOME
from ...gateway.agent_hub import sanitize_subprocess_env

logger = logging.getLogger("mia.connectors.notebooklm")

# runner(args, timeout) -> (returncode, stdout, stderr). Inyectable en tests (mock).
Runner = Callable[..., tuple[int, str, str]]

_IS_WINDOWS = os.name == "nt"
_PIP_TIMEOUT = 900        # pip + playwright install pueden tardar minutos
_CLI_TIMEOUT = 120        # auth check / list
_AUTH_TTL_SECONDS = 30.0  # cachea el resultado de `auth check` (evita spawnear en cada poll)


def _installer_python() -> str:
    """Intérprete para CREAR el venv del CLI. El spec pide Python 3.12; se prefiere si está
    disponible (`py -3.12` en Windows / `python3.12`), y si no, se cae al Python del backend
    (3.11 cumple el 3.10+ real de notebooklm-py). Devuelve un ejecutable o un lanzador."""
    candidates: list[list[str]] = []
    if _IS_WINDOWS:
        candidates.append(["py", "-3.12"])          # Windows launcher
    candidates.append(["python3.12"])
    for cand in candidates:
        try:
            r = subprocess.run([*cand, "-c", "import sys;print(sys.executable)"],
                               capture_output=True, text=True, timeout=20, shell=False)
            if r.returncode == 0 and r.stdout.strip():
                return r.stdout.strip()
        except Exception:  # noqa: BLE001 — candidato ausente: probar el siguiente
            continue
    logger.info("notebooklm.setup: Python 3.12 no encontrado; uso el del backend (%s)",
                sys.executable)
    return sys.executable

# ── rutas (todo bajo MIA_HOME, aislado del backend) ──────────────────────────────
def _cli_root() -> Path:
    return MIA_HOME / "notebooklm-cli"


def _venv_dir() -> Path:
    return _cli_root() / "venv"


def _venv_python() -> Path:
    return _venv_dir() / ("Scripts/python.exe" if _IS_WINDOWS else "bin/python")


def bin_path() -> Optional[Path]:
    """Ruta del entry-point `notebooklm` dentro del venv aislado. None si no existe."""
    p = _venv_dir() / ("Scripts/notebooklm.exe" if _IS_WINDOWS else "bin/notebooklm")
    return p if p.is_file() else None


def _install_marker() -> Path:
    """Marcador de instalación COMPLETA. Se escribe solo tras el ÚLTIMO paso (el navegador),
    para que una instalación a medias (p. ej. el navegador falló tras crearse ya el .exe con
    pip) NO cuente como 'instalado' — así el error se muestra y el reintento funciona
    (revisión capa 2, MAYOR 1)."""
    return _cli_root() / "installed.ok"


def _signal_file() -> Path:
    """Señal 'ya inicié sesión' que confirm_login() crea para que el guion guarde la sesión."""
    return _cli_root() / "login.signal"


# ── verdad en disco ──────────────────────────────────────────────────────────────
def installed() -> bool:
    """Instalado = el binario existe Y el marcador de instalación completa (MAYOR 1: el .exe
    aparece con pip, ANTES del navegador; sin el marcador, un navegador faltante no se
    disfraza de 'instalado')."""
    return bin_path() is not None and _install_marker().is_file()


# ── verificación de sesión vía el CLI (NO confiar en el exit code) ────────────────
# `notebooklm auth check` puede imprimir un error y AUN ASÍ devolver código 0 (spec de Pipe).
# Por eso se analiza el TEXTO: si trae cualquiera de estas señales, se considera NO conectado.
def _auth_signals_fail(output: str) -> bool:
    low = str(output or "").lower()
    if "storage exists" in low and "fail" in low:
        return True
    if "sid cookie" in low and "fail" in low:
        return True
    return any(s in low for s in (
        "storage file not found",
        "run 'notebooklm login'",
        'run "notebooklm login"',
        "run notebooklm login",
        "auth_required",
    ))


_auth_cache: tuple[bool, float] = (False, 0.0)


def _invalidate_auth_cache() -> None:
    global _auth_cache
    _auth_cache = (False, 0.0)


def verify_auth(runner: Optional[Runner] = None) -> bool:
    """Comprueba de VERDAD la sesión: `auth check` (analizando el TEXTO, no el exit code) y,
    si pasa, confirma con `list --json` exit 0 — una "conexión" que no puede listar NO cuenta
    (ese era el bug 'muestra conectado pero la lista falla'). Nunca propaga."""
    b = bin_path()
    if b is None:
        return False
    runner = runner or _default_runner
    try:
        _code, out, err = runner([str(b), "auth", "check"], timeout=_CLI_TIMEOUT,
                                 env=_safe_env())
    except Exception:  # noqa: BLE001
        return False
    if _auth_signals_fail((out or "") + "\n" + (err or "")):
        return False
    try:
        lcode, _lout, _lerr = runner([str(b), "list", "--json"], timeout=_CLI_TIMEOUT,
                                     env=_safe_env())
    except Exception:  # noqa: BLE001
        return False
    return lcode == 0


def authenticated(runner: Optional[Runner] = None) -> bool:
    """True si la cuenta de Google está conectada DE VERDAD (verificado con el CLI, no un flag).
    Cachea el resultado con TTL corto para no spawnear el CLI en cada poll de estado."""
    global _auth_cache
    if bin_path() is None:
        return False
    now = time.monotonic()
    val, ts = _auth_cache
    if ts > 0.0 and (now - ts) < _AUTH_TTL_SECONDS:
        return val
    val = verify_auth(runner)
    _auth_cache = (val, now)
    return val


# ── estado transitorio (instalación / login en curso) ────────────────────────────
_lock = threading.Lock()
_install_thread: Optional[threading.Thread] = None
_login_thread: Optional[threading.Thread] = None
_state: dict = {
    "install_phase": None,   # creando_entorno | instalando_cli | instalando_navegador | verificando
    "install_error": None,   # mensaje en llano
    "login_error": None,
}

_PHASE_PCT = {"creando_entorno": 15, "instalando_cli": 55,
              "instalando_navegador": 85, "verificando": 95}
_PHASE_MSG = {
    "creando_entorno": "Preparando el entorno de NotebookLM…",
    "instalando_cli": "Instalando NotebookLM (esto tarda unos minutos)…",
    "instalando_navegador": "Instalando el navegador que NotebookLM necesita…",
    "verificando": "Revisando que quedó completo…",
}
_MSG_NO_INSTALADO = ("NotebookLM no está instalado. Instálalo aquí con el botón "
                     "«Instalar NotebookLM» (descarga unos cientos de MB, tarda unos minutos).")
_MSG_SIN_CONECTAR = ("NotebookLM está instalado pero falta conectar tu cuenta de Google. "
                     "Usa «Conectar mi cuenta».")
_MSG_CONECTADO = "NotebookLM está instalado y tu cuenta está conectada."
_MSG_CONECTANDO = ("Se abrió una ventana del navegador. Inicia sesión en Google y en "
                   "notebooklm.google.com; cuando termines, pulsa «Ya inicié sesión».")


def _install_running() -> bool:
    return _install_thread is not None and _install_thread.is_alive()


def _login_running() -> bool:
    return _login_thread is not None and _login_thread.is_alive()


def get_status() -> dict:
    """Estado combinado disco + memoria, en llano para la tarjeta de Conexiones."""
    with _lock:
        installing = _install_running()
        logging_in = _login_running()
        st = dict(_state)
    inst = installed()
    auth = authenticated()

    if installing:
        phase = st["install_phase"] or "creando_entorno"
        return {"estado": "instalando", "instalado": inst, "autenticado": auth,
                "listo": False, "mensaje": _PHASE_MSG.get(phase, "Instalando…"),
                "progreso": {"fase": phase, "porcentaje": _PHASE_PCT.get(phase)}}
    if st["install_error"] and not inst:
        return {"estado": "error", "instalado": False, "autenticado": False,
                "listo": False, "mensaje": st["install_error"], "progreso": None}
    if not inst:
        return {"estado": "no_instalado", "instalado": False, "autenticado": False,
                "listo": False, "mensaje": _MSG_NO_INSTALADO, "progreso": None}
    if logging_in and not auth:
        return {"estado": "conectando", "instalado": True, "autenticado": False,
                "listo": False, "mensaje": _MSG_CONECTANDO, "progreso": None}
    if st["login_error"] and not auth:
        return {"estado": "error", "instalado": True, "autenticado": False,
                "listo": False, "mensaje": st["login_error"], "progreso": None}
    if not auth:
        return {"estado": "instalado_sin_conectar", "instalado": True, "autenticado": False,
                "listo": False, "mensaje": _MSG_SIN_CONECTAR, "progreso": None}
    return {"estado": "conectado", "instalado": True, "autenticado": True,
            "listo": True, "mensaje": _MSG_CONECTADO, "progreso": None}


# ── instalación ──────────────────────────────────────────────────────────────────
def _default_runner(args: list[str], *, timeout: int,
                    env: Optional[dict] = None) -> tuple[int, str, str]:
    """env=None → hereda el entorno (para pasos de instalación con el propio Python de MIA:
    venv/pip/playwright). Para EJECUTAR el binario del tercero o el guion de login se pasa un
    entorno SANEADO (sin secretos de la instalación) — ver CP-S3 / MAYOR 2."""
    proc = subprocess.run(args, capture_output=True, text=True, timeout=timeout,
                          shell=False, env=env)
    return proc.returncode, proc.stdout, proc.stderr


def _safe_env() -> dict:
    """Entorno saneado (allowlist del SO + MIA_HOME, sin claves de la instalación) para
    ejecutar el binario NO oficial de NotebookLM y el guion de login. Mismo blindaje que
    `client.py` aplica a la consulta viva (CP-S3)."""
    return sanitize_subprocess_env(dict(os.environ))


def start_install(runner: Optional[Runner] = None) -> dict:
    """Arranca la instalación en background. Single-flight: dos clics = una instalación."""
    global _install_thread
    if installed():
        return {"estado": "instalado_sin_conectar" if not authenticated() else "conectado",
                "mensaje": _MSG_CONECTADO if authenticated() else _MSG_SIN_CONECTAR}
    with _lock:
        if _install_running():
            return {"estado": "instalando", "mensaje": "La instalación ya está en curso."}
        _state.update(install_phase="creando_entorno", install_error=None)
        _install_thread = threading.Thread(
            target=_install_worker, args=(runner or _default_runner,),
            name="mia-notebooklm-install", daemon=True)
        _install_thread.start()
    return {"estado": "instalando",
            "mensaje": "Empecé a instalar NotebookLM. Puedes seguir el avance aquí mismo."}


def _set_install_phase(phase: str) -> None:
    with _lock:
        _state["install_phase"] = phase


def _install_worker(runner: Runner) -> None:
    """Crea el venv aislado, instala el CLI y el navegador. Corre en un thread."""
    global _install_thread
    try:
        root = _cli_root()
        root.mkdir(parents=True, exist_ok=True)
        # 1) venv aislado con Python 3.12 si está (spec), si no el del backend (3.11 cumple 3.10+).
        _set_install_phase("creando_entorno")
        _check(runner([_installer_python(), "-m", "venv", str(_venv_dir())], timeout=_PIP_TIMEOUT),
               "no se pudo crear el entorno")
        vpy = str(_venv_python())
        # 2) el CLI (con extra [browser] → trae Playwright).
        _set_install_phase("instalando_cli")
        _check(runner([vpy, "-m", "pip", "install", "notebooklm-py[browser]"],
                      timeout=_PIP_TIMEOUT), "no se pudo instalar NotebookLM")
        # 3) el navegador que Playwright/NotebookLM necesita.
        _set_install_phase("instalando_navegador")
        _check(runner([vpy, "-m", "playwright", "install", "chromium"], timeout=_PIP_TIMEOUT),
               "no se pudo instalar el navegador")
        _set_install_phase("verificando")
        if bin_path() is None:
            raise RuntimeError("la instalación terminó pero no encuentro el programa de NotebookLM")
        # Marcador de completitud SOLO tras el último paso (el navegador): a partir de aquí
        # installed() dice True (MAYOR 1). Antes de esto, un navegador faltante deja
        # installed()=False → el error se muestra y el reintento funciona.
        _install_marker().write_text("ok", encoding="utf-8")
        with _lock:
            _state.update(install_phase=None, install_error=None)
        logger.info("notebooklm.setup: CLI instalado en %s", _venv_dir())
    except Exception as e:  # noqa: BLE001 — cualquier fallo → error en llano, sin propagar
        logger.exception("notebooklm.setup: falló la instalación")
        with _lock:
            _state.update(install_phase=None,
                          install_error="No se pudo instalar NotebookLM. Revisa la conexión "
                                        "a internet e intenta de nuevo. Detalle: " + str(e)[:200])
    finally:
        with _lock:
            if _install_thread is threading.current_thread():
                _install_thread = None


def _check(result: tuple[int, str, str], what: str) -> None:
    code, _out, stderr = result
    if code != 0:
        raise RuntimeError(f"{what} (código {code}): {(stderr or '')[:200]}")


# ── conexión (login de Google) ───────────────────────────────────────────────────
# Guion de login: abre un navegador NO headless (el `notebooklm login` del CLI necesita un
# Enter interactivo que un backend no puede dar; el proyecto documenta este workaround). El
# navegador queda abierto hasta que aparece el archivo-señal (lo crea confirm_login), momento
# en que se captura la sesión. [VERIFICAR] contra Playwright real en la máquina de Pipe.
_LOGIN_SCRIPT = r'''
import json, sys, time
from pathlib import Path
from playwright.sync_api import sync_playwright

STORAGE = Path.home() / ".notebooklm" / "storage_state.json"
PROFILE = Path.home() / ".notebooklm" / "browser_profile"
SIGNAL = Path(sys.argv[1])
STORAGE.parent.mkdir(parents=True, exist_ok=True)
try:
    SIGNAL.unlink()
except FileNotFoundError:
    pass

with sync_playwright() as p:
    ctx = p.chromium.launch_persistent_context(
        user_data_dir=str(PROFILE), headless=False,
        args=["--disable-blink-features=AutomationControlled"])
    page = ctx.pages[0] if ctx.pages else ctx.new_page()
    page.goto("https://notebooklm.google.com/")
    # Espera la confirmación del abogado (o un tope de 10 min para no dejar un proceso colgado).
    deadline = time.monotonic() + 600
    while not SIGNAL.exists() and time.monotonic() < deadline:
        time.sleep(1)
    if SIGNAL.exists():
        with open(STORAGE, "w", encoding="utf-8") as fh:
            json.dump(ctx.storage_state(), fh)
    ctx.close()
'''


def start_login(runner: Optional[Runner] = None) -> dict:
    """Abre el navegador para el login de Google (background). Single-flight."""
    global _login_thread
    if not installed():
        return {"estado": "no_instalado", "mensaje": _MSG_NO_INSTALADO}
    if authenticated():
        return {"estado": "conectado", "mensaje": _MSG_CONECTADO}
    with _lock:
        if _login_running():
            return {"estado": "conectando", "mensaje": _MSG_CONECTANDO}
        _state.update(login_error=None)
        _login_thread = threading.Thread(
            target=_login_worker, args=(runner or _default_runner,),
            name="mia-notebooklm-login", daemon=True)
        _login_thread.start()
    return {"estado": "conectando", "mensaje": _MSG_CONECTANDO}


def _login_worker(runner: Runner) -> None:
    """Escribe el guion de login a disco y lo corre con el python del venv (abre el navegador)."""
    global _login_thread
    try:
        try:
            _signal_file().unlink()
        except FileNotFoundError:
            pass
        script_path = _cli_root() / "login_script.py"
        script_path.write_text(_LOGIN_SCRIPT, encoding="utf-8")
        # El guion bloquea hasta la señal o el tope de 10 min → timeout holgado por encima.
        # Entorno SANEADO (MAYOR 2): el guion lanza Chromium y toca Google; no debe ver las
        # claves de la instalación.
        _check(runner([str(_venv_python()), str(script_path), str(_signal_file())],
                      timeout=660, env=_safe_env()), "el navegador de login no terminó bien")
        _invalidate_auth_cache()  # la sesión acaba de cambiar → recomputar, no leer caché vieja
        if not authenticated():
            raise RuntimeError("no se guardó la sesión de Google (¿se cerró el navegador antes "
                               "de iniciar sesión?)")
        with _lock:
            _state.update(login_error=None)
        logger.info("notebooklm.setup: cuenta de Google conectada")
    except Exception as e:  # noqa: BLE001
        logger.exception("notebooklm.setup: falló el login")
        with _lock:
            _state.update(login_error="No se pudo conectar tu cuenta de Google. Intenta de "
                                      "nuevo. Detalle: " + str(e)[:200])
    finally:
        try:
            _signal_file().unlink()
        except FileNotFoundError:
            pass
        with _lock:
            if _login_thread is threading.current_thread():
                _login_thread = None


def confirm_login() -> dict:
    """El abogado pulsó «Ya inicié sesión»: crea el archivo-señal para que el guion capture la
    sesión. No espera aquí (el status refleja el resultado en el siguiente polling)."""
    if not _login_running():
        return {"estado": get_status()["estado"],
                "mensaje": "No hay una conexión en curso. Pulsa «Conectar mi cuenta» primero."}
    try:
        _cli_root().mkdir(parents=True, exist_ok=True)
        _signal_file().write_text("ok", encoding="utf-8")
    except OSError:
        logger.exception("notebooklm.setup: no se pudo crear la señal de login")
        return {"estado": "error", "mensaje": "No se pudo confirmar el inicio de sesión."}
    return {"estado": "conectando", "mensaje": "Guardando tu sesión…"}


# ── lista de notebooks (para el selector; metadata del abogado, sin datos de cliente) ──
def list_notebooks(runner: Optional[Runner] = None) -> list[dict]:
    """Notebooks del abogado como [{"id","titulo"}]. [] si no instalado/conectado o error.

    Corre `notebooklm list --json`. Es una llamada a Google, pero solo trae los TÍTULOS de
    los notebooks del propio abogado (sin datos de cliente) — necesaria para el selector."""
    b = bin_path()
    if b is None or not authenticated():
        return []
    runner = runner or _default_runner
    try:
        # Entorno SANEADO (MAYOR 2): ejecutar el binario NO oficial no debe filtrarle las
        # claves de la instalación — mismo blindaje que la consulta viva (client.py).
        code, stdout, _stderr = runner([str(b), "list", "--json"],
                                       timeout=_CLI_TIMEOUT, env=_safe_env())
    except Exception:  # noqa: BLE001 — nunca propaga; sin lista, el abogado pega el id a mano
        logger.warning("notebooklm.setup: no se pudo listar notebooks", exc_info=True)
        return []
    if code != 0:
        return []
    try:
        data = json.loads(stdout or "{}")
    except (ValueError, TypeError):
        return []
    items = data.get("notebooks") if isinstance(data, dict) else data
    out: list[dict] = []
    for it in items or []:
        if isinstance(it, dict) and it.get("id"):
            out.append({"id": str(it["id"]),
                        "titulo": str(it.get("title") or it.get("titulo") or it["id"])})
    return out
