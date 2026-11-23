#!/usr/bin/env python3
"""Tables and figures from the benchmark's results/ directory.

Cross-platform decides: the best cells setting (0-143) and the best nuclei setting (156-167)
are the ones with the highest mean Cross-platform F1. TissueNet cell settings (144-155) are
ranked on TissueNet alone. Crops whose F1 is NaN (both masks empty) are counted, never averaged.
Writes summary.csv, headline.json, effects_<factor>.png, interaction.png, platforms.png and
montage_<dataset>__<crop>.png.
"""

from __future__ import annotations

import argparse
import itertools
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from segmentation_benchmark.settings import today_index  # noqa: E402

# Ranking blocks: name -> (target, scope, dataset the rank is decided on).
BLOCKS = {
    "cells_raw": ("cells", "raw", "crossplatform"),
    "nuclei_all": ("nuclei", "all", "crossplatform"),
    "cells_tissuenet": ("cells", "tissuenet", "tissuenet"),
}
FACTORS = {
    "projection_method": "Projection method",
    "low_percentile": "Low percentile",
    "projection_sigma": "Projection sigma",
    "gaussian_sigma": "Gaussian sigma",
    "clip_limit": "CLAHE clip limit",
    "thresholds": "Flow / cellprob thresholds",
}
FACTOR_COLUMNS = [c for c in FACTORS if c != "thresholds"] + ["flow_threshold", "cellprob_threshold"]
GROUPS = ["Vectra", "CODEX", "Tonsil", "TissueNet"]

# dataviz palette, light surface: blue = today, orange = best.
TODAY_COLOR, BEST_COLOR = "#2a78d6", "#eb6834"
INK, INK_2, GRID, POINT = "#0b0b0b", "#52514e", "#e4e3de", "#a9a8a1"
F1_LABEL = "Cross-platform F1 (IoU 0.5)"


def load(results: Path, settings: pd.DataFrame) -> pd.DataFrame:
    """Per-crop rows of every finished setting, with the setting's factors attached."""
    files = sorted(p for p in results.glob("*.csv") if not p.name.endswith(".partial.csv"))
    if not files:
        raise SystemExit(f"no results/<N>.csv in {results}")
    df = pd.concat([pd.read_csv(p, dtype={"crop": str}) for p in files], ignore_index=True)
    df["group"] = np.where(df["dataset"] == "crossplatform", df["platform"], df["dataset"].str.capitalize())
    df.loc[df["dataset"] == "tissuenet", "group"] = "TissueNet"
    return df.drop(columns=["target"]).merge(settings, on="index", how="left")


def summarise(df: pd.DataFrame) -> pd.DataFrame:
    """Per setting x dataset: mean and SD of F1 and mean AP over crops, n crops, n NaN crops."""
    grouped = df.groupby(["index", "target", "scope", "dataset"])
    out = grouped.agg(
        mean_f1=("f1", "mean"),
        sd_f1=("f1", "std"),
        mean_ap=("mean_ap", "mean"),
        sd_ap=("mean_ap", "std"),
        n_crops=("f1", "size"),
        n_nan=("f1", lambda s: int(s.isna().sum())),
    )
    return out.reset_index()


def _row(summary: pd.DataFrame, settings: pd.DataFrame, index: int, dataset: str) -> dict | None:
    """One headline row: factor values and scores of setting `index` on `dataset`."""
    sel = summary[(summary["index"] == index) & (summary["dataset"] == dataset)]
    if sel.empty:
        return None
    s = sel.iloc[0]
    factors = settings.set_index("index").loc[index, FACTOR_COLUMNS].to_dict()
    by_dataset = summary[summary["index"] == index].set_index("dataset")["mean_f1"]
    return {
        "index": index,
        **{k: (v.item() if hasattr(v, "item") else v) for k, v in factors.items()},
        "dataset": dataset,
        "mean_f1": _num(s["mean_f1"]),
        "mean_ap": _num(s["mean_ap"]),
        "n_crops": int(s["n_crops"]),
        "n_nan": int(s["n_nan"]),
        "f1_by_dataset": {d: _num(v) for d, v in by_dataset.items()},
    }


def _num(value) -> float | None:
    return None if pd.isna(value) else float(value)


