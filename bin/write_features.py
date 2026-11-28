#!/usr/bin/env python3
"""Write learned-feature shapes and tables into the SpatialData store.

Tables are `{method}_{model}.h5ad` (region `{method}_cells`), VirTues niche tables (region a
shapes file in this write) and tables without a region. Each is checked against its region
before the store is touched. An element of the same name is removed by path first, so a retry
or -resume gives the same result.
"""

from __future__ import annotations

import argparse
import re
import shutil
import sys
from pathlib import Path

from write_segmentations import image_transformations, reconsolidate, write_element

# spatialdata is imported inside functions so the module imports without it.


def check_table(name: str, adata, sdata_path: Path, shape_index: dict) -> None:
    """Raise ValueError unless the table's rows fit its region; no region means no check."""
    import anndata as ad

    attrs = adata.uns.get("spatialdata_attrs") or {}
    region = attrs.get("region")
    if region is None:
        return
    match = re.fullmatch(r"(.+)_cells", region) if isinstance(region, str) else None
    if match:
        base = f"{match.group(1)}_table"
        reference = ad.read_zarr(sdata_path / "tables" / base)
        if not adata.obs_names.equals(reference.obs_names):
            raise ValueError(f"table '{name}' rows differ from '{base}' (names or order); refusing to write")
    elif isinstance(region, str) and region in shape_index:
        ids = adata.obs[attrs["instance_key"]].astype(str).tolist()
        if ids != shape_index[region]:
            raise ValueError(
                f"table '{name}' rows differ from shapes '{region}' (ids or order); refusing to write"
            )
    else:
        raise ValueError(f"table '{name}' has region {region!r}: not a cells region nor shapes in this write")


def write_features(sdata_path: Path, tables: list[Path], shapes: list[Path] = ()) -> None:
    import anndata as ad
    import geopandas as gpd
    import spatialdata as sd
    from spatialdata.models import ShapesModel

    _, transformations = image_transformations(sdata_path)

    # Validate everything before touching the store.
    gdfs = {p.stem: gpd.read_parquet(p) for p in shapes}
    shape_index = {name: gdf.index.astype(str).tolist() for name, gdf in gdfs.items()}
    adatas = {p.stem: ad.read_h5ad(p) for p in tables}
    for name, adata in adatas.items():
        check_table(name, adata, sdata_path, shape_index)

    for kind, names in (("shapes", gdfs), ("tables", adatas)):
        for name in names:
            element = sdata_path / kind / name
            if element.is_dir():
                shutil.rmtree(element)
                print(f"[write_features] removed {kind} {name}: replaced by this write")
    reconsolidate(sdata_path)

    sdata = sd.read_zarr(sdata_path)
    for name, gdf in gdfs.items():
        write_element(sdata, name, ShapesModel.parse(gdf, transformations=transformations), "shapes")
    for name, adata in adatas.items():
        write_element(sdata, name, adata, "table")

    # Re-read: an in-place write that silently did nothing must not pass.
    check = sd.read_zarr(sdata_path)
    absent = [n for n in gdfs if n not in check.shapes] + [n for n in adatas if n not in check.tables]
    if absent:
        raise RuntimeError(f"not in {sdata_path} after writing: {absent}")
    print(f"[write_features] {sdata_path} :: shapes {list(gdfs)}, tables {list(adatas)}")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--sdata", required=True, type=Path, help="SpatialData .zarr store, written in place")
    ap.add_argument("--tables", nargs="*", default=[], type=Path, help="NAME.h5ad files")
    ap.add_argument("--shapes", nargs="*", default=[], type=Path, help="NAME.parquet GeoParquet files")
    args = ap.parse_args()
    write_features(args.sdata, args.tables, args.shapes)
    return 0


if __name__ == "__main__":
    sys.exit(main())
