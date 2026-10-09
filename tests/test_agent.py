from __future__ import annotations

import unittest

from ethmac_v9.agent import HouseholdAgent
from ethmac_v9.models import (
    ACTIONS,
    ActionOutcome,
    EnvironmentFeedback,
    Evidence,
    HouseholdAttributes,
    HouseholdState,
    default_beliefs,
)


def sample_state(tenure: str = "monthly_rent") -> HouseholdState:
    attributes = HouseholdAttributes(
        household_id="HH-001",
        age=38,
        household_size=3,
        income_monthly=6500,
        initial_tenure=tenure,
        dwelling_type="apartment",
        lifecycle_stage="child_rearing",
        improvement_goal=0.8,
        liquidity_pressure=0.4,
        loss_aversion=0.6,
        risk_perception=0.3,
        residential_attachment=0.4,
        policy_trust_tendency=0.7,
        peer_sensitivity=0.6,
    )
    return HouseholdState(
        attributes=attributes,
        beliefs=default_beliefs(),
        goals={
            "housing_adequacy": 0.25,
            "financial_security": 0.30,
            "mobility": 0.10,
            "family_stability": 0.25,
            "policy_opportunity": 0.10,
        },
        memory=[],
        current_round=0,
        tenure=tenure,
        liquid_assets=100000,
        liquidity_pressure=attributes.liquidity_pressure,
        satisfaction=0.5,
        regret=0.0,
    )


class HouseholdAgentTests(unittest.TestCase):
    def test_future_evidence_is_blocked(self) -> None:
        agent = HouseholdAgent(sample_state())
        evidence = Evidence("E-FUTURE", 2, None, "P1", "official", "policy_eligibility_prob", 0.9, 1.0, "policy://P1")
        with self.assertRaisesRegex(ValueError, "future"):
            agent.perceive([evidence], round_index=1)

    def test_visible_evidence_updates_belief(self) -> None:
        agent = HouseholdAgent(sample_state())
        before = agent.state.beliefs.policy_eligibility_prob
        evidence = Evidence("E1", 0, 2, "P1", "official", "policy_eligibility_prob", 0.9, 1.0, "policy://P1")
        agent.perceive([evidence], round_index=0)
        self.assertGreater(agent.state.beliefs.policy_eligibility_prob, before)
        self.assertEqual(agent.state.memory[-1].content_ref, "E1")

    def test_memory_is_bounded(self) -> None:
        agent = HouseholdAgent(sample_state(), memory_window=12)
        evidence = [
            Evidence(f"E{i:02d}", 0, None, f"S{i}", "online", "affordability_prob", 0.4, 0.7, f"source://{i}")
            for i in range(15)
        ]
        agent.perceive(evidence, round_index=0)
        self.assertEqual(len(agent.state.memory), 12)

    def test_outcome_updates_experience_and_next_round(self) -> None:
        agent = HouseholdAgent(sample_state())
        prior = agent.state.beliefs.action_success_prob["search_buy"]
        agent.apply_outcome(ActionOutcome("search_buy", 0, True, 0.8, 0.1, -10000, "owner"))
        self.assertGreater(agent.state.beliefs.action_success_prob["search_buy"], prior)
        self.assertEqual(agent.state.tenure, "owner")
        self.assertEqual(agent.state.current_round, 1)
        self.assertEqual(agent.state.memory[-1].kind, "action_outcome")

    def test_failed_action_does_not_change_tenure(self) -> None:
        agent = HouseholdAgent(sample_state())
        agent.apply_outcome(ActionOutcome("search_buy", 0, False, 0.2, 0.8, 0, "owner"))
        self.assertEqual(agent.state.tenure, "monthly_rent")

    def test_market_and_network_feedback_update_next_state(self) -> None:
        agent = HouseholdAgent(sample_state())
        agent.apply_outcome(ActionOutcome("wait", 0, True, 0.55, 0.1))
        before_price = agent.state.beliefs.price_growth_expectation
        before_trust = agent.state.beliefs.channel_trust["online"]
        shares = {action: 0.0 for action in ACTIONS}
        shares["search_buy"] = 1.0
        agent.apply_environment_feedback(
            EnvironmentFeedback(1, 0.08, shares, {"online": False})
        )
        self.assertGreater(agent.state.beliefs.price_growth_expectation, before_price)
        self.assertLess(agent.state.beliefs.channel_trust["online"], before_trust)
        self.assertEqual(agent.state.memory[-1].kind, "social_observation")


if __name__ == "__main__":
    unittest.main()
