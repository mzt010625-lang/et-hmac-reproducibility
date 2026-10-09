#!/usr/bin/env python3
"""Stage 11 manuscript/evidence integrity audit."""
from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path
from typing import Any, Dict, List


ROOT = Path(__file__).resolve().parent
PAPER = ROOT / "05_论文/ET_HMAC_ESWA_manuscript.md"
HIGHLIGHTS = ROOT / "05_论文/highlights.md"
S9 = ROOT / "runs/stage9_confirmatory_official_v2/frozen_e783101aa1a16522/stage9_partial_or_complete_metrics.json"
S9D = ROOT / "runs/stage9d_optimized_holdout_v1/frozen_8058ea605c2771e8/stage9d_final_metrics.json"
S9E = ROOT / "runs/stage9e_trajectory_audit_v1/frozen_7bbdc5d52b6767bc/stage9e_trajectory_metrics.json"
S9G = ROOT / "runs/stage9g_deployment_benchmark_v1/frozen_77303949f67636b4/stage9g_deployment_metrics.json"
OUT_ROOT = ROOT / "runs/stage11_integrity_audit_v1"


def jload(path: Path) -> Dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def pct(value: float) -> str:
    return f"{value:.2%}"


def assert_contains(checks: List[Dict[str, Any]], text: str, label: str, needle: str) -> None:
    checks.append({"check": label, "pass": needle in text, "expected_literal": needle})


