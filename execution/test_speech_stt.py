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
  G. install.py + rutas status/install (CP-Z1b): instalación desde el producto —
     consent-first (400 sin confirmar), single-flight, progreso visible, retry
     limpio tras fallo de red, anti path-traversal fail-closed, idempotencia.
     Con MIA_SPEECH_MODELS_DIR → tempdir y _download reemplazada: JAMÁS se
     descargan los pesos reales ni se tocan los ya instalados en esta máquina.

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


def _fake_tar(members: dict[str, bytes]) -> bytes:
    """tar.bz2 pequeño en memoria — ejercita la extracción REAL sin bajar 650 MB."""
    import tarfile

    buf = io.BytesIO()
    with tarfile.open(fileobj=buf, mode="w:bz2") as tf:
        for name, data in members.items():
            info = tarfile.TarInfo(name)
            info.size = len(data)
            tf.addfile(info, io.BytesIO(data))
    return buf.getvalue()


def install_checks() -> None:
    import tempfile
    import threading
    import urllib.error

    from mia.speech import engine as se
    from mia.speech import install as si

    def _reset() -> None:
        with si._state_lock:
            si._thread = None
            si._state.update(status="no_instalado", phase=None, bytes_done=0,
                             bytes_total=None, error=None)

    def _join(timeout=10.0) -> None:
        t = si._thread
        if t is not None:
            t.join(timeout)

    parakeet_members = {
        f"{se._PARAKEET_DIR}/{n}": b"fake-model-bytes"
        for n in ["encoder.int8.onnx", "decoder.int8.onnx",
                  "joiner.int8.onnx", "tokens.txt"]
    }
    good_tar = _fake_tar(parakeet_members)
    fake_vad = b"\x00" * (600 * 1024)  # ≥ 500 KB, pasa el umbral de sanidad
    # CP-Z2: la instalación ahora también baja el modelo de VOZ (TTS). El tar
    # falso trae sus archivos para no descargar el modelo real (~67 MB).
    tts_members = {f"{si._TTS_DIR}/{n}": b"fake-voice-bytes" for n in si._TTS_FILES}
    good_tts_tar = _fake_tar(tts_members)

    old_env = os.environ.get("MIA_SPEECH_MODELS_DIR")
    real_download = si._download
    tmp = tempfile.mkdtemp(prefix="mia-cpz1b-")
    gate = threading.Event()  # libera la descarga bloqueada (también en finally)
    try:
        os.environ["MIA_SPEECH_MODELS_DIR"] = tmp
        dest = Path(tmp)
        _reset()

        st = si.get_status()
        jerga = ("onnx", "tar.bz2", "ps1", "script", "thread", "endpoint")
        check("g-01 · sin modelos → no_instalado con mensaje en llano",
              st["estado"] == "no_instalado" and st["listo"] is False
              and st["progreso"] is None
              and not any(j in st["mensaje"].lower() for j in jerga))

        # g-03/g-04/g-05/g-06 · flujo completo con la descarga BLOQUEADA a mitad
        def _blocked(url, path, on_progress):
            if "silero" in url:
                path.write_bytes(fake_vad)
                return
            if "tts-models" in url:
                path.write_bytes(good_tts_tar)
                return
            on_progress(10 * 1024 * 1024, 460 * 1024 * 1024)
            gate.wait(10)
            path.write_bytes(good_tar)
            on_progress(460 * 1024 * 1024, 460 * 1024 * 1024)

        si._download = _blocked
        r1 = si.start_install()
        first_thread = si._thread
        check("g-03a · con confirmación → arranca en background ('descargando')",
              r1["status"] == "descargando" and first_thread is not None)

        # el hilo reporta el primer avance enseguida, pero no es instantáneo
        import time as _t
        deadline = _t.time() + 5
        st = si.get_status()
        while (not (st.get("progreso") or {}).get("descargado_mb")
               and _t.time() < deadline):
            _t.sleep(0.05)
            st = si.get_status()
        prog = st.get("progreso") or {}
        check("g-05 · progreso visible durante la descarga (MB y porcentaje coherentes)",
              st["estado"] == "descargando" and prog.get("descargado_mb") == 10
              and prog.get("total_mb") == 460 and prog.get("porcentaje") == 2
              and "MB" in st["mensaje"])

        r2 = si.start_install()
        check("g-04 · single-flight: segundo clic → 'ya en curso', sin segundo hilo",
              r2["status"] == "descargando" and "curso" in r2["message"]
              and si._thread is first_thread)

        gate.set()
        _join()
        st = si.get_status()
        files_ok = all((dest / se._PARAKEET_DIR / n).is_file()
                       for n in ["encoder.int8.onnx", "decoder.int8.onnx",
                                 "joiner.int8.onnx", "tokens.txt"])
        tts_ok = all((dest / si._TTS_DIR / n).is_file() for n in si._TTS_FILES)
        check("g-03 · al terminar: instalado con dictado (4) + voz (TTS) + VAD",
              st["estado"] == "instalado" and st["listo"] is True and files_ok
              and tts_ok and (dest / "silero_vad.onnx").is_file())
        check("g-06 · ni tarball ni .part quedan en disco tras el éxito",
              not list(dest.glob("*.tar.bz2")) and not list(dest.glob("*.part")))

        calls: list[str] = []

        def _spy(url, path, on_progress):
            calls.append(url)
            raise AssertionError("no debería descargar nada")

        si._download = _spy
        r3 = si.start_install()
        check("g-09 · reinvocar ya instalado → idempotente, sin re-descarga",
              r3["status"] == "instalado" and calls == [])

        # g-12 · Parakeet presente + VAD ausente → solo baja el detector de voz
        (dest / "silero_vad.onnx").unlink()

        def _vad_only(url, path, on_progress):
            calls.append(url)
            path.write_bytes(fake_vad)

        si._download = _vad_only
        r12 = si.start_install()
        _join()
        check("g-12 · falta solo el detector de voz → se baja solo eso (parcial)",
              len(calls) == 1 and "silero" in calls[0]
              and (dest / "silero_vad.onnx").is_file()
              and si.get_status()["estado"] == "instalado")
        check("g-12b · si solo falta el detector, el mensaje NO anuncia 700 MB",
              "700" not in (r12.get("message") or ""))

        # g-13 · archivos truncados (0 bytes) NO cuentan como instalado
        # (hallazgo capa 2 #1: un corte a mitad de la instalación no puede
        # dejar a get_status mintiendo "listo").
        for n in ["encoder.int8.onnx", "decoder.int8.onnx"]:
            (dest / se._PARAKEET_DIR / n).write_bytes(b"")
        st13 = si.get_status()
        check("g-13 · archivos de 0 bytes → el estado NO dice instalado",
              st13["estado"] != "instalado" and st13["listo"] is False)

        # g-08b · el validador manual del tar también rechaza symlinks/hardlinks
        # (hallazgo capa 2 #3 — la rama sin filter= debe dar las mismas garantías).
        import tarfile as _tf
        link = _tf.TarInfo("sub")
        link.type = _tf.SYMTYPE
        link.linkname = "../../fuera"
        ok_reg = _tf.TarInfo("normal.txt")
        ok_reg.type = _tf.REGTYPE
        rejected = False
        try:
            si._validate_member(link)
        except RuntimeError:
            rejected = True
        accepted = True
        try:
            si._validate_member(ok_reg)
        except RuntimeError:
            accepted = False
        check("g-08b · symlink dentro del tar → rechazado; archivo normal → pasa",
              rejected and accepted)

        # g-07 · fallo de red → error en llano, parciales fuera, retry limpio
        import shutil as _sh
        _sh.rmtree(dest / se._PARAKEET_DIR)
        (dest / "silero_vad.onnx").unlink()
        _reset()

        def _fail(url, path, on_progress):
            path.write_bytes(b"a medias")
            raise urllib.error.URLError("sin red")

        si._download = _fail
        si.start_install()
        _join()
        st = si.get_status()
        check("g-07a · sin red → estado error con mensaje en llano y sin parciales",
              st["estado"] == "error" and "internet" in st["mensaje"]
              and not any(j in st["mensaje"].lower() for j in jerga)
              and not list(dest.glob("*.part")) and not list(dest.glob("*.tar.bz2")))

        def _good(url, path, on_progress):
            path.write_bytes(fake_vad if "silero" in url else good_tar)

        si._download = _good
        si.start_install()
        _join()
        check("g-07b · reintento tras el fallo → instala limpio",
              si.get_status()["estado"] == "instalado")

        # g-08 · tar malicioso (../evil.txt) → rechazado fail-closed
        _sh.rmtree(dest / se._PARAKEET_DIR)
        _reset()
        evil_tar = _fake_tar({"../evil.txt": b"pwned"})

        def _evil(url, path, on_progress):
            if "silero" in url:
                path.write_bytes(fake_vad)
                return
            path.write_bytes(evil_tar)

        si._download = _evil
        si.start_install()
        _join()
        check("g-08 · entrada con '..' en el archivo → extracción rechazada, "
              "nada escrito fuera de la carpeta",
              si.get_status()["estado"] == "error"
              and not (dest.parent / "evil.txt").is_file()
              and not (dest / "evil.txt").is_file())

        # g-11 · el 503 del motor ya manda a Configuración, no a un script
        eng = se.SpeechEngine()
        ok, reason = eng.available()
        check("g-11 · sin pesos, available() apunta a Configuración (sin 'ps1')",
              ok is False and "Configuración" in reason
              and "ps1" not in reason and "script" not in reason.lower())
    finally:
        # ORDEN (hallazgo capa 2 #8): primero esperar cualquier worker vivo y
        # SOLO después restaurar _download — si se restaurara antes, un worker
        # rezagado haría la descarga REAL.
        gate.set()
        _join()
        si._download = real_download
        _reset()
        if old_env is None:
            os.environ.pop("MIA_SPEECH_MODELS_DIR", None)
        else:
            os.environ["MIA_SPEECH_MODELS_DIR"] = old_env
        import shutil as _sh
        _sh.rmtree(tmp, ignore_errors=True)


