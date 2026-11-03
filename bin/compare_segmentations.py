#!/usr/bin/env python3
"""Compare the Cellpose and InstanSeg cells of one store: counts, areas, one-to-one matches, crops.

Reads shapes/{method}_cells and the image named by the store's `cell_segmentation_image`
attribute; never writes to the store. Writes {prefix}_comparison.json and
{prefix}_comparison.html. A cell matches when it pairs one-to-one with a cell of the other
method at IoU >= MIN_IOU; pairs are taken greedily, highest IoU first, so each cell is used once
even where cells of one method overlap.

JSON keys:
  sample      the prefix (meta.id)
  image       image element the crops are drawn from
  channel     channel shown in grey in the crops
  min_iou     IoU a pair needs to match
  n_matched   pairs matched one-to-one
  methods.{m} n_cells; median_area_px2; match_share, the share of m's cells matched in the
              other method. Both null when m has no cells.
  crops[]     density_band, x0, y0, width, height, n_cells (both methods), n_outlines.{m}
Areas are px² only: the store records no pixel size.
"""

from __future__ import annotations

import argparse
import json
import math
import sys
import tempfile
from pathlib import Path
from typing import Any


METHODS = ("cellpose", "instanseg")
MIN_IOU = 0.5
# Okabe-Ito orange and sky blue: distinct from each other and from grey under colour-vision deficiencies.
COLOURS = {"cellpose": (230, 159, 0), "instanseg": (86, 180, 233)}
NUCLEAR_HINTS = ("dapi", "hoechst", "dna", "nuc")


def grey_channel(names: list[str]) -> tuple[int, str]:
    """The first channel whose name looks nuclear, else channel 0."""
    for i, name in enumerate(names):
        if any(hint in name.lower() for hint in NUCLEAR_HINTS):
            return i, name
    return 0, names[0]


def _geoms(frame: Any) -> Any:
    """Geometries as an array, invalid ones made valid (polygonal parts only); None where empty."""
    import numpy as np
    import shapely
    from link_compartments import polygonal

    geoms = np.asarray(frame.geometry.array, dtype=object)
    # An invalid polygon (e.g. self-intersecting) makes GEOS overlays raise.
    invalid = ~shapely.is_valid(geoms) & ~shapely.is_missing(geoms)
    geoms[invalid] = [polygonal(g) for g in shapely.make_valid(geoms[invalid])]
    geoms[np.array([g is None or g.is_empty for g in geoms], dtype=bool)] = None
    return geoms


def n_matched(a: Any, b: Any, min_iou: float = MIN_IOU) -> int:
    """Pairs of a and b matched one-to-one at IoU >= min_iou, highest IoU first."""
    import numpy as np
    import shapely

    if len(a) == 0 or len(b) == 0:
        return 0
    ga, gb = _geoms(a), _geoms(b)
    # STRtree: only touching pairs, never all pairs (whole slides have ~1e6 cells).
    ia, ib = shapely.STRtree(gb).query(ga, predicate="intersects")
    inter = shapely.area(shapely.intersection(ga[ia], gb[ib]))
    union = shapely.area(ga[ia]) + shapely.area(gb[ib]) - inter
    # Rounding keeps float noise from breaking the >= min_iou bound at exactly 0.5.
    iou = np.round(np.divide(inter, union, out=np.zeros_like(inter), where=union > 0), 9)
    keep = iou >= min_iou
    ia, ib, iou = ia[keep], ib[keep], iou[keep]
    used_a, used_b = set(), set()
    for k in np.lexsort((ib, ia, -iou)):
        if ia[k] not in used_a and ib[k] not in used_b:
            used_a.add(ia[k])
            used_b.add(ib[k])
    return len(used_a)


def match_share(a: Any, b: Any, min_iou: float = MIN_IOU) -> float:
    """Share of a's cells with a one-to-one match in b at IoU >= min_iou; NaN when a is empty."""
    return n_matched(a, b, min_iou) / len(a) if len(a) else math.nan


