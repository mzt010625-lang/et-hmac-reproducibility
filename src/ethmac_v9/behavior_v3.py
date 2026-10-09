"""Prompt compilation, validation, and consensus guard for Behavior v3."""
from __future__ import annotations

import json
import re
from typing import Any, Optional

from .behavior_prior_v3 import infer as infer_prior

AUDIT_KEYS = {"v", "id", "identity_fit", "context_fit", "action_vote",
              "confidence", "override_request", "override_code", "evidence",
              "belief_updates", "memory_updates"}
IDENTITY = {"SUPPORTS_PRIOR", "CONFLICTS_PRIOR", "NEUTRAL"}
CONTEXT = {"SUPPORTS_PRIOR", "SUPPORTS_ALTERNATIVE", "NEUTRAL"}
OVERRIDES = {"NONE", "MARKET_INFEASIBLE", "RECENT_MEMORY_FAILURE",
             "VALID_POLICY_BARRIER", "VALID_POLICY_ENABLEMENT"}
BELIEF_UPDATES = {"REASSESS_ELIGIBILITY", "REASSESS_AFFORDABILITY",
                  "UPDATE_PRICE_EXPECTATION", "UPDATE_SOURCE_TRUST"}
MEMORY_UPDATES = {"RECORD_SEARCH_OUTCOME", "RECORD_TRANSACTION_OUTCOME",
                  "NO_DIRECT_UPDATE"}
REQUIRED_SYSTEM_MODULES = (
    "# 角色与任务", "# 信息边界", "# Agent认知结构",
    "# 四通道审查与信念—行动路径", "# 审查顺序",
    "# 状态更新职责", "# 输出契约",
)
REQUIRED_USER_MARKERS = (
    "{{AGENT_STATE_JSON}}", "{{RULE_PRIOR_JSON}}", "{{EVENT_CONTEXT_JSON}}",
    "<agent_state>", "<rule_prior>", "<event_context>",
)


def validate_prompt_structure(system_prompt: str, user_template: str) -> None:
    missing_system = [item for item in REQUIRED_SYSTEM_MODULES if item not in system_prompt]
    missing_user = [item for item in REQUIRED_USER_MARKERS if item not in user_template]
    if missing_system or missing_user:
        raise ValueError(
            "incomplete behavior prompt structure; missing_system="
            + repr(missing_system) + "; missing_user=" + repr(missing_user)
        )


def compile_user_message(template: str, record: dict) -> tuple[str, dict]:
    prior = infer_prior(record)
    agent = {key: record[key] for key in ("id", "round", "visible_cutoff", "allowed",
             "family", "state", "beliefs", "goals", "memory", "memory_omitted")
             if key in record}
    context = {"evidence": record.get("evidence", []), "ontology": record.get("ontology", {})}
    message = template.replace("{{AGENT_STATE_JSON}}", json.dumps(agent, ensure_ascii=False,
        sort_keys=True, separators=(",", ":")))
    message = message.replace("{{RULE_PRIOR_JSON}}", json.dumps(prior, ensure_ascii=False,
        sort_keys=True, separators=(",", ":")))
    message = message.replace("{{EVENT_CONTEXT_JSON}}", json.dumps(context, ensure_ascii=False,
        sort_keys=True, separators=(",", ":")))
    return message, prior


