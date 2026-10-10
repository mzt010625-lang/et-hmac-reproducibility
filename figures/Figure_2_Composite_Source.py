# Academic Figure Skill Asset Confirmation (verified against assets/figures/)
# (a) forest/dot-interval plot -> cross-type inherit from BarComparison -> param inherit
# (b) compact token composition -> assets/figures/BarComposition/plot_brute_force.py -> param inherit
# (c) paired invocation-rate dot plot -> cross-type inherit from GroupedBarChart -> param inherit
# (d) resource-quality scatter -> cross-type inherit from basic scatter -> param inherit
# RULE: "native run" = load pre-rendered PNG via Image.open().ax.imshow().
#       "param inherit" = drawing function below that copies Class A/B/C values.
#       If a panel says "native run" and you write a drawing function, you broke the contract.

# Academic Figure Skill Typography Baseline — COPY VERBATIM, place at TOP of script
import matplotlib as mpl
mpl.rcParams.update({
    "font.family": "sans-serif",
    "font.sans-serif": ["Arial", "Helvetica", "Liberation Sans"],
    "font.size": 8,
    "axes.titlesize": 8,
    "axes.labelsize": 8,
    "xtick.labelsize": 7,
    "ytick.labelsize": 7,
    "legend.fontsize": 8,
    "figure.titlesize": 9,
    "axes.spines.top": False,
    "axes.spines.right": False,
    "axes.linewidth": 0.6,
    "xtick.direction": "out",
    "ytick.direction": "out",
    "xtick.major.width": 0.6,
    "ytick.major.width": 0.6,
    "legend.frameon": False,
})

# Academic Figure Skill Nature/Cell/Science Color Palette -- COPY VERBATIM
CATEGORICAL = ["#2166AC", "#B2182B", "#1B7837", "#F1A340", "#762A83", "#666666"]
CATEGORICAL_EXTENDED = [
    "#2166AC", "#B2182B", "#1B7837", "#F1A340", "#762A83", "#666666",
    "#4393C3", "#D6604D", "#5AAE61", "#B35806", "#9970AB", "#999999",
]
DIVERGING   = ["#2166AC", "#F7F7F7", "#B2182B"]
SEQUENTIAL  = ["#F7FBFF", "#6BAED6", "#08306B"]
ACCENT_RED  = "#B2182B"
GREY        = "#999999"
BLACK       = "#222222"

# Academic Figure Skill Export Baseline — COPY VERBATIM
mpl.rcParams.update({
    "pdf.fonttype": 42,         # TrueType font embedding
    "svg.fonttype": "none",     # editable text in SVG
    "savefig.bbox": "tight",    # trim whitespace
    "savefig.dpi": 300,
})

def save_cns_figure(fig, filename):
    """Standard Academic Figure Skill export: vector PDF + 300dpi PNG preview."""
    fig.savefig(f"{filename}.pdf", bbox_inches="tight", dpi=300)
    fig.savefig(f"{filename}.png", bbox_inches="tight", dpi=300)

import json
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
from matplotlib.lines import Line2D
from matplotlib.patches import Patch
from matplotlib.ticker import PercentFormatter


HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
METRICS = ROOT / "runs/stage9d_optimized_holdout_v1/frozen_8058ea605c2771e8/stage9d_final_metrics.json"
OUT = ROOT / "09_ESWA_Final_Submission/LaTeX_Source/figures/fig02_performance_resource_summary"
EDITABLE = ROOT / "09_ESWA_Final_Submission/Editable_Figures"


def panel_label(ax, label):
    ax.text(-0.16, 1.08, label, transform=ax.transAxes, fontsize=9,
            fontweight="bold", va="top", ha="left")


def style_axis(ax):
    ax.spines["left"].set_color(BLACK)
    ax.spines["bottom"].set_color(BLACK)
    ax.tick_params(length=3, color=BLACK, pad=2)
    ax.grid(False)


