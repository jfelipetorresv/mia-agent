"""
Mia · test_playbook_manager.py — gate del Módulo 2b (PlaybookManager).

Verifica OFFLINE:
  1. ÍNDICE SIEMPRE PRESENTE: render_index() lista todos los playbooks y no
     depende del estado activo. Presupuesto ~3.000 tokens (exceso rechazado).
  2. CONTENIDO COMPLETO SOLO ON-DEMAND: por defecto el cuerpo no entra al prompt;
     el índice nunca contiene el cuerpo; el cuerpo solo aparece cuando se solicita
     explícitamente (get_content / activate).

Salida: exit 0 = PASS.
    .venv\\Scripts\\python.exe execution\\test_playbook_manager.py
"""
from __future__ import annotations
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))  # para `import mia.*`

from mia.memory.playbook_manager import (
    PLAYBOOK_INDEX_MAX_TOKENS,
    Playbook,
    PlaybookManager,
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


# Cuerpos con un centinela para verificar que NO se filtran al índice.
PB1 = Playbook(
    id="caducidad-reparacion-directa",
    title="Caducidad en reparación directa",
    summary="cómputo del término de 2 años",
    applies_when="el daño es imputable al Estado y se discute la oportunidad",
    content="CUERPO_SECRETO_PB1 — el término de caducidad de la reparación directa es de dos años...",
)
PB2 = Playbook(
    id="objecion-cuantia",
    title="Objeción a la cuantía",
    summary="estrategia para cuantías infladas",
    applies_when="la pretensión económica no está soportada en pruebas",
    content="CUERPO_SECRETO_PB2 — para objetar la cuantía conviene exigir el soporte probatorio...",
)


def _mgr() -> PlaybookManager:
    m = PlaybookManager()
    m.register(PB1)
    m.register(PB2)
    return m


# --- 1 · índice siempre presente ----------------------------------------------
def test_index_always_present() -> None:
    m = _mgr()
    idx = m.render_index()
    check("el índice lista todos los playbooks", PB1.id in idx and PB2.id in idx)
    check("el índice trae títulos y resúmenes", "Caducidad en reparación directa" in idx and "cuantías infladas" in idx)
    check("el índice NO contiene el contenido completo",
          "CUERPO_SECRETO_PB1" not in idx and "CUERPO_SECRETO_PB2" not in idx)

    # No depende del estado activo: sigue idéntico tras activar.
    m.activate(PB1.id)
    check("el índice sigue idéntico tras activar un playbook", m.render_index() == idx)

    # Presupuesto del índice.
    check("presupuesto del índice = 3000 tokens", PLAYBOOK_INDEX_MAX_TOKENS == 3000)
    big = PlaybookManager()
    huge = Playbook(id="x", title="t", summary="s" * 13000, applies_when="w", content="c")
    check("un índice > 3000 tokens se rechaza (ValueError)", _raises(lambda: big.register(huge)))


# --- 2 · contenido completo solo on-demand ------------------------------------
def test_content_on_demand() -> None:
    m = _mgr()

    # Por defecto: nada activo → sin contenido en el prompt.
    check("sin activar, render_active() está vacío", m.render_active() == "")

    # El cuerpo solo se obtiene con una llamada EXPLÍCITA.
    check("get_content() devuelve el cuerpo completo (explícito)", "CUERPO_SECRETO_PB1" in m.get_content(PB1.id))

    # Activar = traer on-demand el contenido del que aplica al asunto.
    m.activate(PB1.id)
    active = m.render_active()
    check("tras activar, render_active() incluye el cuerpo del activo", "CUERPO_SECRETO_PB1" in active)
    check("render_active() NO incluye el cuerpo del no-activo", "CUERPO_SECRETO_PB2" not in active)
    check("active_ids refleja el activo", m.active_ids == [PB1.id])

    # reset() limpia los activos (frontera de asunto).
    m.reset()
    check("reset() limpia los activos", m.active_ids == [] and m.render_active() == "")

    # id desconocido falla.
    check("get_content() de id desconocido lanza KeyError", _raises(lambda: m.get_content("no-existe")))
    check("activate() de id desconocido lanza KeyError", _raises(lambda: m.activate("no-existe")))


def main() -> int:
    print("== Módulo 2b · PlaybookManager ==")
    test_index_always_present()
    test_content_on_demand()
    passed = sum(1 for _, ok in _results if ok)
    total = len(_results)
    print(f"\n{passed}/{total} checks PASS")
    return 0 if passed == total else 1


if __name__ == "__main__":
    raise SystemExit(main())
