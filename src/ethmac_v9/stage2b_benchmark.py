from __future__ import annotations

import csv
import hashlib
import json
import math
from collections import defaultdict
from datetime import date
from pathlib import Path
from typing import Any, Dict, Iterable, List, Mapping, Sequence, Tuple

from .models import ACTIONS, HouseholdAttributes, HouseholdBeliefs, HouseholdState, MemoryItem, clamp
from .validation import assert_group_disjoint, find_banned_keys, validate_reference_request


ROUND_DATES = {
    1: date(2013, 3, 31),
    2: date(2013, 6, 30),
    3: date(2013, 9, 30),
    4: date(2013, 12, 31),
}


def canonical_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def stable_hash(*parts: object) -> str:
    return hashlib.sha256("\x1f".join(str(part) for part in parts).encode("utf-8")).hexdigest()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def load_jsonl(path: Path) -> List[Dict[str, Any]]:
    rows: List[Dict[str, Any]] = []
    with path.open(encoding="utf-8") as handle:
        for line_number, line in enumerate(handle, start=1):
            if not line.strip():
                continue
            try:
                rows.append(json.loads(line))
            except json.JSONDecodeError as exc:
                raise ValueError(f"invalid JSONL at {path}:{line_number}: {exc}") from exc
    return rows


def load_csv_by_household(path: Path, year: int = 2013) -> Dict[str, Dict[str, str]]:
    result: Dict[str, Dict[str, str]] = {}
    with path.open(encoding="utf-8-sig", newline="") as handle:
        for row in csv.DictReader(handle):
            if int(row["year"]) != year:
                continue
            result[row["household_id"]] = row
    return result


def load_induced_network(
    path: Path,
    household_ids: set[str],
    year: int = 2013,
) -> Tuple[Dict[str, List[str]], List[Dict[str, str]], Dict[str, int]]:
    neighbors: Dict[str, set[str]] = defaultdict(set)
    edges: List[Dict[str, str]] = []
    audit = {"year_edges": 0, "induced_edges": 0, "cross_GU_induced_edges_excluded": 0}
    with path.open(encoding="utf-8-sig", newline="") as handle:
        for row in csv.DictReader(handle):
            if int(row["year"]) != year:
                continue
            audit["year_edges"] += 1
            source = row["source_household_id"]
            target = row["target_household_id"]
            if source not in household_ids or target not in household_ids:
                continue
            source_gu = source.split("-")[2]
            target_gu = target.split("-")[2]
            if source_gu != target_gu:
                audit["cross_GU_induced_edges_excluded"] += 1
                continue
            if target in neighbors[source]:
                continue
            neighbors[source].add(target)
            neighbors[target].add(source)
            edges.append({"source_household_id": source, "target_household_id": target, "edge_type": row["edge_type"]})
    audit["induced_edges"] = len(edges)
    return {key: sorted(value) for key, value in neighbors.items()}, sorted(edges, key=lambda x: (x["source_household_id"], x["target_household_id"])), audit


def normalize_tenure(value: object) -> str:
    text = str(value)
    return text if text in {"owner", "jeonse", "monthly_rent"} else "other"


def normalize_dwelling(value: object) -> str:
    text = str(value).lower()
    if text == "apartment":
        return "apartment"
    if text in {"detached", "detached_house"}:
        return "detached"
    if text in {"row_house", "multi_family", "multi_family_house", "multiplex"}:
        return "multi_family"
    if text == "officetel":
        return "officetel"
    return "other"


def lifecycle_stage(age: int, household_size: int, married: bool) -> str:
    if age >= 65:
        return "retired"
    if household_size == 1 and not married:
        return "single"
    if age < 35:
        return "new_family"
    if age < 50 and household_size >= 3:
        return "child_rearing"
    if age < 60:
        return "mature_family"
    return "empty_nest"


def normalize_weights(values: Mapping[str, float]) -> Dict[str, float]:
    total = sum(max(0.0, float(value)) for value in values.values())
    if total <= 0:
        raise ValueError("goal weights have no positive mass")
    normalized = {key: max(0.0, float(value)) / total for key, value in values.items()}
    correction_key = max(normalized)
    normalized[correction_key] += 1.0 - sum(normalized.values())
    return normalized


