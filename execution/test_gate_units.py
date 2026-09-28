"""Dependencies must invalidate audited units; identities alone never approve."""
import json
import os
import sys
import unittest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "backend")))
from mia.agents import gate_units as U

_original_plan = U.plan
def scoped_plan(*args, **kwargs):
    return _original_plan(*args, tenant_id="tenant", matter_id="matter", **kwargs)


class UnitsTests(unittest.TestCase):
    def setUp(self):
        self.a = "Primer párrafo suficientemente largo con una tesis sintética y su justificación local."
        self.b = "Segundo párrafo suficientemente largo con una conclusión sintética dependiente del primero."
        self.text = self.a + "\n\n" + self.b
        self.evidence = {"manifest_hash": "sourcehash"}
        self.plan = scoped_plan(self.text, self.evidence, ["generic"], None)
        self.rows = [{"id": "p1", "apto": True, "dependencias_unidades": [], "dependencias_fuentes": ["source:1"], "alcance": "local"},
                     {"id": "p2", "apto": True, "dependencias_unidades": ["p1"], "dependencias_fuentes": [], "alcance": "local"}]
        ok, self.receipt = U.accept(json.dumps({"veredicto": "APTO", "impacto_global": False, "unidades": self.rows}), self.plan, {"source:1"})
        self.assertTrue(ok)

    def test_identical_and_dependent_delta(self):
        self.assertEqual(scoped_plan(self.text, self.evidence, ["generic"], self.receipt)["pending"], [])
        changed = scoped_plan(self.text.replace("Primer", "Nuevo primer"), self.evidence, ["generic"], self.receipt)
        self.assertEqual(changed["pending"], ["p1", "p2"])
        self.assertFalse(changed["full"])
        local = scoped_plan(self.a + "\n\n" + self.b.replace("Segundo", "Nuevo segundo"), self.evidence, ["generic"], self.receipt)
        self.assertEqual(local["pending"], ["p2"])
        self.assertEqual(len(local["inherited"]), 1)

    def test_only_complete_json_fence_is_tolerated(self):
        raw = json.dumps({"veredicto":"APTO", "impacto_global":False, "unidades":self.rows})
        self.assertTrue(U.accept("```json\n" + raw + "\n```", self.plan, {"source:1"})[0])
        for invalid in [None, 42, "Explanation\n"+raw, "```json\n"+raw+"\n```\nextra", "APTO\n"+raw]:
            self.assertFalse(U.accept(invalid,self.plan,{"source:1"})[0])

    def test_source_jurisdiction_structure_invalidate(self):
        for text, evidence, jurisdictions in [(self.text, {"manifest_hash": "changed"}, ["generic"]),
                                               (self.text, self.evidence, ["other"]),
                                               (self.a, self.evidence, ["generic"]),
                                               (self.b + "\n\n" + self.a, self.evidence, ["generic"])]:
            self.assertTrue(scoped_plan(text, evidence, jurisdictions, self.receipt)["full"])

    def test_absent_invalid_dependencies_never_create_receipts(self):
        for rows in [self.rows[:1], [dict(self.rows[0], dependencias_fuentes=["unknown"]), self.rows[1]],
                     [dict(self.rows[0], dependencias_unidades=None), self.rows[1]]]:
            self.assertFalse(U.accept(json.dumps({"veredicto": "APTO", "impacto_global": False, "unidades": rows}), self.plan, {"source:1"})[0])
        self.assertFalse(U.accept("APTO", self.plan, {"source:1"})[0])

    def test_global_impact_blocks_incremental(self):
        current = scoped_plan(self.a + "\n\n" + self.b.replace("Segundo", "Nuevo segundo"), self.evidence, ["generic"], self.receipt)
        response = json.dumps({"veredicto": "APTO", "impacto_global": True, "unidades": [self.rows[1]]})
        self.assertFalse(U.accept(response, current, {"source:1"})[0])
        inconsistent = json.dumps({"veredicto": "APTO", "impacto_global": False,
                                   "unidades": [dict(self.rows[1], alcance="global")]})
        self.assertFalse(U.accept(inconsistent, current, {"source:1"})[0])
        ok, receipt = U.accept(json.dumps({"veredicto": "APTO", "impacto_global": True,
                                           "unidades": self.rows}), self.plan, {"source:1"})
        self.assertTrue(ok)
        self.assertTrue(all(r["scope"] == "global" for r in receipt["units"]))
        self.assertTrue(scoped_plan(self.text.replace("Primer", "Nuevo primer"), self.evidence,
                                   ["generic"], receipt)["full"])

    def test_different_tenant_or_matter_cannot_inherit(self):
        for tenant, matter in [("other", "matter"), ("tenant", "other")]:
            p = _original_plan(self.text, self.evidence, ["generic"], self.receipt,
                               tenant_id=tenant, matter_id=matter)
            self.assertEqual(p["pending"], ["p1", "p2"])
            self.assertEqual(p["inherited"], [])


if __name__ == "__main__":
    unittest.main()
