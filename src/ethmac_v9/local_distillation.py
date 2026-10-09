from __future__ import annotations

import hashlib
import math
import re
from dataclasses import dataclass
from typing import Any, Dict, Iterable, List, Mapping, Sequence, Tuple

from .models import ACTIONS


CHANNELS = ("official", "market", "neighbor", "relative", "online")
EVIDENCE_TYPES = ("policy_claim", "market_observation", "network_topology")
POLICY_KEYWORDS = {
    "buy_support": ("homebuyer", "home buyer", "purchase", "buy", "acquisition"),
    "rental_support": ("rent", "rental", "jeonse", "tenant"),
    "finance_relief": ("ltv", "dti", "loan", "mortgage", "financial support"),
    "tax_relief": ("tax", "deduction", "exemption"),
    "supply": ("supply", "units", "housing construction"),
    "redevelopment": ("redevelopment", "reconstruction", "renewal"),
    "market_risk": ("vacancy", "decline", "risk", "unmet demand"),
}
TOKEN_RE = re.compile(r"[a-z][a-z0-9_]{2,}")
NUMBER_RE = re.compile(r"([a-z_]+)=(-?[0-9]+(?:\.[0-9]+)?)")
TEXT_HASH_BINS = 32
CATEGORY_HASH_BINS = 12
RULE_HASH_BINS = 8


def _hash_bin(value: str, bins: int) -> int:
    digest = hashlib.sha256(value.encode("utf-8")).digest()
    return int.from_bytes(digest[:8], "big") % bins


def _safe_float(value: Any, default: float = 0.0) -> float:
    try:
        result = float(value)
    except (TypeError, ValueError):
        return default
    return result if math.isfinite(result) else default


def feature_names() -> Tuple[str, ...]:
    names: List[str] = [
        "round", "age", "household_size", "log_income", "log_liquid_assets",
        "liquidity_pressure", "loss_aversion", "risk_perception",
        "residential_attachment", "policy_trust_tendency", "peer_sensitivity",
        "improvement_goal", "policy_eligibility_prob", "affordability_prob",
        "price_growth_expectation", "policy_duration_expectation",
        "satisfaction", "regret", "memory_size", "memory_success_rate",
        "memory_failure_rate", "l1_margin", "l1_active_rule_count",
        "l1_suppressed_rule_count", "l1_blocked_count",
        "evidence_conflict_count", "missing_evidence_count", "rule_conflict_count",
        "multistep_dependency", "two_hop_network_dependency", "unseen_policy_combination",
        "visible_evidence_count", "mean_evidence_reliability", "valid_policy_share",
        "network_neighbor_count", "market_demand_mean", "market_demand_max",
        "market_demand_min", "market_matches_sum", "market_unmet_sum",
        "market_inventory_sum",
    ]
    for action in ACTIONS:
        names.extend((f"allowed:{action}", f"l1_score:{action}", f"l1_action:{action}"))
    for channel in CHANNELS:
        names.extend((f"channel_count:{channel}", f"channel_reliability:{channel}"))
    for evidence_type in EVIDENCE_TYPES:
        names.append(f"evidence_type_count:{evidence_type}")
    for keyword in POLICY_KEYWORDS:
        names.append(f"policy_keyword:{keyword}")
    names.extend(f"text_hash:{index}" for index in range(TEXT_HASH_BINS))
    names.extend(f"category_hash:{index}" for index in range(CATEGORY_HASH_BINS))
    names.extend(f"rule_hash:{index}" for index in range(RULE_HASH_BINS))
    return tuple(names)


FEATURE_NAMES = feature_names()


