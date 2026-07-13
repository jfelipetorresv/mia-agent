"""
Mia · test_litellm_packaging.py — gate EN FRÍO del empaquetado del proxy LiteLLM
(bloque instalador · Contrato 3, plan F2, sesión 43).

Verifica por string-literal (sin correr el build, sin PyInstaller, sin red) que
packaging/entry_litellm.py, packaging/mia-litellm.spec, packaging/build_litellm.ps1,
packaging/litellm_config.installer.yaml y packaging/setup_venv_litellm.ps1
conservan el contrato acordado con el orquestador (memory/plan-f2-instalador.md):
el orden ESTRICTO de blindajes del entry (mapa de costos -> allowlist/scrub de
entorno -> neutralización de dotenv -> import/delegación de litellm), que la
allowlist NUNCA deja pasar DATABASE_URL/PG_*, que el spec es onedir con
upx=False, que el build script usa el pyinstaller de .venv-litellm (nunca el de
la app) y trae el humo real, y que el master_key SOLO vive en el yaml
instalador (el litellm_config.yaml de dev no cambia).

Salida: exit 0 = PASS · exit 1 = FAIL.
    .venv\\Scripts\\python.exe execution\\test_litellm_packaging.py
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

_results: list[tuple[str, bool]] = []


def check(name: str, ok: bool) -> None:
    _results.append((name, bool(ok)))
    print(("  [OK]   " if ok else "  [FAIL] ") + name)


def code_only(source: str) -> str:
    """Quita el docstring de módulo (primer bloque triple-comillado) y las
    líneas de comentario ('#...'), para anclar los checks de orden al CÓDIGO
    real y no a la prosa que lo documenta (mismo criterio que test_packaging.py
    y test_shell_hardening.py -- varios de estos literales también aparecen,
    a propósito, en los comentarios que explican por qué existe cada blindaje).
    """
    no_docstring = re.sub(r'^\s*""".*?"""', "", source, count=1, flags=re.DOTALL)
    lines = [
        line
        for line in no_docstring.splitlines()
        if not line.strip().startswith("#")
    ]
    return "\n".join(lines)


def main() -> int:
    print("== Empaquetado del proxy LiteLLM: gate en frío (Contrato 3 · plan F2) ==")

    entry_path = PACKAGING / "entry_litellm.py"
    spec_path = PACKAGING / "mia-litellm.spec"
    build_path = PACKAGING / "build_litellm.ps1"
    installer_cfg_path = PACKAGING / "litellm_config.installer.yaml"
    setup_venv_path = PACKAGING / "setup_venv_litellm.ps1"
    dev_cfg_path = ROOT / "litellm_config.yaml"
    orchestration_json_path = PACKAGING / "orchestration.installer.json"
    run_clean_ps1_path = ROOT / "scripts" / "run_litellm_clean.ps1"

    # 0 · existencia de los archivos nuevos de este frente.
    check("packaging/entry_litellm.py existe", entry_path.is_file())
    check("packaging/mia-litellm.spec existe", spec_path.is_file())
    check("packaging/build_litellm.ps1 existe", build_path.is_file())
    check("packaging/litellm_config.installer.yaml existe", installer_cfg_path.is_file())
    check("packaging/setup_venv_litellm.ps1 existe", setup_venv_path.is_file())

    check("packaging/orchestration.installer.json existe", orchestration_json_path.is_file())
    check("scripts/run_litellm_clean.ps1 existe", run_clean_ps1_path.is_file())

    if not (entry_path.is_file() and spec_path.is_file() and build_path.is_file()
            and installer_cfg_path.is_file() and setup_venv_path.is_file()
            and dev_cfg_path.is_file() and orchestration_json_path.is_file()
            and run_clean_ps1_path.is_file()):
        passed = sum(1 for _, ok in _results if ok)
        total = len(_results)
        print(f"\nRESULT: {passed}/{total} checks PASS (abortado: faltan archivos base)")
        return 1

    entry_raw = entry_path.read_text(encoding="utf-8")
    spec = spec_path.read_text(encoding="utf-8")
    build = build_path.read_text(encoding="utf-8")
    setup_venv = setup_venv_path.read_text(encoding="utf-8")
    installer_cfg = installer_cfg_path.read_text(encoding="utf-8")
    dev_cfg = dev_cfg_path.read_text(encoding="utf-8")
    orchestration_json = orchestration_json_path.read_text(encoding="utf-8")
    run_clean_ps1 = run_clean_ps1_path.read_text(encoding="utf-8")

    entry_code = code_only(entry_raw)

    # 1 · orden ESTRICTO del entry (Contrato 3): cost-map -> allowlist/scrub ->
    #     neutralización dotenv -> import/delegación de litellm. Se ancla a
    #     statements reales de código (no a menciones en comentarios/docstring).
    cost_map_idx = entry_code.find('os.environ.setdefault("LITELLM_LOCAL_MODEL_COST_MAP", "True")')
    if cost_map_idx == -1:
        cost_map_idx = entry_code.find("os.environ.setdefault('LITELLM_LOCAL_MODEL_COST_MAP', 'True')")
    check(
        "entry_litellm.py fija LITELLM_LOCAL_MODEL_COST_MAP=True vía os.environ.setdefault()",
        cost_map_idx != -1,
    )

    allowlist_call_idx = entry_code.find("_allowlist_load_env(")
    # La primera ocurrencia real es la DEFINICIÓN de la función; la llamada real
    # (statement de nivel de módulo) es la ocurrencia SIGUIENTE.
    if allowlist_call_idx != -1:
        allowlist_call_idx = entry_code.find("_allowlist_load_env(", allowlist_call_idx + 1)
    check(
        "entry_litellm.py invoca la carga allowlist del .env del app_dir",
        allowlist_call_idx != -1,
    )

    scrub_idx = entry_code.find("os.environ.pop(_var, None)")
    check(
        "entry_litellm.py hace scrub duro de variables de entorno (os.environ.pop)",
        scrub_idx != -1,
    )

    dotenv_patch_idx = entry_code.find("dotenv.load_dotenv = _noop_load_dotenv")
    dotenv_main_patch_idx = entry_code.find("dotenv.main.load_dotenv = _noop_load_dotenv")
    check(
        "entry_litellm.py neutraliza dotenv.load_dotenv a no-op",
        dotenv_patch_idx != -1,
    )
    check(
        "entry_litellm.py neutraliza TAMBIÉN dotenv.main.load_dotenv a no-op",
        dotenv_main_patch_idx != -1,
    )

    import_litellm_idx = -1
    for m in re.finditer(r"^import litellm\b", entry_code, re.MULTILINE):
        import_litellm_idx = m.start()
        break
    check(
        "entry_litellm.py importa litellm (statement real, no en comentario/docstring)",
        import_litellm_idx != -1,
    )
    check(
        "entry_litellm.py delega al CLI real de litellm (run_server())",
        "litellm.run_server()" in entry_code,
    )

    order_indices = [cost_map_idx, allowlist_call_idx, scrub_idx, dotenv_patch_idx, import_litellm_idx]
    order_ok = all(i != -1 for i in order_indices) and order_indices == sorted(order_indices) and len(set(order_indices)) == len(order_indices)
    check(
        "orden textual ESTRICTO: cost-map -> allowlist -> scrub -> neutralización dotenv -> import litellm",
        order_ok,
    )

    # 2 · la allowlist NUNCA debe dejar pasar DATABASE_URL ni PG_*; el scrub SÍ
    #     debe cubrir DATABASE_URL y las variables de Postgres/Prisma.
    allowlist_block_match = re.search(r"_ALLOWLIST_EXACT\s*=\s*\{(.*?)\}", entry_raw, re.DOTALL)
    allowlist_block = allowlist_block_match.group(1) if allowlist_block_match else ""
    check(
        "la allowlist del entry (_ALLOWLIST_EXACT) NO incluye DATABASE_URL",
        "DATABASE_URL" not in allowlist_block,
    )
    check(
        "la allowlist del entry (_ALLOWLIST_EXACT) NO incluye ninguna clave PG_*",
        "PG_" not in allowlist_block,
    )
    check(
        "la allowlist SÍ acepta ANTHROPIC_API_KEY, VOYAGE_API_KEY, OPENROUTER_API_KEY y LITELLM_MASTER_KEY",
        all(
            key in allowlist_block
            for key in ("ANTHROPIC_API_KEY", "VOYAGE_API_KEY", "OPENROUTER_API_KEY", "LITELLM_MASTER_KEY")
        ),
    )

    scrub_block_match = re.search(r"_SCRUB_VARS\s*=\s*\((.*?)\)", entry_raw, re.DOTALL)
    scrub_block = scrub_block_match.group(1) if scrub_block_match else ""
    check(
        "el scrub duro del entry (_SCRUB_VARS) SÍ incluye DATABASE_URL",
        "DATABASE_URL" in scrub_block,
    )
    check(
        "el scrub duro del entry (_SCRUB_VARS) SÍ incluye variables PG_*/Postgres (PG_PASSWORD, POSTGRES_HOST, etc.)",
        "PG_PASSWORD" in scrub_block and "POSTGRES_HOST" in scrub_block,
    )
    check(
        "el entry nunca sobreescribe una variable ya presente en el entorno (allowlist con guard 'if key in os.environ')",
        "if key in os.environ" in entry_raw,
    )

    # 3 · app_dir se resuelve SIN importar mia (duplicación mínima consciente,
    #     Contrato 3): MIA_APP_DIR env > frozen -> LOCALAPPDATA/Mia > dev -> repo.
    check(
        "entry_litellm.py NO importa el paquete 'mia' (resolución de app_dir duplicada a propósito)",
        not re.search(r"^\s*(import mia\b|from mia\b)", entry_raw, re.MULTILINE),
    )
    check(
        "entry_litellm.py resuelve MIA_APP_DIR desde el entorno",
        'os.environ.get("MIA_APP_DIR"' in entry_raw or "os.environ.get('MIA_APP_DIR'" in entry_raw,
    )
    check(
        "entry_litellm.py distingue frozen (sys.frozen) de dev para el app_dir",
        'getattr(sys, "frozen"' in entry_raw or "getattr(sys, 'frozen'" in entry_raw,
    )
    check(
        "entry_litellm.py usa LOCALAPPDATA para el app_dir cuando esta frozen",
        "LOCALAPPDATA" in entry_raw,
    )
    # Lección del build real (2026-07-10): con stdout redirigido a archivo/pipe
    # (cáscara, humo del build), el banner no-ASCII de litellm muere con
    # UnicodeEncodeError en cp1252. El entry debe reconfigurar los streams a
    # UTF-8 — el equivalente frozen del PYTHONIOENCODING de start_litellm.ps1.
    check(
        "entry_litellm.py reconfigura stdout/stderr a UTF-8 (equivalente frozen de PYTHONIOENCODING)",
        'reconfigure(encoding="utf-8"' in entry_raw or "reconfigure(encoding='utf-8'" in entry_raw,
    )

    # 4 · mia-litellm.spec: onedir, upx=False (nunca True), collect_* de litellm,
    #     tiktoken_ext, salida correcta.
    check(
        "mia-litellm.spec es un onedir (COLLECT presente, no --onefile)",
        "COLLECT(" in spec,
    )
    check(
        "mia-litellm.spec usa upx=False (no upx=True)",
        "upx=False" in spec and "upx=True" not in spec,
    )
    check(
        "mia-litellm.spec tiene upx=False tanto en EXE como en COLLECT (2 ocurrencias)",
        spec.count("upx=False") >= 2,
    )
    check(
        "mia-litellm.spec recolecta litellm (collect_all o collect_data_files)",
        "collect_all(\"litellm\")" in spec or "collect_all('litellm')" in spec
        or "collect_data_files(\"litellm\")" in spec or "collect_data_files('litellm')" in spec,
    )
    check(
        "mia-litellm.spec trae los hiddenimports de tiktoken_ext",
        "tiktoken_ext" in spec and "tiktoken_ext.openai_public" in spec,
    )
    check(
        "mia-litellm.spec apunta el Analysis a entry_litellm.py",
        "entry_litellm.py" in spec,
    )
    check(
        "mia-litellm.spec NO trae ninguna llamada collect_*() sobre prisma",
        not re.search(r"collect_\w+\(\s*[\"']prisma[\"']", spec, re.IGNORECASE),
    )
    check(
        "mia-litellm.spec nombra su salida como 'mia-litellm' (EXE/COLLECT name=)",
        spec.count('name="mia-litellm"') >= 2 or spec.count("name='mia-litellm'") >= 2,
    )
    # Lección del primer build real (2026-07-10): litellm 1.74.8 crea un
    # AsyncHTTPHandler al importarse y llama certifi.where() — sin el
    # cacert.pem dentro del bundle, el exe muere en el import con
    # FileNotFoundError antes de servir nada.
    check(
        "mia-litellm.spec recolecta los data files de certifi (cacert.pem dentro del bundle)",
        'collect_data_files("certifi")' in spec or "collect_data_files('certifi')" in spec,
    )
    check(
        "build_litellm.ps1 pinea pyinstaller-hooks-contrib (hook-certifi) en .venv-litellm",
        "pyinstaller-hooks-contrib" in build,
    )

    # 5 · build_litellm.ps1: venv correcto, valida $LASTEXITCODE, verifica pin
    #     de litellm tras instalar pyinstaller, humo real presente.
    check(
        "build_litellm.ps1 usa el pyinstaller de .venv-litellm (nunca el de la app)",
        ".venv-litellm\\Scripts\\pyinstaller.exe" in build,
    )
    check(
        "build_litellm.ps1 NO usa el pyinstaller del venv de la app (.venv\\Scripts\\pyinstaller.exe)",
        ".venv\\Scripts\\pyinstaller.exe" not in build.replace(".venv-litellm\\Scripts\\pyinstaller.exe", ""),
    )
    check(
        "build_litellm.ps1 referencia mia-litellm.spec",
        "mia-litellm.spec" in build,
    )
    check(
        "build_litellm.ps1 valida $LASTEXITCODE de PyInstaller (no asume éxito ciego)",
        "$LASTEXITCODE" in build and "$exitCode" in build,
    )
    check(
        "build_litellm.ps1 verifica el pin de litellm (1.74.8) tras instalar pyinstaller en su venv",
        "1.74.8" in build and "litellm" in build,
    )
    check(
        "build_litellm.ps1 trae el humo real: valida /health/liveliness",
        "/health/liveliness" in build,
    )
    check(
        "build_litellm.ps1 trae el humo real: valida /v1/models",
        "/v1/models" in build,
    )
    check(
        "build_litellm.ps1 valida el caso SIN Bearer (401/403)",
        "401" in build and "403" in build,
    )
    check(
        "build_litellm.ps1 mata el proceso del humo (taskkill /T /F)",
        "taskkill" in build and "/T" in build and "/F" in build,
    )
    check(
        "build_litellm.ps1 usa MIA_APP_DIR apuntando a una carpeta temporal en el humo (no el .env real del repo)",
        "MIA_APP_DIR" in build and "$env:TEMP" in build,
    )

    # 6 · setup_venv_litellm.ps1: usa el intérprete base de .venv (pyvenv.cfg),
    #     pinea litellm[proxy]==1.74.8, es idempotente.
    check(
        "setup_venv_litellm.ps1 lee el intérprete base desde .venv\\pyvenv.cfg",
        "pyvenv.cfg" in setup_venv and "home" in setup_venv,
    )
    check(
        "setup_venv_litellm.ps1 instala litellm[proxy]==1.74.8",
        "1.74.8" in setup_venv and "litellm[proxy]" in setup_venv,
    )
    check(
        "setup_venv_litellm.ps1 es idempotente (verifica antes de reinstalar)",
        "idempotente" in setup_venv.lower() or "Test-LitellmPinOk" in setup_venv,
    )

    # 7 · master_key SOLO en el yaml instalador, litellm_config.yaml (dev) NO cambia.
    check(
        "litellm_config.installer.yaml define general_settings.master_key vía os.environ/LITELLM_MASTER_KEY",
        "master_key" in installer_cfg and "os.environ/LITELLM_MASTER_KEY" in installer_cfg,
    )
    check(
        "litellm_config.yaml (dev) NO tiene master_key (no se toca este archivo)",
        "master_key" not in dev_cfg,
    )

    # 7b · CP-OR: ambos yaml (dev + instalador) exponen los alias de OpenRouter,
    #      SINCRONIZADOS: openrouter-sonnet (razonamiento) y openrouter-haiku (tareas
    #      baratas de la política "openrouter"), ambos con os.environ/OPENROUTER_API_KEY.
    for cfg_name, cfg_text in (("litellm_config.yaml (dev)", dev_cfg),
                               ("litellm_config.installer.yaml", installer_cfg)):
        check(
            f"{cfg_name} expone el alias openrouter-sonnet",
            "openrouter-sonnet" in cfg_text,
        )
        check(
            f"{cfg_name} expone el alias openrouter-haiku (CP-OR · tareas baratas)",
            "openrouter-haiku" in cfg_text,
        )
        check(
            f"{cfg_name}: los alias de OpenRouter usan os.environ/OPENROUTER_API_KEY",
            cfg_text.count("os.environ/OPENROUTER_API_KEY") >= 2,
        )

    # 9 · bind loopback (correccion de seguridad): el CLI de litellm bindea en
    #     0.0.0.0 por defecto -- el gateway de modelos (reenvia prompts
    #     juridicos con las llaves de API de la firma) debe quedar SOLO en
    #     127.0.0.1, igual criterio que la DB (listen_addresses).
    orchestration_json_obj = json.loads(orchestration_json)
    litellm_cmd = orchestration_json_obj.get("litellm", {}).get("cmd", [])
    host_flag_idx = litellm_cmd.index("--host") if "--host" in litellm_cmd else -1
    check(
        "orchestration.installer.json: el cmd de litellm trae --host seguido de 127.0.0.1",
        host_flag_idx != -1
        and host_flag_idx + 1 < len(litellm_cmd)
        and litellm_cmd[host_flag_idx + 1] == "127.0.0.1",
    )

    check(
        "entry_litellm.py inyecta --host 127.0.0.1 por defecto si no viene en argv (defensa en profundidad)",
        '"--host" not in sys.argv[1:]' in entry_code
        and 'sys.argv[1:1] = ["--host", "127.0.0.1"]' in entry_code,
    )

    run_clean_cmd_match = re.search(r"^\s*&\s*\$LiteLLM\s+--config\s+\$Config.*$", run_clean_ps1, re.MULTILINE)
    run_clean_cmd = run_clean_cmd_match.group(0) if run_clean_cmd_match else ""
    check(
        "scripts/run_litellm_clean.ps1 lanza litellm con --host 127.0.0.1",
        "--host 127.0.0.1" in run_clean_cmd,
    )

    check(
        "build_litellm.ps1 verifica el bind loopback del humo (netstat/Get-NetTCPConnection)",
        "Get-NetTCPConnection" in build and "127.0.0.1" in build,
    )
    check(
        "build_litellm.ps1 exige que el acceso via IP LAN falle si hay IP LAN disponible",
        "Get-NetIPAddress" in build,
    )
    check(
        "build_litellm.ps1 pinea pyinstaller-hooks-contrib==2026.6 como string literal",
        "2026.6" in build,
    )
    check(
        "build_litellm.ps1 pinea pyinstaller==6.21.0 como string literal",
        "6.21.0" in build,
    )

    # 8 · .gitignore cubre .venv-litellm/ y packaging/dist|build.
    gitignore = (ROOT / ".gitignore").read_text(encoding="utf-8")
    check(
        ".gitignore ignora .venv-litellm/",
        ".venv-litellm/" in gitignore,
    )
    check(
        ".gitignore ignora packaging/dist/ y packaging/build/",
        "packaging/dist/" in gitignore and "packaging/build/" in gitignore,
    )

    passed = sum(1 for _, ok in _results if ok)
    total = len(_results)
    print(f"\nRESULT: {passed}/{total} checks PASS")
    return 0 if passed == total else 1


if __name__ == "__main__":
    sys.exit(main())
