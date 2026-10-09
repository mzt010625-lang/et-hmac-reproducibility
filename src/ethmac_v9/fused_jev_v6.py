"""Single-call fusion of the fast action and routing JEV contracts."""
from __future__ import annotations

from .two_jev_v3 import FAST_RISKS, GATE_REASONS, _number
from .two_jev_v4 import compact_record

FUSED_KEYS = {
    "v", "id", "action", "confidence", "alternative", "uncertainty", "risk", "evidence",
    "error", "gain", "harm", "escalate", "reasons",
}


def fused_input(record: dict) -> dict:
    return compact_record(record)


def deterministic_escalation_precondition(compact: dict) -> bool:
    """Frozen, label-free event boundary for invoking full semantic L2."""
    local = compact["local_override"]
    prior = compact["prior"]
    structure = compact["structure"]
    return bool(
        not local["market_infeasible"]
        and not local["recent_same_action_failure"]
        and prior["hard_case"]
        and prior["margin"] <= 0.01 + 1e-12
        and structure["conflict_count"] >= 2
        and structure["multistep"]
    )


def validate_fused(output: dict, compact: dict) -> None:
    if not isinstance(output, dict) or set(output) != FUSED_KEYS:
        raise ValueError("JEV fused v6 keys mismatch")
    if output["v"] != "jev_fused_action_route_v6" or output["id"] != compact["id"]:
        raise ValueError("JEV fused v6 version/id mismatch")

    allowed = list(compact["allowed"])
    if output["action"] not in allowed:
        raise ValueError("illegal JEV fused action")
    expected = ("wait" if "wait" in allowed and
                (compact["local_override"]["market_infeasible"] or
                 compact["local_override"]["recent_same_action_failure"])
                else compact["prior"]["action"])
    if output["action"] != expected:
        raise ValueError("JEV fused v6 violated the frozen action contract")
    if len(allowed) == 1:
        if output["alternative"] is not None:
            raise ValueError("alternative must be null")
    elif output["alternative"] not in allowed or output["alternative"] == output["action"]:
        raise ValueError("alternative must be another legal action")

    for key in ("confidence", "uncertainty", "error", "gain", "harm"):
        output[key] = _number(output[key], key)
        if not 0 <= output[key] <= 1:
            raise ValueError(key + " outside [0,1]")
    # Providers occasionally interpret gain as conditional-on-L2 rather than
    # the requested unconditional probability.  Project only the probability
    # triplet onto the declared feasible bounds; the immutable raw receipt,
    # action, escalation decision and reason codes are never changed.
    raw_probabilities = {key: output[key] for key in ("error", "gain", "harm")}
    output["gain"] = min(output["gain"], output["error"])
    output["harm"] = min(output["harm"], 1 - output["error"])
    projected = any(abs(output[key] - raw_probabilities[key]) > 1e-12 for key in raw_probabilities)

    risks = output["risk"]
    if not isinstance(risks, list):
        raise ValueError("fused risks must be a list")
    raw_risks = list(risks)
    risks = list(dict.fromkeys(item for item in risks if item in FAST_RISKS))[:3]
    output["risk"] = risks
    refs = set(compact["visible_refs"])
    evidence = output["evidence"]
    if not isinstance(evidence, list):
        raise ValueError("fused evidence must be a list")
    raw_evidence = list(evidence)
    evidence = list(dict.fromkeys(item for item in evidence if item in refs))[:2]
    output["evidence"] = evidence
    reasons = output["reasons"]
    if not isinstance(reasons, list):
        raise ValueError("fused route reasons must be a list")
    raw_reasons = list(reasons)
    reasons = list(dict.fromkeys(item for item in reasons if item in GATE_REASONS))[:3]
    output["reasons"] = reasons
    output["schema_sanitization"] = {
        "risk_dropped": [item for item in raw_risks if item not in risks],
        "evidence_dropped": [item for item in raw_evidence if item not in evidence],
        "reason_dropped": [item for item in raw_reasons if item not in reasons],
    }

    if type(output["escalate"]) is not bool:
        raise ValueError("model escalation suggestion must be boolean")
    model_escalation = output["escalate"]
    expected_escalation = deterministic_escalation_precondition(compact)
    # JEV supplies semantic risk evidence and a route proposal. A frozen,
    # label-free system guard is authoritative: it vetoes false-positive cost
    # and forces coverage of the predeclared compound-risk boundary.
    output["escalate"] = expected_escalation
    if expected_escalation and not reasons:
        output["reasons"] = reasons = ["LOW_MARGIN", "MULTISTEP"]
    output["route_guard"] = {
        "model_escalate": model_escalation,
        "final_escalate": expected_escalation,
        "overridden": model_escalation != expected_escalation,
        "boundary": "unresolved_hard_case_margin_0.01_conflicts_2_multistep",
    }
    output["probability_projection"] = ({"method": "clip_to_unconditional_probability_bounds",
                                         "raw": raw_probabilities} if projected else None)
