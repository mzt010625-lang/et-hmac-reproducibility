"""Zero-token ontology/event router for the Stage 8D shared contract.

The router is deliberately conservative: it identifies records on which one
of the *frozen, externally testable* semantic-exception predicates can fire.
It never predicts the final action and never vetoes a valid L2 decision.
"""
from __future__ import annotations

from typing import Any

from .stage8d_contract import _market_inventory, base_action


def _conflict_count(record: dict[str, Any]) -> int:
    ontology = record.get("ontology", {})
    return sum(int(ontology.get(key) or 0) for key in (
        "missing_evidence_count", "evidence_conflict_count", "rule_conflict_count"
    ))


def route_reasons(record: dict[str, Any]) -> list[str]:
    """Return auditable reasons for invoking L2, without using an L2 label.

    Policy routing requires a precompiled, machine-readable applicability
    relation.  Legacy free text alone is not a safe household-level trigger;
    it must first be compiled once per policy and then joined to households.
    """
    base = base_action(record)
    allowed = set(record.get("allowed", []))
    reasons: list[str] = []

    if base.startswith("search_") and "wait" in allowed:
        if _market_inventory(record, base) == 0:
            reasons.append("MARKET_ZERO_CANDIDATE")

    if "wait" in allowed and any(
        item.get("action") == base and item.get("success") is False
        for item in record.get("memory", [])
    ):
        reasons.append("RECENT_FAILURE_CANDIDATE")

    ontology = record.get("ontology", {})
    if (
        "wait" in allowed
        and ontology.get("multistep_dependency")
        and _conflict_count(record) >= 2
    ):
        reasons.append("CONFLICT_WAIT_CANDIDATE")

    # This field is intentionally absent from the legacy Stage 8C records.
    # It is produced by the planned once-per-policy ontology compiler, not by
    # inspecting the full-L2 answer for the current household.
    for relation in record.get("policy_applicability", []):
        if not isinstance(relation, dict):
            continue
        if relation.get("status") != "MATCHED_AMBIGUOUS":
            continue
        if relation.get("base_action") not in {None, base}:
            continue
        if relation.get("candidate_action") not in allowed:
            continue
        reasons.append("POLICY_SEMANTIC_CANDIDATE")
        break

    return reasons


def should_route_l2(record: dict[str, Any]) -> bool:
    return bool(route_reasons(record))
