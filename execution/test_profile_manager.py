"""
Mia · test_profile_manager.py — gate del Módulo 2a (ProfileManager).

Verifica OFFLINE:
  1. FROZEN al inicio del asunto: el snapshot captura el perfil vigente; cambiar el
     perfil durante un asunto activo NO afecta ese asunto, solo el SIGUIENTE.
  2. Presupuesto de tokens: PERFIL_ABOGADO ≤600, PERFIL_DESPACHO ≤900; exceder el
     presupuesto se rechaza con ValueError.
  3. El snapshot es inmutable y `render()` arma el bloque (omitiendo vacíos).

Salida: exit 0 = PASS.
    .venv\\Scripts\\python.exe execution\\test_profile_manager.py
"""
from __future__ import annotations
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))  # para `import mia.*`

from mia.memory.profile_manager import (
    PERFIL_ABOGADO_MAX_TOKENS,
    PERFIL_DESPACHO_MAX_TOKENS,
    ProfileManager,
    estimate_tokens,
)

_results: list[tuple[str, bool]] = []


def check(name: str, ok: bool) -> None:
    _results.append((name, bool(ok)))
    print(("  [OK]   " if ok else "  [FAIL] ") + name)


def _raises(fn) -> bool:
    try:
        fn()
        return False
    except Exception:
        return True


# --- 1 · frozen al inicio del asunto ------------------------------------------
def test_frozen_at_matter_start() -> None:
    pm = ProfileManager(abogado="abogado-v1", despacho="despacho-v1")
    snap1 = pm.start_matter("m-1")
    check("el snapshot captura el perfil vigente",
          snap1.abogado == "abogado-v1" and snap1.despacho == "despacho-v1")

    # Cambio de perfil DURANTE el asunto activo.
    pm.set_abogado("abogado-v2")
    pm.set_despacho("despacho-v2")

    check("cambiar el perfil NO afecta el asunto activo (abogado)", snap1.abogado == "abogado-v1")
    check("cambiar el perfil NO afecta el asunto activo (despacho)", snap1.despacho == "despacho-v1")
    check("el perfil vigente del manager SÍ cambió", pm.abogado == "abogado-v2" and pm.despacho == "despacho-v2")

    # El SIGUIENTE asunto sí ve el cambio.
    snap2 = pm.start_matter("m-2")
    check("el SIGUIENTE asunto ve el cambio (abogado)", snap2.abogado == "abogado-v2")
    check("el SIGUIENTE asunto ve el cambio (despacho)", snap2.despacho == "despacho-v2")
    check("el asunto previo sigue intacto tras abrir el siguiente", snap1.abogado == "abogado-v1")

    # El snapshot es inmutable.
    check("el snapshot es inmutable (frozen)", _raises(lambda: setattr(snap1, "abogado", "x")))


# --- 2 · presupuesto de tokens ------------------------------------------------
def test_budgets() -> None:
    check("límite PERFIL_ABOGADO = 600", PERFIL_ABOGADO_MAX_TOKENS == 600)
    check("límite PERFIL_DESPACHO = 900", PERFIL_DESPACHO_MAX_TOKENS == 900)

    # ~4 caracteres por token: 600 tok = 2400 chars (ok), 2401 chars = 601 tok (over).
    ok_abogado = "a" * (PERFIL_ABOGADO_MAX_TOKENS * 4)
    over_abogado = "a" * (PERFIL_ABOGADO_MAX_TOKENS * 4 + 1)
    check("abogado en el límite (600 tok) se acepta", not _raises(lambda: ProfileManager(abogado=ok_abogado)))
    check("abogado > 600 tok se rechaza (ValueError)", _raises(lambda: ProfileManager(abogado=over_abogado)))

    ok_despacho = "a" * (PERFIL_DESPACHO_MAX_TOKENS * 4)
    over_despacho = "a" * (PERFIL_DESPACHO_MAX_TOKENS * 4 + 1)
    check("despacho en el límite (900 tok) se acepta", not _raises(lambda: ProfileManager(despacho=ok_despacho)))
    check("despacho > 900 tok se rechaza (ValueError)", _raises(lambda: ProfileManager(despacho=over_despacho)))

    # También al editar (no solo al construir).
    pm = ProfileManager()
    check("set_abogado > 600 tok se rechaza", _raises(lambda: pm.set_abogado(over_abogado)))
    check("estimate_tokens('') == 0", estimate_tokens("") == 0)


# --- 3 · render ---------------------------------------------------------------
def test_render() -> None:
    pm = ProfileManager(abogado="Especialista en seguros.", despacho="Defendemos aseguradoras.")
    snap = pm.start_matter("m-1")
    r = snap.render()
    check("render incluye ambos perfiles", "Perfil del abogado" in r and "Perfil del despacho" in r)
    check("abogado_tokens estima > 0", snap.abogado_tokens > 0)

    pm2 = ProfileManager(abogado="solo el abogado")
    snap2 = pm2.start_matter("m-2")
    r2 = snap2.render()
    check("render omite el perfil de despacho vacío",
          "Perfil del abogado" in r2 and "Perfil del despacho" not in r2)


def main() -> int:
    print("== Módulo 2a · ProfileManager ==")
    test_frozen_at_matter_start()
    test_budgets()
    test_render()
    passed = sum(1 for _, ok in _results if ok)
    total = len(_results)
    print(f"\n{passed}/{total} checks PASS")
    return 0 if passed == total else 1


if __name__ == "__main__":
    raise SystemExit(main())
