from __future__ import annotations

import hashlib
import json
import random
from dataclasses import asdict
from typing import Any, Dict, Iterable, Mapping, MutableMapping, Optional, Sequence, Set, Tuple

from .agent import HouseholdAgent
from .models import (
    ACTIONS,
    ActionOutcome,
    EnvironmentFeedback,
    HouseholdAttributes,
    HouseholdState,
    default_beliefs,
)
from .stage6_contracts import (
    DecisionLedger,
    HardGuard,
    L2Attempt,
    resolve_final_decision,
)


def canonical_hash(value: Any) -> str:
    payload = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


class Stage6Environment:
    """Small deterministic environment used to verify the ABM feedback loop."""

    def __init__(self, seed: int = 20260928) -> None:
        self.seed = int(seed)

    def _rng(self, world_id: str, household_id: str, round_index: int) -> random.Random:
        material = f"{self.seed}|{world_id}|{household_id}|{round_index}".encode("utf-8")
        integer_seed = int(hashlib.sha256(material).hexdigest()[:16], 16)
        return random.Random(integer_seed)

    def _execute_one(
        self,
        world_id: str,
        agent: HouseholdAgent,
        action: str,
        round_index: int,
        force_failure: bool,
    ) -> ActionOutcome:
        if action not in ACTIONS:
            raise ValueError("environment received an unknown action")
        if round_index != agent.state.current_round:
            raise ValueError("decision round and household state round differ")
        if action in {"list_for_sale", "list_for_rent"} and agent.state.tenure != "owner":
            raise ValueError("environment received an objectively illegal owner action")
        if action in {"stay", "wait"}:
            success_probability = 1.0
        else:
            prior = agent.state.beliefs.action_success_prob[action]
            affordability = agent.state.beliefs.affordability_prob
            success_probability = max(0.05, min(0.95, 0.55 * prior + 0.45 * affordability))
        success = False if force_failure else self._rng(world_id, agent.state.attributes.household_id, round_index).random() < success_probability
        cash_delta = 0.0
        new_tenure: Optional[str] = None
        if success and action == "search_buy":
            cash_delta = -min(agent.state.liquid_assets * 0.20, agent.state.attributes.income_monthly * 6.0)
            new_tenure = "owner"
        elif success and action == "search_jeonse":
            cash_delta = -min(agent.state.liquid_assets * 0.10, agent.state.attributes.income_monthly * 3.0)
            new_tenure = "jeonse"
        elif success and action == "search_monthly_rent":
            cash_delta = -min(agent.state.liquid_assets * 0.03, agent.state.attributes.income_monthly)
            new_tenure = "monthly_rent"
        elif success and action == "list_for_sale":
            cash_delta = agent.state.attributes.income_monthly * 12.0
            new_tenure = "other"
        elif success and action == "list_for_rent":
            cash_delta = agent.state.attributes.income_monthly * 0.50
        satisfaction = 0.75 if success else 0.25
        regret = 0.10 if success else 0.75
        return ActionOutcome(
            action=action,
            round_index=round_index,
            success=success,
            satisfaction=satisfaction,
            regret=regret,
            cash_delta=cash_delta,
            new_tenure=new_tenure,
            evidence_source_id="stage6_environment",
            evidence_channel="self_experience",
        )

    def step(
        self,
        *,
        world_id: str,
        round_index: int,
        agents: Mapping[str, HouseholdAgent],
        decisions: Mapping[str, Any],
        forced_failures: Optional[Set[Tuple[str, str, int]]] = None,
    ) -> Dict[str, Any]:
        forced = forced_failures or set()
        if set(agents) != set(decisions):
            raise ValueError("every household must have exactly one final decision")
        pre_hashes = {household_id: canonical_hash(agent.state.to_dict()) for household_id, agent in agents.items()}
        outcomes: Dict[str, ActionOutcome] = {}
        for household_id in sorted(agents):
            decision = decisions[household_id]
            if decision.status != "COMMITTED" or decision.final_action is None:
                raise ValueError("environment cannot execute an undecided record")
            outcome = self._execute_one(
                world_id,
                agents[household_id],
                decision.final_action,
                round_index,
                (world_id, household_id, round_index) in forced,
            )
            outcomes[household_id] = outcome
            agents[household_id].apply_outcome(outcome)
        shares = {action: 0.0 for action in ACTIONS}
        for decision in decisions.values():
            shares[decision.final_action] += 1.0 / len(decisions)
        market_growth = max(-0.2, min(0.2, 0.01 + 0.03 * shares["search_buy"] - 0.02 * shares["list_for_sale"]))
        for household_id, agent in agents.items():
            agent.apply_environment_feedback(
                EnvironmentFeedback(
                    round_index=agent.state.current_round,
                    market_price_growth=market_growth,
                    peer_action_shares=shares,
                    source_verifications={"online": round_index % 2 == 0},
                    market_source_id=f"market:{world_id}",
                )
            )
        post_hashes = {household_id: canonical_hash(agent.state.to_dict()) for household_id, agent in agents.items()}
        return {
            "world_id": world_id,
            "round": round_index,
            "decisions": {household_id: decisions[household_id].to_dict() for household_id in sorted(decisions)},
            "outcomes": {household_id: asdict(outcomes[household_id]) for household_id in sorted(outcomes)},
            "peer_action_shares": shares,
            "market_price_growth": market_growth,
            "pre_state_hashes": pre_hashes,
            "post_state_hashes": post_hashes,
            "all_states_changed": all(pre_hashes[key] != post_hashes[key] for key in pre_hashes),
        }


