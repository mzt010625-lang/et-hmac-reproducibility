from copy import deepcopy

from ethmac_v9.fused_jev_v6 import deterministic_escalation_precondition, validate_fused


def compact(escalate=False):
    return {
        "id": "x", "allowed": ["stay", "wait"],
        "prior": {"action": "stay", "margin": .005 if escalate else .2, "hard_case": escalate, "reasons": []},
        "core": {},
        "local_override": {"market_infeasible": False, "target_market": None, "recent_same_action_failure": False},
        "structure": {"conflict_count": 2 if escalate else 0, "valid_policy_count": 1,
                      "evidence_conflicts": 0, "missing_evidence": 0, "rule_conflicts": 0,
                      "multistep": escalate, "two_hop_network": False, "novel_policy_combo": escalate},
        "visible_refs": ["e1"],
    }


def output(escalate=False):
    return {"v": "jev_fused_action_route_v6", "id": "x", "action": "stay", "confidence": .8,
            "alternative": "wait", "uncertainty": .2, "risk": [], "evidence": ["e1"],
            "error": .5 if escalate else .1, "gain": .4 if escalate else .05,
            "harm": .05 if escalate else .02, "escalate": escalate,
            "reasons": ["MULTISTEP"] if escalate else []}


def test_event_boundary_is_label_free_and_deterministic():
    assert not deterministic_escalation_precondition(compact(False))
    assert deterministic_escalation_precondition(compact(True))


def test_validate_accepts_both_paths():
    validate_fused(output(False), compact(False))
    validate_fused(output(True), compact(True))


def test_system_guard_vetoes_route_false_positive():
    bad = deepcopy(output(False)); bad["escalate"] = True; bad["reasons"] = ["MULTISTEP"]
    validate_fused(bad, compact(False))
    assert bad["escalate"] is False
    assert bad["route_guard"]["model_escalate"] is True
    assert bad["route_guard"]["overridden"] is True
