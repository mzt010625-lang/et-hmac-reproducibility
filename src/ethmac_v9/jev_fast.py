from __future__ import annotations

import json
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any, Dict, Iterable, List, Mapping, Optional, Sequence, Tuple

from .stage2b_benchmark import sha256_file


def _mean(values: Iterable[float]) -> Optional[float]:
    rows = list(values)
    return sum(rows) / len(rows) if rows else None


def compact_memory(state: Mapping[str, Any]) -> Dict[str, Any]:
    memory = list(state.get("memory") or [])
    by_kind = Counter(str(row.get("kind", "unknown")) for row in memory)
    by_channel = Counter(str(row.get("channel", "unknown")) for row in memory)
    outcomes = [row for row in memory if row.get("success") is not None]
    return {
        "window_size": len(memory),
        "kind_counts": dict(sorted(by_kind.items())),
        "channel_counts": dict(sorted(by_channel.items())),
        "success_count": sum(int(bool(row.get("success"))) for row in outcomes),
        "failure_count": sum(int(not bool(row.get("success"))) for row in outcomes),
        "mean_credibility": _mean(float(row.get("credibility", 0.0)) for row in memory),
        "recent_actions": [str(row["action"]) for row in memory[-3:] if row.get("action")],
    }


def compact_evidence(evidence: Sequence[Mapping[str, Any]]) -> List[Dict[str, Any]]:
    groups: Dict[Tuple[Any, ...], List[Mapping[str, Any]]] = defaultdict(list)
    for row in evidence:
        key = (
            row.get("source_id"), row.get("evidence_type"), row.get("channel"),
            row.get("policy_state"), row.get("validity_evidenced"),
            round(float(row.get("reliability", 0.0)), 3), row.get("provenance"),
        )
        groups[key].append(row)
    compacted: List[Dict[str, Any]] = []
    for _, rows in sorted(groups.items(), key=lambda item: str(item[0])):
        representative = sorted(rows, key=lambda row: str(row["evidence_id"]))[0]
        compacted.append({
            "evidence_id": str(representative["evidence_id"]),
            "visible_from": int(representative["visible_from"]),
            "expires_after": representative.get("expires_after"),
            "channel": representative.get("channel"),
            "evidence_type": representative.get("evidence_type"),
            "source_id": representative.get("source_id"),
            "reliability": round(float(representative.get("reliability", 0.0)), 3),
            "policy_state": representative.get("policy_state"),
            "validity_evidenced": representative.get("validity_evidenced"),
            "neighbor_count": representative.get("neighbor_count"),
            "provenance": representative.get("provenance"),
            "group_size": len(rows),
        })
    return compacted


def compact_jev_record(record: Mapping[str, Any]) -> Dict[str, Any]:
    state = record["household_state"]
    attributes = state["attributes"]
    beliefs = state["beliefs"]
    return {
        "record_id": record["record_id"],
        "household_id": record["household_id"],
        "round": record["round"],
        "visible_cutoff": record["visible_cutoff"],
        "allowed_actions": list(record["allowed_actions"]),
        "household_state": {
            "profile": {
                "lifecycle_stage": attributes["lifecycle_stage"],
                "household_size": attributes["household_size"],
                "dwelling_type": attributes["dwelling_type"],
                "tenure": state["tenure"],
                "income_monthly": attributes["income_monthly"],
                "liquid_assets": state["liquid_assets"],
                "improvement_goal": attributes["improvement_goal"],
                "loss_aversion": attributes["loss_aversion"],
                "risk_perception": attributes["risk_perception"],
                "residential_attachment": attributes["residential_attachment"],
                "peer_sensitivity": attributes["peer_sensitivity"],
                "policy_trust_tendency": attributes["policy_trust_tendency"],
            },
            "dynamic": {
                "liquidity_pressure": state["liquidity_pressure"],
                "satisfaction": state["satisfaction"],
                "regret": state["regret"],
                "current_round": state["current_round"],
            },
            "beliefs": {
                "price_growth_expectation": beliefs["price_growth_expectation"],
                "policy_eligibility_prob": beliefs["policy_eligibility_prob"],
                "affordability_prob": beliefs["affordability_prob"],
                "policy_duration_expectation": beliefs["policy_duration_expectation"],
                "channel_trust": beliefs["channel_trust"],
                "action_success_prob": beliefs["action_success_prob"],
            },
            "goals": state["goals"],
            "memory_summary": compact_memory(state),
        },
        "visible_evidence": compact_evidence(record["visible_evidence"]),
        "l1_output": json.loads(json.dumps(record["l1_output"], ensure_ascii=False)),
        "ontology_features": json.loads(json.dumps(record["ontology_features"], ensure_ascii=False)),
        "router_context": json.loads(json.dumps(record["router_context"], ensure_ascii=False)),
    }