def initial_goal_weights(
    improvement_goal: float,
    liquidity_pressure: float,
    residential_attachment: float,
    policy_trust: float,
    household_size: int,
) -> Dict[str, float]:
    return normalize_weights({
        "housing_adequacy": 0.15 + 0.65 * improvement_goal,
        "financial_security": 0.20 + 0.75 * liquidity_pressure,
        "mobility": 0.10 + 0.60 * (1.0 - residential_attachment),
        "family_stability": 0.15 + 0.35 * residential_attachment + 0.05 * min(household_size, 5),
        "policy_opportunity": 0.10 + 0.50 * policy_trust,
    })


def policy_duration_rounds(policy_facts: Sequence[Mapping[str, Any]], current_round: int, default: float) -> Tuple[float, float]:
    values: List[float] = []
    evidenced = 0
    cutoff = ROUND_DATES[current_round]
    for fact in policy_facts:
        valid_to = fact.get("valid_to")
        if valid_to:
            end = date.fromisoformat(str(valid_to)[:10])
            values.append(clamp((end - cutoff).days / 91.25, 0.0, 12.0))
            evidenced += 1
    if not values:
        return default, 1.0
    return sum(values) / len(values), 1.0 - evidenced / max(1, len(policy_facts))


def policy_template_id(policy_facts: Sequence[Mapping[str, Any]]) -> str:
    if not policy_facts:
        return "POLICY-NONE"
    signature = []
    for fact in policy_facts:
        components = [
            {
                "instrument": component.get("instrument"),
                "direction": component.get("direction"),
                "target_groups": sorted(str(item) for item in component.get("target_groups") or []),
            }
            for component in fact.get("components") or []
        ]
        signature.append({
            "scope_level": fact.get("scope_level"),
            "policy_state": fact.get("policy_state"),
            "components": components,
        })
    return "PT-" + stable_hash(canonical_json(sorted(signature, key=canonical_json)))[:16]


def _quote_for_evidence(policy: Mapping[str, Any], evidence_id: str) -> str:
    quotes: List[str] = []
    for component in policy.get("components") or []:
        quote = str(component.get("evidence_quote") or "").strip()
        if quote and quote not in quotes:
            quotes.append(quote)
    for event in policy.get("action_timeline") or []:
        quote = str(event.get("evidence_quote") or "").strip()
        if quote and quote not in quotes:
            quotes.append(quote)
    if not quotes:
        return f"Policy evidence unit {evidence_id} is visible, but no verbatim claim is available."
    return " | ".join(quotes[:2])


def build_visible_evidence(
    packet: Mapping[str, Any],
    round_index: int,
    neighbor_ids: Sequence[str],
) -> List[Dict[str, Any]]:
    receipt_by_policy = {item["policy_episode_id"]: item for item in packet.get("policy_receipts") or []}
    evidence: List[Dict[str, Any]] = []
    used: set[str] = set()
    for policy in packet.get("policy_facts") or []:
        policy_id = str(policy.get("policy_episode_id"))
        receipt = receipt_by_policy.get(policy_id, {})
        ids = [str(item) for item in policy.get("source_evidence_unit_ids") or []]
        for evidence_id in ids:
            if evidence_id in used:
                continue
            used.add(evidence_id)
            evidence.append({
                "evidence_id": evidence_id,
                "visible_from": round_index,
                "expires_after": None,
                "source_id": policy_id,
                "channel": "official",
                "evidence_type": "policy_claim",
                "claim": _quote_for_evidence(policy, evidence_id),
                "reliability": round(float(receipt.get("trust", packet.get("information_state", {}).get("trust", 0.5))), 6),
                "policy_state": policy.get("policy_state"),
                "validity_evidenced": bool(policy.get("validity_evidenced", False)),
                "provenance": "source_policy_packet",
            })
    for segment in ("sale", "jeonse", "monthly_rent"):
        market = packet["market"][segment]
        evidence.append({
            "evidence_id": f"MARKET-{packet['profile']['gu']}-{segment}-R{round_index}",
            "visible_from": round_index,
            "expires_after": round_index,
            "source_id": f"market:{packet['profile']['gu']}:{segment}",
            "channel": "market",
            "evidence_type": "market_observation",
            "claim": (
                f"{segment}: unit_price_before_krw_m2={float(market['unit_price_before_krw_m2']):.2f}; "
                f"demand_pressure={float(market['demand_pressure']):.6f}; matches={int(market['matches'])}; "
                f"unmet_demand={int(market['unmet_demand'])}; inventory_end={int(market['inventory_end'])}"
            ),
            "reliability": 0.8,
            "provenance": "source_market_packet",
        })
    evidence.append({
        "evidence_id": f"NETWORK-{packet['household_id']}-R{round_index}",
        "visible_from": round_index,
        "expires_after": round_index,
        "source_id": "frozen_N3_induced_network",
        "channel": "neighbor",
        "evidence_type": "network_topology",
        "claim": f"Visible induced-network neighbor count={len(neighbor_ids)}; no neighbor action label is supplied.",
        "neighbor_count": len(neighbor_ids),
        "reliability": 0.6 if neighbor_ids else 0.3,
        "provenance": "frozen_stage_c_N3_edges",
    })
    return evidence