def summarise(frames: dict[str, Any], min_iou: float = MIN_IOU) -> dict[str, Any]:
    """Counts, median areas and both match shares; JSON-ready, with null for undefined values."""
    import numpy as np
    import shapely

    if len(frames) != 2:
        raise ValueError(f"comparison needs two methods, got {sorted(frames)}")
    (ma, a), (mb, b) = frames.items()
    matched = n_matched(a, b, min_iou)
    methods = {}
    for name, frame in ((ma, a), (mb, b)):
        n = len(frame)
        areas = shapely.area(_geoms(frame)).astype(float)
        areas = areas[~np.isnan(areas)]  # empty geometries have no area
        methods[name] = {
            "n_cells": n,
            "median_area_px2": float(np.median(areas)) if len(areas) else None,
            "match_share": matched / n if n else None,
        }
    return {"min_iou": min_iou, "n_matched": matched, "methods": methods}


def centroids(frame: Any) -> Any:
    """(n, 2) x, y centroids of the non-empty geometries."""
    import numpy as np
    import shapely

    geoms = _geoms(frame)
    geoms = geoms[[g is not None for g in geoms]]
    return shapely.get_coordinates(shapely.centroid(geoms)) if len(geoms) else np.zeros((0, 2))


def render_crops(
    sdata_path: Path,
    element: str,
    channel_index: int,
    frames: dict[str, Any],
    out_dir: Path,
    window: int,
) -> list[dict[str, Any]]:
    """The densest, median and sparsest windows, both outlines over one grey channel; one PNG each."""
    import numpy as np
    import zarr
    from PIL import Image
    from qc_images import composite, draw_outlines, pick_windows, stretch, window_counts
    from shapely.geometry import box

    image = zarr.open_array(str(sdata_path / "images" / element / "s0"), mode="r")
    _, height, width = image.shape
    points = np.concatenate([centroids(f) for f in frames.values()])
    picks = pick_windows(window_counts(points, (height, width), window), 3)

    # Only the windows are read; one pair of display bounds for all, so the crops are comparable.
    planes = []
    for pick in picks:
        x0, y0 = pick["grid_x"] * window, pick["grid_y"] * window
        planes.append((pick, x0, y0, np.asarray(image[channel_index, y0 : y0 + window, x0 : x0 + window])))
    if not planes:
        return []
    pooled = np.concatenate([p[3].ravel() for p in planes])
    lo, hi = float(np.percentile(pooled, 1.0)), float(np.percentile(pooled, 99.5))

    out = []
    for pick, x0, y0, plane in planes:
        img = Image.fromarray(composite([(stretch(plane, lo, hi), (1.0, 1.0, 1.0))]), mode="RGB")
        frame_box = box(x0, y0, x0 + plane.shape[1], y0 + plane.shape[0])
        drawn = {}
        for name, frame in frames.items():
            hits = frame.sindex.query(frame_box) if len(frame) else []
            drawn[name] = draw_outlines(img, frame.geometry.iloc[hits], x0, y0, COLOURS[name])
        file = f"crop_{pick['density_band']}.png"
        img.save(out_dir / file, optimize=True)
        out.append(
            {
                "density_band": pick["density_band"],
                "x0": int(x0),
                "y0": int(y0),
                "width": int(plane.shape[1]),
                "height": int(plane.shape[0]),
                "n_cells": pick["n_cells"],
                "n_outlines": drawn,
                "file": file,
            }
        )
    return out


def _pct(share: float | None) -> str:
    return "–" if share is None else f"{share * 100:.1f}%"


def _median(area: float | None) -> str:
    return "–" if area is None else f"{area:,.0f} px²"


