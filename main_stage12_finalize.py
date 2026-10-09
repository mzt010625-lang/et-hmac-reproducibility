#!/usr/bin/env python3
"""Build the Stage 9–12 technical freeze manifest without external fabrication."""
from __future__ import annotations

import hashlib
import json
import os
import re
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parent
OUT = ROOT / "07_投稿包"
SECRET = re.compile(rb"(?<![A-Za-z0-9])sk-[A-Za-z0-9]{20,}")
TEXT_SUFFIXES = {".py", ".md", ".json", ".jsonl", ".sh", ".yaml", ".yml", ".ttl", ".rq", ".csv", ".txt"}

KEY_FILES = [
    ROOT / "05_论文/ET_HMAC_ESWA_manuscript.md",
    ROOT / "05_论文/ESWA_SMPT_title_page.md",
    ROOT / "05_论文/highlights.md",
    ROOT / "05_论文/ESWA_cover_letter_draft.md",
    ROOT / "06_报告/Stage11两轮模拟审稿_2026-10-09.md",
    ROOT / "06_报告/Stage11新增路由文献核验_2026-10-09.md",
    ROOT / "06_报告/Stage12选刊与投稿要求核验_2026-10-09.md",
    ROOT / "00_项目管理/当前有效口径与入口_2026-10-09.md",
    ROOT / "runs/stage9_confirmatory_official_v2/frozen_e783101aa1a16522/stage9_partial_or_complete_metrics.json",
    ROOT / "runs/stage9d_optimized_holdout_v1/frozen_8058ea605c2771e8/stage9d_final_metrics.json",
    ROOT / "runs/stage9e_trajectory_audit_v1/frozen_7bbdc5d52b6767bc/stage9e_trajectory_metrics.json",
    ROOT / "runs/stage9g_deployment_benchmark_v1/frozen_77303949f67636b4/stage9g_deployment_metrics.json",
    ROOT / "data/stage9f_expert_blind_pack_v1/expert_review_completion_summary.json",
    ROOT / "runs/stage11_integrity_audit_v1/frozen_c1731373b98c0b4e/stage11_integrity_metrics.json",
]


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def load(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def run_tests() -> dict:
    env = dict(os.environ)
    env["PYTHONPATH"] = str(ROOT / "src")
    proc = subprocess.run(
        [sys.executable, "-m", "unittest", "discover", "-s", "tests", "-p", "test_*.py", "-q"],
        cwd=ROOT,
        env=env,
        text=True,
        capture_output=True,
        check=False,
    )
    combined = proc.stdout + "\n" + proc.stderr
    count_match = re.search(r"Ran (\d+) tests", combined)
    return {
        "pass": proc.returncode == 0,
        "count": int(count_match.group(1)) if count_match else None,
        "returncode": proc.returncode,
    }


def scan_secrets() -> list[str]:
    hits = []
    skip = {".git", ".venv", "__pycache__"}
    for path in ROOT.rglob("*"):
        if not path.is_file() or any(part in skip for part in path.parts):
            continue
        if path.suffix.lower() not in TEXT_SUFFIXES or path.stat().st_size > 5_000_000:
            continue
        if SECRET.search(path.read_bytes()):
            hits.append(str(path.relative_to(ROOT)))
    return sorted(hits)


def main() -> int:
    missing = [str(path.relative_to(ROOT)) for path in KEY_FILES if not path.exists()]
    if missing:
        raise FileNotFoundError(f"Missing freeze inputs: {missing}")

    tests = run_tests()
    secret_hits = scan_secrets()
    s9d = load(KEY_FILES[9])
    s11 = load(KEY_FILES[-1])
    overall = s9d["overall"]
    resources = overall["resources"]

    external_gaps = [
        "500条双专家盲评已经完成，但当前归档不含仲裁前逐专家标注表，无法复算专家间Kappa或alpha。",
        "尚无真实家庭行为标签或真实宏观总量校准结果。",
        "现有API轨迹证据属于纵向回放，不是行为反馈驱动的多世界闭环。",
        "去密后的公共代码/数据包已生成，但GitHub仓库URL尚待上传后回填；归档DOI尚未取得。",
    ]
    technical_pass = tests["pass"] and not secret_hits and not s11["failed"]
    status = (
        "TECHNICAL_PACKAGE_COMPLETE_GITHUB_UPLOAD_AND_EMPIRICAL_VALIDATION_PENDING"
        if technical_pass
        else "TECHNICAL_PACKAGE_FAILED"
    )
    result = {
        "status": status,
        "journal_positioning": {"primary": "Expert Systems with Applications", "conditional_backup": "Simulation Modelling Practice and Theory"},
        "frozen_primary_result": {
            "records": 1020,
            "model_reference_agreement": overall["accuracy"],
            "balanced_agreement": overall["balanced_accuracy"],
            "macro_f1": overall["macro_f1"],
            "l2_rate": overall["l2_rate"],
            "token_saving": resources["token_saving_rate"],
            "valid_l2_overwritten": 0,
            "interpretation": "Agreement with an independently executed full-L2 operational reference; not real household-behaviour accuracy.",
        },
        "verification": {
            "unit_tests": tests,
            "stage11_checks": len(s11["checks"]),
            "stage11_failed": len(s11["failed"]),
            "credential_pattern_hits": secret_hits,
        },
        "external_gaps": external_gaps,
        "submission_gate": "完成GitHub上传并回填最终URL后可进入ESWA投稿系统；归档DOI是推荐增强项。正文必须继续区分全量L2一致率、专家面效度和真实家庭行为效度。",
        "files": {str(path.relative_to(ROOT)): sha256(path) for path in KEY_FILES},
    }

    OUT.mkdir(parents=True, exist_ok=True)
    manifest = OUT / "stage12_submission_manifest.json"
    manifest.write_text(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    report = f"""# Stage 9–12最终状态

**状态：{status}**

## 冻结主结果

| 指标 | 结果 | 正确解释 |
|---|---:|---|
| 独立复验记录 | 1,020 | Stage 9D新家庭留出集 |
| 与独立全量L2一致率 | {overall['accuracy']:.2%} | 模型参照一致率，不是真实行为准确率 |
| 平衡一致率 | {overall['balanced_accuracy']:.2%} | 按全量L2动作类别平均召回 |
| Macro-F1 | {overall['macro_f1']:.2%} | 相对全量L2动作 |
| L2调用率 | {overall['l2_rate']:.2%} | 253/1,020 |
| Token节省 | {resources['token_saving_rate']:.2%} | JEV与选中L2总Token相对全量L2 |
| 有效L2被快路径覆盖 | 0 | L2分歧不会触发回退 |

## 技术验收

- 单元/契约/泄漏测试：{tests['count']}项，{'全部通过' if tests['pass'] else '存在失败'}。
- Stage 11自动审计：{len(s11['checks'])}项，失败{len(s11['failed'])}项。
- 长密钥模式扫描：{len(secret_hits)}个命中文件。
- 当前主投：Expert Systems with Applications；SMPT仅在补齐闭环与真实V&V后作为备投。

## 仍需外部或作者完成

""" + "\n".join(f"- {item}" for item in external_gaps) + "\n\n## 投稿门禁\n\n" + result["submission_gate"] + "\n"
    (OUT / "STAGE9_12_FINAL_STATUS.md").write_text(report, encoding="utf-8")
    print(json.dumps({"status": status, "manifest": str(manifest), "tests": tests, "secret_hits": secret_hits}, ensure_ascii=False, indent=2))
    return 0 if technical_pass else 1


if __name__ == "__main__":
    raise SystemExit(main())
