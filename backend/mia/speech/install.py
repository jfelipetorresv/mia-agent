"""Mia · speech.install — instalación de los modelos de dictado DESDE el producto.

Antes de esto, activar la voz exigía que un administrador corriera
scripts/download_speech_models.ps1 a mano — inaceptable para el usuario
objetivo (un abogado sin background técnico). Este módulo descarga los MISMOS
pesos, desde las MISMAS URLs, a la MISMA carpeta que el ps1 (que se conserva
como vía de administrador), pero desde un botón del Panel de control con
confirmación explícita (consent-first, patrón "Instalar Obsidian").

Es Python stdlib puro (urllib + tarfile + shutil): a diferencia del instalador
de Obsidian (que instala software en el HOST con winget y por eso se limita a
Modo B), esto solo escribe pesos en el data-dir propio de Mia → funciona igual
en Modo A (Docker/Linux) y Modo B (Windows nativo). NO lo "arregles" agregando
PowerShell o deshabilitándolo en Modo A.

Estado: el DISCO es la fuente de verdad de instalado/no instalado
(`missing_components()` mira los mismos archivos que `engine.available()`).
La memoria del proceso solo guarda lo transitorio — la descarga viva — que de
todas formas muere con el proceso: persistirla en DB mentiría tras un reinicio
("descargando" eterno). Mismo criterio que `_clip_hits` (routes/speech.py) y
`_detect_cache` (routes/setup.py): Modo B corre 1 worker. Limitación declarada
para Modo A multi-worker: el polling del progreso puede caer en un worker sin
la descarga (verá "no instalado" mientras otro descarga); mitigación futura =
estado en Postgres.
"""
from __future__ import annotations

import logging
import os
import shutil
import tarfile
import threading
import urllib.error
import urllib.request
from pathlib import Path

from .engine import _PARAKEET_DIR, _VAD_FILE, models_dir
from .tts import _TTS_DIR, _TTS_FILES

logger = logging.getLogger(__name__)

# Mismas URLs que scripts/download_speech_models.ps1 — una sola fuente de pesos.
RELEASE_BASE = "https://github.com/k2-fsa/sherpa-onnx/releases/download/asr-models"
PARAKEET_TARBALL = _PARAKEET_DIR + ".tar.bz2"
_TARBALL_LOCAL = "parakeet-v3-int8.tar.bz2"  # mismo nombre local que el ps1
_STAGING_DIR = _PARAKEET_DIR + ".staging"    # extracción atómica (capa 2 #1)
_PARAKEET_FILES = ["encoder.int8.onnx", "decoder.int8.onnx", "joiner.int8.onnx", "tokens.txt"]

# Voz de salida (CP-Z2): los modelos TTS viven en OTRO release (tag tts-models).
# Misma mecánica de descarga atómica que Parakeet; el modelo lo fija tts.py.
TTS_RELEASE_BASE = "https://github.com/k2-fsa/sherpa-onnx/releases/download/tts-models"
TTS_TARBALL = _TTS_DIR + ".tar.bz2"
_TTS_TARBALL_LOCAL = "tts-voz-es.tar.bz2"
_TTS_STAGING_DIR = _TTS_DIR + ".staging"
_VAD_MIN_BYTES = 500 * 1024        # mismo umbral de sanidad que el ps1
_CHUNK = 1024 * 1024               # lectura por MiB
_HTTP_TIMEOUT = 60                 # por operación de socket, no por descarga total
# ~460 MB de tarball + ~650 MB extraído + margen. Fail-soft ANTES de descargar.
_MIN_FREE_BYTES = 2 * 1024 ** 3

_state_lock = threading.Lock()
_thread: threading.Thread | None = None
_state: dict = {
    "status": "no_instalado",  # no_instalado | descargando | instalado | error
    "phase": None,             # descarga | extraccion | verificacion
    "bytes_done": 0,
    "bytes_total": None,       # Content-Length (None si el servidor no lo da)
    "error": None,             # mensaje en llano del último fallo
}

