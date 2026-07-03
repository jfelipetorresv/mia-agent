"""
Mia · test_speech_stt.py — gate de CP-Z1 (dictado local — Ola 3).

Verifica OFFLINE (decodificación de audio, guardrail del pulido, la ruta con un
motor doble, rate-limit, candado de privacidad) y contra DB REAL (allow_cloud_audio
fail-closed por tenant). Si los pesos de Parakeet v3 están descargados en esta
máquina, corre además la INTEGRACIÓN real (transcribir el es.wav del modelo y un
audio largo por el camino del VAD); si no están, esos checks se saltan con aviso
(el dictado es opcional por instalación — la regresión no exige los pesos).

  A. audio.py: WAV PCM → float32 16 kHz mono (estéreo, 8/16/24/32 bits, re-muestreo);
     rechazos en lenguaje llano (vacío, corrupto, >5 min, >32 MB).
  B. engine.py: motor declarado LOCAL; disponibilidad honesta sin pesos.
  C. cleanup.py: guardrail anti-traducción/anti-invención; fail-soft sin Ollama.
  D. ruta /api/speech/transcribe: 503 sin motor, 400 audio malo, 413 tamaño,
     429 rate-limit, 403 si un motor NO-local no tiene opt-in del despacho,
     respuesta con text/cleaned_text/message.
  E. DB: allow_cloud_audio default False; solo `true` literal lo enciende;
     error de lectura → False (fail-closed).
  F. (si hay pesos) integración real: español correcto en es.wav; audio >60 s
     transcrito por el camino VAD/troceo.

Exit 0 = PASS · 1 = FAIL.     .venv\\Scripts\\python.exe execution\\test_speech_stt.py
"""
import asyncio
import io
import os
import sys
import wave
from pathlib import Path
from types import SimpleNamespace

import numpy as np
from dotenv import load_dotenv

if sys.platform == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

ROOT = Path(__file__).resolve().parents[1]
load_dotenv(ROOT / ".env")
sys.path.insert(0, str(ROOT / "backend"))
sys.path.insert(0, str(ROOT / "execution"))

_results: list = []


def check(name: str, ok) -> None:
    _results.append((name, bool(ok)))
    print(("  [OK]   " if ok else "  [FAIL] ") + name)


def _wav(samples: np.ndarray, rate=16000, channels=1, width=2) -> bytes:
    """WAV PCM en memoria a partir de float32 [-1,1]."""
    buf = io.BytesIO()
    with wave.open(buf, "wb") as wf:
        wf.setnchannels(channels)
        wf.setsampwidth(width)
        wf.setframerate(rate)
        if width == 2:
            wf.writeframes((samples * 32767).astype("<i2").tobytes())
        elif width == 4:
            wf.writeframes((samples * 2147483647).astype("<i4").tobytes())
        elif width == 1:
            wf.writeframes(((samples * 127) + 128).astype(np.uint8).tobytes())
    return buf.getvalue()


def _tone(seconds: float, rate=16000, hz=220.0) -> np.ndarray:
    t = np.arange(int(seconds * rate), dtype=np.float32) / rate
    return (0.3 * np.sin(2 * np.pi * hz * t)).astype(np.float32)


