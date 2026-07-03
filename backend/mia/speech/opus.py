"""Mia · speech.opus — códec OGG/Opus para el canal de Telegram (CP-Z2).

Las notas de voz de Telegram son OGG/Opus; el decodificador WAV de audio.py
(stdlib `wave`) no las lee. Este módulo aísla el ÚNICO punto que necesita un
códec real, con PyAV (`av`) — un wheel autocontenido que empaqueta ffmpeg, sin
binario externo (funciona igual en Modo A/Docker y Modo B/Windows nativo).

Dos direcciones:
  - `decode_ogg_opus_to_pcm16k(data)`: nota de voz ENTRANTE → PCM 16 kHz mono
    float32, listo para el STT (mismos topes y errores en llano que audio.py).
  - `encode_pcm_to_ogg_opus(samples, rate)`: audio que Mia sintetizó (TTS) →
    bytes OGG/Opus para enviarlo como nota de voz SALIENTE.

Defensivo por diseño: entrada acotada en bytes y en duración de salida (una nota
de voz maliciosa no debe reventar memoria); cualquier fallo del decodificador se
traduce a `AudioInvalido` en lenguaje llano (nunca una traza cruda al abogado).
"""
from __future__ import annotations

import io
import logging

import numpy as np

from .audio import MAX_SECONDS, MAX_UPLOAD_BYTES, TARGET_RATE, AudioInvalido

logger = logging.getLogger(__name__)

# Opus opera a 48 kHz; el resampleo lo hace PyAV. Bitrate de voz suficiente.
_OPUS_RATE = 48_000

# Tope duro de muestras a la salida del decodificador (defensa anti-bomba: un
# .oga corto puede declarar una duración enorme). MAX_SECONDS es el mismo tope
# de duración del dictado (audio.py).
_MAX_OUT_SAMPLES = (MAX_SECONDS + 5) * TARGET_RATE


def _require_av():
    try:
        import av  # noqa: F401
    except ImportError as exc:  # pragma: no cover - entorno sin la dep
        raise AudioInvalido(
            "Este servidor no puede procesar notas de voz todavía."
        ) from exc
    import av

    return av


def decode_ogg_opus_to_pcm16k(data: bytes) -> np.ndarray:
    """Nota de voz OGG/Opus → float32 mono 16 kHz. Lanza AudioInvalido en llano."""
    if not data:
        raise AudioInvalido("La nota de voz llegó vacía. Intenta grabar de nuevo.")
    if len(data) > MAX_UPLOAD_BYTES:
        raise AudioInvalido("La nota de voz es demasiado grande. Grábala más corta.")

    av = _require_av()
    try:
        container = av.open(io.BytesIO(data))
    except Exception as exc:  # noqa: BLE001
        raise AudioInvalido(
            "No se pudo leer la nota de voz. Vuelve a intentarlo."
        ) from exc

    resampler = av.AudioResampler(format="flt", layout="mono", rate=TARGET_RATE)
    chunks: list[np.ndarray] = []
    total = 0
    try:
        for frame in container.decode(audio=0):
            for out in resampler.resample(frame):
                arr = out.to_ndarray().reshape(-1).astype(np.float32, copy=False)
                chunks.append(arr)
                total += arr.size
                if total > _MAX_OUT_SAMPLES:
                    raise AudioInvalido(
                        "La nota de voz supera los 5 minutos. Grábala más corta."
                    )
        for out in resampler.resample(None):  # drena el buffer del resampler
            arr = out.to_ndarray().reshape(-1).astype(np.float32, copy=False)
            chunks.append(arr)
            total += arr.size
    except AudioInvalido:
        raise
    except Exception as exc:  # noqa: BLE001
        raise AudioInvalido(
            "No se pudo procesar la nota de voz. Vuelve a intentarlo."
        ) from exc
    finally:
        try:
            container.close()
        except Exception:  # noqa: BLE001
            pass

    if not chunks:
        raise AudioInvalido("La nota de voz llegó vacía. Intenta grabar de nuevo.")
    samples = np.concatenate(chunks)
    if samples.size == 0:
        raise AudioInvalido("La nota de voz llegó vacía. Intenta grabar de nuevo.")
    return np.ascontiguousarray(samples, dtype=np.float32)


def encode_pcm_to_ogg_opus(samples: np.ndarray, rate: int) -> bytes:
    """PCM float32 mono a `rate` Hz → bytes OGG/Opus (nota de voz de Telegram).

    Lanza AudioInvalido si el audio de entrada es vacío o el códec falla."""
    arr = np.asarray(samples, dtype=np.float32).reshape(-1)
    if arr.size == 0 or rate <= 0:
        raise AudioInvalido("No hay audio para enviar.")
    arr = np.clip(arr, -1.0, 1.0)

    av = _require_av()
    buf = io.BytesIO()
    try:
        out = av.open(buf, mode="w", format="ogg")
        stream = out.add_stream("libopus", rate=_OPUS_RATE)
        stream.layout = "mono"
        resampler = av.AudioResampler(format="s16", layout="mono", rate=_OPUS_RATE)

        frame = av.AudioFrame.from_ndarray(arr.reshape(1, -1), format="flt", layout="mono")
        frame.sample_rate = int(rate)
        for rframe in resampler.resample(frame):
            for pkt in stream.encode(rframe):
                out.mux(pkt)
        for rframe in resampler.resample(None):     # drena el resampler
            for pkt in stream.encode(rframe):
                out.mux(pkt)
        for pkt in stream.encode(None):             # drena el codificador
            out.mux(pkt)
        out.close()
    except Exception as exc:  # noqa: BLE001
        logger.exception("speech.opus: fallo codificando OGG/Opus")
        raise AudioInvalido("No se pudo preparar la nota de voz de Mia.") from exc

    return buf.getvalue()
