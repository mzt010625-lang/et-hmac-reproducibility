# Academic Figure Skill Asset Confirmation (verified against assets/figures/)
# Sankey -> assets/figures/SankeyDiagram/plot_SankeyDiagram.py -> param inherit
# Reason: the production asset simulates eight-layer categorical data, whereas this
# figure must preserve all 23 frozen two-layer disagreement records. Native reuse
# would change the data and the graph's meaning.
# RULE: "native run" = load pre-rendered PNG via Image.open().ax.imshow().
#       "param inherit" = drawing function below that copies Class A/B/C values.

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

from collections import Counter, defaultdict
import csv
import json
from pathlib import Path

mpl.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.path import Path as MplPath
from matplotlib.patches import PathPatch, Rectangle


HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
FROZEN = ROOT / "runs/stage9d_optimized_holdout_v1/frozen_8058ea605c2771e8/policy_ood"
OUT = ROOT / "09_ESWA_Final_Submission/LaTeX_Source/figures/fig03_ood_disagreement_sankey"
CSV = HERE / "Figure_3_OOD_Sankey_Source_Data.csv"
REPORT = HERE / "Figure_3_OOD_Sankey_Statistics_and_QA.md"

DISPLAY = {
    "list_for_rent": "List for rent",
    "list_for_sale": "List for sale",
    "search_buy": "Search buy",
    "search_jeonse": "Search jeonse",
    "search_monthly_rent": "Search monthly rent",
    "stay": "Stay",
    "wait": "Wait",
}


def read_jsonl(path: Path) -> dict[str, dict]:
    rows = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line]
    found = {row["record_id"]: row["output"] for row in rows}
    if len(found) != len(rows):
        raise ValueError(f"Duplicate record IDs in {path}")
    return found


def transitions() -> tuple[list[tuple[str, str, str, int]], dict[str, int]]:
    hybrid = read_jsonl(FROZEN / "hybrid/l2_parsed.jsonl")
    full = read_jsonl(FROZEN / "full/l2_parsed.jsonl")
    if len(hybrid) != 200 or set(hybrid) != set(full):
        raise ValueError("Expected 200 identically identified OOD L2 records in both arms")
    counts: Counter[tuple[str, str, str]] = Counter()
    for rid in sorted(hybrid):
        h, f = hybrid[rid], full[rid]
        if h["final_action"] == f["final_action"]:
            continue
        if h["final_action"] not in DISPLAY or f["final_action"] not in DISPLAY:
            raise ValueError(f"Unknown action in {rid}")
        accepted = int(bool(h["guard_accepted"])) + int(bool(f["guard_accepted"]))
        if accepted == 1:
            pattern = "Asymmetric validation"
        elif accepted == 2:
            pattern = "Both valid"
        else:
            raise ValueError(f"Unexpected both-invalid disagreement in {rid}")
        counts[(h["final_action"], f["final_action"], pattern)] += 1
    rows = [(src, dst, pattern, n) for (src, dst, pattern), n in sorted(counts.items())]
    pattern_counts = Counter({pattern: sum(n for _, _, mode, n in rows if mode == pattern)
                              for pattern in ("Asymmetric validation", "Both valid")})
    if sum(n for *_, n in rows) != 23 or len(rows) != 15 or pattern_counts != {
        "Asymmetric validation": 21, "Both valid": 2
    }:
        raise ValueError(f"OOD disagreement audit changed: {len(rows)} links, {pattern_counts}")
    return rows, dict(pattern_counts)


def barycentric_order(rows: list[tuple[str, str, str, int]]) -> tuple[list[str], list[str]]:
    left_counts = Counter()
    right_counts = Counter()
    for src, dst, _, n in rows:
        left_counts[src] += n
        right_counts[dst] += n
    left = sorted(left_counts, key=lambda name: (-left_counts[name], name))
    right = sorted(right_counts, key=lambda name: (-right_counts[name], name))
    for _ in range(8):
        li = {name: i for i, name in enumerate(left)}
        right.sort(key=lambda dst: (
            sum(li[src] * n for src, target, _, n in rows if target == dst) / right_counts[dst],
            -right_counts[dst], dst,
        ))
        ri = {name: i for i, name in enumerate(right)}
        left.sort(key=lambda src: (
            sum(ri[dst] * n for source, dst, _, n in rows if source == src) / left_counts[src],
            -left_counts[src], src,
        ))
    return left, right


def layout(names: list[str], counts: Counter[str], unit: float) -> dict[str, tuple[float, float]]:
    gap = 0.025
    top = 0.86
    positions = {}
    for name in names:
        height = counts[name] * unit
        positions[name] = (top - height, top)
        top -= height + gap
    if top < 0.09:
        raise ValueError("Flow labels would extend below the figure")
    return positions


def ribbon(ax, x_left: float, x_right: float, source: tuple[float, float],
           target: tuple[float, float], color: str) -> None:
    sy0, sy1 = source
    ty0, ty1 = target
    c1 = x_left + (x_right - x_left) * 0.38
    c2 = x_right - (x_right - x_left) * 0.38
    verts = [(x_left, sy1), (c1, sy1), (c2, ty1), (x_right, ty1),
             (x_right, ty0), (c2, ty0), (c1, sy0), (x_left, sy0),
             (x_left, sy1)]
    codes = [MplPath.MOVETO, MplPath.CURVE4, MplPath.CURVE4, MplPath.CURVE4,
             MplPath.LINETO, MplPath.CURVE4, MplPath.CURVE4, MplPath.CURVE4,
             MplPath.CLOSEPOLY]
    ax.add_patch(PathPatch(MplPath(verts, codes), facecolor=color,
                           edgecolor="white", linewidth=0.3, antialiased=True))


