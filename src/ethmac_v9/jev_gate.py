"""JEV judges L1; only JEV-positive, budget-selected records use L2.

Full-call predictions are used exclusively by the evaluation/feasibility side.
No teacher action is consumed by compression or allocation.
"""
from __future__ import annotations

import json
import math
from collections import Counter
from typing import Any, Mapping, Sequence

from .evaluation import compare_quality, nearest_rank_percentile
from .jev_runner import validate_jev_input
from .models import ACTIONS

REASONS = {"STABLE", "LOW_MARGIN", "RULE_GAP", "POLICY_CONFLICT",
           "MISSING_EVIDENCE", "GOAL_CONFLICT", "MEMORY", "NETWORK", "MULTISTEP", "NOVELTY",
           # Upstream JEV-fast risk codes are valid verifier evidence.  Keeping
           # them verbatim avoids a false or lossy mapping between market and
           # policy conflict, or between uncertainty and conflict.
           "MARKET_CONFLICT", "POLICY_UNCERTAINTY", "MEMORY_CONFLICT", "HIGH_STAKES"}
KEYS = {"v", "id", "error", "gain", "harm", "escalate", "reasons"}


def normalize_output(out: dict) -> list[str]:
    """Canonicalize representation-only gate variants; raw receipts are kept."""
    if not isinstance(out, dict):
        raise ValueError("JEV gate output must be an object")
    repairs = []
    for key in ("error", "gain", "harm"):
        value = out.get(key)
        if isinstance(value, str):
            try:
                repaired = float(value.strip())
            except ValueError:
                continue
            out[key] = repaired
            repairs.append("numeric_string_" + key)
    value = out.get("escalate")
    if isinstance(value, str) and value.strip().lower() in {"true", "false"}:
        out["escalate"] = value.strip().lower() == "true"
        repairs.append("boolean_string_escalate")
    if isinstance(out.get("reasons"), str):
        out["reasons"] = [out["reasons"]]
        repairs.append("singleton_reason_to_list")
    if out.get("reasons") == ["NONE"] and out.get("escalate") is False:
        out["reasons"] = ["STABLE"]
        repairs.append("no_risk_to_stable")
    return repairs


def compact_input(source: Mapping[str, Any]) -> dict:
    validate_jev_input(dict(source))
    state = source["household_state"]
    # Deduplicate only identical claims from the SAME source and time, preserving
    # contradictory content and provenance. No truncation of policy substance.
    evidence = {}
    for row in source["visible_evidence"]:
        item = {key: row.get(key) for key in (
            "claim", "channel", "evidence_type", "source_id", "visible_from",
            "expires_after", "policy_state", "validity_evidenced", "reliability",
            "neighbor_count")}
        fingerprint = json.dumps(item, ensure_ascii=False, sort_keys=True)
        if fingerprint not in evidence:
            evidence[fingerprint] = {"ref": row["evidence_id"], **item, "count": 0}
        evidence[fingerprint]["count"] += 1
    attrs = {k: v for k, v in state["attributes"].items() if k not in {"household_id", "initial_tenure", "liquidity_pressure"}}
    beliefs = {k: v for k, v in state["beliefs"].items() if k != "action_success_counts"}
    memory = [{k: item.get(k) for k in ("round_index", "kind", "channel",
               "content_ref", "credibility", "action", "success", "satisfaction", "regret")}
              for item in state.get("memory", [])[-6:]]
    l1 = source["l1_output"]
    return {
        "id": source["record_id"], "round": source["round"],
        "visible_cutoff": source["visible_cutoff"], "allowed": source["allowed_actions"],
        "family": attrs,
        "state": {k: state[k] for k in ("tenure", "liquid_assets", "liquidity_pressure", "satisfaction", "regret")},
        "beliefs": beliefs, "goals": state["goals"], "memory": memory,
        "memory_omitted": max(0, len(state.get("memory", [])) - len(memory)),
        "evidence": list(evidence.values()),
        "l1": {"action": l1["recommended_action"], "scores": l1["action_scores"],
               "margin": l1["top_two_margin"], "active": l1["active_rule_ids"],
               "suppressed": l1["suppressed_rule_ids"],
               "score_is_probability": False,
               "variant": l1.get("variant", "rules_v1"),
               "market_missing_or_conflicting": l1.get("market_missing_or_conflicting", [])},
        "ontology": source["ontology_features"],
    }


