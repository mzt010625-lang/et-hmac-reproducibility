from __future__ import annotations

import json
from collections import defaultdict
from pathlib import Path
from typing import Any, Dict, Iterable, List, Mapping, Sequence, Tuple

from .models import HouseholdAttributes, HouseholdBeliefs, HouseholdState, MemoryItem
from .rule_engine import DefeasibleRuleEngine, InferenceResult
from .stage2b_benchmark import stable_hash
from .stage6_contracts import find_l2_forbidden_input_keys, validate_l2_request


def state_from_dict(value: Mapping[str, Any]) -> HouseholdState:
    return HouseholdState(
        attributes=HouseholdAttributes(**value["attributes"]),
        beliefs=HouseholdBeliefs(**value["beliefs"]),
        goals=dict(value["goals"]),
        memory=[MemoryItem(**item) for item in value["memory"]],
        current_round=int(value["current_round"]),
        tenure=str(value["tenure"]),
        liquid_assets=float(value["liquid_assets"]),
        liquidity_pressure=float(value["liquidity_pressure"]),
        satisfaction=float(value["satisfaction"]),
        regret=float(value["regret"]),
    )


def ontology_features(record: Mapping[str, Any], inference: InferenceResult) -> Dict[str, Any]:
    evidence = record["visible_evidence"]
    types = {str(item.get("evidence_type")) for item in evidence}
    conflict_sources = {
        str(item.get("source_id")) for item in evidence
        if item.get("provenance") == "preregistered_synthetic_conflict_probe"
    }
    missing = 0
    missing += int("policy_claim" not in types)
    missing += int("market_observation" not in types)
    missing += int("network_topology" not in types)
    network_count = max(
        [int(item.get("neighbor_count", 0)) for item in evidence if item.get("evidence_type") == "network_topology"] or [0]
    )
    supported_actions = [action for action in inference.allowed_actions if float(inference.action_scores[action]) > 0.2]
    return {
        "evidence_conflict_count": 1 if len(conflict_sources) >= 2 else 0,
        "missing_evidence_count": missing,
        "multistep_dependency": int(record["round"]) >= 3 and len(record["state"]["memory"]) >= 6,
        "rule_conflict_count": max(0, len(supported_actions) - 1),
        "two_hop_network_dependency": network_count >= 5,
        "unseen_policy_combination": str(record["policy_template_id"]).startswith("PT-X-"),
    }


def infer_l1(
    record: Mapping[str, Any],
    request: Mapping[str, Any],
    engine: DefeasibleRuleEngine,
) -> Tuple[InferenceResult, Dict[str, Any], Dict[str, Any]]:
    state = state_from_dict(record["state"])
    state.validate()
    policy_evidence = [
        item for item in record["visible_evidence"]
        if item.get("evidence_type") == "policy_claim" and item.get("channel") == "official"
    ]
    context = {
        "policy_source_trust": float(state.beliefs.channel_trust["official"]),
        "official_eligibility_verified": bool(
            state.beliefs.policy_eligibility_prob >= 0.7
            and any(float(item.get("reliability", 0.0)) >= 0.75 for item in policy_evidence)
        ),
        "peer_buy_share": 0.0,
    }
    inference = engine.infer(
        state,
        context=context,
        allowed_actions=request["allowed_actions"],
        evidence_ids=[str(item["evidence_id"]) for item in record["visible_evidence"]],
    )
    scores = sorted((float(inference.action_scores[action]), action) for action in inference.allowed_actions)
    top = scores[-1][0]
    second = scores[-2][0] if len(scores) > 1 else top
    l1_output = {
        "recommended_action": inference.recommended_action,
        "action_scores": inference.action_scores,
        "active_rule_ids": inference.active_rule_ids,
        "hard_blocked_actions": inference.blocked_actions,
        "suppressed_rule_ids": inference.suppressed_rule_ids,
        "top_two_margin": max(0.0, top - second),
    }
    return inference, l1_output, ontology_features(record, inference)


def build_jev_input(
    record: Mapping[str, Any],
    request: Mapping[str, Any],
    engine: DefeasibleRuleEngine,
    budget_fraction: float,
) -> Dict[str, Any]:
    _, l1_output, features = infer_l1(record, request, engine)
    state = record["state"]
    return {
        "record_id": record["record_id"],
        "household_id": record["household_id"],
        "round": record["round"],
        "visible_cutoff": record["visible_cutoff"],
        "allowed_actions": list(request["allowed_actions"]),
        "household_state": json.loads(json.dumps(state, ensure_ascii=False)),
        "visible_evidence": json.loads(json.dumps(record["visible_evidence"], ensure_ascii=False)),
        "l1_output": l1_output,
        "ontology_features": features,
        "router_context": {
            "budget_fraction_remaining": float(budget_fraction),
            "decision_is_high_stakes": bool(
                float(state["liquidity_pressure"]) >= 0.85
                or float(state["liquid_assets"]) < float(state["attributes"]["income_monthly"]) * 3.0
            ),
        },
    }


