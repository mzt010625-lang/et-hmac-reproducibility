#!/usr/bin/env python3
"""Run the frozen Stage 9D optimized holdout against independent full L2."""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import getpass
import hashlib
import json
import math
import os
from pathlib import Path
import random
import statistics
import sys

ROOT = Path(__file__).resolve().parent
sys.path[:0] = [str(ROOT), str(ROOT / "src")]

from ethmac_v9.jev_runner import sha256_file
from ethmac_v9.stage8d_router import route_reasons as hard_guard_reasons
from ethmac_v9.stage8f_contract import base_action
from ethmac_v9.stage8g_router import coarse_route_reasons
import main_stage8g_isolated_jev_comparison as g
import main_stage8h_final_development as h
import main_stage9 as s9

CONFIG = ROOT / "configs/stage9d_optimized_holdout_v1.json"
DATA = ROOT / "data/stage9d_optimized_holdout_v1"
MANIFEST = DATA / "dataset_manifest.json"
AUDIT = DATA / "pre_api_audit.json"
COHORTS = ("natural", "stress", "policy_ood")
INPUTS = {name: DATA / f"{name}_inputs.jsonl" for name in COHORTS}
SELECTION_MANIFESTS = {name: DATA / f"{name}_selection_manifest.jsonl" for name in COHORTS}
OUTPUT_ROOT = ROOT / "runs/stage9d_optimized_holdout_v1"
BOOTSTRAP_REPLICATES = 2000
SEED = 20261009


def prepare() -> tuple[dict, dict[str, list[dict]], Path]:
    config = json.loads(CONFIG.read_text(encoding="utf-8"))
    manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
    audit = json.loads(AUDIT.read_text(encoding="utf-8"))
    if manifest["status"] != "FROZEN_STAGE9D_INPUTS_READY" or audit["status"] != "PASS_STAGE9D_PRE_API_ISOLATION_GATE":
        raise RuntimeError("Stage 9D pre-API gates are not frozen")
    for section in ("source_hashes", "output_hashes"):
        for relative, expected in manifest[section].items():
            path = ROOT / relative
            if not path.exists() or sha256_file(path) != expected:
                raise RuntimeError("Stage 9D frozen hash mismatch: " + relative)
    cohorts = {name: s9.rows(path) for name, path in INPUTS.items()}
    if {name: len(values) for name, values in cohorts.items()} != config["cohorts"]:
        raise RuntimeError("Stage 9D input cardinality changed")
    frozen = [CONFIG, MANIFEST, AUDIT, h.JEV_SYSTEM, h.JEV_USER, h.JEV_SCHEMA,
              g.L2_SYSTEM, g.L2_USER, g.L2_SCHEMA,
              ROOT / "src/ethmac_v9/stage8d_router.py", ROOT / "src/ethmac_v9/stage8f_contract.py",
              ROOT / "src/ethmac_v9/stage8g_router.py", Path(__file__), *INPUTS.values(),
              *SELECTION_MANIFESTS.values()]
    hashes = {str(path.relative_to(ROOT)): sha256_file(path) for path in frozen}
    digest = hashlib.sha256(json.dumps(hashes, sort_keys=True).encode()).hexdigest()
    folder = OUTPUT_ROOT / ("frozen_" + digest[:16])
    folder.mkdir(parents=True, exist_ok=True)
    run_manifest = {
        "version": config["config_version"], "status": "FROZEN_STAGE9D_RUN",
        "provider": config["provider"], "model": config["model"],
        "cohorts": config["cohorts"], "hard_guard_bypasses_jev": True,
        "execution_order": config["execution_order"], "files": hashes,
        "response_reuse_between_hybrid_and_full_reference": False,
        "external_upload_authorized_by_user": True, "api_key_recorded": False,
        "created_at_utc": datetime.now(timezone.utc).isoformat(),
    }
    path = folder / "run_manifest.json"
    if path.exists():
        old = json.loads(path.read_text(encoding="utf-8"))
        for key in ("version", "provider", "model", "cohorts", "execution_order", "files"):
            if old.get(key) != run_manifest.get(key):
                raise RuntimeError("Stage 9D run manifest mismatch: " + key)
    else:
        s9.save_json(path, run_manifest)
    for cohort in COHORTS:
        (folder / cohort / "hybrid").mkdir(parents=True, exist_ok=True)
        (folder / cohort / "full").mkdir(parents=True, exist_ok=True)
    return config, cohorts, folder


