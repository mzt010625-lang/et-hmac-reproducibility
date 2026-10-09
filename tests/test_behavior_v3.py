import copy
import unittest

from ethmac_v9.behavior_prior_v3 import infer
from ethmac_v9.behavior_v3 import combine_consensus, validate_audit, validate_prompt_structure


def record():
    return {
        "id": "R1", "round": 2, "visible_cutoff": 2,
        "allowed": ["stay", "wait", "search_monthly_rent"],
        "family": {"risk_perception": .4, "residential_attachment": .3,
                   "improvement_goal": .4},
        "state": {"tenure": "monthly_rent", "liquidity_pressure": .7},
        "beliefs": {"affordability_prob": .3, "price_growth_expectation": 0,
                    "uncertainty": {"a": .4, "b": .6}},
        "goals": {"financial_security": .3, "family_stability": .2,
                  "mobility": .25, "policy_opportunity": .1},
        "memory": [], "memory_omitted": 0,
        "evidence": [{"ref": "M1", "evidence_type": "market_observation",
                      "claim": "monthly_rent: demand_pressure=1; unmet_demand=2; inventory_end=5"}],
        "ontology": {"multistep_dependency": False, "missing_evidence_count": 0,
                     "evidence_conflict_count": 0, "rule_conflict_count": 0},
    }


def audit(r, prior):
    return {"v": "behavior_audit_v3", "id": r["id"],
            "identity_fit": "SUPPORTS_PRIOR", "context_fit": "SUPPORTS_PRIOR",
            "action_vote": prior["action"], "confidence": .8,
            "override_request": False, "override_code": "NONE", "evidence": ["M1"],
            "belief_updates": [], "memory_updates": ["NO_DIRECT_UPDATE"]}


class BehaviorV3Tests(unittest.TestCase):
    def test_prior_is_deterministic_and_non_owner_safe(self):
        r = record()
        first = infer(r)
        self.assertEqual(first, infer(copy.deepcopy(r)))
        self.assertEqual(first["action"], "search_monthly_rent")
        self.assertIn(first["action"], r["allowed"])

    def test_non_override_preserves_prior(self):
        r = record(); prior = infer(r); a = audit(r, prior)
        validate_audit(a, r, prior)
        decision = combine_consensus(r, prior, [a, copy.deepcopy(a)])
        self.assertEqual(decision["final_action"], prior["action"])
        self.assertEqual(decision["source"], "DETERMINISTIC_PRIOR")

    def test_invalid_free_override_is_rejected(self):
        r = record(); prior = infer(r); a = audit(r, prior)
        a.update({"override_request": True, "override_code": "NONE", "action_vote": "stay"})
        with self.assertRaises(ValueError):
            validate_audit(a, r, prior)

    def test_incomplete_prompt_is_rejected_before_api(self):
        with self.assertRaisesRegex(ValueError, "incomplete behavior prompt"):
            validate_prompt_structure("# 角色与任务", "{{AGENT_STATE_JSON}}")


if __name__ == "__main__":
    unittest.main()