def extract_feature_vector(record: Mapping[str, Any], jev_input: Mapping[str, Any]) -> List[float]:
    """Build a fixed, CPU-only vector without L2 output or reference labels."""
    state = record["state"]
    attrs = state["attributes"]
    beliefs = state["beliefs"]
    memory = list(state.get("memory") or [])
    l1 = jev_input["l1_output"]
    ontology = jev_input["ontology_features"]
    evidence = list(record.get("visible_evidence") or [])
    values: Dict[str, float] = {name: 0.0 for name in FEATURE_NAMES}

    scalar = {
        "round": _safe_float(record.get("round")) / 4.0,
        "age": _safe_float(attrs.get("age")) / 100.0,
        "household_size": _safe_float(attrs.get("household_size")) / 10.0,
        "log_income": math.log1p(max(0.0, _safe_float(attrs.get("income_monthly")))) / 20.0,
        "log_liquid_assets": math.log1p(max(0.0, _safe_float(state.get("liquid_assets")))) / 25.0,
        "liquidity_pressure": _safe_float(state.get("liquidity_pressure")),
        "loss_aversion": _safe_float(attrs.get("loss_aversion")),
        "risk_perception": _safe_float(attrs.get("risk_perception")),
        "residential_attachment": _safe_float(attrs.get("residential_attachment")),
        "policy_trust_tendency": _safe_float(attrs.get("policy_trust_tendency")),
        "peer_sensitivity": _safe_float(attrs.get("peer_sensitivity")),
        "improvement_goal": _safe_float(attrs.get("improvement_goal")),
        "policy_eligibility_prob": _safe_float(beliefs.get("policy_eligibility_prob")),
        "affordability_prob": _safe_float(beliefs.get("affordability_prob")),
        "price_growth_expectation": _safe_float(beliefs.get("price_growth_expectation")) * 5.0,
        "policy_duration_expectation": _safe_float(beliefs.get("policy_duration_expectation")) / 5.0,
        "satisfaction": _safe_float(state.get("satisfaction")),
        "regret": _safe_float(state.get("regret")),
        "memory_size": min(len(memory), 10) / 10.0,
        "l1_margin": min(5.0, _safe_float(l1.get("top_two_margin"))) / 5.0,
        "l1_active_rule_count": min(len(l1.get("active_rule_ids") or []), 10) / 10.0,
        "l1_suppressed_rule_count": min(len(l1.get("suppressed_rule_ids") or []), 10) / 10.0,
        "l1_blocked_count": len(l1.get("hard_blocked_actions") or []) / len(ACTIONS),
        "evidence_conflict_count": min(3.0, _safe_float(ontology.get("evidence_conflict_count"))) / 3.0,
        "missing_evidence_count": min(3.0, _safe_float(ontology.get("missing_evidence_count"))) / 3.0,
        "rule_conflict_count": min(3.0, _safe_float(ontology.get("rule_conflict_count"))) / 3.0,
        "multistep_dependency": float(bool(ontology.get("multistep_dependency"))),
        "two_hop_network_dependency": float(bool(ontology.get("two_hop_network_dependency"))),
        "unseen_policy_combination": float(bool(ontology.get("unseen_policy_combination"))),
        "visible_evidence_count": min(len(evidence), 40) / 40.0,
    }
    successes = sum(item.get("success") is True for item in memory)
    failures = sum(item.get("success") is False for item in memory)
    scalar["memory_success_rate"] = successes / len(memory) if memory else 0.0
    scalar["memory_failure_rate"] = failures / len(memory) if memory else 0.0
    values.update(scalar)

    allowed = set(jev_input["allowed_actions"])
    for action in ACTIONS:
        values[f"allowed:{action}"] = float(action in allowed)
        values[f"l1_score:{action}"] = max(-5.0, min(5.0, _safe_float((l1.get("action_scores") or {}).get(action)))) / 5.0
        values[f"l1_action:{action}"] = float(l1.get("recommended_action") == action)

    reliabilities: List[float] = []
    channel_reliabilities: Dict[str, List[float]] = {channel: [] for channel in CHANNELS}
    valid_policy = 0
    policy_count = 0
    neighbor_count = 0
    market_numbers: Dict[str, List[float]] = {}
    for item in evidence:
        channel = str(item.get("channel") or "")
        evidence_type = str(item.get("evidence_type") or "")
        reliability = _safe_float(item.get("reliability"))
        reliabilities.append(reliability)
        if channel in CHANNELS:
            values[f"channel_count:{channel}"] += 1.0
            channel_reliabilities[channel].append(reliability)
        if evidence_type in EVIDENCE_TYPES:
            values[f"evidence_type_count:{evidence_type}"] += 1.0
        if evidence_type == "policy_claim":
            policy_count += 1
            valid_policy += int(item.get("validity_evidenced") is True)
        neighbor_count = max(neighbor_count, int(item.get("neighbor_count") or 0))
        claim = str(item.get("claim") or "").lower()
        for name, words in POLICY_KEYWORDS.items():
            values[f"policy_keyword:{name}"] += float(any(word in claim for word in words))
        for token in TOKEN_RE.findall(claim):
            values[f"text_hash:{_hash_bin(token, TEXT_HASH_BINS)}"] += 1.0
        if evidence_type == "market_observation":
            for name, number in NUMBER_RE.findall(claim):
                market_numbers.setdefault(name, []).append(float(number))

    values["mean_evidence_reliability"] = sum(reliabilities) / len(reliabilities) if reliabilities else 0.0
    values["valid_policy_share"] = valid_policy / policy_count if policy_count else 0.0
    values["network_neighbor_count"] = min(neighbor_count, 20) / 20.0
    demand = market_numbers.get("demand_pressure", [])
    values["market_demand_mean"] = sum(demand) / len(demand) / 3.0 if demand else 0.0
    values["market_demand_max"] = max(demand) / 3.0 if demand else 0.0
    values["market_demand_min"] = min(demand) / 3.0 if demand else 0.0
    values["market_matches_sum"] = min(100.0, sum(market_numbers.get("matches", []))) / 100.0
    values["market_unmet_sum"] = min(100.0, sum(market_numbers.get("unmet_demand", []))) / 100.0
    values["market_inventory_sum"] = min(200.0, sum(market_numbers.get("inventory_end", []))) / 200.0
    for channel in CHANNELS:
        count = values[f"channel_count:{channel}"]
        values[f"channel_count:{channel}"] = min(count, 20.0) / 20.0
        rows = channel_reliabilities[channel]
        values[f"channel_reliability:{channel}"] = sum(rows) / len(rows) if rows else 0.0
    for evidence_type in EVIDENCE_TYPES:
        key = f"evidence_type_count:{evidence_type}"
        values[key] = min(values[key], 20.0) / 20.0
    for name in POLICY_KEYWORDS:
        key = f"policy_keyword:{name}"
        values[key] = min(values[key], 10.0) / 10.0
    for index in range(TEXT_HASH_BINS):
        key = f"text_hash:{index}"
        values[key] = math.log1p(values[key]) / 5.0

    categories = (
        "tenure=" + str(state.get("tenure")),
        "initial_tenure=" + str(attrs.get("initial_tenure")),
        "lifecycle=" + str(attrs.get("lifecycle_stage")),
        "dwelling=" + str(attrs.get("dwelling_type")),
        "queue=" + str(record.get("queue_type")),
    )
    for category in categories:
        values[f"category_hash:{_hash_bin(category, CATEGORY_HASH_BINS)}"] += 1.0
    for rule_id in l1.get("active_rule_ids") or []:
        values[f"rule_hash:{_hash_bin(str(rule_id), RULE_HASH_BINS)}"] += 1.0
    for rule_id in l1.get("suppressed_rule_ids") or []:
        values[f"rule_hash:{_hash_bin('suppressed:' + str(rule_id), RULE_HASH_BINS)}"] -= 1.0
    return [values[name] for name in FEATURE_NAMES]