def validate_output(out: dict, record: dict) -> None:
    normalize_output(out)
    if set(out) != KEYS or out["v"] != "jev_gate_v2" or out["id"] != record["id"]:
        raise ValueError("JEV gate schema/id mismatch")
    for key in ("error", "gain", "harm"):
        value = out[key]
        if isinstance(value, bool) or not isinstance(value, (float, int)) or not math.isfinite(value) or not 0 <= value <= 1:
            raise ValueError(f"{key} must be a finite probability")
    if out["gain"] > out["error"] + 1e-9 or out["harm"] > 1 - out["error"] + 1e-9:
        raise ValueError("gain/harm inconsistent with joint-event probability definitions")
    if type(out["escalate"]) is not bool:
        raise ValueError("escalate must be boolean")
    reasons = out["reasons"]
    if not isinstance(reasons, list) or not 1 <= len(reasons) <= 3 or any(not isinstance(x, str) for x in reasons):
        raise ValueError("reasons must contain 1-3 codes")
    if set(reasons) - REASONS or len(set(reasons)) != len(reasons):
        raise ValueError("unknown/duplicate reason")
    if "STABLE" in reasons and (len(reasons) != 1 or out["escalate"]):
        raise ValueError("STABLE conflicts with escalation")
    if out["escalate"] and out["gain"] <= out["harm"]:
        raise ValueError("escalation requires positive predicted net gain")


def allocate(gates: Sequence[dict], predicted_cost: Mapping[str, float],
             jev_tokens: int, config: dict, rate: float) -> dict:
    """Cardinality-constrained knapsack with conservative 100-token units.

    Rank/selection use JEV outputs and ex-ante costs ONLY. Exact dynamic
    programming maximizes predicted net gain on this quantized budget grid.
    Observed selected-L2 costs are audited afterwards, never used to reroute.
    """
    n = len(gates)
    if len({g["id"] for g in gates}) != n or set(predicted_cost) != {g["id"] for g in gates}:
        raise ValueError("allocator IDs mismatch")
    if not 0 <= rate <= config["maximum_l2_rate"]:
        raise ValueError("L2 rate exceeds frozen maximum")
    cap = int(math.floor(n * rate + 1e-12))
    budget = max(0, math.floor(sum(predicted_cost.values()) * config["primary_total_token_ratio"]) - jev_tokens)
    quantum = config["budget_quantum_tokens"]
    units = budget // quantum
    states = {(0, 0): (0.0, ())}
    for g in sorted(gates, key=lambda x: x["id"]):
        value = g["gain"] - g["harm"]
        if not g["escalate"] or value <= 0:
            continue
        cost = math.ceil(predicted_cost[g["id"]] / quantum)
        for (count, used), (score, ids) in list(states.items()):
            key = (count + 1, used + cost)
            if key[0] <= cap and key[1] <= units:
                candidate = (score + value, ids + (g["id"],))
                old = states.get(key)
                if old is None or candidate[0] > old[0] + 1e-12:
                    states[key] = candidate
    best = max(states, key=lambda k: (states[k][0], -k[1], -k[0]))
    score, selected = states[best]
    return {"selected_ids": list(selected), "capacity": cap, "l2_rate_budget": rate,
            "predicted_l2_budget_tokens": budget, "predicted_net_gain": score,
            "predicted_selected_tokens": sum(predicted_cost[i] for i in selected),
            "all_selected_jev_positive": True, "teacher_outputs_used_for_selection": False}


def feasibility(l1: Mapping[str, str], l2: Mapping[str, str], n: int, config: dict) -> dict:
    if not set(l2) <= set(l1) or len(l1) != n:
        raise ValueError("feasibility IDs mismatch")
    mismatches = sum(l1[i] != a for i, a in l2.items())
    tolerated = math.floor(n * (1 - config["target_agreement"]) + 1e-9)
    necessary = max(0, mismatches - tolerated)
    known = len(l2)
    bounds = {}
    for rate in (config["primary_l2_rate"], config["maximum_l2_rate"]):
        cap = math.floor(n * rate + 1e-9)
        bounds[str(rate)] = (n - max(0, mismatches - cap)) / n
    return {"evaluation_only_oracle": True, "known_teacher_records": known,
            "known_l1_l2_disagreements": mismatches, "total_records": n,
            "allowed_disagreements_at_98_percent": tolerated,
            "minimum_l2_calls_lower_bound": necessary, "minimum_l2_rate_lower_bound": necessary / n,
            "optimistic_agreement_upper_bound": bounds,
            "feasible_under_30pct_calls": necessary <= math.floor(n * config["maximum_l2_rate"]),
            "scope": "Same frozen L1 and teacher actions on this development cohort; not population accuracy."}


