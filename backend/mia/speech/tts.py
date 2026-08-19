"""Mia · speech.tts — motor de VOZ DE SALIDA local (CP-Z2, Ola 3).

La contraparte de engine.py (dictado): aquí Mia HABLA. Sintetiza texto a audio
100% dentro de la infraestructura del despacho — el texto de la respuesta nunca
sale a un servicio de nube. Reusa `sherpa-onnx` (la MISMA librería del dictado,
ya instalada) con un modelo VITS/Piper en español; los pesos se descargan aparte
(speech/install.py o scripts/download_speech_models.ps1), como los del STT.

Igual que el STT, todo es LOCAL y OPCIONAL: sin `sherpa-onnx` o sin los pesos en
disco, `available()` explica qué falta en llano y la ruta responde 503 — ningún
otro módulo de Mia depende de esto.

El motor es un singleton de carga perezosa (el modelo VITS se carga UNA vez al
primer uso). `synthesize()` es síncrono y con lock — la ruta lo llama vía
asyncio.to_thread y serializa la concurrencia (mismo criterio que engine.py).
"""
from __future__ import annotations

import logging
import os
import threading

import numpy as np

from .engine import models_dir  # misma carpeta de pesos que el STT

logger = logging.getLogger(__name__)

# ¿La síntesis ocurre dentro de la infraestructura del despacho? VITS vía
# sherpa-onnx corre en el proceso del API → SÍ. Si algún día se agrega un TTS de
# nube, DEBE declararse False y el candado allow_cloud_audio (policy.py) lo
# bloqueará por defecto (mismo patrón que ENGINE_IS_LOCAL).
TTS_IS_LOCAL = True

# Modelo de voz de salida. Constantes en un solo lugar: cambiar de voz = cambiar
# esto (y install.py lo importa para descargar el mismo modelo). La voz la eligió
# Pipe por el oído (capa 3, contenido que oye el cliente).
#
# es_MX-ald-medium: español latinoamericano (México), 22050 Hz, 1 hablante.
# sid/speed por defecto.
#
# PENDIENTE (agnosticismo de jurisdicción): hoy la voz es una sola para todos los
# despachos, y un despacho español oiría acento latinoamericano. La elección correcta
# es POR DESPACHO —del pack de jurisdicción o de una preferencia del despacho—, pero
# cambiarla no es cosmético: el modelo es un asset que descarga install.py (habría que
# empaquetar una voz por variante). Se deja documentado, no resuelto.
_TTS_DIR = "vits-piper-es_MX-ald-medium"
_TTS_MODEL_FILE = "es_MX-ald-medium.onnx"
_TTS_TOKENS = "tokens.txt"
_TTS_DATA_DIR = "espeak-ng-data"        # léxico de espeak-ng que trae el modelo
_TTS_SID = 0                            # hablante (multi-speaker: 0..num_speakers-1)
_TTS_SPEED = 1.0                        # 1.0 = velocidad natural; >1 más rápido

# Archivos que deben existir en disco para considerar el TTS instalado.
_TTS_FILES = [_TTS_MODEL_FILE, _TTS_TOKENS]

# Tope de caracteres por síntesis: una nota de voz conversacional, no un escrito.
# La ruta y el puente ya recortan/derivan a texto lo largo; esto es la red dura.
MAX_TTS_CHARS = 2000


class TtsEngine:
    """Síntesis de voz local con carga perezosa. Una instancia por proceso."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._tts = None
        self._load_error: str | None = None

    # ---------- disponibilidad ----------

    def available(self) -> tuple[bool, str]:
        """(ok, razón en llano si no). NO carga el modelo: solo verifica requisitos."""
        try:
            import sherpa_onnx  # noqa: F401
        except ImportError:
            return False, (
                "La voz de Mia no está instalada en este servidor "
                "(falta el componente de voz)."
            )
        tdir = models_dir() / _TTS_DIR
        if not all((tdir / f).is_file() for f in _TTS_FILES):
            return False, (
                "El modelo de voz de Mia no está descargado en este servidor. "
                "Instálalo desde Configuración con el botón "
                "«Instalar dictado por voz»."
            )
        if self._load_error:
            return False, self._load_error
        return True, ""

    # ---------- carga ----------

    def _ensure_loaded(self):
        """Carga el modelo VITS UNA vez (bajo lock). Lanza RuntimeError en llano."""
        if self._tts is not None:
            return self._tts
        ok, reason = self.available()
        if not ok:
            raise RuntimeError(reason)
        import sherpa_onnx

        tdir = models_dir() / _TTS_DIR
        provider = os.getenv("MIA_SPEECH_PROVIDER", "cpu").strip().lower() or "cpu"

        def _build(prov: str):
            cfg = sherpa_onnx.OfflineTtsConfig(
                model=sherpa_onnx.OfflineTtsModelConfig(
                    vits=sherpa_onnx.OfflineTtsVitsModelConfig(
                        model=str(tdir / _TTS_MODEL_FILE),
                        tokens=str(tdir / _TTS_TOKENS),
                        data_dir=str(tdir / _TTS_DATA_DIR),
                    ),
                    num_threads=int(os.getenv("MIA_SPEECH_THREADS", "4")),
                    provider=prov,
                ),
            )
            if not cfg.validate():
                raise RuntimeError("configuración de voz inválida")
            return sherpa_onnx.OfflineTts(cfg)

        try:
            tts = _build(provider)
        except Exception:
            if provider == "cpu":
                self._load_error = (
                    "El componente de voz no pudo iniciarse en este servidor."
                )
                logger.exception("speech.tts: fallo cargando VITS (provider=cpu)")
                raise RuntimeError(self._load_error)
            # DirectML u otro provider no disponible en este build → CPU (declarado,
            # mismo criterio que engine.py: VITS es rápido en CPU).
            logger.warning(
                "speech.tts: provider %r no disponible; usando CPU", provider
            )
            try:
                tts = _build("cpu")
            except Exception:
                self._load_error = (
                    "El componente de voz no pudo iniciarse en este servidor."
                )
                logger.exception("speech.tts: fallo cargando VITS (fallback cpu)")
                raise RuntimeError(self._load_error)

        self._tts = tts
        logger.info("speech.tts: modelo de voz cargado (provider solicitado=%s)", provider)
        return tts

    # ---------- síntesis ----------

    def synthesize(self, text: str) -> dict:
        """Texto → {'samples': float32 mono en [-1,1], 'sample_rate': int}.

        Síncrono; con lock (sherpa-onnx no garantiza generación concurrente sobre
        el mismo objeto). Texto vacío → samples vacío (el llamador decide). Recorta
        a MAX_TTS_CHARS por seguridad dura."""
        clean = (text or "").strip()
        if not clean:
            return {"samples": np.zeros(0, dtype=np.float32), "sample_rate": 0}
        if len(clean) > MAX_TTS_CHARS:
            clean = clean[:MAX_TTS_CHARS]
        with self._lock:
            tts = self._ensure_loaded()
            audio = tts.generate(clean, sid=_TTS_SID, speed=_TTS_SPEED)
            samples = np.ascontiguousarray(
                np.asarray(audio.samples, dtype=np.float32)
            )
            return {"samples": samples, "sample_rate": int(audio.sample_rate)}


# Singleton del proceso (la ruta lo usa; los gates lo reemplazan por un doble).
_tts_engine: TtsEngine | None = None
_tts_engine_lock = threading.Lock()


def get_tts_engine() -> TtsEngine:
    global _tts_engine
    if _tts_engine is None:
        with _tts_engine_lock:
            if _tts_engine is None:
                _tts_engine = TtsEngine()
    return _tts_engine
