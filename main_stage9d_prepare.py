#!/usr/bin/env python3
"""Freeze a new Stage 9D cohort for the hard-guard-bypass architecture."""
from __future__ import annotations

from collections import Counter, defaultdict
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parent
sys.path[:0] = [str(ROOT), str(ROOT / "src")]

from ethmac_v9.rule_engine import DefeasibleRuleEngine
from ethmac_v9.stage2b_benchmark import load_jsonl
from ethmac_v9.stage8d_router import route_reasons as hard_guard_reasons
from ethmac_v9.stage8g_router import coarse_route_reasons
from ethmac_v9.jev_runner import sha256_file
import main_stage9_prepare as p

CONFIG = ROOT / "configs/stage9d_optimized_holdout_v1.json"
OUTPUT = ROOT / "data/stage9d_optimized_holdout_v1"
STAGE9_DATA = ROOT / "data/stage9_confirmatory_v1"
STAGE9_RUN = ROOT / "runs/stage9_confirmatory_official_v2/frozen_e783101aa1a16522"


def select_unseen_pilot_natural(records: list[dict], excluded: set[str], config: dict) -> list[dict]:
    by_world: dict[str, dict[str, list[dict]]] = defaultdict(lambda: defaultdict(list))
    for record in records:
        if record["split"] == "pilot" and record["household_id"] not in excluded:
            by_world[record["world_id"]][record["household_id"]].append(record)
    candidates = [(world_id, household) for world_id in sorted(by_world) for household in by_world[world_id]]
    needed = int(config["natural_design"]["households"])
    ranked = sorted(candidates, key=lambda pair: (
        p.stable_hash(config["seed"], "stage9d-natural", pair[0], pair[1]), pair))
    if len(ranked) < needed:
        raise RuntimeError("insufficient never-exposed pilot households")
    selected = {household for _, household in ranked[:needed]}
    output = [record for record in records if record["household_id"] in selected]
    output.sort(key=lambda value: (p.stable_hash(config["seed"], "stage9d-order", value["household_id"]),
                                   int(value["round"])))
    if len(selected) != int(config["natural_design"]["households"]) or len(output) != int(config["cohorts"]["natural"]):
        raise RuntimeError("unseen pilot natural cardinality mismatch")
    return output


def paired_stress_parents(natural_raw: list[dict], config: dict) -> list[tuple[str, dict]]:
    by_household: dict[str, list[dict]] = defaultdict(list)
    for record in natural_raw:
        by_household[str(record["household_id"])].append(record)
    output = []
    needed = int(config["stress_design"]["records_per_condition"])
    for condition in config["stress_design"]["conditions"]:
        ranked = sorted(by_household, key=lambda value: (
            p.stable_hash(config["seed"], "stage9d-stress", condition, value), value))[:needed]
        for household in ranked:
            candidates = sorted(by_household[household], key=lambda value: int(value["round"]))
            index = int(p.stable_hash(config["seed"], condition, household, "round")[:8], 16) % len(candidates)
            output.append((condition, candidates[index]))
    return output


def paired_ood_parents(natural_raw: list[dict], natural_inputs: dict[str, dict],
                       config: dict) -> list[tuple[str, dict]]:
    """Sample independently within condition; cross-condition pairing is allowed."""
    output = []
    needed = int(config["policy_ood_design"]["records_per_condition"])
    for code in config["policy_ood_design"]["conditions"]:
        spec = p.OOD_REGISTRY[code]
        compatible = [record for record in natural_raw
                      if spec["requires"] in natural_inputs[record["record_id"]]["allowed"]]
        compatible.sort(key=lambda value: (
            p.stable_hash(config["seed"], "stage9d-ood", code, value["record_id"]), value["record_id"]))
        if len(compatible) < needed:
            raise RuntimeError(f"insufficient compatible unseen OOD parents for {code}")
        output.extend((code, record) for record in compatible[:needed])
    return output


