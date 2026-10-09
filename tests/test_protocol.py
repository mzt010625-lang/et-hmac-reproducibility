from __future__ import annotations

import json
import unittest
from pathlib import Path

from ethmac_v9.validation import assert_group_disjoint, validate_reference_request

ROOT = Path(__file__).resolve().parents[1]


def valid_request():
    return {
        "record_id": "R1",
        "household_id": "H1",
        "round": 1,
        "visible_cutoff": 1,
        "household_state": {"tenure": "monthly_rent"},
        "visible_evidence": [{"evidence_id": "E1", "visible_from": 1}],
        "allowed_actions": ["stay", "wait"],
        "task_definition": "Select one allowed housing action from information visible through this round."
    }


class ProtocolTests(unittest.TestCase):
    def test_schema_files_are_valid_json(self) -> None:
        for path in (ROOT / "schemas").glob("*.json"):
            json.loads(path.read_text(encoding="utf-8"))

    def test_reference_request_accepts_clean_input(self) -> None:
        validate_reference_request(valid_request())

    def test_reference_request_recursively_blocks_l1_leak(self) -> None:
        payload = valid_request()
        payload["household_state"]["nested"] = {"semantic_scorecard": {"search_buy": 4.2}}
        with self.assertRaisesRegex(ValueError, "semantic_scorecard"):
            validate_reference_request(payload)

    def test_reference_request_blocks_future_evidence(self) -> None:
        payload = valid_request()
        payload["visible_evidence"][0]["visible_from"] = 2
        with self.assertRaisesRegex(ValueError, "future"):
            validate_reference_request(payload)

    def test_group_split_leak_is_detected(self) -> None:
        rows = [
            {"household_id": "H1", "split": "development"},
            {"household_id": "H1", "split": "locked_test"},
        ]
        with self.assertRaisesRegex(ValueError, "crosses"):
            assert_group_disjoint(rows, ["household_id"])


if __name__ == "__main__":
    unittest.main()