def audio_checks() -> None:
    from mia.speech import audio as sa

    mono = _tone(1.0)
    out = sa.decode_wav_to_pcm16k(_wav(mono))
    check("a-01 · WAV PCM16 16k mono → float32 16k, misma duración",
          out.dtype == np.float32 and abs(out.size - 16000) < 4
          and float(np.abs(out).max()) <= 1.0)

    stereo = np.repeat(mono, 2)  # L=R intercalado
    buf = io.BytesIO()
    with wave.open(buf, "wb") as wf:
        wf.setnchannels(2); wf.setsampwidth(2); wf.setframerate(16000)
        wf.writeframes((stereo * 32767).astype("<i2").tobytes())
    out2 = sa.decode_wav_to_pcm16k(buf.getvalue())
    check("a-02 · estéreo se mezcla a mono sin cambiar la duración",
          abs(out2.size - 16000) < 4 and np.allclose(out2[:100], out[:100], atol=1e-3))

    out48 = sa.decode_wav_to_pcm16k(_wav(_tone(1.0, rate=48000), rate=48000))
    check("a-03 · 48 kHz se re-muestrea a 16 kHz (1 s sigue siendo ~16000 muestras)",
          abs(out48.size - 16000) < 8)

    ok8 = sa.decode_wav_to_pcm16k(_wav(mono, width=1)).size > 0
    ok32 = sa.decode_wav_to_pcm16k(_wav(mono, width=4)).size > 0
    check("a-04 · PCM de 8 y 32 bits también decodifican", ok8 and ok32)

    # 24 bits (hallazgo capa 2: la aritmética de 3 bytes + signo no tenía red)
    ints24 = np.clip((mono * 8388607).astype(np.int64), -8388608, 8388607)
    b24 = np.zeros((ints24.size, 3), dtype=np.uint8)
    u = ints24.astype(np.uint32) & 0xFFFFFF
    b24[:, 0], b24[:, 1], b24[:, 2] = u & 0xFF, (u >> 8) & 0xFF, (u >> 16) & 0xFF
    buf24 = io.BytesIO()
    with wave.open(buf24, "wb") as wf:
        wf.setnchannels(1); wf.setsampwidth(3); wf.setframerate(16000)
        wf.writeframes(b24.tobytes())
    out24 = sa.decode_wav_to_pcm16k(buf24.getvalue())
    check("a-04b · PCM de 24 bits decodifica con signo correcto",
          out24.size == mono.size and float(np.abs(out24 - mono).max()) < 1e-3)

    def _rejects(data: bytes, frag: str) -> bool:
        try:
            sa.decode_wav_to_pcm16k(data)
            return False
        except sa.AudioInvalido as e:
            msg = str(e)
            # en llano: sin jerga técnica en lo que ve el abogado
            return frag in msg and not any(
                j in msg.lower() for j in ("pcm", "wav", "bytes", "sample", "hz"))

    check("a-05 · vacío → rechazo en llano", _rejects(b"", "vacía"))
    check("a-06 · corrupto → rechazo en llano", _rejects(b"no soy un wav" * 10, "audio"))

    # >5 min: WAV con cabecera que declara más frames de los permitidos
    long_wav = _wav(_tone(2.0))  # base corta; se edita el header no: mejor real corto a 8k
    big = _wav(_tone(301.0, rate=8000), rate=8000)
    check("a-07 · más de 5 minutos → rechazo en llano", _rejects(big, "5 minutos"))

    too_big = b"\x00" * (sa.MAX_UPLOAD_BYTES + 1)
    check("a-08 · más de 32 MB → rechazo en llano", _rejects(too_big, "grande"))


def engine_checks() -> None:
    from mia.speech import engine as se

    check("e-01 · el motor v1 se declara LOCAL (base del candado de privacidad)",
          se.ENGINE_IS_LOCAL is True)

    old = os.environ.get("MIA_SPEECH_MODELS_DIR")
    try:
        os.environ["MIA_SPEECH_MODELS_DIR"] = str(ROOT / "mia-data" / "no-existe-cpz1")
        eng = se.SpeechEngine()
        ok, reason = eng.available()
        check("e-02 · sin pesos descargados: no disponible y lo explica en llano",
              ok is False and "descargado" in reason and "onnx" not in reason.lower())
        try:
            eng.transcribe(np.zeros(16000, dtype=np.float32))
            check("e-03 · transcribir sin pesos lanza el motivo en llano", False)
        except RuntimeError as e:
            check("e-03 · transcribir sin pesos lanza el motivo en llano",
                  "descargado" in str(e))
    finally:
        if old is None:
            os.environ.pop("MIA_SPEECH_MODELS_DIR", None)
        else:
            os.environ["MIA_SPEECH_MODELS_DIR"] = old

    check("e-04 · parámetros de Lexter intactos (0.3 / 60 s / 1.25 s / 450 ms)",
          se.VAD_THRESHOLD == 0.3 and se.CHUNK_SECONDS == 60
          and se.MIN_CLIP_SECONDS == 1.25 and se.VAD_MARGIN_SECONDS == 0.45)


