"""Mia · packaging/entry_litellm.py — entrypoint del bundle PyInstaller del proxy LiteLLM.

Empaqueta `litellm[proxy]` como un SEGUNDO ejecutable (mia-litellm.exe, onedir,
ver mia-litellm.spec) para que la cáscara de escritorio lo lance como un servicio
más (junto a DB/backend/frontend), sin requerir Python instalado en la máquina
del abogado. El proxy libre (dev, `scripts/start_litellm.ps1` +
`scripts/run_litellm_clean.ps1`) resuelve estos mismos riesgos con variables de
entorno de PowerShell y un hot-patch de `proxy_server.py`; aquí NO hay PowerShell
entre el usuario y el proceso, así que cada blindaje se reimplementa en Python,
en el ORDEN EXACTO que importa (ver cada bloque abajo — el orden es el contrato,
no un detalle de estilo).

Nota de diseño (Contrato 3, plan F2): el CLI real de litellm es un comando click
(`litellm.proxy.proxy_cli.run_server`, expuesto como `litellm.run_server` y como
el entry_point de consola "litellm"). Al llamarlo como función, click ejecuta su
`Command.main()`, que por defecto parsea `sys.argv[1:]` — exactamente el mismo
argv que la cáscara / build_litellm.ps1 le pasan al exe (`--config ... --port
...`), así que NO se re-construye el argv a mano: se deja que click lo lea.
"""
from __future__ import annotations

import os
import re
import sys
from pathlib import Path

# ---------------------------------------------------------------------------
# Blindaje 1 · mapa de costos local (mismo motivo que packaging/entry_backend.py):
# sin esta variable, litellm dispara un httpx.get() a GitHub EN CADA ARRANQUE
# para bajar precios/costos de modelos — rompe local-first y cuelga con firewall
# corporativo. DEBE ir antes de cualquier `import litellm` más abajo.
# ---------------------------------------------------------------------------
os.environ.setdefault("LITELLM_LOCAL_MODEL_COST_MAP", "True")

# ---------------------------------------------------------------------------
# Blindaje 1b · stdout/stderr en UTF-8 (lección del build real 2026-07-10):
# el proxy imprime su banner con caracteres no-ASCII vía click.echo; cuando la
# cáscara (o el humo del build) redirige stdout a archivo/pipe, Python usa la
# codificación de la locale de Windows (cp1252) y el arranque MUERE con
# UnicodeEncodeError antes de servir nada. Es el mismo blindaje que
# scripts/start_litellm.ps1 logra en dev con PYTHONIOENCODING=utf-8 — pero un
# exe congelado no puede depender de que quien lo lance exporte esa variable.
# errors="replace" garantiza que ningún carácter raro vuelva a tumbar el proceso.
# ---------------------------------------------------------------------------
for _stream in (sys.stdout, sys.stderr):
    try:
        _stream.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass  # sin consola (p. ej. lanzado sin stdout): no hay nada que reconfigurar.


def _resolve_app_dir() -> Path:
    """Replica MÍNIMA y consciente de `backend/mia/config.py` (líneas 15-30):
    MIA_APP_DIR (env) > frozen -> %LOCALAPPDATA%\\Mia > dev -> raíz del repo.
    NO importa `mia` a propósito: este exe se empaqueta solo (mia-litellm.spec
    no incluye el paquete backend) y duplicar 6 líneas es más simple y más
    seguro que acoplar dos bundles de PyInstaller distintos.
    """
    app_dir_env = os.environ.get("MIA_APP_DIR", "").strip()
    if app_dir_env:
        return Path(app_dir_env).resolve()
    if getattr(sys, "frozen", False):
        return (Path(os.environ.get("LOCALAPPDATA") or Path.home()) / "Mia").resolve()
    # Dev: este archivo vive en <repo>/packaging/entry_litellm.py -> el padre es <repo>/.
    return Path(__file__).resolve().parent.parent


# ---------------------------------------------------------------------------
# Blindaje 2 · allowlist-load del .env del app_dir. A propósito NO se usa
# `dotenv.load_dotenv()` (traería TODO el .env, incluida DATABASE_URL) ni se
# lee desde el cwd (el proceso puede arrancar desde cualquier carpeta runtime,
# igual que scripts/run_litellm_clean.ps1 aísla el cwd del repo).
# ---------------------------------------------------------------------------
_ALLOWLIST_EXACT = {
    "ANTHROPIC_API_KEY",
    "VOYAGE_API_KEY",
    "OPENROUTER_API_KEY",
    "LITELLM_MASTER_KEY",
}
_ENV_LINE_RE = re.compile(r"^\s*([^#=][^=]*?)\s*=\s*(.*)$")


