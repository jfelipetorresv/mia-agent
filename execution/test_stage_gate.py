"""Gate: fail-closed de etapas y tope de pasada cara."""
from __future__ import annotations

import asyncio
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from mia.agents import packs, stage_gate  # noqa: E402
from mia.agents.graph import MatterGraphBuilder  # noqa: E402
from mia.memory.trace_capture import TraceCapture  # noqa: E402
from mia.policy import turn_budget  # noqa: E402

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

FAILED: list[str] = []


def check(name: str, ok: bool) -> None:
    print(f"  [{'OK' if ok else 'FAIL'}] {name}")
    if not ok:
        FAILED.append(name)


def main() -> int:
    try:
        stage_gate.require_upstream_for_draft({})
        closed = False
    except stage_gate.StageIncomplete as exc:
        closed = exc.stage == "facts"
    check("draft aborta si no hay pack de hechos", closed)

    md = packs.example_metadata_packs()
    stage_gate.require_upstream_for_draft(md)
    check("draft pasa preflight con packs de ejemplo", True)

    try:
        turn_budget.authorize_expensive({"expensive_calls": ["legal_verification"]},
                                       "legal_verification", authorized=False)
        second = False
    except turn_budget.TurnBudgetExceeded:
        second = True
    check("2a pasada cara sin autorizacion: TurnBudgetExceeded", second)
    turn_budget.authorize_expensive({"expensive_calls": ["legal_verification"]},
                                   "legal_verification", authorized=True)
    check("2ª pasada cara con autorización explícita pasa", True)
    check("cli-claude es no_medida, no USD 0 fingido",
          turn_budget.cost_status_for_alias("cli-claude") == "no_medida")
    check("claude-sonnet es medido",
          turn_budget.cost_status_for_alias("claude-sonnet") == "medido")

    builder = MatterGraphBuilder(trace_capture=TraceCapture())

    async def fake_llm(*_a, **_k):
        raise AssertionError("el draft no debe llamar al modelo sin packs")

    builder._llm = fake_llm
    state = {
        "tenant_id": "00000000-0000-0000-0000-000000000001",
        "matter_id": "00000000-0000-0000-0000-000000000002",
        "messages": [{"role": "user", "content": "¿operó la caducidad?"}],
        "documents": [{"id": "d1", "content": "x", "document_id": "d1"}],
        "knowledge": [],
        "metadata": {"diagnosis": "algo"},
    }
    out = asyncio.run(builder.draft_node(state))
    check("draft_node sin packs no llama al LLM",
          "producto verificado" in (out.get("draft") or "")
          and isinstance((out.get("metadata") or {}).get("stage_failed"), dict))

    if FAILED:
        print("FAIL:", ", ".join(FAILED))
        return 1
    print("PASS: etapas fail-closed y tope por turno.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
