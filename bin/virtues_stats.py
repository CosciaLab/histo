#!/usr/bin/env python3
"""VirTues model scale and slide statistics; no torch, so it runs in the sopa image.

Model pixel k covers image interval [k / pixel_size, (k + 1) / pixel_size) at 1 um/px, so
windows are resampled on demand and never written as a temporary image.
"""

import argparse
import json
import math
import sys
from pathlib import Path

import numpy as np

MODEL_UM_PER_PX = 1.0
QUANTILE = 0.99
N_BINS = 65536  # uint16 values
STATS_FORMAT = 1
TISSUE_KEY = "region_of_interest"  # written by sopa's tissue segmentation


def model_shape(image_yx, pixel_size):
    """Model grid (rows, cols) for an image of (y, x) pixels."""
    return tuple(int(math.floor(n * pixel_size)) for n in image_yx)


def _axis_weights(start, stop, pixel_size, n_image):
    """Source indices and area weights, both (stop - start, taps), for model pixels start..stop-1."""
    taps = math.ceil(1 / pixel_size) + 1
    k = np.arange(start, stop, dtype=np.float64)
    lo, hi = k / pixel_size, (k + 1) / pixel_size
    j = np.floor(lo).astype(np.int64)[:, None] + np.arange(taps)[None, :]
    overlap = np.minimum(j + 1, hi[:, None]) - np.maximum(j, lo[:, None])
    weights = np.clip(overlap, 0, None) * pixel_size
    weights[j >= n_image] = 0.0
    return np.minimum(j, n_image - 1), weights


def resample_window(image, channel, y0, y1, x0, x1, pixel_size):
    """Area-averaged model window, float32 (y1 - y0, x1 - x0); reads only the pixels it needs."""
    _, h, w = image.shape
    if pixel_size == 1.0:
        return np.asarray(image[channel, y0:y1, x0:x1]).astype(np.float32)
    rows, wr = _axis_weights(y0, y1, pixel_size, h)
    cols, wc = _axis_weights(x0, x1, pixel_size, w)
    ra, rb, ca, cb = rows.min(), rows.max() + 1, cols.min(), cols.max() + 1
    block = np.asarray(image[channel, ra:rb, ca:cb]).astype(np.float64)
    # explicit fixed-order sums, not a matrix product, so a value never depends on the window shape
    tmp = np.zeros((y1 - y0, cb - ca))
    for t in range(rows.shape[1]):
        tmp += block[rows[:, t] - ra, :] * wr[:, t, None]
    out = np.zeros((y1 - y0, x1 - x0))
    for t in range(cols.shape[1]):
        out += tmp[:, cols[:, t] - ca] * wc[None, :, t]
    return out.astype(np.float32)


def tissue_mask(polygons, y0, y1, x0, x1, pixel_size):
    """True where a model pixel's centre, in image coordinates, lies inside a polygon."""
    import shapely

    xs = (np.arange(x0, x1) + 0.5) / pixel_size
    ys = (np.arange(y0, y1) + 0.5) / pixel_size
    gx, gy = np.meshgrid(xs, ys)
    mask = np.zeros(gx.shape, dtype=bool)
    for poly in polygons:
        mask |= shapely.contains_xy(poly, gx, gy)
    return mask


def to_image_pixels(shapes, image):
    """A shapes element's geometries in the image's pixel coordinates, in row order.

    sopa's tissue() keeps the ROI in its coarsest level's pixels, with a scale to global.
    """
    import shapely
    from spatialdata.transformations import get_transformation

    from_shapes = get_transformation(shapes, get_all=True)
    from_image = get_transformation(image, get_all=True)
    shared = sorted(set(from_shapes) & set(from_image), key=lambda cs: cs != "global")  # global first
    if not shared:
        raise ValueError(
            f"shapes and image share no coordinate system: {sorted(from_shapes)}, {sorted(from_image)}"
        )
    xy = ("x", "y")
    shapes_to_cs = from_shapes[shared[0]].to_affine_matrix(xy, xy)
    image_to_cs = from_image[shared[0]].to_affine_matrix(xy, xy)
    m = np.linalg.inv(image_to_cs) @ shapes_to_cs  # shape px -> coordinate system -> image px
    geoms = np.asarray(shapes.geometry, dtype=object)
    if np.array_equal(m, np.eye(3)):
        return list(geoms)  # untouched, so coordinates stay bit-identical
    return list(shapely.transform(geoms, lambda c: c @ m[:2, :2].T + m[:2, 2]))


def histogram(image, polygons, channels, pixel_size, rows=2048):
    """int64 (len(channels), N_BINS) counts of rounded model values over tissue pixels."""
    if not np.issubdtype(image.dtype, np.unsignedinteger):
        raise TypeError(f"image dtype is {image.dtype}; VirTues statistics need an unsigned integer image")
    h, w = model_shape(image.shape[1:], pixel_size)
    counts = np.zeros((len(channels), N_BINS), dtype=np.int64)
    for y0 in range(0, h, rows):
        for x0 in range(0, w, rows):  # square windows bound memory by tile size, not image width
            y1, x1 = min(y0 + rows, h), min(x0 + rows, w)
            mask = tissue_mask(polygons, y0, y1, x0, x1, pixel_size)
            if not mask.any():
                continue
            for i, channel in enumerate(channels):
                values = resample_window(image, channel, y0, y1, x0, x1, pixel_size)[mask]
                bins = np.clip(np.rint(values), 0, N_BINS - 1).astype(np.int64)
                counts[i] += np.bincount(bins, minlength=N_BINS)
    return counts


