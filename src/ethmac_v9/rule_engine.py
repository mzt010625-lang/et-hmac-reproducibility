from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Sequence, Set

from .models import ACTIONS, HouseholdState


@dataclass(frozen=True)
class RuleTrace:
    rule_id: str
    rule_type: str
    status: str
    reason: str
    affected_actions: List[str]
    evidence_ids: List[str]


@dataclass
class InferenceResult:
    recommended_action: str
    allowed_actions: List[str]
    blocked_actions: List[str]
    action_scores: Dict[str, float]
    active_rule_ids: List[str]
    suppressed_rule_ids: List[str]
    trace: List[RuleTrace]

    def to_dict(self) -> Dict[str, Any]:
        return {
            "recommended_action": self.recommended_action,
            "allowed_actions": self.allowed_actions,
            "blocked_actions": self.blocked_actions,
            "action_scores": self.action_scores,
            "active_rule_ids": self.active_rule_ids,
            "suppressed_rule_ids": self.suppressed_rule_ids,
            "trace": [asdict(row) for row in self.trace],
        }


def _lookup(root: Any, dotted_path: str) -> Any:
    value = root
    for part in dotted_path.split("."):
        if isinstance(value, dict):
            if part not in value:
                return None
            value = value[part]
        else:
            if not hasattr(value, part):
                return None
            value = getattr(value, part)
    return value


def _condition_matches(root: Dict[str, Any], condition: Dict[str, Any]) -> bool:
    actual = _lookup(root, condition["path"])
    expected = condition.get("value")
    op = condition["op"]
    if op == "eq":
        return actual == expected
    if op == "ne":
        return actual != expected
    if actual is None:
        return False
    if op == "ge":
        return actual >= expected
    if op == "gt":
        return actual > expected
    if op == "le":
        return actual <= expected
    if op == "lt":
        return actual < expected
    if op == "in":
        return actual in expected
    if op == "contains":
        return expected in actual
    raise ValueError(f"unsupported rule operator: {op}")


class DefeasibleRuleEngine:
    def __init__(self, config: Dict[str, Any]) -> None:
        self.version = config["version"]
        self.tie_break_order: List[str] = config["tie_break_order"]
        self.rules: List[Dict[str, Any]] = sorted(
            config["rules"], key=lambda rule: (-int(rule["priority"]), rule["id"])
        )
        ids = [rule["id"] for rule in self.rules]
        if len(ids) != len(set(ids)):
            raise ValueError("rule IDs must be unique")

    @classmethod
    def from_file(cls, path: Path) -> "DefeasibleRuleEngine":
        return cls(json.loads(path.read_text(encoding="utf-8")))

    def infer(
        self,
        state: HouseholdState,
        context: Optional[Dict[str, Any]] = None,
        allowed_actions: Optional[Iterable[str]] = None,
        evidence_ids: Optional[Sequence[str]] = None,
    ) -> InferenceResult:
        context = dict(context or {})
        root = {"state": state, "context": context}
        explicit_allowed: Set[str] = set(allowed_actions or ACTIONS)
        unknown = explicit_allowed - set(ACTIONS)
        if unknown:
            raise ValueError(f"unknown actions in allowed_actions: {sorted(unknown)}")
        evidence = list(evidence_ids or [])

        matched: Dict[str, Dict[str, Any]] = {}
        trace: List[RuleTrace] = []
        for rule in self.rules:
            is_match = all(_condition_matches(root, cond) for cond in rule.get("when", []))
            status = "matched" if is_match else "not_matched"
            affected = list(rule.get("effect", {}).get("block", []))
            affected += list(rule.get("effect", {}).get("support", {}).keys())
            matched[rule["id"]] = {"rule": rule, "match": is_match}
            trace.append(
                RuleTrace(rule["id"], rule["type"], status, rule.get("reason", ""), affected, evidence)
            )

        blocked: Set[str] = set(ACTIONS) - explicit_allowed
        for entry in matched.values():
            rule = entry["rule"]
            if entry["match"] and rule["type"] == "hard":
                blocked.update(rule.get("effect", {}).get("block", []))

        suppressed: Set[str] = set()
        for entry in matched.values():
            rule = entry["rule"]
            if entry["match"] and rule["type"] == "exception":
                suppressed.update(rule.get("effect", {}).get("suppress_rules", []))
        for entry in matched.values():
            rule = entry["rule"]
            if entry["match"] and rule["type"] == "restoration":
                suppressed.difference_update(rule.get("effect", {}).get("restore_rules", []))

        scores = {action: 0.0 for action in ACTIONS}
        scores["stay"] = 0.2
        scores["wait"] = 0.1
        active_ids: List[str] = []
        for rule_id, entry in matched.items():
            rule = entry["rule"]
            if not entry["match"] or rule["type"] not in {"default", "soft"}:
                continue
            if rule_id in suppressed:
                continue
            active_ids.append(rule_id)
            for action, weight in rule.get("effect", {}).get("support", {}).items():
                scores[action] += float(weight)

        allowed = [action for action in self.tie_break_order if action not in blocked]
        if not allowed:
            raise ValueError("hard constraints block every action")
        rank = {action: index for index, action in enumerate(self.tie_break_order)}
        recommended = min(allowed, key=lambda action: (-scores[action], rank[action]))

        updated_trace: List[RuleTrace] = []
        for row in trace:
            status = row.status
            if row.rule_id in suppressed and status == "matched":
                status = "matched_but_suppressed"
            updated_trace.append(
                RuleTrace(row.rule_id, row.rule_type, status, row.reason, row.affected_actions, row.evidence_ids)
            )
        return InferenceResult(
            recommended_action=recommended,
            allowed_actions=allowed,
            blocked_actions=sorted(blocked),
            action_scores=scores,
            active_rule_ids=sorted(active_ids),
            suppressed_rule_ids=sorted(suppressed),
            trace=updated_trace,
        )

