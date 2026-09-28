"""El recibo HITL representa el checkpoint, con dobles sin DB ni proveedores."""
from __future__ import annotations

from contextlib import asynccontextmanager
import json
from pathlib import Path
import sys
from types import SimpleNamespace
import unittest
from unittest.mock import AsyncMock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))
from mia.api.routes import hitl  # noqa: E402


class ResumeStateTests(unittest.IsolatedAsyncioTestCase):
    async def receipt(self, decision, *, status=None, ready=False, pending=False, fail=False):
        report = {"gate_llm": {"veredicto": "apto", "checker_version":
                  hitl.legal_ledger.CHECKER_VERSIONS["citation_verification"]},
                  "evidence_coverage": {"complete": True}, "citas": 0}
        snapshot = SimpleNamespace(
            next=("hitl_checkpoint",) if pending else (),
            values={"draft": "Versión persistida nueva", "metadata": {
                "final_status": status, "final_ready": ready, "verification": report}},
        )

        class Graph:
            async def astream(self, *args, **kwargs):
                if fail:
                    raise RuntimeError("fallo sintético")
                # Las actualizaciones transitorias no autorizan el recibo final.
                yield {"draft": {"draft": "texto transitorio"}}

            async def aget_state(self, *args):
                return snapshot

        db_write = AsyncMock()

        @asynccontextmanager
        async def cp():
            yield None

        @asynccontextmanager
        async def conn(*args):
            yield SimpleNamespace(execute=db_write)

        command = {"decision": decision, "draft_hash": "a" * 64, "attested": True}
        if pending:
            command["argument_selection"] = {"include": ["A2"], "exclude": ["A1"]}
        with (patch.object(hitl, "open_checkpointer", cp),
              patch.object(hitl, "build_matter_graph", lambda cp: Graph()),
              patch.object(hitl, "assert_owns_matter", AsyncMock()),
              patch.object(hitl, "require_awaiting_review", AsyncMock()),
              patch.object(hitl, "_require_current_draft_hash", AsyncMock(return_value=snapshot)),
              patch.object(hitl.pool, "tenant_connection", conn)):
            response = await hitl._resume(
                SimpleNamespace(state=SimpleNamespace(tenant_id="synthetic-tenant")),
                "synthetic-matter", command)
            events = [event async for event in response.body_iterator]
        return events, db_write

    async def test_terminal_decisions_use_persisted_state(self):
        for decision in ("approved", "editing", "rejected"):
            with self.subTest(decision=decision):
                ready = decision != "rejected"
                events, write = await self.receipt(decision, status=decision, ready=ready)
                done = json.loads(events[-1]["data"])
                self.assertEqual(done["status"], decision)
                self.assertEqual(done["draft"], "Versión persistida nueva")
                self.assertEqual(done["final_ready"], ready)
                self.assertFalse(done["awaiting_review"])
                self.assertFalse(write.call_args.args[1][0])

    async def test_selection_returns_new_review_and_hash(self):
        events, write = await self.receipt("approved", pending=True)
        self.assertEqual(events[-1]["event"], "done")
        done = json.loads(events[-1]["data"])
        self.assertEqual(done["status"], "awaiting_review")
        self.assertEqual(done["final_status"], "awaiting_review")
        self.assertTrue(done["awaiting_review"])
        self.assertFalse(done["final_ready"])
        self.assertEqual(done["draft"], "Versión persistida nueva")
        self.assertEqual(done["draft_hash"], hitl.legal_ledger.content_hash(done["draft"]))
        self.assertEqual(done["verification"]["gate_llm"]["veredicto"], "apto")
        self.assertTrue(write.call_args.args[1][0])

    async def test_missing_final_evidence_never_reports_approved(self):
        for status in (None, "approved", "verification_required"):
            events, _ = await self.receipt("approved", status=status)
            done = json.loads(events[-1]["data"])
            self.assertEqual(done["status"], "verification_required")
            self.assertFalse(done["final_ready"])

    async def test_failure_never_emits_completion(self):
        with self.assertLogs("mia.api.stream", level="ERROR"):
            events, write = await self.receipt("approved", fail=True)
        self.assertEqual(events[-1]["event"], "error")
        self.assertNotIn("done", [event["event"] for event in events])
        write.assert_not_awaited()


if __name__ == "__main__":
    unittest.main()
