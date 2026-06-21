"""
Mia · test_jurisdiction_pack.py — gate de la abstracción de Pack (Fase 0.C, Decisión #24).

Verifica OFFLINE (sin DB, sin red):
  1. load_pack("co") carga datos reales del pack (festivos, formatos de ID, marcadores).
  2. load_pack(inexistente) y load_pack("")/None -> GenericPack SIN excepción (modo genérico).
  3. list_packs() incluye los packs instalados (al menos "co") y NO el genérico.
  4. El GenericPack trae formatos de ID genéricos y está marcado is_generic.
  5. Un pack provisional NO se presenta como verificado (verified=False).

Salida: exit 0 = PASS.
    .venv\\Scripts\\python.exe execution\\test_jurisdiction_pack.py
"""
from __future__ import annotations
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))  # para `import mia.*`

from mia.jurisdiction.pack import (
    GENERIC_CODE,
    JurisdictionPack,
    generic_pack,
    list_packs,
    load_pack,
)

_results: list[tuple[str, bool]] = []


def check(name: str, ok: bool) -> None:
    _results.append((name, bool(ok)))
    print(("  [OK]   " if ok else "  [FAIL] ") + name)


def _no_raise(fn) -> bool:
    try:
        fn()
        return True
    except Exception as e:  # noqa: BLE001
        print(f"         (excepción inesperada: {e!r})")
        return False


def main() -> int:
    # 1 · pack co carga datos reales
    co = load_pack("co")
    check("load_pack('co') devuelve JurisdictionPack", isinstance(co, JurisdictionPack))
    check("co.code == 'co'", co.code == "co")
    check("co.name == 'Colombia'", co.name == "Colombia")
    check("co trae festivos (2025 no vacío)", len(co.holiday_dates(2025)) > 0)
    check("co trae formatos de ID (cedula)", "cedula" in co.id_formats)
    check("co trae marcadores documentales (norm)", "norm" in co.doc_markers)
    check("co NO es genérico", co.is_generic is False)

    # 2 · inexistente / vacío / None -> GenericPack sin excepción
    check("load_pack('xx') no lanza", _no_raise(lambda: load_pack("xx")))
    check("load_pack('xx') -> genérico", load_pack("xx").is_generic is True)
    check("load_pack('') -> genérico", load_pack("").is_generic is True)
    check("load_pack(None) -> genérico", load_pack(None).is_generic is True)
    check("load_pack('co') es case-insensitive", load_pack("CO").code == "co")

    # 3 · list_packs incluye co, excluye genérico
    packs = list_packs()
    check("list_packs() incluye 'co'", "co" in packs)
    check("list_packs() NO incluye el genérico", GENERIC_CODE not in packs)

    # 4 · GenericPack tiene formatos genéricos
    g = generic_pack()
    check("genérico trae formato email", "email" in g.id_formats)
    check("genérico sin festivos", g.holiday_dates(2025) == [])
    check("genérico sin marcadores", g.doc_markers == {})

    # 5 · un pack provisional NO se presenta como verificado (regla cardinal)
    check("co.verified is False (provisional)", co.verified is False)
    check("co.verified_at is None (provisional)", co.verified_at is None)

    passed = sum(1 for _, ok in _results if ok)
    total = len(_results)
    print(f"\nRESULT: {passed}/{total} checks PASS")
    if passed == total:
        print("Jurisdiction Pack OK — abstracción de packs verificada.")
        return 0
    print("Jurisdiction Pack FAIL.")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
