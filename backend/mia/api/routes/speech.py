"""Mia · api.routes.speech — dictado local (CP-Z1, Ola 3).

POST /api/speech/transcribe — el botón de micrófono de la web envía un clip WAV
(16 kHz mono; el backend tolera y re-muestrea si no) y recibe el texto dictado.
Todo el procesamiento es LOCAL (Silero VAD + Parakeet v3 vía sherpa-onnx): el
audio nunca sale del servidor del despacho.

Salvaguardas:
  - Autenticación: el middleware exige Bearer en /api/* (no es OPEN_PATH).
  - Candado de privacidad (policy.py): motor de nube requeriría opt-in explícito
    del despacho (allow_cloud_audio, default False fail-closed). El motor v1 es
    local → hoy el candado no bloquea a nadie, pero la exigencia es estructural.
  - Topes: 32 MB / 5 min por clip (audio.py) + rate-limit por despacho
    (20 clips / 5 min, en memoria — Modo B 1 worker, mismo criterio que auth.py).
  - Concurrencia: el STT es trabajo de CPU → corre en un thread y un semáforo
    global lo serializa (los clips en cola esperan, no tumban el event loop).
  - Pulido opcional (`pulir=true`): SOLO con el modelo local (cleanup.py);
    fail-soft — sin Ollama corriendo, el texto sale crudo.
"""
from __future__ import annotations

import asyncio
import logging
import os
import time
from contextlib import asynccontextmanager

from fastapi import APIRouter, File, Form, HTTPException, Request, Response, UploadFile
from pydantic import BaseModel

from ...speech import audio as speech_audio
from ...speech import cleanup as speech_cleanup
from ...speech import engine as speech_engine
from ...speech import install as speech_install
from ...speech import opus as speech_opus
from ...speech import policy as speech_policy
from ...speech import tts as speech_tts

logger = logging.getLogger(__name__)

router = APIRouter(tags=["speech"])

# Rate-limit por ABOGADO (tenant + email del JWT, hallazgo capa 2): dictar 20
# clips en 5 minutos es uso humano intenso para UNA persona; por despacho
# castigaría a las firmas con varios abogados dictando a la vez. En memoria
# (1 worker, Modo B); si algún día hubiera un despliegue multi-worker, migrar
# a contador compartido (mismo apunte que auth.py).
_RATE_MAX_CLIPS = 20
_RATE_WINDOW_SECONDS = 5 * 60
_clip_hits: dict[tuple[str, str], list[float]] = {}

# El STT/TTS satura CPU: un semáforo global serializa las operaciones de voz del
# proceso (una nota de voz de Telegram encadena transcribe + synthesize sobre él).
_stt_semaphore = asyncio.Semaphore(max(1, int(os.getenv("MIA_SPEECH_CONCURRENCY", "1"))))
# Tope de espera por transcripción/síntesis: si el motor se cuelga (modelo
# corrupto, bug de runtime), el request responde 503 en vez de dejar la voz
# muerta para siempre. El thread colgado queda zombi con el lock — límite declarado.
_STT_TIMEOUT_SECONDS = max(60, int(os.getenv("MIA_SPEECH_TIMEOUT", "240")))
# Tope de espera para ADQUIRIR el semáforo (no solo para la operación): bajo
# contención (p. ej. dictado por web + nota de voz de Telegram simultáneos) un
# turno no debe quedarse colgado hasta el timeout HTTP del puente (~5 min) y
# degradar en silencio — responde un 503 explícito y honesto (hallazgo capa 2).
# 45s deja margen bajo el timeout HTTP del puente (300s): 45 + _STT_TIMEOUT (240)
# = 285 < 300, sin el empate al límite que señaló la re-verificación de capa 2.
_ACQUIRE_TIMEOUT_SECONDS = max(10, int(os.getenv("MIA_SPEECH_ACQUIRE_TIMEOUT", "45")))


@asynccontextmanager
async def _speech_slot():
    """Adquiere el semáforo de voz con tope de espera. Si el componente está
    ocupado más de _ACQUIRE_TIMEOUT_SECONDS, 503 en llano en vez de colgar."""
    try:
        await asyncio.wait_for(_stt_semaphore.acquire(), timeout=_ACQUIRE_TIMEOUT_SECONDS)
    except asyncio.TimeoutError:
        raise HTTPException(
            status_code=503,
            detail="El componente de voz está ocupado en este momento. "
                   "Intenta de nuevo en unos segundos.",
        )
    try:
        yield
    finally:
        _stt_semaphore.release()


