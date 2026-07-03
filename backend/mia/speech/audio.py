"""Mia · speech.audio — del WAV del navegador a PCM 16 kHz mono float32.

El botón de micrófono (frontend) graba, re-muestrea a 16 kHz mono y envía un
WAV PCM. Este módulo lo decodifica con la stdlib (`wave` + numpy, sin ffmpeg)
y lo deja EXACTO como lo esperan Silero VAD y Parakeet: float32 en [-1, 1] a
16 000 Hz mono — los parámetros que Lexter validó (docs/analisis-lexter.md).

Tolerante pero acotado: acepta PCM entero de 8/16/24/32 bits, mezcla estéreo a
mono y re-muestrea si el navegador no pudo entregar 16 kHz. Todo lo demás se
rechaza con un mensaje en lenguaje llano (AudioInvalido).
"""
from __future__ import annotations

import io
import wave

import numpy as np

# Frecuencia que esperan los modelos (Lexter/Silero/Parakeet): no configurable.
TARGET_RATE = 16_000

# Topes duros (se validan aquí y en la ruta): un dictado es un clip corto.
MAX_SECONDS = 5 * 60          # 5 minutos por clip (tope del diseño de CP-Z1)
MAX_UPLOAD_BYTES = 32 * 1024 * 1024   # 32 MB — WAV PCM16 16 kHz de 5 min ≈ 9.6 MB


class AudioInvalido(ValueError):
    """Audio que no se puede procesar. `str(e)` es apto para mostrarse al abogado."""


def decode_audio_to_pcm16k(data: bytes) -> np.ndarray:
    """Decodifica el audio a float32 mono 16 kHz sea WAV o nota de voz OGG/Opus.

    El botón de micrófono de la web envía WAV PCM; Telegram envía notas de voz en
    OGG/Opus. Se detecta por los primeros bytes de la cabecera y se delega al
    decodificador que corresponde (WAV = stdlib `wave`; Opus = speech/opus.py, que
    usa PyAV). Un formato desconocido se intenta como WAV y, si no, se rechaza en
    llano — así el STT sirve a ambas superficies transparentemente (CP-Z2)."""
    if not data:
        raise AudioInvalido("La grabación llegó vacía. Intenta grabar de nuevo.")
    head = data[:4]
    if head == b"OggS":
        from . import opus  # import perezoso: opus.py depende de este módulo
        return opus.decode_ogg_opus_to_pcm16k(data)
    if head == b"RIFF":
        return decode_wav_to_pcm16k(data)
    # Desconocido: algunos clientes omiten detalles de cabecera → intenta WAV.
    return decode_wav_to_pcm16k(data)


def decode_wav_to_pcm16k(data: bytes) -> np.ndarray:
    """Decodifica un WAV PCM a float32 mono 16 kHz. Lanza AudioInvalido en llano."""
    if not data:
        raise AudioInvalido("La grabación llegó vacía. Intenta dictar de nuevo.")
    if len(data) > MAX_UPLOAD_BYTES:
        raise AudioInvalido("La grabación es demasiado grande. Dicta en clips más cortos.")
    try:
        with wave.open(io.BytesIO(data)) as wf:
            channels = wf.getnchannels()
            width = wf.getsampwidth()
            rate = wf.getframerate()
            frames = wf.getnframes()
            if rate <= 0 or channels <= 0 or frames <= 0:
                raise AudioInvalido("La grabación llegó vacía. Intenta dictar de nuevo.")
            if frames / rate > MAX_SECONDS:
                raise AudioInvalido(
                    "La grabación supera los 5 minutos. Dicta en clips más cortos."
                )
            raw = wf.readframes(frames)
    except AudioInvalido:
        raise
    except (wave.Error, EOFError) as exc:
        raise AudioInvalido(
            "No se pudo leer el audio. Vuelve a intentar el dictado."
        ) from exc

    samples = _pcm_bytes_to_float32(raw, width)
    if channels > 1:
        # Mezcla a mono (mismo criterio que Lexter: promedio de canales).
        samples = samples[: (len(samples) // channels) * channels]
        samples = samples.reshape(-1, channels).mean(axis=1)
    if rate != TARGET_RATE:
        samples = _resample_linear(samples, rate, TARGET_RATE)
    if samples.size == 0:
        raise AudioInvalido("La grabación llegó vacía. Intenta dictar de nuevo.")
    return np.ascontiguousarray(samples, dtype=np.float32)


def _pcm_bytes_to_float32(raw: bytes, width: int) -> np.ndarray:
    """PCM entero (8/16/24/32 bits) → float32 en [-1, 1]."""
    if width == 2:
        return np.frombuffer(raw, dtype="<i2").astype(np.float32) / 32768.0
    if width == 4:
        return np.frombuffer(raw, dtype="<i4").astype(np.float32) / 2147483648.0
    if width == 1:  # WAV de 8 bits es unsigned con offset 128
        return (np.frombuffer(raw, dtype=np.uint8).astype(np.float32) - 128.0) / 128.0
    if width == 3:  # 24 bits: 3 bytes little-endian por muestra
        b = np.frombuffer(raw, dtype=np.uint8)
        b = b[: (len(b) // 3) * 3].reshape(-1, 3)
        vals = (
            b[:, 0].astype(np.int32)
            | (b[:, 1].astype(np.int32) << 8)
            | (b[:, 2].astype(np.int32) << 16)
        )
        vals = np.where(vals >= 1 << 23, vals - (1 << 24), vals)
        return vals.astype(np.float32) / 8388608.0
    raise AudioInvalido("El formato del audio no es compatible. Vuelve a intentar.")


def _resample_linear(samples: np.ndarray, src_rate: int, dst_rate: int) -> np.ndarray:
    """Re-muestreo lineal (suficiente para voz; el navegador ya entrega 16 kHz en el
    camino normal — esto es la red de seguridad para navegadores que no puedan)."""
    if src_rate == dst_rate or samples.size == 0:
        return samples
    n_out = max(1, int(round(samples.size * dst_rate / src_rate)))
    x_out = np.linspace(0.0, samples.size - 1, n_out, dtype=np.float64)
    return np.interp(x_out, np.arange(samples.size, dtype=np.float64), samples).astype(
        np.float32
    )
