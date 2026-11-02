#!/usr/bin/env python3
"""Mean marker intensity per cell, one AnnData table per method, written to a file.

Copied from sopa 2.2.12 (BSD 3-Clause, licence below) with two changes: polygon holes are
honoured, so a cytoplasm ring is not measured as the whole cell, and the mask origin follows the
clipped chunk (an upstream chunk-edge bug).
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


def mean_intensities(image, shapes):
    """Mean intensity per shape and channel: array (n_shapes, n_channels). Image and shapes share pixel coordinates."""
    # From sopa 2.2.12 (aggregation/channels.py::_aggregate_channels_aligned, mode "average");
    # changes: hole-aware rasterize, mask origin follows the clipped chunk, NaN for empty masks,
    # returns the array instead of an AnnData
    import dask
    import numpy as np
    import shapely
    from shapely.geometry import box

    cells = shapes.geometry.tolist()
    tree = shapely.STRtree(cells)

    n_channels = len(image.coords["c"])
    areas = np.zeros(len(cells))
    aggregation = np.zeros((len(cells), n_channels))

    chunk_sizes = image.data.chunks
    offsets_y = np.cumsum(np.pad(chunk_sizes[1], (1, 0), "constant"))
    offsets_x = np.cumsum(np.pad(chunk_sizes[2], (1, 0), "constant"))

    def _average_chunk_inside_cells(chunk, iy, ix):
        ymin, ymax = offsets_y[iy], offsets_y[iy + 1]
        xmin, xmax = offsets_x[ix], offsets_x[ix + 1]

        patch = box(xmin, ymin, xmax, ymax)
        intersections = tree.query(patch, predicate="intersects")

        for index in intersections:
            cell = cells[index]
            bounds = pixel_outer_bounds(cell.bounds)

            sub_image = chunk[
                :,
                max(bounds[1] - ymin, 0) : bounds[3] - ymin,
                max(bounds[0] - xmin, 0) : bounds[2] - xmin,
            ]

            if sub_image.shape[1] == 0 or sub_image.shape[2] == 0:
                continue

            mask = rasterize(cell, sub_image.shape[1:], (max(bounds[0], xmin), max(bounds[1], ymin)))

            areas[index] += np.sum(mask)
            aggregation[index] += np.sum(sub_image * mask, axis=(1, 2))

    tasks = [
        dask.delayed(_average_chunk_inside_cells)(chunk, iy, ix)
        for iy, row in enumerate(image.chunk({"c": -1}).data.to_delayed()[0])
        for ix, chunk in enumerate(row)
    ]
    # synchronous: tasks add into shared per-cell arrays, which threads would race on
    dask.compute(tasks, scheduler="synchronous")

    with np.errstate(invalid="ignore", divide="ignore"):
        return np.where(areas[:, None] > 0, aggregation / areas[:, None], np.nan)


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


def compartment_layer(image, shapes, cells):
    """Mean intensities for `shapes` (indexed by cell id), as rows aligned to `cells`; NaN where a cell has none."""
    import numpy as np

    out = np.full((len(cells), len(image.coords["c"])), np.nan)
    present = cells.index.isin(shapes.index)
    if present.any():
        out[present] = mean_intensities(image, shapes.loc[cells.index[present]])
    return out


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--sdata", required=True, help="SpatialData store; only read")
    parser.add_argument("--method", required=True, help="method name; the table's region is {method}_cells")
    parser.add_argument("--cells", required=True, help="cells parquet from RESOLVE")
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
        help="expand cells for measuring (cell compartment only); obs area and obsm spatial stay unexpanded",
    )
    parser.add_argument("--output", required=True, help="h5ad file to write")
    args = parser.parse_args()

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
    cells = gpd.read_parquet(args.cells)
    measured = expand_radius(cells, args.expand_radius_ratio)
    x = mean_intensities(image, measured)

    layers = {}
    if args.nuclei_compartment:
        layers["nucleus"] = compartment_layer(image, gpd.read_parquet(args.nuclei_compartment), cells)
    if args.cytoplasm:
        layers["cytoplasm"] = compartment_layer(image, gpd.read_parquet(args.cytoplasm), cells)
    obs_extra = pd.read_parquet(args.links).reindex(cells.index) if args.links else None

    table = build_table(
        cells, x, var_names, layers, obs_extra, f"{args.method}_cells", args.slide, args.core_id, specs
    )
    table.write_h5ad(args.output)
    print(f"[aggregate] {args.method}: {table.n_obs} cells x {table.n_vars} markers, layers {sorted(layers)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