def build_l2_case(
    record: Mapping[str, Any],
    request: Mapping[str, Any],
    engine: DefeasibleRuleEngine,
) -> Dict[str, Any]:
    inference, _, features = infer_l1(record, request, engine)
    goals = record["state"]["goals"]
    l2_request = {
        "schema_version": "l2_request_v1",
        "request_id": f"L2REQ:{record['record_id']}:v1",
        "record_id": record["record_id"],
        "decision_version": f"{record['record_id']}:r{record['round']}:v1",
        "household_id": record["household_id"],
        "snapshot_round": record["round"],
        "visible_cutoff": record["visible_cutoff"],
        "allowed_actions": list(request["allowed_actions"]),
        "household_state": json.loads(json.dumps(record["state"], ensure_ascii=False)),
        "visible_evidence": json.loads(json.dumps(record["visible_evidence"], ensure_ascii=False)),
        "ontology_context": features,
        "memory_summary": [
            {
                "round_index": item["round_index"],
                "kind": item["kind"],
                "source_id": item["source_id"],
                "channel": item["channel"],
                "content_ref": item["content_ref"],
                "credibility": item["credibility"],
            }
            for item in record["state"]["memory"][-6:]
        ],
        "decision_objectives": {
            "housing_improvement": float(goals["housing_adequacy"]),
            "liquidity_security": float(goals["financial_security"]),
            "residential_stability": float(goals["family_stability"]),
            "risk_control": float(
                (goals["financial_security"] + goals["family_stability"]) / 2.0
            ),
        },
    }
    validate_l2_request(l2_request)
    if find_l2_forbidden_input_keys(l2_request):
        raise ValueError("L2 request contains method anchoring fields")
    return {
        "case_id": _case_id(record["record_id"]),
        "l2_request": l2_request,
        "execution_context": {
            "fast_action": inference.recommended_action,
            "fast_source": "L1",
        },
    }


def _case_id(record_id: str) -> str:
    return "PILOT-" + stable_hash(record_id)[:18]


def stable_select(rows: Iterable[Mapping[str, Any]], count: int, seed: int, tag: str) -> List[Mapping[str, Any]]:
    ranked = sorted(rows, key=lambda row: (stable_hash(seed, tag, row["record_id"]), row["record_id"]))
    if len(ranked) < count:
        raise ValueError(f"not enough rows for {tag}: need {count}, have {len(ranked)}")
    return ranked[:count]


def select_pilot_records(
    natural_records: Sequence[Mapping[str, Any]],
    challenge_records: Sequence[Mapping[str, Any]],
    stress_manifest: Sequence[Mapping[str, Any]],
    pair_manifest: Sequence[Mapping[str, Any]],
    config: Mapping[str, Any],
    phase: str,
) -> Tuple[List[Mapping[str, Any]], List[Dict[str, Any]]]:
    phase_config = config[phase]
    seed = int(config["seed"])
    split = str(config["split"])
    challenge_by_id = {row["record_id"]: row for row in challenge_records}
    selected: List[Mapping[str, Any]] = []
    selection_manifest: List[Dict[str, Any]] = []

    # Reserve the complete full-Pilot challenge household set before choosing
    # natural records. This makes phase1 a reusable strict subset of full.
    full_challenge_households: set[str] = set()
    for condition in sorted({row["condition_code"] for row in stress_manifest}):
        candidates = [row for row in stress_manifest if row["split"] == split and row["condition_code"] == condition]
        reserved = stable_select(
            candidates,
            int(config["full"]["stress_records_per_condition"]),
            seed,
            f"stress:{condition}",
        )
        full_challenge_households.update(str(row["household_id"]) for row in reserved)
    for factor in sorted({row["factor_code"] for row in pair_manifest}):
        candidates = [row for row in pair_manifest if row["split"] == split and row["factor_code"] == factor]
        reserved = stable_select(
            ({"record_id": row["pair_id"], **row} for row in candidates),
            int(config["full"]["counterfactual_pairs_per_factor"]),
            seed,
            f"pair:{factor}",
        )
        full_challenge_households.update(str(row["household_id"]) for row in reserved)

    stress_n = int(phase_config["stress_records_per_condition"])
    for condition in sorted({row["condition_code"] for row in stress_manifest}):
        candidates = [row for row in stress_manifest if row["split"] == split and row["condition_code"] == condition]
        picked = stable_select(candidates, stress_n, seed, f"stress:{condition}")
        for meta in picked:
            selected.append(challenge_by_id[meta["record_id"]])
            selection_manifest.append({"record_id": meta["record_id"], "source_line": "stress", "stratum_code": condition})

    pair_n = int(phase_config["counterfactual_pairs_per_factor"])
    for factor in sorted({row["factor_code"] for row in pair_manifest}):
        candidates = [row for row in pair_manifest if row["split"] == split and row["factor_code"] == factor]
        picked = stable_select(
            ({"record_id": row["pair_id"], **row} for row in candidates),
            pair_n,
            seed,
            f"pair:{factor}",
        )
        for pair in picked:
            for variant in ("A", "B"):
                record_id = pair[f"variant_{variant}_record_id"]
                selected.append(challenge_by_id[record_id])
                selection_manifest.append({
                    "record_id": record_id,
                    "source_line": "counterfactual",
                    "stratum_code": factor,
                    "pair_id": pair["pair_id"],
                    "variant": variant,
                })

    natural_n = int(phase_config["natural_records"])
    natural_candidates = [
        row for row in natural_records
        if row["split"] == split and row["household_id"] not in full_challenge_households
    ]
    one_per_household: Dict[str, Mapping[str, Any]] = {}
    for row in sorted(natural_candidates, key=lambda item: (stable_hash(seed, "natural-round", item["household_id"], item["round"]), item["record_id"])):
        one_per_household.setdefault(str(row["household_id"]), row)
    natural_selected = stable_select(one_per_household.values(), natural_n, seed, "natural")
    for record in natural_selected:
        selected.append(record)
        selection_manifest.append({"record_id": record["record_id"], "source_line": "natural", "stratum_code": f"R{record['round']}"})

    selected = sorted(selected, key=lambda row: (stable_hash(seed, phase, "order", row["record_id"]), row["record_id"]))
    if len(selected) != int(phase_config["total_records"]):
        raise ValueError(f"pilot count mismatch for {phase}: {len(selected)}")
    return selected, selection_manifest
