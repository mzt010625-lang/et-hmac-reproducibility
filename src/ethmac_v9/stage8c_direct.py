"""Stage 8C compact JEV and independent direct-L2 contracts."""
from __future__ import annotations

import json
import math
import re
from typing import Any

from .behavior_prior_v3 import infer as infer_prior

ACTIONS_ORDER = ["stay", "wait", "search_buy", "search_jeonse",
                 "search_monthly_rent", "list_for_sale", "list_for_rent"]
RISK_CODES = {"LOW_MARGIN", "POLICY_CONFLICT", "MARKET_CONFLICT", "GOAL_CONFLICT",
              "MEMORY_CONFLICT", "NETWORK", "MULTISTEP", "NOVELTY", "HIGH_STAKES"}
BELIEF_UPDATES = {"REASSESS_ELIGIBILITY", "REASSESS_AFFORDABILITY",
                  "UPDATE_PRICE_EXPECTATION", "UPDATE_SOURCE_TRUST"}
MEMORY_UPDATES = {"RECORD_SEARCH_OUTCOME", "RECORD_TRANSACTION_OUTCOME",
                  "NO_DIRECT_UPDATE"}
JEV_KEYS = {"v", "id", "action", "confidence", "need_l2_probability",
            "uncertainty_codes", "route_reason_codes", "evidence"}
JEV_COMPACT_KEYS = {"v", "id", "a", "c", "p", "u", "r", "e"}
L2_KEYS = {"v", "id", "action", "confidence", "evidence",
           "belief_updates", "memory_updates"}


def _round(value: Any, digits: int = 4) -> Any:
    if isinstance(value, bool) or value is None or isinstance(value, str):
        return value
    if isinstance(value, (int, float)):
        return round(float(value), digits)
    if isinstance(value, dict):
        return {key: _round(item, digits) for key, item in value.items()}
    if isinstance(value, list):
        return [_round(item, digits) for item in value]
    return value


def _number(value: Any, name: str) -> float:
    if isinstance(value, str):
        try:
            value = float(value)
        except ValueError as exc:
            raise ValueError(name + " must be numeric") from exc
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(name + " must be numeric")
    value = float(value)
    if not math.isfinite(value) or not 0 <= value <= 1:
        raise ValueError(name + " must be in [0,1]")
    return value


def _market_summary(record: dict) -> dict:
    result = {}
    for item in record.get("evidence", []):
        if item.get("evidence_type") != "market_observation":
            continue
        claim = str(item.get("claim") or "")
        kind = claim.split(":", 1)[0]
        values = dict(re.findall(
            r"(demand_pressure|matches|unmet_demand|inventory_end)=(-?\d+(?:\.\d+)?)", claim
        ))
        result[kind] = {"ref": item.get("ref"), **{key: float(value) for key, value in values.items()}}
    return result


def _memory_summary(record: dict) -> dict:
    memory = list(record.get("memory", []))
    action_events = [item for item in memory if item.get("action")]
    latest = max(action_events, key=lambda item: int(item.get("round_index") or 0), default=None)
    failures = [item for item in action_events if item.get("success") is False]
    return {"n": len(memory), "omitted": int(record.get("memory_omitted") or 0),
            "last": ({"a": latest.get("action"), "ok": latest.get("success"),
                      "r": latest.get("round_index"), "sat": _round(latest.get("satisfaction")),
                      "regret": _round(latest.get("regret"))} if latest else None),
            "failed": list(dict.fromkeys(item["action"] for item in failures))[-2:]}


def _event_summary(record: dict) -> dict:
    evidence = list(record.get("evidence", []))
    policies = [item for item in evidence if item.get("evidence_type") == "policy_claim"]
    policy_summary = [{"ref": item.get("ref"), "valid": item.get("validity_evidenced"),
                       "rel": _round(item.get("reliability"))}
                      for item in sorted(policies, key=lambda x: float(x.get("reliability") or 0), reverse=True)[:2]]
    networks = [{"ref": item.get("ref"), "neighbor_count": item.get("neighbor_count"),
                 "reliability": _round(item.get("reliability"))}
                for item in evidence if item.get("evidence_type") == "network_topology"]
    return {"policy": policy_summary, "market": _market_summary(record),
            "network": networks[:2], "ontology": _round(record.get("ontology", {}))}


