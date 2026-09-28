"""Real PostgreSQL receipts, source invalidation and contextual final history."""
import asyncio
import os
from pathlib import Path
import sys
import unittest
import uuid
import json
from types import SimpleNamespace
from unittest.mock import patch, AsyncMock, Mock

if sys.platform == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

from isolated_test_env import load
load()
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))
import psycopg
from mia.db import pool
from mia.memory import legal_ledger as L
from mia.memory.source_fingerprints import fingerprint
from mia.agents.graph import MatterGraphBuilder
from mia.agents.retrieval import dedupe_chunks
from mia.agents import research
from mia.setup.db_bootstrap import apply_migrations
from mia.api.routes.ux import download_final_docx
from starlette.requests import Request
from fastapi import HTTPException


def admin():
    return psycopg.connect(host=os.environ["PG_HOST"], port=os.environ["PG_PORT"],
                           dbname=os.environ["PG_DB"], user="postgres",
                           password=os.environ["PG_PASSWORD"], autocommit=True)


class ContextTests(unittest.IsolatedAsyncioTestCase):
    def test_isolated_environment_selection(self):
        from isolated_test_env import select
        ci = {"CI": "true", "PG_HOST": "127.0.0.1", "PG_PORT": "55432",
              "PG_DB": "synthetic", "PG_PASSWORD": "synthetic", "PG_APP_PASSWORD": "synthetic"}
        self.assertEqual(select(ci)["PG_PORT"], "55432")
        with self.assertRaises(RuntimeError):
            select({**ci, "CI": "false"})
        with self.assertRaises(RuntimeError):
            select({"GITHUB_ACTIONS": "true", "PG_HOST": "127.0.0.1"})
        with self.assertRaises(RuntimeError):
            select({"MIA_TEST_ENV_FILE": __file__}, lambda path: {"PG_PORT": "55432"})

    def test_first_source_fingerprint_survives_repeated_deduplication(self):
        row = {"id": str(uuid.uuid4()), "document_id": str(uuid.uuid4()), "ord": 0,
               "content": "An authentic original source excerpt.", "filename": "test.txt"}
        first = dedupe_chunks([row])[0]
        original = first["origin_hash"]
        first["content"] = "original source excerpt."
        second = dedupe_chunks([first])[0]
        self.assertEqual(second["origin_hash"], original)
        self.assertNotEqual(second["reviewed_hash"], L.content_hash(row["content"]))

    def test_norm_identity_fields_affect_fingerprint(self):
        row = {"id": str(uuid.uuid4()), "norm_type": "ley", "norm_number": "1",
               "full_text": "Same original bytes", "title": "Synthetic norm", "jurisdiction": "generic"}
        original = fingerprint("legal_norm", row)
        for key, value in [("norm_number","2"),("title","Other norm"),("jurisdiction","other")]:
            self.assertNotEqual(original, fingerprint("legal_norm", {**row,key:value}))

    async def test_complete_receipt_and_live_source_contract(self):
        apply_migrations(os.environ["PG_HOST"], os.environ["PG_PORT"], os.environ["PG_DB"],
                         os.environ["PG_PASSWORD"], [ROOT / "backend/mia/db/migrations/067_legal_final_context.sql"])
        with admin() as conn:
            tid = str(conn.execute("INSERT INTO tenants(name) VALUES('LEGAL_CONTEXT_TEST') RETURNING id").fetchone()[0])
            other = str(conn.execute("INSERT INTO tenants(name) VALUES('LEGAL_CONTEXT_OTHER') RETURNING id").fetchone()[0])
            mid = str(conn.execute("INSERT INTO matters(tenant_id,title) VALUES(%s,'Synthetic evidence') RETURNING id", (tid,)).fetchone()[0])
            doc = str(conn.execute("INSERT INTO documents(tenant_id,matter_id,filename) VALUES(%s,%s,'synthetic.txt') RETURNING id", (tid,mid)).fetchone()[0])
            sid = str(conn.execute("INSERT INTO chunks(tenant_id,document_id,ord,content) VALUES(%s,%s,0,'The authentic source') RETURNING id", (tid,doc)).fetchone()[0])
            norm_id = str(conn.execute("INSERT INTO legal_norms(norm_type,norm_number,issuing_body,title,summary,full_text,effective_date,jurisdiction) "
                "VALUES('ley',%s,'Synthetic tests','Synthetic primary norm','Paraphrased summary','The authentic normative rule.', '2026-01-01','generic') RETURNING id",
                (uuid.uuid4().hex,)).fetchone()[0])
        await pool.open_pool()
        try:
            text = "Exact reviewed human wording."
            source = {"source_kind": "chunk", "source_id": sid, "id": sid, "document_id": doc,
                      "ord": 0, "filename": "synthetic.txt", "folio_ancla": None,
                      "content": "The authentic source"}
            source["origin_hash"] = fingerprint("chunk", source)
            # Integrated productive path: real textual gate, HITL and final ledger.
            builder = object.__new__(MatterGraphBuilder)
            builder.trace_capture = SimpleNamespace(capture=Mock(return_value=SimpleNamespace(timestamp="synthetic")))
            async def auditor(messages, **kwargs):
                requested, _ = json.JSONDecoder().raw_decode(messages[1]["content"].split("Cobertura solicitada:\n",1)[1])
                return json.dumps({"veredicto":"APTO", "impacto_global":False,
                    "unidades":[{"id":uid,"apto":True,"dependencias_unidades":[],
                        "dependencias_fuentes":["[doc 1]"],"alcance":"global"}
                        for uid in requested["revisar"]]}), {}
            builder._llm = auditor
            state = {"tenant_id":tid,"matter_id":mid,"draft":"The authentic source [doc 1].",
                     "jurisdictions":["generic"],"documents":[source],"metadata":{},"messages":[]}
            with (patch("mia.agents.graph.turn_budget.authorize_expensive"),
                  patch("mia.agents.graph.turn_budget.record_expensive_call"),
                  patch("mia.agents.graph.matter_handoff.save_handoff", AsyncMock()),
                  patch("mia.agents.graph.trace_search.index_trace", AsyncMock()),
                  patch("mia.agents.graph.enqueue_learning_job", AsyncMock(return_value=("synthetic",True,"queued")))):
                state.update(await builder.verificador_citas_node(state))
                self.assertTrue(L.verification_passes(state["metadata"]["verification"]))
                human = "  The authentic source [doc 1].\n\nHuman wording preserved.  "
                with patch("mia.agents.graph.interrupt", return_value={"decision":"editing",
                           "draft_hash":L.content_hash(state["draft"]),"attested":True,"edited_text":human}):
                    state.update(await builder.hitl_checkpoint_node(state))
                state.update(await builder.finalize_node(state))
            self.assertTrue(state["metadata"]["final_ready"])
            self.assertEqual(state["draft"],human)
            self.assertEqual((await L.validated_latest_final(tid,mid))["content"],human)
            integrated_request = Request({"type":"http","method":"GET","path":"/",
                                          "headers":[],"state":{"tenant_id":tid}})
            self.assertTrue((await download_final_docx(mid,integrated_request)).body.startswith(b"PK"))
            with admin() as conn:
                conn.execute("UPDATE chunks SET content='Mutated source' WHERE id=%s",(sid,))
            with self.assertRaises(HTTPException) as stale:
                await download_final_docx(mid,integrated_request)
            self.assertEqual(stale.exception.status_code,409)
            with admin() as conn:
                conn.execute("UPDATE chunks SET content='The authentic source' WHERE id=%s",(sid,))
                from psycopg.rows import dict_row
                norm = conn.execute("SELECT * FROM legal_norms WHERE id=%s",(norm_id,)).fetchone()
                columns = [d.name for d in conn.execute("SELECT * FROM legal_norms LIMIT 0").description]
                norm = dict(zip(columns,norm))
            sat = AsyncMock()
            sat.search_norms.return_value = [norm]
            sat.search_jurisprudence.return_value = [{"id":str(uuid.uuid4()),"court":"Synthetic court","radicado":"77","ratio_decidendi":"Unrelated derived judgment"}]
            with patch.object(research,"SATGraph",return_value=sat):
                _, norm_sources, _ = await research.gather_sources(tid,"synthetic",jurisdictions=["generic"])
            self.assertEqual(norm_sources[1]["content"],"Unrelated derived judgment")
            async def norm_auditor(messages,**kwargs):
                requested,_ = json.JSONDecoder().raw_decode(messages[1]["content"].split("Cobertura solicitada:\n",1)[1])
                return json.dumps({"veredicto":"APTO","impacto_global":False,
                    "fuentes_no_utilizadas":[{"locator":f"jurisprudence:{norm_sources[1]['source_id']}","motivo":"No assertion depends on this summary"}],
                    "unidades":[{"id":uid,"apto":True,"dependencias_unidades":[],
                        "dependencias_fuentes":["[doc 1]"],"alcance":"global"} for uid in requested["revisar"]]}),{}
            builder._llm = norm_auditor
            norm_state = {"tenant_id":tid,"matter_id":mid,"draft":f"Conforme a {norm_sources[0]['referencia']} [doc 1], the authentic normative rule.",
                "jurisdictions":["generic"],"documents":[source],"metadata":{"research_sources":norm_sources},"messages":[]}
            with (patch("mia.agents.graph.turn_budget.authorize_expensive"),
                  patch("mia.agents.graph.turn_budget.record_expensive_call"),
                  patch("mia.agents.graph.matter_handoff.save_handoff",AsyncMock()),
                  patch("mia.agents.graph.trace_search.index_trace",AsyncMock()),
                  patch("mia.agents.graph.enqueue_learning_job",AsyncMock(return_value=("synthetic",True,"queued")))):
                norm_state.update(await builder.verificador_citas_node(norm_state))
                self.assertEqual(norm_state["metadata"]["verification"]["gate_llm"]["veredicto"],"apto")
                with patch("mia.agents.graph.interrupt",return_value={"decision":"approved",
                           "draft_hash":L.content_hash(norm_state["draft"]),"attested":True}):
                    norm_state.update(await builder.hitl_checkpoint_node(norm_state))
                norm_state.update(await builder.finalize_node(norm_state))
            self.assertTrue(norm_state["metadata"]["final_ready"])
            selected_context=(await L.validated_latest_final(tid,mid))["metadata"]["verification_context"]
            self.assertEqual({s["id"] for s in selected_context["sources"]},{norm_id,sid})
            self.assertTrue((await download_final_docx(mid,integrated_request)).body.startswith(b"PK"))
            with admin() as conn:
                conn.execute("UPDATE legal_norms SET full_text='Changed normative original' WHERE id=%s",(norm_id,))
            with self.assertRaises(HTTPException) as changed_original:
                await download_final_docx(mid,integrated_request)
            self.assertEqual(changed_original.exception.status_code,409)
            with admin() as conn:
                conn.execute("UPDATE legal_norms SET full_text='The authentic normative rule.' WHERE id=%s",(norm_id,))
            self.assertTrue((await download_final_docx(mid,integrated_request)).body.startswith(b"PK"))
            with admin() as conn:
                conn.execute("UPDATE legal_norms SET norm_number='changed identity' WHERE id=%s",(norm_id,))
            with self.assertRaises(HTTPException) as invalid_norm:
                await download_final_docx(mid,integrated_request)
            self.assertEqual(invalid_norm.exception.status_code,409)
            ctx = L.make_context(str(uuid.uuid4()), ["generic"], [], [source])
            for _ in range(2):
                await L.record_gate(tid,mid,L.content_hash(text),gate="citation_verification",passed=True,
                    checker_version=L.CHECKER_VERSIONS["citation_verification"],verification_context=ctx,
                    trace_id="same-stable-pass")
            with admin() as conn:
                count = conn.execute("SELECT count(*) FROM legal_gate_receipts WHERE matter_id=%s AND trace_id='same-stable-pass'",(mid,)).fetchone()[0]
                self.assertEqual(count,1)
            builder = object.__new__(MatterGraphBuilder)
            report = {"gate_llm": {"veredicto": "apto", "checker_version": "citation-verifier-v3"},
                      "evidence_coverage": {"complete": True}}
            with patch("mia.agents.graph.interrupt", return_value={"decision": "approved", "draft_hash": L.content_hash(text), "attested": True}):
                accepted = await builder.hitl_checkpoint_node({"tenant_id": tid,"matter_id": mid,"draft": text,
                    "jurisdictions": ["generic"],"documents": [source],"metadata": {"verification": report}})
            self.assertEqual(accepted["hitl_status"], "approved")

            async def receipt(gate, context=ctx, passed=True, version=None):
                await L.record_gate(tid, mid, L.content_hash(text), gate=gate, passed=passed,
                                    checker_version=version or L.CHECKER_VERSIONS[gate], verification_context=context, trace_id=str(uuid.uuid4()))
            await receipt("citation_verification")
            wrong = {**ctx, "run_id": str(uuid.uuid4())}
            await receipt("human_approval", wrong)
            self.assertFalse(await L.finalise_if_gated(tid,mid,text,verification_context=ctx))
            await receipt("human_approval")
            self.assertTrue(await L.finalise_if_gated(tid,mid,text,verification_context=ctx))
            final = await L.validated_latest_final(tid,mid)
            self.assertEqual(final["content"], text)
            request = Request({"type": "http", "method": "GET", "path": "/",
                               "headers": [], "state": {"tenant_id": tid}})
            exported = await download_final_docx(mid, request)
            self.assertTrue(exported.body.startswith(b"PK"))
            with admin() as conn:
                conn.execute("UPDATE documents SET filename='changed-locator.txt' WHERE id=%s",(doc,))
            self.assertIsNone(await L.validated_latest_final(tid,mid))
            with admin() as conn:
                conn.execute("UPDATE documents SET filename='synthetic.txt' WHERE id=%s",(doc,))
            self.assertIsNotNone(await L.validated_latest_final(tid,mid))
            self.assertIsNone(await L.validated_latest_final(other,mid))
            await receipt("citation_verification", passed=False)
            self.assertIsNone(await L.validated_latest_final(tid,mid))
            with self.assertRaises(HTTPException) as denied:
                await download_final_docx(mid, request)
            self.assertEqual(denied.exception.status_code, 409)
            await receipt("citation_verification")
            self.assertIsNotNone(await L.validated_latest_final(tid,mid))
            await receipt("citation_verification", passed=False)
            self.assertIsNone(await L.validated_latest_final(tid,mid))
            await receipt("citation_verification")
            with admin() as conn:
                conn.execute("UPDATE chunks SET content='Changed authentic source' WHERE id=%s", (sid,))
            self.assertIsNone(await L.validated_latest_final(tid,mid))
            source.update(content="Changed authentic source")
            source["origin_hash"] = fingerprint("chunk", source)
            new_ctx = L.make_context(str(uuid.uuid4()), ["generic"], [], [source])
            self.assertFalse(await L.finalise_if_gated(tid,mid,text,verification_context=new_ctx))
            await receipt("citation_verification", new_ctx, version="old-verifier")
            await receipt("human_approval",new_ctx)
            self.assertFalse(await L.finalise_if_gated(tid,mid,text,verification_context=new_ctx))
            await receipt("citation_verification",new_ctx)
            self.assertTrue(await L.finalise_if_gated(tid,mid,text,verification_context=new_ctx))
            with admin() as conn:
                count = conn.execute("SELECT count(*) FROM legal_artifact_ledger WHERE matter_id=%s AND artifact_kind='final'", (mid,)).fetchone()[0]
                self.assertEqual(count, 4)
                conn.execute("UPDATE matters SET jurisdictions=%s::jsonb WHERE id=%s",('["other"]',mid))
            self.assertIsNone(await L.validated_latest_final(tid,mid))
            with admin() as conn:
                conn.execute("UPDATE matters SET jurisdictions='[]'::jsonb WHERE id=%s",(mid,))
                conn.execute("DELETE FROM chunks WHERE id=%s",(sid,))
            self.assertIsNone(await L.validated_latest_final(tid,mid))
        finally:
            await pool.close_pool()
            with admin() as conn:
                conn.execute("DELETE FROM tenants WHERE id IN (%s,%s)",(tid,other))
                conn.execute("DELETE FROM legal_norms WHERE id=%s",(norm_id,))


if __name__ == "__main__":
    unittest.main()