def build_demo_agents() -> Dict[str, HouseholdAgent]:
    agents: Dict[str, HouseholdAgent] = {}
    for index, tenure in enumerate(("monthly_rent", "monthly_rent", "owner"), start=1):
        household_id = f"HH-DEMO-{index:02d}"
        attributes = HouseholdAttributes(
            household_id=household_id,
            age=32 + index * 5,
            household_size=2 + index % 2,
            income_monthly=6000 + index * 1200,
            initial_tenure=tenure,
            dwelling_type="apartment",
            lifecycle_stage="child_rearing" if index < 3 else "mature_family",
            improvement_goal=0.55 + index * 0.10,
            liquidity_pressure=0.25 + index * 0.10,
            loss_aversion=0.45 + index * 0.05,
            risk_perception=0.35 + index * 0.08,
            residential_attachment=0.40 + index * 0.08,
            policy_trust_tendency=0.65,
            peer_sensitivity=0.45 + index * 0.05,
        )
        state = HouseholdState(
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
            liquid_assets=100000 + index * 40000,
            liquidity_pressure=attributes.liquidity_pressure,
            satisfaction=0.5,
            regret=0.0,
        )
        agents[household_id] = HouseholdAgent(state)
    return agents


def _demo_l2_request(household_id: str, round_index: int, allowed_actions: Sequence[str]) -> Dict[str, Any]:
    record_id = f"DEMO:{household_id}:r{round_index}"
    return {
        "schema_version": "l2_request_v1",
        "request_id": f"REQ:{record_id}",
        "record_id": record_id,
        "decision_version": f"{record_id}:v1",
        "household_id": household_id,
        "snapshot_round": round_index,
        "visible_cutoff": round_index,
        "allowed_actions": list(allowed_actions),
        "household_state": {"round": round_index},
        "visible_evidence": [],
        "ontology_context": {"rule_conflict_count": 0},
        "memory_summary": [],
        "decision_objectives": {"housing_improvement": 0.6, "liquidity_security": 0.5},
    }


def _demo_l2_output(request: Mapping[str, Any], action: str) -> Dict[str, Any]:
    return {
        "schema_version": "l2_output_v1",
        "request_id": request["request_id"],
        "record_id": request["record_id"],
        "decision_version": request["decision_version"],
        "action": action,
        "confidence": 0.7,
        "evidence_ids": [],
        "rationale_codes": ["GOAL_TRADEOFF"],
        "state_update_codes": ["NO_DIRECT_UPDATE"],
    }


def run_local_closed_loop(rounds: int = 3, seed: int = 20260928) -> Dict[str, Any]:
    if rounds <= 0:
        raise ValueError("rounds must be positive")
    agents = build_demo_agents()
    environment = Stage6Environment(seed=seed)
    guard = HardGuard()
    ledger = DecisionLedger()
    trajectory = []
    forced_failures = {("WORLD-DEMO", "HH-DEMO-02", 0)}
    for round_index in range(rounds):
        decisions = {}
        for household_id, agent in sorted(agents.items()):
            allowed = ["stay", "wait", "search_buy", "search_jeonse", "search_monthly_rent"]
            if agent.state.tenure == "owner":
                allowed.extend(["list_for_sale", "list_for_rent"])
            request = _demo_l2_request(household_id, round_index, allowed)
            fast_action = "stay" if household_id == "HH-DEMO-01" else "wait"
            l2_requested = household_id != "HH-DEMO-01"
            attempts = []
            if l2_requested:
                l2_action = "search_buy" if household_id == "HH-DEMO-02" else ("list_for_rent" if "list_for_rent" in allowed else "search_buy")
                output = _demo_l2_output(request, l2_action)
                attempts.append(
                    L2Attempt(
                        attempt_index=1,
                        response_id=f"RESP:{request['request_id']}:1",
                        output=output,
                        guard_result=guard.validate(output, request, request["decision_version"]),
                    )
                )
            decision = resolve_final_decision(
                record_id=request["record_id"],
                decision_version=request["decision_version"],
                fast_action=fast_action,
                fast_source="L1",
                allowed_actions=allowed,
                l2_requested=l2_requested,
                attempts=attempts,
            )
            decisions[household_id] = ledger.commit(decision)
        trajectory.append(
            environment.step(
                world_id="WORLD-DEMO",
                round_index=round_index,
                agents=agents,
                decisions=decisions,
                forced_failures=forced_failures,
            )
        )
    return {
        "schema_version": "stage6_local_closed_loop_v1",
        "world_id": "WORLD-DEMO",
        "rounds": rounds,
        "households": len(agents),
        "decisions": len(ledger.rows()),
        "l2_final_decisions": sum(row.final_source == "L2" for row in ledger.rows()),
        "valid_l2_override_count": ledger.valid_l2_override_count(),
        "all_round_states_changed": all(row["all_states_changed"] for row in trajectory),
        "trajectory": trajectory,
        "final_states": {household_id: agent.state.to_dict() for household_id, agent in sorted(agents.items())},
    }