def build(summary: dict[str, Any], asset_dir: Path) -> str:
    """One self-contained page, styled as the QC report."""
    from qc_report import JS, css, esc, figure, inline_png, table, thousands, tile

    methods = summary["methods"]
    (ma, a), (mb, b) = methods.items()
    tiles = [
        tile(f"{name} cells", thousands(m["n_cells"]), "median " + _median(m["median_area_px2"]))
        for name, m in methods.items()
    ] + [
        tile(f"{ma} matched", _pct(a["match_share"]), f"of its cells, in {mb}"),
        tile(f"{mb} matched", _pct(b["match_share"]), f"of its cells, in {ma}"),
    ]
    rows = [
        [
            f'<span style="color:rgb{COLOURS.get(name, (0, 0, 0))}">&#9632;</span> {esc(name)}',
            thousands(m["n_cells"]),
            "–" if m["median_area_px2"] is None else f"{m['median_area_px2']:,.0f}",
            _pct(m["match_share"]),
        ]
        for name, m in methods.items()
    ]
    figs = [
        figure(
            inline_png(asset_dir / c["file"]),
            f"{esc(c['density_band'])} &middot; {thousands(c['n_cells'])} cells, both methods",
            f"({c['x0']:,}, {c['y0']:,}) &middot; {c['width']}&times;{c['height']} px &middot; "
            + " &middot; ".join(f"{esc(k)} {v}" for k, v in c["n_outlines"].items())
            + " outlines",
        )
        for c in summary["crops"]
    ]
    crops = (
        f"""
<section>
  <h2>Both outlines on the same crops</h2>
  <p class="note"><strong>{esc(summary["channel"])}</strong> in grey, {esc(ma)} in
  <span style="color:rgb{COLOURS[ma]}"><strong>orange</strong></span> and {esc(mb)} in
  <span style="color:rgb{COLOURS[mb]}"><strong>blue</strong></span>, drawn in that order, so
  where they agree blue lies on top. The densest, median and sparsest windows by cell count;
  one display range for all three. Click a crop to enlarge it.</p>
  <div class="gallery">{"".join(figs)}</div>
</section>"""
        if figs
        else ""
    )
    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Segmentation comparison &middot; {esc(summary["sample"])}</title>
<style>{css()}</style>
</head>
<body>
<div id="tip" role="status" aria-live="polite"></div>
<div id="lightbox" role="dialog" aria-label="Enlarged image">
  <button id="lbclose" type="button" aria-label="Close">&times;</button>
  <img alt=""><figcaption></figcaption>
</div>
<div class="wrap">
<header>
  <div>
    <h1>Segmentation comparison &middot; {esc(summary["sample"])}</h1>
    <div class="sub">{esc(ma)} and {esc(mb)} cells on image element
      <strong>{esc(summary["image"])}</strong></div>
  </div>
  <button id="theme" type="button">Toggle theme</button>
</header>

<section>
  <div class="herolabel">Cells matched one-to-one</div>
  <div class="hero">{esc(thousands(summary["n_matched"]))}</div>
  <div class="tiles">{"".join(tiles)}</div>
</section>

<section>
  <h2>Counts, areas and matches</h2>
  <p class="note">A cell is matched when it pairs with one cell of the other method at
  IoU &ge; {summary["min_iou"]:g}; each cell is used once, highest IoU first. A second
  opinion, not a ground truth: neither method is the reference. Areas in px&sup2;.</p>
  {table(["Method", "Cells", "Median area (px²)", "Matched in the other"], rows)}
</section>
{crops}
<footer>Rendered by <code>bin/compare_segmentations.py</code>; the numbers are in
<code>{esc(summary["sample"])}_comparison.json</code>. Self-contained: no external scripts,
fonts or network access.</footer>
</div>
<script>{JS}</script>
</body>
</html>
"""


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--sdata", required=True, type=Path, help="SpatialData .zarr store, read only")
    ap.add_argument("--prefix", required=True, help="output file prefix, the sample id")
    ap.add_argument("--window", type=int, default=500, help="crop size in pixels (default: 500)")
    args = ap.parse_args()

    from qc_images import read_boundaries
    from qc_metrics import image_channel_labels, segmentation_image_element

    element = segmentation_image_element(args.sdata)
    channel_index, channel = grey_channel(image_channel_labels(args.sdata, element))
    frames = {m: read_boundaries(args.sdata, f"{m}_cells") for m in METHODS}

    summary = {"sample": args.prefix, "image": element, "channel": channel, **summarise(frames)}
    with tempfile.TemporaryDirectory() as tmp:
        summary["crops"] = render_crops(args.sdata, element, channel_index, frames, Path(tmp), args.window)
        page = build(summary, Path(tmp))
    for crop in summary["crops"]:
        del crop["file"]

    Path(f"{args.prefix}_comparison.json").write_text(json.dumps(summary, indent=2, allow_nan=False) + "\n")
    Path(f"{args.prefix}_comparison.html").write_text(page)
    for name, m in summary["methods"].items():
        print(f"[compare] {name}: {m['n_cells']:,} cells, {_pct(m['match_share'])} matched")
    print(f"[compare] {len(summary['crops'])} crops of {args.window} px from {element}::{channel}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
