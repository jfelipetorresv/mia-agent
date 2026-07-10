"""Mia · speech.engine — motor de dictado local: Silero VAD + Parakeet TDT v3.

Reusa los modelos y parámetros que Lexter (fork de Handy, MIT) ya validó en
español jurídico (docs/analisis-lexter.md): 16 kHz mono float32, VAD Silero con
umbral 0.3, margen de voz ~450 ms (pre-roll/hangover del SmoothedVad de Lexter),
trozos de máximo 60 s, clips <1 s acolchados a 1.25 s. STT: Parakeet TDT 0.6B v3
int8 (decisión de Pipe 2026-07-02) vía sherpa-onnx (OfflineRecognizer nemo_transducer).

TODO es local y opcional: sin `sherpa-onnx` instalado o sin los pesos en disco
(se instalan desde el Panel de control — speech/install.py — o con
scripts/download_speech_models.ps1 como vía de administrador), `available()`
explica qué falta en llano y el endpoint responde 503 — ningún otro módulo de
Mia depende de esto.

El motor es un singleton de carga perezosa (el modelo pesa ~460 MB en disco;
se carga UNA vez al primer dictado). `transcribe()` es síncrono y con lock — la
ruta lo llama vía asyncio.to_thread y serializa la concurrencia.
"""
from __future__ import annotations

import logging
import os
import threading
from pathlib import Path

import numpy as np

from .. import config
from .audio import TARGET_RATE

logger = logging.getLogger(__name__)

# ¿El motor procesa el audio dentro de la infraestructura del despacho?
# Parakeet+Silero vía sherpa-onnx corren en el proceso del API → SÍ. Si algún día
# se agrega un motor de nube, DEBE declararse False y el candado allow_cloud_audio
# (policy.py) lo bloqueará por defecto.
ENGINE_IS_LOCAL = True

# Parámetros de Lexter (analisis-lexter.md) — no cambiar sin re-validar dictado.
VAD_THRESHOLD = 0.3
VAD_MARGIN_SECONDS = 0.45      # pre-roll y hangover del SmoothedVad(15,15,2)
VAD_MIN_SPEECH_SECONDS = 0.06  # onset 60 ms
CHUNK_SECONDS = 60             # trozos de STT para audios largos
MIN_CLIP_SECONDS = 1.25        # clips <1 s se acolchan a esto
# Hasta esta duración el clip va DIRECTO al STT (Parakeet tolera bien el silencio
# de un dictado corto); el VAD entra para recortar/partir audios largos.
DIRECT_STT_SECONDS = CHUNK_SECONDS

_PARAKEET_DIR = "sherpa-onnx-nemo-parakeet-tdt-0.6b-v3-int8"
_VAD_FILE = "silero_vad.onnx"


def models_dir() -> Path:
    """Carpeta de pesos (estado de instalación, gitignored). Configurable por .env."""
    raw = os.getenv("MIA_SPEECH_MODELS_DIR", "")
    if raw.strip():
        p = Path(raw.strip())
        return p if p.is_absolute() else (config.PROJECT_ROOT / p).resolve()
    return config.PROJECT_ROOT / "mia-data" / "models" / "speech"


