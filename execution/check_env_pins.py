"""
Mia · check_env_pins.py — gate del Riesgo #32: pins del venv de la app.

Verifica que las dependencias de runtime del API instaladas en el venv
activo coincidan EXACTO con los pins de backend/pyproject.toml. Si el
proxy LiteLLM (u otra herramienta) degrada el venv de la app, este gate
falla antes de que el API arranque con versiones incorrectas.

Uso:  & ".venv\\Scripts\\python.exe" execution/check_env_pins.py
Sin dependencias externas (solo stdlib). Exit 0 = PASS, 1 = FAIL.
"""
from __future__ import annotations

import sys
from importlib.metadata import PackageNotFoundError, version
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

# Versiones esperadas — deben coincidir con los pins == de backend/pyproject.toml.
EXPECTED: dict[str, str] = {
    "fastapi": "0.115.14",
    "uvicorn": "0.29.0",
    "starlette": "0.46.2",
    "sse-starlette": "3.0.3",
    "websockets": "15.0.1",
    "python-multipart": "0.0.18",
    "psycopg": "3.3.4",
    "psycopg-pool": "3.3.1",
    "litellm": "1.74.8",
    "cryptography": "43.0.3",
}

_results: list[tuple[str, bool]] = []

# R3-CRITICO (Codex, ronda 3): las dos configs versionadas del proxy LiteLLM DEBEN pinear
# router_settings.num_retries == 0. Sin él, LiteLLM 1.74.8 hereda num_retries=2 y el proxy
# reintenta por su cuenta (hasta 3 POST al proveedor por intento físico de MIA). Esta es la
# guarda ANTI-DERIVA estática, en el tramo rápido que SÍ se corre siempre. La prueba viva
# (una invocación → una petición) vive en execution/test_litellm_proxy_retries.py.
_LITELLM_CONFIGS: list[tuple[str, Path]] = [
    ("litellm_config.yaml", ROOT / "litellm_config.yaml"),
    ("packaging/litellm_config.installer.yaml",
     ROOT / "packaging" / "litellm_config.installer.yaml"),
]


def _router_num_retries(path: Path) -> str | None:
    """Valor de `num_retries` dentro del bloque top-level `router_settings` (solo stdlib).

    Devuelve el valor como texto, o None si el bloque o la clave no existen. Escáner por
    indentación: entra al bloque cuando ve `router_settings:` a nivel 0 y busca `num_retries:`
    indentado debajo. Ignora comentarios y líneas vacías. No usa PyYAML a propósito: este gate
    corre en el tramo rápido y su contrato es 'solo stdlib'.
    """
    if not path.exists():
        return None
    in_router = False
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.split("#", 1)[0].rstrip()  # descarta el comentario de la línea
        if not line.strip():
            continue
        indent = len(line) - len(line.lstrip())
        key = line.strip()
        if indent == 0:
            in_router = key.startswith("router_settings:")
            continue
        if in_router and key.startswith("num_retries:"):
            return key.split(":", 1)[1].strip()
    return None


def check(name: str, ok: bool, detail: str) -> None:
    _results.append((name, bool(ok)))
    print(("  [PASS] " if ok else "  [FAIL] ") + f"{name}: {detail}")


def check_router_pins() -> None:
    print("\n== router_settings.num_retries == 0 en las configs del proxy (R3-CRITICO) ==")
    for name, path in _LITELLM_CONFIGS:
        val = _router_num_retries(path)
        check(f"router num_retries · {name}", val == "0",
              f"router_settings.num_retries = {val!r} (esperado '0'; None = bloque/clave ausente)")


def main() -> int:
    print("== Pins del venv de la app (Riesgo #32) ==")
    print(f"Python: {sys.executable}")
    for pkg, expected in EXPECTED.items():
        try:
            installed = version(pkg)
        except PackageNotFoundError:
            check(pkg, False, f"NO instalado (esperado {expected})")
            continue
        check(pkg, installed == expected, f"instalado {installed} / esperado {expected}")

    check_router_pins()

    passed = sum(1 for _, ok in _results if ok)
    total = len(_results)
    print(f"\nRESULT: {passed}/{total} checks PASS")
    if passed == total:
        print("Pins del venv OK.")
        return 0
    print("Pins FAIL — el venv de la app fue alterado (Riesgo #32) o una config del proxy "
          "perdió su pin de router_settings.num_retries (R3-CRITICO). Ver los [FAIL] de arriba.")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
