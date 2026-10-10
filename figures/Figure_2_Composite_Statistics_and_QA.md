# Figure 2 statistics and reproducibility report

- Figure objective: show that the hybrid path preserves agreement with the independently executed full-L2 reference while concentrating semantic computation on selected cohorts.
- Layout: 2 x 2 quantitative grid, 183 mm x 108 mm, Arial/Helvetica-compatible typography, black/white/one-grey palette.
- Panel (a): N = 1020 decision records clustered within 100 households. Points are agreement, balanced agreement, and macro-F1. Whiskers are two-sided 95% household-cluster bootstrap intervals from 2000 replicates. No hypothesis test is drawn.
- Panel (b): service-token accounting from provider receipts. Full L2 = 2,750,418; hybrid = 870,253; JEV = 147,061; selected L2 = 723,192.
- Panel (c): invocation counts divided by cohort record counts. Natural N = 400; stress N = 420; policy OOD N = 200.
- Panel (d): each point is one frozen cohort. X is hybrid tokens / full-L2 tokens; Y is exact action agreement with separately executed full L2.
- Source of truth: `runs/stage9d_optimized_holdout_v1/frozen_8058ea605c2771e8/stage9d_final_metrics.json`.
- Interpretation boundary: agreement is model-reference fidelity, not observed household-choice accuracy.
- No records or columns were dropped, and no experimental values were changed during figure redesign.

## Visual QA

- Anti-pattern scan: passed. No default palette, four-sided box, grid background, 3D effect, or legend occlusion.
- Code compliance: passed. Width is 183 mm; minimum text size is 6.5 pt; vector PDF and 300 dpi PNG are exported; PDF fonts use type 42 embedding.
- Visual logic: passed. Each panel carries distinct evidence, bar lengths start at zero, non-bar axes are restricted to the relevant data range, and marker shapes preserve grayscale interpretation.
- Render verification: passed after two iterations. Panel labels, direct labels, legends, and confidence intervals do not overlap at final manuscript size.
- Palette: white, black, and one uniform grey only.