def headline(summary: pd.DataFrame, settings: pd.DataFrame) -> tuple[dict, dict]:
    """headline.json content and the best/today index of each block that has results."""
    found = set(summary["index"])
    missing = sorted(set(settings["index"]) - found)
    if missing:
        print(f"WARNING: {len(missing)} settings have no results: {missing}", file=sys.stderr)
    out, picks = {"missing_settings": missing}, {}
    for name, (target, scope, dataset) in BLOCKS.items():
        block = settings[(settings["target"] == target) & (settings["scope"] == scope)]["index"]
        block_missing = sorted(set(block) - found)
        ranked = summary[
            summary["index"].isin(block) & (summary["dataset"] == dataset) & summary["mean_f1"].notna()
        ]
        if ranked.empty:
            print(f"{name}: no results on {dataset}, skipped", file=sys.stderr)
            continue
        best = int(ranked.loc[ranked["mean_f1"].idxmax(), "index"])
        today = today_index(settings, target, scope)
        if block_missing:
            print(f"WARNING {name}: {len(block_missing)} of {len(block)} settings missing", file=sys.stderr)
        if today in block_missing:
            print(f"WARNING {name}: today's setting {today} has no results", file=sys.stderr)
        best_row, today_row = _row(summary, settings, best, dataset), _row(summary, settings, today, dataset)
        diff = None
        if today_row and best_row["mean_f1"] is not None and today_row["mean_f1"] is not None:
            diff = best_row["mean_f1"] - today_row["mean_f1"]
        out[name] = {
            "best": best_row,
            "today": today_row,
            "f1_difference": diff,
            "today_missing": today in block_missing,
            "missing_settings": block_missing,
        }
        picks[name] = (best, today)
    return out, picks


def _style():
    import matplotlib as mpl

    mpl.use("Agg")
    mpl.rcParams.update(
        {
            "font.size": 16,
            "axes.titlesize": 20,
            "axes.titleweight": "bold",
            "axes.labelsize": 16,
            "axes.edgecolor": INK_2,
            "axes.labelcolor": INK,
            "text.color": INK,
            "xtick.color": INK_2,
            "ytick.color": INK_2,
            "axes.spines.top": False,
            "axes.spines.right": False,
            "axes.grid": True,
            "axes.axisbelow": True,
            "grid.color": GRID,
            "grid.linewidth": 1,
            "figure.facecolor": "white",
            "axes.facecolor": "white",
            "savefig.facecolor": "white",
            "legend.frameon": False,
        }
    )


def _level_table(block: pd.DataFrame) -> pd.DataFrame:
    """Settings of the block with a combined `thresholds` factor column."""
    block = block.copy()
    block["thresholds"] = [
        f"flow {f:g}\nprob {p:g}"
        for f, p in zip(block["flow_threshold"], block["cellprob_threshold"], strict=True)
    ]
    return block


def effect_ranges(table: pd.DataFrame) -> dict[str, pd.Series]:
    """Per factor, the mean F1 of each level, marginalised over the other factors."""
    return {f: table.groupby(f)["mean_f1"].mean() for f in FACTORS if table[f].nunique() > 1}


def plot_effects(table: pd.DataFrame, today: pd.Series, out: Path, note: str = "") -> dict[str, pd.Series]:
    import matplotlib.pyplot as plt
    from matplotlib.lines import Line2D

    means = effect_ranges(table)
    lo, hi = table["mean_f1"].min(), table["mean_f1"].max()
    pad = 0.08 * max(hi - lo, 0.05)
    rng = np.random.default_rng(0)
    for factor, level_means in means.items():
        fig, ax = plt.subplots(figsize=(10, 5.6))
        levels = list(level_means.index)
        for i, level in enumerate(levels):
            ys = table.loc[table[factor] == level, "mean_f1"]
            ax.scatter(
                i + rng.uniform(-0.18, 0.18, len(ys)),
                ys,
                s=36,
                color=POINT,
                alpha=0.7,
                linewidths=0,
                zorder=2,
            )
            ax.scatter(i, level_means[level], s=220, color=INK, edgecolor="white", linewidths=2, zorder=3)
            ax.annotate(
                f"{level_means[level]:.3f}",
                (i, level_means[level]),
                xytext=(26, 0),
                textcoords="offset points",
                va="center",
                fontsize=15,
                bbox={"fc": "white", "ec": "none", "alpha": 0.85, "pad": 1.5},
                zorder=4,
            )
        ticks = [f"{lv:g}" if isinstance(lv, int | float) else str(lv) for lv in levels]
        is_today = [str(today[factor]) == str(lv) for lv in levels]
        ax.set_xticks(
            range(len(levels)), [t + ("\n(today)" if m else "") for t, m in zip(ticks, is_today, strict=True)]
        )
        ax.set_xlim(-0.6, len(levels) - 0.4)
        ax.set_ylim(lo - pad, hi + pad)
        ax.set_xlabel(FACTORS[factor])
        ax.set_ylabel(f"Mean {F1_LABEL}")
        ax.set_title(f"{FACTORS[factor]}: mean F1 per level")
        ax.grid(axis="x", visible=False)
        handles = [
            Line2D([], [], marker="o", ls="", color=POINT, markersize=7, label="one setting"),
            Line2D([], [], marker="o", ls="", color=INK, markersize=13, label="mean over settings"),
        ]
        fig.legend(handles=handles, loc="lower center", ncol=2, fontsize=14)
        if note:
            fig.text(0.01, 0.01, note, fontsize=12, color=BEST_COLOR, fontweight="bold")
        fig.tight_layout(rect=(0, 0.07, 1, 1))
        fig.savefig(out / f"effects_{factor}.png", dpi=200)
        plt.close(fig)
    return means


