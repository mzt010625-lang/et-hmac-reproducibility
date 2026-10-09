#!/usr/bin/env python3
"""Prepare a blinded Stage 9F expert/external-validity package.

No expert judgments are invented. The output is a frozen review instrument and
an explicit gap report, not an external-validity result.
"""
from __future__ import annotations

import hashlib
import json
import random
from pathlib import Path
from typing import Any, Dict, List


ROOT = Path(__file__).resolve().parent
DATA = ROOT / "data/stage9_confirmatory_v1"
OUT_ROOT = ROOT / "data/stage9f_expert_blind_pack_v1"
SEED = 20261009
QUOTAS = {"natural": 150, "stress": 175, "policy_ood": 175}


def read_jsonl(path: Path) -> List[Dict[str, Any]]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def dump_json(path: Path, value: Any) -> None:
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def dump_jsonl(path: Path, rows: List[Dict[str, Any]]) -> None:
    path.write_text("".join(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n" for row in rows), encoding="utf-8")


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> int:
    rng = random.Random(SEED)
    selected: List[Dict[str, Any]] = []
    for queue, quota in QUOTAS.items():
        rows = read_jsonl(DATA / f"{queue}_inputs.jsonl")
        if len(rows) < quota:
            raise RuntimeError(f"{queue} contains fewer records than its frozen quota")
        chosen = rng.sample(rows, quota)
        for record in chosen:
            # Keep only pre-decision information. Do not expose L1/JEV/L2 outputs.
            selected.append({
                "review_id": "REV-" + hashlib.sha256(record["id"].encode("utf-8")).hexdigest()[:12],
                "queue_stratum": queue,
                "round": record.get("round"),
                "family": record.get("family"),
                "state": record.get("state"),
                "beliefs": record.get("beliefs"),
                "goals": record.get("goals"),
                "memory": record.get("memory"),
                "allowed_actions": record.get("allowed"),
                "event_context": {
                    "evidence": record.get("evidence"),
                    "ontology": record.get("ontology"),
                    "visible_cutoff": record.get("visible_cutoff"),
                },
                "annotation": {
                    "primary_action": None,
                    "acceptable_action_set": [],
                    "confidence_0_to_1": None,
                    "reality_fit_1_to_5": None,
                    "task_validity_1_to_5": None,
                    "evidence_ids": [],
                    "comment": None,
                },
            })
    rng.shuffle(selected)
    OUT_ROOT.mkdir(parents=True, exist_ok=True)
    pack = OUT_ROOT / "expert_blind_annotation_pack.jsonl"
    dump_jsonl(pack, selected)
    schema = OUT_ROOT / "annotation_schema.json"
    dump_json(schema, {
        "actions": ["stay", "wait", "search_buy", "search_jeonse", "search_monthly_rent", "list_for_sale", "list_for_rent"],
        "required": ["primary_action", "acceptable_action_set", "confidence_0_to_1", "reality_fit_1_to_5", "task_validity_1_to_5"],
        "blindness": "No L1, JEV, L2, route, score, or target action is present in the review packet.",
    })
    protocol = OUT_ROOT / "STAGE9F_EXPERT_PROTOCOL.md"
    protocol.write_text("""# Stage 9F 外部行为与专家校准协议（冻结稿）

## 当前状态

已冻结500条盲评材料：自然队列150条、压力队列175条、政策OOD 175条。材料只包含决策前家庭状态、信念、目标、有限记忆、政策/市场/网络证据、本体关系和合法行为集，不含任何L1、JEV、L2、路由或目标动作。

## 必须遵循的标注流程

1. 至少两名具有住房政策、城市经济或社会仿真背景的审查者独立盲评；
2. 每条同时标注首选行为和可接受行为集，避免把真实多解问题伪装成单一真值；
3. 先锁定两人原始结果，再对分歧进行仲裁；
4. 报告首选动作的Krippendorff's alpha/多类Kappa、可接受集Jaccard和置信度加权一致率；
5. 将混合系统、全量L2和透明快路径分别与专家首选及可接受集比较；
6. 专家标签、模型一致率和真实观察统计分别报告，不得混称“准确率”。

## 外部统计锚点

当前家庭属性是由官方分布约束的合成总体，并非真实家庭纵向行为记录。正式外部效度还需一项可匹配时间、地区、产权和家庭类型口径的现实住房迁移/租购转换/政策响应统计。在取得该数据前，只能报告模型参照一致性、约束合法性和压力测试性能。

## 不可替代的人工环节

本协议不得由同一模型的多次调用替代。未实际招募审查者和完成盲评前，Stage 9F状态必须保持为“协议及材料已冻结，外部评价待完成”。
""", encoding="utf-8")
    manifest = {
        "status": "FROZEN_PROTOCOL_EXTERNAL_REVIEW_PENDING",
        "seed": SEED,
        "records": len(selected),
        "quotas": QUOTAS,
        "external_behavior_labels_available": False,
        "expert_annotations_completed": False,
        "files": {p.name: sha256(p) for p in [pack, schema, protocol]},
    }
    dump_json(OUT_ROOT / "stage9f_manifest.json", manifest)
    print(json.dumps(manifest, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
