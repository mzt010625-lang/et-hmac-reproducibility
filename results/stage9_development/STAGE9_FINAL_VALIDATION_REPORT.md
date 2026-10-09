## Material Passport

- Origin Skill: experiment-agent
- Origin Mode: validate
- Origin Date: 2026-10-09
- Verification Status: ANALYZED
- Version Label: stage9_validation_v1

## Stage 9 Final Validation Report

- **Status**: COMPLETE_WITH_OOD_RESOURCE_STRESS_LIMITATION
- **Records**: 4,400 synthetic household-event records
- **Provider/model**: DeepSeek official API / deepseek-flash
- **Interpretation boundary**: quality is agreement with a fresh independent full-L2 reference; it is not observed household behavior accuracy or human-expert accuracy.

### Primary results

| Cohort | N | Agreement | Balanced agreement | Macro-F1 | L2 rate | Token saving | Full L2 P95 | Hybrid sequential P95 |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| Natural | 2,000 | 100.00% | 100.00% | 100.00% | 13.50% | 75.16% | 3.38s | 5.37s |
| Stress | 1,400 | 100.00% | 100.00% | 100.00% | 16.36% | 70.56% | 3.12s | 4.74s |
| Policy OOD | 1,000 | 87.40% | 88.65% | 88.02% | 100.00% | -35.69% | 2.67s | 4.53s |
| Overall | 4,400 | 97.14% | 96.92% | 96.77% | 34.07% | 46.80% | 3.21s | 5.01s |

Natural + stress operational subset: agreement 100.00%, L2 rate 14.68%, Token saving 73.26%.

### Resource ledger

| Item | Value |
|---|---:|
| Full-L2 reference tokens | 11,929,981 |
| Compact-JEV tokens | 2,102,449 |
| Selected-L2 tokens | 4,244,445 |
| Hybrid deployment tokens | 6,346,894 |
| Known tokens across all experiment arms | 18,276,875 |
| Paid JEV / selected-L2 / full-L2 responses | 2,145 / 1,499 / 4,402 |
| Valid L2 overwritten | 0 |
| Selected L2 missing | 0 |

Two interrupted/transport-ambiguous requests have no provider response or usage receipt and are excluded from known-token totals; their records were subsequently completed. Two invalid ID responses and one exact-ID-only repair response remain included in the stress full-L2 token and latency accounting.

### Internal engineering references (not publication requirements)

| Reference | Result | Status |
|---|---:|---|
| Overall agreement >=95% | 97.14% | PASS |
| Overall Token saving >=50% | 46.80% | FAIL |
| Strict Token saving >=60% | 46.80% | FAIL |
| Overall L2 rate <=30% | 34.07% | FAIL |
| P95 reduction >=30% | -56.18% | FAIL |
| No valid L2 overwritten | 0 | PASS |

### Warnings

| Type | Detail | Affected |
|---|---|---|
| OOD self-variance | Both OOD arms called the same model independently, yet agreement was only 87.40%. | OOD quality and overall quality |
| OOD safety cost | The frozen hard guard routed all OOD records to L2, so JEV became pure overhead and Token saving was -35.69%. | OOD and overall resources |
| Sequential latency | Hybrid sequential P95 was 56.18% slower than full L2, despite lower in-distribution Token use. | Latency claim |
| Synthetic evidence | Records are synthetic; no real household or human-expert labels were used in Stage 9. | External validity |

### Fallacy scan

- **Coverage**: 11/11 fallacy types checked

| Fallacy | Severity | Finding |
|---|---|---|
| Simpson's paradox | CAUTION | The 97.14% aggregate masks the 87.40% OOD result; cohort-stratified results must remain visible. |
| Ecological fallacy | NOTE | Per-record simulation agreement cannot establish population-level human behavior accuracy. |
| Berkson's paradox | NOTE | Full cohorts were evaluated; coarse-candidate selection affects routing analysis only. |
| Collider bias | NOTE | No causal regression or covariate adjustment was performed. |
| Base-rate neglect | NOTE | Balanced agreement, Macro-F1 and per-class results accompany raw agreement. |
| Regression to the mean | NOTE | No extreme-score pre/post comparison was used. |
| Survivorship bias | NOTE | All 4,400 record IDs received accepted final outputs; no failed record was dropped. |
| Look-elsewhere effect | NOTE | All frozen primary metrics are reported, including failed internal references. |
| Garden of forking paths | CAUTION | Stage 8 was developmental; only the newly frozen Stage 9 cohorts are confirmatory evidence. |
| Correlation != causation | CAUTION | Reference alignment must not be described as causal policy validity or real behavior accuracy. |
| Reverse causality | NOTE | No directional causal association was estimated. |

### Reproducibility

- **Method**: environment-sensitive independent replay with immutable ledgers and frozen prompts/data
- **Verdict**: PARTIALLY_REPRODUCIBLE
- Natural and stress outputs were fully aligned across independent L2 calls, while policy OOD exposed material model self-variance. Raw requests, responses, parsed outputs, errors, hashes and the exact-ID-only repair record are preserved.
