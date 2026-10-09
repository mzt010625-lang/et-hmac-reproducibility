from __future__ import annotations

import copy
import hashlib
import json
from collections import defaultdict
from typing import Any, Dict, Iterable, List, Mapping, MutableMapping, Sequence, Tuple

from .stage2b_benchmark import canonical_json, stable_hash, validate_household_state
from .validation import assert_group_disjoint, find_banned_keys, validate_reference_request


def _neutral_id(prefix: str, *parts: object) -> str:
    return f"{prefix}-{stable_hash(*parts)[:18]}"


def _rank_households(household_ids: Iterable[str], seed: int, split: str) -> List[str]:
    return sorted(set(household_ids), key=lambda value: (stable_hash(seed, split, value), value))


def allocate_households(
    records: Sequence[Mapping[str, Any]],
    config: Mapping[str, Any],
) -> Tuple[Dict[Tuple[str, str], List[str]], Dict[Tuple[str, str], List[str]], List[str]]:
    household_split: Dict[str, str] = {}
    for record in records:
        household_id = str(record["household_id"])
        split = str(record["split"])
        previous = household_split.setdefault(household_id, split)
        if previous != split:
            raise ValueError(f"household crosses splits: {household_id}")
    stress_allocations: Dict[Tuple[str, str], List[str]] = {}
    counterfactual_allocations: Dict[Tuple[str, str], List[str]] = {}
    unused: List[str] = []
    for split in ("development", "pilot"):
        ranked = _rank_households(
            (household_id for household_id, owner in household_split.items() if owner == split),
            int(config["seed"]),
            split,
        )
        cursor = 0
        stress_count = int(config["stress"][f"{split}_per_condition"])
        for condition in config["stress"]["conditions"]:
            selected = ranked[cursor : cursor + stress_count]
            if len(selected) != stress_count:
                raise ValueError("not enough households for stress allocation")
            stress_allocations[(split, condition)] = selected
            cursor += stress_count
        pair_count = int(config["counterfactual"][f"{split}_pairs_per_factor"])
        for factor in config["counterfactual"]["factors"]:
            selected = ranked[cursor : cursor + pair_count]
            if len(selected) != pair_count:
                raise ValueError("not enough households for counterfactual allocation")
            counterfactual_allocations[(split, factor)] = selected
            cursor += pair_count
        unused.extend(ranked[cursor:])
    return stress_allocations, counterfactual_allocations, sorted(unused)


def select_parent_record(records_by_household: Mapping[str, Sequence[Mapping[str, Any]]], household_id: str, seed: int) -> Mapping[str, Any]:
    rows = sorted(records_by_household[household_id], key=lambda row: int(row["round"]))
    index = int(stable_hash(seed, household_id, "round")[:8], 16) % len(rows)
    return rows[index]


def _set_policy_template(record: MutableMapping[str, Any], tag: str) -> None:
    record["policy_template_id"] = "PT-X-" + stable_hash(record["policy_template_id"], tag, canonical_json(record["visible_evidence"]))[:16]


def _network_evidence(evidence: Sequence[MutableMapping[str, Any]]) -> MutableMapping[str, Any]:
    matches = [item for item in evidence if item.get("evidence_type") == "network_topology"]
    if len(matches) != 1:
        raise ValueError("challenge source must contain exactly one network_topology item")
    return matches[0]