def build_memory(previous_packets: Sequence[Mapping[str, Any]], current_round: int, window: int) -> List[Dict[str, Any]]:
    memories: List[Dict[str, Any]] = []
    for packet in previous_packets:
        prior_round = int(str(packet["round_id"])[-1])
        info = packet["information_state"]
        for policy in packet.get("policy_facts") or []:
            policy_id = str(policy.get("policy_episode_id"))
            memories.append({
                "memory_id": f"policy:{policy_id}:R{prior_round}",
                "round_index": prior_round,
                "kind": "policy_evidence",
                "source_id": policy_id,
                "channel": "official",
                "content_ref": policy_id,
                "action": None,
                "success": None,
                "satisfaction": 0.5,
                "regret": 0.0,
                "credibility": clamp(float(info.get("trust", 0.5)) * (1.0 - float(info.get("misunderstanding", 0.0)))),
            })
        sale = packet["market"]["sale"]
        memories.append({
            "memory_id": f"market:{packet['profile']['gu']}:R{prior_round}",
            "round_index": prior_round,
            "kind": "market_observation",
            "source_id": f"market:{packet['profile']['gu']}",
            "channel": "market",
            "content_ref": f"sale_price={float(sale['unit_price_before_krw_m2']):.2f}",
            "action": None,
            "success": None,
            "satisfaction": 0.5,
            "regret": 0.0,
            "credibility": 0.8,
        })
    ranked = sorted(
        memories,
        key=lambda item: (
            math.exp(-0.18 * max(0, current_round - int(item["round_index"]))) * max(0.01, float(item["credibility"])),
            int(item["round_index"]),
            str(item["memory_id"]),
        ),
        reverse=True,
    )[:window]
    return sorted(ranked, key=lambda item: (int(item["round_index"]), str(item["memory_id"])))


def _liquid_assets(monthly_income: float, tenure: str, config: Mapping[str, Any]) -> float:
    if tenure == "owner":
        multiple = float(config["owner_equity_income_multiple"])
    elif tenure in {"jeonse", "monthly_rent"}:
        multiple = float(config["renter_savings_income_multiple"])
    else:
        multiple = float(config["other_savings_income_multiple"])
    return monthly_income * 12.0 * multiple


