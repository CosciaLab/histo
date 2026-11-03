#!/usr/bin/env python3
"""Link resolved nuclei to resolved cells and derive each cell's nucleus and cytoplasm.

A nucleus links to the cell holding the largest share of its area, if that share is at least
MIN_SHARE; ties go to the cell first in the cells frame. A cell's nucleus compartment is the
union of its linked nuclei clipped to the cell; its cytoplasm is the cell minus that. Nothing
is dropped: unlinked nuclei keep an empty link. Writes four parquets, all indexed `cell_id`:
{method}_nuclei (the nuclei plus LINK_COLUMN), {method}_nucleus_compartment and
{method}_cytoplasm (cells with a non-empty one only) and {method}_links (one row per cell).
"""

from __future__ import annotations

import argparse
import sys
from dataclasses import dataclass
from pathlib import Path

# Heavy libraries are imported inside functions so the module imports without them.

MIN_SHARE = 0.5  # a nucleus belongs to a cell only if most of it lies there
# Not `cell_id`: the index is already named so, and pandas then calls groupby/reset_index ambiguous.
LINK_COLUMN = "linked_cell_id"


@dataclass
class Linked:
    nuclei: object  # GeoDataFrame: the input nuclei plus LINK_COLUMN (None when unlinked)
    links: object  # DataFrame, one row per cell: n_nuclei, nucleus_id, nucleus_area, cytoplasm_area
    nucleus_compartment: object  # GeoDataFrame indexed by cell
    cytoplasm: object  # GeoDataFrame indexed by cell


def polygonal(geom):
    """Only the polygonal parts of `geom` (overlays can add lines or points); None if none are left."""
    import shapely
    from shapely.geometry import GeometryCollection, MultiPolygon, Polygon

    if geom is None or geom.is_empty:
        return None
    if isinstance(geom, (Polygon, MultiPolygon)):
        return geom
    polys = []
    for part in shapely.get_parts(geom):
        if isinstance(part, Polygon) and not part.is_empty:
            polys.append(part)
        elif isinstance(part, (MultiPolygon, GeometryCollection)):
            nested = polygonal(part)
            if nested is not None:
                polys.extend(shapely.get_parts(nested))
    if not polys:
        return None
    return polys[0] if len(polys) == 1 else MultiPolygon(polys)


def check_unique(frame, name: str) -> None:
    dup = frame.index[frame.index.duplicated()]
    if len(dup):
        raise ValueError(f"{name} index is not unique: {list(dup[:5])}")


