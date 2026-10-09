from __future__ import annotations

import hashlib
import json
from copy import deepcopy
from pathlib import Path
from typing import Any, Dict, Iterable, List, Tuple

from .models import ACTIONS

OUTPUT_KEYS = {
    "schema_version", "record_id", "action_probabilities",
    "fast_action_error_probability_raw", "l2_correction_probability_raw",
    "l2_harm_probability_raw", "semantic_conflict_score_raw", "novelty_score_raw",
    "confidence_raw", "should_escalate_raw", "route_reasons", "evidence_ids",
}
REASON_CODES = {
    "L1_LOW_MARGIN", "RULE_CONFLICT", "EVIDENCE_CONFLICT", "NOVEL_STATE",
    "NETWORK_DEPENDENCE", "MULTISTEP_DEPENDENCE", "HIGH_STAKES",
    "MISSING_EVIDENCE", "FAST_PATH_STABLE", "HARD_CONSTRAINT_RISK",
}


def sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def sha256_file(path: Path) -> str:
    return sha256_bytes(path.read_bytes())


def load_records(path: Path) -> List[Dict[str, Any]]:
    if path.suffix.lower() == ".jsonl":
        rows = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]
    else:
        parsed = json.loads(path.read_text(encoding="utf-8"))
        rows = parsed if isinstance(parsed, list) else [parsed]
    if not rows or any(not isinstance(row, dict) for row in rows):
        raise ValueError("input must contain one JSON object, a JSON array, or JSONL objects")
    for row in rows:
        validate_jev_input(row)
    return rows


def validate_jev_input(record: Dict[str, Any]) -> None:
    required = {
        "record_id", "household_id", "round", "visible_cutoff", "allowed_actions",
        "household_state", "visible_evidence", "l1_output", "ontology_features", "router_context",
    }
    missing = sorted(required - set(record))
    if missing:
        raise ValueError("JEV input misses fields: " + ", ".join(missing))
    if int(record["round"]) > int(record["visible_cutoff"]):
        raise ValueError("round cannot exceed visible_cutoff")
    allowed = set(record["allowed_actions"])
    if not allowed or allowed - set(ACTIONS):
        raise ValueError("allowed_actions is empty or contains an unknown action")
    if record["l1_output"].get("recommended_action") not in allowed:
        raise ValueError("L1 action is outside allowed_actions")
    for evidence in record["visible_evidence"]:
        if int(evidence["visible_from"]) > int(record["visible_cutoff"]):
            raise ValueError("future evidence found in JEV input")


def normalize_jev_output(
    output: Dict[str, Any],
    source: Dict[str, Any],
) -> Tuple[Dict[str, Any], Dict[str, Any]]:
    """Canonically zero-fill only omitted actions that are hard-blocked in this record.

    Some JSON-only models return probabilities only for ``allowed_actions`` even
    when the prompt requests all seven action keys.  Filling an omitted blocked
    action with zero is lossless.  Missing legal actions, unknown action keys,
    malformed probability objects, and invalid probability values are never
    repaired here; the normal validator must reject them.

    The raw provider response remains in ``responses.jsonl``.  The returned
    metadata is written next to the normalized parsed output so the repair is
    visible and auditable.
    """
    normalized = deepcopy(output)
    probabilities = normalized.get("action_probabilities")
    if not isinstance(probabilities, dict):
        raise ValueError("action_probabilities must be a JSON object")

    provided = set(probabilities)
    canonical = set(ACTIONS)
    unknown = sorted(provided - canonical)
    if unknown:
        raise ValueError("action_probabilities contains unknown actions: " + ", ".join(unknown))

    missing = canonical - provided
    allowed = set(source["allowed_actions"])
    missing_allowed = [action for action in ACTIONS if action in missing and action in allowed]
    if missing_allowed:
        raise ValueError(
            "action_probabilities omits allowed actions and cannot be repaired: "
            + ", ".join(missing_allowed)
        )

    filled = [action for action in ACTIONS if action in missing]
    for action in filled:
        probabilities[action] = 0.0
    return normalized, {
        "applied": bool(filled),
        "strategy": "ZERO_FILL_OMITTED_HARD_BLOCKED_ACTIONS" if filled else "NONE",
        "filled_zero_actions": filled,
        "raw_action_keys": [action for action in ACTIONS if action in provided],
    }


def validate_jev_output(output: Dict[str, Any], source: Dict[str, Any]) -> None:
    if set(output) != OUTPUT_KEYS:
        missing = sorted(OUTPUT_KEYS - set(output))
        extra = sorted(set(output) - OUTPUT_KEYS)
        raise ValueError(f"JEV output keys mismatch; missing={missing}, extra={extra}")
    if output["schema_version"] != "jev_output_v1":
        raise ValueError("unexpected JEV schema_version")
    if output["record_id"] != source["record_id"]:
        raise ValueError("JEV output record_id does not match input")
    probabilities = output["action_probabilities"]
    if set(probabilities) != set(ACTIONS):
        raise ValueError("action_probabilities must contain exactly seven actions")
    values = [float(probabilities[action]) for action in ACTIONS]
    if any(value < 0 or value > 1 for value in values) or abs(sum(values) - 1.0) > 1e-3:
        raise ValueError("action probabilities must be in [0,1] and sum to 1")
    for field in (
        "fast_action_error_probability_raw", "l2_correction_probability_raw",
        "l2_harm_probability_raw", "semantic_conflict_score_raw", "novelty_score_raw",
        "confidence_raw",
    ):
        value = float(output[field])
        if not 0 <= value <= 1:
            raise ValueError(f"{field} must be in [0,1]")
    if not isinstance(output["should_escalate_raw"], bool):
        raise ValueError("should_escalate_raw must be boolean")
    reasons = output["route_reasons"]
    if not isinstance(reasons, list) or not 1 <= len(reasons) <= 5 or set(reasons) - REASON_CODES:
        raise ValueError("route_reasons is empty, too long, or contains unknown codes")
    if len(reasons) != len(set(reasons)):
        raise ValueError("route_reasons contains duplicate codes")
    fast_stable = "FAST_PATH_STABLE" in reasons
    if fast_stable and len(reasons) != 1:
        raise ValueError("FAST_PATH_STABLE must be the only route reason")
    if fast_stable == bool(output["should_escalate_raw"]):
        raise ValueError("FAST_PATH_STABLE must mean should_escalate_raw=false and vice versa")
    visible_ids = {str(row["evidence_id"]) for row in source["visible_evidence"]}
    evidence_ids = output["evidence_ids"]
    if not isinstance(evidence_ids, list) or len(evidence_ids) > 5 or set(evidence_ids) - visible_ids:
        raise ValueError("JEV output cites unavailable evidence")


def append_jsonl(path: Path, value: Dict[str, Any]) -> None:
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n")
