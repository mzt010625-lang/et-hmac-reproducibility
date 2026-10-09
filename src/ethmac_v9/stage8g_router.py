"""Frozen coarse prefilter used by both isolated Stage 8G hybrid routes."""
from __future__ import annotations

from typing import Any

from .stage8d_contract import _market_inventory, base_action
from .stage8d_router import route_reasons as exact_route_reasons


def _conflicts(record: dict[str, Any]) -> int:
    ontology = record.get("ontology", {})
    return sum(int(ontology.get(key) or 0) for key in (
        "missing_evidence_count", "evidence_conflict_count", "rule_conflict_count"
    ))


def coarse_route_reasons(record: dict[str, Any]) -> list[str]:
    """Return an intentionally broad candidate set before JEV refinement.

    Exact finite exceptions and near-threshold/cross-market distractors are
    both admitted. Route A sends every candidate to L2; Route B asks an
    isolated compact JEV to separate them before independently calling L2.
    """
    exact = exact_route_reasons(record)
    if exact:
        return ["EXACT_" + reason for reason in exact]

    base = base_action(record)
    allowed = set(record.get("allowed", []))
    reasons: list[str] = []
    if base.startswith("search_") and "wait" in allowed:
        inventory = _market_inventory(record, base)
        any_market_zero = any(
            item.get("evidence_type") == "market_observation"
            and "inventory_end=0" in str(item.get("claim") or "")
            for item in record.get("evidence", [])
        )
        if inventory == 1:
            reasons.append("NEAR_ZERO_MATCHING_MARKET")
        elif inventory is not None and inventory > 0 and any_market_zero:
            reasons.append("ZERO_ONLY_IN_OTHER_MARKET")

    ontology = record.get("ontology", {})
    if (
        "wait" in allowed
        and ontology.get("multistep_dependency")
        and _conflicts(record) == 1
    ):
        reasons.append("NEAR_CONFLICT_THRESHOLD")

    for relation in record.get("policy_applicability", []):
        if isinstance(relation, dict) and relation.get("status") in {
            "MATCHED_AMBIGUOUS", "NEAR_MATCH_AMBIGUOUS"
        }:
            reasons.append("POLICY_APPLICABILITY_CANDIDATE")
            break
    return reasons


def should_prefilter(record: dict[str, Any]) -> bool:
    return bool(coarse_route_reasons(record))
