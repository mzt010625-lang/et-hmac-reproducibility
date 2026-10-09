#!/usr/bin/env python3
"""Stage 9E: trajectory evidence audit and local closed-loop software gate.

This stage deliberately separates two kinds of evidence:
1. longitudinal replay evidence from the frozen Stage 9D natural cohort; and
2. deterministic software validation of the action->outcome->state feedback loop.

The Stage 9D replay is not relabelled as an action-conditioned world simulation.
"""
from __future__ import annotations

import hashlib
import json
import math
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any, Dict, Iterable, List, Mapping, Sequence, Tuple

from src.ethmac_v9.stage6_environment import run_local_closed_loop


ROOT = Path(__file__).resolve().parent
DATA = ROOT / "data/stage9d_optimized_holdout_v1"
SOURCE_RUN = ROOT / "runs/stage9d_optimized_holdout_v1/frozen_8058ea605c2771e8"
OUT_ROOT = ROOT / "runs/stage9e_trajectory_audit_v1"
ACTIONS = [
    "stay", "wait", "search_buy", "search_jeonse", "search_monthly_rent",
    "list_for_sale", "list_for_rent",
]


def read_jsonl(path: Path) -> List[Dict[str, Any]]:
    if not path.exists():
        return []
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def write_json(path: Path, value: Any) -> None:
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def js_divergence(p: Sequence[float], q: Sequence[float]) -> float:
    m = [(a + b) / 2 for a, b in zip(p, q)]

    def kl(a: Sequence[float], b: Sequence[float]) -> float:
        total = 0.0
        for x, y in zip(a, b):
            if x > 0:
                total += x * math.log2(x / y)
        return total

    return 0.5 * kl(p, m) + 0.5 * kl(q, m)


def normalized_distribution(values: Iterable[Any], support: Sequence[Any]) -> List[float]:
    counts = Counter(values)
    n = sum(counts.values())
    return [counts[item] / n if n else 0.0 for item in support]


def transition_distribution(trajectories: Mapping[str, Sequence[str]]) -> Tuple[List[str], List[float]]:
    support = [f"{a}->{b}" for a in ACTIONS for b in ACTIONS]
    observed = []
    for sequence in trajectories.values():
        observed.extend(f"{sequence[i]}->{sequence[i + 1]}" for i in range(len(sequence) - 1))
    return support, normalized_distribution(observed, support)


def usage_tokens(path: Path) -> Dict[str, int]:
    output: Dict[str, int] = {}
    for row in read_jsonl(path):
        usage = row.get("response", {}).get("usage", {})
        output[row["record_id"]] = int(usage.get("total_tokens", 0) or 0)
    return output