def compact_jev_input(record: dict) -> dict:
    prior = infer_prior(record)
    family = record["family"]
    state = record["state"]
    beliefs = record["beliefs"]
    memory = _memory_summary(record)
    event = _event_summary(record)
    market_key = {
        "search_buy": "sale",
        "search_jeonse": "jeonse",
        "search_monthly_rent": "monthly_rent",
    }.get(prior["action"])
    market_row = event["market"].get(market_key, {}) if market_key else {}
    event["local"] = {
        "market_infeasible": bool(market_key and market_row.get("inventory_end") == 0),
        "recent_same_action_failure": bool(
            memory.get("last")
            and memory["last"].get("a") == prior["action"]
            and memory["last"].get("ok") is False
        ),
    }
    ontology = event["ontology"]
    policy = event["policy"]
    network = event["network"]
    compact_event = {
        "policy": {
            "valid_count": sum(item.get("valid") is True for item in policy),
            "max_reliability": max((float(item.get("rel") or 0) for item in policy), default=0.0),
        },
        "network": {
            "neighbor_count": max((int(item.get("neighbor_count") or 0) for item in network), default=0),
            "two_hop": bool(ontology.get("two_hop_network_dependency")),
        },
        "ontology": {key: ontology.get(key) for key in (
            "evidence_conflict_count", "missing_evidence_count", "rule_conflict_count",
            "multistep_dependency", "unseen_policy_combination")},
        "local": event["local"],
    }
    visible_refs = [item.get("ref") for item in policy[:1] if item.get("ref")]
    if market_key and market_row.get("ref"):
        visible_refs.append(market_row["ref"])
    return {
        "id": record["id"], "round": record["round"], "visible_cutoff": record["visible_cutoff"],
        "agent_state": {
            "family": _round({"lc": family.get("lifecycle_stage"),
                "imp": family.get("improvement_goal"), "risk": family.get("risk_perception"),
                "attach": family.get("residential_attachment"),
                "trust": family.get("policy_trust_tendency"), "peer": family.get("peer_sensitivity")}),
            "state": _round({"ten": state.get("tenure"), "liq": state.get("liquidity_pressure"),
                              "regret": state.get("regret")}),
            "beliefs": _round({"aff": beliefs.get("affordability_prob"),
                "elig": beliefs.get("policy_eligibility_prob"),
                "price": beliefs.get("price_growth_expectation"),
                "dur": beliefs.get("policy_duration_expectation")}),
            "goals": _round({"stable": record["goals"].get("family_stability"),
                "finance": record["goals"].get("financial_security"),
                "adequacy": record["goals"].get("housing_adequacy"),
                "mobility": record["goals"].get("mobility"),
                "policy": record["goals"].get("policy_opportunity")}),
            "memory": {"n": memory["n"], "om": memory["omitted"],
                       "last": memory["last"], "failed": memory["failed"]},
            "allowed": list(record["allowed"]),
        },
        "rule_prior": {"a": prior["action"], "m": prior["decision_margin"],
                       "h": prior["hard_case"]},
        "event_context": {
            "policy": {"valid": compact_event["policy"]["valid_count"],
                       "rel": compact_event["policy"]["max_reliability"]},
            "network": {"n": compact_event["network"]["neighbor_count"],
                        "two": compact_event["network"]["two_hop"]},
            "ontology": {"ec": ontology.get("evidence_conflict_count"),
                         "miss": ontology.get("missing_evidence_count"),
                         "rc": ontology.get("rule_conflict_count"),
                         "multi": ontology.get("multistep_dependency"),
                         "new": ontology.get("unseen_policy_combination")},
            "local": {"mi": event["local"]["market_infeasible"],
                      "rf": event["local"]["recent_same_action_failure"]},
        },
        "visible_refs": visible_refs,
    }


def direct_l2_input(record: dict) -> dict:
    agent = {key: record[key] for key in ("id", "round", "visible_cutoff", "family", "state",
             "beliefs", "goals", "memory", "memory_omitted", "allowed")}
    context = {"evidence": record.get("evidence", []), "ontology": record.get("ontology", {})}
    return {"agent_state": agent, "event_context": context}