def usage_ledger(rows: Sequence[dict]) -> dict:
    totals = {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0, "reasoning_tokens": 0}
    unknown = 0
    unknown_latency = 0
    for row in rows:
        # A successful logical response can follow one or more transport/decode
        # retries. Their provider-side token usage is unknowable, so retain the
        # successful receipt while marking each ambiguous HTTP attempt.
        for attempt in row.get("attempts") or []:
            if attempt.get("status") == "transport_or_decode_error":
                unknown += 1
        elapsed = row.get("elapsed_ms_total")
        if not isinstance(elapsed, (int, float)) or not math.isfinite(elapsed) or elapsed <= 0:
            unknown_latency += 1
        usage = (row.get("response") or {}).get("usage")
        if not isinstance(usage, dict) or any(type(usage.get(k)) is not int or usage[k] < 0 for k in ("prompt_tokens", "completion_tokens", "total_tokens")):
            unknown += 1
            continue
        for k in ("prompt_tokens", "completion_tokens", "total_tokens"):
            totals[k] += usage[k]
        details = usage.get("completion_tokens_details") or {}
        if type(details.get("reasoning_tokens")) is int:
            totals["reasoning_tokens"] += details["reasoning_tokens"]
    return {**totals, "attempt_records": len(rows), "unknown_usage_attempts": unknown,
            "unknown_latency_attempts": unknown_latency,
            "latency_seconds": sum(float(r.get("elapsed_ms_total", 0)) for r in rows) / 1000}


