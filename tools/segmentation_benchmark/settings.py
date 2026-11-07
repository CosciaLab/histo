#!/usr/bin/env python3
"""Settings grid for the segmentation benchmark: one row per SLURM array task.

Rows 0-143 vary the channel projection and Cellpose thresholds on raw-channel datasets.
Rows 144-155 vary Cellpose on TissueNet and 156-167 on nuclei; both keep TODAY's projection.
Regenerate the committed CSV with: python settings.py --out settings.csv
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


def build_settings() -> pd.DataFrame:
    """The 168-row grid; the `index` column is the SLURM array task id."""
    rows = [
        ("cells", "raw", method, low, p_sigma, g_sigma, clip, flow, prob)
        for method, low, p_sigma, g_sigma, clip, (flow, prob) in itertools.product(
            ["max", "mean"], [1, 50], [0, 1, 2], GAUSSIAN_LEVELS, CLIP_LEVELS, THRESHOLD_LEVELS
        )
    ]
    for target, scope in [("cells", "tissuenet"), ("nuclei", "all")]:
        rows += [
            (
                target,
                scope,
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
    columns = [
        "target",
        "scope",
        "projection_method",
        "low_percentile",
        "projection_sigma",
        "gaussian_sigma",
        "clip_limit",
        "flow_threshold",
        "cellprob_threshold",
    ]
    df = pd.DataFrame(rows, columns=columns)
    df.insert(0, "index", range(len(df)))
    return df


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
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    build_settings().to_csv(args.out, index=False)


if __name__ == "__main__":
    main()