def compile_direct_user(template: str, record: dict) -> str:
    payload = direct_l2_input(record)
    message = template.replace("{{AGENT_STATE_JSON}}", json.dumps(
        payload["agent_state"], ensure_ascii=False, sort_keys=True, separators=(",", ":")))
    return message.replace("{{EVENT_CONTEXT_JSON}}", json.dumps(
        payload["event_context"], ensure_ascii=False, sort_keys=True, separators=(",", ":")))


def _normalize_list(output: dict, key: str, allowed: set[str], maximum: int) -> list[str]:
    raw = output.get(key)
    if not isinstance(raw, list):
        raise ValueError(key + " must be a list")
    return list(dict.fromkeys(item for item in raw if isinstance(item, str) and item in allowed))[:maximum]


def validate_jev(output: dict, compact: dict) -> dict:
    if not isinstance(output, dict):
        raise ValueError("JEV v8 output must be an object")
    if JEV_COMPACT_KEYS.issubset(output):
        output = {"v": output["v"], "id": output["id"], "action": output["a"],
                  "confidence": output["c"], "need_l2_probability": output["p"],
                  "uncertainty_codes": output["u"], "route_reason_codes": output["r"],
                  "evidence": output["e"]}
    elif JEV_KEYS.issubset(output):
        output = {key: output[key] for key in JEV_KEYS}
    else:
        raise ValueError("JEV v8 required keys mismatch")
    if output["v"] not in {"j9", "jev_action_route_v9"} or output["id"] != compact["id"]:
        raise ValueError("JEV v9 version/id mismatch")
    output["v"] = "jev_action_route_v9"
    allowed = compact["agent_state"]["allowed"]
    if output["action"] not in allowed:
        raise ValueError("JEV v7 action is illegal")
    output["confidence"] = _number(output["confidence"], "confidence")
    output["need_l2_probability"] = _number(output["need_l2_probability"], "need_l2_probability")
    output["uncertainty_codes"] = _normalize_list(output, "uncertainty_codes", RISK_CODES, 3)
    output["route_reason_codes"] = _normalize_list(output, "route_reason_codes", RISK_CODES, 3)
    refs = set(compact["visible_refs"])
    output["evidence"] = _normalize_list(output, "evidence", refs, 2)
    return output


def validate_direct_l2(output: dict, record: dict) -> dict:
    if not isinstance(output, dict) or not L2_KEYS.issubset(output):
        raise ValueError("direct L2 v4 required keys mismatch")
    output = {key: output[key] for key in L2_KEYS}
    if output["v"] != "l2_direct_decision_v5" or output["id"] != record["id"]:
        raise ValueError("direct L2 v4 version/id mismatch")
    if output["action"] not in record["allowed"]:
        raise ValueError("direct L2 action is illegal")
    output["confidence"] = _number(output["confidence"], "confidence")
    refs = {str(item["ref"]) for item in record.get("evidence", [])}
    output["evidence"] = _normalize_list(output, "evidence", refs, 4)
    output["belief_updates"] = _normalize_list(output, "belief_updates", BELIEF_UPDATES, 4)
    output["memory_updates"] = _normalize_list(output, "memory_updates", MEMORY_UPDATES, 3)
    if "NO_DIRECT_UPDATE" in output["memory_updates"]:
        output["memory_updates"] = ["NO_DIRECT_UPDATE"]
    return output


def ontology_force_l2(record: dict) -> bool:
    ontology = record.get("ontology", {})
    conflicts = sum(int(ontology.get(key) or 0) for key in
                    ("evidence_conflict_count", "missing_evidence_count", "rule_conflict_count"))
    multistep = bool(ontology.get("multistep_dependency"))
    return bool((multistep and conflicts >= 2)
                or (multistep and ontology.get("unseen_policy_combination"))
                or (ontology.get("two_hop_network_dependency") and
                    int(ontology.get("evidence_conflict_count") or 0) > 0))


def route(record: dict, jev: dict, threshold: float) -> tuple[bool, dict]:
    forced = ontology_force_l2(record)
    model = jev["need_l2_probability"] >= threshold - 1e-12
    return forced or model, {"forced_by_ontology_guard": forced,
                             "model_threshold_positive": model,
                             "threshold": threshold}