@dataclass
class Standardizer:
    means: List[float]
    scales: List[float]

    @classmethod
    def fit(cls, rows: Sequence[Sequence[float]]) -> "Standardizer":
        if not rows:
            raise ValueError("cannot fit a standardizer on no rows")
        width = len(rows[0])
        means = [sum(float(row[j]) for row in rows) / len(rows) for j in range(width)]
        scales = []
        for j, mean in enumerate(means):
            variance = sum((float(row[j]) - mean) ** 2 for row in rows) / len(rows)
            scales.append(math.sqrt(variance) if variance > 1e-12 else 1.0)
        return cls(means, scales)

    def transform_one(self, row: Sequence[float]) -> List[float]:
        return [(float(value) - self.means[j]) / self.scales[j] for j, value in enumerate(row)]

    def transform(self, rows: Sequence[Sequence[float]]) -> List[List[float]]:
        return [self.transform_one(row) for row in rows]

    def to_dict(self) -> Dict[str, Any]:
        return {"means": self.means, "scales": self.scales}


def _softmax(values: Sequence[float]) -> List[float]:
    peak = max(values)
    exponents = [math.exp(value - peak) for value in values]
    total = sum(exponents)
    return [value / total for value in exponents]


@dataclass
class SoftmaxModel:
    weights: List[List[float]]
    biases: List[float]
    standardizer: Standardizer

    def predict_proba(self, row: Sequence[float], allowed_actions: Iterable[str]) -> List[float]:
        x = self.standardizer.transform_one(row)
        logits = [self.biases[c] + sum(weight * value for weight, value in zip(self.weights[c], x)) for c in range(len(ACTIONS))]
        probabilities = _softmax(logits)
        allowed = set(allowed_actions)
        probabilities = [probabilities[i] if action in allowed else 0.0 for i, action in enumerate(ACTIONS)]
        total = sum(probabilities)
        if total <= 0:
            return [1.0 / len(allowed) if action in allowed else 0.0 for action in ACTIONS]
        return [value / total for value in probabilities]

    def to_dict(self) -> Dict[str, Any]:
        return {
            "model_type": "standard_library_multinomial_logistic_v1",
            "actions": list(ACTIONS),
            "feature_names": list(FEATURE_NAMES),
            "weights": self.weights,
            "biases": self.biases,
            "standardizer": self.standardizer.to_dict(),
        }


