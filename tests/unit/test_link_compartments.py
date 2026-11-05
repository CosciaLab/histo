"""Tests for link_compartments.py: linking rules on hand-drawn polygons, outputs and their round-trip."""

import math
import sys

import pytest
from link_compartments import LINK_COLUMN, MIN_SHARE, link, main, polygonal, write_linked

pd = pytest.importorskip("pandas", reason="needs pandas")
gpd = pytest.importorskip("geopandas", reason="needs geopandas")
from shapely.geometry import GeometryCollection, LineString, MultiPolygon, Point, Polygon, box  # noqa: E402


def frame(geoms, names):
    return gpd.GeoDataFrame(geometry=geoms, index=pd.Index(names, name="cell_id"))


def cells(geoms, names=None):
    return frame(geoms, names or [f"img_cells_{i}" for i in range(len(geoms))])


def nuclei(geoms, names=None):
    return frame(geoms, names or [f"img_nuclei_{i}" for i in range(len(geoms))])


def linked_to(out, nucleus):
    value = out.nuclei.loc[nucleus, LINK_COLUMN]
    return None if pd.isna(value) else value


def test_min_share_is_half():
    assert MIN_SHARE == 0.5


def test_nucleus_mostly_inside_links_and_minority_share_does_not():
    c = cells([box(0, 0, 10, 10), box(20, 0, 30, 10)])
    # 80% inside cell 0; 40% inside cell 1 (the rest is outside every cell)
    n = nuclei([box(2, 4, 12, 6), box(26, 4, 36, 6)])
    out = link(c, n)
    assert linked_to(out, "img_nuclei_0") == "img_cells_0"
    assert linked_to(out, "img_nuclei_1") is None
    assert out.links.loc["img_cells_1", "n_nuclei"] == 0


def test_two_nuclei_union_clipped_and_largest_is_nucleus_id():
    c = cells([box(0, 0, 10, 10)])
    small = box(1, 1, 3, 3)  # area 4
    large = box(5, 4, 11, 8)  # area 24, 20 inside the cell
    out = link(c, nuclei([small, large]))
    row = out.links.loc["img_cells_0"]
    assert row["n_nuclei"] == 2
    assert row["nucleus_id"] == "img_nuclei_1"
    compartment = out.nucleus_compartment.geometry.loc["img_cells_0"]
    assert compartment.equals(small.union(box(5, 4, 10, 8)))
    assert row["nucleus_area"] == pytest.approx(24)


def test_nucleus_sticking_out_is_clipped_and_cytoplasm_is_the_rest():
    c = cells([box(0, 0, 10, 10)])
    out = link(c, nuclei([box(6, 2, 12, 8)]))  # 4x6 of 6x6 inside: share 2/3
    compartment = out.nucleus_compartment.geometry.loc["img_cells_0"]
    assert compartment.equals(box(6, 2, 10, 8))
    cytoplasm = out.cytoplasm.geometry.loc["img_cells_0"]
    assert cytoplasm.equals(box(0, 0, 10, 10).difference(box(6, 2, 10, 8)))
    assert out.links.loc["img_cells_0", "cytoplasm_area"] == pytest.approx(100 - 24)


def test_nucleus_inside_gives_a_ring_cytoplasm():
    c = cells([box(0, 0, 10, 10)])
    out = link(c, nuclei([box(3, 3, 7, 7)]))
    cytoplasm = out.cytoplasm.geometry.loc["img_cells_0"]
    assert isinstance(cytoplasm, Polygon)
    assert len(cytoplasm.interiors) == 1
    assert out.links.loc["img_cells_0", "cytoplasm_area"] == pytest.approx(84)
    assert out.links.loc["img_cells_0", "nucleus_area"] == pytest.approx(16)


def test_nucleus_filling_the_cell_leaves_no_cytoplasm_row():
    c = cells([box(0, 0, 10, 10), box(20, 0, 30, 10)])
    n = nuclei([box(0, 0, 10, 10), box(23, 3, 27, 7)])
    out = link(c, n)
    assert "img_cells_0" not in out.cytoplasm.index
    assert "img_cells_0" in out.nucleus_compartment.index
    assert out.links.loc["img_cells_0", "cytoplasm_area"] == 0
    assert "img_cells_1" in out.cytoplasm.index


def test_cell_without_nucleus_has_no_compartment_rows():
    c = cells([box(0, 0, 10, 10), box(20, 0, 30, 10)])
    out = link(c, nuclei([box(2, 2, 4, 4)]))
    row = out.links.loc["img_cells_1"]
    assert row["n_nuclei"] == 0
    assert pd.isna(row["nucleus_id"])
    assert row["nucleus_area"] == 0
    assert math.isnan(row["cytoplasm_area"])
    assert "img_cells_1" not in out.nucleus_compartment.index
    assert "img_cells_1" not in out.cytoplasm.index


