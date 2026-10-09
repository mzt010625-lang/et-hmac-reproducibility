#!/usr/bin/env python3
"""Stage 9G local deployment benchmark on frozen Stage 9D inputs/receipts."""
from __future__ import annotations

import hashlib
import json
import math
import platform
import resource
import statistics
import time
from pathlib import Path
from typing import Any, Dict, List

from src.ethmac_v9.stage8d_router import route_reasons as hard_guard_reasons
from src.ethmac_v9.stage8f_contract import base_action
from src.ethmac_v9.stage8g_router import coarse_route_reasons


ROOT = Path(__file__).resolve().parent
DATA = ROOT / "data/stage9d_optimized_holdout_v1"
RUN = ROOT / "runs/stage9d_optimized_holdout_v1/frozen_8058ea605c2771e8"
OUT_ROOT = ROOT / "runs/stage9g_deployment_benchmark_v1"
COHORTS = ("natural", "stress", "policy_ood")
PASSES = 500


def rows(path: Path) -> List[Dict[str, Any]]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def percentile(values: List[float], p: float) -> float:
    ordered = sorted(values)
    return ordered[max(0, math.ceil(p * len(ordered)) - 1)] if ordered else 0.0


def usage(path: Path) -> Dict[str, Dict[str, float]]:
    result = {}
    if not path.exists():
        return result
    for row in rows(path):
        result[row["record_id"]] = {
            "seconds": float(row.get("elapsed_ms_total", 0.0)) / 1000,
            "tokens": int(row.get("response", {}).get("usage", {}).get("total_tokens", 0) or 0),
        }
    return result


