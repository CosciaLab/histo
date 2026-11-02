#!/usr/bin/env python3
"""Merge one spec's patch parquets into one GeoParquet, resolving overlaps with sopa.

Nothing is written into the SpatialData store: parallel writers would race on its root
metadata. WRITE_SEGMENTATIONS is the only writer and takes the element name from the file stem.
The store is only read, for the attribute naming the image that ids are built on.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

SEGMENTATION_ATTR = "cell_segmentation_image"  # sopa's SopaAttrs.CELL_SEGMENTATION


def store_image_key(sdata_path: str | Path) -> str:
    """The store's segmentation image, read from the root attributes without loading images."""
    root = Path(sdata_path)
    # zarr v3 stores keep attributes in zarr.json, v2 in .zattrs
    if (root / "zarr.json").exists():
        attrs = json.loads((root / "zarr.json").read_text()).get("attributes", {})
    elif (root / ".zattrs").exists():
        attrs = json.loads((root / ".zattrs").read_text())
    else:
        raise ValueError(f"{root} has no zarr.json or .zattrs; is it a SpatialData store?")
    if SEGMENTATION_ATTR not in attrs:
        raise ValueError(f"store attribute '{SEGMENTATION_ATTR}' is missing; was the store prepared by sopa?")
    return attrs[SEGMENTATION_ATTR]


def read_patches(paths):
    """Concatenate patch parquets. 0-byte files (stubs) are skipped; 0-row frames (glass) are fine."""
    import geopandas as gpd
    import pandas as pd

    frames = [gpd.read_parquet(p) for p in paths if Path(p).stat().st_size > 0]
    if not frames:
        return gpd.GeoDataFrame(geometry=[])
    return gpd.GeoDataFrame(pd.concat(frames).reset_index(drop=True))


def check_not_empty(cells, name: str) -> None:
    if len(cells) == 0:
        raise ValueError(f"segmentation '{name}' found no cells")


def assign_ids(cells, image_key: str, target: str):
    """Index `{image_key}_{target}_{n}` named `cell_id`, n from 0; any incoming index is dropped."""
    out = cells.reset_index(drop=True)
    out.index = [f"{image_key}_{target}_{n}" for n in range(len(out))]
    out.index.name = "cell_id"
    return out


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--sdata", required=True)
    parser.add_argument("--spec", required=True, help="JSON file with one segmentation spec")
    parser.add_argument("--patches", required=True, nargs="+", help="patch parquet files of this spec")
    parser.add_argument("--output", required=True, help="parquet file to write")
    args = parser.parse_args()

    from sopa.segmentation import solve_conflicts

    spec = json.loads(Path(args.spec).read_text())
    image_key = store_image_key(args.sdata)

    cells = read_patches(args.patches)
    check_not_empty(cells, spec["name"])
    n_before = len(cells)
    cells = assign_ids(solve_conflicts(cells), image_key, spec["target"])
    print(f"[resolve] {spec['name']}: {n_before} patch cells -> {len(cells)} after resolving overlaps")
    cells.to_parquet(args.output)
    return 0


if __name__ == "__main__":
    sys.exit(main())