def test_even_split_links_to_the_first_cell_in_frame_order():
    # labels sort the other way, so this tests order, not label
    c = cells([box(0, 0, 10, 10), box(10, 0, 20, 10)], names=["img_cells_9", "img_cells_1"])
    out = link(c, nuclei([box(8, 4, 12, 6)]))
    assert linked_to(out, "img_nuclei_0") == "img_cells_9"
    assert out.links.loc["img_cells_1", "n_nuclei"] == 0


def test_polygonal_drops_lines_and_points():
    poly = box(0, 0, 1, 1)
    collection = GeometryCollection([poly, LineString([(2, 2), (3, 3)]), Point(5, 5)])
    assert polygonal(collection).equals(poly)
    assert polygonal(GeometryCollection([LineString([(0, 0), (1, 1)])])) is None
    assert polygonal(Polygon()) is None
    two = GeometryCollection([poly, box(5, 5, 6, 6), LineString([(2, 2), (3, 3)])])
    assert isinstance(polygonal(two), MultiPolygon)


def test_overlay_returning_lines_keeps_only_the_polygon():
    # U-shaped cell with a notch at the top; the nucleus reaches into the notch, so its
    # intersection with the cell is a polygon plus two lines along the notch walls.
    cell = box(0, 0, 10, 10).difference(box(4, 5, 6, 10))
    nucleus = box(1, 1, 9, 4).union(box(4, 4, 6, 8))
    assert isinstance(nucleus.intersection(cell), GeometryCollection)
    out = link(cells([cell]), nuclei([nucleus]))
    compartment = out.nucleus_compartment.geometry.loc["img_cells_0"]
    cytoplasm = out.cytoplasm.geometry.loc["img_cells_0"]
    assert isinstance(compartment, (Polygon, MultiPolygon))
    assert isinstance(cytoplasm, (Polygon, MultiPolygon))
    assert compartment.area == pytest.approx(26)
    assert cytoplasm.area == pytest.approx(cell.area - 26)


def aggregate_links(c, out, tmp_path):
    """Feed the written links parquet through aggregation's table assembly and h5ad writer, as AGGREGATE does."""
    pytest.importorskip("anndata", reason="needs anndata")
    pytest.importorskip("spatialdata", reason="needs spatialdata")
    import anndata as ad
    import numpy as np
    from aggregate_compartments import build_table, obs_columns, stat_var

    write_linked(out, "m", tmp_path / "linked")
    links = pd.read_parquet(tmp_path / "linked" / "m_links.parquet").reindex(c.index)
    compartment = gpd.read_parquet(tmp_path / "linked" / "m_nucleus_compartment.parquet")
    obs_extra = obs_columns(c, "cells", compartment, links)
    quantification = {"statistics": ["mean"], "tile_size": 2048, "max_window_px": 0}
    table = build_table(
        c,
        np.zeros((len(c), 1)),
        stat_var(["ch0"], ["mean"]),
        {},
        obs_extra,
        "m_cells",
        "slide",
        None,
        [],
        quantification,
    )
    table.write_h5ad(tmp_path / "table.h5ad")
    return ad.read_h5ad(tmp_path / "table.h5ad").obs


def test_empty_nuclei_frame_links_nothing(tmp_path):
    c = cells([box(0, 0, 10, 10), box(20, 0, 30, 10)])
    out = link(c, nuclei([]))
    assert list(out.links["n_nuclei"]) == [0, 0]
    assert len(out.nuclei) == 0
    assert len(out.nucleus_compartment) == 0
    assert len(out.cytoplasm) == 0
    obs = aggregate_links(c, out, tmp_path)
    assert list(obs["n_nuclei"]) == [0, 0]
    assert obs["nucleus_id"].isna().all()


def test_all_nuclei_unlinked_still_aggregates(tmp_path):
    c = cells([box(0, 0, 10, 10), box(20, 0, 30, 10)])
    out = link(c, nuclei([box(50, 50, 52, 52)]))
    assert out.nuclei[LINK_COLUMN].isna().all()
    write_linked(out, "m", tmp_path / "nuc")
    back = gpd.read_parquet(tmp_path / "nuc" / "m_nuclei.parquet")
    assert back[LINK_COLUMN].isna().all()
    obs = aggregate_links(c, out, tmp_path)
    assert obs["nucleus_id"].isna().all()
    assert obs["cytoplasm_area"].isna().all()


def test_invalid_polygons_are_repaired_and_counted(capsys):
    bowtie_cell = Polygon([(0, 0), (10, 10), (10, 0), (0, 10)])  # two triangles meeting at (5, 5)
    bowtie_nucleus = Polygon([(20, 0), (24, 4), (24, 0), (20, 4)])
    c = cells([bowtie_cell, box(18, -2, 26, 6)])
    n = nuclei([box(8, 4, 9, 6), bowtie_nucleus, Polygon([(30, 0), (31, 1), (32, 2), (30, 0)])])
    out = link(c, n)
    assert linked_to(out, "img_nuclei_0") == "img_cells_0"
    assert linked_to(out, "img_nuclei_1") == "img_cells_1"
    assert linked_to(out, "img_nuclei_2") is None
    assert out.nuclei.geometry.loc["img_nuclei_1"].equals(bowtie_nucleus)  # output keeps input geometry
    log = capsys.readouterr().out
    assert "[link] cells: 1 of 2 repaired; 0 empty, not linked" in log
    assert "[link] nuclei: 2 of 3 repaired; 1 empty, not linked" in log