def canonical_bytes(record: Dict[str, Any]) -> bytes:
    return json.dumps(record, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")


def main() -> int:
    inputs = []
    routes = {}
    jev = {}; hybrid_l2 = {}; full_l2 = {}
    for cohort in COHORTS:
        for record in rows(DATA / f"{cohort}_inputs.jsonl"):
            inputs.append((cohort, record))
        for row in rows(RUN / cohort / "route_selection.jsonl"):
            routes[row["record_id"]] = row
        jev.update(usage(RUN / cohort / "hybrid/jev_responses.jsonl"))
        hybrid_l2.update(usage(RUN / cohort / "hybrid/l2_responses.jsonl"))
        full_l2.update(usage(RUN / cohort / "full/l2_responses.jsonl"))
    if len(inputs) != 1020 or len(routes) != 1020 or len(full_l2) != 1020:
        raise RuntimeError("Stage 9D deployment benchmark inputs are incomplete")

    # Warm up imported rule functions before timing.
    for _, record in inputs[:32]:
        base_action(record); hard_guard_reasons(record); coarse_route_reasons(record)
    rss_before = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    timings_ns = []
    checksum = 0
    start = time.perf_counter_ns()
    for _ in range(PASSES):
        for _, record in inputs:
            t0 = time.perf_counter_ns()
            action = base_action(record)
            hard = hard_guard_reasons(record)
            coarse = coarse_route_reasons(record) if not hard else []
            checksum ^= hash((record["id"], action, tuple(hard), tuple(coarse)))
            timings_ns.append(time.perf_counter_ns() - t0)
    elapsed = (time.perf_counter_ns() - start) / 1e9
    rss_after = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss

    # Content-addressed replay: first pass misses, later passes hit.
    cache: Dict[str, Dict[str, Any]] = {}
    hit = miss = 0
    cache_start = time.perf_counter_ns()
    for _ in range(20):
        for _, record in inputs:
            key = hashlib.sha256(canonical_bytes(record)).hexdigest()
            if key in cache:
                hit += 1
                checksum ^= hash(cache[key]["base_action"])
            else:
                miss += 1
                cache[key] = {"base_action": base_action(record), "route": routes[record["id"]]["route_to_l2"]}
    cache_elapsed = (time.perf_counter_ns() - cache_start) / 1e9

    hybrid_latencies = []
    full_latencies = []
    hard_latencies = []
    nonhard_latencies = []
    for _, record in inputs:
        rid = record["id"]
        route = routes[rid]
        j = jev.get(rid, {"seconds": 0.0})["seconds"]
        h = hybrid_l2.get(rid, {"seconds": 0.0})["seconds"]
        f = full_l2[rid]["seconds"]
        latency = j + h
        hybrid_latencies.append(latency)
        full_latencies.append(f)
        (hard_latencies if route["hard_guard_selected"] else nonhard_latencies).append(latency)

    metrics = {
        "status": "FROZEN_STAGE9G_LOCAL_DEPLOYMENT_BENCHMARK_COMPLETE",
        "system": {"platform": platform.platform(), "python": platform.python_version()},
        "records": len(inputs),
        "local_cpu_path": {
            "passes": PASSES,
            "operations": len(inputs) * PASSES,
            "elapsed_seconds": elapsed,
            "throughput_ops_per_second": len(inputs) * PASSES / elapsed,
            "latency_microseconds": {
                "median": statistics.median(timings_ns) / 1000,
                "p95": percentile(timings_ns, 0.95) / 1000,
                "p99": percentile(timings_ns, 0.99) / 1000,
            },
            "max_rss_before": rss_before,
            "max_rss_after": rss_after,
            "checksum": checksum,
        },
        "content_addressed_replay": {
            "lookups": hit + miss,
            "hits": hit,
            "misses": miss,
            "hit_rate": hit / (hit + miss),
            "elapsed_seconds": cache_elapsed,
            "lookup_throughput_per_second": (hit + miss) / cache_elapsed,
            "scope": "Repeated deterministic replay benchmark, not an observed production cache hit rate.",
        },
        "observed_api_receipt_latency_seconds": {
            "hybrid": {
                "median": statistics.median(hybrid_latencies),
                "p95": percentile(hybrid_latencies, .95),
                "mean": statistics.mean(hybrid_latencies),
            },
            "full_l2": {
                "median": statistics.median(full_latencies),
                "p95": percentile(full_latencies, .95),
                "mean": statistics.mean(full_latencies),
            },
            "hybrid_p95_change_vs_full": percentile(hybrid_latencies, .95) / percentile(full_latencies, .95) - 1,
            "hard_guard_path_p95": percentile(hard_latencies, .95),
            "nonhard_path_p95": percentile(nonhard_latencies, .95),
        },
        "claim_boundaries": [
            "API receipt latency includes remote service and network effects; it is not server-side GPU kernel time.",
            "No server GPU memory, accelerator utilization, queue telemetry, or energy measurement is available.",
            "Dynamic batching and speculative cancellation were not claimed because the endpoint exposes no batch scheduler telemetry.",
            "The CPU benchmark measures ontology/rule/routing preparation on one local process only.",
        ],
    }
    digest = hashlib.sha256(json.dumps(metrics, ensure_ascii=False, sort_keys=True).encode()).hexdigest()[:16]
    out = OUT_ROOT / f"frozen_{digest}"
    out.mkdir(parents=True, exist_ok=True)
    metrics_path = out / "stage9g_deployment_metrics.json"
    metrics_path.write_text(json.dumps(metrics, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    report = f"""# Stage 9G 本地部署与资源测量

| 项目 | 结果 |
|---|---:|
| 冻结记录 | {len(inputs)} |
| CPU快路径吞吐 | {metrics['local_cpu_path']['throughput_ops_per_second']:,.0f} 机会/秒 |
| CPU快路径P95 | {metrics['local_cpu_path']['latency_microseconds']['p95']:.2f} 微秒 |
| 内容寻址回放命中率 | {metrics['content_addressed_replay']['hit_rate']:.2%} |
| 混合路径API P95 | {metrics['observed_api_receipt_latency_seconds']['hybrid']['p95']:.3f} 秒 |
| 全量L2 API P95 | {metrics['observed_api_receipt_latency_seconds']['full_l2']['p95']:.3f} 秒 |
| 混合P95相对变化 | {metrics['observed_api_receipt_latency_seconds']['hybrid_p95_change_vs_full']:.2%} |

CPU数据证明本体、先验和路由工作可在微秒级完成，但API接口没有提供服务端GPU/NPU、显存、排队或能耗数据。因此论文只能论证异构映射和请求减少，不得将API时延反推为服务端硬件加速比。
"""
    report_path = out / "STAGE9G_DEPLOYMENT_REPORT.md"
    report_path.write_text(report, encoding="utf-8")
    manifest = {
        "status": metrics["status"],
        "source_run": str(RUN.relative_to(ROOT)),
        "files": {
            metrics_path.name: hashlib.sha256(metrics_path.read_bytes()).hexdigest(),
            report_path.name: hashlib.sha256(report_path.read_bytes()).hexdigest(),
        },
    }
    (out / "stage9g_freeze_manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({"status": metrics["status"], "output": str(out), "cpu_ops_s": metrics["local_cpu_path"]["throughput_ops_per_second"], "hybrid_p95_change": metrics["observed_api_receipt_latency_seconds"]["hybrid_p95_change_vs_full"]}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