def cleanup_checks() -> None:
    from mia.speech import cleanup as sc

    orig = "el demandado no contestó la demanda dentro del término"
    check("c-01 · guardrail: acepta una corrección razonable en español",
          sc._looks_wrong(orig, "El demandado no contestó la demanda dentro del término.")
          is False)
    check("c-02 · guardrail: rechaza traducción al inglés",
          sc._looks_wrong(orig, "The defendant did not answer the claim in time")
          is True)
    # hallazgo capa 2: "no" existe en ambos idiomas y burlaba el guardrail v1
    check("c-02b · guardrail: rechaza traducción aunque comparta palabras ('no')",
          sc._looks_wrong("el testigo dijo que no hay prueba del contrato",
                          "The witness said there is no proof of the contract") is True)
    check("c-03 · guardrail: rechaza vacío, resumen y relleno",
          sc._looks_wrong(orig, "") and sc._looks_wrong(orig, "no contestó")
          and sc._looks_wrong(orig, orig * 3))

    from mia.agent import llm as llm_mod
    real = llm_mod.call_llm
    try:
        llm_mod.call_llm = lambda *a, **k: SimpleNamespace(choices=[SimpleNamespace(
            message=SimpleNamespace(content="El demandado no contestó la demanda "
                                            "dentro del término."))])
        check("c-04 · pulido con modelo local disponible → texto corregido",
              sc.polish_transcript(orig) is not None)

        captured: dict = {}

        def _capture(messages, **kw):
            captured.update(kw)
            raise ConnectionError("ollama apagado")

        llm_mod.call_llm = _capture
        out = sc.polish_transcript(orig)
        check("c-05 · sin Ollama corriendo → fail-soft (None, el dictado sale crudo)",
              out is None)
        check("c-06 · el pulido exige el modelo LOCAL (model=mia-local, sin nube)",
              captured.get("model") == "mia-local")
    finally:
        llm_mod.call_llm = real

    # Contrato del lado de llm.py (hallazgo capa 2): un model explícito debe
    # producir una cadena de UN alias — si un refactor futuro le agrega fallback
    # a la nube, este check lo delata.
    check("c-07 · resolve_fallback_chain('speech_cleanup', model='mia-local') "
          "== ['mia-local'] (sin fallback a nube)",
          llm_mod.resolve_fallback_chain("speech_cleanup", "mia-local") == ["mia-local"])

    from mia.api.middleware import OPEN_PATHS
    check("c-08 · /api/speech/transcribe exige autenticación (no es OPEN_PATH)",
          "/api/speech/transcribe" not in OPEN_PATHS)


class _FakeUpload:
    def __init__(self, data: bytes):
        self._data = data

    async def read(self, n: int = -1) -> bytes:
        return self._data if n < 0 else self._data[:n]


class _FakeEngine:
    def __init__(self, ok=True, reason="", text="hola mundo"):
        self._ok, self._reason, self._text = ok, reason, text

    def available(self):
        return self._ok, self._reason

    def transcribe(self, samples):
        return {"text": self._text, "duration_seconds": 1.0}


def _req(tenant="33333333-3333-3333-3333-333333333333", email="abogado@lexia.co"):
    return SimpleNamespace(state=SimpleNamespace(tenant_id=tenant, email=email))


