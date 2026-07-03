"""
Mia · test_speech_tts.py — gate de CP-Z2 (voz de salida local + notas de voz).

Verifica OFFLINE la síntesis de voz local y el códec OGG/Opus de Telegram con
dobles (sin descargar pesos reales salvo la sección de integración, que se salta
si el modelo de voz no está en esta máquina):

  A. opus.py: round-trip encode(PCM)→decode(OGG/Opus)→PCM 16k; rechazos en
     lenguaje llano (vacío, no-Opus, >32 MB); encode de audio vacío rechazado.
  B. audio.py: el despachador enruta OggS→Opus y RIFF→WAV transparentemente.
  C. tts.py: motor declarado LOCAL; disponibilidad honesta sin pesos (en llano);
     texto vacío → audio vacío; texto larguísimo → recortado a MAX_TTS_CHARS.
  D. ruta /api/speech/synthesize: 400 texto vacío, 413 muy largo, 503 sin motor,
     429 rate-limit, 403 si un motor NO-local no tiene opt-in del despacho,
     200 con audio OGG/Opus; exige autenticación (no OPEN_PATH, 401 sin tenant).
  E. (si hay pesos) integración real: sintetiza español y el audio round-trip
     por Opus vuelve como PCM no vacío.

Exit 0 = PASS · 1 = FAIL.     .venv\\Scripts\\python.exe execution\\test_speech_tts.py
"""
import asyncio
import os
import sys
from pathlib import Path
from types import SimpleNamespace

import numpy as np

if sys.platform == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

_results: list = []


def check(name: str, ok) -> None:
    _results.append((name, bool(ok)))
    print(("  [OK]   " if ok else "  [FAIL] ") + name)


def _tone(seconds: float, rate=22050, hz=180.0) -> np.ndarray:
    t = np.arange(int(seconds * rate), dtype=np.float32) / rate
    return (0.3 * np.sin(2 * np.pi * hz * t)).astype(np.float32)


def opus_checks() -> None:
    from mia.speech import opus as so

    tone = _tone(0.6)
    ogg = so.encode_pcm_to_ogg_opus(tone, 22050)
    check("a-01 · encode PCM → OGG/Opus (bytes con cabecera OggS)",
          len(ogg) > 0 and ogg[:4] == b"OggS")

    pcm = so.decode_ogg_opus_to_pcm16k(ogg)
    check("a-02 · decode OGG/Opus → PCM 16 kHz mono float32, duración ~igual",
          pcm.dtype == np.float32 and abs(pcm.size / 16000 - 0.6) < 0.1)

    def _rejects(fn, frag: str) -> bool:
        try:
            fn()
            return False
        except so.AudioInvalido as e:
            msg = str(e)
            return frag in msg and not any(
                j in msg.lower() for j in ("opus", "ogg", "codec", "pcm", "av"))

    check("a-03 · decode de bytes vacíos → rechazo en llano",
          _rejects(lambda: so.decode_ogg_opus_to_pcm16k(b""), "vacía"))
    check("a-04 · decode de algo que NO es Opus → rechazo en llano",
          _rejects(lambda: so.decode_ogg_opus_to_pcm16k(b"no soy opus" * 20), "voz"))
    check("a-05 · decode de una nota > 32 MB → rechazo en llano",
          _rejects(lambda: so.decode_ogg_opus_to_pcm16k(b"\x00" * (so.MAX_UPLOAD_BYTES + 1)),
                   "grande"))
    check("a-06 · encode de audio vacío → rechazo en llano",
          _rejects(lambda: so.encode_pcm_to_ogg_opus(np.zeros(0, dtype=np.float32), 22050),
                   "audio"))


def audio_dispatch_checks() -> None:
    import io
    import wave

    from mia.speech import audio as sa
    from mia.speech import opus as so

    # OggS → camino Opus
    ogg = so.encode_pcm_to_ogg_opus(_tone(0.5), 22050)
    pcm_opus = sa.decode_audio_to_pcm16k(ogg)
    check("b-01 · el despachador enruta OGG/Opus (cabecera OggS) al códec Opus",
          pcm_opus.size > 0 and abs(pcm_opus.size / 16000 - 0.5) < 0.1)

    # RIFF → camino WAV stdlib
    buf = io.BytesIO()
    with wave.open(buf, "wb") as wf:
        wf.setnchannels(1); wf.setsampwidth(2); wf.setframerate(16000)
        wf.writeframes((_tone(0.5, rate=16000) * 32767).astype("<i2").tobytes())
    pcm_wav = sa.decode_audio_to_pcm16k(buf.getvalue())
    check("b-02 · el despachador enruta WAV (cabecera RIFF) al decodificador stdlib",
          pcm_wav.size > 0 and abs(pcm_wav.size - 8000) < 8)

    check("b-03 · entrada vacía → rechazo en llano (sin jerga)",
          _dispatch_rejects(sa, b"", "vacía"))