def build_household_state(
    packet: Mapping[str, Any],
    profile: Mapping[str, str],
    traits: Mapping[str, str],
    previous_packets: Sequence[Mapping[str, Any]],
    initialization: Mapping[str, Any],
) -> Dict[str, Any]:
    round_index = int(str(packet["round_id"])[-1])
    age = max(18, min(100, int(float(profile["head_age"]))))
    household_size = max(1, min(15, int(float(profile["household_size"]))))
    monthly_income = float(profile["income_midpoint_10k_krw_month"]) * 10000.0
    tenure = normalize_tenure(profile["tenure"])
    risk_tolerance = clamp(float(traits["risk_tolerance"]))
    migration_friction = clamp(float(traits["migration_friction"]))
    peer_sensitivity = clamp(float(traits["peer_sensitivity"]))
    digital_access = clamp(float(traits["digital_access_propensity"]))
    policy_interest = clamp(float(traits["policy_interest"]))
    married = str(profile["head_married"]).lower() == "true"

    income_score = clamp(float(profile["income_band"]) / 14.0)
    crowding = clamp((household_size - 2.0) / 4.0)
    tenure_need = {"owner": 0.15, "jeonse": 0.45, "monthly_rent": 0.70, "other": 0.60}[tenure]
    improvement_goal = clamp(0.45 * tenure_need + 0.35 * crowding + 0.20 * (1.0 - migration_friction))
    liquidity_pressure = clamp(0.90 - 0.75 * income_score + (0.10 if tenure == "monthly_rent" else 0.0))
    risk_perception = 1.0 - risk_tolerance
    loss_aversion = clamp(0.30 + 0.60 * risk_perception)
    policy_trust = clamp(0.25 + 0.45 * policy_interest + 0.15 * digital_access)

    attributes = {
        "household_id": packet["household_id"],
        "age": age,
        "household_size": household_size,
        "income_monthly": monthly_income,
        "initial_tenure": tenure,
        "dwelling_type": normalize_dwelling(profile["dwelling_type"]),
        "lifecycle_stage": lifecycle_stage(age, household_size, married),
        "improvement_goal": improvement_goal,
        "liquidity_pressure": liquidity_pressure,
        "loss_aversion": loss_aversion,
        "risk_perception": risk_perception,
        "residential_attachment": migration_friction,
        "policy_trust_tendency": policy_trust,
        "peer_sensitivity": peer_sensitivity,
    }

    info = packet["information_state"]
    current_sale = float(packet["market"]["sale"]["unit_price_before_krw_m2"])
    if previous_packets:
        prior_sale = float(previous_packets[-1]["market"]["sale"]["unit_price_before_krw_m2"])
        price_growth = max(-0.2, min(0.2, current_sale / prior_sale - 1.0)) if prior_sale else 0.0
        price_uncertainty = 0.25
    else:
        price_growth = 0.0
        price_uncertainty = 0.75
    policy_duration, duration_uncertainty = policy_duration_rounds(
        packet.get("policy_facts") or [],
        round_index,
        float(initialization["default_policy_duration_rounds"]),
    )
    affordability = clamp(0.10 + 0.80 * income_score - 0.15 * max(0.0, float(packet["market"]["sale"]["demand_pressure"])))
    official_trust = clamp(float(info.get("trust", 0.0))) if info.get("received") else policy_trust
    beta_prior = [float(value) for value in initialization["action_success_beta_prior"]]
    beliefs = {
        "price_growth_expectation": price_growth,
        "policy_eligibility_prob": clamp(float(info.get("eligibility_proxy", 0.0))),
        "affordability_prob": affordability,
        "channel_trust": {
            "official": official_trust,
            "relative": clamp(0.45 + 0.15 * peer_sensitivity),
            "neighbor": clamp(0.40 + 0.30 * peer_sensitivity),
            "online": clamp(0.25 + 0.45 * digital_access),
        },
        "action_success_prob": {action: 0.5 for action in ACTIONS},
        "action_success_counts": {action: list(beta_prior) for action in ACTIONS},
        "policy_duration_expectation": policy_duration,
        "uncertainty": {
            "price_growth_expectation": price_uncertainty,
            "policy_eligibility_prob": clamp(1.0 - float(info.get("comprehension", 0.0)) + 0.5 * float(info.get("misunderstanding", 0.0))),
            "affordability_prob": 0.5,
            "policy_duration_expectation": duration_uncertainty,
        },
    }
    goals = initial_goal_weights(improvement_goal, liquidity_pressure, migration_friction, policy_trust, household_size)
    memory = build_memory(previous_packets, round_index, int(initialization["memory_window"]))
    state = {
        "attributes": attributes,
        "beliefs": beliefs,
        "goals": goals,
        "memory": memory,
        "current_round": round_index,
        "tenure": tenure,
        "liquid_assets": _liquid_assets(monthly_income, tenure, initialization),
        "liquidity_pressure": liquidity_pressure,
        "satisfaction": 0.5,
        "regret": 0.0,
    }
    validate_household_state(state, int(initialization["memory_window"]))
    return state