async def route_checks() -> None:
    from fastapi import HTTPException
    from mia.api.routes import speech as route
    from mia.speech import engine as se

    wav_ok = _wav(_tone(1.0))
    real_get = route.speech_engine.get_engine

    def _status(coro) -> int:
        try:
            asyncio.get_event_loop()
        except Exception:
            pass
        return 0

    async def _call(**kw):
        try:
            return await route.transcribe(**kw)
        except HTTPException as e:
            return e

    try:
        route._clip_hits.clear()

        route.speech_engine.get_engine = lambda: _FakeEngine(
            ok=False, reason="El modelo de dictado no está descargado en este servidor. "
                             "Pide a tu administrador ejecutar scripts/download_speech_models.ps1.")
        r = await _call(request=_req(), audio=_FakeUpload(wav_ok), pulir=False)
        check("r-01 · motor no instalado → 503 con explicación en llano",
              isinstance(r, Exception) and r.status_code == 503
              and "descargado" in r.detail)

        route.speech_engine.get_engine = lambda: _FakeEngine()
        r = await _call(request=_req(), audio=_FakeUpload(b"basura"), pulir=False)
        check("r-02 · audio ilegible → 400 en llano",
              isinstance(r, Exception) and r.status_code == 400)

        r = await _call(request=_req(), audio=_FakeUpload(wav_ok), pulir=False)
        check("r-03 · clip válido → texto + duración + sin mensaje de error",
              isinstance(r, dict) and r["text"] == "hola mundo"
              and r["message"] is None and r["cleaned_text"] is None)

        route.speech_engine.get_engine = lambda: _FakeEngine(text="")
        r = await _call(request=_req(), audio=_FakeUpload(wav_ok), pulir=False)
        check("r-04 · clip sin voz → texto vacío con aviso honesto",
              isinstance(r, dict) and r["text"] == "" and "voz" in (r["message"] or ""))

        route.speech_engine.get_engine = lambda: _FakeEngine()
        big = b"\x00" * (route.speech_audio.MAX_UPLOAD_BYTES + 2)
        r = await _call(request=_req(), audio=_FakeUpload(big), pulir=False)
        check("r-05 · subida gigante → 413 (lectura acotada)",
              isinstance(r, Exception) and r.status_code == 413)

        route._clip_hits.clear()
        tenant = "44444444-4444-4444-4444-444444444444"
        last = None
        for _ in range(route._RATE_MAX_CLIPS + 1):
            last = await _call(request=_req(tenant, "ana@lexia.co"),
                               audio=_FakeUpload(wav_ok), pulir=False)
        check("r-06 · rate-limit por abogado → 429 al exceder los clips de la ventana",
              isinstance(last, Exception) and last.status_code == 429)
        # otro abogado DEL MISMO despacho conserva su cupo (hallazgo capa 2: no
        # castigar a las firmas con varios usuarios dictando a la vez)
        r_otro = await _call(request=_req(tenant, "beto@lexia.co"),
                             audio=_FakeUpload(wav_ok), pulir=False)
        check("r-06b · otro abogado del mismo despacho NO queda bloqueado por el primero",
              isinstance(r_otro, dict) and r_otro["text"] == "hola mundo")
        route._clip_hits.clear()

        # candado de privacidad: motor NO-local sin opt-in → 403; con opt-in pasa
        old_local = se.ENGINE_IS_LOCAL
        real_policy = route.speech_policy.allow_cloud_audio
        try:
            route.speech_engine.ENGINE_IS_LOCAL = False

            async def _deny(t):
                return False

            async def _allow(t):
                return True

            route.speech_policy.allow_cloud_audio = _deny
            r = await _call(request=_req(), audio=_FakeUpload(wav_ok), pulir=False)
            check("r-07 · motor de nube SIN opt-in del despacho → 403 (candado)",
                  isinstance(r, Exception) and r.status_code == 403
                  and "no autorizó" in r.detail)

            route.speech_policy.allow_cloud_audio = _allow
            r = await _call(request=_req(), audio=_FakeUpload(wav_ok), pulir=False)
            check("r-08 · motor de nube CON opt-in explícito → pasa",
                  isinstance(r, dict) and r["text"] == "hola mundo")
        finally:
            route.speech_engine.ENGINE_IS_LOCAL = old_local
            route.speech_policy.allow_cloud_audio = real_policy

        # pulido opcional: cableado y fail-soft
        real_polish = route.speech_cleanup.polish_transcript
        try:
            route.speech_cleanup.polish_transcript = lambda t: "Hola, mundo."
            r = await _call(request=_req(), audio=_FakeUpload(wav_ok), pulir=True)
            check("r-09 · pulir=true → cleaned_text del modelo local",
                  isinstance(r, dict) and r["cleaned_text"] == "Hola, mundo.")
            route.speech_cleanup.polish_transcript = lambda t: None
            r = await _call(request=_req(), audio=_FakeUpload(wav_ok), pulir=True)
            check("r-10 · pulido no disponible → el texto crudo se entrega igual",
                  isinstance(r, dict) and r["text"] == "hola mundo"
                  and r["cleaned_text"] is None)
        finally:
            route.speech_cleanup.polish_transcript = real_polish

        # sin tenant en el request (no autenticado de verdad) → 401
        r = await _call(request=SimpleNamespace(state=SimpleNamespace(tenant_id=None)),
                        audio=_FakeUpload(wav_ok), pulir=False)
        check("r-11 · sin contexto de tenant → 401", isinstance(r, Exception)
              and r.status_code == 401)
    finally:
        route.speech_engine.get_engine = real_get
        route._clip_hits.clear()


