#!/usr/bin/env python3
"""VirTues cell, niche and tissue embeddings, in tile windows so image size does not limit memory.

The tiling core is model-free and tested with a fake encoder. Coordinates are model px
(1 um/px); "padded" coordinates shift them by PAD, as upstream pads before cutting crops.
"""

from dataclasses import dataclass
from collections.abc import Callable

import numpy as np

from virtues_stats import tissue_mask

CROP = 128
PATCH = 8
STEP = 42
PAD = 120
TILE = 2048
BATCH = 32
NICHE_MIN_TISSUE = 0.30
BLUR_SIGMA = 1.0
GRID = CROP // PATCH  # patches per crop side

_K = np.exp(-0.5 * (np.array([-1.0, 0.0, 1.0]) / BLUR_SIGMA) ** 2)
BLUR_KERNEL = (_K / _K.sum()).astype(np.float32)  # torchvision v2.GaussianBlur(3, 1.0), 1D
# patch index of each pixel in a crop, row-major as the encoder's 16 x 16 tokens
_PATCH_OF_PIXEL = (np.arange(CROP)[:, None] // PATCH * GRID + np.arange(CROP)[None, :] // PATCH).ravel()


def _crop_starts(n):
    """Upstream's crop starts along one axis: every STEP, plus one flush with the far edge."""
    return sorted(set(range(0, n - CROP + 1, STEP)) | {n - CROP})


def uniform_crops(h, w):
    """Sorted crop origins of upstream _get_uniform_crops(img, STEP, CROP) for an h x w padded image."""
    return [(i, j) for i in _crop_starts(h) for j in _crop_starts(w)]


def model_input(read_raw, stats, y0, y1, x0, x1, padded_shape):
    """Standardised, blurred float32 (c, y1 - y0, x1 - x0) in padded coordinates."""
    cap, mean, sd = (np.asarray(stats[k], dtype=np.float32)[:, None, None] for k in ("cap", "mean", "sd"))
    h, w = padded_shape[0] - 2 * PAD, padded_shape[1] - 2 * PAD
    # one pixel more on each side feeds the blur; zeros outside the image are upstream's pad
    ey0, ex0 = y0 - 1 - PAD, x0 - 1 - PAD
    raw = np.zeros((len(cap), y1 - y0 + 2, x1 - x0 + 2), dtype=np.float32)
    ry0, ry1 = max(ey0, 0), min(y1 + 1 - PAD, h)
    rx0, rx1 = max(ex0, 0), min(x1 + 1 - PAD, w)
    if ry1 > ry0 and rx1 > rx0:
        for c in range(len(cap)):
            raw[c, ry0 - ey0 : ry1 - ey0, rx0 - ex0 : rx1 - ex0] = read_raw(c, ry0, ry1, rx0, rx1)
    z = (np.log1p(np.minimum(raw, cap)) - mean) / sd
    k0, k1, k2 = BLUR_KERNEL
    z = k0 * z[:, :-2] + k1 * z[:, 1:-1] + k2 * z[:, 2:]
    return (k0 * z[:, :, :-2] + k1 * z[:, :, 1:-1] + k2 * z[:, :, 2:]).astype(np.float32)


@dataclass
class CellSource:
    """One segmentation method's cells, labels 1..n, all in padded coordinates."""

    read_labels: Callable  # (y0, y1, x0, x1) -> int32 labels, 0 for background
    centroids: np.ndarray  # (n, 2) y, x
    bboxes: np.ndarray  # (n, 4) y0, y1, x0, x1


def label_reader(geoms, pixel_size):
    """read_labels(y0, y1, x0, x1) in padded coordinates; geoms in image coordinates, the earlier wins."""
    from shapely import STRtree
    from shapely.geometry import box

    tree = STRtree(geoms)

    def read_labels(y0, y1, x0, x1):
        labels = np.zeros((y1 - y0, x1 - x0), dtype=np.int32)
        my0, my1, mx0, mx1 = y0 - PAD, y1 - PAD, x0 - PAD, x1 - PAD
        window = box(mx0 / pixel_size, my0 / pixel_size, mx1 / pixel_size, my1 / pixel_size)
        for i in np.sort(tree.query(window)):
            gx0, gy0, gx1, gy1 = geoms[i].bounds
            # model pixels whose centre can lie inside the geom's bounds
            ky0 = max(int(np.ceil(gy0 * pixel_size - 0.5)), my0)
            ky1 = min(int(np.floor(gy1 * pixel_size - 0.5)) + 1, my1)
            kx0 = max(int(np.ceil(gx0 * pixel_size - 0.5)), mx0)
            kx1 = min(int(np.floor(gx1 * pixel_size - 0.5)) + 1, mx1)
            if ky1 <= ky0 or kx1 <= kx0:
                continue
            inside = tissue_mask([geoms[i]], ky0, ky1, kx0, kx1, pixel_size)
            region = labels[ky0 - my0 : ky1 - my0, kx0 - mx0 : kx1 - mx0]
            region[inside & (region == 0)] = i + 1
        return labels

    return read_labels


def _embed_dim(read_input, encode):
    """Embedding size D, from an empty batch, for outputs with no rows."""
    c = read_input(0, 0, 0, 0).shape[0]
    return encode(np.zeros((0, c, CROP, CROP), dtype=np.float32)).shape[-1]


def _crop_mask(rows, cols, bboxes):
    """Bool (len(rows), len(cols)): crops whose box meets any bbox (y0, y1, x0, x1)."""
    ri0 = np.searchsorted(rows, bboxes[:, 0] - CROP, side="right")
    ri1 = np.searchsorted(rows, bboxes[:, 1], side="left")
    ci0 = np.searchsorted(cols, bboxes[:, 2] - CROP, side="right")
    ci1 = np.searchsorted(cols, bboxes[:, 3], side="left")
    ok = (ri1 > ri0) & (ci1 > ci0)
    ri0, ri1, ci0, ci1 = ri0[ok], ri1[ok], ci0[ok], ci1[ok]
    # 2D difference array: each bbox adds 1 over its rectangle of crops
    diff = np.zeros((len(rows) + 1, len(cols) + 1), dtype=np.int64)
    np.add.at(diff, (ri0, ci0), 1)
    np.add.at(diff, (ri0, ci1), -1)
    np.add.at(diff, (ri1, ci0), -1)
    np.add.at(diff, (ri1, ci1), 1)
    return diff.cumsum(0).cumsum(1)[:-1, :-1] > 0


def _crop_cells(labels, tokens):
    """Cells in one crop: ids, float32 (p, D) sums of count x token, int64 pixel counts."""
    lab = labels.ravel()
    fg = lab > 0
    if not fg.any():
        return None
    # sorted by cell then patch, so each cell's sum adds its patches in a fixed order
    keys, counts = np.unique(lab[fg].astype(np.int64) * GRID * GRID + _PATCH_OF_PIXEL[fg], return_counts=True)
    cells, patches = keys // (GRID * GRID), keys % (GRID * GRID)
    starts = np.flatnonzero(np.r_[True, cells[1:] != cells[:-1]])
    vals = counts[:, None].astype(np.float32) * tokens[patches]
    return cells[starts], np.add.reduceat(vals, starts, axis=0), np.add.reduceat(counts, starts)


def cell_embeddings(read_input, sources, padded_shape, encode, tile=TILE, batch=BATCH):
    """Per method (emb float32 (n, D), weight float64 (n,)), NaN rows where the weight is 0."""
    rows, cols = np.array(_crop_starts(padded_shape[0])), np.array(_crop_starts(padded_shape[1]))
    nx = -(-padded_shape[1] // tile)
    owner = {
        m: (s.centroids[:, 0] // tile * nx + s.centroids[:, 1] // tile).astype(np.int64)
        for m, s in sources.items()
    }
    sums = dict.fromkeys(sources)
    weights = {m: np.zeros(len(s.centroids), dtype=np.float64) for m, s in sources.items()}
    tiles = np.unique(np.concatenate([np.zeros(0, np.int64), *owner.values()]))
    for t in tiles:
        owned = {m: owner[m] == t for m in sources}
        bboxes = np.concatenate([np.asarray(s.bboxes)[owned[m]] for m, s in sources.items()])
        mask = _crop_mask(rows, cols, bboxes)
        if not mask.any():
            continue
        ri, ci = np.nonzero(mask)  # row-major, upstream's sorted order
        wy0, wy1 = rows[ri.min()], rows[ri.max()] + CROP
        wx0, wx1 = cols[ci.min()], cols[ci.max()] + CROP
        x = read_input(wy0, wy1, wx0, wx1)
        labels = {m: s.read_labels(wy0, wy1, wx0, wx1) for m, s in sources.items() if owned[m].any()}
        for b in range(0, len(ri), batch):
            origins = [
                (rows[i] - wy0, cols[j] - wx0)
                for i, j in zip(ri[b : b + batch], ci[b : b + batch], strict=False)
            ]
            crops = np.stack([x[:, y : y + CROP, xx : xx + CROP] for y, xx in origins])
            tokens = encode(crops).reshape(len(origins), GRID * GRID, -1)
            for (y, xx), tok in zip(origins, tokens, strict=False):
                for m, lab in labels.items():
                    found = _crop_cells(lab[y : y + CROP, xx : xx + CROP], tok)
                    if found is None:
                        continue
                    ids, vals, counts = found
                    keep = owned[m][ids - 1]  # only this tile's cells, so each cell is summed once
                    if sums[m] is None:
                        sums[m] = np.zeros((len(weights[m]), tok.shape[-1]), dtype=np.float32)
                    sums[m][ids[keep] - 1] += vals[keep]
                    weights[m][ids[keep] - 1] += counts[keep]
        del x, labels
    out = {}
    for m in sources:
        if sums[m] is None:
            sums[m] = np.zeros((len(weights[m]), _embed_dim(read_input, encode)), dtype=np.float32)
        emb, has = sums[m], weights[m][:, None] > 0
        np.divide(emb, weights[m][:, None], out=emb, where=has)  # in place: no (n, D) float64 copy
        emb[~has[:, 0]] = np.nan
        out[m] = (emb, weights[m])
    return out


def niche_embeddings(read_input, read_tissue, image_shape_model, encode, batch=BATCH):
    """Kept squares' model origins, tissue fractions and float32 (k, D) patch-mean embeddings."""
    h, w = (n // CROP * CROP for n in image_shape_model)  # squares fully inside the image
    origins, fractions, embeddings, pending = [], [], [], []

    def flush():
        tokens = encode(np.stack(pending))
        embeddings.append(tokens.reshape(len(pending), GRID * GRID, -1).mean(axis=1))
        pending.clear()

    for ty in range(0, h, TILE):
        for tx in range(0, w, TILE):  # one tile window at a time
            y1, x1 = min(ty + TILE, h), min(tx + TILE, w)
            tissue = read_tissue(ty, y1, tx, x1)
            frac = tissue.reshape((y1 - ty) // CROP, CROP, (x1 - tx) // CROP, CROP).mean(axis=(1, 3))
            if not (frac >= NICHE_MIN_TISSUE).any():
                continue
            x = read_input(ty + PAD, y1 + PAD, tx + PAD, x1 + PAD)
            for i, j in zip(*np.nonzero(frac >= NICHE_MIN_TISSUE), strict=False):
                origins.append((ty + i * CROP, tx + j * CROP))
                fractions.append(frac[i, j])
                pending.append(x[:, i * CROP : (i + 1) * CROP, j * CROP : (j + 1) * CROP].copy())
                if len(pending) == batch:
                    flush()
            del x
    if pending:
        flush()
    if not origins:
        return [], np.zeros(0), np.zeros((0, _embed_dim(read_input, encode)), dtype=np.float32)
    emb = np.concatenate(embeddings).astype(np.float32)
    order = sorted(range(len(origins)), key=origins.__getitem__)  # grid order across tiles
    return [origins[i] for i in order], np.asarray(fractions, dtype=np.float64)[order], emb[order]


def tissue_embedding(niches):
    """Mean of the niche rows; NaN (D,) when there are none."""
    if len(niches) == 0:
        return np.full(niches.shape[1], np.nan, dtype=np.float32)
    return niches.astype(np.float64).mean(axis=0).astype(np.float32)