def main() -> int:
    config = json.loads(CONFIG.read_text(encoding="utf-8"))
    source_records = load_jsonl(p.NATURAL_SOURCE)
    source_requests = {row["record_id"]: row for row in load_jsonl(p.REQUEST_SOURCE)}
    provider_ids = p.prior_provider_ids()
    for path in STAGE9_RUN.glob("**/*_responses.jsonl"):
        for row in load_jsonl(path):
            record_id = row.get("record_id")
            if isinstance(record_id, str):
                provider_ids.add(record_id)
    excluded = p.previously_selected_households(provider_ids)
    for path in (STAGE9_DATA / "natural_selection_manifest.jsonl",
                 STAGE9_DATA / "stress_selection_manifest.jsonl"):
        excluded.update(str(row["household_id"]) for row in load_jsonl(path))
    engine = DefeasibleRuleEngine.from_file(p.RULES)

    print("[1/6] 选择100个全新家庭并保留四轮轨迹", flush=True)
    natural_raw = select_unseen_pilot_natural(source_records, excluded, config)
    natural_inputs = [p.convert(row, source_requests[row["record_id"]], engine) for row in natural_raw]
    natural_by_id = {row["record_id"]: value for row, value in zip(natural_raw, natural_inputs)}
    natural_households = {row["household_id"] for row in natural_raw}

    print("[2/6] 构建420条全新家庭压力记录", flush=True)
    stress_parents = paired_stress_parents(natural_raw, config)
    stress_raw, stress_manifest = p.build_stress(stress_parents, config)
    stress_inputs = [p.convert(row, source_requests[row["parent_sample_id"]], engine) for row in stress_raw]

    print(f"[3/6] 构建{config['cohorts']['policy_ood']}条配对合成政策OOD记录", flush=True)
    ood_parents = paired_ood_parents(natural_raw, natural_by_id, config)
    ood_raw, ood_inputs, ood_manifest = p.build_ood(ood_parents, source_requests, engine, config)
    cohorts = {"natural": natural_inputs, "stress": stress_inputs, "policy_ood": ood_inputs}
    expected = {key: int(value) for key, value in config["cohorts"].items()}
    if {key: len(value) for key, value in cohorts.items()} != expected:
        raise RuntimeError("Stage 9D cohort cardinality mismatch")

    print("[4/6] 执行隔离、未来信息与目标泄漏审计", flush=True)
    all_ids = [row["id"] for values in cohorts.values() for row in values]
    if len(all_ids) != len(set(all_ids)) or set(all_ids) & provider_ids:
        raise RuntimeError("Stage 9D record isolation failure")
    stage9_ids = {row["record_id"] for path in (
        STAGE9_DATA / "natural_selection_manifest.jsonl",
        STAGE9_DATA / "stress_selection_manifest.jsonl",
        STAGE9_DATA / "policy_ood_selection_manifest.jsonl") for row in load_jsonl(path)}
    if set(all_ids) & stage9_ids:
        raise RuntimeError("Stage 9D overlaps Stage 9 record IDs")
    banned = {"expected_action", "expected_final_action", "expected_route", "teacher_action",
              "reference_action", "l2_action", "condition_code", "condition_name", "polarity"}
    banned_hits = []
    future = 0
    for cohort, values in cohorts.items():
        for row in values:
            banned_hits.extend(f"{cohort}:{row['id']}:{hit}" for hit in p.recursive_key_hits(row, banned))
            future += sum(int(item.get("visible_from") or 0) > int(row["visible_cutoff"])
                          for item in row.get("evidence", []))
    if banned_hits or future:
        raise RuntimeError("Stage 9D leakage audit failure")
    stress_households = {row["household_id"] for row in stress_raw}
    if stress_households - natural_households or natural_households & excluded:
        raise RuntimeError("Stage 9D household isolation failure")

    print("[5/6] 写入冻结输入与审计", flush=True)
    OUTPUT.mkdir(parents=True, exist_ok=True)
    artifacts = {
        "natural_source_records.jsonl": natural_raw,
        "natural_inputs.jsonl": natural_inputs,
        "natural_selection_manifest.jsonl": [{
            "record_id": row["record_id"], "household_id": row["household_id"],
            "world_id": row["world_id"], "round": row["round"], "source_split": row["split"]
        } for row in natural_raw],
        "stress_source_records.jsonl": stress_raw,
        "stress_inputs.jsonl": stress_inputs,
        "stress_selection_manifest.jsonl": stress_manifest,
        "policy_ood_source_records.jsonl": ood_raw,
        "policy_ood_inputs.jsonl": ood_inputs,
        "policy_ood_selection_manifest.jsonl": ood_manifest,
    }
    for name, values in artifacts.items():
        p.write_jsonl(OUTPUT / name, values)
    audit = {
        "status": "PASS_STAGE9D_PRE_API_ISOLATION_GATE", "network_called": False,
        "counts": expected, "total_records": len(all_ids),
        "record_overlap_with_prior_provider_responses": len(set(all_ids) & provider_ids),
        "record_overlap_with_stage9": len(set(all_ids) & stage9_ids),
        "excluded_prior_households": len(excluded),
        "natural_unique_households": len(natural_households),
        "natural_complete_four_round_households": sum(
            {int(row["round"]) for row in natural_raw if row["household_id"] == household} == {1, 2, 3, 4}
            for household in natural_households),
        "stress_unique_households": len(stress_households),
        "natural_stress_household_overlap": len(natural_households & stress_households),
        "paired_design": True,
        "future_evidence_count": future, "banned_target_key_hits": banned_hits,
        "coarse_candidates": {name: sum(bool(coarse_route_reasons(row)) for row in values)
                              for name, values in cohorts.items()},
        "hard_guard_candidates": {name: sum(bool(hard_guard_reasons(row)) for row in values)
                                  for name, values in cohorts.items()},
        "nonhard_jev_candidates": {name: sum(bool(coarse_route_reasons(row)) and not bool(hard_guard_reasons(row))
                                                   for row in values) for name, values in cohorts.items()},
        "stress_condition_counts": dict(Counter(row["condition_code"] for row in stress_manifest)),
        "policy_ood_condition_counts": dict(Counter(row["condition_code"] for row in ood_manifest)),
        "interpretation_boundaries": [
            "Synthetic household-event records, not observed choices.",
            "Full-L2 alignment is not real-world behavior accuracy.",
            "Stage 9D tests a frozen post-Stage-9 architecture on 100 households never sent to a provider before this stage.",
            "Natural, stress and policy-OOD records are paired within those households; inference must cluster by household.",
        ],
    }
    p.write_json(OUTPUT / "pre_api_audit.json", audit)

    print("[6/6] 生成SHA-256冻结清单", flush=True)
    output_files = sorted(path for path in OUTPUT.iterdir() if path.is_file() and path.name != "dataset_manifest.json")
    source_files = [CONFIG, p.NATURAL_SOURCE, p.REQUEST_SOURCE, p.SOURCE_MANIFEST, p.RULES,
                    STAGE9_RUN / "stage9_final_freeze_manifest.json", Path(__file__)]
    manifest = {
        "version": config["config_version"], "status": "FROZEN_STAGE9D_INPUTS_READY",
        "network_called": False, "api_calls_performed": 0, "records": len(all_ids),
        "cohorts": expected, "route_equation": config["route_equation"],
        "hard_guard_bypasses_jev": True, "response_reuse_between_hybrid_and_full_reference": False,
        "source_hashes": {str(path.relative_to(ROOT)): sha256_file(path) for path in source_files},
        "output_hashes": {str(path.relative_to(ROOT)): sha256_file(path) for path in output_files},
        "all_ids_sha256": hashlib.sha256("\n".join(all_ids).encode()).hexdigest(),
        "external_upload_authorized_by_user": True, "api_key_recorded": False,
        "created_at_utc": datetime.now(timezone.utc).isoformat(),
    }
    p.write_json(OUTPUT / "dataset_manifest.json", manifest)
    print(json.dumps({"manifest": manifest, "audit": audit}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
