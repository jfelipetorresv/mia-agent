"""Mia · connectors.obsidian_install — detección e instalación guiada de Obsidian (CP-C2 · decisión #32).

Solo Windows (Modo B nativo). Dos funciones, ambas seguras de llamar desde la API:

- `is_installed()` — NUNCA lanza: busca Obsidian.exe en las rutas típicas de instalación
  por usuario (%LOCALAPPDATA%) y, como respaldo, le pregunta a winget. Si winget no
  existe en el equipo, simplemente devuelve False.
- `install()` — ejecuta winget como LISTA de argumentos (sin shell, sin interpolación)
  con timeout de 10 minutos. Devuelve (ok, mensaje en lenguaje llano para el abogado).
"""
from __future__ import annotations

import os
import subprocess
from pathlib import Path

WINGET_ID = "Obsidian.Obsidian"
INSTALL_TIMEOUT_S = 600
DETECT_TIMEOUT_S = 60


def _local_candidates() -> list[Path]:
    """Rutas típicas del ejecutable en instalaciones por usuario de Windows."""
    local = os.environ.get("LOCALAPPDATA", "")
    if not local:
        return []
    base = Path(local)
    return [
        base / "Obsidian" / "Obsidian.exe",
        base / "Programs" / "obsidian" / "Obsidian.exe",
        base / "Programs" / "Obsidian" / "Obsidian.exe",
    ]


def is_installed() -> bool:
    """¿Obsidian ya está en este equipo? Nunca lanza (aunque winget no exista)."""
    try:
        for exe in _local_candidates():
            if exe.is_file():
                return True
    except OSError:
        pass
    try:
        proc = subprocess.run(
            ["winget", "list", "--id", WINGET_ID, "-e",
             "--accept-source-agreements", "--disable-interactivity"],
            capture_output=True, text=True, timeout=DETECT_TIMEOUT_S,
        )
        return proc.returncode == 0 and WINGET_ID.lower() in (proc.stdout or "").lower()
    except Exception:  # noqa: BLE001 — sin winget (o roto) simplemente "no detectado"
        return False


def install() -> tuple[bool, str]:
    """Instala Obsidian vía winget (silencioso, sin shell). Devuelve (ok, mensaje llano)."""
    if is_installed():
        return True, "Obsidian ya está instalado en este equipo."
    cmd = [
        "winget", "install", "--id", WINGET_ID, "-e", "--silent",
        "--accept-package-agreements", "--accept-source-agreements",
    ]
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=INSTALL_TIMEOUT_S)
    except FileNotFoundError:
        return False, (
            "No encontré el instalador de aplicaciones de Windows (winget) en este equipo. "
            "Puedes descargar Obsidian manualmente desde obsidian.md e intentarlo de nuevo."
        )
    except subprocess.TimeoutExpired:
        return False, (
            "La instalación está tardando más de lo normal. Revisa tu conexión a internet "
            "e inténtalo de nuevo en unos minutos."
        )
    except Exception:  # noqa: BLE001 — mensaje llano, sin detalles técnicos
        return False, (
            "No pude iniciar la instalación de Obsidian. "
            "Puedes instalarlo manualmente desde obsidian.md."
        )
    if proc.returncode == 0 or is_installed():
        return True, "Listo: Obsidian quedó instalado en este equipo."
    return False, (
        "No pude completar la instalación de Obsidian automáticamente. "
        "Puedes instalarlo manualmente desde obsidian.md."
    )
