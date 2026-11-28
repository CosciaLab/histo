#!/usr/bin/env python3
"""Tables and figures from the round-2 results (settings_round2.csv).

The pick, fixed before the run: one (flow_threshold, cellprob_threshold) pair for nuclei and
cells, the one whose worst shortfall from each key result's own best is smallest (ties: higher
mean F1). Key results: cells and nuclei on Cross-platform and TissueNet, `markers` channels,
CLAHE off. Tonsil is reported, not used (partly annotated).
Writes summary_round2.csv, pick.json, channels.csv, clahe.csv, anchors.csv (with --round1),
heatmaps.png, channels.png and clahe.png.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from segmentation_benchmark.report import INK, INK_2, _style, load, summarise  # noqa: E402
from segmentation_benchmark.settings import CLAHE_PAIRS, build_round2, build_settings  # noqa: E402

KEYS = {
    "cells_crossplatform": ("cells", "raw", "markers", "crossplatform"),
    "cells_tissuenet": ("cells", "tissuenet", "markers", "tissuenet"),
    "nuclei_crossplatform": ("nuclei", "all", "markers", "crossplatform"),
    "nuclei_tissuenet": ("nuclei", "all", "markers", "tissuenet"),
}
PANELS = {  # heatmap title -> (target, scope, cell_channels, dataset)
    "Cells · Cross-platform": KEYS["cells_crossplatform"],
    "Cells · TissueNet": KEYS["cells_tissuenet"],
    "Nuclei · Cross-platform": KEYS["nuclei_crossplatform"],
    "Nuclei · TissueNet": KEYS["nuclei_tissuenet"],
    "Cells · Cross-platform, all channels": ("cells", "raw", "all", "crossplatform"),
    "Cells · Cross-platform, membrane": ("cells", "raw", "membrane", "crossplatform"),
    "Cells · Tonsil (not used)": ("cells", "raw", "markers", "tonsil"),
    "Nuclei · Tonsil (not used)": ("nuclei", "all", "markers", "tonsil"),
}
SELECTION_COLORS = {"all": "#2a78d6", "markers": "#eb6834", "membrane": "#1baf7a"}  # validated, light
PAIR = ["flow_threshold", "cellprob_threshold"]


def block(summary: pd.DataFrame, target, scope, selection, dataset, clip=0.0) -> pd.DataFrame:
    s = summary
    m = (s["target"] == target) & (s["scope"] == scope) & (s["cell_channels"] == selection)
    return s[m & (s["dataset"] == dataset) & np.isclose(s["clip_limit"], clip)]


def threshold_table(summary: pd.DataFrame) -> pd.DataFrame:
    """Long table: key, flow, cellprob, mean F1 for the four key results at CLAHE off."""
    parts = [block(summary, *spec).assign(key=key) for key, spec in KEYS.items()]
    return pd.concat(parts)[["key", *PAIR, "mean_f1"]]


def pick(table: pd.DataFrame) -> dict:
    """The pair with the smallest worst shortfall from each key's best; see the module docstring."""
    wide = table.pivot_table(index=PAIR, columns="key", values="mean_f1")
    complete = wide.dropna()
    missing = [[float(f), float(p)] for f, p in wide.index.difference(complete.index)]
    best_f1 = complete.max()
    shortfall = best_f1 - complete
    order = pd.DataFrame({"worst": shortfall.max(axis=1), "mean": complete.mean(axis=1)})
    chosen = order.sort_values(["worst", "mean"], ascending=[True, False]).index[0]
    return {
        "pair": [_num(chosen[0]), _num(chosen[1])],
        "worst_shortfall": float(order.loc[chosen, "worst"]),
        "f1": {k: float(complete.loc[chosen, k]) for k in complete.columns},
        "shortfall": {k: float(shortfall.loc[chosen, k]) for k in complete.columns},
        "best": {
            k: {"pair": [_num(v) for v in complete[k].idxmax()], "f1": float(best_f1[k])}
            for k in complete.columns
        },
        "missing_pairs": [[_num(f), _num(p)] for f, p in missing],
    }


def _num(x) -> float | int:
    return int(x) if float(x).is_integer() else float(x)


def channel_table(df: pd.DataFrame, pair: list) -> pd.DataFrame:
    """Mean cells F1 per channel selection and group (Vectra, CODEX, Tonsil) at `pair`, CLAHE off."""
    m = (df["target"] == "cells") & (df["scope"] == "raw") & np.isclose(df["clip_limit"], 0)
    m &= np.isclose(df["flow_threshold"], pair[0]) & np.isclose(df["cellprob_threshold"], pair[1])
    sub = df[m]
    out = sub.groupby(["cell_channels", "group"])["f1"].agg(mean_f1="mean", n="count").reset_index()
    cp = sub[sub["dataset"] == "crossplatform"].groupby("cell_channels")["f1"].agg(mean_f1="mean", n="count")
    return pd.concat([out, cp.reset_index().assign(group="Cross-platform")], ignore_index=True)


