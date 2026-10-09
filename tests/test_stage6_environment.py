from __future__ import annotations

import unittest

from ethmac_v9.stage6_environment import run_local_closed_loop


class Stage6EnvironmentTests(unittest.TestCase):
    def test_three_round_closed_loop_changes_state_and_preserves_l2(self) -> None:
        result = run_local_closed_loop(rounds=3, seed=20260928)
        self.assertEqual(result["households"], 3)
        self.assertEqual(result["decisions"], 9)
        self.assertEqual(result["l2_final_decisions"], 6)
        self.assertEqual(result["valid_l2_override_count"], 0)
        self.assertTrue(result["all_round_states_changed"])
        self.assertEqual(len(result["trajectory"]), 3)
        for state in result["final_states"].values():
            self.assertEqual(state["current_round"], 3)
            self.assertGreaterEqual(len(state["memory"]), 3)

    def test_fixed_seed_is_exactly_reproducible(self) -> None:
        first = run_local_closed_loop(rounds=3, seed=20260928)
        second = run_local_closed_loop(rounds=3, seed=20260928)
        self.assertEqual(first, second)

    def test_forced_market_failure_does_not_change_committed_action(self) -> None:
        result = run_local_closed_loop(rounds=1, seed=20260928)
        row = result["trajectory"][0]
        decision = row["decisions"]["HH-DEMO-02"]
        outcome = row["outcomes"]["HH-DEMO-02"]
        self.assertEqual(decision["final_action"], "search_buy")
        self.assertEqual(decision["final_source"], "L2")
        self.assertFalse(outcome["success"])


if __name__ == "__main__":
    unittest.main()