class SpeechEngine:
    """VAD + STT locales con carga perezosa. Una instancia por proceso."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._recognizer = None
        self._vad_model_path: Path | None = None
        self._load_error: str | None = None

    # ---------- disponibilidad ----------

    def available(self) -> tuple[bool, str]:
        """(ok, razón en llano si no). NO carga el modelo: solo verifica requisitos."""
        try:
            import sherpa_onnx  # noqa: F401
        except ImportError:
            return False, (
                "El dictado no está instalado en este servidor "
                "(falta el componente de voz)."
            )
        pdir = models_dir() / _PARAKEET_DIR
        needed = ["encoder.int8.onnx", "decoder.int8.onnx", "joiner.int8.onnx", "tokens.txt"]
        if not all((pdir / f).is_file() for f in needed):
            return False, (
                "El modelo de dictado no está descargado en este servidor. "
                "Instálalo desde Configuración con el botón "
                "«Instalar dictado por voz»."
            )
        if self._load_error:
            return False, self._load_error
        return True, ""

    # ---------- carga ----------

    def _ensure_loaded(self):
        """Carga el reconocedor UNA vez (bajo lock). Lanza RuntimeError en llano si falla."""
        if self._recognizer is not None:
            return self._recognizer
        ok, reason = self.available()
        if not ok:
            raise RuntimeError(reason)
        import sherpa_onnx

        pdir = models_dir() / _PARAKEET_DIR
        provider = os.getenv("MIA_SPEECH_PROVIDER", "cpu").strip().lower() or "cpu"
        kwargs = dict(
            encoder=str(pdir / "encoder.int8.onnx"),
            decoder=str(pdir / "decoder.int8.onnx"),
            joiner=str(pdir / "joiner.int8.onnx"),
            tokens=str(pdir / "tokens.txt"),
            num_threads=int(os.getenv("MIA_SPEECH_THREADS", "4")),
            sample_rate=TARGET_RATE,
            feature_dim=80,
            model_type="nemo_transducer",
        )
        try:
            rec = sherpa_onnx.OfflineRecognizer.from_transducer(provider=provider, **kwargs)
        except Exception:
            if provider == "cpu":
                self._load_error = (
                    "El componente de dictado no pudo iniciarse en este servidor."
                )
                logger.exception("speech: fallo cargando Parakeet v3 (provider=cpu)")
                raise RuntimeError(self._load_error)
            # DirectML u otro provider no disponible en este build → CPU (declarado).
            logger.warning(
                "speech: provider %r no disponible; usando CPU (Parakeet int8 es "
                "rápido en CPU — ver analisis-lexter.md)", provider,
            )
            try:
                rec = sherpa_onnx.OfflineRecognizer.from_transducer(provider="cpu", **kwargs)
            except Exception:
                self._load_error = (
                    "El componente de dictado no pudo iniciarse en este servidor."
                )
                logger.exception("speech: fallo cargando Parakeet v3 (fallback cpu)")
                raise RuntimeError(self._load_error)
        vad_path = models_dir() / _VAD_FILE
        self._vad_model_path = vad_path if vad_path.is_file() else None
        if self._vad_model_path is None:
            logger.warning(
                "speech: silero_vad.onnx no está en %s — los audios largos se "
                "partirán en trozos fijos de %ss sin recorte de silencio",
                models_dir(), CHUNK_SECONDS,
            )
        self._recognizer = rec
        logger.info("speech: Parakeet v3 cargado (provider solicitado=%s)", provider)
        return rec

    # ---------- transcripción ----------

    def transcribe(self, samples: np.ndarray) -> dict:
        """PCM float32 16 kHz mono → {'text', 'duration_seconds'}. Síncrono; con lock
        (sherpa-onnx no garantiza streams concurrentes sobre el mismo reconocedor).

        Límite conocido (Riesgo #45): un clip muy corto de voz cortada a media palabra
        (<~0.7 s) puede transcribirse en otro idioma — Parakeet v3 es multilingüe y no
        se le fija idioma. Silencio y ruido puros SÍ devuelven vacío. El abogado revisa
        el texto antes de usarlo; mitigación futura = filtrar por segundos de voz del VAD."""
        with self._lock:
            rec = self._ensure_loaded()
            duration = float(samples.size) / TARGET_RATE
            if duration < MIN_CLIP_SECONDS:
                pad = int(MIN_CLIP_SECONDS * TARGET_RATE) - samples.size
                samples = np.pad(samples, (0, max(pad, 0)))
            if duration <= DIRECT_STT_SECONDS:
                chunks = [samples]
            else:
                chunks = self._split_long_audio(samples)
            parts: list[str] = []
            for chunk in chunks:
                if chunk.size == 0:
                    continue
                stream = rec.create_stream()
                stream.accept_waveform(TARGET_RATE, chunk)
                rec.decode_stream(stream)
                text = (stream.result.text or "").strip()
                if text:
                    parts.append(text)
            return {"text": " ".join(parts).strip(), "duration_seconds": round(duration, 2)}

    def _split_long_audio(self, samples: np.ndarray) -> list[np.ndarray]:
        """Audios > 60 s: segmentos de voz por VAD (Silero, umbral 0.3, margen 450 ms)
        agrupados en trozos ≤ 60 s. Sin VAD disponible → cortes fijos cada 60 s."""
        segments = self._vad_segments(samples)
        if segments is None:
            step = CHUNK_SECONDS * TARGET_RATE
            return [samples[i:i + step] for i in range(0, samples.size, step)]
        # Lista vacía = el VAD NO encontró voz: no hay nada que transcribir
        # (hallazgo capa 2: antes se mandaban 60 s de silencio al STT bajo el lock).
        chunks: list[np.ndarray] = []
        max_len = CHUNK_SECONDS * TARGET_RATE
        for start, end in segments:
            seg = samples[start:end]
            for i in range(0, seg.size, max_len):
                chunks.append(seg[i:i + max_len])
        return chunks

    def _vad_segments(self, samples: np.ndarray) -> list[tuple[int, int]] | None:
        """Índices (inicio, fin) de voz con margen de 450 ms, o None si el VAD no
        está disponible o falla (se degrada a cortes fijos, nunca rompe el dictado)."""
        if self._vad_model_path is None:
            return None
        try:
            import sherpa_onnx

            vcfg = sherpa_onnx.VadModelConfig()
            vcfg.silero_vad.model = str(self._vad_model_path)
            vcfg.silero_vad.threshold = VAD_THRESHOLD
            vcfg.silero_vad.min_silence_duration = VAD_MARGIN_SECONDS
            vcfg.silero_vad.min_speech_duration = VAD_MIN_SPEECH_SECONDS
            vcfg.sample_rate = TARGET_RATE
            window = int(vcfg.silero_vad.window_size) or 512
            vad = sherpa_onnx.VoiceActivityDetector(
                vcfg, buffer_size_in_seconds=float(len(samples)) / TARGET_RATE + 10.0
            )
            margin = int(VAD_MARGIN_SECONDS * TARGET_RATE)
            out: list[tuple[int, int]] = []

            def _drain() -> None:
                while not vad.empty():
                    seg = vad.front
                    start = max(0, int(seg.start) - margin)
                    end = min(samples.size, int(seg.start) + len(seg.samples) + margin)
                    out.append((start, end))
                    vad.pop()

            for i in range(0, samples.size, window):
                vad.accept_waveform(samples[i:i + window])
                _drain()
            vad.flush()
            _drain()
            if not out:
                return []
            # Funde solapes (los márgenes de 450 ms pueden encadenar segmentos vecinos).
            merged = [out[0]]
            for start, end in out[1:]:
                if start <= merged[-1][1]:
                    merged[-1] = (merged[-1][0], max(merged[-1][1], end))
                else:
                    merged.append((start, end))
            return merged
        except Exception:  # noqa: BLE001 — el VAD es optimización, no requisito
            logger.exception("speech: VAD falló; se usan cortes fijos de %ss", CHUNK_SECONDS)
            return None


# Singleton del proceso (la ruta lo usa; los gates lo reemplazan por un doble).
_engine: SpeechEngine | None = None
_engine_lock = threading.Lock()


def get_engine() -> SpeechEngine:
    global _engine
    if _engine is None:
        with _engine_lock:
            if _engine is None:
                _engine = SpeechEngine()
    return _engine
