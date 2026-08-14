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
  3. collect_all('rapidocr_onnxruntime') solo para perfiles ocr/full; el perfil
     core conserva PyMuPDF para PDF textual y declara que no lee escaneos.
  4. hiddenimports de tiktoken_ext — tiktoken usa un registro de plugins
     (entry points) que el análisis estático de PyInstaller no detecta.
  5. pathex apunta a backend/ (no al repo completo) para que 'mia' se
     resuelva como paquete de primer nivel, igual que en desarrollo.
  6. upx=False en EXE y COLLECT (fix Fase 1 · capa 2 · M2) — UPX puede
     corromper en silencio las DLL nativas de onnxruntime (OCR muerto sin
     error visible). La compresión final la hace el instalador NSIS.
  7. datas explícitas (NO collect_*) para mia/db/schema.sql y
     mia/db/migrations/*.sql (F2 · sesión 43, bootstrap de primer arranque):
     mia.setup.first_run necesita aplicarlos dentro del bundle (sys._MEIPASS),
     igual que en dev. Se usa una lista `datas=[(origen, "mia/db")]` explícita
     y NO collect_data_files/collect_all porque execution/test_packaging.py
     exige EXACTAMENTE 2 llamadas collect_*() reales (litellm + rapidocr) —
     agregar una tercera rompería ese gate.

FUERA del bundle en todos los perfiles: los pesos de voz
(Parakeet TDT / Silero VAD / Piper TTS) NO se incluyen. Viven en
mia-data/models/speech/ (carpeta de datos de INSTANCIA, gitignored) y se
instalan aparte con scripts/download_speech_models.ps1 o el Panel de control
(backend/mia/speech/install.py). backend/mia/speech/engine.py los busca en
config.PROJECT_ROOT/mia-data/models/speech — nunca en una ruta empaquetable
por PyInstaller. El perfil voice/full permite empaquetar los runtimes
sherpa-onnx y av detectados por PyInstaller; core/ocr los excluye. Los modelos
.onnx (cientos de MB) jamás entran aquí.
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

PROFILE = os.environ.get("MIA_BUNDLE_PROFILE", "core").strip().lower()
if PROFILE not in {"core", "ocr", "voice", "full"}:
    raise ValueError(f"MIA_BUNDLE_PROFILE invalido: {PROFILE}")
WITH_OCR = PROFILE in {"ocr", "full"}
WITH_VOICE = PROFILE in {"voice", "full"}

datas = []
binaries = []
hiddenimports = [
    "tiktoken_ext",
    "tiktoken_ext.openai_public",
    # Backup cifrado F1: el hook oficial de PyInstaller cubre cryptography,
    # y este hidden import deja explícito el binding nativo que debe viajar.
    "cryptography.hazmat.bindings._rust",
]

# F2 (sesión 43): schema.sql + migrations/*.sql, para que mia.setup.first_run
# los resuelva dentro del bundle (mia/db/... bajo sys._MEIPASS) igual que en
# dev (backend/mia/db/...). Datas explícitas, no collect_* — ver nota 7 arriba.
DB_DIR = os.path.join(BACKEND_DIR, "mia", "db")
datas += [(os.path.join(DB_DIR, "schema.sql"), "mia/db")]
for _mig in sorted(os.listdir(os.path.join(DB_DIR, "migrations"))):
    if _mig.endswith(".sql"):
        datas.append((os.path.join(DB_DIR, "migrations", _mig), "mia/db/migrations"))

datas += collect_data_files(
    "litellm",
    excludes=["**/tests/**", "**/test/**", "**/docs/**", "**/__pycache__/**"],
)

if WITH_OCR:
    tmp_ret = collect_all("rapidocr_onnxruntime")
    datas += tmp_ret[0]
    binaries += tmp_ret[1]
    hiddenimports += tmp_ret[2]

excludes = [
    "pytest", "_pytest", "unittest", "doctest", "pydoc", "IPython", "jupyter",
    "notebook", "sphinx", "mkdocs",
]
if not WITH_OCR:
    excludes += ["rapidocr_onnxruntime", "onnxruntime", "cv2", "PIL"]
if not WITH_VOICE:
    excludes += ["sherpa_onnx", "av"]

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
    excludes=excludes,
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
    # console=True (F4 · sesión 45, cierre Riesgo #59 pt 3): la cáscara Tauri
    # lanza este exe con CREATE_NO_WINDOW (desktop/src-tauri/src/lib.rs), que YA
    # oculta la ventana de consola negra al abogado (§G) SIN perder stdout. Un
    # exe windowed (console=False) haría que el bootloader de PyInstaller descarte
    # sys.stdout AUNQUE la cáscara redirija el handle a archivo: el paso de primer
    # arranque (run_setup) le muestra al abogado la ÚLTIMA LÍNEA de setup.out.log
    # como progreso/motivo de error — con windowed ese log queda vacío y, si el
    # bootstrap falla, el abogado no sabría por qué. Por eso console=True + la
    # ventana la esconde la cáscara, no el spec. Reversible.
    console=True,
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