def validate_audit(output: dict, record: dict, prior: dict) -> None:
    if not isinstance(output, dict) or set(output) != AUDIT_KEYS:
        raise ValueError("behavior audit keys mismatch")
    if output["v"] != "behavior_audit_v3" or output["id"] != record["id"]:
        raise ValueError("behavior audit version/id mismatch")
    if output["identity_fit"] not in IDENTITY or output["context_fit"] not in CONTEXT:
        raise ValueError("invalid fit code")
    if output["action_vote"] not in record["allowed"]:
        raise ValueError("action vote is illegal")
    confidence = output["confidence"]
    if isinstance(confidence, bool) or not isinstance(confidence, (int, float)) or not 0 <= confidence <= 1:
        raise ValueError("confidence must be in [0,1]")
    if type(output["override_request"]) is not bool or output["override_code"] not in OVERRIDES:
        raise ValueError("invalid override fields")
    if output["override_request"]:
        if output["override_code"] == "NONE" or output["action_vote"] == prior["action"] or not output["evidence"]:
            raise ValueError("override request lacks a different action, reason, or evidence")
    elif output["override_code"] != "NONE" or output["action_vote"] != prior["action"]:
        raise ValueError("non-override must preserve prior action and NONE code")
    refs = {str(x["ref"]) for x in record.get("evidence", [])}
    ev = output["evidence"]
    if (not isinstance(ev, list) or len(ev) > 4 or len(ev) != len(set(ev))
            or any(not isinstance(x, str) for x in ev) or set(ev) - refs):
        raise ValueError("invalid evidence references")
    for field, allowed in (("belief_updates", BELIEF_UPDATES), ("memory_updates", MEMORY_UPDATES)):
        value = output[field]
        if (not isinstance(value, list) or len(value) != len(set(value))
                or any(not isinstance(x, str) for x in value) or set(value) - allowed):
            raise ValueError("invalid " + field)
    if "NO_DIRECT_UPDATE" in output["memory_updates"] and len(output["memory_updates"]) != 1:
        raise ValueError("NO_DIRECT_UPDATE must be exclusive")


def _market_inventory(record: dict, action: str) -> Optional[float]:
    target = {"search_buy": "sale", "search_jeonse": "jeonse",
              "search_monthly_rent": "monthly_rent"}.get(action)
    if target is None:
        return None
    values = []
    for evidence in record.get("evidence", []):
        claim = str(evidence.get("claim") or "")
        if evidence.get("evidence_type") != "market_observation" or not claim.startswith(target + ":"):
            continue
        match = re.search(r"inventory_end=(-?\d+(?:\.\d+)?)", claim)
        if match:
            values.append(float(match.group(1)))
    return values[0] if len(values) == 1 else None


def _recent_failure(record: dict, action: str) -> bool:
    candidates = [m for m in record.get("memory", []) if m.get("action") == action and m.get("success") is not None]
    if not candidates:
        return False
    latest = max(candidates, key=lambda m: int(m.get("round_index") or 0))
    return latest.get("success") is False


def locally_verifiable_override(record: dict, prior: dict, audit: dict) -> bool:
    if not audit["override_request"]:
        return False
    code = audit["override_code"]
    if code == "MARKET_INFEASIBLE":
        inventory = _market_inventory(record, prior["action"])
        return inventory is not None and inventory <= 0
    if code == "RECENT_MEMORY_FAILURE":
        return _recent_failure(record, prior["action"])
    # Policy semantics are logged for later adjudication but not automatically
    # trusted by the stability-first v3 guard.
    return False


def combine_consensus(record: dict, prior: dict, audits: list[dict]) -> dict:
    if len(audits) != 2:
        raise ValueError("the v3 full-call baseline requires two blind audits")
    for audit in audits:
        validate_audit(audit, record, prior)
    same_override = (
        all(audit["override_request"] for audit in audits)
        and audits[0]["action_vote"] == audits[1]["action_vote"]
        and audits[0]["override_code"] == audits[1]["override_code"]
        and all(locally_verifiable_override(record, prior, audit) for audit in audits)
    )
    final = audits[0]["action_vote"] if same_override else prior["action"]
    return {
        "v": "behavior_decision_v3",
        "id": record["id"],
        "prior_action": prior["action"],
        "final_action": final,
        "source": "LLM_CONSENSUS_OVERRIDE" if same_override else "DETERMINISTIC_PRIOR",
        "raw_audit_agreement": audits[0]["action_vote"] == audits[1]["action_vote"],
        "override_committed": same_override,
        "hard_case": prior["hard_case"],
    }
