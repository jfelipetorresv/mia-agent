"""Synthetic textual gate coverage, including the old late-source blind spot."""
import asyncio
import json
import copy
import subprocess
import tempfile
from pathlib import Path
import os
import sys
import unittest
from unittest.mock import AsyncMock, patch

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "backend")))
from mia.agents import gate_evidence as E
from mia.agents.graph import MatterGraphBuilder
from mia.agents import research


class EvidenceTests(unittest.IsolatedAsyncioTestCase):
    @unittest.skipUnless(sys.platform == "win32", "PowerShell driver runs on Windows")
    def test_quick_precheck_fails_before_suites_without_isolated_config(self):
        root=Path(__file__).resolve().parents[1]
        env={k:v for k,v in os.environ.items() if not k.startswith("PG_") and k not in ("CI","GITHUB_ACTIONS","MIA_TEST_ENV_FILE")}
        with tempfile.TemporaryDirectory() as folder:
            bad=Path(folder)/"invalid.env"
            bad.write_text("PG_PORT=55432\n",encoding="utf-8")
            for path in [None,str(Path(folder)/"absent.env"),str(bad)]:
                current=dict(env)
                if path: current["MIA_TEST_ENV_FILE"]=path
                result=subprocess.run(["powershell","-NoProfile","-File",str(root/"scripts/verify.ps1"),"-Mode","quick"],
                    cwd=root,env=current,capture_output=True,text=True,timeout=30)
                self.assertEqual(result.returncode,2)
                self.assertIn("PRECHECK",result.stdout+result.stderr)
                self.assertNotIn("===",result.stdout)
    async def test_gather_primary_and_unused_derived_are_audited_once(self):
        norm = {"id":"synthetic", "norm_type":"ley", "norm_number":"1", "title":"Primary", "effective_date":"2026-01-01",
                "full_text":"La reparación procede.","summary":"Paráfrasis totalmente distinta."}
        sat = AsyncMock()
        sat.search_norms.return_value = [norm]
        sat.search_jurisprudence.return_value = [{"id":"derived", "court":"Corte", "radicado":"77",
                                                 "ratio_decidendi":"Resumen ajeno"}]
        with patch.object(research,"SATGraph",return_value=sat):
            _, sources, _ = await research.gather_sources("tenant","query",jurisdictions=["generic"])
        self.assertEqual(sources[0]["pasaje"],norm["full_text"])
        self.assertEqual(sources[0]["summary"],norm["summary"])
        self.assertEqual(sources[1]["content"],"Resumen ajeno")
        from mia.agents import barreras_harness as B
        coverage = B.revisar_fuentes([sources[0]], exigir=True)
        self.assertEqual(coverage["pasaje_no_coincide"],[])
        self.assertEqual(B.filtrar_fuentes([sources[0]],coverage),[sources[0]])
        builder = object.__new__(MatterGraphBuilder)
        async def audit(messages,**kwargs):
            requested,_ = json.JSONDecoder().raw_decode(messages[1]["content"].split("Cobertura solicitada:\n",1)[1])
            available = "legal_norm:synthetic"
            return json.dumps({"veredicto":"APTO","impacto_global":False,
                "fuentes_no_utilizadas":[{"locator":"jurisprudence:derived","motivo":"Ninguna afirmación depende de este resumen"}],
                "unidades":[{"id":uid,"apto":True,"dependencias_unidades":[],
                    "dependencias_fuentes":[available],"alcance":"global"} for uid in requested["revisar"]]}),{}
        builder._llm = AsyncMock(side_effect=audit)
        md={"research_sources":sources}
        report={"fuentes":{"aviso":"Aviso anterior de cobertura"}}
        with patch("mia.agents.graph.turn_budget.authorize_expensive"), patch("mia.agents.graph.turn_budget.record_expensive_call"), patch("mia.agents.graph._accum_usage"):
            await builder._audit_textual_evidence({},md,"La reparación procede.",report)
        self.assertEqual(report["gate_llm"]["veredicto"],"apto")
        self.assertEqual(md["audited_evidence_selection"]["sources"],[sources[0]])
        self.assertEqual(report["evidence_coverage"]["scope"],"audited_dependencies")
        self.assertIn("Aviso anterior de cobertura",report["fuentes"]["aviso"])
        # A separate explicit citation cannot silently drop the derived inventory.
        cited={"citas":1,"detalle":[{"cita":sources[0]["referencia"]}]}
        with patch("mia.agents.graph.turn_budget.authorize_expensive"), patch("mia.agents.graph.turn_budget.record_expensive_call"), patch("mia.agents.graph._accum_usage"):
            await builder._audit_textual_evidence({},md,"Conforme a " + sources[0]["referencia"] + ", procede. La jurisprudencia lo admite.",cited)
        self.assertEqual(cited["gate_llm"]["veredicto"],"apto")
        self.assertEqual(len(cited["evidence_coverage"]["exclusions"]),1)
        # Explicitly citing the derived judgment prevents exclusion.
        denied={}
        with patch("mia.agents.graph.turn_budget.authorize_expensive"):
            await builder._audit_textual_evidence({},md,sources[1]["referencia"],denied)
        self.assertEqual(denied["gate_llm"]["veredicto"],"unavailable")
        # Declaring a semantic dependency on unavailable material rejects approval.
        async def dependent(messages,**kwargs):
            raw,_ = await audit(messages,**kwargs)
            parsed = json.loads(raw)
            parsed["unidades"][0]["dependencias_fuentes"] = ["jurisprudence:derived"]
            return json.dumps(parsed),{}
        builder._llm = dependent
        failure = {}
        with patch("mia.agents.graph.turn_budget.authorize_expensive"), patch("mia.agents.graph.turn_budget.record_expensive_call"), patch("mia.agents.graph._accum_usage"):
            await builder._audit_textual_evidence({},md,"Uncited assertion depends on the missing judgment.",failure)
        self.assertEqual(failure["gate_llm"]["veredicto"],"hallazgos")
        self.assertNotIn("audited_evidence_selection",md)

    def test_doc_backed_citation_does_not_drag_unused_derived(self):
        sources = [{"referencia":"Sentencia 77", "evidence_kind":"derived_ratio","content":"Summary"}]
        docs = [{"content":"Ley 1 de 2020 original", "filename":"original.txt"}]
        selected, documents = E.select_used("Ley 1 de 2020 [doc 1]", sources, docs,
            {"citas":1,"detalle":[{"cita":"Ley 1 de 2020",
                "fuente":{"tipo":"expediente","referencia":"[doc 1]"}}]})
        self.assertEqual(selected,sources)
        coverage=E.build(selected,documents,budget_tokens=1000,text="Ley 1 de 2020 [doc 1]",
            report={"citas":1,"detalle":[{"cita":"Ley 1 de 2020","fuente":{"tipo":"expediente","referencia":"[doc 1]"}}]})
        self.assertTrue(coverage["complete"])
        self.assertEqual(len(coverage["exclusion_candidates"]),1)

    async def test_sealed_old_anchor_is_not_a_current_dependency(self):
        docs=[{"id":"original","content":"Ley 1 de 2020 supports the claim."},
              {"id":"other","content":"Other original"},{"id":"wrong","content":"The claim is false."}]
        report={"citas":1,"detalle":[{"cita":"Ley 1 de 2020","estado":"sellada",
            "fuente":{"tipo":"expediente","referencia":"[doc 3]"}}]}
        self.assertEqual(E.select_used("Ley 1 de 2020",[],docs,report)[1],docs)
        builder=object.__new__(MatterGraphBuilder)
        async def auditor(messages,**kwargs):
            evidence,_=json.JSONDecoder().raw_decode(messages[1]["content"].split("Evidencia textual original con identidad, localizador y huella (JSON):\n",1)[1])
            self.assertEqual(len(evidence),3)
            return json.dumps({"veredicto":"APTO","impacto_global":False,"unidades":[{"id":"p1","apto":True,
                "dependencias_unidades":[],"dependencias_fuentes":["[doc 1]"],"alcance":"global"}]}),{}
        builder._llm=auditor
        md={}
        with patch("mia.agents.graph.turn_budget.authorize_expensive"),patch("mia.agents.graph.turn_budget.record_expensive_call"),patch("mia.agents.graph._accum_usage"):
            await builder._audit_textual_evidence({"documents":docs},md,"Ley 1 de 2020",report)
        self.assertEqual(md["audited_evidence_selection"]["documents"],[docs[0]])

    async def test_lost_invalid_or_changed_provenance_selection_triggers_full_review(self):
        builder=object.__new__(MatterGraphBuilder)
        builder._llm=AsyncMock(return_value=(json.dumps({"veredicto":"APTO","impacto_global":False,
            "unidades":[{"id":"p1","apto":True,"dependencias_unidades":[],"dependencias_fuentes":["research_sources[1]"],"alcance":"local"}]}),{}))
        md={"research_sources":[{"referencia":"Primary","content":"Original","origin_hash":"a"*64}]}
        state={"tenant_id":"tenant","matter_id":"matter"}
        with patch("mia.agents.graph.turn_budget.authorize_expensive"),patch("mia.agents.graph.turn_budget.record_expensive_call"),patch("mia.agents.graph._accum_usage"):
            await builder._audit_textual_evidence(state,md,"Claim",{})
            md.pop("audited_evidence_selection")
            await builder._audit_textual_evidence(state,md,"Claim",{})
            self.assertEqual(builder._llm.await_count,2)
            md["audited_evidence_selection"]["sources"][0]["origin_hash"]="bad"
            await builder._audit_textual_evidence(state,md,"Claim",{})
            self.assertEqual(builder._llm.await_count,3)
            md["research_sources"][0]["origin_hash"]="b"*64
            report={}
            await builder._audit_textual_evidence(state,md,"Claim",report)
            self.assertEqual(builder._llm.await_count,4)
            self.assertTrue(report["unit_coverage"]["full"])

    def test_custom_pattern_derived_remains_required(self):
        source = {"referencia":"NormaX 22 de 2021", "content":"Derived", "evidence_kind":"derived_summary"}
        report = {"citas":1,"detalle":[{"cita":"artículo 3 NormaX 22"}]}
        selected, docs = E.select_used("artículo 3 NormaX 22",[source],[],report)
        result = E.build(selected,docs,budget_tokens=1000,text="artículo 3 NormaX 22",report=report)
        self.assertFalse(result["complete"])
        self.assertEqual(result["exclusion_candidates"],[])

    async def test_same_reference_different_ids_preserves_exact_dependency(self):
        sources = [{"referencia":"Same law", "source_kind":"legal_norm", "source_id":key,
                    "content":"Authentic primary"} for key in ("one","two")]
        builder = object.__new__(MatterGraphBuilder)
        builder._llm = AsyncMock(return_value=(json.dumps({"veredicto":"APTO","impacto_global":False,
            "unidades":[{"id":"p1","apto":True,"dependencias_unidades":[],
                "dependencias_fuentes":["legal_norm:one"],"alcance":"global"}]}),{}))
        md={"research_sources":sources}
        with patch("mia.agents.graph.turn_budget.authorize_expensive"), patch("mia.agents.graph.turn_budget.record_expensive_call"), patch("mia.agents.graph._accum_usage"):
            await builder._audit_textual_evidence({},md,"Synthetic supported assertion.",{})
        self.assertEqual(md["audited_evidence_selection"]["sources"],[sources[0]])

    async def test_turn_budget_keeps_specific_reason(self):
        from mia.policy.turn_budget import TurnBudgetExceeded
        builder = object.__new__(MatterGraphBuilder)
        builder._llm = AsyncMock()
        report={}
        with patch("mia.agents.graph.turn_budget.authorize_expensive",side_effect=TurnBudgetExceeded("Segunda pasada requiere autorización")):
            await builder._audit_textual_evidence({}, {"research_sources":[{"referencia":"Law","content":"Original"}]},"Claim",report)
        self.assertEqual(report["gate_llm"]["detalle"],"Segunda pasada requiere autorización")
        builder._llm.assert_not_awaited()

    def test_selection_fingerprint_rejects_content_identity_locator_mutations(self):
        source={"referencia":"Primary","source_id":"one","locator":"page 1",
                "origin_hash":"a"*64,"content":"Original"}
        selection={"text_hash":E.digest("Claim"),"manifest_hash":"b"*64,
                   "sources":[source],"documents":[]}
        selection["selection_hash"]=E.selection_hash(selection["sources"],[])
        self.assertEqual(E.reviewed_selection("Claim",{"audited_evidence_selection":selection},[]),([source],[]))
        for key,value in [("content","Changed"),("source_id","other"),("locator","page 2"),("origin_hash","c"*64)]:
            changed=copy.deepcopy(selection)
            changed["sources"][0][key]=value
            self.assertEqual(E.reviewed_selection("Claim",{"audited_evidence_selection":changed},[]),([],[]))
    def test_original_required(self):
        missing = E.build([{"referencia": "Ley 1", "pasaje": "title", "chunk_hash": "a"*64}], [], budget_tokens=1000)
        self.assertFalse(missing["complete"])
        self.assertEqual(missing["missing"], ["Ley 1"])
        too_long = E.build([{"referencia": "Ley 1", "content": "x"*9000}], [], budget_tokens=10)
        self.assertTrue(too_long["over_budget"])
        self.assertFalse(too_long["complete"])
        self.assertEqual(too_long["payload"], "")

    def test_out_of_range_anchor_has_missing_coverage(self):
        sources, docs = E.select_used("Claim [doc 5].", [], [{"content":"Original"}])
        report = E.build(sources, docs, budget_tokens=1000)
        self.assertFalse(report["complete"])
        self.assertIn("[doc 5]", report["missing"])

    async def test_gate_catches_contrary_late_source(self):
        builder = object.__new__(MatterGraphBuilder)
        sources = [{"referencia": "Ley 1", "content": "Neutral "*650},
                   {"referencia": "Ley 2", "content": "La reparación NO procede en este caso."}]
        md = {"research_sources": sources}
        report = {"citas": 2, "selladas": 2}
        async def reviewer(messages, **kwargs):
            content = messages[-1]["content"]
            self.assertIn("La reparación NO procede", content)
            self.assertGreater(content.index("La reparación NO procede"), 4000)
            return "HALLAZGOS: la fuente contradice la tesis.", {}
        builder._llm = reviewer
        with patch("mia.agents.graph.turn_budget.authorize_expensive"), patch("mia.agents.graph.turn_budget.record_expensive_call"), patch("mia.agents.graph._accum_usage"):
            await builder._audit_textual_evidence({"documents": []}, md, "La reparación procede según Ley 1 y Ley 2.", report)
        self.assertEqual(report["gate_llm"]["veredicto"], "hallazgos")
        self.assertTrue(report["evidence_coverage"]["complete"])

    async def test_missing_original_does_not_call_reviewer(self):
        builder = object.__new__(MatterGraphBuilder)
        builder._llm = AsyncMock(return_value=("APTO", {}))
        report = {}
        await builder._audit_textual_evidence({}, {"research_sources": [{"referencia": "Ley 1"}]}, "Tesis", report)
        builder._llm.assert_not_called()
        self.assertEqual(report["gate_llm"]["veredicto"], "unavailable")

    async def test_positive_textual_review(self):
        builder = object.__new__(MatterGraphBuilder)
        builder._llm = AsyncMock(return_value=(' {"veredicto":"APTO","impacto_global":false,"unidades":[{"id":"p1","apto":true,"dependencias_unidades":[],"dependencias_fuentes":["research_sources[1]"],"alcance":"local"}]}', {}))
        report = {}
        with patch("mia.agents.graph.turn_budget.authorize_expensive"), patch("mia.agents.graph.turn_budget.record_expensive_call"), patch("mia.agents.graph._accum_usage"):
            await builder._audit_textual_evidence({}, {"research_sources": [{"referencia": "Ley 1", "content": "La reparación procede."}]}, "La reparación procede.", report, authorized=True)
        self.assertEqual(report["gate_llm"]["veredicto"], "apto")

    async def test_sealed_identity_still_calls_textual_gate(self):
        builder = object.__new__(MatterGraphBuilder)
        report = {"citas": 1, "selladas": 1}
        async def wall(state, md, text):
            md["verification"] = report
            return text
        builder._verify_draft = wall
        builder._audit_textual_evidence = AsyncMock()
        out = await builder.verificador_citas_node({"draft": "Ley 1", "metadata": {}})
        builder._audit_textual_evidence.assert_awaited_once()
        self.assertEqual(out["draft"], "Ley 1")

    def test_derived_material_cannot_cover_primary_source(self):
        result = E.build([{"referencia": "Ley 1", "content": "Resumen auténtico",
                           "evidence_kind": "derived_summary"}], [], budget_tokens=1000)
        self.assertFalse(result["complete"])
        self.assertEqual(result["scope"], "received_material")

    def test_custom_citations_and_plural_doc_anchors_preserved(self):
        sources = [{"referencia": "Ley 1"}, {"referencia": "NormaX 22"}]
        docs = [{"content": "a"}, {"content": "b"}, {"content": "c"}]
        used, selected = E.select_used("Ley 1 y NormaX 22 [doc 1] [docs 2,3]", sources, docs,
            {"citas": 2, "detalle": [{"cita": "Ley 1"}, {"cita": "NormaX 22"}]})
        self.assertEqual(used, sources)
        self.assertEqual([d["gate_locator"] for d in selected], ["[doc 1]", "[doc 2]", "[doc 3]"])

    async def test_malformed_apto_does_not_approve(self):
        builder = object.__new__(MatterGraphBuilder)
        builder._llm = AsyncMock(return_value=("APTO\n{bad JSON}", {}))
        report = {}
        with patch("mia.agents.graph.turn_budget.authorize_expensive"), patch("mia.agents.graph.turn_budget.record_expensive_call"), patch("mia.agents.graph._accum_usage"):
            await builder._audit_textual_evidence({}, {"research_sources": [{"referencia": "Ley 1", "content": "Regla"}]}, "Tesis", report)
        self.assertNotEqual(report["gate_llm"]["veredicto"], "apto")


if __name__ == "__main__":
    unittest.main()
