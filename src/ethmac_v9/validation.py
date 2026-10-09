from __future__ import annotations

from typing import Any, Dict, Iterable, List, Set

REFERENCE_BANNED_KEYS: Set[str] = {
    "l0_action", "l1_action", "fast_action", "local_action", "prediction",
    "recommended_action", "semantic_scorecard", "action_scores", "rule_scores",
    "rule_ids", "route", "router_decision", "router_score", "jev_output",
    "l2_action", "final_action", "reference_action_candidate", "target_action",
    "expected_action", "candidate_label",
}


def find_banned_keys(value: Any, path: str = "$") -> List[str]:
    hits: List[str] = []
    if isinstance(value, dict):
        for key, child in value.items():
            child_path = f"{path}.{key}"
            if key.lower() in REFERENCE_BANNED_KEYS:
                hits.append(child_path)
            hits.extend(find_banned_keys(child, child_path))
    elif isinstance(value, list):
        for index, child in enumerate(value):
            hits.extend(find_banned_keys(child, f"{path}[{index}]"))
    return hits


def validate_reference_request(payload: Dict[str, Any]) -> None:
    hits = find_banned_keys(payload)
    if hits:
        raise ValueError("reference request contains banned fields: " + ", ".join(hits))
    required = {
        "record_id", "household_id", "round", "visible_cutoff",
        "household_state", "visible_evidence", "allowed_actions", "task_definition",
    }
    missing = sorted(required - set(payload))
    if missing:
        raise ValueError("reference request misses fields: " + ", ".join(missing))
    if payload["round"] > payload["visible_cutoff"]:
        raise ValueError("round cannot exceed visible_cutoff")
    for evidence in payload["visible_evidence"]:
        if int(evidence["visible_from"]) > int(payload["visible_cutoff"]):
            raise ValueError("future evidence in reference request")


def assert_group_disjoint(rows: Iterable[Dict[str, Any]], fields: Iterable[str]) -> None:
    for field in fields:
        owner: Dict[Any, str] = {}
        for row in rows:
            value = row.get(field)
            if value is None:
                continue
            split = row["split"]
            if value in owner and owner[value] != split:
                raise ValueError(f"{field}={value!r} crosses {owner[value]} and {split}")
            owner[value] = split

