#!/usr/bin/env python3
"""Project many mIF channels into a nuclear and a cell channel for 2-channel segmentation.

`project` adds an image element `<source>_projected` with channels `nuclear` and `cell`
and points sopa's `cell_segmentation_image` at it, so patchify, segmentation and resolve
use it. `drop` deletes it and restores the attribute, so AGGREGATE quantifies the full
image and the published store has one image element, as without projection.

Each channel is rescaled to [0, 1] by its own percentiles, optionally smoothed, then the
group is combined by max or mean. Written as uint16: sopa refuses float images.
"""

from __future__ import annotations

import argparse
import json
import math
import sys
from pathlib import Path
from typing import Any

from qc_metrics import read_marker_cycles

OUTPUT_CHANNELS = ("nuclear", "cell")
METHODS = ("max", "mean")
SOURCE_ATTR = "histo_projection_source"
SEGMENTATION_ATTR = "cell_segmentation_image"  # sopa's SopaAttrs.CELL_SEGMENTATION
TISSUE_KEY = "region_of_interest"  # written by sopa's tissue segmentation
# Percentiles are taken on the coarsest pyramid level at least this long, so the cost is
# fixed whatever the slide size.
PERCENTILE_MIN_SIDE = 2000
PREVIEW_MAX_SIDE = 1500
UINT16_MAX = 65535


def resolve_groups(rows: list[dict[str, Any]]) -> tuple[dict[str, list[str]], str]:
    """Marker names for each output channel, in channel order, and how they were chosen.

    Any value in the `segmentation` column makes that column the whole selection.
    Otherwise: the first `dna` channel (the Ashlar reference cycle), and every `marker`
    whose compartment includes membrane or cytoplasm.
    """
    if any(r.get("segmentation") for r in rows):
        groups = {
            ch: [r["marker_name"] for r in rows if r.get("segmentation") == ch] for ch in OUTPUT_CHANNELS
        }
        how = "segmentation column"
    else:
        dna = [r["marker_name"] for r in rows if r.get("channel_role") == "dna"]
        cell = [
            r["marker_name"]
            for r in rows
            if r.get("channel_role") == "marker"
            and {"membrane", "cytoplasm"} & set((r.get("channel_compartment") or "").split("+"))
        ]
        groups = {"nuclear": dna[:1], "cell": cell}
        how = "first dna channel; markers with channel_compartment membrane or cytoplasm"

    for ch, names in groups.items():
        if not names:
            raise ValueError(
                f"no channels for '{ch}' (selected by {how}). Set the marker sheet's "
                f"segmentation column to 'nuclear' or 'cell' on the channels to use."
            )
    return groups, how


def percentile_bounds(values: Any, low: float, high: float) -> tuple[float, float] | None:
    """(lo, hi) intensity bounds, or None for a channel too flat to rescale.

    Exact zeros are left out: Ashlar pads unregistered areas with them, and counting them
    puts the floor below the real background.
    """
    import numpy as np

    values = np.asarray(values)
    values = values[values > 0]
    if values.size == 0:
        return None
    lo, hi = (float(v) for v in np.percentile(values, [low, high]))
    return (lo, hi) if hi > lo else None


def rescale(x: Any, lo: float, hi: float) -> Any:
    """Map lo..hi to 0..1 as float32, clipped. Works on numpy and dask arrays."""
    return ((x.astype("float32") - lo) / (hi - lo)).clip(0, 1)


def combine(stack: Any, method: str) -> Any:
    """Collapse the channel axis (0) of a rescaled stack."""
    if method == "max":
        return stack.max(axis=0)
    if method == "mean":
        return stack.mean(axis=0)
    raise ValueError(f"unknown method '{method}'; expected one of {METHODS}")


def scale_factors_of(shapes: list[tuple[int, int]]) -> list[int]:
    """Per-level downscale factors of a pyramid, from its (y, x) shapes."""
    return [round(a[0] / b[0]) for a, b in zip(shapes, shapes[1:], strict=False)]


def coarse_level(shapes: list[tuple[int, int]], min_side: int = PERCENTILE_MIN_SIDE) -> int:
    """Index of the coarsest level whose long side is still at least `min_side`."""
    ok = [i for i, s in enumerate(shapes) if max(s) >= min_side]
    return ok[-1] if ok else 0