def stats_from_histogram(counts):
    """cap, mean, sd (population, two-pass) of log1p(min(v, cap)), and tissue_pixels."""
    counts = np.asarray(counts, dtype=np.int64)
    n = int(counts.sum())
    if n == 0:
        raise ValueError("no tissue pixels")
    cum = np.cumsum(counts)

    def value_at(rank):  # rank-th smallest pixel value, 0-based
        return int(np.searchsorted(cum, rank, side="right"))

    virtual = QUANTILE * (n - 1)
    lower = math.floor(virtual)
    # numpy's linear method, on the two neighbouring values
    cap = float(np.quantile([value_at(lower), value_at(min(lower + 1, n - 1))], virtual - lower))
    x = np.log1p(np.minimum(np.arange(N_BINS, dtype=np.float64), cap))
    c = counts.astype(np.float64)
    mean = float((c * x).sum() / n)
    sd = float(np.sqrt((c * (x - mean) ** 2).sum() / n))
    if sd == 0:
        raise ValueError("standard deviation is zero (constant marker)")
    return {"cap": cap, "mean": mean, "sd": sd, "tissue_pixels": n}


def load_stats(path, channels):
    """Markers for [(name, uniprot_id)], checking format and IDs against the file."""
    stats = json.loads(Path(path).read_text())
    if stats.get("format") != STATS_FORMAT:
        raise ValueError(f"{path}: format {stats.get('format')}, expected {STATS_FORMAT}")
    out = {}
    for name, uid in channels:
        entry = stats["markers"].get(name)
        if entry is None:
            raise ValueError(f"{path}: marker {name} is missing; the file has {sorted(stats['markers'])}")
        if entry["uniprot_id"] != uid:
            raise ValueError(f"{path}: marker {name} has UniProt ID {entry['uniprot_id']}, expected {uid}")
        out[name] = entry
    return out


def combine(paths, slide, pixel_size, output):
    """Sum per-core histograms and write the slide statistics file."""
    loaded = []
    for p in paths:
        with np.load(p, allow_pickle=False) as z:
            loaded.append(
                (
                    str(z["sample"]),
                    [str(m) for m in z["markers"]],
                    [str(u) for u in z["uniprot_ids"]],
                    z["counts"],
                )
            )
    first = loaded[0]
    for sample, markers, ids, _ in loaded[1:]:
        if markers != first[1] or ids != first[2]:
            raise ValueError(
                f"{sample} has markers/IDs {list(zip(markers, ids, strict=True))}, "
                f"but {first[0]} has {list(zip(first[1], first[2], strict=True))}"
            )
    total = sum(c for *_, c in loaded)
    result = {}
    for i, (name, uid) in enumerate(zip(first[1], first[2], strict=True)):
        try:
            result[name] = {"uniprot_id": uid, **stats_from_histogram(total[i])}
        except ValueError as e:
            raise ValueError(f"slide {slide}, marker {name}: {e}") from e
    doc = {
        "format": STATS_FORMAT,
        "slide": slide,
        "cores": sorted(s for s, *_ in loaded),
        "model_um_per_px": MODEL_UM_PER_PX,
        "pixel_size": pixel_size,
        "markers": result,
    }
    Path(output).write_text(json.dumps(doc, indent=2) + "\n")


def _histogram_cli(args):
    import spatialdata as sd

    from resolve_segmentation import store_image_key

    pairs = [c.rsplit(":", 1) for c in args.channels.split(",")]
    sdata = sd.read_zarr(args.sdata)
    if TISSUE_KEY not in sdata.shapes:
        sys.exit(f"[virtues_stats] {args.sdata} has no '{TISSUE_KEY}' shapes element")
    image = sdata.images[store_image_key(args.sdata)]
    if hasattr(image, "children"):  # multiscale: full resolution is scale0
        image = image["scale0"]["image"]
    available = [str(c) for c in image.coords["c"].values]
    unknown = [n for n, _ in pairs if n not in available]
    if unknown:
        sys.exit(f"[virtues_stats] unknown channels {unknown}; the store has {available}")
    try:
        counts = histogram(
            image.data,
            to_image_pixels(sdata.shapes[TISSUE_KEY], image),
            [available.index(n) for n, _ in pairs],
            args.pixel_size,
        )
    except (TypeError, ValueError) as e:
        sys.exit(f"[virtues_stats] {e}")
    sample = Path(args.output).name.removesuffix("_virtues_hist.npz")
    np.savez(
        args.output,
        counts=counts,
        markers=np.array([n for n, _ in pairs]),
        uniprot_ids=np.array([u for _, u in pairs]),
        sample=sample,
    )


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    h = sub.add_parser("histogram", help="per-core tissue histograms")
    h.add_argument("--sdata", required=True, help="SpatialData store; only read")
    h.add_argument("--channels", required=True, help="NAME:UNIPROT_ID,...")
    h.add_argument("--pixel-size", required=True, type=float, help="um per image px")
    h.add_argument("--output", required=True)
    c = sub.add_parser("combine", help="sum a slide's histograms into statistics")
    c.add_argument("--slide", required=True)
    c.add_argument("--pixel-size", required=True, type=float)
    c.add_argument("--output", required=True)
    c.add_argument("histograms", nargs="+")
    args = parser.parse_args(argv)
    if args.command == "histogram":
        _histogram_cli(args)
    else:
        try:
            combine(args.histograms, args.slide, args.pixel_size, args.output)
        except ValueError as e:
            sys.exit(f"[virtues_stats] {e}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
