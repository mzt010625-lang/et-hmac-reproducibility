from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any, Dict, Iterable, List, Mapping, Optional, Sequence, Tuple

from .models import ACTIONS

TECHNICAL_FAILURES: Tuple[str, ...] = (
    "transport_error", "timeout", "parse_error", "schema_error",
)
HARD_FAILURES: Tuple[str, ...] = (
    "action_illegal", "objective_infeasible", "evidence_out_of_scope",
    "future_information", "value_out_of_range", "stale_snapshot",
)
GUARD_FAILURES = TECHNICAL_FAILURES + HARD_FAILURES
L2_RATIONALE_CODES: Tuple[str, ...] = (
    "POLICY_EVIDENCE", "AFFORDABILITY", "LIQUIDITY", "RISK",
    "NETWORK", "MEMORY", "GOAL_TRADEOFF", "UNCERTAINTY",
)
STATE_UPDATE_CODES: Tuple[str, ...] = (
    "REASSESS_ELIGIBILITY", "REASSESS_AFFORDABILITY", "UPDATE_PRICE_EXPECTATION",
    "UPDATE_SOURCE_TRUST", "RECORD_SEARCH_OUTCOME", "RECORD_TRANSACTION_OUTCOME",
    "NO_DIRECT_UPDATE",
)
L2_REQUEST_KEYS = {
    "schema_version", "request_id", "record_id", "decision_version",
    "household_id", "snapshot_round", "visible_cutoff", "allowed_actions",
    "household_state", "visible_evidence", "ontology_context",
    "memory_summary", "decision_objectives",
}
L2_OUTPUT_KEYS = {
    "schema_version", "request_id", "record_id", "decision_version", "action",
    "confidence", "evidence_ids", "rationale_codes", "state_update_codes",
}
L2_FORBIDDEN_INPUT_KEYS = {
    "l0_action", "l1_action", "l1_output", "fast_action", "local_action",
    "recommended_action", "action_scores", "rule_scores", "jev_output",
    "router_decision", "reference_action", "reference_label", "target_action",
    "expected_action", "candidate_label", "final_action",
}


def find_l2_forbidden_input_keys(value: Any, path: str = "$") -> List[str]:
    hits: List[str] = []
    if isinstance(value, Mapping):
        for key, child in value.items():
            child_path = f"{path}.{key}"
            if str(key).lower() in L2_FORBIDDEN_INPUT_KEYS:
                hits.append(child_path)
            hits.extend(find_l2_forbidden_input_keys(child, child_path))
    elif isinstance(value, list):
        for index, child in enumerate(value):
            hits.extend(find_l2_forbidden_input_keys(child, f"{path}[{index}]"))
    return hits


def validate_l2_request(request: Mapping[str, Any]) -> None:
    if set(request) != L2_REQUEST_KEYS:
        raise ValueError(
            f"L2 request keys mismatch; missing={sorted(L2_REQUEST_KEYS-set(request))}, "
            f"extra={sorted(set(request)-L2_REQUEST_KEYS)}"
        )
    if request["schema_version"] != "l2_request_v1":
        raise ValueError("unexpected L2 request schema_version")
    hits = find_l2_forbidden_input_keys(request)
    if hits:
        raise ValueError("L2 request contains forbidden anchoring/label fields: " + ", ".join(hits))
    if int(request["snapshot_round"]) > int(request["visible_cutoff"]):
        raise ValueError("snapshot_round cannot exceed visible_cutoff")
    allowed = list(request["allowed_actions"])
    if not allowed or len(allowed) != len(set(allowed)) or set(allowed) - set(ACTIONS):
        raise ValueError("allowed_actions is empty, duplicated, or unknown")
    for evidence in request["visible_evidence"]:
        if int(evidence["visible_from"]) > int(request["visible_cutoff"]):
            raise ValueError("future evidence in L2 request")
        expires = evidence.get("expires_after")
        if expires is not None and int(expires) < int(request["snapshot_round"]):
            raise ValueError("expired evidence in L2 request")