_MSG_NO_INSTALADO = (
    "El dictado por voz no está instalado. Instálalo aquí con el botón "
    "«Instalar dictado por voz» (~700 MB, tarda unos minutos)."
)
_MSG_INSTALADO = "El dictado por voz está instalado y listo para usar."
_MSG_EN_CURSO = "La descarga ya está en curso."
_MSG_ERROR_RED = (
    "No se pudo descargar el componente de voz. Revisa la conexión a internet "
    "del servidor e intenta de nuevo."
)
_MSG_ERROR_DISCO = (
    "No hay espacio suficiente en el disco del servidor para el componente de voz."
)


def _present(path: Path) -> bool:
    """Un archivo de 0 bytes NO cuenta como presente (hallazgo capa 2 #1: un
    estado roto previo no debe hacer decir 'instalado' a get_status)."""
    try:
        return path.is_file() and path.stat().st_size > 0
    except OSError:
        return False


def missing_components() -> tuple[list[str], bool, list[str]]:
    """(archivos Parakeet faltantes, ¿falta el detector de voz?, archivos TTS
    faltantes). Mira el disco. El dictado (STT) y la voz (TTS) se instalan juntos."""
    pdir = models_dir() / _PARAKEET_DIR
    missing = [f for f in _PARAKEET_FILES if not _present(pdir / f)]
    vad_missing = not _present(models_dir() / _VAD_FILE)
    tdir = models_dir() / _TTS_DIR
    tts_missing = [f for f in _TTS_FILES if not _present(tdir / f)]
    return missing, vad_missing, tts_missing


def _downloading() -> bool:
    return _thread is not None and _thread.is_alive()


def get_status() -> dict:
    """Estado combinado disco + memoria, listo para pantalla (mensajes en llano)."""
    with _state_lock:
        downloading = _downloading()
        status = dict(_state)
    if downloading:
        done_mb = int(status["bytes_done"] / (1024 * 1024))
        total = status["bytes_total"]
        total_mb = int(total / (1024 * 1024)) if total else None
        pct = int(status["bytes_done"] * 100 / total) if total else None
        if status["phase"] == "descarga":
            avance = (
                f"({done_mb} de {total_mb} MB)" if total_mb else f"({done_mb} MB)"
            )
            mensaje = f"Estoy descargando el componente de voz {avance}…"
        elif status["phase"] == "extraccion":
            mensaje = "Estoy preparando el componente de voz (ya casi termina)…"
        else:
            mensaje = "Estoy revisando que el componente de voz quedó completo…"
        return {
            "estado": "descargando",
            "listo": False,
            "mensaje": mensaje,
            "progreso": {
                "fase": status["phase"],
                "descargado_mb": done_mb,
                "total_mb": total_mb,
                "porcentaje": pct,
            },
        }
    missing, _vad_missing, tts_missing = missing_components()
    if not missing and not tts_missing:
        return {"estado": "instalado", "listo": True, "mensaje": _MSG_INSTALADO,
                "progreso": None}
    if status["status"] == "error" and status["error"]:
        # El error queda visible pero el estado se comporta como "no instalado":
        # el botón de instalar reaparece y el reintento arranca limpio.
        return {"estado": "error", "listo": False, "mensaje": status["error"],
                "progreso": None}
    return {"estado": "no_instalado", "listo": False, "mensaje": _MSG_NO_INSTALADO,
            "progreso": None}


def start_install() -> dict:
    """Arranca la descarga en background. Single-flight: dos clics = una descarga."""
    global _thread
    # El I/O de disco (stats, mkdir, disk_usage) va FUERA del lock (hallazgo
    # capa 2 #5): el polling de get_status no debe esperar detrás de un disco
    # lento. El worker re-verifica qué falta al arrancar, así que un dato viejo
    # aquí solo produce un no-op, nunca una doble descarga.
    missing, vad_missing, tts_missing = missing_components()
    if not missing and not vad_missing and not tts_missing:
        return {"status": "instalado", "message": _MSG_INSTALADO}
    dest = models_dir()
    try:
        dest.mkdir(parents=True, exist_ok=True)
        if shutil.disk_usage(dest).free < _MIN_FREE_BYTES:
            return {"status": "error", "message": _MSG_ERROR_DISCO}
    except OSError:
        logger.exception("speech.install: no se pudo preparar %s", dest)
        return {
            "status": "error",
            "message": "No se pudo preparar la carpeta del componente de voz "
                       "en el servidor.",
        }
    with _state_lock:
        if _downloading():
            return {"status": "descargando", "message": _MSG_EN_CURSO}
        _state.update(
            status="descargando", phase="descarga", bytes_done=0,
            bytes_total=None, error=None,
        )
        _thread = threading.Thread(
            target=_install_worker, args=(dest,),
            name="mia-speech-install", daemon=True,
        )
        _thread.start()
    if missing or tts_missing:
        mensaje = ("Empecé a descargar el componente de voz (~750 MB). "
                   "Puedes seguir el avance aquí mismo.")
    else:
        # Solo falta el detector de voz (~2 MB): no anunciar 750 MB (exactitud).
        mensaje = "Empecé a descargar el detector de voz (es pequeño, tarda poco)."
    return {"status": "descargando", "message": mensaje}


