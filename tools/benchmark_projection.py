#!/usr/bin/env python3
"""Benchmark channel projection settings for 2-channel Cellpose, without ground truth.

Runs a grid of projection and Cellpose settings on one crop of a SpatialData store, the
way the pipeline does: percentiles from bin/project_channels.py, then sopa's own Gaussian,
CLAHE and `cellpose_patch`. Run it in an environment with sopa and cellpose; cellpose < 4
gives `cyto3`, >= 4 gives Cellpose-SAM. Writes metrics.csv and an outline montage.

Metrics (higher is better unless noted):
  nuclei_in_cells   share of reference nuclei whose centroid falls inside a cell
  one_nucleus       share of cells holding exactly one nucleus centroid
  no_nucleus        share of cells holding none (fragments; lower is better)
  multi_nucleus     share holding two or more (merges; lower is better)
  coverage_<m>      share of marker m's Otsu-positive pixels inside cells
  coverage_min      the worst-covered marker, the lineage most likely missed
  covered           share of the crop inside any cell; coverage alone rewards cells that
                    swallow everything, so read it against this

None of these replaces looking at the montage: the outlines, not the numbers, decided
the defaults in docs/decisions.md.
"""

from __future__ import annotations

import argparse
import csv
import itertools
import sys
import time
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "bin"))

from project_channels import combine, percentile_bounds, rescale  # noqa: E402

PREVIEW_CROP = 400


def load(sdata_path: Path) -> tuple[Any, list[str]]:
    """Full-resolution image (lazy) and its channel names."""
    import spatialdata as sd

    sdata = sd.read_zarr(sdata_path)
    key = sdata.attrs.get("cell_segmentation_image") or next(iter(sdata.images))
    image = next(iter(sdata[key]["scale0"].values()))
    return image, [str(c) for c in image.c.values]


def bounds_for(image: Any, names: list[str], markers: list[str], low: float, high: float) -> dict[str, tuple]:
    """Per-marker (lo, hi) from the full image, as project_channels.py takes them."""
    import numpy as np

    out = {}
    for m in markers:
        b = percentile_bounds(np.asarray(image.data[names.index(m)]), low, high)
        if b is not None:
            out[m] = b
    return out


def project_crop(
    planes: dict[str, Any], bounds: dict[str, tuple], markers: list[str], method: str, sigma: float
):
    """One projected channel of the crop, as uint16."""
    import numpy as np
    from scipy.ndimage import gaussian_filter

    stack = []
    for m in markers:
        if m not in bounds:
            continue
        x = rescale(planes[m], *bounds[m])
        stack.append(gaussian_filter(x, sigma) if sigma > 0 else x)
    return (combine(np.stack(stack), method) * 65535 + 0.5).astype(np.uint16)


def sopa_preprocess(image: Any, gaussian_sigma: float, clip_limit: float) -> Any:
    """sopa.segmentation.stainings._run_patch, before the model."""
    import numpy as np
    from scipy.ndimage import gaussian_filter
    from skimage import exposure

    if gaussian_sigma > 0:
        image = np.stack([gaussian_filter(c, sigma=gaussian_sigma) for c in image])
    if clip_limit > 0:
        image = np.stack([exposure.equalize_adapthist(c, clip_limit=clip_limit) for c in image])
    return image


def segment(image: Any, n_channels: int, diameter: float, flow: float, cellprob: float, gpu: bool) -> Any:
    from sopa.segmentation.methods import cellpose_patch

    channels = ["cell", "nuclear"] if n_channels == 2 else ["nuclear"]
    method = cellpose_patch(
        diameter=diameter, channels=channels, gpu=gpu, flow_threshold=flow, cellprob_threshold=cellprob
    )
    return method(image)


def reference_nuclei(dna: Any, diameter: float, gpu: bool, cache: Path) -> Any:
    """Nuclear centroids from Cellpose 'nuclei' on the DNA channel, cached."""
    import numpy as np

    if cache.exists():
        return np.load(cache)
    from cellpose import models
    from skimage.measure import regionprops

    model = models.CellposeModel(gpu=gpu, model_type="nuclei")
    labels = model.eval(dna, channels=[0, 0], diameter=diameter)[0]
    cents = np.array([p.centroid for p in regionprops(labels)]).round().astype(int)
    np.save(cache, cents)
    return cents


def metrics(labels: Any, nuclei: Any, positives: dict[str, Any]) -> dict[str, float]:
    import numpy as np

    n_cells = int(labels.max())
    areas = np.bincount(labels.ravel())[1:]
    areas = areas[areas > 0]
    hit = labels[nuclei[:, 0], nuclei[:, 1]]
    # Cellpose labels run 1..n without gaps.
    per_cell = np.bincount(hit[hit > 0], minlength=n_cells + 1)[1:]
    out = {
        "n_cells": len(areas),
        "median_area": float(np.median(areas)) if len(areas) else 0.0,
        "nuclei_in_cells": float((hit > 0).mean()),
        "one_nucleus": float((per_cell == 1).mean()) if len(per_cell) else 0.0,
        "no_nucleus": float((per_cell == 0).mean()) if len(per_cell) else 0.0,
        "multi_nucleus": float((per_cell >= 2).mean()) if len(per_cell) else 0.0,
    }
    inside = labels > 0
    for m, pos in positives.items():
        out[f"coverage_{m}"] = float(inside[pos].mean())
    out["coverage_min"] = min(out[f"coverage_{m}"] for m in positives)
    out["coverage_mean"] = float(np.mean([out[f"coverage_{m}"] for m in positives]))
    out["covered"] = float(inside.mean())
    return out


