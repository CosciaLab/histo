#!/usr/bin/env python3
"""Write resolved shapes and aggregated tables into the SpatialData store.

The only task that writes them: parallel writers race on the store's root metadata. Element
name is the file stem (instanseg_cells.parquet -> instanseg_cells). An element already in the
store is deleted and rewritten, so a retry or -resume gives the same result. Shapes are
written first, then tables; `{image}_projected` is deleted unless --keep-projection.
An empty shapes file (e.g. no cytoplasm in a core without nuclei) writes no element.
Names matching RESERVED are pipeline-owned: one not in this write is removed, so a run with
fewer methods or targets leaves no leftovers.
"""

from __future__ import annotations

import argparse
import re
import shutil
import sys
import warnings
from pathlib import Path

# spatialdata is imported inside functions so the module imports without it.

SEGMENTATION_ATTR = "cell_segmentation_image"  # sopa's SopaAttrs.CELL_SEGMENTATION
RESERVED = re.compile(r"^(cellpose|instanseg)_(cells|nuclei|cytoplasm|table)$")
ELEMENT_KINDS = ("shapes", "tables")


def regions_of(adata) -> list[str]:
    """The shapes a TableModel-parsed table annotates."""
    attrs = adata.uns.get("spatialdata_attrs")
    if not attrs or "region" not in attrs:
        raise ValueError("no spatialdata_attrs/region (not TableModel-parsed)")
    region = attrs["region"]
    return [region] if isinstance(region, str) else list(region)


def elements_on_disk(sdata_path: Path, kind: str) -> set[str]:
    """Names of the element folders under `kind` (shapes, tables), read or not."""
    folder = sdata_path / kind
    return {e.name for e in folder.iterdir() if e.is_dir()} if folder.is_dir() else set()


def remove_stale(sdata_path: Path, keep: set[str]) -> list[str]:
    """Remove pipeline-owned shapes and tables not in `keep`, by path; returns their names."""
    removed = []
    for kind in ELEMENT_KINDS:
        for name in sorted(elements_on_disk(sdata_path, kind)):
            if RESERVED.match(name) and name not in keep:
                shutil.rmtree(sdata_path / kind / name)
                removed.append(name)
                print(f"[write_segmentations] removed stale {kind} {name}: not in this write")
    if removed:
        reconsolidate(sdata_path)
    return removed


def reconsolidate(sdata_path: Path) -> None:
    """Rewrite consolidated metadata after removals by path, if the store has it."""
    import zarr

    if not zarr.open_group(sdata_path, mode="r").metadata.consolidated_metadata:
        return
    with warnings.catch_warnings():
        # Shapes are parquet, not zarr; zarr warns about them, as spatialdata also silences.
        warnings.filterwarnings("ignore", category=zarr.errors.ZarrUserWarning)
        zarr.consolidate_metadata(sdata_path)


def delete_element(sdata, name: str) -> None:
    """Delete `name` if present, memory first, then disk."""
    if name in sdata:
        # The in-memory element must go first: spatialdata refuses to delete backing files.
        del sdata[name]
        sdata.delete_element_from_disk(name)


def replace_element(sdata, name: str, element, kind: str) -> None:
    """Delete `name` if present, then write `element` in its place."""
    delete_element(sdata, name)
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

    # Images only: other elements may be stale or half-written, and are dealt with below.
    images = sd.read_zarr(sdata_path, selection=("images",))
    image_key = images.attrs.get(SEGMENTATION_ATTR)
    if image_key is None:
        raise ValueError(f"{sdata_path} has no '{SEGMENTATION_ATTR}' attribute: no image to place shapes on")
    if image_key not in images.images:
        raise ValueError(f"'{SEGMENTATION_ATTR}' is '{image_key}' but {sdata_path} has no such image")
    transformations = get_transformation(images.images[image_key], get_all=True)

    # Read and validate everything before touching the store.
    gdfs = {p.stem: gpd.read_parquet(p) for p in shapes}
    # spatialdata cannot parse an empty GeoDataFrame; a stale element of the name is still removed.
    empty = sorted(name for name, gdf in gdfs.items() if len(gdf) == 0)
    shape_names = [p.stem for p in shapes if p.stem not in empty]
    table_names = [p.stem for p in tables]
    adatas = {p.stem: ad.read_h5ad(p) for p in tables}
    regions = {}
    for name, adata in adatas.items():
        try:
            regions[name] = regions_of(adata)
        except ValueError as e:
            raise ValueError(f"table '{name}': {e}") from e
    # A table may annotate shapes already in the store; those stay.
    keep = set(gdfs) | set(table_names) | {r for rs in regions.values() for r in rs}
    known = (set(shape_names) | elements_on_disk(sdata_path, "shapes")) - set(empty)
    for name in adatas:
        missing = [r for r in regions[name] if r not in known]
        if missing:
            raise ValueError(
                f"table '{name}' has region {missing} but no such shapes. Known: {sorted(known)}"
            )

    stale = remove_stale(sdata_path, keep)
    sdata = sd.read_zarr(sdata_path)
    for name in empty:
        delete_element(sdata, name)
        print(f"[write_segmentations] {name} is empty: no element written")
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
    left = [n for n in empty if n in check.shapes] + [n for n in stale if n in check]
    if left:
        raise RuntimeError(f"still in {sdata_path} though empty or stale: {left}")
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