def plot_interaction(table: pd.DataFrame, means: dict[str, pd.Series], out: Path, note: str = "") -> None:
    import matplotlib.pyplot as plt
    from matplotlib.colors import LinearSegmentedColormap

    ranked = sorted(means, key=lambda f: means[f].max() - means[f].min(), reverse=True)
    if len(ranked) < 2:
        print("interaction.png: fewer than two varying factors, skipped", file=sys.stderr)
        return
    a, b = ranked[:2]
    grid = table.pivot_table(index=a, columns=b, values="mean_f1", aggfunc="mean")
    cmap = LinearSegmentedColormap.from_list("blue", ["#eaf1fb", "#2a78d6", "#0e3a73"])
    fig, ax = plt.subplots(figsize=(10, 5.6))
    im = ax.imshow(grid.values, cmap=cmap, aspect="auto")
    mid = (np.nanmin(grid.values) + np.nanmax(grid.values)) / 2
    for i, j in itertools.product(range(grid.shape[0]), range(grid.shape[1])):
        v = grid.values[i, j]
        ax.text(j, i, f"{v:.3f}", ha="center", va="center", fontsize=18, color="white" if v > mid else INK)
    fmt = lambda lv: f"{lv:g}" if isinstance(lv, int | float) else str(lv)  # noqa: E731
    ax.set_xticks(range(grid.shape[1]), [fmt(v) for v in grid.columns])
    ax.set_yticks(range(grid.shape[0]), [fmt(v) for v in grid.index])
    ax.set_xlabel(FACTORS[b])
    ax.set_ylabel(FACTORS[a])
    ax.set_title(f"{FACTORS[a]} x {FACTORS[b]}: mean F1", fontsize=17)
    ax.grid(False)
    for s in ax.spines.values():
        s.set_visible(False)
    fig.colorbar(im, ax=ax, label=f"Mean {F1_LABEL}")
    if note:
        fig.text(0.01, 0.01, note, fontsize=12, color=BEST_COLOR, fontweight="bold")
    fig.tight_layout(rect=(0, 0.04 if note else 0, 1, 1))
    fig.savefig(out / "interaction.png", dpi=200)
    plt.close(fig)


def plot_platforms(df: pd.DataFrame, picks: dict, out: Path) -> None:
    """Best vs today per platform (Vectra, CODEX) and dataset (Tonsil, TissueNet)."""
    import matplotlib.pyplot as plt

    rows = []
    for group in GROUPS:
        name = "cells_tissuenet" if group == "TissueNet" else "cells_raw"
        if name not in picks:
            continue
        best, today = picks[name]
        sub = df[df["group"] == group]
        both = (
            sub[sub["index"] == today]
            .set_index(["dataset", "crop"])["f1"]
            .to_frame("today")
            .join(sub[sub["index"] == best].set_index(["dataset", "crop"])["f1"].rename("best"), how="inner")
            .dropna()  # only crops scored by both settings, so the bars compare like with like
        )
        if len(both):
            rows.append((group, both, len(both)))
    if not rows:
        print("platforms.png: no data, skipped", file=sys.stderr)
        return
    fig, ax = plt.subplots(figsize=(10, 5.6))
    width = 0.36
    for label, color, shift in [("Today", TODAY_COLOR, -1), ("Best", BEST_COLOR, 1)]:
        key = label.lower()
        for i, (_g, vals, _n) in enumerate(rows):
            m = vals[key].mean()
            if np.isnan(m):
                continue
            x = i + shift * width / 2
            ax.bar(x, m, width - 0.04, color=color, label=label if i == 0 else None, zorder=2)
            ax.text(x, m + 0.01, f"{m:.2f}", ha="center", va="bottom", fontsize=15)
    ax.set_xticks(range(len(rows)), [f"{g}\nn = {n}" for g, _v, n in rows])
    ax.set_ylim(0, 1)
    ax.set_ylabel("Mean F1 (IoU 0.5)")
    ax.set_title("Best vs today: mean F1 per platform and dataset")
    ax.grid(axis="x", visible=False)
    ax.legend(loc="upper right", ncol=2, fontsize=15)
    fig.text(
        0.01,
        0.01,
        "n = crops scored by both settings. TissueNet: best of its own settings (144-155).",
        fontsize=12,
        color=INK_2,
    )
    fig.tight_layout(rect=(0, 0.03, 1, 1))
    fig.savefig(out / "platforms.png", dpi=200)
    plt.close(fig)


