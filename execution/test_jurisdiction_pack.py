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
from datetime import date
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

    # 6 · quick win freshness declarativo por archivo (docs/analisis-claude-for-legal.md §5.3)
    check("co.freshness trae entrada por archivo de datos (term_catalog)",
          isinstance(co.freshness, dict) and "term_catalog" in co.freshness)
    check("sin last_verified (pack provisional) -> is_stale es None (no evaluable, no 'vigente')",
          co.is_stale("term_catalog") is None)
    check("is_stale de un archivo sin entrada de freshness -> None",
          co.is_stale("archivo_inexistente") is None)
    check("genérico sin freshness ({})", g.freshness == {})
    check("genérico is_stale siempre None", g.is_stale("holidays") is None)

    import dataclasses
    vencido = dataclasses.replace(co, freshness={
        "term_catalog": {"last_verified": "2000-01-01", "freshness_window_days": 90}})
    vigente = dataclasses.replace(co, freshness={
        "term_catalog": {"last_verified": date.today().isoformat(), "freshness_window_days": 90}})
    sin_ventana = dataclasses.replace(co, freshness={
        "term_catalog": {"last_verified": "2000-01-01", "freshness_window_days": None}})
    malformado = dataclasses.replace(co, freshness={"term_catalog": {"last_verified": "no-es-fecha", "freshness_window_days": 90}})
    check("is_stale True cuando pasó la ventana de vigencia", vencido.is_stale("term_catalog") is True)
    check("is_stale False dentro de la ventana", vigente.is_stale("term_catalog") is False)
    check("freshness_window_days=None (sin vencimiento) -> is_stale None", sin_ventana.is_stale("term_catalog") is None)
    check("fecha malformada -> is_stale None (fail-soft, no lanza)", malformado.is_stale("term_catalog") is None)

    # 7 · fail-soft de load_pack ante "freshness" de tipo equivocado en meta.json
    # (revisión capa 2: is_stale() solo validaba la entrada POR ARCHIVO, no el valor
    # de nivel superior — un meta.json con "freshness": [...] tumbaba is_stale con
    # AttributeError. load_pack ahora descarta el valor si no es dict).
    import json as _json
    import tempfile
    from mia.jurisdiction import pack as pack_mod

    def _malformed_top_level_freshness_is_safe() -> bool:
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            (tmp_path / "zz").mkdir()
            (tmp_path / "zz" / "meta.json").write_text(_json.dumps({
                "code": "zz", "name": "Zeta", "version": "0",
                "verified": False, "verified_at": None, "sources": [],
                "freshness": ["esto no es un dict"],
            }), encoding="utf-8")
            original = pack_mod.PACKS_DIR
            pack_mod.PACKS_DIR = tmp_path
            try:
                zz = pack_mod.load_pack("zz")
                return zz.freshness == {} and zz.is_stale("cualquiera") is None
            finally:
                pack_mod.PACKS_DIR = original

    check("load_pack fail-soft ante 'freshness' de tipo equivocado en meta.json (no lanza, da {})",
          _malformed_top_level_freshness_is_safe())

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