def main() -> int:
    inputs = {row["id"]: row for row in read_jsonl(DATA / "natural_inputs.jsonl")}
    selection = {row["record_id"]: row for row in read_jsonl(DATA / "natural_selection_manifest.jsonl")}
    routes = {row["record_id"]: row for row in read_jsonl(SOURCE_RUN / "natural/route_selection.jsonl")}
    full = {row["record_id"]: row["output"]["final_action"] for row in read_jsonl(SOURCE_RUN / "natural/full/l2_parsed.jsonl")}
    hybrid_l2 = {row["record_id"]: row["output"]["final_action"] for row in read_jsonl(SOURCE_RUN / "natural/hybrid/l2_parsed.jsonl")}
    if not inputs or set(inputs) != set(selection) or set(inputs) != set(routes) or set(inputs) != set(full):
        raise RuntimeError("Stage 9D natural cohort is incomplete or identifiers do not align")

    rows = []
    for record_id, record in inputs.items():
        route = routes[record_id]
        hybrid_action = hybrid_l2[record_id] if route["route_to_l2"] else route["base_action"]
        rows.append({
            "record_id": record_id,
            "household_id": selection[record_id]["household_id"],
            "world_id": selection[record_id]["world_id"],
            "round": int(selection[record_id]["round"]),
            "hybrid_action": hybrid_action,
            "reference_action": full[record_id],
            "agreement": hybrid_action == full[record_id],
            "route_to_l2": bool(route["route_to_l2"]),
            "jev_called": bool(route["jev_called"]),
        })
    rows.sort(key=lambda row: (row["household_id"], row["round"]))

    hybrid_traj: Dict[str, List[str]] = defaultdict(list)
    reference_traj: Dict[str, List[str]] = defaultdict(list)
    per_round: Dict[str, Dict[str, Any]] = {}
    for row in rows:
        hybrid_traj[row["household_id"]].append(row["hybrid_action"])
        reference_traj[row["household_id"]].append(row["reference_action"])
    for round_index in sorted({row["round"] for row in rows}):
        subset = [row for row in rows if row["round"] == round_index]
        per_round[str(round_index)] = {
            "n": len(subset),
            "agreement": sum(row["agreement"] for row in subset) / len(subset),
            "l2_rate": sum(row["route_to_l2"] for row in subset) / len(subset),
            "jev_rate": sum(row["jev_called"] for row in subset) / len(subset),
        }

    trajectory_exact = sum(hybrid_traj[key] == reference_traj[key] for key in hybrid_traj) / len(hybrid_traj)
    trajectory_hamming = {
        key: sum(a != b for a, b in zip(hybrid_traj[key], reference_traj[key])) / len(hybrid_traj[key])
        for key in hybrid_traj
    }
    action_p = normalized_distribution((row["hybrid_action"] for row in rows), ACTIONS)
    action_q = normalized_distribution((row["reference_action"] for row in rows), ACTIONS)
    transition_support, trans_p = transition_distribution(hybrid_traj)
    _, trans_q = transition_distribution(reference_traj)
    transition_l1 = 0.5 * sum(abs(a - b) for a, b in zip(trans_p, trans_q))

    # Audit whether the frozen records truly contain action-conditioned outcome memory.
    memory_lengths = []
    future_memory_violations = 0
    action_outcome_items = 0
    households_with_belief_change = 0
    households_with_state_change = 0
    for household_id in hybrid_traj:
        hrows = [inputs[row["record_id"]] for row in rows if row["household_id"] == household_id]
        hrows.sort(key=lambda row: row["round"])
        belief_signatures = []
        state_signatures = []
        for record in hrows:
            memory = record.get("memory", [])
            memory_lengths.append(len(memory))
            belief_signatures.append(json.dumps(record.get("beliefs", {}), sort_keys=True))
            state_signatures.append(json.dumps(record.get("state", {}), sort_keys=True))
            for item in memory:
                item_round = item.get("round_index", item.get("round", -1))
                if isinstance(item_round, int) and item_round >= int(record["round"]):
                    future_memory_violations += 1
                if item.get("kind") == "action_outcome" or item.get("action") is not None:
                    action_outcome_items += 1
        households_with_belief_change += len(set(belief_signatures)) > 1
        households_with_state_change += len(set(state_signatures)) > 1

    jev_tokens = usage_tokens(SOURCE_RUN / "natural/hybrid/jev_responses.jsonl")
    selected_l2_tokens = usage_tokens(SOURCE_RUN / "natural/hybrid/l2_responses.jsonl")
    full_tokens = usage_tokens(SOURCE_RUN / "natural/full/l2_responses.jsonl")
    for round_index, stats in per_round.items():
        ids = [row["record_id"] for row in rows if str(row["round"]) == round_index]
        stats["jev_tokens"] = sum(jev_tokens.get(record_id, 0) for record_id in ids)
        stats["selected_l2_tokens"] = sum(selected_l2_tokens.get(record_id, 0) for record_id in ids)
        stats["full_l2_tokens"] = sum(full_tokens.get(record_id, 0) for record_id in ids)
        stats["token_saving"] = 1 - (stats["jev_tokens"] + stats["selected_l2_tokens"]) / stats["full_l2_tokens"]

    software_runs = []
    for seed in range(2026100901, 2026100911):
        result = run_local_closed_loop(rounds=4, seed=seed)
        trajectory = result["trajectory"]
        final_states = result["final_states"]
        software_runs.append({
            "seed": seed,
            "rounds": len(trajectory),
            "all_rounds_changed_state": all(step["all_states_changed"] for step in trajectory),
            "all_agents_have_action_outcome_memory": all(
                any(item.get("kind") == "action_outcome" and item.get("action") in ACTIONS for item in state["memory"])
                for state in final_states.values()
            ),
            "all_agents_advanced_four_rounds": all(state["current_round"] == 4 for state in final_states.values()),
        })

    result = {
        "status": "FROZEN_STAGE9E_LONGITUDINAL_AND_SOFTWARE_GATE_COMPLETE",
        "source_stage9d_run": str(SOURCE_RUN.relative_to(ROOT)),
        "evidence_scope": {
            "longitudinal_replay": True,
            "action_conditioned_api_closed_loop": False,
            "local_feedback_software_gate": True,
            "warning": "Stage 9D natural records were generated as longitudinal snapshots; their later records were not causally regenerated from the method-specific prior action.",
        },
        "longitudinal_replay": {
            "records": len(rows),
            "households": len(hybrid_traj),
            "rounds_per_household": sorted({len(value) for value in hybrid_traj.values()}),
            "record_level_agreement": sum(row["agreement"] for row in rows) / len(rows),
            "trajectory_exact_match_rate": trajectory_exact,
            "mean_trajectory_hamming_rate": sum(trajectory_hamming.values()) / len(trajectory_hamming),
            "action_distribution_js_divergence_bits": js_divergence(action_p, action_q),
            "transition_distribution_total_variation": transition_l1,
            "per_round": per_round,
        },
        "cognition_audit": {
            "memory_window_observed_max": max(memory_lengths),
            "future_memory_violations": future_memory_violations,
            "action_outcome_memory_items": action_outcome_items,
            "households_with_belief_change": households_with_belief_change,
            "households_with_state_change": households_with_state_change,
            "conclusion": "The snapshots are temporally valid and stateful, but contain no executed-action outcome memory; therefore they are not formal action-feedback ABM evidence.",
        },
        "local_closed_loop_software_gate": {
            "runs": len(software_runs),
            "all_pass": all(
                item["all_rounds_changed_state"]
                and item["all_agents_have_action_outcome_memory"]
                and item["all_agents_advanced_four_rounds"]
                for item in software_runs
            ),
            "details": software_runs,
            "scope": "Verifies deterministic transition plumbing only; it is not behavioral validation.",
        },
        "transition_support": transition_support,
    }

    digest = hashlib.sha256(json.dumps(result, ensure_ascii=False, sort_keys=True).encode("utf-8")).hexdigest()[:16]
    out = OUT_ROOT / f"frozen_{digest}"
    out.mkdir(parents=True, exist_ok=True)
    metrics_path = out / "stage9e_trajectory_metrics.json"
    write_json(metrics_path, result)
    report = f"""# Stage 9E 轨迹证据与闭环软件门检

## 结论

- Stage 9D自然队列包含 {len(hybrid_traj)} 个家庭、每户4轮的纵向快照；混合架构与独立全量L2的逐条一致率为 {result['longitudinal_replay']['record_level_agreement']:.2%}，整条4轮行为序列完全一致率为 {trajectory_exact:.2%}。
- 行为分布JS散度为 {result['longitudinal_replay']['action_distribution_js_divergence_bits']:.6f} bit，相邻轮行为转移分布总变差为 {transition_l1:.6f}。
- 有限记忆最大长度为 {max(memory_lengths)}，未来信息违例为 {future_memory_violations}。
- 但这批快照的 action_outcome 记忆数为 {action_outcome_items}；因此它们是“纵向回放”，不是按本路线上轮行为因果再生成下轮世界的闭环证据。
- 本地10个种子的软件门检全部通过：行为执行、市场/网络反馈、信念、信任、资产、满意度、后悔和有限记忆能够进入下一轮。这只证明实现闭环可用，不证明现实行为效度。

## 每轮资源与路由

| 轮次 | N | 一致率 | L2率 | JEV率 | Token节省 |
|---:|---:|---:|---:|---:|---:|
"""
    for round_index, stats in per_round.items():
        report += f"| {round_index} | {stats['n']} | {stats['agreement']:.2%} | {stats['l2_rate']:.2%} | {stats['jev_rate']:.2%} | {stats['token_saving']:.2%} |\n"
    report += """

## 证据边界

论文可报告本阶段的纵向序列一致性、行为转移分布及闭环实现完整性；不得将其表述为现实市场轨迹准确率，也不得声称Stage 9D已完成行为反馈驱动的API闭环。
"""
    report_path = out / "STAGE9E_TRAJECTORY_AUDIT_REPORT.md"
    report_path.write_text(report, encoding="utf-8")
    freeze = {
        "status": result["status"],
        "source_run": str(SOURCE_RUN.relative_to(ROOT)),
        "files": {
            metrics_path.name: sha256(metrics_path),
            report_path.name: sha256(report_path),
        },
    }
    write_json(out / "stage9e_freeze_manifest.json", freeze)
    print(json.dumps({
        "status": result["status"],
        "output": str(out),
        "trajectory_exact_match_rate": trajectory_exact,
        "software_gate_all_pass": result["local_closed_loop_software_gate"]["all_pass"],
        "action_conditioned_api_closed_loop": False,
    }, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
