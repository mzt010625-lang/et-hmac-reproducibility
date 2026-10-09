from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List, Mapping, Sequence, Set

from .api_client import ChatAPIConfig
from .validation import validate_reference_request


RATIONALE_CODES: Set[str] = {
    "AFFORDABILITY", "LIQUIDITY", "RISK", "GOAL_FIT",
    "EVIDENCE", "MEMORY", "UNCERTAINTY", "LEGALITY",
}


def load_reference_smoke_cases(path: Path) -> List[Dict[str, Any]]:
    rows = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]
    if not rows:
        raise ValueError("reference smoke input is empty")
    seen = set()
    for row in rows:
        if set(row) != {"case_id", "reference_request"}:
            raise ValueError("reference smoke row must contain only case_id and reference_request")
        case_id = str(row["case_id"])
        if case_id in seen:
            raise ValueError("duplicate reference smoke case_id")
        seen.add(case_id)
        validate_reference_request(row["reference_request"])
        if "JEV" in json.dumps(row["reference_request"], ensure_ascii=False).upper():
            raise ValueError("method-specific JEV identifier leaked into reference request")
    return rows


def build_reference_payload(
    config: ChatAPIConfig,
    system_prompt: str,
    reference_request: Mapping[str, Any],
) -> Dict[str, Any]:
    validate_reference_request(dict(reference_request))
    return {
        "model": config.model,
        "messages": [
            {"role": "system", "content": system_prompt},
            {
                "role": "user",
                "content": "请对以下当前可见决策机会进行盲标注，并严格返回JSON：\n"
                + json.dumps(reference_request, ensure_ascii=False, sort_keys=True, separators=(",", ":")),
            },
        ],
        "temperature": config.temperature,
        "max_tokens": config.max_tokens,
        "stream": config.stream,
        **({"response_format": {"type": "json_object"}} if config.response_format_json_object else {}),
    }


def validate_reference_annotation(
    annotation: Mapping[str, Any],
    request: Mapping[str, Any],
    annotator_id: str,
) -> None:
    required = {
        "schema_version", "record_id", "annotator_id", "decision_status",
        "best_action", "acceptable_actions", "confidence", "evidence_ids",
        "rationale_codes", "ambiguity_reason",
    }
    if set(annotation) != required:
        raise ValueError(f"annotation keys mismatch: {sorted(set(annotation) ^ required)}")
    if annotation["schema_version"] != "reference_annotation_v1":
        raise ValueError("invalid reference annotation schema_version")
    if annotation["record_id"] != request["record_id"]:
        raise ValueError("annotation record_id mismatch")
    if annotation["annotator_id"] != annotator_id:
        raise ValueError("annotation annotator_id mismatch")
    status = annotation["decision_status"]
    if status not in {"labeled", "abstain"}:
        raise ValueError("invalid decision_status")
    allowed = set(request["allowed_actions"])
    acceptable = annotation["acceptable_actions"]
    if not isinstance(acceptable, list) or len(acceptable) != len(set(acceptable)):
        raise ValueError("acceptable_actions must be a unique list")
    if set(acceptable) - allowed:
        raise ValueError("acceptable_actions contains an illegal action")
    best = annotation["best_action"]
    if status == "labeled":
        if best not in allowed or best not in acceptable:
            raise ValueError("labeled annotation requires legal best_action included in acceptable_actions")
        if annotation["ambiguity_reason"] is not None:
            raise ValueError("labeled annotation must set ambiguity_reason to null")
    else:
        if best is not None:
            raise ValueError("abstain annotation must set best_action to null")
        if not isinstance(annotation["ambiguity_reason"], str) or not annotation["ambiguity_reason"].strip():
            raise ValueError("abstain annotation requires ambiguity_reason")
    confidence = annotation["confidence"]
    if isinstance(confidence, bool) or not isinstance(confidence, (int, float)) or not 0 <= float(confidence) <= 1:
        raise ValueError("confidence must be in [0, 1]")
    visible_ids = {str(item["evidence_id"]) for item in request["visible_evidence"]}
    evidence_ids = annotation["evidence_ids"]
    if not isinstance(evidence_ids, list) or len(evidence_ids) > 5 or len(evidence_ids) != len(set(evidence_ids)):
        raise ValueError("evidence_ids must be a unique list with at most five entries")
    if set(evidence_ids) - visible_ids:
        raise ValueError("annotation cites invisible evidence")
    rationale = annotation["rationale_codes"]
    if not isinstance(rationale, list) or not 1 <= len(rationale) <= 5 or len(rationale) != len(set(rationale)):
        raise ValueError("rationale_codes must contain one to five unique entries")
    if set(rationale) - RATIONALE_CODES:
        raise ValueError("annotation contains an unknown rationale code")


def neutralize_interface_record(
    source: Mapping[str, Any],
    *,
    neutral_index: int,
    prefix: str,
    task_definition: str,
) -> Dict[str, Any]:
    record_id = f"{prefix}-{neutral_index:03d}"
    household_id = f"HH-{prefix}-{neutral_index:03d}"
    request = {
        "record_id": record_id,
        "household_id": household_id,
        "round": int(source["round"]),
        "visible_cutoff": int(source["visible_cutoff"]),
        "household_state": json.loads(json.dumps(source["household_state"], ensure_ascii=False)),
        "visible_evidence": json.loads(json.dumps(source["visible_evidence"], ensure_ascii=False)),
        "allowed_actions": list(source["allowed_actions"]),
        "task_definition": task_definition,
    }
    validate_reference_request(request)
    return request
