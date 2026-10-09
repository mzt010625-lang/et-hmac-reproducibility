"""Prior-anchored compact contracts for the Stage 7H two-JEV experiment."""
from __future__ import annotations

import math
import re

from .behavior_prior_v3 import infer as infer_prior
from .two_jev_v3 import FAST_KEYS, FAST_RISKS, GATE_KEYS, GATE_REASONS, _number


def _market(record: dict) -> dict:
    result = {}
    for item in record.get("evidence", []):
        if item.get("evidence_type") != "market_observation":
            continue
        claim = str(item.get("claim") or "")
        kind = claim.split(":", 1)[0]
        match = re.search(r"inventory_end=(-?\d+(?:\.\d+)?)", claim)
        if match and kind not in result:
            result[kind] = {"ref": item["ref"], "inventory": float(match.group(1))}
    return result


def _recent_failure(record: dict, action: str) -> bool:
    candidates = [item for item in record.get("memory", [])
                  if item.get("action") == action and item.get("success") is not None]
    if not candidates:
        return False
    latest = max(candidates, key=lambda item: int(item.get("round_index") or 0))
    return latest.get("success") is False


def compact_record(record: dict) -> dict:
    prior = infer_prior(record)
    action = prior["action"]
    target = {"search_buy": "sale", "search_jeonse": "jeonse",
              "search_monthly_rent": "monthly_rent"}.get(action)
    market = _market(record)
    target_market = market.get(target) if target else None
    market_infeasible = bool(target_market and target_market["inventory"] <= 0)
    recent_failure = _recent_failure(record, action)
    ontology = record["ontology"]
    structural_count = sum(bool(ontology.get(key)) for key in
                           ("evidence_conflict_count", "missing_evidence_count", "rule_conflict_count",
                            "multistep_dependency", "two_hop_network_dependency", "unseen_policy_combination"))
    goals = sorted(record["goals"].items(), key=lambda pair: (-pair[1], pair[0]))[:2]
    valid_policy_count = sum(item.get("evidence_type") == "policy_claim" and
                             item.get("validity_evidenced") is True for item in record.get("evidence", []))
    refs = [item["ref"] for item in record.get("evidence", [])]
    return {
        "id": record["id"], "allowed": record["allowed"],
        "prior": {"action": action, "margin": prior["decision_margin"],
                  "hard_case": prior["hard_case"], "reasons": prior["reason_codes"]},
        "core": {"tenure": record["state"]["tenure"],
                 "liquidity_pressure": record["state"]["liquidity_pressure"],
                 "affordability": record["beliefs"]["affordability_prob"],
                 "price_expectation": record["beliefs"]["price_growth_expectation"],
                 "risk": record["family"]["risk_perception"],
                 "attachment": record["family"]["residential_attachment"],
                 "top_goals": dict(goals)},
        "local_override": {"market_infeasible": market_infeasible,
                           "target_market": target_market,
                           "recent_same_action_failure": recent_failure},
        "structure": {"conflict_count": structural_count, "valid_policy_count": valid_policy_count,
                      "evidence_conflicts": int(ontology.get("evidence_conflict_count") or 0),
                      "missing_evidence": int(ontology.get("missing_evidence_count") or 0),
                      "rule_conflicts": int(ontology.get("rule_conflict_count") or 0),
                      "multistep": bool(ontology.get("multistep_dependency")),
                      "two_hop_network": bool(ontology.get("two_hop_network_dependency")),
                      "novel_policy_combo": bool(ontology.get("unseen_policy_combination"))},
        "visible_refs": refs,
    }


def fast_input(record: dict) -> dict:
    return compact_record(record)


def validate_fast(output: dict, compact: dict) -> None:
    if not isinstance(output, dict) or set(output) != FAST_KEYS:
        raise ValueError("JEV-fast v4 keys mismatch")
    if output["v"] != "jev_fast_behavior_v4" or output["id"] != compact["id"]:
        raise ValueError("JEV-fast v4 version/id mismatch")
    allowed = list(compact["allowed"])
    if output["action"] not in allowed:
        raise ValueError("illegal JEV-fast v4 action")
    expected = "wait" if ("wait" in allowed and (compact["local_override"]["market_infeasible"] or
                                                    compact["local_override"]["recent_same_action_failure"])) else compact["prior"]["action"]
    if output["action"] != expected:
        raise ValueError("JEV-fast v4 violated the frozen deterministic semantic contract")
    if len(allowed) == 1:
        if output["alternative"] is not None:
            raise ValueError("alternative must be null")
    elif output["alternative"] not in allowed or output["alternative"] == output["action"]:
        raise ValueError("alternative must be another legal action")
    for key in ("confidence", "uncertainty"):
        output[key] = _number(output[key], key)
        if not 0 <= output[key] <= 1:
            raise ValueError(key + " outside [0,1]")
    # ``structure.missing_evidence`` already carries this fact losslessly to
    # the route verifier.  If the provider redundantly emits the same concept
    # as an unlisted risk label, remove only that duplicate representation;
    # the immutable raw response and the action remain untouched.
    if isinstance(output.get("risk"), list):
        output["risk"] = [item for item in output["risk"] if item != "MISSING_EVIDENCE"]
    if (not isinstance(output["risk"], list) or len(output["risk"]) > 3 or
            len(output["risk"]) != len(set(output["risk"])) or set(output["risk"]) - FAST_RISKS):
        raise ValueError("invalid v4 risks")
    refs = set(compact["visible_refs"])
    evidence = output["evidence"]
    if not isinstance(evidence, list) or len(evidence) > 2 or len(evidence) != len(set(evidence)) or set(evidence) - refs:
        raise ValueError("invalid v4 evidence refs")


def gate_input(compact: dict, fast: dict) -> dict:
    validate_fast(fast, compact)
    return {"id": compact["id"], "fast": {key: fast[key] for key in
            ("action", "confidence", "uncertainty", "risk")},
            "prior": compact["prior"], "local_override": compact["local_override"],
            "structure": compact["structure"]}


def validate_gate(output: dict, gate_record: dict) -> None:
    if not isinstance(output, dict) or set(output) != GATE_KEYS:
        raise ValueError("JEV route v4 keys mismatch")
    if output["v"] != "jev_route_verifier_v4" or output["id"] != gate_record["id"]:
        raise ValueError("JEV route v4 version/id mismatch")
    for key in ("error", "gain", "harm"):
        output[key] = _number(output[key], key)
        if not 0 <= output[key] <= 1:
            raise ValueError(key + " outside [0,1]")
    if output["gain"] > output["error"] + 1e-9 or output["harm"] > 1 - output["error"] + 1e-9:
        raise ValueError("incoherent route probabilities")
    if type(output["escalate"]) is not bool:
        raise ValueError("escalate must be boolean")
    if output["escalate"] != (output["gain"] - output["harm"] >= .30 - 1e-9):
        raise ValueError("escalate must follow the frozen net-gain threshold")
    reasons = output["reasons"]
    if not isinstance(reasons, list) or len(reasons) > 3 or len(reasons) != len(set(reasons)) or set(reasons) - GATE_REASONS:
        raise ValueError("invalid v4 gate reasons")
    if output["escalate"] and not reasons:
        raise ValueError("escalation requires reasons")
