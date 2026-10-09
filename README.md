# ET-HMAC reproducibility package

This repository contains the public reproducibility materials for **Executable Semantic Contracts for Selective LLM Invocation in Agent-Based Simulation**.

Repository: https://github.com/mzt010625-lang/et-hmac-reproducibility

## Primary frozen result

On the independent 1,020-record Stage 9D holdout, the hybrid system reached 97.75% agreement with a separately executed full-L2 operational reference, 96.48% balanced agreement, and 96.70% macro-F1 while reducing tokens by 68.36% and invoking L2 for 24.80% of opportunities. These are model-reference metrics, not observed household-behaviour accuracy. All 23 mismatches occurred in the policy-OOD cohort; 21 reflected asymmetric evidence-reference validation and two reflected different valid L2 outputs.

## Architecture

1. A transparent goal-conditioned prior produces a fast legal action.
2. Frozen ontology/event hard guards directly route non-deferrable cases to L2.
3. Only non-hard ambiguous candidates call the compact JEV router.
4. A valid selected L2 output is authoritative and is never rejected merely because it differs from the fast path.

## Contents

- `src/`: implementation modules;
- `configs/`, `prompts/`, `schemas/`, `ontology/`, `rules/`: frozen contracts;
- `data/`: synthetic Stage 9 development and Stage 9D holdout inputs;
- `results/`: frozen metrics, parsed decisions, routing ledgers, and manifests;
- `tests/`: unit, contract, leakage, and L2-authority tests;
- `documentation/`: manuscript source and final evidence-boundary reports.
- `figures/`: publication figures in PDF/PNG plus the editable PowerPoint source.

## Verification

Run:

```bash
PYTHONPATH=src python3 -m unittest discover -s tests -p 'test_*.py' -q
```

The frozen local research package passed 156 tests. The public package contains a self-contained 49-test core contract subset; run the command above to verify it. API calls are not required to inspect or recompute the published aggregate metrics.

## Data and ethics boundary

The household records are synthetic and distribution-constrained, and no observed household-choice labels are claimed. The longitudinal API records are replay-based rather than fully action-conditioned multi-world simulations.

## Credentials and provider data

API keys, private service endpoints, and local absolute paths are excluded. Raw provider request/response content is not required for the public aggregate result; the package retains parsed outputs, routing ledgers, token accounting, and hashes needed for audit.

## Provenance identifiers

Historical module names such as `ethmac_v9`, record identifiers beginning with `V9-`, and schema version fields are retained as immutable experiment-provenance identifiers. They are not the public manuscript or release version.

## Author

Ziteng Ma, China Academy of Information and Communications Technology (CAICT). ORCID: 0009-0000-0015-4497.

## Licence

No reuse licence has been selected yet. Copyright remains with the author until a licence is added.