def validate_household_state(state: Mapping[str, Any], memory_window: int = 12) -> None:
    model = HouseholdState(
        attributes=HouseholdAttributes(**state["attributes"]),
        beliefs=HouseholdBeliefs(**state["beliefs"]),
        goals=dict(state["goals"]),
        memory=[MemoryItem(**item) for item in state["memory"]],
        current_round=int(state["current_round"]),
        tenure=str(state["tenure"]),
        liquid_assets=float(state["liquid_assets"]),
        liquidity_pressure=float(state["liquidity_pressure"]),
        satisfaction=float(state["satisfaction"]),
        regret=float(state["regret"]),
    )
    model.validate(memory_window)


def assign_splits(gu_ids: Sequence[str], seed: int, pilot_count: int) -> Dict[str, str]:
    ranked = sorted(set(gu_ids), key=lambda gu: (stable_hash(seed, gu), gu))
    pilot = set(ranked[:pilot_count])
    return {gu: ("pilot" if gu in pilot else "development") for gu in ranked}


def build_candidate(
    packets: Sequence[Mapping[str, Any]],
    profiles: Mapping[str, Mapping[str, str]],
    traits: Mapping[str, Mapping[str, str]],
    neighbors: Mapping[str, Sequence[str]],
    config: Mapping[str, Any],
) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]], List[Dict[str, Any]]]:
    packet_households = {str(packet["household_id"]) for packet in packets}
    missing_profiles = sorted(packet_households - set(profiles))
    missing_traits = sorted(packet_households - set(traits))
    if missing_profiles or missing_traits:
        raise ValueError(f"missing source joins: profiles={len(missing_profiles)}, traits={len(missing_traits)}")

    by_household: Dict[str, List[Mapping[str, Any]]] = defaultdict(list)
    for packet in packets:
        by_household[str(packet["household_id"])].append(packet)
    for household_packets in by_household.values():
        household_packets.sort(key=lambda packet: int(str(packet["round_id"])[-1]))

    gu_ids = [str(packet["profile"]["gu"]) for packet in packets]
    split_by_gu = assign_splits(gu_ids, int(config["split"]["seed"]), int(config["split"]["pilot_gu_count"]))
    records: List[Dict[str, Any]] = []
    requests: List[Dict[str, Any]] = []
    for household_id in sorted(by_household):
        history: List[Mapping[str, Any]] = []
        for packet in by_household[household_id]:
            round_index = int(str(packet["round_id"])[-1])
            gu = str(packet["profile"]["gu"])
            split = split_by_gu[gu]
            world_id = f"WORLD-2013-{gu}"
            network_seed = int(stable_hash(config["split"]["seed"], world_id)[:12], 16)
            state = build_household_state(
                packet,
                profiles[household_id],
                traits[household_id],
                history,
                config["state_initialization"],
            )
            evidence = build_visible_evidence(packet, round_index, neighbors.get(household_id, []))
            record_id = f"V9-NAT-{household_id}-R{round_index}"
            record = {
                "record_id": record_id,
                "parent_sample_id": None,
                "household_id": household_id,
                "world_id": world_id,
                "network_seed": network_seed,
                "policy_template_id": policy_template_id(packet.get("policy_facts") or []),
                "round": round_index,
                "visible_cutoff": round_index,
                "queue_type": "natural",
                "split": split,
                "state": state,
                "visible_evidence": evidence,
            }
            request = {
                "record_id": record_id,
                "household_id": household_id,
                "round": round_index,
                "visible_cutoff": round_index,
                "household_state": json.loads(json.dumps(state, ensure_ascii=False)),
                "visible_evidence": json.loads(json.dumps(evidence, ensure_ascii=False)),
                "allowed_actions": list(packet["allowed_actions"]),
                "task_definition": str(config["task_definition"]),
            }
            validate_reference_request(request)
            if find_banned_keys(record) or find_banned_keys(request):
                raise ValueError(f"banned method field leaked into {record_id}")
            records.append(record)
            requests.append(request)
            history.append(packet)

    assert_group_disjoint(records, ("household_id", "world_id", "network_seed"))
    world_manifest = []
    for gu in sorted(set(gu_ids)):
        household_ids = sorted(household_id for household_id in by_household if profiles[household_id]["canonical_gu_id"] == gu)
        world_id = f"WORLD-2013-{gu}"
        world_manifest.append({
            "world_id": world_id,
            "spatial_cluster": gu,
            "split": split_by_gu[gu],
            "network_seed": int(stable_hash(config["split"]["seed"], world_id)[:12], 16),
            "household_count": len(household_ids),
            "record_count": len(household_ids) * 4,
            "induced_N3_edge_count": sum(1 for household_id in household_ids for neighbor in neighbors.get(household_id, []) if household_id < neighbor),
            "interpretation": "Spatial cluster for development replay; not an independently generated world replicate.",
        })
    return records, requests, world_manifest


