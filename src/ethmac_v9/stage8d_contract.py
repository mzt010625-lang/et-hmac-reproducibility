"""Frozen finite semantic-exception contract for Stage 8D development."""
from __future__ import annotations

import math
import re
from typing import Any


ACTIONS = {
    "stay", "wait", "search_buy", "search_jeonse",
    "search_monthly_rent", "list_for_sale", "list_for_rent",
}
OVERRIDES = {
    "NONE", "MARKET_ZERO", "RECENT_FAILURE",
    "POLICY_BLOCK", "POLICY_ENABLE", "CONFLICT_WAIT",
}
BELIEF_UPDATES = {
    "REASSESS_ELIGIBILITY", "REASSESS_AFFORDABILITY",
    "UPDATE_PRICE_EXPECTATION", "UPDATE_SOURCE_TRUST",
}
MEMORY_UPDATES = {
    "RECORD_SEARCH_OUTCOME", "RECORD_TRANSACTION_OUTCOME", "NO_DIRECT_UPDATE",
}
REQUIRED = {
    "v", "id", "base_action", "action", "override_code", "confidence",
    "evidence", "belief_updates", "memory_updates",
}


def _finite(value: Any, name: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(name + " must be numeric")
    number = float(value)
    if not math.isfinite(number):
        raise ValueError(name + " must be finite")
    return number


def base_action(record: dict) -> str:
    """Execute only the frozen base table; semantic exceptions are excluded."""
    allowed = set(record["allowed"])
    family, state = record["family"], record["state"]
    beliefs, goals, ontology = record["beliefs"], record["goals"], record["ontology"]
    action = None
    if "list_for_sale" in allowed and (
        _finite(state["liquidity_pressure"], "liquidity_pressure") >= 0.68
        or (
            _finite(beliefs["price_growth_expectation"], "price_growth_expectation") <= -0.04
            and _finite(family["improvement_goal"], "improvement_goal") >= 0.35
        )
    ):
        action = "list_for_sale"
    elif "list_for_rent" in allowed and (
        _finite(family["residential_attachment"], "residential_attachment") >= 0.45
        or _finite(goals["financial_security"], "financial_security") >= 0.28
    ):
        action = "list_for_rent"
    elif "search_buy" in allowed and (
        _finite(beliefs["affordability_prob"], "affordability_prob") >= 0.72
        and _finite(state["liquidity_pressure"], "liquidity_pressure") <= 0.45
        and _finite(family["risk_perception"], "risk_perception") <= 0.65
    ):
        action = "search_buy"
    elif "search_jeonse" in allowed and (
        _finite(beliefs["affordability_prob"], "affordability_prob") >= 0.50
        and _finite(goals["financial_security"], "financial_security")
        + _finite(goals["family_stability"], "family_stability")
        - _finite(goals["mobility"], "mobility")
        - _finite(goals["policy_opportunity"], "policy_opportunity") >= 0
    ):
        action = "search_jeonse"
    elif "search_monthly_rent" in allowed and (
        _finite(state["liquidity_pressure"], "liquidity_pressure") >= 0.55
        or _finite(beliefs["affordability_prob"], "affordability_prob") <= 0.40
        or _finite(goals["mobility"], "mobility") >= 0.23
    ):
        action = "search_monthly_rent"
    if action is None:
        conflicts = sum(int(ontology.get(key) or 0) for key in (
            "missing_evidence_count", "evidence_conflict_count", "rule_conflict_count"
        ))
        if ontology.get("multistep_dependency") and conflicts > 0 and "wait" in allowed:
            action = "wait"
        else:
            action = "stay" if "stay" in allowed else "wait"
    if action not in allowed:
        raise ValueError("base table returned an illegal action")
    return action


def _market_inventory(record: dict, action: str) -> float | None:
    market = {
        "search_buy": "sale", "search_jeonse": "jeonse",
        "search_monthly_rent": "monthly_rent",
    }.get(action)
    if not market:
        return None
    for item in record.get("evidence", []):
        claim = str(item.get("claim") or "")
        if item.get("evidence_type") == "market_observation" and claim.startswith(market + ":"):
            match = re.search(r"inventory_end=(-?\d+(?:\.\d+)?)", claim)
            return float(match.group(1)) if match else None
    return None


def validate_output(output: dict, record: dict) -> dict:
    if not isinstance(output, dict) or set(output) != REQUIRED:
        raise ValueError("L2 v6 output keys mismatch")
    if output["v"] != "l2_semantic_exception_v7" or output["id"] != record["id"]:
        raise ValueError("L2 v6 version/id mismatch")
    allowed = set(record["allowed"])
    if output["base_action"] not in allowed or output["action"] not in allowed:
        raise ValueError("L2 v6 returned an illegal action")
    expected_base = base_action(record)
    if output["base_action"] != expected_base:
        raise ValueError(
            f"L2 v6 base table mismatch: got {output['base_action']}, expected {expected_base}"
        )
    code = output["override_code"]
    if code not in OVERRIDES:
        raise ValueError("invalid override_code")
    confidence = _finite(output["confidence"], "confidence")
    if not 0 <= confidence <= 1:
        raise ValueError("confidence must be in [0,1]")
    refs = {str(item["ref"]): item for item in record.get("evidence", [])}
    evidence = output["evidence"]
    if (
        not isinstance(evidence, list) or len(evidence) > 4
        or len(evidence) != len(set(evidence)) or any(ref not in refs for ref in evidence)
    ):
        raise ValueError("invalid evidence references")
    if (
        not isinstance(output["belief_updates"], list)
        or set(output["belief_updates"]) - BELIEF_UPDATES
        or len(output["belief_updates"]) != len(set(output["belief_updates"]))
    ):
        raise ValueError("invalid belief_updates")
    if (
        not isinstance(output["memory_updates"], list)
        or set(output["memory_updates"]) - MEMORY_UPDATES
        or len(output["memory_updates"]) != len(set(output["memory_updates"]))
    ):
        raise ValueError("invalid memory_updates")
    if "NO_DIRECT_UPDATE" in output["memory_updates"] and len(output["memory_updates"]) != 1:
        raise ValueError("NO_DIRECT_UPDATE must be exclusive")
    if code == "NONE" and output["action"] != output["base_action"]:
        raise ValueError("NONE cannot change the base action")
    if code != "NONE" and output["action"] == output["base_action"]:
        raise ValueError("an override code must change the action")
    if code != "NONE" and not evidence:
        raise ValueError("an override requires direct evidence")
    if code == "MARKET_ZERO":
        if _market_inventory(record, output["base_action"]) != 0 or output["action"] != "wait":
            raise ValueError("MARKET_ZERO is not externally verifiable")
    if code == "RECENT_FAILURE":
        failed = any(
            item.get("action") == output["base_action"] and item.get("success") is False
            for item in record.get("memory", [])
        )
        if not failed or output["action"] != "wait":
            raise ValueError("RECENT_FAILURE is not externally verifiable")
    if code in {"POLICY_BLOCK", "POLICY_ENABLE"}:
        valid_policy_refs = {
            ref for ref, item in refs.items()
            if item.get("channel") == "official"
            and item.get("evidence_type") == "policy_claim"
            and item.get("validity_evidenced") is True
            and item.get("policy_state") == "operational_with_evidenced_validity"
        }
        if not (set(evidence) & valid_policy_refs):
            raise ValueError("policy override lacks an operational evidenced official source")
    if code == "CONFLICT_WAIT":
        ontology = record.get("ontology", {})
        conflicts = sum(int(ontology.get(key) or 0) for key in (
            "missing_evidence_count", "evidence_conflict_count", "rule_conflict_count"
        ))
        if not ontology.get("multistep_dependency") or conflicts < 2 or output["action"] != "wait":
            raise ValueError("CONFLICT_WAIT is not externally verifiable")
    return output


def resolve_output(output: dict, record: dict) -> dict:
    """Apply the hard contract guard and deterministically resolve invalid L2.

    A legal, evidenced L2 remains final even when it differs from the base.
    Only malformed or externally unverifiable L2 output uses the documented
    fail-safe base action.
    """
    if not isinstance(output, dict) or set(output) != REQUIRED:
        raise ValueError("L2 v7 output keys mismatch")
    if output.get("v") != "l2_semantic_exception_v7" or output.get("id") != record["id"]:
        raise ValueError("L2 v7 version/id mismatch")
    allowed = set(record["allowed"])
    if output.get("base_action") not in allowed or output.get("action") not in allowed:
        reason = "illegal action or base action"
    else:
        try:
            validate_output(output, record)
        except ValueError as exc:
            reason = str(exc)
        else:
            return {
                "raw_output": output,
                "guard_accepted": True,
                "guard_reason": None,
                "final_action": output["action"],
                "final_source": "L2",
            }
    return {
        "raw_output": output,
        "guard_accepted": False,
        "guard_reason": reason,
        "final_action": base_action(record),
        "final_source": "BASE_FAILSAFE_INVALID_L2",
    }
