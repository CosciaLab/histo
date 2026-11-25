#!/usr/bin/env python3
"""VirTues cell, niche and tissue embeddings, in tile windows so image size does not limit memory.

The tiling core is model-free and tested with a fake encoder; load_virtues, virtues_encoder and the
CLI add the model. Coordinates are model px (1 um/px); "padded" coordinates shift them by PAD, as
upstream pads before cutting crops. torch, virtues and esm are imported inside functions, so the
core imports without them.
"""

import argparse
import hashlib
import json
import os
import sys
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

import numpy as np

from virtues_stats import MODEL_UM_PER_PX, TISSUE_KEY, load_stats, model_shape, resample_window, tissue_mask

CROP = 128
PATCH = 8
STEP = 42
PAD = 120
TILE = 2048
BATCH = 32
NICHE_MIN_TISSUE = 0.30
BLUR_SIGMA = 1.0
GRID = CROP // PATCH  # patches per crop side
EMBED_DIM = 512
ESM_MODEL = "esm2_t30_150M_UR50D"

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


# --- model ---


def uniprot_sequences(fasta, ids):
    """Sequences for ids from a UniProt FASTA (headers >sp|ACC|...); KeyError names absent IDs."""
    wanted, seqs, current = set(ids), {}, None
    with Path(fasta).open() as f:
        for line in f:
            if line.startswith(">"):
                acc = line.split("|")[1] if line.count("|") >= 2 else None
                current = acc if acc in wanted else None
                if current is not None:
                    seqs[current] = []
            elif current is not None:
                seqs[current].append(line.strip())
    missing = [i for i in ids if i not in seqs]
    if missing:
        raise KeyError(f"UniProt IDs {missing} are not in {fasta}")
    return {i: "".join(seqs[i]) for i in ids}


def esm_embeddings(sequences, device):
    """float32 (n, 640) ESM-2 marker embeddings: upstream ESMWrapper's model and its mean over residues."""
    import types

    import torch

    # upstream's module imports Bio.SeqIO for a FASTA helper only; the image has no biopython
    try:
        import Bio  # noqa: F401
    except ImportError:
        sys.modules["Bio"] = types.SimpleNamespace(SeqIO=None)
    from virtues.utils.compute_esm_embeddings import ESMWrapper

    esm = ESMWrapper(ESM_MODEL, device)
    layer = esm.model.num_layers
    out = []
    for seq in sequences:
        _, _, tokens = esm.batch_converter([("marker", seq)])
        with torch.no_grad():
            # ESMWrapper.embed without return_contacts: its attention maps for Ki-67 (3256 aa) exceed an A40
            rep = esm.model(tokens.to(device), repr_layers=[layer])["representations"][layer]
        out.append(rep[0, 1 : len(seq) + 1].mean(0).float().cpu())
    del esm
    return torch.stack(out)


def build_model(weights, prior_bias_embeddings, device):
    """MultiplexVirtues with these marker embeddings (row i = channel i) and the weights, in eval mode."""
    from safetensors.torch import load_file
    from virtues.modules.multiplex_virtues import MultiplexVirtues

    model = MultiplexVirtues(prior_bias_embeddings=prior_bias_embeddings)
    model.load_state_dict(load_file(str(weights)))
    return model.to(device).eval()


def load_virtues(weights, sequences, device):
    """The model, with ESM-2 embeddings of the channels' sequences in channel order."""
    return build_model(weights, esm_embeddings(sequences, device), device)


def virtues_encoder(model, n_channels, device):
    """encode(crops float32 (n, c, 128, 128)) -> patch summary tokens float32 (n, 16, 16, 512), as upstream."""
    import torch

    channels = torch.arange(n_channels, device=device)

    def encode(crops):
        if len(crops) == 0:  # the core asks with an empty batch for the embedding size
            return np.zeros((0, GRID, GRID, EMBED_DIM), dtype=np.float32)
        x = torch.from_numpy(np.ascontiguousarray(crops, dtype=np.float32)).to(device)
        with torch.no_grad(), torch.amp.autocast("cuda", enabled=True):
            out = model.encoder.forward_list(list(x), [channels] * len(crops), multiplex_mask=None)
        return torch.stack(out.patch_summary_tokens).float().cpu().numpy()

    return encode


# --- CLI ---

OBS_COLUMNS = ("region", "slide", "core_id", "cell_id")