def main() -> None:
    rows, patterns = transitions()
    left_names, right_names = barycentric_order(rows)
    left_counts = Counter()
    right_counts = Counter()
    for src, dst, _, n in rows:
        left_counts[src] += n
        right_counts[dst] += n
    unit = 0.023
    left = layout(left_names, left_counts, unit)
    right = layout(right_names, right_counts, unit)
    left_index = {name: i for i, name in enumerate(left_names)}
    right_index = {name: i for i, name in enumerate(right_names)}
    from_left = defaultdict(list)
    to_right = defaultdict(list)
    for row in rows:
        from_left[row[0]].append(row)
        to_right[row[1]].append(row)
    source_slots = {}
    target_slots = {}
    for src, group in from_left.items():
        y = left[src][0]
        for row in sorted(group, key=lambda item: (right_index[item[1]], item[2])):
            source_slots[row] = (y, y + row[3] * unit)
            y += row[3] * unit
    for dst, group in to_right.items():
        y = right[dst][0]
        for row in sorted(group, key=lambda item: (left_index[item[0]], item[2])):
            target_slots[row] = (y, y + row[3] * unit)
            y += row[3] * unit

    fig, ax = plt.subplots(figsize=(183 / 25.4, 86 / 25.4))
    fig.patch.set_facecolor("white")
    ax.set_xlim(0, 1)
    ax.set_ylim(0, 1)
    ax.axis("off")
    ax.text(0.015, 0.965, "23 policy-OOD action disagreements",
            ha="left", va="top", fontsize=9, fontweight="semibold", color=BLACK)
    ax.text(0.27, 0.91, "Hybrid final action", ha="right", va="center",
            fontsize=8, fontweight="semibold", color=BLACK)
    ax.text(0.73, 0.91, "Independent full-L2 action", ha="left", va="center",
            fontsize=8, fontweight="semibold", color=BLACK)

    for row in sorted(rows, key=lambda item: item[2] == "Both valid"):
        color = BLACK if row[2] == "Both valid" else GREY
        ribbon(ax, 0.28, 0.72, source_slots[row], target_slots[row], color)

    for names, positions, counts, x, text_x, align in [
        (left_names, left, left_counts, 0.268, 0.258, "right"),
        (right_names, right, right_counts, 0.720, 0.742, "left"),
    ]:
        for name in names:
            low, high = positions[name]
            ax.add_patch(Rectangle((x, low), 0.012, high - low,
                                   facecolor="white", edgecolor=BLACK, linewidth=0.8))
            ax.text(text_x, (low + high) / 2, f"{DISPLAY[name]}  {counts[name]}",
                    ha=align, va="center", fontsize=7.1, color=BLACK)

    ax.add_patch(Rectangle((0.27, 0.035), 0.018, 0.012, facecolor=GREY, edgecolor="none"))
    ax.text(0.295, 0.041, "Asymmetric validation (21)", fontsize=7.2,
            va="center", ha="left", color=BLACK)
    ax.add_patch(Rectangle((0.58, 0.035), 0.018, 0.012, facecolor=BLACK, edgecolor="none"))
    ax.text(0.605, 0.041, "Both L2 outputs valid (2)", fontsize=7.2,
            va="center", ha="left", color=BLACK)

    fig.subplots_adjust(left=0.012, right=0.988, top=0.995, bottom=0.015)
    OUT.parent.mkdir(parents=True, exist_ok=True)
    save_cns_figure(fig, str(OUT))
    fig.savefig(f"{OUT}.svg", bbox_inches="tight")
    plt.close(fig)

    with CSV.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle)
        writer.writerow(["hybrid_final_action", "full_l2_final_action", "validation_pattern", "records"])
        writer.writerows(rows)

    REPORT.write_text(
        "# Figure 3 statistics and reproducibility report\n\n"
        "- Objective: expose the directional action differences after all 200 synthetic policy-OOD records were routed to L2.\n"
        "- Figure type: compact two-column Sankey, 183 mm × 86 mm, black/white/one uniform grey.\n"
        "- Unit of analysis: one synthetic household-policy OOD record; 23 records with different final actions are shown, no downsampling.\n"
        "- The ribbons encode 15 directed action-pair types; ribbon thickness is the exact number of records (1–4).\n"
        "- Grey represents the 21 asymmetric evidence/output-validation disagreements; black represents two disagreements in which both L2 outputs were valid. No significance test or confidence interval is asserted by this descriptive figure.\n"
        f"- Source: `{(FROZEN / 'hybrid/l2_parsed.jsonl').relative_to(ROOT)}` and `{(FROZEN / 'full/l2_parsed.jsonl').relative_to(ROOT)}`.\n"
        "- Node totals and all 15 link totals are exported to `Figure_3_OOD_Sankey_Source_Data.csv`.\n"
        "- Interpretation boundary: these are independent model-reference disagreements, not errors against observed household choices.\n"
        "- Asset scan: eight-layer simulated Sankey production script was incompatible with two-layer frozen observations; no simulated rows were reused.\n"
        "- QA: 23/23 records accounted for; 21 + 2 validation split verified; 200/200 OOD records had both L2 receipts; ≥7 pt direct labels; no default palette, grid, or 3-D effect; vector PDF and SVG plus 300 dpi PNG exported.\n",
        encoding="utf-8",
    )
    print(json.dumps({"records": 23, "directed_flows": 15, "patterns": patterns,
                      "left_nodes": left_names, "right_nodes": right_names,
                      "output_pdf": str(OUT) + ".pdf"}, indent=2))


if __name__ == "__main__":
    main()
