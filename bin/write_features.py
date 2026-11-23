#!/usr/bin/env python3
"""Write learned-feature tables (`{method}_{model}.h5ad`) into the SpatialData store.

Each table must have the same rows, in the same order, as `tables/{method}_table`. An element
of the same name is removed by path first, so a retry or -resume gives the same result.
"""

from __future__ import annotations

import argparse
import shutil
import sys
from pathlib import Path

from write_segmentations import reconsolidate, write_element

# spatialdata is imported inside functions so the module imports without it.


def write_features(sdata_path: Path, tables: list[Path]) -> None:
    import anndata as ad
    import spatialdata as sd

    # Validate everything before touching the store.
    adatas = {}
    for path in tables:
        name = path.stem
        method = name.rsplit("_", 1)[0]
        base = f"{method}_table"
        reference = ad.read_zarr(sdata_path / "tables" / base)
        adata = ad.read_h5ad(path)
        if not adata.obs_names.equals(reference.obs_names):
            raise ValueError(f"table '{name}' rows differ from '{base}' (names or order); refusing to write")
        adatas[name] = adata

    for name in adatas:
        element = sdata_path / "tables" / name
        if element.is_dir():
            shutil.rmtree(element)
            print(f"[write_features] removed tables {name}: replaced by this write")
    reconsolidate(sdata_path)

    sdata = sd.read_zarr(sdata_path)
    for name, adata in adatas.items():
        write_element(sdata, name, adata, "table")

    # Re-read: an in-place write that silently did nothing must not pass.
    check = sd.read_zarr(sdata_path)
    absent = [n for n in adatas if n not in check.tables]
    if absent:
        raise RuntimeError(f"not in {sdata_path} after writing: {absent}")
    print(f"[write_features] {sdata_path} :: tables {list(adatas)}")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--sdata", required=True, type=Path, help="SpatialData .zarr store, written in place")
    ap.add_argument("--tables", nargs="+", default=[], type=Path, help="{method}_{model}.h5ad files")
    args = ap.parse_args()
    write_features(args.sdata, args.tables)
    return 0


if __name__ == "__main__":
    sys.exit(main())
