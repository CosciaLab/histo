#!/usr/bin/env python3
"""Write resolved shapes and aggregated tables into the SpatialData store.

The only task that writes them: parallel writers race on the store's root metadata. Element
name is the file stem (instanseg_cells.parquet -> instanseg_cells). An element already in the
store is deleted and rewritten, so a retry or -resume gives the same result. Shapes are
written first, then tables; `{image}_projected` is deleted unless --keep-projection.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

# spatialdata is imported inside functions so the module imports without it.

SEGMENTATION_ATTR = "cell_segmentation_image"  # sopa's SopaAttrs.CELL_SEGMENTATION


def regions_of(adata) -> list[str]:
    """The shapes a TableModel-parsed table annotates."""
    attrs = adata.uns.get("spatialdata_attrs")
    if not attrs or "region" not in attrs:
        raise ValueError("no spatialdata_attrs/region (not TableModel-parsed)")
    region = attrs["region"]
    return [region] if isinstance(region, str) else list(region)


def replace_element(sdata, name: str, element, kind: str) -> None:
    """Delete `name` if present (memory first, then disk), then write `element` in its place."""
    if name in sdata:
        # The in-memory element must go first: spatialdata refuses to delete backing files.
        del sdata[name]
        sdata.delete_element_from_disk(name)
    sdata[name] = element
    sdata.write_element(name)
    print(f"[write_segmentations] wrote {kind} {name}")


def drop_projection(sdata, image_key: str) -> None:
    """Delete `{image_key}_projected` if present; a no-op otherwise."""
    name = f"{image_key}_projected"
    if name in sdata.images:
        del sdata[name]
        sdata.delete_element_from_disk(name)
        print(f"[write_segmentations] dropped {name}")


def write_segmentations(
    sdata_path: Path, shapes: list[Path], tables: list[Path], keep_projection: bool = False
) -> None:
    import anndata as ad
    import geopandas as gpd
    import spatialdata as sd
    from spatialdata.models import ShapesModel
    from spatialdata.transformations import get_transformation

    sdata = sd.read_zarr(sdata_path)
    image_key = sdata.attrs.get(SEGMENTATION_ATTR)
    if image_key is None:
        raise ValueError(f"{sdata_path} has no '{SEGMENTATION_ATTR}' attribute: no image to place shapes on")
    if image_key not in sdata.images:
        raise ValueError(f"'{SEGMENTATION_ATTR}' is '{image_key}' but {sdata_path} has no such image")
    transformations = get_transformation(sdata.images[image_key], get_all=True)

    shape_names = [p.stem for p in shapes]
    table_names = [p.stem for p in tables]
    # Read and validate everything before touching the store.
    gdfs = {p.stem: gpd.read_parquet(p) for p in shapes}
    adatas = {p.stem: ad.read_h5ad(p) for p in tables}
    known = set(shape_names) | set(sdata.shapes)
    for name, adata in adatas.items():
        try:
            missing = [r for r in regions_of(adata) if r not in known]
        except ValueError as e:
            raise ValueError(f"table '{name}': {e}") from e
        if missing:
            raise ValueError(
                f"table '{name}' has region {missing} but no such shapes. Known: {sorted(known)}"
            )

    for name in shape_names:
        replace_element(sdata, name, ShapesModel.parse(gdfs[name], transformations=transformations), "shapes")
    for name in table_names:
        replace_element(sdata, name, adatas[name], "table")
    if not keep_projection:
        drop_projection(sdata, image_key)

    # Re-read: an in-place write that silently did nothing must not pass.
    check = sd.read_zarr(sdata_path)
    absent = [n for n in shape_names if n not in check.shapes] + [
        n for n in table_names if n not in check.tables
    ]
    if absent:
        raise RuntimeError(f"not in {sdata_path} after writing: {absent}")
    for name in table_names:
        for region in regions_of(check.tables[name]):
            if region not in check.shapes:
                raise RuntimeError(f"table '{name}' region '{region}' is not a shape in {sdata_path}")
    print(f"[write_segmentations] {sdata_path} :: shapes {shape_names}, tables {table_names}")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--sdata", required=True, type=Path, help="SpatialData .zarr store, written in place")
    ap.add_argument("--shapes", nargs="*", default=[], type=Path, help="NAME.parquet GeoParquet files")
    ap.add_argument("--tables", nargs="*", default=[], type=Path, help="NAME.h5ad AnnData files")
    ap.add_argument("--keep-projection", action="store_true", help="leave {image}_projected in the store")
    args = ap.parse_args()
    write_segmentations(args.sdata, args.shapes, args.tables, args.keep_projection)
    return 0


if __name__ == "__main__":
    sys.exit(main())
