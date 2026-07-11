"""Mia · packaging/entry_backend.py — entrypoint del bundle PyInstaller del backend.

Equivalente a `python -m mia.api.run`, pero pensado como script PRINCIPAL de un
bundle onedir (mia-backend.spec): no requiere -m ni PYTHONPATH externo, porque
`pathex=[backend/]` en el .spec hace que el paquete `mia` se recolecte dentro
del bundle igual que en desarrollo.

Este entry es prácticamente idéntico al usado en el spike de Fase 4
(spike-fase4/entry.py, probado y viable: onedir de 459 MB, /health responde sin
Python instalado). Los tres imports "innecesarios" de abajo NO son adorno:
son la única razón por la que el bundle resultante funciona. Ver cada
comentario para el porqué exacto.
"""
from __future__ import annotations

import os

# CRÍTICO (fix Fase 1 · capa 2 · M1): litellm, al importarse, si NO encuentra
# LITELLM_LOCAL_MODEL_COST_MAP en el entorno, dispara un httpx.get() a
# raw.githubusercontent.com para descargar el mapa de precios/costos de
# modelos — EN CADA ARRANQUE del exe, sin excepción. Esto viola local-first
# (Mia no debe llamar a internet para arrancar), y en una máquina con
# firewall corporativo (el caso típico de un despacho) ese GET se cuelga
# hasta el timeout de httpx, demorando o colgando el arranque del backend.
# El guard de data-files (collect_data_files('litellm') en el .spec, que sí
# empaqueta el JSON local model_prices_and_context_window_backup.json) NO
# evita esta llamada de red: litellm decide hacer el GET ANTES de mirar si
# tiene el archivo local, a menos que esta env var le diga explícitamente
# "usa el mapa local, no llames a la red". setdefault() para no pisar un
# valor que el usuario ya haya fijado, pero SIEMPRE con esta guarda activa
# por defecto. Debe ir ANTES del `import litellm` de más abajo — el efecto
# es en el momento de importar el módulo, no después.
os.environ.setdefault("LITELLM_LOCAL_MODEL_COST_MAP", "True")

# IMPORTANTE (hallazgo del spike): mia.api.run arranca uvicorn con la app
# referenciada como STRING ("mia.api.main:app"), no como objeto importado
# directamente (uvicorn.run("mia.api.main:app", ...) / uvicorn.Config("mia.api.main:app", ...)).
# PyInstaller solo bundlea lo que su análisis estático detecta por imports
# REALES; una referencia string dentro de uvicorn.Config()/uvicorn.run() es
# invisible para ese análisis. Sin esta línea, PyInstaller arma un bundle que
# ni siquiera contiene mia.api.main (ni sus ~20 routers, langgraph, psycopg,
# etc.) y el .exe falla en runtime con "Could not import module mia.api.main".
# Forzamos el import aquí para que el analizador de PyInstaller SÍ recorra el
# árbol completo de la app real.
import mia.api.main  # noqa: F401  (fuerza el bundling; el import real ocurre vía uvicorn)

# litellm se importa de forma perezosa en varios módulos (p. ej. mia/embeddings.py
# usa `import litellm` dentro de la función, no al nivel de módulo), así que un
# smoke test que solo pegue a /health puede NO ejercitarlo nunca. Lo importamos
# aquí en frío para que el arranque del exe FALLE de inmediato (en vez de fallar
# silenciosamente la primera vez que alguien ingiera un documento) si sus
# archivos de datos (model_prices_and_context_window_backup.json, tokenizers)
# no quedaron dentro del bundle. Requiere collect_data_files('litellm') en el
# .spec — ver mia-backend.spec.
import litellm  # noqa: F401

# Ídem para el OCR local: rapidocr_onnxruntime degrada a None EN SILENCIO si
# faltan sus modelos .onnx empaquetados (no lanza excepción, solo deshabilita
# el OCR sin avisar). Los modelos se recolectan con collect_all('rapidocr_onnxruntime')
# en el .spec.
# LÍMITE HONESTO de este import (fix Fase 1 · capa 2 · m4): este import SOLO
# verifica que el paquete Python y sus binarios onnxruntime están presentes en
# el bundle. NO instancia el motor de OCR, así que NO valida que los archivos
# .onnx concretos (los modelos de detección/reconocimiento) se hayan copiado
# bien, estén completos, o carguen sin error — eso solo se sabe al INSTANCIAR
# el motor (primer uso real). Ese smoke real de instanciación vive, cuando es
# viable, en build_backend.ps1 (paso opcional post-build); si no es viable
# ahí, queda como TODO explícito para el E2E de Fase 4 — no lo prometemos
# cubierto aquí.
import rapidocr_onnxruntime  # noqa: F401

from mia.api.run import main


def _ocr_smoke_test() -> int:
    """Modo smoke opcional post-build (fix Fase 1 · capa 2 · m4).

    Instancia el motor OCR REAL (RapidOCR()) desde el bundle — a diferencia de
    `mia.ingest.ocr.get_ocr_engine()`, que degrada a None EN SILENCIO ante
    cualquier excepción, aquí dejamos que la excepción se propague y la
    reportamos con honestidad. Esto atrapa el caso más común de corrupción
    (modelos .onnx faltantes o truncados dentro del bundle) sin necesidad de
    levantar el servidor completo ni subir un documento real.

    Invocado por build_backend.ps1 como `mia-backend.exe --ocr-smoke-test`,
    NUNCA en producción. NO reemplaza el E2E real de Fase 4 (subir un PDF
    escaneado de verdad y validar el texto extraído) — ese sigue siendo un
    TODO explícito documentado en build_backend.ps1.
    """
    try:
        from rapidocr_onnxruntime import RapidOCR

        RapidOCR()
    except Exception as exc:  # noqa: BLE001 - queremos capturar y reportar cualquier falla de carga
        print(f"OCR_SMOKE_TEST: FAIL ({exc!r})")
        return 1
    print("OCR_SMOKE_TEST: OK")
    return 0


if __name__ == "__main__":
    import sys

    # --first-run (bootstrap de primer arranque, F2 · sesión 43): la cáscara lo
    # invoca ANTES de arrancar uvicorn normalmente, en una máquina limpia, para
    # dejar Postgres/.env/migraciones/checkpointer listos. Los imports pesados de
    # arriba (mia.api.main, litellm, rapidocr) ya ocurrieron para cuando llegamos
    # aquí — no dependen de que la base de datos exista, así que no hay que
    # reordenarlos ni duplicar el entry point. Sin esta bandera, el arranque es
    # IDÉNTICO al de siempre.
    if "--first-run" in sys.argv:
        from mia.setup.first_run import main as first_run_main

        rest = [a for a in sys.argv[1:] if a != "--first-run"]
        sys.exit(first_run_main(rest))

    if "--ocr-smoke-test" in sys.argv:
        sys.exit(_ocr_smoke_test())
    main()
