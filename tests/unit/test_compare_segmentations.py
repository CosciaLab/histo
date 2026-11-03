"""Tests for compare_segmentations.py: one-to-one IoU matching, the JSON contract and the page."""

import json
import math

import pytest
from compare_segmentations import MIN_IOU, grey_channel, match_share, summarise

np = pytest.importorskip("numpy", reason="needs numpy")
pd = pytest.importorskip("pandas", reason="needs pandas")
gpd = pytest.importorskip("geopandas", reason="needs geopandas")
from shapely.geometry import box  # noqa: E402


def frame(geoms, prefix="img_cells"):
    return gpd.GeoDataFrame(
        geometry=geoms, index=pd.Index([f"{prefix}_{i}" for i in range(len(geoms))], name="cell_id")
    )


def grid(n, shift=0.0, size=10.0):
    """n squares in a row, 2 px apart, shifted right by `shift`."""
    return frame([box(i * (size + 2) + shift, 0, i * (size + 2) + shift + size, size) for i in range(n)])


def test_min_iou_is_half():
    assert MIN_IOU == 0.5


def test_identical_frames_match_fully():
    a = grid(5)
    assert match_share(a, a.copy()) == 1.0


def test_shifted_by_half_a_width_matches_nothing():
    # IoU of a square and its half-width shift is 1/3.
    assert match_share(grid(5), grid(5, shift=5.0)) == 0.0


def test_one_extra_cell_in_b():
    n = 4
    a, b = grid(n), grid(n + 1)
    assert match_share(a, b) == 1.0
    assert match_share(b, a) == pytest.approx(n / (n + 1))


def test_iou_of_exactly_half_matches():
    a = frame([box(0, 0, 2, 1)])
    b = frame([box(0, 0, 1, 1)])
    assert match_share(a, b) == 1.0


def test_each_b_is_used_once():
    # Two overlapping a cells both reach IoU >= 0.5 with the one b cell; only the better one matches.
    b = frame([box(0, 0, 10, 10)])
    a = frame([box(0, 0, 10, 10), box(0, 0, 10, 8)])
    assert match_share(a, b) == 0.5
    assert match_share(b, a) == 1.0


def test_empty_a_is_nan_and_empty_b_is_zero():
    empty = frame([])
    assert math.isnan(match_share(empty, grid(3)))
    assert match_share(grid(3), empty) == 0.0


def test_invalid_polygon_is_repaired_not_raised():
    from shapely.geometry import Polygon

    # Repaired into two triangles of area 25 each, so IoU with the square is exactly 0.5.
    bowtie = Polygon([(0, 0), (10, 10), (10, 0), (0, 10)])
    assert match_share(frame([bowtie]), frame([box(0, 0, 10, 10)])) == 1.0


def test_input_frames_are_left_unchanged():
    from shapely.geometry import Polygon

    bowtie = Polygon([(0, 0), (10, 10), (10, 0), (0, 10)])
    a, b = frame([bowtie]), frame([box(0, 0, 10, 10)])
    match_share(a, b)
    assert a.geometry.iloc[0] is bowtie
    assert not a.geometry.iloc[0].is_valid


def test_repaired_is_a_valid_copy():
    from compare_segmentations import repaired
    from shapely.geometry import Polygon

    bowtie = Polygon([(0, 0), (10, 10), (10, 0), (0, 10)])
    a = frame([bowtie, box(0, 0, 1, 1)])
    out = repaired(a)
    assert out.geometry.is_valid.all()
    assert out.geometry.iloc[0].area == pytest.approx(50.0)
    assert list(out.index) == list(a.index)
    assert a.geometry.iloc[0] is bowtie


class TestGreyChannel:
    def test_first_nuclear_looking_name(self):
        assert grey_channel(["CD3", "Hoechst", "DAPI_2"]) == (1, "Hoechst")

    def test_case_insensitive(self):
        assert grey_channel(["CD3", "dapi"]) == (1, "dapi")

    def test_falls_back_to_channel_0(self):
        assert grey_channel(["CD3", "CD8"]) == (0, "CD3")


class TestSummarise:
    def test_keys_and_values(self):
        out = summarise({"cellpose": grid(4), "instanseg": grid(5)})
        assert out["min_iou"] == 0.5
        assert out["n_matched"] == 4
        assert out["methods"]["cellpose"] == {"n_cells": 4, "median_area_px2": 100.0, "match_share": 1.0}
        assert out["methods"]["instanseg"]["match_share"] == pytest.approx(0.8)

    def test_empty_method_gives_null_not_nan(self):
        out = summarise({"cellpose": frame([]), "instanseg": grid(2)})
        text = json.dumps(out, allow_nan=False)
        assert json.loads(text)["methods"]["cellpose"] == {
            "n_cells": 0,
            "median_area_px2": None,
            "match_share": None,
        }

    def test_needs_exactly_two_methods(self):
        with pytest.raises(ValueError, match="two"):
            summarise({"cellpose": grid(2)})


def make_store(path, image):
    """A store with one image element named by `cell_segmentation_image`, as qc_metrics reads it."""
    zarr = pytest.importorskip("zarr")
    element = path / "images" / "img"
    element.mkdir(parents=True)
    arr = zarr.create_array(
        store=str(element / "s0"), shape=image.shape, dtype=image.dtype, chunks=(1, 16, 16)
    )
    arr[:] = image
    labels = ["CD3", "DAPI"][: image.shape[0]]
    meta = {
        "zarr_format": 3,
        "node_type": "group",
        "attributes": {"ome": {"omero": {"channels": [{"label": n} for n in labels]}}},
    }
    (element / "zarr.json").write_text(json.dumps(meta))
    (path / "zarr.json").write_text(
        json.dumps({"zarr_format": 3, "node_type": "group", "attributes": {"cell_segmentation_image": "img"}})
    )


def write_shapes(store, name, gdf):
    d = store / "shapes" / name
    d.mkdir(parents=True)
    gdf.to_parquet(d / "shapes.parquet")


def test_main_writes_json_and_html(tmp_path, monkeypatch):
    import compare_segmentations

    store = tmp_path / "s.zarr"
    rng = np.random.default_rng(0)
    make_store(store, rng.integers(0, 1000, size=(2, 64, 64), dtype=np.uint16))
    write_shapes(store, "cellpose_cells", grid(4))
    write_shapes(store, "instanseg_cells", grid(5))

    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(
        "sys.argv", ["compare_segmentations.py", "--sdata", str(store), "--prefix", "s", "--window", "32"]
    )
    assert compare_segmentations.main() == 0

    out = json.loads((tmp_path / "s_comparison.json").read_text())
    assert out["sample"] == "s"
    assert out["image"] == "img"
    assert out["channel"] == "DAPI"
    assert out["methods"]["instanseg"]["n_cells"] == 5
    assert 1 <= len(out["crops"]) <= 3
    page = (tmp_path / "s_comparison.html").read_text()
    assert "cellpose" in page and "instanseg" in page
    assert page.count("data:image/png;base64,") == len(out["crops"])


def test_main_names_a_missing_element(tmp_path, monkeypatch):
    import compare_segmentations

    store = tmp_path / "s.zarr"
    make_store(store, np.zeros((1, 16, 16), dtype=np.uint16))
    write_shapes(store, "cellpose_cells", grid(2))
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr("sys.argv", ["compare_segmentations.py", "--sdata", str(store), "--prefix", "s"])
    with pytest.raises(FileNotFoundError, match="instanseg_cells"):
        compare_segmentations.main()
