"""Uncalibrated domain-prior L1 v2 candidate, not a fitted teacher surrogate.

Five household goals evaluate all seven legal actions. All constants are fixed
engineering priors; development agreement does not establish behavioral validity.
No L2 prediction, reference label, record ID or household ID is a model feature.
"""
from __future__ import annotations
import math
import re
from .models import ACTIONS, clamp
from .jev_runner import validate_jev_input


def infer(source: dict) -> dict:
    validate_jev_input(source)
    s = source["household_state"]
    a, b, goals = s["attributes"], s["beliefs"], s["goals"]
    allowed = [x for x in ACTIONS if x in source["allowed_actions"]]
    if s["tenure"] != "owner":
        allowed = [x for x in allowed if x not in ("list_for_sale", "list_for_rent")]
    if not allowed:
        raise ValueError("L1 v2 has no hard-feasible action")
    # Only read typed numeric market fields, never keyword-interpret a policy as
    # legal eligibility. Conflicting repeated market snapshots are not averaged.
    market, conflicts = {}, []
    for e in source["visible_evidence"]:
        if e.get("evidence_type") != "market_observation":
            continue
        claim = e.get("claim", "")
        kind = claim.split(":", 1)[0]
        if kind not in ("sale", "jeonse", "monthly_rent"):
            continue
        vals = dict(re.findall(r"(demand_pressure|inventory_end|unmet_demand)=(-?\d+(?:\.\d+)?)", claim))
        if len(vals) != 3:
            continue
        item = {k: float(v) for k, v in vals.items()}
        if kind in market and market[kind] != item:
            conflicts.append(kind)
        else:
            market[kind] = item
    for kind in conflicts:
        market.pop(kind, None)
    pressure = s["liquidity_pressure"]
    risk = a["risk_perception"]
    loss = a["loss_aversion"]
    attach = a["residential_attachment"]
    improve = a["improvement_goal"]
    afford = b["affordability_prob"]
    satis = s["satisfaction"]
    need = clamp((improve + 1 - satis) / 2)
    uncertainty = sum(b["uncertainty"].values()) / max(1, len(b["uncertainty"]))
    eligibility = b["policy_eligibility_prob"] * b["channel_trust"]["official"]
    # Each vector: adequacy, financial security, family stability, mobility,
    # policy opportunity. They describe preferences, never legal permissions.
    vectors = {
        "stay": [1-need, 1-pressure, attach, 0, 0],
        "wait": [0.5*(1-need), 0.5*(1-pressure)+0.5*uncertainty,
                 0.5+0.5*attach, 0.5, 0.5*eligibility],
        "search_buy": [need, afford*(1-pressure), 0.6, 0.2, eligibility],
        "search_jeonse": [need, afford*(1-0.5*pressure), 0.6, 0.6, 0],
        "search_monthly_rent": [need, pressure, 0.3, 1, 0],
        "list_for_sale": [0.2, pressure, 1-attach, 1, 0],
        "list_for_rent": [0.2, 0.5+0.5*pressure, 0.5*(1-attach), 0.5, 0],
    }
    goal_keys = ["housing_adequacy", "financial_security", "family_stability", "mobility", "policy_opportunity"]
    if set(goals) != set(goal_keys):
        raise ValueError("L1 v2 goal schema changed")
    action_market = {"search_buy": "sale", "list_for_sale": "sale",
                     "search_jeonse": "jeonse", "search_monthly_rent": "monthly_rent",
                     "list_for_rent": "monthly_rent"}
    moving = {"search_buy", "search_jeonse", "search_monthly_rent", "list_for_sale", "list_for_rent"}
    irreversible = {"search_buy": 1, "search_jeonse": .6, "search_monthly_rent": .25,
                    "list_for_sale": 1, "list_for_rent": .4, "stay": 0, "wait": 0}
    scores, traces = dict.fromkeys(ACTIONS, 0.0), {}
    for action in allowed:
        success = b["action_success_prob"][action]
        expected_goal = sum(goals[k] * v for k, v in zip(goal_keys, vectors[action]))
        # A failed search does not imply a forced transaction or change of tenure.
        if action in moving:
            expected_goal *= .5 + .5*success
        adjustment = 0.0
        m = market.get(action_market.get(action))
        if m:
            demand = math.tanh(m["demand_pressure"])
            if action.startswith("search_"):
                adjustment = -.10*demand - .15*int(m["inventory_end"] <= 0)
            elif action.startswith("list_"):
                adjustment = .10*demand
        switching = .10*attach*int(action in moving)
        downside = .10*irreversible[action]*(risk+loss)*(1-success)
        history, weight = 0.0, 0.0
        for mem in s.get("memory", []):
            if mem.get("action") != action or mem.get("success") is None:
                continue
            w = float(mem["credibility"]) * .8**max(0, source["round"]-mem["round_index"])
            history += w*((1 if mem["success"] else -1) + mem["satisfaction"]-mem["regret"]-.5)
            weight += w
        memory_term = .05*history/max(1, weight)
        # bounded utility scores, not calibrated class probabilities
        scores[action] = clamp(.25+.5*(expected_goal+adjustment-switching-downside+memory_term))
        traces[action] = {"goal": expected_goal, "market": adjustment,
                          "switching_cost": switching, "risk_cost": downside, "memory": memory_term}
    ranked = sorted(allowed, key=lambda x: (-scores[x], ACTIONS.index(x)))
    margin = scores[ranked[0]]-scores[ranked[1]] if len(ranked)>1 else 0.0
    return {"recommended_action": ranked[0], "action_scores": scores,
            "top_two_margin": margin, "active_rule_ids": ["U2_GOAL", "U2_SUCCESS", "U2_RISK", "U2_MARKET", "U2_MEMORY"],
            "suppressed_rule_ids": [], "hard_blocked_actions": [x for x in ACTIONS if x not in allowed],
            "utility_trace": traces, "market_missing_or_conflicting": [x for x in ("sale", "jeonse", "monthly_rent") if x not in market],
            "calibrated": False, "variant": "l1_goal_utility_v2_candidate"}
