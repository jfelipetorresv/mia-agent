"""
Mia · test_installer_bundle.py — gate EN FRÍO del ensamblaje del instalador
(bloque instalador · Fase 4).

Verifica por string-literal / parseo de JSON (SIN correr cargo/tauri, SIN
compilar, SIN red) que la configuración con la que se produce el instalador de
doble clic es internamente COHERENTE: que todo payload que la cáscara Tauri va a
buscar junto a su ejecutable (rutas literales `${exe_dir}\\X\\...` en
packaging/orchestration.installer.json) esté efectivamente declarado para
copiarse ahí por el bundler (mapa `bundle.resources` de tauri.conf.json), y que
los dos exes de Python arranquen SIN ventana de consola negra (§G).

Qué se valida:

  1. console=True en AMBOS specs de PyInstaller (mia-backend.spec y
     mia-litellm.spec). La cáscara ya lanza cada exe con CREATE_NO_WINDOW
     (desktop/src-tauri/src/lib.rs), que oculta la ventana de consola al abogado
     (§G, Riesgo #59 pt 3/7) SIN volver el exe windowed. Un exe windowed
     (console=False) haría que PyInstaller descarte sys.stdout aunque la cáscara
     lo redirija a archivo: el paso run_setup del primer arranque le muestra al
     abogado la última línea de setup.out.log como progreso/motivo de error, y
     con windowed ese log queda vacío. El gate exige console=True y prohíbe
     console=False.

  2. tauri.conf.json declara el bundler NSIS y el mapa de payloads:
     - bundle.targets incluye "nsis" (y NO deja "all", que intentaría MSI/WiX
       sin la toolchain instalada y rompería el build).
     - bundle.resources es un MAPA (destinos explícitos) que copia los 4
       payloads pesados + el yaml de config + el orchestration RENOMBRADO.
     - bundle.windows.nsis existe (installMode + compression).

  3. EL INVARIANTE CENTRAL (evita el bug que el recon marcó como crítico): la
     cáscara (lib.rs) lee literalmente "orchestration.json" junto al exe, pero
     el repo solo tiene la plantilla "orchestration.installer.json". El único
     puente es el mapa de resources con destino EXACTO "orchestration.json". El
     gate exige que exista ese renombrado en el mapa.

  4. COHERENCIA cruzada: cada primer-segmento `${exe_dir}\\<seg>\\...`
     referenciado en orchestration.installer.json (cmd[0], cwd, db.pg_bin de
     setup/litellm/backend/frontend/db) tiene un destino `<seg>` en el mapa de
     resources. Si alguien renombra un payload en un lado y no en el otro, el
     instalador armaría pero la cáscara no encontraría el motor en frío — esto
     lo caza aquí, sin esperar al E2E.

  5. build_installer.ps1 (contrato de ensamblaje) existe y: autodetecta el
     Postgres portable, EXIGE pgvector (lib\\vector.dll) e initdb.exe, verifica
     los payloads antes del bundler, y corre el bundler de Tauri.

NOTA DE ALCANCE: este gate valida la COHERENCIA de la configuración, no la
ubicación física real tras instalar (si Tauri anida los resources bajo
`resources\\` en vez de junto al exe). Esa verificación es EMPÍRICA (instalar el
setup.exe y mirar el árbol) y es un paso obligatorio del E2E de Fase 4 —
Riesgo #59. Aquí solo se ancla que la config no tenga derivas internas.

Salida: exit 0 = PASS · exit 1 = FAIL.
    .venv\\Scripts\\python.exe execution\\test_installer_bundle.py
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

ROOT = Path(__file__).resolve().parents[1]
PACKAGING = ROOT / "packaging"
BACKEND_SPEC = PACKAGING / "mia-backend.spec"
LITELLM_SPEC = PACKAGING / "mia-litellm.spec"
BUILD_INSTALLER = PACKAGING / "build_installer.ps1"
ORCH_INSTALLER = PACKAGING / "orchestration.installer.json"
TAURI_CONF = ROOT / "desktop" / "src-tauri" / "tauri.conf.json"

_results: list[tuple[str, bool]] = []


def check(name: str, ok: bool) -> None:
    _results.append((name, bool(ok)))
    print(("  [OK]   " if ok else "  [FAIL] ") + name)


def _norm_dest(dest: str) -> str:
    """Normaliza un destino del mapa de resources: sin backslash/slash final."""
    return dest.replace("\\", "/").strip("/")


def main() -> int:
    print("== test_installer_bundle: gate en frío del ensamblaje del instalador ==\n")

    # --- 1 · console=True en ambos specs (la ventana la oculta la cáscara) ---
    print("1 · console=True (la cáscara oculta la ventana con CREATE_NO_WINDOW;")
    print("    un exe windowed vaciaría el stdout del primer arranque)")
    for label, spec in (("mia-backend.spec", BACKEND_SPEC), ("mia-litellm.spec", LITELLM_SPEC)):
        raw = spec.read_text(encoding="utf-8") if spec.is_file() else ""
        check(f"{label} existe", spec.is_file())
        # Se ancla a la ASIGNACIÓN de argumento del EXE() (inicio de línea): los
        # comentarios explican la decisión y mencionan ambos valores en prosa, así
        # que buscar el literal en cualquier lugar daría falsos positivos.
        check(
            f"{label} declara console=True (ventana oculta por la cáscara, stdout vivo)",
            bool(re.search(r"^\s*console\s*=\s*True", raw, re.MULTILINE)),
        )
        check(
            f"{label} NO deja console=False (vaciaría el stdout del setup)",
            not bool(re.search(r"^\s*console\s*=\s*False", raw, re.MULTILINE)),
        )

    # --- 2 · tauri.conf.json: bundler NSIS + mapa de resources --------------
    print("\n2 · tauri.conf.json declara el bundler NSIS y el mapa de payloads")
    check("tauri.conf.json existe", TAURI_CONF.is_file())
    conf = {}
    if TAURI_CONF.is_file():
        try:
            conf = json.loads(TAURI_CONF.read_text(encoding="utf-8"))
        except Exception as exc:
            check(f"tauri.conf.json es JSON válido ({exc})", False)
    bundle = conf.get("bundle", {}) if isinstance(conf, dict) else {}

    targets = bundle.get("targets")
    targets_ok = (
        (isinstance(targets, list) and "nsis" in targets)
        or targets == "nsis"
    )
    check("bundle.targets incluye 'nsis'", targets_ok)
    check(
        "bundle.targets NO es 'all' (evita MSI/WiX sin toolchain)",
        targets != "all",
    )

    resources = bundle.get("resources")
    check("bundle.resources es un mapa (destinos explícitos)", isinstance(resources, dict))
    dests = set()
    src_by_dest = {}
    if isinstance(resources, dict):
        for src, dest in resources.items():
            d = _norm_dest(str(dest))
            dests.add(d)
            src_by_dest[d] = str(src).replace("\\", "/")

    windows = bundle.get("windows", {}) if isinstance(bundle, dict) else {}
    nsis = windows.get("nsis", {}) if isinstance(windows, dict) else {}
    check("bundle.windows.nsis existe (installMode/compression)", isinstance(nsis, dict) and len(nsis) > 0)

    # --- 3 · EL renombrado orchestration.installer.json -> orchestration.json
    print("\n3 · el renombrado a orchestration.json (la cáscara lee ese nombre literal)")
    rename_ok = (
        "orchestration.json" in dests
        and src_by_dest.get("orchestration.json", "").endswith("orchestration.installer.json")
    )
    check(
        "bundle.resources mapea *orchestration.installer.json -> 'orchestration.json'",
        rename_ok,
    )

    # --- 4 · coherencia cruzada con orchestration.installer.json ------------
    print("\n4 · cada payload que la cáscara busca en ${exe_dir}\\X tiene destino X en el mapa")
    check("packaging/orchestration.installer.json existe", ORCH_INSTALLER.is_file())
    orch = {}
    if ORCH_INSTALLER.is_file():
        try:
            orch = json.loads(ORCH_INSTALLER.read_text(encoding="utf-8"))
        except Exception as exc:
            check(f"orchestration.installer.json es JSON válido ({exc})", False)

    # Recolecta TODOS los strings que usan ${exe_dir}/<seg>/... del JSON.
    exe_dir_refs: set[str] = set()
    token = "${exe_dir}/"

    def _scan(value) -> None:
        if isinstance(value, str):
            # Normaliza backslashes: si un futuro editor escribe ${exe_dir}\mia-backend
            # el segmento igual se detecta (M2 · capa 2 sesión 45).
            norm = value.replace("\\", "/")
            if token in norm:
                tail = norm.split(token, 1)[1]
                seg = tail.split("/", 1)[0]
                if seg:
                    exe_dir_refs.add(seg)
        elif isinstance(value, list):
            for v in value:
                _scan(v)
        elif isinstance(value, dict):
            for v in value.values():
                _scan(v)

    _scan(orch)
    # Debe haber referencias reales (si no, el JSON cambió de forma y el gate
    # estaría dando un PASS vacío).
    check("orchestration.installer.json referencia payloads via ${exe_dir}", len(exe_dir_refs) > 0)

    for seg in sorted(exe_dir_refs):
        check(
            f"el payload '{seg}' (referenciado por la cáscara) tiene destino en bundle.resources",
            seg in dests,
        )

    # Sanidad explícita de los payloads esperados (por si el JSON se recorta).
    for expected in ("mia-backend", "mia-litellm", "mia-frontend", "pgsql"):
        check(f"bundle.resources copia el payload '{expected}'", expected in dests)

    # --- 5 · build_installer.ps1 (contrato de ensamblaje) -------------------
    print("\n5 · build_installer.ps1 (contrato de ensamblaje reproducible)")
    check("packaging/build_installer.ps1 existe", BUILD_INSTALLER.is_file())
    bi = BUILD_INSTALLER.read_text(encoding="utf-8") if BUILD_INSTALLER.is_file() else ""
    check("build_installer.ps1 EXIGE pgvector (lib\\vector.dll)", "vector.dll" in bi)
    check("build_installer.ps1 verifica initdb.exe del Postgres portable", "initdb.exe" in bi)
    check(
        "build_installer.ps1 copia el Postgres portable a dist/pgsql",
        "dist" in bi and "pgsql" in bi and "robocopy" in bi.lower(),
    )
    check(
        "build_installer.ps1 EXCLUYE pgAdmin del pgsql empaquetado (~700 MB, sin uso)",
        "pgAdmin 4" in bi and "/XD" in bi,
    )
    check("build_installer.ps1 corre el bundler de Tauri", "tauri build" in bi)
    check(
        "build_installer.ps1 recompila los 3 payloads (backend/litellm/frontend)",
        all(s in bi for s in ("build_backend.ps1", "build_litellm.ps1", "build_frontend.ps1")),
    )

    passed = sum(1 for _, ok in _results if ok)
    total = len(_results)
    print(f"\nRESULT: {passed}/{total} checks PASS")
    return 0 if passed == total else 1


if __name__ == "__main__":
    sys.exit(main())
