from __future__ import annotations

import math
from dataclasses import replace
from typing import Dict, Iterable

from .models import (
    ACTIONS,
    TENURES,
    ActionOutcome,
    EnvironmentFeedback,
    Evidence,
    HouseholdState,
    MemoryItem,
    clamp,
)


class HouseholdAgent:
    """Persistent household cognition with bounded, time-valid memory.

    The class is deliberately API-free. It freezes Stage 3 state semantics and
    transition behavior before System-1/JEV or System-2 is connected.
    """

    def __init__(
        self,
        state: HouseholdState,
        memory_window: int = 12,
        memory_decay: float = 0.18,
        belief_learning_rate: float = 0.35,
        trust_learning_rate: float = 0.12,
    ) -> None:
        self.state = state
        self.memory_window = memory_window
        self.memory_decay = memory_decay
        self.belief_learning_rate = belief_learning_rate
        self.trust_learning_rate = trust_learning_rate
        self.state.validate(memory_window)

    def _append_memory(self, item: MemoryItem) -> None:
        self.state.memory.append(item)
        now = self.state.current_round
        ranked = sorted(
            self.state.memory,
            key=lambda m: (
                math.exp(-self.memory_decay * max(0, now - m.round_index))
                * max(0.01, m.credibility),
                m.round_index,
                m.memory_id,
            ),
            reverse=True,
        )
        self.state.memory = sorted(ranked[: self.memory_window], key=lambda m: (m.round_index, m.memory_id))

    def memory_weight(self, item: MemoryItem, at_round: int) -> float:
        age = max(0, at_round - item.round_index)
        return math.exp(-self.memory_decay * age) * max(0.01, item.credibility)

    def perceive(self, evidence: Iterable[Evidence], round_index: int) -> None:
        if round_index < self.state.current_round:
            raise ValueError("cannot perceive evidence in a past round")
        for item in evidence:
            if not item.is_visible(round_index):
                raise ValueError(f"future or expired evidence blocked: {item.evidence_id}")
            trust = self.state.beliefs.channel_trust.get(item.channel, 0.5)
            weight = clamp(self.belief_learning_rate * trust * clamp(item.reliability))
            beliefs = self.state.beliefs
            if item.variable == "price_growth_expectation":
                beliefs.price_growth_expectation = max(
                    -0.2,
                    min(0.2, (1 - weight) * beliefs.price_growth_expectation + weight * item.value),
                )
            elif item.variable == "policy_eligibility_prob":
                beliefs.policy_eligibility_prob = clamp(
                    (1 - weight) * beliefs.policy_eligibility_prob + weight * item.value
                )
            elif item.variable == "affordability_prob":
                beliefs.affordability_prob = clamp(
                    (1 - weight) * beliefs.affordability_prob + weight * item.value
                )
            elif item.variable == "policy_duration_expectation":
                beliefs.policy_duration_expectation = max(
                    0.0,
                    min(12.0, (1 - weight) * beliefs.policy_duration_expectation + weight * item.value),
                )
            else:
                raise ValueError(f"unsupported belief variable: {item.variable}")
            if item.variable in beliefs.uncertainty:
                beliefs.uncertainty[item.variable] = clamp(
                    beliefs.uncertainty[item.variable] * (1 - 0.5 * weight)
                )
            self._append_memory(
                MemoryItem(
                    memory_id=f"evidence:{item.evidence_id}",
                    round_index=round_index,
                    kind="evidence",
                    source_id=item.source_id,
                    channel=item.channel,
                    content_ref=item.evidence_id,
                    credibility=clamp(trust * item.reliability),
                )
            )
        self.state.current_round = round_index
        self.state.validate(self.memory_window)

    def update_source_trust(self, channel: str, verified: bool) -> None:
        if channel not in self.state.beliefs.channel_trust:
            return
        old = self.state.beliefs.channel_trust[channel]
        target = 1.0 if verified else 0.0
        self.state.beliefs.channel_trust[channel] = clamp(
            (1 - self.trust_learning_rate) * old + self.trust_learning_rate * target
        )

    def apply_outcome(self, outcome: ActionOutcome) -> HouseholdState:
        if outcome.action not in ACTIONS:
            raise ValueError("outcome action is not in the action vocabulary")
        if outcome.round_index != self.state.current_round:
            raise ValueError("outcome must belong to the current decision round")
        if outcome.new_tenure is not None and outcome.new_tenure not in TENURES:
            raise ValueError("invalid new_tenure")

        alpha, beta = self.state.beliefs.action_success_counts[outcome.action]
        alpha += 1.0 if outcome.success else 0.0
        beta += 0.0 if outcome.success else 1.0
        self.state.beliefs.action_success_counts[outcome.action] = [alpha, beta]
        self.state.beliefs.action_success_prob[outcome.action] = alpha / (alpha + beta)

        self.state.satisfaction = clamp(outcome.satisfaction)
        self.state.regret = clamp(outcome.regret)
        self.state.liquid_assets = max(0.0, self.state.liquid_assets + outcome.cash_delta)
        annual_income = max(1.0, self.state.attributes.income_monthly * 12.0)
        pressure_delta = -outcome.cash_delta / annual_income * 0.2
        self.state.liquidity_pressure = clamp(self.state.liquidity_pressure + pressure_delta)
        if outcome.success and outcome.new_tenure is not None:
            self.state.tenure = outcome.new_tenure

        self._append_memory(
            MemoryItem(
                memory_id=f"outcome:{self.state.attributes.household_id}:{outcome.round_index}:{outcome.action}",
                round_index=outcome.round_index,
                kind="action_outcome",
                source_id=outcome.evidence_source_id,
                channel=outcome.evidence_channel,
                content_ref=outcome.action,
                action=outcome.action,
                success=outcome.success,
                satisfaction=self.state.satisfaction,
                regret=self.state.regret,
                credibility=1.0,
            )
        )
        self.state.current_round += 1
        self.state.validate(self.memory_window)
        return self.state

    def apply_environment_feedback(self, feedback: EnvironmentFeedback) -> None:
        """Update market/social cognition after execution, before the next choice."""
        if feedback.round_index != self.state.current_round:
            raise ValueError("environment feedback must belong to the next state round")
        if set(feedback.peer_action_shares) - set(ACTIONS):
            raise ValueError("peer_action_shares contains an unknown action")
        total = sum(feedback.peer_action_shares.values())
        if total and abs(total - 1.0) > 1e-6:
            raise ValueError("peer_action_shares must sum to 1")

        old = self.state.beliefs.price_growth_expectation
        alpha = self.belief_learning_rate * 0.8
        self.state.beliefs.price_growth_expectation = max(
            -0.2, min(0.2, (1 - alpha) * old + alpha * feedback.market_price_growth)
        )
        self._append_memory(
            MemoryItem(
                memory_id=f"market:{self.state.attributes.household_id}:{feedback.round_index}",
                round_index=feedback.round_index,
                kind="market_observation",
                source_id=feedback.market_source_id,
                channel="market",
                content_ref=f"price_growth={feedback.market_price_growth:.6f}",
                credibility=0.8,
            )
        )
        if feedback.peer_action_shares:
            top_action = min(
                ACTIONS,
                key=lambda action: (-feedback.peer_action_shares.get(action, 0.0), ACTIONS.index(action)),
            )
            self._append_memory(
                MemoryItem(
                    memory_id=f"social:{self.state.attributes.household_id}:{feedback.round_index}",
                    round_index=feedback.round_index,
                    kind="social_observation",
                    source_id="network_neighbors",
                    channel="neighbor",
                    content_ref=f"peer_top_action={top_action}",
                    credibility=clamp(self.state.attributes.peer_sensitivity),
                )
            )
        for channel, verified in feedback.source_verifications.items():
            self.update_source_trust(channel, verified)
        self.state.validate(self.memory_window)

    def cognitive_snapshot(self) -> Dict[str, object]:
        return {
            "household_id": self.state.attributes.household_id,
            "round": self.state.current_round,
            "tenure": self.state.tenure,
            "beliefs": self.state.to_dict()["beliefs"],
            "goals": dict(self.state.goals),
            "memory_refs": [m.content_ref for m in self.state.memory],
            "satisfaction": self.state.satisfaction,
            "regret": self.state.regret,
        }