def _dispatch_rejects(sa, data, frag) -> bool:
    try:
        sa.decode_audio_to_pcm16k(data)
        return False
    except sa.AudioInvalido as e:
        return frag in str(e)


def tts_engine_checks() -> None:
    from mia.speech import tts as st

    check("c-01 · el motor de voz v1 se declara LOCAL (base del candado)",
          st.TTS_IS_LOCAL is True)
    check("c-02 · hay tope de caracteres por síntesis (nota de voz, no un escrito)",
          isinstance(st.MAX_TTS_CHARS, int) and st.MAX_TTS_CHARS > 0)

    old = os.environ.get("MIA_SPEECH_MODELS_DIR")
    try:
        os.environ["MIA_SPEECH_MODELS_DIR"] = str(ROOT / "mia-data" / "no-existe-cpz2")
        eng = st.TtsEngine()
        ok, reason = eng.available()
        check("c-03 · sin pesos de voz: no disponible y lo explica en llano",
              ok is False and "descargado" in reason and "onnx" not in reason.lower())
    finally:
        if old is None:
            os.environ.pop("MIA_SPEECH_MODELS_DIR", None)
        else:
            os.environ["MIA_SPEECH_MODELS_DIR"] = old

    # texto vacío → audio vacío SIN cargar el modelo (retorno temprano)
    eng2 = st.TtsEngine()
    r = eng2.synthesize("   ")
    check("c-04 · texto vacío → samples vacío, sin cargar el modelo",
          r["samples"].size == 0 and r["sample_rate"] == 0)

    # recorte a MAX_TTS_CHARS: motor con un sherpa falso que captura el texto
    captured: dict = {}

    class _FakeSherpa:
        def generate(self, text, sid=0, speed=1.0):
            captured["text"] = text
            captured["sid"] = sid
            return SimpleNamespace(samples=np.zeros(10, dtype=np.float32), sample_rate=22050)

    eng3 = st.TtsEngine()
    eng3._ensure_loaded = lambda: _FakeSherpa()  # noqa: SLF001 — doble de prueba
    eng3.synthesize("hola " * 1000)  # ~5000 chars, > MAX_TTS_CHARS
    check("c-05 · texto larguísimo → recortado a MAX_TTS_CHARS antes de sintetizar",
          len(captured.get("text", "")) == st.MAX_TTS_CHARS)


class _FakeTtsEngine:
    def __init__(self, ok=True, reason=""):
        self._ok, self._reason = ok, reason

    def available(self):
        return self._ok, self._reason

    def synthesize(self, text):
        # audio real corto para que el códec Opus de la ruta trabaje de verdad
        return {"samples": _tone(0.4), "sample_rate": 22050}


def _req(tenant="55555555-5555-5555-5555-555555555555", email="abogado@lexia.co"):
    return SimpleNamespace(state=SimpleNamespace(tenant_id=tenant, email=email))