@dataclass(frozen=True)
class GuardResult:
    accepted: bool
    failure_reason: Optional[str]
    details: Tuple[str, ...]
    guard_version: str = "hard_guard_v1"

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


class HardGuard:
    """Objective contract guard. It intentionally receives no L1/JEV preference."""

    version = "hard_guard_v1"

    def validate(
        self,
        output: Mapping[str, Any],
        request: Mapping[str, Any],
        current_decision_version: Optional[str] = None,
    ) -> GuardResult:
        try:
            validate_l2_request(request)
        except (KeyError, TypeError, ValueError) as exc:
            reason = "future_information" if "future evidence" in str(exc) else "schema_error"
            return GuardResult(False, reason, (str(exc),), self.version)
        if set(output) != L2_OUTPUT_KEYS:
            missing = sorted(L2_OUTPUT_KEYS - set(output))
            extra = sorted(set(output) - L2_OUTPUT_KEYS)
            return GuardResult(False, "schema_error", (f"missing={missing}", f"extra={extra}"), self.version)
        if output.get("schema_version") != "l2_output_v1":
            return GuardResult(False, "schema_error", ("unexpected schema_version",), self.version)
        for field in ("request_id", "record_id", "decision_version"):
            if str(output.get(field)) != str(request.get(field)):
                return GuardResult(False, "stale_snapshot", (f"{field} mismatch",), self.version)
        if current_decision_version is not None and str(output["decision_version"]) != str(current_decision_version):
            return GuardResult(False, "stale_snapshot", ("current decision version differs",), self.version)
        action = output.get("action")
        if action not in set(request["allowed_actions"]):
            return GuardResult(False, "action_illegal", (f"action={action!r}",), self.version)
        try:
            confidence = float(output["confidence"])
        except (TypeError, ValueError):
            return GuardResult(False, "value_out_of_range", ("confidence is not numeric",), self.version)
        if not 0 <= confidence <= 1:
            return GuardResult(False, "value_out_of_range", ("confidence outside [0,1]",), self.version)
        reasons = output["rationale_codes"]
        if (
            not isinstance(reasons, list)
            or not 1 <= len(reasons) <= 5
            or len(reasons) != len(set(reasons))
            or set(reasons) - set(L2_RATIONALE_CODES)
        ):
            return GuardResult(False, "schema_error", ("invalid rationale_codes",), self.version)
        update_codes = output["state_update_codes"]
        if (
            not isinstance(update_codes, list)
            or len(update_codes) > 5
            or len(update_codes) != len(set(update_codes))
            or set(update_codes) - set(STATE_UPDATE_CODES)
        ):
            return GuardResult(False, "schema_error", ("invalid state_update_codes",), self.version)
        evidence_ids = output["evidence_ids"]
        if not isinstance(evidence_ids, list) or len(evidence_ids) > 5 or len(evidence_ids) != len(set(evidence_ids)):
            return GuardResult(False, "schema_error", ("invalid evidence_ids",), self.version)
        evidence_map = {str(row["evidence_id"]): row for row in request["visible_evidence"]}
        unknown = [str(eid) for eid in evidence_ids if str(eid) not in evidence_map]
        if unknown:
            return GuardResult(False, "evidence_out_of_scope", tuple(unknown), self.version)
        for evidence_id in evidence_ids:
            evidence = evidence_map[str(evidence_id)]
            if int(evidence["visible_from"]) > int(request["visible_cutoff"]):
                return GuardResult(False, "future_information", (str(evidence_id),), self.version)
            expires = evidence.get("expires_after")
            if expires is not None and int(expires) < int(request["snapshot_round"]):
                return GuardResult(False, "evidence_out_of_scope", (f"expired:{evidence_id}",), self.version)
        return GuardResult(True, None, (), self.version)


@dataclass(frozen=True)
class L2Attempt:
    attempt_index: int
    response_id: str
    output: Mapping[str, Any]
    guard_result: GuardResult