def outline(rgb: Any, labels: Any) -> Any:
    from skimage.segmentation import find_boundaries

    out = rgb.copy()
    out[find_boundaries(labels, mode="inner")] = (255, 255, 0)
    return out


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--sdata", required=True, type=Path)
    ap.add_argument("--nuclear", required=True, help="nuclear marker, e.g. DNA_6")
    ap.add_argument(
        "--default-cell", required=True, help="comma-separated: the marker sheet's default cell set"
    )
    ap.add_argument("--curated-cell", required=True, help="comma-separated: a hand-picked cell set")
    ap.add_argument("--crop", required=True, help="y0,x0,size of the crop to segment")
    ap.add_argument("--diameter", type=float, required=True, help="cell diameter in pixels")
    ap.add_argument("--nuclear-diameter", type=float, required=True, help="nucleus diameter in pixels")
    ap.add_argument("--out", required=True, type=Path)
    ap.add_argument("--quick", action="store_true", help="only the settings worth a slow model")
    ap.add_argument("--gpu", action="store_true")
    args = ap.parse_args()

    import numpy as np
    from cellpose import version as cellpose_version
    from PIL import Image
    from scipy.ndimage import gaussian_filter
    from skimage.filters import threshold_otsu

    from project_channels import preview_rgb

    args.out.mkdir(parents=True, exist_ok=True)
    model_name = "cpsam" if int(cellpose_version.split(".")[0]) >= 4 else "cyto3"
    image, names = load(args.sdata)
    y0, x0, size = (int(v) for v in args.crop.split(","))
    crop = (slice(y0, y0 + size), slice(x0, x0 + size))

    sets = {"default": args.default_cell.split(","), "curated": args.curated_cell.split(",")}
    all_markers = sorted({args.nuclear, *sets["default"], *sets["curated"]})
    planes = {m: np.asarray(image.data[names.index(m)][crop]) for m in all_markers}

    nuclei = reference_nuclei(planes[args.nuclear], args.nuclear_diameter, args.gpu, args.out / "nuclei.npy")
    positives = {}
    for m in sets["default"]:
        x = gaussian_filter(planes[m].astype("float32"), 1)
        positives[m] = x > threshold_otsu(x)

    if args.quick:
        grid = [("max", 1, "default", 0.0, 0.4, 0.0), ("max", 50, "default", 0.0, 0.4, 0.0),
                ("mean", 1, "default", 0.0, 0.4, 0.0), ("max", 1, "curated", 0.0, 0.4, 0.0)]  # fmt: skip
    else:
        grid = list(
            itertools.product(
                ["max", "mean"], [1, 50], ["default", "curated"], [0.0, 0.2], [(0.4, 0.0), (2.0, -6.0)]
            )
        )
        grid = [(m, lo, s, c, f, p) for m, lo, s, c, (f, p) in grid]
    baselines = (
        [(0.4, 0.0, 0.0)] if args.quick else list(itertools.product([0.4, 2.0], [0.0, -6.0], [0.0, 0.2]))
    )
    baselines = [b for b in baselines if (b[0], b[1]) in {(0.4, 0.0), (2.0, -6.0)}]

    rows, montage = [], []
    cache = {}
    for flow, cellprob, clip in baselines:
        t = time.time()
        dna = planes[args.nuclear][None]
        labels = segment(sopa_preprocess(dna, 1, clip), 1, args.diameter, flow, cellprob, args.gpu)
        config = f"dna_only_clahe{clip}_flow{flow}_prob{cellprob}"
        row = {"model": model_name, "config": config, "method": "", "low": "", "cells": "",
               "clip_limit": clip, "flow": flow, "cellprob": cellprob, "seconds": round(time.time() - t, 1)}  # fmt: skip
        rows.append(row | metrics(labels, nuclei, positives))
        print(rows[-1], flush=True)

    for method, low, cell_set, clip, flow, cellprob in grid:
        t = time.time()
        key = (method, low, cell_set)
        if key not in cache:
            b = bounds_for(image, names, [args.nuclear, *sets[cell_set]], low, 99.9)
            cache[key] = np.stack(
                [
                    project_crop(planes, b, sets[cell_set], method, 1.0),
                    project_crop(planes, b, [args.nuclear], method, 1.0),
                ]
            )  # sopa's order: cell, then nuclear
        proj = cache[key]
        labels = segment(sopa_preprocess(proj, 1, clip), 2, args.diameter, flow, cellprob, args.gpu)
        config = f"{method}_low{low}_{cell_set}_clahe{clip}_flow{flow}_prob{cellprob}"
        row = {"model": model_name, "config": config, "method": method, "low": low, "cells": cell_set,
               "clip_limit": clip, "flow": flow, "cellprob": cellprob, "seconds": round(time.time() - t, 1)}  # fmt: skip
        rows.append(row | metrics(labels, nuclei, positives))
        print(rows[-1], flush=True)
        p = slice(0, PREVIEW_CROP)
        rgb = preview_rgb(proj[1][p, p] / 65535, proj[0][p, p] / 65535)
        montage.append((config, outline(rgb, labels[p, p])))

    with (args.out / f"metrics_{model_name}.csv").open("w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=list(rows[-1]))
        w.writeheader()
        w.writerows(rows)

    cols = 4
    h = PREVIEW_CROP
    sheet = np.zeros((h * -(-len(montage) // cols), h * cols, 3), dtype=np.uint8)
    for i, (_c, tile) in enumerate(montage):
        r, c = divmod(i, cols)
        sheet[r * h : (r + 1) * h, c * h : (c + 1) * h] = tile
    Image.fromarray(sheet).save(args.out / f"montage_{model_name}.png")
    (args.out / f"montage_{model_name}.txt").write_text("\n".join(c for c, _ in montage) + "\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