async def install_route_checks() -> None:
    from fastapi import HTTPException
    from mia.api.middleware import OPEN_PATHS
    from mia.api.routes import speech as route
    from mia.speech import install as si

    check("g-10 · status e install exigen autenticación (no son OPEN_PATH)",
          "/api/speech/status" not in OPEN_PATHS
          and "/api/speech/install" not in OPEN_PATHS)

    try:
        await route.speech_install_models(
            request=_req(), body=route.SpeechInstallBody())
        check("g-02 · instalar SIN confirmación → 400 consent-first", False)
    except HTTPException as e:
        check("g-02 · instalar SIN confirmación → 400 consent-first",
              e.status_code == 400 and "confirmación" in e.detail
              and si._thread is None)

    real_start = si.start_install
    try:
        si.start_install = lambda: {"status": "descargando", "message": "ok"}
        r = await route.speech_install_models(
            request=_req(), body=route.SpeechInstallBody(confirmar=True))
        check("g-02b · con confirmación → la instalación arranca",
              r.get("status") == "descargando")
    finally:
        si.start_install = real_start

    st = await route.speech_status(request=_req())
    check("g-02c · la ruta de estado responde con estado/listo/mensaje",
          isinstance(st, dict) and {"estado", "listo", "mensaje"} <= set(st))


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
    install_checks()
    asyncio.run(install_route_checks())
    integration_checks()

    passed = sum(1 for _, ok in _results if ok)
    total = len(_results)
    print(f"\nRESULT: {passed}/{total} checks PASS")
    return 0 if passed == total else 1


if __name__ == "__main__":
    raise SystemExit(main())
