"""Mia · speech — dictado local (CP-Z1, Ola 3).

Voz-a-texto 100% LOCAL: el audio del abogado JAMÁS sale de la infraestructura
del despacho. Motor: Silero VAD + Parakeet TDT 0.6B v3 (ONNX int8) vía
sherpa-onnx — los MISMOS modelos y parámetros que Lexter (el dictado de
escritorio de Pipe, fork de Handy, MIT) ya validó en español jurídico real.
Diseño completo en docs/analisis-lexter.md.

Módulos:
  - audio.py   → decodifica el WAV del navegador a PCM float32 16 kHz mono
  - engine.py  → SpeechEngine (VAD + STT, carga perezosa, opcional)
  - policy.py  → candado de privacidad allow_cloud_audio (default False, fail-closed)
  - cleanup.py → pulido opcional del dictado con el modelo LOCAL (nunca nube)

Los pesos de los modelos NO se versionan (licencias propias + tamaño): se
descargan en instalación con scripts/download_speech_models.ps1 a
mia-data/models/speech/. Sin modelos o sin sherpa-onnx, el endpoint degrada
con un 503 en lenguaje llano — el resto de Mia no se entera.
"""