def link(cells, nuclei) -> Linked:
    """Apply the linking rules; `cells` and `nuclei` are GeoDataFrames with unique indices."""
    import geopandas as gpd
    import numpy as np
    import pandas as pd
    import shapely

    check_unique(cells, "cells")
    check_unique(nuclei, "nuclei")
    cell_geoms = np.asarray(cells.geometry.array, dtype=object)
    nuc_geoms = np.asarray(nuclei.geometry.array, dtype=object)
    nuc_area = shapely.area(nuc_geoms)

    # STRtree: O((cells + nuclei) log cells) plus one intersection per touching pair, not all pairs.
    nuc_pos, cell_pos = shapely.STRtree(cell_geoms).query(nuc_geoms, predicate="intersects")
    with np.errstate(divide="ignore", invalid="ignore"):
        share = (
            shapely.area(shapely.intersection(nuc_geoms[nuc_pos], cell_geoms[cell_pos])) / nuc_area[nuc_pos]
        )
    # Rounding keeps float noise from breaking an exact 50/50 tie or the >= MIN_SHARE bound.
    pairs = pd.DataFrame({"nuc": nuc_pos, "cell": cell_pos, "share": np.round(share, 9)})
    best = pairs.sort_values(["nuc", "share", "cell"], ascending=[True, False, True]).drop_duplicates("nuc")
    best = best[best["share"] >= MIN_SHARE].copy()
    best["area"] = nuc_area[best["nuc"].to_numpy()]

    linked_to = np.full(len(nuclei), None, dtype=object)
    linked_to[best["nuc"].to_numpy()] = cells.index[best["cell"].to_numpy()]
    out_nuclei = nuclei.copy()
    out_nuclei[LINK_COLUMN] = linked_to

    n_nuclei = np.zeros(len(cells), dtype=int)
    nucleus_id = np.full(len(cells), None, dtype=object)
    nucleus_area = np.zeros(len(cells))
    cytoplasm_area = np.full(len(cells), np.nan)  # undefined without a nucleus

    counts = best.groupby("cell").size()
    n_nuclei[counts.index.to_numpy()] = counts.to_numpy()
    largest = best.sort_values(["cell", "area", "nuc"], ascending=[True, False, True]).drop_duplicates("cell")
    nucleus_id[largest["cell"].to_numpy()] = nuclei.index[largest["nuc"].to_numpy()]

    # One union per cell; sorted by cell position, so rows follow the cells frame.
    unions = gpd.GeoDataFrame(
        {"cell": best["cell"].to_numpy()}, geometry=list(nuc_geoms[best["nuc"].to_numpy()])
    )
    unions = unions.dissolve(by="cell")
    pos = unions.index.to_numpy(dtype=int)
    compartment = np.array(
        [
            polygonal(g)
            for g in shapely.intersection(np.asarray(unions.geometry.array, dtype=object), cell_geoms[pos])
        ],
        dtype=object,
    )
    present = np.array([g is not None for g in compartment], dtype=bool)
    cytoplasm = np.full(len(pos), None, dtype=object)
    cytoplasm[present] = [
        polygonal(g) for g in shapely.difference(cell_geoms[pos[present]], compartment[present])
    ]
    nucleus_area[pos] = [0.0 if g is None else g.area for g in compartment]
    cytoplasm_area[pos] = [0.0 if g is None else g.area for g in cytoplasm]

    def shapes(geoms):
        keep = np.array([g is not None for g in geoms], dtype=bool)
        index = pd.Index(cells.index[pos[keep]], name="cell_id")
        return gpd.GeoDataFrame(geometry=list(geoms[keep]), index=index, crs=cells.crs)

    links = pd.DataFrame(
        {
            "n_nuclei": n_nuclei,
            "nucleus_id": nucleus_id,
            "nucleus_area": nucleus_area,
            "cytoplasm_area": cytoplasm_area,
        },
        index=pd.Index(cells.index, name="cell_id"),
    )
    return Linked(out_nuclei, links, shapes(compartment), shapes(cytoplasm))


def write_linked(linked: Linked, method: str, out_dir: Path) -> None:
    """Write the four parquets; file stems are element names for the writer."""
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    linked.nuclei.to_parquet(out_dir / f"{method}_nuclei.parquet")
    linked.nucleus_compartment.to_parquet(out_dir / f"{method}_nucleus_compartment.parquet")
    linked.cytoplasm.to_parquet(out_dir / f"{method}_cytoplasm.parquet")
    linked.links.to_parquet(out_dir / f"{method}_links.parquet")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cells", required=True, help="cells parquet from RESOLVE")
    parser.add_argument("--nuclei", required=True, help="nuclei parquet from RESOLVE")
    parser.add_argument("--method", required=True, help="method name; prefixes every output file")
    parser.add_argument("--out-dir", required=True, type=Path, help="directory to write into; created")
    args = parser.parse_args()

    import geopandas as gpd

    linked = link(gpd.read_parquet(args.cells), gpd.read_parquet(args.nuclei))
    write_linked(linked, args.method, args.out_dir)
    links = linked.links
    n_linked = int(linked.nuclei[LINK_COLUMN].notna().sum())
    print(
        f"[link] {args.method}: {n_linked} of {len(linked.nuclei)} nuclei linked; "
        f"{int((links['n_nuclei'] > 0).sum())} of {len(links)} cells have a nucleus, "
        f"{int((links['cytoplasm_area'] == 0).sum())} of them no cytoplasm"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
