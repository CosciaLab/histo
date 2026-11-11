#!/usr/bin/env python3
"""Score each marker channel per cell with Nimbus, in tile windows so image size does not limit memory.

This part is model-free: tile assignment, windows, label rasterisation, the per-store
normalisation factor and per-cell means. Sizes below are in image px unless named *_MODEL_PX.
"""

import math

QUANTILE = 0.999
TILE_MODEL_PX = 2048
MIN_WINDOW_MODEL_PX = 1056
MARGIN_EXTRA_MODEL_PX = 32
# Heavy libraries are imported inside functions so pure helpers test without them.


def image_px(model_px, pixel_size):
    """Convert a size in model px to image px."""
    return math.ceil(model_px / pixel_size)


def assign_tiles(centroids, tile_size):
    """Tile index (tx, ty) of each (x, y) centroid; a cell belongs to the tile holding its centroid."""
    import numpy as np

    return np.floor(np.asarray(centroids, dtype=float) / tile_size).astype(int)


def _axis(lo, hi, margin, min_window, size):
    lo, hi = lo - margin, hi + margin
    if hi - lo < min_window:
        extra = min_window - (hi - lo)
        lo -= extra // 2
        hi = lo + min_window
    if hi - lo <= size:
        # shift inward at the border so the minimum holds where the image allows
        if lo < 0:
            lo, hi = 0, hi - lo
        if hi > size:
            lo, hi = lo - (hi - size), size
    return max(int(lo), 0), min(int(hi), size)


def tile_windows(bounds, tiles, tile_size, margin, min_window, image_shape):
    """(y0, y1, x0, x1) per tile: grown to its cells' bounds, then by margin, then to min_window, clipped."""
    import numpy as np

    bounds, tiles = np.asarray(bounds, dtype=float), np.asarray(tiles)
    h, w = image_shape
    windows = {}
    for tx, ty in np.unique(tiles, axis=0):
        b = bounds[(tiles == (tx, ty)).all(axis=1)]
        x_lo = min(tx * tile_size, b[:, 0].min())
        x_hi = max((tx + 1) * tile_size, math.ceil(b[:, 2].max()) + 1)
        y_lo = min(ty * tile_size, b[:, 1].min())
        y_hi = max((ty + 1) * tile_size, math.ceil(b[:, 3].max()) + 1)
        x0, x1 = _axis(math.floor(x_lo), math.ceil(x_hi), margin, min_window, w)
        y0, y1 = _axis(math.floor(y_lo), math.ceil(y_hi), margin, min_window, h)
        windows[(int(tx), int(ty))] = (y0, y1, x0, x1)
    return windows


def label_window(geoms, labels, window):
    """int32 label image of every geom intersecting the window; labels must be > 0."""
    import numpy as np
    from aggregate_compartments import pixel_outer_bounds, rasterize

    y0, y1, x0, x1 = window
    out = np.zeros((y1 - y0, x1 - x0), dtype=np.int32)
    for geom, label in zip(geoms, labels, strict=True):
        # same outer bounds as aggregation (polygon() includes boundary pixels), clipped to the window
        gx0, gy0, gx1, gy1 = pixel_outer_bounds(geom.bounds)
        bx0, bx1, by0, by1 = max(gx0, x0), min(gx1, x1), max(gy0, y0), min(gy1, y1)
        if bx1 <= bx0 or by1 <= by0:
            continue
        mask = rasterize(geom, (by1 - by0, bx1 - bx0), (bx0, by0))
        sub = out[by0 - y0 : by1 - y0, bx0 - x0 : bx1 - x0]
        sub[mask > 0] = label
    return out


def normalisation_factors(image, channel_names, quantile=QUANTILE, max_pixels=50_000_000):
    """Per-channel quantile of nonzero pixels on a strided grid; None where a channel is all zero."""
    import numpy as np

    _, h, w = image.shape
    s = max(1, math.ceil(math.sqrt(h * w / max_pixels)))
    factors = {}
    for c, name in enumerate(channel_names):
        sub = np.asarray(image[c, ::s, ::s])
        nz = sub[sub > 0]
        factors[name] = float(np.quantile(nz, quantile)) if nz.size else None
    return factors


def cell_means(labels, prediction, wanted):
    """Mean of prediction over each wanted label's pixels; NaN where a label has no pixel."""
    import numpy as np

    wanted = np.asarray(wanted)
    n = int(max(labels.max(), wanted.max())) + 1
    flat = labels.ravel()
    counts = np.bincount(flat, minlength=n)
    sums = np.bincount(flat, weights=np.asarray(prediction, dtype=np.float64).ravel(), minlength=n)
    with np.errstate(invalid="ignore", divide="ignore"):
        means = sums[wanted] / counts[wanted]
    return np.where(counts[wanted] > 0, means, np.nan)


def score_cells(image, geoms, cell_labels, channel_names, factors, predict, tile_size, margin, min_window):
    """(n_cells, n_channels) float32 scores in geoms order; each cell scored once, in its centroid's tile."""
    import numpy as np
    import shapely

    # a missing factor must never fall back to a per-window quantile
    missing = [c for c in channel_names if c not in factors]
    if missing:
        raise KeyError(f"no normalisation factor for channels: {missing}")

    cell_labels = np.asarray(cell_labels)
    out = np.full((len(geoms), len(channel_names)), np.nan, dtype=np.float32)
    if not len(geoms):
        return out
    # empty or None geoms are skipped (rows stay NaN), as in aggregation
    valid = np.array([g is not None and not g.is_empty for g in geoms], dtype=bool)
    if not valid.any():
        return out
    garr = np.asarray(geoms, dtype=object)
    vidx = np.flatnonzero(valid)
    centroids = np.array([(garr[i].centroid.x, garr[i].centroid.y) for i in vidx])
    bounds = np.array([garr[i].bounds for i in vidx])
    tiles = assign_tiles(centroids, tile_size)
    windows = tile_windows(bounds, tiles, tile_size, margin, min_window, image.shape[1:])
    tree = shapely.STRtree(garr[vidx])

    for tile, (y0, y1, x0, x1) in windows.items():
        owned = vidx[(tiles == tile).all(axis=1)]
        near = vidx[tree.query(shapely.box(x0, y0, x1, y1), predicate="intersects")]
        labels = label_window(garr[near], cell_labels[near], (y0, y1, x0, x1))
        for c, name in enumerate(channel_names):
            factor = factors[name]
            if factor is None:
                continue
            window = np.asarray(image[c, y0:y1, x0:x1], dtype=np.float32)
            normalised = np.clip(window / factor, 0, 1)
            pred = predict(name, normalised, labels)
            out[owned, c] = cell_means(labels, pred, cell_labels[owned])
    return out
