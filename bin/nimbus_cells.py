#!/usr/bin/env python3
"""Score each marker channel per cell with Nimbus, in tile windows so image size does not limit memory.

The tiling core (assignment, windows, label rasterisation, normalisation factor, per-cell means) is
model-free; load_nimbus, nimbus_predictor and the CLI add the model. Sizes are in image px unless
named *_MODEL_PX.
"""

import argparse
import hashlib
import json
import math
import sys
from pathlib import Path

QUANTILE = 0.999
TILE_MODEL_PX = 2048
MIN_WINDOW_MODEL_PX = 1056
MARGIN_EXTRA_MODEL_PX = 32
WEIGHTS = "V1.pt"
MODEL_MAGNIFICATION = 10
MAGNIFICATION_AT_1_UM = 10  # "10x" = 1 um/px: unconfirmed upstream (see tools/containers/nimbus/README.md)
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


def magnification(pixel_size):
    """Upstream magnification for an image of pixel_size um/px; the single place for the 10x = 1 um/px assumption."""
    return MAGNIFICATION_AT_1_UM / pixel_size


def load_nimbus(device, batch_size=4):
    """Nimbus with V1.pt as a valid-padding model; weights come from the image, never the network."""
    from nimbus_inference.nimbus import Nimbus

    nimbus = Nimbus(
        dataset=None,
        output_dir="",
        save_predictions=False,
        batch_size=batch_size,
        test_time_aug=True,
        model_magnification=MODEL_MAGNIFICATION,
        device=device,
        checkpoint=WEIGHTS,
    )
    nimbus.load_checkpoint(padding="valid")
    return nimbus


def model_halo(nimbus):
    """Model px lost per side by the valid model after upstream's crop_by (96 for V1)."""
    import numpy as np
    import torch

    side = np.array(nimbus.input_shape)
    with torch.no_grad():
        out = np.array(nimbus.model(torch.rand(1, 2, *side).to(nimbus.device)).shape[-2:])
    out = out - out % 2**5
    halo = (side - out) // 2
    return int(halo.max())


def nimbus_predictor(nimbus, pixel_size, batch_size=4):
    """predict(channel, normalised, labels) -> probability map, mirroring upstream predict_fovs per channel."""
    import cv2
    import numpy as np
    from nimbus_inference.utils import prepare_binary_mask, prepare_input_data, test_time_aug

    def predict(channel, normalised, labels):
        h, w = normalised.shape
        binary = prepare_binary_mask(labels)
        img = normalised
        if pixel_size != 1:
            size = (round(w * pixel_size), round(h * pixel_size))
            img = cv2.resize(normalised, size)
            binary = cv2.resize(binary, size, interpolation=cv2.INTER_NEAREST)
        data = prepare_input_data(img, binary_mask=binary)
        # the image is already normalised, so upstream's factor argument is unused here
        pred = test_time_aug(data, channel, nimbus, normalization_dict={channel: 1.0}, batch_size=batch_size)
        if not isinstance(pred, np.ndarray):
            pred = pred.cpu().numpy()
        pred = np.squeeze(pred)
        if pixel_size != 1:
            pred = cv2.resize(pred, (w, h), interpolation=cv2.INTER_NEAREST)
        return pred

    return predict


def build_table(scores, channels, obs, region, provenance):
    """AnnData of scores (cells x channels) with the source table's obs, parsed as a SpatialData table."""
    import pandas as pd
    from anndata import AnnData
    from spatialdata.models import TableModel

    adata = AnnData(scores.astype("float32"), obs=obs.copy(), var=pd.DataFrame(index=pd.Index(channels)))
    adata.uns["nimbus"] = provenance
    return TableModel.parse(adata, region=region, region_key="region", instance_key="cell_id")


