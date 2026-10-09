from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any, Dict, List, Optional, Tuple

ACTIONS: Tuple[str, ...] = (
    "stay",
    "wait",
    "search_buy",
    "search_jeonse",
    "search_monthly_rent",
    "list_for_sale",
    "list_for_rent",
)
CHANNELS: Tuple[str, ...] = ("official", "relative", "neighbor", "online")
TENURES: Tuple[str, ...] = ("owner", "jeonse", "monthly_rent", "other")
MEMORY_KINDS: Tuple[str, ...] = (
    "policy_evidence", "market_observation", "social_observation", "search_result",
    "transaction_result", "action_outcome", "source_verification", "evidence",
)


def clamp(value: float, low: float = 0.0, high: float = 1.0) -> float:
    return max(low, min(high, float(value)))


@dataclass(frozen=True)
class HouseholdAttributes:
    household_id: str
    age: int
    household_size: int
    income_monthly: float
    initial_tenure: str
    dwelling_type: str
    lifecycle_stage: str
    improvement_goal: float
    liquidity_pressure: float
    loss_aversion: float
    risk_perception: float
    residential_attachment: float
    policy_trust_tendency: float
    peer_sensitivity: float

    def validate(self) -> None:
        if not self.household_id:
            raise ValueError("household_id is required")
        if not 18 <= self.age <= 100:
            raise ValueError("age must be in [18, 100]")
        if not 1 <= self.household_size <= 15:
            raise ValueError("household_size must be in [1, 15]")
        if self.income_monthly < 0:
            raise ValueError("income_monthly must be non-negative")
        if self.initial_tenure not in TENURES:
            raise ValueError("invalid initial_tenure")
        for name in (
            "improvement_goal", "liquidity_pressure", "loss_aversion",
            "risk_perception", "residential_attachment",
            "policy_trust_tendency", "peer_sensitivity",
        ):
            value = getattr(self, name)
            if not 0 <= value <= 1:
                raise ValueError(f"{name} must be in [0, 1]")


@dataclass
class HouseholdBeliefs:
    price_growth_expectation: float
    policy_eligibility_prob: float
    affordability_prob: float
    channel_trust: Dict[str, float]
    action_success_prob: Dict[str, float]
    action_success_counts: Dict[str, List[float]]
    policy_duration_expectation: float
    uncertainty: Dict[str, float] = field(default_factory=dict)

    def validate(self) -> None:
        if not -0.2 <= self.price_growth_expectation <= 0.2:
            raise ValueError("price_growth_expectation must be in [-0.2, 0.2]")
        for name in ("policy_eligibility_prob", "affordability_prob"):
            if not 0 <= getattr(self, name) <= 1:
                raise ValueError(f"{name} must be in [0, 1]")
        if not 0 <= self.policy_duration_expectation <= 12:
            raise ValueError("policy_duration_expectation must be in [0, 12]")
        if set(CHANNELS) - set(self.channel_trust):
            raise ValueError("channel_trust misses a required channel")
        if set(ACTIONS) - set(self.action_success_prob):
            raise ValueError("action_success_prob misses an action")
        if set(ACTIONS) - set(self.action_success_counts):
            raise ValueError("action_success_counts misses an action")
        for mapping in (self.channel_trust, self.action_success_prob, self.uncertainty):
            if any(not 0 <= float(v) <= 1 for v in mapping.values()):
                raise ValueError("probability/uncertainty values must be in [0, 1]")
        for counts in self.action_success_counts.values():
            if len(counts) != 2 or min(counts) < 1:
                raise ValueError("action success Beta counts must contain alpha,beta >= 1")


@dataclass(frozen=True)
class Evidence:
    evidence_id: str
    visible_from: int
    expires_after: Optional[int]
    source_id: str
    channel: str
    variable: str
    value: float
    reliability: float
    provenance: str

    def is_visible(self, round_index: int) -> bool:
        return self.visible_from <= round_index and (
            self.expires_after is None or round_index <= self.expires_after
        )


@dataclass
class MemoryItem:
    memory_id: str
    round_index: int
    kind: str
    source_id: str
    channel: str
    content_ref: str
    action: Optional[str] = None
    success: Optional[bool] = None
    satisfaction: float = 0.5
    regret: float = 0.0
    credibility: float = 0.5


@dataclass(frozen=True)
class ActionOutcome:
    action: str
    round_index: int
    success: bool
    satisfaction: float
    regret: float
    cash_delta: float = 0.0
    new_tenure: Optional[str] = None
    evidence_source_id: str = "self"
    evidence_channel: str = "self_experience"


@dataclass(frozen=True)
class EnvironmentFeedback:
    round_index: int
    market_price_growth: float
    peer_action_shares: Dict[str, float]
    source_verifications: Dict[str, bool] = field(default_factory=dict)
    market_source_id: str = "market"


@dataclass
class HouseholdState:
    attributes: HouseholdAttributes
    beliefs: HouseholdBeliefs
    goals: Dict[str, float]
    memory: List[MemoryItem]
    current_round: int
    tenure: str
    liquid_assets: float
    liquidity_pressure: float
    satisfaction: float
    regret: float

    def validate(self, memory_window: int = 12) -> None:
        self.attributes.validate()
        self.beliefs.validate()
        if self.tenure not in TENURES:
            raise ValueError("invalid tenure")
        if self.liquid_assets < 0:
            raise ValueError("liquid_assets must be non-negative")
        if not 0 <= self.liquidity_pressure <= 1:
            raise ValueError("liquidity_pressure must be in [0, 1]")
        if self.current_round < 0:
            raise ValueError("current_round must be non-negative")
        if len(self.memory) > memory_window:
            raise ValueError("memory exceeds configured window")
        if any(item.kind not in MEMORY_KINDS for item in self.memory):
            raise ValueError("memory contains an unsupported kind")
        if not self.goals or abs(sum(self.goals.values()) - 1.0) > 1e-9:
            raise ValueError("goal weights must sum to 1")
        if any(not 0 <= v <= 1 for v in self.goals.values()):
            raise ValueError("goal weights must be in [0, 1]")
        if not 0 <= self.satisfaction <= 1 or not 0 <= self.regret <= 1:
            raise ValueError("satisfaction and regret must be in [0, 1]")

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


def default_beliefs() -> HouseholdBeliefs:
    return HouseholdBeliefs(
        price_growth_expectation=0.0,
        policy_eligibility_prob=0.5,
        affordability_prob=0.5,
        channel_trust={"official": 0.75, "relative": 0.55, "neighbor": 0.5, "online": 0.4},
        action_success_prob={action: 0.5 for action in ACTIONS},
        action_success_counts={action: [1.0, 1.0] for action in ACTIONS},
        policy_duration_expectation=3.0,
        uncertainty={
            "price_growth_expectation": 0.5,
            "policy_eligibility_prob": 0.5,
            "affordability_prob": 0.5,
            "policy_duration_expectation": 0.5,
        },
    )