def build_report(inputs, gates, l2_decisions, l2_responses, jev_responses,
                 predicted_cost, config, local_latency, reference_rows=None):
    ids = [r["id"] for r in inputs]
    gate_by_id = {r["id"]: r for r in gates}
    teachers = {r["record_id"]: r for r in l2_decisions}
    if len(set(ids)) != len(ids) or set(gate_by_id) != set(ids) or len(gates) != len(ids) or set(teachers) != set(ids) or len(teachers) != len(ids):
        raise ValueError("complete, unique, aligned JEV/L2 records are required")
    l1, l2 = {}, {}
    for r in inputs:
        i = r["id"]
        validate_output(gate_by_id[i], r)
        d = teachers[i]
        f = d["final_decision"]
        if not d["guard_result"]["accepted"] or f["final_source"] != "L2" or f["final_action"] != f["accepted_l2_action"]:
            raise ValueError("invalid/overwritten L2 cannot enter the full-call reference")
        l1[i], l2[i] = r["l1"]["action"], f["final_action"]
    j_book, l_book = usage_ledger(jev_responses), usage_ledger(l2_responses)
    if any(r["record_id"] not in ids for r in list(jev_responses) + list(l2_responses)):
        raise ValueError("ledger contains out-of-cohort record")
    if l_book["total_tokens"] <= 0:
        raise ValueError("full-L2 token denominator is missing")
    l_cost = {i: usage_ledger([r for r in l2_responses if r["record_id"] == i]) for i in ids}
    j_cost = {i: usage_ledger([r for r in jev_responses if r["record_id"] == i]) for i in ids}
    if any(l_cost[i]["attempt_records"] == 0 or j_cost[i]["attempt_records"] == 0 for i in ids):
        raise ValueError("a per-record API ledger is missing")
    baseline_latency = [l_cost[i]["latency_seconds"] for i in ids]
    curve = []
    for rate in config["budget_curve"]:
        allocation = allocate(gates, predicted_cost, j_book["total_tokens"], config, rate)
        chosen = set(allocation["selected_ids"])
        hybrid = {i: l2[i] if i in chosen else l1[i] for i in ids}
        quality = compare_quality(hybrid, l2, reference_rows)
        selected_tokens = sum(l_cost[i]["total_tokens"] for i in chosen)
        hybrid_tokens = j_book["total_tokens"] + selected_tokens
        latencies = [local_latency[i] + j_cost[i]["latency_seconds"] +
                     (l_cost[i]["latency_seconds"] if i in chosen else 0) for i in ids]
        ratio = hybrid_tokens / l_book["total_tokens"]
        baseline_p95 = nearest_rank_percentile(baseline_latency, .95)
        p95ratio = nearest_rank_percentile(latencies, .95) / baseline_p95 if baseline_p95 > 0 else None
        complete_ledger = j_book["unknown_usage_attempts"] + l_book["unknown_usage_attempts"] == 0
        complete_latency = j_book["unknown_latency_attempts"] + l_book["unknown_latency_attempts"] == 0
        audit = {
            "agreement_at_least_98_percent": "PASS" if quality["all_l2_decision_agreement"] >= config["target_agreement"] else "FAIL",
            "token_saving_at_least_50_percent": ("PASS" if ratio <= .5 else "FAIL") if complete_ledger else "NOT_EVALUABLE",
            "token_saving_at_least_60_percent": ("PASS" if ratio <= .4 else "FAIL") if complete_ledger else "NOT_EVALUABLE",
            "l2_call_rate_at_most_30_percent": "PASS" if len(chosen) / len(ids) <= .3 else "FAIL",
            "p95_reduction_at_least_30_percent": ("PASS" if p95ratio <= .7 else "FAIL") if complete_latency and p95ratio is not None else "NOT_EVALUABLE",
            "every_selected_l2_has_positive_jev_gate": "PASS" if all(gate_by_id[i]["escalate"] for i in chosen) else "FAIL",
            "valid_l2_override_zero": "PASS",
            "accuracy_at_least_98_percent": "NOT_EVALUABLE",
            "acc_ba_macro_f1_noninferiority_1pp": "NOT_EVALUABLE",
        }
        if reference_rows is not None:
            audit["descriptive_accuracy_at_least_98_percent"] = (
                "PASS" if quality["hybrid"]["accuracy"] >= config["target_absolute_accuracy"] else "FAIL")
            audit["descriptive_acc_ba_macro_f1_gap_at_most_1pp"] = (
                "PASS" if all(gap <= config["noninferiority_margin_pp"] for gap in
                    quality["all_l2_minus_hybrid_gap_percentage_points"].values()) else "FAIL")
        curve.append({"budget": allocation, "quality": quality,
            "resources": {"l1_api_tokens": 0, "jev_tokens": j_book["total_tokens"],
                "selected_l2_tokens": selected_tokens, "hybrid_tokens": hybrid_tokens,
                "all_l2_tokens": l_book["total_tokens"], "token_saving": 1 - ratio,
                "actual_l2_call_rate": len(chosen) / len(ids),
                "hybrid_serial_seconds": sum(latencies), "all_l2_serial_seconds": sum(baseline_latency),
                "hybrid_p95_seconds": nearest_rank_percentile(latencies, .95),
                "all_l2_p95_seconds": nearest_rank_percentile(baseline_latency, .95),
                "p95_reduction": 1 - p95ratio if p95ratio is not None else None,
                "usage_complete": complete_ledger, "latency_complete": complete_latency},
            "target_audit": audit,
            "decisions": [{"id": i, "l1": l1[i], "jev_approved": gate_by_id[i]["escalate"],
                "selected": i in chosen, "final": hybrid[i], "source": "L2" if i in chosen else "L1",
                "all_l2": l2[i],
                "route_reason": ("JEV_APPROVED_BUDGET_SELECTED" if i in chosen else
                    "JEV_APPROVED_BUT_BUDGET_REJECTED" if gate_by_id[i]["escalate"] else "JEV_REJECTED")}
                for i in ids]})
    primary = next(r for r in curve if r["budget"]["l2_rate_budget"] == config["primary_l2_rate"])
    feasible = feasibility(l1, l2, len(ids), config)
    status = "PILOT_COMPLETE_FORMAL_VALIDATION_PENDING"
    if "FAIL" in primary["target_audit"].values():
        status = "PILOT_FAIL_TARGETS"
    if not feasible["feasible_under_30pct_calls"]:
        status = "L1_CEILING_BLOCKS_98_PERCENT_TARGET"
    return {"status": status, "formal_evaluation_eligible": False,
            "evaluation_mode": "offline paired replay of cached full-L2; latency is reconstruction, not a new end-to-end deployment measurement",
            "primary": primary, "curve": curve, "feasibility": feasible,
            "research_ledger": {"jev": j_book, "all_l2_including_failed_and_retried": l_book,
                                "historical_and_new_total_tokens": j_book["total_tokens"] + l_book["total_tokens"]},
            "l2_action_support": dict(Counter(l2.values())),
            "remaining_targets": {name: "NOT_EVALUABLE" for name in (
                "formal_98_percent_accuracy", "formal_noninferiority_CI",
                "true_error_AUROC_AUPRC_ECE", "net_corrections", "strong_baseline_significance",
                "closed_loop_trajectory", "ontology_agent_ablations",
                "external_realism", "real_hardware_energy_memory", "cash_price_manifest")},
            "next_step": "Improve and validate L1 on disjoint development data before new confirmatory testing; never force escalation rate or relabel actions to pass."}
