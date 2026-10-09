"""Deterministic identity-context behavior prior for the Stage 8 baseline.

The prior is a transparent social-science engineering hypothesis, not a fitted
teacher surrogate and not a claim of real-world behavioral validity.  Record
identifiers and cached L2 decisions are deliberately unavailable to the policy.
"""
from __future__ import annotations

import math
import re
from typing import Any

from .models import ACTIONS


def _number(value: Any, name: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"{name} must be numeric")
    value = float(value)
    if not math.isfinite(value):
        raise ValueError(f"{name} must be finite")
    return value


def _market(record: dict) -> dict[str, dict[str, float]]:
    out: dict[str, dict[str, float]] = {}
    conflicted: set[str] = set()
    for evidence in record.get("evidence", []):
        if evidence.get("evidence_type") != "market_observation":
            continue
        claim = str(evidence.get("claim") or "")
        kind = claim.split(":", 1)[0]
        if kind not in {"sale", "jeonse", "monthly_rent"}:
            continue
        values = dict(re.findall(
            r"(demand_pressure|unmet_demand|inventory_end)=(-?\d+(?:\.\d+)?)", claim
        ))
        if len(values) != 3:
            continue
        item = {key: float(value) for key, value in values.items()}
        if kind in out and out[kind] != item:
            conflicted.add(kind)
        else:
            out[kind] = item
    for kind in conflicted:
        out.pop(kind, None)
    return out


def infer(record: dict) -> dict:
    required = {"id", "round", "allowed", "family", "state", "beliefs",
                "goals", "memory", "evidence", "ontology"}
    missing = required - set(record)
    if missing:
        raise ValueError("behavior prior input misses: " + ", ".join(sorted(missing)))
    allowed = list(record["allowed"])
    if not allowed or len(allowed) != len(set(allowed)) or set(allowed) - set(ACTIONS):
        raise ValueError("invalid allowed action set")
    family, state = record["family"], record["state"]
    beliefs, goals, ontology = record["beliefs"], record["goals"], record["ontology"]
    tenure = str(state["tenure"])
    if tenure != "owner" and set(allowed) & {"list_for_sale", "list_for_rent"}:
        raise ValueError("non-owner received owner-only actions")

    liquidity = _number(state["liquidity_pressure"], "liquidity_pressure")
    affordability = _number(beliefs["affordability_prob"], "affordability_prob")
    price_growth = _number(beliefs["price_growth_expectation"], "price_growth_expectation")
    risk = _number(family["risk_perception"], "risk_perception")
    attachment = _number(family["residential_attachment"], "residential_attachment")
    improvement = _number(family["improvement_goal"], "improvement_goal")
    financial = _number(goals["financial_security"], "financial_security")
    stability = _number(goals["family_stability"], "family_stability")
    mobility = _number(goals["mobility"], "mobility")
    policy_opportunity = _number(goals["policy_opportunity"], "policy_opportunity")
    uncertainty_values = [_number(x, "uncertainty") for x in beliefs["uncertainty"].values()]
    uncertainty = sum(uncertainty_values) / max(1, len(uncertainty_values))
    market = _market(record)

    action = None
    reason_codes: list[str] = []
    threshold_distances: list[float] = []
    if tenure == "owner":
        sale_pressure = liquidity >= 0.68
        adverse_holding = price_growth <= -0.04 and improvement >= 0.35
        threshold_distances.extend((abs(liquidity - 0.68), abs(price_growth + 0.04),
                                    abs(improvement - 0.35)))
        if "list_for_sale" in allowed and (sale_pressure or adverse_holding):
            action = "list_for_sale"
            reason_codes.extend(["OWNER", "LIQUIDITY_OR_HOLDING_RISK"])
        elif "list_for_rent" in allowed and (attachment >= 0.45 or financial >= 0.28):
            action = "list_for_rent"
            reason_codes.extend(["OWNER", "HOLD_AND_INCOME"])
            threshold_distances.extend((abs(attachment - 0.45), abs(financial - 0.28)))
    else:
        if "search_buy" in allowed:
            threshold_distances.extend((abs(affordability - 0.72), abs(liquidity - 0.45),
                                        abs(risk - 0.65)))
            if affordability >= 0.72 and liquidity <= 0.45 and risk <= 0.65:
                action = "search_buy"
                reason_codes.append("BUY_FEASIBLE")
        if action is None and "search_jeonse" in allowed:
            balance = financial + stability - mobility - policy_opportunity
            threshold_distances.extend((abs(affordability - 0.50), abs(balance)))
            if affordability >= 0.50 and balance >= 0:
                action = "search_jeonse"
                reason_codes.append("JEONSE_STABILITY_FIT")
        if action is None and "search_monthly_rent" in allowed:
            threshold_distances.extend((abs(liquidity - 0.55), abs(affordability - 0.40),
                                        abs(mobility - 0.23)))
            if liquidity >= 0.55 or affordability <= 0.40 or mobility >= 0.23:
                action = "search_monthly_rent"
                reason_codes.append("MONTHLY_RENT_FLEXIBILITY")

    structural_uncertainty = bool(ontology.get("multistep_dependency")) and (
        int(ontology.get("missing_evidence_count") or 0) > 0
        or int(ontology.get("evidence_conflict_count") or 0) > 0
        or int(ontology.get("rule_conflict_count") or 0) > 0
    )
    if action is None and "wait" in allowed and structural_uncertainty:
        action = "wait"
        reason_codes.append("STRUCTURAL_UNCERTAINTY")
    if action is None:
        action = "stay" if "stay" in allowed else "wait"
        reason_codes.append("CURRENT_ARRANGEMENT_DEFAULT")

    margin = min(threshold_distances) if threshold_distances else 1.0
    hard_case = bool(
        structural_uncertainty
        or int(ontology.get("evidence_conflict_count") or 0) > 0
        or int(ontology.get("rule_conflict_count") or 0) > 0
        or margin < 0.05
    )
    intent = "ACT" if action not in {"stay", "wait"} else ("DEFER" if action == "wait" else "STAY")
    return {
        "v": "behavior_prior_v3",
        "id": record["id"],
        "intent": intent,
        "action": action,
        "reason_codes": reason_codes,
        "decision_margin": round(margin, 6),
        "hard_case": hard_case,
        "diagnostics": {
            "tenure": tenure,
            "uncertainty_mean": round(uncertainty, 6),
            "market_types_available": sorted(market),
            "structural_uncertainty": structural_uncertainty,
        },
    }