class SpeechInstallBody(BaseModel):
    """Consent-first (patrón Instalar Obsidian): sin confirmación explícita no
    se descarga nada. El default False hace que un POST vacío sea un rechazo."""

    confirmar: bool = False


class SynthesizeBody(BaseModel):
    """Texto a convertir en voz. La respuesta es audio OGG/Opus (nota de voz)."""

    text: str = ""


def _tenant(request: Request) -> str:
    t = getattr(request.state, "tenant_id", None)
    if not t:
        raise HTTPException(
            status_code=401, detail="Tu sesión no es válida. Vuelve a iniciar sesión."
        )
    return t


def _check_rate(tenant_id: str, email: str) -> None:
    now = time.monotonic()
    key = (tenant_id, email or "")
    hits = [t for t in _clip_hits.get(key, []) if now - t < _RATE_WINDOW_SECONDS]
    if len(hits) >= _RATE_MAX_CLIPS:
        _clip_hits[key] = hits
        raise HTTPException(
            status_code=429,
            detail="Se dictaron muchos clips seguidos. Espera un momento e intenta de nuevo.",
        )
    hits.append(now)
    _clip_hits[key] = hits
    # Poda: claves cuya ventana quedó vacía no deben vivir para siempre (auth.py).
    for k in [k for k, v in _clip_hits.items()
              if k != key and (not v or now - v[-1] >= _RATE_WINDOW_SECONDS)]:
        del _clip_hits[k]


@router.post("/speech/transcribe")
async def transcribe(
    request: Request,
    audio: UploadFile = File(...),
    pulir: bool = Form(False),
):
    tenant_id = _tenant(request)
    _check_rate(tenant_id, getattr(request.state, "email", "") or "")

    eng = speech_engine.get_engine()
    ok, reason = eng.available()
    if not ok:
        raise HTTPException(status_code=503, detail=reason)

    # Candado de privacidad (Ola 3): un motor que NO sea local exige el opt-in
    # explícito del despacho. Se verifica en CADA dictado, no al configurar.
    if not speech_engine.ENGINE_IS_LOCAL:
        if not await speech_policy.allow_cloud_audio(tenant_id):
            raise HTTPException(
                status_code=403,
                detail=(
                    "Este despacho no autorizó enviar audio fuera del servidor. "
                    "El dictado en la nube está apagado."
                ),
            )

    # Lectura ACOTADA (mismo criterio que la subida de documentos, auditoría 2026-07).
    data = await audio.read(speech_audio.MAX_UPLOAD_BYTES + 1)
    if len(data) > speech_audio.MAX_UPLOAD_BYTES:
        raise HTTPException(
            status_code=413,
            detail="La grabación es demasiado grande. Dicta en clips más cortos.",
        )
    # Decodificación y STT: AMBOS son trabajo de CPU (numpy sobre hasta 32 MB +
    # el modelo) → van a un thread y DENTRO del semáforo, para que N clips
    # simultáneos jamás congelen el event loop del API (hallazgo capa 2: antes la
    # decodificación corría en el loop y frenaba los SSE de otros abogados).
    async with _speech_slot():
        try:
            samples = await asyncio.to_thread(speech_audio.decode_audio_to_pcm16k, data)
        except speech_audio.AudioInvalido as e:
            raise HTTPException(status_code=400, detail=str(e))
        try:
            result = await asyncio.wait_for(
                asyncio.to_thread(eng.transcribe, samples),
                timeout=_STT_TIMEOUT_SECONDS,
            )
        except asyncio.TimeoutError:
            logger.error("speech: transcripción excedió %ss (tenant=%s) — posible "
                         "motor colgado", _STT_TIMEOUT_SECONDS, tenant_id)
            raise HTTPException(
                status_code=503,
                detail="El dictado está tardando demasiado. Intenta con un clip más corto.",
            )
        except RuntimeError as e:
            # El motor explicó en llano por qué no pudo (modelo ausente/corrupto).
            raise HTTPException(status_code=503, detail=str(e))
        except Exception:
            logger.exception("speech: fallo transcribiendo un clip (tenant=%s)", tenant_id)
            raise HTTPException(
                status_code=500,
                detail="No se pudo transcribir el dictado. Vuelve a intentarlo.",
            )

    text = result.get("text", "")
    cleaned = None
    if pulir and text:
        cleaned = await asyncio.to_thread(speech_cleanup.polish_transcript, text)

    return {
        "text": text,
        "cleaned_text": cleaned,
        "duration_seconds": result.get("duration_seconds", 0.0),
        "message": None if text else "No se escuchó voz en la grabación.",
    }


