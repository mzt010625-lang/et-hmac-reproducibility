import unittest

from ethmac_v9.stage8f_contract import resolve_output


def policy_record(with_relation=True):
    relation = {
        "relation_id": "REL1", "source_ref": "P1", "status": "MATCHED_AMBIGUOUS",
        "effect": "BLOCK", "base_action": "search_buy", "candidate_action": "wait",
        "match_basis": ["state.tenure"],
    }
    return {
        "id": "P", "allowed": ["stay", "wait", "search_buy"],
        "family": {"improvement_goal": 0.2, "residential_attachment": 0.2,
                   "risk_perception": 0.3},
        "state": {"liquidity_pressure": 0.2},
        "beliefs": {"price_growth_expectation": 0.0, "affordability_prob": 0.85},
        "goals": {"financial_security": 0.2, "family_stability": 0.2,
                  "mobility": 0.2, "policy_opportunity": 0.2},
        "ontology": {"multistep_dependency": False, "missing_evidence_count": 0,
                     "evidence_conflict_count": 0, "rule_conflict_count": 0},
        "memory": [], "policy_applicability": [relation] if with_relation else [],
        "evidence": [{"ref": "P1", "channel": "official",
                      "evidence_type": "policy_claim", "validity_evidenced": True,
                      "policy_state": "operational_with_evidenced_validity",
                      "claim": "matched exclusion"}],
    }


def policy_output():
    return {"v": "l2_semantic_exception_v9", "id": "P",
            "base_action": "search_buy", "action": "wait",
            "override_code": "POLICY_BLOCK", "confidence": 0.9,
            "evidence": ["P1"], "belief_updates": [], "memory_updates": []}


class Stage8FContractTest(unittest.TestCase):
    def test_matching_policy_relation_preserves_different_l2_action(self):
        resolved = resolve_output(policy_output(), policy_record(True))
        self.assertTrue(resolved["guard_accepted"])
        self.assertEqual(resolved["final_action"], "wait")
        self.assertEqual(resolved["final_source"], "L2")

    def test_missing_policy_relation_is_contract_failure_not_l1_disagreement(self):
        resolved = resolve_output(policy_output(), policy_record(False))
        self.assertFalse(resolved["guard_accepted"])
        self.assertIn("machine-readable", resolved["guard_reason"])
        self.assertEqual(resolved["final_action"], "search_buy")


if __name__ == "__main__":
    unittest.main()