def _sb():
    import psycopg
    kw = dict(host=os.getenv("PG_HOST", "127.0.0.1"), port=os.getenv("PG_PORT", "5432"),
              dbname=os.getenv("PG_DB", "mia"), user="postgres",
              password=os.getenv("PG_PASSWORD", ""))
    return psycopg.connect(autocommit=True, **kw)


async def db_checks() -> None:
    from mia.db import pool
    from mia.speech import policy as sp

    await pool.open_pool()
    tenants: list[str] = []
    with _sb() as c:
        ta = str(c.execute("INSERT INTO tenants(name) VALUES('A voz cpz1') RETURNING id")
                 .fetchone()[0])
        tb = str(c.execute("INSERT INTO tenants(name) VALUES('B voz cpz1') RETURNING id")
                 .fetchone()[0])
    tenants.extend([ta, tb])
    try:
        check("p-db1 · sin fila en tenant_settings → allow_cloud_audio False (default)",
              await sp.allow_cloud_audio(ta) is False)

        with _sb() as c:
            c.execute(
                "INSERT INTO tenant_settings (tenant_id, config) VALUES (%s::uuid, "
                "'{\"speech\": {\"allow_cloud_audio\": true}}'::jsonb)", (ta,))
        check("p-db2 · opt-in explícito (true literal) → True",
              await sp.allow_cloud_audio(ta) is True)

        with _sb() as c:
            c.execute(
                "INSERT INTO tenant_settings (tenant_id, config) VALUES (%s::uuid, "
                "'{\"speech\": {\"allow_cloud_audio\": \"yes\"}}'::jsonb)", (tb,))
        check("p-db3 · valores no booleanos ('yes', 1) NO encienden el candado",
              await sp.allow_cloud_audio(tb) is False)

        check("p-db4 · error de lectura (id malformado) → False, fail-closed",
              await sp.allow_cloud_audio("esto-no-es-un-uuid") is False)
    finally:
        with _sb() as c:
            for t in tenants:
                c.execute("DELETE FROM tenant_settings WHERE tenant_id = %s::uuid", (t,))
                c.execute("DELETE FROM tenants WHERE id = %s::uuid", (t,))
        await pool.close_pool()


def integration_checks() -> None:
    from mia.speech import engine as se
    from mia.speech.audio import decode_wav_to_pcm16k

    eng = se.SpeechEngine()
    ok, _ = eng.available()
    es_wav = (se.models_dir() / se._PARAKEET_DIR / "test_wavs" / "es.wav")
    if not ok or not es_wav.is_file():
        print("  [SKIP] integración real: pesos de Parakeet no descargados en esta "
              "máquina (correr scripts/download_speech_models.ps1 para activarla)")
        return

    samples = decode_wav_to_pcm16k(es_wav.read_bytes())
    r = eng.transcribe(samples)
    check("i-01 · es.wav real → español correcto (contiene 'país')",
          "país" in r["text"] and r["duration_seconds"] > 4)

    # audio LARGO (>60 s): el clip de 5 s repetido 13 veces con pausas → camino VAD
    silence = np.zeros(8000, dtype=np.float32)
    tiled = np.concatenate([np.concatenate([samples, silence]) for _ in range(13)])
    r2 = eng.transcribe(tiled)
    check("i-02 · audio de %.0f s → camino VAD/troceo transcribe completo"
          % (tiled.size / 16000),
          r2["text"].count("país") >= 10)

    # hallazgo capa 2: >60 s de puro silencio no debe gastar STT (VAD → 0 trozos)
    import time as _t
    t0 = _t.time()
    r3 = eng.transcribe(np.zeros(70 * 16000, dtype=np.float32))
    check("i-03 · 70 s de silencio → texto vacío sin pasar por el STT (rápido)",
          r3["text"] == "" and (_t.time() - t0) < 3.0)


def main() -> int:
    print("== test_speech_stt (CP-Z1 · dictado local) ==")
    audio_checks()
    engine_checks()
    cleanup_checks()
    asyncio.run(route_checks())
    asyncio.run(db_checks())
    integration_checks()

    passed = sum(1 for _, ok in _results if ok)
    total = len(_results)
    print(f"\nRESULT: {passed}/{total} checks PASS")
    return 0 if passed == total else 1


if __name__ == "__main__":
    raise SystemExit(main())
