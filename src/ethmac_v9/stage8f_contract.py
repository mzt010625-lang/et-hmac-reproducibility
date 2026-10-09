"""Stage 8F contract with machine-readable policy applicability guards."""
from __future__ import annotations

from .stage8d_contract import REQUIRED, base_action, resolve_output as resolve_v7


def _policy_relation(output: dict, record: dict) -> dict | None:
    effect = "BLOCK" if output["override_code"] == "POLICY_BLOCK" else "ENABLE"
    for relation in record.get("policy_applicability", []):
        if not isinstance(relation, dict):
            continue
        if relation.get("status") != "MATCHED_AMBIGUOUS" or relation.get("effect") != effect:
            continue
        if relation.get("base_action") not in {None, output["base_action"]}:
            continue
        if relation.get("candidate_action") != output["action"]:
            continue
        if relation.get("source_ref") not in output["evidence"]:
            continue
        return relation
    return None


def resolve_output(output: dict, record: dict) -> dict:
    if not isinstance(output, dict) or set(output) != REQUIRED:
        raise ValueError("L2 v9 output keys mismatch")
    if output.get("v") != "l2_semantic_exception_v9" or output.get("id") != record["id"]:
        raise ValueError("L2 v9 version/id mismatch")
    translated = dict(output)
    translated["v"] = "l2_semantic_exception_v7"
    resolved = resolve_v7(translated, record)
    resolved["raw_output"] = output
    if output["override_code"] in {"POLICY_BLOCK", "POLICY_ENABLE"} and resolved["guard_accepted"]:
        if _policy_relation(output, record) is None:
            return {
                "raw_output": output,
                "guard_accepted": False,
                "guard_reason": "policy override lacks a matching machine-readable applicability relation",
                "final_action": base_action(record),
                "final_source": "BASE_FAILSAFE_INVALID_L2",
            }
    return resolved


__all__ = ["base_action", "resolve_output"]
