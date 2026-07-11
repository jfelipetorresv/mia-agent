# -*- mode: python ; coding: utf-8 -*-
"""Mia · packaging/mia-backend.spec — bundle onedir reproducible del backend.

Empaqueta el backend FastAPI/uvicorn de Mia con PyInstaller para que corra sin
Python instalado en la máquina del abogado. Adaptado 1:1 del spike validado en
spike-fase4/mia-backend.spec (build de 459 MB, /health responde en frío) —
lecciones OBLIGATORIAS que este spec preserva:

  1. entry_backend.py importa mia.api.main EXPLÍCITAMENTE porque
     mia/api/run.py arranca uvicorn con la app referenciada como STRING
     ("mia.api.main:app"); el análisis estático de PyInstaller no ve esa
     referencia, así que sin el import explícito el bundle queda sin los
     routers/langgraph/psycopg reales.
  2. collect_data_files('litellm') — litellm se usa también IN-PROCESS (no
     solo como cliente del proxy externo: mia/embeddings.py llama
     litellm.embedding() directo para voyage-law-2) y necesita sus JSON de
     precios y tokenizers en tiempo de ejecución.
  3. collect_all('rapidocr_onnxruntime') — sin esto el motor de OCR degrada
     a None EN SILENCIO (no hay excepción visible, solo un feature apagado).
  4. hiddenimports de tiktoken_ext — tiktoken usa un registro de plugins
     (entry points) que el análisis estático de PyInstaller no detecta.
  5. pathex apunta a backend/ (no al repo completo) para que 'mia' se
     resuelva como paquete de primer nivel, igual que en desarrollo.
  6. upx=False en EXE y COLLECT (fix Fase 1 · capa 2 · M2) — UPX puede
     corromper en silencio las DLL nativas de onnxruntime (OCR muerto sin
     error visible). La compresión final la hace el instalador NSIS.

FUERA del bundle (decisión de Pipe 2026-07-10): los pesos de voz
(sherpa-onnx / Parakeet TDT / Silero VAD / Piper TTS) NO se incluyen. Viven en
mia-data/models/speech/ (carpeta de datos de INSTANCIA, gitignored) y se
instalan aparte con scripts/download_speech_models.ps1 o el Panel de control
(backend/mia/speech/install.py). backend/mia/speech/engine.py los busca en
config.PROJECT_ROOT/mia-data/models/speech — nunca en una ruta empaquetable
por PyInstaller. Por eso este .spec NO tiene collect_all('sherpa_onnx') ni
collect_data_files('sherpa_onnx'): solo se empaqueta el módulo Python de
sherpa-onnx (código, pequeño) porque PyInstaller lo detecta como dependencia
de backend/mia/speech/engine.py; los .onnx (cientos de MB) jamás entran aquí.
execution/test_packaging.py (gate en frío) verifica que este contrato no se
rompa por accidente.
"""
import os

from PyInstaller.utils.hooks import collect_all, collect_data_files

# SPECPATH: variable que PyInstaller inyecta en el namespace de ejecución del
# .spec = carpeta que contiene este archivo (packaging/). Construimos todo en
# absoluto para que el build sea reproducible sin importar desde dónde se
# invoque pyinstaller (build_backend.ps1 siempre pasa la ruta absoluta al
# .spec, pero esto lo blinda incluso si alguien lo corre manual).
PACKAGING_DIR = SPECPATH
REPO_ROOT = os.path.dirname(PACKAGING_DIR)
BACKEND_DIR = os.path.join(REPO_ROOT, "backend")
ENTRY_SCRIPT = os.path.join(PACKAGING_DIR, "entry_backend.py")

datas = []
binaries = []
hiddenimports = ["tiktoken_ext", "tiktoken_ext.openai_public"]

datas += collect_data_files("litellm")

tmp_ret = collect_all("rapidocr_onnxruntime")
datas += tmp_ret[0]
binaries += tmp_ret[1]
hiddenimports += tmp_ret[2]

# NO agregar aquí collect_all('sherpa_onnx') / collect_data_files('sherpa_onnx')
# ni nada de 'parakeet' / 'piper' / 'silero' — ver nota "FUERA del bundle" arriba.
# execution/test_packaging.py falla si alguien lo reintroduce por accidente.

a = Analysis(
    [ENTRY_SCRIPT],
    pathex=[BACKEND_DIR],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
    optimize=0,
)
pyz = PYZ(a.pure)

# upx=False (fix Fase 1 · capa 2 · M2): UPX comprime binarios re-escribiendo su
# stub de descompresión; con las DLL nativas de onnxruntime (usadas por
# rapidocr_onnxruntime para el OCR) esa re-escritura puede corromperlas EN
# SILENCIO en cualquier máquina de build que tenga upx.exe en el PATH — el
# bundle arma sin error visible, pero el OCR queda muerto (o el proceso
# revienta) en runtime. upx_exclude=[] (vacío) no protegía nada porque no
# excluía justamente esas DLL. La compresión real del tamaño del bundle ya la
# hace el instalador NSIS final (Fase 1, frente C) — determinismo y binarios
# intactos importan más que ahorrar MB aquí.
exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="mia-backend",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=True,  # console=True por ahora (decisión pendiente: modo ventana/servicio en fases futuras).
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)
coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=False,
    upx_exclude=[],
    name="mia-backend",
)