def _crop_preview(data: Path, crop: pd.Series) -> np.ndarray:
    """Projection preview as the pipeline makes it: nuclear magenta, cells green."""
    import tifffile
    from segmentation_benchmark.preprocess import project  # puts bin/ on sys.path

    from project_channels import preview_rgb

    image = tifffile.imread(data / "crops" / crop["dataset"] / crop["crop"] / "image.tif")
    sigma = 0 if crop["dataset"] == "tissuenet" else 1
    proj = project(image, int(crop["nuclear"]), "max", 1, sigma) / 65535
    return preview_rgb(proj[1], proj[0])


def _outline(rgb: np.ndarray, labels: np.ndarray) -> np.ndarray:
    from skimage.segmentation import find_boundaries

    out = rgb.copy()
    out[find_boundaries(labels, mode="inner")] = (255, 255, 0)
    return out


def plot_montages(df: pd.DataFrame, picks: dict, data: Path, results: Path, out: Path) -> None:
    import matplotlib.pyplot as plt
    import tifffile

    crops_csv = data / "crops.csv"
    if not crops_csv.exists():
        print(f"no {crops_csv}, montages skipped", file=sys.stderr)
        return
    crops = pd.read_csv(crops_csv, dtype={"crop": str})
    label_root = results.parent / "labels"
    for _, crop in crops[crops["montage"].astype(bool)].iterrows():
        name = "cells_tissuenet" if crop["dataset"] == "tissuenet" else "cells_raw"
        key = f"{crop['dataset']}__{crop['crop']}"
        if name not in picks:
            continue
        best, today = picks[name]
        paths = {i: label_root / str(i) / f"{key}.tif" for i in {best, today}}
        truth_path = data / "crops" / crop["dataset"] / crop["crop"] / "cells.tif"
        missing = [p for p in [*paths.values(), truth_path] if not p.exists()]
        if missing:
            print(f"montage {key}: missing {missing[0]}, skipped", file=sys.stderr)
            continue
        rgb = _crop_preview(data, crop)
        sub = df[(df["dataset"] == crop["dataset"]) & (df["crop"] == crop["crop"])].set_index("index")["f1"]
        panels = [("Ground truth\n(reference)", tifffile.imread(truth_path))]
        for label, i in (("Today", today), ("Best", best)):
            f1 = sub.get(i, np.nan)
            shown = "n/a" if pd.isna(f1) else f"{f1:.2f}"
            panels.append((f"{label} (setting {i})\nF1 (IoU 0.5) {shown}", tifffile.imread(paths[i])))
        fig, axes = plt.subplots(1, 3, figsize=(16, 5.8))
        for ax, (title, labels) in zip(axes, panels, strict=True):
            ax.imshow(_outline(rgb, labels), interpolation="nearest")
            ax.set_title(title, fontsize=16)
            ax.axis("off")
        fig.suptitle(f"{crop['dataset']} {crop['crop']}", fontsize=18, fontweight="bold")
        fig.text(
            0.01,
            0.01,
            "Preview: today's projection settings. Nuclei magenta, cells green.",
            fontsize=12,
            color=INK_2,
        )
        fig.tight_layout(rect=(0, 0.03, 1, 0.94))
        fig.savefig(out / f"montage_{key}.png", dpi=150)
        plt.close(fig)


def build_report(results: Path, data: Path, out: Path) -> None:
    from segmentation_benchmark.settings import build_settings

    out.mkdir(parents=True, exist_ok=True)
    settings = build_settings()
    df = load(results, settings)
    summary = summarise(df)
    summary.to_csv(out / "summary.csv", index=False)
    head, picks = headline(summary, settings)
    (out / "headline.json").write_text(json.dumps(head, indent=2) + "\n")

    _style()
    raw = summary[
        (summary["target"] == "cells") & (summary["scope"] == "raw") & (summary["dataset"] == "crossplatform")
    ]
    if not raw.empty:
        table = _level_table(raw.merge(settings.drop(columns=["target", "scope"]), on="index"))
        today_row = _level_table(
            settings.set_index("index").loc[[today_index(settings, "cells", "raw")]]
        ).iloc[0]
        n_total = int(((settings["target"] == "cells") & (settings["scope"] == "raw")).sum())
        n_found = int(table["index"].nunique())
        note = f"Incomplete: {n_found} of {n_total} settings" if n_found < n_total else ""
        means = plot_effects(table, today_row, out, note)
        plot_interaction(table, means, out, note)
    plot_platforms(df, picks, out)
    plot_montages(df, picks, data, results, out)
    print(f"report written to {out}")


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("--results", type=Path, required=True)
    p.add_argument("--data", type=Path, required=True)
    p.add_argument("--out", type=Path, required=True)
    a = p.parse_args()
    build_report(a.results, a.data, a.out)


if __name__ == "__main__":
    main()