def test_cytoplasm_sliver_counts_as_none():
    c = cells([box(0, 0, 10, 10)])
    out = link(c, nuclei([box(0, 0, 10 - 1e-9, 10)]))
    assert "img_cells_0" not in out.cytoplasm.index
    assert out.links.loc["img_cells_0", "cytoplasm_area"] == 0


def test_nucleus_across_three_cells():
    c = cells([box(0, 0, 10, 10), box(10, 0, 20, 10), box(20, 0, 30, 10)])
    # shares 4/15, 10/15, 1/15; then 6/22, 10/22, 6/22
    out = link(c, nuclei([box(6, 0, 21, 1), box(4, 2, 26, 3)]))
    assert linked_to(out, "img_nuclei_0") == "img_cells_1"
    assert linked_to(out, "img_nuclei_1") is None


def test_nucleus_only_touching_a_cell_is_unlinked():
    out = link(cells([box(0, 0, 10, 10)]), nuclei([box(10, 0, 12, 2)]))
    assert linked_to(out, "img_nuclei_0") is None
    assert out.links.loc["img_cells_0", "n_nuclei"] == 0


def test_every_cell_appears_once_in_links_in_cell_order():
    c = cells([box(0, 0, 10, 10), box(10, 0, 20, 10), box(40, 0, 50, 10)])
    n = nuclei([box(2, 2, 4, 4), box(5, 5, 7, 7), box(12, 2, 14, 4), box(8, 4, 12, 6)])
    out = link(c, n)
    assert list(out.links.index) == list(c.index)
    assert out.links.index.name == "cell_id"
    assert list(out.links["n_nuclei"]) == [3, 1, 0]


def test_duplicate_index_raises():
    with pytest.raises(ValueError, match="cells index is not unique"):
        link(cells([box(0, 0, 1, 1), box(2, 2, 3, 3)], names=["a", "a"]), nuclei([]))
    with pytest.raises(ValueError, match="nuclei index is not unique"):
        link(cells([box(0, 0, 1, 1)]), nuclei([box(0, 0, 1, 1), box(0, 0, 1, 1)], names=["n", "n"]))


def test_nothing_is_dropped_from_nuclei():
    c = cells([box(0, 0, 10, 10)])
    n = nuclei([box(2, 2, 4, 4), box(50, 50, 52, 52)])
    n["score"] = [0.9, 0.1]
    out = link(c, n)
    assert list(out.nuclei.index) == list(n.index)
    assert out.nuclei.index.name == "cell_id"
    assert list(out.nuclei["score"]) == [0.9, 0.1]


def test_written_parquets_round_trip(tmp_path):
    c = cells([box(0, 0, 10, 10), box(20, 0, 30, 10)])
    n = nuclei([box(3, 3, 7, 7), box(50, 50, 52, 52)])
    write_linked(link(c, n), "instanseg", tmp_path / "linked")
    names = sorted(p.name for p in (tmp_path / "linked").iterdir())
    assert names == [
        "instanseg_cytoplasm.parquet",
        "instanseg_links.parquet",
        "instanseg_nuclei.parquet",
        "instanseg_nucleus_compartment.parquet",
    ]
    back = gpd.read_parquet(tmp_path / "linked" / "instanseg_nuclei.parquet")
    assert back.index.name == "cell_id"
    assert back.loc["img_nuclei_0", LINK_COLUMN] == "img_cells_0"
    assert pd.isna(back.loc["img_nuclei_1", LINK_COLUMN])
    links = pd.read_parquet(tmp_path / "linked" / "instanseg_links.parquet")
    assert links.index.name == "cell_id"
    assert list(links.columns) == ["n_nuclei", "nucleus_id", "nucleus_area", "cytoplasm_area"]
    for name in ("cytoplasm", "nucleus_compartment"):
        shapes = gpd.read_parquet(tmp_path / "linked" / f"instanseg_{name}.parquet")
        assert shapes.index.name == "cell_id"
        assert list(shapes.index) == ["img_cells_0"]


def test_cli_writes_all_four_files_even_without_nuclei(tmp_path, monkeypatch):
    cells([box(0, 0, 10, 10)]).to_parquet(tmp_path / "cells.parquet")
    nuclei([]).to_parquet(tmp_path / "nuclei.parquet")
    argv = ["link_compartments.py", "--cells", str(tmp_path / "cells.parquet")]
    argv += ["--nuclei", str(tmp_path / "nuclei.parquet"), "--method", "cellpose"]
    argv += ["--out-dir", str(tmp_path / "linked")]
    monkeypatch.setattr(sys, "argv", argv)
    assert main() == 0
    assert len(list((tmp_path / "linked").glob("cellpose_*.parquet"))) == 4
    links = pd.read_parquet(tmp_path / "linked" / "cellpose_links.parquet")
    assert list(links["n_nuclei"]) == [0]
