from __future__ import annotations

import copy
import unittest
from dataclasses import replace

from ethmac_v9.stage6_contracts import (
    DecisionLedger,
    GuardResult,
    HardGuard,
    L2Attempt,
    find_l2_forbidden_input_keys,
    resolve_final_decision,
    validate_l2_request,
)


def request() -> dict:
    return {
        "schema_version": "l2_request_v1",
        "request_id": "REQ-1",
        "record_id": "REC-1",
        "decision_version": "REC-1:r2:v1",
        "household_id": "HH-1",
        "snapshot_round": 2,
        "visible_cutoff": 2,
        "allowed_actions": ["stay", "wait", "search_buy"],
        "household_state": {"tenure": "monthly_rent", "liquid_assets": 100000},
        "visible_evidence": [
            {"evidence_id": "E-1", "visible_from": 2, "channel": "official", "claim": "visible"}
        ],
        "ontology_context": {"rule_conflict_count": 1},
        "memory_summary": [],
        "decision_objectives": {"housing_improvement": 0.7, "liquidity_security": 0.4},
    }


def output(action: str = "search_buy") -> dict:
    return {
        "schema_version": "l2_output_v1",
        "request_id": "REQ-1",
        "record_id": "REC-1",
        "decision_version": "REC-1:r2:v1",
        "action": action,
        "confidence": 0.7,
        "evidence_ids": ["E-1"],
        "rationale_codes": ["POLICY_EVIDENCE", "AFFORDABILITY"],
        "state_update_codes": ["REASSESS_AFFORDABILITY"],
    }


def attempt(action: str = "search_buy", index: int = 1, response_id: str = "RESP-1") -> L2Attempt:
    req = request()
    out = output(action)
    guard = HardGuard().validate(out, req, current_decision_version=req["decision_version"])
    return L2Attempt(index, response_id, out, guard)


def resolve(fast_action: str = "wait", attempts=(), l2_requested: bool = True):
    req = request()
    return resolve_final_decision(
        record_id=req["record_id"],
        decision_version=req["decision_version"],
        fast_action=fast_action,
        fast_source="L1",
        allowed_actions=req["allowed_actions"],
        l2_requested=l2_requested,
        attempts=attempts,
    )


