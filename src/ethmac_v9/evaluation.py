from __future__ import annotations

import math
from typing import Any, Dict, Mapping, Optional, Sequence, Set, Tuple

from .models import ACTIONS


def nearest_rank_percentile(values: Sequence[float], probability: float) -> float:
    if not values:
        raise ValueError("percentile requires at least one value")
    if not 0 < probability <= 1:
        raise ValueError("probability must be in (0, 1]")
    ordered = sorted(float(value) for value in values)
    index = max(0, math.ceil(probability * len(ordered)) - 1)
    return ordered[index]


def evc_score(jev_output: Mapping[str, Any]) -> float:
    """Decision-time value score fixed before seeing L2 or reference outputs."""
    return float(jev_output["l2_correction_probability_raw"]) - float(
        jev_output["l2_harm_probability_raw"]
    )


def select_budgeted_l2(
    fast_rows: Sequence[Mapping[str, Any]],
    budget_rate: float,
) -> Tuple[Set[str], Dict[str, float], int]:
    if not 0 <= budget_rate <= 1:
        raise ValueError("budget_rate must be in [0, 1]")
    if not fast_rows:
        raise ValueError("fast_rows is empty")
    scores: Dict[str, float] = {}
    for row in fast_rows:
        record_id = str(row["record_id"])
        if record_id in scores:
            raise ValueError(f"duplicate fast row for {record_id}")
        scores[record_id] = evc_score(row["jev_output"])
    capacity = int(math.floor(len(fast_rows) * budget_rate + 1e-12))
    ranked = sorted(scores, key=lambda record_id: (-scores[record_id], record_id))
    selected = {record_id for record_id in ranked[:capacity] if scores[record_id] > 0}
    return selected, scores, capacity


def parse_reference_annotations(
    rows: Sequence[Mapping[str, Any]],
) -> Tuple[Dict[str, str], Dict[str, Set[str]], Set[str]]:
    best: Dict[str, str] = {}
    acceptable: Dict[str, Set[str]] = {}
    abstained: Set[str] = set()
    for row in rows:
        annotation = row.get("annotation") if isinstance(row.get("annotation"), Mapping) else row
        record_id = str(annotation.get("record_id") or row.get("record_id") or "")
        if not record_id:
            raise ValueError("reference annotation lacks record_id")
        if record_id in best or record_id in abstained:
            raise ValueError(f"duplicate reference annotation for {record_id}")
        status = str(annotation.get("decision_status"))
        if status == "abstain":
            abstained.add(record_id)
            continue
        if status != "labeled":
            raise ValueError(f"invalid reference decision_status for {record_id}")
        action = str(annotation.get("best_action"))
        if action not in ACTIONS:
            raise ValueError(f"invalid best_action for {record_id}")
        accepted = {str(value) for value in annotation.get("acceptable_actions") or [action]}
        if not accepted or accepted - set(ACTIONS) or action not in accepted:
            raise ValueError(f"invalid acceptable_actions for {record_id}")
        best[record_id] = action
        acceptable[record_id] = accepted
    return best, acceptable, abstained


def classification_metrics(
    predictions: Mapping[str, str],
    labels: Mapping[str, str],
    acceptable: Mapping[str, Set[str]],
) -> Dict[str, Any]:
    ids = sorted(labels)
    if not ids:
        raise ValueError("no labeled records are available")
    if any(record_id not in predictions for record_id in ids):
        raise ValueError("a prediction is missing for a labeled record")
    support = {action: 0 for action in ACTIONS}
    true_positive = {action: 0 for action in ACTIONS}
    false_positive = {action: 0 for action in ACTIONS}
    false_negative = {action: 0 for action in ACTIONS}
    exact_correct = 0
    set_hit = 0
    for record_id in ids:
        truth = labels[record_id]
        prediction = str(predictions[record_id])
        if prediction not in ACTIONS:
            raise ValueError(f"invalid prediction for {record_id}")
        support[truth] += 1
        exact_correct += int(prediction == truth)
        set_hit += int(prediction in acceptable[record_id])
        for action in ACTIONS:
            true_positive[action] += int(prediction == action and truth == action)
            false_positive[action] += int(prediction == action and truth != action)
            false_negative[action] += int(prediction != action and truth == action)
    recalls = {
        action: (true_positive[action] / support[action] if support[action] else None)
        for action in ACTIONS
    }
    present_recalls = [value for value in recalls.values() if value is not None]
    f1 = {}
    for action in ACTIONS:
        denominator = 2 * true_positive[action] + false_positive[action] + false_negative[action]
        f1[action] = 2 * true_positive[action] / denominator if denominator else 0.0
    return {
        "n_labeled": len(ids),
        "accuracy": exact_correct / len(ids),
        "acceptable_set_hit_rate": set_hit / len(ids),
        "balanced_accuracy": sum(present_recalls) / len(present_recalls),
        "macro_f1_seven_actions": sum(f1.values()) / len(ACTIONS),
        "class_support": support,
        "class_recall": recalls,
        "class_f1": f1,
    }


def compare_quality(
    hybrid_actions: Mapping[str, str],
    all_l2_actions: Mapping[str, str],
    reference_rows: Optional[Sequence[Mapping[str, Any]]] = None,
) -> Dict[str, Any]:
    ids = sorted(all_l2_actions)
    if set(hybrid_actions) != set(ids):
        raise ValueError("hybrid and all-L2 IDs differ")
    agreement_count = sum(hybrid_actions[record_id] == all_l2_actions[record_id] for record_id in ids)
    agreement = agreement_count / len(ids)
    result: Dict[str, Any] = {
        "all_l2_decision_agreement": agreement,
        "all_l2_decision_disagreements": len(ids) - agreement_count,
        "agreement_is_not_ground_truth_accuracy": True,
        "reference_metrics_status": "NOT_EVALUABLE_NO_REFERENCE_LABELS",
        "hybrid": None,
        "all_l2": None,
        "all_l2_minus_hybrid_gap_percentage_points": None,
        "abstained_records": 0,
    }
    if reference_rows is None:
        return result
    labels, acceptable, abstained = parse_reference_annotations(reference_rows)
    unknown = (set(labels) | abstained) - set(ids)
    if unknown:
        raise ValueError(f"reference IDs are outside the experiment: {sorted(unknown)}")
    missing = set(ids) - set(labels) - abstained
    if missing:
        raise ValueError(f"reference annotations are missing records: {sorted(missing)}")
    hybrid_metrics = classification_metrics(hybrid_actions, labels, acceptable)
    l2_metrics = classification_metrics(all_l2_actions, labels, acceptable)
    result.update({
        "reference_metrics_status": "DESCRIPTIVE_REFERENCE_METRICS_AVAILABLE",
        "hybrid": hybrid_metrics,
        "all_l2": l2_metrics,
        "all_l2_minus_hybrid_gap_percentage_points": {
            metric: 100.0 * (float(l2_metrics[metric]) - float(hybrid_metrics[metric]))
            for metric in ("accuracy", "balanced_accuracy", "macro_f1_seven_actions")
        },
        "abstained_records": len(abstained),
    })
    return result