def _cleanup_partials(dest: Path) -> None:
    """Borra restos de intentos anteriores para que el reintento arranque limpio."""
    for leftover in [dest / _TARBALL_LOCAL, dest / (_TARBALL_LOCAL + ".part"),
                     dest / (_VAD_FILE + ".part"),
                     dest / _TTS_TARBALL_LOCAL, dest / (_TTS_TARBALL_LOCAL + ".part")]:
        try:
            leftover.unlink(missing_ok=True)
        except OSError:
            logger.warning("speech.install: no se pudo borrar %s", leftover)
    # La extracción ocurre en un área de trabajo aparte (publicación atómica,
    # hallazgo capa 2 #1): si un intento anterior murió a medias, fuera con ella.
    shutil.rmtree(dest / _STAGING_DIR, ignore_errors=True)
    shutil.rmtree(dest / _TTS_STAGING_DIR, ignore_errors=True)


def _download(url: str, dest: Path, on_progress) -> None:
    """Descarga url → dest (archivo completo). Separada e inyectable: los gates la
    reemplazan — JAMÁS descargar los pesos reales en tests. Un 404/500 lanza
    HTTPError (equivalente al -f del ps1: nunca escribe la página de error)."""
    req = urllib.request.Request(url, headers={"User-Agent": "mia-speech-install"})
    with urllib.request.urlopen(req, timeout=_HTTP_TIMEOUT) as resp:
        total = resp.headers.get("Content-Length")
        total_bytes = int(total) if total and total.isdigit() else None
        done = 0
        on_progress(done, total_bytes)
        with open(dest, "wb") as fh:
            while True:
                chunk = resp.read(_CHUNK)
                if not chunk:
                    break
                fh.write(chunk)
                done += len(chunk)
                on_progress(done, total_bytes)


def _set_progress(done: int, total: int | None) -> None:
    with _state_lock:
        _state["bytes_done"] = done
        if total is not None:
            _state["bytes_total"] = total


def _set_phase(phase: str) -> None:
    with _state_lock:
        _state["phase"] = phase


def _validate_member(member: tarfile.TarInfo) -> None:
    """Rechaza entradas peligrosas del tar (fail-closed): rutas absolutas, '..'
    y todo lo que NO sea archivo regular o directorio — symlinks/hardlinks
    podrían apuntar fuera de la carpeta (hallazgo capa 2 #3)."""
    name = member.name.replace("\\", "/")
    if name.startswith("/") or ".." in name.split("/"):
        raise RuntimeError(f"entrada insegura en el archivo: {member.name}")
    if not (member.isreg() or member.isdir()):
        raise RuntimeError(f"entrada no permitida en el archivo: {member.name}")


def _safe_extract(tarball: Path, dest: Path) -> None:
    """Extrae el tar.bz2 bloqueando path traversal (fail-closed)."""
    with tarfile.open(tarball, "r:bz2") as tf:
        try:
            tf.extractall(dest, filter="data")  # PEP 706 (Python 3.11.4+)
        except TypeError:
            # Runtime sin filtros: validación manual con las mismas garantías.
            for member in tf.getmembers():
                _validate_member(member)
            tf.extractall(dest)


