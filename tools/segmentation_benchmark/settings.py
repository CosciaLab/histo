#!/usr/bin/env python3
"""Settings grid for the segmentation benchmark: one row per SLURM array task.

Round 1 (settings.csv): rows 0-143 vary the channel projection and Cellpose thresholds on
raw-channel datasets; 144-155 vary Cellpose on TissueNet and 156-167 on nuclei, both with
TODAY's projection.
Round 2 (settings_round2.csv): round 1's best preprocessing (no smoothing, no CLAHE), a
7 x 8 threshold grid per block, three cell channel selections, and CLAHE 0.01 at 9 pairs.
Regenerate: python settings.py --grid round1 --out settings.csv (round2: settings_round2.csv)
"""

from __future__ import annotations

import argparse
import itertools
from pathlib import Path

import pandas as pd

TODAY = {
    "projection_method": "max",
    "low_percentile": 1,
    "projection_sigma": 1,
    "gaussian_sigma": 1,
    "clip_limit": 0.2,
    "flow_threshold": 2,
    "cellprob_threshold": -6,
}

GAUSSIAN_LEVELS = [0, 1, 2]
CLIP_LEVELS = [0, 0.2]
THRESHOLD_LEVELS = [(2, -6), (0.4, 0)]  # (flow_threshold, cellprob_threshold) pairs

ROUND2_BASE = {"projection_method": "max", "low_percentile": 1, "projection_sigma": 0, "gaussian_sigma": 0}
FLOW_LEVELS = [0.2, 0.4, 0.6, 0.8, 1.0, 1.5, 2.0]
CELLPROB_LEVELS = [-6, -4, -3, -2, -1, 0, 1, 2]
CLAHE_PAIRS = list(itertools.product([0.4, 1.0, 2.0], [-6, -2, 0]))
BLOCKS = [("cells", "raw"), ("cells", "tissuenet"), ("nuclei", "all")]
COLUMNS = [
    "target",
    "scope",
    "cell_channels",
    "projection_method",
    "low_percentile",
    "projection_sigma",
    "gaussian_sigma",
    "clip_limit",
    "flow_threshold",
    "cellprob_threshold",
]


def build_settings() -> pd.DataFrame:
    """The 168-row grid; the `index` column is the SLURM array task id."""
    rows = [
        ("cells", "raw", "all", method, low, p_sigma, g_sigma, clip, flow, prob)
        for method, low, p_sigma, g_sigma, clip, (flow, prob) in itertools.product(
            ["max", "mean"], [1, 50], [0, 1, 2], GAUSSIAN_LEVELS, CLIP_LEVELS, THRESHOLD_LEVELS
        )
    ]
    for target, scope in [("cells", "tissuenet"), ("nuclei", "all")]:
        rows += [
            (
                target,
                scope,
                "all",
                TODAY["projection_method"],
                TODAY["low_percentile"],
                TODAY["projection_sigma"],
                g_sigma,
                clip,
                flow,
                prob,
            )
            for g_sigma, clip, (flow, prob) in itertools.product(
                GAUSSIAN_LEVELS, CLIP_LEVELS, THRESHOLD_LEVELS
            )
        ]
    return _frame(rows)


def build_round2() -> pd.DataFrame:
    """The 307-row round-2 grid: thresholds on round 1's best preprocessing."""
    pairs = list(itertools.product(FLOW_LEVELS, CELLPROB_LEVELS))
    blocks = [("cells", "raw", sel, 0.0, pairs) for sel in ("markers", "all", "membrane")]
    blocks += [("cells", "tissuenet", "markers", 0.0, pairs), ("nuclei", "all", "markers", 0.0, pairs)]
    blocks += [(t, sc, "markers", 0.01, CLAHE_PAIRS) for t, sc in BLOCKS]
    base = ROUND2_BASE
    rows = [
        (t, sc, sel, base["projection_method"], base["low_percentile"], base["projection_sigma"],
         base["gaussian_sigma"], clip, flow, prob)
        for t, sc, sel, clip, block_pairs in blocks
        for flow, prob in block_pairs
    ]  # fmt: skip
    return _frame(rows)


def _frame(rows: list[tuple]) -> pd.DataFrame:
    df = pd.DataFrame(rows, columns=COLUMNS)
    df.insert(0, "index", range(len(df)))
    return df


GRIDS = {"round1": build_settings, "round2": build_round2}


def today_index(settings: pd.DataFrame, target: str, scope: str) -> int:
    """Array index of the TODAY row within one (target, scope) block."""
    match = settings[(settings["target"] == target) & (settings["scope"] == scope)]
    for key, value in TODAY.items():
        match = match[match[key] == value]
    if len(match) != 1:
        raise ValueError(f"TODAY must occur exactly once in block {target}/{scope}, found {len(match)}")
    return int(match["index"].iloc[0])


def main() -> None:
    parser = argparse.ArgumentParser(description="Write the benchmark settings grid as CSV.")
    parser.add_argument("--grid", choices=GRIDS, default="round1")
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    GRIDS[args.grid]().to_csv(args.out, index=False)


if __name__ == "__main__":
    main()
