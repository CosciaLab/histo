#!/usr/bin/env python3
"""Per-cell marker intensity statistics, one AnnData table per method, written to a file.

Statistics (mean, median, std, min, max, q25, q75, q90) are computed per cell and marker from
all of the cell's pixels, read in tile windows so size does not limit the image. `rasterize` and
`pixel_outer_bounds` are copied from sopa 2.2.12 (BSD 3-Clause, licence below); `rasterize` honours
polygon holes, so a cytoplasm ring is not measured as the whole cell.
The store is only read; a later step writes the table into it.

Optional compartments (nucleus, cytoplasm) become layers of the same table. Their parquets
are indexed by cell id; cells absent from them get NaN. `--links` is a parquet of per-cell
columns indexed by cell id (for example n_nuclei), joined into obs.


BSD 3-Clause License

Copyright (c) 2023, Blampey Quentin
All rights reserved.

Redistribution and use in source and binary forms, with or without
modification, are permitted provided that the following conditions are met:

1. Redistributions of source code must retain the above copyright notice, this
   list of conditions and the following disclaimer.

2. Redistributions in binary form must reproduce the above copyright notice,
   this list of conditions and the following disclaimer in the documentation
   and/or other materials provided with the distribution.

3. Neither the name of the copyright holder nor the names of its
   contributors may be used to endorse or promote products derived from
   this software without specific prior written permission.

THIS SOFTWARE IS PROVIDED BY THE COPYRIGHT HOLDERS AND CONTRIBUTORS "AS IS"
AND ANY EXPRESS OR IMPLIED WARRANTIES, INCLUDING, BUT NOT LIMITED TO, THE
IMPLIED WARRANTIES OF MERCHANTABILITY AND FITNESS FOR A PARTICULAR PURPOSE ARE
DISCLAIMED. IN NO EVENT SHALL THE COPYRIGHT HOLDER OR CONTRIBUTORS BE LIABLE
FOR ANY DIRECT, INDIRECT, INCIDENTAL, SPECIAL, EXEMPLARY, OR CONSEQUENTIAL
DAMAGES (INCLUDING, BUT NOT LIMITED TO, PROCUREMENT OF SUBSTITUTE GOODS OR
SERVICES; LOSS OF USE, DATA, OR PROFITS; OR BUSINESS INTERRUPTION) HOWEVER
CAUSED AND ON ANY THEORY OF LIABILITY, WHETHER IN CONTRACT, STRICT LIABILITY,
OR TORT (INCLUDING NEGLIGENCE OR OTHERWISE) ARISING IN ANY WAY OUT OF THE USE
OF THIS SOFTWARE, EVEN IF ADVISED OF THE POSSIBILITY OF SUCH DAMAGE.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

# Heavy libraries are imported inside functions so pure helpers test without them.


def rasterize(cell, shape, xy_min=(0, 0)):
    """1 where the polygon touches a pixel, else 0; holes (interiors) are 0."""
    # From sopa 2.2.12 (shapes/_rasterize.py); change: holes rasterized as 0, each part in its own mask
    import numpy as np
    import shapely.affinity
    from shapely.geometry import MultiPolygon
    from skimage.draw import polygon

    xmin, ymin, xmax, ymax = [xy_min[0], xy_min[1], xy_min[0] + shape[1], xy_min[1] + shape[0]]

    cell_translated = shapely.affinity.translate(cell, -xmin, -ymin)
    geoms = cell_translated.geoms if isinstance(cell_translated, MultiPolygon) else [cell_translated]

    shape = (ymax - ymin, xmax - xmin)

    rasterized_image = np.zeros(shape, dtype=np.int8)

    for geom in geoms:
        # own mask per part, so one part's hole cannot erase another part
        part = np.zeros(shape, dtype=np.int8)
        x, y = geom.exterior.coords.xy
        rr, cc = polygon(y, x, shape)
        part[rr, cc] = 1
        for interior in geom.interiors:
            x, y = interior.coords.xy
            rr, cc = polygon(y, x, shape)
            part[rr, cc] = 0
        rasterized_image |= part

    return rasterized_image


def pixel_outer_bounds(bounds):
    # From sopa 2.2.12 (shapes/_vectorize.py); unchanged
    from math import ceil, floor

    return [floor(bounds[0]), floor(bounds[1]), ceil(bounds[2]) + 1, ceil(bounds[3]) + 1]


STATISTICS = ("mean", "median", "std", "min", "max", "q25", "q75", "q90")
TILE_SIZE = 2048  # px; shapes are owned by the tile holding their centroid


def parse_statistics(text: str) -> list[str]:
    """Split a comma-separated list; refuse off-menu names, duplicates, and a missing mean."""
    names = [t.strip() for t in text.split(",")]
    for name in names:
        if name not in STATISTICS:
            raise ValueError(f"unknown statistic {name!r}; choose from {', '.join(STATISTICS)}")
    dupes = sorted({n for n in names if names.count(n) > 1})
    if dupes:
        raise ValueError(f"duplicate statistics: {', '.join(dupes)}")
    if "mean" not in names:
        raise ValueError("statistics must include 'mean' (it fills X)")
    return names


def _reduce(pixels, statistic):
    """One statistic over axis 0 of (n_pixels, n_channels) float64 pixels."""
    import numpy as np

    if statistic == "mean":
        return pixels.mean(axis=0)
    if statistic == "median":
        return np.median(pixels, axis=0)
    if statistic == "std":
        return pixels.std(axis=0)  # ddof 0
    if statistic == "min":
        return pixels.min(axis=0)
    if statistic == "max":
        return pixels.max(axis=0)
    return np.quantile(pixels, int(statistic[1:]) / 100, axis=0)


def measure_intensities(image, shapes, statistics, tile_size=TILE_SIZE):
    """Statistics per shape and channel: float32 (n_shapes, n_channels * n_statistics), statistic-major.

    Also returns the largest read window side in px. Image and shapes share pixel coordinates.
    """
    import numpy as np

    cells = shapes.geometry.tolist()
    n_channels = len(image.coords["c"])
    out = np.full((len(cells), n_channels * len(statistics)), np.nan, dtype=np.float32)
    height, width = image.sizes["y"], image.sizes["x"]
    n_ty, n_tx = -(-height // tile_size), -(-width // tile_size)

    # each shape is measured in the tile holding its centroid, from a window that holds all its pixels
    owned = {}
    for i, cell in enumerate(cells):
        if cell is None or cell.is_empty:
            continue
        x, y = cell.centroid.x, cell.centroid.y
        tile = (min(max(int(y // tile_size), 0), n_ty - 1), min(max(int(x // tile_size), 0), n_tx - 1))
        owned.setdefault(tile, []).append(i)

    largest = 0
    for (ty, tx), indices in owned.items():
        boxes = {}
        for i in indices:
            b = pixel_outer_bounds(cells[i].bounds)
            b = [max(b[0], 0), max(b[1], 0), min(b[2], width), min(b[3], height)]
            if b[2] > b[0] and b[3] > b[1]:
                boxes[i] = b
        if not boxes:
            continue
        x0 = min([tx * tile_size, *(b[0] for b in boxes.values())])
        y0 = min([ty * tile_size, *(b[1] for b in boxes.values())])
        x1 = max([min((tx + 1) * tile_size, width), *(b[2] for b in boxes.values())])
        y1 = max([min((ty + 1) * tile_size, height), *(b[3] for b in boxes.values())])
        window = image.data[:, y0:y1, x0:x1].compute()
        largest = max(largest, x1 - x0, y1 - y0)

        for i, (bx0, by0, bx1, by1) in boxes.items():
            sub = window[:, by0 - y0 : by1 - y0, bx0 - x0 : bx1 - x0]
            mask = rasterize(cells[i], sub.shape[1:], (bx0, by0)).astype(bool)
            if not mask.any():
                continue
            pixels = sub[:, mask].T.astype(np.float64)
            for s, statistic in enumerate(statistics):
                out[i, s * n_channels : (s + 1) * n_channels] = _reduce(pixels, statistic)
    return out, largest


def label_cells(obs, slide: str, core_id: str | None = None):
    """Return obs with slide (and core_id, if given) as categorical columns."""
    import pandas as pd

    if not slide:
        raise ValueError("slide must be a non-empty name")

    obs = obs.copy()
    obs["slide"] = pd.Categorical([slide] * len(obs))
    if core_id:
        obs["core_id"] = pd.Categorical([core_id] * len(obs))
    return obs


def specs_by_name(specs: list[dict]) -> dict:
    """uns['segmentation']: anndata cannot write a list of dicts, so key by spec name; None values dropped."""
    return {s["name"]: {k: v for k, v in s.items() if v is not None} for s in specs}


def build_table(cells, x, var_names, layers, obs_extra, region, slide, core_id, specs):
    """AnnData with sopa's obs columns, obs_names = cell index unchanged, parsed as a SpatialData table."""
    # area and obsm['spatial'] describe the cells as given (unexpanded); sopa used the expanded ones
    import pandas as pd
    from anndata import AnnData
    from spatialdata.models import TableModel

    if x.shape[0] != len(cells):
        raise ValueError(f"x has {x.shape[0]} rows but there are {len(cells)} cells")

    names = cells.index.astype(str)
    obs = pd.DataFrame(index=pd.Index(names))
    obs["region"] = pd.Series(region, index=names, dtype="category")
    obs = label_cells(obs, slide, core_id)
    obs["cell_id"] = names
    obs["area"] = cells.area.values
    if obs_extra is not None:
        obs = obs.join(obs_extra.set_axis(obs_extra.index.astype(str)))

    adata = AnnData(x, obs=obs, var=pd.DataFrame(index=list(var_names)))
    for name, layer in layers.items():
        adata.layers[name] = layer
    adata.obsm["spatial"] = cells.centroid.get_coordinates().values.reshape(len(cells), 2)
    adata.uns["segmentation"] = specs_by_name(specs)

    return TableModel.parse(adata, region=region, region_key="region", instance_key="cell_id")


