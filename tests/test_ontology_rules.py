from __future__ import annotations

import json
import unittest
from pathlib import Path

from ethmac_v9.ontology import Fact, KnowledgeGraph
from ethmac_v9.rule_engine import DefeasibleRuleEngine
from test_agent import sample_state

ROOT = Path(__file__).resolve().parents[1]


class OntologyTests(unittest.TestCase):
    def test_evidence_visibility_and_provenance(self) -> None:
        graph = KnowledgeGraph()
        graph.add_evidence("E1", "PolicyEvent", 2, "policy://P1", "official", 4)
        self.assertEqual(graph.visible_evidence_ids(1), [])
        self.assertEqual(graph.visible_evidence_ids(2), ["E1"])
        self.assertEqual(graph.evidence_provenance("E1", 3)["source_channel"], "official")
        self.assertEqual(graph.visible_evidence_ids(5), [])

    def test_evidence_requires_provenance(self) -> None:
        graph = KnowledgeGraph()
        with self.assertRaises(ValueError):
            graph.add(Fact("E1", "hasProvenance", "", provenance=""))

    def test_ttl_and_shapes_have_required_contracts(self) -> None:
        ontology = (ROOT / "ontology/ethmac_v9.ttl").read_text(encoding="utf-8")
        shapes = (ROOT / "ontology/ethmac_v9_shapes.ttl").read_text(encoding="utf-8")
        for token in ("eh:Household", "eh:Evidence", "eh:PolicyEvent", "eh:DecisionTrace", "eh:visibleFrom"):
            self.assertIn(token, ontology)
        for token in ("eh:EvidenceShape", "sh:minCount 1", "eh:DecisionTraceShape"):
            self.assertIn(token, shapes)


class RuleEngineTests(unittest.TestCase):
    def setUp(self) -> None:
        self.engine = DefeasibleRuleEngine.from_file(ROOT / "rules/rules_v1.json")

    def test_non_owner_cannot_list(self) -> None:
        result = self.engine.infer(sample_state("monthly_rent"), context={"policy_source_trust": 0.8})
        self.assertIn("list_for_sale", result.blocked_actions)
        self.assertIn("list_for_rent", result.blocked_actions)

    def test_exception_suppresses_buy_defaults(self) -> None:
        state = sample_state()
        state.attributes = state.attributes.__class__(**{**state.attributes.__dict__, "risk_perception": 0.9})
        state.beliefs.affordability_prob = 0.8
        result = self.engine.infer(state, context={"policy_source_trust": 0.8})
        self.assertIn("D001_AFFORDABLE_BUY", result.suppressed_rule_ids)
        self.assertIn("D002_IMPROVEMENT_GOAL", result.suppressed_rule_ids)
        self.assertNotIn("D001_AFFORDABLE_BUY", result.active_rule_ids)

    def test_restoration_uses_stronger_official_evidence(self) -> None:
        state = sample_state()
        state.beliefs.policy_eligibility_prob = 0.9
        state.beliefs.affordability_prob = 0.6
        suppressed = self.engine.infer(state, context={"policy_source_trust": 0.2, "official_eligibility_verified": False})
        restored = self.engine.infer(state, context={"policy_source_trust": 0.2, "official_eligibility_verified": True})
        self.assertIn("D003_POLICY_ELIGIBILITY", suppressed.suppressed_rule_ids)
        self.assertNotIn("D003_POLICY_ELIGIBILITY", restored.suppressed_rule_ids)
        self.assertIn("D003_POLICY_ELIGIBILITY", restored.active_rule_ids)

    def test_trace_is_complete_and_auditable(self) -> None:
        result = self.engine.infer(sample_state(), context={"policy_source_trust": 0.8}, evidence_ids=["E1"])
        config = json.loads((ROOT / "rules/rules_v1.json").read_text(encoding="utf-8"))
        self.assertEqual(len(result.trace), len(config["rules"]))
        self.assertTrue(all(row.rule_id and row.status for row in result.trace))
        self.assertTrue(all(row.evidence_ids == ["E1"] for row in result.trace))


if __name__ == "__main__":
    unittest.main()