def apply_stress(record: Mapping[str, Any], condition: str, seed: int) -> Dict[str, Any]:
    value = copy.deepcopy(record)
    state = value["state"]
    evidence = value["visible_evidence"]
    if condition == "S01":
        value["visible_evidence"] = [item for item in evidence if item.get("evidence_type") != "policy_claim"]
        state["beliefs"]["policy_eligibility_prob"] = 0.5
        state["beliefs"]["uncertainty"]["policy_eligibility_prob"] = 1.0
    elif condition == "S02":
        value["visible_evidence"] = [item for item in evidence if item.get("evidence_type") != "market_observation"]
        state["beliefs"]["price_growth_expectation"] = 0.0
        state["beliefs"]["uncertainty"]["price_growth_expectation"] = 1.0
    elif condition == "S03":
        for item in evidence:
            draw = int(stable_hash(seed, record["record_id"], item["evidence_id"])[:8], 16) / 0xFFFFFFFF
            item["reliability"] = max(0.05, min(0.95, round(float(item.get("reliability", 0.5)) + (draw - 0.5) * 0.7, 6)))
    elif condition == "S04":
        base_id = _neutral_id("E", seed, record["record_id"], condition)
        evidence.extend([
            {
                "evidence_id": base_id + "-A",
                "visible_from": int(record["round"]),
                "expires_after": int(record["round"]),
                "source_id": "synthetic_blind_source_A",
                "channel": "official",
                "evidence_type": "policy_claim",
                "claim": "A current policy notice states that the support arrangement remains available for four additional decision rounds.",
                "reliability": 0.7,
                "policy_state": "operational_with_evidenced_validity",
                "validity_evidenced": True,
                "provenance": "preregistered_synthetic_conflict_probe",
            },
            {
                "evidence_id": base_id + "-B",
                "visible_from": int(record["round"]),
                "expires_after": int(record["round"]),
                "source_id": "synthetic_blind_source_B",
                "channel": "official",
                "evidence_type": "policy_claim",
                "claim": "An equally current policy notice states that the support arrangement ends after this decision round.",
                "reliability": 0.7,
                "policy_state": "operational_with_evidenced_validity",
                "validity_evidenced": True,
                "provenance": "preregistered_synthetic_conflict_probe",
            },
        ])
        state["beliefs"]["uncertainty"]["policy_duration_expectation"] = 1.0
    elif condition == "S05":
        item = _network_evidence(evidence)
        item["neighbor_count"] = 0
        item["claim"] = "No neighbor is visible in the current induced-network snapshot; no neighbor action label is supplied."
        item["reliability"] = 0.3
        item["provenance"] = "preregistered_network_isolation_probe"
    elif condition == "S06":
        state["memory"] = []
        for key in state["beliefs"]["uncertainty"]:
            state["beliefs"]["uncertainty"][key] = max(0.9, float(state["beliefs"]["uncertainty"][key]))
    elif condition == "S07":
        state["liquid_assets"] = round(float(state["liquid_assets"]) * 0.65, 6)
        state["liquidity_pressure"] = min(1.0, float(state["liquidity_pressure"]) + 0.25)
        evidence.append({
            "evidence_id": _neutral_id("E", seed, record["record_id"], condition),
            "visible_from": int(record["round"]),
            "expires_after": int(record["round"]),
            "source_id": "household_cash_ledger",
            "channel": "self_experience",
            "evidence_type": "liquidity_event",
            "claim": "An unplanned essential expense reduced currently available liquid assets by 35 percent.",
            "reliability": 1.0,
            "provenance": "preregistered_exogenous_liquidity_probe",
        })
    else:
        raise ValueError(f"unknown stress condition: {condition}")
    _set_policy_template(value, condition)
    return value


def apply_counterfactual(record: Mapping[str, Any], factor: str, level: Any) -> Dict[str, Any]:
    value = copy.deepcopy(record)
    state = value["state"]
    if factor == "C01":
        state["liquidity_pressure"] = float(level)
    elif factor == "C02":
        state["beliefs"]["channel_trust"]["official"] = float(level)
    elif factor == "C03":
        state["beliefs"]["price_growth_expectation"] = float(level)
    elif factor == "C04":
        state["beliefs"]["policy_eligibility_prob"] = float(level)
    elif factor == "C05":
        item = _network_evidence(value["visible_evidence"])
        item["neighbor_count"] = int(level)
        item["claim"] = f"Visible induced-network neighbor count={int(level)}; no neighbor action label is supplied."
        item["provenance"] = "preregistered_counterfactual_network_probe"
    else:
        raise ValueError(f"unknown counterfactual factor: {factor}")
    _set_policy_template(value, factor)
    return value


def _request_from_record(record: Mapping[str, Any], parent_request: Mapping[str, Any]) -> Dict[str, Any]:
    request = {
        "record_id": record["record_id"],
        "household_id": record["household_id"],
        "round": record["round"],
        "visible_cutoff": record["visible_cutoff"],
        "household_state": copy.deepcopy(record["state"]),
        "visible_evidence": copy.deepcopy(record["visible_evidence"]),
        "allowed_actions": list(parent_request["allowed_actions"]),
        "task_definition": str(parent_request["task_definition"]),
    }
    validate_reference_request(request)
    if find_banned_keys(request):
        raise ValueError("challenge request contains a banned method field")
    return request