@router.post("/speech/synthesize")
async def synthesize(request: Request, body: SynthesizeBody):
    """Texto → nota de voz OGG/Opus, 100% local (CP-Z2). La usa el puente de
    Telegram para que Mia responda hablando. Mismas salvaguardas que transcribe:
    auth, rate-limit por abogado, candado de privacidad y semáforo de CPU."""
    tenant_id = _tenant(request)
    _check_rate(tenant_id, getattr(request.state, "email", "") or "")

    text = (body.text or "").strip()
    if not text:
        raise HTTPException(status_code=400, detail="No hay texto para convertir en voz.")
    if len(text) > speech_tts.MAX_TTS_CHARS:
        raise HTTPException(
            status_code=413,
            detail="El texto es demasiado largo para una nota de voz.",
        )

    eng = speech_tts.get_tts_engine()
    ok, reason = eng.available()
    if not ok:
        raise HTTPException(status_code=503, detail=reason)

    # Candado de privacidad (Ola 3): un motor de voz que NO sea local exigiría el
    # opt-in explícito del despacho. El TTS v1 es local → hoy no bloquea, pero la
    # exigencia es estructural (idéntico a transcribe).
    if not speech_tts.TTS_IS_LOCAL:
        if not await speech_policy.allow_cloud_audio(tenant_id):
            raise HTTPException(
                status_code=403,
                detail=(
                    "Este despacho no autorizó procesar la voz fuera del servidor. "
                    "La voz en la nube está apagada."
                ),
            )

    # Síntesis + codificación: ambos trabajo de CPU → thread DENTRO del semáforo
    # (compartido con el STT: una operación de voz a la vez por proceso).
    async with _speech_slot():
        try:
            result = await asyncio.wait_for(
                asyncio.to_thread(eng.synthesize, text),
                timeout=_STT_TIMEOUT_SECONDS,
            )
        except asyncio.TimeoutError:
            logger.error("speech.tts: síntesis excedió %ss (tenant=%s)",
                         _STT_TIMEOUT_SECONDS, tenant_id)
            raise HTTPException(
                status_code=503,
                detail="La voz está tardando demasiado. Intenta con un texto más corto.",
            )
        except RuntimeError as e:
            raise HTTPException(status_code=503, detail=str(e))
        except Exception:
            logger.exception("speech.tts: fallo sintetizando (tenant=%s)", tenant_id)
            raise HTTPException(
                status_code=500,
                detail="No se pudo generar la voz. Vuelve a intentarlo.",
            )

        samples = result.get("samples")
        sample_rate = int(result.get("sample_rate", 0))
        if samples is None or getattr(samples, "size", 0) == 0 or sample_rate <= 0:
            raise HTTPException(
                status_code=500,
                detail="No se pudo generar la voz. Vuelve a intentarlo.",
            )
        try:
            ogg = await asyncio.to_thread(
                speech_opus.encode_pcm_to_ogg_opus, samples, sample_rate
            )
        except speech_audio.AudioInvalido as e:
            raise HTTPException(status_code=500, detail=str(e))

    return Response(content=ogg, media_type="audio/ogg")


@router.get("/speech/status")
async def speech_status(request: Request):
    """Estado del dictado para la tarjeta del Panel y el botón de micrófono:
    instalado / no instalado / descargando (con progreso) / error, en llano."""
    _tenant(request)
    # get_status toca disco (stat de ≤6 archivos) → thread, patrón _detected.
    return await asyncio.to_thread(speech_install.get_status)


@router.post("/speech/install")
async def speech_install_models(request: Request, body: SpeechInstallBody):
    """Descarga los modelos de dictado EN el servidor (background, single-flight).
    Solo escribe en el data-dir de Mia — no instala software en el host."""
    _tenant(request)
    if not body.confirmar:
        raise HTTPException(
            status_code=400,
            detail=(
                "Para continuar necesito tu confirmación: esta acción descarga "
                "el componente de dictado por voz (~700 MB) en el servidor. "
                "Vuelve a intentarlo confirmando la descarga."
            ),
        )
    return await asyncio.to_thread(speech_install.start_install)