def freeze_selection(records: list[dict], jev: dict[str, dict], path: Path) -> list[dict]:
    output = []
    expected_jev = {record["id"] for record in records
                    if coarse_route_reasons(record) and not hard_guard_reasons(record)}
    if set(jev) != expected_jev:
        raise RuntimeError("nonhard JEV ledger mismatch")
    for record in records:
        hard = hard_guard_reasons(record); coarse = coarse_route_reasons(record)
        answer = jev.get(record["id"])
        jev_selected = bool(answer and answer["should_escalate"])
        output.append({
            "record_id": record["id"], "base_action": base_action(record),
            "coarse_candidate": bool(coarse), "coarse_reasons": coarse,
            "hard_guard_selected": bool(hard), "hard_guard_reasons": hard,
            "jev_called": record["id"] in expected_jev,
            "jev_selected": jev_selected,
            "jev_probability": float(answer["need_l2_probability"]) if answer else None,
            "route_to_l2": bool(hard) or jev_selected,
            "route_equation": "hard_guard_event OR jev_should_escalate",
            "hard_guard_bypasses_jev": True,
        })
    if path.exists():
        if s9.rows(path) != output:
            raise RuntimeError("Stage 9D frozen route selection changed")
    else:
        s9.save_jsonl(path, output)
    return output


def percentile(values: list[float], probability: float) -> float:
    ordered = sorted(values)
    if not ordered:
        return 0.0
    return ordered[max(0, math.ceil(probability * len(ordered)) - 1)]


def household_maps() -> dict[str, dict[str, str]]:
    return {cohort: {row["record_id"]: str(row["household_id"])
                     for row in s9.rows(SELECTION_MANIFESTS[cohort])} for cohort in COHORTS}


def cohort_rows(cohort: str, records: list[dict], folder: Path,
                household_map: dict[str, str]) -> list[dict]:
    target = folder / cohort
    selection = {row["record_id"]: row for row in s9.rows(target / "route_selection.jsonl")}
    hybrid = s9.response_map(target / "hybrid", "l2")
    full = s9.response_map(target / "full", "l2")
    jbook = s9.attempt_book(target / "hybrid", "jev")
    hbook = s9.attempt_book(target / "hybrid", "l2")
    fbook = s9.attempt_book(target / "full", "l2")
    output = []
    for record in records:
        record_id = record["id"]; route = selection[record_id]
        selected = route["route_to_l2"]
        base = route["base_action"]
        reference = full[record_id]["final_action"]
        prediction = hybrid[record_id]["final_action"] if selected else base
        j = jbook.get(record_id, {"tokens": 0, "seconds": 0.0, "paid_attempts": 0})
        hh = hbook.get(record_id, {"tokens": 0, "seconds": 0.0, "paid_attempts": 0})
        ff = fbook[record_id]
        output.append({
            "cohort": cohort, "id": record_id, "household": household_map[record_id],
            "base": base, "reference": reference, "prediction": prediction,
            "selected": selected, "hard": route["hard_guard_selected"],
            "jev_called": route["jev_called"], "jev_selected": route["jev_selected"],
            "full_changed": reference != base, "match": prediction == reference,
            "jev_tokens": j["tokens"], "hybrid_l2_tokens": hh["tokens"], "full_tokens": ff["tokens"],
            "jev_seconds": j["seconds"], "hybrid_l2_seconds": hh["seconds"], "full_seconds": ff["seconds"],
            "paid_attempts": j["paid_attempts"] + hh["paid_attempts"] + ff["paid_attempts"],
        })
    return output


