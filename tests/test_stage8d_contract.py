import unittest

from ethmac_v9.stage8d_contract import base_action, resolve_output
from ethmac_v9.stage8d_router import route_reasons


def record():
    return {
        "id": "T1", "allowed": ["stay", "wait", "search_monthly_rent"],
        "family": {"improvement_goal": 0.2, "residential_attachment": 0.2,
                   "risk_perception": 0.5},
        "state": {"liquidity_pressure": 0.7},
        "beliefs": {"price_growth_expectation": 0.0, "affordability_prob": 0.3},
        "goals": {"financial_security": 0.2, "family_stability": 0.2,
                  "mobility": 0.2, "policy_opportunity": 0.2},
        "ontology": {"multistep_dependency": False, "missing_evidence_count": 0,
                     "evidence_conflict_count": 0, "rule_conflict_count": 0},
        "memory": [],
        "evidence": [{"ref": "M1", "evidence_type": "market_observation",
                      "channel": "market",
                      "claim": "monthly_rent: inventory_end=0"}],
    }


def output(action="search_monthly_rent", code="NONE", evidence=None):
    return {"v": "l2_semantic_exception_v7", "id": "T1",
            "base_action": "search_monthly_rent", "action": action,
            "override_code": code, "confidence": 0.9,
            "evidence": evidence or [], "belief_updates": [],
            "memory_updates": ["NO_DIRECT_UPDATE"] if code == "NONE" else []}


class Stage8DContractTest(unittest.TestCase):
    def test_base_and_route(self):
        current = record()
        self.assertEqual(base_action(current), "search_monthly_rent")
        self.assertEqual(route_reasons(current), ["MARKET_ZERO_CANDIDATE"])

    def test_valid_different_l2_is_final(self):
        resolved = resolve_output(output("wait", "MARKET_ZERO", ["M1"]), record())
        self.assertTrue(resolved["guard_accepted"])
        self.assertEqual(resolved["final_action"], "wait")
        self.assertEqual(resolved["final_source"], "L2")

    def test_unverifiable_l2_uses_failsafe_only_for_invalid_contract(self):
        current = record()
        current["evidence"][0]["claim"] = "monthly_rent: inventory_end=4"
        resolved = resolve_output(output("wait", "MARKET_ZERO", ["M1"]), current)
        self.assertFalse(resolved["guard_accepted"])
        self.assertEqual(resolved["final_action"], "search_monthly_rent")
        self.assertEqual(resolved["final_source"], "BASE_FAILSAFE_INVALID_L2")


if __name__ == "__main__":
    unittest.main()