async def route_checks() -> None:
    from fastapi import HTTPException, Response
    from mia.api.routes import speech as route
    from mia.speech import tts as st

    async def _call(**kw):
        try:
            return await route.synthesize(**kw)
        except HTTPException as e:
            return e

    real_get = route.speech_tts.get_tts_engine
    try:
        route._clip_hits.clear()
        route.speech_tts.get_tts_engine = lambda: _FakeTtsEngine()

        r = await _call(request=_req(), body=route.SynthesizeBody(text="   "))
        check("d-01 · texto vacío → 400 en llano",
              isinstance(r, Exception) and r.status_code == 400)

        long_text = "a" * (st.MAX_TTS_CHARS + 1)
        r = await _call(request=_req(), body=route.SynthesizeBody(text=long_text))
        check("d-02 · texto más largo que el tope → 413",
              isinstance(r, Exception) and r.status_code == 413)

        route.speech_tts.get_tts_engine = lambda: _FakeTtsEngine(
            ok=False, reason="El modelo de voz de Mia no está descargado en este "
                             "servidor. Instálalo desde el Panel de control.")
        r = await _call(request=_req(), body=route.SynthesizeBody(text="Hola Pipe."))
        check("d-03 · motor de voz no instalado → 503 con explicación en llano",
              isinstance(r, Exception) and r.status_code == 503 and "descargado" in r.detail)

        route.speech_tts.get_tts_engine = lambda: _FakeTtsEngine()
        r = await _call(request=_req(), body=route.SynthesizeBody(text="Hola Pipe."))
        check("d-04 · texto válido → 200 con audio OGG/Opus (audio/ogg)",
              isinstance(r, Response) and r.media_type == "audio/ogg"
              and len(r.body) > 0 and r.body[:4] == b"OggS")

        # candado de privacidad: motor NO-local sin opt-in → 403; con opt-in pasa
        old_local = st.TTS_IS_LOCAL
        real_policy = route.speech_policy.allow_cloud_audio
        try:
            route.speech_tts.TTS_IS_LOCAL = False

            async def _deny(t):
                return False

            async def _allow(t):
                return True

            route.speech_policy.allow_cloud_audio = _deny
            r = await _call(request=_req(), body=route.SynthesizeBody(text="Hola."))
            check("d-05 · motor de voz de nube SIN opt-in → 403 (candado)",
                  isinstance(r, Exception) and r.status_code == 403
                  and "no autorizó" in r.detail)

            route.speech_policy.allow_cloud_audio = _allow
            r = await _call(request=_req(), body=route.SynthesizeBody(text="Hola."))
            check("d-06 · motor de voz de nube CON opt-in explícito → pasa",
                  isinstance(r, Response) and r.media_type == "audio/ogg")
        finally:
            route.speech_tts.TTS_IS_LOCAL = old_local
            route.speech_policy.allow_cloud_audio = real_policy

        # rate-limit por abogado (comparte contador con transcribe)
        route._clip_hits.clear()
        tenant = "66666666-6666-6666-6666-666666666666"
        last = None
        for _ in range(route._RATE_MAX_CLIPS + 1):
            last = await _call(request=_req(tenant, "ana@lexia.co"),
                               body=route.SynthesizeBody(text="Hola."))
        check("d-07 · rate-limit por abogado → 429 al exceder la ventana",
              isinstance(last, Exception) and last.status_code == 429)
        route._clip_hits.clear()

        # sin tenant → 401
        r = await _call(request=SimpleNamespace(state=SimpleNamespace(tenant_id=None)),
                        body=route.SynthesizeBody(text="Hola."))
        check("d-08 · sin contexto de tenant → 401",
              isinstance(r, Exception) and r.status_code == 401)

        # componente ocupado (semáforo tomado) → 503 explícito, NO cuelga (capa 2)
        route._clip_hits.clear()
        route.speech_tts.get_tts_engine = lambda: _FakeTtsEngine()
        old_acq = route._ACQUIRE_TIMEOUT_SECONDS
        await route._stt_semaphore.acquire()   # ocupa el único slot del proceso
        try:
            route._ACQUIRE_TIMEOUT_SECONDS = 0.05
            r = await _call(request=_req("77777777-7777-7777-7777-777777777777",
                                         "ocupado@lexia.co"),
                            body=route.SynthesizeBody(text="Hola."))
            check("d-10 · componente de voz ocupado → 503 en llano, no cuelga",
                  isinstance(r, Exception) and r.status_code == 503
                  and "ocupado" in r.detail)
        finally:
            route._ACQUIRE_TIMEOUT_SECONDS = old_acq
            route._stt_semaphore.release()
    finally:
        route.speech_tts.get_tts_engine = real_get
        route._clip_hits.clear()

    from mia.api.middleware import OPEN_PATHS
    check("d-09 · /api/speech/synthesize exige autenticación (no es OPEN_PATH)",
          "/api/speech/synthesize" not in OPEN_PATHS)


def integration_checks() -> None:
    from mia.speech import opus as so
    from mia.speech import tts as st

    eng = st.get_tts_engine()
    ok, _ = eng.available()
    if not ok:
        print("  [SKIP] integración real: el modelo de voz (VITS es) no está "
              "descargado en esta máquina (correr scripts/download_speech_models.ps1)")
        return
    r = eng.synthesize("Hola Pipe, el borrador del caso Zurich ya quedó listo.")
    check("i-01 · síntesis real en español → audio no vacío",
          r["samples"].size > 0 and r["sample_rate"] > 0)
    ogg = so.encode_pcm_to_ogg_opus(r["samples"], r["sample_rate"])
    pcm = so.decode_ogg_opus_to_pcm16k(ogg)
    check("i-02 · el audio sintetizado round-trip por Opus vuelve como PCM no vacío",
          ogg[:4] == b"OggS" and pcm.size > 0)


def main() -> int:
    print("== test_speech_tts (CP-Z2 · voz de salida + notas de voz de Telegram) ==")
    opus_checks()
    audio_dispatch_checks()
    tts_engine_checks()
    asyncio.run(route_checks())
    integration_checks()

    passed = sum(1 for _, ok in _results if ok)
    total = len(_results)
    print(f"\nRESULT: {passed}/{total} checks PASS")
    return 0 if passed == total else 1


if __name__ == "__main__":
    raise SystemExit(main())