def _allowlist_load_env(app_dir: Path) -> None:
    env_path = app_dir / ".env"
    if not env_path.is_file():
        return
    try:
        text = env_path.read_text(encoding="utf-8-sig")
    except OSError:
        return
    for raw_line in text.splitlines():
        match = _ENV_LINE_RE.match(raw_line)
        if not match:
            continue
        key = match.group(1).strip()
        if key not in _ALLOWLIST_EXACT and not key.startswith("LITELLM_"):
            continue  # fuera de la allowlist: NUNCA se carga (ni DATABASE_URL ni PG_*).
        if key in os.environ:
            continue  # nunca sobreescribir una variable ya presente en el entorno.
        value = match.group(2).strip().strip('"').strip("'")
        os.environ[key] = value


_allowlist_load_env(_resolve_app_dir())

# ---------------------------------------------------------------------------
# Blindaje 3 · scrub duro de DATABASE_URL/PG_*: aunque la allowlist de arriba
# nunca las CARGA desde el .env, pudieron llegar heredadas del proceso padre
# (Job Object de la cáscara, o una terminal de desarrollo). Misma lista exacta
# que scripts/run_litellm_clean.ps1 — litellm interpreta DATABASE_URL como "hay
# que gestionar mi BD interna" e intenta importar Prisma (ModuleNotFoundError).
# ---------------------------------------------------------------------------
_SCRUB_VARS = (
    "DATABASE_URL",
    "DIRECT_URL",
    "PG_DB",
    "PGPASSWORD",
    "PG_PASSWORD",
    "PG_APP_PASSWORD",
    "POSTGRES_HOST",
    "POSTGRES_PORT",
    "POSTGRES_USER",
    "POSTGRES_PASSWORD",
    "DATABASE_HOST",
    "DATABASE_PORT",
    "DATABASE_USERNAME",
    "DATABASE_PASSWORD",
    "DATABASE_NAME",
    "DATABASE_SCHEMA",
)
for _var in _SCRUB_VARS:
    os.environ.pop(_var, None)

# ---------------------------------------------------------------------------
# Blindaje 4 · neutralizar dotenv.load_dotenv ANTES de `import litellm`.
# `litellm/__init__.py` hace `from .proxy.proxy_cli import run_server` de forma
# INCONDICIONAL, y `proxy_cli.py` llama `load_dotenv()` a nivel de módulo (si
# LITELLM_MODE != "PRODUCTION", que es el default) — es decir: el simple
# `import litellm` de más abajo, sin este parche, reinyectaría TODO el .env del
# cwd (incluida DATABASE_URL) por fuera de la allowlist del blindaje 2. Se
# parchea el ATRIBUTO del módulo `dotenv` antes de importar litellm porque
# `proxy_cli.py` hace `from dotenv import load_dotenv` — al ejecutarse esa
# línea, toma la versión ya parcheada (no-op) del namespace de `dotenv`.
# ---------------------------------------------------------------------------
import dotenv  # noqa: E402
import dotenv.main  # noqa: E402


def _noop_load_dotenv(*_args: object, **_kwargs: object) -> bool:
    return False


dotenv.load_dotenv = _noop_load_dotenv  # type: ignore[assignment]
dotenv.main.load_dotenv = _noop_load_dotenv  # type: ignore[assignment]

# ---------------------------------------------------------------------------
# Blindaje 5 · delegar al CLI real de litellm. `run_server` es un comando click
# (`@click.command()`); llamarlo invoca `Command.main()`, que parsea
# `sys.argv[1:]` por defecto — el mismo argv que la cáscara / build_litellm.ps1
# ya arman (`--config <ruta> --port <puerto>`). No se re-construye el argv.
# ---------------------------------------------------------------------------
import litellm  # noqa: E402  (el import en frío, aquí, es intencional — ver docstring)

# ---------------------------------------------------------------------------
# Blindaje 6 · defensa en profundidad: si nadie pasó --host en argv, forzar
# loopback ANTES de delegar a click. Así un orchestration.json viejo (sin el
# flag) o un lanzamiento manual del exe NUNCA bindean en 0.0.0.0 (default del
# CLI de litellm), aunque el flag explícito en el JSON/cmd siga siendo la
# protección vigente hoy.
# ---------------------------------------------------------------------------
if "--host" not in sys.argv[1:]:
    sys.argv[1:1] = ["--host", "127.0.0.1"]

if __name__ == "__main__":
    litellm.run_server()
