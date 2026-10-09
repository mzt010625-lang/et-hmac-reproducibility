from __future__ import annotations

import unittest

from ethmac_v9.evaluation import compare_quality, select_budgeted_l2


class EvaluationTests(unittest.TestCase):
    def test_budget_allocator_uses_positive_evc_and_never_exceeds_capacity(self) -> None:
        rows = [
            {
                "record_id": f"R{index}",
                "jev_output": {
                    "l2_correction_probability_raw": correction,
                    "l2_harm_probability_raw": 0.1,
                },
            }
            for index, correction in enumerate((0.9, 0.8, 0.05, 0.7, 0.6), start=1)
        ]
        selected, scores, capacity = select_budgeted_l2(rows, 0.4)
        self.assertEqual(capacity, 2)
        self.assertEqual(selected, {"R1", "R2"})
        self.assertLess(scores["R3"], 0)

    def test_quality_reports_reference_accuracy_and_all_l2_gap(self) -> None:
        hybrid = {"R1": "stay", "R2": "wait", "R3": "stay"}
        all_l2 = {"R1": "stay", "R2": "stay", "R3": "stay"}
        references = [
            {"record_id": "R1", "decision_status": "labeled", "best_action": "stay", "acceptable_actions": ["stay"]},
            {"record_id": "R2", "decision_status": "labeled", "best_action": "wait", "acceptable_actions": ["wait"]},
            {"record_id": "R3", "decision_status": "labeled", "best_action": "stay", "acceptable_actions": ["stay", "wait"]},
        ]
        result = compare_quality(hybrid, all_l2, references)
        self.assertAlmostEqual(result["all_l2_decision_agreement"], 2 / 3)
        self.assertAlmostEqual(result["hybrid"]["accuracy"], 1.0)
        self.assertAlmostEqual(result["all_l2"]["accuracy"], 2 / 3)
        self.assertLess(result["all_l2_minus_hybrid_gap_percentage_points"]["accuracy"], 0)

    def test_all_l2_agreement_is_not_labeled_as_accuracy(self) -> None:
        result = compare_quality({"R1": "stay"}, {"R1": "stay"})
        self.assertEqual(result["all_l2_decision_agreement"], 1.0)
        self.assertTrue(result["agreement_is_not_ground_truth_accuracy"])
        self.assertEqual(result["reference_metrics_status"], "NOT_EVALUABLE_NO_REFERENCE_LABELS")


if __name__ == "__main__":
    unittest.main()