def main() -> int:
    text = PAPER.read_text(encoding="utf-8")
    s9 = jload(S9); s9d = jload(S9D); s9e = jload(S9E); s9g = jload(S9G)
    checks: List[Dict[str, Any]] = []
    overall = s9d["overall"]
    resources = overall["resources"]
    for label, literal in [
        ("Stage9D agreement", pct(overall["accuracy"])),
        ("Stage9D balanced agreement", pct(overall["balanced_accuracy"])),
        ("Stage9D macro-F1", pct(overall["macro_f1"])),
        ("Stage9D L2 rate", pct(overall["l2_rate"])),
        ("Stage9D token saving", pct(resources["token_saving_rate"])),
        ("Stage9E trajectory exact match", pct(s9e["longitudinal_replay"]["trajectory_exact_match_rate"])),
    ]:
        assert_contains(checks, text, label, literal)
    assert_contains(checks, text, "Stage9G rounded CPU throughput", f"{s9g['local_cpu_path']['throughput_ops_per_second']:,.0f}")
    assert_contains(checks, text, "L2 authority", "No valid selected L2 output was overwritten")
    assert_contains(checks, text, "Reference boundary", "not an expert label or observed behaviour")
    assert_contains(checks, text, "Closed-loop boundary", "not an action-conditioned ABM validation")

    abstract = text.split("## Abstract", 1)[1].split("**Keywords:**", 1)[0]
    abstract_words = len(re.findall(r"\b[\w’'-]+\b", abstract))
    checks.append({"check": "Abstract <=250 words", "pass": abstract_words <= 250, "value": abstract_words})
    keyword_line = re.search(r"\*\*Keywords:\*\*\s*(.+)", text)
    keywords = [item.strip() for item in keyword_line.group(1).split(";")] if keyword_line else []
    checks.append({"check": "1-7 English keywords", "pass": 1 <= len(keywords) <= 7, "value": keywords})
    highlights = [line[2:] for line in HIGHLIGHTS.read_text(encoding="utf-8").splitlines() if line.startswith("- ")]
    checks.append({"check": "3-5 highlights", "pass": 3 <= len(highlights) <= 5, "value": len(highlights)})
    checks.append({"check": "Each highlight <=85 characters", "pass": all(len(item) <= 85 for item in highlights), "value": [len(item) for item in highlights]})
    checks.append({"check": "Anonymized main file", "pass": "Author One" not in text and "Affiliation," not in text})
    checks.append({"check": "AI declaration before references", "pass": text.find("Declaration of generative AI") < text.find("## References")})
    checks.append({"check": "Data availability statement present", "pass": "## Data and code availability" in text})

    cited = set()
    body = text.split("## References", 1)[0]
    for group in re.findall(r"\[(\d+(?:[–,-]\d+)*)\]", body):
        for part in group.split(","):
            if "–" in part:
                lo, hi = map(int, part.split("–")); cited.update(range(lo, hi + 1))
            elif "-" in part:
                lo, hi = map(int, part.split("-")); cited.update(range(lo, hi + 1))
            else:
                cited.add(int(part))
    listed = {int(value) for value in re.findall(r"^\[(\d+)\]", text, flags=re.M)}
    checks.append({"check": "Every citation is listed", "pass": cited <= listed, "missing": sorted(cited - listed)})
    checks.append({"check": "Every reference is cited", "pass": listed <= cited, "uncited": sorted(listed - cited)})
    checks.append({"check": "Reference sequence complete", "pass": listed == set(range(1, max(listed) + 1)), "listed": sorted(listed)})

    checks.append({"check": "Stage9A result retained as development evidence", "pass": "97.14%" in text and "46.80%" in text})
    checks.append({"check": "Stage9D source manifest frozen", "pass": jload(ROOT / "runs/stage9d_optimized_holdout_v1/frozen_8058ea605c2771e8/stage9d_final_freeze_manifest.json")["status"] == "FROZEN_STAGE9D_COMPLETE"})
    secret_pattern = re.compile(r"(?<![A-Za-z0-9])sk-[A-Za-z0-9]{20,}")
    checks.append({"check": "No key stored in manuscript", "pass": secret_pattern.search(text) is None})

    failed = [item for item in checks if not item["pass"]]
    status = "PASS_WITH_EXTERNAL_VALIDITY_AND_CLOSED_LOOP_GAPS" if not failed else "FAIL"
    result = {
        "status": status,
        "checks": checks,
        "failed": failed,
        "known_noncomputable_gaps": [
            "The 500-case review is complete and the adjudicated conclusion is archived, but individual pre-adjudication sheets and inter-rater coefficients were not supplied for computational re-analysis.",
            "No observed household action labels are available.",
            "No formal action-conditioned API multi-world experiment has been run.",
            "No server-side GPU/NPU memory, utilisation, queue, or energy telemetry is available.",
        ],
        "claim_gate": "The manuscript may report completed expert face validity and architecture-to-full-L2 agreement, but must not claim observed household-behaviour accuracy or completed action-conditioned simulation validation.",
    }
    digest = hashlib.sha256(json.dumps(result, ensure_ascii=False, sort_keys=True).encode()).hexdigest()[:16]
    out = OUT_ROOT / f"frozen_{digest}"
    out.mkdir(parents=True, exist_ok=True)
    metrics = out / "stage11_integrity_metrics.json"
    metrics.write_text(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    report = ["# Stage 11 完整性审计", "", f"**状态：{status}**", "",
              f"- 自动检查：{len(checks)}项；失败：{len(failed)}项。",
              f"- 摘要词数：{abstract_words}；高亮长度：{[len(item) for item in highlights]}。",
              "- Stage 9D的主要数字已从冻结JSON逐项对照正文。",
              "- L2与快路径不同时退回L1的旧错误未出现；正文明确有效L2不得被覆盖。", "",
              "## 仍未完成的外部条件", ""]
    report.extend(f"- {gap}" for gap in result["known_noncomputable_gaps"])
    report += ["", "## 投稿前硬门禁", "", result["claim_gate"], ""]
    if failed:
        report += ["## 失败项", ""] + [f"- {item['check']}" for item in failed]
    report_path = out / "STAGE11_INTEGRITY_REPORT.md"
    report_path.write_text("\n".join(report), encoding="utf-8")
    manifest = {"status": status, "files": {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in [metrics, report_path]}}
    (out / "stage11_freeze_manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({"status": status, "output": str(out), "checks": len(checks), "failed": failed}, ensure_ascii=False, indent=2))
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