def build_challenges(
    source_records: Sequence[Mapping[str, Any]],
    source_requests: Mapping[str, Mapping[str, Any]],
    config: Mapping[str, Any],
) -> Dict[str, Any]:
    by_household: Dict[str, List[Mapping[str, Any]]] = defaultdict(list)
    for record in source_records:
        by_household[str(record["household_id"])].append(record)
    stress_allocations, counterfactual_allocations, unused = allocate_households(source_records, config)
    seed = int(config["seed"])

    stress_records: List[Dict[str, Any]] = []
    stress_requests: List[Dict[str, Any]] = []
    stress_manifest: List[Dict[str, Any]] = []
    for (split, condition), household_ids in sorted(stress_allocations.items()):
        for household_id in household_ids:
            parent = select_parent_record(by_household, household_id, seed)
            record = apply_stress(parent, condition, seed)
            record_id = _neutral_id("V9-X", seed, parent["record_id"], condition)
            record["record_id"] = record_id
            record["parent_sample_id"] = parent["record_id"]
            record["queue_type"] = "stress"
            request = _request_from_record(record, source_requests[parent["record_id"]])
            validate_household_state(record["state"])
            stress_records.append(record)
            stress_requests.append(request)
            stress_manifest.append({
                "record_id": record_id,
                "parent_sample_id": parent["record_id"],
                "household_id": household_id,
                "split": split,
                "condition_code": condition,
                "condition_name": config["condition_registry"][condition],
                "expected_action": None,
                "expected_direction": None,
            })

    counterfactual_records: List[Dict[str, Any]] = []
    counterfactual_requests: List[Dict[str, Any]] = []
    pair_manifest: List[Dict[str, Any]] = []
    for (split, factor), household_ids in sorted(counterfactual_allocations.items()):
        levels = config["counterfactual_levels"][factor]
        for household_id in household_ids:
            parent = select_parent_record(by_household, household_id, seed)
            pair_id = _neutral_id("PAIR", seed, parent["record_id"], factor)
            variant_ids: Dict[str, str] = {}
            for variant in ("A", "B"):
                record = apply_counterfactual(parent, factor, levels[variant])
                record_id = _neutral_id("V9-P", seed, pair_id, variant)
                record["record_id"] = record_id
                record["parent_sample_id"] = parent["record_id"]
                record["queue_type"] = "counterfactual"
                request = _request_from_record(record, source_requests[parent["record_id"]])
                validate_household_state(record["state"])
                counterfactual_records.append(record)
                counterfactual_requests.append(request)
                variant_ids[variant] = record_id
            pair_manifest.append({
                "pair_id": pair_id,
                "parent_sample_id": parent["record_id"],
                "household_id": household_id,
                "split": split,
                "factor_code": factor,
                "factor_name": config["condition_registry"][factor],
                "variant_A_record_id": variant_ids["A"],
                "variant_B_record_id": variant_ids["B"],
                "variant_A_value": levels["A"],
                "variant_B_value": levels["B"],
                "expected_action": None,
                "expected_direction": None,
            })

    all_records = stress_records + counterfactual_records
    assert_group_disjoint(all_records, ("household_id", "parent_sample_id", "world_id", "network_seed"))
    return {
        "records": all_records,
        "requests": stress_requests + counterfactual_requests,
        "stress_records": stress_records,
        "stress_requests": stress_requests,
        "counterfactual_records": counterfactual_records,
        "counterfactual_requests": counterfactual_requests,
        "stress_manifest": stress_manifest,
        "pair_manifest": pair_manifest,
        "unused_households": unused,
    }


def _drop_record_metadata(record: Mapping[str, Any]) -> Dict[str, Any]:
    value = copy.deepcopy(record)
    for key in ("record_id", "policy_template_id"):
        value.pop(key, None)
    return value


def recursive_diff(left: Any, right: Any, path: str = "$") -> List[str]:
    if type(left) is not type(right):
        return [path]
    if isinstance(left, dict):
        paths: List[str] = []
        for key in sorted(set(left) | set(right)):
            if key not in left or key not in right:
                paths.append(f"{path}.{key}")
            else:
                paths.extend(recursive_diff(left[key], right[key], f"{path}.{key}"))
        return paths
    if isinstance(left, list):
        if len(left) != len(right):
            return [path]
        paths = []
        for index, (a, b) in enumerate(zip(left, right)):
            paths.extend(recursive_diff(a, b, f"{path}[{index}]"))
        return paths
    return [] if left == right else [path]


