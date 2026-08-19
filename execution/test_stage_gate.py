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

    llm_calls = {"n": 0}

    async def count_llm(*_a, **_k):
        llm_calls["n"] += 1
        return "no debería", {}

    builder._llm = count_llm
    broken = {"handoff_broken": "faltan [doc 2]", "facts_pack_ok": False}
    st_h = {
        "tenant_id": "00000000-0000-0000-0000-000000000001",
        "matter_id": "00000000-0000-0000-0000-000000000002",
        "messages": [{"role": "user", "content": "¿operó la caducidad?"}],
        "documents": [{"id": "d1", "content": "x", "document_id": "d1"}],
        "knowledge": [],
        "metadata": dict(broken),
        "jurisdictions": ["co"],
    }
    out_r = asyncio.run(builder.research_node(st_h))
    check("research no llama al LLM si el traspaso está roto",
          llm_calls["n"] == 0 and (out_r.get("metadata") or {}).get("source_pack_ok") is False)
    out_a = asyncio.run(builder.analysis_node(st_h))
    check("analysis no llama al LLM si el traspaso está roto",
          llm_calls["n"] == 0 and (out_a.get("metadata") or {}).get("strategy_pack_ok") is False)
    out_v = asyncio.run(builder.verificador_citas_node({**st_h, "draft": "x"}))
    check("verificador no llama al LLM si el traspaso está roto",
          llm_calls["n"] == 0 and (out_v.get("metadata") or {}).get("stage") == "verificador_citas")

    from mia.agents.graph import _route_after_facts, _route_after_hitl
    check("el grafo desvía facts rotos a abort (sin research/draft/gate)",
          _route_after_facts({"metadata": broken}) == "abort"
          and _route_after_facts({"metadata": {}}) == "research")
    check("HITL re-draft único solo con needs_selection_redraft",
          _route_after_hitl({"metadata": {"needs_selection_redraft": True}}) == "draft"
          and _route_after_hitl({"metadata": {}}) == "finalize")

    captured = {}

    async def capture_llm(messages, **_k):
        captured["user"] = messages[1]["content"]
        return "BORRADOR", {}

    async def no_playbooks(_state, _diag):
        return "", "", []

    import mia.agents.graph as graph_mod
    saved_pb = graph_mod._prepare_playbooks
    graph_mod._prepare_playbooks = no_playbooks
    builder._llm = capture_llm
    md_ok = packs.example_metadata_packs()
    md_ok["diagnosis"] = "Procede la caducidad."
    md_ok["source_packet"] = packs.render_distilled_packet(
        source_pack=packs.SourcePack.model_validate(md_ok["source_pack"]))
    md_ok["research"] = "DUMP ENORME DE MEMORIA DE INVESTIGACIÓN " * 50
    try:
        out_d = asyncio.run(builder.draft_node({
            "tenant_id": "00000000-0000-0000-0000-000000000001",
            "matter_id": "00000000-0000-0000-0000-000000000002",
            "messages": [{"role": "user", "content": "¿operó la caducidad?"}],
            "documents": [{"id": "d1", "content": "x", "document_id": "d1"}],
            "knowledge": [],
            "profile_snapshot": {"despacho": "X"},
            "metadata": md_ok,
        }))
    finally:
        graph_mod._prepare_playbooks = saved_pb
    user_d = captured.get("user") or ""
    check("draft recibe packet (hash) y no el dump de research",
          "hash=" in user_d and "DUMP ENORME" not in user_d
          and "Desarrolla SOLO estos argumentos" in user_d
          and out_d.get("draft") == "BORRADOR")

    from mia.memory import legal_ledger
    draft_txt = "Borrador de prueba para HITL."
    digest = legal_ledger.content_hash(draft_txt)
    md_hitl = packs.example_metadata_packs()
    md_hitl["argument_selection_applied"] = {"include": ["A1"], "exclude": []}
    md_hitl["strategy_pack"]["argumentos"].append({
        "id": "A2", "tesis": "Culpa exclusiva.", "fuente_refs": ["Ley 1"],
        "seleccionado": False, "contraparte": "", "prueba": "[doc 1]",
    })

    def fake_interrupt(_payload):
        return {"decision": "approved", "draft_hash": digest, "attested": True,
                "argument_selection": {"include": ["A2"], "exclude": ["A1"]}}

    saved_interrupt = graph_mod.interrupt
    saved_append = legal_ledger.append_artifact
    saved_record = legal_ledger.record_gate

    async def _ok_art(*_a, **_k):
        return None

    async def _ok_gate(*_a, **_k):
        return None

    graph_mod.interrupt = fake_interrupt
    legal_ledger.append_artifact = _ok_art  # type: ignore[assignment]
    legal_ledger.record_gate = _ok_gate  # type: ignore[assignment]
    try:
        out_h = asyncio.run(builder.hitl_checkpoint_node({
            "tenant_id": "00000000-0000-0000-0000-000000000001",
            "matter_id": "00000000-0000-0000-0000-000000000002",
            "draft": draft_txt,
            "metadata": md_hitl,
            "documents": [],
            "jurisdictions": ["co"],
        }))
    finally:
        graph_mod.interrupt = saved_interrupt
        legal_ledger.append_artifact = saved_append
        legal_ledger.record_gate = saved_record
    check("cambiar la matriz en HITL pide un re-draft autorizado (no aprueba)",
          out_h.get("hitl_status") == "pending"
          and (out_h.get("metadata") or {}).get("needs_selection_redraft") is True
          and (out_h.get("metadata") or {}).get("authorize_expensive_pass") is True)

    if FAILED:
        print("FAIL:", ", ".join(FAILED))
        return 1
    print("PASS: etapas fail-closed y tope por turno.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
