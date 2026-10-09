from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any, Dict, Iterable, Mapping, Tuple

from .models import ACTIONS

SYSTEM1_MODES: Tuple[str, ...] = ("J-route", "J-fast", "J-joint")


def _top_action(probabilities: Mapping[str, float]) -> str:
    return min(ACTIONS, key=lambda action: (-float(probabilities[action]), ACTIONS.index(action)))


def legalize_action_probabilities(
    raw_probabilities: Mapping[str, Any],
    allowed_actions: Iterable[str],
) -> Tuple[Dict[str, float], float]:
    """Apply an external legal-action mask without altering the raw model record."""
    if set(raw_probabilities) != set(ACTIONS):
        raise ValueError("raw probabilities must contain exactly the seven actions")
    values = {action: float(raw_probabilities[action]) for action in ACTIONS}
    if any(value < 0 or value > 1 for value in values.values()):
        raise ValueError("raw probabilities must be in [0,1]")
    if abs(sum(values.values()) - 1.0) > 1e-3:
        raise ValueError("raw probabilities must sum to 1")
    allowed = set(allowed_actions)
    if not allowed or allowed - set(ACTIONS):
        raise ValueError("allowed_actions is empty or contains an unknown action")
    illegal_mass = sum(value for action, value in values.items() if action not in allowed)
    legal_mass = sum(value for action, value in values.items() if action in allowed)
    if legal_mass <= 0:
        raise ValueError("legal action probability mass is zero")
    masked = {
        action: (values[action] / legal_mass if action in allowed else 0.0)
        for action in ACTIONS
    }
    return masked, illegal_mass


@dataclass(frozen=True)
class System1Assessment:
    schema_version: str
    record_id: str
    mode: str
    fast_action: str
    fast_source: str
    risk_target: str
    raw_action_probabilities: Dict[str, float]
    masked_action_probabilities: Dict[str, float]
    raw_top_action: str
    masked_top_action: str
    illegal_probability_mass_raw: float
    should_escalate_raw: bool
    route_reason_codes: Tuple[str, ...]
    fast_action_error_probability_raw: float
    l2_correction_probability_raw: float
    l2_harm_probability_raw: float
    semantic_conflict_score_raw: float
    novelty_score_raw: float
    confidence_raw: float

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


def build_system1_assessment(
    record: Mapping[str, Any],
    jev_output: Mapping[str, Any],
    mode: str = "J-route",
) -> System1Assessment:
    if mode not in SYSTEM1_MODES:
        raise ValueError("unknown System-1 mode")
    if str(record["record_id"]) != str(jev_output["record_id"]):
        raise ValueError("record and JEV output IDs differ")
    raw = {action: float(jev_output["action_probabilities"][action]) for action in ACTIONS}
    masked, illegal_mass = legalize_action_probabilities(raw, record["allowed_actions"])
    raw_top = _top_action(raw)
    masked_top = _top_action(masked)
    if mode == "J-route":
        fast_action = str(record["l1_output"]["recommended_action"])
        fast_source = "L1"
        risk_target = "L1_ERROR"
        should_escalate = bool(jev_output["should_escalate_raw"])
    elif mode == "J-fast":
        fast_action = masked_top
        fast_source = "JEV"
        risk_target = "JEV_ACTION_ERROR"
        should_escalate = False
    else:
        fast_action = masked_top
        fast_source = "JEV"
        risk_target = "JEV_ACTION_ERROR"
        should_escalate = bool(jev_output["should_escalate_raw"])
    if fast_action not in set(record["allowed_actions"]):
        raise ValueError("selected fast action is outside allowed_actions")
    return System1Assessment(
        schema_version="system1_assessment_v1",
        record_id=str(record["record_id"]),
        mode=mode,
        fast_action=fast_action,
        fast_source=fast_source,
        risk_target=risk_target,
        raw_action_probabilities=raw,
        masked_action_probabilities=masked,
        raw_top_action=raw_top,
        masked_top_action=masked_top,
        illegal_probability_mass_raw=illegal_mass,
        should_escalate_raw=should_escalate,
        route_reason_codes=tuple(str(x) for x in jev_output["route_reasons"]),
        fast_action_error_probability_raw=float(jev_output["fast_action_error_probability_raw"]),
        l2_correction_probability_raw=float(jev_output["l2_correction_probability_raw"]),
        l2_harm_probability_raw=float(jev_output["l2_harm_probability_raw"]),
        semantic_conflict_score_raw=float(jev_output["semantic_conflict_score_raw"]),
        novelty_score_raw=float(jev_output["novelty_score_raw"]),
        confidence_raw=float(jev_output["confidence_raw"]),
    )