def structural_fingerprint(record: Mapping[str, Any]) -> str:
    state = json.loads(json.dumps(record["state"], ensure_ascii=False))
    state["attributes"].pop("household_id", None)
    for item in state["memory"]:
        item.pop("memory_id", None)
    value = {
        "round": record["round"],
        "policy_template_id": record["policy_template_id"],
        "state": state,
        "evidence_types": [item.get("evidence_type") for item in record["visible_evidence"]],
    }
    return stable_hash(canonical_json(value))


def audit_candidate(records: Sequence[Mapping[str, Any]], requests: Sequence[Mapping[str, Any]]) -> Dict[str, Any]:
    if len(records) != len(requests):
        raise ValueError("record/request cardinality mismatch")
    ids = [str(record["record_id"]) for record in records]
    household_rounds: Dict[str, set[int]] = defaultdict(set)
    future_evidence = 0
    banned_hits: List[str] = []
    split_groups: Dict[str, Dict[str, set[Any]]] = {
        field: defaultdict(set) for field in ("household_id", "world_id", "network_seed", "policy_template_id")
    }
    fingerprints: Dict[str, set[str]] = defaultdict(set)
    for record, request in zip(records, requests):
        household_rounds[str(record["household_id"])].add(int(record["round"]))
        banned_hits.extend(f"{record['record_id']}:{hit}" for hit in find_banned_keys(request))
        for item in request["visible_evidence"]:
            if int(item["visible_from"]) > int(request["visible_cutoff"]):
                future_evidence += 1
        for field in split_groups:
            split_groups[field][str(record["split"])].add(record[field])
        fingerprints[str(record["split"])].add(structural_fingerprint(record))
    overlap = {}
    for field, by_split in split_groups.items():
        overlap[field] = len(by_split.get("development", set()) & by_split.get("pilot", set()))
    near_duplicate_overlap = len(fingerprints.get("development", set()) & fingerprints.get("pilot", set()))
    return {
        "record_count": len(records),
        "reference_request_count": len(requests),
        "unique_record_ids": len(set(ids)),
        "unique_households": len(household_rounds),
        "households_with_exact_rounds_1_to_4": sum(rounds == {1, 2, 3, 4} for rounds in household_rounds.values()),
        "split_record_counts": {split: sum(record["split"] == split for record in records) for split in ("development", "pilot", "locked_test")},
        "split_household_counts": {split: len(split_groups["household_id"].get(split, set())) for split in ("development", "pilot", "locked_test")},
        "group_overlap_development_vs_pilot": overlap,
        "structural_near_duplicate_overlap": near_duplicate_overlap,
        "future_evidence_count": future_evidence,
        "banned_key_hits": banned_hits,
        "formal_group_isolation_gate": overlap["household_id"] == 0 and overlap["world_id"] == 0 and overlap["network_seed"] == 0,
        "formal_policy_template_isolation_gate": overlap["policy_template_id"] == 0,
        "formal_locked_test_gate": False,
        "formal_evaluation_eligible": False,
        "blocking_reasons": [
            "Development and pilot share national policy templates; an explicit policy-OOD axis must be approved instead of silently forcing template disjointness.",
            "The 2013 source has been used during development and is not a locked out-of-time test.",
            "GU clusters are spatial replay clusters, not independent world replications.",
            "No independent expert or different-model-family reference labels are attached.",
        ],
    }
