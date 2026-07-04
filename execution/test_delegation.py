"""
Mia · test_delegation.py — gate de la primitiva de delegación paralela (CP-E5 · Ola 5).

Ejercita `agents/delegation.py::run_parallel` (mecánica pura, sin DB ni LLM):
  · orden ESTABLE de resultados (no depende del orden de llegada de los workers);
  · FAIL-SOFT por subtarea (una que lanza NO tumba el lote; queda ok=False con su error);
  · concurrencia ACOTADA de verdad (nunca corren más de `max_concurrent` a la vez);
  · tope DURO MAX_WORKERS (una lista enorme se recorta);
  · saturación de `max_concurrent` a [1, MAX_WORKERS] y lista vacía → [].

Salida: exit 0 = PASS · exit 1 = FAIL.

    .venv\\Scripts\\python.exe execution\\test_delegation.py
"""
from __future__ import annotations
import asyncio
import sys
from pathlib import Path

if sys.platform == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

from mia.agents import delegation  # noqa: E402
from mia.agents.delegation import run_parallel, MAX_WORKERS  # noqa: E402

_results: list[tuple[str, bool]] = []


def check(name: str, ok: bool) -> None:
    _results.append((name, bool(ok)))
    print(("  [OK]   " if ok else "  [FAIL] ") + name)


async def _checks() -> None:
    # A · ORDEN ESTABLE: los workers terminan en orden inverso al de la lista, pero el
    # resultado respeta el orden de `keys` (el sintetizador necesita determinismo).
    async def slow_by_index(k: str) -> str:
        # 'a' (idx grande) duerme MENOS que 'c' → 'a' termina primero; el orden debe
        # seguir siendo [a, b, c] por posición, no por llegada.
        delay = {"a": 0.03, "b": 0.02, "c": 0.01}[k]
        await asyncio.sleep(delay)
        return k.upper()

    res = await run_parallel(["a", "b", "c"], slow_by_index, max_concurrent=3)
    check("orden estable: resultados en el orden de keys",
          [r.key for r in res] == ["a", "b", "c"])
    check("orden estable: valores mapeados correctamente",
          [r.value for r in res] == ["A", "B", "C"] and all(r.ok for r in res))

    # B · FAIL-SOFT: una subtarea que lanza no tumba el lote.
    async def maybe_fail(k: str) -> str:
        if k == "boom":
            raise RuntimeError("explosión controlada")
        return k

    res = await run_parallel(["ok1", "boom", "ok2"], maybe_fail)
    by_key = {r.key: r for r in res}
    check("fail-soft: la subtarea que lanza queda ok=False con su error",
          by_key["boom"].ok is False and "explosión" in (by_key["boom"].error or ""))
    check("fail-soft: las demás siguen ok=True con su valor",
          by_key["ok1"].ok and by_key["ok1"].value == "ok1" and by_key["ok2"].ok)
    check("fail-soft: run_parallel NUNCA propaga (devolvió 3 resultados)", len(res) == 3)

    # C · CONCURRENCIA ACOTADA: con max_concurrent=2 nunca corren 3 a la vez.
    state = {"active": 0, "peak": 0}

    async def track(k: str) -> str:
        state["active"] += 1
        state["peak"] = max(state["peak"], state["active"])
        await asyncio.sleep(0.02)
        state["active"] -= 1
        return k

    await run_parallel([str(i) for i in range(6)], track, max_concurrent=2)
    check("concurrencia: el pico simultáneo respeta max_concurrent=2", state["peak"] <= 2)
    check("concurrencia: y de hecho llegó al tope (2)", state["peak"] == 2)

    # D · TOPE DURO MAX_WORKERS: una lista más larga se recorta.
    async def echo(k: str) -> str:
        return k

    big = [str(i) for i in range(MAX_WORKERS + 5)]
    res = await run_parallel(big, echo, max_concurrent=MAX_WORKERS)
    check(f"tope duro: {MAX_WORKERS + 5} subtareas se recortan a MAX_WORKERS={MAX_WORKERS}",
          len(res) == MAX_WORKERS)

    # E · SATURACIÓN de max_concurrent y lista vacía.
    check("vacío: [] → []", (await run_parallel([], echo)) == [])
    # max_concurrent=0 se satura a 1 (no cuelga, corre en serie).
    res = await run_parallel(["x", "y"], echo, max_concurrent=0)
    check("saturación: max_concurrent=0 → corre igual (satura a 1)",
          len(res) == 2 and all(r.ok for r in res))
    # max_concurrent enorme se satura a MAX_WORKERS (no revienta).
    res = await run_parallel(["x", "y"], echo, max_concurrent=10_000)
    check("saturación: max_concurrent gigante no revienta", len(res) == 2)


def main() -> int:
    asyncio.run(_checks())
    passed = sum(1 for _, ok in _results if ok)
    total = len(_results)
    print(f"\n{passed}/{total} checks PASS")
    if passed == total:
        print("Primitiva de delegación OK — CP-E5 (paralelo) verificado.")
        return 0
    print("Delegación FAIL — HALT: no avanzar (CLAUDE.md §G).")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