def audit_challenges(bundle: Mapping[str, Any], config: Mapping[str, Any]) -> Dict[str, Any]:
    records = bundle["records"]
    requests = bundle["requests"]
    stress_manifest = bundle["stress_manifest"]
    pair_manifest = bundle["pair_manifest"]
    by_record = {record["record_id"]: record for record in records}
    banned_hits = []
    future_evidence = 0
    forbidden_string_hits = []
    forbidden_markers = {"CONDITION_CODE", "CONDITION_NAME", "FACTOR_CODE", "FACTOR_NAME", "EXPECTED_DIRECTION"}
    for request in requests:
        banned_hits.extend(f"{request['record_id']}:{path}" for path in find_banned_keys(request))
        serialized = canonical_json(request).upper()
        for marker in forbidden_markers:
            if marker in serialized:
                forbidden_string_hits.append(f"{request['record_id']}:{marker}")
        for evidence in request["visible_evidence"]:
            if int(evidence["visible_from"]) > int(request["visible_cutoff"]):
                future_evidence += 1
    pair_diff_counts: Dict[str, int] = defaultdict(int)
    unexpected_pair_diffs: List[Dict[str, Any]] = []
    allowed_paths = {
        "C01": {"$.state.liquidity_pressure"},
        "C02": {"$.state.beliefs.channel_trust.official"},
        "C03": {"$.state.beliefs.price_growth_expectation"},
        "C04": {"$.state.beliefs.policy_eligibility_prob"},
        "C05": {
            "$.visible_evidence[" + str(index) + "].claim"
            for index in range(64)
        } | {
            "$.visible_evidence[" + str(index) + "].neighbor_count"
            for index in range(64)
        } | {
            "$.visible_evidence[" + str(index) + "].provenance"
            for index in range(64)
        },
    }
    for pair in pair_manifest:
        factor = pair["factor_code"]
        left = _drop_record_metadata(by_record[pair["variant_A_record_id"]])
        right = _drop_record_metadata(by_record[pair["variant_B_record_id"]])
        diffs = recursive_diff(left, right)
        pair_diff_counts[factor] += len(diffs)
        unexpected = sorted(set(diffs) - allowed_paths[factor])
        if unexpected:
            unexpected_pair_diffs.append({"pair_id": pair["pair_id"], "factor_code": factor, "paths": unexpected})
    stress_counts = defaultdict(int)
    for row in stress_manifest:
        stress_counts[(row["split"], row["condition_code"])] += 1
    pair_counts = defaultdict(int)
    for row in pair_manifest:
        pair_counts[(row["split"], row["factor_code"])] += 1
    household_uses = defaultdict(int)
    for record in records:
        household_uses[record["household_id"]] += 1
    return {
        "record_count": len(records),
        "request_count": len(requests),
        "stress_record_count": len(bundle["stress_records"]),
        "counterfactual_record_count": len(bundle["counterfactual_records"]),
        "counterfactual_pair_count": len(pair_manifest),
        "unique_households": len(household_uses),
        "household_variant_count_distribution": {
            str(count): sum(value == count for value in household_uses.values())
            for count in sorted(set(household_uses.values()))
        },
        "unused_household_count": len(bundle["unused_households"]),
        "stress_counts": {f"{split}:{condition}": count for (split, condition), count in sorted(stress_counts.items())},
        "pair_counts": {f"{split}:{factor}": count for (split, factor), count in sorted(pair_counts.items())},
        "future_evidence_count": future_evidence,
        "banned_key_hits": banned_hits,
        "condition_name_hits_in_model_requests": forbidden_string_hits,
        "unexpected_counterfactual_diff": unexpected_pair_diffs,
        "pair_diff_total_by_factor": dict(pair_diff_counts),
        "expected_action_non_null_count": sum(row["expected_action"] is not None for row in stress_manifest + pair_manifest),
        "expected_direction_non_null_count": sum(row["expected_direction"] is not None for row in stress_manifest + pair_manifest),
        "gate_pass": (
            len(records) == 3400
            and len(bundle["stress_records"]) == 1400
            and len(bundle["counterfactual_records"]) == 2000
            and len(pair_manifest) == 1000
            and future_evidence == 0
            and not banned_hits
            and not forbidden_string_hits
            and not unexpected_pair_diffs
        ),
        "interpretation_boundary": "Mechanism probes only; no target action, expected direction, or formal behavior label is encoded.",
    }