def clahe_table(summary: pd.DataFrame) -> pd.DataFrame:
    """Mean F1 at the CLAHE pairs, clip 0 vs 0.01, per key result and Tonsil."""
    specs = dict(
        KEYS,
        cells_tonsil=("cells", "raw", "markers", "tonsil"),
        nuclei_tonsil=("nuclei", "all", "markers", "tonsil"),
    )
    rows = []
    for key, spec in specs.items():
        for clip in (0.0, 0.01):
            b = block(summary, *spec, clip=clip).set_index(PAIR)["mean_f1"]
            for flow, prob in CLAHE_PAIRS:
                rows.append({"key": key, "flow_threshold": flow, "cellprob_threshold": prob, "clip_limit": clip,
                             "mean_f1": b.get((flow, prob), np.nan)})  # fmt: skip
    t = (
        pd.DataFrame(rows)
        .pivot_table(index=["key", *PAIR], columns="clip_limit", values="mean_f1")
        .reset_index()
    )
    t.columns = ["key", *PAIR, "f1_clahe_off", "f1_clahe_001"]
    return t.assign(difference=t["f1_clahe_001"] - t["f1_clahe_off"])


def anchors(summary: pd.DataFrame, round1: Path) -> pd.DataFrame:
    """Round-1 rows that round 2 repeats exactly (same preprocessing and thresholds): mean F1 side by side."""
    r1 = summarise(load(round1, build_settings())).merge(build_settings(), on=["index", "target", "scope"])
    same = {"projection_method": "max", "low_percentile": 1, "projection_sigma": 0, "gaussian_sigma": 0}
    rows = []
    for target, scope in [("cells", "raw"), ("cells", "tissuenet")]:
        a = r1[(r1["target"] == target) & (r1["scope"] == scope) & np.isclose(r1["clip_limit"], 0)]
        # TissueNet ignores the projection factors (run.prepare_input); only the Gaussian matters.
        for k, v in (same if scope == "raw" else {"gaussian_sigma": 0}).items():
            a = a[a[k] == v]
        for _, r in a.iterrows():
            b = block(summary, target, scope, "all" if scope == "raw" else "markers", r["dataset"])
            b = b[
                np.isclose(b["flow_threshold"], r["flow_threshold"])
                & np.isclose(b["cellprob_threshold"], r["cellprob_threshold"])
            ]
            rows.append({"target": target, "dataset": r["dataset"], "flow_threshold": r["flow_threshold"],
                         "cellprob_threshold": r["cellprob_threshold"], "round1": r["mean_f1"],
                         "round2": b["mean_f1"].iloc[0] if len(b) else np.nan})  # fmt: skip
    t = pd.DataFrame(rows)
    return t.assign(difference=t["round2"] - t["round1"])


def plot_heatmaps(summary: pd.DataFrame, chosen: list, out: Path) -> None:
    import matplotlib.pyplot as plt
    from matplotlib.colors import LinearSegmentedColormap
    from matplotlib.patches import Rectangle

    cmap = LinearSegmentedColormap.from_list("blue", ["#eaf1fb", "#2a78d6", "#0e3a73"])
    fig, axes = plt.subplots(2, 4, figsize=(26, 13), constrained_layout=True)
    for ax, (title, spec) in zip(axes.flat, PANELS.items(), strict=True):
        grid = block(summary, *spec).pivot_table(
            index="flow_threshold", columns="cellprob_threshold", values="mean_f1"
        )
        ax.grid(False)
        ax.set_title(title, fontsize=16)
        if grid.empty:
            ax.text(0.5, 0.5, "no results", ha="center", va="center", transform=ax.transAxes)
            continue
        ax.imshow(grid.values, cmap=cmap, aspect="auto")
        ax.set_xticks(range(grid.shape[1]), [_fmt(c) for c in grid.columns], fontsize=12)
        ax.set_yticks(range(grid.shape[0]), [_fmt(r) for r in grid.index], fontsize=12)
        ax.set_xlabel("cellprob_threshold", fontsize=13)
        ax.set_ylabel("flow_threshold", fontsize=13)
        lo, hi = np.nanmin(grid.values), np.nanmax(grid.values)
        for (i, j), v in np.ndenumerate(grid.values):
            dark = hi > lo and (v - lo) / (hi - lo) > 0.55
            ax.text(j, i, "" if np.isnan(v) else f"{v:.2f}", ha="center", va="center", fontsize=11,
                    color="white" if dark else INK)  # fmt: skip
        bi, bj = np.unravel_index(np.nanargmax(grid.values), grid.shape)
        ax.add_patch(Rectangle((bj - 0.5, bi - 0.5), 1, 1, fill=False, ec=INK_2, lw=2, ls="--"))
        if chosen[0] in grid.index and chosen[1] in grid.columns:
            ci, cj = grid.index.get_loc(chosen[0]), grid.columns.get_loc(chosen[1])
            ax.add_patch(Rectangle((cj - 0.5, ci - 0.5), 1, 1, fill=False, ec=INK, lw=3.5))
    fig.suptitle(
        f"Mean F1 (IoU 0.5) by threshold pair. Solid box: pick {chosen}; dashed: panel's best", fontsize=18
    )
    fig.savefig(out / "heatmaps.png", dpi=150)
    plt.close(fig)