def _download_extract_publish(
    dest: Path, url: str, local_tarball: str, staging_name: str,
    final_dir: str, files: list[str], progress,
) -> None:
    """Descarga un tar.bz2 y publica su carpeta de forma ATÓMICA: baja a `.part`,
    extrae en un área de trabajo aparte, verifica ahí los archivos y solo entonces
    renombra a su lugar — si el proceso muere a mitad, el estado sigue siendo
    honesto y el reintento arranca limpio (hallazgo capa 2 #1). Reusado por el
    modelo de dictado (Parakeet) y el de voz (TTS)."""
    tarball = dest / local_tarball
    part = dest / (local_tarball + ".part")
    staging = dest / staging_name
    _set_phase("descarga")
    _download(url, part, progress)
    os.replace(part, tarball)
    _set_phase("extraccion")
    shutil.rmtree(staging, ignore_errors=True)
    staging.mkdir(parents=True, exist_ok=True)
    _safe_extract(tarball, staging)
    tarball.unlink(missing_ok=True)
    extracted = staging / final_dir
    broken = [f for f in files if not _present(extracted / f)]
    if broken:
        raise RuntimeError(f"la descarga llegó incompleta: faltan {broken}")
    # Publicación atómica: el directorio final aparece completo o no aparece.
    shutil.rmtree(dest / final_dir, ignore_errors=True)
    os.replace(extracted, dest / final_dir)
    shutil.rmtree(staging, ignore_errors=True)


def _install_worker(dest: Path) -> None:
    """Corre COMPLETO en un thread — jamás en el event loop del API.

    Re-verifica en disco QUÉ falta (no confía en lo que vio start_install) y
    publica cada modelo de forma ATÓMICA (ver _download_extract_publish). El
    dictado (Parakeet) y la voz (TTS) se instalan juntos; el detector de voz
    (VAD) es fail-soft."""
    global _thread
    try:
        _cleanup_partials(dest)
        need_parakeet, need_vad, need_tts = missing_components()
        if need_parakeet:
            _download_extract_publish(
                dest, f"{RELEASE_BASE}/{PARAKEET_TARBALL}", _TARBALL_LOCAL,
                _STAGING_DIR, _PARAKEET_DIR, _PARAKEET_FILES, _set_progress,
            )
        if need_tts:
            _download_extract_publish(
                dest, f"{TTS_RELEASE_BASE}/{TTS_TARBALL}", _TTS_TARBALL_LOCAL,
                _TTS_STAGING_DIR, _TTS_DIR, _TTS_FILES, _set_progress,
            )
        if need_vad:
            # Fail-soft: sin el detector de voz el motor degrada a cortes fijos
            # de 60 s (engine.py) — no es motivo para declarar error la instalación.
            try:
                vad_part = dest / (_VAD_FILE + ".part")
                _download(f"{RELEASE_BASE}/{_VAD_FILE}", vad_part,
                          lambda d, t: None)
                if vad_part.stat().st_size < _VAD_MIN_BYTES:
                    vad_part.unlink(missing_ok=True)
                    logger.warning("speech.install: el detector de voz descargado "
                                   "no tiene el tamaño esperado; se omite")
                else:
                    os.replace(vad_part, dest / _VAD_FILE)
            except Exception:
                logger.exception("speech.install: no se pudo bajar el detector de "
                                 "voz (opcional); el dictado funciona sin él")
        _set_phase("verificacion")
        missing, _, tts_missing = missing_components()
        if missing or tts_missing:
            raise RuntimeError(
                f"faltan archivos tras la instalación: {missing + tts_missing}"
            )
        with _state_lock:
            _state.update(status="instalado", phase=None, error=None)
        logger.info("speech.install: componente de voz instalado en %s", dest)
    except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError, OSError,
            tarfile.TarError, RuntimeError) as e:
        logger.exception("speech.install: falló la instalación del componente de voz")
        # La publicación es atómica: el dir final nunca queda a medias. Solo hay
        # que barrer el área de trabajo y los parciales para el reintento.
        _cleanup_partials(dest)
        mensaje = _MSG_ERROR_DISCO if isinstance(e, OSError) and getattr(
            e, "errno", None) == 28 else _MSG_ERROR_RED
        with _state_lock:
            _state.update(status="error", phase=None, error=mensaje)
    finally:
        with _state_lock:
            if _thread is threading.current_thread():
                _thread = None