def summarize(items: list[dict]) -> dict:
    reference = [item["reference"] for item in items]
    predicted = [item["prediction"] for item in items]
    selected = [item for item in items if item["selected"]]
    changed = [item for item in items if item["full_changed"]]
    tp = sum(item["selected"] and item["full_changed"] for item in items)
    fp = sum(item["selected"] and not item["full_changed"] for item in items)
    fn = sum(not item["selected"] and item["full_changed"] for item in items)
    tn = len(items) - tp - fp - fn
    jev_tokens = sum(item["jev_tokens"] for item in items)
    selected_tokens = sum(item["hybrid_l2_tokens"] for item in items)
    full_tokens = sum(item["full_tokens"] for item in items)
    result = g.class_metrics(reference, predicted)
    result.update({
        "records": len(items), "hard_guard": sum(item["hard"] for item in items),
        "jev_calls": sum(item["jev_called"] for item in items),
        "l2_calls": len(selected), "l2_rate": len(selected) / len(items),
        "route_vs_full_l2_change": {"tp": tp, "fp": fp, "fn": fn, "tn": tn,
            "recall": tp / (tp + fn) if tp + fn else 0.0,
            "precision": tp / (tp + fp) if tp + fp else 0.0},
        "resources": {"jev_tokens": jev_tokens, "selected_l2_tokens": selected_tokens,
            "hybrid_tokens": jev_tokens + selected_tokens, "full_l2_tokens": full_tokens,
            "token_saving_rate": 1 - (jev_tokens + selected_tokens) / full_tokens,
            "hybrid_p95_seconds": percentile([
                item["jev_seconds"] + item["hybrid_l2_seconds"] for item in items], .95),
            "full_l2_p95_seconds": percentile([item["full_seconds"] for item in items], .95)},
        "decision_precedence": {"selected_l2_final": len(selected), "valid_l2_overwritten": 0},
        "interpretation": "Independent full-L2 alignment, not observed household behavior accuracy.",
    })
    return result


def quantile(values: list[float], probability: float) -> float:
    ordered = sorted(values); position = (len(ordered) - 1) * probability
    lo = math.floor(position); hi = math.ceil(position)
    return ordered[lo] if lo == hi else ordered[lo] + (ordered[hi] - ordered[lo]) * (position - lo)


def bootstrap(items: list[dict]) -> dict:
    clusters: dict[str, list[dict]] = {}
    for item in items:
        clusters.setdefault(item["household"], []).append(item)
    keys = sorted(clusters); rng = random.Random(SEED); values = {key: [] for key in (
        "accuracy", "balanced_accuracy", "macro_f1", "token_saving_rate", "l2_rate")}
    for _ in range(BOOTSTRAP_REPLICATES):
        sample = [item for key in rng.choices(keys, k=len(keys)) for item in clusters[key]]
        summary = summarize(sample)
        values["accuracy"].append(summary["accuracy"])
        values["balanced_accuracy"].append(summary["balanced_accuracy"])
        values["macro_f1"].append(summary["macro_f1"])
        values["token_saving_rate"].append(summary["resources"]["token_saving_rate"])
        values["l2_rate"].append(summary["l2_rate"])
    point = summarize(items)
    points = {"accuracy": point["accuracy"], "balanced_accuracy": point["balanced_accuracy"],
              "macro_f1": point["macro_f1"], "token_saving_rate": point["resources"]["token_saving_rate"],
              "l2_rate": point["l2_rate"]}
    return {"replicates": BOOTSTRAP_REPLICATES, "clusters": len(keys), "cluster_unit": "household",
            "metrics": {key: {"point": points[key], "ci95": [quantile(value, .025), quantile(value, .975)]}
                        for key, value in values.items()}}


def run_cohort(name: str, records: list[dict], config: dict, folder: Path,
               budget: s9.TokenBudget, key: str, retry_failed: bool) -> None:
    target = folder / name
    jev_records = [record for record in records
                   if coarse_route_reasons(record) and not hard_guard_reasons(record)]
    print(f"=== {name} 1/4：非硬守卫JEV {len(jev_records)}条 ===", flush=True)
    s9.call_jev(config, jev_records, target / "hybrid", budget, key, retry_failed)
    jev = s9.response_map(target / "hybrid", "jev")
    selection = freeze_selection(records, jev, target / "route_selection.jsonl")
    selected_ids = {row["record_id"] for row in selection if row["route_to_l2"]}
    selected = [record for record in records if record["id"] in selected_ids]
    print(f"=== {name} 2/4：冻结路由，{len(selected)}条进入L2 ===", flush=True)
    print(f"=== {name} 3/4：混合路线独立L2 {len(selected)}条 ===", flush=True)
    s9.call_l2(config, selected, target / "hybrid", budget, key, retry_failed)
    print(f"=== {name} 4/4：独立全量L2参考 {len(records)}条 ===", flush=True)
    s9.call_l2(config, records, target / "full", budget, key, retry_failed)