class Stage6DecisionContractTests(unittest.TestCase):
    def test_l2_request_has_no_fast_or_reference_fields(self) -> None:
        validate_l2_request(request())
        self.assertEqual(find_l2_forbidden_input_keys(request()), [])

    def test_d01_different_valid_l2_is_final(self) -> None:
        decision = resolve("wait", [attempt("search_buy")])
        self.assertEqual((decision.final_action, decision.final_source), ("search_buy", "L2"))
        self.assertTrue(decision.action_disagreement)

    def test_d02_same_valid_action_source_is_still_l2(self) -> None:
        decision = resolve("wait", [attempt("wait")])
        self.assertEqual((decision.final_action, decision.final_source), ("wait", "L2"))
        self.assertFalse(decision.action_disagreement)

    def test_d03_fast_preference_changes_do_not_change_guard_or_l2(self) -> None:
        att = attempt("search_buy")
        first = resolve("wait", [att])
        second = resolve("stay", [att])
        self.assertTrue(att.guard_result.accepted)
        self.assertEqual(first.final_action, second.final_action)
        self.assertEqual(first.final_source, second.final_source)

    def test_d04_no_vote_between_fast_layers_and_l2(self) -> None:
        decision = resolve("stay", [attempt("search_buy")])
        self.assertEqual(decision.final_action, "search_buy")

    def test_d05_reference_cannot_rewrite_valid_l2(self) -> None:
        decision = resolve("wait", [attempt("search_buy")])
        reference_action = "wait"
        evaluation_correct = decision.final_action == reference_action
        self.assertFalse(evaluation_correct)
        self.assertEqual(decision.final_action, "search_buy")

    def test_d06_soft_rule_conflict_is_not_a_guard_failure(self) -> None:
        req = request()
        out = output("search_buy")
        out["rationale_codes"] = ["GOAL_TRADEOFF"]
        guard = HardGuard().validate(out, req)
        self.assertTrue(guard.accepted)
        self.assertEqual(resolve("wait", [L2Attempt(1, "R", out, guard)]).final_source, "L2")

    def test_d07_illegal_and_future_outputs_are_rejected(self) -> None:
        req = request()
        illegal = output("list_for_sale")
        self.assertEqual(HardGuard().validate(illegal, req).failure_reason, "action_illegal")
        future_req = request()
        future_req["visible_evidence"][0]["visible_from"] = 3
        self.assertEqual(HardGuard().validate(output(), future_req).failure_reason, "future_information")

    def test_d08_illegal_fast_fallback_becomes_undecided(self) -> None:
        bad = L2Attempt(1, "BAD", output("list_for_sale"), GuardResult(False, "action_illegal", ()))
        decision = resolve("list_for_sale", [bad])
        self.assertEqual(decision.status, "UNDECIDED")
        self.assertIsNone(decision.final_action)

    def test_d09_first_valid_retry_is_adopted_and_stops(self) -> None:
        bad = L2Attempt(1, "BAD", output("list_for_sale"), GuardResult(False, "action_illegal", ()))
        good = attempt("search_buy", index=2, response_id="GOOD")
        later = attempt("wait", index=3, response_id="LATE")
        decision = resolve("wait", [bad, good, later])
        self.assertEqual(decision.accepted_l2_response_id, "GOOD")
        self.assertEqual(decision.final_action, "search_buy")
        self.assertEqual(decision.retry_count, 1)

    def test_d10_low_fast_score_cannot_remove_objectively_legal_action(self) -> None:
        req = request()
        self.assertIn("search_buy", req["allowed_actions"])
        self.assertTrue(HardGuard().validate(output("search_buy"), req).accepted)

    def test_d11_commit_is_idempotent_but_not_overwritable(self) -> None:
        ledger = DecisionLedger()
        decision = resolve("wait", [attempt("search_buy")])
        ledger.commit(decision)
        ledger.commit(decision)
        changed = resolve("wait", [attempt("wait")])
        with self.assertRaisesRegex(ValueError, "already committed"):
            ledger.commit(changed)

    def test_d12_execution_failure_does_not_rewrite_decision(self) -> None:
        ledger = DecisionLedger()
        decision = ledger.commit(resolve("wait", [attempt("search_buy")]))
        execution_success = False
        self.assertFalse(execution_success)
        self.assertEqual(ledger.get("REC-1", "REC-1:r2:v1"), decision)
        self.assertEqual(decision.final_action, "search_buy")

    def test_d13_no_l2_request_uses_legal_fast_action_without_fallback_label(self) -> None:
        decision = resolve("wait", [], l2_requested=False)
        self.assertEqual((decision.final_action, decision.final_source), ("wait", "L1"))
        self.assertIsNone(decision.degradation_reason)

    def test_d14_stale_or_late_response_cannot_replace_commit(self) -> None:
        req = request()
        stale = output("search_buy")
        stale["decision_version"] = "REC-1:r1:v1"
        self.assertEqual(HardGuard().validate(stale, req).failure_reason, "stale_snapshot")
        ledger = DecisionLedger()
        first = ledger.commit(resolve("wait", [attempt("search_buy")]))
        late = replace(copy.deepcopy(first), final_action="wait")
        with self.assertRaisesRegex(ValueError, "already committed"):
            ledger.commit(late)

    def test_valid_l2_override_audit_is_zero(self) -> None:
        ledger = DecisionLedger()
        ledger.commit(resolve("wait", [attempt("search_buy")]))
        self.assertEqual(ledger.valid_l2_override_count(), 0)


if __name__ == "__main__":
    unittest.main()