def fit_softmax(
    rows: Sequence[Sequence[float]],
    labels: Sequence[str],
    epochs: int = 120,
    learning_rate: float = 0.06,
    l2: float = 0.002,
) -> SoftmaxModel:
    if len(rows) != len(labels) or not rows:
        raise ValueError("softmax rows and labels must be non-empty and aligned")
    standardizer = Standardizer.fit(rows)
    x_rows = standardizer.transform(rows)
    width = len(x_rows[0])
    classes = len(ACTIONS)
    weights = [[0.0] * width for _ in range(classes)]
    biases = [0.0] * classes
    counts = {action: labels.count(action) for action in ACTIONS}
    present = sum(count > 0 for count in counts.values())
    sample_weights = [len(labels) / (present * counts[label]) if counts[label] else 1.0 for label in labels]
    for epoch in range(epochs):
        grad_w = [[0.0] * width for _ in range(classes)]
        grad_b = [0.0] * classes
        for x, label, sample_weight in zip(x_rows, labels, sample_weights):
            target = ACTIONS.index(label)
            logits = [biases[c] + sum(weights[c][j] * x[j] for j in range(width)) for c in range(classes)]
            probs = _softmax(logits)
            for c in range(classes):
                error = (probs[c] - float(c == target)) * sample_weight
                grad_b[c] += error
                for j, value in enumerate(x):
                    grad_w[c][j] += error * value
        rate = learning_rate / math.sqrt(1.0 + epoch / 80.0)
        scale = 1.0 / len(rows)
        for c in range(classes):
            biases[c] -= rate * grad_b[c] * scale
            for j in range(width):
                weights[c][j] -= rate * (grad_w[c][j] * scale + l2 * weights[c][j])
    return SoftmaxModel(weights, biases, standardizer)


