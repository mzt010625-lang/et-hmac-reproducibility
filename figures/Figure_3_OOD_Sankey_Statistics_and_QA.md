# Figure 3 statistics and reproducibility report

- Objective: expose the directional action differences after all 200 synthetic policy-OOD records were routed to L2.
- Figure type: compact two-column Sankey, 183 mm × 86 mm, black/white/one uniform grey.
- Unit of analysis: one synthetic household-policy OOD record; 23 records with different final actions are shown, no downsampling.
- The ribbons encode 15 directed action-pair types; ribbon thickness is the exact number of records (1–4).
- Grey represents the 21 asymmetric evidence/output-validation disagreements; black represents two disagreements in which both L2 outputs were valid. No significance test or confidence interval is asserted by this descriptive figure.
- Source: `runs/stage9d_optimized_holdout_v1/frozen_8058ea605c2771e8/policy_ood/hybrid/l2_parsed.jsonl` and `runs/stage9d_optimized_holdout_v1/frozen_8058ea605c2771e8/policy_ood/full/l2_parsed.jsonl`.
- Node totals and all 15 link totals are exported to `Figure_3_OOD_Sankey_Source_Data.csv`.
- Interpretation boundary: these are independent model-reference disagreements, not errors against observed household choices.
- Asset scan: eight-layer simulated Sankey production script was incompatible with two-layer frozen observations; no simulated rows were reused.
- QA: 23/23 records accounted for; 21 + 2 validation split verified; 200/200 OOD records had both L2 receipts; ≥7 pt direct labels; no default palette, grid, or 3-D effect; vector PDF and SVG plus 300 dpi PNG exported.