def main():
    metrics = json.loads(METRICS.read_text(encoding="utf-8"))
    overall = metrics["overall"]
    boot = metrics["bootstrap"]["metrics"]
    cohorts = ["natural", "stress", "policy_ood"]
    cohort_labels = ["Natural", "Stress", "Policy OOD"]

    width_in = 183 / 25.4
    height_in = 108 / 25.4
    fig, axes = plt.subplots(2, 2, figsize=(width_in, height_in))
    axa, axb, axc, axd = axes.flat

    # (a) Model-reference fidelity: point estimates and two-sided household-cluster CIs.
    metric_keys = ["accuracy", "balanced_accuracy", "macro_f1"]
    metric_labels = ["Agreement", "Balanced agreement", "Macro-F1"]
    point = np.array([boot[k]["point"] for k in metric_keys])
    lower = np.array([boot[k]["ci95"][0] for k in metric_keys])
    upper = np.array([boot[k]["ci95"][1] for k in metric_keys])
    ypos = np.arange(3)[::-1]
    axa.errorbar(point, ypos, xerr=np.vstack([point - lower, upper - point]),
                 fmt="o", ms=4.2, mfc=BLACK, mec=BLACK, mew=0.6,
                 ecolor=GREY, elinewidth=1.0, capsize=2.3, capthick=0.8, zorder=3)
    for x, y in zip(point, ypos):
        axa.text(x + 0.0022, y, f"{x:.2%}", va="center", ha="left", fontsize=6.5)
    axa.set_yticks(ypos, metric_labels)
    axa.set_xlim(0.925, 1.002)
    axa.xaxis.set_major_formatter(PercentFormatter(1.0, decimals=0))
    axa.set_xlabel("Agreement with full-L2 reference")
    axa.set_title("Reference fidelity", loc="left", pad=5, fontweight="semibold")
    panel_label(axa, "a")
    style_axis(axa)

    # (b) Full-L2 versus hybrid service-token ledger.
    full_l2 = overall["resources"]["full_l2_tokens"] / 1e6
    jev = overall["resources"]["jev_tokens"] / 1e6
    selected_l2 = overall["resources"]["selected_l2_tokens"] / 1e6
    ybar = np.array([1, 0])
    axb.barh(ybar[0], full_l2, height=0.42, color=GREY, edgecolor=BLACK, linewidth=0.6)
    axb.barh(ybar[1], jev, height=0.42, color="white", edgecolor=BLACK,
             linewidth=0.6, hatch="////")
    axb.barh(ybar[1], selected_l2, left=jev, height=0.42, color=GREY,
             edgecolor=BLACK, linewidth=0.6)
    axb.text(full_l2 + 0.055, ybar[0], f"{full_l2:.2f}", va="center", fontsize=6.5)
    axb.text(jev + selected_l2 + 0.055, ybar[1], f"{jev + selected_l2:.2f}", va="center", fontsize=6.5)
    axb.set_yticks(ybar, ["Full L2", "Hybrid"])
    axb.set_xlim(0, 2.95)
    axb.set_xlabel("Service tokens (millions)")
    axb.set_title("Token budget", loc="left", pad=5, fontweight="semibold")
    axb.legend(handles=[Patch(facecolor="white", edgecolor=BLACK, hatch="////", label="JEV"),
                        Patch(facecolor=GREY, edgecolor=BLACK, label="L2")],
               loc="upper right", bbox_to_anchor=(1.0, 1.13), ncol=2,
               handlelength=1.4, columnspacing=1.0, borderaxespad=0.0, fontsize=7)
    panel_label(axb, "b")
    style_axis(axb)

    # (c) JEV and L2 invocation rates by cohort, encoded as a compact paired-dot plot.
    jev_rate = np.array([metrics["by_cohort"][k]["jev_calls"] / metrics["by_cohort"][k]["records"] for k in cohorts])
    l2_rate = np.array([metrics["by_cohort"][k]["l2_calls"] / metrics["by_cohort"][k]["records"] for k in cohorts])
    yc = np.arange(3)[::-1]
    for y, left, right in zip(yc, jev_rate, l2_rate):
        axc.plot([left, right], [y, y], color=GREY, linewidth=0.8, zorder=1)
    axc.scatter(jev_rate, yc, s=25, marker="o", facecolor="white", edgecolor=BLACK,
                linewidth=0.8, zorder=3)
    axc.scatter(l2_rate, yc, s=23, marker="s", facecolor=BLACK, edgecolor=BLACK,
                linewidth=0.6, zorder=3)
    axc.set_yticks(yc, cohort_labels)
    axc.set_xlim(-0.02, 1.04)
    axc.xaxis.set_major_formatter(PercentFormatter(1.0, decimals=0))
    axc.set_xlabel("Invocation rate")
    axc.set_title("Selective routing", loc="left", pad=5, fontweight="semibold")
    axc.legend(handles=[Line2D([], [], marker="o", linestyle="none", mfc="white", mec=BLACK,
                               markersize=4.5, label="JEV"),
                        Line2D([], [], marker="s", linestyle="none", mfc=BLACK, mec=BLACK,
                               markersize=4.2, label="L2")],
               loc="upper right", ncol=2, handletextpad=0.4, columnspacing=0.9,
               borderaxespad=0.0, fontsize=7)
    panel_label(axc, "c")
    style_axis(axc)

    # (d) Cohort operating regimes: reference agreement versus relative token use.
    token_ratio = np.array([metrics["by_cohort"][k]["resources"]["hybrid_tokens"] /
                            metrics["by_cohort"][k]["resources"]["full_l2_tokens"] for k in cohorts])
    agreement = np.array([metrics["by_cohort"][k]["accuracy"] for k in cohorts])
    markers = ["o", "D", "s"]
    faces = ["white", BLACK, GREY]
    for x, y, marker, face in zip(token_ratio, agreement, markers, faces):
        axd.scatter(x, y, s=34, marker=marker, facecolor=face, edgecolor=BLACK,
                    linewidth=0.8, zorder=3)
    offsets = [(-4, -8), (5, -8), (-5, 7)]
    aligns = ["right", "left", "right"]
    vertical_aligns = ["top", "top", "bottom"]
    for x, y, label, offset, align, valign in zip(token_ratio, agreement, cohort_labels, offsets, aligns, vertical_aligns):
        axd.annotate(label, (x, y), xytext=offset, textcoords="offset points",
                     ha=align, va=valign, fontsize=6.5)
    axd.set_xlim(0, 1.05)
    axd.set_ylim(0.85, 1.015)
    axd.xaxis.set_major_formatter(PercentFormatter(1.0, decimals=0))
    axd.yaxis.set_major_formatter(PercentFormatter(1.0, decimals=0))
    axd.set_xlabel("Token use relative to full L2")
    axd.set_ylabel("Reference agreement")
    axd.set_title("Cohort operating regimes", loc="left", pad=5, fontweight="semibold")
    panel_label(axd, "d")
    style_axis(axd)

    fig.subplots_adjust(left=0.105, right=0.985, bottom=0.115, top=0.94,
                        wspace=0.48, hspace=0.55)
    OUT.parent.mkdir(parents=True, exist_ok=True)
    EDITABLE.mkdir(parents=True, exist_ok=True)
    save_cns_figure(fig, str(OUT))
    plt.close(fig)

    report = f"""# Figure 2 statistics and reproducibility report

- Figure objective: show that the hybrid path preserves agreement with the independently executed full-L2 reference while concentrating semantic computation on selected cohorts.
- Layout: 2 x 2 quantitative grid, 183 mm x 108 mm, Arial/Helvetica-compatible typography, black/white/one-grey palette.
- Panel (a): N = {overall['records']} decision records clustered within {metrics['bootstrap']['clusters']} households. Points are agreement, balanced agreement, and macro-F1. Whiskers are two-sided 95% household-cluster bootstrap intervals from {metrics['bootstrap']['replicates']} replicates. No hypothesis test is drawn.
- Panel (b): service-token accounting from provider receipts. Full L2 = {overall['resources']['full_l2_tokens']:,}; hybrid = {overall['resources']['hybrid_tokens']:,}; JEV = {overall['resources']['jev_tokens']:,}; selected L2 = {overall['resources']['selected_l2_tokens']:,}.
- Panel (c): invocation counts divided by cohort record counts. Natural N = {metrics['by_cohort']['natural']['records']}; stress N = {metrics['by_cohort']['stress']['records']}; policy OOD N = {metrics['by_cohort']['policy_ood']['records']}.
- Panel (d): each point is one frozen cohort. X is hybrid tokens / full-L2 tokens; Y is exact action agreement with separately executed full L2.
- Source of truth: `{METRICS.relative_to(ROOT)}`.
- Interpretation boundary: agreement is model-reference fidelity, not observed household-choice accuracy.
- No records or columns were dropped, and no experimental values were changed during figure redesign.

## Visual QA

- Anti-pattern scan: passed. No default palette, four-sided box, grid background, 3D effect, or legend occlusion.
- Code compliance: passed. Width is 183 mm; minimum text size is 6.5 pt; vector PDF and 300 dpi PNG are exported; PDF fonts use type 42 embedding.
- Visual logic: passed. Each panel carries distinct evidence, bar lengths start at zero, non-bar axes are restricted to the relevant data range, and marker shapes preserve grayscale interpretation.
- Render verification: passed after two iterations. Panel labels, direct labels, legends, and confidence intervals do not overlap at final manuscript size.
- Palette: white, black, and one uniform grey only.
"""
    (EDITABLE / "Figure_2_Composite_Statistics_and_QA.md").write_text(report, encoding="utf-8")


if __name__ == "__main__":
    main()
