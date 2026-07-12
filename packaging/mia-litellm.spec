# -*- mode: python ; coding: utf-8 -*-
"""Mia · packaging/mia-litellm.spec — bundle onedir reproducible del proxy LiteLLM.

Segundo ejecutable del instalador (Contrato 3, plan F2): empaqueta
`litellm[proxy]` como `mia-litellm.exe` para que la cáscara lo arranque como un
servicio supervisado más, sin requerir Python en la máquina del abogado.
Comparte los mismos principios de mia-backend.spec (adaptados 1:1 donde aplica):

  1. Se compila SIEMPRE con el pyinstaller del venv DEDICADO (.venv-litellm),
     nunca con el de la app (.venv) — ver packaging/setup_venv_litellm.ps1 y
     packaging/build_litellm.ps1. Así los pins de litellm==1.74.8 usados
     IN-PROCESS por el backend (mia-backend.spec, embeddings) nunca se ven
     afectados por instalar pyinstaller + sus dependencias de build.
  2. collect_all("litellm") — el proxy trae MUCHOS más data files que el uso
     in-process (mia-backend.spec solo necesita collect_data_files, porque ahí
     litellm.embedding() no usa el servidor proxy): tokenizers
     (litellm_core_utils/tokenizers/*.json), el mapa de precios
     (model_prices_and_context_window_backup.json), plantillas de ejemplo de
     config (proxy/example_config_yaml/*.yaml), assets del admin UI
     (proxy/cached_logo.jpg, proxy/auth/public_key.pem), etc. Usar solo
     collect_data_files() aquí dejaría el proxy con features degradadas EN
     SILENCIO (mismo patrón de riesgo que rapidocr_onnxruntime en el backend).
  3. hiddenimports de tiktoken_ext — igual razón que mia-backend.spec: tiktoken
     resuelve sus encoders vía entry points (registro de plugins) que el
     análisis estático de PyInstaller no ve.
  4. upx=False en EXE y COLLECT — mismo riesgo que mia-backend.spec (UPX puede
     corromper en silencio binarios nativos; aquí litellm/enterprise traen
     dependencias con extensiones C como tokenizers/cryptography/pynacl).
  5. SIN prisma: prisma NO está instalado en .venv-litellm (litellm[proxy] no
     lo requiere para el uso de Mia — el proxy es solo gateway de modelos, sin
     BD interna propia, igual que en dev vía scripts/run_litellm_clean.ps1).
     PyInstaller puede advertir "module not found: prisma" al analizar algunos
     imports lazy/guardados de litellm/proxy — es un WARNING no fatal (el
     módulo simplemente no existe en este venv y no se bundlea).
  6. onedir (COLLECT), console=True: mismo patrón que mia-backend.spec. Salida:
     packaging/dist/mia-litellm/.
"""
import os

from PyInstaller.utils.hooks import collect_all, collect_data_files

# SPECPATH: carpeta que contiene este .spec (packaging/). Todo en absoluto para
# que el build sea reproducible sin importar desde dónde se invoque pyinstaller
# (build_litellm.ps1 siempre pasa la ruta absoluta al .spec).
PACKAGING_DIR = SPECPATH
ENTRY_SCRIPT = os.path.join(PACKAGING_DIR, "entry_litellm.py")

datas = []
binaries = []
hiddenimports = ["tiktoken_ext", "tiktoken_ext.openai_public"]

# certifi EXPLICITO (leccion del primer build real, 2026-07-10): litellm 1.74.8
# crea un AsyncHTTPHandler AL IMPORTARSE (litellm/__init__.py:339), y ese
# handler llama ssl.create_default_context(cafile=certifi.where()). Si el
# cacert.pem de certifi no esta dentro del bundle, el exe muere en el import
# con FileNotFoundError ANTES de servir nada. Normalmente lo resuelve el
# hook-certifi de pyinstaller-hooks-contrib (que build_litellm.ps1 instala
# pineado), pero se declara tambien aqui para que el bundle no dependa de que
# ese paquete este presente en el venv de build (defensa en profundidad).
datas += collect_data_files("certifi")

# collect_all (no solo collect_data_files): el proxy real necesita bastante más
# que el JSON de precios que sí basta para el uso in-process del backend — ver
# nota 2 del docstring.
tmp_ret = collect_all("litellm")
datas += tmp_ret[0]
binaries += tmp_ret[1]
hiddenimports += tmp_ret[2]

a = Analysis(
    [ENTRY_SCRIPT],
    pathex=[],
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

# upx=False (misma razón que mia-backend.spec): la compresión final la hace el
# instalador NSIS (Fase 1, frente C); UPX puede corromper binarios nativos en
# silencio en la máquina de build.
exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="mia-litellm",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    # console=True (F4 · sesión 45, cierre Riesgo #59 pt 7): igual criterio que
    # mia-backend.spec — la cáscara lo lanza con CREATE_NO_WINDOW, que oculta la
    # ventana al abogado (§G) sin volver el exe windowed. console=False descartaría
    # el stdout que la cáscara redirige a archivo para diagnóstico. Reversible.
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
    name="mia-litellm",
)