def finalize(cohorts: dict[str, list[dict]], folder: Path) -> dict:
    hh = household_maps(); all_rows = []; by_cohort = {}
    for cohort, records in cohorts.items():
        values = cohort_rows(cohort, records, folder, hh[cohort])
        all_rows.extend(values); by_cohort[cohort] = summarize(values)
    overall = summarize(all_rows)
    result = {
        "status": "FROZEN_STAGE9D_COMPLETE", "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "by_cohort": by_cohort, "overall": overall, "bootstrap": bootstrap(all_rows),
        "claim_boundary": "Model-reference alignment only; not real-world household behavior accuracy.",
        "hard_guard_bypass_confirmed": True,
        "all_valid_selected_l2_final": overall["decision_precedence"]["valid_l2_overwritten"] == 0,
    }
    s9.save_json(folder / "stage9d_final_metrics.json", result)
    lines = ["# Stage 9D 优化架构独立复验", "", "硬守卫样本直接进入 L2；JEV 只审查非硬守卫粗候选。", "",
             "| 队列 | N | 一致率 | BA | Macro-F1 | L2率 | Token节省 | P95混合/全L2(s) |",
             "|---|---:|---:|---:|---:|---:|---:|---:|"]
    for cohort in COHORTS:
        value = by_cohort[cohort]; resource = value["resources"]
        lines.append(f"| {cohort} | {value['records']} | {value['accuracy']:.2%} | {value['balanced_accuracy']:.2%} | {value['macro_f1']:.2%} | {value['l2_rate']:.2%} | {resource['token_saving_rate']:.2%} | {resource['hybrid_p95_seconds']:.2f}/{resource['full_l2_p95_seconds']:.2f} |")
    resource = overall["resources"]
    lines.append(f"| overall | {overall['records']} | {overall['accuracy']:.2%} | {overall['balanced_accuracy']:.2%} | {overall['macro_f1']:.2%} | {overall['l2_rate']:.2%} | {resource['token_saving_rate']:.2%} | {resource['hybrid_p95_seconds']:.2f}/{resource['full_l2_p95_seconds']:.2f} |")
    lines += ["", "注：准确率、BA与Macro-F1均以独立全量L2为操作参考，不是现实家庭行为准确率。",
              "全部有效L2输出拥有最终决策权，未发生L1/JEV覆盖L2。", ""]
    (folder / "STAGE9D_FINAL_REPORT.md").write_text("\n".join(lines), encoding="utf-8")
    freeze = {"status": result["status"], "network_called": True, "api_key_recorded": False,
              "outputs": {name: sha256_file(folder / name) for name in (
                  "stage9d_final_metrics.json", "STAGE9D_FINAL_REPORT.md")},
              "next_stage": "Stage 9E closed-loop multi-round ABM and trajectory-level evaluation"}
    s9.save_json(folder / "stage9d_final_freeze_manifest.json", freeze)
    return result


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--live", action="store_true")
    parser.add_argument("--retry-failed", action="store_true")
    args = parser.parse_args()
    config, cohorts, folder = prepare()
    audit = json.loads(AUDIT.read_text(encoding="utf-8"))
    estimated_calls = sum(len(value) for value in cohorts.values()) + sum(audit["nonhard_jev_candidates"].values()) + sum(audit["hard_guard_candidates"].values())
    if not args.live:
        print(json.dumps({"status": "READY_STAGE9D_OPTIMIZED_HOLDOUT", "network_called": False,
            "run_folder": str(folder), "records": sum(map(len, cohorts.values())),
            "nonhard_jev_calls_max": sum(audit["nonhard_jev_candidates"].values()),
            "hard_guard_direct_l2_min": sum(audit["hard_guard_candidates"].values()),
            "full_l2_calls": sum(map(len, cohorts.values())), "estimated_calls_lower_bound": estimated_calls,
            "token_hard_stop": config["token_hard_stop"], "model": config["model"]}, ensure_ascii=False, indent=2))
        return 0
    s9.endpoint_dns_preflight(config["base_url"]); s9.endpoint_connectivity_preflight(config["base_url"])
    key = os.environ.get("DEEPSEEK_API_KEY") or getpass.getpass("请输入DEEPSEEK_API_KEY（输入不会显示）: ").strip()
    if not key:
        raise RuntimeError("DEEPSEEK_API_KEY is empty")
    lock = folder / ".run_lock"; s9.acquire_run_lock(lock)
    try:
        budget = s9.TokenBudget(folder, int(config["token_hard_stop"]))
        for cohort in COHORTS:
            run_cohort(cohort, cohorts[cohort], config, folder, budget, key, args.retry_failed)
        result = finalize(cohorts, folder)
        print(json.dumps({"status": result["status"], "folder": str(folder),
            "overall": result["overall"], "bootstrap": result["bootstrap"]}, ensure_ascii=False, indent=2))
    finally:
        s9.release_run_lock(lock)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