def compartment_layer(image, shapes, cells, statistics, tile_size=TILE_SIZE):
    """Statistics for `shapes` (indexed by cell id), rows aligned to `cells`; NaN where a cell has none.

    Also returns the largest read window side in px.
    """
    import numpy as np

    out = np.full((len(cells), len(image.coords["c"]) * len(statistics)), np.nan, dtype=np.float32)
    present = cells.index.isin(shapes.index)
    window = 0
    if present.any():
        out[present], window = measure_intensities(
            image, shapes.loc[cells.index[present]], statistics, tile_size
        )
    return out, window


def parse_args(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--sdata", required=True, help="SpatialData store; only read")
    parser.add_argument(
        "--method", required=True, help="method name; the table's region is {method}_{target}"
    )
    parser.add_argument(
        "--shapes", required=True, help="parquet from RESOLVE whose shapes are the table's rows"
    )
    parser.add_argument(
        "--target",
        choices=("cells", "nuclei"),
        default="cells",
        help="what --shapes holds; nuclei only in a nuclei-only run (default: cells)",
    )
    parser.add_argument("--nuclei-compartment", help="nuclei parquet indexed by cell id (layer 'nucleus')")
    parser.add_argument("--cytoplasm", help="cytoplasm parquet indexed by cell id (layer 'cytoplasm')")
    parser.add_argument("--links", help="parquet of per-cell obs columns indexed by cell id")
    parser.add_argument("--specs", required=True, help="JSON list of this method's spec maps")
    parser.add_argument("--slide", required=True, help="slide name from the samplesheet")
    parser.add_argument("--core-id", help="TMA core ID; omit off-TMA")
    parser.add_argument(
        "--expand-radius-ratio",
        type=float,
        default=0,
        help="expand the measured objects (--shapes: cells, or nuclei in a nuclei-only run) for X only, "
        "not the layers; obs area and obsm spatial stay unexpanded",
    )
    parser.add_argument("--output", required=True, help="h5ad file to write")
    args = parser.parse_args(argv)
    if args.target == "nuclei" and (args.nuclei_compartment or args.cytoplasm or args.links):
        parser.error("--nuclei-compartment, --cytoplasm and --links need --target cells")
    return args


def main() -> int:
    args = parse_args()

    import geopandas as gpd
    import pandas as pd
    import spatialdata as sd
    from sopa.shapes import expand_radius
    from sopa.utils import get_spatial_image

    from resolve_segmentation import store_image_key

    specs = json.loads(Path(args.specs).read_text())
    image_key = store_image_key(args.sdata)
    sdata = sd.read_zarr(args.sdata)
    image = get_spatial_image(sdata, image_key)
    var_names = [str(c) for c in image.coords["c"].values]

    # RESOLVE shapes are already in this image's pixel coordinates (identity transform).
    cells = gpd.read_parquet(args.shapes)
    measured = expand_radius(cells, args.expand_radius_ratio)
    x = measure_intensities(image, measured, ["mean"])[0]

    layers = {}
    if args.nuclei_compartment:
        layers["nucleus"] = compartment_layer(
            image, gpd.read_parquet(args.nuclei_compartment), cells, ["mean"]
        )[0]
    if args.cytoplasm:
        layers["cytoplasm"] = compartment_layer(image, gpd.read_parquet(args.cytoplasm), cells, ["mean"])[0]
    obs_extra = pd.read_parquet(args.links).reindex(cells.index) if args.links else None

    table = build_table(
        cells,
        x,
        var_names,
        layers,
        obs_extra,
        f"{args.method}_{args.target}",
        args.slide,
        args.core_id,
        specs,
    )
    table.write_h5ad(args.output)
    print(
        f"[aggregate] {args.method}: {table.n_obs} {args.target} x {table.n_vars} markers, layers {sorted(layers)}"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
