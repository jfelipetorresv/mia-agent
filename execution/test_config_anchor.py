"""Gate · ancla de instancia de config.py (Fase 4 · R1 del spike de distribución).

Protege el contrato de resolución de PROJECT_ROOT (dónde vive el estado de
instancia: .env y mia-data):
  1. Desarrollo (default): la raíz del repo — comportamiento histórico intacto.
  2. MIA_APP_DIR (env): manda siempre; es como la cáscara de escritorio (Tauri)
     le dice al motor empaquetado dónde vive su instancia.
  3. Congelado (sys.frozen, PyInstaller): carpeta de datos de la app del usuario
     (%LOCALAPPDATA%\\Mia), nunca dentro del bundle.
Convención del repo: script standalone (NO pytest), RESULT: X/Y checks PASS.
Cada check importa config en un subproceso limpio (config resuelve en import-time).
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
BACKEND = REPO_ROOT / "backend"

SNIPPET = (
    "import json, mia.config as c;"
    "print(json.dumps({'root': str(c.PROJECT_ROOT), 'home': str(c.MIA_HOME)}))"
)

FROZEN_SNIPPET = (
    "import sys; sys.frozen = True;"
    "import json, mia.config as c;"
    "print(json.dumps({'root': str(c.PROJECT_ROOT)}))"
)


def _probe(snippet: str, extra_env: dict[str, str], want_stderr: bool = False):
    env = os.environ.copy()
    env.pop("MIA_APP_DIR", None)
    env["PYTHONPATH"] = str(BACKEND)
    env.update(extra_env)
    out = subprocess.run(
        [sys.executable, "-c", snippet],
        capture_output=True, text=True, env=env, cwd=str(REPO_ROOT), timeout=120,
    )
    if out.returncode != 0:
        raise RuntimeError(f"subproceso falló: {out.stderr[-500:]}")
    data = json.loads(out.stdout.strip().splitlines()[-1])
    return (data, out.stderr) if want_stderr else data


def main() -> int:
    passed = 0
    total = 8

    # 1 · Desarrollo: sin MIA_APP_DIR ni frozen → raíz del repo (histórico intacto).
    r = _probe(SNIPPET, {})
    ok = Path(r["root"]) == REPO_ROOT
    passed += ok
    print(f"{'PASS' if ok else 'FAIL'} 1/6 default dev = raíz del repo ({r['root']})")

    with tempfile.TemporaryDirectory() as td:
        tdp = Path(td).resolve()

        # 2 · MIA_APP_DIR manda: PROJECT_ROOT = esa carpeta.
        r = _probe(SNIPPET, {"MIA_APP_DIR": str(tdp)})
        ok = Path(r["root"]) == tdp
        passed += ok
        print(f"{'PASS' if ok else 'FAIL'} 2/6 MIA_APP_DIR redirige PROJECT_ROOT")

        # 3 · MIA_HOME relativa se ancla al MIA_APP_DIR (no al repo).
        r = _probe(SNIPPET, {"MIA_APP_DIR": str(tdp), "MIA_HOME": "mia-data"})
        ok = Path(r["home"]) == (tdp / "mia-data").resolve()
        passed += ok
        print(f"{'PASS' if ok else 'FAIL'} 3/6 MIA_HOME relativa ancla al app dir")

        # 4 · El .env se lee desde MIA_APP_DIR (variable inventada como trazador).
        (tdp / ".env").write_text("MIA_ANCHOR_PROBE=desde_app_dir\n", encoding="utf-8")
        r = _probe(
            "import json, os, mia.config as c;"
            "print(json.dumps({'probe': os.getenv('MIA_ANCHOR_PROBE', '')}))",
            {"MIA_APP_DIR": str(tdp)},
        )
        ok = r["probe"] == "desde_app_dir"
        passed += ok
        print(f"{'PASS' if ok else 'FAIL'} 4/6 .env se carga desde MIA_APP_DIR")

        # 5 · Congelado (sys.frozen) sin MIA_APP_DIR → LOCALAPPDATA/Mia.
        r = _probe(FROZEN_SNIPPET, {"LOCALAPPDATA": str(tdp)})
        ok = Path(r["root"]) == (tdp / "Mia").resolve()
        passed += ok
        print(f"{'PASS' if ok else 'FAIL'} 5/6 frozen sin override = LOCALAPPDATA/Mia")

        # 6 · MIA_APP_DIR le gana a frozen (la cáscara siempre puede dictar la ruta).
        r = _probe(FROZEN_SNIPPET, {"MIA_APP_DIR": str(tdp), "LOCALAPPDATA": "C:\\ignorado"})
        ok = Path(r["root"]) == tdp
        passed += ok
        print(f"{'PASS' if ok else 'FAIL'} 6/8 MIA_APP_DIR precede a frozen")

        # 7 · Las TRAZAS (flywheel HITL) siguen el ancla de instancia, no __file__
        #     (hallazgo MAYOR-1 de la revisión adversarial de Fase 4 · R1).
        r = _probe(
            "import json;"
            "from mia.memory.trace_capture import _default_traces_dir;"
            "print(json.dumps({'traces': str(_default_traces_dir())}))",
            {"MIA_APP_DIR": str(tdp), "MIA_HOME": "mia-data"},
        )
        ok = Path(r["traces"]) == (tdp / "mia-data" / "traces").resolve()
        passed += ok
        print(f"{'PASS' if ok else 'FAIL'} 7/8 traces anclan a la instancia (MAYOR-1)")

    # 8 · MIA_APP_DIR sin .env → aviso RUIDOSO en stderr (no arranque mudo con defaults).
    with tempfile.TemporaryDirectory() as td2:
        _, err = _probe(SNIPPET, {"MIA_APP_DIR": str(Path(td2).resolve())}, want_stderr=True)
        ok = "no contiene un .env" in err
        passed += ok
        print(f"{'PASS' if ok else 'FAIL'} 8/8 sin .env avisa en stderr (MENOR-2)")

    print(f"RESULT: {passed}/{total} checks PASS")
    return 0 if passed == total else 1


if __name__ == "__main__":
    sys.exit(main())