def _fmt(x) -> str:
    return f"{x:g}"


def plot_channels(table: pd.DataFrame, chosen: list, out: Path) -> None:
    import matplotlib.pyplot as plt

    groups = [g for g in ["Cross-platform", "Vectra", "CODEX", "Tonsil"] if g in set(table["group"])]
    fig, ax = plt.subplots(figsize=(12, 6.5), constrained_layout=True)
    width = 0.26
    for k, (sel, color) in enumerate(SELECTION_COLORS.items()):
        t = table[table["cell_channels"] == sel].set_index("group").reindex(groups)
        x = np.arange(len(groups)) + (k - 1) * (width + 0.02)
        ax.bar(x, t["mean_f1"], width, color=color, label=sel)
        for xi, v in zip(x, t["mean_f1"], strict=True):
            if not np.isnan(v):
                ax.text(xi, v + 0.01, f"{v:.2f}", ha="center", va="bottom", fontsize=12, color=INK)
    ax.set_xticks(range(len(groups)), groups)
    ax.set_ylim(0, 1)
    ax.set_ylabel("Mean cells F1 (IoU 0.5)")
    ax.grid(axis="x", visible=False)
    ax.legend(title="Cell channels", loc="upper left", ncols=3)
    ax.set_title(f"Cell channel selection at thresholds {chosen}, CLAHE off")
    fig.savefig(out / "channels.png", dpi=150)
    plt.close(fig)


def plot_clahe(table: pd.DataFrame, out: Path) -> None:
    import matplotlib.pyplot as plt

    keys = list(dict.fromkeys(table["key"]))
    fig, ax = plt.subplots(figsize=(12, 6.5), constrained_layout=True)
    for i, key in enumerate(keys):
        d = table[table["key"] == key]["difference"].dropna()
        jitter = np.linspace(-0.15, 0.15, len(d)) if len(d) > 1 else [0]
        ax.scatter(np.full(len(d), i) + jitter, d, s=70, color="#a9a8a1", zorder=3)
        if len(d):
            ax.scatter([i], [d.mean()], s=180, color=INK, zorder=4)
    ax.axhline(0, color=INK_2, lw=1.5)
    ax.set_xticks(range(len(keys)), [k.replace("_", "\n") for k in keys], fontsize=13)
    ax.set_ylabel("F1 with CLAHE 0.01 minus CLAHE off")
    ax.grid(axis="x", visible=False)
    ax.set_title("CLAHE 0.01 at 9 threshold pairs (grey) and their mean (black)")
    fig.savefig(out / "clahe.png", dpi=150)
    plt.close(fig)


def build_report(results: Path, out: Path, round1: Path | None = None) -> dict:
    out.mkdir(parents=True, exist_ok=True)
    settings = build_round2()
    df = load(results, settings)
    summary = summarise(df).merge(settings, on=["index", "target", "scope"])
    missing = sorted(set(settings["index"]) - set(summary["index"]))
    if missing:
        print(f"WARNING: {len(missing)} settings have no results: {missing}", file=sys.stderr)
    summary.to_csv(out / "summary_round2.csv", index=False)
    chosen = pick(threshold_table(summary))
    chosen["missing_settings"] = missing
    (out / "pick.json").write_text(json.dumps(chosen, indent=2))
    channels = channel_table(df, chosen["pair"])
    channels.to_csv(out / "channels.csv", index=False)
    clahe = clahe_table(summary)
    clahe.to_csv(out / "clahe.csv", index=False)
    if round1 is not None:
        anchors(summary, round1).to_csv(out / "anchors.csv", index=False)
    _style()
    plot_heatmaps(summary, chosen["pair"], out)
    plot_channels(channels, chosen["pair"], out)
    plot_clahe(clahe, out)
    return chosen


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("--results", type=Path, required=True, help="round-2 results/ directory")
    p.add_argument("--out", type=Path, required=True)
    p.add_argument("--round1", type=Path, help="round-1 results/, to check the repeated settings")
    a = p.parse_args()
    chosen = build_report(a.results, a.out, a.round1)
    print(json.dumps({k: chosen[k] for k in ("pair", "worst_shortfall", "f1", "best")}, indent=2))


if __name__ == "__main__":
    main()