@dataclass
class BinaryLogisticModel:
    weights: List[float]
    bias: float
    standardizer: Standardizer
    constant_probability: float = -1.0

    def predict_probability(self, row: Sequence[float]) -> float:
        if self.constant_probability >= 0:
            return self.constant_probability
        x = self.standardizer.transform_one(row)
        value = self.bias + sum(weight * item for weight, item in zip(self.weights, x))
        if value >= 0:
            return 1.0 / (1.0 + math.exp(-value))
        exp_value = math.exp(value)
        return exp_value / (1.0 + exp_value)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "model_type": "standard_library_binary_logistic_v1",
            "weights": self.weights,
            "bias": self.bias,
            "constant_probability": self.constant_probability,
            "standardizer": self.standardizer.to_dict(),
        }


def fit_binary_logistic(
    rows: Sequence[Sequence[float]],
    labels: Sequence[int],
    epochs: int = 160,
    learning_rate: float = 0.05,
    l2: float = 0.003,
) -> BinaryLogisticModel:
    if len(rows) != len(labels) or not rows:
        raise ValueError("binary rows and labels must be non-empty and aligned")
    standardizer = Standardizer.fit(rows)
    if len(set(int(value) for value in labels)) == 1:
        probability = (sum(labels) + 1.0) / (len(labels) + 2.0)
        return BinaryLogisticModel([0.0] * len(rows[0]), 0.0, standardizer, probability)
    x_rows = standardizer.transform(rows)
    weights = [0.0] * len(x_rows[0])
    bias = 0.0
    positives = sum(int(value) for value in labels)
    negatives = len(labels) - positives
    positive_weight = len(labels) / (2.0 * positives)
    negative_weight = len(labels) / (2.0 * negatives)
    for epoch in range(epochs):
        grad = [0.0] * len(weights)
        grad_bias = 0.0
        for x, label in zip(x_rows, labels):
            value = bias + sum(weight * item for weight, item in zip(weights, x))
            probability = 1.0 / (1.0 + math.exp(-max(-30.0, min(30.0, value))))
            sample_weight = positive_weight if label else negative_weight
            error = (probability - label) * sample_weight
            grad_bias += error
            for j, item in enumerate(x):
                grad[j] += error * item
        rate = learning_rate / math.sqrt(1.0 + epoch / 80.0)
        scale = 1.0 / len(rows)
        bias -= rate * grad_bias * scale
        for j in range(len(weights)):
            weights[j] -= rate * (grad[j] * scale + l2 * weights[j])
    return BinaryLogisticModel(weights, bias, standardizer)


def prediction_meta_features(probabilities: Sequence[float], l1_action: str) -> List[float]:
    ordered = sorted((float(value) for value in probabilities), reverse=True)
    maximum = ordered[0]
    margin = ordered[0] - ordered[1] if len(ordered) > 1 else ordered[0]
    entropy = -sum(value * math.log(max(value, 1e-12)) for value in probabilities) / math.log(len(ACTIONS))
    predicted = ACTIONS[max(range(len(ACTIONS)), key=lambda index: probabilities[index])]
    return list(probabilities) + [maximum, margin, entropy, float(predicted != l1_action)]


def stable_group_folds(group_keys: Sequence[str], folds: int, seed: int) -> List[int]:
    if folds < 2:
        raise ValueError("fold count must be at least two")
    unique = sorted(set(group_keys), key=lambda value: hashlib.sha256(f"{seed}|{value}".encode("utf-8")).hexdigest())
    assignment = {group: index % folds for index, group in enumerate(unique)}
    return [assignment[group] for group in group_keys]


def top_action(probabilities: Sequence[float]) -> str:
    return ACTIONS[max(range(len(ACTIONS)), key=lambda index: (float(probabilities[index]), -index))]
