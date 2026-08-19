"""Gate: traspaso de asunto — inventario [doc n] al reabrir."""
from __future__ import annotations

import asyncio
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from mia.agents import handoff as matter_handoff  # noqa: E402

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

FAILED: list[str] = []


def check(name: str, ok: bool) -> None:
    print(f"  [{'OK' if ok else 'FAIL'}] {name}")
    if not ok:
        FAILED.append(name)


async def _fake_load(_tenant: str, _matter: str):
    return {"doc_inventory": {"1": "hash-a", "2": "hash-b"}, "locators": [1, 2]}


def main() -> int:
    original = matter_handoff.load_handoff
    matter_handoff.load_handoff = _fake_load  # type: ignore[assignment]
    try:
        asyncio.run(matter_handoff.check_reopen(
            "t", "m",
            [{"id": "hash-a", "content": "x"}, {"id": "hash-b", "content": "y"}]))
        check("reabrir con el mismo inventario cierra", True)

        try:
            asyncio.run(matter_handoff.check_reopen("t", "m", [{"id": "hash-a", "content": "x"}]))
            broken = False
        except matter_handoff.HandoffBroken as exc:
            broken = "[doc 2]" in str(exc)
        check("falta un [doc n] del inventario: HandoffBroken", broken)
    finally:
        matter_handoff.load_handoff = original  # type: ignore[assignment]

    sel = matter_handoff.saved_argument_selection({
        "decisiones": {"hitl": "approved", "argument_selection": {"include": ["A1"], "exclude": ["A2"]}},
    })
    check("el traspaso recarga la selección HITL",
          sel == {"include": ["A1"], "exclude": ["A2"]})
    check("sin ficha no hay selección que recargar",
          matter_handoff.saved_argument_selection(None) is None)

    if FAILED:
        print("FAIL:", ", ".join(FAILED))
        return 1
    print("PASS: traspaso fail-closed al reabrir.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