def cell_source(geoms, pixel_size, model_hw):
    """CellSource for image-coordinate geoms, clipped to the model grid so no label falls outside it."""
    import shapely

    geoms = np.asarray(geoms, dtype=object)
    extent = shapely.box(0, 0, model_hw[1] / pixel_size, model_hw[0] / pixel_size)
    # clip only cells crossing the edge, so interior geometries stay bit-identical
    out = ~shapely.covered_by(geoms, extent)
    geoms = geoms.copy()
    if out.any():
        geoms[out] = shapely.intersection(geoms[out], extent)
    b = shapely.bounds(geoms).reshape(-1, 4)  # minx, miny, maxx, maxy; NaN when empty
    empty = np.isnan(b).any(axis=1)
    centroids = np.zeros((len(geoms), 2))
    c = shapely.centroid(geoms[~empty])
    centroids[~empty] = np.stack([shapely.get_y(c), shapely.get_x(c)], axis=-1) * pixel_size + PAD
    # rounded outward, so the box holds every pixel centre inside the cell
    k = b * pixel_size  # minx, miny, maxx, maxy in model px
    bboxes = (
        np.stack([np.floor(k[:, 1]), np.ceil(k[:, 3]), np.floor(k[:, 0]), np.ceil(k[:, 2])], axis=-1) + PAD
    )
    bboxes[empty] = 0  # no pixel: an empty box selects no crop
    return CellSource(label_reader(list(geoms), pixel_size), centroids, bboxes)


def stats_arrays(entries, names):
    """cap, mean, sd arrays in channel order, from load_stats' per-marker entries."""
    return {k: np.array([entries[n][k] for n in names], dtype=np.float64) for k in ("cap", "mean", "sd")}


def build_table(x, obs, provenance, region=None, instance_key=None):
    """float16 AnnData with virtues_0 ... columns, parsed as a SpatialData table."""
    import pandas as pd
    from anndata import AnnData
    from spatialdata.models import TableModel

    var = pd.DataFrame(index=pd.Index([f"virtues_{i}" for i in range(x.shape[1])]))
    adata = AnnData(x.astype(np.float16), obs=obs.copy(), var=var)
    adata.uns["virtues"] = provenance
    if region is None:
        return TableModel.parse(adata)
    return TableModel.parse(adata, region=region, region_key="region", instance_key=instance_key)


def sha256(path):
    with Path(path).open("rb") as f:
        return hashlib.file_digest(f, "sha256").hexdigest()


def fail(message):
    print(f"[virtues] {message}", file=sys.stderr)
    sys.exit(1)