def preview_rgb(nuclear: Any, cell: Any) -> Any:
    """uint8 RGB: nuclear magenta, cell green, which stays legible to red-green colour blindness."""
    import numpy as np

    n = (np.asarray(nuclear) * 255).astype(np.uint8)
    c = (np.asarray(cell) * 255).astype(np.uint8)
    return np.stack([n, c, n], axis=-1)


def _levels(tree: Any) -> list[Any]:
    """The DataArray of each pyramid level, finest first; a single-scale image is its own level."""
    if not hasattr(tree, "children"):
        return [tree]
    return [
        next(iter(tree[k].values())) for k in sorted(tree.keys(), key=lambda k: int(k.removeprefix("scale")))
    ]


def _tissue_mask(sdata: Any, image: Any, shape: tuple[int, int], factor: float) -> Any | None:
    """Tissue mask at a pyramid level, or None without tissue segmentation."""
    import numpy as np
    from skimage.draw import polygon as fill
    from spatialdata.transformations import Identity, get_transformation

    if TISSUE_KEY not in sdata.shapes:
        return None
    # Polygons are in global coordinates, which equal scale0 pixels only under Identity.
    if not isinstance(get_transformation(image), Identity):
        print(f"[project_channels] image transformation is not Identity; ignoring {TISSUE_KEY}")
        return None

    mask = np.zeros(shape, dtype=bool)
    for geom in sdata.shapes[TISSUE_KEY].geometry:
        for poly in getattr(geom, "geoms", [geom]):
            x, y = np.asarray(poly.exterior.coords).T / factor
            rr, cc = fill(y, x, shape)
            mask[rr, cc] = True
    return mask if mask.any() else None


def project(
    sdata_path: Path,
    markers: Path,
    method: str,
    low: float,
    high: float,
    sigma: float,
    prefix: str,
) -> dict[str, Any]:
    """Write the projected element, point segmentation at it, and return the summary."""
    import dask.array as da
    import numpy as np
    import spatialdata as sd
    from PIL import Image
    from scipy.ndimage import gaussian_filter
    from spatialdata.models import Image2DModel
    from spatialdata.transformations import get_transformation

    if method not in METHODS:
        raise ValueError(f"unknown method '{method}'; expected one of {METHODS}")
    groups, how = resolve_groups(read_marker_cycles(markers))

    sdata = sd.read_zarr(sdata_path)
    # A retried task meets the store it already mutated, so the source is read back.
    source = sdata.attrs.get(SOURCE_ATTR) or sdata.attrs.get(SEGMENTATION_ATTR)
    if source is None:
        if len(sdata.images) != 1:
            raise ValueError(f"cannot tell the source image apart: {sorted(sdata.images)}")
        source = next(iter(sdata.images))
    target = f"{source}_projected"

    levels = _levels(sdata[source])
    full = levels[0]
    shapes = [tuple(level.shape[1:]) for level in levels]
    names = [str(c) for c in full.c.values]
    missing = sorted({m for g in groups.values() for m in g} - set(names))
    if missing:
        raise ValueError(f"marker sheet selects channels the image does not have: {missing}. Image: {names}")

    k = coarse_level(shapes)
    coarse = levels[k]
    factor = shapes[0][0] / shapes[k][0]
    mask = _tissue_mask(sdata, full, shapes[k], factor)

    summary: dict[str, Any] = {
        "source_element": source,
        "element": target,
        "selected_by": how,
        "method": method,
        "low_percentile": low,
        "high_percentile": high,
        "sigma": sigma,
        "percentile_level": k,
        "tissue_masked": mask is not None,
        "channels": {},
        "dropped_constant": [],
    }
    full_planes, preview_planes = [], []
    for ch in OUTPUT_CHANNELS:
        stack, small, used = [], [], []
        for name in groups[ch]:
            i = names.index(name)
            plane = np.asarray(coarse.data[i])
            bounds = percentile_bounds(plane[mask] if mask is not None else plane, low, high)
            if bounds is None:
                print(f"[project_channels] {name}: constant within the sampled area, left out")
                summary["dropped_constant"].append(name)
                continue
            lo, hi = bounds
            x = rescale(full.data[i], lo, hi)
            if sigma > 0:
                x = x.map_overlap(
                    gaussian_filter, depth=math.ceil(4 * sigma), boundary="reflect", sigma=sigma
                )
            stack.append(x)
            small.append(rescale(plane, lo, hi))
            used.append({"marker": name, "lo": lo, "hi": hi})
        if not stack:
            raise ValueError(f"every channel selected for '{ch}' is constant: {groups[ch]}")
        summary["channels"][ch] = used
        full_planes.append(combine(da.stack(stack), method))
        preview_planes.append(combine(np.stack(small), method))

    out = (da.stack(full_planes) * UINT16_MAX + 0.5).astype("uint16")
    element = Image2DModel.parse(
        out,
        dims=("c", "y", "x"),
        c_coords=list(OUTPUT_CHANNELS),
        transformations=get_transformation(full, get_all=True),
        scale_factors=scale_factors_of(shapes) or None,
        chunks=full.data.chunksize,
    )

    if target in sdata.images:
        del sdata[target]
        sdata.delete_element_from_disk(target)
    sdata[target] = element
    sdata.write_element(target)
    sdata.attrs[SOURCE_ATTR] = source
    sdata.attrs[SEGMENTATION_ATTR] = target
    sdata.write_attrs()

    step = max(1, math.ceil(max(shapes[k]) / PREVIEW_MAX_SIDE))
    rgb = preview_rgb(*(p[::step, ::step] for p in preview_planes))
    Image.fromarray(rgb).save(f"{prefix}_projection.png")
    Path(f"{prefix}_projection.json").write_text(json.dumps(summary, indent=2) + "\n")

    print(f"[project_channels] {sdata_path} :: {source} -> {target} ({method}, selected by {how})")
    for ch in OUTPUT_CHANNELS:
        for c in summary["channels"][ch]:
            print(f"  {ch:<8} {c['marker']:<24} lo={c['lo']:.1f} hi={c['hi']:.1f}")
    return summary