def parse_args(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--sdata", required=True, help="SpatialData store; only read")
    parser.add_argument(
        "--method", required=True, help="segmentation method; reads {method}_cells and {method}_table"
    )
    parser.add_argument("--channels", required=True, help="comma-separated image channels to score")
    parser.add_argument("--pixel-size", type=float, required=True, help="image um/px")
    parser.add_argument("--device", default="cpu", choices=["cpu", "cuda"])
    parser.add_argument("--output", required=True, help="h5ad file to write")
    parser.add_argument("--provenance", required=True, help="JSON file to write")
    args = parser.parse_args(argv)
    if args.pixel_size <= 0:
        parser.error("--pixel-size must be positive")
    args.channels = [c for c in args.channels.split(",") if c]
    if not args.channels or len(set(args.channels)) != len(args.channels):
        parser.error("--channels needs at least one name, each once")
    return args


def sha256(path):
    h = hashlib.sha256()
    with Path(path).open("rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def main(argv=None, predict=None, halo=None) -> int:
    """predict and halo are injected by tests; otherwise the real model is loaded."""
    import numpy as np
    import spatialdata as sd

    from resolve_segmentation import store_image_key

    args = parse_args(argv)
    sdata = sd.read_zarr(args.sdata)
    image = sdata.images[store_image_key(args.sdata)]
    if hasattr(image, "children"):  # multiscale: full resolution is scale0
        image = image["scale0"]["image"]
    available = [str(c) for c in image.coords["c"].values]
    unknown = [c for c in args.channels if c not in available]
    if unknown:
        print(f"[nimbus] unknown channels {unknown}; the store has {available}", file=sys.stderr)
        sys.exit(1)
    image = image.sel(c=args.channels)  # score_cells indexes channels by position

    table = sdata.tables[f"{args.method}_table"]
    shapes = sdata.shapes[f"{args.method}_cells"]
    names = [str(n) for n in table.obs_names]
    by_id = shapes.set_axis(shapes.index.astype(str))
    missing = [n for n in names if n not in by_id.index]
    if missing:
        sys.exit(f"[nimbus] {len(missing)} table cells have no shape, e.g. {missing[:3]}")
    geoms = list(by_id.loc[names].geometry)
    labels = np.arange(1, len(names) + 1)  # compact, as cell_means sizes its bincount by the largest label

    weights_sha = ""
    if predict is None:
        nimbus = load_nimbus(args.device)
        predict = nimbus_predictor(nimbus, args.pixel_size)
        halo = model_halo(nimbus)
        weights_sha = sha256(nimbus.checkpoint_path)
    tile = image_px(TILE_MODEL_PX, args.pixel_size)
    margin = image_px(halo + MARGIN_EXTRA_MODEL_PX, args.pixel_size)
    min_window = image_px(MIN_WINDOW_MODEL_PX, args.pixel_size)

    factors = normalisation_factors(image, args.channels)
    scores = score_cells(image, geoms, labels, args.channels, factors, predict, tile, margin, min_window)

    try:
        from importlib.metadata import version

        nimbus_version = version("Nimbus-Inference")
    except Exception:  # noqa: BLE001
        nimbus_version = "unknown"
    provenance = {
        "nimbus_version": nimbus_version,
        "weights": WEIGHTS,
        "weights_sha256": weights_sha,
        "channels": args.channels,
        "factors": {c: f for c, f in factors.items() if f is not None},
        "unscored": [c for c, f in factors.items() if f is None],
        "pixel_size": args.pixel_size,
        "magnification": magnification(args.pixel_size),
        "tile_size": tile,
        "margin": margin,
        "halo": halo,
        "min_window": min_window,
        "test_time_aug": True,
        "device": args.device,
    }
    obs = table.obs[[c for c in ("region", "slide", "core_id", "cell_id") if c in table.obs.columns]]
    out = build_table(scores, args.channels, obs, f"{args.method}_cells", provenance)
    out.write_h5ad(args.output)
    Path(args.provenance).write_text(json.dumps(provenance, indent=2))
    print(
        f"[nimbus] {args.method}: {out.n_obs} cells x {len(args.channels)} channels, unscored {provenance['unscored']}"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
