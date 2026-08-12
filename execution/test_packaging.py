"""
Mia · test_packaging.py — gate EN FRÍO del empaquetado PyInstaller (Fase 4 · frente A).

Verifica por string-literal (sin correr el build, sin PyInstaller, sin red) que
packaging/entry_backend.py, packaging/mia-backend.spec y packaging/build_backend.ps1
conservan el contrato probado en el spike (spike-fase4/): los imports/collects
obligatorios sin los cuales el bundle arranca roto o degrada el OCR en silencio, y
que los pesos de voz (sherpa-onnx) NUNCA quedan incluidos en el bundle (decisión de
Pipe 2026-07-10: voz se instala aparte con scripts/download_speech_models.ps1).

Salida: exit 0 = PASS · exit 1 = FAIL.
    .venv\\Scripts\\python.exe execution\\test_packaging.py
"""
from __future__ import annotations

import sys
from pathlib import Path

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

ROOT = Path(__file__).resolve().parents[1]
PACKAGING = ROOT / "packaging"

_results: list[tuple[str, bool]] = []


def check(name: str, ok: bool) -> None:
    _results.append((name, bool(ok)))
    print(("  [OK]   " if ok else "  [FAIL] ") + name)


def main() -> int:
    print("== Empaquetado PyInstaller: gate en frío (Fase 4 · frente A) ==")

    entry_path = PACKAGING / "entry_backend.py"
    spec_path = PACKAGING / "mia-backend.spec"
    build_path = PACKAGING / "build_backend.ps1"

    check("packaging/entry_backend.py existe", entry_path.is_file())
    check("packaging/mia-backend.spec existe", spec_path.is_file())
    check("packaging/build_backend.ps1 existe", build_path.is_file())

    entry = entry_path.read_text(encoding="utf-8")
    spec = spec_path.read_text(encoding="utf-8")
    build = build_path.read_text(encoding="utf-8")

    # 1 · entry_backend.py DEBE importar mia.api.main textualmente (uvicorn arranca
    #     la app como string; sin este import PyInstaller no bundlea la app real).
    check(
        "entry_backend.py importa 'mia.api.main' textualmente",
        "import mia.api.main" in entry,
    )
    check(
        "entry_backend.py también importa litellm y rapidocr_onnxruntime en frío",
        "import litellm" in entry and "import rapidocr_onnxruntime" in entry,
    )
    check(
        "entry_backend.py delega a mia.api.run.main()",
        "from mia.api.run import main" in entry and "main()" in entry,
    )

    # 1b · fix M1 (revisor adversarial): sin LITELLM_LOCAL_MODEL_COST_MAP,
    #      litellm hace un httpx.get() a raw.githubusercontent.com EN CADA
    #      ARRANQUE del exe (viola local-first; con firewall se cuelga). El
    #      setdefault debe estar en el código (textual) y ANTES del
    #      `import litellm`, porque el efecto ocurre en el momento del import.
    _setdefault_idx = entry.find('os.environ.setdefault("LITELLM_LOCAL_MODEL_COST_MAP", "True")')
    if _setdefault_idx == -1:
        _setdefault_idx = entry.find("os.environ.setdefault('LITELLM_LOCAL_MODEL_COST_MAP', 'True')")
    # Busca el import REAL (statement al inicio de línea), no menciones dentro
    # de comentarios/docstrings que citan "import litellm" entre backticks
    # como referencia explicativa (p. ej. el propio comentario del fix M1).
    _import_litellm_idx = entry.find("\nimport litellm")
    check(
        "entry_backend.py fija LITELLM_LOCAL_MODEL_COST_MAP=True vía os.environ.setdefault()",
        _setdefault_idx != -1,
    )
    check(
        "entry_backend.py fija LITELLM_LOCAL_MODEL_COST_MAP ANTES (en orden textual) del import de litellm",
        _setdefault_idx != -1 and _import_litellm_idx != -1 and _setdefault_idx < _import_litellm_idx,
    )

    # 2 · el .spec debe traer los tres hallazgos obligatorios del spike.
    check(
        "mia-backend.spec trae collect_all('rapidocr_onnxruntime')",
        "collect_all(\"rapidocr_onnxruntime\")" in spec
        or "collect_all('rapidocr_onnxruntime')" in spec,
    )
    check(
        "mia-backend.spec trae collect_data_files('litellm')",
        "collect_data_files(\"litellm\")" in spec or "collect_data_files('litellm')" in spec,
    )
    check(
        "mia-backend.spec trae los hiddenimports de tiktoken_ext",
        "tiktoken_ext" in spec and "tiktoken_ext.openai_public" in spec,
    )
    check(
        "mia-backend.spec apunta el Analysis a backend/ (pathex) y usa el entry correcto",
        "BACKEND_DIR" in spec and "pathex=[BACKEND_DIR]" in spec and "entry_backend.py" in spec,
    )
    check(
        "mia-backend.spec es un onedir (COLLECT presente, no --onefile)",
        "COLLECT(" in spec,
    )

    # 2b · fix M2 (revisor adversarial): upx=True (con upx_exclude=[] vacío)
    #      puede corromper en silencio las DLL nativas de onnxruntime en
    #      cualquier máquina de build que tenga upx.exe en el PATH (OCR muerto
    #      sin error visible). El spec debe usar upx=False tanto en EXE como
    #      en COLLECT, y no debe quedar ningún "upx=True" activo.
    check(
        "mia-backend.spec usa upx=False (no upx=True) — evita corrupción silenciosa de DLL nativas",
        "upx=False" in spec and "upx=True" not in spec,
    )
    check(
        "mia-backend.spec tiene upx=False tanto en EXE como en COLLECT (2 ocurrencias)",
        spec.count("upx=False") >= 2,
    )

    # 3 · el .spec NO debe arrastrar pesos de voz (sherpa-onnx / parakeet / piper /
    #     silero): esos SIEMPRE viven fuera del bundle, en mia-data/models/speech/.
    #     El check busca una llamada REAL a un colector de PyInstaller con uno de
    #     esos nombres como argumento (regex sobre "collect_x('nombre'...)"), no
    #     una simple mención de la palabra — el docstring del .spec SÍ nombra estos
    #     paquetes a propósito, como documentación viva de la exclusión.
    import re

    # Descarta el docstring del módulo (primer bloque \"\"\"...\"\"\") y las líneas de
    # comentario (#...): ahí el texto SÍ nombra a propósito collect_all('sherpa_onnx')
    # como ejemplo de lo que NO hay que hacer — sin descartarlas, un grep ingenuo se
    # dispara con la propia documentación de la exclusión.
    spec_no_docstring = re.sub(r'""".*?"""', "", spec, count=1, flags=re.DOTALL)
    spec_code_only = "\n".join(
        line for line in spec_no_docstring.splitlines() if not line.strip().startswith("#")
    )

    collector_call = re.compile(
        r"collect_(?:all|data_files|submodules|dynamic_libs)\s*\(\s*[\"']([^\"']+)[\"']",
        re.IGNORECASE,
    )
    collected_packages = [m.group(1).lower() for m in collector_call.finditer(spec_code_only)]
    voice_needles = ["sherpa_onnx", "sherpa-onnx", "parakeet", "piper", "silero"]
    check(
        "mia-backend.spec no tiene NINGUNA llamada collect_*() sobre sherpa-onnx/parakeet/piper/silero",
        not any(
            needle.lower() in pkg
            for pkg in collected_packages
            for needle in voice_needles
        ),
    )
    check(
        "mia-backend.spec sigue teniendo exactamente 2 llamadas collect_*() reales (litellm + rapidocr)",
        len(collected_packages) == 2
        and "litellm" in collected_packages
        and "rapidocr_onnxruntime" in collected_packages,
    )

    # 4 · engine.py de voz sigue resolviendo sus modelos fuera del árbol empaquetable
    #     (config.PROJECT_ROOT/mia-data/models/speech), nunca vía collect_* de PyInstaller.
    speech_engine = (ROOT / "backend" / "mia" / "speech" / "engine.py").read_text(encoding="utf-8")
    check(
        "speech/engine.py resuelve los pesos en mia-data/models/speech (fuera del bundle)",
        '"mia-data" / "models" / "speech"' in speech_engine,
    )

    # 5 · build_backend.ps1 debe usar el pyinstaller del venv de la app (nunca uno
    #     global) y apuntar dist/build a packaging/ (no ensuciar el repo raíz).
    check(
        "build_backend.ps1 usa el pyinstaller del venv de la app (.venv\\Scripts\\pyinstaller.exe)",
        ".venv\\Scripts\\pyinstaller.exe" in build,
    )
    check(
        "build_backend.ps1 referencia mia-backend.spec",
        "mia-backend.spec" in build,
    )
    check(
        "build_backend.ps1 limpia solo sus subárboles dist/build antes de compilar",
        "Remove-TreeRobusto (Join-Path $DistPath 'mia-backend')" in build
        and "Remove-TreeRobusto (Join-Path $WorkPath 'mia-backend')" in build,
    )
    check(
        "build_backend.ps1 valida $LASTEXITCODE de PyInstaller (no asume éxito ciego)",
        "$LASTEXITCODE" in build and "$exitCode" in build,
    )

    # 6 · .gitignore debe ignorar SOLO packaging/dist y packaging/build (los fuentes
    #     .py/.spec/.ps1 de packaging/ deben quedar versionados).
    gitignore = (ROOT / ".gitignore").read_text(encoding="utf-8")
    check(
        ".gitignore ignora packaging/dist/ y packaging/build/ (no los fuentes)",
        "packaging/dist/" in gitignore and "packaging/build/" in gitignore,
    )

    passed = sum(1 for _, ok in _results if ok)
    total = len(_results)
    print(f"\nRESULT: {passed}/{total} checks PASS")
    return 0 if passed == total else 1


if __name__ == "__main__":
    sys.exit(main())
