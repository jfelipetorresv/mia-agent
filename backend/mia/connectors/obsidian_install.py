"""Mia · connectors.obsidian_install — detección e instalación guiada de Obsidian (CP-C2 · decisión #32).

Solo Windows (Modo B nativo). Funciones seguras de llamar desde la API:

- `is_installed_fast()` — NUNCA lanza y NUNCA invoca winget: SOLO revisa las rutas
  típicas de instalación por usuario (%LOCALAPPDATA%). Es la que debe usar
  cualquier ruta que se sirve en caliente a una petición HTTP (p.ej.
  GET /api/setup/status) — un winget list sin Obsidian instalado puede tardar
  ~60s (hallazgo MN3) y esa ruta no puede pagar ese costo por petición.
- `is_installed()` — NUNCA lanza: primero el mismo chequeo local de
  `is_installed_fast()` y, como respaldo, le pregunta a winget (hasta
  DETECT_TIMEOUT_S). Si winget no existe en el equipo, simplemente devuelve
  False. Úsala solo en flujos que toleran esa latencia (p.ej. folders.py y el
  propio `install()`), nunca en el camino caliente de un status.
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


def is_installed_fast() -> bool:
    """¿Obsidian ya está en este equipo? SOLO rutas locales — SIN winget, SIN red.

    Segura de llamar desde el camino caliente de una petición HTTP (status del
    asistente de configuración): nunca bloquea esperando un subproceso externo.
    Nunca lanza.
    """
    try:
        for exe in _local_candidates():
            if exe.is_file():
                return True
    except OSError:
        pass
    return False


def is_installed(fast: bool = False) -> bool:
    """¿Obsidian ya está en este equipo? Nunca lanza (aunque winget no exista).

    Con `fast=True` se comporta exactamente como `is_installed_fast()` (sin
    winget). Por defecto (`fast=False`) hace el chequeo local y, si no lo
    encuentra, respalda con winget (hasta DETECT_TIMEOUT_S) — no usar esta
    variante completa en rutas servidas en caliente a una petición HTTP.
    """
    if is_installed_fast():
        return True
    if fast:
        return False
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
