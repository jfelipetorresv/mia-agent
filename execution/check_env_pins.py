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


def check(name: str, ok: bool, detail: str) -> None:
    _results.append((name, bool(ok)))
    print(("  [PASS] " if ok else "  [FAIL] ") + f"{name}: {detail}")


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

    passed = sum(1 for _, ok in _results if ok)
    total = len(_results)
    print(f"\nRESULT: {passed}/{total} checks PASS")
    if passed == total:
        print("Pins del venv OK.")
        return 0
    print("Pins del venv FAIL — el venv de la app fue alterado. Revisar Riesgo #32.")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