@dataclass(frozen=True)
class FinalDecision:
    schema_version: str
    record_id: str
    decision_version: str
    status: str
    final_action: Optional[str]
    final_source: str
    fast_action: Optional[str]
    fast_source: str
    l2_requested: bool
    accepted_l2_response_id: Optional[str]
    accepted_l2_action: Optional[str]
    action_disagreement: Optional[bool]
    retry_count: int
    degradation_reason: Optional[str]
    guard_version: str

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


def resolve_final_decision(
    *,
    record_id: str,
    decision_version: str,
    fast_action: Optional[str],
    fast_source: str,
    allowed_actions: Iterable[str],
    l2_requested: bool,
    attempts: Sequence[L2Attempt] = (),
) -> FinalDecision:
    allowed = set(allowed_actions)
    if not allowed or allowed - set(ACTIONS):
        raise ValueError("invalid allowed action set")
    valid_attempt = next((attempt for attempt in attempts if attempt.guard_result.accepted), None)
    if l2_requested and valid_attempt is not None:
        l2_action = str(valid_attempt.output["action"])
        return FinalDecision(
            schema_version="final_decision_v1",
            record_id=record_id,
            decision_version=decision_version,
            status="COMMITTED",
            final_action=l2_action,
            final_source="L2",
            fast_action=fast_action,
            fast_source=fast_source,
            l2_requested=True,
            accepted_l2_response_id=valid_attempt.response_id,
            accepted_l2_action=l2_action,
            action_disagreement=(fast_action is not None and l2_action != fast_action),
            retry_count=max(0, valid_attempt.attempt_index - 1),
            degradation_reason=None,
            guard_version=valid_attempt.guard_result.guard_version,
        )
    if fast_action in allowed:
        degraded = l2_requested
        failure_reason = None
        if attempts:
            failure_reason = attempts[-1].guard_result.failure_reason
        elif degraded:
            failure_reason = "transport_error"
        return FinalDecision(
            schema_version="final_decision_v1",
            record_id=record_id,
            decision_version=decision_version,
            status="COMMITTED",
            final_action=fast_action,
            final_source=(f"{fast_source}_FALLBACK" if degraded else fast_source),
            fast_action=fast_action,
            fast_source=fast_source,
            l2_requested=l2_requested,
            accepted_l2_response_id=None,
            accepted_l2_action=None,
            action_disagreement=None,
            retry_count=max(0, len(attempts) - 1),
            degradation_reason=failure_reason,
            guard_version=(attempts[-1].guard_result.guard_version if attempts else HardGuard.version),
        )
    return FinalDecision(
        schema_version="final_decision_v1",
        record_id=record_id,
        decision_version=decision_version,
        status="UNDECIDED",
        final_action=None,
        final_source="UNDECIDED",
        fast_action=fast_action,
        fast_source=fast_source,
        l2_requested=l2_requested,
        accepted_l2_response_id=None,
        accepted_l2_action=None,
        action_disagreement=None,
        retry_count=max(0, len(attempts) - 1),
        degradation_reason=(attempts[-1].guard_result.failure_reason if attempts else "no_legal_fallback"),
        guard_version=(attempts[-1].guard_result.guard_version if attempts else HardGuard.version),
    )


class DecisionLedger:
    """Single immutable commit point for decisions consumed by every downstream layer."""

    def __init__(self) -> None:
        self._rows: Dict[Tuple[str, str], FinalDecision] = {}

    def commit(self, decision: FinalDecision) -> FinalDecision:
        key = (decision.record_id, decision.decision_version)
        existing = self._rows.get(key)
        if existing is None:
            self._rows[key] = decision
            return decision
        if existing == decision:
            return existing
        raise ValueError("decision version already committed with different content")

    def get(self, record_id: str, decision_version: str) -> FinalDecision:
        return self._rows[(record_id, decision_version)]

    def rows(self) -> List[FinalDecision]:
        return list(self._rows.values())

    def valid_l2_override_count(self) -> int:
        return sum(
            1
            for row in self._rows.values()
            if row.accepted_l2_action is not None
            and (row.final_source != "L2" or row.final_action != row.accepted_l2_action)
        )