def drop(sdata_path: Path) -> None:
    """Delete the projected element and point segmentation back at the source image."""
    import spatialdata as sd

    sdata = sd.read_zarr(sdata_path)
    source = sdata.attrs.get(SOURCE_ATTR)
    if source is None:
        raise ValueError(f"{sdata_path} has no projection to drop (no '{SOURCE_ATTR}' attribute)")
    target = f"{source}_projected"

    # The in-memory element must go first: spatialdata refuses to delete backing files.
    if target in sdata.images:
        del sdata[target]
        sdata.delete_element_from_disk(target)
    sdata.attrs[SEGMENTATION_ATTR] = source
    del sdata.attrs[SOURCE_ATTR]
    sdata.write_attrs()
    print(f"[project_channels] {sdata_path} :: dropped {target}; segmentation image is {source} again")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="command", required=True)

    p = sub.add_parser("project", help="add the projected element")
    p.add_argument("--sdata", required=True, type=Path, help="SpatialData .zarr store")
    p.add_argument("--markers", required=True, type=Path, help="marker sheet CSV")
    p.add_argument("--prefix", required=True, help="file name prefix for the PNG and JSON")
    p.add_argument("--method", choices=METHODS, default="max", help="how a group is combined (default: max)")
    p.add_argument("--low-percentile", type=float, default=1.0, help="maps to 0 (default: 1)")
    p.add_argument("--high-percentile", type=float, default=99.9, help="maps to 1 (default: 99.9)")
    p.add_argument(
        "--sigma", type=float, default=1.0, help="Gaussian sigma in pixels, 0 for none (default: 1)"
    )

    d = sub.add_parser("drop", help="delete the projected element")
    d.add_argument("--sdata", required=True, type=Path, help="SpatialData .zarr store")

    args = ap.parse_args()
    if args.command == "project":
        if not 0 <= args.low_percentile < args.high_percentile <= 100:
            ap.error("need 0 <= --low-percentile < --high-percentile <= 100")
        project(
            args.sdata,
            args.markers,
            method=args.method,
            low=args.low_percentile,
            high=args.high_percentile,
            sigma=args.sigma,
            prefix=args.prefix,
        )
    else:
        drop(args.sdata)
    return 0


if __name__ == "__main__":
    sys.exit(main())