def parse_args(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--sdata", required=True, help="SpatialData store; only read")
    parser.add_argument("--methods", required=True, help="M1,M2; reads {M}_cells and {M}_table")
    parser.add_argument("--channels", required=True, help="NAME:UNIPROT_ID,... in model channel order")
    parser.add_argument("--unembedded", default="", help="channels without an ID; recorded only")
    parser.add_argument("--stats", required=True, help="slide statistics, *_virtues_stats.json")
    parser.add_argument("--pixel-size", type=float, required=True, help="image um/px")
    parser.add_argument("--device", required=True, help="cuda; FlashAttention has no CPU path")
    parser.add_argument("--batch-size", type=int, default=BATCH, help="crops per GPU batch")
    parser.add_argument("--outdir", default=".")
    args = parser.parse_args(argv)
    if args.pixel_size <= 0:
        parser.error("--pixel-size must be positive")
    if args.batch_size < 1:
        parser.error("--batch-size must be at least 1")
    args.methods = [m for m in args.methods.split(",") if m]
    bad = [c for c in args.channels.split(",") if c and ":" not in c]
    if bad:
        parser.error(f"--channels entries need NAME:UNIPROT_ID; got {bad}")
    args.channels = [tuple(c.rsplit(":", 1)) for c in args.channels.split(",") if c]
    names = [n for n, _ in args.channels]
    if not names or len(set(names)) != len(names) or not args.methods:
        parser.error("--channels and --methods need at least one entry, each once")
    args.unembedded = [c for c in args.unembedded.split(",") if c]
    return args


def main(argv=None, encode=None) -> int:
    """encode is injected by tests; otherwise the model is loaded on the GPU."""
    import geopandas as gpd
    import pandas as pd
    import spatialdata as sd
    from shapely.geometry import box

    from resolve_segmentation import store_image_key

    args = parse_args(argv)
    if not (args.device == "cuda" or args.device.startswith("cuda:")):
        fail(f"VirTues needs a CUDA device (FlashAttention has no CPU path); got --device {args.device}")
    names = [n for n, _ in args.channels]
    ids = [u for _, u in args.channels]

    sdata = sd.read_zarr(args.sdata)
    image = sdata.images[store_image_key(args.sdata)]
    if hasattr(image, "children"):  # multiscale: full resolution is scale0
        image = image["scale0"]["image"]
    available = [str(c) for c in image.coords["c"].values]
    unknown = [n for n in names + args.unembedded if n not in available]
    if unknown:
        fail(f"unknown channels {unknown}; the store has {available}")
    if TISSUE_KEY not in sdata.shapes:
        fail(f"{args.sdata} has no '{TISSUE_KEY}' shapes element")
    try:
        entries = load_stats(args.stats, args.channels)
    except ValueError as e:
        fail(str(e))
    fasta = os.environ.get("VIRTUES_UNIPROT")
    if not fasta:
        fail("VIRTUES_UNIPROT is not set; it names the UniProt FASTA baked into the image")
    try:
        sequences = uniprot_sequences(fasta, ids)
    except KeyError as e:
        fail(e.args[0])

    weights = os.environ.get("VIRTUES_WEIGHTS", "")
    weights_sha = ""
    if encode is None:
        import torch

        if not torch.cuda.is_available():
            fail(f"--device {args.device}, but torch sees no CUDA device")
        model = load_virtues(weights, [sequences[u] for u in ids], args.device)
        encode = virtues_encoder(model, len(ids), args.device)
        weights_sha = sha256(weights)

    ps = args.pixel_size
    data = image.data
    model_hw = model_shape(data.shape[1:], ps)
    padded = (model_hw[0] + 2 * PAD, model_hw[1] + 2 * PAD)
    index = [available.index(n) for n in names]
    st = stats_arrays(entries, names)

    def read_raw(c, y0, y1, x0, x1):
        return resample_window(data, index[c], y0, y1, x0, x1, ps)

    def read_input(y0, y1, x0, x1):
        return model_input(read_raw, st, y0, y1, x0, x1, padded)

    tissue_polys = list(sdata.shapes[TISSUE_KEY].geometry)

    def read_tissue(y0, y1, x0, x1):
        return tissue_mask(tissue_polys, y0, y1, x0, x1, ps)

    sources, obs = {}, {}
    for m in args.methods:
        table = sdata.tables[f"{m}_table"]
        rows = [str(n) for n in table.obs_names]
        by_id = sdata.shapes[f"{m}_cells"].set_axis(sdata.shapes[f"{m}_cells"].index.astype(str))
        missing = [n for n in rows if n not in by_id.index]
        if missing:
            fail(f"{m}: {len(missing)} table cells have no shape, e.g. {missing[:3]}")
        sources[m] = cell_source(list(by_id.loc[rows].geometry), ps, model_hw)
        obs[m] = table.obs[[c for c in OBS_COLUMNS if c in table.obs.columns]]

    cells = cell_embeddings(read_input, sources, padded, encode, batch=args.batch_size)
    origins, fractions, niche_emb = niche_embeddings(
        read_input, read_tissue, model_hw, encode, batch=args.batch_size
    )
    n_squares = (model_hw[0] // CROP) * (model_hw[1] // CROP)

    provenance = {
        "virtues_commit": os.environ.get("VIRTUES_COMMIT", "unknown"),
        "weights": weights,
        "weights_sha256": weights_sha,
        "esm_model": ESM_MODEL,
        "uniprot_release": os.environ.get("VIRTUES_UNIPROT_RELEASE", "unknown"),
        "channels": dict(args.channels),
        "unembedded": args.unembedded,
        "stats": entries,
        "pixel_size": ps,
        "model_um_per_px": MODEL_UM_PER_PX,
        "crop_size": CROP,
        "crop_step": STEP,
        "patch_size": PATCH,
        "padding": PAD,
        "tile_size": TILE,
        "batch_size": args.batch_size,
        "device": args.device,
        "n_cells": {m: len(w) for m, (_, w) in cells.items()},
        "n_cells_without_pixel": {m: int((w == 0).sum()) for m, (_, w) in cells.items()},
        "n_niches_kept": len(origins),
        "n_niches_dropped": n_squares - len(origins),
    }

    outdir = Path(args.outdir)
    outdir.mkdir(parents=True, exist_ok=True)
    for m in args.methods:
        build_table(cells[m][0], obs[m], provenance, f"{m}_cells", "cell_id").write_h5ad(
            outdir / f"{m}_virtues.h5ad"
        )
    # slide and core_id are per store; any non-empty method table carries them
    labels = {}
    for c in ("slide", "core_id"):
        found = [o[c].iloc[0] for o in obs.values() if c in o.columns and len(o)]
        if found:
            labels[c] = str(found[0])
    if origins:
        niche_ids = [f"niche_{i}" for i in range(len(origins))]
        squares = [box(x / ps, y / ps, (x + CROP) / ps, (y + CROP) / ps) for y, x in origins]
        gpd.GeoDataFrame(geometry=squares, index=pd.Index(niche_ids)).to_parquet(
            outdir / "virtues_niches.parquet"
        )
        niche_obs = pd.DataFrame(
            {
                "region": pd.Categorical(["virtues_niches"] * len(origins)),
                "niche_id": niche_ids,
                "tissue_fraction": fractions,
                **{c: pd.Categorical([v] * len(origins)) for c, v in labels.items()},
            },
            index=niche_ids,
        )
        build_table(niche_emb, niche_obs, provenance, "virtues_niches", "niche_id").write_h5ad(
            outdir / "virtues_niches_table.h5ad"
        )
    tissue_obs = pd.DataFrame(
        {**{c: [v] for c, v in labels.items()}, "n_niches": [len(origins)]}, index=["tissue_0"]
    )
    build_table(tissue_embedding(niche_emb)[None, :], tissue_obs, provenance).write_h5ad(
        outdir / "virtues_tissue.h5ad"
    )
    (outdir / "virtues.json").write_text(json.dumps(provenance, indent=2) + "\n")
    print(
        f"[virtues] cells {provenance['n_cells']}, without a pixel {provenance['n_cells_without_pixel']}; "
        f"squares kept {len(origins)}, dropped {provenance['n_niches_dropped']}"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