def write_jsonl(path: Path, rows: Sequence[Mapping[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        "".join(json.dumps(row, ensure_ascii=False, separators=(",", ":")) + "\n" for row in rows),
        encoding="utf-8",
    )


def build_fast_ab_package(
    phase1_jev_path: Path,
    phase1_l2_path: Path,
    phase1_records_path: Path,
    phase1_reference_requests_path: Path,
    thinking_parsed_path: Path,
    selection_manifest_path: Path,
    output_dir: Path,
) -> Dict[str, Any]:
    load = lambda path: [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]
    phase1_jev = load(phase1_jev_path)
    phase1_l2 = load(phase1_l2_path)
    phase1_records = load(phase1_records_path)
    phase1_references = load(phase1_reference_requests_path)
    thinking = load(thinking_parsed_path)
    selection = load(selection_manifest_path)
    ids = [str(row["record_id"]) for row in thinking]
    if len(ids) != 16 or len(set(ids)) != 16:
        raise ValueError("the efficiency A/B package requires the 16 successful thinking-baseline records")
    jev_by_id = {str(row["record_id"]): row for row in phase1_jev}
    l2_by_id = {str(row["l2_request"]["record_id"]): row for row in phase1_l2}
    selection_by_id = {str(row["record_id"]): row for row in selection}
    record_by_id = {str(row["record_id"]): row for row in phase1_records}
    reference_by_id = {str(row["record_id"]): row for row in phase1_references}
    if any(record_id not in jev_by_id or record_id not in l2_by_id for record_id in ids):
        raise ValueError("thinking baseline record is missing from frozen Phase 1 inputs")
    compact = [compact_jev_record(jev_by_id[record_id]) for record_id in ids]
    matched_l2 = [l2_by_id[record_id] for record_id in ids]
    matched_selection = [selection_by_id[record_id] for record_id in ids]
    matched_records = [record_by_id[record_id] for record_id in ids]
    matched_references = [reference_by_id[record_id] for record_id in ids]
    output_dir.mkdir(parents=True, exist_ok=True)
    write_jsonl(output_dir / "compact_jev_inputs.jsonl", compact)
    write_jsonl(output_dir / "matched_l2_cases.jsonl", matched_l2)
    write_jsonl(output_dir / "thinking_baseline.jsonl", thinking)
    write_jsonl(output_dir / "selection_manifest.jsonl", matched_selection)
    write_jsonl(output_dir / "matched_records.jsonl", matched_records)
    write_jsonl(output_dir / "matched_reference_requests.jsonl", matched_references)
    original_bytes = sum(len(json.dumps(jev_by_id[record_id], ensure_ascii=False, separators=(",", ":")).encode("utf-8")) for record_id in ids)
    compact_bytes = sum(len(json.dumps(row, ensure_ascii=False, separators=(",", ":")).encode("utf-8")) for row in compact)
    manifest = {
        "version": "stage7_jev_fast_ab_v1",
        "status": "READY_FOR_LOCAL_API_RUN",
        "formal_evaluation_eligible": False,
        "record_count": len(ids),
        "record_ids": ids,
        "source_counts": dict(sorted(Counter(str(row["source_line"]) for row in matched_selection).items())),
        "input_compression": {
            "original_record_bytes": original_bytes,
            "compact_record_bytes": compact_bytes,
            "compact_to_original_ratio": compact_bytes / original_bytes,
            "reduction_fraction": 1.0 - compact_bytes / original_bytes,
        },
        "gates": {
            "schema_success_rate": 1.0,
            "mean_fast_jev_total_tokens_over_l2": 0.40,
            "mean_l1_plus_fast_jev_latency_over_l2": 0.50,
            "target_l2_call_rate": 0.20,
            "maximum_l2_call_rate": 0.30,
            "minimum_resource_reduction_vs_all_l2": 0.50,
            "end_to_end_total_tokens_over_all_l2": 0.40,
            "end_to_end_serial_latency_over_all_l2": 1.00,
            "end_to_end_p95_latency_over_all_l2": 0.70,
            "quality_noninferiority_margin_percentage_points": 1.00,
            "thinking_baseline_route_agreement": 0.75,
            "valid_l2_override_count": 0,
        },
        "files": {},
        "interpretation_boundary": "Resource/stability A/B only. The thinking baseline is not ground truth and the sample is conditioned on prior successful responses.",
    }
    for name in (
        "compact_jev_inputs.jsonl", "matched_l2_cases.jsonl", "thinking_baseline.jsonl",
        "selection_manifest.jsonl", "matched_records.jsonl", "matched_reference_requests.jsonl",
    ):
        manifest["files"][name] = sha256_file(output_dir / name)
    (output_dir / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return manifest
